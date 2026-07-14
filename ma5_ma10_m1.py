import os
import time

import MetaTrader5 as mt5
import pandas as pd


SYMBOL = os.getenv("MT5_SYMBOL", "XAUUSDm")
TIMEFRAME = mt5.TIMEFRAME_M1
LOT = float(os.getenv("MT5_LOT", "0.01"))
MAGIC = int(os.getenv("MT5_MAGIC", "51010"))
DEVIATION = int(os.getenv("MT5_DEVIATION", "20"))
SL_BUFFER_POINTS = int(os.getenv("MT5_SL_BUFFER_POINTS", "50"))
POLL_SECONDS = float(os.getenv("MT5_POLL_SECONDS", "1"))
SIDEWAYS_LOOKBACK = int(os.getenv("MT5_SIDEWAYS_LOOKBACK", "10"))
ATR_PERIOD = int(os.getenv("MT5_ATR_PERIOD", "14"))
MIN_TREND_EFFICIENCY = float(os.getenv("MT5_MIN_TREND_EFFICIENCY", "0.30"))
MIN_MA10_SLOPE_ATR = float(os.getenv("MT5_MIN_MA10_SLOPE_ATR", "0.50"))


def get_rates(count=100):
    rates = mt5.copy_rates_from_pos(SYMBOL, TIMEFRAME, 0, count)
    if rates is None or len(rates) < 12:
        return None

    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    df["ma5"] = df["close"].rolling(5).mean()
    df["ma10"] = df["close"].rolling(10).mean()
    previous_close = df["close"].shift(1)
    true_range = pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - previous_close).abs(),
            (df["low"] - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    df["atr"] = true_range.rolling(ATR_PERIOD).mean()
    return df


def is_sideways(df):
    candles = df.iloc[:-1].tail(SIDEWAYS_LOOKBACK)
    if len(candles) < SIDEWAYS_LOOKBACK:
        return True

    atr = float(candles.iloc[-1]["atr"])
    if pd.isna(atr) or atr <= 0:
        return True

    total_movement = float(candles["close"].diff().abs().sum())
    net_movement = abs(float(candles.iloc[-1]["close"] - candles.iloc[0]["close"]))
    efficiency = net_movement / total_movement if total_movement > 0 else 0.0
    ma10_slope = abs(float(candles.iloc[-1]["ma10"] - candles.iloc[0]["ma10"]))

    weak_direction = efficiency < MIN_TREND_EFFICIENCY
    flat_ma10 = ma10_slope < atr * MIN_MA10_SLOPE_ATR
    return weak_direction and flat_ma10


def get_signal(df):
    previous = df.iloc[-3]
    current = df.iloc[-2]

    if pd.isna(previous["ma5"]) or pd.isna(previous["ma10"]):
        return None, current

    if previous["ma5"] <= previous["ma10"] and current["ma5"] > current["ma10"]:
        return "BUY", current

    if previous["ma5"] >= previous["ma10"] and current["ma5"] < current["ma10"]:
        return "SELL", current

    return None, current


def bot_positions():
    positions = mt5.positions_get(symbol=SYMBOL)
    if positions is None:
        return []
    return [position for position in positions if position.magic == MAGIC]


def filling_mode():
    info = mt5.symbol_info(SYMBOL)
    if info is not None and info.filling_mode in (
        mt5.ORDER_FILLING_FOK,
        mt5.ORDER_FILLING_IOC,
        mt5.ORDER_FILLING_RETURN,
    ):
        return info.filling_mode
    return mt5.ORDER_FILLING_IOC


def send_market_order(order_type, volume, position_ticket=None, sl=0.0, comment="MA5 MA10 M1"):
    tick = mt5.symbol_info_tick(SYMBOL)
    info = mt5.symbol_info(SYMBOL)
    if tick is None or info is None:
        print("Tick/symbol tidak tersedia:", mt5.last_error())
        return False

    is_buy = order_type == mt5.ORDER_TYPE_BUY
    price = tick.ask if is_buy else tick.bid
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": SYMBOL,
        "volume": volume,
        "type": order_type,
        "price": round(price, info.digits),
        "deviation": DEVIATION,
        "magic": MAGIC,
        "comment": comment,
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": filling_mode(),
    }

    if position_ticket is not None:
        request["position"] = position_ticket
    if sl:
        request["sl"] = round(sl, info.digits)

    result = mt5.order_send(request)
    if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
        error = mt5.last_error() if result is None else f"{result.retcode} - {result.comment}"
        print("Order gagal:", error)
        return False

    return True


def close_position(position):
    close_type = (
        mt5.ORDER_TYPE_SELL
        if position.type == mt5.POSITION_TYPE_BUY
        else mt5.ORDER_TYPE_BUY
    )
    return send_market_order(
        close_type,
        position.volume,
        position_ticket=position.ticket,
        comment="MA cross close",
    )


def calculate_sl(signal, ma10):
    info = mt5.symbol_info(SYMBOL)
    tick = mt5.symbol_info_tick(SYMBOL)
    if info is None or tick is None:
        return 0.0

    broker_distance = max(info.trade_stops_level, info.trade_freeze_level) * info.point
    buffer_distance = max(SL_BUFFER_POINTS * info.point, broker_distance + info.point)

    if signal == "BUY":
        return min(ma10 - buffer_distance, tick.ask - buffer_distance)
    return max(ma10 + buffer_distance, tick.bid + buffer_distance)


def execute_signal(signal, candle, sideways):
    if sideways:
        print(
            f"{candle['time']} | Sinyal {signal} diabaikan: market sideways | "
            f"MA5={candle['ma5']:.3f} MA10={candle['ma10']:.3f}"
        )
        return

    desired_type = (
        mt5.POSITION_TYPE_BUY if signal == "BUY" else mt5.POSITION_TYPE_SELL
    )
    positions = bot_positions()

    if any(position.type == desired_type for position in positions):
        return

    for position in positions:
        if not close_position(position):
            return

    sl = calculate_sl(signal, float(candle["ma10"]))
    order_type = mt5.ORDER_TYPE_BUY if signal == "BUY" else mt5.ORDER_TYPE_SELL
    if send_market_order(order_type, LOT, sl=sl):
        print(
            f"{candle['time']} | {signal} | close={candle['close']:.3f} "
            f"MA5={candle['ma5']:.3f} MA10={candle['ma10']:.3f} SL={sl:.3f}"
        )


def main():
    if not mt5.initialize():
        raise RuntimeError(f"MT5 gagal diinisialisasi: {mt5.last_error()}")

    try:
        if not mt5.symbol_select(SYMBOL, True):
            raise RuntimeError(f"Symbol {SYMBOL} tidak tersedia")

        print(f"Bot aktif: {SYMBOL} M1 | SMA5 (oranye) / SMA10 (putih)")
        last_processed_candle = None

        while True:
            df = get_rates()
            if df is None:
                time.sleep(POLL_SECONDS)
                continue

            signal, candle = get_signal(df)
            candle_time = candle["time"]

            if candle_time != last_processed_candle:
                last_processed_candle = candle_time
                if signal is not None:
                    execute_signal(signal, candle, is_sideways(df))

            time.sleep(POLL_SECONDS)
    except KeyboardInterrupt:
        print("Bot dihentikan")
    finally:
        mt5.shutdown()


if __name__ == "__main__":
    main()
