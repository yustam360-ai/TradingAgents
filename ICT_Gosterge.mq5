//+------------------------------------------------------------------+
//|  ICT_Gosterge.mq5                                                |
//|  ICT 2022 MENTORSHIP MODELI - GOSTERGE (MT5 / MQL5)              |
//|  Islem ACMAZ. Sadece grafikte gosterir.                          |
//+------------------------------------------------------------------+
//  SATIS anlatiliyor, ALIS birebir tersi (dip supurulur, stop dibin altina).
//  Grafik hangi zaman diliminde olursa olsun hesap arka planda 1 dk veriden yapilir:
//   1) YON     : gunluk grafikte son 20 gunun araliginin ortasinin USTUNDE (premium) ise satis,
//                altinda (discount) ise alis.                                   (GunlukYonFiltresi)
//   2) LIKIDITE: onceki haftanin tepesi (PWH), onceki gunun tepesi (PDH),
//                Asya araligi tepesi (NY 19:00-24:00), Londra araligi tepesi (NY 02:00-05:00),
//                esit tepeler (15 dk grafikte iki swing tepe, farki 0.1 ATR'den az) (EQH).
//   3) SAAT    : FOREX  : Londra killzone NY 02:00-05:00, New York killzone NY 07:00-10:00
//                ENDEKS : NY 08:30-11:00 ve NY 13:30-16:00   (OTOMATIK: forex sembolde FOREX)
//   4) GECE YARISI ACILISI: satis sadece NY gece yarisi acilis fiyatinin USTUNDE. (Power of 3)
//   5) SUPURME : killzone icinde fiyat 2. maddedeki bir tepenin ustune cikar (5 dk mum).
//   6) MSS     : supurmeden sonra en fazla 20 mum icinde 5 dk mum son swing dibin ALTINDA kapanir.
//   7) DISPLACEMENT + FVG: kirilim bacaginda 3 mumluk bosluk (once 5 dk, yoksa 4,3,2,1 dk).
//                FVG bacagin %50'sinin USTUNDE (premium) olmali; birden coksa fiyata en yakin.
//   8) GIRIS   : FVG'nin alt kenarina SATIS LIMIT (kirilimdan sonraki 5 dk mum kapaninca).
//                Dolmazsa killzone bitiminden 30 dk sonra iptal; dolmadan TP gelirse iptal.
//   9) STOP    : TEPE  = supurmeyi yapan tepe + StopPayATR x ATR(5 dk)   (varsayilan)
//                FVG1  = FVG'nin 1. mumunun tepesi + 1 tick
//  10) TP      : 2R    = stop mesafesinin 2 kati (varsayilan)
//                ICT   = asagidaki ilk karsi likidite (bacak dibi, onceki gun/hafta dibi, Asya/Londra dibi),
//                        girise uzakligi en az MinRR x stop olan; yoksa islem yok
//  11) Acik islem NY 16:00'da kapanir.  Saatler: sunucu = New York + SunucuNY (FTMO: 7).
//  Grafikte: kirmizi = stop bolgesi, yesil = TP bolgesi, ortadaki cizgi = giris,
//            ok = sinyal, sari kutu = FVG, MSS cizgisi, supurulen seviye cizgisi.
//  Sag ust: son GecmisGun gunun islem / TP / STOP sayisi ve kural bazli teshis.
//  CsvYaz = true: islemler  MQL5\Files\ICT22_<sembol>.csv  dosyasina yazilir.
//  NOT: 90 gunluk 1 dk veri gerekir. Araclar > Secenekler > Grafikler >
//       "Grafikteki en fazla cubuk" = Sinirsiz yapin.
//+------------------------------------------------------------------+
#property copyright "ICT Gosterge"
#property version   "1.00"
#property indicator_chart_window
#property indicator_buffers 0
#property indicator_plots   0

enum TP_SECIM    { TP_2R = 0, TP_ICT = 1 };
enum STOP_SECIM  { STOP_TEPE = 0, STOP_FVG1 = 1 };
enum SEANS_SECIM { SEANS_OTOMATIK = 0, SEANS_FOREX = 1, SEANS_ENDEKS = 2 };

input int         GecmisGun          = 90;         // kac gun geriye taransin
input TP_SECIM    TPTuru             = TP_2R;      // TP: 2R ya da ICT hedefi
input double      MinRR              = 2.0;        // ICT hedefinde en az kac R
input STOP_SECIM  StopTuru           = STOP_TEPE;  // STOP: tepe+pay ya da FVG 1. mum
input double      StopPayATR         = 0.1;        // tepe stopunda pay (ATR kati)
input SEANS_SECIM Seans              = SEANS_OTOMATIK;
input bool        GeceYarisiFiltresi = true;       // 4. madde
input bool        GunlukYonFiltresi  = true;       // 1. madde
input int         GunlukAralik       = 20;         // yon icin kac gunluk aralik
input bool        FVGPremium         = true;       // FVG bacagin %50 ustunde olmali
input double      RiskDolar          = 15.0;       // panelde $ hesabi icin 1R
input int         SunucuNY           = 7;          // sunucu saati - New York saati
input bool        CsvYaz             = true;       // islemleri dosyaya yaz
input bool        SeviyeGoster       = true;       // supurulen seviye cizgisi
input bool        MSSGoster          = true;       // MSS cizgisi
input bool        FVGGoster          = true;       // FVG kutusu
input color       RenkStop           = C'255,205,210';
input color       RenkTP             = C'178,235,220';
input color       RenkFVG            = C'255,236,179';
input int         YaziBoyu           = 9;

#define ON "ICT22_"

struct Seri
  {
   datetime          t[];
   double            o[];
   double            h[];
   double            l[];
   double            c[];
   int               n;
  };

struct Seviye
  {
   double            p;        // gorunum fiyati (satista tepe, alista -dip)
   datetime          bil;      // bilinme ani
   string            ad;
   bool              acik;
  };

struct Islem
  {
   int               yon;      // -1 satis, +1 alis
   int               pencere;  // 0: 1. killzone, 1: 2. killzone
   datetime          tSinyal, tDolum, tCikis, tFvg, tSwing, tMss, tSup, tSevBil;
   double            E, S, TP, R, fvgUst, fvgAlt, mssFiyat, supFiyat, sevFiyat;
   int               sonuc;    // 1 TP, -1 STOP, 0 SURE, 2 ACIK, 3 BEKLIYOR, 4 DOLMADI
   string            seviye;
  };

Seri   M1, M5, M15, MK[4];      // MK: 4,3,2,1 dk (1 dk = M1)
double ATR5[], ATR15[];
MqlRates D1[], W1[];
Islem  ISL[];
int    nIsl = 0;
datetime sonHesap = 0;
bool   forexMi = true;

//+------------------------------------------------------------------+
double V(double p, int y)            { return y < 0 ? p : -p; }
double VH(const Seri &s, int i, int y) { return y < 0 ? s.h[i] : -s.l[i]; }
double VL(const Seri &s, int i, int y) { return y < 0 ? s.l[i] : -s.h[i]; }
double VC(const Seri &s, int i, int y) { return y < 0 ? s.c[i] : -s.c[i]; }
double VO(const Seri &s, int i, int y) { return y < 0 ? s.o[i] : -s.o[i]; }

int Ara(const Seri &s, datetime t)    // t'den buyuk-esit ilk indeks
  {
   int lo = 0, hi = s.n;
   while(lo < hi)
     {
      int m = (lo + hi) / 2;
      if(s.t[m] < t) lo = m + 1;
      else hi = m;
     }
   return lo;
  }

void Boyut(Seri &s, int n)
  {
   ArrayResize(s.t, n); ArrayResize(s.o, n); ArrayResize(s.h, n); ArrayResize(s.l, n); ArrayResize(s.c, n);
  }

void Kur(const Seri &m, int K, Seri &s)
  {
   Boyut(s, m.n);
   s.n = 0;
   long sn = K * 60;
   for(int i = 0; i < m.n; i++)
     {
      datetime b = (datetime)((long)m.t[i] - (long)m.t[i] % sn);
      if(s.n == 0 || s.t[s.n - 1] != b)
        {
         s.t[s.n] = b; s.o[s.n] = m.o[i]; s.h[s.n] = m.h[i]; s.l[s.n] = m.l[i]; s.c[s.n] = m.c[i];
         s.n++;
        }
      else
        {
         int k = s.n - 1;
         if(m.h[i] > s.h[k]) s.h[k] = m.h[i];
         if(m.l[i] < s.l[k]) s.l[k] = m.l[i];
         s.c[k] = m.c[i];
        }
     }
   Boyut(s, s.n);
  }

void ATRHesap(const Seri &s, double &a[], int p)
  {
   ArrayResize(a, s.n);
   double top = 0;
   double tr[];
   ArrayResize(tr, s.n);
   for(int i = 0; i < s.n; i++)
     {
      double x = s.h[i] - s.l[i];
      if(i > 0)
        {
         x = MathMax(x, MathAbs(s.h[i] - s.c[i - 1]));
         x = MathMax(x, MathAbs(s.l[i] - s.c[i - 1]));
        }
      tr[i] = x;
      top += x;
      if(i >= p) top -= tr[i - p];
      a[i] = top / MathMin(i + 1, p);
     }
  }

double MaxVH(const Seri &s, int a, int b, int y)   // [a,b) en yuksek gorunum
  {
   double m = -DBL_MAX;
   for(int i = a; i < b; i++) m = MathMax(m, VH(s, i, y));
   return m;
  }

double MinVL(const Seri &s, int a, int b, int y)
  {
   double m = DBL_MAX;
   for(int i = a; i < b; i++) m = MathMin(m, VL(s, i, y));
   return m;
  }

//+------------------------------------------------------------------+
bool VeriYukle()
  {
   datetime bit = TimeCurrent() + 86400;
   datetime bas = bit - (datetime)((GecmisGun + 6) * 86400);
   MqlRates r[];
   ArraySetAsSeries(r, false);
   int n = CopyRates(_Symbol, PERIOD_M1, bas, bit, r);
   if(n < 1000) return false;
   Boyut(M1, n);
   M1.n = n;
   for(int i = 0; i < n; i++)
     { M1.t[i] = r[i].time; M1.o[i] = r[i].open; M1.h[i] = r[i].high; M1.l[i] = r[i].low; M1.c[i] = r[i].close; }
   Kur(M1, 5, M5);
   Kur(M1, 15, M15);
   Kur(M1, 4, MK[0]);
   Kur(M1, 3, MK[1]);
   Kur(M1, 2, MK[2]);
   Kur(M1, 1, MK[3]);
   ATRHesap(M5, ATR5, 14);
   ATRHesap(M15, ATR15, 14);
   ArraySetAsSeries(D1, false);
   ArraySetAsSeries(W1, false);
   if(CopyRates(_Symbol, PERIOD_D1, bas - (datetime)((GunlukAralik + 10) * 86400), bit, D1) < 5) return false;
   if(CopyRates(_Symbol, PERIOD_W1, bas - 30 * 86400, bit, W1) < 3) return false;
   return true;
  }

//+------------------------------------------------------------------+
int SonD1(datetime D)         // D'den once biten son gunluk mum
  {
   int k = -1;
   for(int i = 0; i < ArraySize(D1); i++) if(D1[i].time < D) k = i;
   return k;
  }

void Ekle(Seviye &a[], int &n, double p, datetime bil, string ad)
  {
   ArrayResize(a, n + 1);
   a[n].p = p; a[n].bil = bil; a[n].ad = ad; a[n].acik = true;
   n++;
  }

int Seviyeler(datetime D, datetime nyMid, int y, Seviye &sv[], double &karsi[], datetime &karsiBil[])
  {
   int n = 0;
   ArrayResize(sv, 0);
   ArrayResize(karsi, 0);
   ArrayResize(karsiBil, 0);
   int nk = 0;
   string u = y < 0 ? "H" : "L";
   int d = SonD1(D);
   if(d >= 0)
     {
      Ekle(sv, n, y < 0 ? D1[d].high : -D1[d].low, D, "PD" + u);
      ArrayResize(karsi, nk + 1); ArrayResize(karsiBil, nk + 1);
      karsi[nk] = y < 0 ? D1[d].low : -D1[d].high; karsiBil[nk] = D; nk++;
     }
   int w = -1;
   for(int i = 0; i < ArraySize(W1); i++) if(W1[i].time <= D) w = i;
   if(w >= 1)
     {
      Ekle(sv, n, y < 0 ? W1[w - 1].high : -W1[w - 1].low, D, "PW" + u);
      ArrayResize(karsi, nk + 1); ArrayResize(karsiBil, nk + 1);
      karsi[nk] = y < 0 ? W1[w - 1].low : -W1[w - 1].high; karsiBil[nk] = D; nk++;
     }
   // Asya NY 19:00-24:00, Londra NY 02:00-05:00
   datetime aB = nyMid - 5 * 3600, aS = nyMid, lB = nyMid + 2 * 3600, lS = nyMid + 5 * 3600;
   int i0 = Ara(M1, aB), i1 = Ara(M1, aS);
   if(i1 > i0)
     {
      Ekle(sv, n, MaxVH(M1, i0, i1, y), aS, "ASYA");
      ArrayResize(karsi, nk + 1); ArrayResize(karsiBil, nk + 1);
      karsi[nk] = MinVL(M1, i0, i1, y); karsiBil[nk] = aS; nk++;
     }
   i0 = Ara(M1, lB); i1 = Ara(M1, lS);
   if(i1 > i0)
     {
      Ekle(sv, n, MaxVH(M1, i0, i1, y), lS, "LON");
      ArrayResize(karsi, nk + 1); ArrayResize(karsiBil, nk + 1);
      karsi[nk] = MinVL(M1, i0, i1, y); karsiBil[nk] = lS; nk++;
     }
   // esit tepeler: 15 dk, son 3 gun, 3 mumluk swing
   int s0 = Ara(M15, D - 3 * 86400), s1 = Ara(M15, nyMid + 16 * 3600);
   int sw[];
   int ns = 0;
   for(int k = MathMax(s0, 1); k < MathMin(s1, M15.n - 1); k++)
      if(VH(M15, k, y) > VH(M15, k - 1, y) && VH(M15, k, y) > VH(M15, k + 1, y))
        { ArrayResize(sw, ns + 1); sw[ns++] = k; }
   for(int b = 1; b < ns; b++)
      for(int a = 0; a < b; a++)
        {
         int ka = sw[a], kb = sw[b];
         if(MathAbs(VH(M15, ka, y) - VH(M15, kb, y)) <= 0.1 * ATR15[kb])
           {
            // a ile b arasinda fiyat bu seviyeyi gecmemis olmali
            double ust = MathMax(VH(M15, ka, y), VH(M15, kb, y));
            if(MaxVH(M15, ka + 1, kb, y) < ust)
               Ekle(sv, n, ust, M15.t[kb + 1] + 15 * 60, "EQ" + u);
           }
        }
   return n;
  }

//+------------------------------------------------------------------+
bool FVGBul(datetime tBas, datetime tKarar, double fiyat, double bacakDip, double bacakTepe, int y,
            double &alt, double &ust, double &ilkTepe, datetime &tA)
  {
   for(int q = 0; q < 5; q++)
     {
      int K = (q == 0 ? 5 : 4 - (q - 1));            // 5,4,3,2,1
      int a0, a1;
      double enAlt = DBL_MAX;
      bool bulundu = false;
      if(K == 5)
        {
         a0 = Ara(M5, tBas); a1 = Ara(M5, tKarar - 5 * 60 + 1);
         for(int a = a0; a + 2 < M5.n; a++)
           {
            int c = a + 2;
            if(M5.t[c] + 5 * 60 > tKarar) break;
            if(VL(M5, a, y) > VH(M5, c, y))
              {
               double b = VH(M5, c, y), t = VL(M5, a, y);
               if(fiyat >= b) continue;
               int e1 = Ara(M5, tKarar);
               if(c + 1 < e1 && MaxVH(M5, c + 1, e1, y) >= b) continue;
               if(FVGPremium && b < bacakDip + 0.5 * (bacakTepe - bacakDip)) continue;
               if(b < enAlt)
                 { enAlt = b; alt = b; ust = t; ilkTepe = VH(M5, a, y); tA = M5.t[a]; bulundu = true; }
              }
           }
        }
      else
        {
         int ix = 4 - K;                                // K=4 ->0, 3->1, 2->2, 1->3
         a0 = Ara(MK[ix], tBas); a1 = Ara(MK[ix], tKarar);
         for(int a = a0; a + 2 < a1; a++)
           {
            int c = a + 2;
            if(MK[ix].t[c] + K * 60 > tKarar) break;
            if(VL(MK[ix], a, y) > VH(MK[ix], c, y))
              {
               double b = VH(MK[ix], c, y), t = VL(MK[ix], a, y);
               if(fiyat >= b) continue;
               if(c + 1 < a1 && MaxVH(MK[ix], c + 1, a1, y) >= b) continue;
               if(FVGPremium && b < bacakDip + 0.5 * (bacakTepe - bacakDip)) continue;
               if(b < enAlt)
                 { enAlt = b; alt = b; ust = t; ilkTepe = VH(MK[ix], a, y); tA = MK[ix].t[a]; bulundu = true; }
              }
           }
        }
      if(bulundu) return true;
     }
   return false;
  }

//+------------------------------------------------------------------+
void Simule(Islem &x, double E, double S, double TP, datetime tIptal, datetime tKapanis, int y)
  {
   int a0 = Ara(M1, x.tSinyal);
   int c1 = Ara(M1, tIptal);
   int z1 = Ara(M1, tKapanis);
   double r = S - E;
   int f = -1;
   for(int m = a0; m < c1 && m < M1.n; m++)
     {
      if(VL(M1, m, y) <= TP && VH(M1, m, y) < E) { x.sonuc = 4; return; }   // dolmadan TP
      if(VH(M1, m, y) >= E) { f = m; break; }
     }
   if(f < 0)
     {
      x.sonuc = (M1.n > 0 && M1.t[M1.n - 1] < tIptal) ? 3 : 4;
      x.tDolum = x.tSinyal;
      x.tCikis = x.sonuc == 3 ? TimeCurrent() : tIptal;
      return;
     }
   x.tDolum = M1.t[f];
   for(int m = f; m < z1 && m < M1.n; m++)
     {
      if(VH(M1, m, y) >= S) { x.sonuc = -1; x.R = -1.0; x.tCikis = M1.t[m]; return; }
      if(m > f && VL(M1, m, y) <= TP) { x.sonuc = 1; x.R = (E - TP) / r; x.tCikis = M1.t[m]; return; }
     }
   int son = MathMin(z1, M1.n) - 1;
   x.R = (E - VC(M1, son, y)) / r;
   if(M1.t[M1.n - 1] < tKapanis - 60) { x.sonuc = 2; x.tCikis = TimeCurrent(); }
   else { x.sonuc = 0; x.tCikis = M1.t[son] + 60; }
  }

//+------------------------------------------------------------------+
void GunTara(datetime D)
  {
   datetime nyMid = D + SunucuNY * 3600;
   datetime kapanis = nyMid + 16 * 3600;
   datetime pB[2], pS[2];
   if(forexMi)
     { pB[0] = nyMid + 2 * 3600; pS[0] = nyMid + 5 * 3600; pB[1] = nyMid + 7 * 3600; pS[1] = nyMid + 10 * 3600; }
   else
     { pB[0] = nyMid + 8 * 3600 + 1800; pS[0] = nyMid + 11 * 3600; pB[1] = nyMid + 13 * 3600 + 1800; pS[1] = nyMid + 16 * 3600; }
   int im = Ara(M1, nyMid);
   if(im >= M1.n) return;
   double gYari = 0;
   bool gOk = false;
   if(GunlukYonFiltresi)
     {
      int d = SonD1(D);
      if(d >= GunlukAralik - 1)
        {
         double hh = -DBL_MAX, ll = DBL_MAX;
         for(int k = d - GunlukAralik + 1; k <= d; k++) { hh = MathMax(hh, D1[k].high); ll = MathMin(ll, D1[k].low); }
         gYari = (hh + ll) / 2.0; gOk = true;
        }
     }
   for(int y = -1; y <= 1; y += 2)
     {
      Seviye sv[];
      double karsi[];
      datetime karsiBil[];
      int nsv = Seviyeler(D, nyMid, y, sv, karsi, karsiBil);
      double geceAcilis = VO(M1, im, y);
      for(int p = 0; p < 2; p++)
        {
         datetime ws = pB[p], we = pS[p];
         datetime iptal = (we + 1800 < kapanis) ? we + 1800 : kapanis;
         // pencere basinda acik seviyeler
         for(int k = 0; k < nsv; k++)
           {
            sv[k].acik = false;
            if(sv[k].bil > ws) continue;
            int a = Ara(M1, sv[k].bil), b = Ara(M1, ws);
            if(b <= a || MaxVH(M1, a, b, y) <= sv[k].p) sv[k].acik = true;
           }
         int i0 = Ara(M5, ws), i1 = Ara(M5, we);
         int i = i0;
         while(i < i1 && i < M5.n)
           {
            if(M5.t[i] + 300 > we) break;
            string vurulan = "";
            double sevP = 0;
            datetime sevB = 0;
            for(int k = 0; k < nsv; k++)
               if(sv[k].acik && VH(M5, i, y) > sv[k].p)
                 {
                  sv[k].acik = false;
                  if(vurulan == "" || sv[k].p > sevP) { sevP = sv[k].p; sevB = sv[k].bil; }
                  vurulan += (vurulan == "" ? "" : "+") + sv[k].ad;
                 }
            if(vurulan == "") { i++; continue; }
            // son dogrulanmis swing dip (3 mum)
            int f = -1;
            for(int k = i - 1; k >= MathMax(1, i - 60); k--)
               if(k + 1 <= i && VL(M5, k, y) < VL(M5, k - 1, y) && VL(M5, k, y) < VL(M5, k + 1, y)) { f = k; break; }
            if(f < 0) { i++; continue; }
            double ref = VL(M5, f, y);
            int jk = -1;
            for(int j = i + 1; j <= i + 20 && j < M5.n; j++)
              {
               if(M5.t[j] + 300 > iptal) break;
               if(VC(M5, j, y) < ref) { jk = j; break; }
              }
            if(jk < 0) { i++; continue; }
            int dec = jk + 1;
            if(dec >= M5.n) break;                               // canli: karar mumu kapanmadi
            datetime tKarar = M5.t[dec] + 300;
            if(tKarar > iptal) break;
            int shi = i;
            for(int k = i; k <= jk; k++) if(VH(M5, k, y) > VH(M5, shi, y)) shi = k;
            double tepe = MaxVH(M5, i, dec + 1, y);
            double dip = MinVL(M5, shi, dec + 1, y);
            double fiyat = VC(M5, dec, y);
            double alt = 0, ust = 0, ilkTepe = 0;
            datetime tA = 0;
            if(!FVGBul(M5.t[shi], tKarar, fiyat, dip, tepe, y, alt, ust, ilkTepe, tA)) { i = jk + 1; continue; }
            double E = alt;
            if(GeceYarisiFiltresi && !(E > geceAcilis)) { i = dec; continue; }
            if(GunlukYonFiltresi && gOk && !(E > V(gYari, y))) { i = dec; continue; }
            double S = StopTuru == STOP_TEPE ? tepe + StopPayATR * ATR5[dec] : ilkTepe + _Point;
            double r = S - E;
            if(r <= 0) { i = dec; continue; }
            double TP;
            if(TPTuru == TP_2R) TP = E - 2.0 * r;
            else
              {
               TP = -DBL_MAX;
               double adaylar[];
               int na = 0;
               ArrayResize(adaylar, 1); adaylar[0] = dip; na = 1;
               for(int k = 0; k < ArraySize(karsi); k++)
                  if(karsiBil[k] <= tKarar) { ArrayResize(adaylar, na + 1); adaylar[na++] = karsi[k]; }
               for(int k = 0; k < na; k++)
                  if(E - adaylar[k] >= MinRR * r && adaylar[k] > TP) TP = adaylar[k];
               if(TP == -DBL_MAX) { i = dec; continue; }
              }
            Islem x;
            x.R = 0; x.sonuc = 4; x.tDolum = 0; x.tCikis = 0;
            x.yon = y; x.pencere = p; x.tSinyal = tKarar; x.seviye = vurulan;
            x.E = V(E, y); x.S = V(S, y); x.TP = V(TP, y);
            x.tFvg = tA; x.fvgUst = V(ust, y); x.fvgAlt = V(alt, y);
            x.tSwing = M5.t[f]; x.mssFiyat = V(ref, y); x.tMss = M5.t[jk] + 300;
            x.tSup = M5.t[i]; x.supFiyat = V(VH(M5, i, y), y);
            x.tSevBil = sevB; x.sevFiyat = V(sevP, y);
            Simule(x, E, S, TP, iptal, kapanis, y);
            ArrayResize(ISL, nIsl + 1);
            ISL[nIsl++] = x;
            i = dec;
           }
        }
     }
  }

//+------------------------------------------------------------------+
void Dikdortgen(string ad, datetime t1, double p1, datetime t2, double p2, color c, bool dolu)
  {
   ObjectCreate(0, ad, OBJ_RECTANGLE, 0, t1, p1, t2, p2);
   ObjectSetInteger(0, ad, OBJPROP_COLOR, c);
   ObjectSetInteger(0, ad, OBJPROP_FILL, dolu);
   ObjectSetInteger(0, ad, OBJPROP_BACK, true);
   ObjectSetInteger(0, ad, OBJPROP_SELECTABLE, false);
   ObjectSetInteger(0, ad, OBJPROP_HIDDEN, true);
  }

void Cizgi(string ad, datetime t1, double p1, datetime t2, double p2, color c, int stil, int kalin)
  {
   ObjectCreate(0, ad, OBJ_TREND, 0, t1, p1, t2, p2);
   ObjectSetInteger(0, ad, OBJPROP_COLOR, c);
   ObjectSetInteger(0, ad, OBJPROP_STYLE, stil);
   ObjectSetInteger(0, ad, OBJPROP_WIDTH, kalin);
   ObjectSetInteger(0, ad, OBJPROP_RAY_RIGHT, false);
   ObjectSetInteger(0, ad, OBJPROP_SELECTABLE, false);
   ObjectSetInteger(0, ad, OBJPROP_HIDDEN, true);
  }

void Yazi(string ad, datetime t, double p, string s, color c, ENUM_ANCHOR_POINT an)
  {
   ObjectCreate(0, ad, OBJ_TEXT, 0, t, p);
   ObjectSetString(0, ad, OBJPROP_TEXT, s);
   ObjectSetInteger(0, ad, OBJPROP_COLOR, c);
   ObjectSetInteger(0, ad, OBJPROP_FONTSIZE, YaziBoyu - 1);
   ObjectSetInteger(0, ad, OBJPROP_ANCHOR, an);
   ObjectSetInteger(0, ad, OBJPROP_SELECTABLE, false);
   ObjectSetInteger(0, ad, OBJPROP_HIDDEN, true);
  }

void Ciz(int k, const Islem &x)
  {
   string n = ON + IntegerToString(k) + "_";
   bool sat = x.yon < 0;
   datetime t1 = x.tDolum, t2 = x.tCikis;
   if(t2 <= t1) t2 = t1 + 60;
   Dikdortgen(n + "stop", t1, x.E, t2, x.S, RenkStop, true);
   Dikdortgen(n + "tp", t1, x.E, t2, x.TP, RenkTP, true);
   Cizgi(n + "giris", t1, x.E, t2, x.E, clrDimGray, STYLE_SOLID, 1);
   string s;
   color c = clrDimGray;
   if(x.sonuc == 1)       { s = StringFormat("TP +%.1fR", x.R); c = clrSeaGreen; }
   else if(x.sonuc == -1) { s = "STOP -1R"; c = clrCrimson; }
   else if(x.sonuc == 0)  { s = StringFormat("SURE %+.1fR", x.R); }
   else if(x.sonuc == 2)  { s = StringFormat("ACIK %+.1fR", x.R); c = clrRoyalBlue; }
   else                   { s = "BEKLIYOR"; c = clrRoyalBlue; }
   Yazi(n + "sonuc", t2, x.E, " " + s, c, ANCHOR_LEFT);
   // sinyal oku
   ObjectCreate(0, n + "ok", OBJ_ARROW, 0, x.tSinyal, sat ? MathMax(x.S, x.supFiyat) : MathMin(x.S, x.supFiyat));
   ObjectSetInteger(0, n + "ok", OBJPROP_ARROWCODE, sat ? 234 : 233);
   ObjectSetInteger(0, n + "ok", OBJPROP_COLOR, sat ? clrCrimson : clrSeaGreen);
   ObjectSetInteger(0, n + "ok", OBJPROP_ANCHOR, sat ? ANCHOR_BOTTOM : ANCHOR_TOP);
   ObjectSetInteger(0, n + "ok", OBJPROP_SELECTABLE, false);
   ObjectSetInteger(0, n + "ok", OBJPROP_HIDDEN, true);
   if(FVGGoster)
      Dikdortgen(n + "fvg", x.tFvg, x.fvgUst, x.tSinyal, x.fvgAlt, RenkFVG, true);
   if(MSSGoster)
     {
      Cizgi(n + "mss", x.tSwing, x.mssFiyat, x.tMss, x.mssFiyat, clrDarkOrange, STYLE_DOT, 1);
      Yazi(n + "mssy", x.tSwing, x.mssFiyat, "MSS", clrDarkOrange, sat ? ANCHOR_LEFT_UPPER : ANCHOR_LEFT_LOWER);
     }
   if(SeviyeGoster && x.tSevBil > 0)
     {
      datetime b = (x.tSevBil > x.tSup - 12 * 3600) ? x.tSevBil : x.tSup - 12 * 3600;
      Cizgi(n + "sev", b, x.sevFiyat, x.tSup, x.sevFiyat, clrSlateGray, STYLE_DASH, 1);
      Yazi(n + "sevy", b, x.sevFiyat, x.seviye, clrSlateGray, sat ? ANCHOR_LEFT_LOWER : ANCHOR_LEFT_UPPER);
     }
  }

//+------------------------------------------------------------------+
void Etiket(int satir, string s, color c)
  {
   string ad = ON + "panel" + IntegerToString(satir);
   ObjectCreate(0, ad, OBJ_LABEL, 0, 0, 0);
   ObjectSetInteger(0, ad, OBJPROP_CORNER, CORNER_RIGHT_UPPER);
   ObjectSetInteger(0, ad, OBJPROP_ANCHOR, ANCHOR_RIGHT_UPPER);
   ObjectSetInteger(0, ad, OBJPROP_XDISTANCE, 10);
   ObjectSetInteger(0, ad, OBJPROP_YDISTANCE, 20 + satir * (YaziBoyu + 8));
   ObjectSetString(0, ad, OBJPROP_TEXT, s);
   ObjectSetString(0, ad, OBJPROP_FONT, "Consolas");
   ObjectSetInteger(0, ad, OBJPROP_FONTSIZE, YaziBoyu);
   ObjectSetInteger(0, ad, OBJPROP_COLOR, c);
   ObjectSetInteger(0, ad, OBJPROP_SELECTABLE, false);
   ObjectSetInteger(0, ad, OBJPROP_HIDDEN, true);
  }

string Oran(int n, int w) { return n > 0 ? StringFormat("%d islem %%%.0f", n, 100.0 * w / n) : "0 islem"; }

void Panel()
  {
   int n = 0, tp = 0, st = 0, su = 0, dl = 0, ac = 0, w = 0, hizli = 0;
   double R = 0;
   int pn[2] = {0, 0}, pw[2] = {0, 0}, yn[2] = {0, 0}, yw[2] = {0, 0};
   string sevAd[] = {"PD", "PW", "ASYA", "LON", "EQ"};
   int sn[5] = {0, 0, 0, 0, 0}, swn[5] = {0, 0, 0, 0, 0};
   for(int k = 0; k < nIsl; k++)
     {
      Islem x = ISL[k];
      if(x.sonuc == 4) { dl++; continue; }
      if(x.sonuc == 2 || x.sonuc == 3) { ac++; continue; }
      n++;
      R += x.R;
      bool kaz = x.R > 0;
      if(kaz) w++;
      if(x.sonuc == 1) tp++;
      else if(x.sonuc == -1) { st++; if(x.tCikis - x.tDolum <= 15 * 60) hizli++; }
      else su++;
      pn[x.pencere]++; if(kaz) pw[x.pencere]++;
      int yi = x.yon > 0 ? 0 : 1;
      yn[yi]++; if(kaz) yw[yi]++;
      for(int q = 0; q < 5; q++)
         if(StringFind(x.seviye, sevAd[q]) >= 0) { sn[q]++; if(kaz) swn[q]++; }
     }
   string p1 = forexMi ? "Londra KZ" : "NY sabah", p2 = forexMi ? "NY KZ" : "NY ogleden s.";
   int s = 0;
   Etiket(s++, StringFormat("ICT 2022 - son %d gun  (%s)", GecmisGun, forexMi ? "FOREX saatleri" : "ENDEKS saatleri"), clrBlack);
   Etiket(s++, StringFormat("Islem %d | TP %d | STOP %d | SURE %d", n, tp, st, su), clrBlack);
   Etiket(s++, StringFormat("Basari %%%.1f | Net %+.1f R | %+.0f $", n > 0 ? 100.0 * w / n : 0.0, R, R * RiskDolar),
          R >= 0 ? clrSeaGreen : clrCrimson);
   Etiket(s++, StringFormat("Dolmayan emir %d | Acik/bekleyen %d", dl, ac), clrDimGray);
   Etiket(s++, StringFormat("TP: %s | STOP: %s", TPTuru == TP_2R ? "2R" : "ICT hedefi", StopTuru == STOP_TEPE ? "tepe+pay" : "FVG 1. mum"), clrDimGray);
   Etiket(s++, "--- teshis ---", clrDimGray);
   Etiket(s++, StringFormat("%s: %s | %s: %s", p1, Oran(pn[0], pw[0]), p2, Oran(pn[1], pw[1])), clrDimGray);
   Etiket(s++, StringFormat("ALIS: %s | SATIS: %s", Oran(yn[0], yw[0]), Oran(yn[1], yw[1])), clrDimGray);
   Etiket(s++, StringFormat("PD: %s | PW: %s", Oran(sn[0], swn[0]), Oran(sn[1], swn[1])), clrDimGray);
   Etiket(s++, StringFormat("ASYA: %s | LON: %s | EQ: %s", Oran(sn[2], swn[2]), Oran(sn[3], swn[3]), Oran(sn[4], swn[4])), clrDimGray);
   if(st > 0)
      Etiket(s++, StringFormat("Stoplarin %%%.0f'i girdikten sonraki 15 dk icinde", 100.0 * hizli / st), clrDimGray);
   string not1 = "";
   if(pn[0] >= 5 && pn[1] >= 5)
     {
      double o1 = 100.0 * pw[0] / pn[0], o2 = 100.0 * pw[1] / pn[1];
      if(MathAbs(o1 - o2) >= 10) not1 = StringFormat("%s daha iyi (%%%.0f / %%%.0f)", o1 > o2 ? p1 : p2, MathMax(o1, o2), MathMin(o1, o2));
     }
   if(not1 != "") Etiket(s++, not1, clrDimGray);
  }

void CsvKaydet()
  {
   int h = FileOpen("ICT22_" + _Symbol + ".csv", FILE_WRITE | FILE_CSV | FILE_ANSI, ';');
   if(h == INVALID_HANDLE) return;
   FileWrite(h, "sinyal", "dolum", "cikis", "yon", "seans", "supurulen", "giris", "stop", "tp", "sonuc", "R", "dolar");
   string snc[] = {"SURE", "TP", "ACIK", "BEKLIYOR", "DOLMADI"};
   for(int k = 0; k < nIsl; k++)
     {
      Islem x = ISL[k];
      string s = x.sonuc == -1 ? "STOP" : snc[x.sonuc];
      FileWrite(h, TimeToString(x.tSinyal), TimeToString(x.tDolum), TimeToString(x.tCikis), x.yon > 0 ? "AL" : "SAT",
                x.pencere, x.seviye, DoubleToString(x.E, _Digits), DoubleToString(x.S, _Digits),
                DoubleToString(x.TP, _Digits), s, DoubleToString(x.R, 2), DoubleToString(x.R * RiskDolar, 2));
     }
   FileClose(h);
  }

//+------------------------------------------------------------------+
void Temizle() { ObjectsDeleteAll(0, ON); }

bool Hesapla()
  {
   if(!VeriYukle()) return false;
   nIsl = 0;
   ArrayResize(ISL, 0);
   datetime son = M1.t[M1.n - 1];
   datetime bas = son - (datetime)(GecmisGun * 86400);
   datetime D = bas - bas % 86400;
   for(; D <= son; D += 86400)
     {
      MqlDateTime dt;
      TimeToStruct(D, dt);
      if(dt.day_of_week == 0 || dt.day_of_week == 6) continue;
      GunTara(D);
     }
   Temizle();
   for(int k = 0; k < nIsl; k++)
      if(ISL[k].sonuc != 4) Ciz(k, ISL[k]);
   Panel();
   if(CsvYaz) CsvKaydet();
   ChartRedraw();
   return true;
  }

//+------------------------------------------------------------------+
int OnInit()
  {
   if(Seans == SEANS_OTOMATIK)
     {
      ENUM_SYMBOL_CALC_MODE m = (ENUM_SYMBOL_CALC_MODE)SymbolInfoInteger(_Symbol, SYMBOL_TRADE_CALC_MODE);
      forexMi = (m == SYMBOL_CALC_MODE_FOREX || m == SYMBOL_CALC_MODE_FOREX_NO_LEVERAGE);
     }
   else forexMi = (Seans == SEANS_FOREX);
   EventSetTimer(20);
   sonHesap = 0;
   return INIT_SUCCEEDED;
  }

void OnDeinit(const int reason)
  {
   EventKillTimer();
   Temizle();
  }

void OnTimer()
  {
   datetime m5 = TimeCurrent() - TimeCurrent() % 300;
   if(m5 != sonHesap)
      if(Hesapla()) sonHesap = m5;
  }

int OnCalculate(const int rates_total, const int prev_calculated, const datetime &time[], const double &open[],
                const double &high[], const double &low[], const double &close[], const long &tick_volume[],
                const long &volume[], const int &spread[])
  {
   if(sonHesap == 0)
      if(Hesapla()) sonHesap = TimeCurrent() - TimeCurrent() % 300;
   return rates_total;
  }
//+------------------------------------------------------------------+
