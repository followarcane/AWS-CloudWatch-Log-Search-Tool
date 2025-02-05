import json
import sys
from typing import Dict, List, Tuple, Optional

class ConfigManager:
    def __init__(self):
        self.env_configs = {}
        self.shortcuts = {}
        self.search_highlight_enabled = True
        self.filter_highlight_enabled = True
        self.sort_by_time_enabled = True
        self.load_config()

    def load_config(self):
        try:
            with open('config.json', 'r') as f:
                config = json.load(f)
                self.env_configs = config.get('env_configs', {})
                
                # Highlight ve sıralama ayarları
                highlight_settings = config.get("highlight_settings", {})
                self.search_highlight_enabled = highlight_settings.get("search_highlight", True)
                self.filter_highlight_enabled = highlight_settings.get("filter_highlight", True)
                self.sort_by_time_enabled = highlight_settings.get("sort_by_time", True)
                
                # Kısayol ayarları
                self.shortcuts = config.get("shortcuts", {
                    "new_tab": {
                        "win": "<Control-t>",
                        "mac": "<Command-t>"
                    },
                    "close_tab": {
                        "win": "<Control-BackSpace>",
                        "mac": "<Command-BackSpace>"
                    },
                    "search_selected": {
                        "win": "<Control-d>",
                        "mac": "<Command-d>"
                    },
                    "stop_search": {
                        "win": "<Control-Shift-C>",
                        "mac": "<Command-Shift-C>"
                    }
                })
                
        except FileNotFoundError:
            self.env_configs = {
                "QA": {"paths": [], "profiles": {}},
                "SB": {"paths": [], "profiles": {}},
                "PROD": {"paths": [], "profiles": {}}
            }
            self.save_config()

    def save_config(self):
        config = {
            'env_configs': self.env_configs,
            'highlight_settings': {
                "search_highlight": self.search_highlight_enabled,
                "filter_highlight": self.filter_highlight_enabled,
                "sort_by_time": self.sort_by_time_enabled
            },
            'shortcuts': self.shortcuts
        }
        with open('config.json', 'w') as f:
            json.dump(config, f, indent=4)

    def get_current_paths_and_profiles(self, env: str) -> List[Tuple[str, str]]:
        try:
            print(f"\nSelected environment: {env}")
            config = self.env_configs.get(env, {"paths": [], "profiles": {}})
            paths = config.get("paths", [])
            
            result = []
            print("Found paths and profiles:")
            for path in paths:
                profile = "steller-developer" if "steller" in path else "bahama-developer"
                print(f"  - Path: {path}")
                print(f"    Profile: {profile}")
                result.append((path, profile))
            
            return result
            
        except Exception as e:
            print(f"Error getting paths and profiles: {e}")
            return []

    def get_platform_key(self) -> str:
        return "mac" if sys.platform == "darwin" else "win"

    def get_shortcut(self, action: str) -> str:
        platform_key = self.get_platform_key()
        return self.shortcuts.get(action, {}).get(platform_key, "")

    def update_shortcut(self, action: str, shortcut: str):
        platform_key = self.get_platform_key()
        if action in self.shortcuts:
            self.shortcuts[action][platform_key] = shortcut 