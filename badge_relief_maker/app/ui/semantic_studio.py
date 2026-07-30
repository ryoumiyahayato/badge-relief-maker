"""Default semantic review UI with Bezier contours and physical inspection."""

from pathlib import Path
import uuid

try:
    from PySide6.QtWidgets import (
        QCheckBox,
        QComboBox,
        QDoubleSpinBox,
        QFormLayout,
        QGroupBox,
        QHBoxLayout,
        QLabel,
        QPushButton,
        QTabWidget,
        QVBoxLayout,
        QWidget,
    )
except Exception:
    QCheckBox = None
    QComboBox = None
    QDoubleSpinBox = None
    QFormLayout = None
    QGroupBox = None
    QHBoxLayout = None
    QLabel = None
    QPushButton = None
    QTabWidget = None
    QVBoxLayout = None
    QWidget = None

from ..core.bezier_contours import default_bezier_contour_from_mask, map_contour_points
from ..core.lineart_regions import save_focused_region_preview
from ..core.options import (
    ADAPTIVE_MESH_DEFAULT,
    CONTOUR_OPERATIONS,
    LOCK_CONFIRMED_REGIONS_DEFAULT,
    QUALITY_MODES,
)
from ..core.profile_inspection import sample_height_profile, save_height_profile_preview
from ..core.project_io import asset_root_for
from ..core.quality_modes import QUALITY_PRESETS
from .bezier_editor import BezierContourEditor
from .editor_window import MainWindow as EditorMainWindow
from .project_window import _PreviewLabel


ROLE_OPTIONS = {
    "空（挖空）": "void",
    "实体补填／底面": "base",
    "低层浮雕": "low",
    "中层浮雕": "mid",
    "高层浮雕": "high",
    "最高构件": "top",
    "相对抬高": "raise",
    "相对压低": "recess",
}
QUALITY_NAMES = {"preview": "快速预览", "standard": "精细模型", "high": "极细模型"}
QUALITY_OPTIONS = {
    f"{QUALITY_NAMES[mode]}（约{settings['max_grid_cells'] // 10000}万网格点）": mode
    for mode, settings in QUALITY_PRESETS.items()
}
QUALITY_LABELS = {mode: label for label, mode in QUALITY_OPTIONS.items()}
REVIEW_OPTIONS = {
    "区域语义图": "semantic_region_preview",
    "识别置信度热图": "confidence_heatmap_preview",
    "实体蒙版": "mask_preview",
}


class MainWindow(EditorMainWindow):
    """Public editor integrating semantic, contour and adaptive-mesh workflows."""

    def __init__(self):
        self._review_regions = []
        self._review_region_index = -1
        self._loading_semantic_controls = False
        super().__init__()
        self.setWindowTitle("Badge Relief Maker - Semantic Studio")
        self._install_semantic_controls()
        self._install_review_panels()
        self._install_bezier_editor()

    def _install_semantic_controls(self):
        if QGroupBox is None:
            return
        self.edit_tool_combo.addItems(["semantic part", "semantic brush"])
        self.edit_tool_combo.setCurrentText("semantic part")
        self.semantic_role_combo = QComboBox()
        self.semantic_role_combo.addItems(ROLE_OPTIONS)
        self.semantic_role_combo.setCurrentText("中层浮雕")
        self.lock_confirmed_check = QCheckBox("锁定已确认区域")
        self.lock_confirmed_check.setChecked(LOCK_CONFIRMED_REGIONS_DEFAULT)
        self.semantic_strength_spin = QDoubleSpinBox()
        self.semantic_strength_spin.setRange(0.01, 0.50)
        self.semantic_strength_spin.setSingleStep(0.01)
        self.semantic_strength_spin.setValue(0.12)
        self.adaptive_mesh_check = QCheckBox("仅在轮廓、刻线和高度突变处细分网格")
        self.adaptive_mesh_check.setChecked(ADAPTIVE_MESH_DEFAULT)
        self.model_quality_combo = QComboBox()
        self.model_quality_combo.addItems(QUALITY_OPTIONS)
        self.model_quality_combo.setCurrentText(QUALITY_LABELS[QUALITY_MODES.default])
        self.quality_combo.hide()
        self.review_combo = QComboBox()
        self.review_combo.addItems(REVIEW_OPTIONS)
        self.next_issue_button = QPushButton("下一个待确认区域")
        group = QGroupBox("人工语义标注与复核")
        form = QFormLayout(group)
        form.addRow("标注含义", self.semantic_role_combo)
        form.addRow("相对修正幅度", self.semantic_strength_spin)
        form.addRow("", self.lock_confirmed_check)
        form.addRow("检查视图", self.review_combo)
        form.addRow("", self.next_issue_button)
        form.addRow("模型密度", self.model_quality_combo)
        form.addRow("", self.adaptive_mesh_check)
        self.controls_layout.insertWidget(max(self.controls_layout.count() - 1, 0), group)
        self._controls.extend(
            [
                self.semantic_role_combo,
                self.semantic_strength_spin,
                self.lock_confirmed_check,
                self.review_combo,
                self.model_quality_combo,
                self.adaptive_mesh_check,
            ]
        )
        self.review_combo.currentTextChanged.connect(self._refresh_review_image)
        self.next_issue_button.clicked.connect(self.focus_next_issue)
        self.lock_confirmed_check.toggled.connect(self._mark_semantic_setting_dirty)
        self.model_quality_combo.currentTextChanged.connect(self._mark_semantic_setting_dirty)
        self.adaptive_mesh_check.toggled.connect(self._mark_semantic_setting_dirty)

    def _install_review_panels(self):
        if QHBoxLayout is None or _PreviewLabel is None or QTabWidget is None:
            return
        self.advanced_tabs = QTabWidget()
        review_page = QWidget()
        review_layout = QVBoxLayout(review_page)
        self.review_preview = _PreviewLabel("区域语义图")
        self.profile_preview = _PreviewLabel("实际高度剖面")
        row = QHBoxLayout()
        row.addWidget(self.review_preview)
        row.addWidget(self.profile_preview)
        review_layout.addLayout(row)
        self.review_preview.clicked.connect(lambda x, y: self._preview_clicked("final", x, y))
        self.section_orientation_combo = QComboBox()
        self.section_orientation_combo.addItems(["水平截面", "垂直截面"])
        self.section_position_spin = QDoubleSpinBox()
        self.section_position_spin.setRange(0.0, 100.0)
        self.section_position_spin.setValue(50.0)
        self.section_position_spin.setSuffix(" %")
        controls = QHBoxLayout()
        controls.addWidget(QLabel("剖面方向"))
        controls.addWidget(self.section_orientation_combo)
        controls.addWidget(QLabel("截面位置"))
        controls.addWidget(self.section_position_spin)
        controls.addStretch(1)
        review_layout.addLayout(controls)
        self.advanced_tabs.addTab(review_page, "语义复核与高度剖面")
        self.right_layout.insertWidget(1, self.advanced_tabs)
        self._controls.extend([self.section_orientation_combo, self.section_position_spin])
        self.section_orientation_combo.currentTextChanged.connect(self._refresh_profile_preview)
        self.section_position_spin.valueChanged.connect(self._refresh_profile_preview)

    def _install_bezier_editor(self):
        if QGroupBox is None:
            return
        self.bezier_editor = BezierContourEditor()
        self.bezier_operation_combo = QComboBox()
        self.bezier_operation_combo.addItems(CONTOUR_OPERATIONS.values)
        initialize_button = QPushButton("从当前实体蒙版初始化")
        new_button = QPushButton("新增轮廓")
        delete_button = QPushButton("删除控制点／轮廓")
        clear_button = QPushButton("清空轮廓")
        apply_button = QPushButton("应用轮廓并刷新")
        toolbar = QHBoxLayout()
        for widget in (
            QLabel("轮廓运算"),
            self.bezier_operation_combo,
            initialize_button,
            new_button,
            delete_button,
            clear_button,
            apply_button,
        ):
            toolbar.addWidget(widget)
        group = QGroupBox("可拖动控制点的贝塞尔轮廓编辑器（双击增加锚点）")
        layout = QFormLayout(group)
        layout.addRow(toolbar)
        layout.addRow(self.bezier_editor)
        self.advanced_tabs.addTab(group, "贝塞尔轮廓")
        self._controls.append(self.bezier_operation_combo)
        self.bezier_editor.contours_changed.connect(self._bezier_contours_changed)
        self.bezier_operation_combo.currentTextChanged.connect(self.bezier_editor.set_selected_operation)
        initialize_button.clicked.connect(self.initialize_bezier_from_mask)
        new_button.clicked.connect(lambda: self.bezier_editor.new_contour(self.bezier_operation_combo.currentText()))
        delete_button.clicked.connect(self.bezier_editor.remove_selected_anchor)
        clear_button.clicked.connect(self.bezier_editor.clear_contours)
        apply_button.clicked.connect(self.refresh_previews)

    def _load_controls_from_project(self, side_name="front"):
        super()._load_controls_from_project(side_name)
        if not hasattr(self, "lock_confirmed_check") or self.project is None:
            return
        self._loading_semantic_controls = True
        try:
            side = self._side_parameters(side_name)
            self.lock_confirmed_check.setChecked(bool(side.lock_confirmed_regions))
            self.adaptive_mesh_check.setChecked(bool(side.adaptive_mesh_enabled))
            quality_label = next(
                (label for label, value in QUALITY_OPTIONS.items() if value == side.quality_mode),
                QUALITY_LABELS[QUALITY_MODES.default],
            )
            self.model_quality_combo.setCurrentText(quality_label)
            self.bezier_editor.set_contours(side.bezier_contours)
        finally:
            self._loading_semantic_controls = False

    def _apply_controls_to_project(self, side_name=None):
        super()._apply_controls_to_project(side_name)
        if not hasattr(self, "lock_confirmed_check") or self.project is None:
            return
        side = self._side_parameters(side_name or self.active_side)
        side.lock_confirmed_regions = self.lock_confirmed_check.isChecked()
        side.adaptive_mesh_enabled = self.adaptive_mesh_check.isChecked()
        side.quality_mode = QUALITY_OPTIONS[self.model_quality_combo.currentText()]
        side.bezier_contours = self.bezier_editor.contours()

    def _semantic_annotation(self, tool, x_normalized, y_normalized):
        if self._preview_transform is None:
            raise ValueError("refresh previews before adding semantic annotations")
        x_pixel, y_pixel = self._preview_transform.target_to_original_point(
            x_normalized,
            y_normalized,
            normalized=True,
        )
        return {
            "annotation_id": uuid.uuid4().hex,
            "tool": tool,
            "role": ROLE_OPTIONS[self.semantic_role_combo.currentText()],
            "x": float(x_pixel),
            "y": float(y_pixel),
            "coordinate_space": "pixel",
            "radius_px": float(self._preview_transform.target_radius_to_original(self.brush_radius_spin.value(), normalized=True)),
            "amount": float(self.semantic_strength_spin.value()),
            "locked": bool(self.lock_confirmed_check.isChecked()),
        }

    def _apply_visual_tool(self, side, tool, preview_space, x_normalized, y_normalized):
        if tool in {"semantic part", "semantic brush"}:
            if preview_space != "final":
                self._log("Semantic annotations must be placed on a final mask, height or review preview.")
                return False
            side.semantic_annotations.append(
                self._semantic_annotation("part" if tool == "semantic part" else "brush", x_normalized, y_normalized)
            )
            return True
        return super()._apply_visual_tool(side, tool, preview_space, x_normalized, y_normalized)

    def _clear_side_coordinate_edits(self, side, keep_perspective=False):
        super()._clear_side_coordinate_edits(side, keep_perspective=keep_perspective)
        side.semantic_annotations = []
        side.bezier_contours = []
        if hasattr(self, "bezier_editor"):
            self.bezier_editor.set_contours([])

    def _after_preview_refresh(self, prepared, paths):
        self._review_regions = [
            item for item in prepared.report.get("semantic_review", {}).get("regions", []) if item.get("status") != "confirmed"
        ]
        self._review_region_index = -1
        self._refresh_review_image()
        self._refresh_profile_preview()
        if hasattr(self, "bezier_editor"):
            self.bezier_editor.set_background(self._editing_source_preview_path)
            self.bezier_editor.set_contours(self._side_parameters(self.active_side).bezier_contours)

    def _refresh_review_image(self, *_):
        if not hasattr(self, "review_preview"):
            return
        key = REVIEW_OPTIONS.get(self.review_combo.currentText(), "semantic_region_preview")
        self._set_preview(self.review_preview, self._preview_paths.get(key), "Review preview unavailable")

    def focus_next_issue(self):
        if not self._review_regions:
            self._log("No unresolved review region remains.")
            return
        base = self._preview_paths.get("semantic_region_preview")
        if not base:
            return
        self._review_region_index = (self._review_region_index + 1) % len(self._review_regions)
        region = self._review_regions[self._review_region_index]
        output = Path(base).with_name("focused_semantic_region.png")
        focused = save_focused_region_preview(base, region, output)
        self._set_preview(self.review_preview, focused, "Focused region unavailable")
        self._log(f"Review region #{region.get('display_id')} ({region.get('pixel_count')} pixels)")

    def _refresh_profile_preview(self, *_):
        if not hasattr(self, "profile_preview") or self._prepared_preview is None or self.project is None or not self.project_path:
            return
        profile = sample_height_profile(
            self._prepared_preview.heightmap,
            self._prepared_preview.mask,
            orientation="horizontal" if self.section_orientation_combo.currentIndex() == 0 else "vertical",
            position_normalized=self.section_position_spin.value() / 100.0,
            width_mm=self.project.dimensions.width_mm,
            height_mm=self.project.dimensions.height_mm,
            relief_height_mm=self._side_parameters(self.active_side).relief_height_mm,
        )
        output = save_height_profile_preview(
            profile,
            asset_root_for(self.project_path) / "previews" / "gui" / self.active_side / "physical_height_profile.png",
        )
        self._set_preview(self.profile_preview, output, "Height profile unavailable")

    def _bezier_contours_changed(self, contours):
        if self._loading_semantic_controls or self.project is None:
            return
        self._side_parameters(self.active_side).bezier_contours = contours
        self._dirty = True

    def _mark_semantic_setting_dirty(self, *_):
        if not self._loading_semantic_controls:
            self._mark_dirty()

    def _set_building(self, building):
        super()._set_building(building)
        if hasattr(self, "bezier_editor"):
            self.bezier_editor.setEnabled(not building)

    def initialize_bezier_from_mask(self):
        if self._prepared_preview is None or self._preview_transform is None or self.project is None:
            self._log("Refresh previews before initializing a Bezier contour.")
            return
        contour = default_bezier_contour_from_mask(self._prepared_preview.mask)
        if contour is None:
            return
        original_rows, original_cols = self._preview_transform.original_shape

        def to_source(x, y):
            source_x, source_y = self._preview_transform.target_to_original_point(x, y, normalized=True)
            return (
                min(max(source_x / max(original_cols - 1, 1), 0.0), 1.0),
                min(max(source_y / max(original_rows - 1, 1), 0.0), 1.0),
            )

        mapped = map_contour_points(contour, to_source)
        self.bezier_editor.set_contours([mapped] if mapped is not None else [])
        self._bezier_contours_changed(self.bezier_editor.contours())
