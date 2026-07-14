import MetaTrader5 as mt5
import pandas as pd
import time
from datetime import datetime

# =========================
# CONFIG
# =========================
SYMBOL = "XAUUSD"
# TIMEFRAME = mt5.TIMEFRAME_M1
TIMEFRAME = mt5.TIMEFRAME_M5
LOTS = 0.01
MAGIC_NUMBER = 26042026
CHECK_INTERVAL = 1  # detik

# EMA
EMA_FAST = 3
EMA_SLOW = 8

# Signal persistence
MIN_SIGNAL_CANDLES = 1

# Spread filter
MAX_SPREAD_POINTS = 300

# Maksimal posisi running per arah
MAX_RUNNING_BUYS = 5
MAX_RUNNING_SELLS = 5

# =========================
# SL / TP MODE
# =========================
# "ATR"   = SL/TP mengikuti ATR
# "FIXED" = SL/TP fixed berdasarkan points
SLTP_MODE = "FIXED"

# --- ATR mode ---
ATR_PERIOD = 14
ATR_MULTIPLIER_SL = 1.5
ATR_MULTIPLIER_TP = 2.5

# --- FIXED mode ---
# Berdasarkan akun kamu:
# 500 points  = 0.500 harga ≈ $0.50
# 2000 points = 2.000 harga ≈ $2.00
FIXED_SL_POINTS = 2000
FIXED_TP_POINTS = 2000

# =========================
# SMART SL SAAT TINGGAL 10% KE TP
# =========================
USE_SMART_SL_NEAR_TP = True
SMART_SL_TRIGGER_REMAINING = 0.10
SMART_SL_MODE = "LOCK"
SMART_SL_LOCK_PERCENT = 0.80
SMART_SL_EXTRA_BUFFER_POINTS = 10

# =========================
# OPSIONAL TRAILING BIASA
# =========================
USE_TRAILING_STOP = False
TRAILING_MODE = "ATR"
ATR_TRAILING_MULTIPLIER = 1.0
FIXED_TRAILING_POINTS = 120

# =========================
# STATE
# =========================
_last_signal = None
_signal_count = 0
_last_entry_bar_time_buy = None
_last_entry_bar_time_sell = None
_smart_sl_done_tickets = set()

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
# INIT
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
    print(f"Trade allowed terminal : {terminal.trade_allowed}")
    print(f"Trade allowed account  : {account.trade_allowed}")

    if not terminal.trade_allowed:
        print("[-] Algo Trading / AutoTrading MT5 masih OFF")
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

def get_spread_points(symbol):
    tick = get_tick(symbol)
    info = get_symbol_info(symbol)
    if tick is None or info is None:
        return 999999
    return (tick.ask - tick.bid) / info.point

def get_rates(symbol, timeframe, bars=200):
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, bars)
    if rates is None or len(rates) == 0:
        return None

    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    return df

def add_indicators(df):
    df["ema_fast"] = df["close"].ewm(span=EMA_FAST, adjust=False).mean()
    df["ema_slow"] = df["close"].ewm(span=EMA_SLOW, adjust=False).mean()

    high_low = df["high"] - df["low"]
    high_close = abs(df["high"] - df["close"].shift())
    low_close = abs(df["low"] - df["close"].shift())
    true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df["atr"] = true_range.ewm(span=ATR_PERIOD, adjust=False).mean()

    return df

def get_open_positions(symbol, magic):
    positions = mt5.positions_get(symbol=symbol)
    if positions is None:
        return []
    return [p for p in positions if p.magic == magic]

def count_positions_by_type(positions):
    buy_count = sum(1 for p in positions if p.type == mt5.POSITION_TYPE_BUY)
    sell_count = sum(1 for p in positions if p.type == mt5.POSITION_TYPE_SELL)
    return buy_count, sell_count

def normalize_volume(symbol, volume):
    info = get_symbol_info(symbol)
    if info is None:
        return volume

    step = info.volume_step
    min_vol = info.volume_min
    max_vol = info.volume_max

    vol = max(min_vol, min(volume, max_vol))
    steps = round(vol / step)
    vol = steps * step
    return round(vol, 2)

def get_filling_mode(info):
    filling_mode = mt5.ORDER_FILLING_IOC
    if hasattr(info, "filling_mode"):
        if info.filling_mode == mt5.ORDER_FILLING_RETURN:
            filling_mode = mt5.ORDER_FILLING_RETURN
        elif info.filling_mode == mt5.ORDER_FILLING_FOK:
            filling_mode = mt5.ORDER_FILLING_FOK
    return filling_mode

def get_sl_tp_distances(info, atr_value):
    if SLTP_MODE.upper() == "ATR":
        sl_distance = atr_value * ATR_MULTIPLIER_SL
        tp_distance = atr_value * ATR_MULTIPLIER_TP
    else:
        sl_distance = FIXED_SL_POINTS * info.point
        tp_distance = FIXED_TP_POINTS * info.point
    return sl_distance, tp_distance

def get_trailing_distance(info, atr_value):
    if TRAILING_MODE.upper() == "ATR":
        return atr_value * ATR_TRAILING_MULTIPLIER
    return FIXED_TRAILING_POINTS * info.point

# =========================
# SIGNAL
# =========================
def check_signal(df):
    global _last_signal, _signal_count

    if len(df) < EMA_SLOW + 2:
        return None, None

    last = df.iloc[-1]

    ema_bullish = last["ema_fast"] > last["ema_slow"]
    ema_bearish = last["ema_fast"] < last["ema_slow"]

    if ema_bullish:
        if _last_signal == "BUY":
            _signal_count += 1
        else:
            _last_signal = "BUY"
            _signal_count = 1

    elif ema_bearish:
        if _last_signal == "SELL":
            _signal_count += 1
        else:
            _last_signal = "SELL"
            _signal_count = 1
    else:
        _last_signal = None
        _signal_count = 0
        return None, None

    if _signal_count >= MIN_SIGNAL_CANDLES:
        return _last_signal, _signal_count

    return None, _signal_count

# =========================
# ORDER
# =========================
def send_order(symbol, lot, order_type, atr_value, magic):
    info = get_symbol_info(symbol)
    tick = get_tick(symbol)

    if info is None or tick is None:
        print("[-] Gagal ambil symbol info / tick")
        return False

    terminal = mt5.terminal_info()
    if terminal is None or not terminal.trade_allowed:
        print("[-] Algo Trading / AutoTrading MT5 masih OFF")
        return False

    lot = normalize_volume(symbol, lot)
    sl_distance, tp_distance = get_sl_tp_distances(info, atr_value)

    if order_type == mt5.ORDER_TYPE_BUY:
        price = tick.ask
        sl = price - sl_distance
        tp = price + tp_distance
        side = "BUY"
    else:
        price = tick.bid
        sl = price + sl_distance
        tp = price - tp_distance
        side = "SELL"

    min_stop_distance = info.trade_stops_level * info.point

    print(
        f"ATR={atr_value:.2f} | Mode={SLTP_MODE} | "
        f"SL_dist={sl_distance:.5f} | TP_dist={tp_distance:.5f}"
    )
    print(
        f"Price={price:.5f} | SL={sl:.5f} | TP={tp:.5f} | "
        f"MinStop={min_stop_distance:.5f}"
    )

    if order_type == mt5.ORDER_TYPE_BUY:
        if (price - sl) < min_stop_distance:
            print("[-] BUY skip: SL terlalu dekat")
            return False
        if (tp - price) < min_stop_distance:
            print("[-] BUY skip: TP terlalu dekat")
            return False
    else:
        if (sl - price) < min_stop_distance:
            print("[-] SELL skip: SL terlalu dekat")
            return False
        if (price - tp) < min_stop_distance:
            print("[-] SELL skip: TP terlalu dekat")
            return False

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
        "comment": "EMA FLEX SMART SL HEDGE",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": get_filling_mode(info),
    }

    print("REQUEST:", request)
    result = mt5.order_send(request)

    if result is None:
        print(f"[{datetime.now()}] [-] order_send gagal (result None)")
        return False

    print(f"[{datetime.now()}] retcode={result.retcode} ({retcode_text(result.retcode)})")

    if result.retcode == mt5.TRADE_RETCODE_DONE:
        print(f"[{datetime.now()}] [OK] {side} OPEN")
        print(f"  Price : {round(price, info.digits)}")
        print(f"  SL    : {round(sl, info.digits)}")
        print(f"  TP    : {round(tp, info.digits)}")
        print(f"  Ticket: {result.order}")
        return True

    print(f"[{datetime.now()}] [-] Order gagal | {retcode_text(result.retcode)}")

    if result.retcode == 10027:
        print("    -> Aktifkan tombol 'Algo Trading' di MT5 sampai hijau.")
    elif result.retcode == 10016:
        print("    -> SL/TP terlalu dekat. Perbesar jarak SL/TP.")
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
    elif result.retcode == 10046:
        print("    -> Akun broker tidak mengizinkan hedging (buy & sell bersamaan).")

    return False

# =========================
# MODIFY SLTP
# =========================
def modify_position_sl_tp(position_ticket, new_sl, current_tp):
    result = mt5.order_send({
        "action": mt5.TRADE_ACTION_SLTP,
        "position": position_ticket,
        "sl": new_sl,
        "tp": current_tp,
    })
    return result

# =========================
# SMART SL NEAR TP
# =========================
def update_smart_sl_near_tp(positions):
    global _smart_sl_done_tickets

    if not USE_SMART_SL_NEAR_TP:
        return

    info = get_symbol_info(SYMBOL)
    tick = get_tick(SYMBOL)

    if info is None or tick is None:
        return

    min_stop_distance = info.trade_stops_level * info.point
    buffer_price = SMART_SL_EXTRA_BUFFER_POINTS * info.point

    active_tickets = {p.ticket for p in positions}
    _smart_sl_done_tickets = {t for t in _smart_sl_done_tickets if t in active_tickets}

    for pos in positions:
        if pos.ticket in _smart_sl_done_tickets:
            continue

        entry = pos.price_open
        tp = pos.tp
        current_sl = pos.sl

        if tp == 0:
            continue

        if pos.type == mt5.POSITION_TYPE_BUY:
            current_price = tick.bid
            total_distance = tp - entry
            remaining_distance = tp - current_price

            if total_distance <= 0:
                continue

            trigger_distance = total_distance * SMART_SL_TRIGGER_REMAINING

            if remaining_distance <= trigger_distance:
                if SMART_SL_MODE.upper() == "BREAKEVEN":
                    new_sl = entry + buffer_price
                else:
                    new_sl = entry + (total_distance * SMART_SL_LOCK_PERCENT) + buffer_price

                if new_sl >= current_price:
                    continue

                if current_sl != 0 and new_sl <= current_sl:
                    continue

                if (current_price - new_sl) < min_stop_distance:
                    continue

                result = modify_position_sl_tp(
                    pos.ticket,
                    round(new_sl, info.digits),
                    pos.tp
                )

                if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                    print(f"[smart-sl] BUY {pos.ticket} -> SL {round(new_sl, info.digits)}")
                    _smart_sl_done_tickets.add(pos.ticket)

        elif pos.type == mt5.POSITION_TYPE_SELL:
            current_price = tick.ask
            total_distance = entry - tp
            remaining_distance = current_price - tp

            if total_distance <= 0:
                continue

            trigger_distance = total_distance * SMART_SL_TRIGGER_REMAINING

            if remaining_distance <= trigger_distance:
                if SMART_SL_MODE.upper() == "BREAKEVEN":
                    new_sl = entry - buffer_price
                else:
                    new_sl = entry - (total_distance * SMART_SL_LOCK_PERCENT) - buffer_price

                if new_sl <= current_price:
                    continue

                if current_sl != 0 and new_sl >= current_sl:
                    continue

                if (new_sl - current_price) < min_stop_distance:
                    continue

                result = modify_position_sl_tp(
                    pos.ticket,
                    round(new_sl, info.digits),
                    pos.tp
                )

                if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                    print(f"[smart-sl] SELL {pos.ticket} -> SL {round(new_sl, info.digits)}")
                    _smart_sl_done_tickets.add(pos.ticket)

# =========================
# OPTIONAL TRAILING STOP
# =========================
def update_trailing_stops(positions, atr_value):
    if not USE_TRAILING_STOP:
        return

    info = get_symbol_info(SYMBOL)
    tick = get_tick(SYMBOL)

    if info is None or tick is None:
        return

    trail_dist = get_trailing_distance(info, atr_value)
    min_stop_distance = info.trade_stops_level * info.point

    for pos in positions:
        if pos.type == mt5.POSITION_TYPE_BUY:
            new_sl = tick.bid - trail_dist
            if pos.sl == 0 or new_sl > pos.sl:
                if (tick.bid - new_sl) >= min_stop_distance:
                    result = modify_position_sl_tp(
                        pos.ticket,
                        round(new_sl, info.digits),
                        pos.tp
                    )
                    if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                        print(f"[trailing] BUY ticket {pos.ticket} -> SL {round(new_sl, info.digits)}")

        elif pos.type == mt5.POSITION_TYPE_SELL:
            new_sl = tick.ask + trail_dist
            if pos.sl == 0 or new_sl < pos.sl:
                if (new_sl - tick.ask) >= min_stop_distance:
                    result = modify_position_sl_tp(
                        pos.ticket,
                        round(new_sl, info.digits),
                        pos.tp
                    )
                    if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                        print(f"[trailing] SELL ticket {pos.ticket} -> SL {round(new_sl, info.digits)}")

# =========================
# MAIN LOOP
# =========================
def run_forward_test():
    global _last_entry_bar_time_buy, _last_entry_bar_time_sell

    initialize_mt5()

    print(f"\n[{datetime.now()}] Bot EMA Flex aktif")
    print(f"  EMA: {EMA_FAST}/{EMA_SLOW}")
    print(f"  Signal persistence: {MIN_SIGNAL_CANDLES} candle(s)")
    print(f"  Max running BUY : {MAX_RUNNING_BUYS}")
    print(f"  Max running SELL: {MAX_RUNNING_SELLS}")
    print(f"  Hedging buy & sell bersamaan: YES")
    print(f"  SLTP mode: {SLTP_MODE}")

    if SLTP_MODE.upper() == "ATR":
        print(f"  ATR SL: {ATR_MULTIPLIER_SL}x | ATR TP: {ATR_MULTIPLIER_TP}x")
    else:
        print(f"  Fixed SL: {FIXED_SL_POINTS} points | Fixed TP: {FIXED_TP_POINTS} points")

    print(f"  Smart SL near TP: {'ON' if USE_SMART_SL_NEAR_TP else 'OFF'}")
    if USE_SMART_SL_NEAR_TP:
        print(f"  Trigger remaining to TP: {SMART_SL_TRIGGER_REMAINING * 100:.0f}%")
        print(f"  Smart SL mode: {SMART_SL_MODE}")
        if SMART_SL_MODE.upper() == "LOCK":
            print(f"  Lock percent: {SMART_SL_LOCK_PERCENT * 100:.0f}%")
        print(f"  Extra buffer: {SMART_SL_EXTRA_BUFFER_POINTS} points")

    print(f"  Trailing stop biasa: {'ON' if USE_TRAILING_STOP else 'OFF'}")
    print("")

    while True:
        try:
            spread = get_spread_points(SYMBOL)
            if spread > MAX_SPREAD_POINTS:
                print(f"[{datetime.now()}] Spread terlalu besar: {spread:.1f}")
                time.sleep(CHECK_INTERVAL)
                continue

            df = get_rates(SYMBOL, TIMEFRAME, 200)
            if df is None:
                print(f"[{datetime.now()}] Gagal ambil data candle")
                time.sleep(CHECK_INTERVAL)
                continue

            df = add_indicators(df)
            last = df.iloc[-1]
            current_bar_time = last["time"]

            positions = get_open_positions(SYMBOL, MAGIC_NUMBER)
            total_positions = len(positions)
            buy_positions, sell_positions = count_positions_by_type(positions)

            if positions:
                update_smart_sl_near_tp(positions)
                update_trailing_stops(positions, last["atr"])

            signal, signal_count = check_signal(df)

            ema_state = "Bullish" if last["ema_fast"] > last["ema_slow"] else "Bearish"
            account = mt5.account_info()
            balance_str = f"{account.balance:.2f}" if account else "?"

            print(
                f"[{datetime.now()}] "
                f"Signal={signal or '-'} ({signal_count or 0}) | "
                f"Spread={spread:.1f} | "
                f"BUY={buy_positions}/{MAX_RUNNING_BUYS} | "
                f"SELL={sell_positions}/{MAX_RUNNING_SELLS} | "
                f"TOTAL={total_positions} | "
                f"EMA={ema_state} | ATR={last['atr']:.2f} | Balance={balance_str}"
            )

            can_entry_buy_this_bar = (_last_entry_bar_time_buy != current_bar_time)
            can_entry_sell_this_bar = (_last_entry_bar_time_sell != current_bar_time)

            can_add_buy = buy_positions < MAX_RUNNING_BUYS
            can_add_sell = sell_positions < MAX_RUNNING_SELLS

            if signal == "BUY":
                if can_entry_buy_this_bar and can_add_buy:
                    ok = send_order(SYMBOL, LOTS, mt5.ORDER_TYPE_BUY, last["atr"], MAGIC_NUMBER)
                    if ok:
                        _last_entry_bar_time_buy = current_bar_time
                elif not can_add_buy:
                    print(f"[{datetime.now()}] Batas BUY tercapai ({MAX_RUNNING_BUYS}). Tunggu ada BUY yang close.")

            elif signal == "SELL":
                if can_entry_sell_this_bar and can_add_sell:
                    ok = send_order(SYMBOL, LOTS, mt5.ORDER_TYPE_SELL, last["atr"], MAGIC_NUMBER)
                    if ok:
                        _last_entry_bar_time_sell = current_bar_time
                elif not can_add_sell:
                    print(f"[{datetime.now()}] Batas SELL tercapai ({MAX_RUNNING_SELLS}). Tunggu ada SELL yang close.")

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