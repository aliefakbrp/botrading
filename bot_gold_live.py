import MetaTrader5 as mt5
import pandas as pd
import time
from datetime import datetime

# ==========================================
# 1. KONFIGURASI LIVE (SALDO $1000)
# ==========================================
SYMBOL = "XAUUSDm"      # Sesuaikan nama di Market Watch
TIMEFRAME = mt5.TIMEFRAME_M1
LOTS = 0.01             # Fixed 0.01 Lot
RR_RATIO = 3            # Risk to Reward 1:3
LOOKBACK = 20           # Periode mencari High/Low
MAGIC_NUMBER = 202604   # ID unik bot
BUFFER_PIPS = 0.40      # Cadangan spread (USD) agar SL aman

# ==========================================
# 2. FUNGSI KONEKSI & ORDER
# ==========================================
def initialize_mt5():
    if not mt5.initialize():
        print("[-] Gagal koneksi ke MT5!")
        quit()
    print(f"[{datetime.now()}] Bot Live Aktif | {SYMBOL} | Lot: {LOTS}")

def get_ohlc(n=100):
    rates = mt5.copy_rates_from_pos(SYMBOL, TIMEFRAME, 0, n)
    if rates is None or len(rates) == 0:
        return pd.DataFrame()
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    return df

def send_limit_order(order_type, price, sl, tp):
    # Pastikan harga dibulatkan 2 desimal (Standar Gold)
    price = round(price, 2)
    sl = round(sl, 2)
    tp = round(tp, 2)
    
    request = {
        "action": mt5.TRADE_ACTION_PENDING,
        "symbol": SYMBOL,
        "volume": LOTS,
        "type": order_type,
        "price": price,
        "sl": sl,
        "tp": tp,
        "magic": MAGIC_NUMBER,
        "comment": "SMC_GOLD_BOT",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    result = mt5.order_send(request)
    return result

# ==========================================
# 3. LOGIKA EKSEKUSI (SMC)
# ==========================================
def run_bot():
    last_processed_time = None
    
    while True:
        df = get_ohlc(100)
        if df.empty:
            time.sleep(2)
            continue
            
        current_candle = df.iloc[-1]
        
        # Eksekusi hanya jika muncul candle baru
        if current_candle['time'] != last_processed_time:
            # Cari Struktur High/Low
            window = df.iloc[-(LOOKBACK+1):-1]
            swing_high = window['high'].max()
            swing_low = window['low'].min()
            
            # --- SETUP BUY (BOS UP) ---
            if current_candle['close'] > swing_high:
                # Cari OB (Candle merah terakhir)
                ob_df = df.iloc[-15:-1][df['close'] < df['open']]
                if not ob_df.empty:
                    entry_p = ob_df.iloc[-1]['high']
                    sl_p = ob_df.iloc[-1]['low'] - BUFFER_PIPS
                    risk = entry_p - sl_p
                    
                    if risk > 0.2: # Jarak SL minimal
                        tp_p = entry_p + (risk * RR_RATIO)
                        res = send_limit_order(mt5.ORDER_TYPE_BUY_LIMIT, entry_p, sl_p, tp_p)
                        if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                            print(f"[{datetime.now()}] BUY LIMIT SET @ {entry_p} | TP: {tp_p}")
                            last_processed_time = current_candle['time']

            # --- SETUP SELL (BOS DOWN) ---
            elif current_candle['close'] < swing_low:
                # Cari OB (Candle hijau terakhir)
                ob_df = df.iloc[-15:-1][df['close'] > df['open']]
                if not ob_df.empty:
                    entry_p = ob_df.iloc[-1]['low']
                    sl_p = ob_df.iloc[-1]['high'] + BUFFER_PIPS
                    risk = sl_p - entry_p
                    
                    if risk > 0.2:
                        tp_p = entry_p - (risk * RR_RATIO)
                        res = send_limit_order(mt5.ORDER_TYPE_SELL_LIMIT, entry_p, sl_p, tp_p)
                        if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                            print(f"[{datetime.now()}] SELL LIMIT SET @ {entry_p} | TP: {tp_p}")
                            last_processed_time = current_candle['time']

        time.sleep(10) # Cek market setiap 10 detik

if __name__ == "__main__":
    initialize_mt5()
    try:
        run_bot()
    except KeyboardInterrupt:
        print("\n[!] Bot dimatikan user.")
    finally:
        mt5.shutdown()