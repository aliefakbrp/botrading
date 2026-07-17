import os
import pandas as pd
import numpy as np

# ==============================================================================
# 1. PARAMETER KONFIGURASI STRATEGI (Sama persis dengan bot live v2)
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

# Parameter Simulasi Akun dan Pasar (Disesuaikan untuk Emas/XAUUSD)
INITIAL_BALANCE = 100.0   # Modal Awal (USD)
POINT_VALUE = 0.01          # Nilai 1 poin/pip untuk emas (2 digit belakang koma)
LOT_SIZE_VALUE = 100        # Kontrak size emas standar (1 Lot = 100 Oz)
SPREAD_POINTS = 20          # Simulasi spread broker (20 poin = 2.0 pips)

# ==============================================================================
# 2. FUNGSI LOGIKA UTAMA (Murni logika aslimu dari ma5_ma10_engulfing_m1_v2.py)
# ==============================================================================
def is_sideways(df_slice):
    candles = df_slice.iloc[:-1].tail(SIDEWAYS_LOOKBACK)
    if len(candles) < SIDEWAYS_LOOKBACK:
        return True

    atr = float(candles.iloc[-1]["atr"])
    if pd.isna(atr) or atr <= 0:
        return True

    total_movement = float(candles["close"].diff().abs().sum())
    net_movement = abs(float(candles.iloc[-1]["close"] - candles.iloc[0]["close"]))
    efficiency = net_movement / total_movement if total_movement > 0 else 0.0
    ma10_slope = abs(float(candles.iloc[-1]["ma10"] - candles.iloc[0]["ma10"]))

    return (
        efficiency < MIN_TREND_EFFICIENCY
        and ma10_slope < atr * MIN_MA10_SLOPE_ATR
    )

def engulfing_signal(df_slice):
    if len(df_slice) < 3:
        return None, df_slice.iloc[-1]

    previous = df_slice.iloc[-3]
    current = df_slice.iloc[-2]
    atr = float(current["atr"])

    if pd.isna(atr) or atr <= 0:
        return None, current

    previous_body = abs(float(previous["close"] - previous["open"]))
    current_body = abs(float(current["close"] - current["open"]))
    valid_body = (
        current_body >= previous_body
        and current_body >= atr * MIN_ENGULFING_BODY_ATR
    )

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
    bullish_ma_rejection = (
        (touched_ma5 and current["close"] > current["ma5"])
        or (touched_ma10 and current["close"] > current["ma10"])
    )
    bearish_ma_rejection = (
        (touched_ma5 and current["close"] < current["ma5"])
        or (touched_ma10 and current["close"] < current["ma10"])
    )

    if bullish_engulfing and bullish_ma_rejection:
        return "BUY", current
    if bearish_engulfing and bearish_ma_rejection:
        return "SELL", current
    return None, current

def continuation_signal(df_slice, active_positions):
    """Logika Continuation Signal sesuai file v2 Anda"""
    if len(active_positions) == 0:
        return None, df_slice.iloc[-1]
        
    direction = active_positions[0]["type"] # BUY atau SELL
    if len(active_positions) >= MAX_ENTRIES_PER_DIRECTION:
        return None, df_slice.iloc[-1]

    current = df_slice.iloc[-2]
    
    touched_ma5 = current["low"] <= current["ma5"] <= current["high"]
    touched_ma10 = current["low"] <= current["ma10"] <= current["high"]
    
    if direction == "BUY":
        rejection = (touched_ma5 and current["close"] > current["ma5"]) or (touched_ma10 and current["close"] > current["ma10"])
        if current["close"] > current["open"] and rejection:
            return "BUY", current
    elif direction == "SELL":
        rejection = (touched_ma5 and current["close"] < current["ma5"]) or (touched_ma10 and current["close"] < current["ma10"])
        if current["close"] < current["open"] and rejection:
            return "SELL", current
            
    return None, current

def calculate_sl_backtest(signal, candle, execution_price):
    buffer_distance = SL_BUFFER_POINTS * POINT_VALUE
    if signal == "BUY":
        reference = min(float(candle["low"]), float(candle["ma10"]))
        return min(reference - buffer_distance, execution_price - buffer_distance)
    else:
        reference = max(float(candle["high"]), float(candle["ma10"]))
        return max(reference + buffer_distance, execution_price + buffer_distance)

# ==============================================================================
# 3. ENGINE UTAMA BACKTEST (MENDUKUNG MULTI-ENTRY DAN REVERSE CLOSE)
# ==============================================================================
def run_backtest(csv_path):
    print(f"[-] Memuat data dari: {csv_path} ...")
    if not os.getenv("NO_FILE_CHECK") and not os.path.exists(csv_path):
        print(f"[!] Error: File tidak ditemukan di path tersebut. Periksa kembali lokasi filenya.")
        return

    kolom_mt5 = ['time', 'open', 'high', 'low', 'close', 'tick_volume', 'spread']
    
    # Membaca otomatis file CSV tanpa header milik Anda (UTF-16 dengan pemisah Koma)
    try:
        df = pd.read_csv(csv_path, header=None, names=kolom_mt5, encoding="utf-16", sep=",")
        if df.shape[1] <= 1 or pd.isna(df['close']).all():
            df = pd.read_csv(csv_path, header=None, names=kolom_mt5, encoding="utf-8", sep=",")
        if df.shape[1] <= 1 or pd.isna(df['close']).all():
            df = pd.read_csv(csv_path, header=None, names=kolom_mt5, encoding="utf-16", sep="\t")
    except Exception as e:
        print(f"[-] Percobaan membaca gagal ({e}), menggunakan format alternatif...")
        try:
            df = pd.read_csv(csv_path, header=None, names=kolom_mt5, encoding="utf-16", sep=",")
        except:
            df = pd.read_csv(csv_path, header=None, names=kolom_mt5, encoding="utf-8", sep=",")

    if df.shape[1] < 5 or pd.isna(df['close']).all():
        print("[!] Error: Gagal memproses struktur kolom CSV. Harap pastikan isi file sesuai format MT5.")
        return

    df["time"] = pd.to_datetime(df["time"])
    df = df.sort_values("time").reset_index(drop=True)

    # Pra-kalkulasi Indikator
    df["ma5"] = df["close"].rolling(5).mean()
    df["ma10"] = df["close"].rolling(10).mean()
    
    previous_close = df["close"].shift(1)
    true_range = pd.concat([
        df["high"] - df["low"],
        (df["high"] - previous_close).abs(),
        (df["low"] - previous_close).abs()
    ], axis=1).max(axis=1)
    df["atr"] = true_range.rolling(ATR_PERIOD).mean()

    start_idx = max(ATR_PERIOD, SIDEWAYS_LOOKBACK) + 5
    balance = INITIAL_BALANCE
    active_positions = []  # List untuk menampung multi-entry aktif
    trades_log = []          

    print(f"[-] Menjalankan simulasi dari {df['time'].iloc[start_idx]} hingga {df['time'].iloc[-1]}...")

    for i in range(start_idx, len(df)):
        current_candle = df.iloc[i]
        df_slice = df.iloc[:i+1] 

        # A. PERIKSA APAKAH ADA SENTUHAN STOP LOSS (SL) PADA SETIAP POSISI AKTIF
        still_active = []
        for pos in active_positions:
            pos_type = pos["type"]
            sl_level = pos["sl"]
            hit_sl = False

            if pos_type == "BUY" and current_candle["low"] <= sl_level:
                pnl = (sl_level - pos["open_price"]) * LOT * LOT_SIZE_VALUE
                balance += pnl
                trades_log.append({
                    "time_open": pos["time_open"], "time_close": current_candle["time"],
                    "type": "BUY", "status": "HIT_SL", "open": pos["open_price"],
                    "close": sl_level, "pnl": pnl, "balance": balance
                })
                hit_sl = True
            elif pos_type == "SELL" and current_candle["high"] >= sl_level:
                pnl = (pos["open_price"] - sl_level) * LOT * LOT_SIZE_VALUE
                balance += pnl
                trades_log.append({
                    "time_open": pos["time_open"], "time_close": current_candle["time"],
                    "type": "SELL", "status": "HIT_SL", "open": pos["open_price"],
                    "close": sl_level, "pnl": pnl, "balance": balance
                })
                hit_sl = True

            if not hit_sl:
                still_active.append(pos)
        active_positions = still_active

        # B. CEK EVALUASI SINYAL (Engulfing Utama dulu, kalau None cek Continuation)
        signal, signal_candle = engulfing_signal(df_slice)
        is_continuation = False
        
        if signal is None:
            signal, signal_candle = continuation_signal(df_slice, active_positions)
            if signal is not None:
                is_continuation = True

        if signal is not None:
            sideways = is_sideways(df_slice)
            if sideways:
                continue  # Dilewati jika pasar terdeteksi sideways

            desired_type = signal
            
            if desired_type == "BUY":
                execution_price = current_candle["open"] + (SPREAD_POINTS * POINT_VALUE)
            else:
                execution_price = current_candle["open"]

            # C. LOGIKA SUB-EKSEKUSI SINYAL
            # 1. Jika ada posisi aktif yang berlawanan arah -> REVERSE CLOSE ALL POSITIONS
            if len(active_positions) > 0 and active_positions[0]["type"] != desired_type:
                for pos in active_positions:
                    if pos["type"] == "BUY":
                        pnl = (execution_price - pos["open_price"]) * LOT * LOT_SIZE_VALUE
                    else:
                        close_price_sell = current_candle["open"] + (SPREAD_POINTS * POINT_VALUE)
                        pnl = (pos["open_price"] - close_price_sell) * LOT * LOT_SIZE_VALUE

                    balance += pnl
                    trades_log.append({
                        "time_open": pos["time_open"], "time_close": current_candle["time"],
                        "type": pos["type"], "status": "REVERSE_CLOSE", 
                        "open": pos["open_price"], "close": current_candle["open"], 
                        "pnl": pnl, "balance": balance
                    })
                active_positions = [] # Kosongkan semua posisi karena berbalik arah

            # 2. Batasi pembukaan posisi berdasarkan max entry per direction
            if len(active_positions) >= MAX_ENTRIES_PER_DIRECTION:
                continue
                
            # 3. Mencegah duplikasi entri pada candle yang sama untuk kelanjutan tren
            if is_continuation and any(pos["time_open"] == current_candle["time"] for pos in active_positions):
                continue

            # 4. Open Posisi Baru (Single maupun Multi-Layering)
            sl = calculate_sl_backtest(desired_type, signal_candle, execution_price)
            active_positions.append({
                "type": desired_type,
                "open_price": execution_price,
                "sl": sl,
                "time_open": current_candle["time"]
            })

    # ==============================================================================
    # 4. LAPORAN EVALUASI PERFORMA BACKTEST
    # ==============================================================================
    print("\n======================= BACKTEST RESULTS =======================")
    if not trades_log:
        print("Tidak ada trade yang tereksekusi selama periode data historis ini.")
        return

    df_trades = pd.DataFrame(trades_log)
    total_trades = len(df_trades)
    wins = df_trades[df_trades["pnl"] > 0]
    losses = df_trades[df_trades["pnl"] <= 0]
    
    win_rate = (len(wins) / total_trades) * 100 if total_trades > 0 else 0
    total_pnl = df_trades["pnl"].sum()

    print(f"Modal Awal          : ${INITIAL_BALANCE:,.2f}")
    print(f"Saldo Akhir         : ${balance:,.2f}")
    print(f"Total Net Profit    : ${total_pnl:,.2f}")
    print(f"Total Eksekusi Trade: {total_trades} kali")
    print(f"Win Rate            : {win_rate:.2f}% (Win: {len(wins)} | Loss: {len(losses)})")
    print(f"Profit Terbesar     : ${df_trades['pnl'].max():,.2f}")
    print(f"Loss Terbesar       : ${df_trades['pnl'].min():,.2f}")
    print("================================================================")
    
    print("\n[i] Rincian 10 Transaksi Terakhir:")
    print(df_trades[["time_close", "type", "status", "pnl", "balance"]].tail(10).to_string(index=False))

if __name__ == "__main__":
    target_csv = r"C:\Users\Alief Akbar Purnama\Downloads\XAUUSDmH1.csv"
    run_backtest(target_csv)