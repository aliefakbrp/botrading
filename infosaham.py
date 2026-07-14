import yfinance as yf
import requests
import time
import pandas as pd
from datetime import datetime

# PENTING:
# Token kamu sudah pernah kebuka di chat.
# Sebaiknya revoke token di BotFather lalu ganti dengan token baru.
TELEGRAM_BOT_TOKEN = "8613543128:AAHAQP259Qga280MUNTVXTiy-XfpW6ypqAE"
TELEGRAM_CHAT_ID = "831567840"

SYMBOLS = ["BBCA.JK", "BBRI.JK", "TLKM.JK", "BMRI.JK","BNBR.JK"]

INTERVAL = "5m"
PERIOD = "1d"
CHECK_EVERY_SECONDS = 300  # 300 detik = 5 menit


def send_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

    data = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text
    }

    try:
        response = requests.post(url, data=data, timeout=10)

        if response.status_code == 200:
            print("[OK] Pesan terkirim ke Telegram")
        else:
            print("[ERROR] Gagal kirim Telegram:", response.text)

    except Exception as e:
        print("[ERROR] Telegram:", e)


def check_signal(symbol):
    df = yf.download(
        symbol,
        interval=INTERVAL,
        period=PERIOD,
        progress=False,
        auto_adjust=False
    )

    if df.empty or len(df) < 30:
        print(f"[SKIP] Data {symbol} kosong / kurang")
        return None

    # Fix kalau yfinance menghasilkan kolom MultiIndex
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df["EMA5"] = df["Close"].ewm(span=5, adjust=False).mean()
    df["EMA13"] = df["Close"].ewm(span=13, adjust=False).mean()

    prev_ema5 = df["EMA5"].iloc[-2].item()
    prev_ema13 = df["EMA13"].iloc[-2].item()
    last_ema5 = df["EMA5"].iloc[-1].item()
    last_ema13 = df["EMA13"].iloc[-1].item()
    price = df["Close"].iloc[-1].item()

    buy = prev_ema5 <= prev_ema13 and last_ema5 > last_ema13
    sell = prev_ema5 >= prev_ema13 and last_ema5 < last_ema13

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if buy:
        tp = price * 1.02
        cl = price * 0.99

        return (
            f"🚀 BUY WATCH {symbol}\n"
            f"Harga: {price:.0f}\n"
            f"TP: {tp:.0f}\n"
            f"CL: {cl:.0f}\n"
            f"Signal: EMA5 cross up EMA13\n"
            f"Waktu: {now}"
        )

    if sell:
        return (
            f"⚠️ SELL / EXIT WATCH {symbol}\n"
            f"Harga: {price:.0f}\n"
            f"Signal: EMA5 cross down EMA13\n"
            f"Waktu: {now}"
        )

    return None


print("Bot saham aktif...")
send_telegram("✅ Bot saham aktif dan mulai memantau chart.")

while True:
    print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Cek market...")

    for symbol in SYMBOLS:
        try:
            print(f"Cek {symbol}...")

            signal = check_signal(symbol)

            if signal:
                print(signal)
                send_telegram(signal)
            else:
                print(f"Tidak ada signal {symbol}")

        except Exception as e:
            print(f"Error {symbol}: {e}")

    time.sleep(CHECK_EVERY_SECONDS)