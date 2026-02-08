from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import asdict
from pathlib import Path
from typing import Dict, List

from core.scanner import ScanItem


class Analyzer:
    def __init__(self, items: List[ScanItem]):
        self.items = items

    def build_stats(self) -> Dict:
        ext_breakdown = defaultdict(lambda: {"size": 0, "count": 0})
        folder_breakdown = defaultdict(lambda: {"size": 0, "count": 0})
        category_breakdown = defaultdict(lambda: {"size": 0, "count": 0})

        for item in self.items:
            path = Path(item.path)
            ext = path.suffix.lower() or "<none>"
            ext_breakdown[ext]["size"] += item.size_bytes
            ext_breakdown[ext]["count"] += 1

            folder = str(path.parent)
            folder_breakdown[folder]["size"] += item.size_bytes
            folder_breakdown[folder]["count"] += 1

            category_breakdown[item.category]["size"] += item.size_bytes
            category_breakdown[item.category]["count"] += 1

        top_files = sorted(self.items, key=lambda x: x.size_bytes, reverse=True)[:50]
        top_folders = sorted(folder_breakdown.items(), key=lambda x: x[1]["size"], reverse=True)[:50]

        return {
            "ext_breakdown": ext_breakdown,
            "folder_breakdown": folder_breakdown,
            "category_breakdown": category_breakdown,
            "top_files": [asdict(item) for item in top_files],
            "top_folders": [{"path": path, **data} for path, data in top_folders],
        }

    @staticmethod
    def write_stats(stats: Dict, path: Path) -> None:
        serializable = {
            "ext_breakdown": stats.get("ext_breakdown"),
            "folder_breakdown": stats.get("folder_breakdown"),
            "category_breakdown": stats.get("category_breakdown"),
            "top_files": stats.get("top_files"),
            "top_folders": stats.get("top_folders"),
        }
        path.write_text(json.dumps(serializable, ensure_ascii=False, indent=2), encoding="utf-8")
