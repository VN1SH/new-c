from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional

from core.rules import build_rules, is_forbidden, match_rule, suggestion_targets

RECENT_SECONDS = 60 * 60 * 24

IMAGE_RASTER_EXT = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".heic", ".avif", ".tif", ".tiff", ".ico"}
IMAGE_VECTOR_EXT = {".svg", ".eps", ".ai"}
IMAGE_RAW_EXT = {".raw", ".cr2", ".cr3", ".nef", ".arw", ".dng", ".orf", ".rw2"}

VIDEO_STANDARD_EXT = {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm", ".m4v", ".ts"}
VIDEO_PRODUCTION_EXT = {".m2ts", ".mts", ".r3d", ".braw", ".dav", ".prores"}

AUDIO_LOSSY_EXT = {".mp3", ".aac", ".ogg", ".m4a", ".wma", ".opus"}
AUDIO_LOSSLESS_EXT = {".flac", ".wav", ".ape", ".alac", ".aiff"}

DOC_WORD_EXT = {".doc", ".docx", ".odt", ".wps", ".rtf"}
DOC_SPREADSHEET_EXT = {".xls", ".xlsx", ".csv", ".tsv", ".ods", ".numbers"}
DOC_PRESENTATION_EXT = {".ppt", ".pptx", ".odp", ".key"}
DOC_PDF_EXT = {".pdf"}
DOC_TEXT_EXT = {".txt", ".md", ".markdown"}
DOC_STRUCTURED_EXT = {".json", ".xml", ".yaml", ".yml", ".toml", ".ini", ".conf", ".cfg"}

ARCHIVE_EXT = {".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz", ".zst"}
DISK_IMAGE_EXT = {".iso", ".img", ".dmg"}

SOURCE_CODE_EXT = {
    ".py",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".java",
    ".go",
    ".rs",
    ".c",
    ".cpp",
    ".h",
    ".hpp",
    ".cs",
    ".php",
    ".rb",
    ".swift",
    ".kt",
    ".sql",
    ".html",
    ".css",
    ".scss",
    ".vue",
}

SCRIPT_EXT = {".bat", ".cmd", ".ps1", ".sh", ".vbs", ".ahk"}

DATABASE_EXT = {".db", ".sqlite", ".sqlite3", ".mdb", ".accdb", ".edb", ".db-wal", ".db-shm"}
VIRTUAL_MACHINE_EXT = {".vhd", ".vhdx", ".vdi", ".vmdk", ".qcow2"}

INSTALLER_EXT = {".msi", ".msix", ".appx", ".cab", ".pkg"}
EXECUTABLE_EXT = {".exe", ".dll", ".sys", ".ocx", ".drv"}
FONT_EXT = {".ttf", ".otf", ".woff", ".woff2"}

GAME_PATH_KEYWORDS = [
    "\\steam\\",
    "\\epic games\\",
    "\\riot games\\",
    "\\blizzard\\",
    "\\battle.net\\",
    "\\minecraft\\",
    "\\games\\",
    "\\hoyoverse\\",
    "\\genshin impact\\",
]

BROWSER_PATH_KEYWORDS = ["\\chrome\\", "\\edge\\", "\\firefox\\", "\\browser\\", "\\msedge\\"]
BROWSER_PROFILE_KEYWORDS = [
    "\\indexeddb\\",
    "\\local storage\\",
    "\\service worker\\",
    "\\session storage\\",
    "\\extension state\\",
    "\\cache storage\\",
    "\\cookies\\",
]
CHAT_PATH_KEYWORDS = [
    "\\wechat\\",
    "\\tencent files\\",
    "\\qq\\",
    "\\ding",
    "\\feishu\\",
    "\\discord\\",
    "\\telegram\\",
    "\\whatsapp\\",
]
PACKAGE_CACHE_KEYWORDS = ["\\pip\\cache\\", "\\npm-cache\\", "\\yarn\\cache\\", "\\nuget\\cache\\"]

ProgressCallback = Callable[[Dict], None]


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
    recommended_action: str = ""
    ai_risk_notes: str = ""
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
    def __init__(
        self,
        stop_flag: Optional[Dict[str, bool]] = None,
        progress_callback: Optional[ProgressCallback] = None,
        progress_interval_sec: float = 0.2,
    ):
        self.rules = build_rules()
        self.stop_flag = stop_flag or {"stop": False}
        self.progress_callback = progress_callback
        self.progress_interval_sec = progress_interval_sec
        self._last_progress_emit = 0.0
        self._files_seen = 0
        self._items_found = 0

    def scan(self) -> ScanResult:
        start = time.time()
        items: List[ScanItem] = []
        skipped: List[str] = []
        seen_paths: set[str] = set()

        self._emit_progress("starting", "Preparing scan...", force=True)

        for rule in self.rules:
            for base in rule.base_paths:
                if self._is_stopped():
                    duration = time.time() - start
                    self._emit_progress("stopped", "Scan stopped by user.", duration=duration, force=True)
                    return ScanResult(items, skipped, duration)

                if not base.exists():
                    continue

                self._emit_progress("scanning_root", str(base), force=True)
                for root, dirs, files in os.walk(base, topdown=True):
                    if self._is_stopped():
                        duration = time.time() - start
                        self._emit_progress("stopped", "Scan stopped by user.", duration=duration, force=True)
                        return ScanResult(items, skipped, duration)

                    current = Path(root)
                    if is_forbidden(current):
                        dirs[:] = []
                        continue

                    for file in files:
                        if self._is_stopped():
                            duration = time.time() - start
                            self._emit_progress("stopped", "Scan stopped by user.", duration=duration, force=True)
                            return ScanResult(items, skipped, duration)

                        path = current / file
                        self._files_seen += 1
                        self._emit_progress("scanning_file", str(path))

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
                        normalized_path = str(path).lower()
                        if normalized_path in seen_paths:
                            continue
                        seen_paths.add(normalized_path)
                        items.append(
                            ScanItem(
                                path=str(path),
                                size_bytes=stat.st_size,
                                mtime=stat.st_mtime,
                                ctime=stat.st_ctime,
                                category=self._classify_path(path, rule.category),
                                rule_name=rule.name,
                                rule_risk=rule.risk,
                                is_recent=is_recent,
                                is_forbidden=False,
                                is_suggestion_only=False,
                            )
                        )
                        self._items_found += 1
                        self._emit_progress("matched", str(path))

        duration = time.time() - start
        self._emit_progress("completed", f"Scan completed in {duration:.1f}s", duration=duration, force=True)
        return ScanResult(items, skipped, duration)

    def _suggestions(self, skipped: List[str]) -> List[ScanItem]:
        suggestions: List[ScanItem] = []
        threshold = 500 * 1024 * 1024
        self._emit_progress("large_file_scan", "Scanning for very large files...", force=True)
        for base in suggestion_targets(threshold):
            if self._is_stopped():
                break
            if not base.exists():
                continue
            for root, _, files in os.walk(base):
                if self._is_stopped():
                    break
                current = Path(root)
                if is_forbidden(current):
                    continue
                for file in files:
                    if self._is_stopped():
                        break
                    path = current / file
                    self._files_seen += 1
                    self._emit_progress("scanning_file", str(path))
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
                            category=self._classify_path(path, "large_files"),
                            rule_name="LargeFile",
                            rule_risk="suggest",
                            is_recent=False,
                            is_forbidden=False,
                            is_suggestion_only=True,
                        )
                    )
                    self._items_found += 1
                    self._emit_progress("matched", str(path))
        return suggestions

    def _classify_path(self, path: Path, fallback: str) -> str:
        path_str = str(path).lower()
        file_name = path.name.lower()
        ext = path.suffix.lower()

        if path_str.startswith("c:\\windows\\") or "\\system32\\" in path_str or ext in {".dll", ".sys", ".mui", ".cat"}:
            return "system_core_files"
        if "softwaredistribution\\download" in path_str:
            return "windows_update_cache"
        if "\\windows\\system32\\driverstore\\" in path_str or ext in {".inf", ".pnf"}:
            return "driver_packages"
        if "\\windows\\temp\\" in path_str:
            return "system_temp_files"
        if any(k in path_str for k in GAME_PATH_KEYWORDS):
            return "game_data"
        if any(k in path_str for k in CHAT_PATH_KEYWORDS):
            return "chat_media_data"
        if "appdata\\local\\temp" in path_str or path_str.endswith(".tmp"):
            return "temporary_files"
        if any(b in path_str for b in BROWSER_PATH_KEYWORDS):
            if any(k in path_str for k in BROWSER_PROFILE_KEYWORDS):
                return "browser_profile_data"
            if "cache" in path_str or "code cache" in path_str or "gpucache" in path_str:
                return "browser_cache_files"
        if "thumbcache" in file_name or ("\\microsoft\\windows\\explorer\\" in path_str and ext in {".db", ".db-wal", ".db-shm"}):
            return "thumbnail_cache_files"
        if any(k in path_str for k in PACKAGE_CACHE_KEYWORDS):
            return "package_manager_cache"
        if "\\crashdumps\\" in path_str or ext == ".dmp":
            return "crash_dump_files"
        if "\\logs\\" in path_str or ext in {".log", ".etl"}:
            return "application_log_files"

        if ext in IMAGE_RAW_EXT:
            return "image_raw_files"
        if ext in IMAGE_VECTOR_EXT:
            return "image_vector_files"
        if ext in IMAGE_RASTER_EXT:
            return "image_raster_files"

        if ext in VIDEO_PRODUCTION_EXT:
            return "video_production_files"
        if ext in VIDEO_STANDARD_EXT:
            return "video_standard_files"

        if ext in AUDIO_LOSSLESS_EXT:
            return "audio_lossless_files"
        if ext in AUDIO_LOSSY_EXT:
            return "audio_lossy_files"

        if ext in DOC_SPREADSHEET_EXT:
            return "spreadsheet_documents"
        if ext in DOC_PRESENTATION_EXT:
            return "presentation_documents"
        if ext in DOC_WORD_EXT:
            return "word_documents"
        if ext in DOC_PDF_EXT:
            return "pdf_documents"
        if ext in DOC_STRUCTURED_EXT:
            return "structured_data_documents"
        if ext in DOC_TEXT_EXT:
            return "document_text_files"

        if ext in ARCHIVE_EXT:
            return "archive_files"
        if ext in DISK_IMAGE_EXT:
            return "disk_image_files"
        if ext in DATABASE_EXT:
            return "database_files"
        if ext in VIRTUAL_MACHINE_EXT:
            return "virtual_machine_files"
        if ext in SOURCE_CODE_EXT:
            return "source_code_files"
        if ext in SCRIPT_EXT:
            return "script_files"
        if ext in INSTALLER_EXT or (ext == ".exe" and "setup" in path.name.lower()):
            return "installer_packages"
        if ext in EXECUTABLE_EXT:
            return "executable_binaries"
        if ext in FONT_EXT:
            return "font_files"
        if "\\program files\\" in path_str or "\\program files (x86)\\" in path_str:
            return "software_runtime_files"
        if "cache" in path_str or "code cache" in path_str or "gpucache" in path_str:
            return "app_runtime_cache"

        fallback_map = {
            "system_files": "system_core_files",
            "windows_update_cache": "windows_update_cache",
            "game_data": "game_data",
            "temporary_files": "temporary_files",
            "software_cache": "app_runtime_cache",
            "browser_cache": "browser_cache_files",
            "log_and_dump_files": "application_log_files",
            "image_files": "image_raster_files",
            "video_files": "video_standard_files",
            "audio_files": "audio_lossy_files",
            "document_files": "document_text_files",
            "archive_files": "archive_files",
            "source_code_files": "source_code_files",
            "database_files": "database_files",
            "installer_packages": "installer_packages",
            "software_files": "software_runtime_files",
            "system_cache": "windows_update_cache",
            "large_files": "large_files",
            "other_files": "other_files",
            "temp": "temporary_files",
            "cache": "app_runtime_cache",
            "logs": "application_log_files",
            "browser_cache": "browser_cache_files",
            "large_files": "large_files",
        }
        return fallback_map.get(fallback, fallback or "other_files")

    def _is_stopped(self) -> bool:
        return bool(self.stop_flag.get("stop"))

    def _emit_progress(self, stage: str, current: str, duration: float = 0.0, force: bool = False) -> None:
        if not self.progress_callback:
            return

        now = time.time()
        if not force and (now - self._last_progress_emit) < self.progress_interval_sec:
            return

        payload = {
            "stage": stage,
            "current": current,
            "files_seen": self._files_seen,
            "items_found": self._items_found,
            "duration": duration,
            "timestamp": now,
        }
        self._last_progress_emit = now
        try:
            self.progress_callback(payload)
        except Exception:
            pass


def hash_payload(payload: Dict) -> str:
    payload_bytes = json.dumps(payload, sort_keys=True).encode("utf-8")
    return hashlib.sha256(payload_bytes).hexdigest()
