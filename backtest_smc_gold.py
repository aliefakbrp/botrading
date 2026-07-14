import MetaTrader5 as mt5
import pandas as pd
import numpy as np

# ==========================================
# 1. KONFIGURASI BACKTEST
# ==========================================
SYMBOL = "XAUUSDx"      
TIMEFRAME = mt5.TIMEFRAME_M1
LOOKBACK_DATA = 50000   
INITIAL_BALANCE = 1000  
LOT_SIZE = 0.01         
RR_RATIO = 3            
STRUCTURE_LOOKBACK = 20 
SPREAD_ADJUST = 0.40    

# 0.01 lot di Gold = $1 per $1 pergerakan harga
RISK_USD_PER_POINT = 1 

def get_historical_data():
    if not mt5.initialize():
        print("[-] Gagal koneksi ke MT5!")
        return None
    
    print(f"[*] Mengambil {LOOKBACK_DATA} data candle {SYMBOL}...")
    rates = mt5.copy_rates_from_pos(SYMBOL, TIMEFRAME, 0, LOOKBACK_DATA)
    mt5.shutdown()
    
    if rates is None or len(rates) == 0:
        print("[-] Data kosong! Pastikan Chart Gold M1 di MT5 sudah terdownload.")
        return None
    
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    return df

def run_backtest_dollar():
    df = get_historical_data()
    if df is None: return

    current_balance = INITIAL_BALANCE
    trade_log = []
    
    print("[*] Simulasi dimulai... Menghitung profit dalam USD...")

    for i in range(STRUCTURE_LOOKBACK + 5, len(df) - 100):
        window = df.iloc[i-STRUCTURE_LOOKBACK:i]
        swing_high = window['high'].max()
        swing_low = window['low'].min()
        current_candle = df.iloc[i]
        
        # --- LOGIKA BUY (BOS UP) ---
        if current_candle['close'] > swing_high:
            ob_candidates = df.iloc[i-15:i][df.iloc[i-15:i]['close'] < df.iloc[i-15:i]['open']]
            if not ob_candidates.empty:
                entry_p = round(ob_candidates.iloc[-1]['high'], 2)
                sl_p = round(ob_candidates.iloc[-1]['low'] - SPREAD_ADJUST, 2)
                
                risk_dist = entry_p - sl_p
                if risk_dist > 0.2: 
                    tp_p = round(entry_p + (risk_dist * RR_RATIO), 2)
                    
                    for j in range(i+1, len(df)):
                        future = df.iloc[j]
                        if future['low'] <= sl_p: # LOSS
                            loss_amount = round(risk_dist * RISK_USD_PER_POINT, 2)
                            current_balance -= loss_amount
                            trade_log.append({
                                'Waktu': current_candle['time'], 'Tipe': 'BUY', 
                                'Entry': entry_p, 'SL': sl_p, 'TP': tp_p, 
                                'Hasil': 'LOSS', 'Profit_USD': -loss_amount
                            })
                            break
                        if future['high'] >= tp_p: # WIN
                            win_amount = round((risk_dist * RR_RATIO) * RISK_USD_PER_POINT, 2)
                            current_balance += win_amount
                            trade_log.append({
                                'Waktu': current_candle['time'], 'Tipe': 'BUY', 
                                'Entry': entry_p, 'SL': sl_p, 'TP': tp_p, 
                                'Hasil': 'WIN', 'Profit_USD': win_amount
                            })
                            break

        # --- LOGIKA SELL (BOS DOWN) ---
        elif current_candle['close'] < swing_low:
            ob_candidates = df.iloc[i-15:i][df.iloc[i-15:i]['close'] > df.iloc[i-15:i]['open']]
            if not ob_candidates.empty:
                entry_p = round(ob_candidates.iloc[-1]['low'], 2)
                sl_p = round(ob_candidates.iloc[-1]['high'] + SPREAD_ADJUST, 2)
                
                risk_dist = sl_p - entry_p
                if risk_dist > 0.2:
                    tp_p = round(entry_p - (risk_dist * RR_RATIO), 2)
                    
                    for j in range(i+1, len(df)):
                        future = df.iloc[j]
                        if future['high'] >= sl_p: # LOSS
                            loss_amount = round(risk_dist * RISK_USD_PER_POINT, 2)
                            current_balance -= loss_amount
                            trade_log.append({
                                'Waktu': current_candle['time'], 'Tipe': 'SELL', 
                                'Entry': entry_p, 'SL': sl_p, 'TP': tp_p, 
                                'Hasil': 'LOSS', 'Profit_USD': -loss_amount
                            })
                            break
                        if future['low'] <= tp_p: # WIN
                            win_amount = round((risk_dist * RR_RATIO) * RISK_USD_PER_POINT, 2)
                            current_balance += win_amount
                            trade_log.append({
                                'Waktu': current_candle['time'], 'Tipe': 'SELL', 
                                'Entry': entry_p, 'SL': sl_p, 'TP': tp_p, 
                                'Hasil': 'WIN', 'Profit_USD': win_amount
                            })
                            break

    # ==========================================
    # 4. HASIL AKHIR
    # ==========================================
    if not trade_log:
        print("[-] Tidak ada trade terdeteksi.")
        return

    history_df = pd.DataFrame(trade_log)
    # Memastikan format waktu enak dibaca di Excel
    history_df['Waktu'] = history_df['Waktu'].dt.strftime('%Y-%m-%d %H:%M')
    history_df.to_csv("history_backtest_gold.csv", index=False)
    
    total_trades = len(history_df)
    total_win = len(history_df[history_df['Hasil'] == 'WIN'])
    total_loss = len(history_df[history_df['Hasil'] == 'LOSS'])
    win_rate = (total_win / total_trades) * 100
    total_profit = round(history_df['Profit_USD'].sum(), 2)

    print("\n" + "="*40)
    print(f" REPORT BACKTEST GOLD (FIXED 0.01 LOT)")
    print("="*40)
    print(f"Saldo Awal       : ${INITIAL_BALANCE}")
    print(f"Total Trade      : {total_trades}")
    print(f"Win / Loss       : {total_win} / {total_loss}")
    print(f"Win Rate         : {win_rate:.2f}%")
    print(f"Total Profit/Loss: ${total_profit:.2f}")
    print(f"Saldo Akhir      : ${round(INITIAL_BALANCE + total_profit, 2)}")
    print("="*40)
    print("[+] Detail trade disimpan ke: history_backtest_gold.csv")

if __name__ == "__main__":
    run_backtest_dollar()