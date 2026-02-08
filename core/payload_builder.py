from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Dict, List

from core.scanner import ScanItem


class PayloadBuilder:
    def __init__(self, mask_paths: bool = True, max_items: int = 200, max_sample_paths: int = 20):
        self.mask_paths = mask_paths
        self.max_items = max_items
        self.max_sample_paths = max_sample_paths

    def _mask_path(self, path: str) -> str:
        if not self.mask_paths:
            return path
        tail = "\\".join(Path(path).parts[-3:])
        hashed = hashlib.sha256(path.encode("utf-8")).hexdigest()[:10]
        return f"***\\{tail}#{hashed}"

    def build(self, items: List[ScanItem], stats_summary: Dict, user_intent: Dict) -> Dict:
        items_sorted = sorted(items, key=lambda x: x.size_bytes, reverse=True)[: self.max_items]
        payload_items = []
        for item in items_sorted:
            payload_items.append(
                {
                    "path": self._mask_path(item.path),
                    "normalized_path": self._mask_path(item.path.lower()),
                    "category": item.category,
                    "ext": Path(item.path).suffix.lower(),
                    "size": item.size_bytes,
                    "mtime": item.mtime,
                    "ctime": item.ctime,
                    "risk_context": {
                        "rule_risk": item.rule_risk,
                        "is_suggestion_only": item.is_suggestion_only,
                    },
                }
            )

        clusters = self._build_clusters(items_sorted)
        payload = {
            "identity": payload_items,
            "clusters": clusters,
            "analysis_stats": stats_summary,
            "user_intent": user_intent,
            "meta": {"masked": self.mask_paths, "total_items": len(items)},
        }
        return self._auto_trim(payload)

    def _build_clusters(self, items: List[ScanItem]) -> List[Dict]:
        clusters: Dict[str, Dict] = {}
        for item in items:
            key = str(Path(item.path).parent)
            if key not in clusters:
                clusters[key] = {"path_pattern": self._mask_path(key), "size": 0, "count": 0, "samples": []}
            clusters[key]["size"] += item.size_bytes
            clusters[key]["count"] += 1
            if len(clusters[key]["samples"]) < self.max_sample_paths:
                clusters[key]["samples"].append(self._mask_path(item.path))
        return list(clusters.values())

    def _auto_trim(self, payload: Dict) -> Dict:
        serialized = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        if len(serialized) <= 300_000:
            return payload
        for cluster in payload.get("clusters", []):
            if "samples" in cluster:
                cluster["samples"] = cluster["samples"][: max(5, self.max_sample_paths // 2)]
        serialized = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        if len(serialized) <= 300_000:
            return payload
        payload["identity"] = payload.get("identity", [])[: max(50, self.max_items // 2)]
        return payload

    @staticmethod
    def write_payload(payload: Dict, path: Path) -> None:
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
