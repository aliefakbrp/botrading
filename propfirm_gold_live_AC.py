import MetaTrader5 as mt5
import pandas as pd
import time
from datetime import datetime

SYMBOL = "XAUUSDm"
TIMEFRAME = mt5.TIMEFRAME_M1
LOTS = 0.01
RR_RATIO = 3
STRUCTURE_LOOKBACK = 20
MAGIC_NUMBER = 202604
BUFFER_PIPS = 0.40

MAX_DAILY_LOSS_PCT = 1  # 🔥 1% daily loss

# ==========================================
# INIT
# ==========================================
def initialize_mt5():
    if not mt5.initialize():
        print("[-] Gagal koneksi ke MT5!")
        quit()
    print(f"[{datetime.now()}] Bot Aktif | {SYMBOL}")

# ==========================================
# DAILY LOSS TRACKER
# ==========================================
daily_start_balance = None
current_day = None

def check_daily_loss():
    global daily_start_balance, current_day
    
    acc = mt5.account_info()
    if acc is None:
        return False
    
    today = datetime.now().date()
    
    # reset tiap hari
    if current_day != today:
        current_day = today
        daily_start_balance = acc.balance
        print(f"[RESET] Balance harian: {daily_start_balance}")
    
    if daily_start_balance is None:
        return False
    
    loss_pct = (daily_start_balance - acc.equity) / daily_start_balance * 100
    
    if loss_pct >= MAX_DAILY_LOSS_PCT:
        print(f"[STOP] Daily loss {loss_pct:.2f}% tercapai")
        return True
    
    return False

# ==========================================
# ORDER CONTROL
# ==========================================
def cancel_all_pending():
    orders = mt5.orders_get(symbol=SYMBOL, magic=MAGIC_NUMBER)
    if orders:
        for order in orders:
            mt5.order_send({
                "action": mt5.TRADE_ACTION_REMOVE,
                "order": order.ticket
            })

def send_limit_order(order_type, price, sl, tp):
    return mt5.order_send({
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
    })

def has_open_position():
    positions = mt5.positions_get(symbol=SYMBOL)
    if not positions:
        return False
    positions = [p for p in positions if p.magic == MAGIC_NUMBER]
    return len(positions) > 0

# ==========================================
# DATA
# ==========================================
def get_ohlc(n=100):
    rates = mt5.copy_rates_from_pos(SYMBOL, TIMEFRAME, 0, n)
    if rates is None or len(rates) == 0:
        return pd.DataFrame()
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    return df

# ==========================================
# BE LOGIC
# ==========================================
def manage_sl_to_be():
    positions = mt5.positions_get(symbol=SYMBOL)
    if not positions:
        return

    positions = [p for p in positions if p.magic == MAGIC_NUMBER]

    for pos in positions:
        entry = pos.price_open
        sl = pos.sl
        tick = mt5.symbol_info_tick(SYMBOL)

        if pos.type == 0:  # BUY
            current = tick.bid
            risk = entry - sl
            profit = current - entry

            if profit >= risk and sl < entry:
                new_sl = entry + 0.2
                mt5.order_send({
                    "action": mt5.TRADE_ACTION_SLTP,
                    "position": pos.ticket,
                    "sl": round(new_sl, 2),
                    "tp": pos.tp
                })
                print(f"[BE+] BUY {pos.ticket}")

        elif pos.type == 1:  # SELL
            current = tick.ask
            risk = sl - entry
            profit = entry - current

            if profit >= risk and sl > entry:
                new_sl = entry - 0.2
                mt5.order_send({
                    "action": mt5.TRADE_ACTION_SLTP,
                    "position": pos.ticket,
                    "sl": round(new_sl, 2),
                    "tp": pos.tp
                })
                print(f"[BE+] SELL {pos.ticket}")

# ==========================================
# MAIN BOT
# ==========================================
def run_bot():
    last_processed_time = None

    while True:
        df = get_ohlc(100)
        if df.empty:
            time.sleep(1)
            continue

        # 🔥 STOP kalau daily loss kena
        if check_daily_loss():
            time.sleep(60)
            continue

        manage_sl_to_be()

        current_candle = df.iloc[-1]

        # ❗ cuma 1 posisi aktif
        if has_open_position():
            time.sleep(1)
            continue

        if current_candle['time'] != last_processed_time:
            window = df.iloc[-(STRUCTURE_LOOKBACK+1):-1]
            swing_high = window['high'].max()
            swing_low = window['low'].min()

            # BUY
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
                            print(f"[{datetime.now()}] BUY {entry}")
                            last_processed_time = current_candle['time']

            # SELL
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
                            print(f"[{datetime.now()}] SELL {entry}")
                            last_processed_time = current_candle['time']

        time.sleep(1)

# ==========================================
# RUN
# ==========================================
if __name__ == "__main__":
    initialize_mt5()
    try:
        run_bot()
    except KeyboardInterrupt:
        print("\n[!] Bot dihentikan.")
    finally:
        mt5.shutdown()