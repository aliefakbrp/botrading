import MetaTrader5 as mt5
import pandas as pd
import time
from datetime import datetime, timedelta

# ==========================================
# KONFIGURASI BOT
# ==========================================
SYMBOL = "XAUUSDm"          # Sesuaikan dengan broker kamu (misal: XAUUSDm)
LOT = 0.01                 # Ukuran Lot
MAGIC_NUMBER = 777888      # ID unik untuk bot ini
TIMEFRAME = mt5.TIMEFRAME_M1

# Parameter Jarak & Pips 
PIP_MULTIPLIER = 0.01 
SL_BUFFER = 50 * PIP_MULTIPLIER      # Jarak SL di luar MA 10
TRAILING_STEP = 50 * PIP_MULTIPLIER  # Trailing stop step
MIN_MA_SPREAD = 5 * PIP_MULTIPLIER   # Minimal jarak MA5 & MA10
SIDEWAYS_LOOKBACK = 5                # Jumlah candle tertutup untuk cek sideways
MIN_MA_SLOPE = 3 * PIP_MULTIPLIER    # Minimal kemiringan MA agar tidak dianggap sideways
HISTORY_LOOKBACK_MINUTES = 10        # Waktu cek history untuk deteksi posisi kena SL
RSI_PERIOD = 14                      # Periode RSI untuk filter geser SL+
RSI_OVERSOLD = 30
RSI_OVERBOUGHT = 70

# ==========================================
# FUNGSI-FUNGSI PENDUKUNG
# ==========================================
def initialize_mt5():
    if not mt5.initialize():
        print("Gagal inisialisasi MT5. Error code =", mt5.last_error())
        quit()
    print("Berhasil terhubung ke MT5!")

def get_data(symbol, timeframe, n_candles=30):
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, n_candles)
    if rates is None:
        return None
    
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    df['ma5'] = df['close'].rolling(window=5).mean()
    df['ma10'] = df['close'].rolling(window=10).mean()
    delta = df['close'].diff()
    gain = delta.clip(lower=0).rolling(window=RSI_PERIOD).mean()
    loss = (-delta.clip(upper=0)).rolling(window=RSI_PERIOD).mean()
    rs = gain / loss
    df['rsi'] = 100 - (100 / (1 + rs))
    return df

def get_active_positions(symbol):
    positions = mt5.positions_get(symbol=symbol)
    if positions is None:
        return []
    return [p for p in positions if p.magic == MAGIC_NUMBER]

def is_sideways_market(df):
    closed_candles = df.iloc[:-1].tail(SIDEWAYS_LOOKBACK)
    if len(closed_candles) < SIDEWAYS_LOOKBACK:
        return True

    first_candle = closed_candles.iloc[0]
    last_candle = closed_candles.iloc[-1]

    ma5 = last_candle['ma5']
    ma10 = last_candle['ma10']
    ma_spread = abs(ma5 - ma10)
    ma5_slope = abs(ma5 - first_candle['ma5'])
    ma10_slope = abs(ma10 - first_candle['ma10'])

    if pd.isna(ma5) or pd.isna(ma10) or pd.isna(ma5_slope) or pd.isna(ma10_slope):
        return True

    return ma_spread <= MIN_MA_SPREAD or (ma5_slope <= MIN_MA_SLOPE and ma10_slope <= MIN_MA_SLOPE)

def get_order_label(order_type):
    return "BUY" if order_type == mt5.ORDER_TYPE_BUY else "SELL"

def get_reverse_order_label(order_type):
    return "SELL" if order_type == mt5.ORDER_TYPE_BUY else "BUY"

def can_move_trailing_sl(position, last_candle):
    rsi = last_candle['rsi']
    if pd.isna(rsi):
        return False

    candle_bullish = last_candle['close'] > last_candle['open']
    candle_bearish = last_candle['close'] < last_candle['open']

    if position.type == mt5.ORDER_TYPE_BUY:
        return rsi >= RSI_OVERBOUGHT and candle_bearish
    if position.type == mt5.ORDER_TYPE_SELL:
        return rsi <= RSI_OVERSOLD and candle_bullish
    return False

def is_engulfing_candle(df):
    if len(df) < 3:
        return None

    prev_candle = df.iloc[-3]
    last_candle = df.iloc[-2]

    prev_bearish = prev_candle['close'] < prev_candle['open']
    prev_bullish = prev_candle['close'] > prev_candle['open']
    last_bearish = last_candle['close'] < last_candle['open']
    last_bullish = last_candle['close'] > last_candle['open']

    bullish_engulfing = (
        prev_bearish
        and last_bullish
        and last_candle['open'] <= prev_candle['close']
        and last_candle['close'] >= prev_candle['open']
    )
    bearish_engulfing = (
        prev_bullish
        and last_bearish
        and last_candle['open'] >= prev_candle['close']
        and last_candle['close'] <= prev_candle['open']
    )

    if bullish_engulfing:
        return "BUY"
    if bearish_engulfing:
        return "SELL"
    return None

def get_last_close_deal(position_ticket):
    date_to = datetime.now()
    date_from = date_to - timedelta(minutes=HISTORY_LOOKBACK_MINUTES)
    deals = mt5.history_deals_get(date_from, date_to)
    if deals is None:
        return None

    close_deals = []
    deal_entry_out = getattr(mt5, "DEAL_ENTRY_OUT", 1)
    for deal in deals:
        if (
            deal.position_id == position_ticket
            and deal.magic == MAGIC_NUMBER
            and deal.entry == deal_entry_out
        ):
            close_deals.append(deal)

    if not close_deals:
        return None
    return max(close_deals, key=lambda deal: deal.time)

def was_closed_by_sl(position_ticket):
    close_deal = get_last_close_deal(position_ticket)
    if close_deal is None:
        return False

    deal_reason_sl = getattr(mt5, "DEAL_REASON_SL", None)
    if deal_reason_sl is not None:
        return close_deal.reason == deal_reason_sl

    return "sl" in str(close_deal.comment).lower()

def close_position(position):
    tick = mt5.symbol_info_tick(position.symbol)
    symbol_info = mt5.symbol_info(position.symbol)
    digits = symbol_info.digits if symbol_info else 2
    pnl = position.profit
    direction = get_order_label(position.type)

    if position.type == mt5.ORDER_TYPE_BUY:
        price = tick.bid
        order_type = mt5.ORDER_TYPE_SELL
    else:
        price = tick.ask
        order_type = mt5.ORDER_TYPE_BUY

    price = round(price, digits)

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": position.symbol,
        "volume": position.volume,
        "type": order_type,
        "position": position.ticket,
        "price": price,
        "deviation": 20,
        "magic": MAGIC_NUMBER,
        "comment": "Force Close Crossover",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    result = mt5.order_send(request)
    if result.retcode == mt5.TRADE_RETCODE_DONE:
        print(f"Posisi {direction} Force Close di {price}. PnL: {pnl:.2f}")
    else:
        print(f"Gagal Force Close {direction}. Error code: {result.retcode}. PnL running: {pnl:.2f}")

def open_trade(symbol, order_type, sl_price):
    tick = mt5.symbol_info_tick(symbol)
    symbol_info = mt5.symbol_info(symbol)
    
    digits = symbol_info.digits if symbol_info else 2

    if order_type == "BUY":
        price = tick.ask
        type_mt5 = mt5.ORDER_TYPE_BUY
        # Pengaman SL
        if sl_price >= price:
            sl_price = price - SL_BUFFER

    elif order_type == "SELL":
        price = tick.bid
        type_mt5 = mt5.ORDER_TYPE_SELL
        # Pengaman SL
        if sl_price <= tick.ask:
            sl_price = tick.ask + SL_BUFFER

    # Pembulatan desimal
    price = round(price, digits)
    sl_price = round(sl_price, digits)

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": LOT,
        "type": type_mt5,
        "price": price,
        "sl": sl_price,
        "deviation": 20,
        "magic": MAGIC_NUMBER,
        "comment": "Bot MA Scalper M1",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    result = mt5.order_send(request)
    
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        print(f"Gagal Entry {order_type}. Error code: {result.retcode}")
        return False
    else:
        print(f"SUKSES Entry {order_type}! Harga: {price}, SL: {sl_price}")
        return result.order if result.order else True

# ==========================================
# LOGIKA UTAMA (LOOPING BOT)
# ==========================================
def run_bot():
    print(f"Memulai Bot Scalping di {SYMBOL} - M1 (Mode Opsi 2: Sentuhan Ekor)...")
    last_position_snapshot = None
    pending_reverse_position = False
    handled_closed_tickets = set()

    while True:
        try:
            df = get_data(SYMBOL, TIMEFRAME)
            if df is None or df.empty:
                time.sleep(1)
                continue

            last_candle = df.iloc[-2]
            ma5 = last_candle['ma5']
            ma10 = last_candle['ma10']
            
            # Pengambilan 3 jenis harga untuk Opsi 2
            close_price = last_candle['close']
            high_price = last_candle['high']
            low_price = last_candle['low']
            
            ma_spread = abs(ma5 - ma10)
            is_trending = ma_spread > MIN_MA_SPREAD
            is_sideways = is_sideways_market(df)

            positions = get_active_positions(SYMBOL)
            opened_reverse = False

            if len(positions) == 0 and last_position_snapshot is not None:
                closed_ticket = last_position_snapshot["ticket"]
                if closed_ticket not in handled_closed_tickets:
                    closed_by_sl = was_closed_by_sl(closed_ticket)
                    engulfing_signal = is_engulfing_candle(df)

                    if (
                        closed_by_sl
                        and engulfing_signal is not None
                        and not last_position_snapshot["is_reverse"]
                    ):
                        reverse_order = get_reverse_order_label(last_position_snapshot["type"])
                        if engulfing_signal == reverse_order:
                            sl_price = low_price - SL_BUFFER if reverse_order == "BUY" else high_price + SL_BUFFER
                            print(f"SL kena + engulfing {engulfing_signal}. Entry reverse {reverse_order}.")
                            if open_trade(SYMBOL, reverse_order, sl_price):
                                pending_reverse_position = True
                                opened_reverse = True
                                time.sleep(3)
                        else:
                            print(
                                f"SL kena + engulfing {engulfing_signal}, tapi arah engulfing bukan reverse "
                                f"dari {get_order_label(last_position_snapshot['type'])}."
                            )
                    elif closed_by_sl and last_position_snapshot["is_reverse"]:
                        print("Posisi reverse kena SL. Bot kembali ke logic trend normal.")

                    handled_closed_tickets.add(closed_ticket)

                last_position_snapshot = None

            if opened_reverse:
                time.sleep(2)
                continue

            if len(positions) == 1:
                pos = positions[0]
                if last_position_snapshot is None or last_position_snapshot["ticket"] != pos.ticket:
                    last_position_snapshot = {
                        "ticket": pos.ticket,
                        "type": pos.type,
                        "is_reverse": pending_reverse_position,
                    }
                    pending_reverse_position = False

            # 1. JIKA TIDAK ADA POSISI (SINGLE ENTRY)
            if len(positions) == 0:
                if is_sideways:
                    print("Market sideways, tidak entry.")
                elif is_trending:
                    # Setup SELL (Ekor Atas menyentuh MA5)
                    # Syarat: Tren Turun + Ekor Atas menembus MA5 + Close masih aman di bawah MA10
                    if ma5 < ma10 and high_price >= ma5 and close_price < ma10:
                        sl_price = ma10 + SL_BUFFER
                        print(f"Sinyal SELL! Ekor candle memantul di MA5. (High: {high_price:.3f})")
                        if open_trade(SYMBOL, "SELL", sl_price):
                            time.sleep(3) 

                    # Setup BUY (Ekor Bawah menyentuh MA5)
                    # Syarat: Tren Naik + Ekor Bawah menembus MA5 + Close masih aman di atas MA10
                    elif ma5 > ma10 and low_price <= ma5 and close_price > ma10:
                        sl_price = ma10 - SL_BUFFER
                        print(f"Sinyal BUY! Ekor candle memantul di MA5. (Low: {low_price:.3f})")
                        if open_trade(SYMBOL, "BUY", sl_price):
                            time.sleep(3)

            # 2. JIKA SUDAH ADA 1 POSISI (MANAJEMEN RISIKO)
            elif len(positions) == 1:
                pos = positions[0]
                tick = mt5.symbol_info_tick(SYMBOL)
                symbol_info = mt5.symbol_info(SYMBOL)
                digits = symbol_info.digits if symbol_info else 2
                current_price = tick.bid if pos.type == mt5.ORDER_TYPE_BUY else tick.ask
                print(
                    f"Running {get_order_label(pos.type)} | Open: {pos.price_open:.{digits}f} | "
                    f"Current: {current_price:.{digits}f} | PnL: {pos.profit:.2f}"
                )

                # Force Close jika tren berbalik arah
                if pos.type == mt5.ORDER_TYPE_BUY and ma5 < ma10:
                    close_position(pos)
                    time.sleep(3)
                elif pos.type == mt5.ORDER_TYPE_SELL and ma5 > ma10:
                    close_position(pos)
                    time.sleep(3)
                
                # Trailing Stop Management
                else:
                    sl_filter_ready = can_move_trailing_sl(pos, last_candle)
                    if not sl_filter_ready:
                        print(f"SL+ belum digeser. RSI: {last_candle['rsi']:.2f}, candle belum konfirmasi balik arah.")

                    if pos.type == mt5.ORDER_TYPE_BUY and sl_filter_ready:
                        new_sl = tick.bid - TRAILING_STEP
                        new_sl = round(new_sl, digits) 
                        if tick.bid - pos.price_open > TRAILING_STEP and new_sl > pos.sl:
                            old_sl = round(pos.sl, digits) if pos.sl else 0.0
                            request = {"action": mt5.TRADE_ACTION_SLTP, "position": pos.ticket, "sl": new_sl}
                            result = mt5.order_send(request)
                            if result.retcode == mt5.TRADE_RETCODE_DONE:
                                print(
                                    f"SL BUY digeser: {old_sl:.{digits}f} -> {new_sl:.{digits}f} | "
                                    f"Current: {tick.bid:.{digits}f} | RSI: {last_candle['rsi']:.2f} | PnL: {pos.profit:.2f}"
                                )
                            
                    elif pos.type == mt5.ORDER_TYPE_SELL and sl_filter_ready:
                        new_sl = tick.ask + TRAILING_STEP
                        new_sl = round(new_sl, digits) 
                        if pos.price_open - tick.ask > TRAILING_STEP and (new_sl < pos.sl or pos.sl == 0.0):
                            old_sl = round(pos.sl, digits) if pos.sl else 0.0
                            request = {"action": mt5.TRADE_ACTION_SLTP, "position": pos.ticket, "sl": new_sl}
                            result = mt5.order_send(request)
                            if result.retcode == mt5.TRADE_RETCODE_DONE:
                                print(
                                    f"SL SELL digeser: {old_sl:.{digits}f} -> {new_sl:.{digits}f} | "
                                    f"Current: {tick.ask:.{digits}f} | RSI: {last_candle['rsi']:.2f} | PnL: {pos.profit:.2f}"
                                )

            elif len(positions) > 1:
                print("PERINGATAN: Terdeteksi lebih dari 1 posisi aktif! Menunggu posisi ditutup...")

            time.sleep(2) 

        except Exception as e:
            print(f"Terjadi Error: {e}")
            time.sleep(5)

if __name__ == "__main__":
    initialize_mt5()
    run_bot()
