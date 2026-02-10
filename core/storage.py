from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict


def get_runtime_dir() -> Path:
    local_appdata = os.environ.get("LOCALAPPDATA")
    base_dir = Path(local_appdata) if local_appdata else (Path.home() / "AppData" / "Local")
    runtime = base_dir / "new-c" / "runtime"
    runtime.mkdir(parents=True, exist_ok=True)
    return runtime


def load_json(path: Path, default: Dict) -> Dict:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def write_json(path: Path, payload: Dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
