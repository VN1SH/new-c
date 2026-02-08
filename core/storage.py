from __future__ import annotations

import json
from pathlib import Path
from typing import Dict


def get_runtime_dir() -> Path:
    runtime = Path(__file__).resolve().parents[1] / "data" / "runtime"
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
