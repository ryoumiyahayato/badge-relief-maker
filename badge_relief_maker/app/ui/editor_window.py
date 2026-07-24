"""Corrected visual editor built on the stable project window.

The legacy window already provides the complete control surface. This subclass
keeps clicks from source and final-grid previews in distinct coordinate spaces,
prevents edits from drifting after crop/resize, freezes mutable controls while a
background build reads the project, and supports a user-selected export folder.
"""

import json
import shutil
from pathlib import Path

try:
    from PySide6.QtWidgets import QFileDialog, QHBoxLayout, QLabel, QMessageBox, QPushButton, QWidget
except Exception:
    QFileDialog = None
    QHBoxLayout = None
    QLabel = None
    QMessageBox = None
    QPushButton = None
    QWidget = None

from ..core.image_editing import rectify_perspective
from ..core.image_preprocess import load_image, normalize_alpha_background
from ..core.preview_exporter import save_source_preview
from ..core.project_build import relief_parameters_from_project
from ..core.project_io import asset_root_for, resolve_project_asset
from ..core.project_model import ManualMarker
from ..core.single_side_pipeline import prepare_relief_field
from .main_window import MainWindow as _BaseMainWindow


class MainWindow(_BaseMainWindow):
    """Project editor with coordinate-safe source and final-grid interactions."""

    def __init__(self):
        self._preview_transform = None
        self._preview_processing_shape = None
        self._raw_source_preview_path = None
        self._editing_source_preview_path = None
        self.selected_output_directory = None
        self.output_directory_label = None
        super().__init__()
        self._install_output_directory_controls()
        self._wire_preview_spaces()

    def _install_output_directory_controls(self):
        if QWidget is None or QHBoxLayout is None or QLabel is None or QPushButton is None:
            return
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(QLabel("Export folder"))
        self.output_directory_label = QLabel("Project exports folder")
        layout.addWidget(self.output_directory_label, 1)
        choose_button = QPushButton("Choose…")
        choose_button.clicked.connect(self.choose_output_directory)
        layout.addWidget(choose_button)
        self.centralWidget().layout().insertWidget(1, row)

    def choose_output_directory(self):
        if QFileDialog is None:
            return
        start = str(self.selected_output_directory or (Path(self.project_path).parent if self.project_path else Path.cwd()))
        selected = QFileDialog.getExistingDirectory(self, "Choose export folder", start)
        if not selected:
            return
        self.selected_output_directory = str(Path(selected).resolve())
        if self.output_directory_label is not None:
            self.output_directory_label.setText(self.selected_output_directory)
        self._log(f"Selected export folder: {self.selected_output_directory}")

    @staticmethod
    def _unique_copy_path(directory, filename):
        directory = Path(directory)
        original = Path(filename)
        candidate = directory / original.name
        counter = 2
        while candidate.exists():
            candidate = directory / f"{original.stem}_{counter}{original.suffix}"
            counter += 1
        return candidate

    def _copy_result_to_selected_output(self, result):
        """Copy a completed atomic project export into the user's chosen folder.

        The project-owned export remains as a recoverable source artifact. Export
        history is updated only after the external copy succeeds, so a copy error
        cannot leave history pointing at a missing file.
        """
        if not self.selected_output_directory or not getattr(result, "output_path", None):
            return result
        source = Path(result.output_path)
        if not source.is_file():
            raise FileNotFoundError(f"completed export does not exist: {source}")
        directory = Path(self.selected_output_directory).resolve()
        directory.mkdir(parents=True, exist_ok=True)
        target = self._unique_copy_path(directory, source.name)
        shutil.copy2(source, target)
        result.output_path = str(target)
        result.report["export_path"] = str(target)
        result.report["project_owned_export_path"] = str(source)
        result.report["selected_output_directory"] = str(directory)
        if self.project is not None and self.project.export_history:
            record = self.project.export_history[-1]
            record.path = str(target)
            record.report = result.report
        return result

    def _build_finished(self, result):
        try:
            self._copy_result_to_selected_output(result)
        except Exception as exc:
            self._error("Could not copy export to the selected folder; the project-owned export was retained", exc)
        super()._build_finished(result)

    def _wire_preview_spaces(self):
        for label in (self.source_preview, self.mask_preview, self.region_preview, self.height_preview):
            try:
                label.clicked.disconnect()
            except (RuntimeError, TypeError):
                pass
        self.source_preview.clicked.connect(lambda x, y: self._preview_clicked("source", x, y))
        self.mask_preview.clicked.connect(lambda x, y: self._preview_clicked("final", x, y))
        self.region_preview.clicked.connect(lambda x, y: self._preview_clicked("final", x, y))
        self.height_preview.clicked.connect(lambda x, y: self._preview_clicked("final", x, y))
        try:
            self.edit_tool_combo.currentTextChanged.disconnect(self._mark_dirty)
        except (RuntimeError, TypeError):
            pass
        self.edit_tool_combo.currentTextChanged.connect(self._edit_tool_changed)

    def _apply_controls_to_project(self, side_name=None):
        super()._apply_controls_to_project(side_name)
        if self.project is not None:
            self.project.double_side.enabled = bool(self.project.front_image is not None and self.project.back_image is not None)

    def _set_preview(self, label, path, empty_text):
        label.clear()
        super()._set_preview(label, path, empty_text)

    def _clear_previews(self):
        self._preview_transform = None
        self._preview_processing_shape = None
        self._raw_source_preview_path = None
        self._editing_source_preview_path = None
        super()._clear_previews()

    def _source_preview_path_for_tool(self):
        if self.edit_tool_combo.currentText() == "perspective quadrilateral":
            return self._raw_source_preview_path
        return self._editing_source_preview_path or self._raw_source_preview_path

    def _edit_tool_changed(self, *_):
        self._crop_first_point = None
        self._perspective_points = []
        self._set_preview(self.source_preview, self._source_preview_path_for_tool(), "Source editing image")

    def _write_source_edit_previews(self, source_path, params, preview_dir):
        loaded = load_image(source_path)
        raw_rgba = normalize_alpha_background(loaded.rgba)
        raw_path = save_source_preview(raw_rgba, Path(preview_dir) / "source_oriented_preview.png")
        editing_rgba, _ = rectify_perspective(raw_rgba, params.perspective_quad)
        editing_path = save_source_preview(editing_rgba, Path(preview_dir) / "source_editing_preview.png")
        return raw_path, editing_path, tuple(editing_rgba.shape[:2])

    def refresh_previews(self):
        record = self._image_record()
        if record is None or not self.project_path:
            self._clear_previews()
            return
        try:
            self._apply_controls_to_project(self.active_side)
            params, _ = relief_parameters_from_project(self.project, self.active_side, self.quality_combo.currentText())
            source_path = resolve_project_asset(self.project_path, record.path)
            preview_dir = asset_root_for(self.project_path) / "previews" / "gui" / self.active_side
            preview_dir.mkdir(parents=True, exist_ok=True)
            prepared = prepare_relief_field(source_path, params, preview_dir=preview_dir)
            raw_path, editing_path, processing_shape = self._write_source_edit_previews(source_path, params, preview_dir)
            self._preview_transform = prepared.image_transform
            self._preview_processing_shape = processing_shape
            self._raw_source_preview_path = raw_path
            self._editing_source_preview_path = editing_path
            paths = prepared.report["preview_paths"]
            self._set_preview(self.source_preview, self._source_preview_path_for_tool(), "Source image unavailable")
            self._set_preview(self.mask_preview, paths.get("mask_overlay_preview"), "Mask preview unavailable")
            self._set_preview(
                self.region_preview,
                paths.get("lineart_region_preview"),
                "Region topology is available for line artwork",
            )
            self._set_preview(self.height_preview, paths.get("relief_preview") or paths.get("heightmap_preview"), "Relief preview unavailable")
            self.report_box.setPlainText(self._preview_summary(prepared.report))
            self.details_box.setPlainText(json.dumps(prepared.report, indent=2, ensure_ascii=False, default=str))
            self._log(f"Refreshed {self.active_side} previews")
        except Exception as exc:
            self._error("Could not refresh previews", exc)

    def _marker_geometry(self, preview_space, x_normalized, y_normalized, radius_normalized):
        coordinate_space = "final_normalized" if preview_space == "final" else "normalized"
        return {
            "x": x_normalized,
            "y": y_normalized,
            "radius_normalized": radius_normalized,
            "coordinate_space": coordinate_space,
        }

    def _mask_edit_geometry(self, preview_space, x_normalized, y_normalized, radius_normalized):
        if preview_space == "final":
            if self._preview_transform is None:
                raise ValueError("refresh previews before editing the final mask")
            x_pixel, y_pixel = self._preview_transform.target_to_original_point(x_normalized, y_normalized, normalized=True)
            radius_pixel = self._preview_transform.target_radius_to_original(radius_normalized, normalized=True)
            return {
                "x": x_pixel,
                "y": y_pixel,
                "radius_px": radius_pixel,
                "coordinate_space": "pixel",
            }
        return {
            "x": x_normalized,
            "y": y_normalized,
            "radius_normalized": radius_normalized,
            "coordinate_space": "normalized",
        }

    def _confirm_perspective_reset(self, side):
        has_dependent_edits = bool(
            side.manual_crop_box
            or side.mask_edits
            or side.region_layers
            or side.lineart_region_overrides
            or any(str(marker.target).lower() in {self.active_side, "both"} for marker in self.project.manual_markers)
        )
        if not has_dependent_edits or QMessageBox is None:
            return True
        answer = QMessageBox.question(
            self,
            "Reset coordinate-dependent edits",
            "Changing perspective changes the source coordinate system. Clear crop, mask, layer and height edits for this side?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        )
        return answer == QMessageBox.StandardButton.Yes

    def _clear_side_coordinate_edits(self, side, keep_perspective=False):
        side.manual_crop_box = None
        side.mask_edits = []
        side.region_layers = []
        side.lineart_region_overrides = []
        if not keep_perspective:
            side.perspective_quad = None
        other_side = "back" if self.active_side == "front" else "front"
        retained = []
        for marker in self.project.manual_markers:
            target = str(marker.target).lower()
            if target == self.active_side:
                continue
            if target == "both":
                retained.append(
                    ManualMarker(
                        marker_type=marker.marker_type,
                        target=other_side,
                        data=dict(marker.data),
                        created_at=marker.created_at,
                    )
                )
            else:
                retained.append(marker)
        self.project.manual_markers = retained

    def _preview_clicked(self, *args):
        if len(args) == 3:
            preview_space, x_normalized, y_normalized = args
        elif len(args) == 2:
            preview_space = "final"
            x_normalized, y_normalized = args
        else:
            return
        if self.project is None or self._image_record() is None:
            return
        if self._build_thread is not None:
            self._log("Wait for the active build before editing previews.")
            return
        tool = self.edit_tool_combo.currentText()
        if tool == "inspect":
            self._log(f"{preview_space} preview point: x={x_normalized:.4f}, y={y_normalized:.4f}")
            return
        side = self._side_parameters(self.active_side)
        radius = self.brush_radius_spin.value()
        try:
            if tool in {"mask add", "mask remove"}:
                side.mask_edits.append(
                    {
                        "shape": "circle",
                        **self._mask_edit_geometry(preview_space, x_normalized, y_normalized, radius),
                        "operation": "add" if tool == "mask add" else "remove",
                    }
                )
            elif tool in {"height set", "height add", "height subtract", "height smooth"}:
                if preview_space != "final":
                    self._log("Height edits must be applied on the final height or mask preview.")
                    return
                self.project.manual_markers.append(
                    ManualMarker(
                        marker_type="height",
                        target=self.active_side,
                        data={
                            "shape": "circle",
                            **self._marker_geometry(preview_space, x_normalized, y_normalized, radius),
                            "operation": tool.removeprefix("height "),
                            "value": self.brush_height_spin.value(),
                        },
                    )
                )
            elif tool in {"region background", "region surface", "region raise", "region recess"}:
                if preview_space != "final":
                    self._log("Line-art region edits must be applied on the final mask or relief preview.")
                    return
                side.lineart_region_overrides.append(
                    {
                        "x": x_normalized,
                        "y": y_normalized,
                        "coordinate_space": "final_normalized",
                        "role": tool.removeprefix("region "),
                        "amount": self.brush_height_spin.value(),
                    }
                )
            elif tool in {"layer set", "layer locked"}:
                if preview_space != "final":
                    self._log("Layer edits must be applied on the final height or mask preview.")
                    return
                side.region_layers.append(
                    {
                        "shape": "circle",
                        **self._marker_geometry(preview_space, x_normalized, y_normalized, radius),
                        "height_normalized": self.brush_height_spin.value(),
                        "locked": tool == "layer locked",
                    }
                )
            elif tool == "crop rectangle":
                if preview_space != "source":
                    self._log("Crop rectangle must be selected on the source editing preview.")
                    return
                if self._preview_processing_shape is None:
                    raise ValueError("refresh previews before selecting a crop")
                if self._crop_first_point is None:
                    self._crop_first_point = (x_normalized, y_normalized)
                    self._log("Crop first corner recorded; click the opposite corner.")
                    return
                first_x, first_y = self._crop_first_point
                self._crop_first_point = None
                rows, cols = self._preview_processing_shape
                side.manual_crop_box = [
                    min(first_x, x_normalized) * cols,
                    min(first_y, y_normalized) * rows,
                    max(first_x, x_normalized) * cols,
                    max(first_y, y_normalized) * rows,
                ]
            elif tool == "perspective quadrilateral":
                if preview_space != "source":
                    self._log("Perspective points must be selected on the oriented source preview.")
                    return
                self._perspective_points.append([x_normalized, y_normalized])
                if len(self._perspective_points) < 4:
                    self._log(f"Perspective point {len(self._perspective_points)}/4 recorded (TL, TR, BR, BL).")
                    return
                if not self._confirm_perspective_reset(side):
                    self._perspective_points = []
                    self._log("Perspective change cancelled.")
                    return
                points = self._perspective_points[:4]
                self._perspective_points = []
                self._clear_side_coordinate_edits(side, keep_perspective=True)
                side.perspective_quad = points
            else:
                return
        except Exception as exc:
            self._error("Could not apply preview edit", exc)
            return
        self._dirty = True
        self.refresh_previews()

    def clear_visual_edits(self):
        if self.project is None:
            return
        self._clear_side_coordinate_edits(self._side_parameters(self.active_side), keep_perspective=False)
        self._crop_first_point = None
        self._perspective_points = []
        self._dirty = True
        self.refresh_previews()

    def _set_building(self, building):
        super()._set_building(building)
        enabled = not building
        if QPushButton is not None:
            for button in self.findChildren(QPushButton):
                button.setEnabled(enabled)
        for control in getattr(self, "_controls", []):
            control.setEnabled(enabled)
        if getattr(self, "side_combo", None) is not None:
            self.side_combo.setEnabled(enabled)
        for preview in (self.source_preview, self.mask_preview, self.height_preview):
            preview.setEnabled(enabled)
