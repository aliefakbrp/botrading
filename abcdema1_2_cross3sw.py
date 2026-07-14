import MetaTrader5 as mt5
import pandas as pd
import time
from datetime import datetime

# =========================
# CONFIG
# =========================
SYMBOL = "XAUUSD"
TIMEFRAME = mt5.TIMEFRAME_M1
# TIMEFRAME = mt5.TIMEFRAME_M5
LOTS = 0.01
MAGIC_NUMBER = 26042026
CHECK_INTERVAL = 1.0  # detik

# EMA
EMA_FAST = 1
EMA_SLOW = 2

# =========================
# SIDEWAYS FILTER M5
# =========================
USE_SIDEWAYS_FILTER = True
ADX_PERIOD = 14
ADX_SIDEWAYS_LEVEL = 20.0

# Untuk XAU M5 EMA 1/2
SIDEWAYS_EMA_DISTANCE = 0.40
SIDEWAYS_CROSS_LOOKBACK = 10
SIDEWAYS_MAX_CROSS = 3

# Spread filter
MAX_SPREAD_POINTS = 300

# Delay setelah close sebelum open lawan
REVERSE_DELAY_SECONDS = 0.8

# Konfirmasi entry awal / cross
ENTRY_CONFIRM_SECONDS = 2.0

# Konfirmasi saat posisi yang sedang terbuka berlawanan arah EMA
REVERSE_CONFIRM_SECONDS = 5.0

# =========================
# STATE
# =========================
_last_cross_key = None
_reverse_pending_since = None
_reverse_pending_direction = None

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
        print("last_error init:", mt5.last_error())
        quit()

    terminal = mt5.terminal_info()
    account = mt5.account_info()

    if terminal is None:
        print("[-] Gagal ambil terminal info")
        print("last_error terminal:", mt5.last_error())
        quit()

    if account is None:
        print("[-] Gagal ambil info akun")
        print("last_error account:", mt5.last_error())
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
        print("last_error symbol_info:", mt5.last_error())
        mt5.shutdown()
        quit()

    if not symbol_info.visible:
        ok = mt5.symbol_select(SYMBOL, True)
        if not ok:
            print(f"[-] Gagal menampilkan symbol {SYMBOL}")
            print("last_error symbol_select:", mt5.last_error())
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


def get_rates(symbol, timeframe, bars=300):
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, bars)
    if rates is None or len(rates) == 0:
        return None

    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    return df


def add_indicators(df):
    df["ema_fast"] = df["close"].ewm(span=EMA_FAST, adjust=False).mean()
    df["ema_slow"] = df["close"].ewm(span=EMA_SLOW, adjust=False).mean()

    # =========================
    # ADX
    # =========================
    high = df["high"]
    low = df["low"]
    close = df["close"]

    up_move = high.diff()
    down_move = -low.diff()

    plus_dm = up_move.where((up_move > down_move) & (up_move > 0), 0.0)
    minus_dm = down_move.where((down_move > up_move) & (down_move > 0), 0.0)

    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()

    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1 / ADX_PERIOD, adjust=False).mean()

    plus_di = 100 * plus_dm.ewm(alpha=1 / ADX_PERIOD, adjust=False).mean() / atr
    minus_di = 100 * minus_dm.ewm(alpha=1 / ADX_PERIOD, adjust=False).mean() / atr

    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di)
    df["adx"] = dx.ewm(alpha=1 / ADX_PERIOD, adjust=False).mean().fillna(0)

    return df


def get_open_positions(symbol, magic):
    positions = mt5.positions_get(symbol=symbol)
    if positions is None:
        return []
    return [p for p in positions if p.magic == magic]


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
    if info is None:
        return mt5.ORDER_FILLING_IOC

    try:
        if hasattr(info, "filling_mode"):
            if info.filling_mode == mt5.ORDER_FILLING_FOK:
                return mt5.ORDER_FILLING_FOK
            if info.filling_mode == mt5.ORDER_FILLING_IOC:
                return mt5.ORDER_FILLING_IOC
            if info.filling_mode == mt5.ORDER_FILLING_RETURN:
                return mt5.ORDER_FILLING_RETURN
    except Exception:
        pass

    return mt5.ORDER_FILLING_IOC


# =========================
# EMA DIRECTION / CROSS
# =========================
def get_current_ema_direction(df):
    if len(df) < 10:
        return None, None

    current_candle = df.iloc[-1]
    curr_fast = current_candle["ema_fast"]
    curr_slow = current_candle["ema_slow"]

    if curr_fast > curr_slow:
        return "BUY", current_candle
    elif curr_fast < curr_slow:
        return "SELL", current_candle
    else:
        return None, current_candle


def check_cross_signal_realtime(df):
    if len(df) < 10:
        return None, None, None, None

    prev_candle = df.iloc[-2]
    current_candle = df.iloc[-1]

    prev_fast = prev_candle["ema_fast"]
    prev_slow = prev_candle["ema_slow"]
    curr_fast = current_candle["ema_fast"]
    curr_slow = current_candle["ema_slow"]

    current_bar_time = current_candle["time"]

    buy_cross = (prev_fast <= prev_slow) and (curr_fast > curr_slow)
    sell_cross = (prev_fast >= prev_slow) and (curr_fast < curr_slow)

    if buy_cross:
        return "BUY", current_bar_time, (str(current_bar_time), "BUY"), current_candle
    if sell_cross:
        return "SELL", current_bar_time, (str(current_bar_time), "SELL"), current_candle

    return None, current_bar_time, None, current_candle


# =========================
# SIDEWAYS FILTER
# =========================
def count_ema_crosses(df, lookback=10):
    if len(df) < lookback + 2:
        return 0

    recent = df.tail(lookback + 1).copy()

    prev_fast = recent["ema_fast"].shift(1)
    prev_slow = recent["ema_slow"].shift(1)
    curr_fast = recent["ema_fast"]
    curr_slow = recent["ema_slow"]

    buy_cross = (prev_fast <= prev_slow) & (curr_fast > curr_slow)
    sell_cross = (prev_fast >= prev_slow) & (curr_fast < curr_slow)

    cross_count = (buy_cross | sell_cross).sum()
    return int(cross_count)


def check_sideways_m5(df):
    if not USE_SIDEWAYS_FILTER:
        return False, {}

    if len(df) < SIDEWAYS_CROSS_LOOKBACK + ADX_PERIOD + 5:
        return False, {}

    current_candle = df.iloc[-1]

    ema_distance = abs(current_candle["ema_fast"] - current_candle["ema_slow"])
    adx = current_candle["adx"]
    cross_count = count_ema_crosses(df, SIDEWAYS_CROSS_LOOKBACK)

    ema_too_close = ema_distance < SIDEWAYS_EMA_DISTANCE
    cross_too_often = cross_count >= SIDEWAYS_MAX_CROSS
    adx_weak = adx < ADX_SIDEWAYS_LEVEL

    is_sideways = adx_weak and (ema_too_close or cross_too_often)

    info = {
        "ema_distance": ema_distance,
        "adx": adx,
        "cross_count": cross_count,
        "ema_too_close": ema_too_close,
        "cross_too_often": cross_too_often,
        "adx_weak": adx_weak,
    }

    return is_sideways, info


def confirm_signal_after_delay(symbol, timeframe, expected_signal, wait_seconds=2.0):
    time.sleep(wait_seconds)

    df = get_rates(symbol, timeframe, 300)
    if df is None:
        print(f"[{datetime.now()}] Gagal ambil data saat konfirmasi sinyal")
        print(f"[{datetime.now()}] last_error confirm rates = {mt5.last_error()}")
        return False, None

    df = add_indicators(df)

    is_sideways, sideways_info = check_sideways_m5(df)
    if is_sideways:
        print(
            f"[{datetime.now()}] Entry {expected_signal} batal karena market SIDEWAYS saat konfirmasi | "
            f"ADX={sideways_info['adx']:.2f} | "
            f"EmaDist={sideways_info['ema_distance']:.2f} | "
            f"Cross{SIDEWAYS_CROSS_LOOKBACK}={sideways_info['cross_count']}"
        )
        return False, None

    current_candle = df.iloc[-1]

    curr_fast = current_candle["ema_fast"]
    curr_slow = current_candle["ema_slow"]

    if expected_signal == "BUY":
        valid = curr_fast > curr_slow
    else:
        valid = curr_fast < curr_slow

    return valid, current_candle


# =========================
# ORDER OPEN
# =========================
def send_order(symbol, lot, order_type, magic):
    info = get_symbol_info(symbol)
    tick = get_tick(symbol)

    if info is None or tick is None:
        print("[-] Gagal ambil symbol info / tick")
        print("last_error open precheck:", mt5.last_error())
        return False

    terminal = mt5.terminal_info()
    if terminal is None or not terminal.trade_allowed:
        print("[-] Algo Trading / AutoTrading MT5 masih OFF")
        print("last_error terminal open:", mt5.last_error())
        return False

    lot = normalize_volume(symbol, lot)
    filling = get_filling_mode(info)

    if order_type == mt5.ORDER_TYPE_BUY:
        price = tick.ask
        side = "BUY"
    else:
        price = tick.bid
        side = "SELL"

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": lot,
        "type": order_type,
        "price": round(price, info.digits),
        "deviation": 20,
        "magic": magic,
        "comment": "EMA12",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": filling,
    }

    print(f"[DEBUG OPEN] symbol={symbol}, ask={tick.ask}, bid={tick.bid}, filling={filling}")
    print(f"[DEBUG OPEN] last_error before send = {mt5.last_error()}")
    print("REQUEST OPEN:", request)

    result = mt5.order_send(request)

    if result is None:
        print(f"[{datetime.now()}] [-] order_send gagal (result None)")
        print(f"[{datetime.now()}] last_error open = {mt5.last_error()}")
        return False

    print(f"[{datetime.now()}] retcode open={result.retcode} ({retcode_text(result.retcode)})")

    if result.retcode == mt5.TRADE_RETCODE_DONE:
        print(f"[{datetime.now()}] [OK] {side} OPEN")
        print(f"  Price : {round(price, info.digits)}")
        print(f"  Ticket: {result.order}")
        return True

    print(f"[{datetime.now()}] [-] Order open gagal | {retcode_text(result.retcode)}")
    return False


# =========================
# ORDER CLOSE
# =========================
def close_position(position):
    info = get_symbol_info(position.symbol)
    tick = get_tick(position.symbol)

    if info is None or tick is None:
        print(f"[-] Gagal ambil info/tick untuk close posisi {position.ticket}")
        print(f"[{datetime.now()}] last_error close precheck = {mt5.last_error()}")
        return False

    if position.type == mt5.POSITION_TYPE_BUY:
        close_type = mt5.ORDER_TYPE_SELL
        price = tick.bid
        side = "BUY"
    else:
        close_type = mt5.ORDER_TYPE_BUY
        price = tick.ask
        side = "SELL"

    filling = get_filling_mode(info)

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": position.symbol,
        "position": position.ticket,
        "volume": position.volume,
        "type": close_type,
        "price": round(price, info.digits),
        "deviation": 20,
        "magic": MAGIC_NUMBER,
        "comment": "XREV",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": filling,
    }

    print(f"[DEBUG CLOSE] symbol={position.symbol}, ask={tick.ask}, bid={tick.bid}, filling={filling}")
    print(f"[DEBUG CLOSE] last_error before send = {mt5.last_error()}")
    print("REQUEST CLOSE:", request)

    result = mt5.order_send(request)

    if result is None:
        print(f"[{datetime.now()}] [-] Close gagal (result None) | ticket {position.ticket}")
        print(f"[{datetime.now()}] last_error close = {mt5.last_error()}")
        return False

    print(f"[{datetime.now()}] retcode close={result.retcode} ({retcode_text(result.retcode)})")

    if result.retcode == mt5.TRADE_RETCODE_DONE:
        print(f"[{datetime.now()}] [OK] CLOSE {side} | ticket {position.ticket}")
        return True

    print(f"[{datetime.now()}] [-] Close gagal | ticket {position.ticket} | {retcode_text(result.retcode)}")
    return False


def close_all_positions(positions):
    all_closed = True
    for pos in positions:
        ok = close_position(pos)
        if not ok:
            all_closed = False
        time.sleep(0.15)
    return all_closed


# =========================
# MAIN LOOP
# =========================
def run_forward_test():
    global _last_cross_key, _reverse_pending_since, _reverse_pending_direction

    initialize_mt5()

    print(f"\n[{datetime.now()}] Bot EMA Realtime Cross Reversal aktif")
    print(f"  Symbol: {SYMBOL}")
    print(f"  Timeframe: M5")
    print(f"  EMA Fast / Slow: {EMA_FAST}/{EMA_SLOW}")
    print(f"  Entry awal: cross realtime + konfirmasi {ENTRY_CONFIRM_SECONDS} detik")
    print(f"  Reverse posisi salah arah: konfirmasi {REVERSE_CONFIRM_SECONDS} detik")
    print(f"  Sideways filter M5: {'ON' if USE_SIDEWAYS_FILTER else 'OFF'}")
    print(f"  Sideways rule: ADX < {ADX_SIDEWAYS_LEVEL}, EmaDist < {SIDEWAYS_EMA_DISTANCE}, Cross{SIDEWAYS_CROSS_LOOKBACK} >= {SIDEWAYS_MAX_CROSS}")
    print(f"  TP/SL fixed: OFF")
    print(f"  Reverse posisi: ON")
    print("")

    while True:
        try:
            spread = get_spread_points(SYMBOL)
            if spread > MAX_SPREAD_POINTS:
                print(f"[{datetime.now()}] Spread terlalu besar: {spread:.1f}")
                time.sleep(CHECK_INTERVAL)
                continue

            df = get_rates(SYMBOL, TIMEFRAME, 300)
            if df is None:
                print(f"[{datetime.now()}] Gagal ambil data candle")
                print(f"[{datetime.now()}] last_error rates = {mt5.last_error()}")
                time.sleep(CHECK_INTERVAL)
                continue

            df = add_indicators(df)

            signal, signal_bar_time, cross_key, current_candle = check_cross_signal_realtime(df)
            current_direction, current_candle = get_current_ema_direction(df)
            is_sideways, sideways_info = check_sideways_m5(df)

            tick = get_tick(SYMBOL)
            info = get_symbol_info(SYMBOL)
            positions = get_open_positions(SYMBOL, MAGIC_NUMBER)
            total_positions = len(positions)

            ema_state = "Bullish" if current_direction == "BUY" else "Bearish" if current_direction == "SELL" else "-"

            pos_text = "-"
            entry_price_str = "-"
            current_price_str = "-"
            profit_str = "-"
            current_position_type = None

            if total_positions > 0 and tick is not None and info is not None:
                p = positions[0]
                is_buy = p.type == mt5.POSITION_TYPE_BUY

                current_position_type = "BUY" if is_buy else "SELL"
                pos_text = current_position_type
                entry_price_str = f"{p.price_open:.{info.digits}f}"
                current_price = tick.bid if is_buy else tick.ask
                current_price_str = f"{current_price:.{info.digits}f}"
                profit_str = f"{p.profit:.2f}"

            account = mt5.account_info()
            balance_str = f"{account.balance:.2f}" if account else "?"

            reverse_wait_str = "-"
            if _reverse_pending_since is not None:
                elapsed = time.time() - _reverse_pending_since
                reverse_wait_str = f"{elapsed:.1f}s->{_reverse_pending_direction}"

            market_status = "SIDEWAYS" if is_sideways else "TRENDING"

            adx_str = "-"
            ema_dist_str = "-"
            cross_count_str = "-"

            if sideways_info:
                adx_str = f"{sideways_info['adx']:.2f}"
                ema_dist_str = f"{sideways_info['ema_distance']:.2f}"
                cross_count_str = str(sideways_info["cross_count"])

            print(
                f"[{datetime.now()}] "
                f"Market={market_status} | "
                f"Signal={signal or '-'} | "
                f"Dir={current_direction or '-'} | "
                f"Spread={spread:.1f} | "
                f"OpenPos={total_positions} ({pos_text}) | "
                f"Entry={entry_price_str} | "
                f"Now={current_price_str} | "
                f"P/L={profit_str} | "
                f"RevWait={reverse_wait_str} | "
                f"EMA={ema_state} | "
                f"Fast={current_candle['ema_fast']:.5f} | "
                f"Slow={current_candle['ema_slow']:.5f} | "
                f"ADX={adx_str} | "
                f"EmaDist={ema_dist_str} | "
                f"Cross{SIDEWAYS_CROSS_LOOKBACK}={cross_count_str} | "
                f"Balance={balance_str}"
            )

            # =========================
            # SIDEWAYS FILTER
            # =========================
            if is_sideways:
                _reverse_pending_since = None
                _reverse_pending_direction = None

                print(
                    f"[{datetime.now()}] Market SIDEWAYS M5, skip entry/reverse | "
                    f"ADX={sideways_info['adx']:.2f} | "
                    f"EmaDist={sideways_info['ema_distance']:.2f} | "
                    f"Cross{SIDEWAYS_CROSS_LOOKBACK}={sideways_info['cross_count']}"
                )

                time.sleep(CHECK_INTERVAL)
                continue

            # =========================
            # 1) ENTRY AWAL SAAT BELUM ADA POSISI
            # =========================
            if total_positions == 0 and signal is not None and cross_key != _last_cross_key:
                print(f"[{datetime.now()}] REALTIME CROSS {signal} terdeteksi di candle {signal_bar_time}")
                print(f"[{datetime.now()}] Tunggu konfirmasi entry {ENTRY_CONFIRM_SECONDS} detik...")

                confirmed, confirmed_candle = confirm_signal_after_delay(
                    SYMBOL,
                    TIMEFRAME,
                    signal,
                    ENTRY_CONFIRM_SECONDS
                )

                if not confirmed:
                    print(f"[{datetime.now()}] Entry {signal} batal, setelah {ENTRY_CONFIRM_SECONDS} detik EMA sudah berubah / sideways.")
                    time.sleep(CHECK_INTERVAL)
                    continue

                print(
                    f"[{datetime.now()}] Entry {signal} valid setelah {ENTRY_CONFIRM_SECONDS} detik | "
                    f"Fast={confirmed_candle['ema_fast']:.5f} | Slow={confirmed_candle['ema_slow']:.5f}"
                )

                mt5.symbol_select(SYMBOL, True)
                time.sleep(0.2)
                refreshed_tick = get_tick(SYMBOL)

                if refreshed_tick is None:
                    print(f"[{datetime.now()}] Tick tidak tersedia, open dibatalkan.")
                    print(f"[{datetime.now()}] last_error tick refresh = {mt5.last_error()}")
                else:
                    if signal == "BUY":
                        ok = send_order(SYMBOL, LOTS, mt5.ORDER_TYPE_BUY, MAGIC_NUMBER)
                        if ok:
                            _last_cross_key = cross_key
                    elif signal == "SELL":
                        ok = send_order(SYMBOL, LOTS, mt5.ORDER_TYPE_SELL, MAGIC_NUMBER)
                        if ok:
                            _last_cross_key = cross_key

                time.sleep(CHECK_INTERVAL)
                continue

            # =========================
            # 2) POSISI SUDAH ADA -> CEK APAKAH BERLAWANAN DENGAN ARAH EMA
            # =========================
            if total_positions > 0 and current_position_type is not None and current_direction is not None:
                if current_position_type != current_direction:
                    if _reverse_pending_since is None or _reverse_pending_direction != current_direction:
                        _reverse_pending_since = time.time()
                        _reverse_pending_direction = current_direction
                        print(
                            f"[{datetime.now()}] Posisi {current_position_type} berlawanan dengan arah EMA {current_direction}. "
                            f"Mulai tunggu {REVERSE_CONFIRM_SECONDS} detik..."
                        )
                    else:
                        elapsed = time.time() - _reverse_pending_since
                        if elapsed >= REVERSE_CONFIRM_SECONDS:
                            print(
                                f"[{datetime.now()}] Arah EMA {current_direction} bertahan {REVERSE_CONFIRM_SECONDS} detik. "
                                f"Close {current_position_type} lalu open {current_direction}."
                            )

                            positions = get_open_positions(SYMBOL, MAGIC_NUMBER)

                            if positions:
                                close_all_positions(positions)
                                time.sleep(REVERSE_DELAY_SECONDS)

                            positions_after_close = get_open_positions(SYMBOL, MAGIC_NUMBER)
                            if positions_after_close:
                                print(f"[{datetime.now()}] Masih ada posisi yang belum tertutup, reverse dibatalkan.")
                            else:
                                mt5.symbol_select(SYMBOL, True)
                                time.sleep(0.2)
                                refreshed_tick = get_tick(SYMBOL)

                                if refreshed_tick is None:
                                    print(f"[{datetime.now()}] Tick tidak tersedia, open reverse dibatalkan.")
                                    print(f"[{datetime.now()}] last_error tick refresh = {mt5.last_error()}")
                                else:
                                    if current_direction == "BUY":
                                        ok = send_order(SYMBOL, LOTS, mt5.ORDER_TYPE_BUY, MAGIC_NUMBER)
                                    else:
                                        ok = send_order(SYMBOL, LOTS, mt5.ORDER_TYPE_SELL, MAGIC_NUMBER)

                                    if ok:
                                        _reverse_pending_since = None
                                        _reverse_pending_direction = None
                                        _last_cross_key = None
                else:
                    # posisi sudah sesuai arah EMA, reset timer reverse
                    _reverse_pending_since = None
                    _reverse_pending_direction = None
            else:
                _reverse_pending_since = None
                _reverse_pending_direction = None

            time.sleep(CHECK_INTERVAL)

        except KeyboardInterrupt:
            print("\n[!] Bot dihentikan manual")
            break
        except Exception as e:
            print(f"[{datetime.now()}] Error: {e}")
            print(f"[{datetime.now()}] last_error exception = {mt5.last_error()}")
            time.sleep(2)

    mt5.shutdown()


if __name__ == "__main__":
    run_forward_test()