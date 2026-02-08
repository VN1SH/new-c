from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List


@dataclass(frozen=True)
class Rule:
    name: str
    base_paths: List[Path]
    include_patterns: List[str]
    risk: str  # low/medium/suggest/forbidden
    category: str
    description: str


SYSTEM_FORBIDDEN_DIRS = [
    Path(r"C:\\Windows\\System32"),
    Path(r"C:\\Windows\\WinSxS"),
    Path(r"C:\\Program Files"),
    Path(r"C:\\Program Files (x86)"),
    Path(r"C:\\System Volume Information"),
]


def _user_profile_paths() -> List[Path]:
    home = Path.home()
    return [
        home,
        home / "AppData" / "Local",
        home / "AppData" / "Roaming",
    ]


def build_rules() -> List[Rule]:
    user_paths = _user_profile_paths()
    temp_paths = [Path.home() / "AppData" / "Local" / "Temp", Path(r"C:\\Windows\\Temp")]

    return [
        Rule(
            name="UserTemp",
            base_paths=temp_paths,
            include_patterns=["*"],
            risk="low",
            category="temp",
            description="常见临时文件目录",
        ),
        Rule(
            name="AppCaches",
            base_paths=[p / "AppData" / "Local" for p in [Path.home()]],
            include_patterns=[
                "*Cache*",
                "*Code Cache*",
                "*GPUCache*",
                "*Crashpad*",
                "*Logs*",
            ],
            risk="low",
            category="cache",
            description="用户缓存目录",
        ),
        Rule(
            name="LogsAndDumps",
            base_paths=user_paths,
            include_patterns=["*.log", "*.dmp"],
            risk="low",
            category="logs",
            description="日志与转储文件",
        ),
        Rule(
            name="BrowserCaches",
            base_paths=[
                Path.home() / "AppData" / "Local" / "Google" / "Chrome" / "User Data",
                Path.home() / "AppData" / "Local" / "Microsoft" / "Edge" / "User Data",
                Path.home() / "AppData" / "Roaming" / "Mozilla" / "Firefox" / "Profiles",
            ],
            include_patterns=["*Cache*", "*Code Cache*", "*GPUCache*"],
            risk="medium",
            category="browser_cache",
            description="浏览器缓存",
        ),
        Rule(
            name="WindowsUpdateCache",
            base_paths=[Path(r"C:\\Windows\\SoftwareDistribution\\Download")],
            include_patterns=["*"],
            risk="medium",
            category="system_cache",
            description="Windows 更新下载缓存",
        ),
    ]


def is_forbidden(path: Path) -> bool:
    normalized = Path(str(path))
    return any(str(normalized).lower().startswith(str(root).lower()) for root in SYSTEM_FORBIDDEN_DIRS)


def is_user_writable(path: Path) -> bool:
    try:
        return path.exists() and path.is_dir()
    except PermissionError:
        return False


def match_rule(path: Path, rules: Iterable[Rule]) -> Rule | None:
    for rule in rules:
        for base in rule.base_paths:
            try:
                if not str(path).lower().startswith(str(base).lower()):
                    continue
            except Exception:
                continue
            if rule.include_patterns == ["*"]:
                return rule
            for pattern in rule.include_patterns:
                if path.match(pattern) or pattern.lower() in str(path).lower():
                    return rule
    return None


def suggestion_targets(threshold_bytes: int) -> List[Path]:
    home = Path.home()
    return [
        home / "Downloads",
        home / "Desktop",
        home / "Documents",
    ]


def duplicate_scan_dirs() -> List[Path]:
    return [Path.home() / "Downloads"]
