import customtkinter as ctk
import socket
import threading
import sqlite3
from datetime import datetime
import os
import tkinter as tk

# Konfigurasi Tema
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

class DataApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Data Collector - TCP Validator")
        self.geometry("800x600")

        # Daftar angka yang dianggap VALID
        self.whitelist_angka = ["12345", "67890", "2024"]

        # Inisialisasi Database
        self.init_db()

        # --- UI LAYOUT ---
        self.label_title = ctk.CTkLabel(self, text="LOG VALIDASI TCP REAL-TIME", font=("Roboto", 24, "bold"))
        self.label_title.pack(pady=20)

        # Log Text Area
        self.log_display = ctk.CTkTextbox(self, width=700, height=350, font=("Consolas", 12))
        self.log_display.pack(pady=10, padx=20, fill="both", expand=True)
        
        # Setup warna (Tags) untuk textbox
        self.log_display._textbox.tag_config("valid", foreground="#2ecc71") # Hijau
        self.log_display._textbox.tag_config("invalid", foreground="#e74c3c") # Merah

        # --- INFO STATUS ---
        # Tampilkan IP Laptop agar kamu mudah melihatnya saat setting di HP
        local_ip = socket.gethostbyname(socket.gethostname())
        self.label_status = ctk.CTkLabel(
            self, 
            text=f"Server Aktif | IP Laptop: {local_ip} | Port: 5005", 
            text_color="cyan",
            font=("Roboto", 14)
        )
        self.label_status.pack(pady=10)

        # Start TCP Listener
        threading.Thread(target=self.tcp_listener, daemon=True).start()
        
        # Load data history
        self.refresh_logs()

    def init_db(self):
        db_path = os.path.join(os.getcwd(), "database_lokal.db")
        with sqlite3.connect(db_path) as conn:
            conn.execute('''CREATE TABLE IF NOT EXISTS log_data 
                            (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                             sumber TEXT, 
                             isi_data TEXT, 
                             status TEXT,
                             waktu DATETIME)''')

    def save_and_display(self, source, text, status):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        db_path = os.path.join(os.getcwd(), "database_lokal.db")
        
        try:
            conn = sqlite3.connect(db_path, timeout=10)
            cursor = conn.cursor()
            cursor.execute("INSERT INTO log_data (sumber, isi_data, status, waktu) VALUES (?, ?, ?, ?)", 
                           (source, text, status, now))
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"DB Error: {e}")

        tag = "valid" if status == "VALID" else "invalid"
        log_msg = f"[{now}] {source} -> Data: {text} | Status: {status}\n"
        
        # Update UI secara aman dari thread berbeda
        self.after(0, lambda: self.log_display._textbox.insert("0.0", log_msg, tag))

    def tcp_listener(self):
        # PERUBAHAN DISINI: Pakai '0.0.0.0' agar bisa diakses dari HP (Luar Device)
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
                            input_user = data.decode('utf-8').strip()
                            
                            # Logika Validasi
                            res_status = "VALID" if input_user in self.whitelist_angka else "INVALID"
                            
                            # Kirim hasil ke fungsi simpan & display
                            self.save_and_display(f"NET_{addr[0]}", input_user, res_status)
            except Exception as e:
                print(f"TCP Error: {e}")

    def refresh_logs(self):
        db_path = os.path.join(os.getcwd(), "database_lokal.db")
        if os.path.exists(db_path):
            with sqlite3.connect(db_path) as conn:
                cursor = conn.execute("SELECT waktu, sumber, isi_data, status FROM log_data ORDER BY id DESC LIMIT 20")
                for row in cursor:
                    tag = "valid" if row[3] == "VALID" else "invalid"
                    msg = f"[{row[0]}] {row[1]} -> Data: {row[2]} | Status: {row[3]}\n"
                    self.log_display._textbox.insert("end", msg, tag)

if __name__ == "__main__":
    app = DataApp()
    app.mainloop()