import tkinter as tk
from tkinter import ttk, messagebox
import sys

class SettingsManager:
    """
    Class responsible for managing application settings and settings window.
    
    This class handles user settings management:
    - Creating settings window
    - Environment (QA/SB/PROD) configurations
    - AWS profile and path settings
    - Appearance and behavior settings
    - Shortcut key configurations
    - Persistent storage of settings
    """
    def __init__(self, main_app):
        self.main_app = main_app
        self.config_manager = main_app.config_manager

    def show_settings(self):
        """Ayarlar penceresini göster"""
        try:
            settings_window = tk.Toplevel(self.main_app.root)
            settings_window.title("Settings")
            settings_window.minsize(600, 600)
            settings_window.transient(self.main_app.root)
            settings_window.grab_set()
            
            container = ttk.Frame(settings_window)
            container.pack(fill="both", expand=True, padx=10, pady=10)
            
            notebook = ttk.Notebook(container)
            notebook.pack(fill="both", expand=True)
            
            # Create tabs
            self._create_paths_tab(notebook)
            self._create_highlight_tab(notebook)
            self._create_shortcuts_tab(notebook)
            
            # Button frame
            button_frame = ttk.Frame(settings_window)
            button_frame.pack(fill="x", side="bottom", padx=10, pady=10)
            
            save_button = ttk.Button(button_frame, text="Save", 
                                   command=lambda: self._save_settings(settings_window))
            save_button.pack(side="right", padx=10, pady=5)
            
            # Size window to content
            settings_window.update_idletasks()
            width = max(600, notebook.winfo_reqwidth() + 40)
            height = max(600, notebook.winfo_reqheight() + button_frame.winfo_reqheight() + 60)
            settings_window.geometry(f"{width}x{height}")
            
        except Exception as e:
            print(f"Error showing settings: {e}")
            import traceback
            traceback.print_exc()

    def _create_paths_tab(self, notebook):
        """Create paths configuration tab"""
        paths_frame = ttk.Frame(notebook)
        notebook.add(paths_frame, text="Paths")
        
        # Environment selection frame
        env_select_frame = ttk.Frame(paths_frame)
        env_select_frame.pack(fill="x", padx=10, pady=5)
        
        ttk.Label(env_select_frame, text="Environment:").pack(side="left", padx=5)
        self.selected_env = tk.StringVar(value="QA")
        
        for env in ["QA", "SB", "PROD"]:
            ttk.Radiobutton(env_select_frame, text=env, 
                          variable=self.selected_env, 
                          value=env,
                          command=self._on_env_change).pack(side="left", padx=10)
        
        # Separator
        ttk.Separator(paths_frame, orient="horizontal").pack(fill="x", padx=5, pady=10)
        
        # Paths configuration frame
        self.paths_config_frame = ttk.LabelFrame(paths_frame, text="Path Configuration")
        self.paths_config_frame.pack(fill="both", expand=True, padx=10, pady=5)
        
        # Store widgets for each environment
        self.tabs = {}
        for env in ["QA", "SB", "PROD"]:
            frame = ttk.Frame(self.paths_config_frame)
            
            # Steller section
            steller_frame = ttk.LabelFrame(frame, text="Steller Configuration")
            steller_frame.pack(fill="x", padx=5, pady=5)
            
            profile_frame = ttk.Frame(steller_frame)
            profile_frame.pack(fill="x", padx=5, pady=5)
            
            ttk.Label(profile_frame, text="Profile:").pack(side="left", padx=5)
            steller_profile = ttk.Entry(profile_frame)
            steller_profile.pack(side="left", fill="x", expand=True, padx=5)
            
            paths_frame = ttk.Frame(steller_frame)
            paths_frame.pack(fill="x", padx=5, pady=5)
            
            ttk.Label(paths_frame, text="Paths:").pack(anchor="w", padx=5)
            steller_paths = tk.Text(paths_frame, height=4)
            steller_paths.pack(fill="x", padx=5, pady=5)
            
            # Separator
            ttk.Separator(frame, orient="horizontal").pack(fill="x", padx=5, pady=10)
            
            # Bahama section
            bahama_frame = ttk.LabelFrame(frame, text="Bahama Configuration")
            bahama_frame.pack(fill="x", padx=5, pady=5)
            
            profile_frame = ttk.Frame(bahama_frame)
            profile_frame.pack(fill="x", padx=5, pady=5)
            
            ttk.Label(profile_frame, text="Profile:").pack(side="left", padx=5)
            bahama_profile = ttk.Entry(profile_frame)
            bahama_profile.pack(side="left", fill="x", expand=True, padx=5)
            
            paths_frame = ttk.Frame(bahama_frame)
            paths_frame.pack(fill="x", padx=5, pady=5)
            
            ttk.Label(paths_frame, text="Paths:").pack(anchor="w", padx=5)
            bahama_paths = tk.Text(paths_frame, height=4)
            bahama_paths.pack(fill="x", padx=5, pady=5)
            
            # Store widgets
            self.tabs[env] = {
                "frame": frame,
                "steller_profile": steller_profile,
                "bahama_profile": bahama_profile,
                "steller_paths": steller_paths,
                "bahama_paths": bahama_paths
            }
            
            # Load current values
            self._load_env_config(env)
        
        # Show initial environment
        self._on_env_change()

    def _on_env_change(self):
        """Handle environment change"""
        selected = self.selected_env.get()
        
        # Hide all frames
        for env in self.tabs:
            self.tabs[env]["frame"].pack_forget()
        
        # Show selected frame
        self.tabs[selected]["frame"].pack(fill="both", expand=True)

    def _create_highlight_tab(self, notebook):
        """Create highlight settings tab"""
        highlight_frame = ttk.Frame(notebook)
        notebook.add(highlight_frame, text="Highlight")
        
        # Search highlight checkbox
        self.search_highlight_var = tk.BooleanVar(value=self.config_manager.search_highlight_enabled)
        ttk.Checkbutton(highlight_frame, text="Enable Search Highlight", 
                       variable=self.search_highlight_var).pack(padx=5, pady=5)
        
        # Filter highlight checkbox
        self.filter_highlight_var = tk.BooleanVar(value=self.config_manager.filter_highlight_enabled)
        ttk.Checkbutton(highlight_frame, text="Enable Filter Highlight", 
                       variable=self.filter_highlight_var).pack(padx=5, pady=5)
        
        # Sort by time checkbox
        self.sort_by_time_var = tk.BooleanVar(value=self.config_manager.sort_by_time_enabled)
        ttk.Checkbutton(highlight_frame, text="Sort Logs by Time", 
                       variable=self.sort_by_time_var).pack(padx=5, pady=5)

    def _create_shortcuts_tab(self, notebook):
        """Create shortcuts configuration tab"""
        shortcut_frame = ttk.Frame(notebook)
        notebook.add(shortcut_frame, text="Shortcuts")
        
        # Platform selection
        platform_frame = ttk.Frame(shortcut_frame)
        platform_frame.pack(fill="x", padx=5, pady=5)
        
        ttk.Label(platform_frame, text="Platform:").pack(side="left", padx=5)
        self.platform_var = tk.StringVar(value="mac" if sys.platform == "darwin" else "win")
        ttk.Radiobutton(platform_frame, text="Windows/Linux", variable=self.platform_var, 
                       value="win").pack(side="left", padx=5)
        ttk.Radiobutton(platform_frame, text="macOS", variable=self.platform_var, 
                       value="mac").pack(side="left", padx=5)
        
        # Shortcut editing areas
        shortcuts_frame = ttk.Frame(shortcut_frame)
        shortcuts_frame.pack(fill="x", padx=5, pady=5)
        
        self.shortcut_entries = {}
        row = 0
        # Label mapping for user-friendly shortcut names
        shortcut_labels = {
            "new_tab": "New Tab",
            "close_tab": "Close Tab",
            "search_selected": "Search Selected Text in New Tab",
            "stop_search": "Stop Search",
            "copy_full_log": "Copy full log block"
        }
        for action, shortcuts in self.config_manager.shortcuts.items():
            label = shortcut_labels.get(action, action)
            ttk.Label(shortcuts_frame, text=f"{label}:").grid(row=row, column=0, padx=5, pady=2)
            entry = ttk.Entry(shortcuts_frame)
            entry.insert(0, shortcuts[self.platform_var.get()])
            entry.grid(row=row, column=1, padx=5, pady=2, sticky="ew")
            self.shortcut_entries[action] = entry
            row += 1
        
        self.platform_var.trace_add("write", self._update_shortcut_entries)

    def _load_env_config(self, env):
        """Load environment configuration"""
        config = self.config_manager.env_configs.get(env, {})
        profiles = config.get("profiles", {})
        paths = config.get("paths", [])
        
        self.tabs[env]["steller_profile"].insert(0, profiles.get("steller", ""))
        self.tabs[env]["bahama_profile"].insert(0, profiles.get("bahama", ""))
        
        steller_paths_list = [p for p in paths if "steller" in p]
        bahama_paths_list = [p for p in paths if "bahama" in p]
        
        self.tabs[env]["steller_paths"].insert("1.0", "\n".join(steller_paths_list))
        self.tabs[env]["bahama_paths"].insert("1.0", "\n".join(bahama_paths_list))

    def _update_shortcut_entries(self, *args):
        """Update shortcuts when platform changes"""
        platform = self.platform_var.get()
        for action, entry in self.shortcut_entries.items():
            entry.delete(0, tk.END)
            entry.insert(0, self.config_manager.shortcuts[action][platform])

    def _save_settings(self, settings_window):
        """Save all settings"""
        try:
            # Save environment settings
            for env in ["QA", "SB", "PROD"]:
                self.config_manager.env_configs[env]["profiles"] = {
                    "steller": self.tabs[env]["steller_profile"].get().strip(),
                    "bahama": self.tabs[env]["bahama_profile"].get().strip()
                }
                
                steller_paths = [p.strip() for p in self.tabs[env]["steller_paths"].get("1.0", "end-1c").split("\n") if p.strip()]
                bahama_paths = [p.strip() for p in self.tabs[env]["bahama_paths"].get("1.0", "end-1c").split("\n") if p.strip()]
                
                self.config_manager.env_configs[env]["paths"] = steller_paths + bahama_paths
            
            # Save highlight settings
            self.config_manager.search_highlight_enabled = self.search_highlight_var.get()
            self.config_manager.filter_highlight_enabled = self.filter_highlight_var.get()
            self.config_manager.sort_by_time_enabled = self.sort_by_time_var.get()
            
            # Save shortcut settings
            platform = self.platform_var.get()
            for action, entry in self.shortcut_entries.items():
                self.config_manager.update_shortcut(action, entry.get())
            
            # Save to file
            self.config_manager.save_config()
            
            # Rebind shortcuts
            self.main_app.bind_shortcuts()
            
            settings_window.destroy()
            messagebox.showinfo("Success", "Settings saved!")
            
        except Exception as e:
            messagebox.showerror("Error", f"Error saving settings: {str(e)}") 