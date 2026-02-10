from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Dict, List

from core.scanner import ScanItem


class PayloadBuilder:
    def __init__(self, mask_paths: bool = False, max_items: int = 5000):
        self.mask_paths = mask_paths
        self.max_items = max_items

    def _mask_path(self, path: str) -> str:
        if not self.mask_paths:
            return path
        tail = "\\".join(Path(path).parts[-3:])
        hashed = hashlib.sha256(path.encode("utf-8")).hexdigest()[:10]
        return f"***\\{tail}#{hashed}"

    def build(self, items: List[ScanItem], stats_summary: Dict, user_intent: Dict) -> Dict:
        index_by_object_id = {id(item): idx for idx, item in enumerate(items)}
        items_limited = items[: self.max_items]

        payload_items = []
        for item in items_limited:
            item_id = index_by_object_id.get(id(item), -1)
            payload_items.append(
                {
                    "item_id": item_id,
                    "file_name": Path(item.path).name,
                    "path": self._mask_path(item.path),
                    "category": item.category,
                    "ext": Path(item.path).suffix.lower(),
                    "size_bytes": int(item.size_bytes),
                    "modified_time": int(item.mtime),
                    "risk_context": {
                        "rule_risk": item.rule_risk,
                        "is_recent": item.is_recent,
                        "is_suggestion_only": item.is_suggestion_only,
                    },
                }
            )

        payload = {
            "identity": payload_items,
            "analysis_stats": stats_summary,
            "user_intent": user_intent,
            "meta": {
                "masked": self.mask_paths,
                "total_items": len(items),
                "payload_items": len(payload_items),
                "rating_levels": ["L1", "L2", "L3", "L4", "L5"],
            },
        }
        return self._auto_trim(payload)

    def _auto_trim(self, payload: Dict) -> Dict:
        serialized = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        if len(serialized) <= 450_000:
            return payload

        # Keep full file list as much as possible; trim heavy stats first.
        if "analysis_stats" in payload:
            payload["analysis_stats"] = {
                "category_breakdown": payload.get("analysis_stats", {}).get("category_breakdown", {}),
            }
        serialized = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        if len(serialized) <= 450_000:
            return payload

        identity = payload.get("identity", [])
        if isinstance(identity, list):
            payload["identity"] = identity[: max(200, len(identity) // 2)]
        return payload

    @staticmethod
    def write_payload(payload: Dict, path: Path) -> None:
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
