import socket
import threading
import sqlite3
from datetime import datetime
import os

# === KONFIGURASI ===
DB_NAME = "database_lokal.db"
TCP_IP = "127.0.0.1"  # Alamat lokal komputer ini
TCP_PORT = 5005       # Port yang ingin dibuka

def inisialisasi_db():
    """Membuat file database dan tabel jika belum ada."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS log_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sumber TEXT,
            isi_data TEXT,
            waktu DATETIME
        )
    ''')
    conn.commit()
    conn.close()
    print(f"[SISTEM] Database {DB_NAME} siap.")

def simpan_ke_db(sumber, pesan):
    """Fungsi pusat untuk menulis data ke SQLite."""
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        waktu_sekarang = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cursor.execute(
            "INSERT INTO log_data (sumber, isi_data, waktu) VALUES (?, ?, ?)",
            (sumber, pesan, waktu_sekarang)
        )
        conn.commit()
        conn.close()
        print(f"\n[SAVE] Berhasil simpan dari {sumber}: {pesan}")
    except Exception as e:
        print(f"\n[ERROR] Gagal simpan ke DB: {e}")

def thread_tcp():
    """Fungsi yang berjalan di background untuk memantau Port TCP."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((TCP_IP, TCP_PORT))
        s.listen(5)
        print(f"[TCP] Menunggu koneksi di {TCP_IP}:{TCP_PORT}...")
        
        while True:
            conn, addr = s.accept()
            with conn:
                # Terima data maksimal 1024 bytes
                data = conn.recv(1024)
                if data:
                    pesan_net = data.decode('utf-8').strip()
                    simpan_ke_db("NETWORK_TCP", pesan_net)

def thread_keyboard():
    """Fungsi yang berjalan untuk menangkap input keyboard di terminal."""
    print("[KBD] Ketik apa saja lalu Enter untuk simpan (Ketik 'keluar' untuk stop):")
    while True:
        teks = input("Input Keyboard > ")
        if teks.lower() == 'keluar':
            print("[SISTEM] Mematikan program...")
            os._exit(0) # Keluar dari semua thread
        if teks.strip():
            simpan_ke_db("KEYBOARD", teks)

# === EKSEKUSI UTAMA ===
if __name__ == "__main__":
    # 1. Siapkan DB
    inisialisasi_db()

    # 2. Jalankan Listener TCP di Thread terpisah (Background)
    t_tcp = threading.Thread(target=thread_tcp, daemon=True)
    t_tcp.start()

    # 3. Jalankan Listener Keyboard di Thread utama
    thread_keyboard()