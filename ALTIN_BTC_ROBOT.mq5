//+------------------------------------------------------------------+
//|  ALTIN_BTC_ROBOT.mq5                                             |
//|  ALTIN + BITCOIN RANGE BREAKOUT (Rene Balke) - TEK ROBOT         |
//+------------------------------------------------------------------+
//  KURALLAR (saatler MT5 SUNUCU saati, her sembol kendi ayariyla):
//   ALTIN : aralik 03:05-06:05, kapanis 18:55, stop = giris fiyatinin %1'i, hafta ici.
//   BTC   : aralik 05:00-09:00, kapanis 20:00, stop = araligin karsi ucu, hafta sonu dahil.
//   1) Aralik basi - sonu arasinin en yuksek ve en dusuk fiyati bulunur.
//   2) Aralik bitince tepeye BUY STOP, dibe SELL STOP konur.
//      (Fiyat o an zaten aralik disindaysa o yonde hemen piyasa emriyle girilir.
//       Bir emir reddedilirse robot 5 sn sonra tekrar dener.)
//   3) Biri dolunca digeri silinir. Her sembolde gunde en fazla 1 islem.
//   4) HEDEF YOK. Kapanis saatinde acik islem kapatilir, dolmayan emir silinir.
//  LOT: her islemde STOP OLURSA ZARAR = "Risk" ($) olacak sekilde otomatik hesaplanir
//       (stop mesafesine gore). Kar olursa ne kadarsa o.
//       Hesaplanan lot sembolun en kucuk lotundan kucukse o gun o sembolde islem acilmaz.
//  GUNLUK ZARAR LIMITI: iki sembolun bugun kapanan + acik zarari toplami limite gelirse
//       her sey kapatilir, o gun yeni islem yok. "Gun" PRAG saatine gore (FTMO gibi):
//       Prag gece yarisi = sunucu 01:00 (PragFark = -1).
//  TELEGRAM: emirler konunca, islem acilinca, kapaninca, limit dolunca ve gun sonunda ozet.
//       MT5: Araclar > Secenekler > Uzman Danismanlar > "WebRequest izin ver" + https://api.telegram.org
//  PANEL : sol ust kosede.
//  TEST  : Strateji sinayicisinda sembol olarak BTCUSD secin (7/24 islem gordugu icin
//          hafta sonu saatleri de akar), robot altini da kendisi isler.
//+------------------------------------------------------------------+
#property copyright "ALTIN BTC ROBOT"
#property version   "1.00"

#include <Trade\Trade.mqh>

input double Risk             = 80.0;       // Islem basina zarar ($) - stop olursa
input double GunlukZararLimit = 250.0;      // Gunluk zarar limiti ($) - iki sembol toplam
input int    PragFark         = -1;         // Prag saati = sunucu saati + bu (FTMO: -1)
input string s1               = "------ ALTIN ------";
input bool   AltinAcik        = true;       // Altin islensin
input string AltinSembol      = "XAUUSD";   // Altin sembolu
input string AltinBasla       = "03:05";    // Altin aralik baslangici
input string AltinBit         = "06:05";    // Altin aralik bitisi (emirler)
input string AltinKapanis     = "18:55";    // Altin kapanis
input bool   AltinKarsiUc     = false;      // Altin stop karsi uc (false: yuzde)
input double AltinStopYuzde   = 1.0;        // Altin stop yuzdesi
input string s2               = "------ BTC ------";
input bool   BtcAcik          = true;       // BTC islensin
input string BtcSembol        = "BTCUSD";   // BTC sembolu
input string BtcBasla         = "05:00";    // BTC aralik baslangici
input string BtcBit           = "09:00";    // BTC aralik bitisi (emirler)
input string BtcKapanis       = "20:00";    // BTC kapanis
input bool   BtcKarsiUc       = true;       // BTC stop karsi uc (false: yuzde)
input double BtcStopYuzde     = 1.0;        // BTC stop yuzdesi (karsi uc false ise)
input string s3               = "------ DIGER ------";
input ulong  Sihir            = 20261120;   // Magic number
input string TelegramToken    = "";         // Telegram bot token
input string TelegramChatID   = "";         // Telegram chat id
input bool   TelegramAcik     = true;       // Telegram mesajlari

#define ON_EK "ABR_"
#define N 2

CTrade   trade;
string   KUYRUK[];
datetime tgBekle = 0;
string   tgDurum = "";
int      gunKey  = 0;
int      limitKey = 0;
bool     limitDoldu = false;

string S[N], AB[N], AI[N], KP[N], AD[N], IK[N];
bool   AKT[N], KU[N], HS[N];
double YZ[N];
double tepe[N], dip[N];
bool   aralikTamam[N], gunBitti[N], kapandi[N], mesajGitti[N];

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

//--- Prag gununun basi (sunucu saatiyle)
datetime PragGunBasi() { long f = (long)PragFark * 3600; return((datetime)((long)GunBasi((datetime)((long)TimeCurrent() + f)) - f)); }

bool HaftaSonu() { MqlDateTime z; TimeToStruct(TimeCurrent(), z); return(z.day_of_week == 0 || z.day_of_week == 6); }

string Para(double x) { return((x >= 0 ? "+" : "") + DoubleToString(x, 2) + " $"); }

string Fiyat(int i, double p) { return(DoubleToString(p, (int)SymbolInfoInteger(S[i], SYMBOL_DIGITS))); }

string Saat() { return(TimeToString(TimeCurrent(), TIME_DATE | TIME_MINUTES)); }

string StopYazi(int i) { return(KU[i] ? "karşı uç" : "%" + DoubleToString(YZ[i], 1)); }

int Bul(string sembol) { for(int i = 0; i < N; i++) if(AKT[i] && S[i] == sembol) return(i); return(-1); }

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
//  EMIR / POZISYON (her sembol ayri)
//+------------------------------------------------------------------+
int Pozisyon(int i, ulong &bilet)
{
   bilet = 0;
   for(int k = PositionsTotal() - 1; k >= 0; k--)
   {
      ulong t = PositionGetTicket(k);
      if(t == 0) continue;
      if(PositionGetString(POSITION_SYMBOL) != S[i]) continue;
      if((ulong)PositionGetInteger(POSITION_MAGIC) != Sihir) continue;
      bilet = t;
      return(PositionGetInteger(POSITION_TYPE) == POSITION_TYPE_BUY ? 1 : -1);
   }
   return(0);
}

ulong BekleyenBul(int i, ENUM_ORDER_TYPE tip)
{
   for(int k = OrdersTotal() - 1; k >= 0; k--)
   {
      ulong t = OrderGetTicket(k);
      if(t == 0) continue;
      if(OrderGetString(ORDER_SYMBOL) != S[i]) continue;
      if((ulong)OrderGetInteger(ORDER_MAGIC) != Sihir) continue;
      if((ENUM_ORDER_TYPE)OrderGetInteger(ORDER_TYPE) == tip) return(t);
   }
   return(0);
}

int BekleyenSay(int i)
{
   int n = 0;
   for(int k = OrdersTotal() - 1; k >= 0; k--)
   {
      ulong t = OrderGetTicket(k);
      if(t == 0) continue;
      if(OrderGetString(ORDER_SYMBOL) != S[i]) continue;
      if((ulong)OrderGetInteger(ORDER_MAGIC) != Sihir) continue;
      n++;
   }
   return(n);
}

void BekleyenSil(int i)
{
   for(int k = OrdersTotal() - 1; k >= 0; k--)
   {
      ulong t = OrderGetTicket(k);
      if(t == 0) continue;
      if(OrderGetString(ORDER_SYMBOL) != S[i]) continue;
      if((ulong)OrderGetInteger(ORDER_MAGIC) != Sihir) continue;
      trade.OrderDelete(t);
   }
}

void Kapat(int i)
{
   BekleyenSil(i);
   ulong b;
   if(Pozisyon(i, b) != 0) trade.PositionClose(b);
}

//--- stop olursa zarar = Risk olacak lot. Cok kucukse 0 doner (islem yok).
double LotHesap(int i, bool al, double giris, double stop)
{
   double kz = 0.0;
   ENUM_ORDER_TYPE ot = al ? ORDER_TYPE_BUY : ORDER_TYPE_SELL;
   if(!OrderCalcProfit(ot, S[i], 1.0, giris, stop, kz) || kz >= 0.0)
   {
      double tv = SymbolInfoDouble(S[i], SYMBOL_TRADE_TICK_VALUE);
      double ts = SymbolInfoDouble(S[i], SYMBOL_TRADE_TICK_SIZE);
      if(tv <= 0.0 || ts <= 0.0) return(0.0);
      kz = -MathAbs(giris - stop) / ts * tv;
   }
   if(kz >= 0.0) return(0.0);
   double lot = Risk / MathAbs(kz);
   double adim = SymbolInfoDouble(S[i], SYMBOL_VOLUME_STEP);
   double enAz = SymbolInfoDouble(S[i], SYMBOL_VOLUME_MIN);
   double enUst = SymbolInfoDouble(S[i], SYMBOL_VOLUME_MAX);
   if(adim <= 0.0) adim = 0.01;
   lot = MathFloor(lot / adim + 1e-9) * adim;
   if(lot < enAz - 1e-9) return(0.0);
   if(lot > enUst) lot = enUst;
   int bas = (int)MathMax(0.0, MathCeil(-MathLog10(adim) - 1e-9));
   return(NormalizeDouble(lot, bas));
}

double StopFiyat(int i, bool al, double giris)
{
   int dg = (int)SymbolInfoInteger(S[i], SYMBOL_DIGITS);
   double k = YZ[i] / 100.0;
   if(KU[i]) return(NormalizeDouble(al ? dip[i] : tepe[i], dg));
   return(NormalizeDouble(al ? giris * (1.0 - k) : giris * (1.0 + k), dg));
}

bool BugunIslemVar(int i)
{
   if(!HistorySelect(GunBasi(TimeCurrent()), TimeCurrent() + 60)) return(false);
   for(int k = 0; k < HistoryDealsTotal(); k++)
   {
      ulong d = HistoryDealGetTicket(k);
      if(d == 0) continue;
      if((ulong)HistoryDealGetInteger(d, DEAL_MAGIC) != Sihir) continue;
      if(HistoryDealGetString(d, DEAL_SYMBOL) != S[i]) continue;
      if(HistoryDealGetInteger(d, DEAL_ENTRY) == DEAL_ENTRY_IN) return(true);
   }
   return(false);
}

bool AralikHesapla(int i)
{
   datetime g = GunBasi(TimeCurrent());
   datetime a = g + Dakika(AB[i]) * 60;
   datetime b = g + Dakika(AI[i]) * 60 - 1;
   MqlRates r[];
   int n = CopyRates(S[i], PERIOD_M1, a, b, r);
   if(n < 30) return(false);                         // tatil / veri yok: bugun islem yok
   tepe[i] = r[0].high; dip[i] = r[0].low;
   for(int k = 1; k < n; k++) { tepe[i] = MathMax(tepe[i], r[k].high); dip[i] = MathMin(dip[i], r[k].low); }
   return(tepe[i] > dip[i]);
}

//--- aralik bitince: emirleri koy / eksik emri tamamla / fiyat disaridaysa piyasadan gir
void EmirIsle(int i)
{
   int dg = (int)SymbolInfoInteger(S[i], SYMBOL_DIGITS);
   double ask = SymbolInfoDouble(S[i], SYMBOL_ASK), bid = SymbolInfoDouble(S[i], SYMBOL_BID);
   if(ask <= 0.0 || bid <= 0.0) return;
   trade.SetTypeFillingBySymbol(S[i]);
   if(ask >= tepe[i] || bid <= dip[i])                 // fiyat zaten aralik disinda: hemen gir
   {
      bool al = (ask >= tepe[i]);
      double giris = al ? ask : bid;
      double st = StopFiyat(i, al, giris);
      double lot = LotHesap(i, al, giris, st);
      if(lot <= 0.0)
      {
         TgEkle("⚠️ " + AD[i] + ": lot çok küçük çıktı (risk " + DoubleToString(Risk, 0) + " $). Bugün işlem yok.");
         gunBitti[i] = true;
         BekleyenSil(i);
         return;
      }
      BekleyenSil(i);
      bool ok = al ? trade.Buy(lot, S[i], ask, st, 0.0, "ABR") : trade.Sell(lot, S[i], bid, st, 0.0, "ABR");
      if(ok) gunBitti[i] = true;
      return;
   }
   double t = NormalizeDouble(tepe[i], dg), d = NormalizeDouble(dip[i], dg);
   double stA = StopFiyat(i, true, t), stS = StopFiyat(i, false, d);
   double lotA = LotHesap(i, true, t, stA), lotS = LotHesap(i, false, d, stS);
   if(lotA <= 0.0 || lotS <= 0.0)
   {
      TgEkle("⚠️ " + AD[i] + ": lot çok küçük çıktı (risk " + DoubleToString(Risk, 0) + " $). Bugün işlem yok.");
      gunBitti[i] = true;
      BekleyenSil(i);
      return;
   }
   bool ok1 = (BekleyenBul(i, ORDER_TYPE_BUY_STOP) != 0);
   bool ok2 = (BekleyenBul(i, ORDER_TYPE_SELL_STOP) != 0);
   if(!ok1) ok1 = trade.BuyStop(lotA, t, S[i], stA, 0.0, ORDER_TIME_GTC, 0, "ABR");
   if(!ok2) ok2 = trade.SellStop(lotS, d, S[i], stS, 0.0, ORDER_TIME_GTC, 0, "ABR");
   if(!mesajGitti[i])
   {
      mesajGitti[i] = true;
      TgEkle("⏰ " + AD[i] + " ARALIK HAZIR (" + AB[i] + "–" + AI[i] + ")\n🔺 Tepe: " + Fiyat(i, tepe[i]) +
             "   🔻 Dip: " + Fiyat(i, dip[i]) + "\n📏 Aralık: " + DoubleToString(tepe[i] - dip[i], 2) + " $" +
             "\n🟢 Buy Stop: " + Fiyat(i, t) + " | lot " + DoubleToString(lotA, 2) + (ok1 ? " ✔" : " ✖ (tekrar denenecek)") +
             "\n🔴 Sell Stop: " + Fiyat(i, d) + " | lot " + DoubleToString(lotS, 2) + (ok2 ? " ✔" : " ✖ (tekrar denenecek)") +
             "\n🛑 Stop " + StopYazi(i) + " = -" + DoubleToString(Risk, 0) + " $ | 🎯 TP yok | 🕐 " + KP[i] + "'te kapanış");
   }
}

//+------------------------------------------------------------------+
//  GUNLUK HESAP (iki sembol toplam veya tek sembol)
//+------------------------------------------------------------------+
void GunVerisi(datetime a, datetime b, string sembol, int &adet, double &kz)
{
   adet = 0; kz = 0.0;
   if(!HistorySelect(a, b)) return;
   for(int k = 0; k < HistoryDealsTotal(); k++)
   {
      ulong d = HistoryDealGetTicket(k);
      if(d == 0) continue;
      if((ulong)HistoryDealGetInteger(d, DEAL_MAGIC) != Sihir) continue;
      if(sembol != "" && HistoryDealGetString(d, DEAL_SYMBOL) != sembol) continue;
      kz += HistoryDealGetDouble(d, DEAL_PROFIT) + HistoryDealGetDouble(d, DEAL_SWAP) +
            HistoryDealGetDouble(d, DEAL_COMMISSION);
      if(HistoryDealGetInteger(d, DEAL_ENTRY) == DEAL_ENTRY_IN) adet++;
   }
}

double AcikKZ(int i)
{
   ulong b;
   if(!AKT[i] || Pozisyon(i, b) == 0 || !PositionSelectByTicket(b)) return(0.0);
   return(PositionGetDouble(POSITION_PROFIT) + PositionGetDouble(POSITION_SWAP));
}

void GunSifirla()
{
   for(int i = 0; i < N; i++) { aralikTamam[i] = false; gunBitti[i] = false; kapandi[i] = false; mesajGitti[i] = false; tepe[i] = 0.0; dip[i] = 0.0; }
}

void GunKontrol()
{
   int g = GunAnahtari(TimeCurrent());
   if(gunKey == 0) { gunKey = g; return; }
   if(g == gunKey) return;
   datetime bugun = GunBasi(TimeCurrent()), dun = bugun - 86400;
   string m = "";
   int topAd = 0; double topKz = 0.0;
   for(int i = 0; i < N; i++)
   {
      if(!AKT[i]) continue;
      int ad; double kz;
      GunVerisi(dun, bugun - 1, S[i], ad, kz);
      if(ad == 0) continue;
      topAd += ad; topKz += kz;
      m += "\n" + IK[i] + " " + AD[i] + ": " + (kz >= 0 ? "✅ " : "❌ ") + Para(kz);
   }
   if(topAd > 0)
      TgEkle("📊 GÜNLÜK ÖZET – " + TimeToString(dun, TIME_DATE) + m + "\n💼 Toplam: " + Para(topKz) +
             "\n🏦 Bakiye: " + DoubleToString(AccountInfoDouble(ACCOUNT_BALANCE), 2) + " $");
   gunKey = g;
   GunSifirla();
}

void LimitKontrol()
{
   int lk = GunAnahtari(TimeCurrent() + PragFark * 3600);   // Prag gunu degisince limit sifirlanir
   if(lk != limitKey) { limitKey = lk; limitDoldu = false; }
   if(limitDoldu) return;
   int ad; double kz;
   GunVerisi(PragGunBasi(), TimeCurrent() + 60, "", ad, kz);
   double top = kz;
   for(int i = 0; i < N; i++) top += AcikKZ(i);
   if(top <= -GunlukZararLimit)
   {
      limitDoldu = true;
      for(int i = 0; i < N; i++) if(AKT[i]) Kapat(i);
      TgEkle("⛔ GÜNLÜK ZARAR LİMİTİ DOLDU\nBugünkü zarar: " + Para(top) + " (limit -" +
             DoubleToString(GunlukZararLimit, 0) + " $)\nHer şey kapatıldı, Prag gece yarısına kadar yeni işlem yok.\n🕐 " + Saat());
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
      ObjectSetInteger(0, n, OBJPROP_XSIZE, 450);
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
   int ad; double kz;
   GunVerisi(PragGunBasi(), TimeCurrent() + 60, "", ad, kz);
   double ak = 0.0;
   for(int i = 0; i < N; i++) ak += AcikKZ(i);
   Arka(240);                                   // once arka plan, yazilar ustte kalsin
   int y = 25;
   Yazi("0", "🥇₿ ALTIN + BTC ROBOT", y, 14, clrDarkGoldenrod); y += 26;
   Yazi("1", "Risk: işlem başı -" + DoubleToString(Risk, 0) + " $ | TP yok | Günlük limit -" +
        DoubleToString(GunlukZararLimit, 0) + " $", y, 9, clrBlack); y += 22;
   for(int i = 0; i < N; i++)
   {
      string on = "s" + IntegerToString(i);
      if(!AKT[i]) { Yazi(on + "a", IK[i] + " " + AD[i] + ": kapalı", y, 10, clrGray); y += 20; Yazi(on + "b", " ", y, 8, clrGray); y += 18; continue; }
      ulong b; int p = Pozisyon(i, b);
      double a = AcikKZ(i);
      string d = (p > 0) ? ("LONG açık " + Para(a)) : (p < 0 ? ("SHORT açık " + Para(a)) :
                 (BekleyenSay(i) > 0 ? "Buy Stop + Sell Stop bekliyor" : "İşlem yok"));
      Yazi(on + "a", IK[i] + " " + AD[i] + " (" + AB[i] + "–" + AI[i] + ", " + KP[i] + ", stop " + StopYazi(i) + "): " + d,
           y, 9, p != 0 ? (a >= 0 ? clrGreen : clrRed) : clrNavy); y += 18;
      string ar = (tepe[i] > 0.0) ? ("   Aralık: " + Fiyat(i, dip[i]) + " – " + Fiyat(i, tepe[i])) : "   Aralık: " + AI[i] + "'i bekliyor";
      Yazi(on + "b", ar, y, 8, clrBlack); y += 20;
   }
   Yazi("5", "Bugün toplam: " + Para(kz + ak) + (limitDoldu ? "  ⛔ LİMİT DOLDU" : ""), y, 10,
        (kz + ak) >= 0 ? clrGreen : clrRed); y += 22;
   Yazi("tg", "Telegram: " + (TelegramAcik ? (tgDurum == "" ? "hazır" : tgDurum) : "kapalı"), y, 8, clrGray);
}

//+------------------------------------------------------------------+
//  ANA
//+------------------------------------------------------------------+
void Calis(int i)
{
   if(!AKT[i]) return;
   if(!HS[i] && HaftaSonu()) return;
   int m = SimdiDakika();
   ulong b;
   int p = Pozisyon(i, b);
   //--- biri dolunca digeri silinir (gunde tek islem)
   if(p != 0 && BekleyenSay(i) > 0) BekleyenSil(i);
   //--- kapanis saati
   if(m >= Dakika(KP[i]))
   {
      if(!kapandi[i] && (p != 0 || BekleyenSay(i) > 0)) Kapat(i);
      kapandi[i] = true;
      return;
   }
   if(limitDoldu || gunBitti[i] || m < Dakika(AI[i])) return;
   if(p != 0) { gunBitti[i] = true; return; }
   if(BugunIslemVar(i)) { gunBitti[i] = true; BekleyenSil(i); return; }
   if(!aralikTamam[i])
   {
      if(!AralikHesapla(i))
      {
         TgEkle("ℹ️ " + AD[i] + ": bugün aralık saatlerinde veri yok (tatil?). Bugün işlem yok.");
         gunBitti[i] = true;
         return;
      }
      aralikTamam[i] = true;
   }
   EmirIsle(i);
}

int OnInit()
{
   S[0] = AltinSembol; AB[0] = AltinBasla; AI[0] = AltinBit; KP[0] = AltinKapanis; KU[0] = AltinKarsiUc; YZ[0] = AltinStopYuzde;
   AKT[0] = AltinAcik; HS[0] = false; AD[0] = "ALTIN"; IK[0] = "🥇";
   S[1] = BtcSembol; AB[1] = BtcBasla; AI[1] = BtcBit; KP[1] = BtcKapanis; KU[1] = BtcKarsiUc; YZ[1] = BtcStopYuzde;
   AKT[1] = BtcAcik; HS[1] = true; AD[1] = "BTC"; IK[1] = "₿";
   trade.SetExpertMagicNumber(Sihir);
   for(int i = 0; i < N; i++)
      if(AKT[i] && !SymbolSelect(S[i], true)) { Print("Sembol bulunamadi: ", S[i]); return(INIT_FAILED); }
   gunKey = GunAnahtari(TimeCurrent());
   limitKey = GunAnahtari(TimeCurrent() + PragFark * 3600);
   GunSifirla();
   string m = "";
   for(int i = 0; i < N; i++)
      if(AKT[i]) m += "\n" + IK[i] + " " + S[i] + ": aralık " + AB[i] + "–" + AI[i] + " | kapanış " + KP[i] + " | stop " + StopYazi(i);
   TgEkle("🤖 ALTIN + BTC ROBOT BAŞLADI" + m + "\n💵 Risk: işlem başı -" + DoubleToString(Risk, 0) +
          " $ (lot otomatik) | 🎯 TP yok\n⛔ Günlük limit: -" + DoubleToString(GunlukZararLimit, 0) + " $");
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
      for(int i = 0; i < N; i++) Calis(i);
   if(!MQLInfoInteger(MQL_TESTER) || MQLInfoInteger(MQL_VISUAL_MODE)) Panel();
   TgGonder();
}

void OnTick() { }

void OnTradeTransaction(const MqlTradeTransaction &tr, const MqlTradeRequest &rq, const MqlTradeResult &rs)
{
   if(tr.type != TRADE_TRANSACTION_DEAL_ADD) return;
   if(!HistoryDealSelect(tr.deal)) return;
   int i = Bul(HistoryDealGetString(tr.deal, DEAL_SYMBOL));
   if(i < 0) return;
   if((ulong)HistoryDealGetInteger(tr.deal, DEAL_MAGIC) != Sihir)
   {
      //--- stop ile kapanista magic yoksa pozisyonun acilis deal'ine bak
      long pid = HistoryDealGetInteger(tr.deal, DEAL_POSITION_ID);
      bool bizim = false;
      if(HistorySelectByPosition(pid))
         for(int k = 0; k < HistoryDealsTotal(); k++)
         {
            ulong x = HistoryDealGetTicket(k);
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
      double sl = StopFiyat(i, al, px);
      if(PositionSelectByTicket((ulong)HistoryDealGetInteger(tr.deal, DEAL_POSITION_ID)) && PositionGetDouble(POSITION_SL) > 0.0)
         sl = PositionGetDouble(POSITION_SL);
      gunBitti[i] = true;
      TgEkle(IK[i] + (al ? " 🟢 " : " 🔴 ") + AD[i] + (al ? " LONG AÇILDI" : " SHORT AÇILDI") +
             "\n📍 Giriş: " + Fiyat(i, px) + "\n🛑 Stop: " + Fiyat(i, sl) + " (" + StopYazi(i) + ", ~-" + DoubleToString(Risk, 0) + " $)" +
             "\n🎯 TP yok, " + KP[i] + "'te kapanacak\n📦 Lot: " + DoubleToString(HistoryDealGetDouble(tr.deal, DEAL_VOLUME), 2) +
             "\n🗑 Karşı emir siliniyor\n🕐 " + Saat());
      return;
   }
   if(g != DEAL_ENTRY_OUT && g != DEAL_ENTRY_OUT_BY) return;
   double p = HistoryDealGetDouble(tr.deal, DEAL_PROFIT) + HistoryDealGetDouble(tr.deal, DEAL_SWAP) +
              HistoryDealGetDouble(tr.deal, DEAL_COMMISSION);
   long sebep = HistoryDealGetInteger(tr.deal, DEAL_REASON);
   string neden = (sebep == DEAL_REASON_SL) ? "🛑 Stop oldu" :
                  (sebep == DEAL_REASON_EXPERT ? (limitDoldu ? "⛔ Günlük limit" : "🕐 " + KP[i] + " kapanışı") : "✋ Elle / diğer");
   string yon = (tip == DEAL_TYPE_SELL) ? "LONG" : "SHORT";
   TgEkle((p > 0 ? "✅ " : "❌ ") + IK[i] + " " + AD[i] + " " + yon + " KAPANDI\n🔚 Çıkış: " + Fiyat(i, px) + "\n" + neden +
          "\n" + (p > 0 ? "💰 Kâr: " : "💸 Zarar: ") + Para(p) + "\n🕐 " + Saat());
}
//+------------------------------------------------------------------+
