import tkinter as tk
from tkinter import ttk, messagebox
import sys
from typing import Optional

class LogSearcherUI:
    """GUI bileşenlerini yöneten sınıf"""
    
    def __init__(self, root: tk.Tk):
        self.root = root
        self.setup_window()
        self.setup_styles()
        self.create_menu()
        
    def setup_window(self):
        """Ana pencere ayarları"""
        self.root.title("AWS Log Searcher")
        self.root.state('zoomed')
        self.root.geometry("1200x800")
        
    def setup_styles(self):
        """TTK stilleri"""
        style = ttk.Style()
        
        # Notebook (tab bar) style
        style.configure("Custom.TNotebook", 
            background='#1a1a1a',
            borderwidth=0,
            padding=0
        )
        
        style.configure("Custom.TNotebook.Tab",
            padding=[10, 5],
            background='#2d2d2d',
            foreground='#808080',
            lightcolor='#2d2d2d',
            borderwidth=0,
        )
        
        style.map("Custom.TNotebook.Tab",
            background=[("selected", '#363636')],
            foreground=[("selected", '#ffffff')],
            expand=[("selected", [1, 1, 1, 0])]
        )
        
        # Menu style
        self.root.option_add('*Menu.background', '#2D2D2D')
        self.root.option_add('*Menu.foreground', '#FFFFFF')
        self.root.option_add('*Menu.activeBackground', '#404040')
        self.root.option_add('*Menu.activeForeground', '#FFFFFF')
        self.root.option_add('*Menu.selectColor', '#FFFFFF')
        
        # Search frame style
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
    
    def create_menu(self):
        """Menü oluşturma"""
        self.menubar = tk.Menu(self.root)
        self.root.config(menu=self.menubar)
        
        # File menu
        file_menu = tk.Menu(self.menubar, tearoff=0)
        self.menubar.add_cascade(label="File", menu=file_menu)
        
        shortcut = "⌘T" if sys.platform == "darwin" else "Ctrl+T"
        file_menu.add_command(label=f"New Tab ({shortcut})", 
                            command=self.on_new_tab)
        
        shortcut = "⌘⌫" if sys.platform == "darwin" else "Ctrl+Backspace"
        file_menu.add_command(label=f"Close Tab ({shortcut})", 
                            command=self.on_close_tab)
        
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.on_exit)
        
        # Settings menu
        settings_menu = tk.Menu(self.menubar, tearoff=0)
        self.menubar.add_cascade(label="Settings", menu=settings_menu)
        settings_menu.add_command(label="Preferences", 
                                command=self.on_preferences)
    
    def on_new_tab(self):
        """Yeni tab oluşturma"""
        if hasattr(self, 'add_tab'):
            self.add_tab()
        
    def on_close_tab(self):
        """Tab kapatma"""
        if hasattr(self, 'close_current_tab'):
            self.close_current_tab()
        
    def on_exit(self):
        """Uygulamadan çıkış"""
        if hasattr(self, 'on_closing'):
            self.on_closing()
        
    def on_preferences(self):
        """Ayarlar penceresi"""
        if hasattr(self, 'show_settings'):
            self.show_settings() 