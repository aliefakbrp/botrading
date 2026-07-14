# EMA 21 M15 + RSI FILTER
# Entry:
# - Harga di atas EMA21 = kandidat BUY
# - Harga di bawah EMA21 = kandidat SELL
#
# Filter RSI:
# - BUY dilarang kalau RSI sekarang > RSI sebelumnya,
#   kecuali harga baru cross dari bawah EMA21 ke atas EMA21.
#
# - SELL dilarang kalau RSI sekarang < RSI sebelumnya,
#   kecuali harga baru cross dari atas EMA21 ke bawah EMA21.
#
# Close / Reverse:
# - Kalau posisi BUY lalu harga di bawah EMA21:
#   tunggu 10 detik, cek ulang.
#   Kalau masih di bawah EMA21 => close BUY lalu coba open SELL.
#
# - Kalau posisi SELL lalu harga di atas EMA21:
#   tunggu 10 detik, cek ulang.
#   Kalau masih di atas EMA21 => close SELL lalu coba open BUY.
#
# Re-entry:
# - Kalau sudah close / cut loss dan signal masih valid,
#   boleh entry lagi sesuai arah EMA21 + filter RSI.

import MetaTrader5 as mt5
import pandas as pd
import time
from datetime import datetime

# =========================
# CONFIG
# =========================
SYMBOL = "XAUUSD"
TIMEFRAME = mt5.TIMEFRAME_M15

LOTS = 0.1
MAGIC_NUMBER = 26042026
CHECK_INTERVAL = 2.0  # cek tiap 2 detik

# EMA
EMA_FAST = 21
EMA_SLOW = 144  # masih dihitung untuk monitoring saja

# RSI
RSI_PERIOD = 14

# Spread filter
MAX_SPREAD_POINTS = 300

# Tunggu 10 detik sebelum close dan reverse
REVERSE_DELAY_SECONDS = 10

# =========================
# CUT LOSS
# =========================
CUT_LOSS_PIPS = 100

# Untuk XAUUSD:
# Umumnya 1 pip = 0.10, jadi 100 pips = 10.00 harga.
# Kalau broker kamu hitung 1 pip = 0.01, ubah PIP_VALUE jadi 0.01.
PIP_VALUE = 0.10

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


def get_rates(symbol, timeframe, bars=400):
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, bars)

    if rates is None or len(rates) == 0:
        return None

    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")

    return df


def calculate_rsi(series, period=14):
    delta = series.diff()

    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)

    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))

    return rsi


def add_indicators(df):
    df["ema_fast"] = df["close"].ewm(span=EMA_FAST, adjust=False).mean()
    df["ema_slow"] = df["close"].ewm(span=EMA_SLOW, adjust=False).mean()
    df["rsi"] = calculate_rsi(df["close"], RSI_PERIOD)
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


def get_position_loss_pips(position):
    tick = get_tick(position.symbol)

    if tick is None:
        return 0

    if position.type == mt5.POSITION_TYPE_BUY:
        current_price = tick.bid
        loss_price = position.price_open - current_price
    else:
        current_price = tick.ask
        loss_price = current_price - position.price_open

    loss_pips = loss_price / PIP_VALUE
    return loss_pips


# =========================
# EMA + RSI LOGIC
# =========================
def get_ema_state(df):
    """
    Logic utama:
    - Harga di atas EMA21 = arah BUY
    - Harga di bawah EMA21 = arah SELL

    Filter RSI:
    - BUY dilarang kalau RSI sekarang > RSI sebelumnya,
      kecuali baru cross ke atas EMA21.

    - SELL dilarang kalau RSI sekarang < RSI sebelumnya,
      kecuali baru cross ke bawah EMA21.

    df.iloc[-1] = candle M15 berjalan/realtime.
    Kalau mau pakai candle yang sudah close saja, ubah:
        current_candle = df.iloc[-2]
        prev_candle = df.iloc[-3]
    """

    if len(df) < EMA_SLOW + RSI_PERIOD + 5:
        return None

    prev_candle = df.iloc[-2]
    current_candle = df.iloc[-1]

    close_price = current_candle["close"]
    prev_close_price = prev_candle["close"]

    ema21 = current_candle["ema_fast"]
    prev_ema21 = prev_candle["ema_fast"]

    ema144 = current_candle["ema_slow"]

    rsi_now = current_candle["rsi"]
    rsi_prev = prev_candle["rsi"]

    if pd.isna(rsi_now) or pd.isna(rsi_prev):
        return None

    price_above_ema21 = close_price > ema21
    price_below_ema21 = close_price < ema21

    prev_price_above_ema21 = prev_close_price > prev_ema21
    prev_price_below_ema21 = prev_close_price < prev_ema21

    fresh_cross_above_ema21 = price_above_ema21 and not prev_price_above_ema21
    fresh_cross_below_ema21 = price_below_ema21 and not prev_price_below_ema21

    rsi_up = rsi_now > rsi_prev
    rsi_down = rsi_now < rsi_prev

    buy_blocked_by_rsi = price_above_ema21 and rsi_up and not fresh_cross_above_ema21
    sell_blocked_by_rsi = price_below_ema21 and rsi_down and not fresh_cross_below_ema21

    buy_allowed = price_above_ema21 and not buy_blocked_by_rsi
    sell_allowed = price_below_ema21 and not sell_blocked_by_rsi

    if price_above_ema21:
        direction = "BUY"
    elif price_below_ema21:
        direction = "SELL"
    else:
        direction = None

    return {
        "bar_time": current_candle["time"],
        "close": close_price,
        "ema_fast": ema21,
        "ema_slow": ema144,
        "rsi_now": rsi_now,
        "rsi_prev": rsi_prev,
        "rsi_up": rsi_up,
        "rsi_down": rsi_down,
        "price_above_ema21": price_above_ema21,
        "price_below_ema21": price_below_ema21,
        "fresh_cross_above_ema21": fresh_cross_above_ema21,
        "fresh_cross_below_ema21": fresh_cross_below_ema21,
        "buy_blocked_by_rsi": buy_blocked_by_rsi,
        "sell_blocked_by_rsi": sell_blocked_by_rsi,
        "buy_allowed": buy_allowed,
        "sell_allowed": sell_allowed,
        "direction": direction,
        "current_candle": current_candle,
    }


def get_entry_signal_by_ema21(ema_state):
    """
    Entry:
    - BUY kalau harga di atas EMA21 dan lolos filter RSI
    - SELL kalau harga di bawah EMA21 dan lolos filter RSI
    """

    if ema_state["buy_allowed"]:
        return "BUY"

    if ema_state["sell_allowed"]:
        return "SELL"

    return None


def get_close_signal_by_ema21(position, ema_state):
    """
    Close / reverse:
    - Posisi BUY close kalau harga di bawah EMA21
    - Posisi SELL close kalau harga di atas EMA21

    Close tidak pakai filter RSI.
    Filter RSI hanya dipakai untuk open/re-entry.
    """

    if position.type == mt5.POSITION_TYPE_BUY and ema_state["price_below_ema21"]:
        return "CLOSE_BUY_REVERSE_TO_SELL"

    if position.type == mt5.POSITION_TYPE_SELL and ema_state["price_above_ema21"]:
        return "CLOSE_SELL_REVERSE_TO_BUY"

    return None


def get_fresh_ema_state():
    """
    Ambil data candle terbaru dan hitung ulang EMA + RSI.
    Dipakai setelah delay 10 detik supaya konfirmasi benar-benar data terbaru.
    """

    df = get_rates(SYMBOL, TIMEFRAME, 400)

    if df is None:
        return None

    df = add_indicators(df)
    return get_ema_state(df)


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
        "comment": "EMA21_RSI_M15",
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
        "comment": "EMA21_RSI_CLOSE",
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


def open_by_signal(signal):
    mt5.symbol_select(SYMBOL, True)
    time.sleep(0.2)

    refreshed_tick = get_tick(SYMBOL)

    if refreshed_tick is None:
        print(f"[{datetime.now()}] Tick tidak tersedia, open {signal} dibatalkan.")
        print(f"[{datetime.now()}] last_error tick refresh = {mt5.last_error()}")
        return False

    if signal == "BUY":
        return send_order(SYMBOL, LOTS, mt5.ORDER_TYPE_BUY, MAGIC_NUMBER)

    if signal == "SELL":
        return send_order(SYMBOL, LOTS, mt5.ORDER_TYPE_SELL, MAGIC_NUMBER)

    return False


# =========================
# CUT LOSS
# =========================
def check_cut_loss_positions():
    positions = get_open_positions(SYMBOL, MAGIC_NUMBER)

    if not positions:
        return False

    closed_any = False

    for pos in positions:
        loss_pips = get_position_loss_pips(pos)
        pos_type = "BUY" if pos.type == mt5.POSITION_TYPE_BUY else "SELL"

        if loss_pips >= CUT_LOSS_PIPS:
            print(
                f"[{datetime.now()}] CUT LOSS kena | "
                f"Posisi={pos_type} | "
                f"Ticket={pos.ticket} | "
                f"Loss={loss_pips:.1f} pips >= {CUT_LOSS_PIPS} pips"
            )

            ok = close_position(pos)

            if ok:
                closed_any = True

            time.sleep(0.15)

    return closed_any


# =========================
# MAIN LOOP
# =========================
def run_forward_test():
    initialize_mt5()

    print(f"\n[{datetime.now()}] Bot EMA21 + RSI Filter M15 aktif")
    print(f"  Symbol: {SYMBOL}")
    print(f"  Timeframe: M15")
    print(f"  EMA Entry: EMA{EMA_FAST}")
    print(f"  EMA Monitoring: EMA{EMA_SLOW}")
    print(f"  RSI Period: {RSI_PERIOD}")
    print(f"  Check interval: {CHECK_INTERVAL} detik")
    print(f"  Entry BUY : Harga di atas EMA21, tapi tidak BUY kalau RSI naik, kecuali fresh cross above EMA21")
    print(f"  Entry SELL: Harga di bawah EMA21, tapi tidak SELL kalau RSI turun, kecuali fresh cross below EMA21")
    print(f"  Close BUY : Harga di bawah EMA21, tunggu {REVERSE_DELAY_SECONDS} detik, lalu konfirmasi")
    print(f"  Close SELL: Harga di atas EMA21, tunggu {REVERSE_DELAY_SECONDS} detik, lalu konfirmasi")
    print(f"  Cut Loss: {CUT_LOSS_PIPS} pips")
    print(f"  PIP_VALUE: {PIP_VALUE}")
    print(f"  TP/SL fixed broker: OFF")
    print("")

    while True:
        try:
            spread = get_spread_points(SYMBOL)

            if spread > MAX_SPREAD_POINTS:
                print(f"[{datetime.now()}] Spread terlalu besar: {spread:.1f}")
                time.sleep(CHECK_INTERVAL)
                continue

            df = get_rates(SYMBOL, TIMEFRAME, 400)

            if df is None:
                print(f"[{datetime.now()}] Gagal ambil data candle")
                print(f"[{datetime.now()}] last_error rates = {mt5.last_error()}")
                time.sleep(CHECK_INTERVAL)
                continue

            df = add_indicators(df)
            ema_state = get_ema_state(df)

            if ema_state is None:
                print(f"[{datetime.now()}] Data belum cukup untuk EMA/RSI")
                time.sleep(CHECK_INTERVAL)
                continue

            current_direction = ema_state["direction"]
            current_candle = ema_state["current_candle"]

            tick = get_tick(SYMBOL)
            info = get_symbol_info(SYMBOL)

            # =========================
            # CEK CUT LOSS DULU
            # =========================
            cl_closed = check_cut_loss_positions()

            if cl_closed:
                print(f"[{datetime.now()}] Ada posisi yang kena CL. Tunggu {REVERSE_DELAY_SECONDS} detik sebelum re-entry.")
                time.sleep(REVERSE_DELAY_SECONDS)

                positions_after_cl = get_open_positions(SYMBOL, MAGIC_NUMBER)

                if positions_after_cl:
                    print(f"[{datetime.now()}] Masih ada posisi setelah CL, entry ulang dibatalkan.")
                    time.sleep(CHECK_INTERVAL)
                    continue

                ema_after_cl = get_fresh_ema_state()

                if ema_after_cl is None:
                    print(f"[{datetime.now()}] Setelah CL, gagal ambil EMA/RSI terbaru.")
                    time.sleep(CHECK_INTERVAL)
                    continue

                reentry_signal = get_entry_signal_by_ema21(ema_after_cl)

                if reentry_signal is None:
                    print(
                        f"[{datetime.now()}] Setelah CL, re-entry diblokir. "
                        f"RSI Now={ema_after_cl['rsi_now']:.2f} | "
                        f"RSI Prev={ema_after_cl['rsi_prev']:.2f} | "
                        f"BuyBlocked={ema_after_cl['buy_blocked_by_rsi']} | "
                        f"SellBlocked={ema_after_cl['sell_blocked_by_rsi']}"
                    )
                    time.sleep(CHECK_INTERVAL)
                    continue

                print(f"[{datetime.now()}] Setelah CL, open ulang sesuai EMA21 + RSI: {reentry_signal}")
                open_by_signal(reentry_signal)

                time.sleep(CHECK_INTERVAL)
                continue

            positions = get_open_positions(SYMBOL, MAGIC_NUMBER)
            total_positions = len(positions)

            ema_state_text = (
                "Harga di atas EMA21" if current_direction == "BUY"
                else "Harga di bawah EMA21" if current_direction == "SELL"
                else "Harga pas EMA21"
            )

            ema_side_text = (
                "ABOVE_EMA21" if ema_state["price_above_ema21"]
                else "BELOW_EMA21" if ema_state["price_below_ema21"]
                else "TOUCH_EMA21"
            )

            rsi_text = (
                "RSI_UP" if ema_state["rsi_up"]
                else "RSI_DOWN" if ema_state["rsi_down"]
                else "RSI_FLAT"
            )

            cross_text = (
                "FRESH_CROSS_ABOVE" if ema_state["fresh_cross_above_ema21"]
                else "FRESH_CROSS_BELOW" if ema_state["fresh_cross_below_ema21"]
                else "-"
            )

            pos_text = "-"
            entry_price_str = "-"
            current_price_str = "-"
            profit_str = "-"
            loss_pips_str = "-"
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

                loss_pips = get_position_loss_pips(p)
                loss_pips_str = f"{loss_pips:.1f}" if loss_pips > 0 else "0.0"

            account = mt5.account_info()
            balance_str = f"{account.balance:.2f}" if account else "?"

            print(
                f"[{datetime.now()}] "
                f"Dir={current_direction or '-'} | "
                f"Side={ema_side_text} | "
                f"RSI={ema_state['rsi_now']:.2f}/{ema_state['rsi_prev']:.2f} {rsi_text} | "
                f"Cross={cross_text} | "
                f"BuyOK={ema_state['buy_allowed']} | "
                f"SellOK={ema_state['sell_allowed']} | "
                f"Spread={spread:.1f} | "
                f"OpenPos={total_positions} ({pos_text}) | "
                f"Entry={entry_price_str} | "
                f"Now={current_price_str} | "
                f"P/L={profit_str} | "
                f"LossPips={loss_pips_str}/{CUT_LOSS_PIPS} | "
                f"EMAState={ema_state_text} | "
                f"Close={current_candle['close']:.5f} | "
                f"EMA21={current_candle['ema_fast']:.5f} | "
                f"EMA144={current_candle['ema_slow']:.5f} | "
                f"Balance={balance_str}"
            )

            # =========================
            # KALAU ADA POSISI, CEK CLOSE / REVERSE DULU
            # =========================
            if total_positions > 0:
                pos = positions[0]

                close_signal = get_close_signal_by_ema21(pos, ema_state)

                if close_signal is not None:
                    print(
                        f"[{datetime.now()}] {close_signal} terdeteksi. "
                        f"Tunggu {REVERSE_DELAY_SECONDS} detik untuk konfirmasi."
                    )

                    time.sleep(REVERSE_DELAY_SECONDS)

                    ema_confirm = get_fresh_ema_state()

                    if ema_confirm is None:
                        print(f"[{datetime.now()}] Gagal ambil data konfirmasi. Close/reverse dibatalkan.")
                        time.sleep(CHECK_INTERVAL)
                        continue

                    confirm_signal = get_close_signal_by_ema21(pos, ema_confirm)

                    if confirm_signal is None:
                        print(f"[{datetime.now()}] Setelah tunggu {REVERSE_DELAY_SECONDS} detik, harga balik lagi. Posisi tetap HOLD.")
                        time.sleep(CHECK_INTERVAL)
                        continue

                    print(f"[{datetime.now()}] Konfirmasi valid: {confirm_signal}. Close posisi sekarang.")

                    ok = close_position(pos)

                    if ok:
                        positions_after_close = get_open_positions(SYMBOL, MAGIC_NUMBER)

                        if positions_after_close:
                            print(f"[{datetime.now()}] Masih ada posisi setelah close. Reverse entry dibatalkan.")
                            time.sleep(CHECK_INTERVAL)
                            continue

                        reentry_signal = get_entry_signal_by_ema21(ema_confirm)

                        if reentry_signal is not None:
                            print(f"[{datetime.now()}] Open kebalikannya setelah konfirmasi dan lolos RSI: {reentry_signal}")
                            open_by_signal(reentry_signal)
                        else:
                            print(
                                f"[{datetime.now()}] Tidak re-entry setelah close karena diblokir RSI / harga belum valid. "
                                f"RSI Now={ema_confirm['rsi_now']:.2f} | "
                                f"RSI Prev={ema_confirm['rsi_prev']:.2f} | "
                                f"BuyBlocked={ema_confirm['buy_blocked_by_rsi']} | "
                                f"SellBlocked={ema_confirm['sell_blocked_by_rsi']}"
                            )

                    time.sleep(CHECK_INTERVAL)
                    continue

                print(f"[{datetime.now()}] Hold posisi {current_position_type}.")
                time.sleep(CHECK_INTERVAL)
                continue

            # =========================
            # KALAU BELUM ADA POSISI, ENTRY SESUAI EMA21 + RSI FILTER
            # =========================
            if total_positions == 0:
                entry_signal = get_entry_signal_by_ema21(ema_state)

                if entry_signal is not None:
                    print(f"[{datetime.now()}] Tidak ada posisi. Open {entry_signal} karena EMA21 + RSI valid.")
                    open_by_signal(entry_signal)
                else:
                    print(
                        f"[{datetime.now()}] Tidak ada posisi. Entry diblokir / belum valid. "
                        f"Side={ema_side_text} | "
                        f"RSI Now={ema_state['rsi_now']:.2f} | "
                        f"RSI Prev={ema_state['rsi_prev']:.2f} | "
                        f"BuyBlocked={ema_state['buy_blocked_by_rsi']} | "
                        f"SellBlocked={ema_state['sell_blocked_by_rsi']} | "
                        f"Cross={cross_text}"
                    )

                time.sleep(CHECK_INTERVAL)
                continue

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