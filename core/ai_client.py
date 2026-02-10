from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path
from typing import Callable, Dict, Optional

import requests

ProgressCallback = Callable[[Dict], None]


class AIClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        cache_enabled: bool,
        cache_path: Path,
        progress_callback: Optional[ProgressCallback] = None,
    ):
        self.base_url = self.normalize_base_url(base_url)
        self.api_key = api_key
        self.model = model
        self.cache_enabled = cache_enabled
        self.cache_path = cache_path
        self.progress_callback = progress_callback
        self.cache = self._load_cache()

    @staticmethod
    def normalize_base_url(base_url: str) -> str:
        text = (base_url or "").strip().rstrip("/")
        if not text:
            return ""
        if re.search(r"/v1($|/)", text, flags=re.IGNORECASE):
            return text
        return f"{text}/v1"

    @staticmethod
    def _build_headers(api_key: str) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        return headers

    @staticmethod
    def fetch_models(base_url: str, api_key: str, timeout: int = 20) -> list[str]:
        url = f"{AIClient.normalize_base_url(base_url)}/models"
        response = requests.get(url, headers=AIClient._build_headers(api_key), timeout=timeout)
        response.raise_for_status()
        data = response.json() if response.content else {}
        models = []
        for item in data.get("data", []) if isinstance(data, dict) else []:
            if isinstance(item, dict):
                model_id = str(item.get("id", "")).strip()
                if model_id:
                    models.append(model_id)
        seen = set()
        unique = []
        for model in models:
            if model not in seen:
                seen.add(model)
                unique.append(model)
        return unique

    @staticmethod
    def test_connection(base_url: str, api_key: str, model: str, timeout: int = 25) -> Dict[str, object]:
        normalized = AIClient.normalize_base_url(base_url)
        if not normalized:
            return {"ok": False, "message": "Base URL 为空。"}
        if not api_key:
            return {"ok": False, "message": "API Key 为空。"}
        if not model:
            return {"ok": False, "message": "模型为空。"}

        url = f"{normalized}/chat/completions"
        body = {
            "model": model,
            "messages": [
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "请回复：连接测试成功"},
            ],
            "temperature": 0,
            "max_tokens": 20,
        }
        response = requests.post(url, headers=AIClient._build_headers(api_key), json=body, timeout=timeout)
        response.raise_for_status()
        data = response.json() if response.content else {}
        choices = data.get("choices", []) if isinstance(data, dict) else []
        if not choices:
            return {"ok": False, "message": "接口可达，但返回内容缺少 choices。"}
        content = str(choices[0].get("message", {}).get("content", "")).strip()
        if not content:
            content = "连接成功，但返回内容为空。"
        return {"ok": True, "message": content}

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

    def _emit_progress(self, stage: str, detail: str, attempt: int = 0) -> None:
        if not self.progress_callback:
            return
        payload = {
            "stage": stage,
            "detail": detail,
            "attempt": attempt,
            "timestamp": time.time(),
        }
        try:
            self.progress_callback(payload)
        except Exception:
            pass

    def _extract_json_text(self, content: str) -> str:
        text = (content or "").strip()
        if text.startswith("```"):
            lines = text.splitlines()
            if len(lines) >= 3:
                text = "\n".join(lines[1:-1]).strip()
        if text.startswith("{") and text.endswith("}"):
            return text
        first = text.find("{")
        last = text.rfind("}")
        if first != -1 and last != -1 and first < last:
            return text[first : last + 1]
        return text

    def _normalize_result(self, data: Dict) -> Dict:
        if not isinstance(data, dict):
            return {
                "advice": {"diagnosis": {"summary": ""}, "items": [], "level_groups": {}},
                "report": {"overview": str(data)},
            }

        advice = data.get("advice")
        report = data.get("report")
        if not isinstance(advice, dict):
            advice = {}
        if not isinstance(report, dict):
            report = {"overview": report if report is not None else ""}

        diagnosis = advice.get("diagnosis")
        if not isinstance(diagnosis, dict):
            legacy_summary = advice.get("summary", {})
            if isinstance(legacy_summary, dict):
                diagnosis = {
                    "summary": legacy_summary.get("text", ""),
                    "highlights": legacy_summary.get("highlights", []),
                    "risks": legacy_summary.get("key_risks", []),
                    "actions": [],
                }
            else:
                diagnosis = {"summary": "", "highlights": [], "risks": [], "actions": []}
        diagnosis.setdefault("summary", "")
        diagnosis.setdefault("highlights", [])
        diagnosis.setdefault("risks", [])
        diagnosis.setdefault("actions", [])
        advice["diagnosis"] = diagnosis

        if not isinstance(advice.get("items"), list):
            advice["items"] = []

        normalized_items = []
        for raw_item in advice.get("items", []):
            if not isinstance(raw_item, dict):
                continue
            level = str(raw_item.get("level", "L3")).upper()
            if level not in {"L1", "L2", "L3", "L4", "L5"}:
                level = "L3"
            normalized_items.append(
                {
                    "item_id": raw_item.get("item_id"),
                    "target": str(raw_item.get("target", "")),
                    "file_name": str(raw_item.get("file_name", "")),
                    "level": level,
                    "confidence": raw_item.get("confidence", 0.0),
                    "reason": str(raw_item.get("reason", "")),
                    "risk_notes": str(raw_item.get("risk_notes", "")),
                    "recommended_action": str(raw_item.get("recommended_action", "")),
                    "requires_confirmation": bool(raw_item.get("requires_confirmation", level in {"L4", "L5"})),
                    "estimated_savings_bytes": int(raw_item.get("estimated_savings_bytes", 0) or 0),
                }
            )
        advice["items"] = normalized_items

        level_groups = advice.get("level_groups", {})
        if not isinstance(level_groups, dict):
            level_groups = {}
        if not level_groups:
            grouped: dict[str, list] = {f"L{i}": [] for i in range(1, 6)}
            for item in advice["items"]:
                grouped.setdefault(item["level"], []).append(item)
            level_groups = grouped
        advice["level_groups"] = level_groups
        return {"advice": advice, "report": report}

    def request_analysis(self, payload: Dict) -> Dict:
        self._emit_progress("prepare", "正在准备 AI 请求数据...")
        payload_hash = self._payload_hash(payload)

        if self.cache_enabled and payload_hash in self.cache:
            self._emit_progress("cache_hit", "已命中本地缓存。")
            return self._normalize_result(self.cache[payload_hash])

        self._emit_progress("cache_miss", "未命中缓存，准备发起请求...")
        headers = self._build_headers(self.api_key)
        system_prompt = (
            "You are a cautious Windows cleanup advisor for C drive analysis. "
            "Return JSON only. "
            "The JSON must contain two top-level fields: advice and report. "
            "advice must include diagnosis and items. "
            "diagnosis fields: summary, highlights[], risks[], actions[]. "
            "You must rate each input item from identity list with exactly five levels L1-L5. "
            "You must return one advice item per item_id and cannot skip items. "
            "Each returned item must preserve the original file_name and path. "
            "Each item fields: item_id, target, file_name, level(L1-L5), confidence(0-1), "
            "reason, risk_notes, recommended_action, requires_confirmation, estimated_savings_bytes. "
            "Use Chinese for all natural-language fields. "
            "Never use English for diagnosis sentences unless user explicitly asks for English. "
            "Do not return markdown."
        )
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            "temperature": 0.2,
        }

        url = f"{self.base_url}/chat/completions"
        last_error: Optional[Exception] = None

        for attempt in range(1, 4):
            try:
                self._emit_progress("request", f"调用模型接口（第 {attempt}/3 次）...", attempt=attempt)
                response = requests.post(url, headers=headers, json=body, timeout=90)
                response.raise_for_status()
                data = response.json()

                self._emit_progress("parse", "正在解析模型返回...", attempt=attempt)
                choices = data.get("choices") if isinstance(data, dict) else None
                if not choices:
                    raise RuntimeError("API response missing choices")
                message = choices[0].get("message", {})
                content = message.get("content", "")
                json_text = self._extract_json_text(content)
                parsed = json.loads(json_text)
                parsed = self._normalize_result(parsed)

                if self.cache_enabled:
                    self.cache[payload_hash] = parsed
                    self._save_cache()

                self._emit_progress("done", "AI 分析完成。")
                return parsed
            except Exception as exc:
                last_error = exc
                self._emit_progress("retry", f"第 {attempt} 次失败：{exc}", attempt=attempt)
                time.sleep(2 ** (attempt - 1))

        self._emit_progress("failed", f"AI 分析失败：{last_error}")
        raise RuntimeError(f"AI call failed: {last_error}")
