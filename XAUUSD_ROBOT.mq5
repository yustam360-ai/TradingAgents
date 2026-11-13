//+------------------------------------------------------------------+
//|  XAUUSD_ROBOT.mq5                                                |
//|  ALTIN RANGE BREAKOUT (Rene Balke kurallari) - OTOMATIK ROBOT    |
//+------------------------------------------------------------------+
//  KURALLAR (videodaki ve testteki gibi; saatler MT5 SUNUCU saati):
//   1) 03:05 - 06:05 arasinin en yuksek ve en dusuk fiyati bulunur (aralik).
//   2) 06:05'te aralik tepesine BUY STOP, aralik dibine SELL STOP konur.
//      (Fiyat o an zaten aralik disindaysa o yonde hemen piyasa emriyle girilir.)
//   3) Biri dolunca digeri hemen silinir. Gunde en fazla 1 islem.
//   4) STOP: giris fiyatinin %1'i uzakta.  HEDEF: YOK.
//   5) 18:55'te acik islem kapatilir, dolmayan emir silinir.
//  LOT: sabit 0.03 (ayarlardan degisir).  0.03 lotta %1 stop yaklasik 0.03 x 100 ons x fiyatin %1'i
//       (altin 4.000 $ iken ~120 $).
//  GUNLUK ZARAR LIMITI: bugun kapanan + acik islem -250 $ olursa her sey kapatilir, o gun yeni islem yok.
//  TELEGRAM: emirler konunca, islem acilinca, kapaninca, limit dolunca ve her gun sonunda ozet.
//          MT5: Araclar > Secenekler > Uzman Danismanlar > "WebRequest izin ver" + https://api.telegram.org
//          Token ve Chat ID: robotun AYARLAR penceresine eski robottakinin aynisini yapistirin.
//  PANEL : sol ust kosede.
//+------------------------------------------------------------------+
#property copyright "XAUUSD ROBOT"
#property version   "1.00"

#include <Trade\Trade.mqh>

input string Sembol           = "XAUUSD";          // Sembol
input double SabitLot         = 0.03;              // Lot (sabit)
input string AralikBasla      = "03:05";           // Aralik baslangici (sunucu saati)
input string AralikBit        = "06:05";           // Aralik bitisi = emirlerin konma saati
input string KapanisSaati     = "18:55";           // Kapanis ve emir silme saati
input double StopYuzde        = 1.0;               // Stop = giris fiyatinin yuzde kaci
input double GunlukZararLimit = 250.0;             // Gunluk zarar limiti ($)
input int    Kayma            = 30;                // Izin verilen kayma (puan)
input ulong  Sihir            = 20261114;          // Magic number
input string TelegramToken    = "";                // Telegram bot token (eski robotla ayni)
input string TelegramChatID   = "";                // Telegram chat id (eski robotla ayni)
input bool   TelegramAcik     = true;              // Telegram mesajlari

#define ON_EK "XAUR_"

CTrade   trade;
string   KUYRUK[];
datetime tgBekle = 0;
string   tgDurum = "";
int      gunKey  = 0;
bool     limitDoldu = false;
bool     emirKondu  = false;
bool     kapandi    = false;
double   aTepe = 0.0, aDip = 0.0;

//+------------------------------------------------------------------+
int Dakika(string s)
{
   string p[];
   if(StringSplit(s, StringGetCharacter(":", 0), p) != 2) return(0);
   return((int)StringToInteger(p[0]) * 60 + (int)StringToInteger(p[1]));
}

int GunAnahtari(datetime t) { MqlDateTime z; TimeToStruct(t, z); return(z.year * 10000 + z.mon * 100 + z.day); }

datetime GunBasi(datetime t) { MqlDateTime z; TimeToStruct(t, z); z.hour = 0; z.min = 0; z.sec = 0; return(StructToTime(z)); }

int SimdiDakika() { MqlDateTime z; TimeToStruct(TimeCurrent(), z); return(z.hour * 60 + z.min); }

bool HaftaIci() { MqlDateTime z; TimeToStruct(TimeCurrent(), z); return(z.day_of_week >= 1 && z.day_of_week <= 5); }

string Para(double x) { return((x >= 0 ? "+" : "") + DoubleToString(x, 2) + " $"); }

string Fiyat(double p) { return(DoubleToString(p, (int)SymbolInfoInteger(Sembol, SYMBOL_DIGITS))); }

string Saat() { return(TimeToString(TimeCurrent(), TIME_DATE | TIME_MINUTES)); }

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
//  EMIR / POZISYON
//+------------------------------------------------------------------+
int Pozisyon(ulong &bilet)
{
   bilet = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong t = PositionGetTicket(i);
      if(t == 0) continue;
      if(PositionGetString(POSITION_SYMBOL) != Sembol) continue;
      if((ulong)PositionGetInteger(POSITION_MAGIC) != Sihir) continue;
      bilet = t;
      return(PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY ? 1 : -1);
   }
   return(0);
}

int BekleyenSay()
{
   int n = 0;
   for(int i = OrdersTotal() - 1; i >= 0; i--)
   {
      ulong t = OrderGetTicket(i);
      if(t == 0) continue;
      if(OrderGetString(ORDER_SYMBOL) != Sembol) continue;
      if((ulong)OrderGetInteger(ORDER_MAGIC) != Sihir) continue;
      n++;
   }
   return(n);
}

void BekleyenSil()
{
   for(int i = OrdersTotal() - 1; i >= 0; i--)
   {
      ulong t = OrderGetTicket(i);
      if(t == 0) continue;
      if(OrderGetString(ORDER_SYMBOL) != Sembol) continue;
      if((ulong)OrderGetInteger(ORDER_MAGIC) != Sihir) continue;
      trade.OrderDelete(t);
   }
}

void HepsiniKapat()
{
   BekleyenSil();
   ulong b;
   if(Pozisyon(b) != 0) trade.PositionClose(b, Kayma);
}

double LotDuzelt(double lot)
{
   double adim = SymbolInfoDouble(Sembol, SYMBOL_VOLUME_STEP);
   double enAz = SymbolInfoDouble(Sembol, SYMBOL_VOLUME_MIN);
   double enUst = SymbolInfoDouble(Sembol, SYMBOL_VOLUME_MAX);
   if(adim <= 0.0) adim = 0.01;
   lot = MathFloor(lot / adim + 1e-9) * adim;
   if(lot < enAz) lot = enAz;
   if(lot > enUst) lot = enUst;
   int bas = (int)MathMax(0.0, MathCeil(-MathLog10(adim) - 1e-9));
   return(NormalizeDouble(lot, bas));
}

bool BugunIslemVar()
{
   if(!HistorySelect(GunBasi(TimeCurrent()), TimeCurrent() + 60)) return(false);
   for(int i = 0; i < HistoryDealsTotal(); i++)
   {
      ulong d = HistoryDealGetTicket(i);
      if(d == 0) continue;
      if((ulong)HistoryDealGetInteger(d, DEAL_MAGIC) != Sihir) continue;
      if(HistoryDealGetString(d, DEAL_SYMBOL) != Sembol) continue;
      if(HistoryDealGetInteger(d, DEAL_ENTRY) == DEAL_ENTRY_IN) return(true);
   }
   return(false);
}

bool AralikHesapla()
{
   datetime g = GunBasi(TimeCurrent());
   datetime a = g + Dakika(AralikBasla) * 60;
   datetime b = g + Dakika(AralikBit) * 60 - 1;
   MqlRates r[];
   int n = CopyRates(Sembol, PERIOD_M1, a, b, r);
   if(n < 30) return(false);                         // tatil / veri yok: bugun islem yok
   aTepe = r[0].high; aDip = r[0].low;
   for(int i = 1; i < n; i++) { aTepe = MathMax(aTepe, r[i].high); aDip = MathMin(aDip, r[i].low); }
   return(aTepe > aDip);
}

void EmirleriKoy()
{
   if(!AralikHesapla())
   {
      TgEkle("ℹ️ XAUUSD ROBOT: bugün 03:05–06:05 arası veri yok (tatil?). Bugün işlem yok.");
      emirKondu = true;
      return;
   }
   int dg = (int)SymbolInfoInteger(Sembol, SYMBOL_DIGITS);
   double ask = SymbolInfoDouble(Sembol, SYMBOL_ASK), bid = SymbolInfoDouble(Sembol, SYMBOL_BID);
   double lot = LotDuzelt(SabitLot);
   double k = StopYuzde / 100.0;
   trade.SetTypeFillingBySymbol(Sembol);
   bool ok1 = false, ok2 = false;
   if(ask >= aTepe)                                   // fiyat zaten tepenin ustunde: hemen alis
      ok1 = trade.Buy(lot, Sembol, ask, NormalizeDouble(ask * (1 - k), dg), 0.0, "XAUR");
   else if(bid <= aDip)                               // fiyat zaten dibin altinda: hemen satis
      ok2 = trade.Sell(lot, Sembol, bid, NormalizeDouble(bid * (1 + k), dg), 0.0, "XAUR");
   else
   {
      double t = NormalizeDouble(aTepe, dg), d = NormalizeDouble(aDip, dg);
      ok1 = trade.BuyStop(lot, t, Sembol, NormalizeDouble(t * (1 - k), dg), 0.0, ORDER_TIME_GTC, 0, "XAUR");
      ok2 = trade.SellStop(lot, d, Sembol, NormalizeDouble(d * (1 + k), dg), 0.0, ORDER_TIME_GTC, 0, "XAUR");
   }
   emirKondu = true;
   TgEkle("⏰ XAUUSD ARALIK HAZIR (03:05–06:05)\n🔺 Tepe: " + Fiyat(aTepe) + "   🔻 Dip: " + Fiyat(aDip) +
          "\n📏 Aralık: " + DoubleToString(aTepe - aDip, 2) + " $" +
          "\n🟢 Buy Stop: " + Fiyat(aTepe) + (ok1 ? " ✔" : " ✖") +
          "\n🔴 Sell Stop: " + Fiyat(aDip) + (ok2 ? " ✔" : " ✖") +
          "\n📦 Lot: " + DoubleToString(lot, 2) + " | 🛑 Stop %" + DoubleToString(StopYuzde, 1) +
          " | 🎯 TP yok | 🕐 " + KapanisSaati + "'te kapanış");
}

//+------------------------------------------------------------------+
//  GUNLUK HESAP
//+------------------------------------------------------------------+
void GunVerisi(datetime a, datetime b, int &adet, int &karli, int &zararli, double &kz)
{
   adet = 0; karli = 0; zararli = 0; kz = 0.0;
   if(!HistorySelect(a, b)) return;
   for(int i = 0; i < HistoryDealsTotal(); i++)
   {
      ulong d = HistoryDealGetTicket(i);
      if(d == 0) continue;
      if(HistoryDealGetString(d, DEAL_SYMBOL) != Sembol) continue;
      if((ulong)HistoryDealGetInteger(d, DEAL_MAGIC) != Sihir) continue;
      double p = HistoryDealGetDouble(d, DEAL_PROFIT) + HistoryDealGetDouble(d, DEAL_SWAP) +
                 HistoryDealGetDouble(d, DEAL_COMMISSION);
      kz += p;
      long g = HistoryDealGetInteger(d, DEAL_ENTRY);
      if(g == DEAL_ENTRY_IN) adet++;
      if(g == DEAL_ENTRY_OUT || g == DEAL_ENTRY_OUT_BY) { if(p > 0.0) karli++; else zararli++; }
   }
}

double AcikKZ()
{
   ulong b;
   if(Pozisyon(b) == 0 || !PositionSelectByTicket(b)) return(0.0);
   return(PositionGetDouble(POSITION_PROFIT) + PositionGetDouble(POSITION_SWAP));
}

void GunKontrol()
{
   int g = GunAnahtari(TimeCurrent());
   if(gunKey == 0) { gunKey = g; return; }
   if(g == gunKey) return;
   datetime bugun = GunBasi(TimeCurrent()), dun = bugun - 86400;
   int ad, ka, za; double kz;
   GunVerisi(dun, bugun - 1, ad, ka, za, kz);
   if(ad > 0)
      TgEkle("📊 XAUUSD GÜNLÜK ÖZET – " + TimeToString(dun, TIME_DATE) +
             "\n🥇 " + IntegerToString(ad) + " işlem | " + (kz >= 0 ? "✅ " : "❌ ") + Para(kz) +
             "\n🏦 Bakiye: " + DoubleToString(AccountInfoDouble(ACCOUNT_BALANCE), 2) + " $");
   gunKey = g;
   limitDoldu = false; emirKondu = false; kapandi = false;
}

void LimitKontrol()
{
   if(limitDoldu) return;
   int ad, ka, za; double kz;
   GunVerisi(GunBasi(TimeCurrent()), TimeCurrent() + 60, ad, ka, za, kz);
   double top = kz + AcikKZ();
   if(top <= -GunlukZararLimit)
   {
      limitDoldu = true;
      HepsiniKapat();
      TgEkle("⛔ XAUUSD GÜNLÜK ZARAR LİMİTİ DOLDU\nBugünkü zarar: " + Para(top) + " (limit -" +
             DoubleToString(GunlukZararLimit, 0) + " $)\nİşlem kapatıldı, bugün yeni işlem yok.\n🕐 " + Saat());
   }
}

//+------------------------------------------------------------------+
//  PANEL (sol ust)
//+------------------------------------------------------------------+
void Yazi(string ad, string metin, int y, int boy, color renk)
{
   string n = ON_EK + ad;
   if(ObjectFind(0, n) < 0)
   {
      ObjectCreate(0, n, OBJ_LABEL, 0, 0, 0);
      ObjectSetInteger(0, n, OBJPROP_CORNER, CORNER_LEFT_UPPER);
      ObjectSetInteger(0, n, OBJPROP_ANCHOR, ANCHOR_LEFT_UPPER);
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

void Arka(int h)
{
   string n = ON_EK + "bg";
   if(ObjectFind(0, n) < 0)
   {
      ObjectCreate(0, n, OBJ_RECTANGLE_LABEL, 0, 0, 0);
      ObjectSetInteger(0, n, OBJPROP_CORNER, CORNER_LEFT_UPPER);
      ObjectSetInteger(0, n, OBJPROP_XDISTANCE, 10);
      ObjectSetInteger(0, n, OBJPROP_YDISTANCE, 15);
      ObjectSetInteger(0, n, OBJPROP_XSIZE, 430);
      ObjectSetInteger(0, n, OBJPROP_BGCOLOR, clrWhite);
      ObjectSetInteger(0, n, OBJPROP_BORDER_TYPE, BORDER_FLAT);
      ObjectSetInteger(0, n, OBJPROP_COLOR, clrSilver);
      ObjectSetInteger(0, n, OBJPROP_SELECTABLE, false);
      ObjectSetInteger(0, n, OBJPROP_HIDDEN, true);
   }
   ObjectSetInteger(0, n, OBJPROP_YSIZE, h);
}

void Panel()
{
   int ad, ka, za; double kz;
   GunVerisi(GunBasi(TimeCurrent()), TimeCurrent() + 60, ad, ka, za, kz);
   double ak = AcikKZ();
   ulong b; int p = Pozisyon(b);
   int y = 25;
   Yazi("0", "🥇 XAUUSD ROBOT", y, 14, clrDarkGoldenrod); y += 26;
   Yazi("1", "Range Breakout: " + AralikBasla + "–" + AralikBit + " aralık, " + KapanisSaati + " kapanış", y, 9, clrBlack); y += 18;
   Yazi("2", "Stop %" + DoubleToString(StopYuzde, 1) + " | TP yok | Lot " + DoubleToString(SabitLot, 2) +
        " | Günlük limit -" + DoubleToString(GunlukZararLimit, 0) + " $", y, 9, clrBlack); y += 22;
   string ar = (aTepe > 0.0) ? ("Aralık: " + Fiyat(aDip) + " – " + Fiyat(aTepe)) : "Aralık: 06:05'i bekliyor";
   Yazi("3", ar, y, 9, clrBlack); y += 18;
   string d = (p > 0) ? ("LONG açık " + Para(ak)) : (p < 0 ? ("SHORT açık " + Para(ak)) :
              (BekleyenSay() > 0 ? "Buy Stop + Sell Stop bekliyor" : "İşlem yok"));
   Yazi("4", "Durum: " + d, y, 10, p != 0 ? (ak >= 0 ? clrGreen : clrRed) : clrNavy); y += 22;
   Yazi("5", "Bugün: " + Para(kz + ak) + (limitDoldu ? "  ⛔ LİMİT DOLDU" : ""), y, 10,
        (kz + ak) >= 0 ? clrGreen : clrRed); y += 22;
   Yazi("tg", "Telegram: " + (TelegramAcik ? (tgDurum == "" ? "hazır" : tgDurum) : "kapalı"), y, 8, clrGray);
   y += 18;
   Arka(y - 10);
}

//+------------------------------------------------------------------+
//  ANA
//+------------------------------------------------------------------+
void Calis()
{
   if(!HaftaIci() || limitDoldu) return;
   int m = SimdiDakika();
   ulong b;
   int p = Pozisyon(b);
   //--- biri dolunca digeri silinir (gunde tek islem)
   if(p != 0 && BekleyenSay() > 0) BekleyenSil();
   //--- 18:55 kapanis
   if(m >= Dakika(KapanisSaati))
   {
      if(!kapandi && (p != 0 || BekleyenSay() > 0)) { HepsiniKapat(); }
      kapandi = true;
      return;
   }
   //--- 06:05'te emirler
   if(!emirKondu && m >= Dakika(AralikBit))
   {
      if(p != 0 || BekleyenSay() > 0 || BugunIslemVar()) { emirKondu = true; return; }   // yeniden baslatmada tekrar koyma
      EmirleriKoy();
   }
}

int OnInit()
{
   trade.SetExpertMagicNumber(Sihir);
   trade.SetDeviationInPoints(Kayma);
   if(!SymbolSelect(Sembol, true)) { Print("Sembol bulunamadi: ", Sembol); return(INIT_FAILED); }
   gunKey = GunAnahtari(TimeCurrent());
   if(SimdiDakika() >= Dakika(AralikBit)) AralikHesapla();
   TgEkle("🤖 XAUUSD ROBOT BAŞLADI\n🥇 " + Sembol + " Range Breakout\n⏰ Aralık " + AralikBasla + "–" + AralikBit +
          " | 🕐 Kapanış " + KapanisSaati + "\n📦 Lot " + DoubleToString(SabitLot, 2) + " | 🛑 Stop %" +
          DoubleToString(StopYuzde, 1) + " | 🎯 TP yok\n⛔ Günlük limit: -" + DoubleToString(GunlukZararLimit, 0) + " $");
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
   if(TerminalInfoInteger(TERMINAL_TRADE_ALLOWED) && MQLInfoInteger(MQL_TRADE_ALLOWED)) Calis();
   if(!MQLInfoInteger(MQL_TESTER) || MQLInfoInteger(MQL_VISUAL_MODE)) Panel();
   TgGonder();
}

void OnTick() { }

void OnTradeTransaction(const MqlTradeTransaction &tr, const MqlTradeRequest &rq, const MqlTradeResult &rs)
{
   if(tr.type != TRADE_TRANSACTION_DEAL_ADD) return;
   if(!HistoryDealSelect(tr.deal)) return;
   if(HistoryDealGetString(tr.deal, DEAL_SYMBOL) != Sembol) return;
   if((ulong)HistoryDealGetInteger(tr.deal, DEAL_MAGIC) != Sihir)
   {
      //--- stop ile kapanista magic yoksa pozisyonun acilis deal'ine bak
      long pid = HistoryDealGetInteger(tr.deal, DEAL_POSITION_ID);
      bool bizim = false;
      if(HistorySelectByPosition(pid))
         for(int i = 0; i < HistoryDealsTotal(); i++)
         {
            ulong x = HistoryDealGetTicket(i);
            if(HistoryDealGetInteger(x, DEAL_ENTRY) == DEAL_ENTRY_IN)
               bizim = ((ulong)HistoryDealGetInteger(x, DEAL_MAGIC) == Sihir);
         }
      if(!bizim || !HistoryDealSelect(tr.deal)) return;
   }
   long g = HistoryDealGetInteger(tr.deal, DEAL_ENTRY);
   double px = HistoryDealGetDouble(tr.deal, DEAL_PRICE);
   long tip = HistoryDealGetInteger(tr.deal, DEAL_TYPE);
   if(g == DEAL_ENTRY_IN)
   {
      bool al = (tip == DEAL_TYPE_BUY);
      double sl = al ? px * (1 - StopYuzde / 100.0) : px * (1 + StopYuzde / 100.0);
      TgEkle((al ? "🟢 XAUUSD LONG AÇILDI" : "🔴 XAUUSD SHORT AÇILDI") +
             "\n📍 Giriş: " + Fiyat(px) + "\n🛑 Stop: ~" + Fiyat(sl) + " (%" + DoubleToString(StopYuzde, 1) + ")" +
             "\n🎯 TP yok, " + KapanisSaati + "'te kapanacak\n📦 Lot: " + DoubleToString(HistoryDealGetDouble(tr.deal, DEAL_VOLUME), 2) +
             "\n🗑 Karşı emir siliniyor\n🕐 " + Saat());
      return;
   }
   if(g != DEAL_ENTRY_OUT && g != DEAL_ENTRY_OUT_BY) return;
   double p = HistoryDealGetDouble(tr.deal, DEAL_PROFIT) + HistoryDealGetDouble(tr.deal, DEAL_SWAP) +
              HistoryDealGetDouble(tr.deal, DEAL_COMMISSION);
   long sebep = HistoryDealGetInteger(tr.deal, DEAL_REASON);
   string neden = (sebep == DEAL_REASON_SL) ? "🛑 Stop oldu" :
                  (sebep == DEAL_REASON_EXPERT ? (limitDoldu ? "⛔ Günlük limit" : "🕐 " + KapanisSaati + " kapanışı") : "✋ Elle / diğer");
   string yon = (tip == DEAL_TYPE_SELL) ? "LONG" : "SHORT";
   TgEkle((p > 0 ? "✅ " : "❌ ") + "XAUUSD " + yon + " KAPANDI\n🔚 Çıkış: " + Fiyat(px) + "\n" + neden +
          "\n" + (p > 0 ? "💰 Kâr: " : "💸 Zarar: ") + Para(p) + "\n🕐 " + Saat());
}
//+------------------------------------------------------------------+
