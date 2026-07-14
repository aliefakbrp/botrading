import MetaTrader5 as mt5
import pandas as pd
import time
from datetime import datetime

SYMBOL = "XAUUSDm"
# TIMEFRAME = mt5.TIMEFRAME_M1
TIMEFRAME = mt5.TIMEFRAME_M15
LOTS = 0.01
RR_RATIO = 3
STRUCTURE_LOOKBACK = 20
MAGIC_NUMBER = 202604
BUFFER_PIPS = 0.40

def initialize_mt5():
    if not mt5.initialize():
        print("[-] Gagal koneksi ke MT5!")
        quit()
    print(f"[{datetime.now()}] Bot Live Aktif | {SYMBOL} | Lot: {LOTS}")

def cancel_all_pending():
    orders = mt5.orders_get(symbol=SYMBOL, magic=MAGIC_NUMBER)
    if orders:
        for order in orders:
            request = {
                "action": mt5.TRADE_ACTION_REMOVE,
                "order": order.ticket
            }
            result = mt5.order_send(request)
            if result.retcode == mt5.TRADE_RETCODE_DONE:
                print(f"[!] Order lama {order.ticket} dicancel")

def send_limit_order(order_type, price, sl, tp):
    request = {
        "action": mt5.TRADE_ACTION_PENDING,
        "symbol": SYMBOL,
        "volume": LOTS,
        "type": order_type,
        "price": round(price, 2),
        "sl": round(sl, 2),
        "tp": round(tp, 2),
        "magic": MAGIC_NUMBER,
        "comment": "SMC_GOLD_BOT",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    return mt5.order_send(request)

def get_ohlc(n=100):
    rates = mt5.copy_rates_from_pos(SYMBOL, TIMEFRAME, 0, n)
    if rates is None or len(rates) == 0:
        return pd.DataFrame()
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    return df

def run_bot():
    last_processed_time = None

    while True:
        df = get_ohlc(100)
        if df.empty:
            time.sleep(1)
            continue

        current_candle = df.iloc[-1]

        if current_candle['time'] != last_processed_time:
            window = df.iloc[-(STRUCTURE_LOOKBACK+1):-1]
            swing_high = window['high'].max()
            swing_low = window['low'].min()

            if current_candle['close'] > swing_high:
                cancel_all_pending()

                ob_df = df.iloc[-15:-1][df['close'] < df['open']]
                if not ob_df.empty:
                    entry = ob_df.iloc[-1]['high']
                    sl = ob_df.iloc[-1]['low'] - BUFFER_PIPS
                    risk = entry - sl

                    if risk > 0.2:
                        tp = entry + (risk * RR_RATIO)
                        res = send_limit_order(mt5.ORDER_TYPE_BUY_LIMIT, entry, sl, tp)
                        if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                            print(f"[{datetime.now()}] BUY LIMIT {entry}")
                            last_processed_time = current_candle['time']

            elif current_candle['close'] < swing_low:
                cancel_all_pending()

                ob_df = df.iloc[-15:-1][df['close'] > df['open']]
                if not ob_df.empty:
                    entry = ob_df.iloc[-1]['low']
                    sl = ob_df.iloc[-1]['high'] + BUFFER_PIPS
                    risk = sl - entry

                    if risk > 0.2:
                        tp = entry - (risk * RR_RATIO)
                        res = send_limit_order(mt5.ORDER_TYPE_SELL_LIMIT, entry, sl, tp)
                        if res and res.retcode == mt5.TRADE_RETCODE_DONE:
                            print(f"[{datetime.now()}] SELL LIMIT {entry}")
                            last_processed_time = current_candle['time']

        time.sleep(1)

if __name__ == "__main__":
    initialize_mt5()
    try:
        run_bot()
    except KeyboardInterrupt:
        print("\n[!] Bot dihentikan.")
    finally:
        mt5.shutdown()