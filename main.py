# -*- coding: utf-8 -*-
from __future__ import annotations

import sys
from pathlib import Path

from aipilot.app import (
    AboutDialog,
    DrawingCopilotApp,
    ExportDialog,
    GlobalPromptDialog,
    ProjectDialog,
    RegionDialog,
    SettingsDialog,
    StartupLanguageDialog,
    run,
    startup_language_required,
)
from aipilot.model import Project, Region, export_selected


if __name__ == "__main__":
    export_flags = (
        "--export-smoke",
        "--export-smoke-en",
        "--export-smoke-direct",
        "--export-smoke-direct-en",
        "--export-smoke-weak",
        "--export-smoke-weak-en",
        "--export-smoke-weak-indirect",
        "--export-smoke-weak-indirect-en",
        "--export-smoke-weak-direct",
        "--export-smoke-weak-direct-en",
    )
    if any(flag in sys.argv for flag in export_flags):
        try:
            export_flag = next(flag for flag in export_flags if flag in sys.argv)
            output_index = sys.argv.index(export_flag) + 1
            output_dir = Path(sys.argv[output_index]) if output_index < len(sys.argv) else Path.cwd() / "TEST" / "exe_export_smoke"
            project = Project(
                title="EXE自检构图",
                canvas_width=320,
                canvas_height=240,
                global_prompt="用于验证打包程序可以导出结构文件。",
            )
            project.add_region(
                Region(
                    name="中心主体",
                    x=80,
                    y=50,
                    width=160,
                    height=140,
                    category="rough",
                    description="主体位于画面中心，并与周围区域保持当前构图关系。",
                    ai_notes="普通生图优先读取自然语言关系；矢量路径只作辅助校验。",
                    priority=5,
                )
            )
            project.add_region(
                Region(
                    name="自由闭合区",
                    x=0,
                    y=0,
                    width=1,
                    height=1,
                    category="rough",
                    description="用于验证自由闭合区域导出。",
                    ai_notes="应导出 pixel_points。",
                    priority=3,
                    shape="polygon",
                    points=[[30, 180], [120, 140], [210, 160], [250, 220], [60, 230]],
                    color="#2A9D8F",
                )
            )
            export_selected(
                project,
                output_dir,
                ["png", "weak_txt"] if "weak" in export_flag else ["png", "svg", "prompt"],
                language="en" if export_flag.endswith("-en") else "zh",
                generation_mode="direct" if "direct" in export_flag else "indirect",
                weak_txt_mode=(
                    "indirect"
                    if "weak-indirect" in export_flag
                    else ("direct" if "weak-direct" in export_flag else "compact")
                ),
            )
        except Exception as exc:
            raise SystemExit(str(exc))
    elif "--dialog-centering-smoke" in sys.argv:
        app = DrawingCopilotApp()
        app.attributes("-alpha", 0.0)
        app.geometry("1200x800+100+80")
        app.update()
        region = Region(name="Centering test", x=10, y=10, width=100, height=80)
        factories = [
            lambda: ProjectDialog(app, app.project, app.language, modal=False),
            lambda: GlobalPromptDialog(app, app.project, app.language, modal=False),
            lambda: RegionDialog(app, app.project, region, app.language, modal=False),
            lambda: ExportDialog(app, app.language, modal=False),
            lambda: AboutDialog(app, app.language, modal=False),
        ]
        parent_center = (
            app.winfo_rootx() + app.winfo_width() / 2,
            app.winfo_rooty() + app.winfo_height() / 2,
        )
        for factory in factories:
            dialog = factory()
            dialog.update()
            dialog_center = (
                dialog.winfo_rootx() + dialog.winfo_width() / 2,
                dialog.winfo_rooty() + dialog.winfo_height() / 2,
            )
            if abs(dialog_center[0] - parent_center[0]) > 45 or abs(dialog_center[1] - parent_center[1]) > 45:
                raise SystemExit(f"Dialog is not centered: {dialog.title()}")
            dialog.destroy()
        app.destroy()
    elif "--startup-language-smoke" in sys.argv:
        app = DrawingCopilotApp()
        app.attributes("-alpha", 0.0)
        dialog = StartupLanguageDialog(app, app.language, modal=False)
        dialog.update()
        if dialog.result is not None:
            raise SystemExit("Startup language dialog selected a language before user input")
        dialog.choose("en")
        if dialog.result != "en":
            raise SystemExit("Startup language selection failed")
        app.destroy()
    elif "--startup-language-policy-smoke" in sys.argv:
        if not startup_language_required({}):
            raise SystemExit("A fresh profile did not request a language")
        if startup_language_required({"language": "zh"}):
            raise SystemExit("Remembered Chinese requested a language again")
        if startup_language_required({"language": "en"}):
            raise SystemExit("Remembered English requested a language again")
        if not startup_language_required({"language": "invalid"}):
            raise SystemExit("Invalid persisted language was accepted")
    elif "--zoom-fill-sync-smoke" in sys.argv:
        app = DrawingCopilotApp()
        app.withdraw()
        app.project.regions.clear()
        app.project.add_region(
            Region(
                name="Zoom fill sync",
                x=80,
                y=70,
                width=260,
                height=200,
                shape="polygon",
                points=[[80, 70], [340, 70], [340, 270], [80, 270]],
                holes=[[[150, 120], [270, 120], [270, 220], [150, 220]]],
            )
        )
        app.refresh_canvas()
        overlay_items = app.canvas.find_withtag("region_overlay")
        preview_items = app.canvas.find_withtag("region_zoom_preview")
        if len(overlay_items) != 1 or len(preview_items) < 1:
            raise SystemExit("Compound-region zoom preview was not created")
        initial_coords = app.canvas.coords(preview_items[0])
        app.zoom_canvas_by(1.12, 200, 160)
        zoomed_coords = app.canvas.coords(preview_items[0])
        if app.canvas.itemcget(overlay_items[0], "state") != "hidden":
            raise SystemExit("Heavy raster fill stayed visible during live zoom")
        if app.canvas.itemcget(preview_items[0], "state") != "normal":
            raise SystemExit("Lightweight vector fill did not activate during live zoom")
        if max(zoomed_coords) <= max(initial_coords):
            raise SystemExit("Lightweight vector fill did not scale with the region edge")
        hole_x = app._screen(210)
        hole_y = app._screen(170)
        hole_items = app.canvas.find_overlapping(hole_x, hole_y, hole_x, hole_y)
        if any("region_zoom_preview" in app.canvas.gettags(item) for item in hole_items):
            raise SystemExit("Live zoom preview incorrectly filled a region hole")
        app._finish_zoom_refresh()
        if app.zoom_preview_active:
            raise SystemExit("Exact fill did not replace the live zoom preview")
        app.destroy()
    elif "--export-dialog-smoke" in sys.argv or "--export-dialog-smoke-en" in sys.argv:
        app = DrawingCopilotApp()
        app.withdraw()
        language = "en" if "--export-dialog-smoke-en" in sys.argv else "zh"
        dialog = ExportDialog(app, language, modal=False)
        dialog.update()
        if dialog.ai_mode.get() != "indirect":
            raise SystemExit("Indirect AI export mode is not the default")
        if len(dialog.ai_mode_buttons) != 2:
            raise SystemExit("AI export mode does not show two radio buttons")
        dialog.ai_mode_buttons[1].invoke()
        if dialog.ai_mode.get() != "direct":
            raise SystemExit("Direct AI export radio button is not selectable")
        dialog.preset.set("workflow")
        dialog.update_description()
        if any(not button.instate(["disabled"]) for button in dialog.ai_mode_buttons):
            raise SystemExit("AI mode radio buttons stay enabled for another preset")
        dialog.preset.set("weak_ai")
        dialog.update_description()
        if dialog.weak_mode.get() != "compact" or len(dialog.weak_mode_buttons) != 3:
            raise SystemExit("Weak-AI TXT modes are incomplete or have the wrong default")
        if any(button.instate(["disabled"]) for button in dialog.weak_mode_buttons):
            raise SystemExit("Weak-AI TXT mode radio buttons are disabled")
        dialog.weak_mode_buttons[1].invoke()
        if dialog.weak_mode.get() != "indirect":
            raise SystemExit("Weak-AI indirect TXT mode is not selectable")
        dialog.weak_mode_buttons[2].invoke()
        if dialog.weak_mode.get() != "direct":
            raise SystemExit("Weak-AI direct TXT mode is not selectable")
        dialog.destroy()
        app.destroy()
    elif "--settings-smoke" in sys.argv or "--settings-smoke-en" in sys.argv:
        app = DrawingCopilotApp()
        language = "en" if "--settings-smoke-en" in sys.argv else "zh"
        app.withdraw()
        dialog = SettingsDialog(app, app.settings, language, modal=False)
        dialog.update()
        if dialog.winfo_rootx() < 0 or dialog.winfo_rooty() < 0:
            raise SystemExit("Settings dialog starts outside the screen")
        if dialog.winfo_rootx() + dialog.winfo_width() > dialog.winfo_screenwidth():
            raise SystemExit("Settings dialog exceeds screen width")
        if dialog.winfo_rooty() + dialog.winfo_height() > dialog.winfo_screenheight():
            raise SystemExit("Settings dialog exceeds screen height")
        expected_background = dialog.settings_footer.winfo_toplevel().tk.call(
            "ttk::style", "lookup", "TFrame", "-background"
        )
        if dialog.settings_canvas.cget("background") != expected_background:
            raise SystemExit("Settings dialog canvas background does not match the footer")
        if dialog.settings_footer.winfo_width() != dialog.winfo_width():
            raise SystemExit("Settings footer does not span the dialog width")
        dialog.destroy()
        app.destroy()
    elif "--fullscreen-smoke" in sys.argv:
        app = DrawingCopilotApp()
        app.attributes("-alpha", 0.0)
        app.geometry("1100x720+80+60")
        app.update()
        saved_geometry = app.normal_window_geometry
        app.state("zoomed")
        app.update()
        app.toggle_fullscreen(True)
        app.update()
        if not app.is_fullscreen or app.fullscreen_button.cget("text") != "窗口":
            raise SystemExit("Chinese fullscreen button did not switch to Window")
        app.language = "en"
        app._rebuild_localized_ui()
        app.update()
        if any(button.winfo_manager() != "grid" for button in app.toolbar_action_buttons):
            raise SystemExit("Toolbar actions disappeared after language switch")
        if app.fullscreen_button.cget("text") != "Window":
            raise SystemExit("English fullscreen button did not switch to Window")
        app.toggle_fullscreen(False)
        app.update()
        if app.is_fullscreen or app.state() != "zoomed":
            raise SystemExit("Fullscreen did not return to maximized window state")
        if app.fullscreen_button.cget("text") != "Fullscreen":
            raise SystemExit("Fullscreen button did not restore its normal label")
        app.state("normal")
        app.update()
        saved_size = saved_geometry.split("+", 1)[0]
        if app.geometry().split("+", 1)[0] != saved_size:
            raise SystemExit("Normal window geometry was replaced by the fullscreen size")
        app.destroy()
    elif "--ui-smoke" in sys.argv or "--ui-smoke-en" in sys.argv:
        app = DrawingCopilotApp()
        if "--ui-smoke-en" in sys.argv:
            app.language = "en"
            app.default_category.set("General area")
            app.edit_mode_display.set(app._edit_mode_label(app.edit_mode.get()))
            app.draw_tool_display.set(app._draw_tool_label(app.draw_tool.get()))
            app._rebuild_localized_ui()
        app.project.add_region(
            Region(
                name="UI自检自由区域",
                x=0,
                y=0,
                width=1,
                height=1,
                shape="polygon",
                points=[[40, 40], [180, 60], [160, 180], [70, 160]],
                category="rough",
            )
        )
        app.refresh_canvas()
        app.refresh_region_list()
        app.geometry("1040x680")
        app.update_idletasks()
        app.update()
        action_right = max(
            button.winfo_x() + button.winfo_width()
            for button in app.toolbar_action_buttons
        )
        if action_right > app.toolbar_actions.winfo_width():
            raise SystemExit("Toolbar actions exceed the visible width")

        class SmokeEvent:
            def __init__(self, x: int, y: int) -> None:
                self.x = x
                self.y = y

        app.on_canvas_press(SmokeEvent(240, 240))
        app.on_canvas_drag(SmokeEvent(340, 220))
        app.on_canvas_drag(SmokeEvent(390, 310))
        app.on_canvas_drag(SmokeEvent(260, 340))
        app.on_canvas_release(SmokeEvent(240, 240))
        if len(app.project.regions) < 2:
            raise SystemExit("UI smoke did not create a freehand region")
        app.after(900, app.destroy)
        app.mainloop()
    else:
        run()
