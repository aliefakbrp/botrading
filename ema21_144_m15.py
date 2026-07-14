# EMA 21 / 144 M15
# Entry ikut arah EMA
# Close BUY kalau EMA21 turun
# Close SELL kalau EMA21 naik
# Re-entry sesuai arah EMA21 setelah close / CL

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
EMA_SLOW = 144

# Spread filter
MAX_SPREAD_POINTS = 300

# Delay kecil setelah close sebelum entry ulang
REVERSE_DELAY_SECONDS = 0.8

# =========================
# CUT LOSS
# =========================
CUT_LOSS_PIPS = 20

# Untuk XAUUSD:
# Umumnya 1 pip = 0.10, jadi 20 pips = 2.00 harga.
# Kalau broker kamu hitung 1 pip = 0.01, ubah PIP_VALUE jadi 0.01.
PIP_VALUE = 0.10

# =========================
# STATE
# =========================
_last_action_bar_time = None

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


def add_indicators(df):
    df["ema_fast"] = df["close"].ewm(span=EMA_FAST, adjust=False).mean()
    df["ema_slow"] = df["close"].ewm(span=EMA_SLOW, adjust=False).mean()
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
# EMA LOGIC
# =========================
def get_ema_state(df):
    """
    Pakai candle berjalan/realtime seperti code kamu sebelumnya.
    df.iloc[-1] = candle M15 yang sedang berjalan.

    Kalau mau pakai candle close saja:
    ubah current_candle = df.iloc[-2]
    dan prev_candle = df.iloc[-3]
    """

    if len(df) < EMA_SLOW + 5:
        return None

    prev_candle = df.iloc[-2]
    current_candle = df.iloc[-1]

    prev_fast = prev_candle["ema_fast"]
    curr_fast = current_candle["ema_fast"]

    curr_slow = current_candle["ema_slow"]

    ema21_up = curr_fast > prev_fast
    ema21_down = curr_fast < prev_fast

    bullish_trend = curr_fast > curr_slow
    bearish_trend = curr_fast < curr_slow

    if bullish_trend:
        direction = "BUY"
    elif bearish_trend:
        direction = "SELL"
    else:
        direction = None

    return {
        "bar_time": current_candle["time"],
        "close": current_candle["close"],
        "ema_fast": curr_fast,
        "ema_slow": curr_slow,
        "ema21_up": ema21_up,
        "ema21_down": ema21_down,
        "bullish_trend": bullish_trend,
        "bearish_trend": bearish_trend,
        "direction": direction,
        "current_candle": current_candle,
    }


def get_close_signal_by_ema21(position, ema_state):
    """
    Close rule:
    - BUY close kalau EMA21 sekarang lebih rendah dari sebelumnya
    - SELL close kalau EMA21 sekarang lebih tinggi dari sebelumnya
    """

    if position.type == mt5.POSITION_TYPE_BUY and ema_state["ema21_down"]:
        return "CLOSE_BUY"

    if position.type == mt5.POSITION_TYPE_SELL and ema_state["ema21_up"]:
        return "CLOSE_SELL"

    return None


def get_entry_signal_by_ema21(ema_state):
    """
    Entry / re-entry rule:
    - BUY kalau trend bullish dan EMA21 naik
    - SELL kalau trend bearish dan EMA21 turun
    """

    if ema_state["bullish_trend"] and ema_state["ema21_up"]:
        return "BUY"

    if ema_state["bearish_trend"] and ema_state["ema21_down"]:
        return "SELL"

    return None


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
        "comment": "EMA21_144_M15",
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
        "comment": "EMA21_144_CLOSE",
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
    global _last_action_bar_time

    initialize_mt5()

    print(f"\n[{datetime.now()}] Bot EMA 21/144 M15 aktif")
    print(f"  Symbol: {SYMBOL}")
    print(f"  Timeframe: M15")
    print(f"  EMA Fast / Slow: {EMA_FAST}/{EMA_SLOW}")
    print(f"  Check interval: {CHECK_INTERVAL} detik")
    print(f"  Entry BUY : EMA21 > EMA144 dan EMA21 naik")
    print(f"  Entry SELL: EMA21 < EMA144 dan EMA21 turun")
    print(f"  Close BUY : EMA21 turun")
    print(f"  Close SELL: EMA21 naik")
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
                print(f"[{datetime.now()}] Data belum cukup untuk EMA {EMA_SLOW}")
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
                print(f"[{datetime.now()}] Ada posisi yang kena CL.")

                time.sleep(REVERSE_DELAY_SECONDS)

                positions_after_cl = get_open_positions(SYMBOL, MAGIC_NUMBER)

                if positions_after_cl:
                    print(f"[{datetime.now()}] Masih ada posisi setelah CL, entry ulang dibatalkan.")
                    time.sleep(CHECK_INTERVAL)
                    continue

                reentry_signal = get_entry_signal_by_ema21(ema_state)

                if reentry_signal is None:
                    print(f"[{datetime.now()}] Setelah CL, EMA belum valid untuk re-entry.")
                    time.sleep(CHECK_INTERVAL)
                    continue

                print(f"[{datetime.now()}] Setelah CL, open ulang sesuai EMA: {reentry_signal}")
                open_by_signal(reentry_signal)

                time.sleep(CHECK_INTERVAL)
                continue

            positions = get_open_positions(SYMBOL, MAGIC_NUMBER)
            total_positions = len(positions)

            ema_state_text = (
                "Bullish" if current_direction == "BUY"
                else "Bearish" if current_direction == "SELL"
                else "-"
            )

            ema_slope_text = (
                "EMA21_UP" if ema_state["ema21_up"]
                else "EMA21_DOWN" if ema_state["ema21_down"]
                else "FLAT"
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
                f"Slope={ema_slope_text} | "
                f"Spread={spread:.1f} | "
                f"OpenPos={total_positions} ({pos_text}) | "
                f"Entry={entry_price_str} | "
                f"Now={current_price_str} | "
                f"P/L={profit_str} | "
                f"LossPips={loss_pips_str}/{CUT_LOSS_PIPS} | "
                f"EMA={ema_state_text} | "
                f"EMA21={current_candle['ema_fast']:.5f} | "
                f"EMA144={current_candle['ema_slow']:.5f} | "
                f"Balance={balance_str}"
            )

            # =========================
            # KALAU ADA POSISI, CEK CLOSE DULU
            # =========================
            if total_positions > 0:
                pos = positions[0]

                close_signal = get_close_signal_by_ema21(pos, ema_state)

                if close_signal is not None:
                    print(f"[{datetime.now()}] {close_signal} terdeteksi.")

                    ok = close_position(pos)

                    if ok:
                        time.sleep(REVERSE_DELAY_SECONDS)

                        positions_after_close = get_open_positions(SYMBOL, MAGIC_NUMBER)

                        if positions_after_close:
                            print(f"[{datetime.now()}] Masih ada posisi setelah close. Re-entry dibatalkan.")
                            time.sleep(CHECK_INTERVAL)
                            continue

                        reentry_signal = get_entry_signal_by_ema21(ema_state)

                        if reentry_signal is not None:
                            print(f"[{datetime.now()}] Re-entry langsung: {reentry_signal}")
                            open_by_signal(reentry_signal)
                        else:
                            print(f"[{datetime.now()}] Tidak re-entry. EMA21 belum searah.")

                    time.sleep(CHECK_INTERVAL)
                    continue

                # Kalau posisi lawan arah trend EMA utama, close lalu ikut arah baru kalau valid
                if current_position_type == "BUY" and current_direction == "SELL":
                    print(f"[{datetime.now()}] Posisi BUY tapi EMA sudah bearish. Close BUY.")

                    close_all_positions(positions)
                    time.sleep(REVERSE_DELAY_SECONDS)

                    reentry_signal = get_entry_signal_by_ema21(ema_state)

                    if reentry_signal == "SELL":
                        print(f"[{datetime.now()}] Open SELL setelah close BUY.")
                        open_by_signal("SELL")

                    time.sleep(CHECK_INTERVAL)
                    continue

                if current_position_type == "SELL" and current_direction == "BUY":
                    print(f"[{datetime.now()}] Posisi SELL tapi EMA sudah bullish. Close SELL.")

                    close_all_positions(positions)
                    time.sleep(REVERSE_DELAY_SECONDS)

                    reentry_signal = get_entry_signal_by_ema21(ema_state)

                    if reentry_signal == "BUY":
                        print(f"[{datetime.now()}] Open BUY setelah close SELL.")
                        open_by_signal("BUY")

                    time.sleep(CHECK_INTERVAL)
                    continue

                print(f"[{datetime.now()}] Hold posisi {current_position_type}.")
                time.sleep(CHECK_INTERVAL)
                continue

            # =========================
            # KALAU BELUM ADA POSISI, ENTRY SESUAI EMA
            # =========================
            if total_positions == 0:
                entry_signal = get_entry_signal_by_ema21(ema_state)

                if entry_signal is not None:
                    print(f"[{datetime.now()}] Tidak ada posisi. Open {entry_signal} sesuai EMA.")
                    open_by_signal(entry_signal)
                else:
                    print(f"[{datetime.now()}] Tidak ada posisi. Belum ada signal entry.")

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