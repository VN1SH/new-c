from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, Iterable, List

from send2trash import send2trash

from core.rules import is_forbidden
from core.scanner import ScanItem


@dataclass
class CleanupResult:
    deleted: List[Dict]
    failed: List[Dict]
    skipped: List[Dict]

    def to_dict(self) -> Dict:
        return {
            "deleted": self.deleted,
            "failed": self.failed,
            "skipped": self.skipped,
        }


class Cleaner:
    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run

    def clean(self, items: Iterable[ScanItem], allow_delete: bool = False) -> CleanupResult:
        deleted: List[Dict] = []
        failed: List[Dict] = []
        skipped: List[Dict] = []

        for item in items:
            path = Path(item.path)
            if item.is_suggestion_only or item.is_forbidden or is_forbidden(path):
                skipped.append({"path": item.path, "reason": "forbidden_or_suggestion"})
                continue
            if not path.exists():
                skipped.append({"path": item.path, "reason": "missing"})
                continue
            if self.dry_run:
                deleted.append({"path": item.path, "bytes": item.size_bytes, "dry_run": True})
                continue
            try:
                send2trash(str(path))
                deleted.append({"path": item.path, "bytes": item.size_bytes, "method": "trash"})
            except Exception as exc:
                if allow_delete:
                    try:
                        if path.is_dir():
                            os.rmdir(path)
                        else:
                            path.unlink()
                        deleted.append({"path": item.path, "bytes": item.size_bytes, "method": "delete"})
                    except Exception as inner:
                        failed.append({"path": item.path, "error": str(inner)})
                else:
                    failed.append({"path": item.path, "error": str(exc)})
        return CleanupResult(deleted, failed, skipped)


def write_cleanup_plan(items: Iterable[ScanItem], path: Path) -> None:
    payload = [asdict(item) for item in items]
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_cleanup_result(result: CleanupResult, path: Path) -> None:
    path.write_text(json.dumps(result.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
