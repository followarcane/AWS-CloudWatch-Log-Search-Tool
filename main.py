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

class SearchTab(ttk.Frame):
    """Frame for each search tab"""
    def __init__(self, parent, main_app):
        super().__init__(parent)
        self.main_app = main_app
        self.full_log_content = ""
        self.active_threads = []
        self.log_queue = queue.Queue()
        self.is_searching = False
        self.search_completed = False
        
        # GUI variables
        self.search_var = tk.StringVar()
        self.filter_var = tk.StringVar()
        self.time_var = tk.StringVar(value="1")
        self.env_var = tk.StringVar(value="QA")
        self.status_var = tk.StringVar()
        self.path_filter_var = tk.StringVar(value="All")
        
        # Variable for search dialog
        self.search_dialog = None
        
        # Create GUI
        self.setup_gui()
        
        # Add right-click menu
        self.context_menu = tk.Menu(self, tearoff=0)
        shortcut_text = "⌘D" if sys.platform == "darwin" else "Ctrl+D"
        self.context_menu.add_command(
            label=f"Search Selected Text in New Tab ({shortcut_text})", 
            command=self.search_selected_text
        )
        
        # Bind right-click event to text widget
        self.text_widget.bind("<Button-3>", self.show_context_menu)
        
        # Bind shortcut
        is_mac = sys.platform == "darwin"
        if is_mac:
            self.text_widget.bind("<Command-f>", self.show_search_dialog)
            self.text_widget.bind("<Command-d>", self.search_selected_text)
        else:
            self.text_widget.bind("<Control-f>", self.show_search_dialog)
            self.text_widget.bind("<Control-d>", self.search_selected_text)

        # Bind tab change event to handle search frame
        self.bind('<Visibility>', self.on_tab_change)

    def setup_gui(self):
        # Control frame
        control_frame = ttk.Frame(self)
        control_frame.pack(fill="x", padx=5, pady=5)
        
        # Environment selection
        env_frame = ttk.Frame(control_frame)
        env_frame.pack(side="left", padx=5)
        
        ttk.Label(env_frame, text="Env:").pack(side="left", padx=5)
        self.env_var = tk.StringVar(value="QA")
        env_choices = ["QA", "SB", "PROD"]
        env_menu = ttk.OptionMenu(env_frame, self.env_var, "QA", *env_choices)
        env_menu.pack(side="left", padx=5)
        
        # Search criteria
        search_frame = ttk.Frame(control_frame)
        search_frame.pack(side="left", padx=5)
        
        ttk.Label(search_frame, text="Search:").pack(side="left", padx=5)
        search_entry = ttk.Entry(search_frame, textvariable=self.search_var, width=40)
        search_entry.pack(side="left", padx=5)
        
        # Bind Enter key to search entry
        search_entry.bind('<Return>', lambda e: self.start_search())
        
        ttk.Label(search_frame, text="Start Time:").pack(side="left", padx=5)
        time_entry = ttk.Entry(search_frame, textvariable=self.time_var, width=10)
        time_entry.pack(side="left", padx=5)
        
        # Also bind Enter key to time entry
        time_entry.bind('<Return>', lambda e: self.start_search())
        
        ttk.Label(search_frame, text="hours ago").pack(side="left")
        
        # Buttons
        button_frame = ttk.Frame(control_frame)
        button_frame.pack(side="left", padx=5)
        
        self.search_button = ttk.Button(button_frame, text="Search", command=self.start_search)
        self.search_button.pack(side="left", padx=2)
        
        self.stop_button = ttk.Button(button_frame, text="Stop", command=self.stop_search, state="disabled")
        self.stop_button.pack(side="left", padx=2)
        
        # Stop with Command+Shift+C (macOS) or Ctrl+Shift+C (Windows/Linux)
        if sys.platform == "darwin":
            self.main_app.root.bind('<Command-Shift-C>', lambda e: self.stop_search())
        else:
            self.main_app.root.bind('<Control-Shift-C>', lambda e: self.stop_search())
        
        self.clear_button = ttk.Button(button_frame, text="Clear", command=self.clear_content)
        self.clear_button.pack(side="left", padx=2)
        
        # Filtering frame
        filter_frame = ttk.Frame(self)
        filter_frame.pack(fill="x", padx=5, pady=5)
        
        # Filtering area (left side)
        filter_left_frame = ttk.Frame(filter_frame)
        filter_left_frame.pack(side="left")
        
        ttk.Label(filter_left_frame, text="Filter:").pack(side="left", padx=5)
        self.filter_var.trace_add("write", lambda *args: self.main_app.debounce_filter(self))
        ttk.Entry(filter_left_frame, textvariable=self.filter_var, width=40).pack(side="left", padx=5)
        
        # Frame for spacing
        ttk.Frame(filter_frame).pack(side="left", padx=10)
        
        # Path filter (right side)
        path_filter_frame = ttk.Frame(filter_frame)
        path_filter_frame.pack(side="left")
        
        ttk.Label(path_filter_frame, text="Path:").pack(side="left", padx=5)
        self.path_filter = ttk.Combobox(path_filter_frame, 
            textvariable=self.path_filter_var,
            width=40,
            state="readonly"
        )
        self.path_filter.pack(side="left", padx=5)
        
        # Update path list
        def update_path_list(*args):
            paths = ["All"]
            env = self.env_var.get()
            config = self.main_app.env_configs.get(env, {"paths": []})
            paths.extend(config["paths"])
            self.path_filter['values'] = paths
            if self.path_filter_var.get() not in paths:
                self.path_filter_var.set("All")
        
        # Update path list when environment changes
        self.env_var.trace_add("write", update_path_list)
        update_path_list()  # Initial load
        
        # Apply filtering when path changes
        self.path_filter_var.trace_add("write", lambda *args: self.apply_path_filter())
        
        # Text widget and scrollbar frame
        text_scroll_frame = ttk.Frame(self)
        text_scroll_frame.pack(side="top", fill="both", expand=True)

        # Text widget
        self.text_widget = tk.Text(text_scroll_frame, wrap=tk.WORD, 
            bg='black',
            fg='white',
            insertbackground='white'
        )
        self.text_widget.pack(side="left", fill="both", expand=True)

        # Create tag for quick search
        self.text_widget.tag_configure("quick_search", background="yellow", foreground="black")
        
        # Scrollbar
        scrollbar = ttk.Scrollbar(text_scroll_frame, command=self.text_widget.yview)

        scrollbar.pack(side="right", fill="y")
        self.text_widget.configure(yscrollcommand=scrollbar.set)
        
        # Make text widget read-only
        self.text_widget.configure(state='disabled')
        
        # Status bar and progress bar
        status_frame = ttk.Frame(self)
        status_frame.pack(side="bottom", fill="x")

        # Status bar
        self.progress_bar = ttk.Progressbar(status_frame, mode='indeterminate')
        self.progress_bar.pack(fill="x", padx=5, pady=2)
        ttk.Label(status_frame, textvariable=self.status_var).pack(fill="x", padx=5)

        # Style definitions
        style = ttk.Style()
        style.configure("Search.TFrame", 
            background='#2d2d2d',
            borderwidth=1,
            relief='solid'
        )
        style.configure("Search.TEntry",
            fieldbackground='#2d2d2d',
            foreground='white',
            insertcolor='white',
            borderwidth=0
        )

    def update_full_content(self, content):
        """Update log content"""
        self.full_log_content = content

    def start_search(self):
        """Start search for this tab"""
        if self.is_searching:
            return
            
        self.stop_search()
        self.clear_content()
        
        # Get search value
        search_value = self.search_var.get()
        if not search_value:
            self.status_var.set("Please enter a search value")
            return
            
        filter_pattern = f'"{search_value}"'  # Enclose in quotes
        
        self.is_searching = True
        self.search_completed = False
        self.toggle_buttons(searching=True)
        self.progress_bar.start()
        
        # Start a separate thread for each path
        paths_and_profiles = self.main_app.get_current_paths_and_profiles()
        for path, profile in paths_and_profiles:
            thread = threading.Thread(
                target=self.main_app.search_logs,
                args=(path, profile, filter_pattern, self),
                daemon=True
            )
            thread.start()
            self.active_threads.append(thread)
        
        self.main_app.update_gui(self)

    def stop_search(self):
        """Stop search for this tab"""
        self.is_searching = False
        self.status_var.set("Stopping search...")
        
        # Stop active threads
        for thread in self.active_threads:
            if thread.is_alive():
                thread.join(timeout=0.1)
        self.active_threads.clear()
        
        # Process logs in queue
        while not self.log_queue.empty():
            try:
                self.log_queue.get_nowait()
            except queue.Empty:
                break
        
        # Mark search as completed
        self.search_completed = True
        
        # Update GUI
        self.status_var.set("Search stopped!")
        self.progress_bar.stop()
        self.toggle_buttons(searching=False)
        
        # Sort logs and apply highlight
        if self.main_app.sort_by_time_enabled:
            self.main_app.sort_logs_by_time()
        
        # Highlight searched term
        search_term = self.search_var.get()
        if search_term:
            self.highlight_search(search_term)

    def toggle_buttons(self, searching=True):
        """Update button states"""
        state = "disabled" if searching else "normal"
        self.search_button.configure(state=state)
        self.clear_button.configure(state=state)
        self.stop_button.configure(state="normal" if searching else "disabled")

    def get_filter_pattern(self):
        """Get search value"""
        search_value = self.search_var.get()
        if not search_value:
            return None
        return f'"{search_value}"'

    def clear_content(self):
        """Clear tab content"""
        # Clear text widget
        self.text_widget.configure(state='normal')
        self.text_widget.delete(1.0, "end")
        self.text_widget.configure(state='disabled')
        
        # Reset status and progress bar
        self.status_var.set("")
        self.progress_bar.stop()
        
        # Clear filtering area
        self.filter_var.set("")
        
        # Reset log content
        self.full_log_content = ""
        
        # Clear tags
        for tag in self.text_widget.tag_names():
            self.text_widget.tag_delete(tag)
        
        # Reset search states
        self.search_completed = False

    def show_context_menu(self, event):
        """Show right-click menu"""
        try:
            # Show menu if text is selected
            if self.text_widget.tag_ranges("sel"):
                self.context_menu.post(event.x_root, event.y_root)
        except:
            pass

    def search_selected_text(self, event=None):
        """Search selected text in new tab"""
        try:
            # Get selected text
            if self.text_widget.tag_ranges("sel"):
                selected_text = self.text_widget.selection_get()
                
                # Create new tab
                new_tab = self.main_app.add_tab()
                
                # Copy current tab's environment and time settings
                new_tab.env_var.set(self.env_var.get())
                new_tab.time_var.set(self.time_var.get())
                
                # Set selected text in search box
                new_tab.search_var.set(selected_text)
                
                # Configure button states and states
                new_tab.is_searching = True
                new_tab.search_completed = False
                new_tab.toggle_buttons(searching=True)
                new_tab.progress_bar.start()
                
                # Make sure the new tab is selected and visible
                self.main_app.notebook.select(new_tab)
                
                # Start search in new tab
                new_tab.after(100, lambda: new_tab.start_search())
                
            return "break"
            
        except Exception as e:
            print(f"Error in search_selected_text: {e}")
            return "break"

    def apply_path_filter(self):
        """Apply path-based filtering"""
        try:
            selected_path = self.path_filter_var.get()
            
            # Update text widget
            self.text_widget.configure(state='normal')
            
            # Show all content if "All" is selected and no filter is applied
            if selected_path == "All":
                if not self.filter_var.get():
                    self.text_widget.delete(1.0, tk.END)
                    self.text_widget.insert(tk.END, self.full_log_content)
                    self.main_app.reapply_colors(self)
                    search_term = self.search_var.get()
                    if search_term:
                        self.main_app.highlight_text(self, "1.0", "end", search_term, "search_highlight")
                else:
                    # Apply normal filtering
                    self.main_app.filter_logs(self)
                
                self.text_widget.configure(state='disabled')
                return
            
            # Filter logs based on selected path
            filtered_content = []
            current_log = []
            include_log = False
            
            for line in self.full_log_content.split('\n'):
                # New log start
                if line.strip() and len(line.split()) >= 2 and line.split()[1].count(':') == 2:
                    # Add previous log
                    if current_log and include_log:
                        filtered_content.extend(current_log)
                        filtered_content.append('')  # Add empty line
                    
                    current_log = [line]
                    include_log = selected_path in line
                elif line.strip():
                    current_log.append(line)
            
            # Add last log
            if current_log and include_log:
                filtered_content.extend(current_log)
            
            # Update text widget
            self.text_widget.delete(1.0, tk.END)
            self.text_widget.insert(tk.END, '\n'.join(filtered_content))
            
            # Apply coloring
            self.main_app.reapply_colors(self)
            
            # Highlight search term
            search_term = self.search_var.get()
            if search_term:
                self.main_app.highlight_text(self, "1.0", "end", search_term, "search_highlight")
            
            # Apply normal filtering
            if self.filter_var.get():
                self.main_app.filter_logs(self)
            
        except Exception as e:
            print(f"Path filtering error: {e}")
        finally:
            self.text_widget.configure(state='disabled')

    def highlight_text(self, start, end, text, tag):
        """Highlight given text"""
        if not text:
            return
            
        # Check highlight settings
        if tag == "search_highlight" and not self.main_app.search_highlight_enabled:
            return
        if tag == "filter_highlight" and not self.main_app.filter_highlight_enabled:
            return
            
        # Red for search, yellow for filter highlight
        if tag == "search_highlight":
            self.text_widget.tag_configure(tag, background="#aa0000", foreground="#ffffff")
        else:
            self.text_widget.tag_configure(tag, background="#aaaa00", foreground="#000000")
        
        count = tk.IntVar()
        pos = start
        while True:
            pos = self.text_widget.search(text, pos, end, count=count, nocase=True)
            if not pos:
                break
            self.text_widget.tag_add(tag, pos, f"{pos}+{count.get()}c")
            pos = f"{pos}+{count.get()}c"

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

    def reapply_colors(self):
        """Reapply coloring to all logs"""
        try:
            content = self.text_widget.get("1.0", tk.END)
            lines = content.split('\n')
            
            self.text_widget.delete("1.0", tk.END)
            
            for line in lines:
                if not line.strip():
                    self.text_widget.insert(tk.END, "\n")
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
                        self.text_widget.insert(tk.END, f"{timestamp} ", "timestamp")
                        self.text_widget.insert(tk.END, f"[{level}] ", f"level_{level_color}")
                        self.text_widget.insert(tk.END, f"{message}\n", "message")
                else:
                    # Trace log or other lines
                    self.text_widget.insert(tk.END, f"{line}\n", "message")
            
            # Set coloring tags
            self.text_widget.tag_configure("timestamp", foreground="#8be9fd")
            self.text_widget.tag_configure("message", foreground="white")
            
            for color in ["#ff5555", "#ffb86c", "#50fa7b"]:
                self.text_widget.tag_configure(f"level_{color}", foreground=color)
                
        except Exception as e:
            print(f"Coloring error: {e}")
            self.text_widget.configure(state='disabled')

    def show_search_dialog(self, event=None):
        """Show search dialog"""
        try:
            # Make sure this tab is selected and focused
            current = self.main_app.notebook.select()
            current_tab = self.main_app.notebook.nametowidget(current)
            
            if current_tab != self:
                return "break"
            
            # If search frame already exists, just focus it
            if hasattr(self, 'search_frame'):
                if self.search_frame.winfo_exists():
                    self.search_entry.focus_set()
                    return "break"
            
            # Create search frame
            self.search_frame = ttk.Frame(self.text_widget, style="Search.TFrame")
            
            # Search entry with smaller padding
            search_var = tk.StringVar()
            self.search_entry = ttk.Entry(self.search_frame, textvariable=search_var, width=20)
            self.search_entry.pack(fill='x', padx=2, pady=2)
            
            # Position frame at top-right of text widget
            self.text_widget.update_idletasks()
            frame_width = 200
            self.search_frame.place(
                x=self.text_widget.winfo_width() - frame_width - 5,
                y=5,
                width=frame_width,
                height=30
            )
            
            # Enter handler - just highlight
            def on_enter(event=None):
                search_text = search_var.get()
                if search_text:
                    self.highlight_search(search_text)
                return "break"
            
            # Escape handler - close frame and clean up
            def on_escape(event=None):
                if hasattr(self, 'search_frame') and self.search_frame.winfo_exists():
                    self.clear_highlights()
                    self.search_frame.destroy()
                    delattr(self, 'search_frame')  # Remove the reference
                    self.text_widget.focus_set()
                return "break"
            
            # Bind keys
            self.search_entry.bind("<Return>", on_enter)
            self.search_entry.bind("<Escape>", on_escape)
            
            # Focus entry
            self.search_entry.focus_set()
            
            # Update frame position when text widget is resized
            def update_frame_position(event=None):
                if hasattr(self, 'search_frame') and self.search_frame.winfo_exists():
                    self.search_frame.place(
                        x=self.text_widget.winfo_width() - frame_width - 5,
                        y=5
                    )
            
            self.text_widget.bind('<Configure>', update_frame_position)
            
            return "break"
            
        except Exception as e:
            print(f"Error in show_search_dialog: {e}")
            return "break"

    def clear_highlights(self):
        """Clear all search highlights"""
        try:
            self.text_widget.configure(state='normal')
            self.text_widget.tag_remove("quick_search", "1.0", "end")
        finally:
            self.text_widget.configure(state='disabled')

    def highlight_search(self, search_text):
        """Highlight text in the log"""
        try:
            self.text_widget.configure(state='normal')
            
            # Remove previous highlights
            self.text_widget.tag_remove("quick_search", "1.0", "end")
            
            # Highlight new matches
            start_pos = "1.0"
            while True:
                start_pos = self.text_widget.search(
                    search_text, start_pos, "end", 
                    nocase=True, 
                    regexp=False
                )
                if not start_pos:
                    break
                    
                end_pos = f"{start_pos}+{len(search_text)}c"
                self.text_widget.tag_add("quick_search", start_pos, end_pos)
                start_pos = end_pos
                
            # Configure highlight style
            self.text_widget.tag_config("quick_search", background="yellow", foreground="black")
            
        finally:
            self.text_widget.configure(state='disabled')

    def on_tab_change(self, event):
        """Handle tab change events"""
        # If this tab is not visible and has a search frame, hide it
        if not self.winfo_viewable() and hasattr(self, 'search_frame'):
            if self.search_frame.winfo_exists():
                self.search_frame.destroy()

class LogSearcherGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("AWS Log Searcher")
        self.root.state('zoomed')
        self.root.geometry("1200x800")
        
        # Style definitions
        style = ttk.Style()
        
        # Notebook (tab bar) style
        style.configure("Custom.TNotebook", 
            background='#1a1a1a',  # Dark background
            borderwidth=0,         # No border
            padding=0
        )
        
        style.configure("Custom.TNotebook.Tab",
            padding=[10, 5],      # Horizontal and vertical padding
            background='#2d2d2d', # Normal tab color
            foreground='#808080', # Normal tab text color
            lightcolor='#2d2d2d',
            borderwidth=0,        # No border
        )
        
        style.map("Custom.TNotebook.Tab",
            background=[("selected", '#363636')],  # Selected tab color
            foreground=[("selected", '#ffffff')],  # Selected tab text color
            expand=[("selected", [1, 1, 1, 0])]    # Slightly expand selected tab
        )
        
        # Menu style
        root.option_add('*Menu.background', '#2D2D2D')
        root.option_add('*Menu.foreground', '#FFFFFF')
        root.option_add('*Menu.activeBackground', '#404040')
        root.option_add('*Menu.activeForeground', '#FFFFFF')
        root.option_add('*Menu.selectColor', '#FFFFFF')
        
        # Create menu bar
        self.menubar = tk.Menu(root)
        root.config(menu=self.menubar)
        
        # File menu
        file_menu = tk.Menu(self.menubar, tearoff=0)
        self.menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="New Tab", command=self.add_tab, 
            accelerator="⌘T" if sys.platform == "darwin" else "Ctrl+T")
        file_menu.add_command(label="Close Tab", command=self.close_current_tab, 
            accelerator="⌘⌫" if sys.platform == "darwin" else "Ctrl+Backspace")
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.on_closing)
        
        # Settings menu
        settings_menu = tk.Menu(self.menubar, tearoff=0)
        self.menubar.add_cascade(label="Settings", menu=settings_menu)
        settings_menu.add_command(label="Preferences", command=self.show_settings)
        
        # Read paths from config
        self.load_config()
        self.last_tab_number = 0
        
        # Main container
        main_container = ttk.Frame(root)
        main_container.pack(fill="both", expand=True, padx=10, pady=5)
        
        # Notebook (tab container)
        self.notebook = ttk.Notebook(main_container, style="Custom.TNotebook")
        self.notebook.pack(fill="both", expand=True, padx=0, pady=0)  # Remove padding
        
        # Track tab changes
        self.notebook.bind('<<NotebookTabChanged>>', self.on_tab_changed)
        
        # Add first tab
        self.add_tab()
        
        # To prevent GUI locking
        self.root = root
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        # Debounce timer for filtering
        self.filter_timer = None
        
        # Add keyboard shortcuts
        self.bind_shortcuts()
        
        # Alternative shortcuts for closing tab
        self.root.bind('<Command-BackSpace>', lambda e: self.close_current_tab())  # For macOS
        self.root.bind('<Control-BackSpace>', lambda e: self.close_current_tab())  # For Windows/Linux
        
        # or
        self.root.bind('<Command-d>', lambda e: self.close_current_tab())  # For macOS
        self.root.bind('<Control-d>', lambda e: self.close_current_tab())  # For Windows/Linux

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
            self.sort_logs_by_time()
        
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
        tab.filter_timer = self.root.after(300, lambda: self.filter_logs(tab))

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

    def filter_logs(self, tab):
        """Filter logs"""
        try:
            filter_text = tab.filter_var.get().lower()
            
            # Update text widget
            tab.text_widget.configure(state='normal')
            tab.text_widget.delete(1.0, tk.END)
            
            # If content is empty
            if not tab.full_log_content.strip():
                tab.text_widget.configure(state='disabled')
                return
            
            # If filter is empty, show all logs
            if not filter_text:
                tab.text_widget.insert(tk.END, tab.full_log_content)
                self.reapply_colors(tab)
                search_term = tab.search_var.get()
                if search_term:
                    self.highlight_text(tab, "1.0", "end", search_term, "search_highlight")
                tab.text_widget.configure(state='disabled')
                return
            
            # If filter text is invalid, show original logs
            if not self.is_valid_filter_text(filter_text):
                tab.text_widget.insert(tk.END, tab.full_log_content)
                self.reapply_colors(tab)
                search_term = tab.search_var.get()
                if search_term:
                    self.highlight_text(tab, "1.0", "end", search_term, "search_highlight")
                tab.text_widget.configure(state='disabled')
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
                            self.highlight_text(current_pos, "end", filter_text, "filter_highlight")
            
            # Highlight search term
            search_term = tab.search_var.get()
            if search_term:
                self.highlight_text(tab, "1.0", "end", search_term, "search_highlight")
            
            tab.text_widget.configure(state='disabled')
                        
        except Exception as e:
            print(f"Filtering error: {e}")
            tab.text_widget.configure(state='disabled')

    def highlight_text(self, tab, start, end, text, tag):
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
                    self.sort_logs_by_time()
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

    def sort_logs_by_time(self):
        """Sort logs by time"""
        current_tab = self.get_current_tab()
        if not current_tab:
            return
            
        try:
            # Get all logs from text widget
            current_tab.text_widget.configure(state='normal')
            content = current_tab.text_widget.get(1.0, tk.END)
            
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
            current_tab.text_widget.delete(1.0, tk.END)
            
            # Add sorted logs
            for i, (_, log) in enumerate(parsed_logs):
                # Add separator (except first log)
                if i > 0:
                    current_tab.text_widget.insert(tk.END, "─" * 100 + "\n", "separator")
                    current_tab.text_widget.tag_configure("separator", foreground="#6272a4")
                
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
                        current_pos = current_tab.text_widget.index("end-1c")
                        current_tab.text_widget.insert(tk.END, f"{timestamp} ", "timestamp")
                        current_tab.text_widget.insert(tk.END, f"[{level}] ", f"level_{level_color}")
                        current_tab.text_widget.insert(tk.END, f"{message}\n", "message")
                
                # Add trace logs
                for line in lines[1:]:
                    current_tab.text_widget.insert(tk.END, line + "\n", "message")
                
                current_tab.text_widget.insert(tk.END, "\n")
            
            # Set coloring tags
            current_tab.text_widget.tag_configure("timestamp", foreground="#8be9fd")
            current_tab.text_widget.tag_configure("message", foreground="white")
            
            for color in ["#ff5555", "#ffb86c", "#50fa7b"]:
                current_tab.text_widget.tag_configure(f"level_{color}", foreground=color)
            
            # Reapply highlights
            search_term = current_tab.search_var.get()
            if search_term:
                self.highlight_text(current_tab, "1.0", "end", search_term, "search_highlight")
                
        except Exception as e:
            print(f"Log sorting error: {e}")
        finally:
            current_tab.text_widget.configure(state='disabled')

    def reapply_colors(self, tab):
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
            tab.text_widget.configure(state='disabled')

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