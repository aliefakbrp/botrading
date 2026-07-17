import MetaTrader5 as mt5
import pandas as pd
import numpy as np
from backtesting import Backtest, Strategy

# ==========================================
# PARAMETER (Berdasarkan file ma5_ma10_engulfing_h1_v2.py)
# ==========================================
SYMBOL = "XAUUSDm"
TIMEFRAME = mt5.TIMEFRAME_H1
LOT = 0.01
SL_BUFFER_POINTS = 50       
SIDEWAYS_LOOKBACK = 10
ATR_PERIOD = 14
MIN_TREND_EFFICIENCY = 0.30
MIN_MA10_SLOPE_ATR = 0.50
MIN_ENGULFING_BODY_ATR = 0.10
MAX_ENTRIES_PER_DIRECTION = 3
TRAILING_START_POINTS = 50   
TRAILING_DISTANCE_POINTS = 50 

# ==========================================
# 1. AMBIL DATA HISTORIS DARI MT5
# ==========================================
def fetch_data(symbol, timeframe, count=5000):
    if not mt5.initialize():
        print("Gagal inisialisasi MT5")
        return None
    mt5.symbol_select(symbol, True)
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, count)
    mt5.shutdown()
    
    if rates is None:
        return None
        
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    df.set_index('time', inplace=True)
    df.rename(columns={'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close', 'tick_volume': 'Volume'}, inplace=True)
    return df

# ==========================================
# 2. LOGIKA STRATEGI (SAMA PERSIS DENGAN BOT)
# ==========================================
class MAEngulfingV2(Strategy):
    def init(self):
        close = pd.Series(self.data.Close)
        high = pd.Series(self.data.High)
        low = pd.Series(self.data.Low)
        
        # Indikator MA
        self.ma5 = self.I(lambda x: x.rolling(5).mean(), close)
        self.ma10 = self.I(lambda x: x.rolling(10).mean(), close)
        
        # Indikator ATR
        prev_close = close.shift(1)
        tr = pd.concat([high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
        self.atr = self.I(lambda x: x.rolling(ATR_PERIOD).mean(), tr)
        
        # Deteksi Point Size (Untuk Konversi 50 Points)
        sample_diff = np.abs(np.diff(close.values[:100]))
        min_diff = np.min(sample_diff[sample_diff > 0])
        self.point_size = min_diff if min_diff > 0 else 0.01

    def next(self):
        if len(self.data) < max(ATR_PERIOD, SIDEWAYS_LOOKBACK) + 3:
            return
            
        # Index [-2] adalah candle yang baru saja SELESAI (closed)
        # Index [-3] adalah candle sebelumnya
        curr = -2
        prev = -3
        
        c_open = self.data.Open[curr]
        c_close = self.data.Close[curr]
        c_high = self.data.High[curr]
        c_low = self.data.Low[curr]
        c_ma5 = self.ma5[curr]
        c_ma10 = self.ma10[curr]
        c_atr = self.atr[curr]
        
        p_open = self.data.Open[prev]
        p_close = self.data.Close[prev]
        
        current_price = self.data.Close[-1] # Harga live saat ini (pembukaan bar baru)
        
        # --- 1. MANAGE TRAILING STOP ---
        t_start = TRAILING_START_POINTS * self.point_size
        t_dist = TRAILING_DISTANCE_POINTS * self.point_size
        
        for trade in self.trades:
            if trade.is_long:
                if current_price - trade.entry_price >= t_start:
                    new_sl = current_price - t_dist
                    if trade.sl is None or new_sl > trade.sl:
                        trade.sl = new_sl
            elif trade.is_short:
                if trade.entry_price - current_price >= t_start:
                    new_sl = current_price + t_dist
                    if trade.sl is None or new_sl < trade.sl:
                        trade.sl = new_sl

        # --- 2. CEK SIDEWAYS ---
        lb_close = pd.Series(self.data.Close).iloc[-SIDEWAYS_LOOKBACK-1:-1]
        lb_ma10 = pd.Series(self.ma10).iloc[-SIDEWAYS_LOOKBACK-1:-1]
        
        total_movement = lb_close.diff().abs().sum()
        net_movement = abs(lb_close.iloc[-1] - lb_close.iloc[0])
        efficiency = net_movement / total_movement if total_movement > 0 else 0.0
        ma10_slope = abs(lb_ma10.iloc[-1] - lb_ma10.iloc[0])
        
        is_sideways = (efficiency < MIN_TREND_EFFICIENCY and ma10_slope < (c_atr * MIN_MA10_SLOPE_ATR))
        
        # --- 3. SINYAL ENGULFING (Fungsi engulfing_signal) ---
        p_body = abs(p_close - p_open)
        c_body = abs(c_close - c_open)
        valid_body = (c_body >= p_body and c_body >= (c_atr * MIN_ENGULFING_BODY_ATR))
        
        bullish_engulfing = (p_close < p_open and c_close > c_open and c_open <= p_close and c_close >= p_open and valid_body)
        bearish_engulfing = (p_close > p_open and c_close < c_open and c_open >= p_close and c_close <= p_open and valid_body)
        
        touched_ma5 = (c_low <= c_ma5 <= c_high)
        touched_ma10 = (c_low <= c_ma10 <= c_high)
        
        bullish_ma_rejection = ((touched_ma5 and c_close > c_ma5) or (touched_ma10 and c_close > c_ma10))
        bearish_ma_rejection = ((touched_ma5 and c_close < c_ma5) or (touched_ma10 and c_close < c_ma10))
        
        signal = None
        if bullish_engulfing and bullish_ma_rejection:
            signal = "BUY"
        elif bearish_engulfing and bearish_ma_rejection:
            signal = "SELL"
            
        # --- 4. SINYAL CONTINUATION ---
        has_buy = any(t.is_long for t in self.trades)
        has_sell = any(t.is_short for t in self.trades)
        
        if signal is None:
            if has_buy and c_close > c_open and c_close > p_close and c_close > c_ma5:
                signal = "BUY"
            elif has_sell and c_close < c_open and c_close < p_close and c_close < c_ma5:
                signal = "SELL"
                
        if signal is None:
            return

        # --- 5. EKSEKUSI (Strict Mode: No Hedging / No Reverse) ---
        buy_trades = [t for t in self.trades if t.is_long]
        sell_trades = [t for t in self.trades if t.is_short]
        
        buffer_dist = SL_BUFFER_POINTS * self.point_size
        
        if signal == "BUY":
            # LOGIKA KUNCI: Abaikan sinyal jika ada posisi SELL (Tidak boleh buka berlawanan!)
            if len(sell_trades) > 0:
                return
            if is_sideways and not has_buy: 
                return
            if len(buy_trades) >= MAX_ENTRIES_PER_DIRECTION:
                return
                
            # SL = min(Low, MA10) - Buffer
            ref_low = min(float(c_low), float(c_ma10))
            sl_price = min(ref_low - buffer_dist, current_price - buffer_dist)
            
            self.buy(size=1, sl=sl_price)
            
        elif signal == "SELL":
            # LOGIKA KUNCI: Abaikan sinyal jika ada posisi BUY (Tidak boleh buka berlawanan!)
            if len(buy_trades) > 0:
                return
            if is_sideways and not has_sell:
                return
            if len(sell_trades) >= MAX_ENTRIES_PER_DIRECTION:
                return
                
            # SL = max(High, MA10) + Buffer
            ref_high = max(float(c_high), float(c_ma10))
            sl_price = max(ref_high + buffer_dist, current_price + buffer_dist)
            
            self.sell(size=1, sl=sl_price)

# ==========================================
# 3. RUN BACKTEST
# ==========================================
if __name__ == "__main__":
    print(f"Mendownload data {SYMBOL}...")
    data = fetch_data(SYMBOL, TIMEFRAME, count=1000)
    
    if data is not None:
        print("Memulai simulasi V2 murni...")
        # Modal 1000 USD (Sesuai saldomu), Leverage 1:500
        bt = Backtest(data, MAEngulfingV2, cash=1000, margin=1/500, hedging=False)
        stats = bt.run()
        print("\n=== HASIL BACKTEST ===")
        print(stats)
        bt.plot()
    else:
        print("Gagal mengambil data, pastikan MT5 terbuka.")