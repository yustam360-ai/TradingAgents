//+------------------------------------------------------------------+
//|  EAROBOT_ICT.mq5                                                 |
//|  IKI MANTIKLI ROBOT (MT5 / MQL5) - FTMO                          |
//|  1) KESISIM : EAROBOT'un kurallari (22 sembolun kurallari cikti)  |
//|  2) ICT     : Ekin/ICT modeli, 82 sembol, her biri kendi mantigi |
//+------------------------------------------------------------------+
//  Butun saatler NEW YORK saati (FTMO sunucusu = NY + 7 saat, SunucuNY ayari).
//
//  1) KESISIM (EAROBOT, AYNEN): 39 sembol, 39 kural. Cikarilan 22 sembol:
//     AAPL JNJ XAUUSD(Asya kirilimi) RACE CSCO BABA FRA40.cash EU50.cash USDILS USDSGD EURCZK
//     SOYBEAN.c HEATOIL.c ADAUSD XCUUSD EURHUF FDX XPTUSD CORN.c WHEAT.c BAC XTZUSD
//     - 1 saatlik mum kapaninca sart kontrol edilir, sart varsa piyasa emriyle islem acilir.
//     - STOP = giris -/+ (stop katsayisi x ATR14), HEDEF = stopun 2 kati. 5 gun icinde TP/stop yoksa kapanir.
//     - Magic: Sihir*100 + kural no.  Ayni kural ayni anda tek islem, ayni yonde 10 dk tekrar acmaz.
//  2) ICT (ekin_142_test_3ay.py ile BIREBIR AYNI mantik, her sembol kendi mantigi):
//     - Saat: FOREX Londra NY 02:00-05:00 + NY 07:00-10:00 | DIGER NY 08:30-11:00.
//     - Killzone basinda alinmamis seviyenin supurulmesi -> MSS / IFVG -> FVG/IFVG'den giris.
//     - Limit emir (ORTA / KENAR) ya da kirilim mumu kapaninca piyasa emri (KAPANIS).
//       Emir seans sonuna (SEANS_SONU) ya da 2 saat (2_SAAT) gecerli; fiyat girise gelmeden TP
//       seviyesine giderse emir iptal.  Acik islem NY 16:00'da kapanir.
//     - Sembolde ayni anda tek ICT islemi / emri.  DISIPLIN=EKIN: seansta tek islem, kazandiysa o gun bitti.
//     - Magic: (Sihir+1)*100 + sembol sira no.
//  LOT   : stop olursa RiskDolar (15 $) zarar. En kucuk lottan kucukse en kucuk lot;
//          en kucuk lotta zarar EnFazlaZarar'i (30 $) gecerse islem ACILMAZ.
//  MAKAS : o andaki spread'in o lottaki maliyeti MakasSinir'i (6 $) gecerse islem ACILMAZ.
//  GUNLUK LIMIT: 250 $, SADECE BU ROBOTUN islemleri (iki mantik birlikte). Kalan = 250 + bugun kapanan + acik.
//          Gun Prag gece yarisinda baslar. 0'a inerse robot KENDI islemlerini kapatir, o gun durur.
//  TELEGRAM: TP / STOP / kapanis mesaji; stop olan islem 24 saat izlenir; Prag gece yarisi gun sonu raporu.
//          MT5: Araclar > Secenekler > Uzman Danismanlar > "WebRequest izin ver" + https://api.telegram.org
//  PANEL : sol ust kose (grafik arka plani beyaz olmali, yazi siyah).
//+------------------------------------------------------------------+
#property copyright "EAROBOT"
#property version   "2.01"

#include <Trade\Trade.mqh>

input double RiskDolar      = 15.0;      // stop olursa zarar ($)
input double EnFazlaZarar   = 30.0;      // en kucuk lotta zarar bunu gecerse islem yok ($)
input double MakasSinir     = 6.0;       // spread maliyeti bunu gecerse islem yok ($)
input double GunlukLimit    = 250.0;     // robotun gunluk zarar limiti ($), acik islemler dahil
input int    TekrarDakika   = 10;        // KESISIM: ayni kural ayni yonde kac dakika tekrar acmaz
input int    SunucuNY       = 7;         // sunucu saati - New York saati
input int    Kayma          = 20;        // izin verilen kayma (puan)
input ulong  Sihir          = 20261108;  // magic: KESISIM Sihir*100+kural, ICT (Sihir+1)*100+sembol
input string TelegramToken  = "";        // EAROBOT.mq5 ile ayni token
input string TelegramChatID = "";        // EAROBOT.mq5 ile ayni chat id
input bool   TelegramAcik   = true;      // Telegram mesajlari
input int    YaziBoyu       = 14;        // sol ust yazi boyutu
input int    YaziY          = 30;        // sol ust yazinin ustten uzakligi
input int    TestSunucuPragFarki = 1;    // SADECE Strateji Test Araci: sunucu saati - Prag saati

#define K_SAAT   0
#define K_RSI    1
#define K_SAKIN  2
#define K_EMA    3
#define K_ASYA   4
#define SURE_SN  432000      // 5 gun
#define IZLE_SN  86400       // stop sonrasi 24 saat

//--- ICT mantik secenekleri (ekin_142_test_3ay.py SORULAR ile ayni sira)
#define G_ORTA      0
#define G_KENAR     1
#define G_KAPANIS   2
#define ST_SWING    0
#define ST_FVGMUM   1
#define ST_UC       2
#define T_2R        0
#define T_3R        1
#define T_LIK       2
#define AD_PDH      0
#define AD_PWH      1
#define AD_ASYA     2
#define AD_LONDRA   3
#define AD_NYPM     4
#define AD_ESIT     5
#define AD_FVG1     6
#define AD_FVG4     7
#define AD_FVGG     8
#define BOS         1e300    // bos aralik (Python inf)
#define ICT_GUN     60       // ICT icin yuklenen 1 dk gecmis (gun)
#define NY_KAPANIS  1380     // sunucu 23:00 = NY 16:00 (gun basindan dakika)

struct Kural
{
   string s;       // sembol
   int    tip;
   int    yon;     // +1 AL, -1 SAT, 0 iki yon
   int    a;       // SAAT: baslangic saati, RSI: alt, EMA: hizli
   int    b;       // SAAT: bitis saati (dahil degil), RSI: ust (dahil degil), EMA: yavas
   int    f;       // EMA: filtre EMA (0 = yok)
   double sk;      // stop = sk x ATR, hedef = 2 x sk x ATR
   string ad;      // mantigin adi (Telegram)
   bool   aktif;
};

//--- ICT: bir sembol ve kendi mantigi
class CEk
{
public:
   string s;
   int    mss;      // 0 SART, 1 IFVG_YETER
   int    yon;      // 0 YOK, 1 EKIN, 2 ICT
   int    giris;    // G_ORTA / G_KENAR / G_KAPANIS
   int    stp;      // ST_SWING / ST_FVGMUM / ST_UC
   int    tp;       // T_2R / T_3R / T_LIK
   int    sev;      // 0 EKIN, 1 ICT
   int    zmn;      // 0 EKIN_5_3, 1 ICT_15_5
   int    dis;      // 0 YOK, 1 EKIN
   int    emir;     // 0 SEANS_SONU, 1 2_SAAT
   int    shrp;     // 0 YOK, 1 SART
   double tol;      // esit tepe toleransi (ATR)
   string ad;       // mantik metni
   bool   aktif;
   bool   forex;
   //--- killzone hazirligi
   long   hzKs, hzKe, hzD, hzDp, sonB, denKs;
   int    den;
   int    hzKz;     // 0 LONDRA, 1 NY
   bool   hzOk;
   int    yonEk, yonIc;
   int    lvY[];  double lvP[];  int lvTip[];   // seviye: yon, fiyat (ayna), tip 0 hesap(>) 1 esit tepe(>) 2 FVG(>=)
   int    kY[];   double kP[];                  // karsi likidite (ayna)
           CEk() { aktif = true; forex = false; hzKs = -1; hzKe = 0; hzD = 0; hzDp = 0; sonB = 0; hzKz = 0; hzOk = false; yonEk = 0; yonIc = 0; denKs = -1; den = 0; }
};

Kural    K[];
string   SEM[];
datetime SONBAR[];
bool     HAZIR[];
CEk     *EK[];
CTrade   trade;
string   ON_EK = "EAR_";
string   GV_DUR, GV_RAPOR;
int      durGun = -1;
bool     limitDurdu = false;
double   sonKalan = 0.0;
int      asyaKi = -1;
long     asyaGun = -1;
bool     asyaBitti = true;
double   asyaUst = 0.0, asyaAlt = 0.0;
string   KUYRUK[];
datetime tgBekle = 0;
string   tgDurum = "";
ulong    NPID[];  string NSTR[];                    // robotun kapattigi islemlerin nedeni
ulong    MPID[];                                    // mesaji gonderilen kapanislar
ulong    IZPID[]; ulong IZMG[]; int IZYON[]; double IZTP[]; datetime IZKAP[]; double IZGIR[]; double IZSL[]; double IZLOT[];
datetime sonIzleme = 0;

//--- ICT calisma dizileri (1 dk mumlar, sunucu dakikasi)
long   gT[];
double gO[], gH[], gL[], gC[], gS[];
int    gN = 0;
bool   gST = false;                                 // seyrek tablo hazir mi
double STX[], STN[];
int    STNn = 0;
int    LG[];
//--- degerlendirme: 3 / 5 / 15 dk mumlar
long   b3t[], b5t[], b15t[];
double b3o[], b3h[], b3l[], b3c[], b5o[], b5h[], b5l[], b5c[], b15o[], b15h[], b15l[], b15c[];
int    n3 = 0, n5 = 0, n15 = 0;
int    sw5[], sw15[], bq5[];
int    nbq5 = 0;
//--- bulunan kurulumlar
long   kTd[];  int kYn[];  double kTepe[], kTG[], kAlt[], kUst[], kMS[];  bool kSharp[];
int    nKur = 0;
//--- bolge listesi (kurulum icinde)
double zAlt[], zUst[], zGov[];  int zTur[];
int    nZon = 0;

//+------------------------------------------------------------------+
//  KURALLAR
//+------------------------------------------------------------------+
void KuralEkle(string s, int tip, int yon, int a, int b, int f, double sk, string ad)
{
   int n = ArraySize(K);
   ArrayResize(K, n + 1);
   K[n].s = s; K[n].tip = tip; K[n].yon = yon; K[n].a = a; K[n].b = b; K[n].f = f;
   K[n].sk = sk; K[n].ad = ad; K[n].aktif = true;
}

void EmaKural(string s, int hz, int yv, int f, double sk)
{
   string fs = (f == 0) ? "yok" : ("EMA" + IntegerToString(f));
   KuralEkle(s, K_EMA, 0, hz, yv, f, sk,
             StringFormat("EMA %d/%d kesişim, filtre %s, stop %.1f ATR / TP %.1f ATR", hz, yv, fs, sk, 2.0 * sk));
}

void KurallariYukle()
{
   ArrayResize(K, 0);
   //--- bolum 3: 8 kural (stop 1 ATR, hedef 2 ATR)
   KuralEkle("EURCZK", K_SAAT,  1, 19,  2, 0, 1.0, "AL - Asya seansı (mum NY 19:00-01:00 kapanınca), stop 1 ATR / TP 2 ATR");
   KuralEkle("EURCZK", K_SAAT, -1,  8, 12, 0, 1.0, "SAT - NY sabah (mum NY 08:00-11:00 kapanınca), stop 1 ATR / TP 2 ATR");
   KuralEkle("EURCZK", K_RSI,  -1, 55, 70, 0, 1.0, "SAT - RSI 55-70, stop 1 ATR / TP 2 ATR");
   KuralEkle("USDILS", K_SAKIN,-1,  0,  0, 0, 1.0, "SAT - sakin piyasa (ATR < ATR100 ort. x 0.8), stop 1 ATR / TP 2 ATR");
   KuralEkle("USDILS", K_SAAT, -1, 12, 17, 0, 1.0, "SAT - NY öğleden sonra (mum NY 12:00-16:00 kapanınca), stop 1 ATR / TP 2 ATR");
   KuralEkle("USDSGD", K_RSI,   1, 30, 45, 0, 1.0, "AL - RSI 30-45, stop 1 ATR / TP 2 ATR");
   KuralEkle("MANUSD", K_RSI,  -1, 55, 70, 0, 1.0, "SAT - RSI 55-70, stop 1 ATR / TP 2 ATR");
   KuralEkle("XAUUSD", K_ASYA,  0,  0,  0, 0, 0.0, "AL/SAT - Asya aralığı kırılımı, stop karşı uç / TP 2 x aralık, NY 16:00 kapanış");
   //--- bolum 3B: 56 sembol EMA kesisim (hedef = 2 x stop)
   EmaKural("US30.cash",   5, 13,   0, 1.8);
   EmaKural("USDCAD",      8, 21, 100, 1.0);
   EmaKural("AUDUSD",      9, 21,  50, 1.3);
   EmaKural("XPTUSD",      9, 21,  50, 0.7);
   EmaKural("WHEAT.c",     5, 13,  50, 1.6);
   EmaKural("HK50.cash",   5, 13,  50, 1.7);
   EmaKural("SOYBEAN.c",  12, 26,   0, 1.6);
   EmaKural("AAVUSD",     21, 55,   0, 1.3);
   EmaKural("BTCUSD",     20, 50, 100, 1.0);
   EmaKural("CORN.c",      5, 13, 200, 1.6);
   EmaKural("ADAUSD",     20, 50,   0, 1.1);
   EmaKural("EURNZD",     12, 26, 100, 1.2);
   EmaKural("ICPUSD",      9, 21,  50, 2.0);
   EmaKural("NVDA",        5, 13,  50, 1.0);
   EmaKural("HEATOIL.c",  12, 26, 100, 1.4);
   EmaKural("AUDCHF",     12, 26,   0, 1.9);
   EmaKural("ALVG",        5, 13,   0, 0.7);
   EmaKural("GOOG",        5, 13,   0, 0.9);
   EmaKural("XCUUSD",     12, 26,   0, 2.0);
   EmaKural("TTE",         5, 13,  50, 1.1);
   EmaKural("XTZUSD",     20, 50,   0, 1.7);
   EmaKural("FRA40.cash",  8, 21, 100, 0.7);
   EmaKural("EU50.cash",   9, 26, 100, 0.8);
   EmaKural("GBPUSD",      8, 21, 100, 1.6);
   EmaKural("RTX",         5, 13,  50, 1.2);
   EmaKural("EURHUF",      8, 21,   0, 2.0);
   EmaKural("USDCHF",     20, 50,   0, 1.7);
   EmaKural("META",        5, 13,   0, 0.9);
   EmaKural("EURAUD",     12, 26,   0, 2.0);
   EmaKural("GE",          5, 13,   0, 0.9);
   EmaKural("MSFT",        9, 21,   0, 0.7);
   EmaKural("EURNOK",      5, 13, 100, 2.0);
   EmaKural("ARM",         5, 13,   0, 1.7);
   EmaKural("GRTUSD",     20, 50, 100, 1.5);
   EmaKural("SAN",         8, 21,   0, 0.8);
   EmaKural("AZN",         5, 13,   0, 1.2);
   EmaKural("AMD",         5, 13,   0, 1.0);
   EmaKural("QCOM",        9, 21,   0, 1.0);
   EmaKural("T",           5, 13,   0, 0.8);
   EmaKural("AAPL",       12, 26,   0, 0.7);
   EmaKural("DIS",         8, 21,   0, 1.6);
   EmaKural("COFFEE.c",   12, 26,   0, 1.1);
   EmaKural("BABA",        5, 13,   0, 1.2);
   EmaKural("INTC",        5, 13,  50, 1.2);
   EmaKural("LMT",         9, 21,   0, 0.9);
   EmaKural("FDX",         5, 13, 100, 1.0);
   EmaKural("AVGO",        9, 21,   0, 1.3);
   EmaKural("BAC",         5, 13, 100, 1.2);
   EmaKural("IBM",         5, 13,  50, 1.0);
   EmaKural("ZM",          5, 13,  50, 1.1);
   EmaKural("UKOIL.cash", 21, 55,   0, 1.9);
   EmaKural("JNJ",         5, 13,   0, 1.5);
   EmaKural("CSCO",        8, 21,  50, 1.7);
   EmaKural("BA",          9, 21,   0, 0.7);
   EmaKural("RACE",        9, 21,   0, 1.8);
   EmaKural("CVX",         5, 13,   0, 1.8);
}

//--- KESISIM'den cikarilan 22 sembol (kurallari pasif; sira numaralari ve magic'ler degismez)
void KesisimCikar()
{
   string cik[] = {"AAPL", "JNJ", "XAUUSD", "RACE", "CSCO", "BABA", "FRA40.cash", "EU50.cash", "USDILS", "USDSGD",
                   "EURCZK", "SOYBEAN.c", "HEATOIL.c", "ADAUSD", "XCUUSD", "EURHUF", "FDX", "XPTUSD", "CORN.c",
                   "WHEAT.c", "BAC", "XTZUSD"};
   for(int ki = 0; ki < ArraySize(K); ki++)
      for(int j = 0; j < ArraySize(cik); j++)
         if(K[ki].s == cik[j]) { K[ki].aktif = false; break; }
}

//+------------------------------------------------------------------+
//  ICT SEMBOLLERI VE MANTIKLARI (ekin_142_test_3ay.py MANTIK listesi, %50 ustu 82 sembol)
//+------------------------------------------------------------------+
string Deger(string m, string k)
{
   string p[];
   int n = StringSplit(m, ' ', p);
   for(int i = 0; i < n; i++)
      if(StringFind(p[i], k + "=") == 0) return(StringSubstr(p[i], StringLen(k) + 1));
   return("");
}

int Secenek(string m, string k, string a0, string a1, string a2, bool &ok)
{
   string v = Deger(m, k);
   if(v == a0) return(0);
   if(v == a1) return(1);
   if(a2 != "" && v == a2) return(2);
   ok = false;
   return(0);
}

void EkinEkle(string s, string m)
{
   CEk *e = new CEk();
   bool ok = true;
   e.s     = s;
   e.ad    = m;
   e.mss   = Secenek(m, "MSS", "SART", "IFVG_YETER", "", ok);
   e.yon   = Secenek(m, "YON", "YOK", "EKIN", "ICT", ok);
   e.giris = Secenek(m, "GIRIS", "ORTA", "KENAR", "KAPANIS", ok);
   e.stp   = Secenek(m, "STOP", "SWING_GOVDE", "FVG_MUM", "SUPURULEN_UC", ok);
   e.tp    = Secenek(m, "TP", "2R", "3R", "LIKIDITE", ok);
   e.sev   = Secenek(m, "SEVIYE", "EKIN", "ICT", "", ok);
   e.zmn   = Secenek(m, "ZAMAN", "EKIN_5_3", "ICT_15_5", "", ok);
   e.dis   = Secenek(m, "DISIPLIN", "YOK", "EKIN", "", ok);
   e.emir  = Secenek(m, "EMIR", "SEANS_SONU", "2_SAAT", "", ok);
   e.shrp  = Secenek(m, "SHARP", "YOK", "SART", "", ok);
   int t   = Secenek(m, "ESIT_TOL", "0.05ATR", "0.1ATR", "0.2ATR", ok);
   e.tol   = (t == 0) ? 0.05 : ((t == 1) ? 0.1 : 0.2);
   if(!ok) { e.aktif = false; PrintFormat("ICT mantik okunamadi: %s  %s", s, m); }
   int n = ArraySize(EK);
   ArrayResize(EK, n + 1);
   EK[n] = e;
}

void EkinYukle()
{
   EkinEkle("EURGBP", "MSS=SART YON=ICT GIRIS=KENAR STOP=SUPURULEN_UC TP=LIKIDITE SEVIYE=ICT ZAMAN=EKIN_5_3 DISIPLIN=EKIN EMIR=2_SAAT SHARP=YOK ESIT_TOL=0.05ATR");
   EkinEkle("XOM", "MSS=IFVG_YETER YON=EKIN GIRIS=KENAR STOP=FVG_MUM TP=LIKIDITE SEVIYE=ICT ZAMAN=EKIN_5_3 DISIPLIN=YOK EMIR=2_SAAT SHARP=YOK ESIT_TOL=0.05ATR");
   EkinEkle("XLMUSD", "MSS=SART YON=YOK GIRIS=ORTA STOP=SUPURULEN_UC TP=LIKIDITE SEVIYE=EKIN ZAMAN=ICT_15_5 DISIPLIN=YOK EMIR=2_SAAT SHARP=YOK ESIT_TOL=0.05ATR");
   EkinEkle("VECUSD", "MSS=SART YON=YOK GIRIS=KENAR STOP=SWING_GOVDE TP=3R SEVIYE=EKIN ZAMAN=ICT_15_5 DISIPLIN=YOK EMIR=2_SAAT SHARP=YOK ESIT_TOL=0.05ATR");
   EkinEkle("IMXUSD", "MSS=IFVG_YETER YON=EKIN GIRIS=ORTA STOP=FVG_MUM TP=2R SEVIYE=ICT ZAMAN=ICT_15_5 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=SART ESIT_TOL=0.2ATR");
   EkinEkle("ADAUSD", "MSS=SART YON=YOK GIRIS=KENAR STOP=FVG_MUM TP=3R SEVIYE=EKIN ZAMAN=ICT_15_5 DISIPLIN=YOK EMIR=2_SAAT SHARP=YOK ESIT_TOL=0.05ATR");
   EkinEkle("USDCZK", "MSS=SART YON=EKIN GIRIS=KENAR STOP=SUPURULEN_UC TP=3R SEVIYE=EKIN ZAMAN=EKIN_5_3 DISIPLIN=YOK EMIR=2_SAAT SHARP=YOK ESIT_TOL=0.05ATR");
   EkinEkle("EURUSD", "MSS=IFVG_YETER YON=ICT GIRIS=ORTA STOP=FVG_MUM TP=2R SEVIYE=EKIN ZAMAN=EKIN_5_3 DISIPLIN=EKIN EMIR=2_SAAT SHARP=SART ESIT_TOL=0.2ATR");
   EkinEkle("BA", "MSS=IFVG_YETER YON=ICT GIRIS=ORTA STOP=SUPURULEN_UC TP=2R SEVIYE=ICT ZAMAN=ICT_15_5 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=YOK ESIT_TOL=0.05ATR");
   EkinEkle("BMW", "MSS=IFVG_YETER YON=EKIN GIRIS=KENAR STOP=FVG_MUM TP=2R SEVIYE=EKIN ZAMAN=ICT_15_5 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=YOK ESIT_TOL=0.05ATR");
   EkinEkle("USDHKD", "MSS=IFVG_YETER YON=YOK GIRIS=ORTA STOP=FVG_MUM TP=2R SEVIYE=EKIN ZAMAN=ICT_15_5 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=YOK ESIT_TOL=0.05ATR");
   EkinEkle("COFFEE.c", "MSS=IFVG_YETER YON=ICT GIRIS=KENAR STOP=SUPURULEN_UC TP=2R SEVIYE=ICT ZAMAN=ICT_15_5 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=YOK ESIT_TOL=0.05ATR");
   EkinEkle("DXY.cash", "MSS=IFVG_YETER YON=YOK GIRIS=KENAR STOP=SWING_GOVDE TP=2R SEVIYE=EKIN ZAMAN=EKIN_5_3 DISIPLIN=YOK EMIR=2_SAAT SHARP=SART ESIT_TOL=0.05ATR");
   EkinEkle("XAUAUD", "MSS=SART YON=YOK GIRIS=ORTA STOP=FVG_MUM TP=LIKIDITE SEVIYE=EKIN ZAMAN=EKIN_5_3 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=SART ESIT_TOL=0.05ATR");
   EkinEkle("BNBUSD", "MSS=SART YON=YOK GIRIS=ORTA STOP=FVG_MUM TP=LIKIDITE SEVIYE=EKIN ZAMAN=ICT_15_5 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=YOK ESIT_TOL=0.2ATR");
   EkinEkle("DASHUSD", "MSS=SART YON=YOK GIRIS=KAPANIS STOP=SWING_GOVDE TP=3R SEVIYE=ICT ZAMAN=ICT_15_5 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=YOK ESIT_TOL=0.05ATR");
   EkinEkle("AMZN", "MSS=SART YON=YOK GIRIS=KENAR STOP=SWING_GOVDE TP=2R SEVIYE=EKIN ZAMAN=EKIN_5_3 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=YOK ESIT_TOL=0.05ATR");
   EkinEkle("EURNZD", "MSS=SART YON=YOK GIRIS=KAPANIS STOP=FVG_MUM TP=2R SEVIYE=ICT ZAMAN=ICT_15_5 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=YOK ESIT_TOL=0.1ATR");
   EkinEkle("SOYBEAN.c", "MSS=SART YON=YOK GIRIS=KAPANIS STOP=SUPURULEN_UC TP=3R SEVIYE=ICT ZAMAN=EKIN_5_3 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=YOK ESIT_TOL=0.05ATR");
   EkinEkle("SIEGn", "MSS=IFVG_YETER YON=YOK GIRIS=ORTA STOP=SUPURULEN_UC TP=LIKIDITE SEVIYE=ICT ZAMAN=EKIN_5_3 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=YOK ESIT_TOL=0.1ATR");
   EkinEkle("DOTUSD", "MSS=IFVG_YETER YON=YOK GIRIS=ORTA STOP=SWING_GOVDE TP=2R SEVIYE=EKIN ZAMAN=EKIN_5_3 DISIPLIN=YOK EMIR=2_SAAT SHARP=YOK ESIT_TOL=0.05ATR");
   EkinEkle("USDSEK", "MSS=IFVG_YETER YON=YOK GIRIS=KENAR STOP=SWING_GOVDE TP=2R SEVIYE=EKIN ZAMAN=ICT_15_5 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=YOK ESIT_TOL=0.2ATR");
   EkinEkle("GBPCAD", "MSS=SART YON=EKIN GIRIS=KAPANIS STOP=FVG_MUM TP=2R SEVIYE=ICT ZAMAN=ICT_15_5 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=SART ESIT_TOL=0.2ATR");
   EkinEkle("XMRUSD", "MSS=IFVG_YETER YON=EKIN GIRIS=KAPANIS STOP=SWING_GOVDE TP=2R SEVIYE=ICT ZAMAN=EKIN_5_3 DISIPLIN=EKIN EMIR=SEANS_SONU SHARP=YOK ESIT_TOL=0.1ATR");
   EkinEkle("MBG", "MSS=IFVG_YETER YON=YOK GIRIS=ORTA STOP=FVG_MUM TP=2R SEVIYE=EKIN ZAMAN=EKIN_5_3 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=YOK ESIT_TOL=0.05ATR");
   EkinEkle("DOGEUSD", "MSS=SART YON=YOK GIRIS=ORTA STOP=FVG_MUM TP=3R SEVIYE=EKIN ZAMAN=ICT_15_5 DISIPLIN=EKIN EMIR=2_SAAT SHARP=YOK ESIT_TOL=0.05ATR");
   EkinEkle("ZM", "MSS=SART YON=YOK GIRIS=ORTA STOP=FVG_MUM TP=2R SEVIYE=EKIN ZAMAN=ICT_15_5 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=YOK ESIT_TOL=0.05ATR");
   EkinEkle("BABA", "MSS=IFVG_YETER YON=YOK GIRIS=ORTA STOP=FVG_MUM TP=2R SEVIYE=ICT ZAMAN=ICT_15_5 DISIPLIN=YOK EMIR=2_SAAT SHARP=YOK ESIT_TOL=0.05ATR");
   EkinEkle("CORN.c", "MSS=SART YON=YOK GIRIS=KENAR STOP=SUPURULEN_UC TP=3R SEVIYE=EKIN ZAMAN=ICT_15_5 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=YOK ESIT_TOL=0.05ATR");
   EkinEkle("CHFJPY", "MSS=IFVG_YETER YON=ICT GIRIS=KENAR STOP=FVG_MUM TP=2R SEVIYE=ICT ZAMAN=ICT_15_5 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=YOK ESIT_TOL=0.05ATR");
   EkinEkle("SBUX", "MSS=IFVG_YETER YON=EKIN GIRIS=KAPANIS STOP=SUPURULEN_UC TP=LIKIDITE SEVIYE=EKIN ZAMAN=EKIN_5_3 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=YOK ESIT_TOL=0.05ATR");
   EkinEkle("BARUSD", "MSS=SART YON=YOK GIRIS=ORTA STOP=SUPURULEN_UC TP=LIKIDITE SEVIYE=ICT ZAMAN=EKIN_5_3 DISIPLIN=YOK EMIR=2_SAAT SHARP=SART ESIT_TOL=0.05ATR");
   EkinEkle("USDZAR", "MSS=IFVG_YETER YON=YOK GIRIS=ORTA STOP=FVG_MUM TP=2R SEVIYE=EKIN ZAMAN=EKIN_5_3 DISIPLIN=YOK EMIR=2_SAAT SHARP=YOK ESIT_TOL=0.05ATR");
   EkinEkle("ADSGn", "MSS=SART YON=YOK GIRIS=KENAR STOP=FVG_MUM TP=3R SEVIYE=EKIN ZAMAN=EKIN_5_3 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=YOK ESIT_TOL=0.05ATR");
   EkinEkle("XAUEUR", "MSS=SART YON=YOK GIRIS=KAPANIS STOP=FVG_MUM TP=2R SEVIYE=EKIN ZAMAN=EKIN_5_3 DISIPLIN=EKIN EMIR=SEANS_SONU SHARP=SART ESIT_TOL=0.05ATR");
   EkinEkle("SANUSD", "MSS=IFVG_YETER YON=YOK GIRIS=KAPANIS STOP=SUPURULEN_UC TP=3R SEVIYE=EKIN ZAMAN=ICT_15_5 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=YOK ESIT_TOL=0.05ATR");
   EkinEkle("FRA40.cash", "MSS=IFVG_YETER YON=YOK GIRIS=ORTA STOP=SUPURULEN_UC TP=2R SEVIYE=ICT ZAMAN=EKIN_5_3 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=YOK ESIT_TOL=0.05ATR");
   EkinEkle("MCD", "MSS=IFVG_YETER YON=ICT GIRIS=ORTA STOP=FVG_MUM TP=LIKIDITE SEVIYE=ICT ZAMAN=EKIN_5_3 DISIPLIN=YOK EMIR=2_SAAT SHARP=SART ESIT_TOL=0.05ATR");
   EkinEkle("AUDJPY", "MSS=SART YON=EKIN GIRIS=KAPANIS STOP=SWING_GOVDE TP=LIKIDITE SEVIYE=EKIN ZAMAN=EKIN_5_3 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=YOK ESIT_TOL=0.05ATR");
   EkinEkle("INTC", "MSS=IFVG_YETER YON=ICT GIRIS=KAPANIS STOP=FVG_MUM TP=3R SEVIYE=ICT ZAMAN=ICT_15_5 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=SART ESIT_TOL=0.05ATR");
   EkinEkle("GOOG", "MSS=IFVG_YETER YON=EKIN GIRIS=ORTA STOP=SWING_GOVDE TP=LIKIDITE SEVIYE=EKIN ZAMAN=ICT_15_5 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=SART ESIT_TOL=0.05ATR");
   EkinEkle("BAYGn", "MSS=IFVG_YETER YON=YOK GIRIS=KENAR STOP=FVG_MUM TP=2R SEVIYE=EKIN ZAMAN=EKIN_5_3 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=YOK ESIT_TOL=0.2ATR");
   EkinEkle("NKE", "MSS=IFVG_YETER YON=YOK GIRIS=KENAR STOP=FVG_MUM TP=3R SEVIYE=EKIN ZAMAN=EKIN_5_3 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=SART ESIT_TOL=0.05ATR");
   EkinEkle("ETHUSD", "MSS=IFVG_YETER YON=ICT GIRIS=KENAR STOP=FVG_MUM TP=3R SEVIYE=EKIN ZAMAN=ICT_15_5 DISIPLIN=YOK EMIR=2_SAAT SHARP=YOK ESIT_TOL=0.05ATR");
   EkinEkle("AVGO", "MSS=IFVG_YETER YON=ICT GIRIS=ORTA STOP=SWING_GOVDE TP=2R SEVIYE=EKIN ZAMAN=EKIN_5_3 DISIPLIN=YOK EMIR=2_SAAT SHARP=SART ESIT_TOL=0.05ATR");
   EkinEkle("SPN35.cash", "MSS=IFVG_YETER YON=ICT GIRIS=KAPANIS STOP=SWING_GOVDE TP=3R SEVIYE=ICT ZAMAN=EKIN_5_3 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=YOK ESIT_TOL=0.05ATR");
   EkinEkle("NZDCAD", "MSS=SART YON=EKIN GIRIS=KENAR STOP=FVG_MUM TP=2R SEVIYE=ICT ZAMAN=ICT_15_5 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=SART ESIT_TOL=0.2ATR");
   EkinEkle("XTZUSD", "MSS=IFVG_YETER YON=YOK GIRIS=KAPANIS STOP=FVG_MUM TP=LIKIDITE SEVIYE=ICT ZAMAN=ICT_15_5 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=YOK ESIT_TOL=0.1ATR");
   EkinEkle("KO", "MSS=IFVG_YETER YON=ICT GIRIS=KENAR STOP=FVG_MUM TP=2R SEVIYE=EKIN ZAMAN=EKIN_5_3 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=YOK ESIT_TOL=0.05ATR");
   EkinEkle("USDCNH", "MSS=SART YON=YOK GIRIS=ORTA STOP=FVG_MUM TP=2R SEVIYE=EKIN ZAMAN=ICT_15_5 DISIPLIN=YOK EMIR=2_SAAT SHARP=SART ESIT_TOL=0.05ATR");
   EkinEkle("EURNOK", "MSS=IFVG_YETER YON=EKIN GIRIS=KENAR STOP=SWING_GOVDE TP=LIKIDITE SEVIYE=ICT ZAMAN=ICT_15_5 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=SART ESIT_TOL=0.05ATR");
   EkinEkle("JNJ", "MSS=IFVG_YETER YON=YOK GIRIS=KENAR STOP=SUPURULEN_UC TP=3R SEVIYE=EKIN ZAMAN=ICT_15_5 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=YOK ESIT_TOL=0.05ATR");
   EkinEkle("LTCUSD", "MSS=IFVG_YETER YON=YOK GIRIS=KENAR STOP=SUPURULEN_UC TP=LIKIDITE SEVIYE=ICT ZAMAN=EKIN_5_3 DISIPLIN=YOK EMIR=2_SAAT SHARP=SART ESIT_TOL=0.2ATR");
   EkinEkle("GRTUSD", "MSS=IFVG_YETER YON=EKIN GIRIS=KAPANIS STOP=SWING_GOVDE TP=2R SEVIYE=ICT ZAMAN=EKIN_5_3 DISIPLIN=EKIN EMIR=SEANS_SONU SHARP=YOK ESIT_TOL=0.05ATR");
   EkinEkle("LNKUSD", "MSS=SART YON=EKIN GIRIS=KENAR STOP=FVG_MUM TP=2R SEVIYE=EKIN ZAMAN=EKIN_5_3 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=YOK ESIT_TOL=0.05ATR");
   EkinEkle("GBPUSD", "MSS=SART YON=YOK GIRIS=ORTA STOP=SUPURULEN_UC TP=2R SEVIYE=EKIN ZAMAN=ICT_15_5 DISIPLIN=EKIN EMIR=SEANS_SONU SHARP=YOK ESIT_TOL=0.05ATR");
   EkinEkle("ASML", "MSS=IFVG_YETER YON=YOK GIRIS=ORTA STOP=FVG_MUM TP=2R SEVIYE=EKIN ZAMAN=EKIN_5_3 DISIPLIN=YOK EMIR=2_SAAT SHARP=YOK ESIT_TOL=0.05ATR");
   EkinEkle("AMD", "MSS=IFVG_YETER YON=EKIN GIRIS=KAPANIS STOP=SWING_GOVDE TP=3R SEVIYE=ICT ZAMAN=ICT_15_5 DISIPLIN=EKIN EMIR=SEANS_SONU SHARP=SART ESIT_TOL=0.05ATR");
   EkinEkle("GBPNZD", "MSS=SART YON=EKIN GIRIS=ORTA STOP=FVG_MUM TP=LIKIDITE SEVIYE=EKIN ZAMAN=EKIN_5_3 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=SART ESIT_TOL=0.05ATR");
   EkinEkle("USDCAD", "MSS=SART YON=EKIN GIRIS=ORTA STOP=FVG_MUM TP=LIKIDITE SEVIYE=ICT ZAMAN=ICT_15_5 DISIPLIN=YOK EMIR=2_SAAT SHARP=SART ESIT_TOL=0.2ATR");
   EkinEkle("USOIL.cash", "MSS=IFVG_YETER YON=EKIN GIRIS=KENAR STOP=SUPURULEN_UC TP=LIKIDITE SEVIYE=ICT ZAMAN=ICT_15_5 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=SART ESIT_TOL=0.1ATR");
   EkinEkle("EURAUD", "MSS=SART YON=YOK GIRIS=KENAR STOP=SUPURULEN_UC TP=LIKIDITE SEVIYE=ICT ZAMAN=ICT_15_5 DISIPLIN=YOK EMIR=2_SAAT SHARP=YOK ESIT_TOL=0.2ATR");
   EkinEkle("AUDCAD", "MSS=IFVG_YETER YON=ICT GIRIS=KENAR STOP=FVG_MUM TP=3R SEVIYE=EKIN ZAMAN=EKIN_5_3 DISIPLIN=EKIN EMIR=SEANS_SONU SHARP=YOK ESIT_TOL=0.05ATR");
   EkinEkle("CVX", "MSS=SART YON=EKIN GIRIS=KENAR STOP=FVG_MUM TP=3R SEVIYE=EKIN ZAMAN=EKIN_5_3 DISIPLIN=YOK EMIR=2_SAAT SHARP=SART ESIT_TOL=0.05ATR");
   EkinEkle("AZN", "MSS=SART YON=YOK GIRIS=ORTA STOP=FVG_MUM TP=3R SEVIYE=EKIN ZAMAN=EKIN_5_3 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=YOK ESIT_TOL=0.05ATR");
   EkinEkle("GME", "MSS=IFVG_YETER YON=EKIN GIRIS=KAPANIS STOP=FVG_MUM TP=LIKIDITE SEVIYE=EKIN ZAMAN=ICT_15_5 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=YOK ESIT_TOL=0.05ATR");
   EkinEkle("ETCUSD", "MSS=SART YON=YOK GIRIS=KENAR STOP=SUPURULEN_UC TP=2R SEVIYE=ICT ZAMAN=EKIN_5_3 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=YOK ESIT_TOL=0.2ATR");
   EkinEkle("USDMXN", "MSS=SART YON=EKIN GIRIS=KAPANIS STOP=SWING_GOVDE TP=LIKIDITE SEVIYE=EKIN ZAMAN=ICT_15_5 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=YOK ESIT_TOL=0.1ATR");
   EkinEkle("XAGEUR", "MSS=SART YON=YOK GIRIS=KENAR STOP=FVG_MUM TP=2R SEVIYE=EKIN ZAMAN=EKIN_5_3 DISIPLIN=YOK EMIR=2_SAAT SHARP=SART ESIT_TOL=0.05ATR");
   EkinEkle("AUDNZD", "MSS=IFVG_YETER YON=EKIN GIRIS=ORTA STOP=SWING_GOVDE TP=3R SEVIYE=ICT ZAMAN=ICT_15_5 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=SART ESIT_TOL=0.05ATR");
   EkinEkle("AAPL", "MSS=IFVG_YETER YON=ICT GIRIS=KAPANIS STOP=SUPURULEN_UC TP=2R SEVIYE=EKIN ZAMAN=EKIN_5_3 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=SART ESIT_TOL=0.05ATR");
   EkinEkle("UNIUSD", "MSS=IFVG_YETER YON=ICT GIRIS=KAPANIS STOP=FVG_MUM TP=2R SEVIYE=EKIN ZAMAN=ICT_15_5 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=YOK ESIT_TOL=0.2ATR");
   EkinEkle("ARM", "MSS=IFVG_YETER YON=EKIN GIRIS=KAPANIS STOP=SWING_GOVDE TP=3R SEVIYE=EKIN ZAMAN=ICT_15_5 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=YOK ESIT_TOL=0.05ATR");
   EkinEkle("ALVG", "MSS=SART YON=YOK GIRIS=KENAR STOP=SUPURULEN_UC TP=2R SEVIYE=EKIN ZAMAN=EKIN_5_3 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=YOK ESIT_TOL=0.05ATR");
   EkinEkle("SNOW", "MSS=IFVG_YETER YON=YOK GIRIS=ORTA STOP=SUPURULEN_UC TP=2R SEVIYE=ICT ZAMAN=ICT_15_5 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=YOK ESIT_TOL=0.05ATR");
   EkinEkle("NVDA", "MSS=IFVG_YETER YON=EKIN GIRIS=ORTA STOP=SUPURULEN_UC TP=LIKIDITE SEVIYE=EKIN ZAMAN=ICT_15_5 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=YOK ESIT_TOL=0.05ATR");
   EkinEkle("GBPAUD", "MSS=SART YON=YOK GIRIS=KAPANIS STOP=FVG_MUM TP=3R SEVIYE=EKIN ZAMAN=ICT_15_5 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=YOK ESIT_TOL=0.05ATR");
   EkinEkle("GE", "MSS=IFVG_YETER YON=EKIN GIRIS=KENAR STOP=SUPURULEN_UC TP=LIKIDITE SEVIYE=ICT ZAMAN=EKIN_5_3 DISIPLIN=YOK EMIR=2_SAAT SHARP=YOK ESIT_TOL=0.05ATR");
   EkinEkle("US2000.cash", "MSS=IFVG_YETER YON=YOK GIRIS=KAPANIS STOP=FVG_MUM TP=2R SEVIYE=ICT ZAMAN=ICT_15_5 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=SART ESIT_TOL=0.2ATR");
   EkinEkle("MSTR", "MSS=IFVG_YETER YON=YOK GIRIS=ORTA STOP=FVG_MUM TP=2R SEVIYE=EKIN ZAMAN=EKIN_5_3 DISIPLIN=EKIN EMIR=SEANS_SONU SHARP=SART ESIT_TOL=0.05ATR");
   EkinEkle("BTCUSD", "MSS=IFVG_YETER YON=EKIN GIRIS=ORTA STOP=SWING_GOVDE TP=3R SEVIYE=EKIN ZAMAN=ICT_15_5 DISIPLIN=YOK EMIR=2_SAAT SHARP=SART ESIT_TOL=0.2ATR");
   EkinEkle("AUDCHF", "MSS=SART YON=EKIN GIRIS=KAPANIS STOP=SUPURULEN_UC TP=2R SEVIYE=EKIN ZAMAN=EKIN_5_3 DISIPLIN=EKIN EMIR=SEANS_SONU SHARP=YOK ESIT_TOL=0.1ATR");
}

bool  BizimMagic(ulong m) { return(m / 100 == Sihir || m / 100 == Sihir + 1); }
bool  IctMagic(ulong m)   { return(m / 100 == Sihir + 1); }
int   KuralNo(ulong m)    { return((int)(m % 100)); }
ulong KuralMagic(int ki)  { return(Sihir * 100 + (ulong)ki); }
ulong EkMagic(int ei)     { return((Sihir + 1) * 100 + (ulong)ei); }
bool  GecerliKural(int ki){ return(ki >= 0 && ki < ArraySize(K)); }
bool  GecerliEk(int ei)   { return(ei >= 0 && ei < ArraySize(EK)); }

//--- magic -> sembol ve mantik (0 KESISIM, 1 ICT)
bool MagicBilgi(ulong mg, string &s, int &grup)
{
   s = ""; grup = -1;
   if(mg / 100 == Sihir)     { int ki = KuralNo(mg); if(!GecerliKural(ki)) return(false); s = K[ki].s;  grup = 0; return(true); }
   if(mg / 100 == Sihir + 1) { int ei = KuralNo(mg); if(!GecerliEk(ei))    return(false); s = EK[ei].s; grup = 1; return(true); }
   return(false);
}

string GrupAd(int g) { return(g == 1 ? "ICT" : "KESİŞİM"); }

//+------------------------------------------------------------------+
//  ZAMAN
//+------------------------------------------------------------------+
datetime SunucuSimdi()
{
   if(MQLInfoInteger(MQL_TESTER)) return(TimeCurrent());
   return(TimeTradeServer());
}

long NyDk(datetime sunucu) { return((long)sunucu / 60 - (long)SunucuNY * 60); }
datetime SunucuZaman(long nyDk) { return((datetime)((nyDk + (long)SunucuNY * 60) * 60)); }

datetime SonPazar(int yil, int ay)
{
   MqlDateTime z;
   z.year = yil; z.mon = ay + 1; z.day = 1; z.hour = 0; z.min = 0; z.sec = 0;
   if(z.mon == 13) { z.mon = 1; z.year = yil + 1; }
   datetime sonGun = StructToTime(z) - 86400;
   MqlDateTime w;
   TimeToStruct(sonGun, w);
   return(sonGun - w.day_of_week * 86400);
}

bool AvrupaYazSaati(datetime gmt)
{
   MqlDateTime z;
   TimeToStruct(gmt, z);
   datetime bas = SonPazar(z.year, 3) + 3600;
   datetime bit = SonPazar(z.year, 10) + 3600;
   return(gmt >= bas && gmt < bit);
}

datetime PragSimdi()
{
   if(MQLInfoInteger(MQL_TESTER))
      return(TimeCurrent() - TestSunucuPragFarki * 3600);
   datetime g = TimeGMT();
   return(g + (AvrupaYazSaati(g) ? 2 : 1) * 3600);
}

//--- sunucu zamani -> Turkiye saati (GMT+3)
datetime TrZaman(datetime sunucu)
{
   long fark = (long)TimeTradeServer() - (long)TimeGMT();
   fark = (long)MathRound(fark / 1800.0) * 1800;
   return((datetime)((long)sunucu - fark + 3 * 3600));
}

string TrYaz(datetime sunucu) { return(TimeToString(TrZaman(sunucu), TIME_DATE | TIME_MINUTES) + " (TR)"); }

int PragGunKey(datetime &pragBas)
{
   datetime prag = PragSimdi();
   MqlDateTime pz;
   TimeToStruct(prag, pz);
   pragBas = SunucuSimdi() - (pz.hour * 3600 + pz.min * 60 + pz.sec);
   return(pz.year * 10000 + pz.mon * 100 + pz.day);
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
   //--- 3800 karakterden uzunsa satir satir bolunur
   string satirlar[];
   int n = StringSplit(metin, '\n', satirlar);
   string parca = "";
   for(int i = 0; i < n; i++)
   {
      if(StringLen(parca) + StringLen(satirlar[i]) + 1 > 3800 && StringLen(parca) > 0)
      {
         int k = ArraySize(KUYRUK); ArrayResize(KUYRUK, k + 1); KUYRUK[k] = parca;
         parca = "";
      }
      parca += (StringLen(parca) > 0 ? "\n" : "") + satirlar[i];
   }
   if(StringLen(parca) > 0) { int k = ArraySize(KUYRUK); ArrayResize(KUYRUK, k + 1); KUYRUK[k] = parca; }
   if(ArraySize(KUYRUK) > 60)                        // takilirsa en eskiler atilir
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
      tgDurum = "WebRequest izni yok: Araclar > Secenekler > Uzman Danismanlar > https://api.telegram.org";
   else
      tgDurum = StringFormat("hata (kod %d, %d) %s", kod, hata, CharArrayToString(sonuc, 0, WHOLE_ARRAY, CP_UTF8));
   Print("Telegram gonderilemedi: ", tgDurum);
   if(kod == 400 || kod == 401 || kod == 404)       // mesaj/token hatali: bu mesaj atlanir
   {
      for(int i = 1; i < ArraySize(KUYRUK); i++) KUYRUK[i - 1] = KUYRUK[i];
      ArrayResize(KUYRUK, ArraySize(KUYRUK) - 1);
   }
   tgBekle = TimeLocal() + 30;
}

//+------------------------------------------------------------------+
//  GOSTERGELER (testteki hesaplarin aynisi)
//+------------------------------------------------------------------+
void Ema(const MqlRates &r[], int n, int p, double &e[])
{
   ArrayResize(e, n);
   double a = 2.0 / (p + 1.0);
   e[0] = r[0].close;
   for(int i = 1; i < n; i++) e[i] = a * r[i].close + (1.0 - a) * e[i - 1];
}

void Gostergeler(const MqlRates &r[], int n, double &atr[], double &atr100[], double &rsi[])
{
   ArrayResize(atr, n); ArrayResize(atr100, n); ArrayResize(rsi, n);
   double tr[];
   ArrayResize(tr, n);
   tr[0] = r[0].high - r[0].low;
   for(int i = 1; i < n; i++)
      tr[i] = MathMax(r[i].high - r[i].low, MathMax(MathAbs(r[i].high - r[i - 1].close), MathAbs(r[i].low - r[i - 1].close)));
   //--- ATR(14) = son 14 TR'nin basit ortalamasi
   double top = 0.0;
   for(int i = 0; i < n; i++)
   {
      top += tr[i];
      if(i >= 14) top -= tr[i - 14];
      atr[i] = (i >= 13) ? top / 14.0 : 0.0;
   }
   //--- ATR'nin son 100 degerinin ortalamasi
   double top2 = 0.0;
   for(int i = 0; i < n; i++)
   {
      atr100[i] = 0.0;
      if(i < 13) continue;
      top2 += atr[i];
      if(i >= 113) top2 -= atr[i - 100];
      if(i >= 112) atr100[i] = top2 / 100.0;
   }
   //--- RSI(14), Wilder (alfa 1/14)
   double al = 1.0 / 14.0, up = 0.0, dn = 0.0;
   for(int i = 0; i < n; i++)
   {
      double d = (i == 0) ? 0.0 : r[i].close - r[i - 1].close;
      up = (i == 0) ? MathMax(d, 0.0) : (1.0 - al) * up + al * MathMax(d, 0.0);
      dn = (i == 0) ? MathMax(-d, 0.0) : (1.0 - al) * dn + al * MathMax(-d, 0.0);
      rsi[i] = (dn == 0.0) ? 50.0 : 100.0 - 100.0 / (1.0 + up / dn);
   }
}

//--- kapanan mum k icin sinyal: +1 AL, -1 SAT, 0 yok
int Sinyal(int ki, const MqlRates &r[], int n, const double &atr[], const double &atr100[], const double &rsi[])
{
   int k = n - 2;
   if(k < 250 || atr[k] <= 0.0) return(0);
   int tip = K[ki].tip;
   if(tip == K_SAAT)
   {
      long kapanis = NyDk(r[k].time) + 60;                // mumun kapanis ani (NY)
      int sa = (int)((kapanis % 1440) / 60);
      bool ic = (K[ki].a < K[ki].b) ? (sa >= K[ki].a && sa < K[ki].b) : (sa >= K[ki].a || sa < K[ki].b);
      return(ic ? K[ki].yon : 0);
   }
   if(tip == K_RSI)
      return((rsi[k] >= K[ki].a && rsi[k] < K[ki].b) ? K[ki].yon : 0);
   if(tip == K_SAKIN)
      return((atr100[k] > 0.0 && atr[k] / atr100[k] < 0.8) ? K[ki].yon : 0);
   if(tip == K_EMA)
   {
      double eh[], ey[], ef[];
      Ema(r, n, K[ki].a, eh);
      Ema(r, n, K[ki].b, ey);
      double fark = eh[k] - ey[k], once = eh[k - 1] - ey[k - 1];
      bool yukari = (fark > 0.0 && once <= 0.0);
      bool asagi  = (fark < 0.0 && once >= 0.0);
      if(!yukari && !asagi) return(0);
      if(K[ki].f > 0)
      {
         Ema(r, n, K[ki].f, ef);
         if(yukari && !(r[k].close > ef[k])) return(0);
         if(asagi  && !(r[k].close < ef[k])) return(0);
      }
      return(yukari ? 1 : -1);
   }
   return(0);
}

//+------------------------------------------------------------------+
//  ISLEM YARDIMCILARI
//+------------------------------------------------------------------+
double Yuvarla(string s, double p)
{
   double tick = SymbolInfoDouble(s, SYMBOL_TRADE_TICK_SIZE);
   int bas = (int)SymbolInfoInteger(s, SYMBOL_DIGITS);
   if(tick > 0.0) p = MathRound(p / tick) * tick;
   return(NormalizeDouble(p, bas));
}

//--- lot ve o lotta stop zarari
double LotBul(string s, bool al, double giris, double stop, double &zarar)
{
   zarar = 0.0;
   double kar = 0.0;
   if(!OrderCalcProfit(al ? ORDER_TYPE_BUY : ORDER_TYPE_SELL, s, 1.0, giris, stop, kar)) return(0.0);
   double kayip1 = -kar;
   if(kayip1 <= 0.0) return(0.0);
   double adim  = SymbolInfoDouble(s, SYMBOL_VOLUME_STEP);
   double enAz  = SymbolInfoDouble(s, SYMBOL_VOLUME_MIN);
   double enUst = SymbolInfoDouble(s, SYMBOL_VOLUME_MAX);
   if(adim <= 0.0) adim = 0.01;
   double lot = MathFloor(RiskDolar / kayip1 / adim + 1e-9) * adim;
   if(lot < enAz) lot = enAz;                         // yetmiyorsa en kucuk lot
   if(enUst > 0.0 && lot > enUst) lot = enUst;
   int basamak = 0;
   double x = adim;
   while(basamak < 8 && MathAbs(x - MathRound(x)) > 1e-9) { x *= 10.0; basamak++; }
   lot = NormalizeDouble(lot, basamak);
   zarar = lot * kayip1;
   return(lot);
}

bool KuralAcik(ulong mg)
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong t = PositionGetTicket(i);
      if(t == 0) continue;
      if((ulong)PositionGetInteger(POSITION_MAGIC) == mg) return(true);
   }
   return(false);
}

//--- ayni kural ayni yonde son TekrarDakika icinde islem acildi mi
bool YakindaAcildi(ulong mg, int yon)
{
   datetime simdi = SunucuSimdi();
   if(!HistorySelect(simdi - (TekrarDakika + 2) * 60, simdi + 3600)) return(false);
   int n = HistoryDealsTotal();
   for(int i = 0; i < n; i++)
   {
      ulong t = HistoryDealGetTicket(i);
      if(t == 0) continue;
      if((ulong)HistoryDealGetInteger(t, DEAL_MAGIC) != mg) continue;
      if(HistoryDealGetInteger(t, DEAL_ENTRY) != DEAL_ENTRY_IN) continue;
      long tip = HistoryDealGetInteger(t, DEAL_TYPE);
      if(yon > 0 && tip != DEAL_TYPE_BUY) continue;
      if(yon < 0 && tip != DEAL_TYPE_SELL) continue;
      if((datetime)HistoryDealGetInteger(t, DEAL_TIME) >= simdi - TekrarDakika * 60) return(true);
   }
   return(false);
}

//--- deger: mutlak=false ise stop mesafesi (fiyat), mutlak=true ise stop fiyati
bool IslemAc(int ki, int yon, double deger, bool mutlak)
{
   string s = K[ki].s;
   if(limitDurdu) return(false);
   if(!TerminalInfoInteger(TERMINAL_TRADE_ALLOWED) || !MQLInfoInteger(MQL_TRADE_ALLOWED)) return(false);
   long mod = SymbolInfoInteger(s, SYMBOL_TRADE_MODE);
   if(!(mod == SYMBOL_TRADE_MODE_FULL || (yon > 0 && mod == SYMBOL_TRADE_MODE_LONGONLY) ||
        (yon < 0 && mod == SYMBOL_TRADE_MODE_SHORTONLY)))
   { PrintFormat("%s islem acilamadi: sembolde islem kapali", s); return(false); }
   ulong mg = KuralMagic(ki);
   if(KuralAcik(mg)) return(false);
   if(YakindaAcildi(mg, yon))
   { PrintFormat("%s islem acilmadi: ayni kural ayni yonde son %d dk icinde acildi", s, TekrarDakika); return(false); }
   double bid = SymbolInfoDouble(s, SYMBOL_BID);
   double ask = SymbolInfoDouble(s, SYMBOL_ASK);
   if(bid <= 0.0 || ask <= 0.0) return(false);
   double e = (yon > 0) ? ask : bid;
   double mes, sl, tp;
   if(mutlak)
   {
      sl = deger;
      if((yon > 0 && sl >= e) || (yon < 0 && sl <= e))
      { PrintFormat("%s islem acilmadi: fiyat stop seviyesini gecmis", s); return(false); }
      mes = MathAbs(e - sl);
   }
   else
   {
      mes = deger;
      sl = e - yon * mes;
   }
   tp = e + yon * 2.0 * mes;
   sl = Yuvarla(s, sl);
   tp = Yuvarla(s, tp);
   double nokta = SymbolInfoDouble(s, SYMBOL_POINT);
   long seviye = SymbolInfoInteger(s, SYMBOL_TRADE_STOPS_LEVEL);
   if(mes <= 0.0 || mes < seviye * nokta)
   { PrintFormat("%s islem acilmadi: stop mesafesi cok kucuk", s); return(false); }
   double zarar = 0.0;
   double lot = LotBul(s, yon > 0, e, sl, zarar);
   if(lot <= 0.0) { PrintFormat("%s islem acilmadi: lot hesaplanamadi", s); return(false); }
   if(zarar > EnFazlaZarar + 1e-9)
   { PrintFormat("%s islem acilmadi: en kucuk lotta (%.2f) stop zarari %.2f $ > %.2f $", s, lot, zarar, EnFazlaZarar); return(false); }
   double makas = 0.0;
   if(!OrderCalcProfit(ORDER_TYPE_BUY, s, lot, bid, ask, makas)) makas = 0.0;
   if(makas > MakasSinir + 1e-9)
   { PrintFormat("%s islem acilmadi: spread maliyeti %.2f $ > %.2f $", s, makas, MakasSinir); return(false); }

   trade.SetExpertMagicNumber(mg);
   trade.SetDeviationInPoints(Kayma);
   trade.SetTypeFillingBySymbol(s);
   string yorum = "EAR" + IntegerToString(ki);
   bool ok = (yon > 0) ? trade.Buy(lot, s, 0.0, sl, tp, yorum) : trade.Sell(lot, s, 0.0, sl, tp, yorum);
   uint rc = trade.ResultRetcode();
   int dg = (int)SymbolInfoInteger(s, SYMBOL_DIGITS);
   if(ok && (rc == TRADE_RETCODE_DONE || rc == TRADE_RETCODE_PLACED || rc == TRADE_RETCODE_DONE_PARTIAL))
   {
      PrintFormat("%s %s acildi  lot %s  stop %s  TP %s  zarar %.2f $  spread %.2f $  [%s]", s, yon > 0 ? "ALIS" : "SATIS",
                  DoubleToString(lot, 2), DoubleToString(sl, dg), DoubleToString(tp, dg), zarar, makas, K[ki].ad);
      return(true);
   }
   PrintFormat("%s %s acilamadi: %u %s", s, yon > 0 ? "ALIS" : "SATIS", rc, trade.ResultRetcodeDescription());
   return(false);
}

void NedenYaz(ulong pid, string neden)
{
   int n = ArraySize(NPID);
   ArrayResize(NPID, n + 1); ArrayResize(NSTR, n + 1);
   NPID[n] = pid; NSTR[n] = neden;
}

string NedenBul(ulong pid)
{
   for(int i = ArraySize(NPID) - 1; i >= 0; i--) if(NPID[i] == pid) return(NSTR[i]);
   return("");
}

ulong    KDTK[]; datetime KDZ[];                    // kapatma denemeleri (basarisizsa dakikada bir tekrar)

void Kapat(ulong ticket, string neden)
{
   if(!PositionSelectByTicket(ticket)) return;
   datetime simdiK = SunucuSimdi();
   int kd = -1;
   for(int i = 0; i < ArraySize(KDTK); i++) if(KDTK[i] == ticket) { kd = i; break; }
   if(kd >= 0 && (long)simdiK - (long)KDZ[kd] < 60) return;
   if(kd < 0) { kd = ArraySize(KDTK); ArrayResize(KDTK, kd + 1); ArrayResize(KDZ, kd + 1); KDTK[kd] = ticket; }
   KDZ[kd] = simdiK;
   string s = PositionGetString(POSITION_SYMBOL);
   NedenYaz((ulong)PositionGetInteger(POSITION_IDENTIFIER), neden);
   trade.SetExpertMagicNumber((ulong)PositionGetInteger(POSITION_MAGIC));
   trade.SetDeviationInPoints(Kayma);
   trade.SetTypeFillingBySymbol(s);
   if(trade.PositionClose(ticket, Kayma)) PrintFormat("%s kapatildi (%s)", s, neden);
   else PrintFormat("%s kapatilamadi (%s): %u", s, neden, trade.ResultRetcode());
}

string GvAd(string on, ulong x) { return("EAR_" + on + "_" + IntegerToString((long)x)); }

bool EmirSil(ulong ticket, string neden)
{
   if(!OrderSelect(ticket)) return(false);
   string s = OrderGetString(ORDER_SYMBOL);
   trade.SetExpertMagicNumber((ulong)OrderGetInteger(ORDER_MAGIC));
   if(trade.OrderDelete(ticket))
   {
      PrintFormat("%s ICT emri silindi (%s)", s, neden);
      GlobalVariableDel(GvAd("EX", ticket));
      GlobalVariableDel(GvAd("ET", ticket));
      return(true);
   }
   PrintFormat("%s ICT emri silinemedi (%s): %u", s, neden, trade.ResultRetcode());
   return(false);
}

void KendiniKapat(string neden)
{
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong t = PositionGetTicket(i);
      if(t == 0) continue;
      if(BizimMagic((ulong)PositionGetInteger(POSITION_MAGIC))) Kapat(t, neden);
   }
   for(int i = OrdersTotal() - 1; i >= 0; i--)
   {
      ulong t = OrderGetTicket(i);
      if(t == 0) continue;
      if(IctMagic((ulong)OrderGetInteger(ORDER_MAGIC))) EmirSil(t, neden);
   }
}

//--- sembolun su anki islem seansinin bitisi (sunucu saniyesi); seans disindaysa 0
long SeansSonu(string s, datetime t)
{
   MqlDateTime z;
   TimeToStruct(t, z);
   long gun0 = (long)t - (z.hour * 3600 + z.min * 60 + z.sec);
   long sn = (long)t - gun0;
   datetime a, b;
   for(int i = 0; i < 10; i++)
   {
      if(!SymbolInfoSessionTrade(s, (ENUM_DAY_OF_WEEK)z.day_of_week, i, a, b)) break;
      long A = (long)a % 86400, B = (long)b;
      if(B <= A) B = 86400;
      if(B > 86400) B = 86400;
      if(sn >= A && sn < B) return(gun0 + B);
   }
   return(0);
}

//--- KESISIM: 5 gun (Asya kirilimi NY 16:00) | ICT: NY 16:00 kapanisi
void SureKontrol()
{
   datetime simdi = SunucuSimdi();
   long ny = NyDk(simdi);
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong t = PositionGetTicket(i);
      if(t == 0) continue;
      ulong mg = (ulong)PositionGetInteger(POSITION_MAGIC);
      if(!BizimMagic(mg)) continue;
      datetime ac = (datetime)PositionGetInteger(POSITION_TIME);
      if(IctMagic(mg))
      {
         //--- islemin acildigi sunucu gununun 23:00'u (NY 16:00): son acik dakikada kapatilir
         //    (22:59:30; sembolun islem seansi daha once bitiyorsa seans bitisinden 30 sn once)
         long gun = ((long)ac / 60) / 1440;
         long kap = (gun * 1440 + NY_KAPANIS - 1) * 60 + 30;
         long ss = SeansSonu(PositionGetString(POSITION_SYMBOL), simdi);
         if(ss > 0 && ss - 30 < kap && ss > gun * 86400) kap = ss - 30;
         if((long)simdi >= kap) Kapat(t, "NY 16:00 kapanış");
         continue;
      }
      int ki = KuralNo(mg);
      if(!GecerliKural(ki)) continue;
      if(K[ki].tip == K_ASYA)
      {
         long gun = NyDk(ac) / 1440;
         if(ny >= gun * 1440 + 960) Kapat(t, "NY 16:00 kapanış");
      }
      else if((long)simdi - (long)ac >= SURE_SN) Kapat(t, "5 gün doldu");
   }
}

//+------------------------------------------------------------------+
//  1 SAATLIK KURALLAR: her sembolde yeni 1 saatlik mum acilinca
//+------------------------------------------------------------------+
void SembolDegerlendir(int si)
{
   string s = SEM[si];
   datetime t0 = iTime(s, PERIOD_H1, 0);
   if(t0 == 0) return;
   if(!HAZIR[si]) { SONBAR[si] = t0; HAZIR[si] = true; return; }   // acilistaki mum atlanir
   if(t0 <= SONBAR[si]) return;
   bool var = false;
   for(int ki = 0; ki < ArraySize(K); ki++)
      if(K[ki].aktif && K[ki].s == s && K[ki].tip != K_ASYA) { var = true; break; }
   if(!var) { SONBAR[si] = t0; return; }

   MqlRates r[];
   ArraySetAsSeries(r, false);
   int n = CopyRates(s, PERIOD_H1, 0, 1500, r);
   if(n < 300) return;                                  // veri yuklenmedi, sonra tekrar
   if(r[n - 1].time != t0) return;
   SONBAR[si] = t0;
   double atr[], atr100[], rsi[];
   Gostergeler(r, n, atr, atr100, rsi);
   int k = n - 2;
   for(int ki = 0; ki < ArraySize(K); ki++)
   {
      if(!K[ki].aktif || K[ki].s != s || K[ki].tip == K_ASYA) continue;
      int yon = Sinyal(ki, r, n, atr, atr100, rsi);
      if(yon == 0) continue;
      IslemAc(ki, yon, K[ki].sk * atr[k], false);
   }
}

//+------------------------------------------------------------------+
//  XAUUSD ASYA ARALIGI KIRILIMI (her saniye)
//+------------------------------------------------------------------+
bool BugunAcildi(ulong mg, long gun)
{
   datetime bas = SunucuZaman(gun * 1440);
   if(!HistorySelect(bas - 3600, SunucuSimdi() + 3600)) return(false);
   int n = HistoryDealsTotal();
   for(int i = 0; i < n; i++)
   {
      ulong t = HistoryDealGetTicket(i);
      if(t == 0) continue;
      if((ulong)HistoryDealGetInteger(t, DEAL_MAGIC) != mg) continue;
      if(HistoryDealGetInteger(t, DEAL_ENTRY) != DEAL_ENTRY_IN) continue;
      if(NyDk((datetime)HistoryDealGetInteger(t, DEAL_TIME)) / 1440 == gun) return(true);
   }
   return(false);
}

void AsyaKontrol()
{
   if(asyaKi < 0 || !K[asyaKi].aktif) return;
   string s = K[asyaKi].s;
   ulong mg = KuralMagic(asyaKi);
   long ny = NyDk(SunucuSimdi());
   long gun = ny / 1440, dk = ny % 1440;
   if(dk < 60 || dk >= 660) return;                     // giris sadece NY 01:00-11:00
   if(gun != asyaGun)
   {
      asyaGun = gun; asyaBitti = true; asyaUst = 0.0; asyaAlt = 0.0;
      MqlRates r[];
      ArraySetAsSeries(r, false);
      int n = CopyRates(s, PERIOD_M1, SunucuZaman(gun * 1440 - 360), SunucuZaman(gun * 1440 + 60) - 1, r);
      if(n < 60) { asyaGun = -1; return; }              // veri yok, sonra tekrar
      double ust = r[0].high, alt = r[0].low;
      for(int i = 1; i < n; i++) { ust = MathMax(ust, r[i].high); alt = MathMin(alt, r[i].low); }
      if(!(ust > alt)) return;
      asyaUst = ust; asyaAlt = alt;
      if(BugunAcildi(mg, gun) || KuralAcik(mg)) return;
      //--- robot gec acildiysa: 01:00'dan bu dakikaya kadar kirilim olduysa o gun islem yok
      MqlRates m[];
      ArraySetAsSeries(m, false);
      int nm = CopyRates(s, PERIOD_M1, SunucuZaman(gun * 1440 + 60), SunucuZaman(ny) - 1, m);
      for(int i = 0; i < nm; i++)
         if(m[i].high >= asyaUst || m[i].low <= asyaAlt) return;
      asyaBitti = false;
      PrintFormat("XAUUSD Asya araligi: tepe %.2f  dip %.2f", asyaUst, asyaAlt);
   }
   if(asyaBitti) return;
   double bid = SymbolInfoDouble(s, SYMBOL_BID);
   if(bid <= 0.0) return;
   double mh = iHigh(s, PERIOD_M1, 0), ml = iLow(s, PERIOD_M1, 0);
   bool ust = (bid >= asyaUst) || (mh > 0.0 && mh >= asyaUst);
   bool alt = (bid <= asyaAlt) || (ml > 0.0 && ml <= asyaAlt);
   if(!ust && !alt) return;
   asyaBitti = true;                                    // gunde sadece ilk kirilim
   if(ust && alt) { Print("XAUUSD: ayni dakikada iki taraf kirildi - bugun islem yok"); return; }
   if(ust) IslemAc(asyaKi, 1, asyaAlt, true);
   else    IslemAc(asyaKi, -1, asyaUst, true);
}

//+------------------------------------------------------------------+
//  GUNLUK LIMIT + PANEL
//+------------------------------------------------------------------+
void Yazi(string ad, string metin, int y, int boy)
{
   string n = ON_EK + ad;
   if(ObjectFind(0, n) < 0)
   {
      ObjectCreate(0, n, OBJ_LABEL, 0, 0, 0);
      ObjectSetInteger(0, n, OBJPROP_CORNER, CORNER_LEFT_UPPER);
      ObjectSetInteger(0, n, OBJPROP_ANCHOR, ANCHOR_LEFT_UPPER);
      ObjectSetInteger(0, n, OBJPROP_XDISTANCE, 15);
      ObjectSetInteger(0, n, OBJPROP_COLOR, clrBlack);
      ObjectSetString(0, n, OBJPROP_FONT, "Arial Bold");
      ObjectSetInteger(0, n, OBJPROP_SELECTABLE, false);
      ObjectSetInteger(0, n, OBJPROP_HIDDEN, true);
   }
   ObjectSetInteger(0, n, OBJPROP_YDISTANCE, y);
   ObjectSetInteger(0, n, OBJPROP_FONTSIZE, boy);
   ObjectSetString(0, n, OBJPROP_TEXT, metin);
}

//+------------------------------------------------------------------+
//  ICT MODULU  (ekin_142_test_3ay.py: Sembol.seviyeler / kurulum / sonuclar / gecis ile ayni)
//  SATIS gercek fiyatla, ALIS aynada (O,H,L,C -> -O,-L,-H,-C) hesaplanir.
//+------------------------------------------------------------------+
double HM(int y, int i) { return(y < 0 ? gH[i] : -gL[i]); }
double LM(int y, int i) { return(y < 0 ? gL[i] : -gH[i]); }
double OM(int y, int i) { return(y < 0 ? gO[i] : -gO[i]); }
double CM(int y, int i) { return(y < 0 ? gC[i] : -gC[i]); }
double Ayna(int y, double p) { return(y < 0 ? p : -p); }

//--- 1 dk dizisinde ilk gT >= t (searchsorted left)
int IX(long t)
{
   int a = 0, b = gN;
   while(a < b) { int m = (a + b) / 2; if(gT[m] < t) a = m + 1; else b = m; }
   return(a);
}

//--- searchsorted side="right"
int UstSinir(const long &arr[], int n, long t)
{
   int a = 0, b = n;
   while(a < b) { int m = (a + b) / 2; if(arr[m] <= t) a = m + 1; else b = m; }
   return(a);
}

//--- searchsorted side="left"
int AltSinir(const long &arr[], int n, long t)
{
   int a = 0, b = n;
   while(a < b) { int m = (a + b) / 2; if(arr[m] < t) a = m + 1; else b = m; }
   return(a);
}

//--- [basDk, bitDk) arasi 1 dk mumlar (sunucu dakikasi); spread fiyat cinsinden
bool M1Yukle(string s, long basDk, long bitDk)
{
   gN = 0; gST = false;
   if(bitDk <= basDk) return(false);
   MqlRates r[];
   ArraySetAsSeries(r, false);
   int n = CopyRates(s, PERIOD_M1, (datetime)(basDk * 60), (datetime)(bitDk * 60 - 1), r);
   if(n <= 0) return(false);
   double pt = SymbolInfoDouble(s, SYMBOL_POINT);
   ArrayResize(gT, n); ArrayResize(gO, n); ArrayResize(gH, n); ArrayResize(gL, n); ArrayResize(gC, n); ArrayResize(gS, n);
   int k = 0;
   for(int i = 0; i < n; i++)
   {
      long t = (long)r[i].time / 60;
      if(t < basDk || t >= bitDk) continue;
      if(k > 0 && t <= gT[k - 1]) continue;
      gT[k] = t; gO[k] = r[i].open; gH[k] = r[i].high; gL[k] = r[i].low; gC[k] = r[i].close;
      gS[k] = (double)r[i].spread * pt;
      k++;
   }
   gN = k;
   return(gN > 0);
}

//--- aralik en buyuk / en kucuk icin seyrek tablo (hazirlikta, uzun gecmis icin)
void SeyrekKur()
{
   int n = gN;
   STNn = n;
   int kat = 1;
   while((1 << kat) <= n) kat++;
   ArrayResize(STX, kat * n); ArrayResize(STN, kat * n);
   for(int i = 0; i < n; i++) { STX[i] = gH[i]; STN[i] = gL[i]; }
   for(int k = 1; k < kat; k++)
   {
      int h = 1 << (k - 1), u = 1 << k;
      for(int i = 0; i + u <= n; i++)
      {
         STX[k * n + i] = MathMax(STX[(k - 1) * n + i], STX[(k - 1) * n + i + h]);
         STN[k * n + i] = MathMin(STN[(k - 1) * n + i], STN[(k - 1) * n + i + h]);
      }
   }
   ArrayResize(LG, n + 1);
   LG[0] = 0;
   if(n >= 1) LG[1] = 0;
   for(int i = 2; i <= n; i++) LG[i] = LG[i / 2] + 1;
   gST = true;
}

//--- ayna yuksek: [a, b) en buyugu (bossa -BOS)
double MxHm(int y, int a, int b)
{
   if(b <= a) return(-BOS);
   if(gST)
   {
      int k = LG[b - a];
      if(y < 0) return(MathMax(STX[k * STNn + a], STX[k * STNn + b - (1 << k)]));
      return(-MathMin(STN[k * STNn + a], STN[k * STNn + b - (1 << k)]));
   }
   double m = -BOS;
   for(int i = a; i < b; i++) { double v = HM(y, i); if(v > m) m = v; }
   return(m);
}

//--- ayna dusuk: [a, b) en kucugu (bossa +BOS)
double MnLm(int y, int a, int b)
{
   if(b <= a) return(BOS);
   if(gST)
   {
      int k = LG[b - a];
      if(y < 0) return(MathMin(STN[k * STNn + a], STN[k * STNn + b - (1 << k)]));
      return(-MathMax(STX[k * STNn + a], STX[k * STNn + b - (1 << k)]));
   }
   double m = BOS;
   for(int i = a; i < b; i++) { double v = LM(y, i); if(v < m) m = v; }
   return(m);
}

//--- K dakikalik ayna mumlar (gT < sinir); Python mumlar() ile ayni (T // K gruplama)
int Agg(int y, int K, long sinir, long &bt[], double &bo[], double &bh[], double &bl[], double &bc[])
{
   int n = 0;
   int yer = gN / K + 16;
   ArrayResize(bt, 0, yer); ArrayResize(bo, 0, yer); ArrayResize(bh, 0, yer); ArrayResize(bl, 0, yer); ArrayResize(bc, 0, yer);
   long cur = -1;
   for(int i = 0; i < gN; i++)
   {
      if(gT[i] >= sinir) break;
      long k = gT[i] / K;
      double h = HM(y, i), l = LM(y, i), c = CM(y, i);
      if(n == 0 || k != cur)
      {
         cur = k;
         n++;
         ArrayResize(bt, n, yer); ArrayResize(bo, n, yer); ArrayResize(bh, n, yer); ArrayResize(bl, n, yer); ArrayResize(bc, n, yer);
         bt[n - 1] = k * K; bo[n - 1] = OM(y, i); bh[n - 1] = h; bl[n - 1] = l; bc[n - 1] = c;
      }
      else
      {
         if(h > bh[n - 1]) bh[n - 1] = h;
         if(l < bl[n - 1]) bl[n - 1] = l;
         bc[n - 1] = c;
      }
   }
   return(n);
}

//--- ATR: TR'nin 14 mumluk ortalamasi (min_periods=1), ilk TR icin onceki kapanis = c[0]
void Atr(const double &h[], const double &l[], const double &c[], int n, double &at[])
{
   ArrayResize(at, n);
   double tr[];
   ArrayResize(tr, n);
   for(int i = 0; i < n; i++)
   {
      double pc = (i == 0) ? c[0] : c[i - 1];
      tr[i] = MathMax(h[i] - l[i], MathMax(MathAbs(h[i] - pc), MathAbs(l[i] - pc)));
      int bas = MathMax(0, i - 13);
      double top = 0.0;
      for(int j = bas; j <= i; j++) top += tr[j];
      at[i] = top / (double)(i - bas + 1);
   }
}

//--- son swing dip (3 mum): sw[j] = j-1'e kadar olan son swing dip (yoksa -1)
void SonSw(const double &bl[], int n, int &sw[])
{
   ArrayResize(sw, n);
   int son = -1;
   for(int j = 0; j < n; j++)
   {
      sw[j] = son;
      if(j >= 1 && j <= n - 2 && bl[j] < bl[j - 1] && bl[j] < bl[j + 1]) son = j;
   }
}

bool SetteVar(int sev, int ad)
{
   if(sev == 0) return(ad == AD_PDH || ad == AD_PWH || ad == AD_ASYA || ad == AD_LONDRA || ad == AD_NYPM ||
                       ad == AD_ESIT || ad == AD_FVG1 || ad == AD_FVG4);
   return(ad == AD_PDH || ad == AD_ESIT || ad == AD_FVG1 || ad == AD_FVG4 || ad == AD_FVGG);
}

void SevEkle(CEk *e, int y, double p, int tip)
{
   int n = ArraySize(e.lvY);
   ArrayResize(e.lvY, n + 1, 256); ArrayResize(e.lvP, n + 1, 256); ArrayResize(e.lvTip, n + 1, 256);
   e.lvY[n] = y; e.lvP[n] = p; e.lvTip[n] = tip;
}

void KarsiEkle(CEk *e, int y, double p)
{
   int n = ArraySize(e.kY);
   ArrayResize(e.kY, n + 1, 256); ArrayResize(e.kP, n + 1, 256);
   e.kY[n] = y; e.kP[n] = p;
}

//--- hesaplanan seviye (PDH, PWH, ASYA, LONDRA, NY_PM): [bitis, ks) icinde alinmamissa
void HesapSeviye(CEk *e, int y, int ad, double fiyat, bool sonlu, long bitis, long ks, int iks)
{
   if(!SetteVar(e.sev, ad)) return;
   if(!sonlu || bitis > ks) return;
   if(MxHm(y, IX(bitis), iks) > fiyat) return;
   SevEkle(e, y, fiyat, 0);
}

//--- hesaplanan karsi likidite (PDL, PWL, Asya / Londra / NY PM dibi)
void HesapKarsi(CEk *e, int y, double fiyat, bool sonlu, long bitis, long ks, int iks)
{
   if(sonlu && bitis <= ks && MnLm(y, IX(bitis), iks) >= fiyat) KarsiEkle(e, y, fiyat);
}

//--- esit tepeler (1S / 4S): alinmamis (ks dakikasi dahil)
void EsitTepe(CEk *e, int y, int K, const long &bt[], const double &bh[], const double &bl[], const double &bc[], int n,
              long ks, int iks1)
{
   if(n < 3) return;
   double at[];
   Atr(bh, bl, bc, n, at);
   long tT0[], tO[];
   double tP[], tA[];
   int nt = 0;
   for(int i = 1; i < n - 1; i++)
   {
      if(!(bh[i] > bh[i - 1] && bh[i] > bh[i + 1])) continue;
      nt++;
      ArrayResize(tT0, nt, 512); ArrayResize(tO, nt, 512); ArrayResize(tP, nt, 512); ArrayResize(tA, nt, 512);
      tT0[nt - 1] = bt[i + 1] + K; tO[nt - 1] = bt[i]; tP[nt - 1] = bh[i]; tA[nt - 1] = at[i];
   }
   for(int b = 1; b < nt; b++)
   {
      if(tT0[b] > ks) continue;
      int ib = IX(tT0[b]);
      for(int a = MathMax(0, b - 30); a < b; a++)
      {
         //--- a, b olusmadan alinmis: aralarinda gecilmis
         if(tT0[a] <= tO[b] && MxHm(y, IX(tT0[a]), IX(tO[b] + 1)) > tP[a]) continue;
         double oran = (tA[b] > 0.0) ? MathAbs(tP[a] - tP[b]) / tA[b] : 9.0;
         if(oran > 0.2) continue;
         if(!(oran <= e.tol)) continue;
         double lv = MathMax(tP[a], tP[b]);
         if(MxHm(y, ib, iks1) > lv) continue;
         SevEkle(e, y, lv, 1);
      }
   }
}

//--- FVG (1S / 4S / gunluk): dolmamis (ks dakikasi dahil)
void FvgSeviye(CEk *e, int y, int K, const long &bt[], const double &bh[], const double &bl[], int n, long ks, int iks1)
{
   for(int c = 2; c < n; c++)
   {
      if(!(bl[c - 2] > bh[c])) continue;
      long t0 = bt[c] + K;
      if(t0 > ks) continue;
      double lv = bh[c];
      if(MxHm(y, IX(t0), iks1) >= lv) continue;
      SevEkle(e, y, lv, 2);
   }
}

//--- killzone basinda: seviyeler, karsi likidite, gunluk yon.  donus 0 = veri yok, tekrar dene
int EkHazirla(int ei, long ks, long ke, int kz, long simdiDk)
{
   CEk *e = EK[ei];
   string s = e.s;
   long D = (ks / 1440) * 1440;
   if(!M1Yukle(s, D - ICT_GUN * 1440, simdiDk) || gT[0] > D - 30 * 1440)
   {
      if(e.denKs != ks) { e.denKs = ks; e.den = 0; }
      e.den++;
      if(e.den >= 20) { e.hzKs = ks; e.hzOk = false; PrintFormat("ICT %s: gecmis veri yuklenemedi, bu seans atlandi", s); return(1); }
      return(0);
   }
   e.hzKs = ks; e.hzKe = ke; e.hzKz = kz; e.hzD = D; e.hzOk = false;
   e.sonB = MathMax(ks, (simdiDk / 5) * 5 - 5);
   ArrayResize(e.lvY, 0); ArrayResize(e.lvP, 0); ArrayResize(e.lvTip, 0); ArrayResize(e.kY, 0); ArrayResize(e.kP, 0);
   //--- D'den onceki, verisi olan gunler (gercek fiyat)
   long dNo[];
   double dHr[], dLr[], dCr[];
   int nd = 0;
   for(int i = 0; i < gN; i++)
   {
      if(gT[i] >= D) break;
      long g = gT[i] / 1440;
      if(nd == 0 || g != dNo[nd - 1])
      {
         nd++;
         ArrayResize(dNo, nd, 128); ArrayResize(dHr, nd, 128); ArrayResize(dLr, nd, 128); ArrayResize(dCr, nd, 128);
         dNo[nd - 1] = g; dHr[nd - 1] = gH[i]; dLr[nd - 1] = gL[i]; dCr[nd - 1] = gC[i];
      }
      else
      {
         if(gH[i] > dHr[nd - 1]) dHr[nd - 1] = gH[i];
         if(gL[i] < dLr[nd - 1]) dLr[nd - 1] = gL[i];
         dCr[nd - 1] = gC[i];
      }
   }
   int k = nd;
   if(k < 8) { gN = 0; return(1); }
   long Dp = dNo[k - 1] * 1440;
   e.hzDp = Dp;
   //--- YON EKIN: dun govdeyle onceki gunun tepesi ustunde kapandi = AL, dibi altinda = SAT;
   //    fitille sadece yukari gecip icerde kapandi = SAT, sadece asagi = AL
   {
      int yy = k - 1, p = k - 2;
      int v = 0;
      if(dCr[yy] > dHr[p]) v = 1;
      else if(dCr[yy] < dLr[p]) v = -1;
      else
      {
         bool ust = dHr[yy] > dHr[p], alt = dLr[yy] < dLr[p];
         if(ust && !alt) v = -1;
         else if(alt && !ust) v = 1;
      }
      e.yonEk = v;
   }
   //--- YON ICT: dun dolmamis gunluk FVG'ye girip saygi duydu: bullish = AL, bearish = SAT
   {
      int yy = k - 1;
      bool bul = false, ber = false;
      for(int c = 2; c < k - 1; c++)
      {
         int a = c - 2;
         if(dHr[a] < dLr[c])
         {
            bool tamam = true;
            if(c + 1 <= k - 2) { double m = dLr[c + 1]; for(int j = c + 2; j <= k - 2; j++) m = MathMin(m, dLr[j]); tamam = (m > dHr[a]); }
            if(tamam && dLr[yy] <= dLr[c] && dCr[yy] > dHr[a]) bul = true;
         }
         if(dLr[a] > dHr[c])
         {
            bool tamam = true;
            if(c + 1 <= k - 2) { double m = dHr[c + 1]; for(int j = c + 2; j <= k - 2; j++) m = MathMax(m, dHr[j]); tamam = (m < dLr[a]); }
            if(tamam && dHr[yy] >= dHr[c] && dCr[yy] < dLr[a]) ber = true;
         }
      }
      e.yonIc = (bul && !ber) ? 1 : ((ber && !bul) ? -1 : 0);
   }
   SeyrekKur();
   int iks = IX(ks), iks1 = IX(ks + 1);
   long w = (D / 1440 + 3) / 7;
   long hb = (w * 7 - 3) * 1440;
   long t60[], t240[], t1440[];
   double o60[], h60[], l60[], c60[], o240[], h240[], l240[], c240[], o1440[], h1440[], l1440[], c1440[];
   for(int yi = 0; yi < 2; yi++)
   {
      int y = (yi == 0) ? -1 : 1;
      //--- onceki gun
      HesapSeviye(e, y, AD_PDH, (y < 0) ? dHr[k - 1] : -dLr[k - 1], true, D, ks, iks);
      HesapKarsi(e, y, (y < 0) ? dLr[k - 1] : -dHr[k - 1], true, D, ks, iks);
      //--- onceki hafta (hafta pazartesi baslar)
      bool var = false;
      double pwh = -BOS, pwl = BOS;
      for(int j = 0; j < k; j++)
      {
         if((dNo[j] + 3) / 7 != w - 1) continue;
         var = true;
         double hh = (y < 0) ? dHr[j] : -dLr[j], ll = (y < 0) ? dLr[j] : -dHr[j];
         if(hh > pwh) pwh = hh;
         if(ll < pwl) pwl = ll;
      }
      if(var) { HesapSeviye(e, y, AD_PWH, pwh, true, hb, ks, iks); HesapKarsi(e, y, pwl, true, hb, ks, iks); }
      //--- Asya (NY 20:00-24:00)
      int a1 = IX(D + 180), a2 = IX(D + 420);
      HesapSeviye(e, y, AD_ASYA, MxHm(y, a1, a2), a2 > a1, D + 420, ks, iks);
      HesapKarsi(e, y, MnLm(y, a1, a2), a2 > a1, D + 420, ks, iks);
      //--- Londra (NY 02:00-05:00), sadece NY seansinda
      if(kz == 1)
      {
         a1 = IX(D + 540); a2 = IX(D + 720);
         HesapSeviye(e, y, AD_LONDRA, MxHm(y, a1, a2), a2 > a1, D + 720, ks, iks);
         HesapKarsi(e, y, MnLm(y, a1, a2), a2 > a1, D + 720, ks, iks);
      }
      //--- onceki gun NY ogleden sonra (NY 13:30-16:00)
      a1 = IX(Dp + 1230); a2 = IX(Dp + 1380);
      HesapSeviye(e, y, AD_NYPM, MxHm(y, a1, a2), a2 > a1, Dp + 1380, ks, iks);
      HesapKarsi(e, y, MnLm(y, a1, a2), a2 > a1, Dp + 1380, ks, iks);
      //--- 1S / 4S / gunluk mumlar
      int n60 = Agg(y, 60, LONG_MAX, t60, o60, h60, l60, c60);
      int n240 = Agg(y, 240, LONG_MAX, t240, o240, h240, l240, c240);
      if(SetteVar(e.sev, AD_ESIT))
      {
         EsitTepe(e, y, 60, t60, h60, l60, c60, n60, ks, iks1);
         EsitTepe(e, y, 240, t240, h240, l240, c240, n240, ks, iks1);
      }
      if(SetteVar(e.sev, AD_FVG1)) FvgSeviye(e, y, 60, t60, h60, l60, n60, ks, iks1);
      if(SetteVar(e.sev, AD_FVG4)) FvgSeviye(e, y, 240, t240, h240, l240, n240, ks, iks1);
      if(SetteVar(e.sev, AD_FVGG))
      {
         int n1440 = Agg(y, 1440, LONG_MAX, t1440, o1440, h1440, l1440, c1440);
         FvgSeviye(e, y, 1440, t1440, h1440, l1440, n1440, ks, iks1);
      }
      //--- karsi likidite: 1 saatlik swing dipler, alinmamis (ks dakikasi dahil)
      for(int i = 1; i < n60 - 1; i++)
      {
         if(!(l60[i] < l60[i - 1] && l60[i] < l60[i + 1])) continue;
         long t0 = t60[i + 1] + 60;
         if(t0 > ks) continue;
         if(MnLm(y, IX(t0), iks1) < l60[i]) continue;
         KarsiEkle(e, y, l60[i]);
      }
   }
   e.hzOk = true;
   gST = false;
   ArrayFree(STX); ArrayFree(STN); ArrayFree(LG);
   gN = 0;
   PrintFormat("ICT %s %s seansi hazir: seviye %d, karsi %d, yon EKIN %d ICT %d", s, kz == 0 ? "LONDRA" : "NY",
               ArraySize(e.lvY), ArraySize(e.kY), e.yonEk, e.yonIc);
   return(1);
}

//--- MSS: supurme mumundan sonra son swing dibin altinda govde kapanisi
bool Mss(const long &bt[], const double &bh[], const double &bl[], const double &bc[], const int &sw[], int n, int Km,
         long ts, long ke, long &tmss)
{
   tmss = -1;
   int i = UstSinir(bt, n, ts) - 1;
   if(i < 3) return(false);
   double tepe = -BOS, ref = 0.0;
   bool rv = false;
   for(int j = i; j < n; j++)
   {
      if(bt[j] + Km > ke) break;
      if(bh[j] > tepe)
      {
         tepe = bh[j];
         int q = sw[j];
         rv = (q >= 0);
         if(rv) ref = bl[q];
         continue;
      }
      if(rv && bc[j] < ref) { tmss = bt[j] + Km; break; }
   }
   return(true);
}

void ZonEkle(double alt, double ust, double gov, int tur)
{
   nZon++;
   ArrayResize(zAlt, nZon, 32); ArrayResize(zUst, nZon, 32); ArrayResize(zGov, nZon, 32); ArrayResize(zTur, nZon, 32);
   zAlt[nZon - 1] = alt; zUst[nZon - 1] = ust; zGov[nZon - 1] = gov; zTur[nZon - 1] = tur;
}

//--- a bolgesi b'den kucuk mu (alt, ust, govde, tur sirasi)
bool ZonKucuk(int a, int b)
{
   if(zAlt[a] != zAlt[b]) return(zAlt[a] < zAlt[b]);
   if(zUst[a] != zUst[b]) return(zUst[a] < zUst[b]);
   if(zGov[a] != zGov[b]) return(zGov[a] < zGov[b]);
   return(zTur[a] < zTur[b]);
}

//--- kirilim bacagindaki FVG'ler (K dakika)
void ZonFvg(int y, int K, const long &ft[], const double &fo[], const double &fh[], const double &fl[], const double &fc[],
            int n, long tTepe, long Td, double fiyat)
{
   int a0 = UstSinir(ft, n, tTepe) - 1;
   int a1 = AltSinir(ft, n, Td);
   for(int a = MathMax(a0, 0); a < a1 - 2; a++)
   {
      int c = a + 2;
      if(ft[c] + K > Td || !(fl[a] > fh[c])) continue;
      double alt = fh[c], ust = fl[a];
      if(alt <= fiyat || MxHm(y, IX(ft[c] + K), IX(Td)) >= alt) continue;
      ZonEkle(alt, ust, MathMax(fo[a], fc[a]), 0);
   }
}

//--- bir supurmeden kurulum.  false = yok (Python None).  ok = giris bolgesi var
bool Kurulum(int y, long ts, long ke, int s1, int s7, long &Td, bool &ok, double &tepeO, double &tgO, double &altO,
             double &ustO, double &msO, bool &sharpO)
{
   ok = false; Td = -1;
   long tmss = -1;
   if(s7 == 0) { if(!Mss(b5t, b5h, b5l, b5c, sw5, n5, 5, ts, ke, tmss)) return(false); }
   else        { if(!Mss(b15t, b15h, b15l, b15c, sw15, n15, 15, ts, ke, tmss)) return(false); }
   //--- IFVG: likiditeyi alirken (son 5 dk swing dipten tepeye) birakilan yukari FVG'nin govdeyle bozulmasi
   int j0 = UstSinir(b5t, n5, ts) - 1;
   int bacak = (j0 >= 0) ? MathMax(sw5[j0], 0) : 0;
   double tp5 = -BOS;
   int p5 = -1;
   long tifvg = -1;
   int invA[], invJ[];
   int ni = 0;
   for(int j = MathMax(j0, 0); j < n5; j++)
   {
      if(b5t[j] + 5 > ke) break;
      if(b5h[j] > tp5) { tp5 = b5h[j]; p5 = j; continue; }
      for(int q = 0; q < nbq5; q++)
      {
         int a = bq5[q];
         if(a < bacak || a + 2 > n5 - 1) continue;
         if(!(a + 2 <= p5 && b5c[j] < b5h[a])) continue;
         bool vard = false;
         for(int z = 0; z < ni; z++) if(invA[z] == a) { vard = true; break; }
         if(vard) continue;
         ni++;
         ArrayResize(invA, ni, 16); ArrayResize(invJ, ni, 16);
         invA[ni - 1] = a; invJ[ni - 1] = j;
         if(tifvg < 0) tifvg = b5t[j] + 5;
      }
   }
   Td = tmss;
   if(s1 == 1 && tifvg >= 0 && (Td < 0 || tifvg < Td)) Td = tifvg;
   if(Td < 0) return(false);
   int a_ = IX(ts), b_ = IX(Td);
   if(b_ <= a_) return(true);
   double tepe = -BOS;
   int am = a_;
   for(int i = a_; i < b_; i++) { double h = HM(y, i); if(h > tepe) { tepe = h; am = i; } }
   long tTepe = gT[am];
   double fiyat = CM(y, b_ - 1);
   int k5 = UstSinir(b5t, n5, tTepe) - 1;
   if(k5 < 0) return(true);
   double tg = MathMax(b5o[k5], b5c[k5]);
   nZon = 0;
   ZonFvg(y, 5, b5t, b5o, b5h, b5l, b5c, n5, tTepe, Td, fiyat);
   if(nZon == 0 && s7 == 0) ZonFvg(y, 3, b3t, b3o, b3h, b3l, b3c, n3, tTepe, Td, fiyat);
   for(int z = 0; z < ni; z++)
   {
      int a = invA[z], j = invJ[z];
      if(b5t[j] + 5 > Td || j <= k5 || a + 2 > k5) continue;
      double alt = b5h[a], ust = b5l[a + 2];
      if(alt <= fiyat || MxHm(y, IX(b5t[j] + 5), IX(Td)) >= alt) continue;
      ZonEkle(alt, ust, MathMax(b5o[j], b5c[j]), 1);
   }
   if(nZon == 0) return(true);
   int bi = 0;
   for(int z = 1; z < nZon; z++) if(ZonKucuk(z, bi)) bi = z;
   double ms = zGov[0];
   for(int z = 1; z < nZon; z++) if(zGov[z] > ms) ms = zGov[z];
   bool sharp = false;
   for(int q = 0; q < nbq5; q++) if(bq5[q] >= bacak && bq5[q] + 2 <= k5) { sharp = true; break; }
   ok = true;
   tepeO = tepe; tgO = tg; altO = zAlt[bi]; ustO = zUst[bi]; msO = ms; sharpO = sharp;
   return(true);
}

void KurEkle(long Td, int y, double tepe, double tg, double alt, double ust, double ms, bool sharp)
{
   nKur++;
   ArrayResize(kTd, nKur, 16); ArrayResize(kYn, nKur, 16); ArrayResize(kTepe, nKur, 16); ArrayResize(kTG, nKur, 16);
   ArrayResize(kAlt, nKur, 16); ArrayResize(kUst, nKur, 16); ArrayResize(kMS, nKur, 16); ArrayResize(kSharp, nKur, 16);
   kTd[nKur - 1] = Td; kYn[nKur - 1] = y; kTepe[nKur - 1] = tepe; kTG[nKur - 1] = tg;
   kAlt[nKur - 1] = alt; kUst[nKur - 1] = ust; kMS[nKur - 1] = ms; kSharp[nKur - 1] = sharp;
}

//--- hayalet emir: fiyat girise gelmeden TP'ye gittigi icin silinen emir; Python'daki gibi
//    fiyat girise gelene ya da emir suresi bitene kadar sembol mesgul sayilir
string HayaletAd(int ei) { return("EAR_GH_" + IntegerToString((long)Sihir) + "_" + IntegerToString(ei) + "_"); }

void HayaletKur(int ei, int y, double E, long ex)
{
   string g = HayaletAd(ei);
   GlobalVariableSet(g + "E", E);
   GlobalVariableSet(g + "Y", y);
   GlobalVariableSet(g + "X", (double)ex);
}

void HayaletYonet()
{
   long dk = (long)SunucuSimdi() / 60;
   for(int ei = 0; ei < ArraySize(EK); ei++)
   {
      string g = HayaletAd(ei);
      if(!GlobalVariableCheck(g + "X")) continue;
      long ex = (long)GlobalVariableGet(g + "X");
      double E = GlobalVariableGet(g + "E");
      int y = (int)GlobalVariableGet(g + "Y");
      string s = EK[ei].s;
      long b = -1;
      if(dk >= ex) b = ex;
      else
      {
         double bid = SymbolInfoDouble(s, SYMBOL_BID), ask = SymbolInfoDouble(s, SYMBOL_ASK);
         double hi = iHigh(s, PERIOD_M1, 0), lo = iLow(s, PERIOD_M1, 0);
         if(y < 0 && ((bid > 0.0 && bid >= E) || (hi > 0.0 && hi >= E))) b = dk;
         if(y > 0 && ((ask > 0.0 && ask <= E) || (lo > 0.0 && ask > 0.0 && lo + (ask - bid) <= E))) b = dk;
      }
      if(b < 0) continue;
      GlobalVariableSet(g + "B", (double)b);
      GlobalVariableDel(g + "X"); GlobalVariableDel(g + "E"); GlobalVariableDel(g + "Y");
   }
}

//--- sembolde ICT islemi / emri var mi ya da kurulum, onceki islemin bitisinden once mi (Python: Td < mesgul)
bool EkMesgul(int ei, long Td)
{
   ulong mg = EkMagic(ei);
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong t = PositionGetTicket(i);
      if(t != 0 && (ulong)PositionGetInteger(POSITION_MAGIC) == mg) return(true);
   }
   for(int i = OrdersTotal() - 1; i >= 0; i--)
   {
      ulong t = OrderGetTicket(i);
      if(t != 0 && (ulong)OrderGetInteger(ORDER_MAGIC) == mg) return(true);
   }
   string g = HayaletAd(ei);
   if(GlobalVariableCheck(g + "X")) return(true);
   if(GlobalVariableCheck(g + "B") && Td < (long)GlobalVariableGet(g + "B")) return(true);
   datetime simdi = SunucuSimdi();
   if(!HistorySelect(simdi - 3 * 86400, simdi + 3600)) return(false);
   long son = 0;
   ulong pz[];
   int n = HistoryDealsTotal();
   for(int i = 0; i < n; i++)
   {
      ulong t = HistoryDealGetTicket(i);
      if(t == 0) continue;
      if((ulong)HistoryDealGetInteger(t, DEAL_MAGIC) != mg || HistoryDealGetInteger(t, DEAL_ENTRY) != DEAL_ENTRY_IN) continue;
      int z = ArraySize(pz); ArrayResize(pz, z + 1); pz[z] = (ulong)HistoryDealGetInteger(t, DEAL_POSITION_ID);
   }
   for(int i = 0; i < n; i++)
   {
      ulong t = HistoryDealGetTicket(i);
      if(t == 0) continue;
      long en = HistoryDealGetInteger(t, DEAL_ENTRY);
      if(en != DEAL_ENTRY_OUT && en != DEAL_ENTRY_INOUT && en != DEAL_ENTRY_OUT_BY) continue;
      if(ListedeBul((ulong)HistoryDealGetInteger(t, DEAL_POSITION_ID), pz) < 0) continue;
      long c = (long)HistoryDealGetInteger(t, DEAL_TIME) / 60 + 1;
      if(c > son) son = c;
   }
   int no = HistoryOrdersTotal();
   for(int i = 0; i < no; i++)
   {
      ulong t = HistoryOrderGetTicket(i);
      if(t == 0) continue;
      if((ulong)HistoryOrderGetInteger(t, ORDER_MAGIC) != mg) continue;
      long st = HistoryOrderGetInteger(t, ORDER_STATE);
      if(st != ORDER_STATE_CANCELED && st != ORDER_STATE_EXPIRED) continue;
      long c = (long)HistoryOrderGetInteger(t, ORDER_TIME_DONE) / 60;
      if(c > son) son = c;
   }
   return(Td < son);
}

//--- DISIPLIN=EKIN: bu seansta islem acildiysa ya da bugun kazanan islem varsa yeni islem yok
bool EkDisiplin(int ei)
{
   CEk *e = EK[ei];
   ulong mg = EkMagic(ei);
   long D = e.hzD;
   datetime simdi = SunucuSimdi();
   if(!HistorySelect((datetime)((D - 1440) * 60), simdi + 3600)) return(false);
   ulong pz[];
   int n = HistoryDealsTotal();
   for(int i = 0; i < n; i++)
   {
      ulong t = HistoryDealGetTicket(i);
      if(t == 0) continue;
      if((ulong)HistoryDealGetInteger(t, DEAL_MAGIC) != mg || HistoryDealGetInteger(t, DEAL_ENTRY) != DEAL_ENTRY_IN) continue;
      long dk = (long)HistoryDealGetInteger(t, DEAL_TIME) / 60;
      if((dk / 1440) * 1440 != D) continue;
      int kzF = (e.forex && dk - D < 840) ? 0 : 1;
      if(kzF == e.hzKz) return(true);
      int z = ArraySize(pz); ArrayResize(pz, z + 1); pz[z] = (ulong)HistoryDealGetInteger(t, DEAL_POSITION_ID);
   }
   for(int p = 0; p < ArraySize(pz); p++)
   {
      if(PositionSelectByTicket(pz[p])) continue;
      double kar = 0.0;
      bool cik = false;
      for(int i = 0; i < n; i++)
      {
         ulong t = HistoryDealGetTicket(i);
         if(t == 0 || (ulong)HistoryDealGetInteger(t, DEAL_POSITION_ID) != pz[p]) continue;
         long en = HistoryDealGetInteger(t, DEAL_ENTRY);
         if(en != DEAL_ENTRY_OUT && en != DEAL_ENTRY_INOUT && en != DEAL_ENTRY_OUT_BY) continue;
         kar += HistoryDealGetDouble(t, DEAL_PROFIT);
         cik = true;
      }
      if(cik && kar > 0.0) return(true);
   }
   return(false);
}

//--- kurulumdan emir: giris / stop / TP / lot (Python sonuclar() ile ayni)
bool EkIslemAc(int ei, int i)
{
   CEk *e = EK[ei];
   string s = e.s;
   int y = kYn[i];
   long Td = kTd[i];
   if(limitDurdu) return(false);
   if(!TerminalInfoInteger(TERMINAL_TRADE_ALLOWED) || !MQLInfoInteger(MQL_TRADE_ALLOWED)) return(false);
   long mod = SymbolInfoInteger(s, SYMBOL_TRADE_MODE);
   if(!(mod == SYMBOL_TRADE_MODE_FULL || (y > 0 && mod == SYMBOL_TRADE_MODE_LONGONLY) || (y < 0 && mod == SYMBOL_TRADE_MODE_SHORTONLY)))
   { PrintFormat("ICT %s islem acilamadi: sembolde islem kapali", s); return(false); }
   double bid = SymbolInfoDouble(s, SYMBOL_BID);
   double ask = SymbolInfoDouble(s, SYMBOL_ASK);
   if(bid <= 0.0 || ask <= 0.0) return(false);
   bool piyasa = (e.giris == G_KAPANIS);
   double Em;
   if(e.giris == G_ORTA)       Em = 0.5 * (kAlt[i] + kUst[i]);
   else if(e.giris == G_KENAR) Em = kAlt[i];
   else                        Em = (y < 0) ? bid : -ask;
   double Sm = (e.stp == ST_SWING) ? kTG[i] : ((e.stp == ST_FVGMUM) ? kMS[i] : kTepe[i]);
   double r = Sm - Em;
   if(!(r > 0.0)) { PrintFormat("ICT %s kurulum atlandi: stop girisin yanlis tarafinda", s); return(false); }
   double TPm;
   if(e.tp == T_2R)      TPm = Em - 2.0 * r;
   else if(e.tp == T_3R) TPm = Em - 3.0 * r;
   else
   {
      bool var = false;
      TPm = -BOS;
      for(int j = 0; j < ArraySize(e.kY); j++)
         if(e.kY[j] == y && e.kP[j] <= Em - 2.0 * r && e.kP[j] > TPm) { TPm = e.kP[j]; var = true; }
      if(!var) { PrintFormat("ICT %s kurulum atlandi: en az 2R uzakta karsi likidite yok", s); return(false); }
   }
   double E = Ayna(y, Em), S = Ayna(y, Sm), TPr = Ayna(y, TPm);
   long D = e.hzD;
   long bitis = (e.emir == 0) ? e.hzKe : Td + 120;
   if(bitis > D + NY_KAPANIS) bitis = D + NY_KAPANIS;
   if(!piyasa && bitis <= Td) return(false);
   double eLot = piyasa ? ((y < 0) ? bid : ask) : E;
   if(!piyasa && ((y < 0 && bid >= E) || (y > 0 && ask <= E))) piyasa = true;   // fiyat girisi gecmis: hemen dolar
   S = Yuvarla(s, S); TPr = Yuvarla(s, TPr); E = Yuvarla(s, E);
   if(piyasa)
   {
      if(y < 0 && (S <= ask || TPr >= bid)) { PrintFormat("ICT %s islem acilmadi: fiyat stop / TP seviyesini gecmis", s); return(false); }
      if(y > 0 && (S >= bid || TPr <= ask)) { PrintFormat("ICT %s islem acilmadi: fiyat stop / TP seviyesini gecmis", s); return(false); }
   }
   double zarar = 0.0;
   double lot = LotBul(s, y > 0, eLot, S, zarar);
   if(lot <= 0.0) { PrintFormat("ICT %s islem acilmadi: lot hesaplanamadi", s); return(false); }
   if(zarar > EnFazlaZarar + 1e-9)
   { PrintFormat("ICT %s islem acilmadi: en kucuk lotta (%.2f) stop zarari %.2f $ > %.2f $", s, lot, zarar, EnFazlaZarar); return(false); }
   double makas = 0.0;
   if(!OrderCalcProfit(ORDER_TYPE_BUY, s, lot, bid, ask, makas)) makas = 0.0;
   if(makas > MakasSinir + 1e-9)
   { PrintFormat("ICT %s islem acilmadi: spread maliyeti %.2f $ > %.2f $", s, makas, MakasSinir); return(false); }
   double nokta = SymbolInfoDouble(s, SYMBOL_POINT);
   long seviye = SymbolInfoInteger(s, SYMBOL_TRADE_STOPS_LEVEL);
   double gF = piyasa ? ((y < 0) ? bid : ask) : E;
   if(MathAbs(gF - S) < seviye * nokta || MathAbs(TPr - gF) < seviye * nokta)
   { PrintFormat("ICT %s islem acilmadi: stop / TP mesafesi cok kucuk", s); return(false); }

   ulong mg = EkMagic(ei);
   trade.SetExpertMagicNumber(mg);
   trade.SetDeviationInPoints(Kayma);
   string yorum = "ICT" + IntegerToString(ei);
   bool ok;
   if(piyasa)
   {
      trade.SetTypeFillingBySymbol(s);
      ok = (y > 0) ? trade.Buy(lot, s, 0.0, S, TPr, yorum) : trade.Sell(lot, s, 0.0, S, TPr, yorum);
   }
   else
   {
      trade.SetTypeFilling(ORDER_FILLING_RETURN);
      ok = (y > 0) ? trade.BuyLimit(lot, E, s, S, TPr, ORDER_TIME_GTC, 0, yorum)
                   : trade.SellLimit(lot, E, s, S, TPr, ORDER_TIME_GTC, 0, yorum);
      if(!ok && trade.ResultRetcode() == TRADE_RETCODE_INVALID_FILL)
      {
         trade.SetTypeFillingBySymbol(s);
         ok = (y > 0) ? trade.BuyLimit(lot, E, s, S, TPr, ORDER_TIME_GTC, 0, yorum)
                      : trade.SellLimit(lot, E, s, S, TPr, ORDER_TIME_GTC, 0, yorum);
      }
   }
   uint rc = trade.ResultRetcode();
   int dg = (int)SymbolInfoInteger(s, SYMBOL_DIGITS);
   if(ok && (rc == TRADE_RETCODE_DONE || rc == TRADE_RETCODE_PLACED || rc == TRADE_RETCODE_DONE_PARTIAL))
   {
      if(!piyasa)
      {
         ulong tk = trade.ResultOrder();
         GlobalVariableSet(GvAd("EX", tk), (double)bitis);
         GlobalVariableSet(GvAd("ET", tk), (double)Td);
      }
      PrintFormat("ICT %s %s %s  lot %s  giris %s  stop %s  TP %s  zarar %.2f $  spread %.2f $  [%s]", s, y > 0 ? "ALIS" : "SATIS",
                  piyasa ? "piyasa emri" : "limit emir", DoubleToString(lot, 2), DoubleToString(gF, dg), DoubleToString(S, dg),
                  DoubleToString(TPr, dg), zarar, makas, e.ad);
      return(true);
   }
   PrintFormat("ICT %s %s acilamadi: %u %s", s, y > 0 ? "ALIS" : "SATIS", rc, trade.ResultRetcodeDescription());
   return(false);
}

//--- Python gecis(): sharp, yon, mesgul, disiplin
void EkGecis(int ei, int i)
{
   CEk *e = EK[ei];
   int y = kYn[i];
   if(e.shrp == 1 && !kSharp[i]) return;
   if(e.yon == 1 && e.yonEk != y) return;
   if(e.yon == 2 && e.yonIc != y) return;
   if(EkMesgul(ei, kTd[i])) return;
   if(e.dis == 1 && EkDisiplin(ei)) return;
   EkIslemAc(ei, i);
}

//--- her 5 dk sinirinda: seans basindan bu ana kadar olusan mumlarla kurulumlar; yeni olanlar islenir
void EkDegerlendir(int ei, long nowB)
{
   CEk *e = EK[ei];
   if(!M1Yukle(e.s, e.hzDp, nowB)) return;
   long ks = e.hzKs, ke = e.hzKe;
   nKur = 0;
   int i0 = IX(ks);
   for(int yi = 0; yi < 2; yi++)
   {
      int y = (yi == 0) ? -1 : 1;
      //--- seviyelerin supurulme zamanlari
      long vur[];
      int nv = 0;
      for(int j = 0; j < ArraySize(e.lvY); j++)
      {
         if(e.lvY[j] != y) continue;
         double p = e.lvP[j];
         bool esit = (e.lvTip[j] == 2);
         for(int i = i0; i < gN; i++)
         {
            if(gT[i] >= ke) break;
            double h = HM(y, i);
            if(esit ? (h >= p) : (h > p)) { nv++; ArrayResize(vur, nv, 64); vur[nv - 1] = gT[i]; break; }
         }
      }
      if(nv == 0) continue;
      n3  = Agg(y, 3,  (nowB / 3) * 3,   b3t,  b3o,  b3h,  b3l,  b3c);
      n5  = Agg(y, 5,  (nowB / 5) * 5,   b5t,  b5o,  b5h,  b5l,  b5c);
      n15 = Agg(y, 15, (nowB / 15) * 15, b15t, b15o, b15h, b15l, b15c);
      SonSw(b5l, n5, sw5);
      SonSw(b15l, n15, sw15);
      nbq5 = 0;
      ArrayResize(bq5, 0, 256);
      for(int a = 0; a + 2 < n5; a++)
         if(b5h[a] < b5l[a + 2]) { nbq5++; ArrayResize(bq5, nbq5, 256); bq5[nbq5 - 1] = a; }
      long bas = ks;
      while(true)
      {
         long ts = LONG_MAX;
         for(int j = 0; j < nv; j++) if(vur[j] >= bas && vur[j] < ts) ts = vur[j];
         if(ts == LONG_MAX) break;
         long Td; bool ok; double tepe = 0, tg = 0, alt = 0, ust = 0, ms = 0; bool sharp = false;
         if(!Kurulum(y, ts, ke, e.mss, e.zmn, Td, ok, tepe, tg, alt, ust, ms, sharp)) break;
         bas = MathMax(Td, ts + 1);
         if(!ok) continue;
         KurEkle(Td, y, tepe, tg, alt, ust, ms, sharp);
      }
   }
   //--- (Td, yon) sirasi
   int sira[];
   ArrayResize(sira, nKur);
   for(int i = 0; i < nKur; i++) sira[i] = i;
   for(int i = 1; i < nKur; i++)
   {
      int v = sira[i], j = i - 1;
      while(j >= 0 && (kTd[sira[j]] > kTd[v] || (kTd[sira[j]] == kTd[v] && kYn[sira[j]] > kYn[v]))) { sira[j + 1] = sira[j]; j--; }
      sira[j + 1] = v;
   }
   for(int q = 0; q < nKur; q++)
   {
      int i = sira[q];
      if(kTd[i] <= e.sonB || kTd[i] > nowB) continue;
      EkGecis(ei, i);
   }
   e.sonB = nowB;
   gN = 0;
}

//--- bekleyen ICT emirleri: sure dolunca ya da fiyat girise gelmeden TP seviyesine giderse silinir
void EkEmirYonet()
{
   datetime simdi = SunucuSimdi();
   long dk = (long)simdi / 60;
   for(int i = OrdersTotal() - 1; i >= 0; i--)
   {
      ulong t = OrderGetTicket(i);
      if(t == 0) continue;
      ulong mg = (ulong)OrderGetInteger(ORDER_MAGIC);
      if(!IctMagic(mg)) continue;
      int ei = KuralNo(mg);
      string s = OrderGetString(ORDER_SYMBOL);
      long tip = OrderGetInteger(ORDER_TYPE);
      double E = OrderGetDouble(ORDER_PRICE_OPEN), tp = OrderGetDouble(ORDER_TP);
      long kur = (long)OrderGetInteger(ORDER_TIME_SETUP) / 60;
      long ex = GlobalVariableCheck(GvAd("EX", t)) ? (long)GlobalVariableGet(GvAd("EX", t)) : (kur / 1440) * 1440 + NY_KAPANIS;
      long td = GlobalVariableCheck(GvAd("ET", t)) ? (long)GlobalVariableGet(GvAd("ET", t)) : kur;
      if(dk >= ex) { EmirSil(t, "emir süresi doldu"); continue; }
      if(tp <= 0.0) continue;
      bool sat = (tip == ORDER_TYPE_SELL_LIMIT);
      double bid = SymbolInfoDouble(s, SYMBOL_BID), ask = SymbolInfoDouble(s, SYMBOL_ASK);
      bool degdi = (sat && ask > 0.0 && ask <= tp) || (!sat && bid > 0.0 && bid >= tp);
      if(!degdi)
      {
         MqlRates r[];
         ArraySetAsSeries(r, false);
         int n = CopyRates(s, PERIOD_M1, (datetime)(td * 60), simdi, r);
         double pt = SymbolInfoDouble(s, SYMBOL_POINT);
         for(int j = 0; j < n; j++)
         {
            if(sat && r[j].low + r[j].spread * pt <= tp) { degdi = true; break; }
            if(!sat && r[j].high >= tp) { degdi = true; break; }
         }
      }
      if(!degdi) continue;
      if(EmirSil(t, "fiyat girişe gelmeden TP seviyesine gitti") && GecerliEk(ei)) HayaletKur(ei, sat ? -1 : 1, E, ex);
   }
}

//--- ICT zamanlayici: killzone basinda hazirlik (saniyede en fazla 4 sembol), her 5 dk degerlendirme
void EkinKontrol()
{
   long sn = (long)SunucuSimdi();
   long dk = sn / 60;
   long D = (dk / 1440) * 1440;
   long nowB = (dk / 5) * 5;
   int hz = 0;
   for(int ei = 0; ei < ArraySize(EK); ei++)
   {
      CEk *e = EK[ei];
      if(!e.aktif) continue;
      long ks = -1, ke = -1;
      int kz = 1;
      if(e.forex)
      {
         if(dk >= D + 540 && dk < D + 725)       { ks = D + 540; ke = D + 720;  kz = 0; }
         else if(dk >= D + 840 && dk < D + 1025) { ks = D + 840; ke = D + 1020; kz = 1; }
      }
      else if(dk >= D + 930 && dk < D + 1085)    { ks = D + 930; ke = D + 1080; kz = 1; }
      if(ks < 0) continue;
      if(e.hzKs != ks)
      {
         if(dk < ks + 1 || nowB > ke || limitDurdu) continue;
         if(hz >= 4) continue;
         hz++;
         EkHazirla(ei, ks, ke, kz, dk);
         continue;
      }
      if(!e.hzOk || limitDurdu) continue;
      if(nowB < ks + 5 || nowB > ke || nowB <= e.sonB) continue;
      if(sn < nowB * 60 + 2) continue;
      EkDegerlendir(ei, nowB);
   }
}

int nIctSem = 0, nKesKural = 0;

//--- bu robotun pozisyon numaralari (giris islemleri magic tasir); history secili kalir
void PozisyonListesi(datetime bas, datetime bit, ulong &liste[], ulong &mgl[])
{
   ArrayResize(liste, 0); ArrayResize(mgl, 0);
   if(!HistorySelect(bas, bit)) return;
   int n = HistoryDealsTotal();
   for(int i = 0; i < n; i++)
   {
      ulong t = HistoryDealGetTicket(i);
      if(t == 0) continue;
      ulong mg = (ulong)HistoryDealGetInteger(t, DEAL_MAGIC);
      if(!BizimMagic(mg)) continue;
      if(HistoryDealGetInteger(t, DEAL_ENTRY) != DEAL_ENTRY_IN) continue;
      int k = ArraySize(liste);
      ArrayResize(liste, k + 1); ArrayResize(mgl, k + 1);
      liste[k] = (ulong)HistoryDealGetInteger(t, DEAL_POSITION_ID);
      mgl[k] = mg;
   }
}

int ListedeBul(ulong pid, const ulong &liste[])
{
   for(int i = 0; i < ArraySize(liste); i++) if(liste[i] == pid) return(i);
   return(-1);
}

double DealPara(ulong t)
{
   return(HistoryDealGetDouble(t, DEAL_PROFIT) + HistoryDealGetDouble(t, DEAL_SWAP)
        + HistoryDealGetDouble(t, DEAL_COMMISSION) + HistoryDealGetDouble(t, DEAL_FEE));
}

double KalanHesapla(double &kapanan, double &acik, int &nPoz)
{
   datetime pragBas;
   PragGunKey(pragBas);
   ulong poz[], mgl[];
   PozisyonListesi(pragBas - 8 * 86400, SunucuSimdi() + 86400, poz, mgl);
   kapanan = 0.0;
   int n = HistoryDealsTotal();
   for(int i = 0; i < n; i++)
   {
      ulong t = HistoryDealGetTicket(i);
      if(t == 0) continue;
      if((datetime)HistoryDealGetInteger(t, DEAL_TIME) < pragBas) continue;
      long tip = HistoryDealGetInteger(t, DEAL_TYPE);
      if(tip != DEAL_TYPE_BUY && tip != DEAL_TYPE_SELL) continue;
      if(ListedeBul((ulong)HistoryDealGetInteger(t, DEAL_POSITION_ID), poz) < 0) continue;
      kapanan += DealPara(t);
   }
   acik = 0.0; nPoz = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong t = PositionGetTicket(i);
      if(t == 0) continue;
      if(!BizimMagic((ulong)PositionGetInteger(POSITION_MAGIC))) continue;
      acik += PositionGetDouble(POSITION_PROFIT) + PositionGetDouble(POSITION_SWAP);
      nPoz++;
   }
   return(GunlukLimit + kapanan + acik);
}

void LimitKontrol()
{
   datetime pragBas;
   int gunKey = PragGunKey(pragBas);
   double kapanan, acik; int nPoz;
   double kalan = KalanHesapla(kapanan, acik, nPoz);
   sonKalan = kalan;
   int nIct = 0, nKes = 0, nEmir = 0;
   for(int i = PositionsTotal() - 1; i >= 0; i--)
   {
      ulong t = PositionGetTicket(i);
      if(t == 0) continue;
      ulong mg = (ulong)PositionGetInteger(POSITION_MAGIC);
      if(IctMagic(mg)) nIct++;
      else if(BizimMagic(mg)) nKes++;
   }
   for(int i = OrdersTotal() - 1; i >= 0; i--)
   {
      ulong t = OrderGetTicket(i);
      if(t != 0 && IctMagic((ulong)OrderGetInteger(ORDER_MAGIC))) nEmir++;
   }

   if(GlobalVariableCheck(GV_DUR) && (int)GlobalVariableGet(GV_DUR) == gunKey) durGun = gunKey;
   if(kalan <= 0.0 && durGun != gunKey)
   {
      durGun = gunKey;
      GlobalVariableSet(GV_DUR, gunKey);
      PrintFormat("EAROBOT GUNLUK LIMIT DOLDU (kalan %.2f $). Robotun islemleri kapatiliyor, bugun islem yok.", kalan);
      TgEkle(StringFormat("⛔ GÜNLÜK LİMİT DOLDU\nKalan limit: %.2f $\nRobotun bütün işlemleri kapatılıyor, bugün yeni işlem açılmayacak.\nLimit Prag gece yarısı sıfırlanır.", kalan));
   }
   limitDurdu = (durGun == gunKey);
   if(limitDurdu && (nPoz > 0 || nEmir > 0)) KendiniKapat("Günlük limit doldu");

   MqlDateTime pz;
   TimeToStruct(PragSimdi(), pz);
   long ny = NyDk(SunucuSimdi());
   long dk = ny % 1440;
   MqlDateTime tz;
   TimeToStruct(TrZaman(SunucuSimdi()), tz);
   string durum = limitDurdu ? "LİMİT DOLDU - BUGÜN İŞLEM YOK" : "AKTİF";
   if(!limitDurdu && (!TerminalInfoInteger(TERMINAL_TRADE_ALLOWED) || !MQLInfoInteger(MQL_TRADE_ALLOWED)))
      durum = "OTOMATİK İŞLEM KAPALI (Algo Trading butonu)";

   Yazi("kalan", StringFormat("EAROBOT  Kalan günlük limit: %.2f $  (limit %.0f $)", kalan, GunlukLimit), YaziY, YaziBoyu);
   Yazi("bugun", StringFormat("Bugün kapanan: %+.2f $    Açık işlemler: %+.2f $    Toplam: %+.2f $",
                              kapanan, acik, kapanan + acik), YaziY + YaziBoyu * 2, 10);
   Yazi("detay", StringFormat("Açık işlem: %d  (ICT %d / Kesişim %d)    Bekleyen ICT emri: %d    NY %02d:%02d   Prag %02d:%02d   TR %02d:%02d",
                              nPoz, nIct, nKes, nEmir, (int)(dk / 60), (int)(dk % 60), pz.hour, pz.min,
                              tz.hour, tz.min), YaziY + YaziBoyu * 2 + 18, 10);
   Yazi("sembol", StringFormat("ICT: %d sembol    Kesişim: %d sembol, %d kural", nIctSem, ArraySize(SEM), nKesKural),
        YaziY + YaziBoyu * 2 + 36, 10);
   Yazi("durum", "Durum: " + durum + "    (limit Prag 00:00'da sıfırlanır)", YaziY + YaziBoyu * 2 + 54, 10);
   Yazi("tg", "Telegram: " + (TelegramAcik ? (tgDurum == "" ? "hazır" : tgDurum) : "kapalı")
              + (ArraySize(KUYRUK) > 0 ? StringFormat("   (bekleyen mesaj %d)", ArraySize(KUYRUK)) : ""),
        YaziY + YaziBoyu * 2 + 72, 10);
   ChartRedraw(0);
}

//+------------------------------------------------------------------+
//  TELEGRAM MESAJLARI (anlasilan sabit format)
//+------------------------------------------------------------------+
string Virgul(string x) { StringReplace(x, ".", ","); return(x); }
string ParaYaz(double x) { return(Virgul(StringFormat("%+.2f", x)) + " $"); }
string TutarYaz(double x) { return(Virgul(StringFormat("%.2f", x)) + " $"); }
string FiyatYaz(string s, double p) { return(Virgul(DoubleToString(p, (int)SymbolInfoInteger(s, SYMBOL_DIGITS)))); }
string YonYaz(int yon) { return(yon > 0 ? "ALIŞ" : "SATIŞ"); }

string TrSaat(datetime sunucu)
{
   MqlDateTime z;
   TimeToStruct(TrZaman(sunucu), z);
   return(StringFormat("%02d.%02d.%04d %02d:%02d", z.day, z.mon, z.year, z.hour, z.min));
}

string BakiyeYaz(double x)
{
   long kr = (long)MathRound(MathAbs(x) * 100.0);
   string t = IntegerToString(kr / 100), o = "";
   int n = StringLen(t);
   for(int i = 0; i < n; i++)
   {
      if(i > 0 && (n - i) % 3 == 0) o += ".";
      o += StringSubstr(t, i, 1);
   }
   return((x < 0 ? "-" : "") + o + "," + StringFormat("%02d", (int)(kr % 100)) + " $");
}

//+------------------------------------------------------------------+
//  KAPANIS MESAJI + STOP SONRASI 24 SAAT TAKIP
//+------------------------------------------------------------------+
void IzlemeEkle(ulong pid, ulong mg, int yon, double tp, datetime kapanis, double giris, double sl, double lot)
{
   if(tp <= 0.0) return;
   if(GlobalVariableCheck("EAR_IZ_" + IntegerToString((long)pid))) return;
   for(int i = 0; i < ArraySize(IZPID); i++) if(IZPID[i] == pid) return;
   int n = ArraySize(IZPID);
   ArrayResize(IZPID, n + 1); ArrayResize(IZMG, n + 1); ArrayResize(IZYON, n + 1); ArrayResize(IZTP, n + 1);
   ArrayResize(IZKAP, n + 1); ArrayResize(IZGIR, n + 1); ArrayResize(IZSL, n + 1); ArrayResize(IZLOT, n + 1);
   IZPID[n] = pid; IZMG[n] = mg; IZYON[n] = yon; IZTP[n] = tp; IZKAP[n] = kapanis; IZGIR[n] = giris; IZSL[n] = sl; IZLOT[n] = lot;
}

void IzlemeSil(int i)
{
   int n = ArraySize(IZPID);
   for(int j = i + 1; j < n; j++)
   {
      IZPID[j - 1] = IZPID[j]; IZMG[j - 1] = IZMG[j]; IZYON[j - 1] = IZYON[j]; IZTP[j - 1] = IZTP[j];
      IZKAP[j - 1] = IZKAP[j]; IZGIR[j - 1] = IZGIR[j]; IZSL[j - 1] = IZSL[j]; IZLOT[j - 1] = IZLOT[j];
   }
   ArrayResize(IZPID, n - 1); ArrayResize(IZMG, n - 1); ArrayResize(IZYON, n - 1); ArrayResize(IZTP, n - 1);
   ArrayResize(IZKAP, n - 1); ArrayResize(IZGIR, n - 1); ArrayResize(IZSL, n - 1); ArrayResize(IZLOT, n - 1);
}

//--- pozisyonun bilgileri (HistorySelectByPosition)
bool PozisyonBilgi(ulong pid, ulong &mg, int &yon, double &tp, double &sl, double &lot, datetime &acilis, datetime &kapanis,
                   long &neden, double &para, double &girisF, double &cikisF)
{
   mg = 0; yon = 0; tp = 0.0; sl = 0.0; lot = 0.0; acilis = 0; kapanis = 0; neden = -1; para = 0.0; girisF = 0.0; cikisF = 0.0;
   if(!HistorySelectByPosition(pid)) return(false);
   int n = HistoryDealsTotal();
   ulong girisOrder = 0;
   bool cikisVar = false;
   for(int i = 0; i < n; i++)
   {
      ulong t = HistoryDealGetTicket(i);
      if(t == 0) continue;
      long en = HistoryDealGetInteger(t, DEAL_ENTRY);
      para += DealPara(t);
      if(en == DEAL_ENTRY_IN)
      {
         mg = (ulong)HistoryDealGetInteger(t, DEAL_MAGIC);
         yon = (HistoryDealGetInteger(t, DEAL_TYPE) == DEAL_TYPE_BUY) ? 1 : -1;
         acilis = (datetime)HistoryDealGetInteger(t, DEAL_TIME);
         girisF = HistoryDealGetDouble(t, DEAL_PRICE);
         tp = HistoryDealGetDouble(t, DEAL_TP);
         sl = HistoryDealGetDouble(t, DEAL_SL);
         lot = HistoryDealGetDouble(t, DEAL_VOLUME);
         girisOrder = (ulong)HistoryDealGetInteger(t, DEAL_ORDER);
      }
      else if(en == DEAL_ENTRY_OUT || en == DEAL_ENTRY_INOUT || en == DEAL_ENTRY_OUT_BY)
      {
         cikisVar = true;
         datetime ct = (datetime)HistoryDealGetInteger(t, DEAL_TIME);
         if(ct >= kapanis)
         {
            kapanis = ct;
            neden = HistoryDealGetInteger(t, DEAL_REASON);
            cikisF = HistoryDealGetDouble(t, DEAL_PRICE);
         }
      }
   }
   if((tp <= 0.0 || sl <= 0.0) && girisOrder > 0 && HistoryOrderSelect(girisOrder))
   {
      if(tp <= 0.0) tp = HistoryOrderGetDouble(girisOrder, ORDER_TP);
      if(sl <= 0.0) sl = HistoryOrderGetDouble(girisOrder, ORDER_SL);
   }
   return(cikisVar && mg != 0);
}

string NedenAd(long neden, ulong pid)
{
   if(neden == DEAL_REASON_SL) return("STOP");
   if(neden == DEAL_REASON_TP) return("TP");
   string r = NedenBul(pid);
   if(r != "") return(r);
   if(neden == DEAL_REASON_EXPERT) return("Robot kapattı");
   if(neden == DEAL_REASON_SO) return("Stop out");
   return("Elle kapatıldı");
}

void KapanisIsle(ulong pid)
{
   for(int i = 0; i < ArraySize(MPID); i++) if(MPID[i] == pid) return;
   ulong mg; int yon; double tp, sl, lot, para, gF, cF; datetime ac, kp; long neden;
   if(!PozisyonBilgi(pid, mg, yon, tp, sl, lot, ac, kp, neden, para, gF, cF)) return;
   string s; int g;
   if(!MagicBilgi(mg, s, g)) return;
   int n = ArraySize(MPID); ArrayResize(MPID, n + 1); MPID[n] = pid;
   string bas = s + "  " + YonYaz(yon) + "\n📍 Giriş: " + FiyatYaz(s, gF) + "\n";
   string m;
   if(neden == DEAL_REASON_TP)
      m = "✅ TP OLDU – " + GrupAd(g) + "\n" + bas + "🎯 TP: " + FiyatYaz(s, tp > 0.0 ? tp : cF) +
          "\n💰 Kâr: " + ParaYaz(para) + "\n🕐 " + TrSaat(kp);
   else if(neden == DEAL_REASON_SL)
   {
      m = "❌ STOP OLDU – " + GrupAd(g) + "\n" + bas + "🛑 Stop: " + FiyatYaz(s, sl > 0.0 ? sl : cF) +
          "\n💸 Zarar: " + ParaYaz(para) + "\n🕐 " + TrSaat(kp);
      if(tp > 0.0)
      {
         m += "\n👀 İzleniyor: 24 saat içinde TP seviyesine giderse haber vereceğim.";
         IzlemeEkle(pid, mg, yon, tp, kp, gF, sl > 0.0 ? sl : cF, lot);
      }
   }
   else
      m = "🔔 İŞLEM KAPANDI – " + GrupAd(g) + "\n" + bas + "🔚 Çıkış: " + FiyatYaz(s, cF) + "\n" +
          (para >= 0.0 ? "💰 Kâr: " : "💸 Zarar: ") + ParaYaz(para) + "\n🕐 " + TrSaat(kp) + "\nℹ️ Neden: " + NedenAd(neden, pid);
   TgEkle(m);
}

void IzlemeKontrol()
{
   datetime simdi = SunucuSimdi();
   for(int i = ArraySize(IZPID) - 1; i >= 0; i--)
   {
      string s; int g;
      if(!MagicBilgi(IZMG[i], s, g)) { IzlemeSil(i); continue; }
      long kapSn = (long)IZKAP[i];
      datetime bas = (datetime)(kapSn - kapSn % 60 + 60);   // stop dakikasindan sonraki dakika
      long bitSn = ((long)simdi < kapSn + IZLE_SN) ? (long)simdi : kapSn + IZLE_SN;
      datetime bit = (datetime)bitSn;
      MqlRates r[];
      ArraySetAsSeries(r, false);
      int n = (bit > bas) ? CopyRates(s, PERIOD_M1, bas, bit, r) : 0;
      datetime ulasti = 0;
      for(int j = 0; j < n; j++)
      {
         if(r[j].time > bit) break;
         if((IZYON[i] > 0 && r[j].high >= IZTP[i]) || (IZYON[i] < 0 && r[j].low <= IZTP[i])) { ulasti = r[j].time; break; }
      }
      string gv = "EAR_IZ_" + IntegerToString((long)IZPID[i]);
      string ust = s + "  " + YonYaz(IZYON[i]) + "\n";
      if(ulasti > 0)
      {
         double kar = 0.0;
         if(!OrderCalcProfit(IZYON[i] > 0 ? ORDER_TYPE_BUY : ORDER_TYPE_SELL, s, IZLOT[i], IZGIR[i], IZTP[i], kar)) kar = 0.0;
         TgEkle("👀 STOP SONRASI HEDEFE GİTTİ – " + GrupAd(g) + "\n" + ust +
                "📍 Giriş: " + FiyatYaz(s, IZGIR[i]) + "\n🛑 Stop: " + FiyatYaz(s, IZSL[i]) + "\n🎯 TP: " + FiyatYaz(s, IZTP[i]) +
                "\n🕐 " + TrSaat(ulasti) + "\nℹ️ Stop olmasaydı " + ParaYaz(kar) + " kâr olacaktı.");
         GlobalVariableSet(gv, 1);
         IzlemeSil(i);
      }
      else if((long)simdi - (long)IZKAP[i] >= IZLE_SN)
      {
         TgEkle("⌛ İZLEME BİTTİ – " + GrupAd(g) + "\n" + ust + "24 saat içinde TP seviyesine gitmedi. Stop doğruydu.");
         GlobalVariableSet(gv, 1);
         IzlemeSil(i);
      }
   }
}

//--- robot yeniden baslarsa son 24 saatin stoplari tekrar izlemeye alinir
void IzlemeYukle()
{
   datetime simdi = SunucuSimdi();
   ulong poz[], mgl[];
   PozisyonListesi(simdi - IZLE_SN - 6 * 86400, simdi + 86400, poz, mgl);
   ulong adaylar[];
   int n = HistoryDealsTotal();
   for(int i = 0; i < n; i++)
   {
      ulong t = HistoryDealGetTicket(i);
      if(t == 0) continue;
      if(HistoryDealGetInteger(t, DEAL_REASON) != DEAL_REASON_SL) continue;
      if((long)simdi - (long)HistoryDealGetInteger(t, DEAL_TIME) >= IZLE_SN) continue;
      ulong pid = (ulong)HistoryDealGetInteger(t, DEAL_POSITION_ID);
      if(ListedeBul(pid, poz) < 0) continue;
      int k = ArraySize(adaylar); ArrayResize(adaylar, k + 1); adaylar[k] = pid;
   }
   for(int i = 0; i < ArraySize(adaylar); i++)
   {
      ulong mg; int yon; double tp, sl, lot, para, gF, cF; datetime ac, kp; long neden;
      if(!PozisyonBilgi(adaylar[i], mg, yon, tp, sl, lot, ac, kp, neden, para, gF, cF)) continue;
      string s; int g;
      if(!MagicBilgi(mg, s, g) || neden != DEAL_REASON_SL) continue;
      IzlemeEkle(adaylar[i], mg, yon, tp, kp, gF, sl > 0.0 ? sl : cF, lot);
      int m = ArraySize(MPID); ArrayResize(MPID, m + 1); MPID[m] = adaylar[i];
   }
}

//+------------------------------------------------------------------+
//  GUN SONU RAPORU (Prag gece yarisi, limit sifirlaninca)
//+------------------------------------------------------------------+
string RaporBolum(int grup, const string &rS[], const int &rG[], const double &rP[], const bool &rC[], double &top)
{
   int sira[];
   ArrayResize(sira, 0);
   top = 0.0;
   for(int i = 0; i < ArraySize(rS); i++)
      if(rG[i] == grup && rC[i]) { int z = ArraySize(sira); ArrayResize(sira, z + 1); sira[z] = i; top += rP[i]; }
   for(int i = 0; i < ArraySize(sira); i++)
      for(int j = i + 1; j < ArraySize(sira); j++)
         if(rP[sira[j]] > rP[sira[i]]) { int tt = sira[i]; sira[i] = sira[j]; sira[j] = tt; }
   string m = "";
   for(int i = 0; i < ArraySize(sira); i++)
      m += (rP[sira[i]] >= 0.0 ? "✅ " : "❌ ") + rS[sira[i]] + "  " + ParaYaz(rP[sira[i]]) + "\n";
   return(m);
}

void GunSonuRaporu(datetime bas, datetime bit, int gunKey)
{
   ulong poz[], mgl[];
   PozisyonListesi(bas - 8 * 86400, bit + 3600, poz, mgl);
   string rS[]; int rG[]; double rP[]; bool rC[];
   double gunTop = 0.0;
   int n = HistoryDealsTotal();
   for(int i = 0; i < n; i++)
   {
      ulong t = HistoryDealGetTicket(i);
      if(t == 0) continue;
      datetime dt = (datetime)HistoryDealGetInteger(t, DEAL_TIME);
      if(dt < bas || dt >= bit) continue;
      long tip = HistoryDealGetInteger(t, DEAL_TYPE);
      if(tip != DEAL_TYPE_BUY && tip != DEAL_TYPE_SELL) continue;
      int li = ListedeBul((ulong)HistoryDealGetInteger(t, DEAL_POSITION_ID), poz);
      if(li < 0) continue;
      string s; int g;
      if(!MagicBilgi(mgl[li], s, g)) continue;
      double p = DealPara(t);
      gunTop += p;
      int j = -1;
      for(int q = 0; q < ArraySize(rS); q++) if(rS[q] == s && rG[q] == g) { j = q; break; }
      if(j < 0)
      {
         j = ArraySize(rS);
         ArrayResize(rS, j + 1); ArrayResize(rG, j + 1); ArrayResize(rP, j + 1); ArrayResize(rC, j + 1);
         rS[j] = s; rG[j] = g; rP[j] = 0.0; rC[j] = false;
      }
      rP[j] += p;
      long en = HistoryDealGetInteger(t, DEAL_ENTRY);
      if(en == DEAL_ENTRY_OUT || en == DEAL_ENTRY_INOUT || en == DEAL_ENTRY_OUT_BY) rC[j] = true;
   }
   double ictTop = 0.0, kesTop = 0.0;
   string ict = RaporBolum(1, rS, rG, rP, rC, ictTop);
   string kes = RaporBolum(0, rS, rG, rP, rC, kesTop);
   int y = gunKey / 10000, a = (gunKey / 100) % 100, g = gunKey % 100;
   string m = StringFormat("📊 GÜN SONU RAPORU – %02d.%02d.%04d\n\n", g, a, y);
   m += "🧠 ICT\n" + ict + "💰 ICT toplam: " + ParaYaz(ictTop) + "\n\n";
   m += "📈 KESİŞİM\n" + kes + "💰 Kesişim toplam: " + ParaYaz(kesTop) + "\n\n";
   m += "🏁 GENEL TOPLAM: " + ParaYaz(ictTop + kesTop) + "\n";
   m += "🛡️ Kalan günlük limit: " + TutarYaz(GunlukLimit + gunTop) + "\n";
   m += "💼 Bakiye: " + BakiyeYaz(AccountInfoDouble(ACCOUNT_BALANCE));
   TgEkle(m);
}

void RaporKontrol()
{
   datetime pragBas;
   int gunKey = PragGunKey(pragBas);
   if(!GlobalVariableCheck(GV_RAPOR)) { GlobalVariableSet(GV_RAPOR, gunKey); return; }
   int eski = (int)GlobalVariableGet(GV_RAPOR);
   if(eski == gunKey) return;
   GlobalVariableSet(GV_RAPOR, gunKey);
   GunSonuRaporu(pragBas - 86400, pragBas, eski);
}

//+------------------------------------------------------------------+
int OnInit()
{
   trade.SetDeviationInPoints(Kayma);
   GV_DUR   = "EAR_DUR_" + IntegerToString((long)Sihir);
   GV_RAPOR = "EAR_RAPOR_" + IntegerToString((long)Sihir);
   KurallariYukle();
   KesisimCikar();
   EkinYukle();

   ArrayResize(SEM, 0);
   string bulunamayan = "";
   for(int ki = 0; ki < ArraySize(K); ki++)
   {
      if(K[ki].tip == K_ASYA) asyaKi = ki;
      if(!K[ki].aktif) continue;
      string s = K[ki].s;
      if(!SymbolSelect(s, true)) { K[ki].aktif = false; bulunamayan += s + " "; PrintFormat("Sembol bulunamadi: %s", s); continue; }
      bool var = false;
      for(int i = 0; i < ArraySize(SEM); i++) if(SEM[i] == s) { var = true; break; }
      if(var) continue;
      int z = ArraySize(SEM);
      ArrayResize(SEM, z + 1); ArrayResize(SONBAR, z + 1); ArrayResize(HAZIR, z + 1);
      SEM[z] = s; SONBAR[z] = 0; HAZIR[z] = false;
   }
   for(int i = 0; i < ArraySize(SEM); i++)
   {
      datetime t0 = iTime(SEM[i], PERIOD_H1, 0);
      if(t0 > 0) { SONBAR[i] = t0; HAZIR[i] = true; }  // acilistaki mum atlanir
   }
   nKesKural = 0;
   for(int ki = 0; ki < ArraySize(K); ki++) if(K[ki].aktif) nKesKural++;

   nIctSem = 0;
   for(int ei = 0; ei < ArraySize(EK); ei++)
   {
      CEk *e = EK[ei];
      if(!e.aktif) continue;
      if(!SymbolSelect(e.s, true)) { e.aktif = false; bulunamayan += e.s + " "; PrintFormat("ICT sembol bulunamadi: %s", e.s); continue; }
      long cm = SymbolInfoInteger(e.s, SYMBOL_TRADE_CALC_MODE);
      e.forex = (cm == SYMBOL_CALC_MODE_FOREX || cm == SYMBOL_CALC_MODE_FOREX_NO_LEVERAGE);
      nIctSem++;
   }
   IzlemeYukle();
   PrintFormat("EAROBOT calisiyor. KESISIM %d sembol %d kural, ICT %d sembol, risk %.0f $, en fazla %.0f $, spread siniri %.0f $, gunluk limit %.0f $, magic %s / %s",
               ArraySize(SEM), nKesKural, nIctSem, RiskDolar, EnFazlaZarar, MakasSinir, GunlukLimit,
               IntegerToString((long)Sihir), IntegerToString((long)(Sihir + 1)));
   TgEkle(StringFormat("🤖 EAROBOT başladı\n📈 KESİŞİM: %d sembol, %d kural\n🧠 ICT: %d sembol\nRisk: %.0f $  Günlük limit: %.0f $%s",
                       ArraySize(SEM), nKesKural, nIctSem, RiskDolar, GunlukLimit,
                       bulunamayan == "" ? "" : "\nBulunamayan sembol: " + bulunamayan));
   EventSetTimer(1);
   LimitKontrol();
   return(INIT_SUCCEEDED);
}

void OnDeinit(const int reason)
{
   EventKillTimer();
   ObjectsDeleteAll(0, ON_EK);
   ChartRedraw(0);
   for(int i = 0; i < ArraySize(EK); i++) if(CheckPointer(EK[i]) == POINTER_DYNAMIC) delete EK[i];
   ArrayResize(EK, 0);
}

void OnTimer()
{
   LimitKontrol();
   RaporKontrol();
   TgGonder();
   if(SunucuSimdi() - sonIzleme >= 60) { sonIzleme = SunucuSimdi(); IzlemeKontrol(); }
   if(!TerminalInfoInteger(TERMINAL_TRADE_ALLOWED) || !MQLInfoInteger(MQL_TRADE_ALLOWED)) return;
   SureKontrol();
   EkEmirYonet();
   HayaletYonet();
   if(limitDurdu) return;
   for(int i = 0; i < ArraySize(SEM); i++) SembolDegerlendir(i);
   AsyaKontrol();
   EkinKontrol();
}

void OnTradeTransaction(const MqlTradeTransaction &trans, const MqlTradeRequest &request, const MqlTradeResult &result)
{
   if(trans.type != TRADE_TRANSACTION_DEAL_ADD) return;
   if(!HistoryDealSelect(trans.deal)) return;
   long en = HistoryDealGetInteger(trans.deal, DEAL_ENTRY);
   if(en != DEAL_ENTRY_OUT && en != DEAL_ENTRY_INOUT && en != DEAL_ENTRY_OUT_BY) return;
   ulong pid = (ulong)HistoryDealGetInteger(trans.deal, DEAL_POSITION_ID);
   if(PositionSelectByTicket(pid)) return;              // tamamen kapanmadi
   KapanisIsle(pid);
}

void OnTick()
{
   // her sey OnTimer icinde
}
//+------------------------------------------------------------------+
