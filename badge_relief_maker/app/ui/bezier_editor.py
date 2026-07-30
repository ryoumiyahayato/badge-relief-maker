"""Interactive draggable cubic Bezier contour editor."""

from copy import deepcopy

try:
    from PySide6.QtCore import QPointF, Qt, Signal
    from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QPixmap
    from PySide6.QtWidgets import QWidget
except Exception:
    QPointF = None
    Qt = None
    Signal = None
    QColor = None
    QPainter = None
    QPainterPath = None
    QPen = None
    QPixmap = None
    QWidget = object

from ..core.bezier_contours import default_bezier_ellipse, normalize_bezier_contour


if Signal is not None:

    class BezierContourEditor(QWidget):
        """Edit anchors and in/out handles in normalized source coordinates."""

        contours_changed = Signal(object)

        def __init__(self, parent=None):
            super().__init__(parent)
            self._contours = []
            self._background = QPixmap()
            self._selected = None
            self._dragging = False
            self.setMinimumSize(420, 260)
            self.setMouseTracking(True)

        def set_background(self, path):
            self._background = QPixmap(str(path)) if path else QPixmap()
            self.update()

        def set_contours(self, contours):
            self._contours = [
                normalized
                for normalized in (normalize_bezier_contour(item) for item in contours or ())
                if normalized is not None
            ]
            self._selected = None
            self.update()

        def contours(self):
            return deepcopy(self._contours)

        def new_contour(self, operation="add"):
            contour = default_bezier_ellipse(operation)
            if contour is None:
                return
            self._contours.append(contour)
            self._selected = (len(self._contours) - 1, 0, "anchor")
            self._emit_change()

        def set_selected_operation(self, operation):
            if not self._contours:
                return
            contour_index = self._selected[0] if self._selected is not None else len(self._contours) - 1
            self._contours[contour_index]["operation"] = str(operation)
            self._emit_change()

        def remove_selected_anchor(self):
            if self._selected is None:
                return
            contour_index, point_index, _ = self._selected
            points = self._contours[contour_index]["points"]
            if len(points) <= 3:
                self._contours.pop(contour_index)
                self._selected = None
            else:
                points.pop(point_index)
                self._selected = (contour_index, min(point_index, len(points) - 1), "anchor")
            self._emit_change()

        def clear_contours(self):
            self._contours = []
            self._selected = None
            self._emit_change()

        def _to_widget(self, point):
            return QPointF(float(point[0]) * self.width(), float(point[1]) * self.height())

        def _from_widget(self, point):
            return [
                min(max(float(point.x()) / max(self.width(), 1), 0.0), 1.0),
                min(max(float(point.y()) / max(self.height(), 1), 0.0), 1.0),
            ]

        def _nearest_control(self, position, limit=14.0):
            best = None
            best_distance = float(limit) ** 2
            for contour_index, contour in enumerate(self._contours):
                for point_index, point in enumerate(contour["points"]):
                    for kind in ("anchor", "in", "out"):
                        widget_point = self._to_widget(point[kind])
                        distance = (widget_point.x() - position.x()) ** 2 + (widget_point.y() - position.y()) ** 2
                        if distance <= best_distance:
                            best_distance = distance
                            best = (contour_index, point_index, kind)
            return best

        def mousePressEvent(self, event):
            if event.button() == Qt.MouseButton.LeftButton:
                self._selected = self._nearest_control(event.position())
                self._dragging = self._selected is not None
                self.update()
                event.accept()
                return
            super().mousePressEvent(event)

        def mouseMoveEvent(self, event):
            if not self._dragging or self._selected is None:
                return super().mouseMoveEvent(event)
            contour_index, point_index, kind = self._selected
            point = self._contours[contour_index]["points"][point_index]
            new_value = self._from_widget(event.position())
            if kind == "anchor":
                delta = [new_value[0] - point["anchor"][0], new_value[1] - point["anchor"][1]]
                point["anchor"] = new_value
                for handle in ("in", "out"):
                    point[handle] = [
                        min(max(point[handle][0] + delta[0], 0.0), 1.0),
                        min(max(point[handle][1] + delta[1], 0.0), 1.0),
                    ]
            else:
                point[kind] = new_value
            self.update()
            event.accept()

        def mouseReleaseEvent(self, event):
            if self._dragging and event.button() == Qt.MouseButton.LeftButton:
                self._dragging = False
                self._emit_change()
                event.accept()
                return
            super().mouseReleaseEvent(event)

        def mouseDoubleClickEvent(self, event):
            if event.button() != Qt.MouseButton.LeftButton:
                return super().mouseDoubleClickEvent(event)
            if not self._contours:
                self.new_contour("replace")
            contour_index = self._selected[0] if self._selected is not None else len(self._contours) - 1
            value = self._from_widget(event.position())
            points = self._contours[contour_index]["points"]
            insert_at = (self._selected[1] + 1) if self._selected is not None else len(points)
            points.insert(insert_at, {"anchor": value, "in": value[:], "out": value[:]})
            self._selected = (contour_index, insert_at, "anchor")
            self._emit_change()

        def _emit_change(self):
            self.update()
            self.contours_changed.emit(self.contours())

        def paintEvent(self, event):
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.fillRect(self.rect(), QColor(25, 29, 35))
            if not self._background.isNull():
                painter.drawPixmap(self.rect(), self._background)
            for contour_index, contour in enumerate(self._contours):
                points = contour["points"]
                if len(points) < 2:
                    continue
                path = QPainterPath(self._to_widget(points[0]["anchor"]))
                segment_count = len(points) if contour.get("closed", True) else len(points) - 1
                for index in range(segment_count):
                    current = points[index]
                    following = points[(index + 1) % len(points)]
                    path.cubicTo(
                        self._to_widget(current["out"]),
                        self._to_widget(following["in"]),
                        self._to_widget(following["anchor"]),
                    )
                colour = QColor(70, 210, 255) if contour["operation"] != "remove" else QColor(255, 95, 90)
                painter.setPen(QPen(colour, 2.5))
                painter.drawPath(path)
                for point_index, point in enumerate(points):
                    anchor = self._to_widget(point["anchor"])
                    handle_in = self._to_widget(point["in"])
                    handle_out = self._to_widget(point["out"])
                    painter.setPen(QPen(QColor(210, 215, 225), 1.0))
                    painter.drawLine(anchor, handle_in)
                    painter.drawLine(anchor, handle_out)
                    for kind, control, fill in (
                        ("in", handle_in, QColor(255, 196, 70)),
                        ("out", handle_out, QColor(255, 196, 70)),
                        ("anchor", anchor, colour),
                    ):
                        selected = self._selected == (contour_index, point_index, kind)
                        radius = 6 if selected else 4
                        painter.setBrush(QColor(255, 255, 255) if selected else fill)
                        painter.setPen(QPen(QColor(15, 18, 22), 1.0))
                        painter.drawEllipse(control, radius, radius)
            painter.end()

else:

    class BezierContourEditor:
        """Import-safe fallback when PySide6 is unavailable."""

        def __init__(self, *_, **__):
            self._contours = []

        def set_contours(self, contours):
            self._contours = deepcopy(list(contours or ()))

        def contours(self):
            return deepcopy(self._contours)
