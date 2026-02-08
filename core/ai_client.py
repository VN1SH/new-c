from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Dict, Optional

import requests


class AIClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        cache_enabled: bool,
        cache_path: Path,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.cache_enabled = cache_enabled
        self.cache_path = cache_path
        self.cache = self._load_cache()

    def _load_cache(self) -> Dict:
        if not self.cache_path.exists():
            return {}
        try:
            return json.loads(self.cache_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}

    def _save_cache(self) -> None:
        if not self.cache_enabled:
            return
        self.cache_path.write_text(json.dumps(self.cache, ensure_ascii=False, indent=2), encoding="utf-8")

    def _payload_hash(self, payload: Dict) -> str:
        payload_bytes = json.dumps(payload, sort_keys=True).encode("utf-8")
        return hashlib.sha256(payload_bytes).hexdigest()

    def request_analysis(self, payload: Dict) -> Dict:
        payload_hash = self._payload_hash(payload)
        if self.cache_enabled and payload_hash in self.cache:
            return self.cache[payload_hash]

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        system_prompt = (
            "你是安全审慎的Windows清理顾问。仅返回JSON，不要包含任何额外文本。"
            "JSON必须包含advice与report两部分，字段结构与客户端schema一致。"
        )
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            "temperature": 0.2,
        }

        url = f"{self.base_url}/v1/chat/completions"
        last_error: Optional[Exception] = None
        for attempt in range(3):
            try:
                response = requests.post(url, headers=headers, json=body, timeout=60)
                response.raise_for_status()
                data = response.json()
                content = data["choices"][0]["message"]["content"]
                parsed = json.loads(content)
                if self.cache_enabled:
                    self.cache[payload_hash] = parsed
                    self._save_cache()
                return parsed
            except Exception as exc:
                last_error = exc
                time.sleep(2 ** attempt)
        raise RuntimeError(f"AI call failed: {last_error}")
