import MetaTrader5 as mt5
import pandas as pd
import time
from datetime import datetime

# =========================
# CONFIG
# =========================
SYMBOL = "XAUUSD"
TIMEFRAME = mt5.TIMEFRAME_M1
LOTS = 0.01
MAGIC_NUMBER = 51320

# EMA
EMA_FAST = 5
EMA_SLOW = 13

# RSI
RSI_PERIOD = 14
RSI_BUY_LIMIT = 70   # jangan buy kalau RSI >= 70
RSI_SELL_LIMIT = 30  # jangan sell kalau RSI <= 30

# TP SL (sesuaikan dengan broker)
TP_POINTS = 200
SL_POINTS = 150

# max posisi
MAX_BUY = 3
MAX_SELL = 3

# spread filter
MAX_SPREAD = 300

# =========================
# INIT
# =========================
def init():
    if not mt5.initialize():
        print("MT5 gagal connect")
        quit()

    info = mt5.symbol_info(SYMBOL)
    if info is None:
        print(f"Symbol {SYMBOL} tidak ditemukan")
        mt5.shutdown()
        quit()

    if not info.visible:
        if not mt5.symbol_select(SYMBOL, True):
            print(f"Gagal menampilkan symbol {SYMBOL}")
            mt5.shutdown()
            quit()

    print(f"Bot jalan | {SYMBOL} | TF=M1 | EMA {EMA_FAST}/{EMA_SLOW} | RSI {RSI_PERIOD}")

# =========================
# DATA
# =========================
def get_data():
    rates = mt5.copy_rates_from_pos(SYMBOL, TIMEFRAME, 0, 200)
    if rates is None or len(rates) == 0:
        return None

    df = pd.DataFrame(rates)

    df["ema_fast"] = df["close"].ewm(span=EMA_FAST, adjust=False).mean()
    df["ema_slow"] = df["close"].ewm(span=EMA_SLOW, adjust=False).mean()

    delta = df["close"].diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)

    avg_gain = gain.ewm(alpha=1 / RSI_PERIOD, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / RSI_PERIOD, adjust=False).mean()

    rs = avg_gain / avg_loss.replace(0, 1e-10)
    df["rsi"] = 100 - (100 / (1 + rs))

    return df

# =========================
# POSISI
# =========================
def get_positions():
    pos = mt5.positions_get(symbol=SYMBOL)
    if pos is None:
        return []
    return [p for p in pos if p.magic == MAGIC_NUMBER]

def count_pos():
    positions = get_positions()
    buy = sum(1 for p in positions if p.type == mt5.POSITION_TYPE_BUY)
    sell = sum(1 for p in positions if p.type == mt5.POSITION_TYPE_SELL)
    return buy, sell

# =========================
# ORDER
# =========================
def get_filling_mode(info):
    filling_mode = mt5.ORDER_FILLING_IOC
    if hasattr(info, "filling_mode"):
        if info.filling_mode == mt5.ORDER_FILLING_RETURN:
            filling_mode = mt5.ORDER_FILLING_RETURN
        elif info.filling_mode == mt5.ORDER_FILLING_FOK:
            filling_mode = mt5.ORDER_FILLING_FOK
    return filling_mode

def open_order(order_type):
    tick = mt5.symbol_info_tick(SYMBOL)
    info = mt5.symbol_info(SYMBOL)

    if tick is None or info is None:
        print("Gagal ambil tick/info")
        return False

    if order_type == mt5.ORDER_TYPE_BUY:
        price = tick.ask
        sl = price - SL_POINTS * info.point
        tp = price + TP_POINTS * info.point
        side = "BUY"
    else:
        price = tick.bid
        sl = price + SL_POINTS * info.point
        tp = price - TP_POINTS * info.point
        side = "SELL"

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": SYMBOL,
        "volume": LOTS,
        "type": order_type,
        "price": round(price, info.digits),
        "sl": round(sl, info.digits),
        "tp": round(tp, info.digits),
        "deviation": 20,
        "magic": MAGIC_NUMBER,
        "comment": "EMA 5-13 RSI SCALP",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": get_filling_mode(info),
    }

    result = mt5.order_send(request)
    print(f"[{datetime.now()}] {side} ORDER RESULT:", result)
    return result is not None and result.retcode == mt5.TRADE_RETCODE_DONE

# =========================
# MAIN
# =========================
def run():
    init()

    last_signal_bar_time = None

    while True:
        try:
            df = get_data()
            if df is None or len(df) < EMA_SLOW + 5:
                print("Data candle belum cukup")
                time.sleep(1)
                continue

            prev = df.iloc[-2]
            last = df.iloc[-1]

            tick = mt5.symbol_info_tick(SYMBOL)
            info = mt5.symbol_info(SYMBOL)

            if tick is None or info is None:
                print("Tick/info tidak tersedia")
                time.sleep(1)
                continue

            spread = (tick.ask - tick.bid) / info.point

            if spread > MAX_SPREAD:
                print(f"[{datetime.now()}] Spread gede skip: {spread:.1f}")
                time.sleep(1)
                continue

            buy_count, sell_count = count_pos()

            # trend sekarang
            if last["ema_fast"] > last["ema_slow"]:
                market_state = "Bullish"
            elif last["ema_fast"] < last["ema_slow"]:
                market_state = "Bearish"
            else:
                market_state = "Sideways"

            # deteksi cross
            buy_signal = prev["ema_fast"] < prev["ema_slow"] and last["ema_fast"] > last["ema_slow"]
            sell_signal = prev["ema_fast"] > prev["ema_slow"] and last["ema_fast"] < last["ema_slow"]

            current_bar_time = int(last["time"])
            current_rsi = float(last["rsi"])

            print(
                f"[{datetime.now()}] "
                f"Trend={market_state} | "
                f"RSI={current_rsi:.2f} | "
                f"BUY={buy_count}/{MAX_BUY} | "
                f"SELL={sell_count}/{MAX_SELL} | "
                f"Spread={spread:.1f}"
            )

            # supaya tidak spam entry berkali-kali di candle yang sama
            if last_signal_bar_time == current_bar_time:
                time.sleep(1)
                continue

            # BUY
            if buy_signal:
                if current_rsi >= RSI_BUY_LIMIT:
                    print(f"[{datetime.now()}] BUY skip - RSI terlalu tinggi ({current_rsi:.2f})")
                elif buy_count >= MAX_BUY:
                    print(f"[{datetime.now()}] BUY skip - batas BUY penuh")
                else:
                    print(f"[{datetime.now()}] BUY SIGNAL | Trend={market_state} | RSI={current_rsi:.2f}")
                    ok = open_order(mt5.ORDER_TYPE_BUY)
                    if ok:
                        last_signal_bar_time = current_bar_time

            # SELL
            elif sell_signal:
                if current_rsi <= RSI_SELL_LIMIT:
                    print(f"[{datetime.now()}] SELL skip - RSI terlalu rendah ({current_rsi:.2f})")
                elif sell_count >= MAX_SELL:
                    print(f"[{datetime.now()}] SELL skip - batas SELL penuh")
                else:
                    print(f"[{datetime.now()}] SELL SIGNAL | Trend={market_state} | RSI={current_rsi:.2f}")
                    ok = open_order(mt5.ORDER_TYPE_SELL)
                    if ok:
                        last_signal_bar_time = current_bar_time

            time.sleep(1)

        except KeyboardInterrupt:
            print("Bot dihentikan manual")
            break
        except Exception as e:
            print(f"[{datetime.now()}] Error: {e}")
            time.sleep(2)

    mt5.shutdown()

# =========================
if __name__ == "__main__":
    run()