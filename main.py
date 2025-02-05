import tkinter as tk
from tkinter import ttk, messagebox
import subprocess
import threading
import queue
import datetime
from datetime import timedelta
import json
import csv
from tkinter import filedialog
import re
import os
import sys
from log_searcher import LogSearcher
from gui_manager import LogSearcherUI
from search_tab import SearchTab
from log_processor import LogProcessor

class LogSearcherGUI(LogSearcherUI):
    def __init__(self, root):
        super().__init__(root)  # LogSearcherUI'nin init'ini çağır
        self.last_tab_number = 0
        self.log_processor = LogProcessor()
        
        # Read paths from config
        self.load_config()
        
        # Main container
        main_container = ttk.Frame(root)
        main_container.pack(fill="both", expand=True, padx=10, pady=5)
        
        # Notebook (tab container)
        self.notebook = ttk.Notebook(main_container, style="Custom.TNotebook")
        self.notebook.pack(fill="both", expand=True, padx=0, pady=0)
        
        # Track tab changes
        self.notebook.bind('<<NotebookTabChanged>>', self.on_tab_changed)
        
        # Add first tab
        self.add_tab()
        
        # To prevent GUI locking
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        # Debounce timer for filtering
        self.filter_timer = None
        
        # Add keyboard shortcuts
        self.bind_shortcuts()

    def load_config(self):
        try:
            with open('config.json', 'r') as f:
                config = json.load(f)
                self.env_configs = config.get('env_configs', {})
                
                # Highlight and sorting settings
                highlight_settings = config.get("highlight_settings", {})
                self.search_highlight_enabled = highlight_settings.get("search_highlight", True)
                self.filter_highlight_enabled = highlight_settings.get("filter_highlight", True)
                self.sort_by_time_enabled = highlight_settings.get("sort_by_time", True)
                
                # Load shortcut settings
                shortcut_settings = config.get("shortcuts", {
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
                    "stop_search": {  # Newly added shortcut
                        "win": "<Control-Shift-C>",
                        "mac": "<Command-Shift-C>"
                    }
                })
                self.shortcuts = shortcut_settings
                
        except FileNotFoundError:
            # Default config
            self.env_configs = {
                "QA": {"paths": [], "profiles": {}},
                "SB": {"paths": [], "profiles": {}},
                "PROD": {"paths": [], "profiles": {}}
            }
            # Default shortcuts
            self.shortcuts = {
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
                "stop_search": {  # Newly added shortcut
                    "win": "<Control-Shift-C>",
                    "mac": "<Command-Shift-C>"
                }
            }
            self.save_config()
    
    def save_config(self):
        config = {
            'env_configs': self.env_configs
        }
        with open('config.json', 'w') as f:
            json.dump(config, f, indent=4)
    
    def get_time_range(self):
        """Parse entered time and convert to appropriate format"""
        time_input = self.time_var.get().strip()
        
        try:
            # If only number entered, treat as hours
            if time_input.isdigit():
                return f"{time_input}h ago"
            
            # Check date format (YYYY-MM-DD HH:mm:ss)
            datetime.datetime.strptime(time_input, "%Y-%m-%d %H:%M:%S")
            return time_input  # Return if date format is correct
            
        except ValueError as e:
            print(f"Time format error: {e}")  # Print to console
            return "1h ago"  # Default value if format is incorrect
    
    def get_filter_pattern(self):
        search_value = self.search_var.get()
        
        if not search_value:
            return None
            
        return f'"{search_value}"'

    def toggle_buttons(self, searching=True):
        state = "disabled" if searching else "normal"
        self.search_button.configure(state=state)
        self.clear_button.configure(state=state)
        self.export_button.configure(state=state)
        self.settings_button.configure(state=state)
        self.stop_button.configure(state="normal" if searching else "disabled")

    def on_closing(self):
        """Clean up threads when app is closed"""
        current_tab = self.get_current_tab()
        if current_tab:
            current_tab.stop_search()  # Call tab's own stop method
        self.root.destroy()

    def stop_search(self):
        current_tab = self.get_current_tab()
        if not current_tab:
            return
            
        # Stop search
        current_tab.is_searching = False
        current_tab.status_var.set("Stopping search...")
        
        # Wait for threads
        for thread in current_tab.active_threads:
            if thread.is_alive():
                thread.join(timeout=0.1)
        current_tab.active_threads.clear()
        
        # Clear queue
        while not current_tab.log_queue.empty():
            try:
                current_tab.log_queue.get_nowait()
            except queue.Empty:
                break
        
        if self.sort_by_time_enabled and current_tab.text_widget.get("1.0", tk.END).strip():
            self.log_processor.sort_logs_by_time(current_tab)
        
        current_tab.status_var.set("Search stopped!")
        current_tab.progress_bar.stop()
        current_tab.toggle_buttons(searching=False)  # Update tab's own button states

    def get_current_paths_and_profiles(self):
        """Return paths and profiles for selected environment"""
        current_tab = self.get_current_tab()
        if not current_tab:
            return []
        
        env = current_tab.env_var.get()  # Use tab's own env_var
        config = self.env_configs.get(env, {"paths": [], "profiles": {}})
        
        paths_with_profiles = []
        for path in config["paths"]:
            # Determine which profile the path belongs to
            profile = config["profiles"]["steller"] if "steller" in path else config["profiles"]["bahama"]
            paths_with_profiles.append((path, profile))
        
        print(f"\nSelected environment: {env}")
        print(f"Found paths and profiles:")
        for path, profile in paths_with_profiles:
            print(f"  - Path: {path}")
            print(f"    Profile: {profile}")
        
        return paths_with_profiles

    def search_logs(self, path, profile, filter_pattern, tab):
        try:
            cmd = [
                "awslogs",
                "get",
                path,
                "--profile",
                profile,
                "--start",
                f"{tab.time_var.get().strip()}h ago",
                "--query=log"
            ]
            
            if filter_pattern:
                cmd.extend(["--filter-pattern", filter_pattern])
            
            command_str = " ".join(cmd)
            print(f"\nExecuting command: {command_str}")
            
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                encoding='utf-8',
                universal_newlines=True,
                close_fds=True
            )
            
            log_count = 0
            current_log = None
            current_timestamp = None
            current_level = None
            
            for line in iter(process.stdout.readline, ''):
                if not tab.is_searching:
                    print(f"[{path}] Search stopped by user")
                    break
                    
                if line.strip():
                    print(f"\n[{path}] Found log line: {line.strip()}")
                    
                    is_main_log = path in line
                    if is_main_log:
                        log_count += 1
                        if current_log:
                            print(f"[{path}] Sending log #{log_count} to queue")
                            tab.log_queue.put({
                                "timestamp": current_timestamp,
                                "level": current_level,
                                "message": current_log
                            })
                        
                        # Start new log
                        current_log = line.strip()
                        try:
                            # Parse time
                            parts = line.strip().split()
                            for i in range(len(parts)-1):
                                try:
                                    time_str = f"{parts[i]} {parts[i+1]}"
                                    if parts[i].count('-') == 2 and parts[i+1].count(':') == 2:
                                        current_timestamp = time_str
                                        break
                                except ValueError:
                                    continue
                        except Exception as e:
                            print(f"[{path}] Time parse error: {e}")
                            current_timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                        
                        # Determine log level
                        current_level = "INFO"
                        if "ERROR" in line.upper():
                            current_level = "ERROR"
                        elif "WARN" in line.upper():
                            current_level = "WARN"
                    else:
                        # If existing log, add trace log
                        if current_log:
                            current_log += "\n" + line.strip()
            
            # Send last log
            if current_log:
                print(f"[{path}] Sending last log to queue: {current_log[:200]}...")
                tab.log_queue.put({
                    "timestamp": current_timestamp,
                    "level": current_level,
                    "message": current_log
                })
                
            print(f"\n[{path}] Search completed")
            print(f"[{path}] Total logs found: {log_count}")
            
        except Exception as e:
            print(f"\n[{path}] Error during search: {str(e)}")
            import traceback
            traceback.print_exc()
        finally:
            try:
                process.stdout.close()
                process.terminate()
                process.wait(timeout=1)
            except:
                pass

    def debounce_filter(self, tab):
        """Apply debounce for filtering"""
        if hasattr(tab, 'filter_timer') and tab.filter_timer:
            self.root.after_cancel(tab.filter_timer)
        tab.filter_timer = self.root.after(300, lambda: self.log_processor.filter_logs(tab))

    def is_valid_filter_text(self, text):
        """Check if filter text is valid"""
        if not text:
            return False
            
        # Minimum length check
        if len(text) < 2:
            return False
            
        # Invalid if only special characters
        special_chars = '"\'?!,.:;-_=+<>[]{}()|\\/@#$%^&*'
        special_char_count = sum(1 for c in text if c in special_chars)
        if special_char_count == len(text):
            return False
            
        # Consecutive special character check
        consecutive_special = 0
        for c in text:
            if c in special_chars:
                consecutive_special += 1
                if consecutive_special > 2:  # Max 2 consecutive special characters
                    return False
            else:
                consecutive_special = 0
        
        return True

    def update_gui(self, tab):
        try:
            # Check if tab is valid
            if not tab in self.notebook.winfo_children():
                return
            
            if not tab.is_searching and not tab.search_completed:
                return
            
            has_new_logs = False
            batch_size = 0
            
            try:
                while batch_size < 5 and not tab.log_queue.empty():
                    try:
                        log_entry = tab.log_queue.get_nowait()
                        print(f"[Tab {self.notebook.index(tab)}] Processing log: {log_entry['timestamp']} [{log_entry['level']}] Queue size: {tab.log_queue.qsize()}")
                        
                        tab.text_widget.configure(state='normal')
                        
                        # Add log entry
                        if tab.text_widget.get("1.0", "end").strip():
                            tab.text_widget.insert("end", "─" * 100 + "\n", "separator")
                            tab.text_widget.tag_configure("separator", foreground="#6272a4")
                        
                        tab.text_widget.insert("end", f"{log_entry['timestamp']} ", "timestamp")
                        
                        level = log_entry['level']
                        level_color = "#50fa7b"  # Default INFO color
                        if level == "ERROR":
                            level_color = "#ff5555"
                        elif level == "WARN":
                            level_color = "#ffb86c"
                            
                        tab.text_widget.insert("end", f"[{level}] ", f"level_{level_color}")
                        tab.text_widget.insert("end", f"{log_entry['message']}\n\n", "message")
                        
                        # Reapply coloring
                        tab.text_widget.tag_configure("timestamp", foreground="#8be9fd")
                        tab.text_widget.tag_configure(f"level_{level_color}", foreground=level_color)
                        tab.text_widget.tag_configure("message", foreground="white")
                        
                        # Scroll
                        tab.text_widget.see("end")
                        
                        tab.text_widget.configure(state='disabled')
                        
                        # Update original log content
                        tab.full_log_content = tab.text_widget.get(1.0, tk.END)
                        
                        has_new_logs = True
                        batch_size += 1
                        
                    except queue.Empty:
                        break
                    except Exception as e:
                        print(f"[{tab}] Error processing log: {e}")
                        import traceback
                        traceback.print_exc()
                        continue
                    
            except Exception as e:
                print(f"[{tab}] Batch processing error: {e}")
                import traceback
                traceback.print_exc()
            
            # Check active threads
            active_threads = [t for t in tab.active_threads if t.is_alive()]
            
            if not active_threads and tab.log_queue.empty():
                print(f"[Tab {self.notebook.index(tab)}] Search completed")
                tab.is_searching = False
                tab.search_completed = True
                tab.status_var.set("Search completed!")
                tab.progress_bar.stop()
                tab.toggle_buttons(searching=False)
                
                if self.sort_by_time_enabled:
                    self.log_processor.sort_logs_by_time(tab)
            else:
                # Check if tab is valid
                if tab in self.notebook.winfo_children():
                    self.root.after(50, self.update_gui, tab)
                
        except Exception as e:
            print(f"[{tab}] GUI update error: {e}")
            import traceback
            traceback.print_exc()
    
    def start_search(self):
        current_tab = self.get_current_tab()
        if not current_tab:
            return
            
        # Stop searches in all tabs
        for tab_id in self.notebook.tabs():
            tab = self.notebook.nametowidget(tab_id)
            tab.is_searching = False
            
            # Wait for tab's threads
            for thread in tab.active_threads:
                if thread.is_alive():
                    thread.join(timeout=0.1)
            tab.active_threads.clear()
            
            # Clear queue
            while not tab.log_queue.empty():
                try:
                    tab.log_queue.get_nowait()
                except queue.Empty:
                    break
        
            # Clear tab
            self.clear_tab(tab)
            
            filter_pattern = self.get_filter_pattern()
            if not filter_pattern:
                current_tab.status_var.set("Please enter a search value")
                return
            
            # Reset search states
            current_tab.is_searching = True
            current_tab.search_completed = False
            
            self.toggle_buttons(searching=True)
            current_tab.progress_bar.start()
            
            # Start separate threads for each path
            paths_and_profiles = self.get_current_paths_and_profiles()
            for path, profile in paths_and_profiles:
                thread = threading.Thread(
                    target=self.search_logs,
                    args=(path, profile, filter_pattern, current_tab),
                    daemon=True
                )
                thread.start()
                current_tab.active_threads.append(thread)
            
            # Start GUI updates
            self.update_gui(current_tab)

    def export_results(self):
        """Export active tab's content"""
        current_tab = self.get_current_tab()
        if not current_tab:
            return
            
        if not current_tab.text_widget.get(1.0, "end").strip():
            messagebox.showwarning("Warning", "No results to export!")
            return
            
        file_path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
        )
        
        if file_path:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(current_tab.text_widget.get(1.0, "end"))
            
            messagebox.showinfo("Success", "Results exported successfully!")

    def clear_results(self):
        """Clear active tab's content"""
        current_tab = self.get_current_tab()
        if not current_tab:
            return
            
        # Clear queue
        while not current_tab.log_queue.empty():
            try:
                current_tab.log_queue.get_nowait()
            except queue.Empty:
                break
        
        # Clear tab completely
        self.clear_tab(current_tab)

    def show_settings(self):
        settings_window = tk.Toplevel(self.root)
        settings_window.title("Settings")
        settings_window.geometry("1000x800")  # Larger window
        
        # Highlight settings frame
        highlight_frame = ttk.LabelFrame(settings_window, text="Display Settings")
        highlight_frame.pack(fill="x", padx=5, pady=5)
        
        # Search highlight checkbox
        self.search_highlight_var = tk.BooleanVar(value=self.search_highlight_enabled)
        ttk.Checkbutton(highlight_frame, text="Search Highlight", variable=self.search_highlight_var).pack(padx=5, pady=2)
        
        # Filter highlight checkbox
        self.filter_highlight_var = tk.BooleanVar(value=self.filter_highlight_enabled)
        ttk.Checkbutton(highlight_frame, text="Filter Highlight", variable=self.filter_highlight_var).pack(padx=5, pady=2)
        
        # Sort by time checkbox
        self.sort_by_time_var = tk.BooleanVar(value=self.sort_by_time_enabled)
        ttk.Checkbutton(highlight_frame, text="Sort logs by time at search completion", 
                       variable=self.sort_by_time_var).pack(padx=5, pady=2)
        
        # Create notebook (tab) widget
        notebook = ttk.Notebook(settings_window)
        notebook.pack(fill="both", expand=True, padx=5, pady=5)
        
        # Create separate tab for each environment
        tabs = {}
        for env in ["QA", "SB", "PROD"]:
            tab = ttk.Frame(notebook)
            notebook.add(tab, text=env)
            tabs[env] = tab
            
            # AWS Profiles frame
            profile_frame = ttk.LabelFrame(tab, text="AWS Profiles")
            profile_frame.pack(fill="x", padx=5, pady=5)
            
            # Steller Profile
            steller_frame = ttk.Frame(profile_frame)
            steller_frame.pack(fill="x", padx=5, pady=5)
            ttk.Label(steller_frame, text="Steller Profile:").pack(side="left")
            steller_profile = ttk.Entry(steller_frame)
            steller_profile.pack(side="left", padx=5, fill="x", expand=True)
            steller_profile.insert(0, self.env_configs[env]["profiles"]["steller"])
            
            # Bahama Profile
            bahama_frame = ttk.Frame(profile_frame)
            bahama_frame.pack(fill="x", padx=5, pady=5)
            ttk.Label(bahama_frame, text="Bahama Profile:").pack(side="left")
            bahama_profile = ttk.Entry(bahama_frame)
            bahama_profile.pack(side="left", padx=5, fill="x", expand=True)
            bahama_profile.insert(0, self.env_configs[env]["profiles"]["bahama"])
            
            # Path list frame
            path_frame = ttk.LabelFrame(tab, text="Log Paths")
            path_frame.pack(fill="both", expand=True, padx=5, pady=5)
            
            # Steller Paths
            steller_paths_frame = ttk.LabelFrame(path_frame, text="Steller Paths (steller-developer profile)")
            steller_paths_frame.pack(fill="both", expand=True, padx=5, pady=5)
            steller_paths = tk.Text(steller_paths_frame, height=5)
            steller_paths.pack(fill="both", expand=True, padx=5, pady=5)
            # Steller path'lerini yükle
            steller_paths.insert("1.0", "\n".join([p for p in self.env_configs[env]["paths"] if "steller" in p]))
            
            # Bahama Paths
            bahama_paths_frame = ttk.LabelFrame(path_frame, text="Bahama Paths (bahama-developer profile)")
            bahama_paths_frame.pack(fill="both", expand=True, padx=5, pady=5)
            bahama_paths = tk.Text(bahama_paths_frame, height=5)
            bahama_paths.pack(fill="both", expand=True, padx=5, pady=5)
            # Bahama path'lerini yükle
            bahama_paths.insert("1.0", "\n".join([p for p in self.env_configs[env]["paths"] if "bahama" in p]))
            
            # Store widgets for each tab
            tabs[env] = {
                "steller_profile": steller_profile,
                "bahama_profile": bahama_profile,
                "steller_paths": steller_paths,
                "bahama_paths": bahama_paths
            }
        
        # Shortcut settings frame
        shortcut_frame = ttk.LabelFrame(settings_window, text="Shortcut Settings")
        shortcut_frame.pack(fill="x", padx=5, pady=5)
        
        # Platform selection (macOS default)
        platform_frame = ttk.Frame(shortcut_frame)
        platform_frame.pack(fill="x", padx=5, pady=5)
        
        ttk.Label(platform_frame, text="Platform:").pack(side="left")
        # Check system type and set default value
        is_mac = sys.platform == "darwin"
        platform_var = tk.StringVar(value="mac" if is_mac else "win")
        
        ttk.Radiobutton(platform_frame, text="Windows/Linux", 
            variable=platform_var, value="win").pack(side="left", padx=5)
        ttk.Radiobutton(platform_frame, text="macOS", 
            variable=platform_var, value="mac").pack(side="left", padx=5)
        
        # Shortcut editing areas
        shortcuts_frame = ttk.Frame(shortcut_frame)
        shortcuts_frame.pack(fill="x", padx=5, pady=5)
        
        shortcut_entries = {}
        row = 0
        
        for action, shortcuts in self.shortcuts.items():
            ttk.Label(shortcuts_frame, text=f"{action}:").grid(row=row, column=0, padx=5, pady=2)
            entry = ttk.Entry(shortcuts_frame)
            entry.insert(0, shortcuts[platform_var.get()])
            entry.grid(row=row, column=1, padx=5, pady=2, sticky="ew")
            shortcut_entries[action] = entry
            row += 1
        
        def update_shortcut_entries(*args):
            """Update shortcuts when platform changes"""
            platform = platform_var.get()
            for action, entry in shortcut_entries.items():
                entry.delete(0, tk.END)
                entry.insert(0, self.shortcuts[action][platform])
        
        platform_var.trace_add("write", update_shortcut_entries)
        
        def save_settings():
            try:
                # Highlight and sorting settings
                self.env_configs["highlight_settings"] = {
                    "search_highlight": self.search_highlight_var.get(),
                    "filter_highlight": self.filter_highlight_var.get(),
                    "sort_by_time": self.sort_by_time_var.get()
                }
                
                # Save settings for each environment
                for env in ["QA", "SB", "PROD"]:
                    # Profile'ları kaydet
                    self.env_configs[env]["profiles"] = {
                        "steller": tabs[env]["steller_profile"].get().strip(),
                        "bahama": tabs[env]["bahama_profile"].get().strip()
                    }
                    
                    # Path'leri kaydet
                    steller_paths = [p.strip() for p in tabs[env]["steller_paths"].get("1.0", "end-1c").split("\n") if p.strip()]
                    bahama_paths = [p.strip() for p in tabs[env]["bahama_paths"].get("1.0", "end-1c").split("\n") if p.strip()]
                    
                    self.env_configs[env]["paths"] = steller_paths + bahama_paths
                
                # Shortcut settings
                platform = platform_var.get()
                for action, entry in shortcut_entries.items():
                    self.shortcuts[action][platform] = entry.get()
                
                # Rebind shortcuts
                self.bind_shortcuts()
                
                self.save_config()
                settings_window.destroy()
                messagebox.showinfo("Success", "Settings saved!")
                
            except Exception as e:
                messagebox.showerror("Error", f"Error saving settings: {str(e)}")
        
        ttk.Button(settings_window, text="Save", command=save_settings).pack(pady=10)

    def add_tab(self):
        """Add a new search tab"""
        # Increment counter
        self.last_tab_number += 1
        
        # Add new tab
        new_tab = SearchTab(self.notebook, self)
        self.notebook.add(new_tab, text=f"Search {self.last_tab_number}")
        self.notebook.select(new_tab)
        
        # Update Close Tab menu state
        self.update_close_button_state()
        
        return new_tab

    def close_current_tab(self):
        """Close active tab"""
        current = self.notebook.select()
        if current and self.notebook.index('end') > 1:  # At least one tab should remain
            # Clear tab content before closing
            current_tab = self.notebook.nametowidget(current)
            self.clear_tab(current_tab)
            
            # Wait for active threads
            if hasattr(current_tab, 'active_threads'):
                for thread in current_tab.active_threads:
                    if thread.is_alive():
                        thread.join(timeout=0.1)
            
            # Close tab
            self.notebook.forget(current)
            
            # If no tabs left, add a new one
            if self.notebook.index('end') == 0:
                self.add_tab()
            
            # Update Close Tab menu state
            self.update_close_button_state()

    def get_current_tab(self):
        """Return active tab"""
        current = self.notebook.select()
        if current:
            return self.notebook.nametowidget(current)
        return None

    def clear_tab(self, tab):
        """Clear tab completely"""
        # Clear text widget
        tab.text_widget.configure(state='normal')
        tab.text_widget.delete(1.0, "end")
        tab.text_widget.configure(state='disabled')
        
        # Reset status and progress bar
        tab.status_var.set("")
        tab.progress_bar.stop()
        
        # Clear filtering timer
        if hasattr(tab, 'filter_timer'):
            if tab.filter_timer:
                self.root.after_cancel(tab.filter_timer)
            delattr(tab, 'filter_timer')
        
        # Clear filtering area
        tab.filter_var.set("")
        
        # Reset log content
        tab.full_log_content = ""
        
        # Clear tags
        for tag in tab.text_widget.tag_names():
            tab.text_widget.tag_delete(tag)
        
        # Reset search states
        tab.is_searching = False
        tab.search_completed = False

    def on_tab_changed(self, event):
        """Tab changed event"""
        current_tab = self.get_current_tab()
        if current_tab and current_tab.is_searching:
            # Start GUI updates for new tab
            self.update_gui(current_tab)

    def update_close_button_state(self):
        """Update Close Tab menu state based on tab count"""
        # Find File menu
        menu = self.root.nametowidget(self.menubar.entrycget(0, "menu"))
        
        # Find Close Tab menu item index (after New Tab)
        close_tab_index = 1
        
        if self.notebook.index('end') <= 1:
            menu.entryconfigure(close_tab_index, state="disabled")
        else:
            menu.entryconfigure(close_tab_index, state="normal")

    def bind_shortcuts(self):
        """Bind shortcuts"""
        # Determine system type
        is_mac = sys.platform == "darwin"
        platform_key = "mac" if is_mac else "win"
        
        # New tab shortcut
        new_tab_shortcut = self.shortcuts["new_tab"][platform_key]
        self.root.bind(new_tab_shortcut, lambda e: self.add_tab())
        
        # Tab close shortcut
        close_tab_shortcut = self.shortcuts["close_tab"][platform_key]
        self.root.bind(close_tab_shortcut, lambda e: self.close_current_tab())

if __name__ == "__main__":
    root = tk.Tk()
    app = LogSearcherGUI(root)
    root.mainloop()