# -*- coding: utf-8 -*-
"""
ICT ROBOT MANTIGI - 6 AYLIK TEST - BUTUN SEMBOLLER - 10.000 $ ILE BASLASAYDI
==========================================================================
Calistir:   py -3.8 C:\\Users\\User\\Desktop\\ict_6ay_tarama.py
Gerekli:    py -3.8 -m pip install MetaTrader5 pandas numpy
Sadece bazi semboller:   py -3.8 ict_6ay_tarama.py --sembol US100.cash,EURUSD
MT5 acik olmali. SADECE gecmis veri okur, ISLEM ACMAZ.
MT5 > Araclar > Secenekler > Grafikler > "Grafikteki en fazla cubuk" = Sinirsiz (1 dk veri).
Sonuclar MASAUSTUNE:  Masaustu\\ict_6ay_<tarih>\\0_OZET.txt , 1_semboller.csv , 2_islemler.csv

180 GUN ONCE 10.000 $ ile baslar, bugune kadar gider. Her an sadece o ana kadar olusmus mumlar kullanilir.
Tek kural seti, ayar taramasi yok, donem bolunmez.

KURALLAR (LONG anlatiliyor, SHORT birebir tersi)
  SAAT (NY)  : 09:30-11:30 ve 13:30-16:00.  Bu saatler disinda kurulum aranmaz.
  SEVIYELER  : onceki gun dibi (PDL), onceki hafta dibi (PWL), Asya dibi (NY 20:00-24:00),
               Londra dibi (NY 02:00-05:00), 15 dk swing dipler (3 mum fraktal; iki swing arasi en az 5 mum),
               esit dipler (EQL: yeni 15 dk swing dip bir oncekine 15dk ortalama mum boyunun %10'u kadar yakin).
               Fiyat bir seviyeye bir kez fitil attiysa / gectiyse o seviye silinir.
  1 SUPURME  : 1 dk mum seviyenin altina FITIL atar, govdesi (acilis ve kapanis) seviyenin USTUNDE kalir.
  2 SERT MUM : govde >= son 10 mumun ortalama govdesi x 1.5  VE  fitiller toplami < mum boyunun %20'si.
  3 MSS      : supurmeden onceki son 1 dk tepe (3 mum fraktal); SERT bir yukari mumun govdesi bunun ustunde kapanir.
               Fiyat MSS'den once daha asagi inerse dip ve son tepe guncellenir.  Seans penceresi bitince iptal.
  4 FVG      : supurme ile MSS'den sonraki mum arasinda 3 mumluk bosluk (1. mum tepesi < 3. mum dibi);
               bosluk >= son 10 mumun ortalama boyu x 0.25.  Birden fazlaysa en son olusan.
  5 ISKONTO  : supurme dibi (0) ile o ana kadarki en yuksek tepe (1) arasi; FVG ust kenari %50'nin ALTINDA olmali.
  GIRIS      : FVG UST kenarina LIMIT.  15 dk (15 mum) icinde dolmazsa ya da once hedef gelirse iptal.
  STOP       : supurmenin en dip fitili - 3 tick.
  HEDEF      : 2R, tamami kapanir.  Fiyat 1R gidince stop girise cekilir (sonuc 0R).
  RISK       : islem basina 10.000 $'in %1'i = 100 $.
  MAKAS      : islemin spread maliyeti 6 $'i gecerse islem acilmaz.  Spread maliyeti sonuctan dusulur.
  Ayni anda sembol basina yon basina tek kurulum.  Komisyon, gunluk zarar limiti, haber filtresi YOK.
"""
from __future__ import print_function

import argparse
import os
import time
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

try:
    import MetaTrader5 as mt5
except ImportError:
    mt5 = None

GUN = 180
SUNUCU_NY = 7
BASLANGIC = 10000.0
RISK_DOLAR = 100.0
MAKAS_DOLAR = 6.0
RR = 2.0
PENCERE = [(570, 690, "SABAH 09:30-11:30"), (810, 960, "OGLEN 13:30-16:00")]
DISP_KAT = 1.5
FITIL_MAX = 0.20
ORT_MUM = 10
FVG_MIN = 0.25
LIMIT_BEKLE = 15
STOP_TICK = 3
SWING_ARA = 5
EQ_TOL = 0.10
MSS_GERI = 60
LISTE_MIN_ISLEM = 25
LISTE_MIN_BASARI = 40.0

AD_L = {"PD": "PDL", "PW": "PWL", "AS": "ASYA DIP", "LO": "LONDRA DIP", "SW": "15DK SWING DIP", "EQ": "ESIT DIP"}
AD_S = {"PD": "PDH", "PW": "PWH", "AS": "ASYA TEPE", "LO": "LONDRA TEPE", "SW": "15DK SWING TEPE", "EQ": "ESIT TEPE"}


def masaustu():
    ev = os.path.expanduser("~")
    for p in (os.path.join(ev, "Desktop"), os.path.join(ev, "OneDrive", "Desktop"), os.path.join(ev, "Masaüstü")):
        if os.path.isdir(p):
            return p
    return os.getcwd()


def cek(sembol, bas, bit):
    out, a = [], bas
    while a < bit:
        b = min(a + timedelta(days=10), bit)
        r = None
        for _ in range(3):
            r = mt5.copy_rates_range(sembol, mt5.TIMEFRAME_M1, a, b)
            if r is not None:
                break
            time.sleep(0.5)
        if r is not None and len(r):
            d = pd.DataFrame(r)
            if "spread" not in d.columns:
                d["spread"] = 0
            out.append(d[["time", "open", "high", "low", "close", "spread"]])
        a = b
    if not out:
        return None
    return pd.concat(out).drop_duplicates("time").sort_values("time").reset_index(drop=True)


def pencere(m):
    for k, (a, b, _) in enumerate(PENCERE):
        if a <= m < b:
            return k
    return -1


def ilk(arr, i, v, asagi):
    """i'den itibaren arr < v (asagi) ya da arr >= v (yukari) olan ilk indeks; yoksa -1."""
    n, adim = len(arr), 2000
    while i < n:
        j = min(n, i + adim)
        w = np.nonzero(arr[i:j] <= v if asagi else arr[i:j] >= v)[0]
        if len(w):
            return i + int(w[0])
        i, adim = j, adim * 4
    return -1


def ilk_alti(arr, i, v):
    n, adim = len(arr), 2000
    while i < n:
        j = min(n, i + adim)
        w = np.nonzero(arr[i:j] < v)[0]
        if len(w):
            return i + int(w[0])
        i, adim = j, adim * 4
    return -1


# ----------------------------------------------------------------- seviyeler (yon uzayinda: hep "dip")
def seviyeler(T, h, l, ny, gun, ds, de, ws):
    sev = []
    dLo = np.minimum.reduceat(l, ds)
    wLo = np.minimum.reduceat(l, ws)
    for d in range(1, len(ds)):
        sev.append((ds[d], dLo[d - 1], "PD"))
    for w in range(1, len(ws)):
        sev.append((ws[w], wLo[w - 1], "PW"))
    for d in range(len(ds)):
        a, b = ds[d], de[d] + 1
        m = ny[a:b]
        k = np.nonzero(m >= 1200)[0]                      # Asya NY 20:00-24:00
        if len(k):
            son = a + k[-1]
            sonra = np.nonzero(m[k[-1] + 1:] < 1020)[0]
            if len(sonra):
                sev.append((son + 1 + sonra[0], l[a + k].min(), "AS"))
        k = np.nonzero((m >= 120) & (m < 300))[0]        # Londra NY 02:00-05:00
        if len(k):
            son = a + k[-1]
            sonra = np.nonzero((m[k[-1] + 1:] >= 300) & (m[k[-1] + 1:] < 1020))[0]
            if len(sonra):
                sev.append((son + 1 + sonra[0], l[a + k].min(), "LO"))
    # 15 dk swing dipler
    k15 = T // 900
    s15 = np.r_[0, np.nonzero(np.diff(k15))[0] + 1]
    L15 = np.minimum.reduceat(l, s15)
    T15 = k15[s15] * 900
    H15 = np.maximum.reduceat(h, s15)
    rng15 = pd.Series(H15 - L15).rolling(14, min_periods=1).mean().values   # 15 dk ortalama mum boyu
    son_j, son_v = -999, None
    for j in range(1, len(L15) - 1):
        if L15[j] < L15[j - 1] and L15[j] < L15[j + 1]:
            if j - son_j < SWING_ARA:
                continue
            hazir = int(np.searchsorted(T, T15[j + 1] + 900))
            if hazir >= len(T):
                continue
            tip = "SW"
            if son_v is not None and abs(L15[j] - son_v) <= EQ_TOL * rng15[j]:
                tip = "EQ"
            sev.append((hazir, L15[j], tip))
            son_j, son_v = j, L15[j]
    return sev


# ----------------------------------------------------------------- tek yon
def gecis(P, dirn, sembol, kayit, say):
    if dirn > 0:
        o, h, l, c = P["O"], P["H"], P["L"], P["C"]
        adlar = AD_L
    else:
        o, h, l, c = -P["O"], -P["L"], -P["H"], -P["C"]
        adlar = AD_S
    T, ny, gun, SP, tick, sinir = P["T"], P["ny"], P["gun"], P["SP"], P["tick"], P["sinir"]
    n = len(T)
    body = c - o
    rng = h - l
    ortB = pd.Series(np.abs(body)).shift(1).rolling(ORT_MUM, min_periods=1).mean().fillna(0).values
    ortR = pd.Series(rng).shift(1).rolling(ORT_MUM, min_periods=1).mean().fillna(0).values
    sert = (body > 0) & (body >= DISP_KAT * ortB) & ((rng - body) < FITIL_MAX * rng)

    def son_tepe(i):
        for j in range(i - 1, max(i - MSS_GERI, 1) - 1, -1):
            if h[j] > h[j - 1] and h[j] > h[j + 1]:
                return h[j]
        return None

    olay = []
    for (hazir, v, tip) in seviyeler(T, h, l, ny, gun, P["ds"], P["de"], P["ws"]):
        f = ilk_alti(l, int(hazir), v)
        if f < 0 or T[f] < sinir:
            continue
        w = pencere(ny[f])
        if w < 0:
            continue
        if min(o[f], c[f]) <= v:          # govde seviyenin altinda -> supurme degil
            say["govde_alti"] += 1
            continue
        olay.append((f, v, tip, w))
    olay.sort(key=lambda x: x[0])
    mesgul = -1
    son_bar = -1
    for (f, v, tip, w) in olay:
        if f <= mesgul or f == son_bar:
            continue
        son_bar = f
        say["supurme"] += 1
        i0, sl = f, l[f]
        mss = son_tepe(f)
        mssBar, i = -1, f + 1
        a_, b_ = PENCERE[w][0], PENCERE[w][1]
        while i < n - 2 and gun[i] == gun[f] and a_ <= ny[i] < b_:
            if l[i] < sl:
                sl, i0 = l[i], i
                mss = son_tepe(i)
            elif mss is not None and sert[i] and c[i] > mss:
                mssBar = i
                break
            i += 1
        if mssBar < 0:
            mesgul = i
            continue
        say["mss"] += 1
        p = mssBar + 1
        fk = -1
        for k in range(p, i0 + 1, -1):
            if l[k] - h[k - 2] >= FVG_MIN * ortR[k]:
                fk = k
                break
        if fk < 0:
            mesgul = p
            continue
        say["fvg"] += 1
        e = l[fk]
        s = sl - STOP_TICK * tick
        risk = e - s
        if risk <= 0:
            mesgul = p
            continue
        maliyet = RISK_DOLAR * SP[p] / risk
        if maliyet > MAKAS_DOLAR:
            say["makas"] += 1
            mesgul = p
            continue
        tp, be = e + RR * risk, e + risk
        # limit 15 dk bekler. Iskonto: supurme dibi (0) - MSS sonrasi ulasilan en yuksek tepe (1);
        # FVG ust kenari %50'nin altina dustugu andan itibaren emir gecerli (onceki mumlarin tepesiyle olculur).
        tepe = h[i0:p + 1].max()
        dol, iskonto_oldu = -1, False
        for j in range(p + 1, min(n, p + 1 + LIMIT_BEKLE)):
            if e < (sl + tepe) / 2.0:
                iskonto_oldu = True
                if l[j] <= e:
                    dol = j
                    break
            if h[j] >= tp:
                break
            tepe = max(tepe, h[j])
        if dol < 0:
            say["pahali" if not iskonto_oldu else "dolmadi"] += 1
            mesgul = min(n - 1, p + LIMIT_BEKLE)
            continue
        say["islem"] += 1
        if l[dol] <= s:
            sonuc, cik = "STOP", dol
        else:
            isl = ilk(l, dol + 1, s, True)
            ibe = ilk(h, dol + 1, be, False)
            if ibe < 0 or (0 <= isl <= ibe):
                sonuc, cik = ("STOP", isl) if isl >= 0 else ("ACIK", n - 1)
            elif h[ibe] >= tp:
                sonuc, cik = "TP", ibe
            else:
                ib = ilk(l, ibe + 1, e, True)
                it = ilk(h, ibe + 1, tp, False)
                if it >= 0 and (ib < 0 or it < ib):
                    sonuc, cik = "TP", it
                elif ib >= 0:
                    sonuc, cik = "BASABAS", ib
                else:
                    sonuc, cik = "ACIK", n - 1
        mesgul = cik
        R = {"TP": RR, "STOP": -1.0, "BASABAS": 0.0, "ACIK": 0.0}[sonuc]
        mR = SP[p] / risk
        sg = 1 if dirn > 0 else -1
        kayit.append(dict(
            sembol=sembol, yon="LONG" if dirn > 0 else "SHORT", seviye=adlar[tip], pencere=PENCERE[w][2],
            giris_zaman=datetime.utcfromtimestamp(int(T[dol])).strftime("%Y-%m-%d %H:%M"),
            cikis_zaman=datetime.utcfromtimestamp(int(T[cik])).strftime("%Y-%m-%d %H:%M"), cikisT=int(T[cik]),
            giris=sg * e, stop=sg * s, hedef=sg * tp, sonuc=sonuc, R=R, makas_R=round(mR, 3),
            R_net=round(R - mR, 3), dolar=round((R - mR) * RISK_DOLAR, 2)))


def hazirla(df, bilgi, sinir):
    T = df["time"].values.astype(np.int64)
    tny = T - SUNUCU_NY * 3600
    ny = ((tny % 86400) // 60).astype(int)
    key = np.floor_divide(tny + 7 * 3600, 86400)
    wkey = np.floor_divide(key + 3, 7)
    ds = np.r_[0, np.nonzero(np.diff(key))[0] + 1]
    ws = np.r_[0, np.nonzero(np.diff(wkey))[0] + 1]
    de = np.r_[ds[1:] - 1, len(T) - 1]
    gun = np.cumsum(np.r_[0, (np.diff(key) != 0).astype(int)])
    tick = getattr(bilgi, "trade_tick_size", 0) or bilgi.point
    return dict(T=T, O=df["open"].values.astype(float), H=df["high"].values.astype(float),
                L=df["low"].values.astype(float), C=df["close"].values.astype(float),
                SP=df["spread"].values.astype(float) * bilgi.point, ny=ny, gun=gun, ds=ds, de=de, ws=ws,
                tick=tick, sinir=sinir)


def ozet(g):
    n = len(g)
    tp = int((g["sonuc"] == "TP").sum())
    sl = int((g["sonuc"] == "STOP").sum())
    be = int((g["sonuc"] == "BASABAS").sum())
    R = g["R_net"].sum()
    return n, tp, be, sl, (100.0 * tp / n if n else 0.0), R


def tablo(I, kol, baslik):
    s = ["", "== " + baslik + " ==",
         "%-20s %6s %5s %8s %5s %8s %9s %10s" % (kol, "islem", "TP", "BASABAS", "STOP", "basari", "R", "dolar")]
    for k, g in I.groupby(kol):
        n, tp, be, sl, b, R = ozet(g)
        s.append("%-20s %6d %5d %8d %5d %7.1f%% %+9.1f %+10.0f" % (k, n, tp, be, sl, b, R, R * RISK_DOLAR))
    return s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sembol", default="")
    ap.add_argument("--gun", type=int, default=GUN)
    a = ap.parse_args()
    if mt5 is None:
        print("MetaTrader5 paketi yok:  py -3.8 -m pip install MetaTrader5 pandas numpy")
        return
    if not mt5.initialize():
        print("MT5'e baglanilamadi. MT5 acik mi?", mt5.last_error())
        return
    t0 = time.time()
    liste = [x.strip() for x in a.sembol.split(",") if x.strip()] if a.sembol else \
        [x.name for x in (mt5.symbols_get() or []) if getattr(x, "trade_mode", 4) != 0]
    bit = datetime.now() + timedelta(days=1)
    bas = bit - timedelta(days=a.gun + 25)
    sinir = None
    tum = []
    say = dict(govde_alti=0, supurme=0, mss=0, fvg=0, pahali=0, makas=0, dolmadi=0, islem=0)
    print("Taranacak sembol: %d   (1 dk veri, 6 ay)" % len(liste))
    for no, sb in enumerate(liste, 1):
        try:
            mt5.symbol_select(sb, True)
            bilgi = mt5.symbol_info(sb)
            if sinir is None:
                tk = mt5.symbol_info_tick(sb)
                sinir = (int(tk.time) if tk is not None and tk.time else int(time.time())) - a.gun * 86400
            df = cek(sb, bas, bit)
            if bilgi is None or df is None or len(df) < 20000:
                print("%3d/%d %-14s veri yok/az, atlandi" % (no, len(liste), sb))
                continue
            P = hazirla(df, bilgi, sinir)
            k = []
            gecis(P, 1, sb, k, say)
            gecis(P, -1, sb, k, say)
            k = [x for x in k if x["sonuc"] != "ACIK"]
            tum.extend(k)
            if k:
                n, tp, be, sl, b, R = ozet(pd.DataFrame(k))
                print("%3d/%d %-14s islem %3d  TP %3d  BASABAS %3d  STOP %3d  basari %5.1f%%  %+6.1fR  %+7.0f $"
                      % (no, len(liste), sb, n, tp, be, sl, b, R, R * RISK_DOLAR))
            else:
                print("%3d/%d %-14s islem   0" % (no, len(liste), sb))
        except Exception as ex:
            print("%3d/%d %-14s HATA: %s" % (no, len(liste), sb, ex))
    mt5.shutdown()

    klasor = os.path.join(masaustu(), "ict_6ay_" + datetime.now().strftime("%Y%m%d_%H%M"))
    os.makedirs(klasor, exist_ok=True)
    sat = ["ICT ROBOT MANTIGI - 6 AYLIK TEST (%d gun)  %s" % (a.gun, datetime.now().strftime("%d.%m.%Y %H:%M")),
           "10.000 $ ile basladi. Islem basina risk 100 $ (%1). Hedef 2R, 1R'de stop girise. Spread dahil.",
           "Sure: %.0f dk   Sembol: %d" % ((time.time() - t0) / 60.0, len(liste)),
           "", "== ELEME SAYACI (kurulum nerede eleniyor) ==",
           "Govdesi seviyenin altinda kapandi (supurme sayilmadi): %d" % say["govde_alti"],
           "Gecerli supurme (fitil)                             : %d" % say["supurme"],
           "  -> MSS (sert mum govdesi son tepenin ustunde)     : %d" % say["mss"],
           "  -> FVG bulundu                                     : %d" % say["fvg"],
           "  -> 15 dk icinde iskontoya (%%50 alti) hic gecmedi    : %d" % say["pahali"],
           "  -> makas maliyeti 6 $ ustu, elendi                 : %d" % say["makas"],
           "  -> limit 15 dk'da dolmadi / once hedef geldi       : %d" % say["dolmadi"],
           "  -> ISLEM                                           : %d" % say["islem"]]
    I = pd.DataFrame(tum)
    if not len(I):
        sat.append("\nHic islem yok.")
    else:
        I = I.sort_values("cikisT")
        bakiye = BASLANGIC + I["dolar"].cumsum()
        tepe = np.maximum.accumulate(np.r_[BASLANGIC, bakiye.values])
        dd = (tepe[1:] - bakiye.values).max()
        n, tp, be, sl, b, R = ozet(I)
        sat += ["", "== SONUC ==",
                "Islem %d   TP %d   BASABAS %d   STOP %d   basari %%%.1f" % (n, tp, be, sl, b),
                "Toplam %+.1fR  =  %+.0f $     10.000 $  ->  %.0f $" % (R, R * RISK_DOLAR, BASLANGIC + R * RISK_DOLAR),
                "En buyuk dusus (tepeden): %.0f $" % dd]
        sat += tablo(I, "yon", "LONG / SHORT")
        sat += tablo(I, "seviye", "SEVIYE TIPI (hangi tepe/dip ise yariyor)")
        sat += tablo(I, "pencere", "SAAT")
        S = []
        for sb, g in I.groupby("sembol"):
            n, tp, be, sl, b, R = ozet(g)
            S.append(dict(sembol=sb, islem=n, TP=tp, BASABAS=be, STOP=sl, basari=round(b, 1), R=round(R, 2),
                          dolar=round(R * RISK_DOLAR, 0)))
        S = pd.DataFrame(S).sort_values("R", ascending=False)
        S.to_csv(os.path.join(klasor, "1_semboller.csv"), index=False, sep=";", decimal=",")
        I.drop(columns=["cikisT"]).to_csv(os.path.join(klasor, "2_islemler.csv"), index=False, sep=";", decimal=",")
        for ad in ("US100.cash", "EURUSD"):
            r = S[S["sembol"] == ad]
            if len(r):
                r = r.iloc[0]
                sat.append("%-12s islem %d  basari %%%.1f  %+.1fR  %+.0f $" % (ad, r["islem"], r["basari"], r["R"],
                                                                         r["dolar"]))
        E = S[(S["islem"] >= LISTE_MIN_ISLEM) & (S["basari"] >= LISTE_MIN_BASARI)]
        sat += ["", "== EN AZ %d ISLEM VE BASARI %%%d USTU SEMBOLLER: %d ==" % (LISTE_MIN_ISLEM, LISTE_MIN_BASARI, len(E)),
                "%-14s %6s %5s %8s %5s %8s %8s %8s" % ("sembol", "islem", "TP", "BASABAS", "STOP", "basari", "R", "dolar")]
        for _, r in E.iterrows():
            sat.append("%-14s %6d %5d %8d %5d %7.1f%% %+8.1f %+8.0f" % (r["sembol"], r["islem"], r["TP"], r["BASABAS"],
                                                                     r["STOP"], r["basari"], r["R"], r["dolar"]))
        sat += ["", "== EN IYI 20 SEMBOL (R) =="]
        for _, r in S.head(20).iterrows():
            sat.append("%-14s islem %4d  basari %5.1f%%  %+7.1fR  %+7.0f $" % (r["sembol"], r["islem"], r["basari"],
                                                                            r["R"], r["dolar"]))
        sat += ["", "== EN KOTU 10 ==", ", ".join("%s %+.1fR" % (r["sembol"], r["R"]) for _, r in S.tail(10).iterrows())]
    yaz = "\n".join(sat)
    with open(os.path.join(klasor, "0_OZET.txt"), "w", encoding="utf-8") as f:
        f.write(yaz)
    print("\n" + yaz)
    print("\nSonuclar: " + klasor)


if __name__ == "__main__":
    main()
