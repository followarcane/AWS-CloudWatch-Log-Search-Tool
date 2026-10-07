from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from typing import Any

from app.core.logging_setup import setup_logging

logger = setup_logging("logsearcher.config")

# Use Ctrl+ on both platforms — Qt maps Ctrl→⌘ on macOS for shortcuts.
DEFAULT_SHORTCUTS = {
    "new_tab": {"win": "Ctrl+T", "mac": "Ctrl+T"},
    "close_tab": {"win": "Ctrl+W", "mac": "Ctrl+W"},
    "search_selected": {"win": "Ctrl+D", "mac": "Ctrl+D"},
    "stop_search": {"win": "Ctrl+Shift+S", "mac": "Ctrl+Shift+S"},
    "copy_full_log": {"win": "Ctrl+Shift+C", "mac": "Ctrl+Shift+C"},
    "copy_awslogs_command": {"win": "Ctrl+Shift+A", "mac": "Ctrl+Shift+A"},
    "find_in_results": {"win": "Ctrl+F", "mac": "Ctrl+F"},
}


def _deep_merge(base: dict, override: dict) -> dict:
    result = copy.deepcopy(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


class ConfigManager:
    """Loads company config + optional local overrides. Resolves AWS profiles from config."""

    def __init__(self, base_dir: Path | None = None) -> None:
        self.base_dir = Path(base_dir) if base_dir else self._detect_base_dir()
        self.company_path = self._resolve_company_path()
        self.local_path = self._resolve_local_path()
        self.legacy_path = self.base_dir / "config.json"

        self.env_configs: dict[str, Any] = {}
        self.shortcuts: dict[str, dict[str, str]] = copy.deepcopy(DEFAULT_SHORTCUTS)
        self.search_highlight_enabled = True
        self.filter_highlight_enabled = True
        self.sort_by_time_enabled = True
        self.keep_awake_enabled = False
        self.max_collapsed_lines = 15
        self.beautify_logs_enabled = True
        self.load()

    @staticmethod
    def _detect_base_dir() -> Path:
        if getattr(sys, "frozen", False):
            # Writable location next to the .app / executable
            return Path(sys.executable).resolve().parent
        here = Path(__file__).resolve()
        candidate = here.parents[2]  # .../app/config/manager.py -> repo root
        if (candidate / "config.company.json").exists() or (candidate / "config.json").exists():
            return candidate
        return Path.cwd()

    def _resolve_company_path(self) -> Path:
        candidates = [
            self.base_dir / "config.company.json",
            Path.cwd() / "config.company.json",
        ]
        if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
            candidates.insert(0, Path(sys._MEIPASS) / "config.company.json")
        for path in candidates:
            if path.exists():
                return path
        return self.base_dir / "config.company.json"

    def _resolve_local_path(self) -> Path:
        if getattr(sys, "frozen", False):
            home_cfg = Path.home() / ".config" / "awslogsearcher" / "config.local.json"
            home_cfg.parent.mkdir(parents=True, exist_ok=True)
            return home_cfg
        return self.base_dir / "config.local.json"

    def load(self) -> None:
        company: dict[str, Any] = {}
        if self.company_path.exists():
            company = self._read_json(self.company_path)
        elif self.legacy_path.exists():
            logger.warning("config.company.json missing; falling back to config.json")
            company = self._read_json(self.legacy_path)

        local: dict[str, Any] = {}
        if self.local_path.exists():
            local = self._read_json(self.local_path)

        merged = _deep_merge(company, local)
        self._apply(merged)

    def _apply(self, config: dict[str, Any]) -> None:
        raw_envs = config.get("env_configs", {})
        # Strip accidental non-env keys nested under env_configs
        self.env_configs = {
            k: v
            for k, v in raw_envs.items()
            if isinstance(v, dict) and ("paths" in v or "profiles" in v)
        }
        if not self.env_configs:
            self.env_configs = {
                "QA": {"paths": [], "profiles": {}},
                "SB": {"paths": [], "profiles": {}},
                "PROD": {"paths": [], "profiles": {}},
            }

        highlight = config.get("highlight_settings", {})
        self.search_highlight_enabled = highlight.get("search_highlight", True)
        self.filter_highlight_enabled = highlight.get("filter_highlight", True)
        self.sort_by_time_enabled = highlight.get("sort_by_time", True)

        app_settings = config.get("app_settings", {})
        self.keep_awake_enabled = bool(app_settings.get("keep_awake", False))
        self.beautify_logs_enabled = bool(app_settings.get("beautify_logs", True))
        try:
            self.max_collapsed_lines = max(3, int(app_settings.get("max_collapsed_lines", 15)))
        except (TypeError, ValueError):
            self.max_collapsed_lines = 15

        shortcuts = config.get("shortcuts", {})
        self.shortcuts = copy.deepcopy(DEFAULT_SHORTCUTS)
        for action, mapping in shortcuts.items():
            if isinstance(mapping, dict):
                self.shortcuts.setdefault(action, {})
                self.shortcuts[action].update(mapping)

    def save_local(self) -> None:
        """Persist user-editable preferences to config.local.json (does not rewrite company file)."""
        payload = {
            "highlight_settings": {
                "search_highlight": self.search_highlight_enabled,
                "filter_highlight": self.filter_highlight_enabled,
                "sort_by_time": self.sort_by_time_enabled,
            },
            "app_settings": {
                "keep_awake": self.keep_awake_enabled,
                "max_collapsed_lines": self.max_collapsed_lines,
                "beautify_logs": self.beautify_logs_enabled,
            },
            "shortcuts": self.shortcuts,
            "env_configs": self.env_configs,
        }
        with open(self.local_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=4)
            f.write("\n")
        logger.info("Saved local config to %s", self.local_path)

    def environments(self) -> list[str]:
        return list(self.env_configs.keys())

    def paths_for_env(self, env: str) -> list[str]:
        return list(self.env_configs.get(env, {}).get("paths", []))

    def profiles_for_env(self, env: str) -> dict[str, str]:
        return dict(self.env_configs.get(env, {}).get("profiles", {}))

    def resolve_profile(self, env: str, path: str) -> str:
        """Resolve AWS profile from env profiles map by matching key as substring of path."""
        profiles = self.profiles_for_env(env)
        if not profiles:
            raise ValueError(f"No profiles configured for environment '{env}'.")

        # Prefer longest matching key so more specific prefixes win
        matches = [(key, profile) for key, profile in profiles.items() if key in path]
        if matches:
            matches.sort(key=lambda item: len(item[0]), reverse=True)
            return matches[0][1]

        # Fallback: single profile for the env
        if len(profiles) == 1:
            return next(iter(profiles.values()))

        raise ValueError(
            f"Could not resolve AWS profile for path '{path}' in env '{env}'. "
            f"Known profile keys: {', '.join(profiles.keys())}"
        )

    def get_paths_and_profiles(
        self, env: str, selected_paths: list[str] | None = None
    ) -> list[tuple[str, str]]:
        paths = self.paths_for_env(env)
        if selected_paths:
            selected = set(selected_paths)
            paths = [p for p in paths if p in selected]

        result: list[tuple[str, str]] = []
        for path in paths:
            profile = self.resolve_profile(env, path)
            result.append((path, profile))
            logger.debug("Path %s -> profile %s", path, profile)
        return result

    def set_env_paths(self, env: str, paths: list[str]) -> None:
        self.env_configs.setdefault(env, {"paths": [], "profiles": {}})
        self.env_configs[env]["paths"] = list(paths)

    def set_env_profiles(self, env: str, profiles: dict[str, str]) -> None:
        self.env_configs.setdefault(env, {"paths": [], "profiles": {}})
        self.env_configs[env]["profiles"] = dict(profiles)

    def platform_key(self) -> str:
        return "mac" if sys.platform == "darwin" else "win"

    def get_shortcut(self, action: str) -> str:
        return self.shortcuts.get(action, {}).get(self.platform_key(), "")

    def update_shortcut(self, action: str, shortcut: str) -> None:
        self.shortcuts.setdefault(action, {})
        self.shortcuts[action][self.platform_key()] = shortcut

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any]:
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except Exception as exc:
            logger.error("Failed to read %s: %s", path, exc)
            return {}
