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
MAGIC_NUMBER = 26042026

# Untuk XAUUSDm Exness, mulai dari angka yang lebih realistis
TP_PIPS = 100
SL_PIPS = 100

EMA_FAST = 9
EMA_SLOW = 21

MAX_SPREAD_POINTS = 300
MAX_BUY_POSITIONS = 1
MAX_SELL_POSITIONS = 1
MIN_DISTANCE_PIPS = 50
CHECK_INTERVAL = 1  # detik

# =========================
# RETCODE HELPER
# =========================
RETCODE_MAP = {
    10004: "TRADE_RETCODE_REQUOTE",
    10006: "TRADE_RETCODE_REJECT",
    10007: "TRADE_RETCODE_CANCEL",
    10008: "TRADE_RETCODE_PLACED",
    10009: "TRADE_RETCODE_DONE",
    10010: "TRADE_RETCODE_DONE_PARTIAL",
    10011: "TRADE_RETCODE_ERROR",
    10012: "TRADE_RETCODE_TIMEOUT",
    10013: "TRADE_RETCODE_INVALID",
    10014: "TRADE_RETCODE_INVALID_VOLUME",
    10015: "TRADE_RETCODE_INVALID_PRICE",
    10016: "TRADE_RETCODE_INVALID_STOPS",
    10017: "TRADE_RETCODE_TRADE_DISABLED",
    10018: "TRADE_RETCODE_MARKET_CLOSED",
    10019: "TRADE_RETCODE_NO_MONEY",
    10020: "TRADE_RETCODE_PRICE_CHANGED",
    10021: "TRADE_RETCODE_PRICE_OFF",
    10022: "TRADE_RETCODE_INVALID_EXPIRATION",
    10023: "TRADE_RETCODE_ORDER_CHANGED",
    10024: "TRADE_RETCODE_TOO_MANY_REQUESTS",
    10025: "TRADE_RETCODE_NO_CHANGES",
    10026: "TRADE_RETCODE_SERVER_DISABLES_AT",
    10027: "TRADE_RETCODE_CLIENT_DISABLES_AT",
    10028: "TRADE_RETCODE_LOCKED",
    10029: "TRADE_RETCODE_FROZEN",
    10030: "TRADE_RETCODE_INVALID_FILL",
    10031: "TRADE_RETCODE_CONNECTION",
    10032: "TRADE_RETCODE_ONLY_REAL",
    10033: "TRADE_RETCODE_LIMIT_ORDERS",
    10034: "TRADE_RETCODE_LIMIT_VOLUME",
    10035: "TRADE_RETCODE_INVALID_ORDER",
    10036: "TRADE_RETCODE_POSITION_CLOSED",
    10038: "TRADE_RETCODE_INVALID_CLOSE_VOLUME",
    10039: "TRADE_RETCODE_CLOSE_ORDER_EXIST",
    10040: "TRADE_RETCODE_LIMIT_POSITIONS",
    10041: "TRADE_RETCODE_REJECT_CANCEL",
    10042: "TRADE_RETCODE_LONG_ONLY",
    10043: "TRADE_RETCODE_SHORT_ONLY",
    10044: "TRADE_RETCODE_CLOSE_ONLY",
    10045: "TRADE_RETCODE_FIFO_CLOSE",
    10046: "TRADE_RETCODE_HEDGE_PROHIBITED",
}

def retcode_text(code):
    return RETCODE_MAP.get(code, f"UNKNOWN_RETCODE_{code}")

# =========================
# MT5 INIT
# =========================
def initialize_mt5():
    if not mt5.initialize():
        print("[-] Gagal konek ke MT5")
        quit()

    terminal = mt5.terminal_info()
    account = mt5.account_info()

    if terminal is None:
        print("[-] Gagal ambil terminal info")
        quit()

    if account is None:
        print("[-] Gagal ambil info akun")
        quit()

    print(f"[{datetime.now()}] MT5 connected")
    print(f"Akun   : {account.login}")
    print(f"Server : {account.server}")
    print(f"Balance: {account.balance}")

    # Cek Algo Trading / AutoTrading
    # retcode 10027 biasanya karena ini False
    print(f"Trade allowed terminal : {terminal.trade_allowed}")
    print(f"Trade allowed account  : {account.trade_allowed}")

    if not terminal.trade_allowed:
        print("[-] Algo Trading / AutoTrading di MT5 masih OFF")
        print("    Nyalakan tombol 'Algo Trading' sampai hijau, lalu jalankan ulang bot.")
        mt5.shutdown()
        quit()

    symbol_info = mt5.symbol_info(SYMBOL)
    if symbol_info is None:
        print(f"[-] Symbol {SYMBOL} tidak ditemukan")
        mt5.shutdown()
        quit()

    if not symbol_info.visible:
        ok = mt5.symbol_select(SYMBOL, True)
        if not ok:
            print(f"[-] Gagal menampilkan symbol {SYMBOL}")
            mt5.shutdown()
            quit()

    print(f"Symbol             : {SYMBOL}")
    print(f"Digits             : {symbol_info.digits}")
    print(f"Point              : {symbol_info.point}")
    print(f"Trade stops level  : {symbol_info.trade_stops_level}")
    print(f"Freeze level       : {symbol_info.trade_freeze_level}")
    print(f"Volume min         : {symbol_info.volume_min}")
    print(f"Volume max         : {symbol_info.volume_max}")
    print(f"Volume step        : {symbol_info.volume_step}")

# =========================
# HELPERS
# =========================
def get_symbol_info(symbol):
    return mt5.symbol_info(symbol)

def get_tick(symbol):
    return mt5.symbol_info_tick(symbol)

def get_pip_size(symbol_info):
    # Untuk broker 3/5 digit, 1 pip = 10 point
    if symbol_info.digits in [3, 5]:
        return symbol_info.point * 10
    return symbol_info.point

def get_spread_points(symbol):
    tick = get_tick(symbol)
    info = get_symbol_info(symbol)
    if tick is None or info is None:
        return 999999
    return (tick.ask - tick.bid) / info.point

def get_rates(symbol, timeframe, bars=100):
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, bars)
    if rates is None or len(rates) == 0:
        return None

    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    return df

def add_indicators(df):
    df["ema_fast"] = df["close"].ewm(span=EMA_FAST, adjust=False).mean()
    df["ema_slow"] = df["close"].ewm(span=EMA_SLOW, adjust=False).mean()
    return df

def get_open_positions(symbol, magic):
    positions = mt5.positions_get(symbol=symbol)
    if positions is None:
        return []
    return [p for p in positions if p.magic == magic]

def get_positions_by_type(positions, position_type):
    return [p for p in positions if p.type == position_type]

def is_far_enough(new_price, positions, pip_size, min_distance_pips):
    if not positions:
        return True

    min_distance = pip_size * min_distance_pips
    for p in positions:
        if abs(new_price - p.price_open) < min_distance:
            return False
    return True

def normalize_volume(symbol, volume):
    info = get_symbol_info(symbol)
    if info is None:
        return volume

    step = info.volume_step
    min_vol = info.volume_min
    max_vol = info.volume_max

    vol = max(min_vol, min(volume, max_vol))
    # bulatkan ke step
    steps = round(vol / step)
    vol = steps * step
    return round(vol, 2)

# =========================
# SIGNAL
# =========================
def check_signal(df):
    if len(df) < 30:
        return None

    last = df.iloc[-1]
    prev = df.iloc[-2]

    buy_signal = (
        last["ema_fast"] > last["ema_slow"] and
        last["close"] > prev["high"]
    )

    sell_signal = (
        last["ema_fast"] < last["ema_slow"] and
        last["close"] < prev["low"]
    )

    if buy_signal:
        return "BUY"
    elif sell_signal:
        return "SELL"
    return None

# =========================
# ORDER
# =========================
def send_order(symbol, lot, order_type, sl_pips, tp_pips, magic):
    info = get_symbol_info(symbol)
    tick = get_tick(symbol)

    if info is None or tick is None:
        print("[-] Gagal ambil symbol info / tick")
        return

    if not mt5.terminal_info().trade_allowed:
        print("[-] Algo Trading / AutoTrading MT5 masih OFF")
        return

    lot = normalize_volume(symbol, lot)
    pip_size = get_pip_size(info)

    if order_type == mt5.ORDER_TYPE_BUY:
        price = tick.ask
        sl = price - (sl_pips * pip_size)
        tp = price + (tp_pips * pip_size)
        side = "BUY"
    else:
        price = tick.bid
        sl = price + (sl_pips * pip_size)
        tp = price - (tp_pips * pip_size)
        side = "SELL"

    # validasi jarak stop minimal broker
    min_stop_distance = info.trade_stops_level * info.point

    print(f"STOP LEVEL: {info.trade_stops_level} point")
    print(f"Min stop distance: {min_stop_distance}")
    print(f"Price={price} | SL={sl} | TP={tp}")

    if order_type == mt5.ORDER_TYPE_BUY:
        if (price - sl) < min_stop_distance:
            print("[-] BUY skip: SL terlalu dekat")
            return
        if (tp - price) < min_stop_distance:
            print("[-] BUY skip: TP terlalu dekat")
            return
    else:
        if (sl - price) < min_stop_distance:
            print("[-] SELL skip: SL terlalu dekat")
            return
        if (price - tp) < min_stop_distance:
            print("[-] SELL skip: TP terlalu dekat")
            return

    filling_mode = mt5.ORDER_FILLING_IOC
    # kalau broker/symbol tidak cocok IOC, coba fallback RETURN
    if hasattr(info, "filling_mode"):
        if info.filling_mode == mt5.ORDER_FILLING_RETURN:
            filling_mode = mt5.ORDER_FILLING_RETURN
        elif info.filling_mode == mt5.ORDER_FILLING_FOK:
            filling_mode = mt5.ORDER_FILLING_FOK

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": lot,
        "type": order_type,
        "price": round(price, info.digits),
        "sl": round(sl, info.digits),
        "tp": round(tp, info.digits),
        "deviation": 20,
        "magic": magic,
        "comment": "ForwardTest M1",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": filling_mode,
    }

    print("REQUEST:", request)

    result = mt5.order_send(request)

    if result is None:
        print(f"[{datetime.now()}] [-] order_send gagal (result None)")
        return

    print(f"[{datetime.now()}] retcode={result.retcode} ({retcode_text(result.retcode)})")

    if result.retcode == mt5.TRADE_RETCODE_DONE:
        print(f"[{datetime.now()}] [OK] {side} OPEN")
        print(f"  Price : {price}")
        print(f"  SL    : {round(sl, info.digits)}")
        print(f"  TP    : {round(tp, info.digits)}")
        print(f"  Ticket: {result.order}")
    else:
        print(f"[{datetime.now()}] [-] Order gagal | retcode={result.retcode} ({retcode_text(result.retcode)})")

        if result.retcode == 10027:
            print("    -> Aktifkan tombol 'Algo Trading' di MT5 sampai hijau.")
        elif result.retcode == 10016:
            print("    -> SL/TP masih terlalu dekat. Besarkan TP_PIPS / SL_PIPS.")
        elif result.retcode == 10030:
            print("    -> Filling mode tidak cocok untuk symbol ini.")
        elif result.retcode == 10014:
            print("    -> Volume tidak valid. Cek LOTS / volume_step broker.")
        elif result.retcode == 10015:
            print("    -> Harga tidak valid / berubah.")
        elif result.retcode == 10021:
            print("    -> Tidak ada harga quote saat order dikirim.")
        elif result.retcode == 10017:
            print("    -> Trading untuk symbol/akun sedang disabled.")

# =========================
# MAIN LOOP
# =========================
def run_forward_test():
    initialize_mt5()
    info = get_symbol_info(SYMBOL)
    pip_size = get_pip_size(info)

    print(f"[{datetime.now()}] Forward test aktif...\n")

    while True:
        try:
            spread = get_spread_points(SYMBOL)
            if spread > MAX_SPREAD_POINTS:
                print(f"[{datetime.now()}] Spread terlalu besar: {spread:.1f}")
                time.sleep(CHECK_INTERVAL)
                continue

            df = get_rates(SYMBOL, TIMEFRAME, 100)
            if df is None:
                print(f"[{datetime.now()}] Gagal ambil data candle")
                time.sleep(CHECK_INTERVAL)
                continue

            df = add_indicators(df)
            signal = check_signal(df)

            positions = get_open_positions(SYMBOL, MAGIC_NUMBER)
            buy_positions = get_positions_by_type(positions, mt5.POSITION_TYPE_BUY)
            sell_positions = get_positions_by_type(positions, mt5.POSITION_TYPE_SELL)

            tick = get_tick(SYMBOL)
            if tick is None:
                time.sleep(CHECK_INTERVAL)
                continue

            print(
                f"[{datetime.now()}] "
                f"Signal={signal} | Spread={spread:.1f} | "
                f"BuyPos={len(buy_positions)} | SellPos={len(sell_positions)}"
            )

            if signal == "BUY":
                if len(buy_positions) < MAX_BUY_POSITIONS:
                    if is_far_enough(tick.ask, buy_positions, pip_size, MIN_DISTANCE_PIPS):
                        send_order(SYMBOL, LOTS, mt5.ORDER_TYPE_BUY, SL_PIPS, TP_PIPS, MAGIC_NUMBER)

            elif signal == "SELL":
                if len(sell_positions) < MAX_SELL_POSITIONS:
                    if is_far_enough(tick.bid, sell_positions, pip_size, MIN_DISTANCE_PIPS):
                        send_order(SYMBOL, LOTS, mt5.ORDER_TYPE_SELL, SL_PIPS, TP_PIPS, MAGIC_NUMBER)

            time.sleep(CHECK_INTERVAL)

        except KeyboardInterrupt:
            print("\n[!] Bot dihentikan manual")
            break
        except Exception as e:
            print(f"[{datetime.now()}] Error: {e}")
            time.sleep(2)

    mt5.shutdown()

if __name__ == "__main__":
    run_forward_test()