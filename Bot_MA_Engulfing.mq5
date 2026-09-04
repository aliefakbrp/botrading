//+------------------------------------------------------------------+
//|                                         Bot_MA_Engulfing.mq5     |
//|  Versi MQL5 dari bot Python (MetaTrader5 python API)             |
//|  Strategi: MA5/MA10 rejection + Engulfing + filter sideways ATR  |
//+------------------------------------------------------------------+
#property copyright "Converted from Python bot"
#property version   "1.00"
#property strict

//==============================================================================
// 1. PARAMETER KONFIGURASI BOT LIVE
//==============================================================================
input string   InpSymbol               = "XAUUSDm";
input double   InpLot                  = 0.01;
input int      InpSLBufferPoints       = 50;
input int      InpSidewaysLookback     = 10;
input int      InpATRPeriod            = 14;
input double   InpMinTrendEfficiency   = 0.30;
input double   InpMinMA10SlopeATR      = 0.50;
input double   InpMinEngulfBodyATR     = 0.10;
input int      InpMaxEntriesPerDir     = 3;

input ENUM_TIMEFRAMES InpTimeframe     = PERIOD_H1;
input ulong    InpMagicNumber          = 101010;
input ulong    InpDeviation            = 20;

//==============================================================================
// Struktur data candle (menggantikan baris DataFrame python)
//==============================================================================
struct SCandle
  {
   datetime time;
   double   open;
   double   high;
   double   low;
   double   close;
   double   ma5;
   double   ma10;
   double   atr;
  };

//==============================================================================
// Variabel Global
//==============================================================================
datetime g_lastCandleTime = 0;
double   g_pointSize      = 0.0;
string   g_currentDirection = ""; // "" , "BUY" , "SELL"

//==============================================================================
// 2. FUNGSI DATA (mengganti get_data() python)
//==============================================================================
// Mengambil 100 candle terakhir dan menghitung ma5, ma10, atr.
// Array hasil di-index secara "series": [0]=candle berjalan (belum close),
// [1]=candle terakhir yang sudah close (setara df.iloc[-2] python),
// [2]=candle sebelum itu (setara df.iloc[-3] python), dst.
bool GetData(SCandle &candles[])
  {
   MqlRates rates[];
   int copied = CopyRates(InpSymbol, InpTimeframe, 0, 100, rates);
   if(copied < 20)
      return false;

   ArraySetAsSeries(rates, true);

   int n = copied;
   ArrayResize(candles, n);

   for(int i = 0; i < n; i++)
     {
      candles[i].time  = rates[i].time;
      candles[i].open  = rates[i].open;
      candles[i].high  = rates[i].high;
      candles[i].low   = rates[i].low;
      candles[i].close = rates[i].close;
      candles[i].ma5   = 0.0;
      candles[i].ma10  = 0.0;
      candles[i].atr   = 0.0;
     }

   // MA5 : rolling mean of close (5 candle, termasuk candle i s/d i+4)
   for(int i = 0; i <= n - 5; i++)
     {
      double sum = 0.0;
      for(int k = 0; k < 5; k++)
         sum += candles[i + k].close;
      candles[i].ma5 = sum / 5.0;
     }

   // MA10 : rolling mean of close (10 candle)
   for(int i = 0; i <= n - 10; i++)
     {
      double sum = 0.0;
      for(int k = 0; k < 10; k++)
         sum += candles[i + k].close;
      candles[i].ma10 = sum / 10.0;
     }

   // True Range lalu ATR = rolling mean sederhana (SAMA seperti pandas
   // rolling().mean() di python -- BUKAN smoothing Wilder standar MT5)
   double tr[];
   ArrayResize(tr, n);
   for(int i = 0; i < n; i++)
      tr[i] = 0.0;

   for(int i = 0; i <= n - 2; i++)
     {
      double prevClose = candles[i + 1].close; // candle sebelumnya secara waktu
      double a = candles[i].high - candles[i].low;
      double b = MathAbs(candles[i].high - prevClose);
      double c = MathAbs(candles[i].low  - prevClose);
      tr[i] = MathMax(a, MathMax(b, c));
     }

   for(int i = 0; i <= n - InpATRPeriod - 1; i++)
     {
      double sum = 0.0;
      for(int k = 0; k < InpATRPeriod; k++)
         sum += tr[i + k];
      candles[i].atr = sum / InpATRPeriod;
     }

   return true;
  }

//==============================================================================
// 3. FUNGSI LOGIKA UTAMA
//==============================================================================
bool IsSideways(const SCandle &candles[])
  {
   // Butuh minimal InpSidewaysLookback candle yang sudah close (index 1..lookback)
   if(ArraySize(candles) < InpSidewaysLookback + 1)
      return true;

   double atr = candles[1].atr; // atr candle terakhir yang sudah close
   if(atr <= 0.0)
      return true;

   double totalMovement = 0.0;
   for(int k = 1; k <= InpSidewaysLookback - 1; k++)
      totalMovement += MathAbs(candles[k].close - candles[k + 1].close);

   double netMovement = MathAbs(candles[1].close - candles[InpSidewaysLookback].close);
   double efficiency  = (totalMovement > 0.0) ? (netMovement / totalMovement) : 0.0;
   double ma10Slope   = MathAbs(candles[1].ma10 - candles[InpSidewaysLookback].ma10);

   return (efficiency < InpMinTrendEfficiency && ma10Slope < atr * InpMinMA10SlopeATR);
  }

// Mengembalikan "BUY","SELL" atau "" (kosong = tidak ada sinyal).
// signalCandle diisi dengan candle acuan (setara df.iloc[-2] python).
string EngulfingSignal(const SCandle &candles[], SCandle &signalCandle)
  {
   int n = ArraySize(candles);
   if(n < 3)
     {
      if(n > 0) signalCandle = candles[1 < n ? 1 : 0];
      return "";
     }

   SCandle previous = candles[2]; // df.iloc[-3]
   SCandle current  = candles[1]; // df.iloc[-2]
   signalCandle = current;

   double atr = current.atr;
   if(atr <= 0.0)
      return "";

   double previousBody = MathAbs(previous.close - previous.open);
   double currentBody  = MathAbs(current.close  - current.open);
   bool validBody = (currentBody >= previousBody && currentBody >= atr * InpMinEngulfBodyATR);

   bool bullishEngulfing =
      (previous.close < previous.open) &&
      (current.close  > current.open)  &&
      (current.open  <= previous.close) &&
      (current.close >= previous.open)  &&
      validBody;

   bool bearishEngulfing =
      (previous.close > previous.open) &&
      (current.close  < current.open)  &&
      (current.open  >= previous.close) &&
      (current.close <= previous.open)  &&
      validBody;

   bool touchedMA5  = (current.low <= current.ma5  && current.ma5  <= current.high);
   bool touchedMA10 = (current.low <= current.ma10 && current.ma10 <= current.high);

   bool bullishMARejection = (touchedMA5  && current.close > current.ma5) ||
                              (touchedMA10 && current.close > current.ma10);
   bool bearishMARejection = (touchedMA5  && current.close < current.ma5) ||
                              (touchedMA10 && current.close < current.ma10);

   if(bullishEngulfing && bullishMARejection)
      return "BUY";
   if(bearishEngulfing && bearishMARejection)
      return "SELL";

   return "";
  }

string ContinuationSignal(const SCandle &candles[], string currentDirection,
                           int numActivePositions, SCandle &signalCandle)
  {
   int n = ArraySize(candles);
   if(numActivePositions == 0 || currentDirection == "")
     {
      if(n > 0) signalCandle = candles[1 < n ? 1 : 0];
      return "";
     }
   if(numActivePositions >= InpMaxEntriesPerDir)
     {
      if(n > 0) signalCandle = candles[1 < n ? 1 : 0];
      return "";
     }
   if(n < 2)
      return "";

   SCandle current = candles[1];
   signalCandle = current;

   bool touchedMA5  = (current.low <= current.ma5  && current.ma5  <= current.high);
   bool touchedMA10 = (current.low <= current.ma10 && current.ma10 <= current.high);

   if(currentDirection == "BUY")
     {
      bool rejection = (touchedMA5 && current.close > current.ma5) ||
                        (touchedMA10 && current.close > current.ma10);
      if(current.close > current.open && rejection)
         return "BUY";
     }
   else if(currentDirection == "SELL")
     {
      bool rejection = (touchedMA5 && current.close < current.ma5) ||
                        (touchedMA10 && current.close < current.ma10);
      if(current.close < current.open && rejection)
         return "SELL";
     }

   return "";
  }

//==============================================================================
// 4. FUNGSI EKSEKUSI MT5 (LIVE TRADING)
//==============================================================================
int GetActivePositions(ulong &tickets[])
  {
   ArrayResize(tickets, 0);
   int total = PositionsTotal();
   int count = 0;
   for(int i = 0; i < total; i++)
     {
      ulong ticket = PositionGetTicket(i);
      if(ticket == 0)
         continue;
      if(!PositionSelectByTicket(ticket))
         continue;
      if(PositionGetString(POSITION_SYMBOL) != InpSymbol)
         continue;
      if((ulong)PositionGetInteger(POSITION_MAGIC) != InpMagicNumber)
         continue;

      count++;
      ArrayResize(tickets, count);
      tickets[count - 1] = ticket;
     }
   return count;
  }

double CalculateLiveSL(string signal, const SCandle &candle)
  {
   double bufferDistance = InpSLBufferPoints * g_pointSize;
   MqlTick tick;
   SymbolInfoTick(InpSymbol, tick);

   if(signal == "BUY")
     {
      double reference = MathMin(candle.low, candle.ma10);
      return MathMin(reference - bufferDistance, tick.ask - bufferDistance);
     }
   else
     {
      double reference = MathMax(candle.high, candle.ma10);
      return MathMax(reference + bufferDistance, tick.bid + bufferDistance);
     }
  }

void OpenTrade(string orderType, double slPrice)
  {
   if(!SymbolInfoInteger(InpSymbol, SYMBOL_VISIBLE))
      SymbolSelect(InpSymbol, true);

   MqlTick tick;
   SymbolInfoTick(InpSymbol, tick);

   ENUM_ORDER_TYPE action;
   double price;
   if(orderType == "BUY")
     {
      action = ORDER_TYPE_BUY;
      price  = tick.ask;
     }
   else
     {
      action = ORDER_TYPE_SELL;
      price  = tick.bid;
     }

   MqlTradeRequest request;
   MqlTradeResult  result;
   ZeroMemory(request);
   ZeroMemory(result);

   request.action       = TRADE_ACTION_DEAL;
   request.symbol       = InpSymbol;
   request.volume       = InpLot;
   request.type         = action;
   request.price        = price;
   request.sl           = slPrice;
   request.deviation    = InpDeviation;
   request.magic        = InpMagicNumber;
   request.comment      = "Bot_MA_Engulfing";
   request.type_time    = ORDER_TIME_GTC;
   request.type_filling = ORDER_FILLING_IOC;

   if(!OrderSend(request, result) || result.retcode != TRADE_RETCODE_DONE)
      PrintFormat("[!] Gagal Eksekusi %s: %s (Code: %d)", orderType, result.comment, result.retcode);
   else
      PrintFormat("[+] Berhasil Eksekusi %s @ %.5f | SL: %.5f", orderType, price, slPrice);
  }

void CloseAllPositions()
  {
   ulong tickets[];
   int count = GetActivePositions(tickets);

   for(int i = 0; i < count; i++)
     {
      if(!PositionSelectByTicket(tickets[i]))
         continue;

      double volume = PositionGetDouble(POSITION_VOLUME);
      long   type   = PositionGetInteger(POSITION_TYPE);

      MqlTick tick;
      SymbolInfoTick(InpSymbol, tick);

      ENUM_ORDER_TYPE orderType;
      double price;
      if(type == POSITION_TYPE_BUY)
        {
         orderType = ORDER_TYPE_SELL;
         price     = tick.bid;
        }
      else
        {
         orderType = ORDER_TYPE_BUY;
         price     = tick.ask;
        }

      MqlTradeRequest request;
      MqlTradeResult  result;
      ZeroMemory(request);
      ZeroMemory(result);

      request.action       = TRADE_ACTION_DEAL;
      request.symbol       = InpSymbol;
      request.volume       = volume;
      request.type         = orderType;
      request.position     = tickets[i];
      request.price        = price;
      request.deviation    = InpDeviation;
      request.magic        = InpMagicNumber;
      request.comment      = "Bot_Reverse_Close";
      request.type_time    = ORDER_TIME_GTC;
      request.type_filling = ORDER_FILLING_IOC;

      if(!OrderSend(request, result) || result.retcode != TRADE_RETCODE_DONE)
         PrintFormat("[!] Gagal menutup posisi %I64u: %s", tickets[i], result.comment);
      else
         PrintFormat("[*] Posisi %I64u berhasil ditutup.", tickets[i]);
     }
  }

//==============================================================================
// 5. ENGINE UTAMA BOT LIVE
//==============================================================================
int OnInit()
  {
   g_pointSize = SymbolInfoDouble(InpSymbol, SYMBOL_POINT);
   g_lastCandleTime = 0;
   g_currentDirection = "";

   PrintFormat("=========================================================");
   PrintFormat("[*] LIVE TRADING BOT BERJALAN | Aset: %s", InpSymbol);
   PrintFormat("[*] Terhubung ke akun: %I64d", AccountInfoInteger(ACCOUNT_LOGIN));
   PrintFormat("=========================================================");

   return(INIT_SUCCEEDED);
  }

void OnDeinit(const int reason)
  {
   Print("[!] Bot Live Trading dihentikan.");
  }

void OnTick()
  {
   // 1. Tarik data terbaru
   SCandle candles[];
   if(!GetData(candles))
      return;

   datetime currentCandleTime = candles[1].time; // setara df.iloc[-2]["time"]

   // 2. Evaluasi HANYA JIKA ada candle yang baru ditutup
   if(g_lastCandleTime == 0 || currentCandleTime > g_lastCandleTime)
     {
      g_lastCandleTime = currentCandleTime;
      PrintFormat("[-] Menunggu peluang... Waktu Server: %s", TimeToString(TimeCurrent(), TIME_SECONDS));

      // Cek Posisi Aktif Saat Ini
      ulong tickets[];
      int numPositions = GetActivePositions(tickets);

      string currentDirection = "";
      if(numPositions > 0)
        {
         if(PositionSelectByTicket(tickets[0]))
            currentDirection = (PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY) ? "BUY" : "SELL";
        }

      // Evaluasi Sinyal
      SCandle signalCandle;
      string signal = EngulfingSignal(candles, signalCandle);

      if(signal == "")
         signal = ContinuationSignal(candles, currentDirection, numPositions, signalCandle);

      // Eksekusi jika ada sinyal
      if(signal != "")
        {
         if(IsSideways(candles))
           {
            Print("[!] Sinyal terdeteksi tapi diabaikan (Pasar Sideways).");
           }
         else
           {
            PrintFormat("[+] Sinyal Valid Terdeteksi: %s", signal);

            // Jika sinyal berlawanan arah dengan posisi saat ini -> Tutup semua (Reverse)
            if(currentDirection != "" && signal != currentDirection)
              {
               Print("[*] Sinyal Berbalik Arah! Melakukan Reverse Close...");
               CloseAllPositions();
               numPositions = 0; // Update jumlah posisi setelah ditutup
              }

            // Buka Posisi Baru (Single / Multi-Entry)
            if(numPositions < InpMaxEntriesPerDir)
              {
               double slPrice = CalculateLiveSL(signal, signalCandle);
               OpenTrade(signal, slPrice);
              }
            else
              {
               PrintFormat("[!] Batas maksimal entry (%d) telah tercapai.", InpMaxEntriesPerDir);
              }
           }
        }
     }
  }
//+------------------------------------------------------------------+
