//+------------------------------------------------------------------+
//|  XBTC_ROBOT.mq5                                                  |
//|  ALTIN (XAUUSD) + BITCOIN (BTCUSD)  -  OTOMATIK ROBOT (MT5)      |
//+------------------------------------------------------------------+
//  MANTIK "XBTC"  (testte iki sembolde de 2025 ve 2026'da karda cikan: 9/26/100, 15 DK, C)
//   Grafik 15 DAKIKALIK (robot hangi grafikte calisirsa calissin 15 dk mumlara bakar).
//   LONG : 9 EMA, 26 EMA'yi YUKARI keser VE mum 100 EMA'nin USTUNDE kapanir
//          -> kesisim mumu kapaninca, yeni mumun acilisinda ALIS.
//   SHORT: 9 EMA, 26 EMA'yi ASAGI keser VE mum 100 EMA'nin ALTINDA kapanir -> SATIS.
//   STOP : giristen 2 x ATR(14)   (ATR = son 14 mumun ortalama boyu, testteki gibi)
//   TP   : YOK.  9 EMA 26 EMA'yi TERS yone kesince (mum kapaninca) islem kapanir.
//   Sembol basina ayni anda tek islem.
//  RISK  : her islemde zarar sabit RiskDolar (30 $). Lot, stop mesafesine gore MT5'in kendi
//          OrderCalcProfit fonksiyonuyla hesaplanir.
//  GUNLUK ZARAR LIMITI: bugun kapanan + acik islemler toplami -250 $'a inerse robotun butun
//          islemleri kapatilir, o gun yeni islem acilmaz. Ertesi gun (sunucu saati 00:00) devam.
//  TELEGRAM: islem acilinca, kapaninca, limit dolunca ve her gun sonunda ozet.
//          MT5: Araclar > Secenekler > Uzman Danismanlar > "WebRequest izin ver" + https://api.telegram.org
//          Token ve Chat ID: robotun AYARLAR penceresine eski robottakinin aynisini yapistirin.
//  PANEL : sag ust kosede.
//+------------------------------------------------------------------+
#property copyright "XBTC ROBOT"
#property version   "1.00"

#include <Trade\Trade.mqh>

input string Semboller        = "XAUUSD,BTCUSD";   // Semboller (virgulle)
input double RiskDolar        = 30.0;              // Islem basina zarar ($)
input double GunlukZararLimit = 250.0;             // Gunluk zarar limiti ($)
input int    HizliEma         = 9;                 // Hizli EMA
input int    YavasEma         = 26;                // Yavas EMA
input int    YonEma           = 100;               // Yon EMA
input int    AtrPeriyot       = 14;                // ATR periyodu
input double StopAtr          = 2.0;               // Stop = ATR x
input int    Kayma            = 30;                // Izin verilen kayma (puan)
input ulong  Sihir            = 20261113;          // Magic number
input string TelegramToken    = "";                // Telegram bot token (eski robotla ayni)
input string TelegramChatID   = "";                // Telegram chat id (eski robotla ayni)
input bool   TelegramAcik     = true;              // Telegram mesajlari

#define ON_EK "XBTC_"

CTrade   trade;
string   S[];
datetime sonMum[];
string   KUYRUK[];
datetime tgBekle = 0;
string   tgDurum = "";
int      gunKey  = 0;
bool     limitDoldu = false;

//+------------------------------------------------------------------+
//  YARDIMCI
//+------------------------------------------------------------------+
int GunAnahtari(datetime t)
{
   MqlDateTime z; TimeToStruct(t, z);
   return(z.year * 10000 + z.mon * 100 + z.day);
}

datetime GunBasi(datetime t)
{
   MqlDateTime z; TimeToStruct(t, z);
   z.hour = 0; z.min = 0; z.sec = 0;
   return(StructToTime(z));
}

string Para(double x)
{
   return((x >= 0 ? "+" : "") + DoubleToString(x, 2) + " $");
}

string Fiyat(string sb, double p)
{
   return(DoubleToString(p, (int)SymbolInfoInteger(sb, SYMBOL_DIGITS)));
}

//+------------------------------------------------------------------+
//  TELEGRAM
//+------------------------------------------------------------------+
string UrlKodla(string s)
{
   uchar b[];
   int n = StringToCharArray(s, b, 0, WHOLE_ARRAY, CP_UTF8);
   string o = "";
   for(int i = 0; i < n; i++)
   {
      uchar c = b[i];
      if(c == 0) break;
      if((c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') ||
         c == '-' || c == '_' || c == '.' || c == '~')
         o += CharToString(c);
      else
         o += StringFormat("%%%02X", (int)c);
   }
   return(o);
}

void TgEkle(string metin)
{
   if(!TelegramAcik) return;
   int k = ArraySize(KUYRUK);
   ArrayResize(KUYRUK, k + 1);
   KUYRUK[k] = metin;
   if(ArraySize(KUYRUK) > 60)
   {
      int fazla = ArraySize(KUYRUK) - 60;
      for(int i = 0; i < 60; i++) KUYRUK[i] = KUYRUK[i + fazla];
      ArrayResize(KUYRUK, 60);
   }
}

void TgGonder()
{
   if(!TelegramAcik || MQLInfoInteger(MQL_TESTER)) { ArrayResize(KUYRUK, 0); return; }
   if(ArraySize(KUYRUK) == 0) return;
   if(StringLen(TelegramToken) < 10 || StringLen(TelegramChatID) < 2)
   {
      tgDurum = "Token / Chat ID girilmemis (robot ayarlari)";
      ArrayResize(KUYRUK, 0);
      return;
   }
   if(TimeLocal() < tgBekle) return;
   string url = "https://api.telegram.org/bot" + TelegramToken + "/sendMessage";
   string govde = "chat_id=" + TelegramChatID + "&text=" + UrlKodla(KUYRUK[0]);
   char veri[], sonuc[];
   StringToCharArray(govde, veri, 0, StringLen(govde));
   string basliklar = "Content-Type: application/x-www-form-urlencoded\r\n", cevapBaslik;
   ResetLastError();
   int kod = WebRequest("POST", url, basliklar, 5000, veri, sonuc, cevapBaslik);
   if(kod == 200)
   {
      for(int i = 1; i < ArraySize(KUYRUK); i++) KUYRUK[i - 1] = KUYRUK[i];
      ArrayResize(KUYRUK, ArraySize(KUYRUK) - 1);
      tgDurum = "OK";
      return;
   }
   int hata = GetLastError();
   if(kod == -1 && hata == 4014)
      tgDurum = "WebRequest izni yok (Araclar > Secenekler > Uzman Danismanlar)";
   else
      tgDurum = StringFormat("hata (kod %d, %d)", kod, hata);
   Print("Telegram gonderilemedi: ", tgDurum);
   if(kod == 400 || kod == 401 || kod == 404)
   {
      for(int i = 1; i < ArraySize(KUYRUK); i++) KUYRUK[i - 1] = KUYRUK[i];
      ArrayResize(KUYRUK, ArraySize(KUYRUK) - 1);
   }
   tgBekle = TimeLocal() + 30;
}

//+------------------------------------------------------------------+
//  SINYAL  (testteki hesabin aynisi: EMA = ewm adjust=False, ATR = 14 mumun basit ortalamasi)
//  kes: +1 yukari kesisim, -1 asagi kesisim (son KAPANAN mumda), yon: kapanis 100 EMA'ya gore
//+------------------------------------------------------------------+
bool SinyalOku(string sb, int &kes, int &yon, double &atr)
{
   MqlRates r[];
   ArraySetAsSeries(r, false);
   int n = CopyRates(sb, PERIOD_M15, 0, 700, r);
   if(n < YonEma + 60) return(false);
   double kf = 2.0 / (HizliEma + 1.0), ks = 2.0 / (YavasEma + 1.0), kt = 2.0 / (YonEma + 1.0);
   double ef = r[0].close, es = r[0].close, et = r[0].close;
   double dOnce = 0.0, dSon = 0.0;
   int son = n - 2;                                   // son KAPANAN mum (n-1 olusan mum)
   for(int i = 1; i <= son; i++)
   {
      ef = r[i].close * kf + ef * (1.0 - kf);
      es = r[i].close * ks + es * (1.0 - ks);
      et = r[i].close * kt + et * (1.0 - kt);
      if(i == son - 1) dOnce = ef - es;
   }
   dSon = ef - es;
   kes = 0;
   if(dSon > 0.0 && dOnce <= 0.0) kes = 1;
   if(dSon < 0.0 && dOnce >= 0.0) kes = -1;
   yon = 0;
   if(r[son].close > et) yon = 1;
   if(r[son].close < et) yon = -1;
   double top = 0.0;
   for(int i = son - AtrPeriyot + 1; i <= son; i++)
   {
      double a = r[i].high - r[i].low;
      double b = MathAbs(r[i].high - r[i - 1].close);
      double c = MathAbs(r[i].low - r[i - 1].close);
      top += MathMax(a, MathMax(b, c));
   }
   atr = top / AtrPeriyot;
   return(atr > 0.0);
}

//+------------------------------------------------------------------+
//  POZISYON
//+------------------------------------------------------------------+
int PozYon(string sb, ulong &bilet)
{
   bilet = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong t = PositionGetTicket(i);
      if(t == 0) continue;
      if(PositionGetString(POSITION_SYMBOL) != sb) continue;
      if((ulong)PositionGetInteger(POSITION_MAGIC) != Sihir) continue;
      bilet = t;
      return(PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY ? 1 : -1);
   }
   return(0);
}

double LotBul(string sb, int y, double fiyat, double sl)
{
   double kayip1 = 0.0;
   ENUM_ORDER_TYPE tip = (y > 0) ? ORDER_TYPE_BUY : ORDER_TYPE_SELL;
   if(!OrderCalcProfit(tip, sb, 1.0, fiyat, sl, kayip1)) return(0.0);
   kayip1 = MathAbs(kayip1);
   if(kayip1 <= 0.0) return(0.0);
   double adim  = SymbolInfoDouble(sb, SYMBOL_VOLUME_STEP);
   double enAz  = SymbolInfoDouble(sb, SYMBOL_VOLUME_MIN);
   double enUst = SymbolInfoDouble(sb, SYMBOL_VOLUME_MAX);
   if(adim <= 0.0) adim = 0.01;
   double lot = MathFloor(RiskDolar / kayip1 / adim + 1e-9) * adim;
   if(lot < enAz)
   {
      if(enAz * kayip1 <= RiskDolar * 1.5) lot = enAz;   // en kucuk lot riski en fazla 1.5 kat olabilir
      else return(0.0);
   }
   if(lot > enUst) lot = enUst;
   int bas = (int)MathMax(0.0, MathCeil(-MathLog10(adim) - 1e-9));
   return(NormalizeDouble(lot, bas));
}

void Ac(string sb, int y, double atr)
{
   double fiyat = (y > 0) ? SymbolInfoDouble(sb, SYMBOL_ASK) : SymbolInfoDouble(sb, SYMBOL_BID);
   if(fiyat <= 0.0) return;
   int dg = (int)SymbolInfoInteger(sb, SYMBOL_DIGITS);
   double mesafe = StopAtr * atr;
   double enAz = (double)SymbolInfoInteger(sb, SYMBOL_TRADE_STOPS_LEVEL) * SymbolInfoDouble(sb, SYMBOL_POINT);
   if(mesafe < enAz) mesafe = enAz;
   double sl = NormalizeDouble(y > 0 ? fiyat - mesafe : fiyat + mesafe, dg);
   double lot = LotBul(sb, y, fiyat, sl);
   if(lot <= 0.0)
   {
      Print(sb, " lot hesaplanamadi (risk cok kucuk ya da sembol kapali)");
      return;
   }
   double kayip = 0.0;
   OrderCalcProfit(y > 0 ? ORDER_TYPE_BUY : ORDER_TYPE_SELL, sb, lot, fiyat, sl, kayip);
   trade.SetTypeFillingBySymbol(sb);
   bool ok = (y > 0) ? trade.Buy(lot, sb, fiyat, sl, 0.0, "XBTC") : trade.Sell(lot, sb, fiyat, sl, 0.0, "XBTC");
   if(ok && (trade.ResultRetcode() == TRADE_RETCODE_DONE || trade.ResultRetcode() == TRADE_RETCODE_PLACED))
   {
      double gf = trade.ResultPrice() > 0.0 ? trade.ResultPrice() : fiyat;
      TgEkle((y > 0 ? "🟢 " : "🔴 ") + sb + (y > 0 ? " LONG AÇILDI" : " SHORT AÇILDI") +
             "\n📍 Giriş: " + Fiyat(sb, gf) +
             "\n🛑 Stop: " + Fiyat(sb, sl) + "  (" + Para(-MathAbs(kayip)) + ")" +
             "\n🎯 TP yok: 9 EMA 26'yı ters kesince kapanacak" +
             "\n📦 Lot: " + DoubleToString(lot, 2) +
             "\n🧠 XBTC: 9/26 kesişim + 100 EMA yön, 15 dk" +
             "\n🕐 " + TimeToString(TimeCurrent(), TIME_DATE | TIME_MINUTES));
   }
   else
      PrintFormat("%s islem acilamadi: %d %s", sb, trade.ResultRetcode(), trade.ResultRetcodeDescription());
}

void Kapat(ulong bilet)
{
   if(bilet == 0) return;
   if(!PositionSelectByTicket(bilet)) return;
   trade.PositionClose(bilet, Kayma);
}

void HepsiniKapat()
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong t = PositionGetTicket(i);
      if(t == 0) continue;
      if((ulong)PositionGetInteger(POSITION_MAGIC) != Sihir) continue;
      trade.PositionClose(t, Kayma);
   }
}

//+------------------------------------------------------------------+
//  GUNLUK HESAP
//+------------------------------------------------------------------+
bool BizimDeal(ulong d)
{
   if((ulong)HistoryDealGetInteger(d, DEAL_MAGIC) == Sihir) return(true);
   //--- stopla kapananlarda magic yoksa: pozisyonun acilis deal'ine bak
   long pid = HistoryDealGetInteger(d, DEAL_POSITION_ID);
   for(int i = HistoryDealsTotal() - 1; i >= 0; i--)
   {
      ulong x = HistoryDealGetTicket(i);
      if(x == 0 || x == d) continue;
      if(HistoryDealGetInteger(x, DEAL_POSITION_ID) != pid) continue;
      if(HistoryDealGetInteger(x, DEAL_ENTRY) != DEAL_ENTRY_IN) continue;
      return((ulong)HistoryDealGetInteger(x, DEAL_MAGIC) == Sihir);
   }
   return(false);
}

// a-b arasi: sembol basina acilan islem, kapanan karli/zararli, kapanan K/Z
void GunVerisi(datetime a, datetime b, int &acilan[], int &karli[], int &zararli[], double &kz[])
{
   int n = ArraySize(S);
   ArrayResize(acilan, n); ArrayResize(karli, n); ArrayResize(zararli, n); ArrayResize(kz, n);
   ArrayInitialize(acilan, 0); ArrayInitialize(karli, 0); ArrayInitialize(zararli, 0); ArrayInitialize(kz, 0.0);
   if(!HistorySelect(a, b)) return;
   for(int i = 0; i < HistoryDealsTotal(); i++)
   {
      ulong d = HistoryDealGetTicket(i);
      if(d == 0) continue;
      string sb = HistoryDealGetString(d, DEAL_SYMBOL);
      int k = -1;
      for(int j = 0; j < n; j++) if(S[j] == sb) { k = j; break; }
      if(k < 0) continue;
      if(!BizimDeal(d)) continue;
      long g = HistoryDealGetInteger(d, DEAL_ENTRY);
      double p = HistoryDealGetDouble(d, DEAL_PROFIT) + HistoryDealGetDouble(d, DEAL_SWAP) +
                 HistoryDealGetDouble(d, DEAL_COMMISSION);
      kz[k] += p;
      if(g == DEAL_ENTRY_IN) acilan[k]++;
      if(g == DEAL_ENTRY_OUT || g == DEAL_ENTRY_OUT_BY)
      {
         if(p > 0.0) karli[k]++; else zararli[k]++;
      }
   }
}

double AcikKZ(string sb)
{
   double t = 0.0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong x = PositionGetTicket(i);
      if(x == 0) continue;
      if((ulong)PositionGetInteger(POSITION_MAGIC) != Sihir) continue;
      if(sb != "" && PositionGetString(POSITION_SYMBOL) != sb) continue;
      t += PositionGetDouble(POSITION_PROFIT) + PositionGetDouble(POSITION_SWAP);
   }
   return(t);
}

string OzetMetni(datetime a, datetime b, string baslik)
{
   int ac[], ka[], za[]; double kz[];
   GunVerisi(a, b, ac, ka, za, kz);
   string m = baslik;
   double top = 0.0; int topI = 0;
   for(int k = 0; k < ArraySize(S); k++)
   {
      m += "\n" + (StringFind(S[k], "XAU") >= 0 ? "🥇 " : (StringFind(S[k], "BTC") >= 0 ? "₿ " : "• ")) + S[k] +
           ": " + IntegerToString(ac[k]) + " işlem | ✅ " + IntegerToString(ka[k]) + " kâr  ❌ " +
           IntegerToString(za[k]) + " zarar | " + Para(kz[k]);
      top += kz[k]; topI += ac[k];
   }
   m += "\n💰 Toplam: " + IntegerToString(topI) + " işlem, " + Para(top) +
        "\n🏦 Bakiye: " + DoubleToString(AccountInfoDouble(ACCOUNT_BALANCE), 2) + " $";
   return(m);
}

void GunKontrol()
{
   int g = GunAnahtari(TimeCurrent());
   if(gunKey == 0) { gunKey = g; return; }
   if(g == gunKey) return;
   //--- yeni gun: dunun ozeti
   datetime bugun = GunBasi(TimeCurrent());
   datetime dun = bugun - 86400;
   TgEkle(OzetMetni(dun, bugun - 1, "📊 XBTC GÜNLÜK ÖZET – " + TimeToString(dun, TIME_DATE)));
   gunKey = g;
   limitDoldu = false;
}

void LimitKontrol()
{
   if(limitDoldu) return;
   datetime bas = GunBasi(TimeCurrent());
   int ac[], ka[], za[]; double kz[];
   GunVerisi(bas, TimeCurrent() + 60, ac, ka, za, kz);
   double top = AcikKZ("");
   for(int k = 0; k < ArraySize(kz); k++) top += kz[k];
   if(top <= -GunlukZararLimit)
   {
      limitDoldu = true;
      HepsiniKapat();
      TgEkle("⛔ XBTC GÜNLÜK ZARAR LİMİTİ DOLDU\nBugünkü zarar: " + Para(top) + " (limit -" +
             DoubleToString(GunlukZararLimit, 0) + " $)\nAçık işlemler kapatıldı, bugün yeni işlem açılmayacak." +
             "\n🕐 " + TimeToString(TimeCurrent(), TIME_DATE | TIME_MINUTES));
   }
}

//+------------------------------------------------------------------+
//  PANEL (sag ust)
//+------------------------------------------------------------------+
void Yazi(string ad, string metin, int y, int boy, color renk)
{
   string n = ON_EK + ad;
   if(ObjectFind(0, n) < 0)
   {
      ObjectCreate(0, n, OBJ_LABEL, 0, 0, 0);
      ObjectSetInteger(0, n, OBJPROP_CORNER, CORNER_RIGHT_UPPER);
      ObjectSetInteger(0, n, OBJPROP_ANCHOR, ANCHOR_RIGHT_UPPER);
      ObjectSetInteger(0, n, OBJPROP_XDISTANCE, 20);
      ObjectSetString(0, n, OBJPROP_FONT, "Arial Bold");
      ObjectSetInteger(0, n, OBJPROP_SELECTABLE, false);
      ObjectSetInteger(0, n, OBJPROP_HIDDEN, true);
   }
   ObjectSetInteger(0, n, OBJPROP_YDISTANCE, y);
   ObjectSetInteger(0, n, OBJPROP_FONTSIZE, boy);
   ObjectSetInteger(0, n, OBJPROP_COLOR, renk);
   ObjectSetString(0, n, OBJPROP_TEXT, metin);
}

void Arka(int yukseklik)
{
   string n = ON_EK + "bg";
   if(ObjectFind(0, n) < 0)
   {
      ObjectCreate(0, n, OBJ_RECTANGLE_LABEL, 0, 0, 0);
      ObjectSetInteger(0, n, OBJPROP_CORNER, CORNER_RIGHT_UPPER);
      ObjectSetInteger(0, n, OBJPROP_XDISTANCE, 470);
      ObjectSetInteger(0, n, OBJPROP_YDISTANCE, 15);
      ObjectSetInteger(0, n, OBJPROP_XSIZE, 460);
      ObjectSetInteger(0, n, OBJPROP_BGCOLOR, clrWhite);
      ObjectSetInteger(0, n, OBJPROP_BORDER_TYPE, BORDER_FLAT);
      ObjectSetInteger(0, n, OBJPROP_COLOR, clrSilver);
      ObjectSetInteger(0, n, OBJPROP_SELECTABLE, false);
      ObjectSetInteger(0, n, OBJPROP_HIDDEN, true);
   }
   ObjectSetInteger(0, n, OBJPROP_YSIZE, yukseklik);
}

void Panel()
{
   datetime bas = GunBasi(TimeCurrent());
   int ac[], ka[], za[]; double kz[];
   GunVerisi(bas, TimeCurrent() + 60, ac, ka, za, kz);
   double top = AcikKZ("");
   int topI = 0;
   for(int k = 0; k < ArraySize(kz); k++) { top += kz[k]; topI += ac[k]; }
   int y = 25;
   Yazi("0", "XBTC ROBOT", y, 14, clrNavy); y += 26;
   Yazi("1", "9/26 EMA kesişim + 100 EMA yön | 15 dk", y, 9, clrBlack); y += 18;
   Yazi("2", "Stop 2 ATR | TP yok: ters kesişimde çıkış", y, 9, clrBlack); y += 18;
   Yazi("3", "Risk/işlem " + DoubleToString(RiskDolar, 0) + " $ | Günlük limit -" +
        DoubleToString(GunlukZararLimit, 0) + " $", y, 9, clrBlack); y += 22;
   Yazi("4", "Bugün: " + IntegerToString(topI) + " işlem | " + Para(top) +
        (limitDoldu ? "  ⛔ LİMİT DOLDU" : ""), y, 10, top >= 0 ? clrGreen : clrRed); y += 22;
   for(int k = 0; k < ArraySize(S); k++)
   {
      ulong b; int p = PozYon(S[k], b);
      double ak = AcikKZ(S[k]);
      string durum = (p == 0) ? "işlem yok" : ((p > 0 ? "LONG " : "SHORT ") + Para(ak));
      Yazi("s" + IntegerToString(k), S[k] + ": " + durum + " | bugün " + IntegerToString(ac[k]) + " işlem " +
           Para(kz[k] + ak), y, 9, (kz[k] + ak) >= 0 ? clrGreen : clrRed);
      y += 18;
   }
   Yazi("tg", "Telegram: " + (TelegramAcik ? (tgDurum == "" ? "hazır" : tgDurum) : "kapalı"), y, 8, clrGray);
   y += 18;
   Arka(y - 10);
}

//+------------------------------------------------------------------+
//  ANA
//+------------------------------------------------------------------+
void Kontrol(int k)
{
   string sb = S[k];
   datetime t[];
   if(CopyTime(sb, PERIOD_M15, 0, 1, t) != 1) return;
   if(t[0] == sonMum[k]) return;                       // yeni 15 dk mum bekleniyor
   int kes, yon; double atr;
   if(!SinyalOku(sb, kes, yon, atr)) return;
   sonMum[k] = t[0];
   if(kes == 0) return;
   ulong bilet;
   int p = PozYon(sb, bilet);
   if((p == 1 && kes == -1) || (p == -1 && kes == 1))  // ters kesisim: cikis
      Kapat(bilet);
   p = PozYon(sb, bilet);
   if(p != 0 || limitDoldu) return;
   if(kes == 1 && yon == 1)   Ac(sb, 1, atr);
   if(kes == -1 && yon == -1) Ac(sb, -1, atr);
}

int OnInit()
{
   trade.SetExpertMagicNumber(Sihir);
   trade.SetDeviationInPoints(Kayma);
   string p[];
   int n = StringSplit(Semboller, StringGetCharacter(",", 0), p);
   ArrayResize(S, 0);
   for(int i = 0; i < n; i++)
   {
      string s = p[i];
      StringTrimLeft(s); StringTrimRight(s);
      if(s == "") continue;
      if(!SymbolSelect(s, true)) { Print("Sembol bulunamadi: ", s); continue; }
      int k = ArraySize(S); ArrayResize(S, k + 1); S[k] = s;
   }
   ArrayResize(sonMum, ArraySize(S));
   for(int i = 0; i < ArraySize(S); i++)
   {
      datetime t[];
      sonMum[i] = (CopyTime(S[i], PERIOD_M15, 0, 1, t) == 1) ? t[0] : 0;   // acilista eski sinyal kullanilmaz
   }
   gunKey = GunAnahtari(TimeCurrent());
   string ss = "";
   for(int i = 0; i < ArraySize(S); i++) ss += (i > 0 ? ", " : "") + S[i];
   TgEkle("🤖 XBTC ROBOT BAŞLADI\n📈 Semboller: " + ss + "\n🧠 9/26 EMA kesişim + 100 EMA yön, 15 dk\n🛑 Stop 2 ATR | 🎯 TP yok (ters kesişimde çıkış)" +
          "\n💵 Risk/işlem: " + DoubleToString(RiskDolar, 0) + " $ | ⛔ Günlük limit: -" +
          DoubleToString(GunlukZararLimit, 0) + " $");
   EventSetTimer(5);
   Panel();
   return(INIT_SUCCEEDED);
}

void OnDeinit(const int reason)
{
   EventKillTimer();
   ObjectsDeleteAll(0, ON_EK);
}

void OnTimer()
{
   GunKontrol();
   LimitKontrol();
   if(TerminalInfoInteger(TERMINAL_TRADE_ALLOWED) && MQLInfoInteger(MQL_TRADE_ALLOWED))
      for(int k = 0; k < ArraySize(S); k++) Kontrol(k);
   Panel();
   TgGonder();
}

void OnTick()
{
   // islemler OnTimer icinde
}

void OnTradeTransaction(const MqlTradeTransaction &tr, const MqlTradeRequest &rq, const MqlTradeResult &rs)
{
   if(tr.type != TRADE_TRANSACTION_DEAL_ADD) return;
   if(!HistoryDealSelect(tr.deal)) return;
   long g = HistoryDealGetInteger(tr.deal, DEAL_ENTRY);
   if(g != DEAL_ENTRY_OUT && g != DEAL_ENTRY_OUT_BY) return;
   string sb = HistoryDealGetString(tr.deal, DEAL_SYMBOL);
   bool bizim = ((ulong)HistoryDealGetInteger(tr.deal, DEAL_MAGIC) == Sihir);
   if(!bizim)
   {
      long pid = HistoryDealGetInteger(tr.deal, DEAL_POSITION_ID);
      if(HistorySelectByPosition(pid))
         for(int i = 0; i < HistoryDealsTotal(); i++)
         {
            ulong x = HistoryDealGetTicket(i);
            if(HistoryDealGetInteger(x, DEAL_ENTRY) == DEAL_ENTRY_IN)
               bizim = ((ulong)HistoryDealGetInteger(x, DEAL_MAGIC) == Sihir);
         }
      if(!HistoryDealSelect(tr.deal)) return;
   }
   if(!bizim) return;
   double p = HistoryDealGetDouble(tr.deal, DEAL_PROFIT) + HistoryDealGetDouble(tr.deal, DEAL_SWAP) +
              HistoryDealGetDouble(tr.deal, DEAL_COMMISSION);
   long sebep = HistoryDealGetInteger(tr.deal, DEAL_REASON);
   string neden = (sebep == DEAL_REASON_SL) ? "🛑 Stop oldu" :
                  (sebep == DEAL_REASON_EXPERT ? (limitDoldu ? "⛔ Günlük limit" : "🔄 Ters kesişim") : "✋ Elle / diğer");
   string yon = (HistoryDealGetInteger(tr.deal, DEAL_TYPE) == DEAL_TYPE_SELL) ? "LONG" : "SHORT";
   TgEkle((p > 0 ? "✅ " : "❌ ") + sb + " " + yon + " KAPANDI" +
          "\n🔚 Çıkış: " + Fiyat(sb, HistoryDealGetDouble(tr.deal, DEAL_PRICE)) +
          "\n" + neden +
          "\n" + (p > 0 ? "💰 Kâr: " : "💸 Zarar: ") + Para(p) + "  (" + DoubleToString(p / RiskDolar, 1) + "R)" +
          "\n🕐 " + TimeToString(TimeCurrent(), TIME_DATE | TIME_MINUTES));
}
//+------------------------------------------------------------------+
