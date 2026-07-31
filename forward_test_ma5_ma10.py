import MetaTrader5 as mt5
import pandas as pd
import time
from datetime import datetime

# ==============================================================================
# 1. PARAMETER KONFIGURASI BOT LIVE
# ==============================================================================
SYMBOL = "XAUUSDm"
LOT = 0.01
SL_BUFFER_POINTS = 50
SIDEWAYS_LOOKBACK = 10
ATR_PERIOD = 14
MIN_TREND_EFFICIENCY = 0.30
MIN_MA10_SLOPE_ATR = 0.50
MIN_ENGULFING_BODY_ATR = 0.10
MAX_ENTRIES_PER_DIRECTION = 3

TIMEFRAME = mt5.TIMEFRAME_H1  # Pastikan TF sesuai dengan strategi Anda
MAGIC_NUMBER = 101010         # ID Unik agar bot mengenali posisinya sendiri
DEVIATION = 20                # Toleransi slippage harga (points)

# ==============================================================================
# 2. FUNGSI LOGIKA UTAMA 
# ==============================================================================
def is_sideways(df):
    candles = df.iloc[:-1].tail(SIDEWAYS_LOOKBACK)
    if len(candles) < SIDEWAYS_LOOKBACK:
        return True

    atr = float(candles.iloc[-1]["atr"])
    if pd.isna(atr) or atr <= 0:
        return True

    total_movement = float(candles["close"].diff().abs().sum())
    net_movement = abs(float(candles.iloc[-1]["close"] - candles.iloc[0]["close"]))
    efficiency = net_movement / total_movement if total_movement > 0 else 0.0
    ma10_slope = abs(float(candles.iloc[-1]["ma10"] - candles.iloc[0]["ma10"]))

    return (efficiency < MIN_TREND_EFFICIENCY and ma10_slope < atr * MIN_MA10_SLOPE_ATR)

def engulfing_signal(df):
    if len(df) < 3:
        return None, df.iloc[-1]

    previous = df.iloc[-3]
    current = df.iloc[-2]
    atr = float(current["atr"])

    if pd.isna(atr) or atr <= 0:
        return None, current

    previous_body = abs(float(previous["close"] - previous["open"]))
    current_body = abs(float(current["close"] - current["open"]))
    valid_body = (current_body >= previous_body and current_body >= atr * MIN_ENGULFING_BODY_ATR)

    bullish_engulfing = (
        previous["close"] < previous["open"]
        and current["close"] > current["open"]
        and current["open"] <= previous["close"]
        and current["close"] >= previous["open"]
        and valid_body
    )
    bearish_engulfing = (
        previous["close"] > previous["open"]
        and current["close"] < current["open"]
        and current["open"] >= previous["close"]
        and current["close"] <= previous["open"]
        and valid_body
    )

    touched_ma5 = current["low"] <= current["ma5"] <= current["high"]
    touched_ma10 = current["low"] <= current["ma10"] <= current["high"]
    
    bullish_ma_rejection = ((touched_ma5 and current["close"] > current["ma5"]) or 
                            (touched_ma10 and current["close"] > current["ma10"]))
    bearish_ma_rejection = ((touched_ma5 and current["close"] < current["ma5"]) or 
                            (touched_ma10 and current["close"] < current["ma10"]))

    if bullish_engulfing and bullish_ma_rejection:
        return "BUY", current
    if bearish_engulfing and bearish_ma_rejection:
        return "SELL", current
    return None, current

def continuation_signal(df, current_direction, num_active_positions):
    if num_active_positions == 0 or current_direction is None:
        return None, df.iloc[-1]
        
    if num_active_positions >= MAX_ENTRIES_PER_DIRECTION:
        return None, df.iloc[-1]

    current = df.iloc[-2]
    touched_ma5 = current["low"] <= current["ma5"] <= current["high"]
    touched_ma10 = current["low"] <= current["ma10"] <= current["high"]
    
    if current_direction == "BUY":
        rejection = (touched_ma5 and current["close"] > current["ma5"]) or (touched_ma10 and current["close"] > current["ma10"])
        if current["close"] > current["open"] and rejection:
            return "BUY", current
    elif current_direction == "SELL":
        rejection = (touched_ma5 and current["close"] < current["ma5"]) or (touched_ma10 and current["close"] < current["ma10"])
        if current["close"] < current["open"] and rejection:
            return "SELL", current
            
    return None, current

# ==============================================================================
# 3. FUNGSI EKSEKUSI MT5 (LIVE TRADING)
# ==============================================================================
def get_data():
    rates = mt5.copy_rates_from_pos(SYMBOL, TIMEFRAME, 0, 100)
    if rates is None:
        return None
    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    df["ma5"] = df["close"].rolling(5).mean()
    df["ma10"] = df["close"].rolling(10).mean()
    previous_close = df["close"].shift(1)
    true_range = pd.concat([
        df["high"] - df["low"], (df["high"] - previous_close).abs(), (df["low"] - previous_close).abs()
    ], axis=1).max(axis=1)
    df["atr"] = true_range.rolling(ATR_PERIOD).mean()
    return df

def get_active_positions():
    positions = mt5.positions_get(symbol=SYMBOL)
    if positions is None:
        return []
    # Filter hanya posisi milik bot ini
    return [p for p in positions if p.magic == MAGIC_NUMBER]

def calculate_live_sl(signal, candle, point_size):
    buffer_distance = SL_BUFFER_POINTS * point_size
    tick = mt5.symbol_info_tick(SYMBOL)
    
    if signal == "BUY":
        reference = min(float(candle["low"]), float(candle["ma10"]))
        return min(reference - buffer_distance, tick.ask - buffer_distance)
    else:
        reference = max(float(candle["high"]), float(candle["ma10"]))
        return max(reference + buffer_distance, tick.bid + buffer_distance)

def open_trade(order_type, sl_price):
    symbol_info = mt5.symbol_info(SYMBOL)
    if not symbol_info.visible:
        mt5.symbol_select(SYMBOL, True)
        
    tick = mt5.symbol_info_tick(SYMBOL)
    
    if order_type == "BUY":
        order_action = mt5.ORDER_TYPE_BUY
        price = tick.ask
    else:
        order_action = mt5.ORDER_TYPE_SELL
        price = tick.bid

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": SYMBOL,
        "volume": float(LOT),
        "type": order_action,
        "price": price,
        "sl": float(sl_price),
        "deviation": DEVIATION,
        "magic": MAGIC_NUMBER,
        "comment": "Bot_MA_Engulfing",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    
    result = mt5.order_send(request)
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        print(f"[!] Gagal Eksekusi {order_type}: {result.comment} (Code: {result.retcode})")
    else:
        print(f"[+] Berhasil Eksekusi {order_type} @ {price} | SL: {sl_price}")

def close_all_positions():
    positions = get_active_positions()
    for pos in positions:
        tick = mt5.symbol_info_tick(SYMBOL)
        
        if pos.type == mt5.ORDER_TYPE_BUY:
            order_type = mt5.ORDER_TYPE_SELL
            price = tick.bid
        else:
            order_type = mt5.ORDER_TYPE_BUY
            price = tick.ask

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": SYMBOL,
            "volume": pos.volume,
            "type": order_type,
            "position": pos.ticket,
            "price": price,
            "deviation": DEVIATION,
            "magic": MAGIC_NUMBER,
            "comment": "Bot_Reverse_Close",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        result = mt5.order_send(request)
        if result.retcode == mt5.TRADE_RETCODE_DONE:
            print(f"[*] Posisi {pos.ticket} berhasil ditutup.")
        else:
            print(f"[!] Gagal menutup posisi {pos.ticket}: {result.comment}")

# ==============================================================================
# 4. ENGINE UTAMA BOT LIVE
# ==============================================================================
def run_live_bot():
    if not mt5.initialize():
        print("[!] Gagal terhubung ke MT5. Pastikan MT5 terbuka.")
        return

    print(f"=========================================================")
    print(f"[*] LIVE TRADING BOT BERJALAN | Aset: {SYMBOL}")
    print(f"[*] Terhubung ke akun: {mt5.account_info().login}")
    print(f"=========================================================")

    last_candle_time = None
    point_size = mt5.symbol_info(SYMBOL).point

    try:
        while True:
            # 1. Tarik data terbaru
            df = get_data()
            if df is None or len(df) < 20:
                time.sleep(2)
                continue

            current_candle_time = df.iloc[-2]["time"]

            # 2. Evaluasi HANYA JIKA ada candle yang baru ditutup
            if last_candle_time is None or current_candle_time > last_candle_time:
                last_candle_time = current_candle_time
                print(f"\n[-] Menunggu peluang... Waktu Server: {datetime.now().strftime('%H:%M:%S')}")

                # Cek Posisi Aktif Saat Ini
                active_positions = get_active_positions()
                num_positions = len(active_positions)
                
                current_direction = None
                if num_positions > 0:
                    current_direction = "BUY" if active_positions[0].type == mt5.ORDER_TYPE_BUY else "SELL"

                # Evaluasi Sinyal
                signal, signal_candle = engulfing_signal(df)
                
                if signal is None:
                    signal, signal_candle = continuation_signal(df, current_direction, num_positions)

                # Eksekusi jika ada sinyal
                if signal is not None:
                    if is_sideways(df):
                        print("[!] Sinyal terdeteksi tapi diabaikan (Pasar Sideways).")
                    else:
                        print(f"[+] Sinyal Valid Terdeteksi: {signal}")
                        
                        # Jika sinyal berlawanan arah dengan posisi saat ini -> Tutup semua (Reverse)
                        if current_direction is not None and signal != current_direction:
                            print("[*] Sinyal Berbalik Arah! Melakukan Reverse Close...")
                            close_all_positions()
                            num_positions = 0 # Update jumlah posisi setelah ditutup

                        # Buka Posisi Baru (Single / Multi-Entry)
                        if num_positions < MAX_ENTRIES_PER_DIRECTION:
                            sl_price = calculate_live_sl(signal, signal_candle, point_size)
                            open_trade(signal, sl_price)
                        else:
                            print(f"[!] Batas maksimal entry ({MAX_ENTRIES_PER_DIRECTION}) telah tercapai.")

            # Jeda waktu sebelum mengecek ulang (mengurangi beban CPU)
            time.sleep(1)

    except KeyboardInterrupt:
        print("\n[!] Bot Live Trading dihentikan oleh pengguna.")
        mt5.shutdown()

if __name__ == "__main__":
    run_live_bot()