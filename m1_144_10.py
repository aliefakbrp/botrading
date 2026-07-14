import MetaTrader5 as mt5
import pandas as pd
import pandas_ta as ta
import time
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import pytz

class XAUUSD_TradingBot:
    def __init__(self, login, password, server, symbol="XAUUSDm", timeframe=mt5.TIMEFRAME_M1):
        # Konfigurasi Akun dan Simbol
        self.login = login
        self.password = password
        self.server = server
        self.symbol = symbol
        self.timeframe = timeframe
        
        # Konfigurasi Manajemen Risiko
        self.lot_size = 0.01
        self.sl_pips = 100
        self.tp_pips = 200
        self.sl_plus_trigger_pips = 50
        self.max_daily_loss_pct = 3.0
        
        # Inisialisasi Zona Waktu (MT5 biasanya menggunakan waktu server, kita set ke UTC untuk standarisasi News)
        self.utc = pytz.UTC

    def initialize_mt5(self):
        # Mencoba melakukan inisialisasi dan login ke terminal MT5
        if not mt5.initialize(login=self.login, password=self.password, server=self.server):
            print(f"Gagal inisialisasi MT5, Error: {mt5.last_error()}")
            return False
            
        # Memastikan simbol tersedia dan terlihat di Market Watch
        if not mt5.symbol_select(self.symbol, True):
            print(f"Simbol {self.symbol} tidak ditemukan!")
            return False
            
        print("Berhasil terhubung ke MetaTrader 5!")
        return True

    def get_market_data(self):
        # Mengambil 200 candle terakhir untuk perhitungan indikator
        rates = mt5.copy_rates_from_pos(self.symbol, self.timeframe, 0, 200)
        if rates is None:
            return None
            
        # Mengonversi data ke Pandas DataFrame
        df = pd.DataFrame(rates)
        df['time'] = pd.to_datetime(df['time'], unit='s')
        
        # Menghitung Indikator menggunakan pandas_ta
        df['MA_10'] = ta.sma(df['close'], length=10)
        df['MA_144'] = ta.sma(df['close'], length=144)
        
        # ADX mengembalikan DataFrame dengan kolom ADX_14, DMP_14, DMN_14
        adx = ta.adx(df['high'], df['low'], df['close'], length=14)
        df['ADX'] = adx['ADX_14']
        
        df['RSI'] = ta.rsi(df['close'], length=14)
        df['ATR'] = ta.atr(df['high'], df['low'], df['close'], length=14)
        
        return df

    def check_news_filter(self):
        # Membaca RSS Feed dari ForexFactory
        try:
            url = "https://nfs.faireconomy.media/ff_calendar_thisweek.xml"
            response = requests.get(url, timeout=10)
            root = ET.fromstring(response.content)
            
            now_utc = datetime.now(self.utc)
            
            for item in root.findall('event'):
                impact = item.find('impact').text
                country = item.find('country').text
                date_str = item.find('date').text # Format: 07-10-2026
                time_str = item.find('time').text # Format: 1:30pm
                
                # Hanya peduli dengan berita USD (mempengaruhi XAUUSD) dengan Impact High
                if country == "USD" and impact == "High":
                    # Parsing waktu berita
                    dt_str = f"{date_str} {time_str}"
                    news_time = datetime.strptime(dt_str, "%m-%d-%Y %I:%M%p").replace(tzinfo=self.utc)
                    
                    # Cek selisih waktu
                    time_diff = (news_time - now_utc).total_seconds() / 60.0
                    
                    # Jika berita terjadi dalam rentang -60 menit (sudah lewat) hingga +60 menit (akan datang)
                    if -60 <= time_diff <= 60:
                        return True # Berita sedang/akan terjadi, pause trading!
            return False
        except Exception as e:
            print(f"Error mengambil data berita: {e}")
            # Failsafe: Jika error baca berita, anggap aman agar bot tetap jalan (atau ubah ke True untuk super ketat)
            return False

    def check_circuit_breaker(self):
        # Mengecek batas kerugian harian maksimal (3%)
        account_info = mt5.account_info()
        if account_info is None:
            return False
            
        balance = account_info.balance
        equity = account_info.equity
        
        # Mengambil history transaksi hari ini
        today = datetime.now()
        start_of_day = datetime(today.year, today.month, today.day)
        
        history_deals = mt5.history_deals_get(start_of_day, today)
        daily_pnl = 0.0
        
        if history_deals is not None and len(history_deals) > 0:
            for deal in history_deals:
                # Menjumlahkan profit dari trade yang tertutup
                daily_pnl += deal.profit 
                
        # Menghitung persentase loss
        if daily_pnl < 0:
            loss_pct = (abs(daily_pnl) / balance) * 100
            if loss_pct >= self.max_daily_loss_pct:
                return True # Circuit breaker aktif!
        return False

    def manage_trailing_stop(self):
        # Mengambil posisi yang sedang terbuka khusus untuk simbol bot ini
        positions = mt5.positions_get(symbol=self.symbol)
        if positions is None or len(positions) == 0:
            return
            
        symbol_info = mt5.symbol_info(self.symbol)
        # Pada XAUUSD MT5, 1 pip biasanya = 10 points (jika broker 2/3 digit belakang koma)
        pip_value = symbol_info.point * 10 
        
        for pos in positions:
            current_price = mt5.symbol_info_tick(self.symbol).bid if pos.type == mt5.ORDER_TYPE_BUY else mt5.symbol_info_tick(self.symbol).ask
            
            # SL+ Logic untuk Posisi BUY
            if pos.type == mt5.ORDER_TYPE_BUY:
                profit_pips = (current_price - pos.price_open) / pip_value
                # Jika profit sudah menyentuh trigger SL+ dan SL saat ini masih di bawah harga entry
                if profit_pips >= self.sl_plus_trigger_pips and pos.sl < pos.price_open:
                    new_sl = pos.price_open + (2 * pip_value) # Lock BE + 2 pips
                    self.modify_sl(pos.ticket, new_sl)
                    print(f"SL+ Aktif untuk BUY Ticket {pos.ticket}. SL digeser ke {new_sl}")
                    
            # SL+ Logic untuk Posisi SELL
            elif pos.type == mt5.ORDER_TYPE_SELL:
                profit_pips = (pos.price_open - current_price) / pip_value
                # Jika profit sudah menyentuh trigger SL+ dan SL saat ini masih di atas harga entry
                if profit_pips >= self.sl_plus_trigger_pips and (pos.sl > pos.price_open or pos.sl == 0):
                    new_sl = pos.price_open - (2 * pip_value) # Lock BE + 2 pips
                    self.modify_sl(pos.ticket, new_sl)
                    print(f"SL+ Aktif untuk SELL Ticket {pos.ticket}. SL digeser ke {new_sl}")

    def modify_sl(self, ticket, new_sl):
        # Mengirim request modifikasi Stop Loss ke broker
        request = {
            "action": mt5.TRADE_ACTION_SLTP,
            "position": ticket,
            "sl": float(new_sl),
        }
        mt5.order_send(request)

    def send_order(self, order_type, price):
        symbol_info = mt5.symbol_info(self.symbol)
        pip_value = symbol_info.point * 10 
        
        # Mengatur SL dan TP Statis secara instan (Hard Stop Loss)
        if order_type == mt5.ORDER_TYPE_BUY:
            sl = price - (self.sl_pips * pip_value)
            tp = price + (self.tp_pips * pip_value)
        else:
            sl = price + (self.sl_pips * pip_value)
            tp = price - (self.tp_pips * pip_value)
            
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": self.symbol,
            "volume": self.lot_size,
            "type": order_type,
            "price": price,
            "sl": float(sl),
            "tp": float(tp),
            "deviation": 20,
            "magic": 101010,
            "comment": "Bot_MA144",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        
        result = mt5.order_send(request)
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            print(f"Order gagal. Kode error: {result.retcode}")
        else:
            print(f"Order berhasil dieksekusi! Tiket: {result.order}")

    def run(self):
        if not self.initialize_mt5():
            return

        print("=== Bot Trading XAUUSD Dimulai ===")
        
        while True:
            try:
                # 1. Tarik Data dan Hitung Indikator
                df = self.get_market_data()
                if df is None or df.empty:
                    time.sleep(10)
                    continue
                    
                latest = df.iloc[-1]
                prev = df.iloc[-2] # Untuk mendeteksi pergerakan ekstrem dari candle sebelumnya
                
                # Data Harga Saat Ini
                tick = mt5.symbol_info_tick(self.symbol)
                ask_price = tick.ask
                bid_price = tick.bid
                
                # Membersihkan layar terminal sederhana (opsional, menggunakan newline print agar riwayat terlihat)
                print("-" * 50)
                print(f"Waktu: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} WIB")
                print(f"Harga {self.symbol} -> Bid: {bid_price:.2f} | Ask: {ask_price:.2f}")
                print(f"Indikator -> MA10: {latest['MA_10']:.2f} | MA144: {latest['MA_144']:.2f} | ADX: {latest['ADX']:.2f} | RSI: {latest['RSI']:.2f}")
                
                # 2. Daily Circuit Breaker
                if self.check_circuit_breaker():
                    print("⚠️ CIRCUIT BREAKER AKTIF! Kerugian harian mencapai batas 3%. Bot dihentikan hingga besok.")
                    # Menutup semua posisi terbuka (Logic close all bisa ditambahkan jika perlu)
                    time.sleep(3600) # Tidur 1 jam sebelum ngecek lagi
                    continue
                
                # 3. Filter Eksekusi: Sideways & News
                is_sideways = latest['ADX'] < 20
                is_news_time = self.check_news_filter()
                
                print(f"Status Filter -> Sideways: {'Ya' if is_sideways else 'Tidak'} | News (1 Jam): {'Ada News!' if is_news_time else 'Aman'}")
                
                # 4. Manajemen SL+
                self.manage_trailing_stop()
                
                # Cek jumlah posisi terbuka agar tidak overtrade
                open_positions = mt5.positions_get(symbol=self.symbol)
                if open_positions is not None and len(open_positions) > 0:
                    print(f"Posisi berjalan: {len(open_positions)} tiket.")
                    time.sleep(10)
                    continue # Tunggu posisi saat ini clear sebelum buka baru
                
                # 5. Anti-Catching Knife (Proteksi Volatilitas Ekstrem)
                candle_range = abs(latest['high'] - latest['low'])
                if candle_range > (2 * latest['ATR']):
                    print("⚠️ Peringatan: Volatilitas tidak wajar (> 2x ATR). Pause Entry (Anti-Catching Knife).")
                    time.sleep(10)
                    continue
                    
                # HENTIKAN eksekusi jika pasar sideways atau sedang news
                if is_sideways or is_news_time:
                    time.sleep(10)
                    continue
                
                # 6. Logika Struktur Tren
                kondisi_bullish = (latest['close'] > latest['MA_144']) and (latest['MA_10'] > latest['MA_144'])
                kondisi_bearish = (latest['close'] < latest['MA_144']) and (latest['MA_10'] < latest['MA_144'])
                
                # 7. Logika Entry Trigger (Pullback)
                margin_of_error = latest['ATR'] * 0.5 # Harga dianggap 'mendekati' MA jika berjarak setengah nilai ATR
                
                if kondisi_bullish:
                    # Pullback: Harga turun mendekati MA 10 atau MA 144
                    near_ma10 = abs(latest['low'] - latest['MA_10']) <= margin_of_error
                    near_ma144 = abs(latest['low'] - latest['MA_144']) <= margin_of_error
                    
                    if (near_ma10 or near_ma144) and (latest['RSI'] < 30 or prev['RSI'] < 30):
                        print("🔥 Sinyal BUY Ditemukan (Trend Naik + Pullback + Oversold)!")
                        self.send_order(mt5.ORDER_TYPE_BUY, ask_price)
                        
                elif kondisi_bearish:
                    # Pullback: Harga naik mendekati MA 10 atau MA 144
                    near_ma10 = abs(latest['high'] - latest['MA_10']) <= margin_of_error
                    near_ma144 = abs(latest['high'] - latest['MA_144']) <= margin_of_error
                    
                    if (near_ma10 or near_ma144) and (latest['RSI'] > 70 or prev['RSI'] > 70):
                        print("🔥 Sinyal SELL Ditemukan (Trend Turun + Pullback + Overbought)!")
                        self.send_order(mt5.ORDER_TYPE_SELL, bid_price)
                
            except Exception as e:
                print(f"Terjadi Error pada Loop Utama: {e}")
                
            # Jeda 10 detik sesuai request sebelum loop berulang
            time.sleep(10)

# ==========================================
# EKSEKUSI PROGRAM UTAMA
# ==========================================
if __name__ == "__main__":
    # GANTI DENGAN KREDENSIAL AKUN DEMO MT5 ANDA
    LOGIN_MT5 = 414017771 
    PASS_MT5 = "12qwaszX_"
    SERVER_MT5 = "Exness-MT5Trial6"
    
    bot = XAUUSD_TradingBot(login=LOGIN_MT5, password=PASS_MT5, server=SERVER_MT5)
    
    try:
        bot.run()
    except KeyboardInterrupt:
        print("\nMematikan bot secara manual...")
        mt5.shutdown()