# -*- coding: utf-8 -*-
"""
EKIN MODELI - 6 AYLIK TARAMA - BUTUN SEMBOLLER - TEK MANTIK (ayar taramasi YOK)
================================================================================
Calistir:   py -3.8 C:\\Users\\User\\Desktop\\ekin_6ay_tarama.py
Gerekli:    py -3.8 -m pip install MetaTrader5 pandas numpy
Sadece bazi semboller:   py -3.8 ekin_6ay_tarama.py --sembol BTCUSD,XAUUSD,EURUSD
MT5 acik olmali. SADECE gecmis veri okur, ISLEM ACMAZ.
Sonuclar MASAUSTUNE:  Masaustu\\ekin_6ay_<tarih>\\0_OZET.txt , 1_semboller.csv , 2_islemler.csv

MANTIK (Ekin Bootcamp; LONG anlatiliyor, SHORT birebir tersi)
  1) GUNLUK YON (41,42): dun govdeyle onceki gunun tepesinin ustunde kapandi -> LONG gunu.
     Onceki gunun dibini alip ustunde kapandi -> LONG gunu.  Tersleri SHORT gunu.  Ic gun = islem yok.
  2) SEVIYE (23,28) - SADECE BUYUK ZAMAN DILIMI:
       onceki gunun dibi (PDL), onceki haftanin dibi (PWL, bu hafta alinmamissa),
       alis yonlu GUNLUK FVG ve HAFTALIK FVG (dolmamis; fiyat yukaridan gelip icine girer).
     Asya / Londra / 5 dk swing dipleri KULLANILMAZ (Ekin 28: "bu onemli bir likidite degil").
  3) UCUZ BOLGE (24): LONG sadece son 10 gunun araliginin ORTASININ ALTINDA (discount),
                      SHORT sadece USTUNDE (premium).
  4) KILLZONE (17,18) NY saati: FOREX/ALTIN/HISSE 02-05 ve 07-10, ENDEKS 08:30-11, KRIPTO gun boyu.
  5) SUPURME: killzone icinde 5 dk mum seviyenin altina iner.
  6a) IFVG (33,34,41): supurmeye giderken birakilan ters FVG, GUCLU mumun GOVDESIYLE kirilir
      -> o mumun kapanisinda giris.
  6b) FVG (19,20,38): guclu mum (displacement) + son swing tepenin ustunde govde kapanisi (MSS)
      -> kirilim bacagindaki FVG'nin ORTASINA limit (en fazla 1 saat bekler).
  7) STOP: supurme mumunun GOVDESININ alti + ATR x 0.10 nefes payi (en az 0.3, en fazla 4 ATR).
  8) HEDEF: 2R (stopun 2 kati).  NY 16:00'da acik islem kapanir.  Gunde en fazla 2, killzone basina 1.
  GUCLU MUM = govde >= son 20 mumun ortalama govdesi x 1.5  VE  govde >= mum boyunun yarisi.
  FVG       = 3 mumluk bosluk, en az ATR(14) x 0.10.
  Spread dahil (giris mumunun spread'i R'den dusulur).  1R = 22.5 $.
"""
from __future__ import print_function

import argparse
import math
import os
import sys
import time
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

try:
    import MetaTrader5 as mt5
except ImportError:
    mt5 = None

GUN = 182
SUNUCU_NY = 7
RISK_DOLAR = 22.5
RR = 2.0
GUCLU_KAT = 1.5
GUCLU_GOVDE = 0.5
FVG_MIN_ATR = 0.10
IFVG_GERI = 20
SETUP_MAX = 36
LIMIT_BEKLE = 12
STOP_PAY = 0.10
MIN_STOP = 0.30
MAX_STOP = 4.0
MAX_GUNLUK = 2
KZ_BASINA = 1
PD_GUN = 10
HTF_FVG_GUN = 60
HTF_FVG_HAFTA = 12
MIN_ISLEM = 5

KZ_AD = {1: "LONDRA", 2: "NEWYORK", 3: "KRIPTO"}
INF = float("inf")


# ----------------------------------------------------------------- yardimci
def masaustu():
    ev = os.path.expanduser("~")
    for p in (os.path.join(ev, "Desktop"), os.path.join(ev, "OneDrive", "Desktop"), os.path.join(ev, "Masaüstü")):
        if os.path.isdir(p):
            return p
    return os.getcwd()


def sembol_tipi(ad):
    s = ad.upper()
    for k in ("BTC", "ETH", "LTC", "XRP", "SOL", "ADA", "DOGE", "BCH", "DOT", "BNB", "AVAX", "LINK",
              "XLM", "XMR", "DASH", "AAVE"):
        if k in s:
            return 3
    for k in ("US100", "US30", "US500", "US2000", "USTEC", "NAS", "SPX", "SP500", "DJ", "DOW", "GER", "DE40",
              "DAX", "UK100", "FTSE", "FRA40", "CAC", "JP225", "NIKKEI", "EU50", "STOXX", "HK50", "AUS200",
              "SPN35", "N25"):
        if k in s:
            return 2
    return 1


def kz_bul(m, tip):
    if tip == 3:
        return 3 if (m < 900 or m >= 1020) else 0
    if tip == 2:
        return 2 if 510 <= m < 660 else 0
    if 120 <= m < 300:
        return 1
    if 420 <= m < 600:
        return 2
    return 0


def kz_bitis(kz, tip):
    if kz == 1:
        return 300
    if kz == 2:
        return 660 if tip == 2 else 600
    return 900


def cek(sembol, bas, bit):
    parcalar, a = [], bas
    while a < bit:
        b = min(a + timedelta(days=30), bit)
        r = None
        for _ in range(3):
            r = mt5.copy_rates_range(sembol, mt5.TIMEFRAME_M5, a, b)
            if r is not None:
                break
            time.sleep(0.5)
        if r is not None and len(r):
            d = pd.DataFrame(r)
            if "spread" not in d.columns:
                d["spread"] = 0
            parcalar.append(d[["time", "open", "high", "low", "close", "spread"]])
        a = b
    if not parcalar:
        return None
    return pd.concat(parcalar).drop_duplicates("time").sort_values("time").reset_index(drop=True)


# ----------------------------------------------------------------- hazirlik
def hazirla(df, point):
    T = df["time"].values.astype(np.int64)
    O = df["open"].values.astype(float)
    H = df["high"].values.astype(float)
    L = df["low"].values.astype(float)
    C = df["close"].values.astype(float)
    SP = df["spread"].values.astype(float) * point
    tny = T - SUNUCU_NY * 3600
    ny = ((tny % 86400) // 60).astype(int)
    key = np.floor_divide(tny + 7 * 3600, 86400)          # gun NY 17:00'de baslar
    wkey = np.floor_divide(key + 3, 7)                     # hafta pazartesi ile baslar
    ds = np.r_[0, np.nonzero(np.diff(key))[0] + 1]
    ws = np.r_[0, np.nonzero(np.diff(wkey))[0] + 1]
    gun = np.cumsum(np.r_[0, (np.diff(key) != 0).astype(int)])
    haf = np.cumsum(np.r_[0, (np.diff(wkey) != 0).astype(int)])
    de = np.r_[ds[1:] - 1, len(T) - 1]
    we = np.r_[ws[1:] - 1, len(T) - 1]
    D = dict(H=np.maximum.reduceat(H, ds), L=np.minimum.reduceat(L, ds), C=C[de], O=O[ds])
    W = dict(H=np.maximum.reduceat(H, ws), L=np.minimum.reduceat(L, ws), C=C[we])
    pc = np.r_[C[0], C[:-1]]
    tr = np.maximum(H - L, np.maximum(np.abs(H - pc), np.abs(L - pc)))
    atr = pd.Series(tr).rolling(14, min_periods=1).mean().values
    ort = pd.Series(np.abs(C - O)).shift(1).rolling(20, min_periods=1).mean().fillna(0).values
    nd = len(ds)
    yon = np.zeros(nd, dtype=int)
    for d in range(2, nd):
        h1, l1, c1, h2, l2 = D["H"][d - 1], D["L"][d - 1], D["C"][d - 1], D["H"][d - 2], D["L"][d - 2]
        bull = (c1 > h2) or (l1 < l2 and c1 > l2)
        bear = (c1 < l2) or (h1 > h2 and c1 < h2)
        if bull and not bear:
            yon[d] = 1
        elif bear and not bull:
            yon[d] = -1
    mid = np.full(nd, np.nan)
    for d in range(PD_GUN, nd):
        mid[d] = (D["H"][d - PD_GUN:d].max() + D["L"][d - PD_GUN:d].min()) / 2.0
    bas = 25
    while bas < len(T) and (gun[bas] < PD_GUN + 1):
        bas += 1
    return dict(T=T, O=O, H=H, L=L, C=C, SP=SP, ny=ny, gun=gun, haf=haf, D=D, W=W, atr=atr, ort=ort,
                yon=yon, mid=mid, bas=bas, n=len(T) - 1)   # son (olusan) mum haric


def fvg_bolgeleri(hi, lo, cl):
    """Yon uzayinda alis FVG'leri: (olustugu bar, ust, alt, bozuldugu bar)."""
    z = []
    for k in range(2, len(hi)):
        if lo[k] > hi[k - 2]:
            top, bot = lo[k], hi[k - 2]
            inv = INF
            for e in range(k + 1, len(hi)):
                if cl[e] < bot:
                    inv = e
                    break
            z.append((k, top, bot, inv))
    return z


# ----------------------------------------------------------------- tek yon taramasi
def gecis(A, dirn, tip, sembol, kayit):
    if dirn > 0:
        o, h, l, c = A["O"], A["H"], A["L"], A["C"]
        dHi, dLo, dCl = A["D"]["H"], A["D"]["L"], A["D"]["C"]
        wHi, wLo, wCl = A["W"]["H"], A["W"]["L"], A["W"]["C"]
        mid = A["mid"]
        adlar = ("PDL", "PWL", "GUNLUK_FVG", "HAFTALIK_FVG")
    else:
        o, h, l, c = -A["O"], -A["L"], -A["H"], -A["C"]
        dHi, dLo, dCl = -A["D"]["L"], -A["D"]["H"], -A["D"]["C"]
        wHi, wLo, wCl = -A["W"]["L"], -A["W"]["H"], -A["W"]["C"]
        mid = -A["mid"]
        adlar = ("PDH", "PWH", "GUNLUK_FVG", "HAFTALIK_FVG")
    T, ny, gun, haf, atr, ort, SP = A["T"], A["ny"], A["gun"], A["haf"], A["atr"], A["ort"], A["SP"]
    n = A["n"]
    body = c - o
    rng = h - l
    guclu = (body > 0) & (body >= GUCLU_KAT * ort) & (body >= GUCLU_GOVDE * rng)
    zd = fvg_bolgeleri(dHi, dLo, dCl)
    zw = fvg_bolgeleri(wHi, wLo, wCl)

    def swing(b, i):
        j0, j1 = min(b - 1, i - 2), max(b - 40, 2)
        for j in range(j0, j1 - 1, -1):
            if j + 2 >= n:
                continue
            x = h[j]
            if x > h[j - 1] and x > h[j - 2] and x >= h[j + 1] and x >= h[j + 2]:
                return x
        return None

    def stop_hesap(e, i, sb, slow):
        pay = STOP_PAY * atr[i]
        s = min(o[sb], c[sb]) - pay
        if s >= e:
            s = slow - pay
        if s >= e:
            return None
        if e - s < MIN_STOP * atr[i]:
            s = e - MIN_STOP * atr[i]
        if e - s > MAX_STOP * atr[i]:
            return None
        return s

    def bitir(x, i, px, sonuc):
        risk = x["g"] - x["s"]
        r = (px - x["g"]) / risk if risk > 0 else 0.0
        mal = x["sp"] / risk if risk > 0 else 0.0
        sg = 1 if dirn > 0 else -1
        kayit.append(dict(
            sembol=sembol, yon="LONG" if dirn > 0 else "SHORT", tip=x["tip"], seviye=x["sev"], kz=x["kz"],
            giris_zaman=datetime.utcfromtimestamp(int(x["tG"])).strftime("%Y-%m-%d %H:%M"),
            cikis_zaman=datetime.utcfromtimestamp(int(T[i])).strftime("%Y-%m-%d %H:%M"),
            tG=int(x["tG"]), giris=sg * x["g"], stop=sg * x["s"], hedef=sg * x["t"], cikis=sg * px,
            sonuc=sonuc, R=round(r, 3), R_net=round(r - mal, 3)))

    curD = curW = -1
    lv = []
    wkMin = INF
    gunIs = 0
    kzS = [0, 0, 0, 0]
    su = pd_ = tr = False
    suBar = suIlk = suKz = 0
    suLow = 0.0
    mss = None
    pdBar = pdKz = trBar = 0
    x = None
    for i in range(A["bas"], n):
        d, w, m = gun[i], haf[i], ny[i]
        if w != curW:
            curW, wkMin = w, INF
        if d != curD:
            curD = d
            if tr:
                bitir(x, i, o[i], "KAPANIS")
                tr = False
            pd_ = su = False
            gunIs, kzS = 0, [0, 0, 0, 0]
            lv = []
            if d >= 1:
                lv.append([dLo[d - 1], adlar[0], True])
            if w >= 1 and wkMin > wLo[w - 1]:
                lv.append([wLo[w - 1], adlar[1], True])
            for (k, top, bot, inv) in zd:
                if d - HTF_FVG_GUN <= k <= d - 1 and inv >= d and o[i] > top:
                    lv.append([top, adlar[2], True])
            for (k, top, bot, inv) in zw:
                if w - HTF_FVG_HAFTA <= k <= w - 1 and inv >= w and o[i] > top:
                    lv.append([top, adlar[3], True])
        # acik islem
        if tr and i > trBar:
            if l[i] <= x["s"]:
                bitir(x, i, x["s"], "STOP"); tr = False
            elif h[i] >= x["t"]:
                bitir(x, i, x["t"], "TP"); tr = False
            elif 960 <= m < 1020:
                bitir(x, i, o[i], "KAPANIS"); tr = False
        # bekleyen limit
        if pd_:
            if l[i] <= x["g"]:
                pd_, tr, trBar = False, True, i
                x["tG"] = T[i]
                x["sp"] = SP[i]
                gunIs += 1
                kzS[pdKz] += 1
                if l[i] <= x["s"]:
                    bitir(x, i, x["s"], "STOP"); tr = False
            elif h[i] >= x["t"] or i - pdBar > LIMIT_BEKLE or (kz_bitis(pdKz, tip) + 60 < m < 1020) or (960 <= m < 1020):
                pd_ = False
        # supurme
        kz = kz_bul(m, tip)
        for L_ in lv:
            if not L_[2] or l[i] >= L_[0]:
                continue
            L_[2] = False
            if su or tr or pd_ or kz <= 0:
                continue
            if gunIs >= MAX_GUNLUK or kzS[kz] >= KZ_BASINA:
                continue
            if A["yon"][d] != dirn:
                continue
            su, suBar, suIlk, suLow, suKz = True, i, i, l[i], kz
            x = dict(sev=L_[1], kz=KZ_AD[kz], tip="", g=0.0, s=0.0, t=0.0, tG=0, sp=0.0)
            mss = swing(i, i)
        if su and i > suBar and l[i] < suLow:
            suLow, suBar = l[i], i
            mss = swing(i, i)
        # giris
        if su:
            bitti = False
            if guclu[i]:
                for k in range(i - 1, max(suIlk - IFVG_GERI, 2) - 1, -1):
                    top, bot = l[k - 2], h[k]
                    if top - bot < FVG_MIN_ATR * atr[i]:
                        continue
                    if not (o[i] < top < c[i]):
                        continue
                    if k + 1 < i and np.any(c[k + 1:i] > top):
                        continue
                    e = c[i]
                    s = stop_hesap(e, i, suBar, suLow)
                    if s is not None and e < mid[d]:
                        x.update(tip="IFVG", g=e, s=s, t=e + RR * (e - s), tG=T[i], sp=SP[i])
                        tr, trBar = True, i
                        gunIs += 1
                        kzS[suKz] += 1
                    bitti = True
                    break
            if not bitti and mss is not None and c[i] > mss:
                if np.any(guclu[suBar:i + 1]):
                    for k in range(i, suBar + 1, -1):
                        if l[k] - h[k - 2] >= FVG_MIN_ATR * atr[i]:
                            e = (l[k] + h[k - 2]) / 2.0
                            s = stop_hesap(e, i, suBar, suLow)
                            if s is not None and e < mid[d]:
                                x.update(tip="FVG", g=e, s=s, t=e + RR * (e - s), tG=T[i])
                                pd_, pdBar, pdKz = True, i, suKz
                            break
                bitti = True
            if not bitti and (i - suIlk > SETUP_MAX or (kz_bitis(suKz, tip) + 30 < m < 1020)):
                bitti = True
            if bitti:
                su = False
        wkMin = min(wkMin, l[i])
    if tr:
        bitir(x, n - 1, c[n - 1], "ACIK")


# ----------------------------------------------------------------- ozet
def ozet_satir(g):
    n = len(g)
    tp = int((g["sonuc"] == "TP").sum())
    sl = int((g["sonuc"] == "STOP").sum())
    kp = n - tp - sl
    R = g["R_net"].sum()
    return n, tp, sl, kp, (100.0 * tp / n if n else 0.0), R


def tablo(df, kol, baslik):
    sat = ["", "== " + baslik + " =="]
    sat.append("%-16s %6s %5s %5s %5s %8s %9s %10s" % (kol, "islem", "TP", "STOP", "KAP", "basari", "R", "dolar"))
    for k, g in df.groupby(kol):
        n, tp, sl, kp, b, R = ozet_satir(g)
        sat.append("%-16s %6d %5d %5d %5d %7.1f%% %+9.1f %+10.0f" % (k, n, tp, sl, kp, b, R, R * RISK_DOLAR))
    return sat


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
    if a.sembol:
        liste = [s.strip() for s in a.sembol.split(",") if s.strip()]
    else:
        liste = [s.name for s in (mt5.symbols_get() or []) if getattr(s, "trade_mode", 4) != 0]
    bit = datetime.now() + timedelta(days=1)
    bas = bit - timedelta(days=a.gun + 30)
    sinir = int(time.time()) - a.gun * 86400
    yari = int(time.time()) - (a.gun // 2) * 86400
    hepsi, sat_s = [], []
    print("Taranacak sembol: %d   (6 ay, 5 dk veri)" % len(liste))
    for no, sb in enumerate(liste, 1):
        try:
            mt5.symbol_select(sb, True)
            bilgi = mt5.symbol_info(sb)
            df = cek(sb, bas, bit)
            if bilgi is None or df is None or len(df) < 5000:
                print("%3d/%d %-14s veri yok/az, atlandi" % (no, len(liste), sb))
                continue
            A = hazirla(df, bilgi.point)
            tip = sembol_tipi(sb)
            kayit = []
            gecis(A, 1, tip, sb, kayit)
            gecis(A, -1, tip, sb, kayit)
            k = pd.DataFrame(kayit)
            if len(k):
                k = k[(k["tG"] >= sinir) & (k["sonuc"] != "ACIK")]
            hepsi.append(k)
            if len(k):
                n, tp, sl, kp, b, R = ozet_satir(k)
                r1 = k[k["tG"] < yari]["R_net"].sum()
                r2 = k[k["tG"] >= yari]["R_net"].sum()
                rl = k[k["yon"] == "LONG"]["R_net"].sum()
                rs = k[k["yon"] == "SHORT"]["R_net"].sum()
            else:
                n = tp = sl = kp = 0
                b = R = r1 = r2 = rl = rs = 0.0
            sat_s.append(dict(sembol=sb, islem=n, TP=tp, STOP=sl, KAPANIS=kp, basari_yuzde=round(b, 1),
                              R=round(R, 2), dolar=round(R * RISK_DOLAR, 0), R_ilk3ay=round(r1, 2),
                              R_son3ay=round(r2, 2), R_long=round(rl, 2), R_short=round(rs, 2),
                              iki_yari_arti=bool(r1 > 0 and r2 > 0)))
            print("%3d/%d %-14s islem %3d  TP %3d  STOP %3d  basari %5.1f%%  %+6.1fR  (%+.0f $)"
                  % (no, len(liste), sb, n, tp, sl, b, R, R * RISK_DOLAR))
        except Exception as ex:
            print("%3d/%d %-14s HATA: %s" % (no, len(liste), sb, ex))
    mt5.shutdown()

    klasor = os.path.join(masaustu(), "ekin_6ay_" + datetime.now().strftime("%Y%m%d_%H%M"))
    os.makedirs(klasor, exist_ok=True)
    S = pd.DataFrame(sat_s)
    I = pd.concat([h for h in hepsi if len(h)]) if any(len(h) for h in hepsi) else pd.DataFrame()
    if len(S):
        S = S.sort_values("R", ascending=False)
        S.to_csv(os.path.join(klasor, "1_semboller.csv"), index=False, sep=";", decimal=",")
    if len(I):
        I.drop(columns=["tG"]).to_csv(os.path.join(klasor, "2_islemler.csv"), index=False, sep=";", decimal=",")

    sat = ["EKIN MODELI - 6 AYLIK TARAMA  (%s)" % datetime.now().strftime("%d.%m.%Y %H:%M"),
           "Tek mantik, ayar taramasi yok. Seviye: PDH/PDL, PWH/PWL, gunluk/haftalik FVG. TP 2R. 1R = %.1f $."
           % RISK_DOLAR, "Sure: %.0f dk" % ((time.time() - t0) / 60.0)]
    if len(I):
        n, tp, sl, kp, b, R = ozet_satir(I)
        sat += ["", "TOPLAM: %d islem  TP %d  STOP %d  KAPANIS %d  basari %%%.1f  %+.1fR  = %+.0f $"
                % (n, tp, sl, kp, b, R, R * RISK_DOLAR),
                "Not: 2R hedefte basabas icin basari en az %33.4 olmali."]
        sat += tablo(I, "yon", "LONG / SHORT")
        sat += tablo(I, "tip", "GIRIS TIPI")
        sat += tablo(I, "seviye", "SEVIYE TIPI (hangi tepe/dip ise yariyor)")
        sat += tablo(I, "kz", "SEANS")
    if len(S):
        E = S[S["islem"] >= MIN_ISLEM]
        sat += ["", "== EN BASARILI 30 SEMBOL (en az %d islem, R'ye gore) ==" % MIN_ISLEM,
                "%-14s %5s %4s %5s %7s %8s %8s %8s %8s %8s %8s"
                % ("sembol", "islem", "TP", "STOP", "basari", "R", "dolar", "ilk3ay", "son3ay", "long", "short")]
        for _, r in E.head(30).iterrows():
            sat.append("%-14s %5d %4d %5d %6.1f%% %+8.1f %+8.0f %+8.1f %+8.1f %+8.1f %+8.1f %s"
                       % (r["sembol"], r["islem"], r["TP"], r["STOP"], r["basari_yuzde"], r["R"], r["dolar"],
                          r["R_ilk3ay"], r["R_son3ay"], r["R_long"], r["R_short"],
                          "<- iki yarida da arti" if r["iki_yari_arti"] else ""))
        G = E[E["iki_yari_arti"]]
        sat += ["", "== HEM ILK 3 AYDA HEM SON 3 AYDA ARTI OLANLAR (%d sembol) ==" % len(G),
                ", ".join(G["sembol"].tolist()) or "yok"]
        sat += ["", "== EN KOTU 10 ==", ", ".join("%s %+.1fR" % (r["sembol"], r["R"]) for _, r in E.tail(10).iterrows())]
    yaz = "\n".join(sat)
    with open(os.path.join(klasor, "0_OZET.txt"), "w", encoding="utf-8") as f:
        f.write(yaz)
    print("\n" + yaz)
    print("\nSonuclar: " + klasor)


if __name__ == "__main__":
    main()
