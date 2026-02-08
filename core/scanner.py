from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from core.rules import (
    build_rules,
    duplicate_scan_dirs,
    is_forbidden,
    match_rule,
    suggestion_targets,
)

RECENT_SECONDS = 60 * 60 * 24


@dataclass
class ScanItem:
    path: str
    size_bytes: int
    mtime: float
    ctime: float
    category: str
    rule_name: str
    rule_risk: str
    ai_level: str = "L3"
    ai_reason: str = ""
    ai_confidence: float = 0.0
    ai_requires_confirmation: bool = False
    is_recent: bool = False
    is_forbidden: bool = False
    is_suggestion_only: bool = False

    def to_dict(self) -> Dict:
        return asdict(self)


class ScanResult:
    def __init__(self, items: List[ScanItem], skipped: List[str], duration: float):
        self.items = items
        self.skipped = skipped
        self.duration = duration

    def to_dict(self) -> Dict:
        return {
            "items": [item.to_dict() for item in self.items],
            "skipped": self.skipped,
            "duration": self.duration,
        }


class Scanner:
    def __init__(self, stop_flag: Optional[Dict[str, bool]] = None):
        self.rules = build_rules()
        self.stop_flag = stop_flag or {"stop": False}

    def scan(self) -> ScanResult:
        start = time.time()
        items: List[ScanItem] = []
        skipped: List[str] = []

        for rule in self.rules:
            for base in rule.base_paths:
                if self.stop_flag.get("stop"):
                    break
                if not base.exists():
                    continue
                for root, dirs, files in os.walk(base, topdown=True):
                    if self.stop_flag.get("stop"):
                        break
                    current = Path(root)
                    if is_forbidden(current):
                        dirs[:] = []
                        continue
                    for file in files:
                        if self.stop_flag.get("stop"):
                            break
                        path = current / file
                        if is_forbidden(path):
                            continue
                        matched = match_rule(path, [rule])
                        if not matched:
                            continue
                        try:
                            stat = path.stat()
                        except (PermissionError, FileNotFoundError, OSError) as exc:
                            skipped.append(f"{path}: {exc}")
                            continue
                        is_recent = (time.time() - stat.st_mtime) < RECENT_SECONDS
                        items.append(
                            ScanItem(
                                path=str(path),
                                size_bytes=stat.st_size,
                                mtime=stat.st_mtime,
                                ctime=stat.st_ctime,
                                category=rule.category,
                                rule_name=rule.name,
                                rule_risk=rule.risk,
                                is_recent=is_recent,
                                is_forbidden=False,
                                is_suggestion_only=False,
                            )
                        )
        items.extend(self._suggestions(skipped))
        duration = time.time() - start
        return ScanResult(items, skipped, duration)

    def _suggestions(self, skipped: List[str]) -> List[ScanItem]:
        suggestions: List[ScanItem] = []
        threshold = 500 * 1024 * 1024
        for base in suggestion_targets(threshold):
            if self.stop_flag.get("stop"):
                break
            if not base.exists():
                continue
            for root, _, files in os.walk(base):
                if self.stop_flag.get("stop"):
                    break
                current = Path(root)
                if is_forbidden(current):
                    continue
                for file in files:
                    if self.stop_flag.get("stop"):
                        break
                    path = current / file
                    if is_forbidden(path):
                        continue
                    try:
                        stat = path.stat()
                    except (PermissionError, FileNotFoundError, OSError) as exc:
                        skipped.append(f"{path}: {exc}")
                        continue
                    if stat.st_size < threshold:
                        continue
                    suggestions.append(
                        ScanItem(
                            path=str(path),
                            size_bytes=stat.st_size,
                            mtime=stat.st_mtime,
                            ctime=stat.st_ctime,
                            category="large_files",
                            rule_name="LargeFile",
                            rule_risk="suggest",
                            is_recent=False,
                            is_forbidden=False,
                            is_suggestion_only=True,
                        )
                    )
        return suggestions


def hash_payload(payload: Dict) -> str:
    payload_bytes = json.dumps(payload, sort_keys=True).encode("utf-8")
    return hashlib.sha256(payload_bytes).hexdigest()
