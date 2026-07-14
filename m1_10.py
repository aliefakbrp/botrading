import MetaTrader5 as mt5
import pandas as pd
import time

# ==========================================
# PENGATURAN BOT
# ==========================================
SYMBOL = "XAUUSDm"          # Ganti dengan pair Anda
TIMEFRAME = mt5.TIMEFRAME_M1
VOLUME = 0.01
MAGIC_NUMBER = 101010
MA_PERIOD = 10
RSI_PERIOD = 14            # Periode RSI standar
SL_PIPS = 150
TRAILING_PIPS = 150

# Variabel Global untuk mengingat RSI pada entry sebelumnya
last_buy_rsi = None
last_sell_rsi = None

# ==========================================
# FUNGSI PENDUKUNG
# ==========================================
def get_pip_value(symbol):
    info = mt5.symbol_info(symbol)
    if info is None: return None
    if info.digits == 5 or info.digits == 3: return info.point * 10
    return info.point

def get_indicators(symbol, timeframe, ma_period, rsi_period):
    """Mengambil harga penutupan terakhir, MA, dan RSI."""
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, max(ma_period, rsi_period) + 50)
    if rates is None or len(rates) == 0:
        return None, None, None
    
    df = pd.DataFrame(rates)
    df['close'] = df['close'].astype(float)
    
    # 1. Hitung Moving Average (MA)
    df['MA'] = df['close'].rolling(window=ma_period).mean()
    
    # 2. Hitung RSI secara manual dengan pandas (Metode EMA)
    delta = df['close'].diff()
    up = delta.clip(lower=0)
    down = -1 * delta.clip(upper=0)
    ema_up = up.ewm(com=rsi_period-1, adjust=False).mean()
    ema_down = down.ewm(com=rsi_period-1, adjust=False).mean()
    rs = ema_up / ema_down
    df['RSI'] = 100 - (100 / (1 + rs))
    
    # Ambil candle index ke-1 (candle terakhir yang sudah CLOSE)
    last_closed_candle = df.iloc[-2] 
    
    return last_closed_candle['close'], last_closed_candle['MA'], last_closed_candle['RSI']

def open_trade(symbol, order_type, price, sl_price):
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": VOLUME,
        "type": order_type,
        "price": price,
        "sl": sl_price,
        "deviation": 20,
        "magic": MAGIC_NUMBER,
        "comment": "Bot MA+RSI Re-Entry",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    result = mt5.order_send(request)
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        print(f"Gagal open posisi: {result.comment}")
        return False
    else:
        print(f"Berhasil open posisi {'BUY' if order_type == mt5.ORDER_TYPE_BUY else 'SELL'} di {price}")
        return True

def manage_trailing_stop(symbol, trailing_pips):
    positions = mt5.positions_get(symbol=symbol)
    if not positions: return
    
    pip_val = get_pip_value(symbol)
    trailing_dist = trailing_pips * pip_val
    
    for pos in positions:
        if pos.magic != MAGIC_NUMBER: continue
            
        current_price = mt5.symbol_info_tick(symbol).bid if pos.type == mt5.POSITION_TYPE_BUY else mt5.symbol_info_tick(symbol).ask
        
        if pos.type == mt5.POSITION_TYPE_BUY:
            new_sl = current_price - trailing_dist
            if new_sl > pos.sl and (current_price - pos.price_open) >= trailing_dist:
                mt5.order_send({"action": mt5.TRADE_ACTION_SLTP, "position": pos.ticket, "symbol": symbol, "sl": new_sl, "tp": pos.tp})
                
        elif pos.type == mt5.POSITION_TYPE_SELL:
            new_sl = current_price + trailing_dist
            if (new_sl < pos.sl or pos.sl == 0.0) and (pos.price_open - current_price) >= trailing_dist:
                mt5.order_send({"action": mt5.TRADE_ACTION_SLTP, "position": pos.ticket, "symbol": symbol, "sl": new_sl, "tp": pos.tp})

# ==========================================
# LOOP UTAMA (MAIN)
# ==========================================
def main():
    global last_buy_rsi, last_sell_rsi
    
    if not mt5.initialize():
        print("Gagal inisialisasi MT5:", mt5.last_error())
        return
    
    print(f"Bot MA 10 & RSI Re-Entry berjalan pada {SYMBOL} - TF {TIMEFRAME}")
    
    while True:
        try:
            mt5.symbol_select(SYMBOL, True)
            manage_trailing_stop(SYMBOL, TRAILING_PIPS)
            
            # Cek status posisi saat ini
            positions = mt5.positions_get(symbol=SYMBOL)
            has_buy = False
            has_sell = False
            
            if positions:
                for pos in positions:
                    if pos.magic == MAGIC_NUMBER:
                        if pos.type == mt5.POSITION_TYPE_BUY: has_buy = True
                        if pos.type == mt5.POSITION_TYPE_SELL: has_sell = True
            
            # Reset memori RSI jika posisi sudah tertutup (Clear memory)
            if not has_buy: last_buy_rsi = None
            if not has_sell: last_sell_rsi = None
            
            close_price, ma_value, current_rsi = get_indicators(SYMBOL, TIMEFRAME, MA_PERIOD, RSI_PERIOD)
            
            if close_price is not None and ma_value is not None and current_rsi is not None:
                tick = mt5.symbol_info_tick(SYMBOL)
                pip_val = get_pip_value(SYMBOL)
                sl_dist = SL_PIPS * pip_val
                
                # ==========================================
                # LOGIKA BUY (Close > MA 10)
                # ==========================================
                if close_price > ma_value:
                    can_buy = False
                    
                    # Jika belum ada Buy, boleh entry
                    if not has_buy: 
                        can_buy = True
                    # Jika sudah ada Buy, cek apakah RSI saat ini LEBIH RENDAH dari RSI Buy terakhir
                    elif has_buy and last_buy_rsi is not None and current_rsi < last_buy_rsi:
                        can_buy = True
                        print(f"Syarat Re-Entry BUY terpenuhi! RSI Saat Ini ({current_rsi:.2f}) < RSI Sblmnya ({last_buy_rsi:.2f})")
                        
                    if can_buy:
                        print(f"Sinyal BUY! Close: {close_price} > MA10: {ma_value:.4f} | RSI: {current_rsi:.2f}")
                        sl_price = tick.ask - sl_dist
                        if open_trade(SYMBOL, mt5.ORDER_TYPE_BUY, tick.ask, sl_price):
                            last_buy_rsi = current_rsi # Simpan RSI untuk re-entry berikutnya
                            
                # ==========================================
                # LOGIKA SELL (Close < MA 10)
                # ==========================================
                elif close_price < ma_value:
                    can_sell = False
                    
                    # Jika belum ada Sell, boleh entry
                    if not has_sell: 
                        can_sell = True
                    # Jika sudah ada Sell, cek apakah RSI saat ini LEBIH TINGGI dari RSI Sell terakhir
                    elif has_sell and last_sell_rsi is not None and current_rsi > last_sell_rsi:
                        can_sell = True
                        print(f"Syarat Re-Entry SELL terpenuhi! RSI Saat Ini ({current_rsi:.2f}) > RSI Sblmnya ({last_sell_rsi:.2f})")
                        
                    if can_sell:
                        print(f"Sinyal SELL! Close: {close_price} < MA10: {ma_value:.4f} | RSI: {current_rsi:.2f}")
                        sl_price = tick.bid + sl_dist
                        if open_trade(SYMBOL, mt5.ORDER_TYPE_SELL, tick.bid, sl_price):
                            last_sell_rsi = current_rsi # Simpan RSI untuk re-entry berikutnya
            
            time.sleep(1) # Jeda agar komputer tidak berat
            
        except Exception as e:
            print(f"Terjadi error: {e}")
            time.sleep(5)

if __name__ == "__main__":
    main()