# -*- coding: utf-8 -*-
from __future__ import annotations

import ctypes
import math
from pathlib import Path
import sys
import tkinter as tk
from tkinter import colorchooser, filedialog, messagebox, ttk
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image, ImageChops, ImageDraw, ImageTk
from shapely.geometry import GeometryCollection, LineString, MultiPolygon, Point, Polygon, box
from shapely.geometry.base import BaseGeometry
from shapely.ops import polygonize, triangulate, unary_union

from . import APP_NAME, APP_VERSION
from .model import (
    CONSTRAINT_TYPES,
    Project,
    Region,
    category_from_label,
    display_label,
    export_all,
    export_selected,
    load_project,
    save_project,
)
from .storage import load_settings, save_settings


def _l(language: str, zh: str, en: str) -> str:
    return en if language == "en" else zh


def startup_language_required(settings: Dict[str, Any]) -> bool:
    """Ask only until the user has made a valid, persisted language choice."""
    return settings.get("language") not in {"zh", "en"}


def _show_centered_dialog(
    dialog: tk.Toplevel,
    parent: tk.Misc,
    width: Optional[int] = None,
    height: Optional[int] = None,
    grab: bool = True,
) -> None:
    parent.update_idletasks()
    dialog.update_idletasks()
    width = width or dialog.winfo_reqwidth()
    height = height or dialog.winfo_reqheight()
    screen_width = dialog.winfo_screenwidth()
    screen_height = dialog.winfo_screenheight()
    width = min(width, max(320, screen_width - 64))
    height = min(height, max(200, screen_height - 96))
    x = max(8, min(screen_width - width - 16, parent.winfo_rootx() + (parent.winfo_width() - width) // 2))
    y = max(8, min(screen_height - height - 48, parent.winfo_rooty() + (parent.winfo_height() - height) // 2))
    dialog.geometry(f"{width}x{height}+{x}+{y}")
    dialog.deiconify()
    dialog.lift()
    if grab:
        dialog.grab_set()


OPERATION_MODES: Dict[str, Dict[str, str]] = {
    "new": {"label": "新建", "label_en": "New", "tip": "新建区域：按住拖动，松开后生成闭合区域。快捷键默认 N。", "tip_en": "Create a region by dragging. Default shortcut: N."},
    "modify": {"label": "增加", "label_en": "Add", "tip": "增加选定区域：拖出闭合范围，合并进当前选区。快捷键默认 M。", "tip_en": "Add the dragged area to the selected region. Default shortcut: M."},
    "delete": {"label": "减少", "label_en": "Subtract", "tip": "减少选定区域：拖出闭合范围，从当前区域扣掉覆盖部分。快捷键默认 D。", "tip_en": "Subtract the dragged area from the selected region. Default shortcut: D."},
    "drag": {"label": "调整", "label_en": "Transform", "tip": "调整区域：拖区域移动，拖角等比缩放，拖边改单轴，顶部圆点旋转。快捷键默认 V/T。", "tip_en": "Move the region, resize from handles, or rotate from the top circle. Default shortcut: V/T."},
    "none": {"label": "无操作", "label_en": "None", "tip": "无操作：暂时禁用画布编辑，防止误触。快捷键默认 Esc。", "tip_en": "Disable canvas editing temporarily. Default shortcut: Esc."},
}


BRUSH_OPERATION_TEXT: Dict[str, Dict[str, str]] = {
    "new": {"label": "画笔", "label_en": "Brush", "short": "画笔", "short_en": "Brush", "tip": "画笔：拖动画出一个新区域。快捷键默认 N。", "tip_en": "Paint a new region. Default shortcut: N."},
    "modify": {"label": "加画", "label_en": "Paint add", "short": "加画", "short_en": "Add", "tip": "加画：把画过的部分并入当前选区。快捷键默认 M。", "tip_en": "Paint into the selected region. Default shortcut: M."},
    "delete": {"label": "擦除", "label_en": "Erase", "short": "擦除", "short_en": "Erase", "tip": "擦除：从当前选区里擦掉画过的部分。快捷键默认 D。", "tip_en": "Erase from the selected region. Default shortcut: D."},
}


BOX_OPERATION_TEXT: Dict[str, Dict[str, str]] = {
    "new": {"label": "框选", "label_en": "Lasso", "short": "框选", "short_en": "Lasso", "tip": "框选：拖出闭合范围，生成新区域。快捷键默认 N。", "tip_en": "Drag a closed selection to create a region. Default shortcut: N."},
    "modify": {"label": "加选", "label_en": "Add selection", "short": "加选", "short_en": "Add", "tip": "加选：拖出闭合范围，合并进当前选区。快捷键默认 M。", "tip_en": "Add a closed selection to the selected region. Default shortcut: M."},
    "delete": {"label": "减选", "label_en": "Subtract", "short": "减选", "short_en": "Subtract", "tip": "减选：拖出闭合范围，从当前选区扣掉覆盖部分。快捷键默认 D。", "tip_en": "Subtract a closed selection from the selected region. Default shortcut: D."},
}


EXPORT_PRESETS: Dict[str, Dict[str, Any]] = {
    "ai_reading": {
        "label": "给 AI 阅读",
        "label_en": "For image AI",
        "description": "只生成强制构图说明，以及带编号、由程序分配唯一索引色的 PNG 和 SVG。",
        "description_en": "Export one mandatory composition brief plus numbered, unique-color PNG and SVG visual indexes.",
        "formats": ["png", "svg", "prompt"],
    },
    "weak_ai": {
        "label": "弱 AI 替代",
        "label_en": "Weak-AI fallback",
        "description": "只生成一张带编号唯一索引色的 PNG，以及一份精简纯文本 TXT；适合输入格式挑剔或上下文能力较弱的生图模型。",
        "description_en": "Export only a numbered unique-color PNG and a compact plain-text TXT for image models with limited input support or context.",
        "formats": ["png", "weak_txt"],
    },
    "workflow": {
        "label": "给自动化工作流",
        "label_en": "For automation",
        "description": "生成结构 JSON、SVG 和机器可读空间关系，适合脚本或节点工作流。",
        "description_en": "Export structure JSON, SVG, and machine-readable spatial relationships.",
        "formats": ["json", "svg", "relations"],
    },
    "handoff": {
        "label": "完整交接包",
        "label_en": "Complete handoff",
        "description": "生成全部结构、视觉参考、关系报告和两阶段提示词，适合交接或留档。",
        "description_en": "Export all structure, visual, relationship, and prompt files for handoff or archiving.",
        "formats": ["json", "markdown", "png", "svg", "relations", "prompt"],
    },
    "visual": {
        "label": "只看视觉参考",
        "label_en": "Visual preview only",
        "description": "生成带编号、由程序分配唯一索引色的 PNG 和 SVG 视觉索引。",
        "description_en": "Export numbered, unique-color PNG and SVG visual indexes.",
        "formats": ["png", "svg"],
    },
}


class DrawingCopilotApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"{APP_NAME} {APP_VERSION}")
        self.geometry("1220x760")
        self.minsize(1040, 680)

        self.settings = load_settings()
        self.language = "en" if self.settings.get("language") == "en" else "zh"
        self.project = Project(title=_l(self.language, "我的AI构图", "My AI Composition"), canvas_width=1024, canvas_height=1024)
        self.project_path: Optional[Path] = None
        self.selected_region_id: Optional[str] = None
        self.operation_mode = tk.StringVar(value="new")
        old_edit_mode = str(self.settings.get("edit_mode", "brush"))
        self.edit_mode = tk.StringVar(value="box" if old_edit_mode in {"box", "框选编辑"} else "brush")
        self.draw_tool = tk.StringVar(value="freehand")
        self.edit_mode_display = tk.StringVar(value=self._edit_mode_label(self.edit_mode.get()))
        self.draw_tool_display = tk.StringVar(value=self._draw_tool_label(self.draw_tool.get()))
        self.brush_size = tk.IntVar(value=int(self.settings.get("brush_size", 36) or 36))
        self.show_brush_cursor = tk.BooleanVar(value=bool(self.settings.get("show_brush_cursor", True)))
        self.brush_fill = tk.BooleanVar(value=bool(self.settings.get("brush_fill", False)))
        self.allow_outside_canvas = tk.BooleanVar(value=bool(self.settings.get("allow_outside_canvas", False)))
        self.default_category = tk.StringVar(value=display_label("rough", self.language))
        self.status_text = tk.StringVar(value=_l(self.language, "当前是新建模式：按住拖动画布，自由圈出闭合区域。", "New-region mode: drag on the canvas to create a closed region."))
        self.is_fullscreen = False
        self.zoom = max(0.2, min(4.0, float(self.settings.get("canvas_zoom", 1.0) or 1.0)))
        self.undo_stack: List[Dict[str, Any]] = []
        self.item_to_region: Dict[int, str] = {}
        self.region_to_items: Dict[str, Tuple[int, ...]] = {}
        self.control_actions: Dict[int, str] = {}
        self.tool_buttons: Dict[str, tk.Button] = {}
        self.tool_tooltips: Dict[str, "Tooltip"] = {}
        self.tool_icons: Dict[str, ImageTk.PhotoImage] = {}
        self.background_photo: Optional[ImageTk.PhotoImage] = None
        self.region_overlay_photos: List[ImageTk.PhotoImage] = []
        self.region_overlay_cache: Dict[Any, ImageTk.PhotoImage] = {}
        self.background_item: Optional[int] = None
        self.drag_start: Optional[Tuple[int, int]] = None
        self.drag_points: List[Tuple[int, int]] = []
        self.preview_item: Optional[int] = None
        self.pending_clicked_region: Optional[str] = None
        self.move_region_id: Optional[str] = None
        self.move_last: Optional[Tuple[int, int]] = None
        self.transform_state: Optional[Dict[str, Any]] = None
        self.modify_state: Optional[Dict[str, Any]] = None
        self.brush_cursor_item: Optional[int] = None
        self.tree_drag_region_id: Optional[str] = None
        self.tree_drag_ready = False
        self.tree_drag_moved = False
        self.tree_drag_press_y = 0
        self.middle_pan_start: Optional[Tuple[int, int]] = None
        self.zoom_refresh_after_id: Optional[str] = None
        self.zoom_preview_dirty = False
        self.zoom_preview_active = False
        self.window_restore_after_id: Optional[str] = None
        self.restoring_window_input = False
        self.normal_window_geometry = ""
        self.pre_fullscreen_state = "normal"
        self.fullscreen_transitioning = False
        self.fullscreen_button: Optional[ttk.Button] = None
        self.tree_drop_line: Optional[tk.Frame] = None
        self.tree_float_label: Optional[tk.Label] = None
        self.tree_drag_insert_index: Optional[int] = None

        self._configure_style()
        self._set_window_icon()
        self._build_ui()
        self._bind_keys()
        self.refresh_canvas()
        self.refresh_region_list()
        self.update_idletasks()
        self.normal_window_geometry = self.geometry()
        self.bind("<Configure>", self._track_normal_window_geometry, add="+")

    def _configure_style(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TButton", padding=(10, 5))
        style.configure("Primary.TButton", padding=(12, 6))
        style.configure("Small.TButton", padding=(8, 3))
        style.configure("Header.TLabel", font=("Microsoft YaHei UI", 12, "bold"))
        style.configure("Hint.TLabel", foreground="#5f6673")

    def _set_window_icon(self) -> None:
        candidates = []
        if getattr(sys, "_MEIPASS", None):
            candidates.append(Path(sys._MEIPASS) / "assets" / "app.ico")
        candidates.append(Path(__file__).resolve().parents[1] / "assets" / "app.ico")
        for path in candidates:
            if path.exists():
                try:
                    self.iconbitmap(str(path))
                    return
                except Exception:
                    continue

    def _build_operation_buttons(self, parent: ttk.Frame) -> None:
        self.tool_icons = {}
        for column, (mode, info) in enumerate(OPERATION_MODES.items()):
            button = tk.Button(
                parent,
                image=self._get_tool_icon(mode),
                text=self._operation_button_label(mode),
                compound=tk.TOP,
                font=("Microsoft YaHei UI", 7),
                width=54,
                height=46,
                relief=tk.FLAT,
                bd=1,
                bg="#f4f4f5",
                activebackground="#e5e7eb",
                command=lambda value=mode: self.set_operation_mode(value),
            )
            button.grid(row=0, column=column, padx=(0, 6))
            tooltip = Tooltip(button, f"{self._operation_full_label(mode)}: {self._operation_tip(mode)}")
            self.tool_buttons[mode] = button
            self.tool_tooltips[mode] = tooltip
        self.tool_icons["undo"] = self._create_undo_icon()
        undo_button = tk.Button(
            parent,
            image=self.tool_icons["undo"],
            text=_l(self.language, "撤销", "Undo"),
            compound=tk.TOP,
            font=("Microsoft YaHei UI", 7),
            width=42,
            height=46,
            relief=tk.FLAT,
            bd=1,
            bg="#f4f4f5",
            activebackground="#e5e7eb",
            command=self.undo,
        )
        undo_button.grid(row=0, column=len(OPERATION_MODES), padx=(6, 0))
        Tooltip(undo_button, _l(self.language, "撤销：回到上一步。快捷键 Ctrl+Z。", "Undo the previous step. Shortcut: Ctrl+Z."))
        self.set_operation_mode(self.operation_mode.get())

    def _operation_text(self, mode: str) -> Dict[str, str]:
        if self.edit_mode.get() == "brush" and mode in BRUSH_OPERATION_TEXT:
            info = BRUSH_OPERATION_TEXT[mode]
        elif self.edit_mode.get() == "box" and mode in BOX_OPERATION_TEXT:
            info = BOX_OPERATION_TEXT[mode]
        else:
            info = OPERATION_MODES[mode]
        suffix = "_en" if self.language == "en" else ""
        label = info.get(f"label{suffix}", info["label"])
        short = info.get(f"short{suffix}", label)
        tip = info.get(f"tip{suffix}", info["tip"])
        return {"label": label, "short": short, "tip": tip}

    def _operation_button_label(self, mode: str) -> str:
        return self._operation_text(mode)["short"]

    def _operation_full_label(self, mode: str) -> str:
        return self._operation_text(mode)["label"]

    def _operation_tip(self, mode: str) -> str:
        return self._operation_text(mode)["tip"]

    def _refresh_operation_button_text(self) -> None:
        for mode, button in self.tool_buttons.items():
            button.configure(image=self._get_tool_icon(mode), text=self._operation_button_label(mode))
            tooltip = self.tool_tooltips.get(mode)
            if tooltip:
                tooltip.text = f"{self._operation_full_label(mode)}：{self._operation_tip(mode)}"

    def _tool_variant(self) -> str:
        return "brush" if self.edit_mode.get() == "brush" else "box"

    def _get_tool_icon(self, mode: str) -> ImageTk.PhotoImage:
        key = f"{self._tool_variant()}:{mode}"
        if key not in self.tool_icons:
            self.tool_icons[key] = self._create_tool_icon(mode, self._tool_variant())
        return self.tool_icons[key]

    def _create_tool_icon(self, mode: str, variant: str) -> ImageTk.PhotoImage:
        image = Image.new("RGBA", (112, 112), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        scale = 4
        dark = "#111827"
        muted = "#6b7280"

        def s(value: float) -> int:
            return int(round(value * scale))

        def pts(points: List[Tuple[float, float]]) -> List[Tuple[int, int]]:
            return [(s(x), s(y)) for x, y in points]

        def line(points: List[Tuple[float, float]], fill: str = dark, width: float = 2.0) -> None:
            draw.line(pts(points), fill=fill, width=s(width))

        def rounded(box: Tuple[float, float, float, float], radius: float = 3.0, fill: Optional[str] = None, outline: Optional[str] = None, width: float = 1.5) -> None:
            draw.rounded_rectangle(tuple(s(v) for v in box), radius=s(radius), fill=fill, outline=outline, width=s(width))

        def ellipse(box: Tuple[float, float, float, float], fill: Optional[str] = None, outline: Optional[str] = None, width: float = 1.5) -> None:
            draw.ellipse(tuple(s(v) for v in box), fill=fill, outline=outline, width=s(width))

        def polygon(points: List[Tuple[float, float]], fill: str) -> None:
            draw.polygon(pts(points), fill=fill)

        def circle_symbol(cx: float, cy: float, radius: float = 8.0) -> None:
            ellipse((cx - radius, cy - radius, cx + radius, cy + radius), outline=dark, width=1.8)

        def arrow_head(tip: Tuple[float, float], left: Tuple[float, float], right: Tuple[float, float]) -> None:
            polygon([tip, left, right], dark)

        def brush_stroke() -> None:
            line([(7, 21), (20, 8)], dark, 3.2)
            ellipse((18, 5, 23, 10), fill=dark)
            line([(5, 23), (10, 22)], muted, 1.5)

        def plus_badge(cx: float = 21, cy: float = 20) -> None:
            ellipse((cx - 4.5, cy - 4.5, cx + 4.5, cy + 4.5), fill="#ffffff", outline=dark, width=1.4)
            line([(cx, cy - 2.8), (cx, cy + 2.8)], dark, 1.7)
            line([(cx - 2.8, cy), (cx + 2.8, cy)], dark, 1.7)

        def minus_badge(cx: float = 21, cy: float = 14) -> None:
            ellipse((cx - 4.5, cy - 4.5, cx + 4.5, cy + 4.5), fill="#ffffff", outline=dark, width=1.4)
            line([(cx - 2.8, cy), (cx + 2.8, cy)], dark, 1.9)

        if mode == "new":
            if variant == "brush":
                brush_stroke()
            else:
                circle_symbol(14, 14, 8)
                line([(14, 9), (14, 19)], dark, 2.4)
                line([(9, 14), (19, 14)], dark, 2.4)
        elif mode == "modify":
            if variant == "brush":
                brush_stroke()
                plus_badge()
            else:
                line([(7, 15), (21, 15)], dark, 2.6)
                line([(14, 8), (14, 22)], dark, 2.6)
                line([(19, 8), (23, 8), (23, 12)], muted, 1.7)
        elif mode == "delete":
            if variant == "brush":
                rounded((8, 9, 21, 18), radius=2.4, fill="#ffffff", outline=dark, width=2.0)
                line([(10, 19), (20, 9)], dark, 2.0)
                minus_badge(20, 20)
            else:
                circle_symbol(14, 14, 8)
                line([(9, 14), (19, 14)], dark, 2.8)
        elif mode == "drag":
            ellipse((11.5, 11.5, 16.5, 16.5), fill=dark)
            line([(14, 4), (14, 24)], dark, 1.9)
            line([(4, 14), (24, 14)], dark, 1.9)
            arrow_head((14, 2), (10.5, 8), (17.5, 8))
            arrow_head((14, 26), (10.5, 20), (17.5, 20))
            arrow_head((2, 14), (8, 10.5), (8, 17.5))
            arrow_head((26, 14), (20, 10.5), (20, 17.5))
            draw.arc(tuple(s(v) for v in (7, 5, 23, 21)), 215, 25, fill=muted, width=s(1.3))
            arrow_head((23, 11), (19, 8.5), (19.5, 14))
        elif mode == "transform":
            line([(7, 21), (21, 7)], dark, 2.0)
            arrow_head((5, 23), (7, 16.5), (11.5, 21))
            arrow_head((23, 5), (16.5, 7), (21, 11.5))
            draw.arc(tuple(s(v) for v in (6, 4, 22, 20)), 205, 25, fill=dark, width=s(1.8))
            arrow_head((22, 10), (18, 7.5), (18.5, 13))
        elif mode == "none":
            ellipse((7, 7, 21, 21), outline=muted, width=2.0)
            line([(8, 20), (20, 8)], muted, 2.4)
        resampling = getattr(getattr(Image, "Resampling", Image), "LANCZOS")
        return ImageTk.PhotoImage(image.resize((28, 28), resampling))

    def _create_undo_icon(self) -> ImageTk.PhotoImage:
        image = Image.new("RGBA", (112, 112), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        scale = 4
        dark = "#111827"

        def s(value: float) -> int:
            return int(round(value * scale))

        draw.arc(tuple(s(v) for v in (5, 6, 24, 25)), 105, 330, fill=dark, width=s(2.5))
        draw.polygon([(s(8), s(5.5)), (s(4), s(15)), (s(14), s(13))], fill=dark)
        resampling = getattr(getattr(Image, "Resampling", Image), "LANCZOS")
        return ImageTk.PhotoImage(image.resize((28, 28), resampling))

    def set_operation_mode(self, mode: str) -> None:
        if mode == "transform":
            mode = "drag"
        if mode not in OPERATION_MODES:
            mode = "new"
        self.operation_mode.set(mode)
        if mode not in {"new", "modify", "delete"} and self.brush_cursor_item:
            self.canvas.delete(self.brush_cursor_item)
            self.brush_cursor_item = None
        for name, button in self.tool_buttons.items():
            active = name == mode
            button.configure(relief=tk.SUNKEN if active else tk.FLAT, bg="#e5e7eb" if active else "#f4f4f5")
        self.status_text.set(self._operation_tip(mode))

    def on_edit_mode_changed(self) -> None:
        self.settings["edit_mode"] = self.edit_mode.get()
        save_settings(self.settings)
        self._refresh_operation_button_text()
        self._sync_edit_mode_controls()
        if self.edit_mode.get() == "brush":
            self.status_text.set(_l(self.language, "画图编辑：画笔会直接增减当前选区；可选择是否填充闭合区域。", "Brush editing: paint directly into or out of the selected region; closed strokes may be filled."))
        else:
            self.status_text.set(_l(self.language, "框选编辑：拖出闭合范围来新建、增加或减少选区。", "Selection editing: drag a closed area to create, add, or subtract."))

    def _edit_mode_label(self, value: str) -> str:
        return {
            "brush": _l(self.language, "画图编辑", "Brush editing"),
            "box": _l(self.language, "框选编辑", "Selection editing"),
        }.get(value, value)

    def _draw_tool_label(self, value: str) -> str:
        return {
            "freehand": _l(self.language, "自由闭合区域", "Freeform region"),
            "rectangle": _l(self.language, "矩形区域", "Rectangle"),
        }.get(value, value)

    def _on_edit_mode_display_changed(self) -> None:
        mapping = {self._edit_mode_label("brush"): "brush", self._edit_mode_label("box"): "box"}
        self.edit_mode.set(mapping.get(self.edit_mode_display.get(), "brush"))
        self.on_edit_mode_changed()

    def _on_draw_tool_display_changed(self) -> None:
        mapping = {self._draw_tool_label("freehand"): "freehand", self._draw_tool_label("rectangle"): "rectangle"}
        self.draw_tool.set(mapping.get(self.draw_tool_display.get(), "freehand"))

    def _sync_edit_mode_controls(self) -> None:
        if self.edit_mode.get() == "brush":
            self.shape_label.grid_remove()
            self.tool_box.grid_remove()
            self.brush_fill_label.grid(row=0, column=0, padx=(0, 4), sticky="e")
            self.brush_fill_check.grid(row=0, column=1, padx=(0, 18), sticky="w")
        else:
            self.brush_fill_label.grid_remove()
            self.brush_fill_check.grid_remove()
            self.shape_label.grid(row=0, column=0, padx=(0, 4), sticky="e")
            self.tool_box.grid(row=0, column=1, padx=(0, 18), sticky="w")

    def on_brush_setting_changed(self) -> None:
        self.settings["brush_size"] = self.brush_size.get()
        self.settings["show_brush_cursor"] = self.show_brush_cursor.get()
        self.settings["brush_fill"] = self.brush_fill.get()
        save_settings(self.settings)

    def on_canvas_motion(self, event: tk.Event) -> None:
        if (
            self.edit_mode.get() != "brush"
            or self.operation_mode.get() not in {"new", "modify", "delete"}
            or not self.show_brush_cursor.get()
        ):
            if self.brush_cursor_item:
                self.canvas.delete(self.brush_cursor_item)
                self.brush_cursor_item = None
            return
        x, y = self._canvas_xy(event)
        radius = max(2, self.brush_size.get() // 2)
        coords = (
            self._screen(x - radius),
            self._screen(y - radius),
            self._screen(x + radius),
            self._screen(y + radius),
        )
        if not self.brush_cursor_item:
            self.brush_cursor_item = self.canvas.create_oval(*coords, outline="#111111", dash=(3, 3), width=1)
        else:
            self.canvas.coords(self.brush_cursor_item, *coords)
            self.canvas.tag_raise(self.brush_cursor_item)

    def on_canvas_leave(self, _event: tk.Event) -> None:
        if self.brush_cursor_item:
            self.canvas.delete(self.brush_cursor_item)
            self.brush_cursor_item = None

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        toolbar = ttk.Frame(self, padding=(10, 8))
        toolbar.grid(row=0, column=0, sticky="ew")
        toolbar.columnconfigure(0, weight=1)

        self.toolbar_actions = ttk.Frame(toolbar)
        self.toolbar_actions.grid(row=0, column=0, columnspan=13, sticky="ew")
        action_specs = [
            (_l(self.language, "新建", "New"), self.new_project, None),
            (_l(self.language, "打开", "Open"), self.open_project, None),
            (_l(self.language, "保存", "Save"), self.save_project, None),
            (_l(self.language, "另存为", "Save as"), self.save_project_as, None),
            (_l(self.language, "导入底图", "Import guide"), self.import_background, None),
            (_l(self.language, "导出", "Export"), self.export_outputs, "Primary.TButton"),
            (_l(self.language, "全局要求", "Global prompt"), self.edit_global_prompt, None),
            (_l(self.language, "设置", "Settings"), self.open_settings, None),
            (self._fullscreen_button_text(), self.toggle_fullscreen, None),
            (_l(self.language, "关于", "About"), self.show_about, None),
        ]
        self.toolbar_action_buttons: List[ttk.Button] = []
        for text, command, style in action_specs:
            options: Dict[str, Any] = {"text": text, "command": command}
            if style:
                options["style"] = style
            self.toolbar_action_buttons.append(ttk.Button(self.toolbar_actions, **options))
        self.fullscreen_button = self.toolbar_action_buttons[8]
        self._reflow_toolbar_actions(10)
        self.toolbar_actions.bind("<Configure>", self._on_toolbar_actions_resize)

        operation_row = ttk.Frame(toolbar)
        operation_row.grid(row=1, column=0, columnspan=13, padx=(0, 0), pady=(8, 0), sticky="w")
        ttk.Label(operation_row, text=_l(self.language, "操作", "Mode")).grid(row=0, column=0, padx=(0, 6), sticky="w")
        mode_box = ttk.Combobox(
            operation_row,
            textvariable=self.edit_mode_display,
            values=[self._edit_mode_label("brush"), self._edit_mode_label("box")],
            width=16 if self.language == "en" else 10,
            state="readonly",
        )
        mode_box.grid(row=0, column=1, padx=(0, 8), sticky="w")
        mode_box.bind("<<ComboboxSelected>>", lambda _event: self._on_edit_mode_display_changed())
        operation_frame = ttk.Frame(operation_row)
        operation_frame.grid(row=0, column=2, padx=(0, 12), sticky="w")
        self._build_operation_buttons(operation_frame)
        ttk.Label(operation_row, text=_l(self.language, "笔触", "Brush")).grid(row=0, column=3, padx=(0, 4), sticky="e")
        ttk.Spinbox(operation_row, from_=4, to=200, textvariable=self.brush_size, width=5, command=self.on_brush_setting_changed).grid(row=0, column=4, padx=(0, 4), sticky="w")
        ttk.Checkbutton(operation_row, text=_l(self.language, "显示笔触", "Show cursor"), variable=self.show_brush_cursor, command=self.on_brush_setting_changed).grid(row=0, column=5, padx=(0, 10), sticky="w")
        shape_row = ttk.Frame(toolbar)
        shape_row.grid(row=2, column=0, columnspan=13, padx=(0, 0), pady=(8, 0), sticky="w")
        self.shape_label = ttk.Label(shape_row, text=_l(self.language, "新建形状", "New shape"))
        self.shape_label.grid(row=0, column=0, padx=(0, 4), sticky="e")
        self.tool_box = ttk.Combobox(
            shape_row,
            textvariable=self.draw_tool_display,
            values=[self._draw_tool_label("freehand"), self._draw_tool_label("rectangle")],
            width=16,
            state="readonly",
        )
        self.tool_box.grid(row=0, column=1, padx=(0, 18), sticky="w")
        self.tool_box.bind("<<ComboboxSelected>>", lambda _event: self._on_draw_tool_display_changed())
        self.brush_fill_label = ttk.Label(shape_row, text=_l(self.language, "画笔填充", "Brush fill"))
        self.brush_fill_check = ttk.Checkbutton(shape_row, text=_l(self.language, "填充闭合区域", "Fill closed stroke"), variable=self.brush_fill, command=self.on_brush_setting_changed)
        self.category_label = ttk.Label(shape_row, text=_l(self.language, "新区域分类", "New region type"))
        self.category_label.grid(row=0, column=2, padx=(0, 4), sticky="e")
        labels = [display_label(key, self.language) for key in CONSTRAINT_TYPES]
        category_box = ttk.Combobox(shape_row, textvariable=self.default_category, values=labels, width=16, state="readonly")
        category_box.grid(row=0, column=3, padx=(0, 10), sticky="w")
        self._sync_edit_mode_controls()

        main = ttk.Frame(self)
        main.grid(row=1, column=0, sticky="nsew")
        main.columnconfigure(0, weight=1)
        main.columnconfigure(1, minsize=380)
        main.rowconfigure(0, weight=1)

        canvas_frame = ttk.Frame(main, padding=(10, 0, 6, 8))
        canvas_frame.rowconfigure(0, weight=1)
        canvas_frame.columnconfigure(0, weight=1)
        self.canvas = tk.Canvas(canvas_frame, bg="#f7f8fb", highlightthickness=1, highlightbackground="#cfd4dc", takefocus=True)
        x_scroll = ttk.Scrollbar(canvas_frame, orient=tk.HORIZONTAL, command=self.canvas.xview)
        y_scroll = ttk.Scrollbar(canvas_frame, orient=tk.VERTICAL, command=self.canvas.yview)
        self.canvas.configure(xscrollcommand=x_scroll.set, yscrollcommand=y_scroll.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll.grid(row=1, column=0, sticky="ew")
        canvas_frame.grid(row=0, column=0, sticky="nsew")

        side = ttk.Frame(main, width=380, padding=(8, 0, 10, 8))
        side.grid(row=0, column=1, sticky="nsew")
        side.grid_propagate(False)
        side.columnconfigure(0, weight=1)
        side.rowconfigure(3, weight=1)
        ttk.Label(side, text=_l(self.language, "区域列表", "Regions"), style="Header.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(side, text=_l(self.language, "上方代表更靠前的图层；区域可以互相叠加。单击选择，双击编辑。", "Higher rows are front layers. Regions may overlap. Click to select; double-click to edit."), style="Hint.TLabel", wraplength=340).grid(
            row=1, column=0, sticky="ew", pady=(4, 8)
        )
        self.tree = ttk.Treeview(side, columns=("shape", "category", "bbox"), show="tree headings", height=14, selectmode="browse")
        self.tree.heading("#0", text=_l(self.language, "名称", "Name"))
        self.tree.heading("shape", text=_l(self.language, "形状", "Shape"))
        self.tree.heading("category", text=_l(self.language, "分类", "Type"))
        self.tree.heading("bbox", text=_l(self.language, "范围", "Bounds"))
        self.tree.column("#0", width=92, anchor="w")
        self.tree.column("shape", width=70, anchor="w")
        self.tree.column("category", width=88, anchor="w")
        self.tree.column("bbox", width=112, anchor="w")
        self.tree.grid(row=3, column=0, sticky="nsew")
        tree_scroll = ttk.Scrollbar(side, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=tree_scroll.set)
        tree_scroll.grid(row=3, column=1, sticky="ns")
        self.tree_drop_line = tk.Frame(side, bg="#4aa3ff", height=3)
        self.tree_float_label = tk.Label(side, text="", bg="#e8f2ff", fg="#12385f", bd=1, relief="solid", padx=8, pady=3)

        buttons = ttk.Frame(side)
        buttons.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        for col in range(4):
            buttons.columnconfigure(col, weight=1)
        ttk.Button(buttons, text=_l(self.language, "编辑", "Edit"), style="Small.TButton", command=self.edit_selected_region).grid(row=0, column=0, sticky="ew", padx=(0, 4))
        ttk.Button(buttons, text=_l(self.language, "复制", "Duplicate"), style="Small.TButton", command=self.duplicate_selected_region).grid(row=0, column=1, sticky="ew", padx=4)
        ttk.Button(buttons, text=_l(self.language, "删除", "Delete"), style="Small.TButton", command=self.delete_selected_region).grid(row=0, column=2, columnspan=2, sticky="ew", padx=(4, 0))
        ttk.Button(buttons, text=_l(self.language, "置顶", "To front"), style="Small.TButton", command=self.bring_selected_to_front).grid(row=1, column=0, sticky="ew", padx=(0, 4), pady=(6, 0))
        ttk.Button(buttons, text=_l(self.language, "上移一层", "Move up"), style="Small.TButton", command=lambda: self.move_selected_order(1)).grid(row=1, column=1, sticky="ew", padx=4, pady=(6, 0))
        ttk.Button(buttons, text=_l(self.language, "下移一层", "Move down"), style="Small.TButton", command=lambda: self.move_selected_order(-1)).grid(row=1, column=2, sticky="ew", padx=4, pady=(6, 0))
        ttk.Button(buttons, text=_l(self.language, "置底", "To back"), style="Small.TButton", command=self.send_selected_to_back).grid(row=1, column=3, sticky="ew", padx=(4, 0), pady=(6, 0))

        ttk.Label(side, text=_l(self.language, "当前选区", "Selection"), style="Header.TLabel").grid(row=5, column=0, sticky="w", pady=(14, 4))
        self.summary = tk.Text(side, height=9, wrap="word", bg="#ffffff", relief="solid", borderwidth=1)
        self.summary.grid(row=6, column=0, columnspan=2, sticky="ew")
        self.summary.configure(state="disabled")
        ttk.Label(side, text=_l(self.language, "提示：选中区域后可用方向键微调，按住 Shift 每次移动 10 像素。自由区域会整体移动。", "Tip: use arrow keys to nudge a selected region; hold Shift to move 10 pixels."), style="Hint.TLabel", wraplength=340).grid(
            row=7, column=0, columnspan=2, sticky="ew", pady=(8, 0)
        )

        status_bar = ttk.Frame(self)
        status_bar.grid(row=2, column=0, sticky="ew")
        status_bar.columnconfigure(1, weight=1)
        zoom_controls = ttk.Frame(status_bar)
        zoom_controls.grid(row=0, column=0, sticky="w", padx=(8, 8), pady=3)
        ttk.Label(zoom_controls, text=_l(self.language, "画布缩放", "Zoom")).grid(row=0, column=0, padx=(0, 4))
        ttk.Button(zoom_controls, text="-", width=3, command=lambda: self.zoom_canvas_by(1 / 1.12)).grid(row=0, column=1, padx=(0, 2))
        ttk.Button(zoom_controls, text="+", width=3, command=lambda: self.zoom_canvas_by(1.12)).grid(row=0, column=2)
        status = ttk.Label(status_bar, textvariable=self.status_text, anchor="w", padding=(4, 4))
        status.grid(row=0, column=1, sticky="ew")

        self.canvas.bind("<ButtonPress-1>", self.on_canvas_press)
        self.canvas.bind("<B1-Motion>", self.on_canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_canvas_release)
        self.canvas.bind("<Double-Button-1>", self.on_canvas_double_click)
        self.canvas.bind("<MouseWheel>", self.on_mouse_wheel)
        self.canvas.bind("<Shift-MouseWheel>", self.on_shift_mouse_wheel)
        self.canvas.bind("<Alt-MouseWheel>", self.on_alt_mouse_wheel)
        self.canvas.bind("<ButtonPress-2>", self.on_middle_press)
        self.canvas.bind("<Alt-ButtonPress-2>", self.on_middle_press)
        self.canvas.bind("<B2-Motion>", self.on_middle_drag)
        self.canvas.bind("<Alt-B2-Motion>", self.on_middle_drag)
        self.canvas.bind("<ButtonRelease-2>", self.on_middle_release)
        self.canvas.bind("<Alt-ButtonRelease-2>", self.on_middle_release)
        self.canvas.bind("<Motion>", self.on_canvas_motion)
        self.canvas.bind("<Leave>", self.on_canvas_leave)
        self.bind_all("<MouseWheel>", self.on_global_mouse_wheel, add="+")
        self.bind_all("<Shift-MouseWheel>", self.on_global_mouse_wheel, add="+")
        self.bind_all("<Alt-MouseWheel>", self.on_global_mouse_wheel, add="+")
        self.bind_all("<ButtonPress-2>", self.on_global_middle_press, add="+")
        self.bind_all("<B2-Motion>", self.on_global_middle_drag, add="+")
        self.bind_all("<ButtonRelease-2>", self.on_global_middle_release, add="+")
        self.bind_all("<KeyRelease-Alt_L>", self.on_alt_key_release, add="+")
        self.bind_all("<KeyRelease-Alt_R>", self.on_alt_key_release, add="+")
        self.tree.bind("<<TreeviewSelect>>", self.on_tree_select)
        self.tree.bind("<Double-Button-1>", self.on_tree_double_click)
        self.tree.bind("<ButtonPress-1>", self.on_tree_button_press)
        self.tree.bind("<B1-Motion>", self.on_tree_drag_motion)
        self.tree.bind("<ButtonRelease-1>", self.on_tree_button_release)

    def _reflow_toolbar_actions(self, columns: int) -> None:
        columns = max(3, min(len(self.toolbar_action_buttons), columns))
        if (
            getattr(self, "_toolbar_action_columns", None) == columns
            and all(button.winfo_manager() == "grid" for button in self.toolbar_action_buttons)
        ):
            return
        self._toolbar_action_columns = columns
        for index, button in enumerate(self.toolbar_action_buttons):
            button.grid_forget()
            button.grid(
                row=index // columns,
                column=index % columns,
                sticky="ew",
                padx=(0 if index % columns == 0 else 6, 6),
                pady=(0, 5),
            )
        for column in range(len(self.toolbar_action_buttons)):
            self.toolbar_actions.columnconfigure(column, weight=1 if column < columns else 0)

    def _on_toolbar_actions_resize(self, event: tk.Event) -> None:
        if not self.toolbar_action_buttons:
            return
        widest = max(button.winfo_reqwidth() for button in self.toolbar_action_buttons) + 12
        if event.width >= widest * 10:
            columns = 10
        elif event.width >= widest * 5:
            columns = 5
        elif event.width >= widest * 4:
            columns = 4
        else:
            columns = 3
        self._reflow_toolbar_actions(columns)

    def _fullscreen_button_text(self) -> str:
        return _l(self.language, "窗口" if self.is_fullscreen else "全屏", "Window" if self.is_fullscreen else "Fullscreen")

    def _update_fullscreen_button(self) -> None:
        if self.fullscreen_button and self.fullscreen_button.winfo_exists():
            self.fullscreen_button.configure(text=self._fullscreen_button_text())

    def _track_normal_window_geometry(self, event: tk.Event) -> None:
        if event.widget is not self or self.is_fullscreen or self.fullscreen_transitioning:
            return
        try:
            if self.state() == "normal":
                self.normal_window_geometry = self.geometry()
        except tk.TclError:
            pass

    def _bind_keys(self) -> None:
        self.bind("<Control-n>", lambda _event: self.new_project())
        self.bind("<Control-o>", lambda _event: self.open_project())
        self.bind("<Control-s>", lambda _event: self.save_project())
        self.bind("<Control-z>", lambda _event: self.undo())
        self.bind("<Delete>", lambda _event: self.delete_selected_region())
        self.bind("<F11>", lambda _event: self.toggle_fullscreen())
        self.bind("<KeyPress>", self.on_key_press)
        for key, dx, dy in (("Left", -1, 0), ("Right", 1, 0), ("Up", 0, -1), ("Down", 0, 1)):
            self.bind(f"<{key}>", lambda event, x=dx, y=dy: self.nudge_selected(x, y, event))

    def on_key_press(self, event: tk.Event) -> Optional[str]:
        if event.keysym == "F11":
            self.toggle_fullscreen()
            return "break"
        if event.keysym == "Escape" and self.is_fullscreen:
            self.toggle_fullscreen(False)
            return "break"
        widget_class = event.widget.winfo_class()
        if widget_class in {"Entry", "Text", "TEntry", "TCombobox", "TSpinbox", "Spinbox"}:
            return None
        defaults = {"new": "n", "modify": "m", "delete": "d", "drag": "v", "transform": "t", "none": "Escape"}
        key = event.keysym if event.keysym == "Escape" else event.char.lower()
        for mode, default in defaults.items():
            shortcut = str(self.settings.get(f"shortcut_{mode}", default))
            compare = shortcut if shortcut == "Escape" else shortcut.lower()
            if key == compare:
                self.set_operation_mode(mode)
                return "break"
        return None

    def push_undo(self) -> None:
        self.undo_stack.append(self.project.to_dict())
        if len(self.undo_stack) > 50:
            self.undo_stack.pop(0)

    def undo(self) -> None:
        if not self.undo_stack:
            self.status_text.set(_l(self.language, "没有可以撤销的步骤。", "There is nothing to undo."))
            return
        self.project = Project.from_dict(self.undo_stack.pop())
        self.selected_region_id = None
        self.refresh_canvas()
        self.refresh_region_list()
        self.status_text.set(_l(self.language, "已撤销上一步。", "Undid the previous step."))

    def new_project(self) -> None:
        dialog = ProjectDialog(self, self.project, self.language)
        if not dialog.result:
            return
        self.push_undo()
        self.project = dialog.result
        self.project_path = None
        self.selected_region_id = None
        self.refresh_canvas()
        self.refresh_region_list()
        self.status_text.set(_l(self.language, "已创建新画布。拖动画布创建第一个区域。", "Created a new canvas. Drag to create the first region."))

    def open_project(self) -> None:
        start_dir = self.settings.get("last_project_dir") or self.settings.get("default_project_dir") or str(Path.home())
        path = filedialog.askopenfilename(
            title=_l(self.language, "打开构图项目", "Open composition project"),
            initialdir=start_dir,
            filetypes=[(_l(self.language, "AI构图项目", "AI composition project"), "*.aicopilot.json *.json"), (_l(self.language, "所有文件", "All files"), "*.*")],
        )
        if not path:
            return
        try:
            self.project = load_project(Path(path))
        except Exception as exc:
            messagebox.showerror(_l(self.language, "打开失败", "Open failed"), _l(self.language, f"无法读取这个项目文件：\n{exc}", f"Could not read this project file:\n{exc}"), parent=self)
            return
        self.project_path = Path(path)
        self.settings["last_project_dir"] = str(self.project_path.parent)
        save_settings(self.settings)
        self.selected_region_id = None
        self.refresh_canvas()
        self.refresh_region_list()
        self.status_text.set(_l(self.language, f"已打开：{self.project_path.name}", f"Opened: {self.project_path.name}"))

    def save_project(self) -> None:
        if self.project_path is None:
            self.save_project_as()
            return
        try:
            save_project(self.project, self.project_path)
        except Exception as exc:
            messagebox.showerror(_l(self.language, "保存失败", "Save failed"), _l(self.language, f"无法保存项目：\n{exc}", f"Could not save the project:\n{exc}"), parent=self)
            return
        self.status_text.set(_l(self.language, f"已保存：{self.project_path}", f"Saved: {self.project_path}"))

    def save_project_as(self) -> None:
        start_dir = self.settings.get("last_project_dir") or self.settings.get("default_project_dir") or str(Path.home())
        path = filedialog.asksaveasfilename(
            title=_l(self.language, "保存构图项目", "Save composition project"),
            initialdir=start_dir,
            initialfile=f"{self.project.title}.aicopilot.json",
            defaultextension=".aicopilot.json",
            filetypes=[(_l(self.language, "AI构图项目", "AI composition project"), "*.aicopilot.json"), ("JSON", "*.json")],
        )
        if not path:
            return
        self.project_path = Path(path)
        self.settings["last_project_dir"] = str(self.project_path.parent)
        save_settings(self.settings)
        self.save_project()

    def import_background(self) -> None:
        path = filedialog.askopenfilename(
            title=_l(self.language, "导入底图", "Import guide image"),
            filetypes=[(_l(self.language, "图片文件", "Image files"), "*.png *.jpg *.jpeg *.webp *.bmp"), (_l(self.language, "所有文件", "All files"), "*.*")],
        )
        if not path:
            return
        try:
            image = Image.open(path)
        except Exception as exc:
            messagebox.showerror(_l(self.language, "导入失败", "Import failed"), _l(self.language, f"无法读取这张图片：\n{exc}", f"Could not read this image:\n{exc}"), parent=self)
            return
        self.push_undo()
        if messagebox.askyesno(_l(self.language, "使用图片尺寸？", "Use image size?"), _l(self.language, f"是否把画布改成这张图片的尺寸？\n{image.width} x {image.height} px", f"Resize the canvas to this image?\n{image.width} x {image.height} px"), parent=self):
            self.project.canvas_width = image.width
            self.project.canvas_height = image.height
        self.project.background_path = path
        self.project.touch()
        self.refresh_canvas()
        self.status_text.set(_l(self.language, "已导入底图。导出 PNG 时会叠加区域标注。", "Guide image imported. Region overlays will appear in the exported PNG."))

    def edit_global_prompt(self) -> None:
        dialog = GlobalPromptDialog(self, self.project, self.language)
        if dialog.saved:
            self.project.touch()
            self.status_text.set(_l(self.language, "已更新全局画面要求。", "Updated global image requirements."))

    def open_settings(self) -> None:
        dialog = SettingsDialog(self, self.settings, self.language)
        if dialog.saved:
            previous_language = self.language
            category_key = category_from_label(self.default_category.get())
            self.settings.update(dialog.result)
            self.language = "en" if self.settings.get("language") == "en" else "zh"
            self.allow_outside_canvas.set(bool(self.settings.get("allow_outside_canvas", False)))
            save_settings(self.settings)
            if self.language != previous_language:
                self.default_category.set(display_label(category_key, self.language))
                self.edit_mode_display.set(self._edit_mode_label(self.edit_mode.get()))
                self.draw_tool_display.set(self._draw_tool_label(self.draw_tool.get()))
                self._rebuild_localized_ui()
            self.status_text.set(_l(self.language, "设置已保存。新的画布操作、语言和默认路径已生效。", "Settings saved. Canvas controls, language, and default paths are now active."))

    def _rebuild_localized_ui(self) -> None:
        for child in self.winfo_children():
            child.destroy()
        self.tool_buttons.clear()
        self.tool_tooltips.clear()
        self.tool_icons.clear()
        self._toolbar_action_columns = None
        self.fullscreen_button = None
        self.item_to_region.clear()
        self.region_to_items.clear()
        self.control_actions.clear()
        self.background_photo = None
        self.region_overlay_photos.clear()
        self.region_overlay_cache.clear()
        self.title(f"{APP_NAME} {APP_VERSION}")
        self._build_ui()
        self.refresh_canvas()
        self.refresh_region_list()

    def export_outputs(self) -> None:
        if not self.project.regions:
            if not messagebox.askyesno(_l(self.language, "还没有区域", "No regions yet"), _l(self.language, "当前还没有划分区域，仍然导出空模板吗？", "There are no regions. Export an empty template anyway?"), parent=self):
                return
        dialog = ExportDialog(self, self.language)
        if not dialog.formats:
            return
        start_dir = self.settings.get("last_export_dir") or self.settings.get("default_export_dir") or str(Path.home())
        directory = filedialog.askdirectory(title=_l(self.language, "选择导出文件夹", "Choose export folder"), initialdir=start_dir)
        if not directory:
            return
        try:
            paths = export_selected(
                self.project,
                Path(directory),
                dialog.formats,
                self.language,
                dialog.generation_mode,
                dialog.weak_txt_mode,
            )
        except Exception as exc:
            messagebox.showerror(_l(self.language, "导出失败", "Export failed"), _l(self.language, f"导出文件时出错：\n{exc}", f"An error occurred while exporting:\n{exc}"), parent=self)
            return
        self.settings["last_export_dir"] = directory
        save_settings(self.settings)
        message = "\n".join(f"{name}: {path}" for name, path in paths.items())
        messagebox.showinfo(_l(self.language, "导出完成", "Export complete"), _l(self.language, f"已生成这些文件：\n\n{message}", f"Generated these files:\n\n{message}"), parent=self)
        self.status_text.set(_l(self.language, f"已导出 {len(paths)} 个 AI 可读文件。", f"Exported {len(paths)} AI-readable files."))

    def refresh_canvas(self) -> None:
        if self.zoom_refresh_after_id:
            self.after_cancel(self.zoom_refresh_after_id)
            self.zoom_refresh_after_id = None
        self.zoom_preview_dirty = False
        self.canvas.delete("all")
        self.item_to_region.clear()
        self.region_to_items.clear()
        self.control_actions.clear()
        self.region_overlay_photos.clear()
        self.zoom_preview_active = False
        self.background_item = None
        self.background_photo = None
        self.brush_cursor_item = None
        self._update_canvas_scrollregion()
        self._draw_background()
        self._draw_canvas_grid()
        for region in self.project.regions:
            self._draw_region(region)
        self._draw_selected_controls()
        self._update_summary()

    def _update_canvas_scrollregion(self) -> None:
        margin = self._canvas_margin()
        self.canvas.configure(
            scrollregion=(
                -margin,
                -margin,
                self._screen(self.project.canvas_width) + margin,
                self._screen(self.project.canvas_height) + margin,
            )
        )

    def _redraw_region_live(self, region_id: str) -> None:
        self._redraw_region_items(region_id, live=True, preserve_order=False)

    def _redraw_region_final(self, region_id: str) -> None:
        self._redraw_region_items(region_id, live=False, preserve_order=True)

    def _redraw_region_items(self, region_id: str, live: bool, preserve_order: bool) -> None:
        for item in self.region_to_items.pop(region_id, ()):
            self.canvas.delete(item)
            self.item_to_region.pop(item, None)
        self.canvas.delete("selection_control")
        self.control_actions.clear()
        region = self.project.get_region(region_id)
        if region:
            self._draw_region(region, live=live)
            if preserve_order:
                self._sync_region_z_order()
        self._draw_selected_controls()

    def _sync_region_z_order(self) -> None:
        for region in self.project.regions:
            for item in self.region_to_items.get(region.region_id, ()):
                self.canvas.tag_raise(item)
        self.canvas.tag_raise("selection_control")
        if self.brush_cursor_item:
            self.canvas.tag_raise(self.brush_cursor_item)

    def _draw_background(self) -> None:
        if not self.project.background_path:
            self.canvas.create_rectangle(0, 0, self._screen(self.project.canvas_width), self._screen(self.project.canvas_height), fill="#ffffff", outline="#d9dde5")
            return
        bg_path = Path(self.project.background_path)
        if not bg_path.exists():
            self.canvas.create_rectangle(0, 0, self._screen(self.project.canvas_width), self._screen(self.project.canvas_height), fill="#fff7e6", outline="#d9dde5")
            self.canvas.create_text(20, 20, text=_l(self.language, "底图文件找不到，将只显示空白画布", "Guide image not found; showing a blank canvas."), anchor="nw", fill="#8a5a00")
            return
        try:
            image = Image.open(bg_path).convert("RGB").resize((self._screen(self.project.canvas_width), self._screen(self.project.canvas_height)), Image.Resampling.LANCZOS)
            self.background_photo = ImageTk.PhotoImage(image)
            self.background_item = self.canvas.create_image(0, 0, image=self.background_photo, anchor="nw")
        except Exception:
            self.canvas.create_rectangle(0, 0, self._screen(self.project.canvas_width), self._screen(self.project.canvas_height), fill="#ffffff", outline="#d9dde5")

    def _draw_canvas_grid(self) -> None:
        step = 100
        for x in range(0, self.project.canvas_width + 1, step):
            sx = self._screen(x)
            self.canvas.create_line(sx, 0, sx, self._screen(self.project.canvas_height), fill="#edf0f5")
            self.canvas.create_text(sx + 4, 4, text=str(x), anchor="nw", fill="#a3aab7", font=("Arial", 8))
        for y in range(0, self.project.canvas_height + 1, step):
            sy = self._screen(y)
            self.canvas.create_line(0, sy, self._screen(self.project.canvas_width), sy, fill="#edf0f5")
            self.canvas.create_text(4, sy + 4, text=str(y), anchor="nw", fill="#a3aab7", font=("Arial", 8))

    def _draw_region(self, region: Region, live: bool = False) -> None:
        region.normalize()
        outline_width = 4 if region.region_id == self.selected_region_id else 2
        shape_items: List[int] = []
        if region.shape == "polygon":
            for part in region.pixel_parts():
                holes = part.get("holes", [])
                points = part["points"]
                if live:
                    closed = points + [points[0]] if points else []
                    if len(closed) >= 4:
                        shape_items.append(
                            self.canvas.create_line(
                                self._flat_screen_points(closed),
                                fill=region.color,
                                width=outline_width,
                                tags=("region", region.region_id),
                            )
                        )
                    for hole in holes:
                        closed_hole = hole + [hole[0]] if hole else []
                        if len(closed_hole) >= 4:
                            shape_items.append(
                                self.canvas.create_line(
                                    self._flat_screen_points(closed_hole),
                                    fill=region.color,
                                    width=max(1, outline_width - 1),
                                    tags=("region", region.region_id),
                                )
                            )
                elif holes:
                    shape_items.extend(self._draw_polygon_region_with_holes(region, points, holes, outline_width))
                else:
                    shape_items.append(
                        self.canvas.create_polygon(
                            self._flat_screen_points(points),
                            outline=region.color,
                            width=outline_width,
                            fill=region.color,
                            stipple="gray25",
                            tags=("region", region.region_id),
                        )
                    )
        else:
            shape_items.append(
                self.canvas.create_rectangle(
                    self._screen(region.x),
                    self._screen(region.y),
                    self._screen(region.x + region.width),
                    self._screen(region.y + region.height),
                    outline=region.color,
                    width=outline_width,
                    fill="" if live else region.color,
                    stipple="" if live else "gray25",
                    tags=("region", region.region_id),
                )
            )
        label = self.canvas.create_text(
            self._screen(region.x) + 6,
            self._screen(region.y) + 6,
                text=f"{region.name}\n{display_label(region.category, self.language)}",
            anchor="nw",
            fill="#111111",
            font=("Microsoft YaHei UI", 10, "bold"),
            tags=("region", region.region_id),
        )
        for shape_item in shape_items:
            self.item_to_region[shape_item] = region.region_id
        self.item_to_region[label] = region.region_id
        self.region_to_items[region.region_id] = tuple([*shape_items, label])

    def _draw_polygon_region_with_holes(self, region: Region, points: List[List[int]], holes: List[List[List[int]]], outline_width: int) -> List[int]:
        points = [(x, y) for x, y in points]
        holes = [[(x, y) for x, y in hole] for hole in holes]
        if len(points) < 3:
            return []
        pad = max(4, outline_width + 3)
        xs = [point[0] for point in points]
        ys = [point[1] for point in points]
        left = self._screen(min(xs)) - pad
        top = self._screen(min(ys)) - pad
        right = self._screen(max(xs)) + pad
        bottom = self._screen(max(ys)) + pad
        width = max(1, right - left + 1)
        height = max(1, bottom - top + 1)

        def local(point: Tuple[int, int]) -> Tuple[int, int]:
            return self._screen(point[0]) - left, self._screen(point[1]) - top

        cache_key = (
            round(self.zoom, 4),
            region.color,
            outline_width,
            tuple(points),
            tuple(tuple(hole) for hole in holes),
        )
        photo = self.region_overlay_cache.get(cache_key)
        if photo is None:
            mask = Image.new("L", (width, height), 0)
            mask_draw = ImageDraw.Draw(mask)
            mask_draw.polygon([local(point) for point in points], fill=255)
            for hole in holes:
                if len(hole) >= 3:
                    mask_draw.polygon([local(point) for point in hole], fill=0)

            tile = Image.new("L", (4, 4), 0)
            tile.putpixel((0, 0), 96)
            tile.putpixel((2, 2), 96)
            pattern = Image.new("L", (width, height), 0)
            for y in range(0, height, 4):
                for x in range(0, width, 4):
                    pattern.paste(tile, (x, y))
            alpha = ImageChops.multiply(mask, pattern)
            fill = Image.new("RGBA", (width, height), (*self._color_rgb(region.color), 0))
            fill.putalpha(alpha)
            photo = ImageTk.PhotoImage(fill)
            if len(self.region_overlay_cache) > 80:
                self.region_overlay_cache.clear()
            self.region_overlay_cache[cache_key] = photo

        preview_items = self._draw_compound_zoom_preview(region, points, holes)
        overlay_item = self.canvas.create_image(
            left,
            top,
            image=photo,
            anchor="nw",
            state="hidden" if self.zoom_preview_active else "normal",
            tags=("region", region.region_id, "region_overlay"),
        )
        self.region_overlay_photos.append(photo)
        items: List[int] = [*preview_items, overlay_item]
        outer = points + [points[0]]
        items.append(
            self.canvas.create_line(
                self._flat_screen_points(outer),
                fill=region.color,
                width=outline_width,
                tags=("region", region.region_id),
            )
        )
        hole_width = max(1, outline_width - 1)
        for hole in holes:
            if len(hole) >= 3:
                closed_hole = hole + [hole[0]]
                items.append(
                    self.canvas.create_line(
                        self._flat_screen_points(closed_hole),
                        fill=region.color,
                        width=hole_width,
                        tags=("region", region.region_id),
                    )
                )
        return items

    def _draw_compound_zoom_preview(
        self,
        region: Region,
        points: List[Tuple[int, int]],
        holes: List[List[Tuple[int, int]]],
    ) -> List[int]:
        """Create lightweight native polygons that preserve holes during live zoom."""
        try:
            geometry: BaseGeometry = Polygon(points, holes=holes or None)
            if not geometry.is_valid:
                geometry = geometry.buffer(0)
        except Exception:
            return []
        preview_items: List[int] = []
        for polygon in self._extract_polygons(geometry):
            for triangle in triangulate(polygon):
                clipped = triangle.intersection(polygon)
                for piece in self._extract_polygons(clipped):
                    if piece.area < 0.5:
                        continue
                    piece_points = list(piece.exterior.coords)[:-1]
                    if len(piece_points) < 3:
                        continue
                    preview_items.append(
                        self.canvas.create_polygon(
                            self._flat_screen_points(piece_points),
                            outline="",
                            fill=region.color,
                            stipple="gray25",
                            state="normal" if self.zoom_preview_active else "hidden",
                            tags=("region", region.region_id, "region_zoom_preview"),
                        )
                    )
        return preview_items

    def _begin_zoom_preview(self) -> None:
        if self.zoom_preview_active:
            return
        self.zoom_preview_active = True
        self.canvas.itemconfigure("region_overlay", state="hidden")
        self.canvas.itemconfigure("region_zoom_preview", state="normal")

    def _draw_selected_controls(self) -> None:
        if self.operation_mode.get() not in {"drag", "transform"}:
            return
        region = self.project.get_region(self.selected_region_id)
        if not region:
            return
        region.normalize()
        pad = self._screen(10)
        left = self._screen(region.x) - pad
        top = self._screen(region.y) - pad
        right = self._screen(region.x + region.width) + pad
        bottom = self._screen(region.y + region.height) + pad
        self.canvas.create_rectangle(left, top, right, bottom, outline="#2563eb", dash=(5, 3), width=2, tags=("selection_control",))
        handle = 5
        handles = {
            "corner_nw": (left, top),
            "corner_ne": (right, top),
            "corner_sw": (left, bottom),
            "corner_se": (right, bottom),
            "edge_n": ((left + right) // 2, top),
            "edge_s": ((left + right) // 2, bottom),
            "edge_w": (left, (top + bottom) // 2),
            "edge_e": (right, (top + bottom) // 2),
        }
        for action, (x, y) in handles.items():
            item = self.canvas.create_rectangle(x - handle, y - handle, x + handle, y + handle, fill="#ffffff", outline="#2563eb", width=2, tags=("selection_control",))
            self.control_actions[item] = action
        rotate_y = top - self._screen(24)
        rotate_x = (left + right) // 2
        self.canvas.create_line(rotate_x, top, rotate_x, rotate_y + handle, fill="#2563eb", dash=(3, 3), tags=("selection_control",))
        rotate = self.canvas.create_oval(rotate_x - handle, rotate_y - handle, rotate_x + handle, rotate_y + handle, fill="#ffffff", outline="#2563eb", width=2, tags=("selection_control",))
        self.control_actions[rotate] = "rotate"
        self.canvas.create_arc(rotate_x - 14, rotate_y - 14, rotate_x + 14, rotate_y + 14, start=35, extent=270, outline="#2563eb", style=tk.ARC, width=1, tags=("selection_control",))

    def refresh_region_list(self) -> None:
        for item in self.tree.get_children():
            self.tree.delete(item)
        for region in reversed(self.project.regions):
            bbox = f"{region.x},{region.y},{region.width},{region.height}"
            shape_label = _l(self.language, "自由", "Freeform") if region.shape == "polygon" else _l(self.language, "矩形", "Rectangle")
            self.tree.insert("", "end", iid=region.region_id, text=region.name, values=(shape_label, display_label(region.category, self.language), bbox))
        if self.selected_region_id and self.tree.exists(self.selected_region_id):
            self.tree.selection_set(self.selected_region_id)
        self._update_summary()

    def on_canvas_press(self, event: tk.Event) -> None:
        x, y = self._canvas_xy(event)
        current = self.canvas.find_withtag("current")
        clicked_region = self._region_at_point(x, y, current)
        self.pending_clicked_region = clicked_region
        mode = self.operation_mode.get()
        if mode == "none":
            if clicked_region:
                self.select_region(clicked_region)
            else:
                self.select_region(None)
            return
        if self.edit_mode.get() == "brush" and mode in {"new", "modify", "delete"}:
            if mode == "delete" and not self.selected_region_id:
                self.status_text.set(_l(self.language, "画笔减少需要先在列表中选中一个区域。", "Select a region before erasing from it."))
                return
            self.push_undo()
            self._start_brush_stroke(x, y, mode)
            return
        if mode in {"drag", "transform"}:
            action = self._control_action_from_items(current)
            region = self.project.get_region(self.selected_region_id)
            if action and region:
                self.push_undo()
                self._start_transform(region, x, y, action)
                return
            if clicked_region:
                self.select_region(clicked_region)
                self.push_undo()
                self.move_region_id = clicked_region
                self.move_last = (x, y)
            else:
                self.select_region(None)
            return
        if mode in {"modify", "delete"}:
            region_id = clicked_region or self.selected_region_id
            region = self.project.get_region(region_id)
            if region:
                self.select_region(region.region_id)
                self.push_undo()
                self._start_modify(region, x, y, mode)
            else:
                self.status_text.set(_l(self.language, "增加/减少选定区域需要先点中一个区域。", "Select a region before adding to or subtracting from it."))
            return
        if clicked_region and mode != "new":
            self.select_region(clicked_region)
            self.drag_start = None
            return
        self.drag_start = (x, y)
        self.drag_points = [(x, y)]
        if self.draw_tool.get() == "rectangle":
            sx, sy = self._screen_point((x, y))
            self.preview_item = self.canvas.create_rectangle(sx, sy, sx, sy, outline="#222222", dash=(4, 3), width=2)
        else:
            sx, sy = self._screen_point((x, y))
            self.preview_item = self.canvas.create_line(sx, sy, sx, sy, fill="#222222", dash=(4, 3), width=2, smooth=True)

    def on_canvas_drag(self, event: tk.Event) -> None:
        x, y = self._canvas_xy(event)
        if self.move_region_id and self.move_last:
            region = self.project.get_region(self.move_region_id)
            if region:
                last_x, last_y = self.move_last
                region.move_by(x - last_x, y - last_y, self.project.canvas_width, self.project.canvas_height)
                self.move_last = (x, y)
                self._redraw_region_live(region.region_id)
            return
        if self.transform_state:
            self._update_transform(x, y)
            return
        if self.modify_state:
            self._append_modify_point(x, y)
            return
        if not self.drag_start or not self.preview_item:
            return
        if self.draw_tool.get() == "rectangle":
            x0, y0 = self.drag_start
            self.canvas.coords(self.preview_item, self._screen(x0), self._screen(y0), self._screen(x), self._screen(y))
            return
        self._append_drag_point(x, y)
        self.canvas.coords(self.preview_item, self._flat_screen_points(self.drag_points))

    def on_canvas_release(self, event: tk.Event) -> None:
        if self.move_region_id:
            self.move_region_id = None
            self.move_last = None
            self.project.touch()
            self.refresh_canvas()
            self.refresh_region_list()
            self.status_text.set(_l(self.language, "区域位置已调整。", "Region position adjusted."))
            return
        if self.transform_state:
            self.transform_state = None
            self.project.touch()
            self.refresh_canvas()
            self.refresh_region_list()
            self.status_text.set(_l(self.language, "区域调整已应用。", "Region transform applied."))
            return
        if self.modify_state:
            self._finish_modify()
            return
        if not self.drag_start:
            return
        x1, y1 = self.drag_start
        x2, y2 = self._canvas_xy(event)
        if self.draw_tool.get() != "rectangle":
            self._append_drag_point(x2, y2, force=True)
        if self.preview_item:
            self.canvas.delete(self.preview_item)
        self.preview_item = None
        self.drag_start = None
        region = self._region_from_drag(x1, y1, x2, y2)
        self.drag_points = []
        if not region:
            if self.pending_clicked_region:
                self.select_region(self.pending_clicked_region)
                self.status_text.set(_l(self.language, "已选择区域。要叠加新区域，请从这里按住拖动。", "Region selected. Drag from here to create an overlapping region."))
            else:
                self.select_region(None)
                self.status_text.set(_l(self.language, "区域太小或点数太少，没有创建。请拖出一个闭合区域。", "The region was too small or had too few points. Drag a closed region."))
            self.pending_clicked_region = None
            return
        self.pending_clicked_region = None
        self.push_undo()
        self.project.add_region(region)
        self.selected_region_id = region.region_id
        self.refresh_canvas()
        self.refresh_region_list()
        if self.edit_mode.get() == "brush":
            self.set_operation_mode("modify")
            self.status_text.set(_l(self.language, "已创建区域，并已自动切换到增加。", "Region created; switched to Add mode."))
            return
        self.status_text.set(_l(self.language, "已创建区域。双击它可以填写详细说明，右侧可调整图层顺序。", "Region created. Double-click it to add details; use the right panel to change layer order."))

    def _start_transform(self, region: Region, x: int, y: int, action: str) -> None:
        region.shape = "polygon"
        region.points = region.pixel_points()
        region.normalize()
        center = (region.x + region.width / 2, region.y + region.height / 2)
        start_angle = math.atan2(y - center[1], x - center[0])
        start_distance = max(8.0, math.hypot(x - center[0], y - center[1]))
        self.transform_state = {
            "region_id": region.region_id,
            "center": center,
            "start_angle": start_angle,
            "start_distance": start_distance,
            "points": region.pixel_points(),
            "holes": region.pixel_holes(),
            "parts": region.pixel_parts()[1:],
            "bbox": (region.x, region.y, region.width, region.height),
            "action": action,
        }
        self.status_text.set(_l(self.language, "旋转缩放：边只改单轴，角点等比缩放，顶部圆点只旋转。", "Transform: edge handles resize one axis, corners scale proportionally, and the top circle rotates."))

    def _update_transform(self, x: int, y: int) -> None:
        state = self.transform_state
        if not state:
            return
        region = self.project.get_region(state["region_id"])
        if not region:
            return
        center_x, center_y = state["center"]
        action = state.get("action")
        if action and action != "rotate":
            self._update_resize_transform(region, x, y, action, state)
            return
        angle = math.atan2(y - center_y, x - center_x)
        angle_delta = angle - state["start_angle"]
        cos_a = math.cos(angle_delta)
        sin_a = math.sin(angle_delta)
        def rotate_point(point_x: int, point_y: int) -> List[int]:
            rel_x = point_x - center_x
            rel_y = point_y - center_y
            new_x = center_x + rel_x * cos_a - rel_y * sin_a
            new_y = center_y + rel_x * sin_a + rel_y * cos_a
            return [int(round(new_x)), int(round(new_y))]

        new_points: List[List[int]] = []
        for point_x, point_y in state["points"]:
            new_points.append(rotate_point(point_x, point_y))
        new_holes: List[List[List[int]]] = []
        for hole in state.get("holes", []):
            new_holes.append([rotate_point(point_x, point_y) for point_x, point_y in hole])
        new_parts: List[Dict[str, Any]] = []
        for part in state.get("parts", []):
            new_parts.append(
                {
                    "points": [rotate_point(point_x, point_y) for point_x, point_y in part.get("points", [])],
                    "holes": [
                        [rotate_point(point_x, point_y) for point_x, point_y in hole]
                        for hole in part.get("holes", [])
                    ],
                }
            )
        region.shape = "polygon"
        region.points = new_points
        region.holes = new_holes
        region.parts = new_parts
        region.normalize()
        self._redraw_region_live(region.region_id)

    def _update_resize_transform(self, region: Region, x: int, y: int, action: str, state: Dict[str, Any]) -> None:
        old_x, old_y, old_w, old_h = state["bbox"]
        left, top = old_x, old_y
        right, bottom = old_x + old_w, old_y + old_h
        min_size = 4
        if action == "edge_w":
            left = min(x, right - min_size)
        elif action == "edge_e":
            right = max(x, left + min_size)
        elif action == "edge_n":
            top = min(y, bottom - min_size)
        elif action == "edge_s":
            bottom = max(y, top + min_size)
        elif action.startswith("corner_"):
            if action == "corner_nw":
                anchor_x, anchor_y = old_x + old_w, old_y + old_h
                sign_x, sign_y = -1, -1
            elif action == "corner_ne":
                anchor_x, anchor_y = old_x, old_y + old_h
                sign_x, sign_y = 1, -1
            elif action == "corner_sw":
                anchor_x, anchor_y = old_x + old_w, old_y
                sign_x, sign_y = -1, 1
            else:
                anchor_x, anchor_y = old_x, old_y
                sign_x, sign_y = 1, 1
            scale = max(abs(x - anchor_x) / max(1, old_w), abs(y - anchor_y) / max(1, old_h), min_size / max(old_w, old_h))
            new_w = max(min_size, old_w * scale)
            new_h = max(min_size, old_h * scale)
            if sign_x < 0:
                left, right = anchor_x - new_w, anchor_x
            else:
                left, right = anchor_x, anchor_x + new_w
            if sign_y < 0:
                top, bottom = anchor_y - new_h, anchor_y
            else:
                top, bottom = anchor_y, anchor_y + new_h
        region.shape = "polygon"
        region.points = [[int(point_x), int(point_y)] for point_x, point_y in state.get("points", [])]
        region.holes = [
            [[int(point_x), int(point_y)] for point_x, point_y in hole]
            for hole in state.get("holes", [])
        ]
        region.parts = [
            {
                "points": [[int(point_x), int(point_y)] for point_x, point_y in part.get("points", [])],
                "holes": [
                    [[int(point_x), int(point_y)] for point_x, point_y in hole]
                    for hole in part.get("holes", [])
                ],
            }
            for part in state.get("parts", [])
        ]
        region.normalize()
        region.set_bbox(int(round(left)), int(round(top)), int(round(right - left)), int(round(bottom - top)))
        self._redraw_region_live(region.region_id)

    def _start_modify(self, region: Region, x: int, y: int, operation: str) -> None:
        region.shape = "polygon"
        region.points = region.pixel_points()
        region.normalize()
        self.modify_state = {"region_id": region.region_id, "points": [(x, y)], "operation": operation}
        sx, sy = self._screen_point((x, y))
        color = "#166534" if operation == "modify" else "#991b1b"
        self.preview_item = self.canvas.create_line(sx, sy, sx, sy, fill=color, dash=(4, 3), width=2, smooth=True)
        if operation == "modify":
            self.status_text.set(_l(self.language, "增加选定区域：圈出要加入当前区域的范围。", "Add to region: draw the area to merge into the current region."))
        else:
            self.status_text.set(_l(self.language, "减少选定区域：圈出要从当前区域扣掉的范围。", "Subtract from region: draw the area to remove from the current region."))

    def _start_brush_stroke(self, x: int, y: int, operation: str) -> None:
        self.modify_state = {
            "region_id": self.selected_region_id,
            "points": [(x, y)],
            "operation": f"brush_{operation}",
            "category": category_from_label(self.default_category.get()),
            "color": self.project.next_color(),
            "filled": self.brush_fill.get(),
        }
        color = "#166534" if operation != "delete" else "#991b1b"
        sx, sy = self._screen_point((x, y))
        self.preview_item = self.canvas.create_line(sx, sy, sx, sy, fill=color, width=max(2, self._screen(self.brush_size.get())), capstyle=tk.ROUND, smooth=True)

    def _append_modify_point(self, x: int, y: int) -> None:
        if not self.modify_state:
            return
        points = self.modify_state["points"]
        last_x, last_y = points[-1]
        if abs(x - last_x) + abs(y - last_y) >= 5:
            points.append((x, y))
            if self.preview_item:
                self.canvas.coords(self.preview_item, self._flat_screen_points(points))

    def _finish_modify(self) -> None:
        state = self.modify_state
        self.modify_state = None
        if self.preview_item:
            self.canvas.delete(self.preview_item)
            self.preview_item = None
        if not state or len(state["points"]) < 2:
            return
        region = self.project.get_region(state["region_id"])
        operation = str(state.get("operation"))
        stroke = list(state["points"]) if operation.startswith("brush_") else self._simplify_points(state["points"])
        if operation.startswith("brush_"):
            self._finish_brush_operation(state, stroke)
        elif not region:
            return
        elif operation == "delete":
            self._subtract_region_area(region, stroke)
        else:
            self._add_region_area(region, stroke)
        self.project.touch()
        changed_region_id = str(state.get("created_region_id") or state.get("region_id") or "")
        if changed_region_id and self.project.get_region(changed_region_id):
            self._redraw_region_final(changed_region_id)
        else:
            self.refresh_canvas()
        self.refresh_region_list()
        if operation == "brush_new" and state.get("created_region_id"):
            self.set_operation_mode("modify")
            self.status_text.set(_l(self.language, "已创建区域，并已自动切换到加画。", "Region created; switched to Paint Add."))
            return
            self.status_text.set(_l(self.language, "已更新选定区域。", "Selected region updated."))

    def _finish_brush_operation(self, state: Dict[str, Any], stroke: List[Tuple[int, int]]) -> None:
        if len(stroke) < 1:
            return
        operation = str(state.get("operation"))
        radius = max(2, self.brush_size.get() // 2)
        stroke = self._simplify_brush_stroke(stroke, radius)
        if operation == "brush_delete":
            brush_geom = self._clip_geometry_to_canvas(self._geometry_from_brush(stroke, radius))
            if brush_geom.is_empty:
                return
            region = self.project.get_region(state.get("region_id"))
            if region:
                self._apply_geometry_result(region, self._geometry_from_region(region).difference(brush_geom))
            return
        region = self.project.get_region(state.get("region_id")) if operation == "brush_modify" else None
        brush_geom = self._geometry_from_brush(stroke, radius)
        if operation in {"brush_new", "brush_modify"} and bool(state.get("filled", False)):
            fill_geom = self._geometry_from_filled_stroke(stroke, radius)
            if not fill_geom.is_empty:
                brush_geom = brush_geom.union(fill_geom)
        brush_geom = self._clip_geometry_to_canvas(brush_geom)
        if brush_geom.is_empty:
            return
        if region:
            self._apply_geometry_result(region, self._geometry_from_region(region).union(brush_geom))
            return
        if not brush_geom.is_empty:
            new_region = Region(
                name=f"{_l(self.language, '区域', 'Region')} {len(self.project.regions) + 1}",
                x=0,
                y=0,
                width=1,
                height=1,
                category=state.get("category", "rough"),
                color=state.get("color", self.project.next_color()),
                shape="polygon",
                filled=bool(state.get("filled", False)),
            )
            self._set_region_from_polygons(new_region, self._extract_polygons(brush_geom))
            self.project.add_region(new_region)
            self.selected_region_id = new_region.region_id
            if operation == "brush_new":
                state["created_region_id"] = new_region.region_id

    def _extract_polygons(self, geom: BaseGeometry) -> List[Polygon]:
        if isinstance(geom, Polygon):
            return [geom]
        if isinstance(geom, MultiPolygon):
            return list(geom.geoms)
        try:
            return [part for part in geom.geoms if isinstance(part, Polygon)]
        except Exception:
            return []

    def _stroke_is_closed(self, stroke: List[Tuple[int, int]], radius: int) -> bool:
        if len(stroke) < 3:
            return False
        start_x, start_y = stroke[0]
        end_x, end_y = stroke[-1]
        return math.hypot(end_x - start_x, end_y - start_y) <= max(12, radius * 3)

    def _geometry_from_filled_stroke(self, stroke: List[Tuple[int, int]], radius: int) -> BaseGeometry:
        if len(stroke) < 3:
            return GeometryCollection()
        points = list(stroke)
        is_closed = self._stroke_is_closed(points, radius)
        if is_closed and points[0] != points[-1]:
            points.append(points[0])
        try:
            line = LineString(points)
            polygons = [poly for poly in polygonize(unary_union(line)) if poly.area >= 4]
        except Exception:
            polygons = []
        if polygons:
            geom = unary_union(polygons)
        elif is_closed:
            geom = Polygon(points)
        else:
            return GeometryCollection()
        if not geom.is_valid:
            geom = geom.buffer(0)
        return geom

    def _outside_canvas_allowed(self) -> bool:
        return bool(self.settings.get("allow_outside_canvas", False))

    def _canvas_bounds_geometry(self) -> BaseGeometry:
        return box(0, 0, self.project.canvas_width, self.project.canvas_height)

    def _clip_geometry_to_canvas(self, geom: BaseGeometry) -> BaseGeometry:
        if self._outside_canvas_allowed() or geom.is_empty:
            return geom
        if not geom.is_valid:
            geom = geom.buffer(0)
        try:
            geom = geom.intersection(self._canvas_bounds_geometry())
        except Exception:
            return GeometryCollection()
        if not geom.is_valid:
            geom = geom.buffer(0)
        return geom

    def _prepare_geometry_for_storage(self, geom: BaseGeometry) -> BaseGeometry:
        geom = self._clip_geometry_to_canvas(geom)
        if geom.is_empty:
            return geom
        if not geom.is_valid:
            geom = geom.buffer(0)
        try:
            simplified = geom.simplify(0.75, preserve_topology=True)
            if not simplified.is_empty:
                geom = simplified
        except Exception:
            pass
        if not geom.is_valid:
            geom = geom.buffer(0)
        return geom

    def _add_region_area(self, region: Region, stroke: List[Tuple[int, int]]) -> None:
        if len(stroke) < 3:
            return
        base = self._geometry_from_region(region)
        addition = self._clip_geometry_to_canvas(self._geometry_from_polygon_points(stroke))
        if addition.is_empty:
            return
        self._apply_geometry_result(region, base.union(addition))

    def _subtract_region_area(self, region: Region, stroke: List[Tuple[int, int]]) -> None:
        if len(stroke) < 3:
            return
        base = self._geometry_from_region(region)
        subtraction = self._clip_geometry_to_canvas(self._geometry_from_polygon_points(stroke))
        if subtraction.is_empty:
            return
        self._apply_geometry_result(region, base.difference(subtraction))

    def _geometry_from_region(self, region: Region) -> BaseGeometry:
        polygons: List[Polygon] = []
        for part in region.pixel_parts():
            points = [(x, y) for x, y in part["points"]]
            holes = [[(x, y) for x, y in hole] for hole in part.get("holes", [])]
            if len(points) >= 3:
                polygons.append(Polygon(points, holes=holes or None))
        if not polygons:
            return GeometryCollection()
        geom = polygons[0] if len(polygons) == 1 else unary_union(polygons)
        if not geom.is_valid:
            geom = geom.buffer(0)
        return geom

    def _geometry_from_polygon_points(self, points: List[Tuple[int, int]]) -> BaseGeometry:
        if len(points) < 3:
            return GeometryCollection()
        closed_points = list(points)
        if closed_points[0] != closed_points[-1]:
            closed_points.append(closed_points[0])
        line = LineString(closed_points)
        try:
            polygons = list(polygonize(unary_union(line)))
        except Exception:
            polygons = []
        geom = unary_union(polygons) if polygons else Polygon(closed_points)
        if not geom.is_valid:
            geom = geom.buffer(0)
        return geom

    def _geometry_from_brush(self, stroke: List[Tuple[int, int]], radius: int) -> BaseGeometry:
        if len(stroke) == 1:
            geom = LineString([stroke[0], (stroke[0][0] + 0.01, stroke[0][1])]).buffer(radius, 4, cap_style="round", join_style="round")
        else:
            geom = LineString(stroke).buffer(radius, 4, cap_style="round", join_style="round")
        return geom.buffer(0) if not geom.is_valid else geom

    def _apply_geometry_result(self, region: Region, geom: BaseGeometry) -> None:
        geom = self._prepare_geometry_for_storage(geom)
        if geom.is_empty:
            self.project.remove_region(region.region_id)
            self.selected_region_id = None
            return
        polygons: List[Polygon] = []
        if isinstance(geom, Polygon):
            polygons = [geom]
        elif isinstance(geom, MultiPolygon):
            polygons = list(geom.geoms)
        else:
            try:
                polygons = [part for part in geom.geoms if isinstance(part, Polygon)]
            except Exception:
                polygons = []
        clean_polygons: List[Polygon] = []
        for poly in polygons:
            clean = poly if poly.is_valid else poly.buffer(0)
            clean_polygons.extend(self._extract_polygons(clean))
        polygons = [poly for poly in clean_polygons if poly.area >= 4]
        if not polygons:
            self.project.remove_region(region.region_id)
            self.selected_region_id = None
            return
        self._set_region_from_polygons(region, polygons)

    def _polygon_to_part(self, polygon: Polygon) -> Dict[str, Any]:
        if not polygon.is_valid:
            fixed_polygons = self._extract_polygons(polygon.buffer(0))
            if fixed_polygons:
                polygon = max(fixed_polygons, key=lambda poly: poly.area)
        coords = self._ring_points_from_coords(polygon.exterior.coords)
        return {
            "points": coords,
            "holes": [
                self._ring_points_from_coords(interior.coords)
                for interior in polygon.interiors
            ],
        }

    def _ring_points_from_coords(self, coords: Any) -> List[List[int]]:
        points: List[List[int]] = []
        for point_x, point_y, *_rest in coords:
            point = [int(round(point_x)), int(round(point_y))]
            if not points or points[-1] != point:
                points.append(point)
        if len(points) > 1 and points[0] == points[-1]:
            points.pop()
        return self._remove_collinear_points(points)

    def _remove_collinear_points(self, points: List[List[int]]) -> List[List[int]]:
        if len(points) <= 3:
            return points
        cleaned: List[List[int]] = []
        total = len(points)
        for index, current in enumerate(points):
            previous = points[index - 1]
            following = points[(index + 1) % total]
            dx1 = current[0] - previous[0]
            dy1 = current[1] - previous[1]
            dx2 = following[0] - current[0]
            dy2 = following[1] - current[1]
            cross = dx1 * dy2 - dy1 * dx2
            dot = dx1 * dx2 + dy1 * dy2
            if cross == 0 and dot > 0:
                continue
            cleaned.append(current)
        return cleaned if len(cleaned) >= 3 else points

    def _set_region_from_polygons(self, region: Region, polygons: List[Polygon]) -> None:
        polygons = sorted(polygons, key=lambda poly: poly.area, reverse=True)
        parts = [self._polygon_to_part(poly) for poly in polygons]
        parts = [part for part in parts if len(part["points"]) >= 3]
        if not parts:
            return
        region.shape = "polygon"
        region.points = parts[0]["points"]
        region.holes = parts[0]["holes"]
        region.parts = parts[1:]
        region.normalize()

    def _set_region_from_polygon(self, region: Region, polygon: Polygon) -> None:
        part = self._polygon_to_part(polygon)
        if len(part["points"]) < 3:
            return
        region.shape = "polygon"
        region.points = part["points"]
        region.holes = part["holes"]
        region.parts = []
        region.normalize()

    def _replace_region_edge(self, region: Region, stroke: List[Tuple[int, int]]) -> None:
        points = region.pixel_points()
        if len(points) < 3:
            return
        start_index = self._nearest_point_index(points, stroke[0])
        end_index = self._nearest_point_index(points, stroke[-1])
        n = len(points)
        if start_index == end_index:
            insert_at = (start_index + 1) % n
            new_points = points[:insert_at] + [[x, y] for x, y in stroke] + points[insert_at:]
        else:
            forward_len = (end_index - start_index) % n
            backward_len = (start_index - end_index) % n
            if forward_len <= backward_len:
                rotated = points[start_index:] + points[:start_index]
                end_rot = forward_len
                new_points = [[x, y] for x, y in stroke] + rotated[end_rot + 1 :]
            else:
                rotated = points[end_index:] + points[:end_index]
                start_rot = backward_len
                new_points = [[x, y] for x, y in reversed(stroke)] + rotated[start_rot + 1 :]
        region.shape = "polygon"
        region.points = self._simplify_points([(point[0], point[1]) for point in new_points])
        region.normalize()

    def _nearest_point_index(self, points: List[List[int]], target: Tuple[int, int]) -> int:
        target_x, target_y = target
        best_index = 0
        best_distance = float("inf")
        for index, (point_x, point_y) in enumerate(points):
            distance = (point_x - target_x) ** 2 + (point_y - target_y) ** 2
            if distance < best_distance:
                best_index = index
                best_distance = distance
        return best_index

    def _region_from_drag(self, x1: int, y1: int, x2: int, y2: int) -> Optional[Region]:
        category = category_from_label(self.default_category.get())
        if self.draw_tool.get() != "rectangle":
            points = self._simplify_points(self.drag_points)
            if len(points) < 3:
                return None
            xs = [point[0] for point in points]
            ys = [point[1] for point in points]
            if max(xs) - min(xs) < 8 or max(ys) - min(ys) < 8:
                return None
            geom = self._clip_geometry_to_canvas(self._geometry_from_polygon_points(points))
            polygons = self._extract_polygons(geom)
            if not polygons:
                return None
            region = Region(
                name=f"{_l(self.language, '区域', 'Region')} {len(self.project.regions) + 1}",
                x=0,
                y=0,
                width=1,
                height=1,
                category=category,
                color=self.project.next_color(),
                shape="polygon",
            )
            self._set_region_from_polygons(region, polygons)
            return region
        if abs(x2 - x1) < 8 or abs(y2 - y1) < 8:
            return None
        x = min(x1, x2)
        y = min(y1, y2)
        width = abs(x2 - x1)
        height = abs(y2 - y1)
        if not self._outside_canvas_allowed():
            geom = self._clip_geometry_to_canvas(box(x, y, x + width, y + height))
            polygons = self._extract_polygons(geom)
            if not polygons:
                return None
            region = Region(
                name=f"{_l(self.language, '区域', 'Region')} {len(self.project.regions) + 1}",
                x=0,
                y=0,
                width=1,
                height=1,
                category=category,
                color=self.project.next_color(),
                shape="polygon",
            )
            self._set_region_from_polygons(region, polygons)
            return region
        return Region(
            name=f"{_l(self.language, '区域', 'Region')} {len(self.project.regions) + 1}",
            x=x,
            y=y,
            width=width,
            height=height,
            category=category,
            color=self.project.next_color(),
        )

    def _append_drag_point(self, x: int, y: int, force: bool = False) -> None:
        if not self.drag_points:
            self.drag_points.append((x, y))
            return
        last_x, last_y = self.drag_points[-1]
        if force or abs(x - last_x) + abs(y - last_y) >= 5:
            self.drag_points.append((x, y))

    def _simplify_brush_stroke(self, points: List[Tuple[int, int]], radius: int) -> List[Tuple[int, int]]:
        if len(points) <= 2:
            return points
        simplified = self._simplify_points(points)
        tolerance = max(1.0, min(6.0, radius * 0.18))
        simplified = self._rdp_points(simplified, tolerance)
        if len(simplified) <= 260:
            return simplified
        tolerance = max(tolerance * 1.5, 2.0)
        while len(simplified) > 260 and tolerance <= 12:
            simplified = self._rdp_points(points, tolerance)
            tolerance *= 1.5
        return simplified

    def _simplify_points(self, points: List[Tuple[int, int]]) -> List[Tuple[int, int]]:
        clean: List[Tuple[int, int]] = []
        for point_x, point_y in points:
            point = (int(point_x), int(point_y))
            if not clean or clean[-1] != point:
                clean.append(point)
        if len(clean) <= 240:
            return clean
        simplified = self._rdp_points(clean, 1.5)
        tolerance = 2.5
        while len(simplified) > 320 and tolerance <= 10:
            simplified = self._rdp_points(clean, tolerance)
            tolerance *= 1.5
        return simplified

    def _rdp_points(self, points: List[Tuple[int, int]], tolerance: float) -> List[Tuple[int, int]]:
        if len(points) <= 2:
            return points
        start = points[0]
        end = points[-1]
        line_dx = end[0] - start[0]
        line_dy = end[1] - start[1]
        length_sq = line_dx * line_dx + line_dy * line_dy
        max_distance = -1.0
        split_index = 0
        for index in range(1, len(points) - 1):
            point_x, point_y = points[index]
            if length_sq == 0:
                distance = math.hypot(point_x - start[0], point_y - start[1])
            else:
                distance = abs(line_dy * point_x - line_dx * point_y + end[0] * start[1] - end[1] * start[0]) / math.sqrt(length_sq)
            if distance > max_distance:
                max_distance = distance
                split_index = index
        if max_distance <= tolerance:
            return [start, end]
        left = self._rdp_points(points[: split_index + 1], tolerance)
        right = self._rdp_points(points[split_index:], tolerance)
        return left[:-1] + right

    def on_canvas_double_click(self, event: tk.Event) -> None:
        x, y = self._canvas_xy(event)
        current = self.canvas.find_withtag("current")
        region_id = self._region_at_point(x, y, current)
        if region_id:
            self.select_region(region_id)
            self.edit_selected_region()

    def on_tree_select(self, _event: tk.Event) -> None:
        selection = self.tree.selection()
        if selection and selection[0] != self.selected_region_id:
            self.select_region(selection[0])

    def on_tree_double_click(self, event: tk.Event) -> None:
        row = self.tree.identify_row(event.y)
        if not row:
            return
        self.select_region(row)
        self.edit_selected_region()

    def on_tree_button_press(self, event: tk.Event) -> None:
        row = self.tree.identify_row(event.y)
        self.tree_drag_region_id = row or None
        self.tree_drag_ready = False
        self.tree_drag_moved = False
        self.tree_drag_press_y = event.y
        self.tree_drag_insert_index = None
        if row and self.tree_float_label:
            self.tree_float_label.configure(text=self.tree.item(row, "text"))

    def on_tree_drag_motion(self, event: tk.Event) -> None:
        if not self.tree_drag_region_id or not self.tree_drop_line:
            return
        if not self.tree_drag_ready:
            if abs(event.y - self.tree_drag_press_y) < 8:
                return
            self.tree_drag_ready = True
        if abs(event.y - self.tree_drag_press_y) < 8 and not self.tree_drag_moved:
            return
        self.tree_drag_moved = True
        tree_x = self.tree.winfo_x()
        tree_y = self.tree.winfo_y()
        index, line_y = self._tree_insert_index_and_y(event.y)
        self.tree_drag_insert_index = index
        y = tree_y + line_y
        self.tree_drop_line.place(x=tree_x, y=y, width=self.tree.winfo_width(), height=3)
        self.tree_drop_line.lift()
        if self.tree_float_label:
            float_y = tree_y + max(0, min(self.tree.winfo_height() - 24, event.y - 12))
            self.tree_float_label.place(x=tree_x + 18, y=float_y, width=max(120, self.tree.winfo_width() - 36))
            self.tree_float_label.lift()

    def on_tree_button_release(self, event: tk.Event) -> None:
        dragged_id = self.tree_drag_region_id
        self.tree_drag_region_id = None
        was_ready = self.tree_drag_ready
        was_moved = self.tree_drag_moved
        self.tree_drag_ready = False
        self.tree_drag_moved = False
        if self.tree_drop_line:
            self.tree_drop_line.place_forget()
        if self.tree_float_label:
            self.tree_float_label.place_forget()
        if not was_ready or not was_moved:
            return
        if dragged_id:
            index, _line_y = self._tree_insert_index_and_y(event.y)
        else:
            index = None
        if not dragged_id or index is None:
            return
        tree_order = list(self.tree.get_children())
        if dragged_id not in tree_order:
            return
        tree_order.remove(dragged_id)
        index = max(0, min(len(tree_order), index))
        tree_order.insert(index, dragged_id)
        id_to_region = {region.region_id: region for region in self.project.regions}
        new_regions = [id_to_region[item_id] for item_id in reversed(tree_order) if item_id in id_to_region]
        if [region.region_id for region in new_regions] == [region.region_id for region in self.project.regions]:
            return
        self.push_undo()
        self.project.regions = new_regions
        self.project.touch()
        self.selected_region_id = dragged_id
        self.refresh_canvas()
        self.refresh_region_list()
        self.status_text.set(_l(self.language, "图层顺序已调整。列表上方显示更靠前的区域。", "Layer order updated. Higher rows are visually in front."))

    def _tree_insert_index_and_y(self, event_y: int) -> Tuple[int, int]:
        children = list(self.tree.get_children())
        if not children:
            return 0, 0
        for index, item_id in enumerate(children):
            bbox = self.tree.bbox(item_id)
            if not bbox:
                continue
            _x, y, _w, h = bbox
            if event_y < y + h / 2:
                return index, y
        last_bbox = self.tree.bbox(children[-1])
        if last_bbox:
            return len(children), last_bbox[1] + last_bbox[3]
        return len(children), max(0, min(self.tree.winfo_height(), event_y))

    def select_region(self, region_id: Optional[str], refresh: bool = True) -> None:
        self.selected_region_id = region_id
        if region_id and self.tree.exists(region_id):
            self.tree.selection_set(region_id)
            self.tree.see(region_id)
        if refresh:
            self.refresh_canvas()
        self._update_summary()

    def edit_selected_region(self) -> None:
        region = self.project.get_region(self.selected_region_id)
        if not region:
            messagebox.showinfo(_l(self.language, "没有选中区域", "No region selected"), _l(self.language, "请先单击一个区域。", "Select a region first."), parent=self)
            return
        self.push_undo()
        dialog = RegionDialog(self, self.project, region, self.language)
        if dialog.saved:
            self.project.touch()
            self.refresh_canvas()
            self.refresh_region_list()
            self.status_text.set(_l(self.language, f"已更新：{region.name}", f"Updated: {region.name}"))
        else:
            self.undo_stack.pop()

    def duplicate_selected_region(self) -> None:
        region = self.project.get_region(self.selected_region_id)
        if not region:
            return
        self.push_undo()
        copy = Region.from_dict(region.to_dict())
        copy.region_id = Region(name="tmp", x=0, y=0, width=1, height=1).region_id
        copy.name = f"{region.name} {_l(self.language, '副本', 'copy')}"
        copy.move_by(24, 24, self.project.canvas_width, self.project.canvas_height)
        copy.color = self.project.next_color()
        self.project.add_region(copy)
        self.selected_region_id = copy.region_id
        self.refresh_canvas()
        self.refresh_region_list()

    def delete_selected_region(self) -> None:
        region = self.project.get_region(self.selected_region_id)
        if not region:
            return
        if not messagebox.askyesno(_l(self.language, "删除区域", "Delete region"), _l(self.language, f"确定删除“{region.name}”吗？", f'Delete "{region.name}"?'), parent=self):
            return
        self.push_undo()
        self.project.remove_region(region.region_id)
        self.selected_region_id = None
        self.refresh_canvas()
        self.refresh_region_list()
        self.status_text.set(_l(self.language, "已删除区域。", "Region deleted."))

    def move_selected_order(self, offset: int) -> None:
        region = self.project.get_region(self.selected_region_id)
        if not region:
            return
        index = self.project.regions.index(region)
        new_index = max(0, min(len(self.project.regions) - 1, index + offset))
        if new_index == index:
            return
        self.push_undo()
        self.project.regions.pop(index)
        self.project.regions.insert(new_index, region)
        self.project.touch()
        self.refresh_canvas()
        self.refresh_region_list()

    def bring_selected_to_front(self) -> None:
        self._move_selected_to_index(len(self.project.regions) - 1)

    def send_selected_to_back(self) -> None:
        self._move_selected_to_index(0)

    def _move_selected_to_index(self, new_index: int) -> None:
        region = self.project.get_region(self.selected_region_id)
        if not region:
            return
        old_index = self.project.regions.index(region)
        new_index = max(0, min(len(self.project.regions) - 1, new_index))
        if old_index == new_index:
            return
        self.push_undo()
        self.project.regions.pop(old_index)
        self.project.regions.insert(new_index, region)
        self.project.touch()
        self.refresh_canvas()
        self.refresh_region_list()

    def nudge_selected(self, dx: int, dy: int, event: tk.Event) -> str:
        region = self.project.get_region(self.selected_region_id)
        if not region:
            return "break"
        self.push_undo()
        step = 10 if event.state & 0x0001 else 1
        region.move_by(dx * step, dy * step, self.project.canvas_width, self.project.canvas_height)
        self.project.touch()
        self.refresh_canvas()
        self.refresh_region_list()
        return "break"

    def on_mouse_wheel(self, event: tk.Event) -> str:
        if not self.settings.get("wheel_pan_enabled", True):
            return ""
        steps = -1 if event.delta > 0 else 1
        self.canvas.yview_scroll(steps * 3, "units")
        return "break"

    def on_shift_mouse_wheel(self, event: tk.Event) -> str:
        if not self.settings.get("wheel_pan_enabled", True):
            return ""
        steps = -1 if event.delta > 0 else 1
        self.canvas.xview_scroll(steps * 3, "units")
        return "break"

    def on_alt_mouse_wheel(self, event: tk.Event) -> str:
        if not self.settings.get("alt_wheel_zoom", True):
            return ""
        requested = 1.12 if event.delta > 0 else 1 / 1.12
        return self.zoom_canvas_by(requested, event.x, event.y)

    def zoom_canvas_by(self, requested: float, anchor_x: Optional[int] = None, anchor_y: Optional[int] = None) -> str:
        old_zoom = self.zoom
        if anchor_x is None or anchor_y is None:
            anchor_x = max(1, self.canvas.winfo_width()) // 2
            anchor_y = max(1, self.canvas.winfo_height()) // 2
        before_x = self.canvas.canvasx(anchor_x) / old_zoom
        before_y = self.canvas.canvasy(anchor_y) / old_zoom
        self.zoom = max(0.2, min(4.0, old_zoom * requested))
        factor = self.zoom / old_zoom
        if abs(factor - 1.0) < 0.0001:
            return "break"
        self._begin_zoom_preview()
        self.canvas.scale("all", 0, 0, factor, factor)
        self._update_canvas_scrollregion()
        scrollregion = [float(value) for value in self.canvas.cget("scrollregion").split()]
        if len(scrollregion) == 4:
            left, top, right, bottom = scrollregion
            width = max(1.0, right - left)
            height = max(1.0, bottom - top)
            self.canvas.xview_moveto(max(0, min(1, (self._screen(before_x) - anchor_x - left) / width)))
            self.canvas.yview_moveto(max(0, min(1, (self._screen(before_y) - anchor_y - top) / height)))
        self.zoom_preview_dirty = True
        self._schedule_zoom_refresh()
        self._claim_canvas_input()
        self._schedule_window_mouse_restore()
        self._schedule_window_mouse_restore(80)
        self.status_text.set(_l(self.language, f"画布缩放：{int(self.zoom * 100)}%", f"Canvas zoom: {int(self.zoom * 100)}%"))
        return "break"

    def on_middle_press(self, event: tk.Event) -> str:
        if not self.settings.get("middle_mouse_pan", True):
            return ""
        if self.zoom_refresh_after_id:
            self.after_cancel(self.zoom_refresh_after_id)
            self.zoom_refresh_after_id = None
        self.canvas.scan_mark(event.x, event.y)
        self.middle_pan_start = (event.x, event.y)
        self._claim_canvas_input()
        return "break"

    def on_middle_drag(self, event: tk.Event) -> str:
        if not self.settings.get("middle_mouse_pan", True):
            return ""
        if self.middle_pan_start is None:
            self.canvas.scan_mark(event.x, event.y)
            self.middle_pan_start = (event.x, event.y)
            return "break"
        self.canvas.scan_dragto(event.x, event.y, gain=1)
        return "break"

    def on_middle_release(self, _event: tk.Event) -> str:
        self.middle_pan_start = None
        if self.zoom_preview_dirty:
            self._schedule_zoom_refresh(260)
        return "break"

    def _schedule_zoom_refresh(self, delay_ms: int = 110) -> None:
        if self.zoom_refresh_after_id:
            self.after_cancel(self.zoom_refresh_after_id)
        self.zoom_refresh_after_id = self.after(delay_ms, self._finish_zoom_refresh)

    def _finish_zoom_refresh(self) -> None:
        self.zoom_refresh_after_id = None
        if not self.zoom_preview_dirty:
            return
        if self.middle_pan_start is not None:
            self._schedule_zoom_refresh(260)
            return
        self.zoom_preview_dirty = False
        xview = self.canvas.xview()[0]
        yview = self.canvas.yview()[0]
        self.settings["canvas_zoom"] = self.zoom
        save_settings(self.settings)
        self.refresh_canvas()
        self.canvas.xview_moveto(xview)
        self.canvas.yview_moveto(yview)
        self._claim_canvas_input()
        self._schedule_window_mouse_restore()

    def _claim_canvas_input(self) -> None:
        try:
            self.focus_set()
            self.canvas.focus_set()
        except tk.TclError:
            pass

    def _schedule_window_mouse_restore(self, delay_ms: int = 0) -> None:
        if delay_ms <= 0:
            self._restore_window_mouse_mode()
            return
        if self.window_restore_after_id:
            try:
                self.after_cancel(self.window_restore_after_id)
            except tk.TclError:
                pass
        try:
            self.window_restore_after_id = self.after(delay_ms, self._restore_window_mouse_mode)
        except tk.TclError:
            self.window_restore_after_id = None

    def _restore_window_mouse_mode(self) -> None:
        self.window_restore_after_id = None
        if self.restoring_window_input:
            return
        self.restoring_window_input = True
        try:
            if sys.platform.startswith("win"):
                try:
                    user32 = ctypes.windll.user32
                    hwnd = int(self.winfo_id())
                    canvas_hwnd = int(self.canvas.winfo_id())
                    user32.ReleaseCapture()
                    user32.SendMessageW(hwnd, 0x001F, 0, 0)
                    user32.SetActiveWindow(hwnd)
                    user32.SetFocus(canvas_hwnd)
                except Exception:
                    pass
            self._claim_canvas_input()
        finally:
            try:
                self.after(50, lambda: setattr(self, "restoring_window_input", False))
            except tk.TclError:
                self.restoring_window_input = False

    def _event_over_canvas(self, event: tk.Event) -> bool:
        try:
            x = int(event.x_root - self.canvas.winfo_rootx())
            y = int(event.y_root - self.canvas.winfo_rooty())
        except Exception:
            return False
        return 0 <= x < self.canvas.winfo_width() and 0 <= y < self.canvas.winfo_height()

    def _event_for_canvas(self, event: tk.Event) -> tk.Event:
        canvas_event = tk.Event()
        canvas_event.x = int(event.x_root - self.canvas.winfo_rootx())
        canvas_event.y = int(event.y_root - self.canvas.winfo_rooty())
        canvas_event.x_root = event.x_root
        canvas_event.y_root = event.y_root
        canvas_event.delta = getattr(event, "delta", 0)
        canvas_event.state = getattr(event, "state", 0)
        canvas_event.widget = self.canvas
        return canvas_event

    def on_global_mouse_wheel(self, event: tk.Event) -> Optional[str]:
        if event.widget is self.canvas or not self._event_over_canvas(event):
            return None
        canvas_event = self._event_for_canvas(event)
        state = getattr(event, "state", 0)
        if state & 0x0008:
            return self.on_alt_mouse_wheel(canvas_event)
        if state & 0x0001:
            return self.on_shift_mouse_wheel(canvas_event)
        return self.on_mouse_wheel(canvas_event)

    def on_global_middle_press(self, event: tk.Event) -> Optional[str]:
        if event.widget is self.canvas or not self._event_over_canvas(event):
            return None
        return self.on_middle_press(self._event_for_canvas(event))

    def on_global_middle_drag(self, event: tk.Event) -> Optional[str]:
        if event.widget is self.canvas or not self._event_over_canvas(event):
            return None
        return self.on_middle_drag(self._event_for_canvas(event))

    def on_global_middle_release(self, event: tk.Event) -> Optional[str]:
        if event.widget is self.canvas:
            return None
        if not self._event_over_canvas(event) and self.middle_pan_start is None:
            return None
        return self.on_middle_release(self._event_for_canvas(event))

    def on_alt_key_release(self, _event: tk.Event) -> str:
        self._schedule_window_mouse_restore()
        self._schedule_window_mouse_restore(80)
        return "break"

    def on_window_focus_in(self, _event: tk.Event) -> Optional[str]:
        return None

    def _update_summary(self) -> None:
        region = self.project.get_region(self.selected_region_id)
        self.summary.configure(state="normal")
        self.summary.delete("1.0", "end")
        if not region:
            text = _l(
                self.language,
                f"项目：{self.project.title}\n画布：{self.project.canvas_width} x {self.project.canvas_height}px\n区域数：{len(self.project.regions)}",
                f"Project: {self.project.title}\nCanvas: {self.project.canvas_width} x {self.project.canvas_height}px\nRegions: {len(self.project.regions)}",
            )
        else:
            if self.language == "en":
                text = (
                    f"Name: {region.name}\n"
                    f"Shape: {'Freeform region' if region.shape == 'polygon' else 'Rectangle'}\n"
                    f"Type: {display_label(region.category, 'en')}\n"
                    f"Pixel bounds: x={region.x}, y={region.y}, w={region.width}, h={region.height}\n"
                    f"Closed points: {len(region.pixel_points())}\n"
                    f"Priority: {region.priority}\n\n"
                    f"Natural language: {region.description or '(Not provided)'}\n\n"
                    f"Standard prompt: {region.standard_prompt or '(Not provided)'}\n\n"
                    f"Notes: {region.ai_notes or '(Not provided)'}"
                )
            else:
                text = (
                    f"名称：{region.name}\n"
                    f"形状：{'自由闭合区域' if region.shape == 'polygon' else '矩形区域'}\n"
                    f"分类：{display_label(region.category)}\n"
                    f"像素范围：x={region.x}, y={region.y}, w={region.width}, h={region.height}\n"
                    f"闭合点数：{len(region.pixel_points())}\n"
                    f"优先级：{region.priority}\n\n"
                    f"自然语言：{region.description or '（未填写）'}\n\n"
                    f"标准化提示词：{region.standard_prompt or '（未填写）'}\n\n"
                    f"备注：{region.ai_notes or '（未填写）'}"
                )
        self.summary.insert("1.0", text)
        self.summary.configure(state="disabled")

    def _canvas_xy(self, event: tk.Event, clamp: Optional[bool] = None) -> Tuple[int, int]:
        x = int(self.canvas.canvasx(event.x) / self.zoom)
        y = int(self.canvas.canvasy(event.y) / self.zoom)
        if clamp is None:
            clamp = False
        if clamp:
            return (
                max(0, min(self.project.canvas_width, x)),
                max(0, min(self.project.canvas_height, y)),
            )
        return x, y

    def _canvas_margin(self) -> int:
        return max(self._screen(180), 80)

    def _screen(self, value: float) -> int:
        return int(round(value * self.zoom))

    def _screen_point(self, point: Tuple[int, int]) -> Tuple[int, int]:
        return self._screen(point[0]), self._screen(point[1])

    def _flat_points(self, points) -> List[int]:
        flat: List[int] = []
        for point in points:
            flat.extend([int(point[0]), int(point[1])])
        if len(flat) == 2:
            flat.extend(flat)
        return flat

    def _flat_screen_points(self, points) -> List[int]:
        flat: List[int] = []
        for point in points:
            flat.extend([self._screen(point[0]), self._screen(point[1])])
        if len(flat) == 2:
            flat.extend(flat)
        return flat

    def _region_at_point(self, x: int, y: int, current_items=None) -> Optional[str]:
        ordered_items: List[int] = []
        for item in current_items or []:
            ordered_items.append(item)
        sx, sy = self._screen(x), self._screen(y)
        for item in reversed(self.canvas.find_overlapping(sx, sy, sx, sy)):
            if item not in ordered_items:
                ordered_items.append(item)
        return self._region_from_items(ordered_items, x, y)

    def _region_from_items(self, items, x: Optional[int] = None, y: Optional[int] = None) -> Optional[str]:
        for item in items:
            region_id: Optional[str] = None
            if item in self.item_to_region:
                region_id = self.item_to_region[item]
            else:
                for tag in self.canvas.gettags(item):
                    if tag.startswith("region_"):
                        region_id = tag
                        break
            if region_id and (x is None or y is None or self._point_hits_region(region_id, x, y)):
                return region_id
        return None

    def _point_hits_region(self, region_id: str, x: int, y: int) -> bool:
        region = self.project.get_region(region_id)
        if not region:
            return False
        if region.shape != "polygon":
            return region.x <= x <= region.x + region.width and region.y <= y <= region.y + region.height
        geom = self._geometry_from_region(region)
        if geom.is_empty:
            return False
        point = Point(x, y)
        if geom.covers(point):
            return True
        return geom.boundary.distance(point) <= max(2.0, 4.0 / max(0.2, self.zoom))

    def _color_rgb(self, value: str) -> Tuple[int, int, int]:
        text = value.strip().lstrip("#")
        if len(text) != 6:
            return (232, 74, 95)
        try:
            return tuple(int(text[index : index + 2], 16) for index in (0, 2, 4))  # type: ignore[return-value]
        except ValueError:
            return (232, 74, 95)

    def _control_action_from_items(self, items) -> Optional[str]:
        for item in items:
            if item in self.control_actions:
                return self.control_actions[item]
        return None

    def toggle_fullscreen(self, enabled: Optional[bool] = None) -> str:
        target = (not self.is_fullscreen) if enabled is None else bool(enabled)
        if target == self.is_fullscreen or self.fullscreen_transitioning:
            return "break"
        self.fullscreen_transitioning = True
        if target:
            try:
                self.pre_fullscreen_state = self.state()
            except tk.TclError:
                self.pre_fullscreen_state = "normal"
            if self.pre_fullscreen_state == "normal":
                self.normal_window_geometry = self.geometry()
        try:
            # Hide the decorated window while Windows changes display modes.
            # This prevents the previous maximized rectangle from flashing.
            self.withdraw()
            self.attributes("-fullscreen", target)
            if not target:
                if self.normal_window_geometry:
                    self.geometry(self.normal_window_geometry)
        except tk.TclError:
            self.fullscreen_transitioning = False
            try:
                self.deiconify()
            except tk.TclError:
                pass
            return "break"
        self.is_fullscreen = target
        self._update_fullscreen_button()
        if target:
            self.status_text.set(_l(self.language, "已进入全屏模式。按 F11 可切换，按 Esc 可退出全屏。", "Fullscreen enabled. Press F11 to toggle or Esc to exit."))
        else:
            self.status_text.set(_l(self.language, "已退出全屏模式。", "Fullscreen disabled."))

        def finish_transition() -> None:
            try:
                self.deiconify()
                if not target and self.pre_fullscreen_state == "zoomed":
                    self.state("zoomed")
                elif not target and self.pre_fullscreen_state == "normal" and self.state() != "normal":
                    self.state("normal")
                self.lift()
                self._claim_canvas_input()
            finally:
                self.fullscreen_transitioning = False

        try:
            self.after_idle(finish_transition)
        except tk.TclError:
            self.fullscreen_transitioning = False
        return "break"

    def show_about(self) -> None:
        AboutDialog(self, self.language)


class ProjectDialog(tk.Toplevel):
    def __init__(self, parent: tk.Tk, current: Project, language: str = "zh", modal: bool = True) -> None:
        super().__init__(parent)
        self.withdraw()
        self.language = language
        self.title(_l(language, "新建画布", "New canvas"))
        self.resizable(False, False)
        self.result: Optional[Project] = None
        self.transient(parent)

        frame = ttk.Frame(self, padding=14)
        frame.grid(row=0, column=0, sticky="nsew")
        self.title_var = tk.StringVar(value=current.title)
        self.width_var = tk.StringVar(value=str(current.canvas_width))
        self.height_var = tk.StringVar(value=str(current.canvas_height))
        ttk.Label(frame, text=_l(language, "项目名称", "Project name")).grid(row=0, column=0, sticky="w", pady=4)
        ttk.Entry(frame, textvariable=self.title_var, width=34).grid(row=0, column=1, sticky="ew", pady=4)
        ttk.Label(frame, text=_l(language, "画布宽度 px", "Canvas width px")).grid(row=1, column=0, sticky="w", pady=4)
        ttk.Entry(frame, textvariable=self.width_var, width=12).grid(row=1, column=1, sticky="w", pady=4)
        ttk.Label(frame, text=_l(language, "画布高度 px", "Canvas height px")).grid(row=2, column=0, sticky="w", pady=4)
        ttk.Entry(frame, textvariable=self.height_var, width=12).grid(row=2, column=1, sticky="w", pady=4)
        ttk.Label(frame, text=_l(language, "常用：1024x1024、1344x768、768x1344", "Common: 1024x1024, 1344x768, 768x1344"), style="Hint.TLabel").grid(row=3, column=0, columnspan=2, sticky="w", pady=(0, 8))
        buttons = ttk.Frame(frame)
        buttons.grid(row=4, column=0, columnspan=2, sticky="e")
        ttk.Button(buttons, text=_l(language, "取消", "Cancel"), command=self.destroy).grid(row=0, column=0, padx=4)
        ttk.Button(buttons, text=_l(language, "创建", "Create"), command=self.on_ok).grid(row=0, column=1, padx=4)
        self.bind("<Return>", lambda _event: self.on_ok())
        _show_centered_dialog(self, parent, grab=modal)
        if modal:
            self.wait_window(self)

    def on_ok(self) -> None:
        try:
            width = int(self.width_var.get())
            height = int(self.height_var.get())
        except ValueError:
            messagebox.showerror(_l(self.language, "尺寸不正确", "Invalid size"), _l(self.language, "宽度和高度必须是数字。", "Width and height must be numbers."), parent=self)
            return
        if not (64 <= width <= 12000 and 64 <= height <= 12000):
            messagebox.showerror(_l(self.language, "尺寸不正确", "Invalid size"), _l(self.language, "宽度和高度需要在 64 到 12000 像素之间。", "Width and height must be between 64 and 12000 pixels."), parent=self)
            return
        self.result = Project(title=self.title_var.get().strip() or _l(self.language, "未命名构图", "Untitled composition"), canvas_width=width, canvas_height=height)
        self.destroy()


class GlobalPromptDialog(tk.Toplevel):
    def __init__(self, parent: tk.Tk, project: Project, language: str = "zh", modal: bool = True) -> None:
        super().__init__(parent)
        self.withdraw()
        self.language = language
        self.title(_l(language, "全局画面要求", "Global image requirements"))
        self.geometry("620x460")
        self.minsize(540, 380)
        self.project = project
        self.saved = False
        self.transient(parent)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        frame = ttk.Frame(self, padding=14)
        frame.grid(row=0, column=0, sticky="nsew")
        frame.columnconfigure(0, weight=1)
        ttk.Label(frame, text=_l(language, "整体画面要什么", "What the whole image should contain"), style="Header.TLabel").grid(row=0, column=0, sticky="w")
        self.prompt = tk.Text(frame, height=8, wrap="word")
        self.prompt.grid(row=1, column=0, sticky="nsew", pady=(6, 12))
        self.prompt.insert("1.0", project.global_prompt)
        ttk.Label(frame, text=_l(language, "不希望出现什么", "What should not appear"), style="Header.TLabel").grid(row=2, column=0, sticky="w")
        self.negative = tk.Text(frame, height=6, wrap="word")
        self.negative.grid(row=3, column=0, sticky="nsew", pady=(6, 12))
        self.negative.insert("1.0", project.negative_prompt)
        buttons = ttk.Frame(frame)
        buttons.grid(row=4, column=0, sticky="e")
        ttk.Button(buttons, text=_l(language, "取消", "Cancel"), command=self.destroy).grid(row=0, column=0, padx=4)
        ttk.Button(buttons, text=_l(language, "保存", "Save"), command=self.on_save).grid(row=0, column=1, padx=4)
        _show_centered_dialog(self, parent, 620, 460, grab=modal)
        if modal:
            self.wait_window(self)

    def on_save(self) -> None:
        self.project.global_prompt = self.prompt.get("1.0", "end").strip()
        self.project.negative_prompt = self.negative.get("1.0", "end").strip()
        self.saved = True
        self.destroy()


class RegionDialog(tk.Toplevel):
    def __init__(
        self,
        parent: tk.Tk,
        project: Project,
        region: Region,
        language: str = "zh",
        modal: bool = True,
    ) -> None:
        super().__init__(parent)
        self.withdraw()
        self.language = language
        self.title(_l(language, "编辑区域标注", "Edit region annotation"))
        self.geometry("700x760")
        self.minsize(620, 680)
        self.project = project
        self.region = region
        self.saved = False
        self.transient(parent)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        self.name_var = tk.StringVar(value=region.name)
        self.category_var = tk.StringVar(value=display_label(region.category, language))
        self.x_var = tk.StringVar(value=str(region.x))
        self.y_var = tk.StringVar(value=str(region.y))
        self.w_var = tk.StringVar(value=str(region.width))
        self.h_var = tk.StringVar(value=str(region.height))
        self.priority_var = tk.StringVar(value=str(region.priority))
        self.color_var = tk.StringVar(value=region.color)

        frame = ttk.Frame(self, padding=14)
        frame.grid(row=0, column=0, sticky="nsew")
        frame.columnconfigure(1, weight=1)
        frame.rowconfigure(8, weight=1)
        frame.rowconfigure(11, weight=1)
        frame.rowconfigure(14, weight=1)

        ttk.Label(frame, text=_l(language, "名称", "Name")).grid(row=0, column=0, sticky="w", pady=4)
        ttk.Entry(frame, textvariable=self.name_var).grid(row=0, column=1, columnspan=3, sticky="ew", pady=4)
        ttk.Label(frame, text=_l(language, "分类", "Type")).grid(row=1, column=0, sticky="w", pady=4)
        labels = [display_label(key, language) for key in CONSTRAINT_TYPES]
        ttk.Combobox(frame, textvariable=self.category_var, values=labels, state="readonly").grid(row=1, column=1, columnspan=3, sticky="ew", pady=4)

        ttk.Label(frame, text=_l(language, "像素位置", "Pixel position")).grid(row=2, column=0, sticky="w", pady=(10, 4))
        ttk.Label(frame, text=_l(language, "自由区域这里是整体外接框，可用于整体缩放。", "For freeform regions this is the overall bounding box used for scaling."), style="Hint.TLabel").grid(row=3, column=1, columnspan=3, sticky="w")
        coord = ttk.Frame(frame)
        coord.grid(row=2, column=1, columnspan=3, sticky="ew", pady=(10, 4))
        for index, (label, variable) in enumerate((("x", self.x_var), ("y", self.y_var), (_l(language, "宽", "w"), self.w_var), (_l(language, "高", "h"), self.h_var))):
            ttk.Label(coord, text=label).grid(row=0, column=index * 2, padx=(0, 3))
            ttk.Entry(coord, textvariable=variable, width=8).grid(row=0, column=index * 2 + 1, padx=(0, 8))

        ttk.Label(frame, text=_l(language, "优先级 1-5", "Priority 1-5")).grid(row=4, column=0, sticky="w", pady=4)
        ttk.Spinbox(frame, from_=1, to=5, textvariable=self.priority_var, width=6).grid(row=4, column=1, sticky="w", pady=4)
        ttk.Label(frame, text=_l(language, "标注颜色", "Guide color")).grid(row=5, column=0, sticky="w", pady=4)
        color_frame = ttk.Frame(frame)
        color_frame.grid(row=5, column=1, sticky="ew", pady=4)
        ttk.Entry(color_frame, textvariable=self.color_var, width=12).grid(row=0, column=0, padx=(0, 6))
        ttk.Button(color_frame, text=_l(language, "选择颜色", "Choose color"), command=self.choose_color).grid(row=0, column=1)

        ttk.Label(frame, text=_l(language, "自然语言", "Natural language"), style="Header.TLabel").grid(row=6, column=0, columnspan=4, sticky="w", pady=(12, 4))
        ttk.Label(frame, text=_l(language, "可以只填这一项。AI 读取文件后会尝试理解并提示词化这段话。", "This may be the only field you fill. The AI will use it as the primary semantic description."), style="Hint.TLabel").grid(
            row=7, column=0, columnspan=4, sticky="w"
        )
        self.description = tk.Text(frame, height=7, wrap="word")
        self.description.grid(row=8, column=0, columnspan=4, sticky="nsew", pady=(4, 10))
        self.description.insert("1.0", region.description)

        ttk.Label(frame, text=_l(language, "标准化提示词", "Standard prompt"), style="Header.TLabel").grid(row=9, column=0, columnspan=4, sticky="w", pady=(4, 4))
        ttk.Label(frame, text=_l(language, "可选。适合写已经整理好的关键词、英文 prompt 或工作流字段。", "Optional: prepared keywords, an English prompt, or workflow fields."), style="Hint.TLabel").grid(
            row=10, column=0, columnspan=4, sticky="w"
        )
        self.standard_prompt = tk.Text(frame, height=5, wrap="word")
        self.standard_prompt.grid(row=11, column=0, columnspan=4, sticky="nsew", pady=(4, 10))
        self.standard_prompt.insert("1.0", region.standard_prompt)

        ttk.Label(frame, text=_l(language, "备注", "Notes"), style="Header.TLabel").grid(row=12, column=0, columnspan=4, sticky="w", pady=(4, 4))
        ttk.Label(frame, text=_l(language, "给自己或协作者看的补充说明，不强制要求 AI 当作提示词执行。", "Supplementary notes for you or collaborators; they are not mandatory prompt instructions."), style="Hint.TLabel").grid(
            row=13, column=0, columnspan=4, sticky="w"
        )
        self.ai_notes = tk.Text(frame, height=5, wrap="word")
        self.ai_notes.grid(row=14, column=0, columnspan=4, sticky="nsew", pady=(4, 10))
        self.ai_notes.insert("1.0", region.ai_notes)

        buttons = ttk.Frame(frame)
        buttons.grid(row=15, column=0, columnspan=4, sticky="e")
        ttk.Button(buttons, text=_l(language, "取消", "Cancel"), command=self.destroy).grid(row=0, column=0, padx=4)
        ttk.Button(buttons, text=_l(language, "保存", "Save"), command=self.on_save).grid(row=0, column=1, padx=4)
        self.bind("<Control-s>", lambda _event: self.on_save())
        _show_centered_dialog(self, parent, 700, 760, grab=modal)
        if modal:
            self.wait_window(self)

    def choose_color(self) -> None:
        color = colorchooser.askcolor(color=self.color_var.get(), parent=self)
        if color and color[1]:
            self.color_var.set(color[1])

    def on_save(self) -> None:
        try:
            x = int(float(self.x_var.get()))
            y = int(float(self.y_var.get()))
            width = int(float(self.w_var.get()))
            height = int(float(self.h_var.get()))
            priority = int(float(self.priority_var.get()))
        except ValueError:
            messagebox.showerror(_l(self.language, "数字不正确", "Invalid number"), _l(self.language, "位置、尺寸和优先级都需要填写数字。", "Position, size, and priority must be numbers."), parent=self)
            return
        if width <= 0 or height <= 0:
            messagebox.showerror(_l(self.language, "尺寸不正确", "Invalid size"), _l(self.language, "宽度和高度必须大于 0。", "Width and height must be greater than zero."), parent=self)
            return
        width = min(width, self.project.canvas_width)
        height = min(height, self.project.canvas_height)
        x = max(0, min(self.project.canvas_width - width, x))
        y = max(0, min(self.project.canvas_height - height, y))
        self.region.name = self.name_var.get().strip() or _l(self.language, "未命名区域", "Untitled region")
        self.region.category = category_from_label(self.category_var.get())
        self.region.set_bbox(x, y, width, height)
        self.region.priority = max(1, min(5, priority))
        self.region.color = self.color_var.get().strip() or "#E84A5F"
        self.region.description = self.description.get("1.0", "end").strip()
        self.region.standard_prompt = self.standard_prompt.get("1.0", "end").strip()
        self.region.ai_notes = self.ai_notes.get("1.0", "end").strip()
        self.region.normalize()
        self.saved = True
        self.destroy()


class SettingsDialog(tk.Toplevel):
    def __init__(
        self,
        parent: tk.Tk,
        settings: Dict[str, Any],
        language: str = "zh",
        modal: bool = True,
    ) -> None:
        super().__init__(parent)
        # Build the dialog while hidden so Windows never paints the default
        # tiny Toplevel at the top-left corner.
        self.withdraw()
        self.language = language
        self.title(_l(language, "设置", "Settings"))
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        preferred_width = 880 if language == "en" else 760
        preferred_height = 760 if language == "en" else 720
        dialog_width = min(preferred_width, max(620, screen_width - 96))
        dialog_height = min(preferred_height, max(520, screen_height - 128))
        parent.update_idletasks()
        x = max(8, min(screen_width - dialog_width - 16, parent.winfo_rootx() + (parent.winfo_width() - dialog_width) // 2))
        y = max(8, min(screen_height - dialog_height - 48, parent.winfo_rooty() + (parent.winfo_height() - dialog_height) // 2))
        self.geometry(f"{dialog_width}x{dialog_height}+{x}+{y}")
        self.minsize(min(dialog_width, 720 if language == "en" else 640), min(dialog_height, 560))
        self.saved = False
        self.result: Dict[str, Any] = dict(settings)
        self.transient(parent)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        body = ttk.Frame(self)
        body.grid(row=0, column=0, sticky="nsew")
        body.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=1)
        dialog_background = ttk.Style(self).lookup("TFrame", "background") or self.cget("background")
        canvas = tk.Canvas(body, highlightthickness=0, background=dialog_background)
        self.settings_canvas = canvas
        scrollbar = ttk.Scrollbar(body, orient=tk.VERTICAL, command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

        frame = ttk.Frame(canvas, padding=16)
        frame_window = canvas.create_window((0, 0), window=frame, anchor="nw")
        frame.bind("<Configure>", lambda _event: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda event: canvas.itemconfigure(frame_window, width=event.width))
        self.bind(
            "<MouseWheel>",
            lambda event: (canvas.yview_scroll(int(-event.delta / 120), "units"), "break")[1],
        )
        frame.columnconfigure(1, weight=1)
        frame.columnconfigure(0, minsize=240 if language == "en" else 190)

        self.middle_mouse_pan = tk.BooleanVar(value=bool(settings.get("middle_mouse_pan", True)))
        self.wheel_pan_enabled = tk.BooleanVar(value=bool(settings.get("wheel_pan_enabled", True)))
        self.alt_wheel_zoom = tk.BooleanVar(value=bool(settings.get("alt_wheel_zoom", True)))
        self.allow_outside_canvas = tk.BooleanVar(value=bool(settings.get("allow_outside_canvas", False)))
        self.language_var = tk.StringVar(value="English" if settings.get("language") == "en" else "中文")
        self.default_project_dir = tk.StringVar(value=str(settings.get("default_project_dir") or ""))
        self.default_export_dir = tk.StringVar(value=str(settings.get("default_export_dir") or ""))
        self.shortcuts = {
            "new": tk.StringVar(value=str(settings.get("shortcut_new", "n"))),
            "modify": tk.StringVar(value=str(settings.get("shortcut_modify", "m"))),
            "delete": tk.StringVar(value=str(settings.get("shortcut_delete", "d"))),
            "drag": tk.StringVar(value=str(settings.get("shortcut_drag", "v"))),
            "transform": tk.StringVar(value=str(settings.get("shortcut_transform", "t"))),
            "none": tk.StringVar(value=str(settings.get("shortcut_none", "Escape"))),
        }

        ttk.Label(frame, text=_l(language, "界面语言", "Interface language"), style="Header.TLabel").grid(row=0, column=0, columnspan=3, sticky="w")
        ttk.Combobox(frame, textvariable=self.language_var, values=["中文", "English"], state="readonly", width=18).grid(row=1, column=0, columnspan=2, sticky="w", pady=(6, 12))

        ttk.Label(frame, text=_l(language, "画布操作", "Canvas controls"), style="Header.TLabel").grid(row=2, column=0, columnspan=3, sticky="w")
        ttk.Checkbutton(frame, text=_l(language, "按住鼠标中键拖拽画布", "Drag the canvas with the middle mouse button"), variable=self.middle_mouse_pan).grid(row=3, column=0, columnspan=3, sticky="w", pady=(8, 2))
        ttk.Checkbutton(frame, text=_l(language, "滚轮移动画布（滚轮上下，Shift+滚轮左右）", "Use the wheel to pan vertically; Shift+wheel pans horizontally"), variable=self.wheel_pan_enabled).grid(row=4, column=0, columnspan=3, sticky="w", pady=2)
        ttk.Checkbutton(frame, text=_l(language, "Alt + 鼠标滚轮缩放画布", "Alt + mouse wheel zooms the canvas"), variable=self.alt_wheel_zoom).grid(row=5, column=0, columnspan=3, sticky="w", pady=2)
        ttk.Label(
            frame,
            text=_l(
                language,
                "已知问题：Alt+滚轮缩放后，如果中键移动画布暂时失效，请先点一下界面，再按中键移动；处于全屏模式时通常不会出现这个问题。",
                "Known issue: after Alt+wheel zoom, click the interface once if middle-button panning temporarily stops. This normally does not occur in fullscreen mode.",
            ),
            style="Hint.TLabel",
            wraplength=560,
        ).grid(row=6, column=0, columnspan=3, sticky="w", pady=(2, 6))
        ttk.Checkbutton(frame, text=_l(language, "允许在画布边界外编辑和绘制", "Allow editing and drawing outside the canvas"), variable=self.allow_outside_canvas).grid(row=7, column=0, columnspan=3, sticky="w", pady=2)

        ttk.Label(frame, text=_l(language, "默认位置", "Default locations"), style="Header.TLabel").grid(row=8, column=0, columnspan=3, sticky="w", pady=(18, 4))
        ttk.Label(frame, text=_l(language, "项目默认保存位置", "Default project folder")).grid(row=9, column=0, sticky="w", pady=4)
        ttk.Entry(frame, textvariable=self.default_project_dir).grid(row=9, column=1, sticky="ew", pady=4)
        ttk.Button(frame, text=_l(language, "选择", "Choose"), command=lambda: self.choose_folder(self.default_project_dir)).grid(row=9, column=2, padx=(8, 0), pady=4)
        ttk.Label(frame, text=_l(language, "导出默认位置", "Default export folder")).grid(row=10, column=0, sticky="w", pady=4)
        ttk.Entry(frame, textvariable=self.default_export_dir).grid(row=10, column=1, sticky="ew", pady=4)
        ttk.Button(frame, text=_l(language, "选择", "Choose"), command=lambda: self.choose_folder(self.default_export_dir)).grid(row=10, column=2, padx=(8, 0), pady=4)

        ttk.Label(frame, text=_l(language, "操作快捷键", "Shortcuts"), style="Header.TLabel").grid(row=11, column=0, columnspan=3, sticky="w", pady=(18, 4))
        shortcut_rows = [
            (_l(language, "新建区域", "New region"), "new"),
            (_l(language, "增加选定区域", "Add to selected region"), "modify"),
            (_l(language, "减少选定区域", "Subtract from selected region"), "delete"),
            (_l(language, "拖拽区域", "Move region"), "drag"),
            (_l(language, "旋转缩放", "Rotate/resize"), "transform"),
            (_l(language, "无操作", "No operation"), "none"),
        ]
        for index, (label, key) in enumerate(shortcut_rows, start=12):
            ttk.Label(frame, text=label).grid(row=index, column=0, sticky="w", pady=4)
            ttk.Entry(frame, textvariable=self.shortcuts[key], width=16).grid(row=index, column=1, sticky="w", pady=4)

        ttk.Label(
            frame,
            text=_l(language, "提示：快捷键只在没有输入文字时生效。Esc 可以作为快捷键填写。", "Shortcuts only work when no text field is active. Esc may be used as a shortcut."),
            style="Hint.TLabel",
            wraplength=560,
        ).grid(row=18, column=0, columnspan=3, sticky="w", pady=(8, 0))

        footer = ttk.Frame(self, padding=(16, 8, 16, 14))
        footer.grid(row=1, column=0, sticky="ew")
        footer.columnconfigure(0, weight=1)
        self.settings_footer = footer
        buttons = ttk.Frame(footer)
        buttons.grid(row=0, column=1, sticky="e")
        ttk.Button(buttons, text=_l(language, "取消", "Cancel"), command=self.destroy).grid(row=0, column=0, padx=4)
        ttk.Button(buttons, text=_l(language, "保存", "Save"), command=self.on_save).grid(row=0, column=1, padx=4)
        self.update_idletasks()
        self.deiconify()
        self.lift()
        self.grab_set()
        if modal:
            self.wait_window(self)

    def choose_folder(self, variable: tk.StringVar) -> None:
        path = filedialog.askdirectory(parent=self, title=_l(self.language, "选择文件夹", "Choose folder"), initialdir=variable.get() or str(Path.home()))
        if path:
            variable.set(path)

    def on_save(self) -> None:
        self.result.update(
            {
                "middle_mouse_pan": self.middle_mouse_pan.get(),
                "wheel_pan_enabled": self.wheel_pan_enabled.get(),
                "alt_wheel_zoom": self.alt_wheel_zoom.get(),
                "allow_outside_canvas": self.allow_outside_canvas.get(),
                "language": "en" if self.language_var.get() == "English" else "zh",
                "default_project_dir": self.default_project_dir.get().strip(),
                "default_export_dir": self.default_export_dir.get().strip(),
            }
        )
        for mode, variable in self.shortcuts.items():
            self.result[f"shortcut_{mode}"] = variable.get().strip() or ("Escape" if mode == "none" else mode[0])
        self.saved = True
        self.destroy()


class StartupLanguageDialog(tk.Toplevel):
    def __init__(
        self,
        parent: tk.Tk,
        initial_language: str = "zh",
        modal: bool = True,
    ) -> None:
        super().__init__(parent)
        self.withdraw()
        self.result: Optional[str] = None
        self.title("选择语言 / Choose Language")
        self.resizable(False, False)
        self.transient(parent)
        self.protocol("WM_DELETE_WINDOW", self.destroy)

        width, height = 460, 230
        parent.update_idletasks()
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        x = max(8, min(screen_width - width - 16, parent.winfo_rootx() + (parent.winfo_width() - width) // 2))
        y = max(8, min(screen_height - height - 48, parent.winfo_rooty() + (parent.winfo_height() - height) // 2))
        self.geometry(f"{width}x{height}+{x}+{y}")

        frame = ttk.Frame(self, padding=24)
        frame.grid(row=0, column=0, sticky="nsew")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        ttk.Label(frame, text="请选择界面语言", style="Header.TLabel", anchor="center").grid(row=0, column=0, sticky="ew")
        ttk.Label(frame, text="Choose the interface language", anchor="center").grid(row=1, column=0, sticky="ew", pady=(4, 20))

        buttons = ttk.Frame(frame)
        buttons.grid(row=2, column=0)
        ttk.Button(buttons, text="中文", width=16, command=lambda: self.choose("zh")).grid(row=0, column=0, padx=8)
        ttk.Button(buttons, text="English", width=16, command=lambda: self.choose("en")).grid(row=0, column=1, padx=8)
        initial_text = "当前：中文" if initial_language != "en" else "Current: English"
        ttk.Label(frame, text=initial_text, style="Hint.TLabel", anchor="center").grid(row=3, column=0, sticky="ew", pady=(18, 0))

        self.update_idletasks()
        self.deiconify()
        self.lift()
        self.grab_set()
        if modal:
            self.wait_window(self)

    def choose(self, language: str) -> None:
        self.result = "en" if language == "en" else "zh"
        self.destroy()


class ExportDialog(tk.Toplevel):
    def __init__(self, parent: tk.Tk, language: str = "zh", modal: bool = True) -> None:
        super().__init__(parent)
        self.withdraw()
        self.language = language
        self.title(_l(language, "选择导出方式", "Choose export mode"))
        self.geometry("700x540" if language == "en" else "660x510")
        self.resizable(False, False)
        self.formats: List[str] = []
        self.generation_mode = "indirect"
        self.weak_txt_mode = "compact"
        self.preset = tk.StringVar(value="ai_reading")
        self.ai_mode = tk.StringVar(value="indirect")
        self.weak_mode = tk.StringVar(value="compact")
        description_key = "description_en" if language == "en" else "description"
        self.description = tk.StringVar(value=EXPORT_PRESETS["ai_reading"][description_key])
        self.transient(parent)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        frame = ttk.Frame(self, padding=16)
        frame.grid(row=0, column=0, sticky="nsew")
        frame.columnconfigure(0, weight=1)
        ttk.Label(frame, text=_l(language, "按使用方式选择导出预设", "Choose an export preset by use case"), style="Header.TLabel").grid(row=0, column=0, sticky="w")
        row = 1
        self.ai_mode_buttons: List[ttk.Radiobutton] = []
        self.weak_mode_buttons: List[ttk.Radiobutton] = []
        for key, preset in EXPORT_PRESETS.items():
            label = preset.get("label_en", preset["label"]) if language == "en" else preset["label"]
            ttk.Radiobutton(frame, text=label, variable=self.preset, value=key, command=self.update_description).grid(
                row=row, column=0, sticky="w", pady=4
            )
            row += 1
            if key == "ai_reading":
                mode_frame = ttk.Frame(frame, padding=(28, 0, 0, 4))
                mode_frame.grid(row=row, column=0, sticky="w")
                indirect = ttk.Radiobutton(
                    mode_frame,
                    text=_l(language, "间接型（默认）", "Indirect (default)"),
                    variable=self.ai_mode,
                    value="indirect",
                    command=self.update_description,
                )
                direct = ttk.Radiobutton(
                    mode_frame,
                    text=_l(language, "直接型", "Direct"),
                    variable=self.ai_mode,
                    value="direct",
                    command=self.update_description,
                )
                indirect.grid(row=0, column=0, sticky="w", padx=(0, 24))
                direct.grid(row=0, column=1, sticky="w")
                self.ai_mode_buttons.extend([indirect, direct])
                row += 1
            elif key == "weak_ai":
                weak_frame = ttk.Frame(frame, padding=(28, 0, 0, 4))
                weak_frame.grid(row=row, column=0, sticky="w")
                weak_modes = (
                    ("compact", _l(language, "精简直接型（默认）", "Compact direct (default)")),
                    ("indirect", _l(language, "间接型", "Indirect")),
                    ("direct", _l(language, "直接型", "Direct")),
                )
                for column, (value, text) in enumerate(weak_modes):
                    button = ttk.Radiobutton(
                        weak_frame,
                        text=text,
                        variable=self.weak_mode,
                        value=value,
                        command=self.update_description,
                    )
                    button.grid(row=0, column=column, sticky="w", padx=(0, 20))
                    self.weak_mode_buttons.append(button)
                row += 1
        ttk.Label(frame, textvariable=self.description, style="Hint.TLabel", wraplength=600 if language == "en" else 550).grid(row=row, column=0, sticky="ew", pady=(12, 4))
        row += 1
        ttk.Label(frame, text=_l(language, "程序会根据预设自动选择文件组合，减少判断成本。", "The application chooses the file set automatically."), style="Hint.TLabel").grid(row=row, column=0, sticky="w")
        row += 1
        buttons = ttk.Frame(frame)
        buttons.grid(row=row, column=0, sticky="e", pady=(18, 0))
        ttk.Button(buttons, text=_l(language, "取消", "Cancel"), command=self.destroy).grid(row=0, column=0, padx=4)
        ttk.Button(buttons, text=_l(language, "继续", "Continue"), command=self.on_ok).grid(row=0, column=1, padx=4)
        self.update_description()
        _show_centered_dialog(self, parent, 700 if language == "en" else 660, 540 if language == "en" else 510, grab=modal)
        if modal:
            self.wait_window(self)

    def update_description(self) -> None:
        key = "description_en" if self.language == "en" else "description"
        preset = self.preset.get()
        description = EXPORT_PRESETS[preset][key]
        if preset == "ai_reading":
            mode_description = _l(
                self.language,
                "间接型：先用本地代码生成程序化底图，停止并等待“继续”。"
                if self.ai_mode.get() == "indirect"
                else "直接型：允许 AI 直接生成最终图像，但全部构图关系仍为强制要求。",
                "Indirect: create a programmatic underpaint first, stop, and wait for “Continue”."
                if self.ai_mode.get() == "indirect"
                else "Direct: allow immediate final image generation while keeping every composition rule mandatory.",
            )
            description = f"{description}\n{mode_description}"
        elif preset == "weak_ai":
            weak_descriptions = {
                "compact": _l(
                    self.language,
                    "精简直接型：保留最关键关系并直接要求出图，适合上下文很弱的模型。",
                    "Compact direct: keep only the most important relationships and request the image immediately.",
                ),
                "indirect": _l(
                    self.language,
                    "间接型：TXT 使用与普通间接型相同的两阶段门禁，但仍只配一张 PNG。",
                    "Indirect: the TXT uses the same two-stage gate as the normal indirect mode, paired only with one PNG.",
                ),
                "direct": _l(
                    self.language,
                    "直接型：TXT 明确授权直接生图，并强化全部构图关系。",
                    "Direct: the TXT explicitly authorizes immediate generation while enforcing all composition rules.",
                ),
            }
            description = f"{description}\n{weak_descriptions[self.weak_mode.get()]}"
        self.description.set(description)
        for button in self.ai_mode_buttons:
            button.state(["!disabled"] if preset == "ai_reading" else ["disabled"])
        for button in self.weak_mode_buttons:
            button.state(["!disabled"] if preset == "weak_ai" else ["disabled"])

    def on_ok(self) -> None:
        preset = self.preset.get()
        self.formats = list(EXPORT_PRESETS[preset]["formats"])
        self.generation_mode = self.ai_mode.get() if preset == "ai_reading" else "indirect"
        self.weak_txt_mode = self.weak_mode.get() if preset == "weak_ai" else "compact"
        self.destroy()


class AboutDialog(tk.Toplevel):
    def __init__(self, parent: tk.Tk, language: str = "zh", modal: bool = True) -> None:
        super().__init__(parent)
        self.withdraw()
        self.title(_l(language, "关于 AI Drawing Copilot", "About AI Drawing Copilot"))
        self.geometry("620x430")
        self.resizable(False, False)
        self.transient(parent)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        frame = ttk.Frame(self, padding=18)
        frame.grid(row=0, column=0, sticky="nsew")
        frame.columnconfigure(0, weight=1)
        ttk.Label(frame, text=f"{APP_NAME} {APP_VERSION}", style="Header.TLabel").grid(row=0, column=0, sticky="w")
        paragraphs = (
            [
                "这是一个面向 AI 作画前期构图的本地工具：先组织结构、区域、层级和自然语言语义，再导出给 AI 或自动化工作流。",
                "程序会先计算区域之间的左右、上下、包含、交叠、邻接、图层与长条走向关系，减少生图模型从颜色图猜位置的负担。",
                "普通生图模型并不可靠地执行像素坐标，因此当前版本将自然语言关系作为主要交接方式，矢量数据作为辅助校验。",
                "隐私说明：当前版本不联网，项目、设置和导出文件都保存在本机。",
            ]
            if language != "en"
            else [
                "A local pre-production tool for organizing composition, regions, layers, and natural-language semantics before handing work to image AI or automation.",
                "The application computes left/right, above/below, containment, overlap, adjacency, layer, and elongated-path relationships so the image model does not have to guess them from colors.",
                "Ordinary image generators do not reliably execute pixel coordinates, so natural-language relationships are the primary handoff and vector data is an auxiliary check.",
                "Privacy: this version does not connect to the internet; projects, settings, and exports remain local.",
            ]
        )
        for index, paragraph in enumerate(paragraphs, start=1):
            ttk.Label(frame, text=paragraph, wraplength=560, justify="left").grid(row=index, column=0, sticky="ew", pady=(12 if index == 1 else 8, 0))
        ttk.Button(frame, text=_l(language, "关闭", "Close"), command=self.destroy).grid(row=6, column=0, sticky="e", pady=(20, 0))
        _show_centered_dialog(self, parent, 620, 430, grab=modal)
        if modal:
            self.wait_window(self)


class Tooltip:
    def __init__(self, widget: tk.Widget, text: str) -> None:
        self.widget = widget
        self.text = text
        self.tip: Optional[tk.Toplevel] = None
        widget.bind("<Enter>", self.show)
        widget.bind("<Leave>", self.hide)

    def show(self, _event: tk.Event) -> None:
        if self.tip:
            return
        x = self.widget.winfo_rootx() + 20
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 8
        self.tip = tk.Toplevel(self.widget)
        self.tip.wm_overrideredirect(True)
        self.tip.wm_geometry(f"+{x}+{y}")
        label = ttk.Label(self.tip, text=self.text, padding=(8, 5), relief="solid", wraplength=260)
        label.grid(row=0, column=0)

    def hide(self, _event: tk.Event) -> None:
        if self.tip:
            self.tip.destroy()
            self.tip = None


def run() -> None:
    app = DrawingCopilotApp()
    if startup_language_required(app.settings):
        dialog = StartupLanguageDialog(app, app.language)
        if dialog.result is None:
            app.destroy()
            return
        selected_language = dialog.result
        category_key = category_from_label(app.default_category.get())
        app.settings["language"] = selected_language
        save_settings(app.settings)
        if selected_language != app.language:
            app.language = selected_language
            app.default_category.set(display_label(category_key, app.language))
            app.edit_mode_display.set(app._edit_mode_label(app.edit_mode.get()))
            app.draw_tool_display.set(app._draw_tool_label(app.draw_tool.get()))
            app._rebuild_localized_ui()
        app.status_text.set(
            _l(
                app.language,
                "已记住中文界面；以后可在设置中更改。",
                "English has been remembered; it can be changed later in Settings.",
            )
        )
    app.mainloop()
