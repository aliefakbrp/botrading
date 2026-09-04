//+------------------------------------------------------------------+
//|                                         EA_MA_Engulfing_H1.mq5   |
//|                        Expert Advisor Backtest & Live Trading    |
//|                    Berdasarkan Logika backtest_ma5_ma10.py       |
//+------------------------------------------------------------------+
#property copyright "Alief Akbar Purnama"
#property link      ""
#property version   "1.00"
#property description "EA Strategi Candlestick Engulfing + MA Rejection + Multi-Layering + Sideways Filter"

#include <Trade\Trade.mqh>
#include <Trade\PositionInfo.mqh>

//+------------------------------------------------------------------+
//| INPUT PARAMETERS                                                 |
//+------------------------------------------------------------------+
input group "=== Parameter Moving Average (Best H1) ==="
input int      InpMAFast               = 1;        // Periode MA Fast (Juara H1 Survivor: 1, 2026: 14)
input int      InpMASlow               = 27;       // Periode MA Slow (Juara H1 Survivor: 27, 2026: 41)
input ENUM_MA_METHOD InpMAMethod       = MODE_SMA; // Metode MA (SMA)
input ENUM_APPLIED_PRICE InpMAPrice    = PRICE_CLOSE; // Applied Price MA

input group "=== Manajemen Transaksi & Lot ==="
input double   InpLotSize              = 0.01;     // Ukuran Lot Transaksi
input ulong    InpMagicNumber          = 51011;    // Magic Number Bot
input int      InpSLBufferPoints       = 50;       // Stop Loss Buffer (Points)
input int      InpMaxEntries           = 3;        // Maksimal Posisi per Arah (Multi-Entry)
input int      InpDeviation            = 20;       // Slippage / Deviation Points

input group "=== Parameter Filter & Indikator ==="
input int      InpATRPeriod            = 14;       // Periode ATR
input int      InpSidewaysLookback     = 10;       // Lookback Periode Sideways
input double   InpMinTrendEfficiency   = 0.30;     // Min Trend Efficiency (0.30)
input double   InpMinMASlowSlopeATR    = 0.50;     // Min MA Slow Slope rasio ATR (0.50)
input double   InpMinEngulfingBodyATR  = 0.10;     // Min Body Candle Rasio ATR (0.10)

//+------------------------------------------------------------------+
//| GLOBAL OBJECTS & VARIABLES                                       |
//+------------------------------------------------------------------+
CTrade         trade;
CPositionInfo  posInfo;

int            h_ma_fast = INVALID_HANDLE;
int            h_ma_slow = INVALID_HANDLE;
int            h_atr     = INVALID_HANDLE;

datetime       last_processed_bar = 0;
datetime       last_entry_bar     = 0;

//+------------------------------------------------------------------+
//| Expert initialization function                                   |
//+------------------------------------------------------------------+
int OnInit()
{
   trade.SetExpertMagicNumber(InpMagicNumber);
   trade.SetDeviationInPoints(InpDeviation);
   trade.SetTypeFillingBySymbol(_Symbol);

   // Inisialisasi Handle Indikator
   h_ma_fast = iMA(_Symbol, _Period, InpMAFast, 0, InpMAMethod, InpMAPrice);
   h_ma_slow = iMA(_Symbol, _Period, InpMASlow, 0, InpMAMethod, InpMAPrice);
   h_atr     = iATR(_Symbol, _Period, InpATRPeriod);

   if(h_ma_fast == INVALID_HANDLE || h_ma_slow == INVALID_HANDLE || h_atr == INVALID_HANDLE)
   {
      Print("[!] Error: Gagal menginisialisasi handle indikator (MA/ATR).");
      return(INIT_FAILED);
   }

   PrintFormat("[+] EA Aktif: %s %s | MA Fast=%d, MA Slow=%d, Lot=%.2f, Max Layer=%d",
               _Symbol, EnumToString(_Period), InpMAFast, InpMASlow, InpLotSize, InpMaxEntries);
   return(INIT_SUCCEEDED);
}

//+------------------------------------------------------------------+
//| Expert deinitialization function                                 |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   if(h_ma_fast != INVALID_HANDLE) IndicatorRelease(h_ma_fast);
   if(h_ma_slow != INVALID_HANDLE) IndicatorRelease(h_ma_slow);
   if(h_atr     != INVALID_HANDLE) IndicatorRelease(h_atr);
}

//+------------------------------------------------------------------+
//| Helper: Hitung Jumlah & Tipe Posisi Aktif Milik Bot             |
//+------------------------------------------------------------------+
void GetActivePositions(int &count, ENUM_POSITION_TYPE &active_type)
{
   count = 0;
   active_type = (ENUM_POSITION_TYPE)-1;

   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      if(posInfo.SelectByIndex(i))
      {
         if(posInfo.Symbol() == _Symbol && posInfo.Magic() == InpMagicNumber)
         {
            count++;
            active_type = posInfo.PositionType();
         }
      }
   }
}

//+------------------------------------------------------------------+
//| Helper: Reverse Close (Tutup Semua Posisi Berlawanan)            |
//+------------------------------------------------------------------+
void CloseAllPositions()
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      if(posInfo.SelectByIndex(i))
      {
         if(posInfo.Symbol() == _Symbol && posInfo.Magic() == InpMagicNumber)
         {
            trade.PositionClose(posInfo.Ticket());
         }
      }
   }
}

//+------------------------------------------------------------------+
//| Helper: Deteksi Kondisi Market Sideways                          |
//+------------------------------------------------------------------+
bool IsSideways(const MqlRates &rates[], const double &ma_slow_buf[], const double atr_val)
{
   if(ArraySize(rates) < InpSidewaysLookback + 2) return true;
   if(atr_val <= 0 || MathIsValidNumber(atr_val) == false) return true;

   double total_movement = 0.0;
   for(int k = 1; k < InpSidewaysLookback; k++)
   {
      total_movement += MathAbs(rates[k].close - rates[k + 1].close);
   }

   double net_movement = MathAbs(rates[1].close - rates[InpSidewaysLookback].close);
   double efficiency = (total_movement > 0) ? (net_movement / total_movement) : 0.0;
   double ma_slope = MathAbs(ma_slow_buf[1] - ma_slow_buf[InpSidewaysLookback]);

   return (efficiency < InpMinTrendEfficiency && ma_slope < atr_val * InpMinMASlowSlopeATR);
}

//+------------------------------------------------------------------+
//| Expert tick function                                             |
//+------------------------------------------------------------------+
void OnTick()
{
   // Pastikan hanya dieksekusi 1 kali saat Bar Baru terbentuk (Sama persis dengan Engine Backtest)
   datetime current_bar_time = iTime(_Symbol, _Period, 0);
   if(current_bar_time == last_processed_bar) return;

   int needed_bars = MathMax(InpSidewaysLookback, MathMax(InpMAFast, InpMASlow)) + 10;
   MqlRates rates[];
   ArraySetAsSeries(rates, true);
   if(CopyRates(_Symbol, _Period, 0, needed_bars, rates) < needed_bars) return;

   double ma_fast_buf[];
   double ma_slow_buf[];
   double atr_buf[];
   ArraySetAsSeries(ma_fast_buf, true);
   ArraySetAsSeries(ma_slow_buf, true);
   ArraySetAsSeries(atr_buf, true);

   if(CopyBuffer(h_ma_fast, 0, 0, needed_bars, ma_fast_buf) < needed_bars) return;
   if(CopyBuffer(h_ma_slow, 0, 0, needed_bars, ma_slow_buf) < needed_bars) return;
   if(CopyBuffer(h_atr,     0, 0, needed_bars, atr_buf)     < needed_bars) return;

   last_processed_bar = current_bar_time;

   // Bar [1] = Candle yang baru saja close (current)
   // Bar [2] = Candle sebelumnya (previous)
   double prev_open  = rates[2].open;
   double prev_close = rates[2].close;
   double c_open     = rates[1].open;
   double c_high     = rates[1].high;
   double c_low      = rates[1].low;
   double c_close    = rates[1].close;
   double c_atr      = atr_buf[1];
   double c_ma_fast  = ma_fast_buf[1];
   double c_ma_slow  = ma_slow_buf[1];

   if(c_atr <= 0 || MathIsValidNumber(c_atr) == false) return;

   // 1. Evaluasi Candlestick Engulfing
   double prev_body = MathAbs(prev_close - prev_open);
   double cur_body  = MathAbs(c_close - c_open);
   bool valid_body  = (cur_body >= prev_body) && (cur_body >= c_atr * InpMinEngulfingBodyATR);

   bool bullish_engulfing = (prev_close < prev_open) && (c_close > c_open) && 
                            (c_open <= prev_close) && (c_close >= prev_open) && valid_body;
   bool bearish_engulfing = (prev_close > prev_open) && (c_close < c_open) && 
                            (c_open >= prev_close) && (c_close <= prev_open) && valid_body;

   // 2. Evaluasi Sentuhan & Rejection MA
   bool touched_ma_fast = (c_low <= c_ma_fast) && (c_ma_fast <= c_high);
   bool touched_ma_slow = (c_low <= c_ma_slow) && (c_ma_slow <= c_high);

   bool bullish_ma_rejection = (touched_ma_fast && c_close > c_ma_fast) || (touched_ma_slow && c_close > c_ma_slow);
   bool bearish_ma_rejection = (touched_ma_fast && c_close < c_ma_fast) || (touched_ma_slow && c_close < c_ma_slow);

   int signal = 0; // 1: BUY, -1: SELL
   bool is_continuation = false;

   if(bullish_engulfing && bullish_ma_rejection)
   {
      signal = 1;
   }
   else if(bearish_engulfing && bearish_ma_rejection)
   {
      signal = -1;
   }
   else
   {
      // 3. Evaluasi Continuation Signal jika tidak ada Engulfing
      int active_count = 0;
      ENUM_POSITION_TYPE active_type;
      GetActivePositions(active_count, active_type);

      if(active_count > 0 && active_count < InpMaxEntries)
      {
         if(active_type == POSITION_TYPE_BUY)
         {
            if(c_close > c_open && bullish_ma_rejection)
            {
               signal = 1;
               is_continuation = true;
            }
         }
         else if(active_type == POSITION_TYPE_SELL)
         {
            if(c_close < c_open && bearish_ma_rejection)
            {
               signal = -1;
               is_continuation = true;
            }
         }
      }
   }

   if(signal == 0) return;

   // 4. Cek Filter Sideways
   if(IsSideways(rates, ma_slow_buf, c_atr))
   {
      return; // Market terdeteksi sideways -> Lewati eksekusi
   }

   // 5. Eksekusi Order & Reverse Close
   int pos_count = 0;
   ENUM_POSITION_TYPE pos_direction;
   GetActivePositions(pos_count, pos_direction);

   ENUM_POSITION_TYPE desired_type = (signal == 1) ? POSITION_TYPE_BUY : POSITION_TYPE_SELL;

   // Jika ada posisi berlawanan arah -> Reverse Close All
   if(pos_count > 0 && pos_direction != desired_type)
   {
      CloseAllPositions();
      pos_count = 0;
   }

   // Cek batas maksimal posisi
   if(pos_count >= InpMaxEntries) return;

   // Mencegah duplikasi entri continuation pada bar yang sama
   if(is_continuation && last_entry_bar == current_bar_time) return;

   // 6. Hitung Stop Loss (SL) Sesuai Logika Python
   double buffer_dist = InpSLBufferPoints * _Point;
   double sl = 0.0;

   if(desired_type == POSITION_TYPE_BUY)
   {
      double ask_price = SymbolInfoDouble(_Symbol, SYMBOL_ASK);
      double ref = MathMin(c_low, c_ma_slow);
      sl = MathMin(ref - buffer_dist, ask_price - buffer_dist);
      sl = NormalizeDouble(sl, _Digits);

      if(trade.Buy(InpLotSize, _Symbol, ask_price, sl, 0, is_continuation ? "Continuation BUY" : "Engulfing BUY"))
      {
         last_entry_bar = current_bar_time;
      }
   }
   else
   {
      double bid_price = SymbolInfoDouble(_Symbol, SYMBOL_BID);
      double ref = MathMax(c_high, c_ma_slow);
      sl = MathMax(ref + buffer_dist, bid_price + buffer_dist);
      sl = NormalizeDouble(sl, _Digits);

      if(trade.Sell(InpLotSize, _Symbol, bid_price, sl, 0, is_continuation ? "Continuation SELL" : "Engulfing SELL"))
      {
         last_entry_bar = current_bar_time;
      }
   }
}
//+------------------------------------------------------------------+
