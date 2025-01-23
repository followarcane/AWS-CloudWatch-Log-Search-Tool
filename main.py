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
    """Her bir arama tab'i için frame"""
    def __init__(self, parent, main_app):
        super().__init__(parent)
        self.main_app = main_app
        self.full_log_content = ""
        self.active_threads = []
        self.log_queue = queue.Queue()
        self.is_searching = False
        self.search_completed = False
        
        # GUI değişkenleri
        self.search_var = tk.StringVar()
        self.filter_var = tk.StringVar()
        self.time_var = tk.StringVar(value="1")
        self.env_var = tk.StringVar(value="QA")
        self.status_var = tk.StringVar()
        self.path_filter_var = tk.StringVar(value="All")
        
        # Search dialog için variable
        self.search_dialog = None
        
        # GUI'yi oluştur
        self.setup_gui()
        
        # Sağ tık menüsü ekle
        self.context_menu = tk.Menu(self, tearoff=0)
        shortcut_text = "⌘D" if sys.platform == "darwin" else "Ctrl+D"
        self.context_menu.add_command(
            label=f"Search Selected Text in New Tab ({shortcut_text})", 
            command=self.search_selected_text
        )
        
        # Text widget'a sağ tık olayını bağla
        self.text_widget.bind("<Button-3>", self.show_context_menu)
        
        # Kısayolu bağla
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
        # Kontrol frame'i
        control_frame = ttk.Frame(self)
        control_frame.pack(fill="x", padx=5, pady=5)
        
        # Environment seçimi
        env_frame = ttk.Frame(control_frame)
        env_frame.pack(side="left", padx=5)
        
        ttk.Label(env_frame, text="Env:").pack(side="left", padx=5)
        self.env_var = tk.StringVar(value="QA")
        env_choices = ["QA", "SB", "PROD"]
        env_menu = ttk.OptionMenu(env_frame, self.env_var, "QA", *env_choices)
        env_menu.pack(side="left", padx=5)
        
        # Arama kriterleri
        search_frame = ttk.Frame(control_frame)
        search_frame.pack(side="left", padx=5)
        
        ttk.Label(search_frame, text="Search:").pack(side="left", padx=5)
        ttk.Entry(search_frame, textvariable=self.search_var, width=40).pack(side="left", padx=5)
        
        ttk.Label(search_frame, text="Start Time:").pack(side="left", padx=5)
        ttk.Entry(search_frame, textvariable=self.time_var, width=10).pack(side="left", padx=5)
        ttk.Label(search_frame, text="hours ago").pack(side="left")
        
        # Butonlar
        button_frame = ttk.Frame(control_frame)
        button_frame.pack(side="left", padx=5)
        
        self.search_button = ttk.Button(button_frame, text="Search", command=self.start_search)
        self.search_button.pack(side="left", padx=2)
        
        self.stop_button = ttk.Button(button_frame, text="Stop", command=self.stop_search, state="disabled")
        self.stop_button.pack(side="left", padx=2)
        
        self.clear_button = ttk.Button(button_frame, text="Clear", command=self.clear_content)
        self.clear_button.pack(side="left", padx=2)
        
        # Filtreleme frame'i
        filter_frame = ttk.Frame(self)
        filter_frame.pack(fill="x", padx=5, pady=5)
        
        # Filtreleme alanı (sol tarafta)
        filter_left_frame = ttk.Frame(filter_frame)
        filter_left_frame.pack(side="left")
        
        ttk.Label(filter_left_frame, text="Filter:").pack(side="left", padx=5)
        self.filter_var.trace_add("write", lambda *args: self.main_app.debounce_filter(self))
        ttk.Entry(filter_left_frame, textvariable=self.filter_var, width=40).pack(side="left", padx=5)
        
        # Boşluk bırakmak için frame
        ttk.Frame(filter_frame).pack(side="left", padx=10)
        
        # Path filtresi (sağ tarafta)
        path_filter_frame = ttk.Frame(filter_frame)
        path_filter_frame.pack(side="left")
        
        ttk.Label(path_filter_frame, text="Path:").pack(side="left", padx=5)
        self.path_filter = ttk.Combobox(path_filter_frame, 
            textvariable=self.path_filter_var,
            width=40,
            state="readonly"
        )
        self.path_filter.pack(side="left", padx=5)
        
        # Path listesini güncelle
        def update_path_list(*args):
            paths = ["All"]
            env = self.env_var.get()
            config = self.main_app.env_configs.get(env, {"paths": []})
            paths.extend(config["paths"])
            self.path_filter['values'] = paths
            if self.path_filter_var.get() not in paths:
                self.path_filter_var.set("All")
        
        # Environment değiştiğinde path listesini güncelle
        self.env_var.trace_add("write", update_path_list)
        update_path_list()  # İlk yükleme
        
        # Path değiştiğinde filtrelemeyi uygula
        self.path_filter_var.trace_add("write", lambda *args: self.apply_path_filter())
        
        # Text widget
        self.text_widget = tk.Text(self, wrap=tk.WORD, 
            bg='black',
            fg='white',
            insertbackground='white'
        )
        self.text_widget.pack(fill="both", expand=True)
        
        # Quick search için tag oluştur
        self.text_widget.tag_configure("quick_search", background="yellow", foreground="black")
        
        # Scrollbar
        scrollbar = ttk.Scrollbar(self, command=self.text_widget.yview)
        scrollbar.pack(side="right", fill="y")
        self.text_widget.configure(yscrollcommand=scrollbar.set)
        
        # Text widget'ı salt okunur yap
        self.text_widget.configure(state='disabled')
        
        # Status bar
        self.progress_bar = ttk.Progressbar(self, mode='indeterminate')
        self.progress_bar.pack(fill="x", padx=5, pady=2)
        ttk.Label(self, textvariable=self.status_var).pack(fill="x", padx=5)

        # Configure styles
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
        """Log içeriğini güncelle"""
        self.full_log_content = content

    def start_search(self):
        """Bu tab için aramayı başlat"""
        if self.is_searching:
            return
            
        self.stop_search()
        self.clear_content()
        
        filter_pattern = self.get_filter_pattern()
        if not filter_pattern:
            self.status_var.set("Lütfen arama değeri girin")
            return
            
        self.is_searching = True
        self.search_completed = False
        self.toggle_buttons(searching=True)
        self.progress_bar.start()
        
        # Her path için ayrı thread başlat
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
        """Bu tab için aramayı durdur"""
        self.is_searching = False
        self.status_var.set("Arama durduruluyor...")
        
        for thread in self.active_threads:
            if thread.is_alive():
                thread.join(timeout=0.1)
        self.active_threads.clear()
        
        while not self.log_queue.empty():
            try:
                self.log_queue.get_nowait()
            except queue.Empty:
                break
                
        self.status_var.set("Arama durduruldu!")
        self.progress_bar.stop()
        self.toggle_buttons(searching=False)

    def toggle_buttons(self, searching=True):
        """Butonların durumunu güncelle"""
        state = "disabled" if searching else "normal"
        self.search_button.configure(state=state)
        self.clear_button.configure(state=state)
        self.stop_button.configure(state="normal" if searching else "disabled")

    def get_filter_pattern(self):
        """Arama değerini al"""
        search_value = self.search_var.get()
        if not search_value:
            return None
        return f'"{search_value}"'

    def clear_content(self):
        """Tab'in içeriğini temizle"""
        # Text widget'ı temizle
        self.text_widget.configure(state='normal')
        self.text_widget.delete(1.0, "end")
        self.text_widget.configure(state='disabled')
        
        # Status ve progress bar'ı sıfırla
        self.status_var.set("")
        self.progress_bar.stop()
        
        # Filtreleme alanını temizle
        self.filter_var.set("")
        
        # Log içeriğini sıfırla
        self.full_log_content = ""
        
        # Tag'leri temizle
        for tag in self.text_widget.tag_names():
            self.text_widget.tag_delete(tag)
        
        # Arama durumlarını sıfırla
        self.search_completed = False

    def show_context_menu(self, event):
        """Sağ tık menüsünü göster"""
        try:
            # Seçili metin varsa menüyü göster
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
        """Path bazlı filtreleme uygula"""
        try:
            selected_path = self.path_filter_var.get()
            
            # Text widget'ı güncelle
            self.text_widget.configure(state='normal')
            
            # Eğer All seçiliyse ve filtre yoksa tüm içeriği göster
            if selected_path == "All":
                if not self.filter_var.get():
                    self.text_widget.delete(1.0, tk.END)
                    self.text_widget.insert(tk.END, self.full_log_content)
                    self.main_app.reapply_colors(self)
                    search_term = self.search_var.get()
                    if search_term:
                        self.main_app.highlight_text(self, "1.0", "end", search_term, "search_highlight")
                else:
                    # Normal filtrelemeyi uygula
                    self.main_app.filter_logs(self)
                
                self.text_widget.configure(state='disabled')
                return
            
            # Seçili path'e göre logları filtrele
            filtered_content = []
            current_log = []
            include_log = False
            
            for line in self.full_log_content.split('\n'):
                # Yeni log başlangıcı
                if line.strip() and len(line.split()) >= 2 and line.split()[1].count(':') == 2:
                    # Önceki logu ekle
                    if current_log and include_log:
                        filtered_content.extend(current_log)
                        filtered_content.append('')  # Boş satır ekle
                    
                    current_log = [line]
                    include_log = selected_path in line
                elif line.strip():
                    current_log.append(line)
            
            # Son logu ekle
            if current_log and include_log:
                filtered_content.extend(current_log)
            
            # Text widget'ı güncelle
            self.text_widget.delete(1.0, tk.END)
            self.text_widget.insert(tk.END, '\n'.join(filtered_content))
            
            # Renklendirmeleri uygula
            self.main_app.reapply_colors(self)
            
            # Arama terimini highlight et
            search_term = self.search_var.get()
            if search_term:
                self.main_app.highlight_text(self, "1.0", "end", search_term, "search_highlight")
            
            # Normal filtrelemeyi de uygula
            if self.filter_var.get():
                self.main_app.filter_logs(self)
            
        except Exception as e:
            print(f"Path filtreleme hatası: {e}")
        finally:
            self.text_widget.configure(state='disabled')

    def highlight_text(self, start, end, text, tag):
        """Verilen metni highlight et"""
        if not text:
            return
            
        # Highlight ayarlarını kontrol et
        if tag == "search_highlight" and not self.main_app.search_highlight_enabled:
            return
        if tag == "filter_highlight" and not self.main_app.filter_highlight_enabled:
            return
            
        # Arama için kırmızı, filtreleme için sarı highlight
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
        """Filtreleme metninin geçerli olup olmadığını kontrol et"""
        if not text:
            return False
            
        # Minimum uzunluk kontrolü
        if len(text) < 2:
            return False
            
        # Sadece özel karakterlerden oluşuyorsa geçersiz
        special_chars = '"\'?!,.:;-_=+<>[]{}()|\\/@#$%^&*'
        special_char_count = sum(1 for c in text if c in special_chars)
        if special_char_count == len(text):
            return False
            
        # Ardışık özel karakter kontrolü
        consecutive_special = 0
        for c in text:
            if c in special_chars:
                consecutive_special += 1
                if consecutive_special > 2:  # En fazla 2 ardışık özel karakter
                    return False
            else:
                consecutive_special = 0
        
        return True

    def reapply_colors(self):
        """Tüm loglar için renklendirmeleri tekrar uygula"""
        try:
            content = self.text_widget.get("1.0", tk.END)
            lines = content.split('\n')
            
            self.text_widget.delete("1.0", tk.END)
            
            for line in lines:
                if not line.strip():
                    self.text_widget.insert(tk.END, "\n")
                    continue
                    
                # Log satırı mı kontrol et
                parts = line.split(' [')
                if len(parts) >= 2:
                    timestamp = parts[0]
                    level_end = parts[1].find(']')
                    if level_end != -1:
                        level = parts[1][:level_end]
                        message = '['.join(parts[1:])
                        
                        # Log seviyesine göre renk belirle
                        if "ERROR" in level:
                            level_color = "#ff5555"
                        elif "WARN" in level:
                            level_color = "#ffb86c"
                        else:
                            level_color = "#50fa7b"
                        
                        # Renkli olarak ekle
                        self.text_widget.insert(tk.END, f"{timestamp} ", "timestamp")
                        self.text_widget.insert(tk.END, f"[{level}] ", f"level_{level_color}")
                        self.text_widget.insert(tk.END, f"{message}\n", "message")
                else:
                    # Trace log veya diğer satırlar
                    self.text_widget.insert(tk.END, f"{line}\n", "message")
            
            # Renklendirme tag'lerini ayarla
            self.text_widget.tag_configure("timestamp", foreground="#8be9fd")
            self.text_widget.tag_configure("message", foreground="white")
            
            for color in ["#ff5555", "#ffb86c", "#50fa7b"]:
                self.text_widget.tag_configure(f"level_{color}", foreground=color)
                
        except Exception as e:
            print(f"Renklendirme hatası: {e}")
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
        
        # Stil tanımlamaları
        style = ttk.Style()
        
        # Notebook (tab bar) stili
        style.configure("Custom.TNotebook", 
            background='#1a1a1a',  # Koyu arka plan
            borderwidth=0,         # Kenarlık yok
            padding=0
        )
        
        style.configure("Custom.TNotebook.Tab",
            padding=[10, 5],      # Yatay ve dikey padding
            background='#2d2d2d', # Tab normal rengi
            foreground='#808080', # Tab normal yazı rengi
            lightcolor='#2d2d2d',
            borderwidth=0,        # Kenarlık yok
        )
        
        style.map("Custom.TNotebook.Tab",
            background=[("selected", '#363636')],  # Seçili tab rengi
            foreground=[("selected", '#ffffff')],  # Seçili tab yazı rengi
            expand=[("selected", [1, 1, 1, 0])]    # Seçili tab'i biraz büyüt
        )
        
        # Menü stili
        root.option_add('*Menu.background', '#2D2D2D')
        root.option_add('*Menu.foreground', '#FFFFFF')
        root.option_add('*Menu.activeBackground', '#404040')
        root.option_add('*Menu.activeForeground', '#FFFFFF')
        root.option_add('*Menu.selectColor', '#FFFFFF')
        
        # Menü çubuğu oluştur
        self.menubar = tk.Menu(root)
        root.config(menu=self.menubar)
        
        # File menüsü
        file_menu = tk.Menu(self.menubar, tearoff=0)
        self.menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="New Tab", command=self.add_tab, 
            accelerator="⌘T" if sys.platform == "darwin" else "Ctrl+T")
        file_menu.add_command(label="Close Tab", command=self.close_current_tab, 
            accelerator="⌘⌫" if sys.platform == "darwin" else "Ctrl+Backspace")
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.on_closing)
        
        # Settings menüsü
        settings_menu = tk.Menu(self.menubar, tearoff=0)
        self.menubar.add_cascade(label="Settings", menu=settings_menu)
        settings_menu.add_command(label="Preferences", command=self.show_settings)
        
        # Configden path'leri oku
        self.load_config()
        self.last_tab_number = 0
        
        # Ana container
        main_container = ttk.Frame(root)
        main_container.pack(fill="both", expand=True, padx=10, pady=5)
        
        # Notebook (tab container)
        self.notebook = ttk.Notebook(main_container, style="Custom.TNotebook")
        self.notebook.pack(fill="both", expand=True, padx=0, pady=0)  # padding'i kaldır
        
        # Tab değişikliğini takip et
        self.notebook.bind('<<NotebookTabChanged>>', self.on_tab_changed)
        
        # İlk tab'i ekle
        self.add_tab()
        
        # GUI kilitlemeyi önlemek için
        self.root = root
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        # Filtreleme için debounce timer
        self.filter_timer = None
        
        # Kısayol tuşlarını ekle
        self.bind_shortcuts()
        
        # Tab kapatma için alternatif kısayollar
        self.root.bind('<Command-BackSpace>', lambda e: self.close_current_tab())  # macOS için
        self.root.bind('<Control-BackSpace>', lambda e: self.close_current_tab())  # Windows/Linux için
        
        # veya
        self.root.bind('<Command-d>', lambda e: self.close_current_tab())  # macOS için
        self.root.bind('<Control-d>', lambda e: self.close_current_tab())  # Windows/Linux için

    def load_config(self):
        try:
            with open('config.json', 'r') as f:
                config = json.load(f)
                self.env_configs = config.get('env_configs', {})
                
                # Highlight ve sıralama ayarlarını yükle
                highlight_settings = config.get("highlight_settings", {})
                self.search_highlight_enabled = highlight_settings.get("search_highlight", True)
                self.filter_highlight_enabled = highlight_settings.get("filter_highlight", True)
                self.sort_by_time_enabled = highlight_settings.get("sort_by_time", True)
                
                # Kısayol ayarlarını yükle
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
                    }
                })
                self.shortcuts = shortcut_settings
                
        except FileNotFoundError:
            # Varsayılan config
            self.env_configs = {
                "QA": {"paths": [], "profiles": {}},
                "SB": {"paths": [], "profiles": {}},
                "PROD": {"paths": [], "profiles": {}}
            }
            # Varsayılan kısayollar
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
        """Girilen zamanı parse et ve uygun formata çevir"""
        time_input = self.time_var.get().strip()
        
        try:
            # Eğer sadece sayı girilmişse saat olarak kabul et
            if time_input.isdigit():
                return f"{time_input}h ago"
            
            # Tarih formatını kontrol et (YYYY-MM-DD HH:mm:ss)
            datetime.datetime.strptime(time_input, "%Y-%m-%d %H:%M:%S")
            return time_input  # Tarih formatı doğruysa aynen döndür
            
        except ValueError as e:
            print(f"Zaman format hatası: {e}")  # Konsola yazdır
            return "1h ago"  # Hatalı format durumunda varsayılan değer
    
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
        """Uygulama kapatılırken thread'leri temizle"""
        current_tab = self.get_current_tab()
        if current_tab:
            current_tab.stop_search()  # Tab'in kendi stop metodunu çağır
        self.root.destroy()

    def stop_search(self):
        current_tab = self.get_current_tab()
        if not current_tab:
            return
            
        # Aramayı durdur
        current_tab.is_searching = False
        current_tab.status_var.set("Arama durduruluyor...")
        
        # Thread'leri bekle
        for thread in current_tab.active_threads:
            if thread.is_alive():
                thread.join(timeout=0.1)
        current_tab.active_threads.clear()
        
        # Queue'yu temizle
        while not current_tab.log_queue.empty():
            try:
                current_tab.log_queue.get_nowait()
            except queue.Empty:
                break
        
        if self.sort_by_time_enabled and current_tab.text_widget.get("1.0", tk.END).strip():
            self.sort_logs_by_time()
        
        current_tab.status_var.set("Arama durduruldu!")
        current_tab.progress_bar.stop()
        current_tab.toggle_buttons(searching=False)  # Tab'in kendi butonlarını güncelle

    def get_current_paths_and_profiles(self):
        """Seçili ortama göre path ve profilleri döndür"""
        current_tab = self.get_current_tab()
        if not current_tab:
            return []
        
        env = current_tab.env_var.get()  # Tab'in kendi env_var'ını kullan
        config = self.env_configs.get(env, {"paths": [], "profiles": {}})
        
        paths_with_profiles = []
        for path in config["paths"]:
            # Path'in hangi profile'a ait olduğunu belirle
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
                tab.time_var.get().strip() + "h ago",  # Tab'in kendi time_var'ını kullan
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
                universal_newlines=True
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
                        
                        # Yeni log başlat
                        current_log = line.strip()
                        try:
                            # Zaman parse et
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
                            print(f"[{path}] Zaman parse hatası: {e}")
                            current_timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                        
                        # Log seviyesini belirle
                        current_level = "INFO"
                        if "ERROR" in line.upper():
                            current_level = "ERROR"
                        elif "WARN" in line.upper():
                            current_level = "WARN"
                    else:
                        # Eğer mevcut log varsa, trace logunu ekle
                        if current_log:
                            current_log += "\n" + line.strip()
            
            # Son logu gönder
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
        """Filtreleme için debounce uygula"""
        if hasattr(tab, 'filter_timer') and tab.filter_timer:
            self.root.after_cancel(tab.filter_timer)
        tab.filter_timer = self.root.after(300, lambda: self.filter_logs(tab))

    def is_valid_filter_text(self, text):
        """Filtreleme metninin geçerli olup olmadığını kontrol et"""
        if not text:
            return False
            
        # Minimum uzunluk kontrolü
        if len(text) < 2:
            return False
            
        # Sadece özel karakterlerden oluşuyorsa geçersiz
        special_chars = '"\'?!,.:;-_=+<>[]{}()|\\/@#$%^&*'
        special_char_count = sum(1 for c in text if c in special_chars)
        if special_char_count == len(text):
            return False
            
        # Ardışık özel karakter kontrolü
        consecutive_special = 0
        for c in text:
            if c in special_chars:
                consecutive_special += 1
                if consecutive_special > 2:  # En fazla 2 ardışık özel karakter
                    return False
            else:
                consecutive_special = 0
        
        return True

    def filter_logs(self, tab):
        """Logları filtrele"""
        try:
            filter_text = tab.filter_var.get().lower()
            
            # Text widget'ı güncelle
            tab.text_widget.configure(state='normal')
            tab.text_widget.delete(1.0, tk.END)
            
            # Eğer içerik boşsa
            if not tab.full_log_content.strip():
                tab.text_widget.configure(state='disabled')
                return
            
            # Eğer filtre boşsa, tüm logları göster
            if not filter_text:
                tab.text_widget.insert(tk.END, tab.full_log_content)
                self.reapply_colors(tab)
                search_term = tab.search_var.get()
                if search_term:
                    self.highlight_text(tab, "1.0", "end", search_term, "search_highlight")
                tab.text_widget.configure(state='disabled')
                return
            
            # Filtre metni geçerli değilse, orijinal logları göster
            if not self.is_valid_filter_text(filter_text):
                tab.text_widget.insert(tk.END, tab.full_log_content)
                self.reapply_colors(tab)
                search_term = tab.search_var.get()
                if search_term:
                    self.highlight_text(tab, "1.0", "end", search_term, "search_highlight")
                tab.text_widget.configure(state='disabled')
                return
            
            # Logları satırlara böl ve grupla
            logs = []
            current_log = []
            
            for line in tab.full_log_content.split('\n'):
                # Eğer bu yeni bir log başlangıcıysa (timestamp ile başlıyorsa)
                if line.strip() and len(line.split()) >= 2 and line.split()[1].count(':') == 2:
                    if current_log:
                        logs.append('\n'.join(current_log))
                    current_log = [line]
                elif line.strip():
                    current_log.append(line)
            
            # Son logu ekle
            if current_log:
                logs.append('\n'.join(current_log))
            
            # Her log grubunu filtrele
            for log in logs:
                if filter_text in log.lower():
                    lines = log.split('\n')
                    first_line = lines[0]
                    
                    # İlk satırı parçala
                    parts = first_line.split(' [')
                    if len(parts) >= 2:
                        timestamp = parts[0]
                        level_end = parts[1].find(']')
                        if level_end != -1:
                            level = parts[1][:level_end]
                            message = '['.join(parts[1:])
                            
                            # Log seviyesine göre renk belirle
                            if "ERROR" in level:
                                level_color = "#ff5555"
                            elif "WARN" in level:
                                level_color = "#ffb86c"
                            else:
                                level_color = "#50fa7b"
                            
                            # Renkli olarak ekle
                            current_pos = tab.text_widget.index("end-1c")
                            tab.text_widget.insert(tk.END, f"{timestamp} ", "timestamp")
                            tab.text_widget.insert(tk.END, f"[{level}] ", f"level_{level_color}")
                            tab.text_widget.insert(tk.END, f"{message}\n", "message")
                            
                            # Trace loglarını ekle
                            for line in lines[1:]:
                                tab.text_widget.insert(tk.END, f"{line}\n", "message")
                            
                            tab.text_widget.insert(tk.END, "\n")
                            
                            # Renklendirme
                            tab.text_widget.tag_configure("timestamp", foreground="#8be9fd")
                            tab.text_widget.tag_configure(f"level_{level_color}", foreground=level_color)
                            tab.text_widget.tag_configure("message", foreground="white")
                            
                            # Filtrelenen metni highlight et
                            self.highlight_text(tab, current_pos, "end", filter_text, "filter_highlight")
            
            # Arama terimini highlight et
            search_term = tab.search_var.get()
            if search_term:
                self.highlight_text(tab, "1.0", "end", search_term, "search_highlight")
            
            tab.text_widget.configure(state='disabled')
                        
        except Exception as e:
            print(f"Filtreleme hatası: {e}")
            tab.text_widget.configure(state='disabled')

    def highlight_text(self, tab, start, end, text, tag):
        """Verilen metni highlight et"""
        if not text:
            return
            
        # Highlight ayarlarını kontrol et
        if tag == "search_highlight" and not self.search_highlight_enabled:
            return
        if tag == "filter_highlight" and not self.filter_highlight_enabled:
            return
            
        # Arama için kırmızı, filtreleme için sarı highlight
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
            # Sadece tab'in geçerli olup olmadığını kontrol et
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
                        
                        # Log girişini ekle
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
                        
                        # Renklendirme
                        tab.text_widget.tag_configure("timestamp", foreground="#8be9fd")
                        tab.text_widget.tag_configure(f"level_{level_color}", foreground=level_color)
                        tab.text_widget.tag_configure("message", foreground="white")
                        
                        # Scroll
                        tab.text_widget.see("end")
                        
                        tab.text_widget.configure(state='disabled')
                        
                        # Orijinal log içeriğini güncelle
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
            
            # Thread durumunu kontrol et
            active_threads = [t for t in tab.active_threads if t.is_alive()]
            
            if not active_threads and tab.log_queue.empty():
                print(f"[Tab {self.notebook.index(tab)}] Search completed")
                tab.is_searching = False
                tab.search_completed = True
                tab.status_var.set("Arama tamamlandı!")
                tab.progress_bar.stop()
                tab.toggle_buttons(searching=False)
                
                if self.sort_by_time_enabled:
                    self.sort_logs_by_time()
            else:
                # Sadece tab'in geçerli olup olmadığını kontrol et
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
            
        # Tüm tab'lerdeki aramaları durdur
        for tab_id in self.notebook.tabs():
            tab = self.notebook.nametowidget(tab_id)
            tab.is_searching = False
            
            # Tab'in thread'lerini bekle
            for thread in tab.active_threads:
                if thread.is_alive():
                    thread.join(timeout=0.1)
            tab.active_threads.clear()
            
            # Queue'yu temizle
            while not tab.log_queue.empty():
                try:
                    tab.log_queue.get_nowait()
                except queue.Empty:
                    break
        
        # Aktif tab'i temizle
        self.clear_tab(current_tab)
        
        filter_pattern = self.get_filter_pattern()
        if not filter_pattern:
            current_tab.status_var.set("Lütfen arama değeri girin")
            return
        
        # Arama durumlarını sıfırla
        current_tab.is_searching = True
        current_tab.search_completed = False
        
        self.toggle_buttons(searching=True)
        current_tab.progress_bar.start()
        
        # Her path için ayrı thread başlat
        paths_and_profiles = self.get_current_paths_and_profiles()
        for path, profile in paths_and_profiles:
            thread = threading.Thread(
                target=self.search_logs,
                args=(path, profile, filter_pattern, current_tab),
                daemon=True
            )
            thread.start()
            current_tab.active_threads.append(thread)
        
        # GUI güncellemesini başlat
        self.update_gui(current_tab)

    def export_results(self):
        """Aktif tab'in içeriğini dışa aktar"""
        current_tab = self.get_current_tab()
        if not current_tab:
            return
            
        if not current_tab.text_widget.get(1.0, "end").strip():
            messagebox.showwarning("Uyarı", "Dışa aktarılacak sonuç bulunamadı!")
            return
            
        file_path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
        )
        
        if file_path:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(current_tab.text_widget.get(1.0, "end"))
            
            messagebox.showinfo("Başarılı", "Sonuçlar başarıyla dışa aktarıldı!")

    def clear_results(self):
        """Aktif tab'in içeriğini temizle"""
        current_tab = self.get_current_tab()
        if not current_tab:
            return
            
        # Queue'yu temizle
        while not current_tab.log_queue.empty():
            try:
                current_tab.log_queue.get_nowait()
            except queue.Empty:
                break
        
        # Tab'i tamamen temizle
        self.clear_tab(current_tab)

    def show_settings(self):
        settings_window = tk.Toplevel(self.root)
        settings_window.title("Ayarlar")
        settings_window.geometry("1000x800")  # Daha büyük pencere
        
        # Highlight ayarları için frame
        highlight_frame = ttk.LabelFrame(settings_window, text="Görünüm Ayarları")
        highlight_frame.pack(fill="x", padx=5, pady=5)
        
        # Search highlight checkbox
        self.search_highlight_var = tk.BooleanVar(value=self.search_highlight_enabled)
        ttk.Checkbutton(highlight_frame, text="Search Highlight", variable=self.search_highlight_var).pack(padx=5, pady=2)
        
        # Filter highlight checkbox
        self.filter_highlight_var = tk.BooleanVar(value=self.filter_highlight_enabled)
        ttk.Checkbutton(highlight_frame, text="Filter Highlight", variable=self.filter_highlight_var).pack(padx=5, pady=2)
        
        # Sort by time checkbox
        self.sort_by_time_var = tk.BooleanVar(value=self.sort_by_time_enabled)
        ttk.Checkbutton(highlight_frame, text="Tarama Bitiminde Zamana Göre Sırala", 
                       variable=self.sort_by_time_var).pack(padx=5, pady=2)
        
        # Notebook (tab) widget'ı oluştur
        notebook = ttk.Notebook(settings_window)
        notebook.pack(fill="both", expand=True, padx=5, pady=5)
        
        # Her ortam için ayrı tab oluştur
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
            
            # Path listesi frame
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
            
            # Her tab için widget'ları sakla
            tabs[env] = {
                "steller_profile": steller_profile,
                "bahama_profile": bahama_profile,
                "steller_paths": steller_paths,
                "bahama_paths": bahama_paths
            }
        
        # Kısayol ayarları için frame
        shortcut_frame = ttk.LabelFrame(settings_window, text="Kısayol Ayarları")
        shortcut_frame.pack(fill="x", padx=5, pady=5)
        
        # Platform seçimi (macOS varsayılan)
        platform_frame = ttk.Frame(shortcut_frame)
        platform_frame.pack(fill="x", padx=5, pady=5)
        
        ttk.Label(platform_frame, text="Platform:").pack(side="left")
        # Sistem tipini kontrol et ve varsayılan değeri belirle
        is_mac = sys.platform == "darwin"
        platform_var = tk.StringVar(value="mac" if is_mac else "win")
        
        ttk.Radiobutton(platform_frame, text="Windows/Linux", 
            variable=platform_var, value="win").pack(side="left", padx=5)
        ttk.Radiobutton(platform_frame, text="macOS", 
            variable=platform_var, value="mac").pack(side="left", padx=5)
        
        # Kısayol düzenleme alanları
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
            """Platform değiştiğinde kısayolları güncelle"""
            platform = platform_var.get()
            for action, entry in shortcut_entries.items():
                entry.delete(0, tk.END)
                entry.insert(0, self.shortcuts[action][platform])
        
        platform_var.trace_add("write", update_shortcut_entries)
        
        def save_settings():
            try:
                # Highlight ve sıralama ayarlarını kaydet
                self.env_configs["highlight_settings"] = {
                    "search_highlight": self.search_highlight_var.get(),
                    "filter_highlight": self.filter_highlight_var.get(),
                    "sort_by_time": self.sort_by_time_var.get()
                }
                
                # Her ortam için ayarları kaydet
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
                
                # Kısayol ayarlarını kaydet
                platform = platform_var.get()
                for action, entry in shortcut_entries.items():
                    self.shortcuts[action][platform] = entry.get()
                
                # Kısayolları yeniden bağla
                self.bind_shortcuts()
                
                self.save_config()
                settings_window.destroy()
                messagebox.showinfo("Başarılı", "Ayarlar kaydedildi!")
                
            except Exception as e:
                messagebox.showerror("Hata", f"Ayarlar kaydedilirken hata oluştu: {str(e)}")
        
        ttk.Button(settings_window, text="Kaydet", command=save_settings).pack(pady=10)

    def sort_logs_by_time(self):
        """Logları zamana göre sırala"""
        current_tab = self.get_current_tab()
        if not current_tab:
            return
            
        try:
            # Text widget'tan tüm logları al
            current_tab.text_widget.configure(state='normal')
            content = current_tab.text_widget.get(1.0, tk.END)
            
            # Logları satırlara böl
            logs = []
            current_log = []
            
            # Her satırı kontrol et
            for line in content.split('\n'):
                # Eğer bu yeni bir log başlangıcıysa (timestamp ile başlıyorsa)
                if line.strip() and len(line.split()) >= 2 and line.split()[1].count(':') == 2:
                    if current_log:
                        logs.append('\n'.join(current_log))
                    current_log = [line]
                elif line.strip():
                    current_log.append(line)
            
            # Son logu ekle
            if current_log:
                logs.append('\n'.join(current_log))
            
            # Her logu parse et ve timestamp ile birlikte sakla
            parsed_logs = []
            for log in logs:
                if not log.strip():
                    continue
                try:
                    lines = log.split('\n')
                    first_line = lines[0]
                    
                    # İlk satırdan timestamp'i al
                    parts = first_line.split()
                    timestamp_str = parts[0] + ' ' + parts[1]
                    timestamp = datetime.datetime.strptime(timestamp_str.split('.')[0], "%Y-%m-%d %H:%M:%S")
                    
                    parsed_logs.append((timestamp, log))
                except (IndexError, ValueError):
                    continue
            
            # Zamana göre sırala
            parsed_logs.sort(key=lambda x: x[0])
            
            # Text widget'ı temizle
            current_tab.text_widget.delete(1.0, tk.END)
            
            # Sıralanmış logları ekle
            for i, (_, log) in enumerate(parsed_logs):
                # Separator ekle (ilk log hariç)
                if i > 0:
                    current_tab.text_widget.insert(tk.END, "─" * 100 + "\n", "separator")
                    current_tab.text_widget.tag_configure("separator", foreground="#6272a4")
                
                # Log satırlarını ekle
                lines = log.split('\n')
                first_line = lines[0]
                
                # İlk satırı parçala
                parts = first_line.split(' [')
                if len(parts) >= 2:
                    timestamp = parts[0]
                    level_end = parts[1].find(']')
                    if level_end != -1:
                        level = parts[1][:level_end]
                        message = '['.join(parts[1:])
                        
                        # Log seviyesine göre renk belirle
                        if "ERROR" in level:
                            level_color = "#ff5555"
                        elif "WARN" in level:
                            level_color = "#ffb86c"
                        else:
                            level_color = "#50fa7b"
                        
                        # Renkli olarak ekle
                        current_pos = current_tab.text_widget.index("end-1c")
                        current_tab.text_widget.insert(tk.END, f"{timestamp} ", "timestamp")
                        current_tab.text_widget.insert(tk.END, f"[{level}] ", f"level_{level_color}")
                        current_tab.text_widget.insert(tk.END, f"{message}\n", "message")
                
                # Trace loglarını ekle
                for line in lines[1:]:
                    current_tab.text_widget.insert(tk.END, line + "\n", "message")
                
                current_tab.text_widget.insert(tk.END, "\n")
            
            # Renklendirme tag'lerini ayarla
            current_tab.text_widget.tag_configure("timestamp", foreground="#8be9fd")
            current_tab.text_widget.tag_configure("message", foreground="white")
            
            for color in ["#ff5555", "#ffb86c", "#50fa7b"]:
                current_tab.text_widget.tag_configure(f"level_{color}", foreground=color)
            
            # Highlight'ları tekrar uygula
            search_term = current_tab.search_var.get()
            if search_term:
                self.highlight_text(current_tab, "1.0", "end", search_term, "search_highlight")
            
            filter_text = current_tab.filter_var.get()
            if filter_text:
                self.highlight_text(current_tab, "1.0", "end", filter_text, "filter_highlight")
                
        except Exception as e:
            print(f"Log sıralama hatası: {e}")
        finally:
            current_tab.text_widget.configure(state='disabled')

    def reapply_colors(self, tab):
        """Tüm loglar için renklendirmeleri tekrar uygula"""
        try:
            content = tab.text_widget.get("1.0", tk.END)
            lines = content.split('\n')
            
            tab.text_widget.delete("1.0", tk.END)
            
            for line in lines:
                if not line.strip():
                    tab.text_widget.insert(tk.END, "\n")
                    continue
                    
                # Log satırı mı kontrol et
                parts = line.split(' [')
                if len(parts) >= 2:
                    timestamp = parts[0]
                    level_end = parts[1].find(']')
                    if level_end != -1:
                        level = parts[1][:level_end]
                        message = '['.join(parts[1:])
                        
                        # Log seviyesine göre renk belirle
                        if "ERROR" in level:
                            level_color = "#ff5555"
                        elif "WARN" in level:
                            level_color = "#ffb86c"
                        else:
                            level_color = "#50fa7b"
                        
                        # Renkli olarak ekle
                        tab.text_widget.insert(tk.END, f"{timestamp} ", "timestamp")
                        tab.text_widget.insert(tk.END, f"[{level}] ", f"level_{level_color}")
                        tab.text_widget.insert(tk.END, f"{message}\n", "message")
                else:
                    # Trace log veya diğer satırlar
                    tab.text_widget.insert(tk.END, f"{line}\n", "message")
            
            # Renklendirme tag'lerini ayarla
            tab.text_widget.tag_configure("timestamp", foreground="#8be9fd")
            tab.text_widget.tag_configure("message", foreground="white")
            
            for color in ["#ff5555", "#ffb86c", "#50fa7b"]:
                tab.text_widget.tag_configure(f"level_{color}", foreground=color)
                
        except Exception as e:
            print(f"Renklendirme hatası: {e}")
            tab.text_widget.configure(state='disabled')

    def add_tab(self):
        """Yeni bir arama tab'i ekle"""
        # Sayacı artır
        self.last_tab_number += 1
        
        # Yeni tab'i ekle
        new_tab = SearchTab(self.notebook, self)
        self.notebook.add(new_tab, text=f"Arama {self.last_tab_number}")
        self.notebook.select(new_tab)
        
        # Kapat butonunun durumunu güncelle
        self.update_close_button_state()
        
        return new_tab

    def close_current_tab(self):
        """Aktif tab'i kapat"""
        current = self.notebook.select()
        if current and self.notebook.index('end') > 1:  # En az bir tab kalsın
            # Tab'i kapatmadan önce içeriğini temizle
            current_tab = self.notebook.nametowidget(current)
            self.clear_tab(current_tab)
            
            # Aktif thread'leri durdur
            if hasattr(current_tab, 'active_threads'):
                for thread in current_tab.active_threads:
                    if thread.is_alive():
                        thread.join(timeout=0.1)
            
            # Tab'i kapat
            self.notebook.forget(current)
            
            # Eğer hiç tab kalmadıysa yeni bir tane ekle
            if self.notebook.index('end') == 0:
                self.add_tab()
            
            # Kapat butonunun durumunu güncelle
            self.update_close_button_state()

    def get_current_tab(self):
        """Aktif tab'i döndür"""
        current = self.notebook.select()
        if current:
            return self.notebook.nametowidget(current)
        return None

    def clear_tab(self, tab):
        """Tab'i tamamen temizle"""
        # Text widget'ı temizle
        tab.text_widget.configure(state='normal')
        tab.text_widget.delete(1.0, "end")
        tab.text_widget.configure(state='disabled')
        
        # Status ve progress bar'ı sıfırla
        tab.status_var.set("")
        tab.progress_bar.stop()
        
        # Filtreleme timer'ı temizle
        if hasattr(tab, 'filter_timer'):
            if tab.filter_timer:
                self.root.after_cancel(tab.filter_timer)
            delattr(tab, 'filter_timer')
        
        # Filtreleme alanını temizle
        tab.filter_var.set("")
        
        # Log içeriğini sıfırla
        tab.full_log_content = ""
        
        # Tag'leri temizle
        for tag in tab.text_widget.tag_names():
            tab.text_widget.tag_delete(tag)
        
        # Arama durumlarını sıfırla
        tab.is_searching = False
        tab.search_completed = False

    def on_tab_changed(self, event):
        """Tab değiştiğinde çağrılır"""
        current_tab = self.get_current_tab()
        if current_tab and current_tab.is_searching:
            # Yeni tab için GUI güncellemesini başlat
            self.update_gui(current_tab)

    def update_close_button_state(self):
        """Tab sayısına göre Close Tab menü öğesinin durumunu güncelle"""
        # File menüsünü bul
        menu = self.root.nametowidget(self.menubar.entrycget(0, "menu"))
        
        # Close Tab menü öğesinin indeksini bul (New Tab'den sonra)
        close_tab_index = 1
        
        if self.notebook.index('end') <= 1:
            menu.entryconfigure(close_tab_index, state="disabled")
        else:
            menu.entryconfigure(close_tab_index, state="normal")

    def bind_shortcuts(self):
        """Kısayolları bağla"""
        # Sistem tipini belirle
        is_mac = sys.platform == "darwin"
        platform_key = "mac" if is_mac else "win"
        
        # Yeni tab kısayolu
        new_tab_shortcut = self.shortcuts["new_tab"][platform_key]
        self.root.bind(new_tab_shortcut, lambda e: self.add_tab())
        
        # Tab kapatma kısayolu
        close_tab_shortcut = self.shortcuts["close_tab"][platform_key]
        self.root.bind(close_tab_shortcut, lambda e: self.close_current_tab())

if __name__ == "__main__":
    root = tk.Tk()
    app = LogSearcherGUI(root)
    root.mainloop()