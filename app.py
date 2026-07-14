import customtkinter as ctk
import socket
import threading
import sqlite3
from datetime import datetime
import os

# Konfigurasi Tema
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

class DataApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Data Collector Desktop - Keyboard & TCP")
        self.geometry("700x500")

        # Inisialisasi Database
        self.init_db()

        # --- UI LAYOUT ---
        self.grid_columnconfigure(0, weight=1)
        
        self.label_title = ctk.CTkLabel(self, text="LOG DATA REAL-TIME", font=("Roboto", 24, "bold"))
        self.label_title.pack(pady=20)

        # Input Frame
        self.input_frame = ctk.CTkFrame(self)
        self.input_frame.pack(pady=10, padx=20, fill="x")

        self.entry_kbd = ctk.CTkEntry(self.input_frame, placeholder_text="Ketik di sini (Keyboard Input)...", width=400)
        self.entry_kbd.pack(side="left", padx=10, pady=10, expand=True, fill="x")
        self.entry_kbd.bind("<Return>", self.handle_keyboard)

        self.btn_send = ctk.CTkButton(self.input_frame, text="Simpan", command=self.handle_keyboard)
        self.btn_send.pack(side="right", padx=10)

        # Log Text Area (Display Data)
        self.log_display = ctk.CTkTextbox(self, width=600, height=250)
        self.log_display.pack(pady=10, padx=20, fill="both", expand=True)

        self.label_status = ctk.CTkLabel(self, text="TCP Server: Aktif di 127.0.0.1:5005", text_color="green")
        self.label_status.pack(pady=5)

        # Start TCP Listener in Background
        threading.Thread(target=self.tcp_listener, daemon=True).start()
        
        # Load data awal
        self.refresh_logs()

    def init_db(self):
        # Menggunakan absolute path agar DBeaver dan Python mengarah ke file yang sama
        db_path = os.path.join(os.getcwd(), "database_lokal.db")
        with sqlite3.connect(db_path) as conn:
            conn.execute('''CREATE TABLE IF NOT EXISTS log_data 
                            (id INTEGER PRIMARY KEY AUTOINCREMENT, sumber TEXT, isi_data TEXT, waktu DATETIME)''')

    def save_to_db(self, source, text):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        db_path = os.path.join(os.getcwd(), "database_lokal.db")
        
        try:
            # Menggunakan timeout agar tidak error saat database dibuka oleh DBeaver
            conn = sqlite3.connect(db_path, timeout=10)
            cursor = conn.cursor()
            cursor.execute("INSERT INTO log_data (sumber, isi_data, waktu) VALUES (?, ?, ?)", 
                           (source, text, now))
            conn.commit()  # Simpan perubahan
            conn.close()
            
            # Update tampilan di kotak Textbox GUI (pindah ke baris paling atas)
            self.after(0, lambda: self.log_display.insert("0.0", f"[{now}] {source}: {text}\n"))
        except Exception as e:
            print(f"Gagal simpan: {e}")

    def handle_keyboard(self, event=None):
        text = self.entry_kbd.get()
        if text:
            self.save_to_db("KEYBOARD", text)
            self.entry_kbd.delete(0, 'end')

    def tcp_listener(self):
        # AF_INET = IPv4, SOCK_STREAM = TCP
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(('127.0.0.1', 5005))
                s.listen(5)
                while True:
                    conn, addr = s.accept()
                    with conn:
                        data = conn.recv(1024)
                        if data:
                            self.save_to_db("NETWORK_TCP", data.decode('utf-8').strip())
            except Exception as e:
                print(f"TCP Error: {e}")

    def refresh_logs(self):
        db_path = os.path.join(os.getcwd(), "database_lokal.db")
        if os.path.exists(db_path):
            with sqlite3.connect(db_path) as conn:
                cursor = conn.execute("SELECT waktu, sumber, isi_data FROM log_data ORDER BY id DESC LIMIT 20")
                for row in cursor:
                    self.log_display.insert("end", f"[{row[0]}] {row[1]}: {row[2]}\n")

if __name__ == "__main__":
    app = DataApp()
    app.mainloop()