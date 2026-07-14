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

# 🔥 CONFIG PROP FIRM
COMMISSION_BUFFER = 0.5
TRAIL_DISTANCE = 0.5
PARTIAL_CLOSE_RATIO = 0.5
MAX_SPREAD = 0.5

MAX_DAILY_LOSS_PCT = 1
MAX_TRADES_PER_DAY = 5
TRADING_START = 13
TRADING_END = 23

daily_start_balance = None
current_day = None
trades_today = 0


def initialize_mt5():
    if not mt5.initialize():
        print("[-] Gagal koneksi ke MT5!")
        quit()
    print(f"[{datetime.now()}] Bot Aktif | {SYMBOL} | Lot: {LOTS}")


def check_daily_loss():
    global daily_start_balance, current_day, trades_today

    acc = mt5.account_info()
    if acc is None:
        return False

    today = datetime.now().date()

    if current_day != today:
        current_day = today
        daily_start_balance = acc.balance
        trades_today = 0
        print(f"[RESET] Balance: {daily_start_balance}")

    loss_pct = (daily_start_balance - acc.equity) / daily_start_balance * 100

    if loss_pct >= MAX_DAILY_LOSS_PCT:
        print(f"[STOP] Daily loss {loss_pct:.2f}%")
        return True

    return False


def is_trading_time():
    hour = datetime.now().hour
    return TRADING_START <= hour <= TRADING_END


def has_open_position():
    positions = mt5.positions_get(symbol=SYMBOL)
    if not positions:
        return False
    positions = [p for p in positions if p.magic == MAGIC_NUMBER]
    return len(positions) > 0


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


def partial_close(position, volume):
    tick = mt5.symbol_info_tick(SYMBOL)
    mt5.order_send({
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": SYMBOL,
        "volume": volume,
        "type": mt5.ORDER_TYPE_SELL if position.type == 0 else mt5.ORDER_TYPE_BUY,
        "position": position.ticket,
        "price": tick.bid if position.type == 0 else tick.ask,
        "magic": MAGIC_NUMBER,
        "comment": "partial_close",
        "type_filling": mt5.ORDER_FILLING_IOC,
    })


def get_ohlc(n=100):
    rates = mt5.copy_rates_from_pos(SYMBOL, TIMEFRAME, 0, n)
    if rates is None or len(rates) == 0:
        return pd.DataFrame()
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    return df


def manage_sl_to_be():
    positions = mt5.positions_get(symbol=SYMBOL)
    if not positions:
        return

    positions = [p for p in positions if p.magic == MAGIC_NUMBER]

    for pos in positions:
        entry = pos.price_open
        sl = pos.sl
        volume = pos.volume
        tick = mt5.symbol_info_tick(SYMBOL)

        if pos.type == 0:
            current = tick.bid
            risk = entry - sl
            profit = current - entry

            if profit >= risk * 1.2 and sl < entry:
                new_sl = entry + COMMISSION_BUFFER
                partial_close(pos, volume * PARTIAL_CLOSE_RATIO)
                mt5.order_send({
                    "action": mt5.TRADE_ACTION_SLTP,
                    "position": pos.ticket,
                    "sl": round(new_sl, 2),
                    "tp": pos.tp
                })

            elif sl >= entry:
                new_sl = current - TRAIL_DISTANCE
                if new_sl > sl:
                    mt5.order_send({
                        "action": mt5.TRADE_ACTION_SLTP,
                        "position": pos.ticket,
                        "sl": round(new_sl, 2),
                        "tp": pos.tp
                    })

        elif pos.type == 1:
            current = tick.ask
            risk = sl - entry
            profit = entry - current

            if profit >= risk * 1.2 and sl > entry:
                new_sl = entry - COMMISSION_BUFFER
                partial_close(pos, volume * PARTIAL_CLOSE_RATIO)
                mt5.order_send({
                    "action": mt5.TRADE_ACTION_SLTP,
                    "position": pos.ticket,
                    "sl": round(new_sl, 2),
                    "tp": pos.tp
                })

            elif sl <= entry:
                new_sl = current + TRAIL_DISTANCE
                if new_sl < sl:
                    mt5.order_send({
                        "action": mt5.TRADE_ACTION_SLTP,
                        "position": pos.ticket,
                        "sl": round(new_sl, 2),
                        "tp": pos.tp
                    })


def run_bot():
    global trades_today
    last_processed_time = None

    while True:
        df = get_ohlc(100)
        if df.empty:
            time.sleep(1)
            continue

        if not is_trading_time():
            time.sleep(60)
            continue

        if check_daily_loss():
            time.sleep(60)
            continue

        if trades_today >= MAX_TRADES_PER_DAY:
            time.sleep(60)
            continue

        manage_sl_to_be()

        if has_open_position():
            time.sleep(1)
            continue

        tick = mt5.symbol_info_tick(SYMBOL)
        spread = tick.ask - tick.bid

        if spread > MAX_SPREAD:
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
                            trades_today += 1
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
                            trades_today += 1
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