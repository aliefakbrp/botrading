import MetaTrader5 as mt5
import pandas as pd
import time
from datetime import datetime

# =========================
# CONFIG
# =========================
SYMBOLS = ["USDJPYm", "EURUSDm", "EURJPYm", "BTCUSDm"]
TIMEFRAME = mt5.TIMEFRAME_M1
RR_RATIO = 3
STRUCTURE_LOOKBACK = 20
BASE_MAGIC_NUMBER = 202604
COMMENT_PREFIX = "SMC_MULTI_BOT"

# Setting per symbol
SETTINGS = {
    "USDJPYm": {
        "lot": 0.1,
        "buffer": 0.04,     # sesuaikan broker
        "min_risk": 0.02
    },
    "EURUSDm": {
        "lot": 0.1,
        "buffer": 0.00040,  # sesuaikan broker
        "min_risk": 0.00020
    },
    "EURJPYm": {
        "lot": 0.1,
        "buffer": 0.04,     # sesuaikan broker
        "min_risk": 0.02
    },
    "BTCUSDm": {
        "lot": 0.1,
        "buffer": 40.0,     # sesuaikan broker
        "min_risk": 20.0
    }
}

# Simpan candle terakhir per symbol
last_processed_time = {symbol: None for symbol in SYMBOLS}


# =========================
# HELPERS
# =========================
def get_magic(symbol: str) -> int:
    return BASE_MAGIC_NUMBER + abs(hash(symbol)) % 10000


def log(symbol: str, message: str):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [{symbol}] {message}")


def initialize_mt5():
    if not mt5.initialize():
        print("[-] Gagal koneksi ke MT5!")
        quit()

    print(f"[{datetime.now()}] MT5 connected")

    for symbol in SYMBOLS:
        info = mt5.symbol_info(symbol)

        if info is None:
            print(f"[-] Symbol tidak ditemukan: {symbol}")
            continue

        if not info.visible:
            selected = mt5.symbol_select(symbol, True)
            if not selected:
                print(f"[-] Gagal select symbol: {symbol}")
                continue

        log(symbol, f"Aktif | digits={info.digits} | point={info.point}")


def get_symbol_info(symbol: str):
    info = mt5.symbol_info(symbol)
    if info is None:
        log(symbol, "symbol_info gagal")
    return info


def has_open_position(symbol: str) -> bool:
    positions = mt5.positions_get(symbol=symbol)
    if positions is None:
        return False

    my_magic = get_magic(symbol)
    for pos in positions:
        if pos.magic == my_magic:
            return True
    return False


def has_pending_order(symbol: str) -> bool:
    orders = mt5.orders_get(symbol=symbol)
    if orders is None:
        return False

    my_magic = get_magic(symbol)
    for order in orders:
        if order.magic == my_magic:
            return True
    return False


def cancel_all_pending(symbol: str):
    orders = mt5.orders_get(symbol=symbol)
    if not orders:
        return

    my_magic = get_magic(symbol)

    for order in orders:
        if order.magic != my_magic:
            continue

        request = {
            "action": mt5.TRADE_ACTION_REMOVE,
            "order": order.ticket
        }

        result = mt5.order_send(request)
        if result is not None and result.retcode == mt5.TRADE_RETCODE_DONE:
            log(symbol, f"Pending order {order.ticket} dicancel")
        else:
            retcode = result.retcode if result else "None"
            comment = result.comment if result else "No response"
            log(symbol, f"Gagal cancel pending {order.ticket} | retcode={retcode} | {comment}")


def get_ohlc(symbol: str, n: int = 100) -> pd.DataFrame:
    rates = mt5.copy_rates_from_pos(symbol, TIMEFRAME, 0, n)

    if rates is None or len(rates) == 0:
        return pd.DataFrame()

    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    return df


def normalize_price(symbol: str, price: float) -> float:
    info = get_symbol_info(symbol)
    if info is None:
        return price
    return round(price, info.digits)


def send_limit_order(symbol: str, lot: float, order_type: int, price: float, sl: float, tp: float):
    info = get_symbol_info(symbol)
    if info is None:
        return None

    price = normalize_price(symbol, price)
    sl = normalize_price(symbol, sl)
    tp = normalize_price(symbol, tp)

    request = {
        "action": mt5.TRADE_ACTION_PENDING,
        "symbol": symbol,
        "volume": lot,
        "type": order_type,
        "price": price,
        "sl": sl,
        "tp": tp,
        "magic": get_magic(symbol),
        "comment": f"{COMMENT_PREFIX}_{symbol}",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_RETURN,
    }

    result = mt5.order_send(request)
    return result


def validate_trade_levels(symbol: str, entry: float, sl: float, tp: float) -> bool:
    info = get_symbol_info(symbol)
    if info is None:
        return False

    if entry <= 0 or sl <= 0 or tp <= 0:
        log(symbol, "Level invalid (<= 0)")
        return False

    if entry == sl or entry == tp or sl == tp:
        log(symbol, "Level invalid (sama)")
        return False

    return True


# =========================
# CORE LOGIC
# =========================
def process_symbol(symbol: str):
    if symbol not in SETTINGS:
        log(symbol, "Setting symbol tidak ditemukan")
        return

    config = SETTINGS[symbol]
    lot = config["lot"]
    buffer_value = config["buffer"]
    min_risk = config["min_risk"]

    df = get_ohlc(symbol, 120)
    if df.empty:
        log(symbol, "OHLC kosong")
        return

    if len(df) < STRUCTURE_LOOKBACK + 20:
        log(symbol, "Data candle belum cukup")
        return

    # Pakai candle yang sudah close, bukan candle aktif
    current_candle = df.iloc[-2]
    current_time = current_candle["time"]

    if current_time == last_processed_time[symbol]:
        return

    # Tandai candle sudah diproses
    last_processed_time[symbol] = current_time

    # Kalau sudah ada posisi bot ini, skip
    if has_open_position(symbol):
        log(symbol, "Ada posisi terbuka, skip")
        return

    # Struktur sebelum candle signal
    window = df.iloc[-(STRUCTURE_LOOKBACK + 2):-2]
    swing_high = window["high"].max()
    swing_low = window["low"].min()

    # Area untuk cari OB
    recent = df.iloc[-16:-2]

    # =========================
    # BUY SETUP
    # =========================
    if current_candle["close"] > swing_high:
        log(symbol, f"BOS bullish terdeteksi | close={current_candle['close']} > swing_high={swing_high}")

        # kalau cuma mau 1 setup aktif, cancel pending lama
        cancel_all_pending(symbol)

        bearish_candles = recent[recent["close"] < recent["open"]]
        if bearish_candles.empty:
            log(symbol, "Tidak ada bearish candle untuk OB buy")
            return

        last_ob = bearish_candles.iloc[-1]
        entry = float(last_ob["high"])
        sl = float(last_ob["low"] - buffer_value)
        risk = entry - sl

        if risk <= min_risk:
            log(symbol, f"Risk buy terlalu kecil | risk={risk} | min={min_risk}")
            return

        tp = entry + (risk * RR_RATIO)

        if not validate_trade_levels(symbol, entry, sl, tp):
            return

        result = send_limit_order(
            symbol=symbol,
            lot=lot,
            order_type=mt5.ORDER_TYPE_BUY_LIMIT,
            price=entry,
            sl=sl,
            tp=tp
        )

        if result is not None and result.retcode == mt5.TRADE_RETCODE_DONE:
            log(
                symbol,
                f"BUY LIMIT sent | entry={normalize_price(symbol, entry)} "
                f"sl={normalize_price(symbol, sl)} tp={normalize_price(symbol, tp)}"
            )
        else:
            retcode = result.retcode if result else "None"
            comment = result.comment if result else "No response"
            log(symbol, f"Gagal BUY LIMIT | retcode={retcode} | {comment}")

    # =========================
    # SELL SETUP
    # =========================
    elif current_candle["close"] < swing_low:
        log(symbol, f"BOS bearish terdeteksi | close={current_candle['close']} < swing_low={swing_low}")

        cancel_all_pending(symbol)

        bullish_candles = recent[recent["close"] > recent["open"]]
        if bullish_candles.empty:
            log(symbol, "Tidak ada bullish candle untuk OB sell")
            return

        last_ob = bullish_candles.iloc[-1]
        entry = float(last_ob["low"])
        sl = float(last_ob["high"] + buffer_value)
        risk = sl - entry

        if risk <= min_risk:
            log(symbol, f"Risk sell terlalu kecil | risk={risk} | min={min_risk}")
            return

        tp = entry - (risk * RR_RATIO)

        if not validate_trade_levels(symbol, entry, sl, tp):
            return

        result = send_limit_order(
            symbol=symbol,
            lot=lot,
            order_type=mt5.ORDER_TYPE_SELL_LIMIT,
            price=entry,
            sl=sl,
            tp=tp
        )

        if result is not None and result.retcode == mt5.TRADE_RETCODE_DONE:
            log(
                symbol,
                f"SELL LIMIT sent | entry={normalize_price(symbol, entry)} "
                f"sl={normalize_price(symbol, sl)} tp={normalize_price(symbol, tp)}"
            )
        else:
            retcode = result.retcode if result else "None"
            comment = result.comment if result else "No response"
            log(symbol, f"Gagal SELL LIMIT | retcode={retcode} | {comment}")


def run_bot():
    while True:
        for symbol in SYMBOLS:
            try:
                process_symbol(symbol)
            except Exception as e:
                log(symbol, f"Error: {e}")

        time.sleep(1)


# =========================
# MAIN
# =========================
if __name__ == "__main__":
    initialize_mt5()
    try:
        run_bot()
    except KeyboardInterrupt:
        print("\n[!] Bot dihentikan.")
    finally:
        mt5.shutdown()