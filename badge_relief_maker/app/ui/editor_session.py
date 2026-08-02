"""State model for the canvas-first deterministic editor.

This module contains no Qt widgets.  Keeping approval, edit history and mode
transitions here makes the workflow testable without starting a window and
prevents the GUI from accidentally sending unapproved data to the mesh path.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class EditorMode(str, Enum):
    SOLID = "solid"
    HEIGHT = "height"
    MESH = "mesh"


class CanvasTool(str, Enum):
    PAN = "pan"
    BACKGROUND_SAMPLE = "background_sample"
    BRUSH_ADD = "brush_add"
    BRUSH_ERASE = "brush_erase"
    FILL = "fill"
    RECTANGLE = "rectangle"
    POLYGON = "polygon"
    HEIGHT_SET = "height_set"
    HEIGHT_RAISE = "height_raise"
    HEIGHT_LOWER = "height_lower"
    HEIGHT_SMOOTH = "height_smooth"


@dataclass
class EditorSession:
    """Mutable, serializable editor state owned by one main window."""

    source_data: Any = None
    preview_source_data: Any = None
    solid_draft: Any = None
    height_draft: Any = None
    formal_solid_mask: Any = None
    formal_height_master: Any = None
    solid_edits: list[dict] = field(default_factory=list)
    height_edits: list[dict] = field(default_factory=list)
    solid_undo_stack: list[dict] = field(default_factory=list)
    solid_redo_stack: list[dict] = field(default_factory=list)
    height_undo_stack: list[dict] = field(default_factory=list)
    height_redo_stack: list[dict] = field(default_factory=list)
    background_samples: list[dict] = field(default_factory=list)
    solid_mask_confirmed: bool = False
    height_master_confirmed: bool = False
    artifact_directory: Path | None = None
    editor_mode: EditorMode = EditorMode.SOLID
    active_tool: CanvasTool = CanvasTool.BRUSH_ADD
    overlay_opacity: float = 0.5
    active_job_id: int | None = None
    canvas_zoom: float = 1.0
    canvas_state: dict = field(default_factory=dict)

    @property
    def solid_redo(self):
        """Compatibility alias used by the previous deterministic window."""
        return self.solid_redo_stack

    @property
    def height_redo(self):
        return self.height_redo_stack

    def reset_for_source(self, source_data, preview_source_data=None, artifact_directory=None) -> None:
        self.source_data = source_data
        self.preview_source_data = preview_source_data or source_data
        self.solid_draft = None
        self.height_draft = None
        self.formal_solid_mask = None
        self.formal_height_master = None
        self.solid_edits.clear()
        self.height_edits.clear()
        self.solid_undo_stack.clear()
        self.solid_redo_stack.clear()
        self.height_undo_stack.clear()
        self.height_redo_stack.clear()
        self.background_samples.clear()
        self.solid_mask_confirmed = False
        self.height_master_confirmed = False
        self.artifact_directory = Path(artifact_directory) if artifact_directory else None
        self.editor_mode = EditorMode.SOLID
        self.active_tool = CanvasTool.BRUSH_ADD
        self.active_job_id = None
        self.canvas_zoom = 1.0

    def add_solid_edit(self, edit: dict) -> None:
        item = deepcopy(edit)
        self.solid_edits.append(item)
        self.solid_undo_stack.append(deepcopy(item))
        self.solid_redo_stack.clear()
        self.mark_solid_changed()

    def add_height_edit(self, edit: dict) -> None:
        item = deepcopy(edit)
        self.height_edits.append(item)
        self.height_undo_stack.append(deepcopy(item))
        self.height_redo_stack.clear()
        self.mark_height_changed()

    def undo(self, mode: EditorMode | None = None) -> dict | None:
        selected = mode or self.editor_mode
        if selected == EditorMode.SOLID:
            if not self.solid_edits:
                return None
            edit = self.solid_edits.pop()
            if self.solid_undo_stack:
                self.solid_undo_stack.pop()
            self.solid_redo_stack.append(deepcopy(edit))
            self.mark_solid_changed()
            return edit
        if selected == EditorMode.HEIGHT:
            if not self.height_edits:
                return None
            edit = self.height_edits.pop()
            if self.height_undo_stack:
                self.height_undo_stack.pop()
            self.height_redo_stack.append(deepcopy(edit))
            self.mark_height_changed()
            return edit
        return None

    def redo(self, mode: EditorMode | None = None) -> dict | None:
        selected = mode or self.editor_mode
        if selected == EditorMode.SOLID:
            if not self.solid_redo_stack:
                return None
            edit = self.solid_redo_stack.pop()
            self.solid_edits.append(deepcopy(edit))
            self.solid_undo_stack.append(deepcopy(edit))
            self.mark_solid_changed()
            return edit
        if selected == EditorMode.HEIGHT:
            if not self.height_redo_stack:
                return None
            edit = self.height_redo_stack.pop()
            self.height_edits.append(deepcopy(edit))
            self.height_undo_stack.append(deepcopy(edit))
            self.mark_height_changed()
            return edit
        return None

    def mark_solid_changed(self) -> None:
        self.solid_mask_confirmed = False
        self.height_master_confirmed = False
        self.formal_solid_mask = None
        self.formal_height_master = None

    def mark_height_changed(self) -> None:
        self.height_master_confirmed = False
        self.formal_height_master = None

    def confirm_solid(self, mask=None) -> None:
        self.formal_solid_mask = mask
        self.solid_mask_confirmed = True
        self.height_master_confirmed = False
        self.formal_height_master = None

    def confirm_height(self, height_master=None) -> None:
        if not self.solid_mask_confirmed:
            raise ValueError("solid mask must be confirmed before height master")
        self.formal_height_master = height_master
        self.height_master_confirmed = True

    def request_mode(self, mode: EditorMode) -> bool:
        selected = EditorMode(mode)
        if selected == EditorMode.HEIGHT and not self.solid_mask_confirmed:
            return False
        if selected == EditorMode.MESH and not (self.solid_mask_confirmed and self.height_master_confirmed):
            return False
        self.editor_mode = selected
        return True

    def set_tool(self, tool: CanvasTool) -> None:
        self.active_tool = CanvasTool(tool)

    def snapshot(self) -> dict:
        """Return a deep immutable-by-convention snapshot for a worker."""
        return {
            "source_data": self.source_data,
            "preview_source_data": self.preview_source_data,
            "solid_edits": deepcopy(self.solid_edits),
            "height_edits": deepcopy(self.height_edits),
            "background_samples": deepcopy(self.background_samples),
            "solid_mask_confirmed": bool(self.solid_mask_confirmed),
            "height_master_confirmed": bool(self.height_master_confirmed),
        }


__all__ = ["CanvasTool", "EditorMode", "EditorSession"]
