# -*- coding: utf-8 -*-
from __future__ import annotations

import json
from pathlib import Path
import shutil
import sys

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aipilot.model import Project, Region, export_all, export_selected, load_project, save_project
from aipilot.relationships import analyze_project_relationships


def main() -> None:
    root = ROOT
    output_dir = root / "TEST" / "smoke_export"
    if output_dir.exists():
        resolved = output_dir.resolve()
        allowed = (root / "TEST").resolve()
        if allowed not in resolved.parents and resolved != allowed:
            raise RuntimeError(f"Refuse to delete outside TEST folder: {resolved}")
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    project = Project(
        title="烟雾测试构图",
        canvas_width=640,
        canvas_height=480,
        global_prompt="一张清晰的构图，左侧是窄河流，右侧是人物。",
        negative_prompt="不要把人物画到河流区域。",
    )
    project.add_region(
        Region(
            name="左侧河流",
            x=40,
            y=60,
            width=110,
            height=320,
            category="rough",
            description="一条竖向窄河流，位于人物左侧并保持窄长走向。",
            ai_notes="保持河流与人物之间的左右关系，不要扩张成湖。",
            priority=5,
            color="#457B9D",
        )
    )
    project.add_region(
        Region(
            name="右侧人物",
            x=330,
            y=90,
            width=210,
            height=330,
            category="larger_than_prompt",
            description="人物的安全外框，真实人物可以略小。",
            ai_notes="头部和肩膀都应在这个范围内。",
            priority=4,
            color="#E84A5F",
        )
    )
    project.add_region(
        Region(
            name="桌面自由区域",
            x=0,
            y=0,
            width=1,
            height=1,
            category="rough",
            description="一个手绘闭合区域，模拟用户随手圈出的桌面。",
            ai_notes="按多边形点列理解区域，不要只看外接框。",
            priority=3,
            color="#2A9D8F",
            shape="polygon",
            points=[[250, 330], [430, 300], [560, 360], [520, 440], [280, 430]],
            filled=False,
            holes=[[[330, 360], [390, 350], [400, 390], [340, 400]]],
            parts=[
                {
                    "points": [[90, 90], [150, 90], [150, 140], [90, 140]],
                    "holes": [],
                }
            ],
        )
    )

    project_file = output_dir / "smoke_project.aicopilot.json"
    save_project(project, project_file)
    loaded = load_project(project_file)
    assert loaded.canvas_width == 640
    assert len(loaded.regions) == 3
    assert loaded.regions[2].filled is False
    assert len(loaded.regions[2].pixel_holes()) == 1
    assert len(loaded.regions[2].pixel_parts()) == 2
    assert len(loaded.regions) == 3

    paths = export_all(loaded, output_dir)
    for name, path in paths.items():
        assert path.exists(), f"missing export: {name}"
        assert path.stat().st_size > 0, f"empty export: {name}"

    spec = json.loads(paths["json"].read_text(encoding="utf-8"))
    assert spec["coordinate_system"]["origin"] == "top-left"
    assert spec["region_semantics"]["type"] == "semantic_masks"
    assert "上层区域不会自动从下层区域中扣除" in spec["region_semantics"]["occlusion_rule"]
    assert spec["regions"][0]["pixel_bbox"] == [40, 60, 110, 320]
    assert spec["regions"][0]["layer_index"] == 1
    assert spec["regions"][0]["category"] == "rough"
    assert spec["regions"][0]["geometry_contract"]["mode"] == "natural_language_layout_guide"
    assert spec["regions"][0]["vector_model"]["svg_path"]
    assert spec["regions"][0]["pixel_mask_model"]["type"] == "not_emitted_for_text_guided_generation"
    assert spec["regions"][2]["shape"] == "polygon"
    assert spec["regions"][2]["filled"] is False
    assert spec["regions"][2]["geometry_contract"]["mode"] == "natural_language_layout_guide"
    assert spec["regions"][2]["pixel_mask_model"]["type"] == "not_emitted_for_text_guided_generation"
    assert len(spec["regions"][2]["pixel_holes"]) == 1
    assert len(spec["regions"][2]["pixel_points"]) == 5
    assert len(spec["regions"][2]["pixel_parts"]) == 2
    reloaded_export = Project.from_dict(spec)
    assert reloaded_export.canvas_width == 640
    assert reloaded_export.canvas_height == 480
    assert len(reloaded_export.regions) == 3
    assert reloaded_export.regions[2].pixel_points() == loaded.regions[2].pixel_points()
    markdown = paths["markdown"].read_text(encoding="utf-8")
    assert "普通生图模型应优先理解自然语言关系" in markdown
    assert "exact_pixel" not in markdown
    assert "```svg-path" in markdown

    relationships = json.loads(paths["relations_json"].read_text(encoding="utf-8"))
    assert relationships["format"] == "ai-drawing-copilot-spatial-relationships-v1"
    assert len(relationships["regions"]) == 3
    assert len(relationships["pairwise_relationships"]) == 3
    assert relationships["regions"][0]["elongated"] is True
    assert relationships["regions"][0]["path_like"] is True
    assert relationships["regions"][0]["centerline"]["segments"]
    assert relationships["regions"][0]["canvas_occupancy"]["mandatory"] is True
    assert relationships["regions"][0]["canvas_occupancy"]["natural_language"]
    assert relationships["regions"][0]["route_narrative"]
    assert all("centroid_a_relative_to_b" in pair for pair in relationships["pairwise_relationships"])
    assert all(pair["mandatory"] is True for pair in relationships["pairwise_relationships"])
    assert all(pair["distance_band"] for pair in relationships["pairwise_relationships"])
    assert "程序已分析 3 组两两关系" in relationships["overall_narrative"]
    relations_markdown = paths["relations_markdown"].read_text(encoding="utf-8")
    assert "程序计算的空间关系" in relations_markdown
    assert "左侧河流" in relations_markdown
    first_pass_prompt = paths["prompt"].read_text(encoding="utf-8")
    assert first_pass_prompt.startswith("# 停止：当前只允许第一阶段")
    assert "强制构图关系说明" in first_pass_prompt
    assert "全部两两强制构图关系" in first_pass_prompt
    assert "各区域在整幅画面中的强制占位" in first_pass_prompt
    assert "X轴" not in first_pass_prompt
    assert "Y轴" not in first_pass_prompt
    assert "允许调用生图工具 = 否" in first_pass_prompt
    assert "用户在上传这些文件的同一条消息里写出的“继续”无效" in first_pass_prompt
    assert "严禁改用直接生图作为替代方案" in first_pass_prompt
    assert "第一阶段——当前已授权" in first_pass_prompt
    assert "第二阶段——当前锁定" in first_pass_prompt

    deprecated = Region(
        name="旧分类",
        x=0,
        y=0,
        width=20,
        height=20,
        category="exact_pixel",
    )
    deprecated.normalize()
    assert deprecated.category == "rough"

    english_dir = output_dir / "english"
    english_paths = export_all(loaded, english_dir, language="en")
    assert "Program-computed spatial relationships" in english_paths["relations_markdown"].read_text(encoding="utf-8")
    english_prompt = english_paths["prompt"].read_text(encoding="utf-8")
    assert english_prompt.startswith("# STOP — STAGE 1 ONLY")
    assert "Mandatory composition brief" in english_prompt
    assert "GENERATIVE_IMAGE_TOOL_ALLOWED = NO" in english_prompt
    assert "A “Continue” written in the same message" in english_prompt
    assert "Stage 2 — LOCKED" in english_prompt

    minimal_dir = output_dir / "minimal"
    for region in loaded.regions:
        region.color = "#808080"
    minimal_paths = export_selected(loaded, minimal_dir, ["png", "svg", "prompt"])
    assert set(minimal_paths) == {"png", "svg", "prompt"}
    assert len(list(minimal_dir.iterdir())) == 3
    svg_text = minimal_paths["svg"].read_text(encoding="utf-8")
    index_color_lines = [
        line for line in svg_text.splitlines() if 'data-region-index="' in line
    ]
    color_by_index = {}
    for line in index_color_lines:
        region_index = line.split('data-region-index="', 1)[1].split('"', 1)[0]
        index_color = line.split('data-index-color="', 1)[1].split('"', 1)[0]
        color_by_index[region_index] = index_color
    assert len(color_by_index) == len(loaded.regions)
    assert len(set(color_by_index.values())) == len(loaded.regions)
    assert "#808080" not in set(color_by_index.values())

    direct_dir = output_dir / "direct"
    direct_paths = export_selected(
        loaded,
        direct_dir,
        ["png", "svg", "prompt"],
        generation_mode="direct",
    )
    direct_prompt = direct_paths["prompt"].read_text(encoding="utf-8")
    assert direct_prompt.startswith("# 直接型：已授权直接生成最终图像")
    assert "允许调用生图工具 = 是" in direct_prompt
    assert "允许忽略强制构图关系 = 否" in direct_prompt
    assert "直接执行——当前已授权" in direct_prompt
    assert "第二阶段——当前锁定" not in direct_prompt
    assert len(list(direct_dir.iterdir())) == 3

    weak_dir = output_dir / "weak_ai"
    weak_paths = export_selected(loaded, weak_dir, ["png", "weak_txt"])
    assert set(weak_paths) == {"png", "weak_txt"}
    assert len(list(weak_dir.iterdir())) == 2
    assert weak_paths["weak_txt"].suffix == ".txt"
    weak_text = weak_paths["weak_txt"].read_text(encoding="utf-8")
    assert weak_text.startswith("弱 AI 精简直接型指令")
    assert weak_paths["png"].name in weak_text
    assert "大范围画面占位" in weak_text
    assert "只输出最终图像" in weak_text

    weak_indirect_dir = output_dir / "weak_ai_indirect"
    weak_indirect = export_selected(
        loaded,
        weak_indirect_dir,
        ["png", "weak_txt"],
        weak_txt_mode="indirect",
    )
    weak_indirect_text = weak_indirect["weak_txt"].read_text(encoding="utf-8")
    assert weak_indirect_text.startswith("弱 AI 间接型两阶段指令")
    assert "允许调用生图工具 = 否" in weak_indirect_text
    assert "严禁改成直接生图" in weak_indirect_text

    weak_direct_dir = output_dir / "weak_ai_direct"
    weak_direct = export_selected(
        loaded,
        weak_direct_dir,
        ["png", "weak_txt"],
        weak_txt_mode="direct",
    )
    weak_direct_text = weak_direct["weak_txt"].read_text(encoding="utf-8")
    assert weak_direct_text.startswith("弱 AI 标准直接型指令")
    assert "允许调用生图工具 = 是" in weak_direct_text
    assert "允许忽略强制构图关系 = 否" in weak_direct_text

    route_project = Project(title="路线占位测试", canvas_width=1000, canvas_height=800)
    route_project.add_region(
        Region(
            name="弯折河流",
            x=0,
            y=0,
            width=1,
            height=1,
            category="rough",
            description="河流",
            shape="polygon",
            points=[
                [430, 270],
                [965, 270],
                [965, 390],
                [760, 390],
                [760, 800],
                [610, 800],
                [610, 370],
                [430, 370],
            ],
        )
    )
    route_project.add_region(
        Region(
            name="右下麦田",
            x=500,
            y=420,
            width=440,
            height=320,
            category="rough",
            description="远处的麦田",
        )
    )
    route_analysis = analyze_project_relationships(route_project)
    river_record, field_record = route_analysis["regions"]
    assert {"right", "bottom"}.issubset(
        {anchor["edge"] for anchor in river_record["canvas_occupancy"]["edge_anchors"]}
    )
    assert "右下角的捷径" in river_record["route_narrative"]
    assert field_record["canvas_occupancy"]["horizontal_mass"] == "right"
    assert field_record["canvas_occupancy"]["vertical_mass"] == "lower"
    assert "不得把主要面积迁到左半部" in field_record["canvas_occupancy"]["natural_language"]
    assert "不得把主要面积抬到上半部" in field_record["canvas_occupancy"]["natural_language"]

    image = Image.open(paths["png"])
    assert image.size == (640, 480)
    print("smoke ok")


if __name__ == "__main__":
    main()
