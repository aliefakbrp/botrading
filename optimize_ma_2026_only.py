import os
import time
import numpy as np
import pandas as pd
import numba as nb

# ==============================================================================
# 1. KONFIGURASI PARAMETER STRATEGI (TAHUN 2026 S/D SEKARANG + AUTO-STOP MC)
# ==============================================================================
SYMBOL = "XAUUSDm"
LOT = 0.01
SL_BUFFER_POINTS = 50
SIDEWAYS_LOOKBACK = 10
ATR_PERIOD = 14
MIN_TREND_EFFICIENCY = 0.30
MIN_MA_SLOPE_ATR = 0.50
MIN_ENGULFING_BODY_ATR = 0.10
MAX_ENTRIES_PER_DIRECTION = 3

INITIAL_BALANCE = 100.0   # Modal Awal (USD)
POINT_VALUE = 0.01          # 1 point = 0.01 (Emas)
LOT_SIZE_VALUE = 100        # Contract size standar emas
SPREAD_POINTS = 20          # Spread 20 points (2 pips)

START_DATE = "2026-01-01 00:00:00"

MA_MIN = 1
MA_MAX = 100

DATA_PATHS = {
    "M5": r"C:\Users\Alief Akbar Purnama\Downloads\XAUUSDmM5-28jun18.csv",
    "M15": r"C:\Users\Alief Akbar Purnama\Downloads\XAUUSDmM15-28jun18.csv",
    "M30": r"C:\Users\Alief Akbar Purnama\Downloads\XAUUSDmM30-28jun18.csv",
    "H1": r"C:\Users\Alief Akbar Purnama\Downloads\XAUUSDmH1-28jun18.csv",
}

# ==============================================================================
# 2. NUMBA ENGINE (AUTO-STOP KETIKA BALANCE <= 0)
# ==============================================================================
@nb.njit(parallel=True, fastmath=True)
def run_all_ma_2026_autostop(
    open_arr, high_arr, low_arr, close_arr, atr_arr, all_mas,
    start_idx,
    lot, lot_size_value, spread_points, point_value,
    sl_buffer_points, sideways_lookback,
    min_trend_efficiency, min_ma_slope_atr, min_engulfing_body_atr,
    max_entries, initial_balance
):
    total_combinations = (MA_MAX - MA_MIN + 1) * (MA_MAX - MA_MIN + 1)
    # Output: [ma_fast, ma_slow, final_balance, total_trades, win_trades, loss_trades, is_mc]
    results = np.zeros((total_combinations, 7), dtype=np.float64)
    
    spread_dist = spread_points * point_value
    sl_buffer_dist = sl_buffer_points * point_value
    multiplier = lot * lot_size_value
    n = len(open_arr)
    
    for idx in nb.prange(total_combinations):
        ma_fast_val = (idx // (MA_MAX - MA_MIN + 1)) + MA_MIN
        ma_slow_val = (idx % (MA_MAX - MA_MIN + 1)) + MA_MIN
        
        ma_fast = all_mas[ma_fast_val]
        ma_slow = all_mas[ma_slow_val]
        
        balance = initial_balance
        pos_types = np.zeros(max_entries, dtype=np.int32)
        pos_opens = np.zeros(max_entries, dtype=np.float64)
        pos_sls = np.zeros(max_entries, dtype=np.float64)
        pos_bar_opens = np.zeros(max_entries, dtype=np.int32)
        pos_count = 0
        
        total_trades = 0
        win_trades = 0
        loss_trades = 0
        is_mc = 0.0
        
        for i in range(start_idx, n):
            if balance <= 0.0:
                balance = 0.0
                is_mc = 1.0
                break
                
            cur_open = open_arr[i]
            cur_high = high_arr[i]
            cur_low = low_arr[i]
            cur_close = close_arr[i]
            
            # A. Cek SL
            still_count = 0
            for p in range(pos_count):
                ptype = pos_types[p]
                psl = pos_sls[p]
                popen = pos_opens[p]
                hit = False
                
                if ptype == 1 and cur_low <= psl:
                    pnl = (psl - popen) * multiplier
                    balance += pnl
                    total_trades += 1
                    if pnl > 0: win_trades += 1
                    else: loss_trades += 1
                    hit = True
                elif ptype == -1 and cur_high >= psl:
                    pnl = (popen - psl) * multiplier
                    balance += pnl
                    total_trades += 1
                    if pnl > 0: win_trades += 1
                    else: loss_trades += 1
                    hit = True
                    
                if not hit:
                    pos_types[still_count] = ptype
                    pos_opens[still_count] = popen
                    pos_sls[still_count] = psl
                    pos_bar_opens[still_count] = pos_bar_opens[p]
                    still_count += 1
            pos_count = still_count
            
            if balance <= 0.0:
                balance = 0.0
                is_mc = 1.0
                break
            
            # B. Cek Sinyal
            prev_open = open_arr[i-2]
            prev_close = close_arr[i-2]
            c_open = open_arr[i-1]
            c_high = high_arr[i-1]
            c_low = low_arr[i-1]
            c_close = close_arr[i-1]
            c_atr = atr_arr[i-1]
            c_ma_fast = ma_fast[i-1]
            c_ma_slow = ma_slow[i-1]
            
            signal = 0
            is_continuation = False
            
            if c_atr > 0 and not np.isnan(c_atr):
                prev_body = abs(prev_close - prev_open)
                cur_body = abs(c_close - c_open)
                valid_body = (cur_body >= prev_body) and (cur_body >= c_atr * min_engulfing_body_atr)
                
                bullish_engulfing = (prev_close < prev_open) and (c_close > c_open) and (c_open <= prev_close) and (c_close >= prev_open) and valid_body
                bearish_engulfing = (prev_close > prev_open) and (c_close < c_open) and (c_open >= prev_close) and (c_close <= prev_open) and valid_body
                
                touched_ma_fast = (c_low <= c_ma_fast) and (c_ma_fast <= c_high)
                touched_ma_slow = (c_low <= c_ma_slow) and (c_ma_slow <= c_high)
                
                bullish_ma_rejection = (touched_ma_fast and c_close > c_ma_fast) or (touched_ma_slow and c_close > c_ma_slow)
                bearish_ma_rejection = (touched_ma_fast and c_close < c_ma_fast) or (touched_ma_slow and c_close < c_ma_slow)
                
                if bullish_engulfing and bullish_ma_rejection:
                    signal = 1
                elif bearish_engulfing and bearish_ma_rejection:
                    signal = -1
                else:
                    if pos_count > 0 and pos_count < max_entries:
                        direction = pos_types[0]
                        if direction == 1:
                            rejection = (touched_ma_fast and c_close > c_ma_fast) or (touched_ma_slow and c_close > c_ma_slow)
                            if c_close > c_open and rejection:
                                signal = 1
                                is_continuation = True
                        elif direction == -1:
                            rejection = (touched_ma_fast and c_close < c_ma_fast) or (touched_ma_slow and c_close < c_ma_slow)
                            if c_close < c_open and rejection:
                                signal = -1
                                is_continuation = True
                                
            if signal != 0:
                total_movement = 0.0
                for k in range(i - sideways_lookback + 1, i):
                    total_movement += abs(close_arr[k] - close_arr[k-1])
                net_movement = abs(close_arr[i-1] - close_arr[i - sideways_lookback])
                efficiency = net_movement / total_movement if total_movement > 0 else 0.0
                ma_slope = abs(ma_slow[i-1] - ma_slow[i - sideways_lookback])
                
                sideways = (efficiency < min_trend_efficiency) and (ma_slope < c_atr * min_ma_slope_atr)
                if sideways:
                    continue
                    
                desired_type = signal
                if desired_type == 1:
                    exec_price = cur_open + spread_dist
                else:
                    exec_price = cur_open
                    
                # C. Reverse Close
                if pos_count > 0 and pos_types[0] != desired_type:
                    for p in range(pos_count):
                        ptype = pos_types[p]
                        popen = pos_opens[p]
                        if ptype == 1:
                            pnl = (exec_price - popen) * multiplier
                        else:
                            close_price_sell = cur_open + spread_dist
                            pnl = (popen - close_price_sell) * multiplier
                        balance += pnl
                        total_trades += 1
                        if pnl > 0: win_trades += 1
                        else: loss_trades += 1
                    pos_count = 0
                    
                    if balance <= 0.0:
                        balance = 0.0
                        is_mc = 1.0
                        break
                        
                if pos_count >= max_entries:
                    continue
                    
                if is_continuation:
                    already_opened = False
                    for p in range(pos_count):
                        if pos_bar_opens[p] == i:
                            already_opened = True
                            break
                    if already_opened:
                        continue
                        
                # D. Hitung SL
                if desired_type == 1:
                    ref = min(c_low, c_ma_slow)
                    sl = min(ref - sl_buffer_dist, exec_price - sl_buffer_dist)
                else:
                    ref = max(c_high, c_ma_slow)
                    sl = max(ref + sl_buffer_dist, exec_price + sl_buffer_dist)
                    
                pos_types[pos_count] = desired_type
                pos_opens[pos_count] = exec_price
                pos_sls[pos_count] = sl
                pos_bar_opens[pos_count] = i
                pos_count += 1
                
        results[idx, 0] = ma_fast_val
        results[idx, 1] = ma_slow_val
        results[idx, 2] = balance
        results[idx, 3] = total_trades
        results[idx, 4] = win_trades
        results[idx, 5] = loss_trades
        results[idx, 6] = is_mc
        
    return results

def load_and_prepare_2026(csv_path, start_date=START_DATE):
    kolom_mt5 = ['time', 'open', 'high', 'low', 'close', 'tick_volume', 'spread']
    try:
        df = pd.read_csv(csv_path, header=None, names=kolom_mt5, encoding="utf-16", sep=",")
        if df.shape[1] <= 1 or pd.isna(df['close']).all():
            df = pd.read_csv(csv_path, header=None, names=kolom_mt5, encoding="utf-8", sep=",")
        if df.shape[1] <= 1 or pd.isna(df['close']).all():
            df = pd.read_csv(csv_path, header=None, names=kolom_mt5, encoding="utf-16", sep="\t")
    except Exception:
        try:
            df = pd.read_csv(csv_path, header=None, names=kolom_mt5, encoding="utf-16", sep=",")
        except:
            df = pd.read_csv(csv_path, header=None, names=kolom_mt5, encoding="utf-8", sep=",")

    df["time"] = pd.to_datetime(df["time"])
    df = df.sort_values("time").reset_index(drop=True)

    previous_close = df["close"].shift(1)
    true_range = pd.concat([
        df["high"] - df["low"],
        (df["high"] - previous_close).abs(),
        (df["low"] - previous_close).abs()
    ], axis=1).max(axis=1)
    df["atr"] = true_range.rolling(ATR_PERIOD).mean()

    n = len(df)
    close_vals = df["close"].values
    all_mas = np.zeros((MA_MAX + 1, n), dtype=np.float64)
    cumsum = np.cumsum(np.insert(close_vals, 0, 0))
    for period in range(1, MA_MAX + 1):
        all_mas[period, period - 1:] = (cumsum[period:] - cumsum[:-period]) / period
        all_mas[period, :period - 1] = np.nan

    idx_2026 = df[df["time"] >= start_date].index[0]
    return df, all_mas, idx_2026

def optimize_2026_timeframes():
    print("=" * 95)
    print(" " * 18 + f"MA 1-100 OPTIMIZER TAHUN 2026 (1 JAN 2026 - SEKARANG)")
    print(" " * 15 + "Modal Awal: $100 | Proteksi Auto-Stop Margin Call Aktif")
    print("=" * 95)
    
    summary = {}
    for tf_name, csv_path in DATA_PATHS.items():
        if not os.path.exists(csv_path):
            continue
            
        print(f"\n[{tf_name}] Memuat data...")
        df, all_mas, start_idx = load_and_prepare_2026(csv_path)
        print(f"[-] Data 2026: {df['time'].iloc[start_idx]} s/d {df['time'].iloc[-1]} ({len(df)-start_idx:,} candle)")
        print(f"[-] Menjalankan 10.000 kombinasi MA...")
        
        t0 = time.time()
        raw = run_all_ma_2026_autostop(
            df["open"].values, df["high"].values, df["low"].values, df["close"].values,
            df["atr"].values, all_mas, start_idx,
            LOT, LOT_SIZE_VALUE, SPREAD_POINTS, POINT_VALUE,
            SL_BUFFER_POINTS, SIDEWAYS_LOOKBACK,
            MIN_TREND_EFFICIENCY, MIN_MA_SLOPE_ATR, MIN_ENGULFING_BODY_ATR,
            MAX_ENTRIES_PER_DIRECTION, INITIAL_BALANCE
        )
        t_sim = time.time() - t0
        print(f"[-] Selesai simulasi dalam {t_sim:.2f} detik!")
        
        df_res = pd.DataFrame(raw, columns=["MA_Fast", "MA_Slow", "Final_Balance", "Total_Trades", "Win_Trades", "Loss_Trades", "Is_MC"])
        df_res["MA_Fast"] = df_res["MA_Fast"].astype(int)
        df_res["MA_Slow"] = df_res["MA_Slow"].astype(int)
        df_res["Total_Trades"] = df_res["Total_Trades"].astype(int)
        df_res["Win_Trades"] = df_res["Win_Trades"].astype(int)
        df_res["Loss_Trades"] = df_res["Loss_Trades"].astype(int)
        df_res["Net_Profit"] = df_res["Final_Balance"] - INITIAL_BALANCE
        df_res["Win_Rate_%"] = np.where(df_res["Total_Trades"] > 0, (df_res["Win_Trades"] / df_res["Total_Trades"]) * 100, 0.0)
        df_res["Status"] = np.where(df_res["Is_MC"] == 1.0, "MARGIN CALL ($0)", "SURVIVED (PROFIT)")
        
        # Urutkan berdasarkan Saldo Akhir Tertinggi
        df_res_sorted = df_res.sort_values(by="Final_Balance", ascending=False).reset_index(drop=True)
        mc_count = (df_res_sorted["Is_MC"] == 1.0).sum()
        survivor_count = len(df_res_sorted) - mc_count
        print(f"[-] Statistik: {survivor_count:,} kombinasi SELAMAT ({survivor_count/100:.1f}%) | {mc_count:,} kombinasi MC ({mc_count/100:.1f}%)")
        
        top20 = df_res_sorted.head(20).copy()
        top20.index = range(1, 21)
        top20.index.name = "Rank"
        summary[tf_name] = top20
        
        output_top20_csv = f"top20_ma_{tf_name.lower()}_2026.csv"
        output_all_csv = f"all_combinations_{tf_name.lower()}_2026.csv"
        top20.to_csv(output_top20_csv)
        df_res_sorted.to_csv(output_all_csv, index=False)
        print(f"[-] Hasil disimpan ke: {output_top20_csv} & {output_all_csv}")
        
        print(f"\n{'='*25} TOP 20 MA [2026 S/D SEKARANG - {tf_name}] {'='*25}")
        display_cols = ["MA_Fast", "MA_Slow", "Final_Balance", "Net_Profit", "Total_Trades", "Win_Rate_%", "Win_Trades", "Loss_Trades", "Status"]
        formatted_df = top20[display_cols].copy()
        formatted_df["Final_Balance"] = formatted_df["Final_Balance"].map(lambda x: f"${x:,.2f}")
        formatted_df["Net_Profit"] = formatted_df["Net_Profit"].map(lambda x: f"${x:,.2f}")
        formatted_df["Win_Rate_%"] = formatted_df["Win_Rate_%"].map(lambda x: f"{x:.2f}%")
        print(formatted_df.to_string())
        print("=" * 95)

    print("\n" + "#" * 95)
    print(" " * 20 + "RINGKASAN PARAMETER TERBAIK KHUSUS TAHUN 2026 (MODAL $100)")
    print("#" * 95)
    for tf_name, top_df in summary.items():
        best = top_df.iloc[0]
        print(f"Timeframe {tf_name:<4} -> MA Fast: {int(best['MA_Fast']):<3} | MA Slow: {int(best['MA_Slow']):<3} | Saldo Akhir: ${best['Final_Balance']:,.2f} | Net Profit: ${best['Net_Profit']:,.2f} | Win Rate: {best['Win_Rate_%']:.2f}% | Trades: {int(best['Total_Trades'])}")
    print("#" * 95)

if __name__ == "__main__":
    optimize_2026_timeframes()
