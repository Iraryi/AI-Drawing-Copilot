# -*- coding: utf-8 -*-
from __future__ import annotations

from itertools import combinations
import math
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from shapely.geometry import LineString, Point, Polygon, box
from shapely.geometry.base import BaseGeometry
from shapely.ops import nearest_points, unary_union


Point2D = Tuple[float, float]


def _t(language: str, zh: str, en: str) -> str:
    return en if language == "en" else zh


def _round_point(point: Any) -> List[float]:
    return [round(float(point.x), 2), round(float(point.y), 2)]


def _safe_geometry(region: Any) -> BaseGeometry:
    if getattr(region, "shape", "rectangle") != "polygon":
        return box(region.x, region.y, region.x + region.width, region.y + region.height)
    polygons: List[BaseGeometry] = []
    for part in region.pixel_parts():
        exterior = part.get("points", [])
        if len(exterior) < 3:
            continue
        holes = [hole for hole in part.get("holes", []) if len(hole) >= 3]
        polygon = Polygon(exterior, holes)
        if not polygon.is_valid:
            polygon = polygon.buffer(0)
        if not polygon.is_empty:
            polygons.append(polygon)
    if not polygons:
        return box(region.x, region.y, region.x + region.width, region.y + region.height)
    geometry = unary_union(polygons)
    if not geometry.is_valid:
        geometry = geometry.buffer(0)
    return geometry


def _boundary_points(geometry: BaseGeometry) -> List[Point2D]:
    points: List[Point2D] = []
    geoms: Iterable[Any]
    if geometry.geom_type == "Polygon":
        geoms = [geometry]
    elif geometry.geom_type == "MultiPolygon":
        geoms = geometry.geoms
    else:
        geoms = []
    for polygon in geoms:
        points.extend((float(x), float(y)) for x, y in polygon.exterior.coords)
    return points


def _principal_axis(geometry: BaseGeometry) -> Dict[str, Any]:
    points = _boundary_points(geometry)
    if len(points) < 2:
        return {"angle_degrees": 0.0, "vector": [1.0, 0.0], "aspect_ratio": 1.0}
    mean_x = sum(point[0] for point in points) / len(points)
    mean_y = sum(point[1] for point in points) / len(points)
    var_x = sum((point[0] - mean_x) ** 2 for point in points) / len(points)
    var_y = sum((point[1] - mean_y) ** 2 for point in points) / len(points)
    cov_xy = sum((point[0] - mean_x) * (point[1] - mean_y) for point in points) / len(points)
    angle = 0.5 * math.atan2(2.0 * cov_xy, var_x - var_y)
    major = max(var_x, var_y, 1e-9)
    minor = max(min(var_x, var_y), 1e-9)
    return {
        "angle_degrees": round(math.degrees(angle), 2),
        "vector": [round(math.cos(angle), 6), round(math.sin(angle), 6)],
        "aspect_ratio": round(math.sqrt(major / minor), 3),
    }


def _orientation(axis: Dict[str, Any]) -> str:
    angle = float(axis["angle_degrees"]) % 180.0
    if angle <= 22.5 or angle >= 157.5:
        return "horizontal"
    if 67.5 <= angle <= 112.5:
        return "vertical"
    if angle < 67.5:
        return "diagonal_down_right"
    return "diagonal_down_left"


def _direction(dx: float, dy: float) -> str:
    if abs(dx) < 1e-6 and abs(dy) < 1e-6:
        return "same_position"
    if abs(dx) > abs(dy) * 1.8:
        return "right" if dx > 0 else "left"
    if abs(dy) > abs(dx) * 1.8:
        return "below" if dy > 0 else "above"
    if dx > 0 and dy > 0:
        return "lower_right"
    if dx > 0 and dy < 0:
        return "upper_right"
    if dx < 0 and dy > 0:
        return "lower_left"
    return "upper_left"


def _inverse_direction(direction: str) -> str:
    return {
        "left": "right",
        "right": "left",
        "above": "below",
        "below": "above",
        "upper_left": "lower_right",
        "upper_right": "lower_left",
        "lower_left": "upper_right",
        "lower_right": "upper_left",
        "inside": "surrounding",
        "surrounding": "inside",
        "overlapping": "overlapping",
        "same_position": "same_position",
    }.get(direction, direction)


def _direction_text(direction: str, language: str) -> str:
    values = {
        "left": ("左侧", "left of"),
        "right": ("右侧", "right of"),
        "above": ("上方", "above"),
        "below": ("下方", "below"),
        "upper_left": ("左上方", "upper-left of"),
        "upper_right": ("右上方", "upper-right of"),
        "lower_left": ("左下方", "lower-left of"),
        "lower_right": ("右下方", "lower-right of"),
        "inside": ("内部", "inside"),
        "surrounding": ("外围并包围", "surrounding"),
        "overlapping": ("交叠", "overlapping"),
        "same_position": ("近似同一位置", "at nearly the same position as"),
    }
    zh, en = values.get(direction, (direction, direction))
    return en if language == "en" else zh


def _canvas_band(value: float, length: float, language: str, axis: str) -> str:
    ratio = 0.5 if length <= 0 else value / length
    index = 0 if ratio < 0.34 else (2 if ratio > 0.66 else 1)
    if axis == "x":
        zh = ["左侧", "中部", "右侧"][index]
        en = ["left", "center", "right"][index]
    else:
        zh = ["上部", "中部", "下部"][index]
        en = ["upper", "middle", "lower"][index]
    return en if language == "en" else zh


def _natural_position(ratio: float, axis: str, language: str) -> str:
    ratio = max(0.0, min(1.0, ratio))
    if axis == "x":
        zh = ["靠近左边缘", "左侧", "中央偏左", "中央附近", "右侧", "靠近右边缘"]
        en = ["near the left edge", "on the left", "just left of center", "around the center", "on the right", "near the right edge"]
    else:
        zh = ["靠近上边缘", "上部", "中央略偏上", "中央高度", "下部", "靠近下边缘"]
        en = ["near the top edge", "in the upper part", "slightly above mid-height", "around mid-height", "in the lower part", "near the bottom edge"]
    thresholds = (0.1, 0.34, 0.47, 0.63, 0.86)
    index = sum(ratio >= threshold for threshold in thresholds)
    return en[index] if language == "en" else zh[index]


def _span_narrative(low: float, high: float, axis: str, language: str) -> str:
    low = max(0.0, min(1.0, low))
    high = max(low, min(1.0, high))
    if axis == "x" and low <= 0.04 and high >= 0.96:
        return _t(language, "横跨整幅画面的宽度", "spans almost the full canvas width")
    if axis == "y" and low <= 0.04 and high >= 0.96:
        return _t(language, "贯穿整幅画面的高度", "spans almost the full canvas height")
    start = _natural_position(low, axis, language)
    end = _natural_position(high, axis, language)
    if language == "en":
        for prefix in ("in ", "on "):
            if start.startswith(prefix):
                start = start[len(prefix):]
            if end.startswith(prefix):
                end = end[len(prefix):]
        if start in {"the left", "the right"}:
            start += " side"
        if end in {"the left", "the right"}:
            end += " side"
        return f"extends from {start} to {end}"
    return f"从{start}延伸到{end}"


def _edge_anchor_label(edge: str, along_ratio: float, language: str) -> str:
    if edge in {"left", "right"}:
        if along_ratio < 0.2:
            position = _t(language, "上端附近", "near the upper end")
        elif along_ratio < 0.42:
            position = _t(language, "上段", "in the upper section")
        elif along_ratio < 0.64:
            position = _t(language, "中段", "in the middle section")
        elif along_ratio < 0.84:
            position = _t(language, "下段", "in the lower section")
        else:
            position = _t(language, "下端附近", "near the lower end")
        edge_name = _t(language, "画面左边缘" if edge == "left" else "画面右边缘", "the left canvas edge" if edge == "left" else "the right canvas edge")
    else:
        if along_ratio < 0.18:
            position = _t(language, "靠左端", "near the left end")
        elif along_ratio < 0.4:
            position = _t(language, "中央偏左", "just left of center")
        elif along_ratio < 0.62:
            position = _t(language, "中央附近", "near the center")
        elif along_ratio < 0.82:
            position = _t(language, "中央偏右", "just right of center")
        else:
            position = _t(language, "靠右端", "near the right end")
        edge_name = _t(language, "画面上边缘" if edge == "top" else "画面下边缘", "the top canvas edge" if edge == "top" else "the bottom canvas edge")
    return f"{edge_name} {position}" if language == "en" else f"{edge_name}{position}"


def _edge_anchors(geometry: BaseGeometry, width: float, height: float, language: str) -> List[Dict[str, Any]]:
    margin = max(6.0, min(width, height) * 0.06)
    zones = {
        "left": box(0, 0, min(width, margin), height),
        "right": box(max(0, width - margin), 0, width, height),
        "top": box(0, 0, width, min(height, margin)),
        "bottom": box(0, max(0, height - margin), width, height),
    }
    bounds = geometry.bounds
    contacts = {
        "left": bounds[0] <= 1.5,
        "right": bounds[2] >= width - 1.5,
        "top": bounds[1] <= 1.5,
        "bottom": bounds[3] >= height - 1.5,
    }
    anchors: List[Dict[str, Any]] = []
    for edge, zone in zones.items():
        clipped = geometry.intersection(zone)
        if clipped.is_empty:
            continue
        center = clipped.centroid
        along_ratio = float(center.y / max(height, 1.0)) if edge in {"left", "right"} else float(center.x / max(width, 1.0))
        label = _edge_anchor_label(edge, along_ratio, language)
        contact = "touching" if contacts[edge] else "near"
        natural = _t(
            language,
            f"与{label}直接相接" if contact == "touching" else f"靠近{label}并保持视觉连接",
            f"connects directly to {label}" if contact == "touching" else f"approaches {label} and remains visually connected to it",
        )
        anchors.append(
            {
                "edge": edge,
                "contact": contact,
                "along_ratio": round(along_ratio, 4),
                "natural_position": label,
                "natural_language": natural,
            }
        )
    return anchors


def _canvas_occupancy(
    geometry: BaseGeometry,
    width: float,
    height: float,
    language: str,
) -> Dict[str, Any]:
    area = max(float(geometry.area), 1e-9)
    left_ratio = float(geometry.intersection(box(0, 0, width / 2, height)).area) / area
    upper_ratio = float(geometry.intersection(box(0, 0, width, height / 2)).area) / area
    right_ratio = max(0.0, 1.0 - left_ratio)
    lower_ratio = max(0.0, 1.0 - upper_ratio)
    middle_horizontal_ratio = float(geometry.intersection(box(0, height * 0.38, width, height * 0.62)).area) / area
    middle_vertical_ratio = float(geometry.intersection(box(width * 0.38, 0, width * 0.62, height)).area) / area
    horizontal_mass = "left" if left_ratio >= 0.66 else ("right" if right_ratio >= 0.66 else "across")
    vertical_mass = "upper" if upper_ratio >= 0.66 else ("lower" if lower_ratio >= 0.66 else "across")

    if horizontal_mass == "left":
        horizontal_text = _t(language, "明显偏在画面左半部", "is weighted clearly toward the left half")
    elif horizontal_mass == "right":
        horizontal_text = _t(language, "明显偏在画面右半部", "is weighted clearly toward the right half")
    else:
        horizontal_text = _t(language, "跨过画面中央并分布在左右两半", "crosses the visual center and occupies both left and right halves")
    if vertical_mass == "upper":
        vertical_text = _t(language, "大部分面积留在画面上半部", "keeps most of its area in the upper half")
    elif vertical_mass == "lower":
        vertical_text = _t(language, "大部分面积留在画面下半部", "keeps most of its area in the lower half")
    else:
        vertical_text = _t(language, "跨过画面中部高度并分布在上下两半", "crosses mid-height and occupies both upper and lower halves")

    bounds = geometry.bounds
    horizontal_reach = _span_narrative(bounds[0] / max(width, 1.0), bounds[2] / max(width, 1.0), "x", language)
    vertical_reach = _span_narrative(bounds[1] / max(height, 1.0), bounds[3] / max(height, 1.0), "y", language)
    center_presence: List[str] = []
    if middle_horizontal_ratio >= 0.38:
        center_presence.append(_t(language, "在画面中部的横向地带保留大面积内容", "retains substantial area across the horizontal middle of the canvas"))
    if middle_vertical_ratio >= 0.38:
        center_presence.append(_t(language, "在画面中央的纵向地带保留大面积内容", "retains substantial area through the vertical middle of the canvas"))

    guard_parts: List[str] = []
    if horizontal_mass == "left":
        guard_parts.append(_t(language, "不得把主要面积迁到右半部", "do not move its main area into the right half"))
    elif horizontal_mass == "right":
        guard_parts.append(_t(language, "不得把主要面积迁到左半部", "do not move its main area into the left half"))
    if vertical_mass == "upper":
        guard_parts.append(_t(language, "不得把主要面积沉到下半部", "do not sink its main area into the lower half"))
    elif vertical_mass == "lower":
        guard_parts.append(_t(language, "不得把主要面积抬到上半部", "do not lift its main area into the upper half"))
    if not guard_parts:
        guard_parts.append(_t(language, "不得把跨越画面中央的主体挤缩到某个角落", "do not compress this center-crossing footprint into a corner"))

    if language == "en":
        narrative = (
            f"MANDATORY CANVAS OCCUPANCY: the main footprint {horizontal_text} and {vertical_text}; "
            f"it {horizontal_reach} horizontally and {vertical_reach} vertically."
        )
        if center_presence:
            narrative += f" It {' and '.join(center_presence)}."
        narrative += f" {'; '.join(part.capitalize() for part in guard_parts)}."
    else:
        narrative = (
            f"强制画面占位：主体{horizontal_text}，并且{vertical_text}；"
            f"横向{horizontal_reach}，纵向{vertical_reach}。"
        )
        if center_presence:
            narrative += f" 必须{'，并且'.join(center_presence)}。"
        narrative += f" {'；'.join(guard_parts)}。"

    anchors = _edge_anchors(geometry, width, height, language)
    if anchors:
        anchor_text = _t(
            language,
            "；".join(anchor["natural_language"] for anchor in anchors),
            "; ".join(anchor["natural_language"] for anchor in anchors),
        )
        narrative += _t(language, f" 画面边缘锚点：{anchor_text}。", f" Canvas-edge anchors: {anchor_text}.")
    return {
        "mandatory": True,
        "horizontal_mass": horizontal_mass,
        "vertical_mass": vertical_mass,
        "left_area_ratio": round(left_ratio, 5),
        "right_area_ratio": round(right_ratio, 5),
        "upper_area_ratio": round(upper_ratio, 5),
        "lower_area_ratio": round(lower_ratio, 5),
        "middle_horizontal_area_ratio": round(middle_horizontal_ratio, 5),
        "middle_vertical_area_ratio": round(middle_vertical_ratio, 5),
        "horizontal_reach": horizontal_reach,
        "vertical_reach": vertical_reach,
        "edge_anchors": anchors,
        "natural_language": narrative,
    }


def _semantic_risks(region: Any, language: str) -> Tuple[List[str], List[str]]:
    text = " ".join(
        str(value).lower()
        for value in (region.name, region.description, region.standard_prompt, region.ai_notes)
        if value
    )
    rules = [
        (
            ("河", "水", "river", "water", "lake", "sea"),
            ("水体可能膨胀成湖、海或港湾", "Water may expand into a lake, sea, or harbor."),
            ("保持水体沿自身区域窄向延伸，区域外立即恢复陆地语义", "Keep water narrow and aligned to its region; restore land semantics immediately outside it."),
        ),
        (
            ("城", "建筑", "city", "castle", "building"),
            ("建筑可能扩张成覆盖邻区的大型城市", "Architecture may expand into a large city covering neighboring regions."),
            ("建筑密度和轮廓不得越过本区域的构图范围", "Keep building density and silhouette inside this region's composition range."),
        ),
        (
            ("火", "敌军", "fire", "army", "smoke"),
            ("火光、烟雾或军队可能抢占整幅画面", "Fire, smoke, or armies may dominate the whole image."),
            ("保持为局部或远景语义，禁止扩张成全图事件", "Keep this local or distant; do not expand it into a scene-wide event."),
        ),
        (
            ("田", "麦", "field", "wheat", "crop"),
            ("田地可能退化成大片单色平面并越界", "Fields may become a flat color plane and spill across boundaries."),
            ("纹理应跟随区域主轴，并在边缘转回相邻地表", "Align texture with the region axis and transition back to neighboring ground at its edge."),
        ),
        (
            ("山", "mountain", "ridge"),
            ("山体可能吞没天空或地面", "Mountains may swallow the sky or ground."),
            ("保持山体层级与地平线关系，不要向上下邻区扩张", "Preserve the mountain layer and horizon relationship; do not expand vertically into neighbors."),
        ),
        (
            ("村", "village", "hamlet"),
            ("村落可能被放大成城市或图标拼贴", "A village may become a city or an icon collage."),
            ("使用低密度、连续的环境细节，保持村落尺度", "Use low-density environmental detail and preserve village scale."),
        ),
        (
            ("墙", "wall", "fortification"),
            ("墙体可能变成横贯画面的厚重块面", "A wall may become an oversized block spanning the image."),
            ("沿真实走向保持厚度稳定，不要吞并邻区", "Follow its real path with stable thickness and do not consume neighbors."),
        ),
    ]
    risks: List[str] = []
    containment: List[str] = []
    for keywords, risk, guard in rules:
        if any(keyword in text for keyword in keywords):
            risks.append(risk[1] if language == "en" else risk[0])
            containment.append(guard[1] if language == "en" else guard[0])
    if not risks:
        risks.append(_t(language, "主体语义可能向相邻区域外溢", "The subject semantics may spill into neighboring regions."))
        containment.append(_t(language, "保持主体位置、尺度与邻接关系，不要把它扩张成全图主题", "Preserve its position, scale, and adjacency; do not expand it into a scene-wide theme."))
    return risks, containment


def _is_path_like(region: Any) -> bool:
    text = " ".join(
        str(value).lower()
        for value in (region.name, region.description, region.standard_prompt, region.ai_notes)
        if value
    )
    keywords = (
        "河流",
        "河道",
        "溪流",
        "水道",
        "道路",
        "小路",
        "公路",
        "城墙",
        "山脊",
        "边界线",
        "地平线",
        "云带",
        "光带",
        "烟带",
        "队列",
        "river",
        "stream",
        "canal",
        "road",
        "path",
        "wall",
        "ridge",
        "boundary line",
        "horizon",
        "cloud band",
        "light band",
        "smoke trail",
    )
    return any(keyword in text for keyword in keywords)


def _cross_section_centerline(geometry: BaseGeometry, axis: Dict[str, Any], samples: int = 9) -> Dict[str, Any]:
    center = geometry.centroid
    vx, vy = (float(axis["vector"][0]), float(axis["vector"][1]))
    nx, ny = -vy, vx
    boundary = _boundary_points(geometry)
    if not boundary:
        return {"points": [_round_point(center)], "segments": []}
    projections = [x * vx + y * vy for x, y in boundary]
    perpendiculars = [x * nx + y * ny for x, y in boundary]
    low, high = min(projections), max(projections)
    cross_low, cross_high = min(perpendiculars), max(perpendiculars)
    padding = max(high - low, cross_high - cross_low, 1.0) * 0.25 + 4.0
    points: List[List[float]] = []
    widths: List[float] = []
    for index in range(samples):
        # Stay slightly inside the region. Exact end-point sections can collapse
        # to one polygon corner because of floating-point rotation.
        ratio = (index + 0.5) / samples
        along = low + (high - low) * ratio
        start = (vx * along + nx * (cross_low - padding), vy * along + ny * (cross_low - padding))
        end = (vx * along + nx * (cross_high + padding), vy * along + ny * (cross_high + padding))
        section = geometry.intersection(LineString([start, end]))
        if section.is_empty:
            continue
        section_center = section.centroid
        point = [round(section_center.x, 2), round(section_center.y, 2)]
        if not points or point != points[-1]:
            points.append(point)
            widths.append(round(float(section.length), 2))
    segments: List[Dict[str, Any]] = []
    for index in range(len(points) - 1):
        start = points[index]
        end = points[index + 1]
        dx, dy = end[0] - start[0], end[1] - start[1]
        segments.append(
            {
                "segment_index": index + 1,
                "start": start,
                "end": end,
                "midpoint": [round((start[0] + end[0]) / 2, 2), round((start[1] + end[1]) / 2, 2)],
                "direction": _direction(dx, dy),
                "length_px": round(math.hypot(dx, dy), 2),
                "local_width_px": round((widths[index] + widths[index + 1]) / 2, 2),
            }
        )
    return {"points": points, "segments": segments}


def _longest_axis_run(points: Sequence[Sequence[float]], axis: str) -> Optional[Dict[str, Any]]:
    best: Optional[Dict[str, Any]] = None
    current: Optional[Dict[str, Any]] = None
    for start, end in zip(points, points[1:]):
        dx = float(end[0]) - float(start[0])
        dy = float(end[1]) - float(start[1])
        is_axis_segment = abs(dx) >= abs(dy) * 1.6 if axis == "horizontal" else abs(dy) >= abs(dx) * 1.6
        if not is_axis_segment:
            if current and (best is None or current["length"] > best["length"]):
                best = current
            current = None
            continue
        length = math.hypot(dx, dy)
        if current is None:
            current = {"start": list(start), "end": list(end), "length": length, "points": [list(start), list(end)]}
        else:
            current["end"] = list(end)
            current["length"] += length
            current["points"].append(list(end))
    if current and (best is None or current["length"] > best["length"]):
        best = current
    return best


def _path_route_narrative(
    name: str,
    centerline: Dict[str, Any],
    occupancy: Dict[str, Any],
    width: float,
    height: float,
    language: str,
) -> str:
    points = centerline.get("points", [])
    anchors = occupancy.get("edge_anchors", [])
    pieces: List[str] = []
    if len(anchors) >= 2:
        anchor_text = _t(
            language,
            "、".join(anchor["natural_position"] for anchor in anchors),
            ", ".join(anchor["natural_position"] for anchor in anchors),
        )
        pieces.append(
            _t(
                language,
                f"两端或外部延伸必须分别对准{anchor_text}",
                f"its ends or off-canvas continuation must remain aligned with {anchor_text}",
            )
        )
    elif anchors:
        pieces.append(
            _t(
                language,
                f"路线必须{anchors[0]['natural_language']}",
                f"the route must {anchors[0]['natural_language']}",
            )
        )

    horizontal = _longest_axis_run(points, "horizontal")
    vertical = _longest_axis_run(points, "vertical")
    if horizontal and horizontal["length"] >= width * 0.16:
        run_points = horizontal["points"]
        xs = [float(point[0]) for point in run_points]
        ys = [float(point[1]) for point in run_points]
        level = _natural_position(sum(ys) / len(ys) / max(height, 1.0), "y", language)
        reach = _span_narrative(min(xs) / max(width, 1.0), max(xs) / max(width, 1.0), "x", language)
        pieces.append(
            _t(
                language,
                f"在{level}保留一段明显而连续的横向长段，该长段{reach}",
                f"it keeps a conspicuous continuous horizontal run {level} that {reach}",
            )
        )
    if vertical and vertical["length"] >= height * 0.16:
        run_points = vertical["points"]
        xs = [float(point[0]) for point in run_points]
        ys = [float(point[1]) for point in run_points]
        side = _natural_position(sum(xs) / len(xs) / max(width, 1.0), "x", language)
        reach = _span_narrative(min(ys) / max(height, 1.0), max(ys) / max(height, 1.0), "y", language)
        pieces.append(
            _t(
                language,
                f"在{side}保留明显的纵向转折，该段{reach}",
                f"it keeps a clear vertical turn {side} that {reach}",
            )
        )
    if horizontal and vertical:
        pieces.append(
            _t(
                language,
                "横向长段与纵向转折必须同时存在，不能拉成直线或单一斜线",
                "the horizontal run and vertical turn must both remain; do not straighten them into one line or diagonal",
            )
        )
    edge_names = {anchor["edge"] for anchor in anchors}
    if {"right", "bottom"}.issubset(edge_names):
        pieces.append(
            _t(
                language,
                "不得把这条路线改成从画面中央直接冲向右下角的捷径",
                "do not replace this route with a shortcut running directly from the canvas center toward the lower-right corner",
            )
        )
    if not pieces:
        pieces.append(
            _t(
                language,
                f"路线必须保持现有弯曲轮廓和整体延伸方向：横向{occupancy['horizontal_reach']}，纵向{occupancy['vertical_reach']}",
                f"the route must preserve its present bends and overall reach: horizontally it {occupancy['horizontal_reach']}, vertically it {occupancy['vertical_reach']}",
            )
        )
    joined = _t(language, "；".join(pieces), "; ".join(pieces))
    return _t(
        language,
        f"强制长条走向：{name} 的{joined}。",
        f"MANDATORY ELONGATED ROUTE: for {name}, {joined}.",
    )


def _pair_relation(
    a: Dict[str, Any],
    b: Dict[str, Any],
    threshold: float,
    language: str,
) -> Dict[str, Any]:
    geom_a: BaseGeometry = a["_geometry"]
    geom_b: BaseGeometry = b["_geometry"]
    intersection = geom_a.intersection(geom_b)
    intersection_area = float(intersection.area)
    area_a = max(float(geom_a.area), 1e-9)
    area_b = max(float(geom_b.area), 1e-9)
    distance = float(geom_a.distance(geom_b))
    point_a, point_b = nearest_points(geom_a, geom_b)
    contains_b = geom_a.covers(geom_b)
    inside_b = geom_b.covers(geom_a)
    centroid_relation = _inverse_direction(
        _direction(
            float(b["centroid"][0]) - float(a["centroid"][0]),
            float(b["centroid"][1]) - float(a["centroid"][1]),
        )
    )
    if inside_b and not contains_b:
        relation = "inside"
    elif contains_b and not inside_b:
        relation = "surrounding"
    elif intersection_area > 0:
        relation = "overlapping"
    else:
        relation = centroid_relation
    touching = bool(geom_a.touches(geom_b) or distance <= 1.5)
    adjacent = bool(distance <= threshold)
    layer_relation = (
        _t(language, f"{a['name']} 位于 {b['name']} 上层", f"{a['name']} is visually above {b['name']}")
        if a["layer_index"] > b["layer_index"]
        else _t(language, f"{b['name']} 位于 {a['name']} 上层", f"{b['name']} is visually above {a['name']}")
    )
    direction_text = _direction_text(relation, language)
    if intersection_area > 0 or touching:
        distance_band = "touching_or_overlapping"
        distance_text = _t(language, "接触或交叠", "touching or overlapping")
    elif distance <= threshold:
        distance_band = "near"
        distance_text = _t(language, "近邻", "near")
    elif distance <= threshold * 4:
        distance_band = "medium"
        distance_text = _t(language, "中等间隔", "medium separation")
    else:
        distance_band = "far"
        distance_text = _t(language, "明显分离", "clearly separated")
    if relation in {"inside", "surrounding", "overlapping"}:
        centroid_text = _direction_text(centroid_relation, language)
        sentence = _t(
            language,
            f"强制构图关系：{a['name']} 与 {b['name']} 的几何关系必须保持为“{direction_text}”，交叠面积约 {intersection_area:.1f} 像素；"
            f"两者属于“{distance_text}”距离；{a['name']} 的中心必须继续位于 {b['name']} 中心的{centroid_text}。{layer_relation}。"
            f"不得取消这种包含/交叠关系，不得互换中心方向或前后层级。",
            f"MANDATORY COMPOSITION RELATION: {a['name']} must remain geometrically {direction_text} {b['name']}, "
            f"with about {intersection_area:.1f} pixels of overlap and a {distance_text} distance band. "
            f"The center of {a['name']} must remain {centroid_text} "
            f"the center of {b['name']}. {layer_relation}. Do not remove this containment/overlap, swap center direction, or reverse layer order.",
        )
    else:
        sentence = _t(
            language,
            f"强制构图关系：{a['name']} 必须保持在 {b['name']} 的{direction_text}，边界最短距离约 {distance:.1f} 像素，属于“{distance_text}”距离；"
            f"{layer_relation}。不得互换方向、明显改变距离级别或颠倒前后层级。",
            f"MANDATORY COMPOSITION RELATION: {a['name']} must remain {direction_text} {b['name']}. "
            f"The shortest boundary distance is about {distance:.1f} pixels ({distance_text}). {layer_relation}. "
            f"Do not swap direction, materially change the distance band, or reverse layer order.",
        )
    if adjacent:
        sentence += _t(language, " 两者必须继续保持邻接/近邻关系。", " They must remain adjacent or near neighbors.")
    return {
        "pair": [a["id"], b["id"]],
        "names": [a["name"], b["name"]],
        "a_relative_to_b": relation,
        "b_relative_to_a": _inverse_direction(relation),
        "centroid_a_relative_to_b": centroid_relation,
        "centroid_b_relative_to_a": _inverse_direction(centroid_relation),
        "intersects": not intersection.is_empty,
        "intersection_area_px": round(intersection_area, 2),
        "overlap_ratio_of_a": round(intersection_area / area_a, 6),
        "overlap_ratio_of_b": round(intersection_area / area_b, 6),
        "touching": touching,
        "adjacent": adjacent,
        "distance_px": round(distance, 2),
        "distance_band": distance_band,
        "nearest_points": [_round_point(point_a), _round_point(point_b)],
        "layer_relation": layer_relation,
        "mandatory": True,
        "constraint_strength": "hard_spatial_relationship",
        "natural_language": sentence,
    }


def analyze_project_relationships(project: Any, language: str = "zh") -> Dict[str, Any]:
    language = "en" if language == "en" else "zh"
    width = int(project.canvas_width)
    height = int(project.canvas_height)
    diagonal = math.hypot(width, height)
    adjacency_threshold = max(8.0, diagonal * 0.015)
    records: List[Dict[str, Any]] = []
    for index, region in enumerate(project.regions, start=1):
        geometry = _safe_geometry(region)
        centroid = geometry.centroid
        axis = _principal_axis(geometry)
        risks, containment = _semantic_risks(region, language)
        path_like = _is_path_like(region)
        centerline = _cross_section_centerline(geometry, axis) if path_like else {"points": [], "segments": []}
        occupancy = _canvas_occupancy(geometry, width, height, language)
        route_narrative = (
            _path_route_narrative(region.name, centerline, occupancy, width, height, language)
            if path_like
            else ""
        )
        parts = region.pixel_parts()
        holes_count = sum(len(part.get("holes", [])) for part in parts)
        location = _t(
            language,
            f"画面{_canvas_band(centroid.y, height, language, 'y')}{_canvas_band(centroid.x, width, language, 'x')}",
            f"{_canvas_band(centroid.y, height, language, 'y')}-{_canvas_band(centroid.x, width, language, 'x')} of the canvas",
        )
        record = {
            "id": region.region_id,
            "name": region.name,
            "semantic": region.description,
            "standard_prompt": region.standard_prompt,
            "notes": region.ai_notes,
            "category": region.category,
            "layer_index": index,
            "priority": region.priority,
            "pixel_bbox": region.pixel_bbox(),
            "area_px": round(float(geometry.area), 2),
            "canvas_coverage_ratio": round(float(geometry.area) / max(width * height, 1), 6),
            "centroid": _round_point(centroid),
            "canvas_location": location,
            "canvas_occupancy": occupancy,
            "principal_axis": axis,
            "orientation": _orientation(axis),
            "elongated": axis["aspect_ratio"] >= 2.2,
            "path_like": path_like,
            "fragmented": len(parts) > 1,
            "part_count": len(parts),
            "has_holes": holes_count > 0,
            "hole_count": holes_count,
            "centerline": centerline,
            "route_narrative": route_narrative,
            "semantic_overflow_risks": risks,
            "containment_rules": containment,
            "_geometry": geometry,
        }
        records.append(record)

    pairs = [_pair_relation(a, b, adjacency_threshold, language) for a, b in combinations(records, 2)]
    by_id = {record["id"]: record for record in records}
    adjacency: Dict[str, Dict[str, Any]] = {}
    for record in records:
        adjacency[record["id"]] = {
            "name": record["name"],
            "directly_adjacent_regions": [],
            "near_regions": [],
            "overlapping_regions": [],
            "visually_above_regions": [
                other["id"] for other in records if other["layer_index"] > record["layer_index"]
            ],
            "visually_below_regions": [
                other["id"] for other in records if other["layer_index"] < record["layer_index"]
            ],
            "directional_neighbors": {},
            "topological_relations": {},
        }
    for pair in pairs:
        a_id, b_id = pair["pair"]
        if pair["touching"]:
            adjacency[a_id]["directly_adjacent_regions"].append(b_id)
            adjacency[b_id]["directly_adjacent_regions"].append(a_id)
        if pair["adjacent"]:
            adjacency[a_id]["near_regions"].append(b_id)
            adjacency[b_id]["near_regions"].append(a_id)
        if pair["intersection_area_px"] > 0:
            adjacency[a_id]["overlapping_regions"].append(b_id)
            adjacency[b_id]["overlapping_regions"].append(a_id)
        adjacency[a_id]["directional_neighbors"][b_id] = pair["centroid_a_relative_to_b"]
        adjacency[b_id]["directional_neighbors"][a_id] = pair["centroid_b_relative_to_a"]
        adjacency[a_id]["topological_relations"][b_id] = pair["a_relative_to_b"]
        adjacency[b_id]["topological_relations"][a_id] = pair["b_relative_to_a"]

    directed_constraints: List[Dict[str, Any]] = []
    pair_lookup = {tuple(pair["pair"]): pair for pair in pairs}
    pair_lookup.update({(pair["pair"][1], pair["pair"][0]): pair for pair in pairs})
    for reference in records:
        if not reference["path_like"] or len(reference["centerline"]["points"]) < 2:
            continue
        line_points = reference["centerline"]["points"]
        candidates: List[Tuple[float, Dict[str, Any], Dict[str, Any]]] = []
        for subject in records:
            if subject["id"] == reference["id"]:
                continue
            pair = pair_lookup.get((subject["id"], reference["id"]))
            if not pair or (not pair["adjacent"] and pair["distance_px"] > adjacency_threshold * 3):
                continue
            if subject["canvas_coverage_ratio"] > 0.4:
                continue
            if pair["a_relative_to_b"] == "surrounding":
                continue
            candidates.append((float(pair["distance_px"]), subject, pair))
        for _distance, subject, pair in sorted(candidates, key=lambda item: item[0])[:8]:
            center = subject["centroid"]
            best_index = min(
                range(len(line_points) - 1),
                key=lambda i: LineString([line_points[i], line_points[i + 1]]).distance(Point(center[0], center[1])),
            )
            start, end = line_points[best_index], line_points[best_index + 1]
            cross = (end[0] - start[0]) * (center[1] - start[1]) - (end[1] - start[1]) * (center[0] - start[0])
            side = "right_side" if cross > 0 else "left_side"
            midpoint = [(start[0] + end[0]) / 2, (start[1] + end[1]) / 2]
            global_side = _direction(center[0] - midpoint[0], center[1] - midpoint[1])
            global_side_text = _direction_text(global_side, language)
            local_place = _t(
                language,
                f"{_natural_position(midpoint[0] / max(width, 1), 'x', language)}、{_natural_position(midpoint[1] / max(height, 1), 'y', language)}的局部路径段",
                f"the local run {_natural_position(midpoint[0] / max(width, 1), 'x', language)} and {_natural_position(midpoint[1] / max(height, 1), 'y', language)}",
            )
            must_be = _t(
                language,
                f"{subject['name']} 必须继续位于 {reference['name']} {local_place}的{global_side_text}，并维持当前最短距离与层级关系。",
                f"{subject['name']} must remain {global_side_text} {local_place} of {reference['name']}, preserving the current distance and layer order.",
            )
            must_not = _t(
                language,
                f"不得把 {subject['name']} 移到 {reference['name']} 的另一侧，也不得让两者语义互相吞并。",
                f"Do not move {subject['name']} to the opposite side of {reference['name']} or let either semantic region consume the other.",
            )
            directed_constraints.append(
                {
                    "constraint_id": f"{subject['id']}_vs_{reference['id']}_path_lock",
                    "subject_region": subject["id"],
                    "reference_region": reference["id"],
                    "reference_segment": best_index + 1,
                    "local_side": side,
                    "natural_side": global_side,
                    "local_place": local_place,
                    "must_be": must_be,
                    "must_not_be": must_not,
                }
            )

    vertical_order = [record["name"] for record in sorted(records, key=lambda item: item["centroid"][1])]
    horizontal_order = [record["name"] for record in sorted(records, key=lambda item: item["centroid"][0])]
    important_pairs = sorted(
        pairs,
        key=lambda pair: (
            not (by_id[pair["pair"][0]]["path_like"] or by_id[pair["pair"][1]]["path_like"]),
            not pair["adjacent"],
            -max(pair["overlap_ratio_of_a"], pair["overlap_ratio_of_b"]),
            pair["distance_px"],
        ),
    )
    overall = _t(
        language,
        f"画布为 {width}×{height}。从上到下大致依次为：{'、'.join(vertical_order) or '无区域'}；"
        f"从左到右大致依次为：{'、'.join(horizontal_order) or '无区域'}。"
        f"程序已分析 {len(pairs)} 组两两关系与 {len(directed_constraints)} 条长条区域定向约束。",
        f"The canvas is {width}×{height}. Approximate top-to-bottom order: {', '.join(vertical_order) or 'no regions'}; "
        f"left-to-right order: {', '.join(horizontal_order) or 'no regions'}. "
        f"The program analyzed {len(pairs)} pairwise relationships and {len(directed_constraints)} directed path constraints.",
    )
    clean_records = [{key: value for key, value in record.items() if key != "_geometry"} for record in records]
    return {
        "format": "ai-drawing-copilot-spatial-relationships-v1",
        "language": language,
        "canvas": {"width": width, "height": height, "origin": "top-left", "unit": "pixel"},
        "adjacency_threshold_px": round(adjacency_threshold, 2),
        "overall_narrative": overall,
        "regions": clean_records,
        "pairwise_relationships": pairs,
        "spatial_adjacency_graph": adjacency,
        "directed_spatial_constraints": directed_constraints,
        "priority_relationships": [pair["natural_language"] for pair in important_pairs[: min(12, len(important_pairs))]],
    }


def render_relationship_markdown(project: Any, analysis: Dict[str, Any], language: str = "zh") -> str:
    language = "en" if language == "en" else "zh"
    lines = [
        _t(language, f"# {project.title}：程序计算的空间关系", f"# {project.title}: Program-computed spatial relationships"),
        "",
        analysis["overall_narrative"],
        "",
        _t(
            language,
            "以下关系由真实区域几何计算，全部属于强制性构图约束，不是参考建议。允许改变材质、光照和细节，但不得交换区域方向、取消邻接/包含/交叠、颠倒图层或改变长条走向。",
            "The following relationships are computed from real region geometry and are mandatory composition constraints, not suggestions. Materials, lighting, and detail may change; region direction, adjacency, containment, overlap, layer order, and elongated paths must not.",
        ),
        "",
        _t(language, "## 单区域分析", "## Per-region analysis"),
        "",
    ]
    for region in analysis["regions"]:
        lines.extend(
            [
                f"### {region['name']} (`{region['id']}`)",
                "",
                _t(language, f"- 位置：{region['canvas_location']}", f"- Location: {region['canvas_location']}"),
                _t(language, f"- 面积：{region['area_px']} px；画布占比：{region['canvas_coverage_ratio']:.2%}", f"- Area: {region['area_px']} px; canvas coverage: {region['canvas_coverage_ratio']:.2%}"),
                _t(language, f"- 中心：{region['centroid']}；方向：{region['orientation']}；长宽倾向：{region['principal_axis']['aspect_ratio']}", f"- Center: {region['centroid']}; orientation: {region['orientation']}; aspect tendency: {region['principal_axis']['aspect_ratio']}"),
                _t(language, f"- 层级：{region['layer_index']}；多部件：{'是' if region['fragmented'] else '否'}；孔洞：{region['hole_count']}", f"- Layer: {region['layer_index']}; fragmented: {region['fragmented']}; holes: {region['hole_count']}"),
                _t(language, f"- 语义：{region['semantic'] or '未填写'}", f"- Semantics: {region['semantic'] or 'not provided'}"),
                f"- {region['canvas_occupancy']['natural_language']}",
                _t(language, f"- 外溢风险：{'；'.join(region['semantic_overflow_risks'])}", f"- Overflow risks: {'; '.join(region['semantic_overflow_risks'])}"),
                _t(language, f"- 防护规则：{'；'.join(region['containment_rules'])}", f"- Containment: {'; '.join(region['containment_rules'])}"),
            ]
        )
        if region.get("route_narrative"):
            lines.append(f"- {region['route_narrative']}")
        if region["centerline"]["segments"]:
            lines.append(_t(language, "- 近似中心线分段：", "- Approximate centerline segments:"))
            for segment in region["centerline"]["segments"]:
                lines.append(
                    _t(
                        language,
                        f"  - 第 {segment['segment_index']} 段：{segment['start']} → {segment['end']}，方向 {segment['direction']}，局部宽度约 {segment['local_width_px']} px",
                        f"  - Segment {segment['segment_index']}: {segment['start']} → {segment['end']}, direction {segment['direction']}, local width about {segment['local_width_px']} px",
                    )
                )
        lines.append("")

    lines.extend([_t(language, "## 重要两两关系", "## Important pairwise relationships"), ""])
    for sentence in analysis["priority_relationships"]:
        lines.append(f"- {sentence}")
    lines.extend(["", _t(language, "## 长条区域定向关系锁定", "## Directed path-side constraints"), ""])
    if analysis["directed_spatial_constraints"]:
        for constraint in analysis["directed_spatial_constraints"]:
            lines.append(f"- {constraint['must_be']} {constraint['must_not_be']}")
    else:
        lines.append(_t(language, "没有检测到需要分段锁定的长条区域。", "No elongated region required segment-side locking."))
    lines.extend(
        [
            "",
            _t(language, "## 全部两两关系", "## All pairwise relationships"),
            "",
            _t(language, "| 区域 A | 区域 B | A 相对 B | 距离 | 交叠面积 | 邻近 | 层级 |", "| Region A | Region B | A relative to B | Distance | Overlap area | Near | Layer order |"),
            "| --- | --- | --- | ---: | ---: | --- | --- |",
        ]
    )
    for pair in analysis["pairwise_relationships"]:
        relation_text = _direction_text(pair["a_relative_to_b"], language)
        if pair["centroid_a_relative_to_b"] != pair["a_relative_to_b"]:
            relation_text += _t(
                language,
                f"（中心在{_direction_text(pair['centroid_a_relative_to_b'], language)}）",
                f" (center {_direction_text(pair['centroid_a_relative_to_b'], language)})",
            )
        lines.append(
            f"| {pair['names'][0]} | {pair['names'][1]} | {relation_text} | "
            f"{pair['distance_px']} | {pair['intersection_area_px']} | {pair['adjacent']} | {pair['layer_relation']} |"
        )
    return "\n".join(lines) + "\n"


def render_first_pass_prompt(
    project: Any,
    analysis: Dict[str, Any],
    artifact_names: Dict[str, str],
    language: str = "zh",
    generation_mode: str = "indirect",
) -> str:
    language = "en" if language == "en" else "zh"
    generation_mode = "direct" if generation_mode == "direct" else "indirect"
    relation_lines = "\n".join(
        f"{index}. {pair['natural_language']}"
        for index, pair in enumerate(analysis["pairwise_relationships"], start=1)
    ) or _t(language, "（当前没有成对区域）", "(There are no region pairs.)")
    region_lines = "\n".join(
        _t(
            language,
            f"- {region['name']}：第 {region['layer_index']} 层，位于{region['canvas_location']}；语义为“{region['semantic'] or '未填写'}”。"
            f"必须保持该位置、尺度倾向和主体归属。防止：{'；'.join(region['containment_rules'])}",
            f"- {region['name']}: layer {region['layer_index']}, located at {region['canvas_location']}; semantics: "
            f"“{region['semantic'] or 'not provided'}”. Preserve its position, scale tendency, and subject ownership. "
            f"Containment: {'; '.join(region['containment_rules'])}",
        )
        for region in analysis["regions"]
    ) or _t(language, "（当前没有区域）", "(There are no regions.)")
    occupancy_lines = "\n".join(
        f"- {region['name']}：{region['canvas_occupancy']['natural_language']}"
        if language == "zh"
        else f"- {region['name']}: {region['canvas_occupancy']['natural_language']}"
        for region in analysis["regions"]
    ) or _t(language, "（当前没有区域）", "(There are no regions.)")
    constraint_lines = "\n".join(
        f"- {item['must_be']} {item['must_not_be']}" for item in analysis["directed_spatial_constraints"]
    ) or _t(language, "- 当前没有长条区域定向锁定。", "- There are no directed path constraints.")
    path_lines_list: List[str] = []
    for region in analysis["regions"]:
        if not region.get("route_narrative"):
            continue
        path_lines_list.append(f"- {region['route_narrative']}")
    path_lines = "\n".join(path_lines_list) or _t(language, "- 当前没有需要分段描述的长条区域。", "- No elongated region requires segmented path description.")
    if language == "en":
        if generation_mode == "direct":
            execution_gate = """# DIRECT MODE — FINAL IMAGE GENERATION IS AUTHORIZED

## Execution authorization — read before doing anything

```text
GENERATION_MODE = DIRECT
GENERATIVE_IMAGE_TOOL_ALLOWED = YES
INTERMEDIATE_UNDERPAINT_REQUIRED = NO
MANDATORY_COMPOSITION_RULES_MAY_BE_IGNORED = NO
ONLY_ALLOWED_FINAL_ARTIFACT = naturalized_final.png
```

Generate the final image directly, but treat every spatial, occupancy, edge-anchor, layer, distance, and elongated-route rule in this file as mandatory. Do not improvise a different layout merely because it looks more conventional.
"""
            execution_steps = """## Direct execution — AUTHORIZED

Use the numbered PNG and SVG indexes together with this written brief, then generate the final naturalized image directly. Preserve every mandatory relationship and output only `naturalized_final.png`.
"""
        else:
            execution_gate = """# STOP — STAGE 1 ONLY; FINAL IMAGE GENERATION IS NOT AUTHORIZED

## Execution gate — read before doing anything

```text
CURRENT_STAGE = 1
GENERATIVE_IMAGE_TOOL_ALLOWED = NO
IMG2IMG_OR_IMAGE_EDITING_ALLOWED = NO
ONLY_ALLOWED_ARTIFACT = texture_underpaint.png
MUST_STOP_AFTER_STAGE_1 = YES
STAGE_2_AUTHORIZED = NO
```

These rules are mandatory:

1. Receiving this file, the PNG/SVG indexes, or a request to “make/generate the image” does **not** authorize final image generation.
2. During Stage 1, do **not** call any generative-image, img2img, image-editing, or image-synthesis tool. Use local deterministic code only.
3. Stage 1 may create only a programmatically rendered structural/material underpaint named `texture_underpaint.png`. It must not be a photorealistic, painterly, naturalized, or final image.
4. After creating that one file, stop immediately. Reply only that Stage 1 is complete and ask the user to send a new message containing “Continue”.
5. A “Continue” written in the same message that supplied these files does not count. Stage 2 requires a separate user message sent **after** `texture_underpaint.png` has been delivered.
6. If local code execution is unavailable or Stage 1 cannot be completed, report the limitation and stop. Never substitute direct image generation.
"""
            execution_steps = """## Two-stage execution

### Stage 1 — CURRENTLY AUTHORIZED

Use local deterministic code, not a generative image model, to create only `texture_underpaint.png`. It must already obey every mandatory relationship in this brief. Do not create a polished scene. Stop after producing it and reply: “Stage 1 complete. Please send Continue.”

### Mandatory stop

Do not begin Stage 2 in the same response or tool run. Do not treat successful Stage 1 completion as automatic permission to continue.

### Stage 2 — LOCKED

Only after the user sends a separate new “Continue” message may you use `texture_underpaint.png` as the sole image input for real img2img/image editing. Naturalize texture, seams, and lighting without violating any mandatory relationship. Output only `naturalized_final.png`.
"""
        return f"""{execution_gate}
# Mandatory composition brief for {project.title}

This document is the authoritative composition constraint. Every spatial relationship below is mandatory, not optional inspiration. Style, material, lighting, and local detail may be improved, but region direction, adjacency, containment, overlap, layer order, distance band, and elongated paths must not change.

## Visual indexes

- `{artifact_names['png']}` — numbered raster index.
- `{artifact_names['svg']}` — numbered vector index.

Both indexes use application-assigned unique index colors. Index colors identify regions only and are never final materials. If an index appears ambiguous, this written brief takes precedence.

Index color legend:

{artifact_names['index_legend']}

## Overall intent

{project.global_prompt or "(No global prompt was provided.)"}

Negative requirements:
{project.negative_prompt or "(No negative prompt was provided.)"}

## Overall spatial structure

{analysis['overall_narrative']}

## Mandatory region semantics

{region_lines}

## Mandatory canvas occupancy

These statements describe where each region has substantial presence across the whole picture. They are not point coordinates or a fine grid.

{occupancy_lines}

## Mandatory pairwise composition relationships

{relation_lines}

## Mandatory elongated-path directions

{path_lines}

## Mandatory local side constraints

{constraint_lines}

## Non-negotiable rules

1. Do not swap any left/right, above/below, or diagonal relationship.
2. Do not remove required adjacency, containment, or overlap.
3. Do not materially change the recorded near/medium/far distance band.
4. Do not reverse layer order or move a covered semantic region out from beneath its upper region.
5. Do not move a region's main footprint into the opposite half of the picture or remove a required canvas-edge anchor.
6. Do not straighten, widen, relocate, or reroute elongated regions.
7. Do not move an object to the opposite side of a recorded path segment.
8. Visual index colors are identifiers only; replace them with the requested natural materials.

{execution_steps}
"""
    if generation_mode == "direct":
        execution_gate = """# 直接型：已授权直接生成最终图像

## 执行授权——进行任何操作前必须先读

```text
生成模式 = 直接型
允许调用生图工具 = 是
必须先生成程序化底图 = 否
允许忽略强制构图关系 = 否
唯一允许输出的最终文件 = naturalized_final.png
```

可以直接生成最终图像，但本文件中的全部空间关系、画面占位、边缘锚点、图层、距离和长条走向仍是强制要求。不得因为常见构图更顺眼，就擅自改成另一套布局。
"""
        execution_steps = """## 直接执行——当前已授权

同时读取带编号的 PNG、SVG 索引图和本说明，然后直接生成自然化最终图像。必须保持全部强制关系，最终只输出 `naturalized_final.png`。
"""
    else:
        execution_gate = """# 停止：当前只允许第一阶段，尚未授权生成最终图像

## 执行门禁——进行任何操作前必须先读

```text
当前阶段 = 第一阶段
允许调用生图工具 = 否
允许进行图生图或图像编辑 = 否
唯一允许输出的文件 = texture_underpaint.png
第一阶段结束后必须停止 = 是
第二阶段已获授权 = 否
```

以下规则属于强制执行要求：

1. 收到本文件、PNG/SVG 索引图，或者收到“制作图片、生成图片”之类的要求，都不等于获得最终生图授权。
2. 第一阶段严禁调用任何生图、图生图、图像编辑或图像合成工具；只能使用本地、确定性的代码绘制。
3. 第一阶段只允许生成一张程序化结构/材质底图，文件名必须是 `texture_underpaint.png`。它不得是写实图、绘画成图、自然化图或最终效果图。
4. 生成这一张底图后必须立刻停止，只能告知“第一阶段已完成，请发送继续”，不得在同一轮开始最终生图。
5. 用户在上传这些文件的同一条消息里写出的“继续”无效。只有在 `texture_underpaint.png` 已经交付之后，用户另发一条包含“继续”的新消息，才算授权第二阶段。
6. 如果当前环境不能运行本地代码，或无法完成第一阶段，只能说明受阻并停止；严禁改用直接生图作为替代方案。
"""
        execution_steps = """## 两阶段执行

### 第一阶段——当前已授权

只使用本地、确定性的代码生成 `texture_underpaint.png`，不得调用生图模型。底图必须已经遵守本文件的全部强制关系，但不得做成写实或自然化的最终画面。本阶段只输出这一张图，然后回复：“第一阶段已完成，请发送继续。”

### 强制停止点

不得在同一轮回复或同一次工具调用中开始第二阶段。第一阶段完成本身不构成自动继续授权。

### 第二阶段——当前锁定

只有用户在底图交付后另发一条包含“继续”的新消息，才能把 `texture_underpaint.png` 作为唯一图像输入进行真正的 img2img/图像编辑。可以自然化材质、接缝和光照，但不得违反任何强制关系。最终只输出 `naturalized_final.png`。
"""
    return f"""{execution_gate}
# {project.title}：强制构图关系说明

本文件是本次生图的最高优先级构图约束。下方每一条空间关系都是强制要求，不是参考建议。画风、材质、光照和局部细节可以自然化，但区域方向、邻接、包含、交叠、图层、距离级别和长条走向不得改变。

## 视觉索引

- `{artifact_names['png']}`：带区域编号的点阵索引图。
- `{artifact_names['svg']}`：带区域编号的矢量索引图。

两张索引图均由程序为不同区域强制分配不同索引色。索引色只用于辨认区域，不代表最终材质。如果视觉索引与文字理解发生歧义，以本文件的自然语言强制关系为准。

索引编号、区域名称与索引色对应表：

{artifact_names['index_legend']}

## 用户整体要求

{project.global_prompt or "（未填写整体要求）"}

不希望出现：
{project.negative_prompt or "（未填写负面要求）"}

## 整体空间结构

{analysis['overall_narrative']}

## 各区域强制语义

{region_lines}

## 各区域在整幅画面中的强制占位

这里描述的是每个区域在整张画面中必须大面积出现在哪里，不是点坐标，也不是把画面切成细碎网格。

{occupancy_lines}

## 全部两两强制构图关系

{relation_lines}

## 长条区域强制走向

{path_lines}

## 长条区域局部两侧强制关系

{constraint_lines}

## 不得违反的总规则

1. 不得交换任何左右、上下或斜向位置关系。
2. 不得取消已经记录的邻接、包含或交叠。
3. 不得明显改变已经记录的近邻/中等/分离距离级别。
4. 不得颠倒图层；上层遮挡下层时，下层语义仍必须保留在原位置。
5. 不得把某个区域的主要面积迁移到画面的相反半边，也不得取消它与画面边缘的锚定关系。
6. 不得拉直、拓宽、平移或重排长条区域的路径。
7. 不得把对象移动到路径分段的另一侧。
8. 视觉索引色只是身份标记，最终必须替换成用户要求的自然材质。

{execution_steps}
"""


def render_weak_ai_prompt(
    project: Any,
    analysis: Dict[str, Any],
    png_name: str,
    language: str = "zh",
    mode: str = "compact",
) -> str:
    language = "en" if language == "en" else "zh"
    mode = mode if mode in {"compact", "indirect", "direct"} else "compact"
    regions = "\n".join(
        _t(
            language,
            f"{index}. {region['name']}：{region['semantic'] or '未填写语义'}。{region['canvas_occupancy']['natural_language']}",
            f"{index}. {region['name']}: {region['semantic'] or 'semantics not provided'}. {region['canvas_occupancy']['natural_language']}",
        )
        for index, region in enumerate(analysis["regions"], start=1)
    ) or _t(language, "没有区域。", "No regions.")
    relationship_source = (
        analysis["priority_relationships"]
        if mode == "compact"
        else [pair["natural_language"] for pair in analysis["pairwise_relationships"]]
    )
    relationships = "\n".join(
        f"{index}. {sentence}"
        for index, sentence in enumerate(relationship_source, start=1)
    ) or _t(language, "没有需要补充的区域关系。", "No additional region relationships.")
    routes = "\n".join(
        f"- {region['route_narrative']}"
        for region in analysis["regions"]
        if region.get("route_narrative")
    ) or _t(language, "没有长条路线。", "No elongated routes.")
    local_constraints = "\n".join(
        f"- {item['must_be']} {item['must_not_be']}"
        for item in (
            analysis["directed_spatial_constraints"][:10]
            if mode == "compact"
            else analysis["directed_spatial_constraints"]
        )
    ) or _t(language, "没有局部两侧约束。", "No local side constraints.")
    if language == "en":
        if mode == "indirect":
            header = """WEAK-AI INDIRECT TWO-STAGE INSTRUCTION

CURRENT_STAGE = 1
GENERATIVE_IMAGE_TOOL_ALLOWED = NO
STAGE_2_AUTHORIZED = NO
ONLY_ALLOWED_STAGE_1_FILE = texture_underpaint.png

Do not generate the final image now. Use local deterministic code only to create `texture_underpaint.png`, then stop. A separate user message sent after delivery and containing “Continue” is required before final image generation.
"""
            final_action = """STAGE 1 ACTION
Create only `texture_underpaint.png` with local code, report that Stage 1 is complete, and stop. If local code is unavailable, report the limitation; do not substitute direct image generation."""
        elif mode == "direct":
            header = """WEAK-AI STANDARD DIRECT INSTRUCTION

GENERATION_MODE = DIRECT
GENERATIVE_IMAGE_TOOL_ALLOWED = YES
MANDATORY_COMPOSITION_RULES_MAY_BE_IGNORED = NO
ONLY_ALLOWED_FINAL_FILE = naturalized_final.png

Generate the final image directly while treating every relationship below as mandatory.
"""
            final_action = "FINAL ACTION\nGenerate and output only `naturalized_final.png`."
        else:
            header = """WEAK-AI COMPACT DIRECT IMAGE INSTRUCTION

Generate one final image now. Do not explain the plan and do not output text instead of the image.
"""
            final_action = "FINAL ACTION\nOutput only the final image."
        return f"""{header}

Read `{png_name}` as a numbered composition index. Every region has a unique index color. The colors identify regions only; replace them with natural materials. Preserve the numbered layout rather than inventing a conventional composition.

OVERALL REQUEST
{project.global_prompt or "No overall request was provided."}

AVOID
{project.negative_prompt or "No negative request was provided."}

MANDATORY REGION MEANING AND LARGE-SCALE CANVAS OCCUPANCY
{regions}

MOST IMPORTANT MANDATORY RELATIONSHIPS
{relationships}

MANDATORY ELONGATED ROUTES
{routes}

MANDATORY LOCAL SIDE RELATIONSHIPS
{local_constraints}

FINAL CHECK
Keep left/right, above/below, adjacency, containment, overlap, layer order, distance tendency, large-scale canvas occupancy, edge anchors, and elongated turns.

{final_action}
"""
    if mode == "indirect":
        header = """弱 AI 间接型两阶段指令

当前阶段 = 第一阶段
允许调用生图工具 = 否
第二阶段已获授权 = 否
第一阶段唯一允许文件 = texture_underpaint.png

现在不得生成最终图像。只能使用本地、确定性的代码生成 `texture_underpaint.png`，然后停止。底图交付后，必须等待用户另发一条包含“继续”的新消息，才能最终生图。
"""
        final_action = """第一阶段动作
只用本地代码生成 `texture_underpaint.png`，告知第一阶段完成，然后停止。如果不能运行本地代码，只能说明受阻，严禁改成直接生图。"""
    elif mode == "direct":
        header = """弱 AI 标准直接型指令

生成模式 = 直接型
允许调用生图工具 = 是
允许忽略强制构图关系 = 否
唯一允许输出的最终文件 = naturalized_final.png

现在直接生成最终图像，但下方每一条关系都必须执行。
"""
        final_action = "最终动作\n只生成并输出 `naturalized_final.png`。"
    else:
        header = """弱 AI 精简直接型指令

现在直接生成一张最终图像。不要解释计划，不要用文字回复代替图像。
"""
        final_action = "最终动作\n只输出最终图像。"
    return f"""{header}

把 `{png_name}` 当作带编号的构图索引图。每个区域都有唯一索引色；颜色只用于识别区域，最终必须换成自然材质。必须保留编号对应的布局，不得擅自改成常见构图。

整体要求
{project.global_prompt or "未填写整体要求。"}

不要出现
{project.negative_prompt or "未填写负面要求。"}

各区域的强制语义和大范围画面占位
{regions}

最重要的强制区域关系
{relationships}

长条区域的强制走向
{routes}

局部两侧的强制关系
{local_constraints}

最终检查
必须保持左右、上下、邻接、包含、交叠、图层、距离倾向、大范围画面占位、边缘锚点和长条转折。

{final_action}
"""
