//+------------------------------------------------------------------+
//|  EKIN_Gosterge.mq5                                               |
//|  Ekin Bootcamp (1-43) mantigi - GOSTERGE. Islem ACMAZ.           |
//+------------------------------------------------------------------+
//  Hangi grafikte acarsan ac, hesap arka planda 5 dk veriden yapilir ve
//  son 6 ayin LONG / SHORT islemleri grafige cizilir. Yeni mum geldikce devam eder.
//
//  SIRA (Ekin'in anlattigi sira, video numarasi transkript dosyasindaki BOLUM):
//   1) GUNLUK YON (41,42): dunku mum, onceki gunun TEPESININ ustunde GOVDEYLE kapandiysa
//      bugun YUKSELIS (sadece LONG). Onceki gunun tepesini alip altinda kapandiysa DUSUS.
//      Tersi: dibin altinda kapanis = DUSUS, dibi alip ustunde kapanis = YUKSELIS.
//      Ic gun (hicbir seviye alinmadi) = YON YOK, islem aranmaz.
//   2) SEVIYELER (23,28): onceki gun tepe/dip (PDH/PDL), onceki hafta tepe/dip (PWH/PWL),
//      Asya tepe/dip (NY 20:00-24:00), Londra tepe/dip (NY 02:00-05:00).
//   3) KILLZONE (17,18) NY saati: FOREX/ALTIN Londra 02-05 ve New York 07-10,
//      ENDEKS 08:30-11:00, KRIPTO killzone yok (gun boyu, 15:00'e kadar).
//   4) SUPURME (15,16,32): killzone icinde fiyat seviyenin altina (LONG) / ustune (SHORT) iner.
//   5a) IFVG (33,34,41): supurmeden onceki/sirasindaki TERS yonlu FVG, GUCLU bir mumun
//       GOVDESIYLE kirilir -> o mumun kapanisindan GIRIS (geri donus beklenmez).
//   5b) FVG (19,20,38): displacement (guclu mum) + MSS (son swing tepenin ustunde GOVDE kapanisi)
//       -> kirilim bacagindaki FVG'nin ORTASINA limit giris.
//   6) STOP (36,38,41): supurmeyi yapan mumun GOVDESININ altina + kucuk nefes payi.
//   7) HEDEF: 2R (stopun 2 kati) ya da karsi likidite (PDH/PWH/Asya/Londra).
//   8) Islem NY 16:00'da hala aciksa kapanir. Gunde en fazla 2, killzone basina 1 islem.
//
//  "GUCLU MUM" = govdesi son 20 mumun ortalama govdesinin en az 1.5 kati VE
//                mumun en az yarisi govde (fitili kisa, kararli mum).
//  "FVG"       = 3 mumluk bosluk, boyu en az ATR(14)'un %10'u (cok minik bosluklar sayilmaz).
//
//  Grafikte: KIRMIZI kutu = stop bolgesi, YESIL kutu = hedef bolgesi, beyaz cizgi = giris,
//            sari cerceve = kullanilan FVG/IFVG, mavi noktali = supurulen seviye.
//  Sag ust: son 6 ayin islem / TP / STOP sayisi, basari yuzdesi, toplam R ve dolar.
//  Saatler: sunucu = New York + SunucuNY (FTMO: 7).
//  NOT: Araclar > Secenekler > Grafikler > "Grafikteki en fazla cubuk" en az 100000 olmali.
//+------------------------------------------------------------------+
#property copyright "EKIN Gosterge"
#property version   "1.00"
#property indicator_chart_window
#property indicator_buffers 0
#property indicator_plots   0

enum ENUM_GIRIS { GIRIS_IKISI=0, GIRIS_SADECE_IFVG=1, GIRIS_SADECE_FVG=2 };
enum ENUM_STOPT { STOP_GOVDE=0, STOP_FITIL=1 };
enum ENUM_TPT   { TP_RR=0, TP_LIKIDITE=1 };
enum ENUM_KZT   { KZ_OTOMATIK=0, KZ_FOREX=1, KZ_ENDEKS=2, KZ_YOK=3 };

input group "Genel"
input int        GecmisGun      = 182;          // Kac gunluk gecmis (6 ay)
input int        SunucuNY       = 7;            // Sunucu saati - New York saati
input double     RiskDolar      = 22.5;         // 1R kac dolar (panel icin)
input group "Kurallar"
input bool       YonFiltresi    = true;         // Gunluk yon filtresi
input ENUM_GIRIS GirisTipi      = GIRIS_IKISI;  // Giris tipi
input ENUM_KZT   KillzoneTipi   = KZ_OTOMATIK;  // Killzone (otomatik: sembol adindan)
input int        MaxGunluk      = 2;            // Gunde en fazla islem
input int        KillzoneBasina = 1;            // Killzone basina en fazla islem
input double     GucluMumKat    = 1.5;          // Guclu mum: govde >= ortalama govde x
input double     GucluMumGovde  = 0.5;          // Guclu mum: govde / mum boyu >=
input double     FvgMinATR      = 0.10;         // FVG en az ATR x
input int        IfvgGeriMum    = 20;           // IFVG: supurmeden kac mum geriye bakilir
input int        SetupMaxMum    = 36;           // Supurmeden sonra en fazla bekleme (5dk mum)
input int        LimitBekleMum  = 12;           // FVG limit en fazla bekleme (5dk mum)
input group "Stop / Hedef"
input ENUM_STOPT StopTipi       = STOP_GOVDE;   // Stop: supurme mumunun govdesi / fitili
input double     StopPayATR     = 0.10;         // Nefes payi (ATR x)
input double     MinStopATR     = 0.30;         // En kucuk stop (ATR x)
input double     MaxStopATR     = 4.0;          // En buyuk stop (ATR x), ustu islem yok
input ENUM_TPT   HedefTipi      = TP_RR;        // Hedef: RR / karsi likidite
input double     RR             = 2.0;          // Risk/Odul (2 = stopun 2 kati)
input group "Gorunum"
input int        PanelYazi      = 12;           // Panel yazi boyu
input int        KutuYazi       = 10;           // Islem yazisi boyu
input int        KutuMinMum     = 12;           // Kutu en az kac grafik mumu genisliginde
input bool       SeviyeCiz      = true;         // Supurulen seviyeyi ciz
input bool       FvgCiz         = true;         // FVG/IFVG kutusunu ciz
input bool       Alarm          = true;         // Yeni sinyalde alarm
input color      RenkStop       = C'205,70,70';
input color      RenkHedef      = C'40,160,95';
input color      RenkGiris      = clrWhite;
input color      RenkFVG        = clrGold;
input color      RenkSeviye     = clrDodgerBlue;
input color      RenkPanel      = C'20,24,32';

#define PFX "EKG_"

struct Islem
  {
   int      yon, tip, sonuc, sev;          // tip 1=IFVG 2=FVG ; sonuc 1=TP -1=STOP 0=KAPANIS 2=ACIK 3=LIMIT
   datetime tG, tC, tSw, tF1, tF2;
   double   g, s, t, c, r, sw, fA, fB;
  };

datetime g_T[];
double   g_O[], g_H[], g_L[], g_C[], g_atr[], g_ort[];
int      g_ny[], g_gun[], g_haf[];
int      g_n=0, g_bas=0;
double   g_dH[], g_dL[], g_dC[];
int      g_yon[], g_nd=0;
double   g_wH[], g_wL[];
int      g_nw=0;
int      g_dir=1, g_kz=1;
Islem    g_isl[];
int      g_ni=0;
bool     g_ok=false;
datetime g_son5=0, g_alarm=0;
int      g_deneme=0;

//--- yon'e gore (SHORT'ta fiyatlar ters cevrilir, ayni LONG mantigi calisir)
double PO(int i) { return g_dir>0 ? g_O[i] : -g_O[i]; }
double PH(int i) { return g_dir>0 ? g_H[i] : -g_L[i]; }
double PL(int i) { return g_dir>0 ? g_L[i] : -g_H[i]; }
double PC(int i) { return g_dir>0 ? g_C[i] : -g_C[i]; }
double DHi(int d){ return g_dir>0 ? g_dH[d] : -g_dL[d]; }
double DLo(int d){ return g_dir>0 ? g_dL[d] : -g_dH[d]; }
double WHi(int w){ return g_dir>0 ? g_wH[w] : -g_wL[w]; }
double WLo(int w){ return g_dir>0 ? g_wL[w] : -g_wH[w]; }

//+------------------------------------------------------------------+
int SembolTipi()
  {
   string s=_Symbol;
   StringToUpper(s);
   string kr[]={"BTC","ETH","LTC","XRP","SOL","ADA","DOGE","BCH","DOT","BNB","AVAX","LINK","XLM","XMR","DASH","AAVE"};
   for(int k=0;k<ArraySize(kr);k++) if(StringFind(s,kr[k])>=0) return 3;
   string ix[]={"US100","US30","US500","US2000","USTEC","NAS","SPX","SP500","DJ","DOW","GER","DE40","DAX",
                "UK100","FTSE","FRA40","CAC","JP225","NIKKEI","EU50","STOXX","HK50","AUS200","SPN35","N25"};
   for(int k=0;k<ArraySize(ix);k++) if(StringFind(s,ix[k])>=0) return 2;
   return 1;
  }

int KZ(int m)   // 0 = killzone disi
  {
   if(g_kz==3) return (m<900 || m>=1020) ? 3 : 0;
   if(g_kz==2) return (m>=510 && m<660) ? 2 : 0;
   if(m>=120 && m<300) return 1;
   if(m>=420 && m<600) return 2;
   return 0;
  }

int KzBitis(int kz)
  {
   if(kz==1) return 300;
   if(kz==2) return (g_kz==2) ? 660 : 600;
   return 900;
  }

bool GucluMum(int i)
  {
   double o=PO(i), c=PC(i), h=PH(i), l=PL(i);
   double b=c-o;
   if(b<=0 || h-l<=0) return false;
   return (b>=GucluMumKat*g_ort[i] && b>=GucluMumGovde*(h-l));
  }

bool SwingTepe(int b,int i,double &v)   // b'den onceki son onaylanmis swing tepe
  {
   int j0=(int)MathMin(b-1,i-2);
   int j1=(int)MathMax(b-40,2);
   for(int j=j0;j>=j1;j--)
     {
      if(j+2>=g_n) continue;
      double h=PH(j);
      if(h>PH(j-1) && h>PH(j-2) && h>=PH(j+1) && h>=PH(j+2)) { v=h; return true; }
     }
   return false;
  }

bool StopHesap(double e,int i,int sb,double sl,double &s)
  {
   double pay=StopPayATR*g_atr[i];
   double gv=MathMin(PO(sb),PC(sb))-pay;
   double fl=sl-pay;
   s=(StopTipi==STOP_GOVDE) ? gv : fl;
   if(s>=e) s=fl;
   if(s>=e) return false;
   if(e-s<MinStopATR*g_atr[i]) s=e-MinStopATR*g_atr[i];
   if(e-s>MaxStopATR*g_atr[i]) return false;
   return true;
  }

bool HedefHesap(double e,double s,const double &hc[],const bool &hv[],double &t)
  {
   double risk=e-s;
   if(HedefTipi==TP_RR) { t=e+RR*risk; return true; }
   double best=DBL_MAX;
   for(int k=0;k<4;k++) if(hv[k] && hc[k]>=e+RR*risk && hc[k]<best) best=hc[k];
   if(best==DBL_MAX) return false;
   t=best;
   return true;
  }

void Ekle(Islem &x)
  {
   Islem y=x;
   if(g_dir<0)
     {
      y.g=-x.g; y.s=-x.s; y.t=-x.t; y.c=-x.c; y.sw=-x.sw; y.fA=-x.fA; y.fB=-x.fB;
     }
   y.yon=g_dir;
   ArrayResize(g_isl,g_ni+1,1000);
   g_isl[g_ni]=y;
   g_ni++;
  }

void Bitir(Islem &x,int i,double px,int s)
  {
   x.tC=g_T[i]; x.c=px; x.sonuc=s;
   double risk=x.g-x.s;
   x.r=(risk>0) ? (px-x.g)/risk : 0;
   Ekle(x);
  }

//+------------------------------------------------------------------+
//| Tek yon icin tum gecmisi tarar (dir=1 LONG, dir=-1 SHORT)        |
//+------------------------------------------------------------------+
void Gecis(int dir)
  {
   g_dir=dir;
   int    curD=-1, curW=-1;
   double lv[4]; bool ok[4];
   double hc[4]; bool hv[4];
   for(int k=0;k<4;k++) { lv[k]=0; ok[k]=false; hc[k]=0; hv[k]=false; }
   double wkLo=DBL_MAX;
   double asL=0,asH=0,loL=0,loH=0;
   bool   asVar=false,asHz=false,loVar=false,loHz=false;
   int    gunIs=0;
   int    kzS[4]={0,0,0,0};
   bool   su=false; int suBar=0,suIlk=0,suKz=0; double suLow=0,mss=0; bool mssV=false;
   bool   pd=false; int pdBar=0,pdKz=0;
   bool   tr=false; int trBar=0;
   Islem  x; ZeroMemory(x);

   for(int i=g_bas;i<g_n;i++)
     {
      int d=g_gun[i], w=g_haf[i], m=g_ny[i];
      if(w!=curW) { curW=w; wkLo=DBL_MAX; }
      //--- yeni gun
      if(d!=curD)
        {
         curD=d;
         if(tr) { Bitir(x,i,PO(i),0); tr=false; }
         pd=false; su=false; gunIs=0;
         for(int k=0;k<4;k++) { kzS[k]=0; ok[k]=false; hv[k]=false; }
         asVar=false; asHz=false; loVar=false; loHz=false;
         if(d>=1) { lv[0]=DLo(d-1); ok[0]=true; hc[0]=DHi(d-1); hv[0]=true; }
         if(w>=1) { lv[1]=WLo(w-1); ok[1]=(wkLo>lv[1]); hc[1]=WHi(w-1); hv[1]=true; }
        }
      //--- acik islem
      if(tr && i>trBar)
        {
         if(PL(i)<=x.s)              { Bitir(x,i,x.s,-1); tr=false; }
         else if(PH(i)>=x.t)         { Bitir(x,i,x.t, 1); tr=false; }
         else if(m>=960 && m<1020)   { Bitir(x,i,PO(i),0); tr=false; }
        }
      //--- bekleyen FVG limit
      if(pd)
        {
         if(PL(i)<=x.g)
           {
            pd=false; tr=true; trBar=i; x.tG=g_T[i]; gunIs++; kzS[pdKz]++;
            if(PL(i)<=x.s) { Bitir(x,i,x.s,-1); tr=false; }
           }
         else if(PH(i)>=x.t || i-pdBar>LimitBekleMum || (m>KzBitis(pdKz)+60 && m<1020) || (m>=960 && m<1020))
            pd=false;
        }
      //--- Asya / Londra seviyeleri hazir mi
      if(!asHz && asVar && m<1020)           { lv[2]=asL; ok[2]=true; hc[2]=asH; hv[2]=true; asHz=true; }
      if(!loHz && loVar && m>=300 && m<1020) { lv[3]=loL; ok[3]=true; hc[3]=loH; hv[3]=true; loHz=true; }
      //--- supurme
      int kz=KZ(m);
      for(int k=0;k<4;k++)
        {
         if(!ok[k] || PL(i)>=lv[k]) continue;
         ok[k]=false;
         if(su || tr || pd || kz<=0) continue;
         if(gunIs>=MaxGunluk || kzS[kz]>=KillzoneBasina) continue;
         if(YonFiltresi && g_yon[d]!=g_dir) continue;
         ZeroMemory(x);
         su=true; suBar=i; suIlk=i; suLow=PL(i); suKz=kz;
         x.sw=lv[k]; x.tSw=g_T[i]; x.sev=k;
         mssV=SwingTepe(i,i,mss);
        }
      if(su && i>suBar && PL(i)<suLow) { suLow=PL(i); suBar=i; mssV=SwingTepe(i,i,mss); }
      //--- giris aramasi
      if(su)
        {
         bool bitti=false;
         //--- 5a) IFVG: ters FVG guclu mumun govdesiyle kirildi -> kapanista giris
         if(GirisTipi!=GIRIS_SADECE_FVG && GucluMum(i))
           {
            int k1=(int)MathMax(suIlk-IfvgGeriMum,2);
            for(int k=i-1;k>=k1;k--)
              {
               double top=PL(k-2), bot=PH(k);
               if(top-bot<FvgMinATR*g_atr[i]) continue;
               if(!(PO(i)<top && PC(i)>top)) continue;
               bool once=false;
               for(int q=k+1;q<i;q++) if(PC(q)>top) { once=true; break; }
               if(once) continue;
               double e=PC(i), s=0, t=0;
               if(StopHesap(e,i,suBar,suLow,s) && HedefHesap(e,s,hc,hv,t))
                 {
                  x.tip=1; x.g=e; x.s=s; x.t=t; x.tG=g_T[i];
                  x.tF1=g_T[k-2]; x.tF2=g_T[i]; x.fA=top; x.fB=bot;
                  tr=true; trBar=i; gunIs++; kzS[suKz]++;
                 }
               bitti=true;
               break;
              }
           }
         //--- 5b) FVG: displacement + MSS -> FVG ortasina limit
         if(!bitti && GirisTipi!=GIRIS_SADECE_IFVG && mssV && PC(i)>mss)
           {
            bool guc=false;
            for(int q=suBar;q<=i;q++) if(GucluMum(q)) { guc=true; break; }
            int fk=-1;
            if(guc) for(int k=i;k>=suBar+2;k--) if(PL(k)-PH(k-2)>=FvgMinATR*g_atr[i]) { fk=k; break; }
            if(fk>=0)
              {
               double top=PL(fk), bot=PH(fk-2), e=(top+bot)/2.0, s=0, t=0;
               if(StopHesap(e,i,suBar,suLow,s) && HedefHesap(e,s,hc,hv,t))
                 {
                  x.tip=2; x.g=e; x.s=s; x.t=t; x.tG=g_T[i];
                  x.tF1=g_T[fk-2]; x.tF2=g_T[i]; x.fA=top; x.fB=bot;
                  pd=true; pdBar=i; pdKz=suKz;
                 }
              }
            bitti=true;
           }
         if(!bitti && (i-suIlk>SetupMaxMum || (m>KzBitis(suKz)+30 && m<1020))) bitti=true;
         if(bitti) su=false;
        }
      //--- seviye biriktirme
      if(m>=1200)
        {
         if(!asVar) { asL=PL(i); asH=PH(i); asVar=true; }
         else { asL=MathMin(asL,PL(i)); asH=MathMax(asH,PH(i)); }
        }
      if(m>=120 && m<300)
        {
         if(!loVar) { loL=PL(i); loH=PH(i); loVar=true; }
         else { loL=MathMin(loL,PL(i)); loH=MathMax(loH,PH(i)); }
        }
      wkLo=MathMin(wkLo,PL(i));
     }
   //--- sonda acik / bekleyen
   if(tr)
     {
      x.sonuc=2; x.tC=g_T[g_n-1]; x.c=PC(g_n-1);
      double risk=x.g-x.s; x.r=(risk>0) ? (x.c-x.g)/risk : 0;
      Ekle(x);
     }
   if(pd) { x.sonuc=3; x.tC=g_T[g_n-1]; x.c=x.g; x.r=0; Ekle(x); }
  }

//+------------------------------------------------------------------+
//| Cizim yardimcilari                                               |
//+------------------------------------------------------------------+
void Rect(string n,datetime t1,double p1,datetime t2,double p2,color c,bool fill,int st=STYLE_SOLID)
  {
   if(!ObjectCreate(0,n,OBJ_RECTANGLE,0,t1,p1,t2,p2)) return;
   ObjectSetInteger(0,n,OBJPROP_COLOR,c);
   ObjectSetInteger(0,n,OBJPROP_FILL,fill);
   ObjectSetInteger(0,n,OBJPROP_STYLE,st);
   ObjectSetInteger(0,n,OBJPROP_WIDTH,1);
   ObjectSetInteger(0,n,OBJPROP_BACK,true);
   ObjectSetInteger(0,n,OBJPROP_SELECTABLE,false);
   ObjectSetInteger(0,n,OBJPROP_HIDDEN,true);
  }

void Cizgi(string n,datetime t1,double p1,datetime t2,double p2,color c,int wd,int st)
  {
   if(!ObjectCreate(0,n,OBJ_TREND,0,t1,p1,t2,p2)) return;
   ObjectSetInteger(0,n,OBJPROP_COLOR,c);
   ObjectSetInteger(0,n,OBJPROP_WIDTH,wd);
   ObjectSetInteger(0,n,OBJPROP_STYLE,st);
   ObjectSetInteger(0,n,OBJPROP_RAY_RIGHT,false);
   ObjectSetInteger(0,n,OBJPROP_RAY_LEFT,false);
   ObjectSetInteger(0,n,OBJPROP_SELECTABLE,false);
   ObjectSetInteger(0,n,OBJPROP_HIDDEN,true);
  }

void Yazi(string n,datetime t,double p,string s,color c,int fs,ENUM_ANCHOR_POINT an)
  {
   if(!ObjectCreate(0,n,OBJ_TEXT,0,t,p)) return;
   ObjectSetString(0,n,OBJPROP_TEXT,s);
   ObjectSetString(0,n,OBJPROP_FONT,"Arial Bold");
   ObjectSetInteger(0,n,OBJPROP_FONTSIZE,fs);
   ObjectSetInteger(0,n,OBJPROP_COLOR,c);
   ObjectSetInteger(0,n,OBJPROP_ANCHOR,an);
   ObjectSetInteger(0,n,OBJPROP_SELECTABLE,false);
   ObjectSetInteger(0,n,OBJPROP_HIDDEN,true);
  }

string SonucYazi(const Islem &x)
  {
   if(x.sonuc==1)  return "TP +"+DoubleToString(x.r,1)+"R";
   if(x.sonuc==-1) return "STOP -1R";
   if(x.sonuc==0)  return "KAPANIS "+(x.r>=0?"+":"")+DoubleToString(x.r,1)+"R";
   if(x.sonuc==2)  return "ACIK "+(x.r>=0?"+":"")+DoubleToString(x.r,1)+"R";
   return "LIMIT BEKLIYOR";
  }

string SeviyeAd(int yon,int k)
  {
   if(yon>0) { string a[]={"PDL","PWL","ASYA DIP","LONDRA DIP"}; return a[k]; }
   string b[]={"PDH","PWH","ASYA TEPE","LONDRA TEPE"};
   return b[k];
  }

void IslemCiz(int idx,const Islem &x)
  {
   string b=PFX+"I"+IntegerToString(idx)+"_";
   int ps=PeriodSeconds();
   datetime t2=x.tC;
   datetime tmin=(datetime)(x.tG+KutuMinMum*ps);
   if(t2<tmin) t2=tmin;
   int st=(x.sonuc==3) ? STYLE_DOT : STYLE_SOLID;
   Rect(b+"S",x.tG,x.g,t2,x.s,RenkStop,x.sonuc!=3,st);
   Rect(b+"T",x.tG,x.g,t2,x.t,RenkHedef,x.sonuc!=3,st);
   Cizgi(b+"E",x.tG,x.g,t2,x.g,RenkGiris,2,STYLE_SOLID);
   color yc=(x.sonuc==1) ? RenkHedef : (x.sonuc==-1 ? RenkStop : clrSilver);
   string yz=(x.yon>0?"LONG ":"SHORT ")+(x.tip==1?"IFVG":"FVG")+" | "+SeviyeAd(x.yon,x.sev)+" | "+SonucYazi(x);
   Yazi(b+"Y",x.tG,x.t,yz,yc,KutuYazi,x.yon>0 ? ANCHOR_LEFT_LOWER : ANCHOR_LEFT_UPPER);
   if(SeviyeCiz)
     {
      datetime a1=(datetime)(x.tSw-8*300), a2=(datetime)(x.tSw+4*300);
      Cizgi(b+"L",a1,x.sw,a2,x.sw,RenkSeviye,2,STYLE_DOT);
      Yazi(b+"LY",a1,x.sw,SeviyeAd(x.yon,x.sev),RenkSeviye,KutuYazi-1,x.yon>0 ? ANCHOR_RIGHT_UPPER : ANCHOR_RIGHT_LOWER);
     }
   if(FvgCiz) Rect(b+"F",x.tF1,x.fA,(datetime)(x.tF2+300),x.fB,RenkFVG,false);
  }

//+------------------------------------------------------------------+
//| Panel                                                            |
//+------------------------------------------------------------------+
void PanelYaz(string &s[],color &c[],int cnt)
  {
   int lh=(int)MathRound(PanelYazi*1.9);
   int w =(int)MathRound(PanelYazi*38);
   int h =cnt*lh+20;
   string bg=PFX+"PBG";
   ObjectCreate(0,bg,OBJ_RECTANGLE_LABEL,0,0,0);
   ObjectSetInteger(0,bg,OBJPROP_CORNER,CORNER_RIGHT_UPPER);
   ObjectSetInteger(0,bg,OBJPROP_XDISTANCE,w+10);
   ObjectSetInteger(0,bg,OBJPROP_YDISTANCE,20);
   ObjectSetInteger(0,bg,OBJPROP_XSIZE,w);
   ObjectSetInteger(0,bg,OBJPROP_YSIZE,h);
   ObjectSetInteger(0,bg,OBJPROP_BGCOLOR,RenkPanel);
   ObjectSetInteger(0,bg,OBJPROP_BORDER_TYPE,BORDER_FLAT);
   ObjectSetInteger(0,bg,OBJPROP_COLOR,clrDimGray);
   ObjectSetInteger(0,bg,OBJPROP_BACK,false);
   ObjectSetInteger(0,bg,OBJPROP_SELECTABLE,false);
   ObjectSetInteger(0,bg,OBJPROP_HIDDEN,true);
   for(int k=0;k<cnt;k++)
     {
      string n=PFX+"P"+IntegerToString(k);
      ObjectCreate(0,n,OBJ_LABEL,0,0,0);
      ObjectSetInteger(0,n,OBJPROP_CORNER,CORNER_RIGHT_UPPER);
      ObjectSetInteger(0,n,OBJPROP_ANCHOR,ANCHOR_LEFT_UPPER);
      ObjectSetInteger(0,n,OBJPROP_XDISTANCE,w-2);
      ObjectSetInteger(0,n,OBJPROP_YDISTANCE,30+k*lh);
      ObjectSetString(0,n,OBJPROP_TEXT,s[k]);
      ObjectSetString(0,n,OBJPROP_FONT,"Consolas");
      ObjectSetInteger(0,n,OBJPROP_FONTSIZE,(k==0)?PanelYazi+2:PanelYazi);
      ObjectSetInteger(0,n,OBJPROP_COLOR,c[k]);
      ObjectSetInteger(0,n,OBJPROP_SELECTABLE,false);
      ObjectSetInteger(0,n,OBJPROP_HIDDEN,true);
     }
  }

void PanelMesaj(string m)
  {
   ObjectsDeleteAll(0,PFX);
   string s[2]; color c[2];
   s[0]="EKIN ICT  |  "+_Symbol; c[0]=clrWhite;
   s[1]=m;                       c[1]=clrGold;
   PanelYaz(s,c,2);
   ChartRedraw();
  }

string Yz(int a,int b) { return b>0 ? DoubleToString(100.0*a/b,1) : "0.0"; }
string Rz(double r)    { return (r>=0?"+":"")+DoubleToString(r,1)+"R"; }

void Panel()
  {
   datetime sb=TimeCurrent()-(datetime)(GecmisGun*86400);
   datetime ilk=(sb>g_T[0]) ? sb : g_T[0];
   int n=0,tp=0,sl=0,zm=0,acik=0,bek=0;
   double R=0;
   int ln=0,lt=0,sn=0,st=0,ifn=0,it=0,fn=0,ft=0;
   double lr=0,sr=0,ir=0,fr=0;
   for(int k=0;k<g_ni;k++)
     {
      if(g_isl[k].tG<sb) continue;
      if(g_isl[k].sonuc==2) { acik++; continue; }
      if(g_isl[k].sonuc==3) { bek++;  continue; }
      bool w=(g_isl[k].sonuc==1);
      double r=g_isl[k].r;
      n++; R+=r;
      if(w) tp++; else if(g_isl[k].sonuc==-1) sl++; else zm++;
      if(g_isl[k].yon>0) { ln++; lr+=r; if(w) lt++; } else { sn++; sr+=r; if(w) st++; }
      if(g_isl[k].tip==1){ ifn++; ir+=r; if(w) it++; } else { fn++; fr+=r; if(w) ft++; }
     }
   int yb=g_yon[g_gun[g_n-1]];
   string ys=(yb>0) ? "YUKSELIS - sadece LONG" : (yb<0 ? "DUSUS - sadece SHORT" : "YON YOK - islem aranmaz");
   if(!YonFiltresi) ys="filtre KAPALI";
   string kzs=(g_kz==1) ? "FOREX 02-05 / 07-10" : (g_kz==2 ? "ENDEKS 08:30-11" : "KRIPTO gun boyu");

   string s[14]; color c[14]; int q=0;
   s[q]="EKIN ICT  |  "+_Symbol;                                                       c[q++]=clrWhite;
   s[q]="Donem : "+TimeToString(ilk,TIME_DATE)+" - "+TimeToString(TimeCurrent(),TIME_DATE); c[q++]=clrSilver;
   s[q]="Bugun : "+ys;                                                                 c[q++]=(yb>0?RenkHedef:(yb<0?RenkStop:clrSilver));
   s[q]="Saat  : "+kzs+" (NY)";                                                        c[q++]=clrSilver;
   s[q]="-----------------------------------------";                                    c[q++]=clrDimGray;
   s[q]="Islem: "+IntegerToString(n)+"   TP: "+IntegerToString(tp)+"   STOP: "+IntegerToString(sl)+"   Kapanis: "+IntegerToString(zm); c[q++]=clrWhite;
   s[q]="Basari: %"+Yz(tp,n)+"   (TP / Islem x 100)";                                 c[q++]=clrGold;
   s[q]="Toplam: "+Rz(R)+"  =  "+(R>=0?"+":"")+DoubleToString(R*RiskDolar,0)+" $   (1R="+DoubleToString(RiskDolar,1)+"$)"; c[q++]=(R>=0?RenkHedef:RenkStop);
   s[q]="-----------------------------------------";                                    c[q++]=clrDimGray;
   s[q]="LONG : "+IntegerToString(ln)+" islem  %"+Yz(lt,ln)+"  "+Rz(lr);              c[q++]=(lr>=0?RenkHedef:RenkStop);
   s[q]="SHORT: "+IntegerToString(sn)+" islem  %"+Yz(st,sn)+"  "+Rz(sr);              c[q++]=(sr>=0?RenkHedef:RenkStop);
   s[q]="IFVG : "+IntegerToString(ifn)+" islem  %"+Yz(it,ifn)+"  "+Rz(ir);              c[q++]=(ir>=0?RenkHedef:RenkStop);
   s[q]="FVG  : "+IntegerToString(fn)+" islem  %"+Yz(ft,fn)+"  "+Rz(fr);              c[q++]=(fr>=0?RenkHedef:RenkStop);
   s[q]="Simdi: acik "+IntegerToString(acik)+"   limit bekleyen "+IntegerToString(bek)+"   | TP "+(HedefTipi==TP_RR?DoubleToString(RR,1)+"R":"likidite"); c[q++]=clrSilver;
   PanelYaz(s,c,q);
  }

//+------------------------------------------------------------------+
//| Ana hesap                                                        |
//+------------------------------------------------------------------+
bool Hesapla()
  {
   datetime simdi=TimeCurrent();
   datetime bas=simdi-(datetime)((GecmisGun+20)*86400);
   MqlRates r[];
   int n=CopyRates(_Symbol,PERIOD_M5,bas,simdi,r);
   if(n<300)
     {
      g_deneme++;
      PanelMesaj("5 dk veri yukleniyor... ("+IntegerToString(MathMax(n,0))+" mum)");
      return false;
     }
   if(r[0].time>bas+5*86400 && g_deneme<15)
     {
      g_deneme++;
      PanelMesaj("6 aylik 5 dk veri indiriliyor... bekleyin");
      return false;
     }
   ArrayResize(g_T,n); ArrayResize(g_O,n); ArrayResize(g_H,n); ArrayResize(g_L,n); ArrayResize(g_C,n);
   ArrayResize(g_atr,n); ArrayResize(g_ort,n); ArrayResize(g_ny,n); ArrayResize(g_gun,n); ArrayResize(g_haf,n);
   g_nd=0; g_nw=0;
   long pk=-1, pw=-1;
   for(int i=0;i<n;i++)
     {
      g_T[i]=r[i].time; g_O[i]=r[i].open; g_H[i]=r[i].high; g_L[i]=r[i].low; g_C[i]=r[i].close;
      long tny=(long)r[i].time-(long)SunucuNY*3600;
      g_ny[i]=(int)((((tny%86400)+86400)%86400)/60);
      long key=(long)MathFloor((tny+7*3600)/86400.0);   // gun NY 17:00'de baslar
      long wk =(long)MathFloor((key+3)/7.0);             // hafta pazartesi gunu ile baslar
      if(key!=pk)
        {
         pk=key; g_nd++;
         ArrayResize(g_dH,g_nd,500); ArrayResize(g_dL,g_nd,500); ArrayResize(g_dC,g_nd,500);
         g_dH[g_nd-1]=g_H[i]; g_dL[g_nd-1]=g_L[i];
        }
      else { g_dH[g_nd-1]=MathMax(g_dH[g_nd-1],g_H[i]); g_dL[g_nd-1]=MathMin(g_dL[g_nd-1],g_L[i]); }
      g_dC[g_nd-1]=g_C[i];
      g_gun[i]=g_nd-1;
      if(wk!=pw)
        {
         pw=wk; g_nw++;
         ArrayResize(g_wH,g_nw,100); ArrayResize(g_wL,g_nw,100);
         g_wH[g_nw-1]=g_H[i]; g_wL[g_nw-1]=g_L[i];
        }
      else { g_wH[g_nw-1]=MathMax(g_wH[g_nw-1],g_H[i]); g_wL[g_nw-1]=MathMin(g_wL[g_nw-1],g_L[i]); }
      g_haf[i]=g_nw-1;
     }
   //--- ATR ve ortalama govde (basit hareketli ortalama)
   for(int i=0;i<n;i++)
     {
      double s=0; int c=0;
      for(int j=i;j>=0 && j>i-14;j--)
        {
         double tr=g_H[j]-g_L[j];
         if(j>0) tr=MathMax(tr,MathMax(MathAbs(g_H[j]-g_C[j-1]),MathAbs(g_L[j]-g_C[j-1])));
         s+=tr; c++;
        }
      g_atr[i]=(c>0) ? s/c : 0;
      s=0; c=0;
      for(int j=i-1;j>=0 && j>=i-20;j--) { s+=MathAbs(g_C[j]-g_O[j]); c++; }
      g_ort[i]=(c>0) ? s/c : 0;
     }
   //--- gunluk yon
   ArrayResize(g_yon,g_nd);
   for(int d=0;d<g_nd;d++)
     {
      g_yon[d]=0;
      if(d<2) continue;
      double h1=g_dH[d-1], l1=g_dL[d-1], c1=g_dC[d-1], h2=g_dH[d-2], l2=g_dL[d-2];
      bool bull=(c1>h2) || (l1<l2 && c1>l2);
      bool bear=(c1<l2) || (h1>h2 && c1<h2);
      if(bull && !bear) g_yon[d]=1;
      else if(bear && !bull) g_yon[d]=-1;
     }
   g_n=n-1;   // olusan son mum haric
   g_bas=0;
   while(g_bas<g_n && (g_gun[g_bas]<2 || g_bas<25)) g_bas++;
   g_kz=(KillzoneTipi==KZ_OTOMATIK) ? SembolTipi() : (int)KillzoneTipi;
   //--- tarama
   g_ni=0; ArrayResize(g_isl,0,1000);
   Gecis(1);
   Gecis(-1);
   //--- cizim
   ObjectsDeleteAll(0,PFX);
   datetime sb=TimeCurrent()-(datetime)(GecmisGun*86400);
   for(int k=0;k<g_ni;k++) if(g_isl[k].tG>=sb) IslemCiz(k,g_isl[k]);
   Panel();
   //--- alarm
   if(Alarm)
     {
      for(int k=0;k<g_ni;k++)
        {
         if(g_isl[k].sonuc<2) continue;
         if(g_isl[k].tG<=g_alarm || g_isl[k].tG<TimeCurrent()-900) continue;
         g_alarm=g_isl[k].tG;
         Alert("EKIN ",_Symbol,": ",(g_isl[k].yon>0?"LONG ":"SHORT "),(g_isl[k].tip==1?"IFVG":"FVG limit"),
               "  giris ",DoubleToString(g_isl[k].g,_Digits),"  stop ",DoubleToString(g_isl[k].s,_Digits),
               "  hedef ",DoubleToString(g_isl[k].t,_Digits));
        }
     }
   ChartRedraw();
   g_ok=true;
   return true;
  }

//+------------------------------------------------------------------+
int OnInit()
  {
   IndicatorSetString(INDICATOR_SHORTNAME,"EKIN ICT");
   EventSetTimer(3);
   return INIT_SUCCEEDED;
  }

void OnDeinit(const int reason)
  {
   EventKillTimer();
   ObjectsDeleteAll(0,PFX);
   ChartRedraw();
  }

void OnTimer()
  {
   if(!g_ok && Hesapla()) g_son5=iTime(_Symbol,PERIOD_M5,0);
  }

int OnCalculate(const int rates_total,const int prev_calculated,const datetime &time[],
                const double &open[],const double &high[],const double &low[],const double &close[],
                const long &tick_volume[],const long &volume[],const int &spread[])
  {
   datetime t5=iTime(_Symbol,PERIOD_M5,0);
   if(t5==0) return rates_total;
   if(!g_ok || t5!=g_son5) { if(Hesapla()) g_son5=t5; }
   return rates_total;
  }
//+------------------------------------------------------------------+
