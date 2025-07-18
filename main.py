import datetime
import queue
import subprocess
import tkinter as tk
from tkinter import filedialog
from tkinter import ttk, messagebox

from config_manager import ConfigManager
from gui_manager import LogSearcherUI
from log_manager import LogManager
from log_processor import LogProcessor
from search_tab import SearchTab
from settings_manager import SettingsManager


class LogSearcherGUI(LogSearcherUI):
    """
    Main application class and coordinator of all components.
    
    This class brings together and manages all application components:
    - GUI components (inherited from LogSearcherUI)
    - Tab management
    - Log operations
    - Settings
    - Search functionality
    - Event handling
    
    Responsible for coordinating all manager classes 
    (LogManager, SettingsManager, etc.)
    """
    def __init__(self, root):
        super().__init__(root)  # LogSearcherUI'nin init'ini çağır
        self.last_tab_number = 0
        self.log_processor = LogProcessor()
        self.config_manager = ConfigManager()
        self.log_manager = LogManager(self.config_manager, self.log_processor)
        self.settings_manager = SettingsManager(self)
        
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
        self.filter_timer = None
        
        # Add keyboard shortcuts
        self.bind_shortcuts()
        
        # Set window close handler
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

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
        """Handle window close event"""
        try:
            # Stop all searches
            for tab in self.notebook.winfo_children():
                if tab.is_searching:
                    tab.stop_search()
            
            # Save config
            self.config_manager.save_config()
            
            # Destroy window
            self.root.destroy()
            
        except Exception as e:
            print(f"Error during closing: {e}")
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
        
        if self.config_manager.sort_by_time_enabled and current_tab.text_widget.get("1.0", tk.END).strip():
            self.log_processor.sort_logs_by_time(current_tab)
        
        current_tab.status_var.set("Search stopped!")
        current_tab.progress_bar.stop()
        current_tab.toggle_buttons(searching=False)  # Update tab's own button states

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

    def start_search(self):
        search_value = self.search_var.get()
        if not search_value:
            self.status_var.set("Please enter a search value")
            return
        
        filter_pattern = f'"{search_value}"'
        paths_and_profiles = self.config_manager.get_current_paths_and_profiles(self.env_var.get())
        
        # LogSearcher'ı kullan
        self.log_searcher.start_search(self, paths_and_profiles, filter_pattern)
        self.log_manager.update_gui(self)

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
        """Ayarlar penceresini göster"""
        try:
            self.settings_manager.show_settings()
        except Exception as e:
            print(f"Error showing settings: {e}")
            import traceback
            traceback.print_exc()

    def add_tab(self):
        """Add a new search tab"""
        # Increment counter
        self.last_tab_number += 1
        
        # Add new tab
        new_tab = SearchTab(self.notebook, self)
        self.notebook.add(new_tab, text=f"Search {self.last_tab_number}")
        self.notebook.select(new_tab)
        
        return new_tab

    def close_current_tab(self, event=None):
        """Close current tab"""
        current = self.notebook.select()
        if current:
            tab = self.notebook.nametowidget(current)
            
            # Stop any ongoing search
            if tab.is_searching:
                tab.stop_search()
            
            # Remove tab
            self.notebook.forget(self.notebook.index(current))
            
            # If no tabs left, add a new one
            if not self.notebook.tabs():
                self.add_tab()

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
        tab.text_widget.configure(state='normal')
        
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
            self.log_manager.update_gui(current_tab)

    def bind_shortcuts(self):
        """Bind shortcuts"""
        # New tab shortcut
        new_tab_shortcut = self.config_manager.get_shortcut("new_tab")
        self.root.bind(new_tab_shortcut, lambda e: self.add_tab())
        
        # Tab close shortcut
        close_tab_shortcut = self.config_manager.get_shortcut("close_tab")
        self.root.bind(close_tab_shortcut, lambda e: self.close_current_tab())

if __name__ == "__main__":
    try:
        root = tk.Tk()
        app = LogSearcherGUI(root)
        root.mainloop()
    except Exception as e:
        print(f"Error starting application: {e}")
        import traceback
        traceback.print_exc()
