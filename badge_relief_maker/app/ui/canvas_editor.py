"""Qt canvas for normalized image editing.

The canvas keeps the image in scene coordinates and treats the view transform
as the single source of truth for zoom.  Painting records remain normalized,
while the live brush is sized in screen pixels so zooming naturally exposes
finer image-space detail.
"""

from __future__ import annotations

import math

import numpy as np

try:
    from PySide6.QtCore import QPoint, QPointF, QRectF, QTimer, Qt, Signal
    from PySide6.QtGui import QColor, QCursor, QImage, QPainterPath, QPen, QPixmap
    from PySide6.QtWidgets import (
        QFrame,
        QGraphicsEllipseItem,
        QGraphicsPathItem,
        QGraphicsPixmapItem,
        QGraphicsRectItem,
        QGraphicsScene,
        QGraphicsView,
    )
except Exception:  # pragma: no cover - core-only installations
    QPoint = QPointF = QRectF = QTimer = Qt = Signal = None
    QCursor = QColor = QImage = QPainterPath = QPen = QPixmap = None
    QFrame = QGraphicsPathItem = QGraphicsRectItem = None
    QGraphicsEllipseItem = QGraphicsPixmapItem = QGraphicsScene = QGraphicsView = object

from ..core.canvas_edits import interpolate_points, screen_radius_to_normalized


def _pixmap_from_array(array: np.ndarray) -> QPixmap:
    values = np.asarray(array)
    if values.dtype.kind == "f":
        values = np.round(np.clip(values, 0.0, 1.0) * 255.0).astype(np.uint8)
    else:
        values = np.asarray(np.clip(values, 0, 255), dtype=np.uint8)
    if values.ndim == 2:
        image = QImage(
            values.data,
            values.shape[1],
            values.shape[0],
            values.strides[0],
            QImage.Format.Format_Grayscale8,
        ).copy()
    elif values.ndim == 3 and values.shape[2] == 4:
        pixels = np.ascontiguousarray(values)
        image = QImage(
            pixels.data,
            pixels.shape[1],
            pixels.shape[0],
            pixels.strides[0],
            QImage.Format.Format_RGBA8888,
        ).copy()
    elif values.ndim == 3 and values.shape[2] == 3:
        pixels = np.ascontiguousarray(values)
        image = QImage(
            pixels.data,
            pixels.shape[1],
            pixels.shape[0],
            pixels.strides[0],
            QImage.Format.Format_RGB888,
        ).copy()
    else:
        raise ValueError("canvas layer must be a 2D, RGB or RGBA array")
    return QPixmap.fromImage(image)


def _overlay(mask: np.ndarray, color: tuple[int, int, int]) -> np.ndarray:
    values = np.asarray(mask, dtype=bool)
    result = np.zeros((*values.shape, 4), dtype=np.uint8)
    result[values, :3] = np.asarray(color, dtype=np.uint8)
    result[values, 3] = 180
    return result


if Signal is not None:

    class CanvasEditor(QGraphicsView):
        """One image canvas with stable pan/zoom and live screen-space brushes."""

        stroke_started = Signal(object)
        stroke_points_changed = Signal(object)
        stroke_finished = Signal(object)
        normalized_clicked = Signal(object)
        zoom_changed = Signal(float)
        brush_size_changed = Signal(int)
        pan_state_changed = Signal(bool)

        MIN_BRUSH_SIZE_PX = 2
        MAX_BRUSH_SIZE_PX = 300
        MIN_ZOOM = 0.05
        MAX_ZOOM = 32.0

        def __init__(self, parent=None):
            self.scene = QGraphicsScene(parent)
            super().__init__(self.scene, parent)
            self.setObjectName("canvasEditor")
            self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            self.setMouseTracking(True)
            self.setDragMode(QGraphicsView.DragMode.NoDrag)
            # Pan and zoom are implemented explicitly below.  This avoids the
            # subtle interaction between AnchorUnderMouse and fitInView's
            # temporary transform.
            self.setTransformationAnchor(QGraphicsView.ViewportAnchor.NoAnchor)
            self.setResizeAnchor(QGraphicsView.ViewportAnchor.NoAnchor)
            self.setBackgroundBrush(QColor("#171b22"))
            self.setFrameShape(QFrame.Shape.NoFrame)

            self.image_width = 1
            self.image_height = 1
            self._zoom = 1.0  # actual scene-to-viewport scale, not a mode flag
            self._fit_pending = False
            self._space_pressed = False
            self._panning = False
            self._painting = False
            self._last_viewport: QPoint | None = None
            self._current_stroke: list[list[float]] = []
            self._stroke_radius_normalized: float | None = None
            self._last_stroke_radius_normalized: float | None = None
            self._brush_size_px = 24
            self.active_tool = "brush_add"
            self.overlay_opacity = 0.5

            self._items: dict[str, QGraphicsPixmapItem] = {}
            self.layer_order = (
                "background",
                "source",
                "solid",
                "height",
                "outline",
                "selection",
                "stroke",
                "cursor",
            )
            self.layers = {"background": self.backgroundBrush()}

            self.outline_item = QGraphicsPathItem()
            self.outline_item.setZValue(5)
            self.outline_item.setVisible(False)
            self.scene.addItem(self.outline_item)

            self.selection_item = QGraphicsRectItem()
            self.selection_item.setPen(QPen(QColor("#ffe08a"), 1.0, Qt.PenStyle.DashLine))
            self.selection_item.setBrush(Qt.BrushStyle.NoBrush)
            self.selection_item.setZValue(6)
            self.selection_item.setVisible(False)
            self.scene.addItem(self.selection_item)

            self._cursor_item = QGraphicsEllipseItem()
            self._cursor_item.setBrush(Qt.BrushStyle.NoBrush)
            self._cursor_item.setZValue(20)
            self._cursor_item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
            self.scene.addItem(self._cursor_item)
            self._cursor_item.setVisible(False)
            self.brush_cursor = self._cursor_item
            self._stroke_item = None

        # -------------------------------------------------------------- state
        @property
        def zoom(self) -> float:
            """Return the actual scene-to-viewport scale."""
            return float(self._zoom)

        @property
        def zoom_percent(self) -> int:
            return int(round(self.zoom * 100.0))

        @property
        def view_scale(self) -> float:
            return self.zoom

        @property
        def brush_size_px(self) -> int:
            return int(self._brush_size_px)

        @property
        def brush_radius_normalized(self) -> float:
            """Compatibility view of the current screen brush in image space."""
            return self.screen_radius_to_normalized(self._brush_size_px / 2.0)

        @brush_radius_normalized.setter
        def brush_radius_normalized(self, value: float):
            # Older callers supplied a normalized radius.  Keep that API while
            # routing the live control through the screen-pixel model.
            radius = max(float(value), 1e-6) * max(min(self.image_width, self.image_height), 1) * self.view_scale
            self.set_brush_size_px(round(radius * 2.0))

        @property
        def current_stroke(self) -> list[list[float]]:
            return [list(point) for point in self._current_stroke]

        @property
        def last_stroke_radius_normalized(self) -> float | None:
            return self._last_stroke_radius_normalized

        def set_brush_size_px(self, value: int | float, *, emit: bool = True):
            resolved = int(np.clip(round(float(value)), self.MIN_BRUSH_SIZE_PX, self.MAX_BRUSH_SIZE_PX))
            changed = resolved != self._brush_size_px
            self._brush_size_px = resolved
            self._refresh_cursor()
            if emit and changed:
                self.brush_size_changed.emit(resolved)
            return resolved

        def set_brush_radius(self, value: float):
            """Compatibility setter accepting old normalized or new pixel input."""
            numeric = float(value)
            if 0.0 < numeric <= 1.0:
                self.brush_radius_normalized = numeric
            else:
                self.set_brush_size_px(numeric)

        @staticmethod
        def brush_size_step(size_px: int | float) -> int:
            size = float(size_px)
            if size < 20.0:
                return 1
            if size <= 100.0:
                return 5
            return 10

        def adjust_brush_size(self, direction: int):
            sign = 1 if int(direction) >= 0 else -1
            return self.set_brush_size_px(self._brush_size_px + sign * self.brush_size_step(self._brush_size_px))

        def screen_radius_to_normalized(self, screen_radius_px: float, *, view_scale: float | None = None) -> float:
            return screen_radius_to_normalized(
                screen_radius_px,
                self.zoom if view_scale is None else view_scale,
                (self.image_height, self.image_width),
            )

        def set_source_data(self, source_data, *, fit=True):
            if source_data is None:
                return
            self.image_height, self.image_width = map(int, source_data.rgba8.shape[:2])
            self.scene.setSceneRect(0.0, 0.0, float(self.image_width), float(self.image_height))
            self._set_layer("source", source_data.rgba8, opacity=1.0, z=1)
            if fit:
                self.fit_to_window()
            else:
                self._sync_zoom()
            self._refresh_cursor()

        def set_source_array(self, array, *, fit=True):
            values = np.asarray(array)
            self.image_height, self.image_width = map(int, values.shape[:2])
            self.scene.setSceneRect(0.0, 0.0, float(self.image_width), float(self.image_height))
            self._set_layer("source", values, opacity=1.0, z=1)
            if fit:
                self.fit_to_window()
            else:
                self._sync_zoom()
            self._refresh_cursor()

        def set_solid_mask(self, mask):
            if mask is None:
                self._clear_layer("solid")
            else:
                self._set_layer("solid", _overlay(mask, (245, 76, 76)), opacity=self.overlay_opacity, z=2)

        def set_height_master(self, height):
            if height is None:
                self._clear_layer("height")
            else:
                values = np.asarray(height, dtype=np.float32)
                rgba = np.zeros((*values.shape, 4), dtype=np.uint8)
                rgba[..., :3] = np.asarray([64, 176, 255], dtype=np.uint8)
                rgba[..., 3] = np.round(np.clip(values, 0.0, 1.0) * 190.0).astype(np.uint8)
                self._set_layer("height", rgba, opacity=self.overlay_opacity, z=3)

        def set_mesh_preview(self, preview):
            if preview is None:
                self._clear_layer("mesh")
            else:
                self._set_layer("mesh", preview, opacity=1.0, z=4)

        def set_layer_visibility(self, name: str, visible: bool):
            item = self._items.get(str(name))
            if item is not None:
                item.setVisible(bool(visible))

        def set_overlay_opacity(self, value: float):
            self.overlay_opacity = float(np.clip(float(value), 0.0, 1.0))
            for name in ("solid", "height"):
                item = self._items.get(name)
                if item is not None:
                    item.setOpacity(self.overlay_opacity)

        def set_tool(self, tool):
            self.cancel_interaction()
            self.active_tool = str(getattr(tool, "value", tool))
            self._refresh_cursor()

        # ------------------------------------------------------------- layers
        def _set_layer(self, name: str, array, *, opacity: float, z: float):
            item = self._items.get(name)
            if item is None:
                item = QGraphicsPixmapItem()
                item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
                self.scene.addItem(item)
                self._items[name] = item
            item.setPixmap(_pixmap_from_array(array))
            item.setPos(0.0, 0.0)
            item.setOpacity(float(opacity))
            item.setZValue(float(z))
            item.setVisible(True)

        def _clear_layer(self, name: str):
            item = self._items.get(name)
            if item is not None:
                item.setVisible(False)

        # --------------------------------------------------------- coordinates
        def viewport_to_image(self, point) -> tuple[float, float] | None:
            if isinstance(point, (QPoint, QPointF)):
                viewport_point = QPointF(float(point.x()), float(point.y()))
            else:
                try:
                    viewport_point = QPointF(float(point[0]), float(point[1]))
                except (TypeError, ValueError, IndexError):
                    return None
            if (
                viewport_point.x() < 0.0
                or viewport_point.y() < 0.0
                or viewport_point.x() >= self.viewport().width()
                or viewport_point.y() >= self.viewport().height()
            ):
                return None
            inverse, invertible = self.viewportTransform().inverted()
            if not invertible:
                return None
            scene_point = inverse.map(viewport_point)
            x, y = float(scene_point.x()), float(scene_point.y())
            if x < 0.0 or y < 0.0 or x > self.image_width - 1 or y > self.image_height - 1:
                return None
            return x, y

        def image_to_viewport(self, point):
            try:
                return self.viewportTransform().map(QPointF(float(point[0]), float(point[1])))
            except (TypeError, ValueError, IndexError):
                return None

        def image_to_normalized(self, point) -> tuple[float, float] | None:
            if point is None:
                return None
            try:
                x, y = float(point[0]), float(point[1])
            except (TypeError, ValueError, IndexError):
                return None
            if x < 0.0 or y < 0.0 or x > self.image_width - 1 or y > self.image_height - 1:
                return None
            return x / max(self.image_width - 1, 1), y / max(self.image_height - 1, 1)

        def normalized_to_image(self, point) -> tuple[float, float] | None:
            try:
                x, y = float(point[0]), float(point[1])
            except (TypeError, ValueError, IndexError):
                return None
            if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
                return None
            return x * max(self.image_width - 1, 1), y * max(self.image_height - 1, 1)

        def image_to_scene(self, point):
            return QPointF(float(point[0]), float(point[1]))

        def normalized_to_viewport(self, point):
            image = self.normalized_to_image(point)
            return self.image_to_viewport(image) if image is not None else None

        # -------------------------------------------------------------- zoom
        def _transform_scale(self) -> float:
            transform = self.transform()
            # The editor only creates uniform scales.  m11 is the exact scale
            # and remains stable across fit/reset/relative zoom operations.
            return max(abs(float(transform.m11())), 1e-9)

        def _sync_zoom(self):
            self._zoom = self._transform_scale()
            self.zoom_changed.emit(float(self._zoom * 100.0))

        def _restore_viewport_anchor(self, scene_point, viewport_point):
            mapped = self.mapFromScene(scene_point)
            delta_x = float(mapped.x() - viewport_point.x())
            delta_y = float(mapped.y() - viewport_point.y())
            if abs(delta_x) > 0.01:
                bar = self.horizontalScrollBar()
                bar.setValue(bar.value() + round(delta_x))
            if abs(delta_y) > 0.01:
                bar = self.verticalScrollBar()
                bar.setValue(bar.value() + round(delta_y))

        def _set_absolute_zoom(self, target: float, anchor=None):
            target = float(np.clip(float(target), self.MIN_ZOOM, self.MAX_ZOOM))
            if self.scene.sceneRect().isEmpty():
                return
            if anchor is None:
                center_viewport = self.viewport().rect().center()
                center_scene = self.mapToScene(center_viewport)
            else:
                anchor = anchor if isinstance(anchor, QPoint) else QPoint(round(anchor.x()), round(anchor.y()))
                center_scene = self.mapToScene(anchor)
            self.resetTransform()
            self.scale(target, target)
            if anchor is None:
                self.centerOn(center_scene)
            else:
                self._restore_viewport_anchor(center_scene, anchor)
            self._sync_zoom()
            self._refresh_cursor()

        def fit_to_window(self):
            if self.scene.sceneRect().isEmpty():
                return
            self.cancel_interaction()
            if not self.isVisible() or self.viewport().width() < 32 or self.viewport().height() < 32:
                self._fit_pending = True
                return
            self._fit_pending = False
            self.fitInView(self.scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
            self._sync_zoom()
            self._refresh_cursor()

        def zoom_to_100(self):
            self._set_absolute_zoom(1.0)

        def set_zoom(self, target: float):
            self._set_absolute_zoom(target)

        def _apply_zoom(self, factor, anchor=None):
            self._set_absolute_zoom(self.zoom * float(factor), anchor=anchor)

        # ------------------------------------------------------------ display
        def set_mode_visibility(self, mode: str):
            mode = str(mode).lower()
            self.set_layer_visibility("source", mode != "mesh")
            self.set_layer_visibility("solid", mode in {"solid", "height", "mesh"})
            self.set_layer_visibility("height", mode in {"height", "mesh"})
            self.set_layer_visibility("mesh", mode == "mesh")
            self._refresh_cursor()

        def set_selection(self, normalized_rect=None):
            if normalized_rect is None:
                self.selection_item.setVisible(False)
                return None
            try:
                x0, y0, x1, y1 = (float(value) for value in normalized_rect)
            except (TypeError, ValueError):
                self.selection_item.setVisible(False)
                return None
            first = self.normalized_to_image((x0, y0))
            second = self.normalized_to_image((x1, y1))
            if first is None or second is None:
                self.selection_item.setVisible(False)
                return None
            self.selection_item.setRect(
                QRectF(
                    min(first[0], second[0]),
                    min(first[1], second[1]),
                    abs(second[0] - first[0]),
                    abs(second[1] - first[1]),
                )
            )
            self.selection_item.setVisible(True)
            return normalized_rect

        def _cursor_color(self):
            if self.active_tool == "brush_erase":
                return QColor("#ff8c8c")
            if self.active_tool.startswith("height_"):
                return QColor("#72c7ff")
            return QColor("#ffe08a")

        def _brush_tool_active(self) -> bool:
            return self.active_tool not in {"pan", "background_sample"}

        def _refresh_cursor(self, viewport_point=None):
            if viewport_point is None:
                viewport_point = self._last_viewport
            if self._panning or not self._brush_tool_active() or viewport_point is None:
                self._cursor_item.setVisible(False)
                return
            image = self.viewport_to_image(viewport_point)
            if image is None:
                self._cursor_item.setVisible(False)
                return
            radius_scene = max(float(self._brush_size_px) / (2.0 * self.zoom), 0.25)
            self._cursor_item.setRect(
                image[0] - radius_scene,
                image[1] - radius_scene,
                radius_scene * 2.0,
                radius_scene * 2.0,
            )
            pen = QPen(self._cursor_color(), max(0.75, 1.5 / self.zoom))
            self._cursor_item.setPen(pen)
            self._cursor_item.setVisible(True)

        def _stroke_pen(self):
            if self.active_tool == "brush_erase":
                color = QColor("#ff6b6b")
            elif self.active_tool.startswith("height_"):
                color = QColor("#64c8ff")
            else:
                color = QColor("#ffe08a")
            pen = QPen(color, max(0.5, (self._stroke_radius_normalized or self.brush_radius_normalized) * min(self.image_width, self.image_height) * 2.0))
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            return pen

        def _update_stroke_preview(self):
            if self._stroke_item is not None:
                self.scene.removeItem(self._stroke_item)
                self._stroke_item = None
            if not self._current_stroke:
                return
            radius = max(float(self._stroke_radius_normalized or self.brush_radius_normalized) * min(self.image_width, self.image_height), 0.25)
            if len(self._current_stroke) == 1:
                image = self.normalized_to_image(self._current_stroke[0])
                self._stroke_item = QGraphicsEllipseItem(image[0] - radius, image[1] - radius, radius * 2.0, radius * 2.0)
                self._stroke_item.setPen(self._stroke_pen())
                self._stroke_item.setBrush(Qt.BrushStyle.NoBrush)
            else:
                path = QPainterPath()
                first = self.normalized_to_image(self._current_stroke[0])
                path.moveTo(QPointF(*first))
                for point in self._current_stroke[1:]:
                    image = self.normalized_to_image(point)
                    path.lineTo(QPointF(*image))
                self._stroke_item = QGraphicsPathItem(path)
                self._stroke_item.setPen(self._stroke_pen())
            self._stroke_item.setZValue(15)
            self._stroke_item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
            self.scene.addItem(self._stroke_item)

        # -------------------------------------------------------------- pan API
        def _begin_pan(self, viewport_position):
            if isinstance(viewport_position, QPointF):
                viewport_position = viewport_position.toPoint()
            elif not isinstance(viewport_position, QPoint):
                viewport_position = QPoint(round(viewport_position[0]), round(viewport_position[1]))
            self._cancel_paint()
            self._panning = True
            self._last_viewport = QPoint(viewport_position)
            self._cursor_item.setVisible(False)
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            self.pan_state_changed.emit(True)

        def _update_pan(self, viewport_position):
            if not self._panning:
                return
            if isinstance(viewport_position, QPointF):
                current = viewport_position.toPoint()
            elif isinstance(viewport_position, QPoint):
                current = viewport_position
            else:
                current = QPoint(round(viewport_position[0]), round(viewport_position[1]))
            previous = self._last_viewport or current
            previous_scene = self.mapToScene(previous)
            current_scene = self.mapToScene(current)
            scene_delta = previous_scene - current_scene
            center = self.mapToScene(self.viewport().rect().center())
            self.centerOn(center + scene_delta)
            self._last_viewport = QPoint(current)

        def _end_pan(self):
            if not self._panning:
                return
            self._panning = False
            self._last_viewport = None
            self.unsetCursor()
            self.pan_state_changed.emit(False)
            self._refresh_cursor()

        def _cancel_paint(self):
            if not self._painting and not self._current_stroke:
                return
            self._painting = False
            self._current_stroke.clear()
            self._stroke_radius_normalized = None
            if self._stroke_item is not None:
                self.scene.removeItem(self._stroke_item)
                self._stroke_item = None
            self._refresh_cursor()

        def cancel_interaction(self):
            self._end_pan()
            self._cancel_paint()

        # -------------------------------------------------------------- events
        def wheelEvent(self, event):
            delta = event.angleDelta().y() or event.pixelDelta().y()
            if not delta:
                event.ignore()
                return
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                self.adjust_brush_size(1 if delta > 0 else -1)
                event.accept()
                return
            factor = 1.15 if delta > 0 else 1.0 / 1.15
            self._apply_zoom(factor, anchor=event.position().toPoint())
            event.accept()

        def keyPressEvent(self, event):
            if event.key() == Qt.Key.Key_Escape:
                self._space_pressed = False
                self.cancel_interaction()
                event.accept()
                return
            if event.key() == Qt.Key.Key_Space:
                self._space_pressed = True
                event.accept()
                return
            if event.key() == Qt.Key.Key_BracketLeft:
                self.adjust_brush_size(-1)
                event.accept()
                return
            if event.key() == Qt.Key.Key_BracketRight:
                self.adjust_brush_size(1)
                event.accept()
                return
            if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                if event.key() == Qt.Key.Key_0:
                    self.fit_to_window()
                    event.accept()
                    return
                if event.key() == Qt.Key.Key_1:
                    self.zoom_to_100()
                    event.accept()
                    return
            super().keyPressEvent(event)

        def keyReleaseEvent(self, event):
            if event.key() == Qt.Key.Key_Space:
                self._space_pressed = False
                if self._panning:
                    self._end_pan()
                event.accept()
                return
            super().keyReleaseEvent(event)

        def mousePressEvent(self, event):
            self.setFocus()
            point = event.position().toPoint()
            self._last_viewport = QPoint(point)
            if event.button() == Qt.MouseButton.MiddleButton or self.active_tool == "pan" or (
                event.button() == Qt.MouseButton.LeftButton and self._space_pressed
            ):
                self._begin_pan(point)
                event.accept()
                return
            if event.button() != Qt.MouseButton.LeftButton:
                super().mousePressEvent(event)
                return
            normalized = self.image_to_normalized(self.viewport_to_image(point))
            if normalized is None:
                self._refresh_cursor(point)
                event.accept()
                return
            self._painting = True
            self._stroke_radius_normalized = self.screen_radius_to_normalized(self._brush_size_px / 2.0)
            self._last_stroke_radius_normalized = self._stroke_radius_normalized
            self._current_stroke = [list(normalized)]
            self.stroke_started.emit(self.current_stroke)
            self.stroke_points_changed.emit(self.current_stroke)
            self._update_stroke_preview()
            event.accept()

        def mouseMoveEvent(self, event):
            current = event.position().toPoint()
            if self._panning:
                self._update_pan(current)
                event.accept()
                return
            self._last_viewport = QPoint(current)
            if self._painting:
                normalized = self.image_to_normalized(self.viewport_to_image(current))
                if normalized is not None and self._current_stroke:
                    spacing = max(float(self._stroke_radius_normalized or self.brush_radius_normalized) * 0.25, 1e-8)
                    additions = interpolate_points([self._current_stroke[-1], normalized], spacing)
                    self._current_stroke.extend(additions[1:])
                    self.stroke_points_changed.emit(self.current_stroke)
                    self._update_stroke_preview()
                event.accept()
                return
            self._refresh_cursor(current)
            super().mouseMoveEvent(event)

        def mouseReleaseEvent(self, event):
            if self._panning:
                self._end_pan()
                event.accept()
                return
            if self._painting and event.button() == Qt.MouseButton.LeftButton:
                current = event.position().toPoint()
                normalized = self.image_to_normalized(self.viewport_to_image(current))
                if normalized is not None and self._current_stroke:
                    spacing = max(float(self._stroke_radius_normalized or self.brush_radius_normalized) * 0.25, 1e-8)
                    additions = interpolate_points([self._current_stroke[-1], normalized], spacing)
                    self._current_stroke.extend(additions[1:])
                stroke = self.current_stroke
                self._painting = False
                self._current_stroke.clear()
                self._stroke_radius_normalized = None
                if self._stroke_item is not None:
                    self.scene.removeItem(self._stroke_item)
                    self._stroke_item = None
                self.stroke_finished.emit(stroke)
                self._last_viewport = QPoint(current)
                self._refresh_cursor(current)
                event.accept()
                return
            super().mouseReleaseEvent(event)

        def leaveEvent(self, event):
            if not self._panning:
                self._cursor_item.setVisible(False)
            super().leaveEvent(event)

        def enterEvent(self, event):
            if QCursor is not None:
                point = self.mapFromGlobal(QCursor.pos())
                self._last_viewport = point
                self._refresh_cursor(point)
            super().enterEvent(event)

        def showEvent(self, event):
            super().showEvent(event)
            if self._fit_pending:
                QTimer.singleShot(0, self.fit_to_window)

        def focusOutEvent(self, event):
            self._space_pressed = False
            self.cancel_interaction()
            super().focusOutEvent(event)

        def resizeEvent(self, event):
            super().resizeEvent(event)
            if self._fit_pending and self.isVisible() and self.viewport().width() >= 32 and self.viewport().height() >= 32:
                QTimer.singleShot(0, self.fit_to_window)
            self._refresh_cursor()

else:  # pragma: no cover

    class CanvasEditor:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("PySide6 is required for CanvasEditor")


__all__ = ["CanvasEditor"]
