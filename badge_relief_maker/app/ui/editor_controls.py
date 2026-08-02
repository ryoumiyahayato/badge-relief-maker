"""Compact editor controls with direct, user-facing terminology."""

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
        QSpinBox,
        QStackedWidget,
        QToolButton,
        QVBoxLayout,
        QWidget,
    )
except Exception:  # pragma: no cover
    Qt = Signal = None
    QCheckBox = QComboBox = QDoubleSpinBox = QFormLayout = QGroupBox = QHBoxLayout = QLabel = object
    QPushButton = QScrollArea = QSlider = QSpinBox = QStackedWidget = QToolButton = QVBoxLayout = QWidget = object

from .editor_session import CanvasTool, EditorMode


if Signal is not None:

    class EditorControls(QWidget):
        """Top bar, tool rail, and the currently selected mode's controls."""

        mode_requested = Signal(str)
        tool_requested = Signal(str)
        action_requested = Signal(str)
        overlay_opacity_changed = Signal(float)
        layer_visibility_requested = Signal(str, bool)
        brush_size_requested = Signal(str, int)

        def __init__(self, parent=None):
            super().__init__(parent)
            self.setObjectName("editorControls")
            self.tool_buttons: dict[str, QToolButton] = {}
            self._brush_widgets: dict[str, tuple[QSlider, QSpinBox]] = {}
            self._build()

        def _build(self):
            root = QVBoxLayout(self)
            root.setContentsMargins(0, 0, 0, 0)
            root.setSpacing(0)

            self.top_bar = QWidget()
            top = QHBoxLayout(self.top_bar)
            top.setContentsMargins(8, 6, 8, 6)
            top.setSpacing(5)
            for label, action in (
                ("打开图片", "open_image"),
                ("打开项目", "open_project"),
                ("保存项目", "save_project"),
                ("撤销", "undo"),
                ("重做", "redo"),
            ):
                top.addWidget(self._button(label, action))
            self.open_image_button = self.top_bar.findChild(QPushButton, "open_imageButton")
            self.open_project_button = self.top_bar.findChild(QPushButton, "open_projectButton")
            self.save_project_button = self.top_bar.findChild(QPushButton, "save_projectButton")
            self.undo_button = self.top_bar.findChild(QPushButton, "undoButton")
            self.redo_button = self.top_bar.findChild(QPushButton, "redoButton")

            top.addSpacing(8)
            self.solid_mode_button = self._mode_button("区域", EditorMode.SOLID)
            self.height_mode_button = self._mode_button("高度", EditorMode.HEIGHT)
            self.mesh_mode_button = self._mode_button("模型", EditorMode.MESH)
            for button in (self.solid_mode_button, self.height_mode_button, self.mesh_mode_button):
                top.addWidget(button)

            top.addSpacing(8)
            self.confirm_solid_button = self._button("确认区域", "approve")
            self.confirm_height_button = self._button("确认高度", "approve")
            self.approve_button = self.confirm_solid_button
            self.build_button = self._button("生成模型", "build")
            self.export_button = self.build_button
            top.addWidget(self.confirm_solid_button)
            top.addWidget(self.confirm_height_button)
            top.addWidget(self.build_button)

            self.overlay_opacity_slider = QSlider(Qt.Orientation.Horizontal)
            self.overlay_opacity_slider.setRange(0, 100)
            self.overlay_opacity_slider.setValue(50)
            self.overlay_opacity_slider.setFixedWidth(72)
            self.overlay_opacity_slider.setToolTip("预览透明度")
            self.overlay_opacity_slider.valueChanged.connect(lambda value: self.overlay_opacity_changed.emit(float(value) / 100.0))
            top.addWidget(QLabel("预览"))
            top.addWidget(self.overlay_opacity_slider)

            self.source_layer_check = self._layer_check("原图", "source", True)
            self.solid_layer_check = self._layer_check("区域", "solid", True)
            self.height_layer_check = self._layer_check("高度", "height", True)
            for checkbox in (self.source_layer_check, self.solid_layer_check, self.height_layer_check):
                top.addWidget(checkbox)

            self.tool_status_label = QLabel("工具：添加区域")
            self.brush_size_status_label = QLabel("画笔：24 px")
            self.zoom_status_label = QLabel("缩放：100%")
            top.addWidget(self.tool_status_label)
            top.addWidget(self.brush_size_status_label)
            top.addWidget(self.zoom_status_label)
            top.addStretch(1)
            self.solid_status_label = QLabel("区域：未确认")
            self.height_status_label = QLabel("高度：未确认")
            self.mode_status_label = QLabel("模式：区域")
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
                CanvasTool.BACKGROUND_SAMPLE.value: "取背景色",
                CanvasTool.BRUSH_ADD.value: "添加区域",
                CanvasTool.BRUSH_ERASE.value: "擦除区域",
                CanvasTool.FILL.value: "填充区域",
                CanvasTool.RECTANGLE.value: "矩形",
                CanvasTool.POLYGON.value: "多边形",
                CanvasTool.HEIGHT_SET.value: "设置高度",
                CanvasTool.HEIGHT_RAISE.value: "抬高",
                CanvasTool.HEIGHT_LOWER.value: "降低",
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

        def _build_brush_controls(self, mode: str, form: QFormLayout):
            slider = QSlider(Qt.Orientation.Horizontal)
            slider.setObjectName(f"{mode}BrushSizeSlider")
            slider.setRange(2, 300)
            slider.setValue(24)
            spin = QSpinBox()
            spin.setObjectName(f"{mode}BrushSizeSpin")
            spin.setRange(2, 300)
            spin.setValue(24)
            spin.setSuffix(" px")
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.addWidget(slider, 1)
            row_layout.addWidget(spin)
            self._brush_widgets[mode] = (slider, spin)

            def from_slider(value, *, selected=mode, target=spin):
                target.blockSignals(True)
                target.setValue(int(value))
                target.blockSignals(False)
                self.brush_size_requested.emit(selected, int(value))

            def from_spin(value, *, selected=mode, target=slider):
                target.blockSignals(True)
                target.setValue(int(value))
                target.blockSignals(False)
                self.brush_size_requested.emit(selected, int(value))

            slider.valueChanged.connect(from_slider)
            spin.valueChanged.connect(from_spin)
            form.addRow("画笔大小", row)
            return slider, spin

        def set_brush_size(self, mode: str, value: int):
            widgets = self._brush_widgets.get(str(mode))
            if widgets is None:
                return
            slider, spin = widgets
            slider.blockSignals(True)
            spin.blockSignals(True)
            slider.setValue(int(value))
            spin.setValue(int(value))
            slider.blockSignals(False)
            spin.blockSignals(False)

        def _build_solid_page(self):
            page, layout, form = self._page("区域")
            self.solid_mode_combo = QComboBox()
            self.solid_mode_combo.addItems(["保留整张图", "去除背景", "手动编辑"])
            self.solid_mode_combo.setCurrentText("去除背景")
            self.explicit_background_combo = QComboBox()
            self.explicit_background_combo.addItems(["自动", "浅色", "深色"])
            self.background_strength_slider = QSlider(Qt.Orientation.Horizontal)
            self.background_strength_slider.setRange(0, 100)
            self.background_strength_slider.setValue(8)
            self.background_strength_spin = QSpinBox()
            self.background_strength_spin.setRange(0, 100)
            self.background_strength_spin.setValue(8)
            self.background_strength_spin.setSuffix(" / 100")
            self.background_strength_slider.valueChanged.connect(self.background_strength_spin.setValue)
            self.background_strength_spin.valueChanged.connect(self.background_strength_slider.setValue)
            strength_row = QWidget()
            strength_layout = QHBoxLayout(strength_row)
            strength_layout.setContentsMargins(0, 0, 0, 0)
            strength_layout.addWidget(self.background_strength_slider, 1)
            strength_layout.addWidget(self.background_strength_spin)
            # Compatibility alias; the visible control is intentionally 0--100.
            self.background_tolerance_spin = self.background_strength_spin
            self.edge_refinement_spin = QSpinBox()
            self.edge_refinement_spin.setRange(-20, 20)
            self.edge_refinement_spin.setValue(0)
            self.edge_refinement_spin.setSuffix(" px")
            self.solid_brush_size_slider, self.solid_brush_size_spin = self._build_brush_controls("solid", form)
            self.solid_radius_spin = self.solid_brush_size_spin
            form.insertRow(0, "保留区域", self.solid_mode_combo)
            form.insertRow(1, "背景类型", self.explicit_background_combo)
            form.insertRow(2, "去背景强度", strength_row)
            form.insertRow(3, "边缘修正", self.edge_refinement_spin)
            self.solid_amount_label = QLabel("在画布上拖动以添加或擦除区域")
            form.addRow(self.solid_amount_label)

            self.remove_background_button = QPushButton("去除背景")
            self.remove_background_button.clicked.connect(lambda: self.action_requested.emit("remove_background"))
            self.refresh_solid_button = QPushButton("重新计算")
            self.refresh_solid_button.clicked.connect(lambda: self.action_requested.emit("refresh_solid"))
            self.sample_background_button = QPushButton("取背景色")
            self.sample_background_button.clicked.connect(lambda: self.action_requested.emit("sample_background"))
            self.finish_polygon_button = QPushButton("完成多边形")
            self.finish_polygon_button.clicked.connect(lambda: self.action_requested.emit("finish_polygon"))
            layout.addWidget(self.remove_background_button)
            layout.addWidget(self.sample_background_button)
            layout.addWidget(self.refresh_solid_button)
            layout.addWidget(self.finish_polygon_button)
            self.solid_confirm_state = QLabel("区域未确认")
            layout.addWidget(self.solid_confirm_state)
            layout.addStretch(1)
            self.property_stack.addWidget(page)

        def _build_height_page(self):
            page, layout, form = self._page("高度")
            self.height_mode_combo = QComboBox()
            self.height_mode_combo.addItems(["亮处更高", "暗处更高", "刻线", "凸线", "等高"])
            self.height_relief_spin = self._spin(0.01, 100.0, 3.0, 0.1, 2, " mm")
            form.addRow("灰度方式", self.height_mode_combo)
            form.addRow("浮雕高度", self.height_relief_spin)
            self.height_brush_size_slider, self.height_brush_size_spin = self._build_brush_controls("height", form)
            self.height_radius_spin = self.height_brush_size_spin
            self.height_amount_spin = self._spin(0.0, 1.0, 0.10, 0.01, 2)
            form.addRow("画笔强度", self.height_amount_spin)

            self.advanced_group = QGroupBox("高级调整")
            self.advanced_group.setCheckable(True)
            self.advanced_group.setChecked(False)
            advanced_widget = QWidget()
            advanced_form = QFormLayout(advanced_widget)
            advanced_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
            self.low_percentile_spin = self._spin(0.0, 49.9, 2.0, 0.5, 1)
            self.high_percentile_spin = self._spin(50.1, 100.0, 98.0, 0.5, 1)
            self.black_point_spin = self._spin(0.0, 0.99, 0.0, 0.01, 2)
            self.white_point_spin = self._spin(0.01, 1.0, 1.0, 0.01, 2)
            self.midtone_spin = self._spin(0.1, 4.0, 1.0, 0.05, 2)
            self.invert_check = QCheckBox("反转灰度")
            self.fixed_height_spin = self._spin(0.0, 1.0, 1.0, 0.05, 2)
            self.line_depth_spin = self._spin(0.0, 5.0, 0.2, 0.05, 2, " mm")
            self.line_threshold_spin = self._spin(0.0, 1.0, 0.35, 0.01, 2)
            self.line_softness_spin = self._spin(0.0, 8.0, 0.75, 0.25, 2, " px")
            for label, control in (
                ("最低百分位", self.low_percentile_spin),
                ("最高百分位", self.high_percentile_spin),
                ("最低点", self.black_point_spin),
                ("最高点", self.white_point_spin),
                ("中间调", self.midtone_spin),
                ("方向", self.invert_check),
                ("等高值", self.fixed_height_spin),
                ("线条深度", self.line_depth_spin),
                ("线条阈值", self.line_threshold_spin),
                ("线条平滑", self.line_softness_spin),
            ):
                advanced_form.addRow(label, control)
            group_layout = QVBoxLayout(self.advanced_group)
            group_layout.addWidget(advanced_widget)
            self.advanced_group.toggled.connect(advanced_widget.setVisible)
            advanced_widget.setVisible(False)
            layout.addWidget(self.advanced_group)

            self.refresh_height_button = QPushButton("重新计算")
            self.refresh_height_button.clicked.connect(lambda: self.action_requested.emit("refresh_height"))
            self.reset_height_button = QPushButton("恢复默认")
            self.reset_height_button.clicked.connect(lambda: self.action_requested.emit("reset_height"))
            layout.addWidget(self.refresh_height_button)
            layout.addWidget(self.reset_height_button)
            self.height_confirm_state = QLabel("高度未确认")
            layout.addWidget(self.height_confirm_state)
            layout.addStretch(1)
            self.property_stack.addWidget(page)

        def _build_mesh_page(self):
            page, layout, form = self._page("模型设置")
            self.width_spin = self._spin(1.0, 2000.0, 80.0, 1.0, 2, " mm")
            self.height_spin = self._spin(1.0, 2000.0, 80.0, 1.0, 2, " mm")
            self.base_spin = self._spin(0.0, 100.0, 2.0, 0.1, 2, " mm")
            self.relief_spin_mesh = self._spin(0.0, 100.0, 3.0, 0.1, 2, " mm")
            self.minimum_thickness_spin = self._spin(0.0, 100.0, 0.8, 0.1, 2, " mm")
            self.min_feature_spin = self._spin(0.001, 100.0, 0.3, 0.05, 3, " mm")
            self.quality_combo = QComboBox()
            self.quality_combo.addItems(["快速", "标准", "精细"])
            self.quality_combo.setCurrentText("标准")
            self.format_combo = QComboBox()
            self.format_combo.addItems(["OBJ", "STL", "GLB"])
            for label, control in (
                ("宽度", self.width_spin),
                ("高度", self.height_spin),
                ("基础厚度", self.base_spin),
                ("浮雕高度", self.relief_spin_mesh),
                ("最小厚度", self.minimum_thickness_spin),
                ("最小细节尺寸", self.min_feature_spin),
                ("模型精度", self.quality_combo),
                ("格式", self.format_combo),
            ):
                form.addRow(label, control)
            # Preserve the previous public attribute used by the coordinator.
            self.mesh_relief_spin = self.relief_spin_mesh
            self.mesh_status_label = QLabel("确认高度后可生成模型")
            self.mesh_report_label = QLabel("")
            self.mesh_report_label.setWordWrap(True)
            layout.addWidget(self.mesh_status_label)
            layout.addWidget(self.mesh_report_label)
            layout.addStretch(1)
            self.property_stack.addWidget(page)

        def set_mode(self, mode: EditorMode | str):
            selected = EditorMode(mode)
            self.property_stack.setCurrentIndex({EditorMode.SOLID: 0, EditorMode.HEIGHT: 1, EditorMode.MESH: 2}[selected])
            self.mode_status_label.setText({EditorMode.SOLID: "模式：区域", EditorMode.HEIGHT: "模式：高度", EditorMode.MESH: "模式：模型"}[selected])
            for value, button in (
                (EditorMode.SOLID, self.solid_mode_button),
                (EditorMode.HEIGHT, self.height_mode_button),
                (EditorMode.MESH, self.mesh_mode_button),
            ):
                button.setChecked(value == selected)
            self.confirm_solid_button.setVisible(selected == EditorMode.SOLID)
            self.confirm_height_button.setVisible(selected == EditorMode.HEIGHT)
            self.build_button.setVisible(selected == EditorMode.MESH)

        def set_approval_state(self, solid: bool, height: bool):
            self.solid_status_label.setText("区域：已确认" if solid else "区域：未确认")
            self.height_status_label.setText("高度：已确认" if height else "高度：未确认")
            self.solid_confirm_state.setText("区域已确认" if solid else "区域未确认")
            self.height_confirm_state.setText("高度已确认" if height else "高度未确认")
            self.height_mode_button.setEnabled(bool(solid))
            self.mesh_mode_button.setEnabled(bool(solid and height))
            self.confirm_solid_button.setEnabled(not solid)
            self.confirm_height_button.setEnabled(bool(solid and not height))
            self.build_button.setEnabled(bool(solid and height))

        def set_tool_enabled(self, tool: CanvasTool | str, enabled: bool):
            button = self.tool_buttons.get(CanvasTool(tool).value)
            if button is not None:
                button.setEnabled(bool(enabled))

        def set_tool_status(self, label: str):
            self.tool_status_label.setText(f"工具：{label}")

        def set_brush_status(self, value: int):
            self.brush_size_status_label.setText(f"画笔：{int(value)} px")

        def set_zoom_status(self, percent: float):
            self.zoom_status_label.setText(f"缩放：{int(round(float(percent)))}%")


else:  # pragma: no cover

    class EditorControls:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("PySide6 is required for EditorControls")


__all__ = ["EditorControls"]
