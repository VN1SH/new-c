from __future__ import annotations

import copy
import re
from pathlib import Path
from typing import Dict, List

from core.scanner import ScanItem


LEVEL_ORDER = {"L1": 1, "L2": 2, "L3": 3, "L4": 4, "L5": 5}

CATEGORY_LABELS_CN = {
    "system_core_files": "系统核心文件",
    "driver_packages": "驱动与设备包",
    "windows_update_cache": "Windows 更新缓存",
    "system_temp_files": "系统临时文件",
    "temporary_files": "用户临时文件",
    "app_runtime_cache": "软件运行缓存",
    "package_manager_cache": "开发包管理缓存",
    "browser_cache_files": "浏览器缓存",
    "browser_profile_data": "浏览器配置/站点数据",
    "thumbnail_cache_files": "缩略图缓存",
    "crash_dump_files": "崩溃转储文件",
    "application_log_files": "应用日志文件",
    "game_data": "游戏数据",
    "chat_media_data": "聊天软件数据",
    "image_raster_files": "图片-位图",
    "image_vector_files": "图片-矢量图",
    "image_raw_files": "图片-RAW源片",
    "video_standard_files": "视频-常规格式",
    "video_production_files": "视频-制作素材",
    "audio_lossy_files": "音频-有损",
    "audio_lossless_files": "音频-无损",
    "word_documents": "文档-文本/Word",
    "spreadsheet_documents": "文档-表格",
    "presentation_documents": "文档-演示文稿",
    "pdf_documents": "文档-PDF",
    "document_text_files": "文档-纯文本",
    "structured_data_documents": "文档-结构化数据",
    "archive_files": "压缩文件",
    "disk_image_files": "磁盘镜像",
    "database_files": "数据库文件",
    "virtual_machine_files": "虚拟机镜像",
    "source_code_files": "源代码",
    "script_files": "脚本文件",
    "installer_packages": "安装包",
    "executable_binaries": "可执行/二进制",
    "software_runtime_files": "软件程序文件",
    "font_files": "字体文件",
    "large_files": "超大文件",
    "other_files": "其他文件",
}

CATEGORY_POLICY = {
    "temporary_files": ("L1", "用户临时文件，通常可安全清理。", "低风险。"),
    "system_temp_files": ("L2", "系统临时文件一般可清理。", "中低风险。"),
    "app_runtime_cache": ("L1", "应用运行缓存可再生。", "低风险。"),
    "browser_cache_files": ("L1", "浏览器缓存可再生。", "低风险。"),
    "thumbnail_cache_files": ("L1", "缩略图缓存可重建。", "低风险。"),
    "application_log_files": ("L2", "日志文件通常可清理。", "中低风险。"),
    "crash_dump_files": ("L2", "崩溃转储多用于排障。", "中低风险。"),
    "windows_update_cache": ("L2", "Windows 更新缓存通常可清理。", "中低风险。"),
    "package_manager_cache": ("L2", "开发包管理缓存可重新下载。", "中低风险。"),
    "archive_files": ("L3", "压缩文件可能是备份或安装包。", "中风险。"),
    "disk_image_files": ("L3", "磁盘镜像体积大且可能复用。", "中风险。"),
    "installer_packages": ("L3", "旧安装包通常可清理。", "中风险。"),
    "large_files": ("L3", "大文件可释放明显空间。", "中风险。"),
    "image_raw_files": ("L4", "RAW 原片通常是源素材。", "高风险。"),
    "video_production_files": ("L4", "视频制作素材通常不可再生。", "高风险。"),
    "audio_lossless_files": ("L3", "无损音频体积较大但可能重要。", "中风险。"),
    "database_files": ("L4", "数据库文件可能包含关键数据。", "高风险。"),
    "virtual_machine_files": ("L5", "虚拟机镜像是完整环境。", "极高风险。"),
    "browser_profile_data": ("L4", "浏览器配置/站点数据可能含登录态。", "高风险。"),
    "chat_media_data": ("L4", "聊天软件数据可能包含历史记录和附件。", "高风险。"),
    "word_documents": ("L4", "文本文档/Word 可能是工作资料。", "高风险。"),
    "spreadsheet_documents": ("L4", "表格文档可能包含关键业务数据。", "高风险。"),
    "presentation_documents": ("L4", "演示文稿可能为业务资产。", "高风险。"),
    "pdf_documents": ("L4", "PDF 可能为合同或归档文档。", "高风险。"),
    "source_code_files": ("L4", "源代码通常属于核心资产。", "高风险。"),
    "script_files": ("L4", "脚本可能参与自动化流程。", "高风险。"),
    "executable_binaries": ("L4", "二进制文件可能是程序运行组件。", "高风险。"),
    "software_runtime_files": ("L5", "程序目录文件不应批量删除。", "极高风险。"),
    "system_core_files": ("L5", "系统核心文件不应清理。", "极高风险。"),
    "driver_packages": ("L5", "驱动文件影响硬件稳定性。", "极高风险。"),
}


def _level_up(level: str) -> str:
    order = min(5, LEVEL_ORDER.get(level, 3) + 1)
    return f"L{order}"


def _safe_float(value: object, default: float = 0.0) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except Exception:
        return default


def _format_bytes(value: int) -> str:
    number = float(value)
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if number < 1024:
            return f"{number:.2f} {unit}"
        number /= 1024
    return f"{number:.2f} PB"


def _contains_cjk(text: object) -> bool:
    if not isinstance(text, str):
        return False
    return bool(re.search(r"[\u4e00-\u9fff]", text))


def _prefer_cn_text(current_value: object, remote_value: object) -> str:
    current_text = str(current_value or "")
    remote_text = str(remote_value or "")
    if _contains_cjk(remote_text):
        return remote_text
    return current_text


def _prefer_cn_list(current_value: object, remote_value: object) -> List[str]:
    current_list = [str(x) for x in current_value] if isinstance(current_value, list) else []
    if not isinstance(remote_value, list):
        return current_list
    remote_list = [str(x) for x in remote_value if x is not None]
    if remote_list and any(_contains_cjk(x) for x in remote_list):
        return remote_list
    return current_list


def _obj_has_cjk(value: object) -> bool:
    if isinstance(value, str):
        return _contains_cjk(value)
    if isinstance(value, list):
        return any(_obj_has_cjk(v) for v in value)
    if isinstance(value, dict):
        return any(_obj_has_cjk(v) for v in value.values())
    return False


def _build_item_advice(item: ScanItem, item_id: int) -> Dict:
    level, reason, risk_notes = CATEGORY_POLICY.get(
        item.category,
        ("L3", "该类别需要人工核验。", "中风险。"),
    )

    if item.is_forbidden:
        level = "L5"
        reason = "受保护路径。"
        risk_notes = "极高风险。"

    if item.rule_risk == "medium" and level == "L1":
        level = "L2"
    if item.rule_risk == "forbidden":
        level = "L5"
    if item.rule_risk == "suggest" and LEVEL_ORDER[level] < 3:
        level = "L3"
    if item.is_suggestion_only and LEVEL_ORDER[level] < 3:
        level = "L3"
    if item.is_recent and LEVEL_ORDER[level] <= 2:
        level = _level_up(level)

    path_lower = item.path.lower()
    if path_lower.startswith("c:\\windows\\") and "temp" not in path_lower and LEVEL_ORDER[level] < 5:
        level = "L5"
        reason = "Windows 系统目录文件。"
        risk_notes = "极高风险。"

    if level == "L1":
        action = "可直接清理"
    elif level == "L2":
        action = "建议关闭相关软件后清理"
    elif level == "L3":
        action = "建议备份或确认后再清理"
    elif level == "L4":
        action = "仅在人工确认后清理"
    else:
        action = "建议保留，不执行自动清理"

    base_confidence = {"L1": 0.95, "L2": 0.88, "L3": 0.78, "L4": 0.68, "L5": 0.96}.get(level, 0.75)
    if item.is_recent:
        base_confidence = max(0.55, base_confidence - 0.1)
    if item.rule_risk == "suggest":
        base_confidence = max(0.5, base_confidence - 0.08)

    return {
        "item_id": item_id,
        "target": item.path,
        "file_name": Path(item.path).name,
        "level": level,
        "confidence": round(base_confidence, 2),
        "reason": reason,
        "risk_notes": risk_notes,
        "recommended_action": action,
        "requires_confirmation": level in {"L4", "L5"},
        "estimated_savings_bytes": int(item.size_bytes),
    }


def _build_level_groups(items: List[Dict]) -> Dict[str, List[Dict]]:
    groups: Dict[str, List[Dict]] = {f"L{i}": [] for i in range(1, 6)}
    for item in items:
        level = str(item.get("level", "L3")).upper()
        groups.setdefault(level, []).append(item)
    return groups


def _build_summary_and_diagnosis(items: List[Dict], stats: Dict) -> Dict:
    category_breakdown = stats.get("category_breakdown", {}) if isinstance(stats, dict) else {}
    sorted_categories = sorted(
        [(k, v) for k, v in category_breakdown.items() if isinstance(v, dict)],
        key=lambda x: x[1].get("size", 0),
        reverse=True,
    )

    level_counts = {f"L{i}": 0 for i in range(1, 6)}
    estimated_savings_bytes = 0
    for item in items:
        level = str(item.get("level", "L3")).upper()
        if level in level_counts:
            level_counts[level] += 1
        if level in {"L1", "L2", "L3"}:
            estimated_savings_bytes += int(item.get("estimated_savings_bytes", 0) or 0)

    top_text = []
    for category, payload in sorted_categories[:4]:
        size = int(payload.get("size", 0) or 0)
        count = int(payload.get("count", 0) or 0)
        category_name = CATEGORY_LABELS_CN.get(category, category)
        top_text.append(f"{category_name}: {_format_bytes(size)} / {count} 项")

    high_risk_count = level_counts["L4"] + level_counts["L5"]
    diagnosis = {
        "summary": (
            f"本次识别到 {len(items)} 项候选文件，预计可释放 "
            f"{_format_bytes(estimated_savings_bytes)}，其中 L4-L5 共 {high_risk_count} 项。"
        ),
        "highlights": top_text,
        "risks": [
            "L4/L5 涉及系统、文档、数据库或运行组件，请谨慎处理。",
            "近期修改文件会自动提升谨慎等级，避免误删正在使用的数据。",
        ],
        "actions": [
            "先清理 L1，再评估 L2。",
            "L3 建议小批次处理，并保留回退窗口。",
            "L4/L5 仅用于人工核验，不建议自动清理。",
        ],
    }
    return {"estimated_savings_bytes": estimated_savings_bytes, "level_counts": level_counts, "diagnosis": diagnosis}


def build_local_ai_result(items: List[ScanItem], stats: Dict) -> Dict:
    advice_items = [_build_item_advice(item, idx) for idx, item in enumerate(items)]
    advice_items.sort(key=lambda x: (LEVEL_ORDER.get(str(x.get("level", "L3")).upper(), 3), -x.get("estimated_savings_bytes", 0)))

    summary_payload = _build_summary_and_diagnosis(advice_items, stats)
    level_groups = _build_level_groups(advice_items)

    advice = {
        "summary": {
            "estimated_savings_bytes": summary_payload["estimated_savings_bytes"],
            "level_counts": summary_payload["level_counts"],
            "key_risks": summary_payload["diagnosis"]["risks"],
        },
        "diagnosis": summary_payload["diagnosis"],
        "level_groups": level_groups,
        "items": advice_items,
    }

    report = {
        "overview": summary_payload["diagnosis"]["summary"],
        "findings": {
            "quick_wins": [
                "L1-L2 通常包含临时文件、缓存和日志。",
                "按体积优先处理可快速释放空间。",
            ],
            "medium_risks": [
                "L3 常见于安装包、压缩包和大文件。",
            ],
            "do_not_touch": [
                "L5 多为系统核心或驱动相关文件。",
            ],
        },
        "recommendations": {
            "cleanup_strategy": [
                "建议按 L1 -> L2 -> L3 的顺序推进。",
                "每批清理后先验证系统和应用稳定性。",
            ],
            "non_delete_options": [
                "大文件优先迁移到非系统盘。",
                "重要文件优先归档而非删除。",
            ],
        },
    }
    return {"advice": advice, "report": report}


def merge_remote_into_local(local_result: Dict, remote_result: Dict, items: List[ScanItem]) -> Dict:
    del items  # reserved for future use
    if not isinstance(remote_result, dict):
        return local_result

    merged = copy.deepcopy(local_result)
    local_advice = merged.get("advice", {})
    local_items = local_advice.get("items", [])
    if not isinstance(local_items, list):
        return merged

    by_item_id = {}
    by_path = {}
    for idx, item in enumerate(local_items):
        if not isinstance(item, dict):
            continue
        item_id = item.get("item_id")
        if isinstance(item_id, int):
            by_item_id[item_id] = idx
        target = str(item.get("target", "")).lower()
        if target:
            by_path[target] = idx

    remote_advice = remote_result.get("advice", {}) if isinstance(remote_result.get("advice", {}), dict) else {}
    remote_items = remote_advice.get("items", [])
    applied = 0
    if isinstance(remote_items, list):
        for raw in remote_items:
            if not isinstance(raw, dict):
                continue
            local_index = None
            remote_item_id = raw.get("item_id")
            if isinstance(remote_item_id, int) and remote_item_id in by_item_id:
                local_index = by_item_id[remote_item_id]
            else:
                target = str(raw.get("target", "")).lower()
                if target in by_path:
                    local_index = by_path[target]
            if local_index is None:
                continue

            current = local_items[local_index]
            level = str(raw.get("level", current.get("level", "L3"))).upper()
            if level not in LEVEL_ORDER:
                level = str(current.get("level", "L3")).upper()
            current["level"] = level
            current["confidence"] = round(_safe_float(raw.get("confidence", current.get("confidence", 0.0))), 2)
            current["reason"] = _prefer_cn_text(current.get("reason", ""), raw.get("reason", ""))
            current["risk_notes"] = _prefer_cn_text(current.get("risk_notes", ""), raw.get("risk_notes", ""))
            current["recommended_action"] = _prefer_cn_text(
                current.get("recommended_action", ""), raw.get("recommended_action", "")
            )
            current["requires_confirmation"] = bool(raw.get("requires_confirmation", level in {"L4", "L5"}))
            if raw.get("estimated_savings_bytes") is not None:
                current["estimated_savings_bytes"] = int(raw.get("estimated_savings_bytes", current.get("estimated_savings_bytes", 0)) or 0)
            applied += 1

    remote_diagnosis = remote_advice.get("diagnosis", {})
    if isinstance(remote_diagnosis, dict):
        diagnosis = local_advice.get("diagnosis", {})
        if isinstance(diagnosis, dict):
            diagnosis["summary"] = _prefer_cn_text(diagnosis.get("summary", ""), remote_diagnosis.get("summary", ""))
            diagnosis["highlights"] = _prefer_cn_list(diagnosis.get("highlights", []), remote_diagnosis.get("highlights", []))
            diagnosis["risks"] = _prefer_cn_list(diagnosis.get("risks", []), remote_diagnosis.get("risks", []))
            diagnosis["actions"] = _prefer_cn_list(diagnosis.get("actions", []), remote_diagnosis.get("actions", []))
            local_advice["diagnosis"] = diagnosis

    remote_report = remote_result.get("report", {})
    if isinstance(remote_report, dict) and remote_report and _obj_has_cjk(remote_report):
        merged["report"] = remote_report

    local_advice["items"] = local_items
    local_advice["level_groups"] = _build_level_groups(local_items)

    level_counts = {f"L{i}": 0 for i in range(1, 6)}
    estimated_savings_bytes = 0
    for item in local_items:
        if not isinstance(item, dict):
            continue
        level = str(item.get("level", "L3")).upper()
        if level in level_counts:
            level_counts[level] += 1
        if level in {"L1", "L2", "L3"}:
            estimated_savings_bytes += int(item.get("estimated_savings_bytes", 0) or 0)
    local_advice["summary"] = {
        "estimated_savings_bytes": estimated_savings_bytes,
        "level_counts": level_counts,
        "key_risks": local_advice.get("diagnosis", {}).get("risks", []) if isinstance(local_advice.get("diagnosis"), dict) else [],
        "remote_applied_items": applied,
    }
    merged["advice"] = local_advice
    return merged
