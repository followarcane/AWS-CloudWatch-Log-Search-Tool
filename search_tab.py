import tkinter as tk
from tkinter import ttk
import sys
from log_searcher import LogSearcher
import queue

# --- Helper: event to sequence string ---
def event_to_sequence(event):
    mods = []
    if event.state & 0x4:
        mods.append("Control")
    if event.state & 0x10000:
        mods.append("Command")
    if event.state & 0x1:
        mods.append("Shift")
    return f"<{'-'.join(mods + [event.keysym.lower()])}>"
# --- End helper ---

class SearchTab(ttk.Frame):
    """
    Class representing each search tab.
    
    This class manages all functionality of a single search tab:
    - Search interface
    - Log display area
    - Filtering capabilities
    - Search status and progress
    - Tab-specific settings
    - Right-click menu and shortcuts
    """
    def __init__(self, parent, main_app):
        super().__init__(parent)
        self.main_app = main_app
        self.log_manager = main_app.log_manager
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
        
        # Log searcher'ı ekle
        self.log_searcher = LogSearcher()
        
        # Create GUI
        self.setup_gui()
        
        # Add right-click menu
        self.context_menu = tk.Menu(self, tearoff=0)
        # --- Shortcut'ları dinamik gösterimle ekle ---
        config_manager = self.main_app.config_manager
        import platform
        def pretty_shortcut(seq):
            if not seq:
                return ""
            seq = seq.replace("<","").replace(">","")
            keys = seq.split('-')
            is_mac = platform.system() == "Darwin"
            pretty = []
            for k in keys:
                k = k.lower()
                if is_mac:
                    if k == "command":
                        pretty.append("⌘")
                    elif k == "shift":
                        pretty.append("⇧")
                    elif k == "option" or k == "alt":
                        pretty.append("⌥")
                    elif k == "control" or k == "ctrl":
                        pretty.append("⌃")
                    else:
                        pretty.append(k.upper())
                else:
                    if k == "command":
                        pretty.append("Cmd")
                    elif k == "shift":
                        pretty.append("Shift")
                    elif k == "option" or k == "alt":
                        pretty.append("Alt")
                    elif k == "control" or k == "ctrl":
                        pretty.append("Ctrl")
                    else:
                        pretty.append(k.upper())
            return ''.join(pretty) if is_mac else '+'.join(pretty)
        # Search Selected Text in New Tab
        search_selected_shortcut = config_manager.get_shortcut("search_selected")
        search_selected_label = pretty_shortcut(search_selected_shortcut)
        self.context_menu.add_command(
            label=f"Search Selected Text in New Tab ({search_selected_label})" if search_selected_label else "Search Selected Text in New Tab",
            command=self.search_selected_text
        )
        # Copy full log block
        copy_full_log_shortcut = config_manager.get_shortcut("copy_full_log")
        shortcut_label = pretty_shortcut(copy_full_log_shortcut)
        self.context_menu.add_command(
            label=f"Copy full log block ({shortcut_label})" if shortcut_label else "Copy full log block",
            command=lambda: self.copy_full_log(self._last_right_click_event)
        )
        # --- End ---
        
        # Bind right-click event to text widget
        self.text_widget.bind("<Button-3>", self.show_context_menu)

        # --- Bind shortcut for copy full log block ---
        # Shortcut ayarını config'den çek
        config_manager = self.main_app.config_manager
        copy_full_log_shortcut = config_manager.get_shortcut("copy_full_log")
        if copy_full_log_shortcut:
            self.text_widget.bind(copy_full_log_shortcut, self.copy_full_log_shortcut)
        # --- End ---
        
        # --- Shortcut'ları config.json'dan çekip text_widget'a bind et ---
        # --- End ---

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
            config = self.main_app.config_manager.env_configs.get(env, {"paths": []})
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
        
        # self.text_widget.configure(state='disabled') 
        self.text_widget.configure(state='normal')      # Kopyalama için normal modda bırak

        # --- Only allow copy and dynamic shortcuts, block all other edits ---
        config_manager = self.main_app.config_manager
        platform_key = config_manager.get_platform_key()
        allowed_shortcuts = set()
        for action, mapping in config_manager.shortcuts.items():
            allowed_shortcuts.add(mapping.get(platform_key, ""))
        # Her zaman kopyalama tuşunu da ekle
        if platform_key == "mac":
            allowed_shortcuts.add("<Command-c>")
        else:
            allowed_shortcuts.add("<Control-c>")

        def block_unwanted_keys(event):
            # Kopyalama (Ctrl+C, Cmd+C) serbest
            if (event.state & 0x4 and event.keysym.lower() == 'c'):
                return
            if (event.state & 0x10000 and event.keysym.lower() == 'c'):
                return
            # Dinamik shortcutlar serbest
            seq = event_to_sequence(event)
            if seq in allowed_shortcuts:
                return
            # Yazma, kesme, yapıştırma ve diğer her şeyi engelle
            return "break"

        self.text_widget.bind('<Key>', block_unwanted_keys)
        self.text_widget.bind('<<Paste>>', lambda e: "break")
        self.text_widget.bind('<<Cut>>', lambda e: "break")
        self.text_widget.bind('<Control-x>', lambda e: "break")
        self.text_widget.bind('<Command-x>', lambda e: "break")
        self.text_widget.bind('<Button-2>', lambda e: "break")  # Orta tık yapıştırmayı engelle

        # --- Custom copy handler: Command+C ve Control+C her platformda çalışsın diye ---
        def custom_copy(event):
            try:
                selection = self.text_widget.selection_get()
                self.text_widget.clipboard_clear()
                self.text_widget.clipboard_append(selection)
            except tk.TclError:
                pass  # Seçili metin yoksa hata verme
            return "break"

        if platform_key == "mac":
            self.text_widget.bind('<Command-c>', custom_copy)
        else:
            self.text_widget.bind('<Control-c>', custom_copy)
        # --- End of copy/shortcut-only protection ---
        
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
        search_value = self.search_var.get()
        if not search_value:
            self.status_var.set("Please enter a search value")
            return
        
        filter_pattern = f'"{search_value}"'
        paths_and_profiles = self.main_app.config_manager.get_current_paths_and_profiles(self.env_var.get())
        
        # LogSearcher'ı kullan
        self.log_searcher.start_search(self, paths_and_profiles, filter_pattern)
        self.log_manager.update_gui(self)

    def stop_search(self):
        """Stop search for this tab"""
        # LogSearcher'ı kullan
        self.log_searcher.stop_search(self)
        
        # Sort logs and apply highlight
        if hasattr(self.main_app, 'log_processor'):
            self.main_app.log_processor.sort_logs_by_time(self)
        
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
            # Sağ tıklama event'ini sakla (log bloğu için lazım)
            self._last_right_click_event = event
            # Show menu if text is selected veya her zaman göster
            self.context_menu.post(event.x_root, event.y_root)
        except:
            pass

    def copy_full_log(self, event):
        """Copy the full log block at the right-clicked position or cursor position, wrapped in triple backticks"""
        try:
            # Sağ tıklama veya kısayol ile çağrılabilir
            if hasattr(self, '_last_right_click_event') and event == self._last_right_click_event:
                index = self.text_widget.index(f"@{event.x},{event.y}")
            else:
                # Kısayol ile çağrıldıysa, imlecin olduğu satırı kullan
                index = self.text_widget.index(tk.INSERT)
            line_no = int(index.split('.')[0])
            total_lines = int(self.text_widget.index('end-1c').split('.')[0])
            # Yukarı doğru log başını bul
            start = line_no
            while start > 1:
                line = self.text_widget.get(f"{start}.0", f"{start}.end").strip()
                if (not line) or (line.startswith('─') and line.endswith('─')):
                    start += 1
                    break
                start -= 1
            else:
                start = 1
            # Aşağı doğru log sonunu bul
            end = line_no
            while end < total_lines:
                line = self.text_widget.get(f"{end}.0", f"{end}.end").strip()
                if (not line) or (line.startswith('─') and line.endswith('─')):
                    end -= 1
                    break
                end += 1
            # Log bloğunu al
            log_text = self.text_widget.get(f"{start}.0", f"{end}.end")
            # Clipboard'a kopyala
            self.text_widget.clipboard_clear()
            self.text_widget.clipboard_append(log_text)
        except Exception as e:
            print(f"Log block could not be copied: {e}")
        return "break"

    def copy_full_log_shortcut(self, event):
        """Kısayol ile log bloğu kopyalama"""
        return self.copy_full_log(event)

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
                    self.main_app.log_processor.reapply_colors(self)
                    search_term = self.search_var.get()
                    if search_term:
                        self.main_app.log_processor.highlight_text(self, "1.0", "end", search_term, "search_highlight")
                else:
                    # Apply normal filtering
                    self.main_app.log_processor.filter_logs(self)
                
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
            self.main_app.log_processor.reapply_colors(self)
            
            # Highlight search term
            search_term = self.search_var.get()
            if search_term:
                self.main_app.log_processor.highlight_text(self, "1.0", "end", search_term, "search_highlight")
            
            # Apply normal filtering
            if self.filter_var.get():
                self.main_app.log_processor.filter_logs(self)
            
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