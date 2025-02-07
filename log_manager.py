import tkinter as tk
from tkinter import ttk
import queue
import datetime
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from search_tab import SearchTab

class LogManager:
    def __init__(self, config_manager, log_processor):
        self.config_manager = config_manager
        self.log_processor = log_processor

    def update_gui(self, tab: 'SearchTab'):
        """Update GUI for given tab"""
        try:
            # Check if tab is valid
            notebook = tab.main_app.notebook
            if not tab in notebook.winfo_children():
                return
            
            if not tab.is_searching and not tab.search_completed:
                return
            
            has_new_logs = False
            batch_size = 0
            
            # Process logs in small batches to prevent GUI freezing
            while batch_size < 5 and not tab.log_queue.empty():
                try:
                    log = tab.log_queue.get_nowait()
                    print(f"[Tab {notebook.index(tab)}] Processing log: {log['timestamp']} [{log['level']}] Queue size: {tab.log_queue.qsize()}")
                    
                    tab.text_widget.configure(state='normal')
                    
                    # Add separator between logs
                    if tab.text_widget.get("1.0", "end").strip():
                        tab.text_widget.insert("end", "─" * 100 + "\n", "separator")
                        tab.text_widget.tag_configure("separator", foreground="#6272a4")
                    
                    # Add log with colors
                    tab.text_widget.insert("end", f"{log['timestamp']} ", "timestamp")
                    
                    level = log['level']
                    level_color = "#50fa7b"  # Default INFO color
                    if level == "ERROR":
                        level_color = "#ff5555"
                    elif level == "WARN":
                        level_color = "#ffb86c"
                    
                    tab.text_widget.insert("end", f"[{level}] ", f"level_{level_color}")
                    tab.text_widget.insert("end", f"{log['message']}\n\n", "message")
                    
                    # Configure tags
                    tab.text_widget.tag_configure("timestamp", foreground="#8be9fd")
                    tab.text_widget.tag_configure(f"level_{level_color}", foreground=level_color)
                    tab.text_widget.tag_configure("message", foreground="white")
                    
                    # Auto-scroll to bottom
                    tab.text_widget.see("end")
                    
                    tab.text_widget.configure(state='disabled')
                    
                    # Update full content
                    tab.full_log_content = tab.text_widget.get(1.0, tk.END)
                    
                    has_new_logs = True
                    batch_size += 1
                    
                except queue.Empty:
                    break
                except Exception as e:
                    print(f"Log processing error: {e}")
                    import traceback
                    traceback.print_exc()
                    continue
            
            # Check if search is completed
            active_threads = [t for t in tab.active_threads if t.is_alive()]
            if not active_threads and tab.log_queue.empty():
                print(f"[Tab {notebook.index(tab)}] Search completed")
                tab.is_searching = False
                tab.search_completed = True
                tab.status_var.set("Search completed!")
                tab.progress_bar.stop()
                tab.toggle_buttons(searching=False)
                
                if self.config_manager.sort_by_time_enabled:
                    self.log_processor.sort_logs_by_time(tab)
            else:
                # Schedule next update if search is still ongoing
                tab.main_app.root.after(100, lambda: self.update_gui(tab))
                
        except Exception as e:
            print(f"[{tab}] GUI update error: {e}")
            import traceback
            traceback.print_exc()

    def clear_logs(self, tab: 'SearchTab'):
        """Clear logs from text widget"""
        tab.text_widget.configure(state='normal')
        tab.text_widget.delete(1.0, tk.END)
        tab.text_widget.configure(state='disabled')
        tab.full_log_content = ""
        
        # Clear all tags
        for tag in tab.text_widget.tag_names():
            tab.text_widget.tag_delete(tag)
        
        # Reset search states
        tab.is_searching = False
        tab.search_completed = False 