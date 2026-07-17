import os
import time

import MetaTrader5 as mt5
import pandas as pd


SYMBOL = os.getenv("MT5_SYMBOL", "XAUUSDm")
TIMEFRAME = mt5.TIMEFRAME_H1
LOT = float(os.getenv("MT5_LOT", "0.01"))
MAGIC = int(os.getenv("MT5_MAGIC", "51011"))
DEVIATION = int(os.getenv("MT5_DEVIATION", "20"))
SL_BUFFER_POINTS = int(os.getenv("MT5_SL_BUFFER_POINTS", "50"))
POLL_SECONDS = float(os.getenv("MT5_POLL_SECONDS", "1"))
SIDEWAYS_LOOKBACK = int(os.getenv("MT5_SIDEWAYS_LOOKBACK", "10"))
ATR_PERIOD = int(os.getenv("MT5_ATR_PERIOD", "14"))
MIN_TREND_EFFICIENCY = float(os.getenv("MT5_MIN_TREND_EFFICIENCY", "0.30"))
MIN_MA10_SLOPE_ATR = float(os.getenv("MT5_MIN_MA10_SLOPE_ATR", "0.50"))
MIN_ENGULFING_BODY_ATR = float(os.getenv("MT5_MIN_ENGULFING_BODY_ATR", "0.10"))
SWING_LOOKBACK = int(os.getenv("MT5_SWING_LOOKBACK", "30"))
TP_SHIFT_TRIGGER_POINTS = int(os.getenv("MT5_TP_SHIFT_TRIGGER_POINTS", "30"))
TP_SHIFT_SL_POINTS = int(os.getenv("MT5_TP_SHIFT_SL_POINTS", "50"))


def get_rates(count=100):
    rates = mt5.copy_rates_from_pos(SYMBOL, TIMEFRAME, 0, count)
    if rates is None or len(rates) < max(ATR_PERIOD, SIDEWAYS_LOOKBACK) + 2:
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

    return (
        efficiency < MIN_TREND_EFFICIENCY
        and ma10_slope < atr * MIN_MA10_SLOPE_ATR
    )


def engulfing_signal(df):
    previous = df.iloc[-3]
    current = df.iloc[-2]
    atr = float(current["atr"])

    if pd.isna(atr) or atr <= 0:
        return None, current

    previous_body = abs(float(previous["close"] - previous["open"]))
    current_body = abs(float(current["close"] - current["open"]))
    valid_body = (
        current_body >= previous_body
        and current_body >= atr * MIN_ENGULFING_BODY_ATR
    )

    bullish_engulfing = (
        previous["close"] < previous["open"]
        and current["close"] > current["open"]
        and current["open"] <= previous["close"]
        and current["close"] >= previous["open"]
        and valid_body
    )
    bearish_engulfing = (
        previous["close"] > previous["open"]
        and current["close"] < current["open"]
        and current["open"] >= previous["close"]
        and current["close"] <= previous["open"]
        and valid_body
    )

    touched_ma5 = current["low"] <= current["ma5"] <= current["high"]
    touched_ma10 = current["low"] <= current["ma10"] <= current["high"]
    bullish_ma_rejection = (
        (touched_ma5 and current["close"] > current["ma5"])
        or (touched_ma10 and current["close"] > current["ma10"])
    )
    bearish_ma_rejection = (
        (touched_ma5 and current["close"] < current["ma5"])
        or (touched_ma10 and current["close"] < current["ma10"])
    )

    if bullish_engulfing and bullish_ma_rejection:
        return "BUY", current
    if bearish_engulfing and bearish_ma_rejection:
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


def send_market_order(
    order_type,
    volume,
    position_ticket=None,
    sl=0.0,
    tp=0.0,
    comment="MA5 MA10 Engulfing V2",
):
    tick = mt5.symbol_info_tick(SYMBOL)
    info = mt5.symbol_info(SYMBOL)
    if tick is None or info is None:
        print("Tick/symbol tidak tersedia:", mt5.last_error())
        return False

    price = tick.ask if order_type == mt5.ORDER_TYPE_BUY else tick.bid
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
    if tp:
        request["tp"] = round(tp, info.digits)

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
        comment="Engulfing reverse close",
    )


def manage_trailing_stop(df):
    info = mt5.symbol_info(SYMBOL)
    tick = mt5.symbol_info_tick(SYMBOL)
    if info is None or tick is None:
        return

    minimum_distance = max(info.trade_stops_level, info.trade_freeze_level) * info.point
    last_closed = df.iloc[-2]
    ma5 = float(last_closed["ma5"])
    if pd.isna(ma5):
        return

    for position in bot_positions():
        if position.type == mt5.POSITION_TYPE_BUY:
            new_sl = round(ma5, info.digits)
            if tick.bid - new_sl < minimum_distance:
                continue
            if position.sl > 0 and new_sl <= position.sl:
                continue
            if new_sl <= position.price_open:
                continue
        else:
            new_sl = round(ma5, info.digits)
            if new_sl - tick.ask < minimum_distance:
                continue
            if position.sl > 0 and new_sl >= position.sl:
                continue
            if new_sl >= position.price_open:
                continue

        request = {
            "action": mt5.TRADE_ACTION_SLTP,
            "symbol": SYMBOL,
            "position": position.ticket,
            "sl": new_sl,
            "tp": position.tp,
            "magic": MAGIC,
        }
        result = mt5.order_send(request)
        if result is not None and result.retcode == mt5.TRADE_RETCODE_DONE:
            print(
                f"Trailing SL MA5 {position.ticket}: {position.sl:.{info.digits}f} "
                f"-> {new_sl:.{info.digits}f}"
            )
        else:
            error = mt5.last_error() if result is None else f"{result.retcode} - {result.comment}"
            print(f"Trailing SL gagal {position.ticket}: {error}")


def modify_position_sl_tp(position, sl, tp, label):
    info = mt5.symbol_info(SYMBOL)
    if info is None:
        return False

    request = {
        "action": mt5.TRADE_ACTION_SLTP,
        "symbol": SYMBOL,
        "position": position.ticket,
        "sl": round(sl, info.digits) if sl else position.sl,
        "tp": round(tp, info.digits) if tp else position.tp,
        "magic": MAGIC,
    }
    result = mt5.order_send(request)
    if result is not None and result.retcode == mt5.TRADE_RETCODE_DONE:
        print(
            f"{label} {position.ticket}: SL {position.sl:.{info.digits}f} "
            f"-> {request['sl']:.{info.digits}f} | TP {position.tp:.{info.digits}f} "
            f"-> {request['tp']:.{info.digits}f}"
        )
        return True

    error = mt5.last_error() if result is None else f"{result.retcode} - {result.comment}"
    print(f"{label} gagal {position.ticket}: {error}")
    return False


def calculate_sl(signal, candle):
    info = mt5.symbol_info(SYMBOL)
    tick = mt5.symbol_info_tick(SYMBOL)
    if info is None or tick is None:
        return 0.0

    broker_distance = max(info.trade_stops_level, info.trade_freeze_level) * info.point
    buffer_distance = max(SL_BUFFER_POINTS * info.point, broker_distance + info.point)

    if signal == "BUY":
        reference = min(float(candle["low"]), float(candle["ma10"]))
        return min(reference - buffer_distance, tick.ask - buffer_distance)

    reference = max(float(candle["high"]), float(candle["ma10"]))
    return max(reference + buffer_distance, tick.bid + buffer_distance)


def find_swing_target(signal, df, reference_price):
    info = mt5.symbol_info(SYMBOL)
    if info is None:
        return 0.0

    minimum_distance = max(info.trade_stops_level, info.trade_freeze_level) * info.point
    candles = df.iloc[:-1].tail(SWING_LOOKBACK).reset_index(drop=True)
    if len(candles) < 3:
        return 0.0

    if signal == "BUY":
        for i in range(len(candles) - 2, 0, -1):
            high = float(candles.iloc[i]["high"])
            previous_high = float(candles.iloc[i - 1]["high"])
            next_high = float(candles.iloc[i + 1]["high"])
            if high > previous_high and high > next_high and high > reference_price + minimum_distance:
                return round(high, info.digits)
        return 0.0

    for i in range(len(candles) - 2, 0, -1):
        low = float(candles.iloc[i]["low"])
        previous_low = float(candles.iloc[i - 1]["low"])
        next_low = float(candles.iloc[i + 1]["low"])
        if low < previous_low and low < next_low and low < reference_price - minimum_distance:
            return round(low, info.digits)
    return 0.0


def calculate_tp(signal, df, entry_price):
    return find_swing_target(signal, df, entry_price)


def manage_near_tp_shift(df):
    info = mt5.symbol_info(SYMBOL)
    tick = mt5.symbol_info_tick(SYMBOL)
    if info is None or tick is None:
        return

    minimum_distance = max(info.trade_stops_level, info.trade_freeze_level) * info.point
    trigger_distance = max(TP_SHIFT_TRIGGER_POINTS * info.point, minimum_distance)
    sl_distance = max(TP_SHIFT_SL_POINTS * info.point, minimum_distance + info.point)

    for position in bot_positions():
        if position.tp <= 0:
            continue

        if position.type == mt5.POSITION_TYPE_BUY:
            distance_to_tp = position.tp - tick.bid
            if distance_to_tp < 0 or distance_to_tp > trigger_distance:
                continue

            next_tp = find_swing_target("BUY", df, position.tp)
            new_tp = next_tp if next_tp > position.tp else position.tp
            new_sl = round(tick.bid - sl_distance, info.digits)
            if position.sl > 0 and new_sl <= position.sl:
                new_sl = position.sl
            if tick.bid - new_sl < minimum_distance:
                continue
        else:
            distance_to_tp = tick.ask - position.tp
            if distance_to_tp < 0 or distance_to_tp > trigger_distance:
                continue

            next_tp = find_swing_target("SELL", df, position.tp)
            new_tp = next_tp if next_tp and next_tp < position.tp else position.tp
            new_sl = round(tick.ask + sl_distance, info.digits)
            if position.sl > 0 and new_sl >= position.sl:
                new_sl = position.sl
            if new_sl - tick.ask < minimum_distance:
                continue

        if new_sl != position.sl or new_tp != position.tp:
            modify_position_sl_tp(position, new_sl, new_tp, "TP shift")


def execute_signal(signal, candle, sideways, df):
    if sideways:
        print(f"{candle['time']} | {signal} engulfing diabaikan: market sideways")
        return

    positions = bot_positions()
    if positions:
        print(f"{candle['time']} | Sinyal {signal} diabaikan: masih ada posisi aktif")
        return

    sl = calculate_sl(signal, candle)
    order_type = mt5.ORDER_TYPE_BUY if signal == "BUY" else mt5.ORDER_TYPE_SELL
    tick = mt5.symbol_info_tick(SYMBOL)
    entry_price = tick.ask if signal == "BUY" else tick.bid
    tp = calculate_tp(signal, df, entry_price)
    if send_market_order(order_type, LOT, sl=sl, tp=tp):
        print(
            f"{candle['time']} | {signal} ENGULFING | close={candle['close']:.3f} "
            f"MA5={candle['ma5']:.3f} MA10={candle['ma10']:.3f} SL={sl:.3f} TP={tp:.3f}"
        )


def main():
    if not mt5.initialize():
        raise RuntimeError(f"MT5 gagal diinisialisasi: {mt5.last_error()}")

    try:
        if not mt5.symbol_select(SYMBOL, True):
            raise RuntimeError(f"Symbol {SYMBOL} tidak tersedia")

        print(f"Bot V2 aktif: {SYMBOL} H1 | SMA5/SMA10 + Engulfing + Sideways")
        last_processed_candle = None

        while True:
            df = get_rates()
            if df is None:
                time.sleep(POLL_SECONDS)
                continue

            manage_trailing_stop(df)
            manage_near_tp_shift(df)
            signal, candle = engulfing_signal(df)
            candle_time = candle["time"]

            if candle_time != last_processed_candle:
                last_processed_candle = candle_time
                if signal is not None:
                    execute_signal(signal, candle, is_sideways(df), df)

            time.sleep(POLL_SECONDS)
    except KeyboardInterrupt:
        print("Bot dihentikan")
    finally:
        mt5.shutdown()


if __name__ == "__main__":
    main()
