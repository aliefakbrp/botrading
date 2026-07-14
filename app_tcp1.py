import customtkinter as ctk
import socket
import threading
import sqlite3
from datetime import datetime

class IndustrialApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("SICK Sensor Validator - TCP to Serial")
        # Perbaikan bug geometry di sini
        self.geometry("900x650")

        # --- UI LAYOUT ---
        self.label_title = ctk.CTkLabel(self, text="SICK SENSOR MONITORING", font=("Roboto", 24, "bold"))
        self.label_title.pack(pady=10)

        # Frame Input (ID & SET)
        self.input_frame = ctk.CTkFrame(self)
        self.input_frame.pack(pady=10, padx=20, fill="x")

        ctk.CTkLabel(self.input_frame, text="ID:").grid(row=0, column=0, padx=10, pady=10)
        self.entry_id = ctk.CTkEntry(self.input_frame, placeholder_text="Contoh: 01")
        self.entry_id.grid(row=0, column=1, padx=10)

        ctk.CTkLabel(self.input_frame, text="SET (Target):").grid(row=0, column=2, padx=10, pady=10)
        self.entry_set = ctk.CTkEntry(self.input_frame, placeholder_text="Input Target")
        self.entry_set.grid(row=0, column=3, padx=10)
        
        # Dashboard Status
        self.info_frame = ctk.CTkFrame(self)
        self.info_frame.pack(pady=10, padx=20, fill="x")
        
        self.label_rad = ctk.CTkLabel(self.info_frame, text="RAD (Reading): ---", font=("Roboto", 18))
        self.label_rad.pack(side="left", padx=50)
        
        self.status_indicator = ctk.CTkLabel(self.info_frame, text="STAS: -", font=("Roboto", 22, "bold"))
        self.status_indicator.pack(side="right", padx=50)

        # Log Display
        self.log_display = ctk.CTkTextbox(self, width=800, height=300, font=("Consolas", 12))
        self.log_display.pack(pady=10, padx=20)
        
        self.log_display.tag_config("match", foreground="#2ecc71")
        self.log_display.tag_config("mismatch", foreground="#e74c3c")

        # Info Jaringan
        try:
            local_ip = socket.gethostbyname(socket.gethostname())
        except:
            local_ip = "127.0.0.1"
            
        self.label_net = ctk.CTkLabel(self, text=f"SERVER RUNNING AT {local_ip}:5005", text_color="cyan")
        self.label_net.pack(pady=5)

        self.init_db()
        # Menjalankan listener di thread terpisah agar UI tidak freeze
        threading.Thread(target=self.tcp_listener, daemon=True).start()

    def init_db(self):
        with sqlite3.connect("industrial_logs.db") as conn:
            conn.execute('''CREATE TABLE IF NOT EXISTS logs 
                            (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                             sensor_id TEXT,
                             set_val TEXT, 
                             read_val TEXT, 
                             status TEXT, 
                             waktu DATETIME)''')

    def process_validation(self, read_value, addr):
        now = datetime.now().strftime("%H:%M:%S")
        target = self.entry_set.get().strip()
        sensor_id = self.entry_id.get().strip() or "Unknown"
        
        self.label_rad.configure(text=f"RAD: {read_value}")
        
        # Validasi
        if read_value == target:
            status = "F" # Match
            color = "#2ecc71"
            tag = "match"
        else:
            status = "NG" # Mismatch
            color = "#e74c3c"
            tag = "mismatch"

        self.status_indicator.configure(text=f"STAS: {status}", text_color=color)

        # Log Message (Data baru di baris paling atas)
        log_msg = f"[{now}] ID:{sensor_id} | SET:{target} | RAD:{read_value} | STAS:{status}\n"
        self.log_display.insert("1.0", log_msg, tag)
        
        with sqlite3.connect("industrial_logs.db") as conn:
            conn.execute("INSERT INTO logs (sensor_id, set_val, read_val, status, waktu) VALUES (?,?,?,?,?)",
                         (sensor_id, target, read_value, status, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))

    def tcp_listener(self):
        # Menggunakan IP 0.0.0.0 agar bisa menerima koneksi dari IP mana pun (termasuk Packet Sender)
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind(('0.0.0.0', 5005))
                s.listen(5)
                while True:
                    conn, addr = s.accept()
                    with conn:
                        data = conn.recv(1024)
                        if data:
                            # Decode dan bersihkan karakter aneh
                            read_val = data.decode('utf-8', errors='ignore').strip()
                            # Kirim ke main thread untuk update UI
                            self.after(0, lambda r=read_val, a=addr[0]: self.process_validation(r, a))
            except Exception as e:
                print(f"TCP Error: {e}")

if __name__ == "__main__":
    app = IndustrialApp()
    app.mainloop()