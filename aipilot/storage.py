# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
from typing import Any, Dict

from . import APP_NAME


def app_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def data_dir() -> Path:
    base = app_base_dir()
    if (base / "portable.mode").exists():
        target = base / "data"
    else:
        target = Path(os.environ.get("APPDATA", str(Path.home()))) / APP_NAME
    target.mkdir(parents=True, exist_ok=True)
    return target


def settings_path() -> Path:
    return data_dir() / "settings.json"


def load_settings() -> Dict[str, Any]:
    path = settings_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_settings(settings: Dict[str, Any]) -> None:
    path = settings_path()
    path.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")

