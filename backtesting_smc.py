import MetaTrader5 as mt5
import numpy as np
import pandas as pd
from backtesting import Backtest, Strategy

# ==========================================
# 1. TARIK DATA HISTORIS DARI MT5
# ==========================================
SYMBOL = "XAUUSDm"  # Ganti sesuai simbol di MT5 kamu (misal: XAUUSD atau XAUUSDm)
TIMEFRAME = mt5.TIMEFRAME_M30
N_CANDLES = 5000  # Jumlah candle yang diuji


def get_historical_data():
    if not mt5.initialize():
        print(
            "[-] Gagal terhubung ke MT5. Pastikan aplikasi MT5 sedang terbuka!"
        )
        quit()

    print(f"[+] Terhubung ke MT5. Mengunduh data {SYMBOL}...")
    rates = mt5.copy_rates_from_pos(SYMBOL, TIMEFRAME, 0, N_CANDLES)
    mt5.shutdown()

    if rates is None or len(rates) == 0:
        print(f"[-] Data {SYMBOL} kosong! Cek nama simbol di Market Watch MT5.")
        quit()

    data_frame = pd.DataFrame(rates)
    data_frame["time"] = pd.to_datetime(data_frame["time"], unit="s")

    # Ubah nama kolom sesuai standar backtesting.py (Wajib Kapital di awal)
    data_frame = data_frame.rename(
        columns={
            "open": "Open",
            "high": "High",
            "low": "Low",
            "close": "Close",
            "tick_volume": "Volume",
        }
    )
    data_frame.set_index("time", inplace=True)
    data_frame = data_frame.dropna()

    print(f"[+] Berhasil memuat {len(data_frame)} candle historis.")
    return data_frame


# ==========================================
# 2. FUNGSI INDIKATOR SMA
# ==========================================
def SMA(values, n):
    return pd.Series(values).rolling(n).mean().values


# ==========================================
# 3. STRATEGI BACKTEST
# ==========================================
class RobustMAStrategy(Strategy):
    fast_period = 5
    slow_period = 10
    sl_pips = 100
    tp_pips = 200

    def init(self):
        price = self.data.Close
        self.ma_fast = self.I(SMA, price, self.fast_period)
        self.ma_slow = self.I(SMA, price, self.slow_period)

    def next(self):
        if np.isnan(self.ma_slow[-1]) or np.isnan(self.ma_slow[-2]):
            return

        fast_now = self.ma_fast[-1]
        fast_prev = self.ma_fast[-2]
        slow_now = self.ma_slow[-1]
        slow_prev = self.ma_slow[-2]

        bullish_cross = (fast_prev <= slow_prev) and (fast_now > slow_now)
        bearish_cross = (fast_prev >= slow_prev) and (fast_now < slow_now)

        point = 0.01
        sl_dist = self.sl_pips * point
        tp_dist = self.tp_pips * point
        current_close = self.data.Close[-1]

        if not self.position:
            # Gunakan size 0.95 (95% porsi equity) agar order tidak tertolak margin
            if bullish_cross:
                self.buy(
                    sl=current_close - sl_dist,
                    tp=current_close + tp_dist,
                    size=0.95,
                )
            elif bearish_cross:
                self.sell(
                    sl=current_close + sl_dist,
                    tp=current_close - tp_dist,
                    size=0.95,
                )


# ==========================================
# 4. RUN BACKTEST
# ==========================================
if __name__ == "__main__":
    # Tarik data dan simpan ke variabel 'df'
    df = get_historical_data()

    # Jalankan simulasi
    bt = Backtest(
        df,
        RobustMAStrategy,
        cash=10000,  # Modal awal $10.000 agar cukup beli emas
        margin=1 / 100,  # Leverage 1:100
        commission=0.0002,
        exclusive_orders=True,
    )

    stats = bt.run()
    print("\n================ HASIL BACKTEST ================")
    print(stats)
    print("================================================")

    # Tampilkan grafik
    bt.plot()