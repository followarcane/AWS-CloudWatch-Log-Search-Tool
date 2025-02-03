import subprocess
import datetime
import queue
import threading
import tkinter as tk
from typing import Optional, Tuple, List, TYPE_CHECKING

if TYPE_CHECKING:
    from main import SearchTab  # For type hints only

class LogSearcher:
    
    def __init__(self):
        self.active_threads = []
        self.log_queue = queue.Queue()
        self.is_searching = False
        self.search_completed = False
    
    def search_logs(self, path: str, profile: str, filter_pattern: str, tab: 'SearchTab') -> None:
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
                        
                        # Yeni log başlat
                        current_log = line.strip()
                        try:
                            # Zamanı ayrıştır
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
                        
                        # Log seviyesini belirle
                        current_level = "INFO"
                        if "ERROR" in line.upper():
                            current_level = "ERROR"
                        elif "WARN" in line.upper():
                            current_level = "WARN"
                    else:
                        # Mevcut log varsa, trace logunu ekle
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

    def start_search(self, tab: 'SearchTab', paths_and_profiles: List[Tuple[str, str]], filter_pattern: str) -> None:
        if tab.is_searching:
            return
            
        tab.stop_search()
        tab.clear_content()
        
        if not filter_pattern:
            tab.status_var.set("Please enter a search value")
            return
            
        tab.is_searching = True
        tab.search_completed = False
        tab.toggle_buttons(searching=True)
        tab.progress_bar.start()
        
        # Her yol için ayrı thread başlat
        for path, profile in paths_and_profiles:
            thread = threading.Thread(
                target=self.search_logs,
                args=(path, profile, filter_pattern, tab),
                daemon=True
            )
            thread.start()
            tab.active_threads.append(thread)

    def stop_search(self, tab: 'SearchTab') -> None:
        """Arama işlemini durdurur"""
        tab.is_searching = False
        tab.status_var.set("Stopping search...")
        
        # Aktif thread'leri durdur
        for thread in tab.active_threads:
            if thread.is_alive():
                thread.join(timeout=0.1)
        tab.active_threads.clear()
        
        # Kuyruktaki logları temizle
        while not tab.log_queue.empty():
            try:
                tab.log_queue.get_nowait()
            except queue.Empty:
                break
        
        # Aramayı tamamlandı olarak işaretle
        tab.search_completed = True
        
        # GUI'yi güncelle
        tab.status_var.set("Search stopped!")
        tab.progress_bar.stop()
        tab.toggle_buttons(searching=False) 