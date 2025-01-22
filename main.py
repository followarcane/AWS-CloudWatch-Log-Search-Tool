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

class LogSearcherGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("AWS Log Searcher")
        
        # Tam ekran aç
        self.root.state('zoomed')  # Windows için
        # Alternatif olarak:
        # self.root.attributes('-zoomed', True)  # Linux için
        
        self.root.geometry("1200x800")
        
        # Configden path'leri oku
        self.load_config()
        
        # Ana container
        main_container = ttk.Frame(root)
        main_container.pack(fill="both", expand=True, padx=10, pady=5)
        
        # Search frame
        search_frame = ttk.LabelFrame(main_container, text="Arama Kriterleri")
        search_frame.pack(fill="x", padx=5, pady=5)
        
        # Environment selection frame
        env_frame = ttk.Frame(search_frame)
        env_frame.pack(fill="x", padx=5, pady=5)
        
        ttk.Label(env_frame, text="Ortam:").pack(side="left", padx=5)
        self.env_var = tk.StringVar(value="QA")
        env_choices = ["QA", "SB", "PROD"]
        env_menu = ttk.OptionMenu(env_frame, self.env_var, "QA", *env_choices)
        env_menu.pack(side="left", padx=5)
        
        # Search criteria
        criteria_frame = ttk.Frame(search_frame)
        criteria_frame.pack(fill="x", padx=5, pady=5)
        
        # Search (filter pattern)
        ttk.Label(criteria_frame, text="Search:").grid(row=0, column=0, padx=5, pady=5)
        self.search_var = tk.StringVar()
        ttk.Entry(criteria_frame, textvariable=self.search_var, width=40).grid(row=0, column=1, padx=5, pady=5)
        
        # Time range
        ttk.Label(criteria_frame, text="Start Time:").grid(row=0, column=2, padx=5, pady=5)
        self.time_var = tk.StringVar(value="1")
        time_entry = ttk.Entry(criteria_frame, textvariable=self.time_var, width=20)
        time_entry.grid(row=0, column=3, padx=2, pady=5)
        ttk.Label(criteria_frame, text="(hours ago or YYYY-MM-DD HH:mm:ss)").grid(row=0, column=4, padx=2, pady=5)
        
        # Buttons
        self.button_frame = ttk.Frame(criteria_frame)
        self.button_frame.grid(row=1, column=0, columnspan=5, pady=5)
        
        self.search_button = ttk.Button(self.button_frame, text="Ara", command=self.start_search)
        self.search_button.pack(side="left", padx=5)
        
        self.stop_button = ttk.Button(self.button_frame, text="Durdur", command=self.stop_search, state="disabled")
        self.stop_button.pack(side="left", padx=5)
        
        self.clear_button = ttk.Button(self.button_frame, text="Temizle", command=self.clear_results)
        self.clear_button.pack(side="left", padx=5)
        
        self.export_button = ttk.Button(self.button_frame, text="Dışa Aktar", command=self.export_results)
        self.export_button.pack(side="left", padx=5)
        
        self.settings_button = ttk.Button(self.button_frame, text="Ayarlar", command=self.show_settings)
        self.settings_button.pack(side="left", padx=5)
        
        # Results frame
        results_frame = ttk.LabelFrame(main_container, text="Sonuçlar")
        results_frame.pack(fill="both", expand=True, padx=5, pady=5)
        
        # Filtreleme frame'i
        filter_frame = ttk.Frame(results_frame)
        filter_frame.pack(fill="x", padx=5, pady=5)
        
        ttk.Label(filter_frame, text="Filtrele:").pack(side="left", padx=5)
        self.filter_var = tk.StringVar()
        self.filter_var.trace_add("write", self.debounce_filter)  # filter_logs yerine debounce_filter
        filter_entry = ttk.Entry(filter_frame, textvariable=self.filter_var, width=40)
        filter_entry.pack(side="left", padx=5)
        
        # Text widget
        self.text_widget = tk.Text(results_frame, wrap=tk.WORD, 
            bg='black',     # Arka plan siyah
            fg='white',     # Varsayılan metin rengi beyaz
            insertbackground='white'  # İmleç rengi beyaz
        )
        self.text_widget.pack(fill="both", expand=True)
        
        # Scrollbar - koyu tema için
        scrollbar = ttk.Scrollbar(results_frame, command=self.text_widget.yview)
        scrollbar.pack(side="right", fill="y")
        self.text_widget.configure(yscrollcommand=scrollbar.set)
        
        # Text widget'ı salt okunur yap
        self.text_widget.configure(state='disabled')
        
        # Status bar
        self.status_var = tk.StringVar()
        self.progress_bar = ttk.Progressbar(root, mode='indeterminate')
        self.progress_bar.pack(fill="x", padx=5, pady=2)
        ttk.Label(root, textvariable=self.status_var).pack(fill="x", padx=5)
        
        # Queue for thread communication
        self.log_queue = queue.Queue()
        
        # Search control
        self.is_searching = False
        
        # Thread kontrolü için
        self.active_threads = []  # Aktif thread'leri takip etmek için
        
        # GUI kilitlemeyi önlemek için
        self.root = root
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)  # Pencere kapatıldığında temizlik yap
        
        # Filtreleme için debounce timer
        self.filter_timer = None

    def load_config(self):
        try:
            with open('config.json', 'r') as f:
                config = json.load(f)
                self.env_configs = config.get('env_configs', {})
                
                # Highlight ve sıralama ayarlarını yükle
                highlight_settings = self.env_configs.get("highlight_settings", {})
                self.search_highlight_enabled = highlight_settings.get("search_highlight", True)
                self.filter_highlight_enabled = highlight_settings.get("filter_highlight", True)
                self.sort_by_time_enabled = highlight_settings.get("sort_by_time", True)  # Yeni ayar
                
        except FileNotFoundError:
            # Varsayılan config
            self.env_configs = {
                "QA": {"paths": [], "profiles": {}},
                "SB": {"paths": [], "profiles": {}},
                "PROD": {"paths": [], "profiles": {}}
            }
            self.save_config()
            self.search_highlight_enabled = True
            self.filter_highlight_enabled = True
            self.sort_by_time_enabled = True  # Varsayılan değer
    
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
        self.stop_search()
        self.root.destroy()

    def stop_search(self):
        """Aramayı durdur ve thread'leri temizle"""
        self.is_searching = False
        self.status_var.set("Arama durduruluyor...")
        
        # Aktif thread'leri bekle
        for thread in self.active_threads:
            if thread.is_alive():
                thread.join(timeout=0.1)
        
        # Thread listesini temizle
        self.active_threads.clear()
        
        # Eğer sıralama seçeneği aktifse ve loglar varsa sırala
        if self.sort_by_time_enabled and self.text_widget.get("1.0", tk.END).strip():
            self.sort_logs_by_time()
        
        self.status_var.set("Arama durduruldu!")
        self.progress_bar.stop()
        self.toggle_buttons(searching=False)

    def get_current_paths_and_profiles(self):
        """Seçili ortama göre path ve profilleri döndür"""
        env = self.env_var.get()
        config = self.env_configs.get(env, {"paths": [], "profiles": {}})
        
        paths_with_profiles = []
        for path in config["paths"]:
            # Path'in hangi profile'a ait olduğunu belirle
            profile = config["profiles"]["steller"] if "steller" in path else config["profiles"]["bahama"]
            paths_with_profiles.append((path, profile))
            
        return paths_with_profiles

    def search_logs(self, path, profile, filter_pattern):
        try:
            cmd = [
                "awslogs",
                "get",
                path,
                "--profile",
                profile,
                "--start",
                self.get_time_range(),
                "--query=log"
            ]
            
            if filter_pattern:
                cmd.extend(["--filter-pattern", filter_pattern])
            
            # Komutu terminale yazdır
            command_str = " ".join(cmd)
            print(f"Executing command: {command_str}")
            
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1, encoding='utf-8')
            
            # Son log zamanını hesapla
            try:
                time_input = self.time_var.get().strip()
                if time_input.isdigit():
                    target_time = datetime.datetime.now() - datetime.timedelta(hours=int(time_input))
                else:
                    target_time = datetime.datetime.strptime(time_input, "%Y-%m-%d %H:%M:%S")
            except ValueError as e:
                print(f"Zaman parse hatası: {e}")
                return
            
            current_log = None  # Şu anki ana log
            current_timestamp = None  # Şu anki timestamp
            current_level = None  # Şu anki log seviyesi
            
            while self.is_searching:
                line = process.stdout.readline()
                if not line and process.poll() is not None:
                    break
                
                if line.strip():
                    # Log path'i içeriyor mu kontrol et
                    is_main_log = path in line
                    
                    if is_main_log:
                        # Eğer önceki log varsa gönder
                        if current_log:
                            self.log_queue.put({
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
                                        log_time = datetime.datetime.strptime(time_str.split('.')[0], "%Y-%m-%d %H:%M:%S")
                                        current_timestamp = time_str
                                        break
                                except ValueError:
                                    continue
                        except Exception as e:
                            print(f"Zaman parse hatası: {e}")
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
                            current_log += line
            
            # Son logu gönder
            if current_log:
                self.log_queue.put({
                    "timestamp": current_timestamp,
                    "level": current_level,
                    "message": current_log
                })
            
            # Arama durdurulduğunda veya bittiğinde process'i sonlandır
            process.terminate()
            process.wait(timeout=1)
            
        except Exception as e:
            print(f"Log arama hatası ({path}): {str(e)}")
            return

    def debounce_filter(self, *args):
        """Filtreleme için debounce uygula"""
        if self.filter_timer:
            self.root.after_cancel(self.filter_timer)
        self.filter_timer = self.root.after(300, self.filter_logs)  # 300ms bekle

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

    def filter_logs(self, *args):
        """Logları filtrele"""
        try:
            filter_text = self.filter_var.get().lower()
            
            # Mevcut içeriği yedekle (eğer henüz yapılmamışsa)
            if not hasattr(self, 'full_log_content'):
                self.full_log_content = self.text_widget.get(1.0, tk.END)
            
            # Text widget'ı güncelle
            self.text_widget.configure(state='normal')
            self.text_widget.delete(1.0, tk.END)
            
            # Eğer filtre boşsa, tüm logları göster
            if not filter_text:
                self.text_widget.insert(tk.END, self.full_log_content)
                
                # Renklendirmeleri tekrar uygula
                self.reapply_colors()
                
                # Highlight'ları tekrar uygula
                search_term = self.search_var.get()
                if search_term:
                    self.highlight_text("1.0", "end", search_term, "search_highlight")
                    
                self.text_widget.configure(state='disabled')
                return
            
            # Filtre metni geçerli değilse, orijinal logları göster
            if not self.is_valid_filter_text(filter_text):
                self.text_widget.insert(tk.END, self.full_log_content)
                self.reapply_colors()
                search_term = self.search_var.get()
                if search_term:
                    self.highlight_text("1.0", "end", search_term, "search_highlight")
                self.text_widget.configure(state='disabled')
                return
            
            # Logları satırlara böl
            lines = self.full_log_content.split('\n')
            total_lines = len(lines)
            batch_size = 50  # Her batch'te işlenecek satır sayısı
            
            def process_batch(start_idx):
                end_idx = min(start_idx + batch_size, total_lines)
                
                # Bu batch'teki satırları işle
                for line in lines[start_idx:end_idx]:
                    if filter_text in line.lower():
                        # Satırı parçalara ayır
                        parts = line.split(' [')
                        if len(parts) >= 2:
                            timestamp = parts[0]
                            level_end = parts[1].find(']')
                            if level_end != -1:
                                level = parts[1][:level_end]
                                message = '['.join(parts[1:])
                                
                                # Renk tanımlamaları
                                if "ERROR" in level:
                                    level_color = "#ff5555"
                                elif "WARN" in level:
                                    level_color = "#ffb86c"
                                else:
                                    level_color = "#50fa7b"
                                
                                # Parçaları renkli ekle
                                current_pos = self.text_widget.index("end-1c")
                                self.text_widget.insert(tk.END, f"{timestamp} ", "timestamp")
                                self.text_widget.insert(tk.END, f"[{level}] ", f"level_{level_color}")
                                self.text_widget.insert(tk.END, f"{message}\n", "message")
                                
                                # Renklendirme
                                self.text_widget.tag_configure("timestamp", foreground="#8be9fd")
                                self.text_widget.tag_configure(f"level_{level_color}", foreground=level_color)
                                self.text_widget.tag_configure("message", foreground="white")
                                
                                # Filtrelenen metni highlight et
                                self.highlight_text(current_pos, "end", filter_text, "filter_highlight")
                
                # Eğer daha işlenecek satır varsa, sonraki batch'i planla
                if end_idx < total_lines:
                    self.root.after(1, lambda: process_batch(end_idx))
                else:
                    # Tüm satırlar işlendi, son işlemleri yap
                    search_term = self.search_var.get()
                    if search_term:
                        self.highlight_text("1.0", "end", search_term, "search_highlight")
                    self.text_widget.configure(state='disabled')
            
            # İlk batch'i başlat
            process_batch(0)
            
        except Exception as e:
            print(f"Filtreleme hatası: {e}")
            self.text_widget.configure(state='disabled')

    def highlight_text(self, start, end, text, tag):
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
            # Kırmızı highlight (daha parlak ve belirgin)
            self.text_widget.tag_configure(tag, background="#aa0000", foreground="#ffffff")
        else:
            # Sarı highlight (daha parlak ve belirgin)
            self.text_widget.tag_configure(tag, background="#aaaa00", foreground="#000000")
        
        count = tk.IntVar()
        pos = start
        while True:
            pos = self.text_widget.search(text, pos, end, count=count, nocase=True)
            if not pos:
                break
            self.text_widget.tag_add(tag, pos, f"{pos}+{count.get()}c")
            pos = f"{pos}+{count.get()}c"

    def update_gui(self):
        try:
            if not self.is_searching:
                return
                
            has_new_logs = False
            batch_size = 0  # Batch sayacı
            try:
                # Queue'dan log al (bloke etmeden)
                while batch_size < 5:  # Her seferinde en fazla 5 log işle
                    try:
                        log_entry = self.log_queue.get_nowait()
                        has_new_logs = True
                        batch_size += 1
                        
                        self.text_widget.configure(state='normal')
                        
                        timestamp = log_entry["timestamp"]
                        level = log_entry["level"]
                        message = log_entry["message"]
                        
                        # Renk tanımlamaları
                        if level == "ERROR":
                            level_color = "#ff5555"
                        elif level == "WARN":
                            level_color = "#ffb86c"
                        else:
                            level_color = "#50fa7b"
                        
                        # Log girişini ekle
                        current_pos = self.text_widget.index("end-1c")
                        
                        # Eğer bu ilk log değilse, öncesine separator ekle
                        if self.text_widget.get("1.0", "end").strip():
                            self.text_widget.insert("end", "─" * 100 + "\n", "separator")
                            self.text_widget.tag_configure("separator", foreground="#6272a4")
                        
                        self.text_widget.insert("end", f"{timestamp} ", "timestamp")
                        self.text_widget.insert("end", f"[{level}] ", f"level_{level_color}")
                        self.text_widget.insert("end", f"{message}\n\n", "message")
                        
                        # Renklendirme
                        self.text_widget.tag_configure("timestamp", foreground="#8be9fd")
                        self.text_widget.tag_configure(f"level_{level_color}", foreground=level_color)
                        self.text_widget.tag_configure("message", foreground="white")
                        
                        # Aranan kelimeyi highlight et
                        search_term = self.search_var.get()
                        if search_term:
                            self.highlight_text(current_pos, "end", search_term, "search_highlight")
                        
                        self.text_widget.configure(state='disabled')
                        
                    except queue.Empty:
                        break
                    
                # Scroll'u sadece batch sonunda yap
                if has_new_logs:
                    self.text_widget.see("end")
                    
            except Exception as e:
                print(f"Log işleme hatası: {e}")
            
            # Aktif thread'leri kontrol et
            active_count = len([t for t in self.active_threads if t.is_alive()])
            
            if active_count == 0 and self.log_queue.empty():
                self.is_searching = False
                self.status_var.set("Arama tamamlandı!")
                self.progress_bar.stop()
                self.toggle_buttons(searching=False)
                
                # Sıralama seçeneği aktifse logları sırala
                if self.sort_by_time_enabled:
                    self.sort_logs_by_time()
            else:
                # GUI güncellemesini daha az sıklıkla planla
                self.root.after(50, self.update_gui)  # 50ms bekle
                
        except Exception as e:
            print(f"GUI güncelleme hatası: {e}")

    def start_search(self):
        # Önceki thread'leri temizle
        self.stop_search()
        
        # Önceki sonuçları temizle
        self.clear_results()
        
        filter_pattern = self.get_filter_pattern()
        if not filter_pattern:
            self.status_var.set("Lütfen arama değeri girin")
            return
        
        self.is_searching = True
        self.toggle_buttons(searching=True)
        self.progress_bar.start()
        
        # Her path için ayrı thread başlat
        paths_and_profiles = self.get_current_paths_and_profiles()
        for path, profile in paths_and_profiles:
            thread = threading.Thread(
                target=self.search_logs,
                args=(path, profile, filter_pattern),
                daemon=True
            )
            thread.start()
            self.active_threads.append(thread)
        
        # GUI güncellemelerini başlat
        self.update_gui()

    def export_results(self):
        if not self.text_widget.get(1.0, "end").strip():
            messagebox.showwarning("Uyarı", "Dışa aktarılacak sonuç bulunamadı!")
            return
            
        file_path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")]
        )
        
        if file_path:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(self.text_widget.get(1.0, "end"))
            
            messagebox.showinfo("Başarılı", "Sonuçlar başarıyla dışa aktarıldı!")

    def clear_results(self):
        self.text_widget.configure(state='normal')
        self.text_widget.delete(1.0, "end")
        self.text_widget.configure(state='disabled')
        self.status_var.set("")
        self.progress_bar.stop()

    def show_settings(self):
        settings_window = tk.Toplevel(self.root)
        settings_window.title("Ayarlar")
        settings_window.geometry("800x600")
        
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
        
        def save_settings():
            try:
                # Highlight ve sıralama ayarlarını kaydet
                self.env_configs["highlight_settings"] = {
                    "search_highlight": self.search_highlight_var.get(),
                    "filter_highlight": self.filter_highlight_var.get(),
                    "sort_by_time": self.sort_by_time_var.get()  # Yeni ayar
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
                
                self.save_config()
                settings_window.destroy()
                messagebox.showinfo("Başarılı", "Ayarlar kaydedildi!")
                
            except Exception as e:
                messagebox.showerror("Hata", f"Ayarlar kaydedilirken hata oluştu: {str(e)}")
        
        ttk.Button(settings_window, text="Kaydet", command=save_settings).pack(pady=10)

    def sort_logs_by_time(self):
        """Logları zamana göre sırala"""
        try:
            # Text widget'tan tüm logları al
            self.text_widget.configure(state='normal')
            content = self.text_widget.get(1.0, tk.END)
            
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
            self.text_widget.delete(1.0, tk.END)
            
            # Sıralanmış logları ekle
            for i, (_, log) in enumerate(parsed_logs):
                # Separator ekle (ilk log hariç)
                if i > 0:
                    self.text_widget.insert(tk.END, "─" * 100 + "\n", "separator")
                    self.text_widget.tag_configure("separator", foreground="#6272a4")
                
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
                        self.text_widget.insert(tk.END, f"{timestamp} ", "timestamp")
                        self.text_widget.insert(tk.END, f"[{level}] ", f"level_{level_color}")
                        self.text_widget.insert(tk.END, f"{message}\n", "message")
                
                # Trace loglarını ekle
                for line in lines[1:]:
                    self.text_widget.insert(tk.END, line + "\n", "message")
                
                self.text_widget.insert(tk.END, "\n")
            
            # Renklendirme tag'lerini ayarla
            self.text_widget.tag_configure("timestamp", foreground="#8be9fd")
            self.text_widget.tag_configure("message", foreground="white")
            
            for color in ["#ff5555", "#ffb86c", "#50fa7b"]:
                self.text_widget.tag_configure(f"level_{color}", foreground=color)
            
            # Highlight'ları tekrar uygula
            search_term = self.search_var.get()
            if search_term:
                self.highlight_text("1.0", "end", search_term, "search_highlight")
            
            filter_text = self.filter_var.get()
            if filter_text:
                self.highlight_text("1.0", "end", filter_text, "filter_highlight")
                
        except Exception as e:
            print(f"Log sıralama hatası: {e}")
        finally:
            self.text_widget.configure(state='disabled')

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

if __name__ == "__main__":
    root = tk.Tk()
    app = LogSearcherGUI(root)
    root.mainloop()