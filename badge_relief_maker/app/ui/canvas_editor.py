"""Qt canvas for normalized, direct image editing."""

from __future__ import annotations

import math

import numpy as np

try:
    from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, Signal
    from PySide6.QtGui import QColor, QImage, QPainterPath, QPen, QPixmap
    from PySide6.QtWidgets import QFrame, QGraphicsEllipseItem, QGraphicsPathItem, QGraphicsPixmapItem, QGraphicsRectItem, QGraphicsScene, QGraphicsView
except Exception:  # pragma: no cover - core-only installations
    QPoint = QPointF = QRectF = Qt = Signal = None
    QFrame = QColor = QImage = QPainterPath = QPen = QPixmap = None
    QGraphicsPathItem = QGraphicsRectItem = None
    QGraphicsEllipseItem = QGraphicsPixmapItem = QGraphicsScene = QGraphicsView = object

from ..core.canvas_edits import interpolate_points


def _pixmap_from_array(array: np.ndarray) -> QPixmap:
    values = np.asarray(array)
    if values.dtype.kind == "f":
        values = np.round(np.clip(values, 0.0, 1.0) * 255.0).astype(np.uint8)
    else:
        values = np.asarray(np.clip(values, 0, 255), dtype=np.uint8)
    if values.ndim == 2:
        image = QImage(values.data, values.shape[1], values.shape[0], values.strides[0], QImage.Format.Format_Grayscale8).copy()
    elif values.ndim == 3 and values.shape[2] == 4:
        pixels = np.ascontiguousarray(values)
        image = QImage(pixels.data, pixels.shape[1], pixels.shape[0], pixels.strides[0], QImage.Format.Format_RGBA8888).copy()
    elif values.ndim == 3 and values.shape[2] == 3:
        pixels = np.ascontiguousarray(values)
        image = QImage(pixels.data, pixels.shape[1], pixels.shape[0], pixels.strides[0], QImage.Format.Format_RGB888).copy()
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
        """Single large image canvas with zoom, pan, layers and stroke signals."""

        stroke_started = Signal(object)
        stroke_points_changed = Signal(object)
        stroke_finished = Signal(object)
        normalized_clicked = Signal(object)

        def __init__(self, parent=None):
            self.scene = QGraphicsScene(parent)
            super().__init__(self.scene, parent)
            self.setObjectName("canvasEditor")
            self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            self.setMouseTracking(True)
            self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
            self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
            self.setBackgroundBrush(QColor("#171b22"))
            self.setFrameShape(QFrame.Shape.NoFrame)
            self.image_width = 1
            self.image_height = 1
            self._zoom = 1.0
            self._space_pressed = False
            self._panning = False
            self._painting = False
            self._last_viewport = None
            self._current_stroke: list[list[float]] = []
            self.brush_radius_normalized = 0.025
            self.active_tool = "brush_add"
            self.overlay_opacity = 0.5
            self._items: dict[str, QGraphicsPixmapItem] = {}
            self.layer_order = ("background", "source", "solid", "height", "outline", "selection", "stroke", "cursor")
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
            self._cursor_item.setPen(QPen(QColor("#ffe08a"), 1.5))
            self._cursor_item.setBrush(Qt.BrushStyle.NoBrush)
            self._cursor_item.setZValue(20)
            self.scene.addItem(self._cursor_item)
            self._cursor_item.setVisible(False)
            self.brush_cursor = self._cursor_item
            self._stroke_item = None

        @property
        def zoom(self) -> float:
            return float(self._zoom)

        @property
        def current_stroke(self) -> list[list[float]]:
            return [list(point) for point in self._current_stroke]

        def set_source_data(self, source_data, *, fit=True):
            if source_data is None:
                return
            self.image_height, self.image_width = map(int, source_data.rgba8.shape[:2])
            self.scene.setSceneRect(0.0, 0.0, float(self.image_width), float(self.image_height))
            self._set_layer("source", source_data.rgba8, opacity=1.0, z=1)
            if fit:
                self.fit_to_window()

        def set_source_array(self, array, *, fit=True):
            values = np.asarray(array)
            self.image_height, self.image_width = map(int, values.shape[:2])
            self.scene.setSceneRect(0.0, 0.0, float(self.image_width), float(self.image_height))
            self._set_layer("source", values, opacity=1.0, z=1)
            if fit:
                self.fit_to_window()

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

        def set_brush_radius(self, value: float):
            self.brush_radius_normalized = float(np.clip(float(value), 1e-5, 1.0))
            self._refresh_cursor()

        def set_tool(self, tool):
            self.active_tool = str(getattr(tool, "value", tool))

        def _set_layer(self, name: str, array, *, opacity: float, z: float):
            item = self._items.get(name)
            if item is None:
                item = QGraphicsPixmapItem()
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

        def fit_to_window(self):
            if self.scene.sceneRect().isEmpty():
                return
            self.fitInView(self.scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
            self._zoom = 1.0

        def zoom_to_100(self):
            self.resetTransform()
            self._zoom = 1.0
            self.centerOn(self.scene.sceneRect().center())

        def _apply_zoom(self, factor):
            target = float(np.clip(self._zoom * factor, 0.05, 32.0))
            factor = target / max(self._zoom, 1e-9)
            self.scale(factor, factor)
            self._zoom = target
            self._refresh_cursor()

        # ------------------------------------------------------------ display
        def set_mode_visibility(self, mode: str):
            mode = str(mode).lower()
            self.set_layer_visibility("source", mode != "mesh")
            self.set_layer_visibility("solid", mode in {"solid", "height", "mesh"})
            self.set_layer_visibility("height", mode in {"height", "mesh"})
            self.set_layer_visibility("mesh", mode == "mesh")

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
            self.selection_item.setRect(QRectF(min(first[0], second[0]), min(first[1], second[1]), abs(second[0] - first[0]), abs(second[1] - first[1])))
            self.selection_item.setVisible(True)
            return normalized_rect

        def _refresh_cursor(self, viewport_point=None):
            if viewport_point is None:
                viewport_point = self._last_viewport
            image = self.viewport_to_image(viewport_point) if viewport_point is not None else None
            if image is None:
                self._cursor_item.setVisible(False)
                return
            radius = self.brush_radius_normalized * min(self.image_width, self.image_height)
            self._cursor_item.setRect(image[0] - radius, image[1] - radius, radius * 2.0, radius * 2.0)
            self._cursor_item.setVisible(True)

        def _update_stroke_preview(self):
            if self._stroke_item is not None:
                self.scene.removeItem(self._stroke_item)
                self._stroke_item = None
            if len(self._current_stroke) < 2:
                return
            path = QPainterPath()
            first = self.normalized_to_image(self._current_stroke[0])
            path.moveTo(QPointF(*first))
            for point in self._current_stroke[1:]:
                image = self.normalized_to_image(point)
                path.lineTo(QPointF(*image))
            # Keep the preview as a scene path without introducing a persisted
            # edit; the actual record is emitted only on mouse release.
            from PySide6.QtWidgets import QGraphicsPathItem

            self._stroke_item = QGraphicsPathItem(path)
            self._stroke_item.setPen(QPen(QColor("#ffe08a"), max(1.0, self.brush_radius_normalized * min(self.image_width, self.image_height) * 2.0)))
            self._stroke_item.setZValue(15)
            self.scene.addItem(self._stroke_item)

        # -------------------------------------------------------------- events
        def wheelEvent(self, event):
            factor = 1.15 if event.angleDelta().y() > 0 else 1.0 / 1.15
            self._apply_zoom(factor)
            event.accept()

        def keyPressEvent(self, event):
            if event.key() == Qt.Key.Key_Space:
                self._space_pressed = True
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
                event.accept()
                return
            super().keyReleaseEvent(event)

        def mousePressEvent(self, event):
            self.setFocus()
            self._last_viewport = event.position().toPoint()
            if event.button() == Qt.MouseButton.MiddleButton or self.active_tool == "pan" or (
                event.button() == Qt.MouseButton.LeftButton and self._space_pressed
            ):
                self._panning = True
                self._pan_anchor_x, self._pan_anchor_y = self._last_viewport.x(), self._last_viewport.y()
                self.setCursor(Qt.CursorShape.ClosedHandCursor)
                event.accept()
                return
            if event.button() != Qt.MouseButton.LeftButton:
                super().mousePressEvent(event)
                return
            normalized = self.image_to_normalized(self.viewport_to_image(self._last_viewport))
            if normalized is None:
                return
            self._painting = True
            self._current_stroke = [list(normalized)]
            self.stroke_started.emit(self.current_stroke)
            self.stroke_points_changed.emit(self.current_stroke)
            self._update_stroke_preview()
            event.accept()

        def mouseMoveEvent(self, event):
            current = event.position().toPoint()
            self._last_viewport = current
            self._refresh_cursor(current)
            if self._panning:
                previous = self._last_viewport if self._last_viewport is not None else current
                # Scroll using the event's screen position relative to the
                # previous event stored just before the update.
                dx = current.x() - getattr(self, "_pan_anchor_x", current.x())
                dy = current.y() - getattr(self, "_pan_anchor_y", current.y())
                self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - dx)
                self.verticalScrollBar().setValue(self.verticalScrollBar().value() - dy)
                self._pan_anchor_x, self._pan_anchor_y = current.x(), current.y()
                event.accept()
                return
            if self._painting:
                normalized = self.image_to_normalized(self.viewport_to_image(current))
                if normalized is not None and self._current_stroke:
                    spacing = self.brush_radius_normalized * 0.25
                    additions = interpolate_points([self._current_stroke[-1], normalized], spacing)
                    self._current_stroke.extend(additions[1:])
                    self.stroke_points_changed.emit(self.current_stroke)
                    self._update_stroke_preview()
                    event.accept()
                    return
            super().mouseMoveEvent(event)

        def mouseReleaseEvent(self, event):
            if self._panning and event.button() in {Qt.MouseButton.LeftButton, Qt.MouseButton.MiddleButton}:
                self._panning = False
                self.unsetCursor()
                event.accept()
                return
            if self._painting and event.button() == Qt.MouseButton.LeftButton:
                stroke = self.current_stroke
                self._painting = False
                self._current_stroke.clear()
                if self._stroke_item is not None:
                    self.scene.removeItem(self._stroke_item)
                    self._stroke_item = None
                self.stroke_finished.emit(stroke)
                event.accept()
                return
            super().mouseReleaseEvent(event)

        def mouseMoveEventPanStart(self):
            self._pan_anchor_x = self._last_viewport.x() if self._last_viewport else 0
            self._pan_anchor_y = self._last_viewport.y() if self._last_viewport else 0

else:  # pragma: no cover

    class CanvasEditor:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("PySide6 is required for CanvasEditor")


__all__ = ["CanvasEditor"]
