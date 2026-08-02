"""Top bar, compact tool rail and mode-specific property panels."""

from __future__ import annotations

try:
    from PySide6.QtCore import Qt, Signal
    from PySide6.QtWidgets import (
        QCheckBox,
        QComboBox,
        QDoubleSpinBox,
        QFormLayout,
        QGroupBox,
        QHBoxLayout,
        QLabel,
        QPushButton,
        QScrollArea,
        QSlider,
        QStackedWidget,
        QToolButton,
        QVBoxLayout,
        QWidget,
    )
except Exception:  # pragma: no cover
    Qt = Signal = None
    QCheckBox = QComboBox = QDoubleSpinBox = QFormLayout = QGroupBox = QHBoxLayout = QLabel = object
    QPushButton = QScrollArea = QSlider = QStackedWidget = QToolButton = QVBoxLayout = QWidget = object

from .editor_session import CanvasTool, EditorMode


if Signal is not None:

    class EditorControls(QWidget):
        """All non-canvas controls for the direct editor."""

        mode_requested = Signal(str)
        tool_requested = Signal(str)
        action_requested = Signal(str)
        overlay_opacity_changed = Signal(float)
        layer_visibility_requested = Signal(str, bool)

        def __init__(self, parent=None):
            super().__init__(parent)
            self.setObjectName("editorControls")
            self.tool_buttons: dict[str, QToolButton] = {}
            self._build()

        def _build(self):
            root = QVBoxLayout(self)
            root.setContentsMargins(0, 0, 0, 0)
            root.setSpacing(0)

            self.top_bar = QWidget()
            top = QHBoxLayout(self.top_bar)
            top.setContentsMargins(8, 6, 8, 6)
            top.setSpacing(5)
            self.open_image_button = self._button("打开图片", "open_image")
            self.open_project_button = self._button("打开项目", "open_project")
            self.save_project_button = self._button("保存项目", "save_project")
            self.undo_button = self._button("撤销", "undo")
            self.redo_button = self._button("重做", "redo")
            for button in (
                self.open_image_button,
                self.open_project_button,
                self.save_project_button,
                self.undo_button,
                self.redo_button,
            ):
                top.addWidget(button)
            top.addSpacing(10)
            self.solid_mode_button = self._mode_button("实体编辑", EditorMode.SOLID)
            self.height_mode_button = self._mode_button("高度编辑", EditorMode.HEIGHT)
            self.mesh_mode_button = self._mode_button("网格预览", EditorMode.MESH)
            for button in (self.solid_mode_button, self.height_mode_button, self.mesh_mode_button):
                top.addWidget(button)
            top.addSpacing(10)
            self.confirm_solid_button = self._button("确认并锁定实体蒙版", "approve")
            self.confirm_height_button = self._button("确认并锁定高度主图", "approve")
            self.approve_button = self.confirm_solid_button
            self.build_button = self._button("构建并导出", "build")
            self.export_button = self.build_button
            top.addWidget(self.confirm_solid_button)
            top.addWidget(self.confirm_height_button)
            top.addWidget(self.build_button)
            self.overlay_opacity_slider = QSlider(Qt.Orientation.Horizontal)
            self.overlay_opacity_slider.setRange(0, 100)
            self.overlay_opacity_slider.setValue(50)
            self.overlay_opacity_slider.setFixedWidth(90)
            self.overlay_opacity_slider.setToolTip("叠加层透明度")
            self.overlay_opacity_slider.valueChanged.connect(lambda value: self.overlay_opacity_changed.emit(float(value) / 100.0))
            top.addWidget(QLabel("叠加"))
            top.addWidget(self.overlay_opacity_slider)
            self.source_layer_check = self._layer_check("原图", "source", True)
            self.solid_layer_check = self._layer_check("实体", "solid", True)
            self.height_layer_check = self._layer_check("高度", "height", True)
            for checkbox in (self.source_layer_check, self.solid_layer_check, self.height_layer_check):
                top.addWidget(checkbox)
            top.addStretch(1)
            self.solid_status_label = QLabel("实体：草稿")
            self.height_status_label = QLabel("高度：草稿")
            self.mode_status_label = QLabel("模式：实体")
            top.addWidget(self.solid_status_label)
            top.addWidget(self.height_status_label)
            top.addWidget(self.mode_status_label)
            root.addWidget(self.top_bar)

            body = QHBoxLayout()
            body.setContentsMargins(0, 0, 0, 0)
            body.setSpacing(6)
            self.tool_bar = QWidget()
            tools = QVBoxLayout(self.tool_bar)
            tools.setContentsMargins(5, 8, 5, 8)
            tools.setSpacing(3)
            tool_labels = {
                CanvasTool.PAN.value: "移动",
                CanvasTool.BACKGROUND_SAMPLE.value: "背景取样",
                CanvasTool.BRUSH_ADD.value: "增加",
                CanvasTool.BRUSH_ERASE.value: "擦除",
                CanvasTool.FILL.value: "填充",
                CanvasTool.RECTANGLE.value: "矩形",
                CanvasTool.POLYGON.value: "多边形",
                CanvasTool.HEIGHT_SET.value: "设置高度",
                CanvasTool.HEIGHT_RAISE.value: "抬高",
                CanvasTool.HEIGHT_LOWER.value: "压低",
                CanvasTool.HEIGHT_SMOOTH.value: "平滑",
            }
            for tool, label in tool_labels.items():
                button = QToolButton()
                button.setText(label)
                button.setToolTip(label)
                button.setCheckable(True)
                button.setAutoExclusive(True)
                button.clicked.connect(lambda checked=False, value=tool: self.tool_requested.emit(value))
                self.tool_buttons[tool] = button
                tools.addWidget(button)
            self.tool_buttons[CanvasTool.BRUSH_ADD.value].setChecked(True)
            tools.addStretch(1)
            body.addWidget(self.tool_bar, 0)

            self.property_scroll = QScrollArea()
            self.property_scroll.setObjectName("editorPropertyScroll")
            self.property_scroll.setWidgetResizable(True)
            self.property_scroll.setMinimumWidth(300)
            self.property_scroll.setMaximumWidth(390)
            self.property_stack = QStackedWidget()
            self._build_solid_page()
            self._build_height_page()
            self._build_mesh_page()
            self.property_scroll.setWidget(self.property_stack)
            body.addWidget(self.property_scroll, 0)
            root.addLayout(body, 1)

        def _layer_check(self, label: str, name: str, checked: bool):
            checkbox = QCheckBox(label)
            checkbox.setChecked(bool(checked))
            checkbox.toggled.connect(lambda value, layer=name: self.layer_visibility_requested.emit(layer, bool(value)))
            return checkbox

        def _button(self, label: str, action: str):
            button = QPushButton(label)
            button.setObjectName(f"{action}Button")
            button.clicked.connect(lambda: self.action_requested.emit(action))
            return button

        def _mode_button(self, label: str, mode: EditorMode):
            button = QPushButton(label)
            button.setCheckable(True)
            button.clicked.connect(lambda: self.mode_requested.emit(mode.value))
            return button

        @staticmethod
        def _spin(minimum, maximum, value, step, decimals, suffix=""):
            spin = QDoubleSpinBox()
            spin.setRange(float(minimum), float(maximum))
            spin.setValue(float(value))
            spin.setSingleStep(float(step))
            spin.setDecimals(int(decimals))
            if suffix:
                spin.setSuffix(suffix)
            return spin

        def _page(self, title: str):
            page = QWidget()
            layout = QVBoxLayout(page)
            layout.setContentsMargins(8, 8, 8, 8)
            layout.setSpacing(8)
            heading = QLabel(title)
            heading.setStyleSheet("font-size:17px; font-weight:700;")
            layout.addWidget(heading)
            form = QFormLayout()
            form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
            layout.addLayout(form)
            return page, layout, form

        def _build_solid_page(self):
            page, layout, form = self._page("实体蒙版")
            self.solid_mode_combo = QComboBox()
            self.solid_mode_combo.addItems(["整个底板", "自动去背景", "自定义实体范围"])
            self.solid_mode_combo.setCurrentText("自动去背景")
            self.explicit_background_combo = QComboBox()
            self.explicit_background_combo.addItems(["自动判断边缘背景", "亮背景", "暗背景"])
            self.background_tolerance_spin = self._spin(0.0, 1.0, 0.08, 0.01, 3)
            self.solid_radius_spin = self._spin(0.002, 0.5, 0.04, 0.005, 3)
            self.solid_amount_label = QLabel("沿画布拖动以编辑实体")
            form.addRow("实体生成模式", self.solid_mode_combo)
            form.addRow("背景模式", self.explicit_background_combo)
            form.addRow("背景容差", self.background_tolerance_spin)
            form.addRow("画笔大小", self.solid_radius_spin)
            form.addRow(self.solid_amount_label)
            self.refresh_solid_button = QPushButton("生成实体初稿")
            self.refresh_solid_button.clicked.connect(lambda: self.action_requested.emit("refresh_solid"))
            self.finish_polygon_button = QPushButton("完成多边形")
            self.finish_polygon_button.clicked.connect(lambda: self.action_requested.emit("finish_polygon"))
            layout.addWidget(self.refresh_solid_button)
            layout.addWidget(self.finish_polygon_button)
            self.solid_confirm_state = QLabel("实体：草稿")
            layout.addWidget(self.solid_confirm_state)
            layout.addStretch(1)
            self.property_stack.addWidget(page)

        def _build_height_page(self):
            page, layout, form = self._page("高度主图")
            self.height_mode_combo = QComboBox()
            self.height_mode_combo.addItems(["亮色凸起", "暗色凸起", "线条凹刻", "线条凸起", "固定高度"])
            self.low_percentile_spin = self._spin(0.0, 49.9, 2.0, 0.5, 1)
            self.high_percentile_spin = self._spin(50.1, 100.0, 98.0, 0.5, 1)
            self.black_point_spin = self._spin(0.0, 0.99, 0.0, 0.01, 2)
            self.white_point_spin = self._spin(0.01, 1.0, 1.0, 0.01, 2)
            self.midtone_spin = self._spin(0.1, 4.0, 1.0, 0.05, 2)
            self.invert_check = QCheckBox("反转")
            self.fixed_height_spin = self._spin(0.0, 1.0, 1.0, 0.05, 2)
            self.line_depth_spin = self._spin(0.0, 5.0, 0.2, 0.05, 2, " mm")
            self.line_threshold_spin = self._spin(0.0, 1.0, 0.35, 0.01, 2)
            self.line_softness_spin = self._spin(0.0, 8.0, 0.75, 0.25, 2, " px")
            self.height_radius_spin = self._spin(0.002, 0.5, 0.04, 0.005, 3)
            self.height_amount_spin = self._spin(0.0, 1.0, 0.10, 0.01, 2)
            for label, control in (
                ("高度解释", self.height_mode_combo),
                ("最低百分位", self.low_percentile_spin),
                ("最高百分位", self.high_percentile_spin),
                ("最低点", self.black_point_spin),
                ("最高点", self.white_point_spin),
                ("中间调", self.midtone_spin),
                ("方向", self.invert_check),
                ("固定高度", self.fixed_height_spin),
                ("线条深度", self.line_depth_spin),
                ("线条阈值", self.line_threshold_spin),
                ("画笔大小", self.height_radius_spin),
                ("画笔强度", self.height_amount_spin),
            ):
                form.addRow(label, control)
            self.refresh_height_button = QPushButton("生成高度初稿")
            self.refresh_height_button.clicked.connect(lambda: self.action_requested.emit("refresh_height"))
            self.reset_height_button = QPushButton("重置高度参数")
            self.reset_height_button.clicked.connect(lambda: self.action_requested.emit("reset_height"))
            layout.addWidget(self.refresh_height_button)
            layout.addWidget(self.reset_height_button)
            self.height_confirm_state = QLabel("高度：草稿")
            layout.addWidget(self.height_confirm_state)
            layout.addStretch(1)
            self.property_stack.addWidget(page)

        def _build_mesh_page(self):
            page, layout, form = self._page("规则网格")
            self.width_spin = self._spin(1.0, 2000.0, 80.0, 1.0, 2, " mm")
            self.height_spin = self._spin(1.0, 2000.0, 80.0, 1.0, 2, " mm")
            self.base_spin = self._spin(0.0, 100.0, 2.0, 0.1, 2, " mm")
            self.relief_spin = self._spin(0.0, 100.0, 3.0, 0.1, 2, " mm")
            self.minimum_thickness_spin = self._spin(0.0, 100.0, 0.8, 0.1, 2, " mm")
            self.min_feature_spin = self._spin(0.001, 100.0, 0.3, 0.05, 3, " mm")
            self.quality_combo = QComboBox()
            self.quality_combo.addItems(["草稿", "标准", "精细"])
            self.quality_combo.setCurrentText("标准")
            self.format_combo = QComboBox()
            self.format_combo.addItems(["OBJ", "STL", "GLB"])
            for label, control in (
                ("宽度", self.width_spin),
                ("高度", self.height_spin),
                ("基础厚度", self.base_spin),
                ("浮雕高度", self.relief_spin),
                ("最小厚度", self.minimum_thickness_spin),
                ("最小特征", self.min_feature_spin),
                ("质量档位", self.quality_combo),
                ("格式", self.format_combo),
            ):
                form.addRow(label, control)
            self.mesh_status_label = QLabel("批准高度后可构建")
            self.mesh_report_label = QLabel("")
            self.mesh_report_label.setWordWrap(True)
            layout.addWidget(self.mesh_status_label)
            layout.addWidget(self.mesh_report_label)
            layout.addStretch(1)
            self.property_stack.addWidget(page)

        def set_mode(self, mode: EditorMode | str):
            selected = EditorMode(mode)
            self.property_stack.setCurrentIndex({EditorMode.SOLID: 0, EditorMode.HEIGHT: 1, EditorMode.MESH: 2}[selected])
            self.mode_status_label.setText({EditorMode.SOLID: "模式：实体", EditorMode.HEIGHT: "模式：高度", EditorMode.MESH: "模式：网格"}[selected])
            for value, button in ((EditorMode.SOLID, self.solid_mode_button), (EditorMode.HEIGHT, self.height_mode_button), (EditorMode.MESH, self.mesh_mode_button)):
                button.setChecked(value == selected)

        def set_approval_state(self, solid: bool, height: bool):
            self.solid_status_label.setText("实体：已批准" if solid else "实体：草稿")
            self.height_status_label.setText("高度：已批准" if height else "高度：草稿")
            self.solid_confirm_state.setText("实体：已批准" if solid else "实体：草稿")
            self.height_confirm_state.setText("高度：已批准" if height else "高度：草稿")
            self.height_mode_button.setEnabled(bool(solid))
            self.mesh_mode_button.setEnabled(bool(solid and height))
            self.confirm_solid_button.setEnabled(not solid)
            self.confirm_height_button.setEnabled(bool(solid and not height))
            self.build_button.setEnabled(bool(solid and height))

        def set_tool_enabled(self, tool: CanvasTool | str, enabled: bool):
            button = self.tool_buttons.get(CanvasTool(tool).value)
            if button is not None:
                button.setEnabled(bool(enabled))


else:  # pragma: no cover

    class EditorControls:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("PySide6 is required for EditorControls")


__all__ = ["EditorControls"]
