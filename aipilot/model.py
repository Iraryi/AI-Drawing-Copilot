# -*- coding: utf-8 -*-
from __future__ import annotations

import colorsys
from dataclasses import dataclass, field
from datetime import datetime
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import uuid

from PIL import Image, ImageDraw, ImageFont

from . import APP_VERSION
from .relationships import (
    analyze_project_relationships,
    render_first_pass_prompt,
    render_relationship_markdown,
    render_weak_ai_prompt,
)


PROJECT_FORMAT_VERSION = "ai-drawing-copilot-project-v1"
EXPORT_FORMAT_VERSION = "ai-drawing-copilot-export-v3"


CONSTRAINT_TYPES: Dict[str, Dict[str, str]] = {
    "rough": {
        "label": "大致范围",
        "label_en": "General area",
        "export_hint": "区域位置允许小幅调整，重点遵守构图关系和主体归属。",
        "export_hint_en": "The area is a flexible composition guide. Preserve the intended subject and relationships rather than treating the boundary as exact pixels.",
    },
    "larger_than_prompt": {
        "label": "比需求范围大",
        "label_en": "Outer safe frame",
        "export_hint": "这是安全外框，真实内容应完全落在其中，可以比框小。",
        "export_hint_en": "This is a safe outer frame. The real subject should stay inside it and may be smaller.",
    },
    "smaller_than_prompt": {
        "label": "比需求范围小",
        "label_en": "Inner core area",
        "export_hint": "这是核心区域，真实内容可以略微超出，但中心和主要结构应留在其中。",
        "export_hint_en": "This is the core area. The real subject may extend slightly beyond it, but its center and main structure should stay here.",
    },
    "avoid": {
        "label": "禁止生成内容",
        "label_en": "Avoid content",
        "export_hint": "该区域不得生成指定内容，也不要把相邻主体扩展到这里。",
        "export_hint_en": "Specified content should not appear in this area, and adjacent subjects should not expand into it.",
    },
    "reference_only": {
        "label": "参考关系",
        "label_en": "Relationship reference",
        "export_hint": "该区域用于说明比例、朝向或相对位置，不要求完全像素锁定。",
        "export_hint_en": "This area describes scale, direction, or relative position. It is not a pixel lock.",
    },
}

DEPRECATED_CONSTRAINT_TYPES = {"exact_pixel", "must_include", "keep_empty"}


DEFAULT_COLORS = [
    "#E84A5F",
    "#2A9D8F",
    "#F4A261",
    "#457B9D",
    "#8E44AD",
    "#E9C46A",
    "#1D3557",
    "#FF7A59",
    "#43AA8B",
    "#577590",
]


def new_id(prefix: str = "region") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def clamp_int(value: Any, minimum: int, maximum: int) -> int:
    try:
        number = int(round(float(value)))
    except (TypeError, ValueError):
        number = minimum
    return max(minimum, min(maximum, number))


def display_label(category: str, language: str = "zh") -> str:
    info = CONSTRAINT_TYPES.get(category, CONSTRAINT_TYPES["rough"])
    if language == "en":
        return info.get("label_en", info["label"])
    return info["label"]


def category_from_label(label: str) -> str:
    for key, info in CONSTRAINT_TYPES.items():
        if info["label"] == label or info.get("label_en") == label:
            return key
    return "rough"


def sanitize_points(points: Any) -> List[List[int]]:
    clean: List[List[int]] = []
    if not isinstance(points, list):
        return clean
    for point in points:
        if not isinstance(point, (list, tuple)) or len(point) < 2:
            continue
        clean.append([clamp_int(point[0], -100000, 100000), clamp_int(point[1], -100000, 100000)])
    return clean


def sanitize_holes(holes: Any) -> List[List[List[int]]]:
    clean: List[List[List[int]]] = []
    if not isinstance(holes, list):
        return clean
    for hole in holes:
        points = sanitize_points(hole)
        if len(points) >= 3:
            clean.append(points)
    return clean


def sanitize_parts(parts: Any) -> List[Dict[str, Any]]:
    clean: List[Dict[str, Any]] = []
    if not isinstance(parts, list):
        return clean
    for part in parts:
        if isinstance(part, dict):
            points = sanitize_points(part.get("points", []))
            holes = sanitize_holes(part.get("holes", []))
        else:
            points = sanitize_points(part)
            holes = []
        if len(points) >= 3:
            clean.append({"points": points, "holes": holes})
    return clean


def bbox_from_points(points: List[List[int]]) -> Tuple[int, int, int, int]:
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    left = min(xs)
    top = min(ys)
    right = max(xs)
    bottom = max(ys)
    return left, top, max(1, right - left), max(1, bottom - top)


@dataclass
class Region:
    name: str
    x: int
    y: int
    width: int
    height: int
    category: str = "rough"
    description: str = ""
    standard_prompt: str = ""
    ai_notes: str = ""
    priority: int = 3
    color: str = "#E84A5F"
    region_id: str = field(default_factory=new_id)
    shape: str = "rectangle"
    points: List[List[int]] = field(default_factory=list)
    filled: bool = True
    holes: List[List[List[int]]] = field(default_factory=list)
    parts: List[Dict[str, Any]] = field(default_factory=list)

    def normalize(self) -> None:
        if self.category in DEPRECATED_CONSTRAINT_TYPES or self.category not in CONSTRAINT_TYPES:
            self.category = "rough"
        self.points = sanitize_points(self.points)
        self.holes = sanitize_holes(self.holes)
        self.parts = sanitize_parts(self.parts)
        if self.shape == "polygon" and len(self.points) >= 3:
            all_points = [point for part in self.pixel_parts(raw=True) for point in part["points"]]
            self.x, self.y, self.width, self.height = bbox_from_points(all_points)
            return
        self.shape = "rectangle"
        self.points = []
        self.holes = []
        self.parts = []
        if self.width < 0:
            self.x += self.width
            self.width = abs(self.width)
        if self.height < 0:
            self.y += self.height
            self.height = abs(self.height)
        self.width = max(1, int(self.width))
        self.height = max(1, int(self.height))
        self.x = int(self.x)
        self.y = int(self.y)

    def set_bbox(self, x: int, y: int, width: int, height: int) -> None:
        self.normalize()
        x = int(x)
        y = int(y)
        width = max(1, int(width))
        height = max(1, int(height))
        if self.shape == "polygon" and len(self.points) >= 3:
            old_x, old_y, old_w, old_h = self.x, self.y, max(1, self.width), max(1, self.height)
            scaled: List[List[int]] = []
            for point_x, point_y in self.points:
                new_x = x + round((point_x - old_x) * width / old_w)
                new_y = y + round((point_y - old_y) * height / old_h)
                scaled.append([int(new_x), int(new_y)])
            self.points = scaled
            scaled_holes: List[List[List[int]]] = []
            for hole in self.holes:
                scaled_hole: List[List[int]] = []
                for point_x, point_y in hole:
                    new_x = x + round((point_x - old_x) * width / old_w)
                    new_y = y + round((point_y - old_y) * height / old_h)
                    scaled_hole.append([int(new_x), int(new_y)])
                scaled_holes.append(scaled_hole)
            self.holes = scaled_holes
            scaled_parts: List[Dict[str, Any]] = []
            for part in self.parts:
                scaled_part_points: List[List[int]] = []
                for point_x, point_y in part.get("points", []):
                    new_x = x + round((point_x - old_x) * width / old_w)
                    new_y = y + round((point_y - old_y) * height / old_h)
                    scaled_part_points.append([int(new_x), int(new_y)])
                scaled_part_holes: List[List[List[int]]] = []
                for hole in part.get("holes", []):
                    scaled_part_hole: List[List[int]] = []
                    for point_x, point_y in hole:
                        new_x = x + round((point_x - old_x) * width / old_w)
                        new_y = y + round((point_y - old_y) * height / old_h)
                        scaled_part_hole.append([int(new_x), int(new_y)])
                    scaled_part_holes.append(scaled_part_hole)
                scaled_parts.append({"points": scaled_part_points, "holes": scaled_part_holes})
            self.parts = scaled_parts
            all_points = [point for part in self.pixel_parts(raw=True) for point in part["points"]]
            self.x, self.y, self.width, self.height = bbox_from_points(all_points)
            return
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.normalize()

    def move_by(self, dx: int, dy: int, canvas_width: int, canvas_height: int) -> None:
        self.normalize()
        dx = int(dx)
        dy = int(dy)
        if self.shape == "polygon" and len(self.points) >= 3:
            self.points = [[point_x + dx, point_y + dy] for point_x, point_y in self.points]
            self.holes = [[[point_x + dx, point_y + dy] for point_x, point_y in hole] for hole in self.holes]
            self.parts = [
                {
                    "points": [[point_x + dx, point_y + dy] for point_x, point_y in part.get("points", [])],
                    "holes": [
                        [[point_x + dx, point_y + dy] for point_x, point_y in hole]
                        for hole in part.get("holes", [])
                    ],
                }
                for part in self.parts
            ]
        else:
            self.x += dx
            self.y += dy
        self.normalize()

    def pixel_bbox(self) -> List[int]:
        self.normalize()
        return [self.x, self.y, self.width, self.height]

    def normalized_bbox(self, canvas_width: int, canvas_height: int) -> List[float]:
        self.normalize()
        return [
            round(self.x / canvas_width, 6),
            round(self.y / canvas_height, 6),
            round(self.width / canvas_width, 6),
            round(self.height / canvas_height, 6),
        ]

    def pixel_points(self) -> List[List[int]]:
        self.normalize()
        if self.shape != "polygon":
            return [
                [self.x, self.y],
                [self.x + self.width, self.y],
                [self.x + self.width, self.y + self.height],
                [self.x, self.y + self.height],
            ]
        return [point[:] for point in self.points]

    def pixel_holes(self) -> List[List[List[int]]]:
        self.normalize()
        return [[point[:] for point in hole] for hole in self.holes] if self.shape == "polygon" else []

    def pixel_parts(self, raw: bool = False) -> List[Dict[str, Any]]:
        if not raw:
            self.normalize()
        if self.shape != "polygon" or len(self.points) < 3:
            return [{"points": self.pixel_points(), "holes": []}] if not raw else []
        parts = [{"points": [point[:] for point in self.points], "holes": [[point[:] for point in hole] for hole in self.holes]}]
        parts.extend(
            {
                "points": [point[:] for point in part.get("points", [])],
                "holes": [[point[:] for point in hole] for hole in part.get("holes", [])],
            }
            for part in self.parts
            if len(part.get("points", [])) >= 3
        )
        return parts

    def normalized_points(self, canvas_width: int, canvas_height: int) -> List[List[float]]:
        return [
            [round(point_x / canvas_width, 6), round(point_y / canvas_height, 6)]
            for point_x, point_y in self.pixel_points()
        ]

    def normalized_holes(self, canvas_width: int, canvas_height: int) -> List[List[List[float]]]:
        return [
            [[round(point_x / canvas_width, 6), round(point_y / canvas_height, 6)] for point_x, point_y in hole]
            for hole in self.pixel_holes()
        ]

    def normalized_parts(self, canvas_width: int, canvas_height: int) -> List[Dict[str, Any]]:
        return [
            {
                "points": [[round(point_x / canvas_width, 6), round(point_y / canvas_height, 6)] for point_x, point_y in part["points"]],
                "holes": [
                    [[round(point_x / canvas_width, 6), round(point_y / canvas_height, 6)] for point_x, point_y in hole]
                    for hole in part.get("holes", [])
                ],
            }
            for part in self.pixel_parts()
        ]

    def to_dict(self) -> Dict[str, Any]:
        self.normalize()
        return {
            "id": self.region_id,
            "name": self.name,
            "shape": self.shape,
            "category": self.category,
            "category_label": display_label(self.category),
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
            "points": self.pixel_points() if self.shape == "polygon" else [],
            "holes": self.pixel_holes() if self.shape == "polygon" else [],
            "parts": self.pixel_parts()[1:] if self.shape == "polygon" else [],
            "filled": self.filled,
            "description": self.description,
            "natural_language": self.description,
            "standard_prompt": self.standard_prompt,
            "ai_notes": self.ai_notes,
            "notes": self.ai_notes,
            "priority": self.priority,
            "color": self.color,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Region":
        pixel_bbox = data.get("pixel_bbox")
        if isinstance(pixel_bbox, (list, tuple)) and len(pixel_bbox) >= 4:
            default_x, default_y, default_width, default_height = pixel_bbox[:4]
        else:
            default_x, default_y, default_width, default_height = 0, 0, 1, 1
        exported_parts = sanitize_parts(data.get("pixel_parts", []))
        if exported_parts:
            source_points = exported_parts[0]["points"]
            source_holes = exported_parts[0]["holes"]
            source_parts = exported_parts[1:]
        else:
            source_points = data.get("pixel_points", data.get("points", []))
            source_holes = data.get("pixel_holes", data.get("holes", []))
            source_parts = data.get("parts", [])
        region = cls(
            region_id=str(data.get("id") or data.get("region_id") or new_id()),
            name=str(data.get("name") or "未命名区域"),
            shape=str(data.get("shape") or "rectangle"),
            category=str(data.get("category") or "rough"),
            x=clamp_int(data.get("x", default_x), -100000, 100000),
            y=clamp_int(data.get("y", default_y), -100000, 100000),
            width=clamp_int(data.get("width", default_width), 1, 100000),
            height=clamp_int(data.get("height", default_height), 1, 100000),
            description=str(data.get("natural_language") or data.get("description") or ""),
            standard_prompt=str(data.get("standard_prompt") or data.get("standardized_prompt") or ""),
            ai_notes=str(data.get("notes") or data.get("ai_notes") or ""),
            priority=clamp_int(data.get("priority", 3), 1, 5),
            color=str(data.get("color") or "#E84A5F"),
            points=sanitize_points(source_points),
            filled=bool(data.get("filled", True)),
            holes=sanitize_holes(source_holes),
            parts=sanitize_parts(source_parts),
        )
        if region.category in DEPRECATED_CONSTRAINT_TYPES or region.category not in CONSTRAINT_TYPES:
            region.category = "rough"
        region.normalize()
        return region


def _points_bbox(points: List[List[int]]) -> List[int]:
    if not points:
        return [0, 0, 0, 0]
    x, y, width, height = bbox_from_points(points)
    return [x, y, width, height]


def _closed(points: List[List[int]]) -> List[List[int]]:
    if not points:
        return []
    closed = [point[:] for point in points]
    if closed[0] != closed[-1]:
        closed.append(closed[0][:])
    return closed


def _svg_subpath(points: List[List[int]]) -> str:
    closed = _closed(points)
    if not closed:
        return ""
    first = closed[0]
    rest = closed[1:]
    return "M " + f"{first[0]} {first[1]} " + " ".join(f"L {point[0]} {point[1]}" for point in rest) + " Z"


def _region_svg_path(region: Region) -> str:
    path_parts: List[str] = []
    for part in region.pixel_parts():
        path_parts.append(_svg_subpath(part["points"]))
        for hole in part.get("holes", []):
            path_parts.append(_svg_subpath(hole))
    return " ".join(part for part in path_parts if part)


def _dense_segment_points(start: List[int], end: List[int]) -> List[List[int]]:
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    steps = max(abs(dx), abs(dy), 1)
    points: List[List[int]] = []
    for index in range(steps + 1):
        ratio = index / steps
        points.append([int(round(start[0] + dx * ratio)), int(round(start[1] + dy * ratio))])
    return points


def _edge_trace(points: List[List[int]]) -> List[List[int]]:
    closed = _closed(points)
    if len(closed) < 2:
        return []
    trace: List[List[int]] = []
    for index in range(len(closed) - 1):
        segment = _dense_segment_points(closed[index], closed[index + 1])
        if trace and segment:
            segment = segment[1:]
        trace.extend(segment)
    deduped: List[List[int]] = []
    for point in trace:
        if not deduped or deduped[-1] != point:
            deduped.append(point)
    return deduped


def _region_vector_model(region: Region, include_edge_trace: bool = False) -> Dict[str, Any]:
    parts: List[Dict[str, Any]] = []
    for index, part in enumerate(region.pixel_parts(), start=1):
        exterior = part["points"]
        holes = part.get("holes", [])
        vector_part: Dict[str, Any] = {
            "part_index": index,
            "closed": True,
            "bbox": _points_bbox(exterior),
            "vertex_count": len(exterior),
            "exterior": [point[:] for point in exterior],
            "holes": [[point[:] for point in hole] for hole in holes],
        }
        if include_edge_trace:
            vector_part["edge_trace_1px"] = _edge_trace(exterior)
            vector_part["hole_edge_traces_1px"] = [_edge_trace(hole) for hole in holes]
        parts.append(vector_part)
    return {
        "type": "compound_vector_region",
        "coordinate_unit": "pixel",
        "fill_rule": "evenodd",
        "svg_path": _region_svg_path(region),
        "parts": parts,
    }


def _region_mask_spans(region: Region, canvas_width: int, canvas_height: int) -> Dict[str, Any]:
    region.normalize()
    x, y, width, height = region.pixel_bbox()
    left = max(0, x)
    top = max(0, y)
    right = min(canvas_width, x + width)
    bottom = min(canvas_height, y + height)
    if right <= left or bottom <= top:
        return {
            "type": "filled_pixel_spans",
            "bbox": [left, top, 0, 0],
            "span_order": ["y", "x_start", "x_end_inclusive"],
            "rows": [],
        }
    mask = Image.new("L", (right - left, bottom - top), 0)
    draw = ImageDraw.Draw(mask)
    if region.shape == "polygon":
        for part in region.pixel_parts():
            exterior = [(point_x - left, point_y - top) for point_x, point_y in part["points"]]
            if len(exterior) >= 3:
                draw.polygon(exterior, fill=255)
            for hole in part.get("holes", []):
                hole_points = [(point_x - left, point_y - top) for point_x, point_y in hole]
                if len(hole_points) >= 3:
                    draw.polygon(hole_points, fill=0)
    else:
        draw.rectangle([region.x - left, region.y - top, region.x + region.width - 1 - left, region.y + region.height - 1 - top], fill=255)

    pixels = mask.load()
    rows: List[List[Any]] = []
    for local_y in range(mask.height):
        intervals: List[List[int]] = []
        run_start: Optional[int] = None
        for local_x in range(mask.width):
            covered = pixels[local_x, local_y] > 0
            if covered and run_start is None:
                run_start = local_x
            elif not covered and run_start is not None:
                intervals.append([left + run_start, left + local_x - 1])
                run_start = None
        if run_start is not None:
            intervals.append([left + run_start, left + mask.width - 1])
        if intervals:
            rows.append([top + local_y, intervals])
    return {
        "type": "filled_pixel_spans",
        "bbox": [left, top, right - left, bottom - top],
        "span_order": ["y", "x_start", "x_end_inclusive"],
        "rows": rows,
    }


def _region_geometry_contract(region: Region, language: str = "zh") -> Dict[str, str]:
    english = language == "en"
    if region.category == "rough":
        return {
            "mode": "natural_language_layout_guide",
            "use": "This is a composition guide. Prioritize natural-language semantics and relationships." if english else "这是构图参考范围。普通生图 AI 往往更依赖自然语言，请优先读取自然语言、关系说明和视觉参考。",
            "tolerance": "Small shifts or deformation are allowed; preserve relationships, occlusion, and subject ownership." if english else "允许偏移或变形；重点保持区域之间的相互关系、遮挡关系和主体归属。",
        }
    if region.category == "larger_than_prompt":
        return {
            "mode": "outer_safe_frame",
            "use": "Content should stay inside this range, but the real subject may be smaller." if english else "内容应落在该范围内，但真实主体可以比区域小。",
            "tolerance": "Shrinking is allowed; leaving the outer frame is discouraged." if english else "允许缩小，不建议越出外框。",
        }
    if region.category == "smaller_than_prompt":
        return {
            "mode": "inner_core_frame",
            "use": "This is the core position. Content may extend slightly beyond it while preserving the center." if english else "这是核心位置，真实内容可略微超过，但中心和主体关系应保持。",
            "tolerance": "A small amount of outward extension is allowed." if english else "允许少量外扩。",
        }
    if region.category == "avoid":
        return {
            "mode": "hard_semantic_rule",
            "use": "This is a strong semantic exclusion rule." if english else "这是强语义约束，必须按类别规则执行。",
            "tolerance": "Do not reverse the semantic rule. Treat geometry as a region guide, not a pixel-perfect mask." if english else "语义不允许反向违背；几何边界按区域形状参考，不要把它误当成像素级遮罩。",
        }
    return {
        "mode": "relationship_reference",
        "use": "Use this to describe scale, orientation, or relative position." if english else "用于说明比例、朝向或相对位置。",
        "tolerance": "Pixel locking is not required." if english else "不要求像素锁定。",
    }


def _region_export_models(region: Region, canvas_width: int, canvas_height: int, language: str = "zh") -> Dict[str, Any]:
    return {
        "geometry_contract": _region_geometry_contract(region, language),
        "vector_model": _region_vector_model(region, include_edge_trace=False),
        "pixel_mask_model": {
            "type": "not_emitted_for_text_guided_generation",
            "reason": (
                "Ordinary image generators are not treated as pixel-level executors. Use natural-language relationships for composition and vector_model for automation or checking."
                if language == "en"
                else "当前版本不再把普通生图 AI 当作像素级执行器；请用自然语言关系说明引导构图，用 vector_model 给自动化工作流或人工校验。"
            ),
        },
    }


@dataclass
class Project:
    title: str = "未命名构图"
    canvas_width: int = 1024
    canvas_height: int = 1024
    global_prompt: str = ""
    negative_prompt: str = ""
    background_path: str = ""
    regions: List[Region] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))

    def touch(self) -> None:
        self.updated_at = datetime.now().isoformat(timespec="seconds")

    def add_region(self, region: Region) -> None:
        region.normalize()
        self.regions.append(region)
        self.touch()

    def remove_region(self, region_id: str) -> None:
        self.regions = [region for region in self.regions if region.region_id != region_id]
        self.touch()

    def get_region(self, region_id: Optional[str]) -> Optional[Region]:
        for region in self.regions:
            if region.region_id == region_id:
                return region
        return None

    def next_color(self) -> str:
        return DEFAULT_COLORS[len(self.regions) % len(DEFAULT_COLORS)]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "format": PROJECT_FORMAT_VERSION,
            "app_version": APP_VERSION,
            "title": self.title,
            "canvas": {"width": self.canvas_width, "height": self.canvas_height},
            "global_prompt": self.global_prompt,
            "negative_prompt": self.negative_prompt,
            "background_path": self.background_path,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "regions": [region.to_dict() for region in self.regions],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Project":
        canvas = data.get("canvas") or {}
        coordinate_system = data.get("coordinate_system") or {}
        return cls(
            title=str(data.get("title") or "未命名构图"),
            canvas_width=clamp_int(
                canvas.get("width", data.get("canvas_width", coordinate_system.get("canvas_width", 1024))),
                64,
                12000,
            ),
            canvas_height=clamp_int(
                canvas.get("height", data.get("canvas_height", coordinate_system.get("canvas_height", 1024))),
                64,
                12000,
            ),
            global_prompt=str(data.get("global_prompt") or ""),
            negative_prompt=str(data.get("negative_prompt") or ""),
            background_path=str(data.get("background_path") or ""),
            created_at=str(data.get("created_at") or datetime.now().isoformat(timespec="seconds")),
            updated_at=str(data.get("updated_at") or datetime.now().isoformat(timespec="seconds")),
            regions=[Region.from_dict(item) for item in data.get("regions", [])],
        )

    def to_ai_spec(self, language: str = "zh") -> Dict[str, Any]:
        english = language == "en"
        return {
            "format": EXPORT_FORMAT_VERSION,
            "app_version": APP_VERSION,
            "title": self.title,
            "created_at": self.created_at,
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "coordinate_system": {
                "origin": "top-left",
                "unit": "pixel",
                "canvas_width": self.canvas_width,
                "canvas_height": self.canvas_height,
                "bbox_order": ["x", "y", "width", "height"],
                "polygon_point_order": ["x", "y"],
                "normalized_bbox_range": "0.0-1.0",
            },
            "region_semantics": {
                "type": "semantic_masks",
                "occlusion_rule": (
                    "Regions represent semantic coverage, not final visible pixels. Upper regions do not subtract from lower semantic regions."
                    if english
                    else "区域表示语义覆盖范围，不是最终可见像素。上层区域不会自动从下层区域中扣除；如果地面区域覆盖了整块地面，即使人物区域在其上方，人物脚下的位置仍然属于地面。"
                ),
                "layer_order": (
                    "regions are ordered back-to-front; a larger layer_index is visually higher without changing other semantic coverage."
                    if english
                    else "regions 按从底到顶排列；layer_index 越大，在视觉参考图中越靠上，但不改变其他区域的语义范围。"
                ),
            },
            "category_rules": {
                key: {
                    "label": info.get("label_en", info["label"]) if english else info["label"],
                    "rule": info.get("export_hint_en", info["export_hint"]) if english else info["export_hint"],
                }
                for key, info in CONSTRAINT_TYPES.items()
            },
            "global_prompt": self.global_prompt,
            "negative_prompt": self.negative_prompt,
            "regions": [
                {
                    "id": region.region_id,
                    "name": region.name,
                    "layer_index": index,
                    "layer_order": "back_to_front",
                    "shape": region.shape,
                    "category": region.category,
                    "category_label": display_label(region.category, language),
                    "category_rule": CONSTRAINT_TYPES.get(region.category, CONSTRAINT_TYPES["rough"]).get(
                        "export_hint_en" if english else "export_hint",
                        CONSTRAINT_TYPES["rough"]["export_hint"],
                    ),
                    "priority": region.priority,
                    "pixel_bbox": region.pixel_bbox(),
                    "normalized_bbox": region.normalized_bbox(self.canvas_width, self.canvas_height),
                    "pixel_points": region.pixel_points(),
                    "normalized_points": region.normalized_points(self.canvas_width, self.canvas_height),
                    "pixel_holes": region.pixel_holes(),
                    "normalized_holes": region.normalized_holes(self.canvas_width, self.canvas_height),
                    "pixel_parts": region.pixel_parts(),
                    "normalized_parts": region.normalized_parts(self.canvas_width, self.canvas_height),
                    **_region_export_models(region, self.canvas_width, self.canvas_height, language),
                    "filled": region.filled,
                    "mask_color": region.color,
                    "natural_language": region.description,
                    "standard_prompt": region.standard_prompt,
                    "notes": region.ai_notes,
                    "description": region.description,
                    "ai_notes": region.ai_notes,
                }
                for index, region in enumerate(self.regions, start=1)
            ],
        }


def save_project(project: Project, path: Path) -> None:
    project.touch()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(project.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")


def load_project(path: Path) -> Project:
    data = json.loads(path.read_text(encoding="utf-8"))
    return Project.from_dict(data)


def export_json(project: Project, path: Path, language: str = "zh") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(project.to_ai_spec(language), ensure_ascii=False, indent=2), encoding="utf-8")


def export_relationships(
    project: Project,
    json_path: Path,
    markdown_path: Path,
    language: str = "zh",
    analysis: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    analysis = analysis or analyze_project_relationships(project, language)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(analysis, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path.write_text(render_relationship_markdown(project, analysis, language), encoding="utf-8")
    return analysis


def export_first_pass_prompt(
    project: Project,
    path: Path,
    artifact_paths: Dict[str, Path],
    language: str = "zh",
    analysis: Optional[Dict[str, Any]] = None,
    generation_mode: str = "indirect",
) -> None:
    analysis = analysis or analyze_project_relationships(project, language)
    artifact_names = {name: item.name for name, item in artifact_paths.items()}
    artifact_names["index_legend"] = "\n".join(
        f"- {index}. {region.name}: {color}"
        for index, (region, color) in enumerate(
            zip(project.regions, _visual_index_colors(len(project.regions))),
            start=1,
        )
    ) or "- (no regions)"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        render_first_pass_prompt(project, analysis, artifact_names, language, generation_mode),
        encoding="utf-8",
    )


def export_weak_ai_prompt(
    project: Project,
    path: Path,
    png_path: Path,
    language: str = "zh",
    analysis: Optional[Dict[str, Any]] = None,
    mode: str = "compact",
) -> None:
    analysis = analysis or analyze_project_relationships(project, language)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        render_weak_ai_prompt(project, analysis, png_path.name, language, mode),
        encoding="utf-8",
    )


def _format_points_block(points: List[List[int]], prefix: str = "") -> List[str]:
    return [f"{prefix}{index:05d}: x={point[0]}, y={point[1]}" for index, point in enumerate(points, start=1)]


def _format_scanline_block(mask_model: Dict[str, Any]) -> List[str]:
    lines: List[str] = []
    for index, row in enumerate(mask_model.get("rows", []), start=1):
        y_value = row[0]
        spans = "; ".join(f"x={start}-{end}" for start, end in row[1])
        lines.append(f"{index:05d}: y={y_value}: {spans}")
    return lines


def export_markdown(project: Project, path: Path, language: str = "zh") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    language = "en" if language == "en" else "zh"
    english = language == "en"
    lines = [
        f"# {project.title} - {'AI composition instructions' if english else 'AI 构图说明'}",
        "",
        (
            "This file explains region semantics and geometry. Ordinary image generators should prioritize natural-language relationships; vector data is retained for automation and checking."
            if english
            else "这份文件说明区域语义与几何。普通生图模型应优先理解自然语言关系；矢量数据保留给自动化流程和人工校验。"
        ),
        (
            "The origin is top-left and the unit is pixels. A bounding box is only a quick locator and never replaces the real polygon."
            if english
            else "坐标原点在左上角，单位为像素。bbox 只用于快速定位，不能替代真实多边形。"
        ),
        "",
        "## Canvas" if english else "## 画布",
        "",
        f"- {'Size' if english else '尺寸'}: {project.canvas_width} x {project.canvas_height} px",
        f"- {'Origin: top-left' if english else '坐标原点：左上角'}",
        "",
        "## Region semantics" if english else "## 区域语义",
        "",
        (
            "Regions are semantic coverage areas, not final visible pixels. An upper layer does not subtract from a lower semantic region."
            if english
            else "区域表示语义覆盖范围，不是最终可见像素。上层区域不会自动从下层区域中扣除。"
        ),
        (
            "For example, a person can visually cover the ground while the position beneath the person still belongs to the ground region."
            if english
            else "例如：人物可以在视觉上挡住地面，但人物脚下的位置仍然属于地面区域。"
        ),
        "",
        "## Category rules" if english else "## 分类执行规则",
        "",
    ]
    for key, info in CONSTRAINT_TYPES.items():
        label = info.get("label_en", info["label"]) if english else info["label"]
        rule = info.get("export_hint_en", info["export_hint"]) if english else info["export_hint"]
        lines.append(f"- `{key}` / {label}: {rule}")
    lines.extend(
        [
            "",
            "## Global requirements" if english else "## 全局画面要求",
            "",
            project.global_prompt.strip() or ("(Not provided)" if english else "（未填写）"),
            "",
            "## Negative requirements" if english else "## 不希望出现的内容",
            "",
            project.negative_prompt.strip() or ("(Not provided)" if english else "（未填写）"),
            "",
            "## Region overview" if english else "## 区域总览",
            "",
            (
                "| ID | Name | Layer | Shape | Category | Mode | Priority | Pixel bbox | Semantics | Prompt | Notes |"
                if english
                else "| ID | 名称 | 层级 | 形状 | 分类 | 执行模式 | 优先级 | 像素范围 | 自然语言 | 标准化提示词 | 备注 |"
            ),
            "| --- | --- | ---: | --- | --- | --- | ---: | --- | --- | --- | --- |",
        ]
    )
    for index, region in enumerate(project.regions, start=1):
        pixel = ", ".join(str(item) for item in region.pixel_bbox())
        natural_language = _md_cell(region.description)
        standard_prompt = _md_cell(region.standard_prompt)
        notes = _md_cell(region.ai_notes)
        shape_label = (
            ("Freeform region" if english else "自由闭合区域")
            if region.shape == "polygon"
            else ("Rectangle" if english else "矩形区域")
        )
        contract = _region_geometry_contract(region, language)
        lines.append(
            f"| {region.region_id} | {_md_cell(region.name)} | {index} | {shape_label} | {display_label(region.category, language)} | "
            f"{contract['mode']} | {region.priority} | {pixel} | {natural_language} | {standard_prompt} | {notes} |"
        )

    lines.extend(["", "## Region details" if english else "## 区域细则", ""])
    for index, region in enumerate(project.regions, start=1):
        models = _region_export_models(region, project.canvas_width, project.canvas_height, language)
        contract = models["geometry_contract"]
        vector = models["vector_model"]
        lines.extend(
            [
                f"### {index}. {region.name} ({region.region_id})",
                "",
                f"- {'Category' if english else '分类'}: {display_label(region.category, language)} / {region.category}",
                f"- {'Execution mode' if english else '执行模式'}: {contract['mode']}",
                f"- {'Pixel bbox' if english else '像素 bbox'}: {', '.join(str(item) for item in region.pixel_bbox())}",
                f"- {'Semantics' if english else '自然语言'}: {region.description.strip() or ('(Not provided)' if english else '（未填写）')}",
                f"- {'Standard prompt' if english else '标准化提示词'}: {region.standard_prompt.strip() or ('(Not provided)' if english else '（未填写）')}",
                f"- {'Notes' if english else '备注'}: {region.ai_notes.strip() or ('(Not provided)' if english else '（未填写）')}",
                "",
                "#### SVG path" if english else "#### SVG 路径",
                "",
                "```svg-path",
                vector["svg_path"] or ("(No path)" if english else "（无路径）"),
                "```",
                "",
                "#### Complete vertices" if english else "#### 完整顶点清单",
                "",
            ]
        )
        for part in vector["parts"]:
            lines.append(f"part {part['part_index']} exterior, bbox={part['bbox']}, vertex_count={part['vertex_count']}")
            lines.extend(_format_points_block(part["exterior"], "  "))
            for hole_index, hole in enumerate(part.get("holes", []), start=1):
                lines.append(f"  hole {hole_index}, vertex_count={len(hole)}")
                lines.extend(_format_points_block(hole, "    "))
        lines.extend(
            [
                "",
                (
                    "The path is auxiliary geometry for checking or automation. Ordinary image generation should follow the semantics and the separate spatial-relationship report."
                    if english
                    else "路径是给校验或自动化使用的辅助几何。普通生图应遵守自然语言语义和单独导出的空间关系报告。"
                ),
            ]
        )
        lines.append("")

    lines.extend(
        [
            "## Execution guidance" if english else "## 给 AI 的执行提示",
            "",
            (
                "1. Read the spatial-relationship report before generating. It already contains program-computed pairwise and path-side relationships."
                if english
                else "1. 生图前先读取空间关系报告；其中已经包含程序计算的两两关系和长条区域两侧关系。"
            ),
            (
                "2. Prioritize natural-language semantics and relationships. Do not infer meaning from colors alone."
                if english
                else "2. 优先理解自然语言语义和关系，不要只根据颜色猜区域含义。"
            ),
            (
                "3. Preserve positions, scale, layer order, adjacency, containment, and elongated paths while allowing natural material transitions."
                if english
                else "3. 保持位置、大小比例、图层、邻接、包含和长条路径，同时允许材质边缘自然过渡。"
            ),
            (
                "4. Vector paths are verification aids; they are not a claim that a normal image generator can obey exact pixels."
                if english
                else "4. 矢量路径只作校验辅助，不再假定普通生图模型能够逐像素执行。"
            ),
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _visual_index_colors(count: int) -> List[str]:
    """Return deterministic, visually distinct colors independent of user colors."""
    colors: List[str] = []
    used: set[str] = set()
    golden_ratio = 0.618033988749895
    for index in range(max(0, count)):
        hue = (0.035 + index * golden_ratio) % 1.0
        saturation = 0.72 + (index % 3) * 0.08
        value = 0.82 + (index % 2) * 0.14
        red, green, blue = colorsys.hsv_to_rgb(hue, min(saturation, 0.92), min(value, 0.96))
        rgb = [round(red * 255), round(green * 255), round(blue * 255)]
        candidate = f"#{rgb[0]:02X}{rgb[1]:02X}{rgb[2]:02X}"
        while candidate in used:
            rgb[2] = (rgb[2] + 17) % 256
            rgb[1] = (rgb[1] + 7) % 256
            candidate = f"#{rgb[0]:02X}{rgb[1]:02X}{rgb[2]:02X}"
        used.add(candidate)
        colors.append(candidate)
    return colors


def export_svg(project: Project, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    svg_lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{project.canvas_width}" height="{project.canvas_height}" viewBox="0 0 {project.canvas_width} {project.canvas_height}">',
        '<rect width="100%" height="100%" fill="#ffffff"/>',
    ]
    index_colors = _visual_index_colors(len(project.regions))
    for index, region in enumerate(project.regions, start=1):
        region.normalize()
        index_color = index_colors[index - 1]
        label = _xml_escape(f"{index}. {region.name} / {display_label(region.category)}")
        contract = _region_geometry_contract(region)
        data_attrs = (
            f'data-region-index="{index}" '
            f'data-index-color="{index_color}" '
            f'data-category="{_xml_escape(region.category)}" '
            f'data-contract="{_xml_escape(contract["mode"])}" '
            f'data-region-name="{_xml_escape(region.name)}"'
        )
        if region.shape == "polygon":
            for part_index, part in enumerate(region.pixel_parts()):
                points = part["points"]
                holes = part.get("holes", [])
                item_id = f"{_xml_escape(region.region_id)}_part{part_index + 1}"
                path_parts = [_svg_subpath(points)]
                for hole in holes:
                    path_parts.append(_svg_subpath(hole))
                svg_lines.append(
                    f'<path id="{item_id}" {data_attrs} d="{" ".join(path_parts)}" fill="{index_color}" fill-opacity="0.46" '
                    f'stroke="{index_color}" stroke-width="4" fill-rule="evenodd"/>'
                )
        else:
            svg_lines.append(
                f'<rect id="{_xml_escape(region.region_id)}" {data_attrs} x="{region.x}" y="{region.y}" width="{region.width}" height="{region.height}" '
                f'fill="{index_color}" fill-opacity="0.46" stroke="{index_color}" stroke-width="4"/>'
            )
        svg_lines.append(
            f'<text x="{region.x + 6}" y="{region.y + 20}" font-size="16" fill="#111111">{label}</text>'
        )
    svg_lines.append("</svg>")
    path.write_text("\n".join(svg_lines), encoding="utf-8")


def _draw_region_part_png(
    overlay: Image.Image,
    draw: ImageDraw.ImageDraw,
    size: Tuple[int, int],
    points: List[Tuple[int, int]],
    holes: List[List[Tuple[int, int]]],
    rgb: Tuple[int, int, int],
    fill: Tuple[int, int, int, int],
    stroke: Tuple[int, int, int, int],
) -> None:
    if holes:
        mask = Image.new("L", size, 0)
        mask_draw = ImageDraw.Draw(mask)
        mask_draw.polygon(points, fill=56)
        for hole in holes:
            mask_draw.polygon(hole, fill=0)
        color_layer = Image.new("RGBA", size, (*rgb, 0))
        color_layer.putalpha(mask)
        overlay.alpha_composite(color_layer)
    else:
        draw.polygon(points, fill=fill)
    draw.line(points + [points[0]], fill=stroke, width=4)
    for hole in holes:
        draw.line(hole + [hole[0]], fill=stroke, width=3)


def export_png(project: Project, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    base = _load_background(project)
    overlay = Image.new("RGBA", base.size, (255, 255, 255, 0))
    draw = ImageDraw.Draw(overlay)
    _draw_grid(draw, project.canvas_width, project.canvas_height)
    font = _load_font(16)
    small_font = _load_font(13)
    index_colors = _visual_index_colors(len(project.regions))
    for index, region in enumerate(project.regions, start=1):
        region.normalize()
        x1, y1 = region.x, region.y
        x2, y2 = region.x + region.width, region.y + region.height
        rgb = _hex_to_rgb(index_colors[index - 1])
        fill = (*rgb, 112)
        stroke = (*rgb, 255)
        if region.shape == "polygon":
            for part in region.pixel_parts():
                points = [tuple(point) for point in part["points"]]
                holes = [[tuple(point) for point in hole] for hole in part.get("holes", [])]
                _draw_region_part_png(overlay, draw, base.size, points, holes, rgb, fill, stroke)
        else:
            draw.rectangle([x1, y1, x2, y2], fill=fill, outline=stroke, width=4)
        title = f"{index}. {region.name}"
        subtitle = display_label(region.category)
        label_w = max(_text_width(draw, title, font), _text_width(draw, subtitle, small_font)) + 12
        draw.rectangle([x1 + 4, y1 + 4, x1 + 4 + label_w, y1 + 46], fill=(255, 255, 255, 220))
        draw.text((x1 + 10, y1 + 8), title, fill=(25, 25, 25, 255), font=font)
        draw.text((x1 + 10, y1 + 29), subtitle, fill=(25, 25, 25, 220), font=small_font)
    image = Image.alpha_composite(base.convert("RGBA"), overlay).convert("RGB")
    image.save(path, "PNG")


def export_all(
    project: Project,
    output_dir: Path,
    language: str = "zh",
    generation_mode: str = "indirect",
) -> Dict[str, Path]:
    return export_selected(
        project,
        output_dir,
        ["json", "markdown", "png", "svg", "relations", "prompt"],
        language,
        generation_mode,
    )


def export_selected(
    project: Project,
    output_dir: Path,
    formats: List[str],
    language: str = "zh",
    generation_mode: str = "indirect",
    weak_txt_mode: str = "compact",
) -> Dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    slug = safe_slug(project.title)
    all_paths = {
        "json": output_dir / f"{slug}.ai-structure.json",
        "markdown": output_dir / f"{slug}.instructions.md",
        "png": output_dir / f"{slug}.guide.png",
        "svg": output_dir / f"{slug}.regions.svg",
        "relations_json": output_dir / f"{slug}.spatial-relationship-report.json",
        "relations_markdown": output_dir / f"{slug}.spatial-relationship-report.md",
        "prompt": output_dir / f"{slug}.mandatory-composition-brief.md",
        "weak_txt": output_dir / f"{slug}.weak-ai-prompt.txt",
    }
    selected: Dict[str, Path] = {}
    analysis: Optional[Dict[str, Any]] = None
    for name in formats:
        if name == "json":
            export_json(project, all_paths["json"], language)
        elif name == "markdown":
            export_markdown(project, all_paths["markdown"], language)
        elif name == "png":
            export_png(project, all_paths["png"])
        elif name == "svg":
            export_svg(project, all_paths["svg"])
        elif name == "relations":
            analysis = export_relationships(
                project,
                all_paths["relations_json"],
                all_paths["relations_markdown"],
                language,
                analysis,
            )
            selected["relations_json"] = all_paths["relations_json"]
            selected["relations_markdown"] = all_paths["relations_markdown"]
            continue
        elif name == "prompt":
            analysis = analysis or analyze_project_relationships(project, language)
            export_first_pass_prompt(
                project,
                all_paths["prompt"],
                all_paths,
                language,
                analysis,
                generation_mode,
            )
        elif name == "weak_txt":
            analysis = analysis or analyze_project_relationships(project, language)
            export_weak_ai_prompt(
                project,
                all_paths["weak_txt"],
                all_paths["png"],
                language,
                analysis,
                weak_txt_mode,
            )
        else:
            continue
        selected[name] = all_paths[name]
    return selected


def safe_slug(value: str) -> str:
    keep: List[str] = []
    for char in value.strip() or "ai-drawing-plan":
        if char.isalnum() or char in ("-", "_"):
            keep.append(char)
        elif char.isspace():
            keep.append("_")
    slug = "".join(keep).strip("_")
    return slug[:60] or "ai-drawing-plan"


def _load_background(project: Project) -> Image.Image:
    size = (project.canvas_width, project.canvas_height)
    if project.background_path:
        bg_path = Path(project.background_path)
        if bg_path.exists():
            try:
                image = Image.open(bg_path).convert("RGB")
                if image.size != size:
                    image = image.resize(size, Image.Resampling.LANCZOS)
                return image
            except Exception:
                pass
    return Image.new("RGB", size, "#ffffff")


def _draw_grid(draw: ImageDraw.ImageDraw, width: int, height: int) -> None:
    step = 100
    for x in range(0, width + 1, step):
        draw.line([(x, 0), (x, height)], fill=(0, 0, 0, 26), width=1)
    for y in range(0, height + 1, step):
        draw.line([(0, y), (width, y)], fill=(0, 0, 0, 26), width=1)


def _load_font(size: int) -> ImageFont.ImageFont:
    candidates = [
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/simhei.ttf",
        "C:/Windows/Fonts/arial.ttf",
    ]
    for candidate in candidates:
        if Path(candidate).exists():
            try:
                return ImageFont.truetype(candidate, size)
            except Exception:
                continue
    return ImageFont.load_default()


def _hex_to_rgb(value: str) -> Tuple[int, int, int]:
    value = value.strip().lstrip("#")
    if len(value) != 6:
        return (232, 74, 95)
    try:
        return (int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16))
    except ValueError:
        return (232, 74, 95)


def _md_cell(value: str) -> str:
    return (value or "（未填写）").replace("|", "｜").replace("\n", "<br>")


def _xml_escape(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _text_width(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> int:
    try:
        left, _, right, _ = draw.textbbox((0, 0), text, font=font)
        return right - left
    except Exception:
        return len(text) * 10
