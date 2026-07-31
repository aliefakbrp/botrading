import json
import os
import time
import MetaTrader5 as mt5

SYMBOL = "XAUUSDm"
LOT = 0.01
MAGIC_NUMBER = 999888

COMMON_PATH = os.path.join(
    os.getenv("APPDATA"), "MetaQuotes", "Terminal", "Common", "Files", "signal.json"
)


def get_signal_data():
    if os.path.exists(COMMON_PATH):
        try:
            with open(COMMON_PATH, "r") as f:
                return json.load(f)
        except Exception:
            return None
    return None


def execute_trade(data):
    signal = data.get("signal")
    sl = data.get("sl", 0.0)
    tp = data.get("tp", 0.0)

    if signal not in ["BUY", "SELL"]:
        return

    # Cek apakah sudah ada posisi aktif
    positions = mt5.positions_get(symbol=SYMBOL, group=f"*{MAGIC_NUMBER}*")
    if positions and len(positions) > 0:
        return  # Batasi 1 posisi aktif saja

    symbol_info = mt5.symbol_info(SYMBOL)
    if not symbol_info:
        return

    price = symbol_info.ask if signal == "BUY" else symbol_info.bid
    order_type = mt5.ORDER_TYPE_BUY if signal == "BUY" else mt5.ORDER_TYPE_SELL

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": SYMBOL,
        "volume": LOT,
        "type": order_type,
        "price": price,
        "sl": sl,
        "tp": tp,
        "deviation": 20,
        "magic": MAGIC_NUMBER,
        "comment": "Bot Indicator Bridge",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }

    res = mt5.order_send(request)
    if res.retcode == mt5.TRADE_RETCODE_DONE:
        print(f"[+] Order {signal} Eksekusi Sukses di {price} | SL: {sl} | TP: {tp}")
    else:
        print(f"[-] Gagal Order: {res.comment}")


# Loop Utama
if mt5.initialize():
    print("[+] Bot Python Siap Menunggu Sinyal...")
    last_processed_time = ""

    while True:
        data = get_signal_data()
        if data:
            sig_time = data.get("time")
            # Jalankan hanya jika sinyal berasal dari waktu/candle baru
            if sig_time != last_processed_time:
                execute_trade(data)
                last_processed_time = sig_time

        time.sleep(1)