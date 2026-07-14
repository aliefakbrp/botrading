import MetaTrader5 as mt5
import pandas as pd
import numpy as np
import time
from datetime import datetime

# =========================
# CONFIG - M1 SCALPING
# =========================
SYMBOL = "XAUUSD"
TIMEFRAME = mt5.TIMEFRAME_M1
LOTS = 0.01
MAGIC_NUMBER = 26042026
CHECK_INTERVAL = 0.5

# EMA
EMA_FAST = 5
EMA_SLOW = 10

MIN_SIGNAL_CANDLES = 1
OPPOSITE_CLOSE_SIGNAL_COUNT = 3
MAX_SPREAD_POINTS = 250
MAX_RUNNING_BUYS = 5
MAX_RUNNING_SELLS = 5

# =========================
# SL/TP MODE
# =========================
SLTP_MODE = "ATR"

ATR_PERIOD = 7
ATR_MULTIPLIER_SL = 1.0
ATR_MULTIPLIER_TP = 1.5

FIXED_SL_POINTS = 100
FIXED_TP_POINTS = 150

# =========================
# SMART SL
# =========================
USE_SMART_SL_NEAR_TP = True
SMART_SL_TRIGGER_REMAINING = 0.20
SMART_SL_MODE = "LOCK"
SMART_SL_LOCK_PERCENT = 0.70
SMART_SL_EXTRA_BUFFER_POINTS = 5

# =========================
# TRAILING STOP
# =========================
USE_TRAILING_STOP = False
TRAILING_MODE = "FIXED"
ATR_TRAILING_MULTIPLIER = 0.5
FIXED_TRAILING_POINTS = 50

# =========================
# CACHE
# =========================
_cached_symbol_info = None
_cached_account = None
_cached_terminal = None
_cache_timestamp = 0
CACHE_TTL = 0.5

# =========================
# STATE
# =========================
_last_signal = None
_signal_count = 0
_last_entry_bar_time_buy = None
_last_entry_bar_time_sell = None
_smart_sl_done_tickets = set()
_last_opposite_close_signal = None

# =========================
# RETCODE
# =========================
RETCODE_MAP = {
    10004: "REQUOTE", 10006: "REJECT", 10007: "CANCEL", 10008: "PLACED",
    10009: "DONE", 10010: "DONE_PARTIAL", 10011: "ERROR", 10012: "TIMEOUT",
    10013: "INVALID", 10014: "INV_VOLUME", 10015: "INV_PRICE", 10016: "INV_STOPS",
    10017: "TRADE_DISABLED", 10018: "MARKET_CLOSED", 10019: "NO_MONEY",
    10020: "PRICE_CHANGED", 10021: "PRICE_OFF", 10022: "INV_EXPIRY", 10023: "ORDER_CHG",
    10024: "TOO_MANY_REQ", 10025: "NO_CHANGES", 10026: "SRV_DISABLED_AT",
    10027: "CLIENT_DISABLED_AT", 10028: "LOCKED", 10029: "FROZEN", 10030: "INV_FILL",
    10031: "CONNECTION", 10032: "ONLY_REAL", 10033: "LIMIT_ORDERS", 10034: "LIMIT_VOLUME",
    10035: "INV_ORDER", 10036: "POS_CLOSED", 10038: "INV_CLOSE_VOL", 10039: "CLOSE_ORDER_EXIST",
    10040: "LIMIT_POSITIONS", 10041: "REJECT_CANCEL", 10042: "LONG_ONLY", 10043: "SHORT_ONLY",
    10044: "CLOSE_ONLY", 10045: "FIFO_CLOSE", 10046: "HEDGE_PROHIBITED",
}

def retcode_text(code):
    return RETCODE_MAP.get(code, f"UNK_{code}")

# =========================
# CACHED HELPERS
# =========================
def get_cached_symbol_info(symbol):
    global _cached_symbol_info, _cache_timestamp
    now = time.time()
    if _cached_symbol_info is not None and (now - _cache_timestamp) < CACHE_TTL:
        return _cached_symbol_info
    info = mt5.symbol_info(symbol)
    if info is not None:
        _cached_symbol_info = info
        _cache_timestamp = now
    return info

def get_cached_terminal_account():
    global _cached_terminal, _cached_account, _cache_timestamp
    now = time.time()
    if _cached_terminal is not None and (now - _cache_timestamp) < CACHE_TTL:
        return _cached_terminal, _cached_account
    terminal = mt5.terminal_info()
    account = mt5.account_info()
    if terminal is not None:
        _cached_terminal = terminal
        _cached_account = account
        _cache_timestamp = now
    return terminal, account

def invalidate_cache():
    global _cached_symbol_info, _cached_terminal, _cached_account, _cache_timestamp
    _cached_symbol_info = None
    _cached_terminal = None
    _cached_account = None
    _cache_timestamp = 0

# =========================
# INIT
# =========================
def initialize_mt5():
    if not mt5.initialize():
        print("[-] Gagal konek ke MT5")
        quit()

    terminal, account = get_cached_terminal_account()
    if terminal is None or account is None:
        print("[-] Gagal ambil info terminal/account")
        mt5.shutdown()
        quit()

    print(f"[{datetime.now()}] MT5 connected | Akun: {account.login} | Balance: {account.balance:.2f}")

    if not terminal.trade_allowed:
        print("[-] Algo Trading OFF - nyalakan tombol hijau di MT5")
        mt5.shutdown()
        quit()

    info = get_cached_symbol_info(SYMBOL)
    if info is None:
        print(f"[-] Symbol {SYMBOL} tidak ditemukan")
        mt5.shutdown()
        quit()

    if not info.visible:
        mt5.symbol_select(SYMBOL, True)

    print(f"Symbol: {SYMBOL} | Digits: {info.digits} | Point: {info.point}")

# =========================
# HELPERS
# =========================
def get_tick(symbol):
    return mt5.symbol_info_tick(symbol)

def get_spread_points(symbol):
    tick = get_tick(symbol)
    info = get_cached_symbol_info(symbol)
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
    close = df["close"].values
    high = df["high"].values
    low = df["low"].values

    alpha_fast = 2.0 / (EMA_FAST + 1)
    alpha_slow = 2.0 / (EMA_SLOW + 1)

    ema_fast = np.zeros(len(close))
    ema_slow = np.zeros(len(close))
    ema_fast[0] = close[0]
    ema_slow[0] = close[0]

    for i in range(1, len(close)):
        ema_fast[i] = alpha_fast * close[i] + (1 - alpha_fast) * ema_fast[i-1]
        ema_slow[i] = alpha_slow * close[i] + (1 - alpha_slow) * ema_slow[i-1]

    df["ema_fast"] = ema_fast
    df["ema_slow"] = ema_slow

    tr = np.maximum(high - low, np.maximum(
        np.abs(high - np.roll(close, 1)),
        np.abs(low - np.roll(close, 1))
    ))
    tr[0] = high[0] - low[0]

    atr = np.zeros(len(tr))
    atr[0] = tr[0]
    alpha_atr = 2.0 / (ATR_PERIOD + 1)
    for i in range(1, len(tr)):
        atr[i] = alpha_atr * tr[i] + (1 - alpha_atr) * atr[i-1]

    df["atr"] = atr
    return df

def get_open_positions(symbol, magic):
    positions = mt5.positions_get(symbol=symbol)
    if positions is None:
        return []
    return [p for p in positions if p.magic == magic]

def count_positions_by_type(positions):
    buy_count = sell_count = 0
    for p in positions:
        if p.type == mt5.POSITION_TYPE_BUY:
            buy_count += 1
        else:
            sell_count += 1
    return buy_count, sell_count

def normalize_volume(symbol, volume):
    info = get_cached_symbol_info(symbol)
    if info is None:
        return volume
    step = info.volume_step
    min_vol = info.volume_min
    max_vol = info.volume_max
    vol = max(min_vol, min(volume, max_vol))
    return round(round(vol / step) * step, 2)

def get_filling_mode(info):
    if hasattr(info, "filling_mode"):
        fm = info.filling_mode
        if fm == mt5.ORDER_FILLING_RETURN:
            return mt5.ORDER_FILLING_RETURN
        if fm == mt5.ORDER_FILLING_FOK:
            return mt5.ORDER_FILLING_FOK
    return mt5.ORDER_FILLING_IOC

def get_sl_tp_distances(info, atr_value):
    if SLTP_MODE.upper() == "ATR":
        return atr_value * ATR_MULTIPLIER_SL, atr_value * ATR_MULTIPLIER_TP
    return FIXED_SL_POINTS * info.point, FIXED_TP_POINTS * info.point

def get_trailing_distance(info, atr_value):
    if TRAILING_MODE.upper() == "ATR":
        return atr_value * ATR_TRAILING_MULTIPLIER
    return FIXED_TRAILING_POINTS * info.point

# =========================
# CLOSE
# =========================
def close_position(position):
    info = get_cached_symbol_info(position.symbol)
    tick = get_tick(position.symbol)
    if info is None or tick is None:
        return False

    is_buy = position.type == mt5.POSITION_TYPE_BUY
    order_type = mt5.ORDER_TYPE_SELL if is_buy else mt5.ORDER_TYPE_BUY
    price = tick.bid if is_buy else tick.ask

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": position.symbol,
        "position": position.ticket,
        "volume": position.volume,
        "type": order_type,
        "price": round(price, info.digits),
        "deviation": 20,
        "magic": MAGIC_NUMBER,
        "comment": "AUTO CLOSE",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": get_filling_mode(info),
    }

    result = mt5.order_send(request)
    if result is None:
        return False

    if result.retcode == mt5.TRADE_RETCODE_DONE:
        print(f"[{datetime.now()}] [OK] CLOSED {position.ticket} | profit={position.profit:.2f}")
        return True

    print(f"[{datetime.now()}] [-] Close failed {position.ticket}: {retcode_text(result.retcode)}")
    return False

def close_profitable_opposite_positions(positions, close_type):
    profitable = [p for p in positions if p.type == close_type and p.profit > 0]
    if not profitable:
        return 0
    count = 0
    for pos in profitable:
        if close_position(pos):
            count += 1
    return count

# =========================
# SIGNAL
# =========================
def check_signal(df):
    global _last_signal, _signal_count, _last_opposite_close_signal

    if len(df) < EMA_SLOW + 1:
        return None, None

    ema_fast = df["ema_fast"].values[-1]
    ema_slow = df["ema_slow"].values[-1]

    if ema_fast > ema_slow:
        if _last_signal == "BUY":
            _signal_count += 1
        else:
            _last_signal = "BUY"
            _signal_count = 1
            _last_opposite_close_signal = None
    elif ema_fast < ema_slow:
        if _last_signal == "SELL":
            _signal_count += 1
        else:
            _last_signal = "SELL"
            _signal_count = 1
            _last_opposite_close_signal = None
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
    info = get_cached_symbol_info(symbol)
    tick = get_tick(symbol)
    terminal, _ = get_cached_terminal_account()

    if info is None or tick is None or terminal is None:
        return False
    if not terminal.trade_allowed:
        print("[-] AutoTrading OFF")
        return False

    lot = normalize_volume(symbol, lot)
    sl_dist, tp_dist = get_sl_tp_distances(info, atr_value)

    is_buy = order_type == mt5.ORDER_TYPE_BUY
    price = tick.ask if is_buy else tick.bid
    sl = price - sl_dist if is_buy else price + sl_dist
    tp = price + tp_dist if is_buy else price - tp_dist

    min_stop = info.trade_stops_level * info.point

    if is_buy:
        if (price - sl) < min_stop or (tp - price) < min_stop:
            return False
    else:
        if (sl - price) < min_stop or (price - tp) < min_stop:
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
        "comment": "EMA SCALP",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": get_filling_mode(info),
    }

    result = mt5.order_send(request)
    if result is None:
        return False

    if result.retcode == mt5.TRADE_RETCODE_DONE:
        print(f"[{datetime.now()}] [OK] {'BUY' if is_buy else 'SELL'} OPEN | Price: {price:.5f} | SL: {sl:.5f} | TP: {tp:.5f} | Ticket: {result.order}")
        invalidate_cache()
        return True

    if result.retcode not in (10009, 10008):
        print(f"[{datetime.now()}] [-] Order failed: {retcode_text(result.retcode)}")
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
# SMART SL
# =========================
def update_smart_sl_near_tp(positions):
    if not USE_SMART_SL_NEAR_TP:
        return

    info = get_cached_symbol_info(SYMBOL)
    tick = get_tick(SYMBOL)
    if info is None or tick is None:
        return

    min_stop = info.trade_stops_level * info.point
    buffer = SMART_SL_EXTRA_BUFFER_POINTS * info.point

    active_tickets = {p.ticket for p in positions}
    _smart_sl_done_tickets &= active_tickets

    for pos in positions:
        if pos.ticket in _smart_sl_done_tickets:
            continue
        if pos.tp == 0:
            continue

        entry = pos.price_open
        tp = pos.tp
        current_sl = pos.sl
        is_buy = pos.type == mt5.POSITION_TYPE_BUY

        if is_buy:
            current_price = tick.bid
            total_dist = tp - entry
            remaining = tp - current_price
            if total_dist <= 0:
                continue
            trigger = total_dist * SMART_SL_TRIGGER_REMAINING
            if remaining <= trigger:
                new_sl = entry + (total_dist * SMART_SL_LOCK_PERCENT) + buffer
                if new_sl >= current_price or (current_sl != 0 and new_sl <= current_sl):
                    continue
                if (current_price - new_sl) < min_stop:
                    continue
        else:
            current_price = tick.ask
            total_dist = entry - tp
            remaining = current_price - tp
            if total_dist <= 0:
                continue
            trigger = total_dist * SMART_SL_TRIGGER_REMAINING
            if remaining <= trigger:
                new_sl = entry - (total_dist * SMART_SL_LOCK_PERCENT) - buffer
                if new_sl <= current_price or (current_sl != 0 and new_sl >= current_sl):
                    continue
                if (new_sl - current_price) < min_stop:
                    continue

        result = modify_position_sl_tp(pos.ticket, round(new_sl, info.digits), pos.tp)
        if result and result.retcode == mt5.TRADE_RETCODE_DONE:
            print(f"[smart-sl] {'BUY' if is_buy else 'SELL'} {pos.ticket} -> SL {new_sl:.5f}")
            _smart_sl_done_tickets.add(pos.ticket)

# =========================
# TRAILING
# =========================
def update_trailing_stops(positions, atr_value):
    if not USE_TRAILING_STOP:
        return

    info = get_cached_symbol_info(SYMBOL)
    tick = get_tick(SYMBOL)
    if info is None or tick is None:
        return

    trail_dist = get_trailing_distance(info, atr_value)
    min_stop = info.trade_stops_level * info.point

    for pos in positions:
        is_buy = pos.type == mt5.POSITION_TYPE_BUY
        current_price = tick.bid if is_buy else tick.ask

        new_sl = current_price - trail_dist if is_buy else current_price + trail_dist

        if is_buy:
            if pos.sl == 0 or new_sl > pos.sl:
                if (current_price - new_sl) >= min_stop:
                    result = modify_position_sl_tp(pos.ticket, round(new_sl, info.digits), pos.tp)
                    if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                        print(f"[trailing] BUY {pos.ticket} -> SL {new_sl:.5f}")
        else:
            if pos.sl == 0 or new_sl < pos.sl:
                if (new_sl - current_price) >= min_stop:
                    result = modify_position_sl_tp(pos.ticket, round(new_sl, info.digits), pos.tp)
                    if result and result.retcode == mt5.TRADE_RETCODE_DONE:
                        print(f"[trailing] SELL {pos.ticket} -> SL {new_sl:.5f}")

# =========================
# MAIN LOOP
# =========================
def run_forward_test():
    global _last_entry_bar_time_buy, _last_entry_bar_time_sell, _last_opposite_close_signal

    initialize_mt5()

    print(f"\n[{datetime.now()}] Bot EMA Scalper M1 aktif")
    print(f"  EMA: {EMA_FAST}/{EMA_SLOW} | Signal: {MIN_SIGNAL_CANDLES} candle")
    print(f"  Max BUY: {MAX_RUNNING_BUYS} | Max SELL: {MAX_RUNNING_SELLS}")
    print(f"  SLTP: {SLTP_MODE} | Smart SL: {'ON' if USE_SMART_SL_NEAR_TP else 'OFF'}\n")

    while True:
        try:
            spread = get_spread_points(SYMBOL)
            if spread > MAX_SPREAD_POINTS:
                time.sleep(CHECK_INTERVAL)
                continue

            df = get_rates(SYMBOL, TIMEFRAME, 100)
            if df is None:
                time.sleep(CHECK_INTERVAL)
                continue

            df = add_indicators(df)
            last = df.iloc[-1]
            current_bar_time = last["time"]

            positions = get_open_positions(SYMBOL, MAGIC_NUMBER)
            buy_positions, sell_positions = count_positions_by_type(positions)

            if positions:
                update_smart_sl_near_tp(positions)
                update_trailing_stops(positions, last["atr"])

            signal, signal_count = check_signal(df)

            _, account = get_cached_terminal_account()
            balance_str = f"{account.balance:.2f}" if account else "?"

            print(
                f"[{datetime.now().strftime('%H:%M:%S')}] "
                f"S={signal or '-'} C={signal_count or 0} | "
                f"SP={spread:.0f} | B={buy_positions}/{MAX_RUNNING_BUYS} S={sell_positions}/{MAX_RUNNING_SELLS} | "
                f"Ema={'B' if last['ema_fast'] > last['ema_slow'] else 'S'} ATR={last['atr']:.2f} Bal={balance_str}"
            )

            can_entry_buy = _last_entry_bar_time_buy != current_bar_time
            can_entry_sell = _last_entry_bar_time_sell != current_bar_time

            if signal == "BUY" and signal_count >= OPPOSITE_CLOSE_SIGNAL_COUNT and sell_positions > 0 and _last_opposite_close_signal != "BUY":
                closed = close_profitable_opposite_positions(positions, mt5.POSITION_TYPE_SELL)
                print(f"[{datetime.now()}] Closed {closed} profitable SELL - signal BUY {signal_count}x")
                _last_opposite_close_signal = "BUY"
                positions = get_open_positions(SYMBOL, MAGIC_NUMBER)
                buy_positions, sell_positions = count_positions_by_type(positions)

            elif signal == "SELL" and signal_count >= OPPOSITE_CLOSE_SIGNAL_COUNT and buy_positions > 0 and _last_opposite_close_signal != "SELL":
                closed = close_profitable_opposite_positions(positions, mt5.POSITION_TYPE_BUY)
                print(f"[{datetime.now()}] Closed {closed} profitable BUY - signal SELL {signal_count}x")
                _last_opposite_close_signal = "SELL"
                positions = get_open_positions(SYMBOL, MAGIC_NUMBER)
                buy_positions, sell_positions = count_positions_by_type(positions)

            if signal == "BUY" and can_entry_buy and buy_positions < MAX_RUNNING_BUYS:
                if send_order(SYMBOL, LOTS, mt5.ORDER_TYPE_BUY, last["atr"], MAGIC_NUMBER):
                    _last_entry_bar_time_buy = current_bar_time

            elif signal == "SELL" and can_entry_sell and sell_positions < MAX_RUNNING_SELLS:
                if send_order(SYMBOL, LOTS, mt5.ORDER_TYPE_SELL, last["atr"], MAGIC_NUMBER):
                    _last_entry_bar_time_sell = current_bar_time

            time.sleep(CHECK_INTERVAL)

        except KeyboardInterrupt:
            print("\n[!] Bot dihentikan")
            break
        except Exception as e:
            print(f"[{datetime.now()}] Error: {e}")
            invalidate_cache()
            time.sleep(1)

    mt5.shutdown()

if __name__ == "__main__":
    run_forward_test()