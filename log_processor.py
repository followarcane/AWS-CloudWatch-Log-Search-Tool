import datetime
import tkinter as tk
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from search_tab import SearchTab

class LogProcessor:
    """
    Class responsible for processing log data.
    
    This class handles log data manipulation:
    - Log filtering
    - Time-based sorting
    - Search term highlighting
    - Log formatting
    - Color and style applications
    """
    def __init__(self, search_highlight_enabled=True, filter_highlight_enabled=True):
        self.search_highlight_enabled = search_highlight_enabled
        self.filter_highlight_enabled = filter_highlight_enabled

    def filter_logs(self, tab: 'SearchTab'):
        """Filter logs based on filter text"""
        try:
            filter_text = tab.filter_var.get().lower()
            
            # Update text widget
            tab.text_widget.configure(state='normal')
            tab.text_widget.delete(1.0, tk.END)
            
            # If content is empty
            if not tab.full_log_content.strip():
                tab.text_widget.configure(state='normal')
                return
            
            # If filter is empty, show all logs
            if not filter_text:
                tab.text_widget.insert(tk.END, tab.full_log_content)
                self.reapply_colors(tab)
                search_term = tab.search_var.get()
                if search_term:
                    self.highlight_text(tab, "1.0", "end", search_term, "search_highlight")
                tab.text_widget.configure(state='normal')
                return
            
            # If filter text is invalid, show original logs
            if not tab.is_valid_filter_text(filter_text):
                tab.text_widget.insert(tk.END, tab.full_log_content)
                self.reapply_colors(tab)
                search_term = tab.search_var.get()
                if search_term:
                    self.highlight_text(tab, "1.0", "end", search_term, "search_highlight")
                tab.text_widget.configure(state='normal')
                return
            
            # Split logs into lines and group them
            logs = []
            current_log = []
            
            for line in tab.full_log_content.split('\n'):
                # If this is a new log start (starts with timestamp)
                if line.strip() and len(line.split()) >= 2 and line.split()[1].count(':') == 2:
                    if current_log:
                        logs.append('\n'.join(current_log))
                    current_log = [line]
                elif line.strip():
                    current_log.append(line)
            
            # Add last log
            if current_log:
                logs.append('\n'.join(current_log))
            
            # Filter each log group
            for log in logs:
                if filter_text in log.lower():
                    lines = log.split('\n')
                    first_line = lines[0]
                    
                    # Parse first line
                    parts = first_line.split(' [')
                    if len(parts) >= 2:
                        timestamp = parts[0]
                        level_end = parts[1].find(']')
                        if level_end != -1:
                            level = parts[1][:level_end]
                            message = '['.join(parts[1:])
                            
                            # Determine color based on log level
                            if "ERROR" in level:
                                level_color = "#ff5555"
                            elif "WARN" in level:
                                level_color = "#ffb86c"
                            else:
                                level_color = "#50fa7b"
                            
                            # Add with color
                            current_pos = tab.text_widget.index("end-1c")
                            tab.text_widget.insert(tk.END, f"{timestamp} ", "timestamp")
                            tab.text_widget.insert(tk.END, f"[{level}] ", f"level_{level_color}")
                            tab.text_widget.insert(tk.END, f"{message}\n", "message")
                            
                            # Add trace logs
                            for line in lines[1:]:
                                tab.text_widget.insert(tk.END, f"{line}\n", "message")
                            
                            tab.text_widget.insert(tk.END, "\n")
                            
                            # Reapply coloring
                            tab.text_widget.tag_configure("timestamp", foreground="#8be9fd")
                            tab.text_widget.tag_configure(f"level_{level_color}", foreground=level_color)
                            tab.text_widget.tag_configure("message", foreground="white")
                            
                            # Highlight filtered text
                            self.highlight_text(tab, current_pos, "end", filter_text, "filter_highlight")
            
            # Highlight search term
            search_term = tab.search_var.get()
            if search_term:
                self.highlight_text(tab, "1.0", "end", search_term, "search_highlight")

            tab.text_widget.configure(state='normal')
                        
        except Exception as e:
            print(f"Filtering error: {e}")
            tab.text_widget.configure(state='normal')

    def sort_logs_by_time(self, tab: 'SearchTab'):
        """Sort logs by timestamp"""
        try:
            # Get all logs from text widget
            tab.text_widget.configure(state='normal')
            content = tab.text_widget.get(1.0, tk.END)
            
            # Split logs into lines
            logs = []
            current_log = []
            
            # Check each line
            for line in content.split('\n'):
                # If this is a new log start (starts with timestamp)
                if line.strip() and len(line.split()) >= 2 and line.split()[1].count(':') == 2:
                    if current_log:
                        logs.append('\n'.join(current_log))
                    current_log = [line]
                elif line.strip():
                    current_log.append(line)
            
            # Add last log
            if current_log:
                logs.append('\n'.join(current_log))
            
            # Parse each log and store with timestamp
            parsed_logs = []
            for log in logs:
                if not log.strip():
                    continue
                try:
                    lines = log.split('\n')
                    first_line = lines[0]
                    
                    # Parse first line for timestamp
                    parts = first_line.split()
                    timestamp_str = parts[0] + ' ' + parts[1]
                    timestamp = datetime.datetime.strptime(timestamp_str.split('.')[0], "%Y-%m-%d %H:%M:%S")
                    
                    parsed_logs.append((timestamp, log))
                except (IndexError, ValueError):
                    continue
            
            # Sort by timestamp
            parsed_logs.sort(key=lambda x: x[0])
            
            # Clear text widget
            tab.text_widget.delete(1.0, tk.END)
            
            # Add sorted logs
            for i, (_, log) in enumerate(parsed_logs):
                # Add separator (except first log)
                if i > 0:
                    tab.text_widget.insert(tk.END, "─" * 100 + "\n", "separator")
                    tab.text_widget.tag_configure("separator", foreground="#6272a4")
                
                # Add log lines
                lines = log.split('\n')
                first_line = lines[0]
                
                # Parse first line
                parts = first_line.split(' [')
                if len(parts) >= 2:
                    timestamp = parts[0]
                    level_end = parts[1].find(']')
                    if level_end != -1:
                        level = parts[1][:level_end]
                        message = '['.join(parts[1:])
                        
                        # Set color based on log level
                        if "ERROR" in level:
                            level_color = "#ff5555"
                        elif "WARN" in level:
                            level_color = "#ffb86c"
                        else:
                            level_color = "#50fa7b"
                        
                        # Add with color
                        current_pos = tab.text_widget.index("end-1c")
                        tab.text_widget.insert(tk.END, f"{timestamp} ", "timestamp")
                        tab.text_widget.insert(tk.END, f"[{level}] ", f"level_{level_color}")
                        tab.text_widget.insert(tk.END, f"{message}\n", "message")
                
                # Add trace logs
                for line in lines[1:]:
                    tab.text_widget.insert(tk.END, line + "\n", "message")
                
                tab.text_widget.insert(tk.END, "\n")
            
            # Set coloring tags
            tab.text_widget.tag_configure("timestamp", foreground="#8be9fd")
            tab.text_widget.tag_configure("message", foreground="white")
            
            for color in ["#ff5555", "#ffb86c", "#50fa7b"]:
                tab.text_widget.tag_configure(f"level_{color}", foreground=color)
            
            # Reapply highlights
            search_term = tab.search_var.get()
            if search_term:
                self.highlight_text(tab, "1.0", "end", search_term, "search_highlight")
                
        except Exception as e:
            print(f"Log sorting error: {e}")
        finally:
            tab.text_widget.configure(state='normal')

    def highlight_text(self, tab: 'SearchTab', start: str, end: str, text: str, tag: str):
        """Highlight given text"""
        if not text:
            return
            
        # Check highlight settings
        if tag == "search_highlight" and not self.search_highlight_enabled:
            return
        if tag == "filter_highlight" and not self.filter_highlight_enabled:
            return
            
        # Red for search, yellow for filter highlight
        if tag == "search_highlight":
            tab.text_widget.tag_configure(tag, background="#aa0000", foreground="#ffffff")
        else:
            tab.text_widget.tag_configure(tag, background="#aaaa00", foreground="#000000")
        
        count = tk.IntVar()
        pos = start
        while True:
            pos = tab.text_widget.search(text, pos, end, count=count, nocase=True)
            if not pos:
                break
            tab.text_widget.tag_add(tag, pos, f"{pos}+{count.get()}c")
            pos = f"{pos}+{count.get()}c"

    def reapply_colors(self, tab: 'SearchTab'):
        """Reapply coloring to all logs"""
        try:
            content = tab.text_widget.get("1.0", tk.END)
            lines = content.split('\n')
            
            tab.text_widget.delete("1.0", tk.END)
            
            for line in lines:
                if not line.strip():
                    tab.text_widget.insert(tk.END, "\n")
                    continue
                    
                # Check if it's a log line
                parts = line.split(' [')
                if len(parts) >= 2:
                    timestamp = parts[0]
                    level_end = parts[1].find(']')
                    if level_end != -1:
                        level = parts[1][:level_end]
                        message = '['.join(parts[1:])
                        
                        # Determine color based on log level
                        if "ERROR" in level:
                            level_color = "#ff5555"
                        elif "WARN" in level:
                            level_color = "#ffb86c"
                        else:
                            level_color = "#50fa7b"
                        
                        # Add with color
                        tab.text_widget.insert(tk.END, f"{timestamp} ", "timestamp")
                        tab.text_widget.insert(tk.END, f"[{level}] ", f"level_{level_color}")
                        tab.text_widget.insert(tk.END, f"{message}\n", "message")
                else:
                    # Trace log or other lines
                    tab.text_widget.insert(tk.END, f"{line}\n", "message")
            
            # Set coloring tags
            tab.text_widget.tag_configure("timestamp", foreground="#8be9fd")
            tab.text_widget.tag_configure("message", foreground="white")
            
            for color in ["#ff5555", "#ffb86c", "#50fa7b"]:
                tab.text_widget.tag_configure(f"level_{color}", foreground=color)
                
        except Exception as e:
            print(f"Coloring error: {e}")
            tab.text_widget.configure(state='normal')
