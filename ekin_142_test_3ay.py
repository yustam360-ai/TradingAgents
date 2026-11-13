# -*- coding: utf-8 -*-
"""
EKIN MODELI - 142 SEMBOL, HER BIRI KENDI MANTIGIYLA - SON 3 AY - GUN GUN - GERCEKCI TEST
=========================================================================================
Python 3.8:   py -3.8 ekin_142_test_3ay.py
Gerekli:      py -3.8 -m pip install MetaTrader5 pandas numpy
TEK DOSYA. MT5'e baglanir, SADECE gecmis veri okur, ISLEM ACMAZ.
SONUCLAR MASAUSTUNE:  Masaustu\\ekin_142_test_<tarih>\\0_OZET.txt

- 142 sembol, her biri 6 aylik testte bulunan KENDI mantigiyla (asagidaki MANTIK listesi, degistirilmedi).
- Son 92 gun, gun gun; her an sadece o ana kadar olusmus mumlara bakilir.
- Kurallar 6 aylik testle AYNI: risk 15 $, SPREAD DAHIL (MT5 1 dk spread'i), spread maliyeti 6 $'i gecen islem
  acilmaz, en kucuk lotta zarar 30 $'i gecerse islem acilmaz, ayni dakikada stop ve TP = STOP.
- NY 16:00 KAPATMA ACIK (Ekin 42 "gun icinde cikmak", 6 aylik testle ayni): TP ya da STOP olmayan islem
  NY 16:00'da (TR kis 00:00) o anki fiyattan kapanir -> "SURE" (kar da olabilir zarar da).
  Kapatmasiz hali icin:  py -3.8 ekin_142_test_3ay.py --kapatma_yok   (o zaman acik kalanlar "ACIK" yazilir)
- 10.000 $ ile baslar; butun semboller ayni hesapta, ayni anda.

CIKTI: 0_OZET.txt (genel 10.000 $, ay ay, sembol sembol basariya gore liste, %50 ustu)
       1_islemler.csv (her islemin karti)
"""
from __future__ import print_function

import argparse
import itertools
import os
import sys
import time
from datetime import date, datetime, timedelta, timezone

import numpy as np
import pandas as pd

try:
    import MetaTrader5 as mt5
except ImportError:
    mt5 = None

RISK = 15.0
EN_FAZLA = 30.0
MAKAS_SINIR = 6.0
BASLANGIC = 10000.0
SUNUCU_NY = 7
GUN_SAYISI = 92
NY_KAPAT = True
KAPANIS = 23 * 60            # sunucu 23:00 = NY 16:00
ESIT_TOL = (0.05, 0.1, 0.2)
SORULAR = [("S1_MSS", ["SART", "IFVG_YETER"]), ("S2_YON", ["YOK", "EKIN", "ICT"]),
           ("S3_GIRIS", ["ORTA", "KENAR", "KAPANIS"]), ("S4_STOP", ["SWING_GOVDE", "FVG_MUM", "SUPURULEN_UC"]),
           ("S5_TP", ["2R", "3R", "LIKIDITE"]), ("S6_SEVIYE", ["EKIN", "ICT"]), ("S7_ZAMAN", ["EKIN_5_3", "ICT_15_5"]),
           ("S9_DISIPLIN", ["YOK", "EKIN"]), ("S11_EMIR", ["SEANS_SONU", "2_SAAT"]), ("S12_SHARP", ["YOK", "SART"]),
           ("S13_ESIT_TOL", ["0.05ATR", "0.1ATR", "0.2ATR"])]
SQ = [s for s, _ in SORULAR]
MANTIKLAR = list(itertools.product(*[range(len(v)) for _, v in SORULAR]))
MI = {m: i for i, m in enumerate(MANTIKLAR)}
NM = len(MANTIKLAR)
SONUC_KOD = {1: "TP", -1: "STOP", 0: "SURE"}
SAY = {"pencere": 0, "supurme": 0, "kirilim": 0, "kurulum": 0}
EKIN_SEV = {"PDH", "PWH", "ASYA", "LONDRA", "NY_PM", "ESIT_TEPE", "FVG_1S", "FVG_4S"}
ICT_SEV = {"PDH", "ESIT_TEPE", "FVG_1S", "FVG_4S", "FVG_GUNLUK"}


def mad(m):
    return " ".join("%s=%s" % (SORULAR[i][0].split("_", 1)[1], SORULAR[i][1][v]) for i, v in enumerate(m))


def ilk(arr, i0, deger, esit):
    """arr[i0:] icinde ilk (>= deger | > deger) indeks; yoksa len(arr). Parca parca arar."""
    n = len(arr)
    i, adim = i0, 512
    while i < n:
        j = min(n, i + adim)
        b = arr[i:j] >= deger if esit else arr[i:j] > deger
        if b.any():
            return i + int(np.argmax(b))
        i, adim = j, adim * 4
    return n


# ----------------------------------------------------------------- saat
def _pazar(y, ay, kacinci):
    if kacinci > 0:
        d = date(y, ay, 1)
        d += timedelta(days=(6 - d.weekday()) % 7)
        return d + timedelta(days=7 * (kacinci - 1))
    d = date(y, ay + 1, 1) - timedelta(days=1)
    return d - timedelta(days=(d.weekday() - 6) % 7)


def ny_utc(d):
    return -4 if _pazar(d.year, 3, 2) <= d < _pazar(d.year, 11, 1) else -5


def sunucu_utc(d):
    return ny_utc(d) + SUNUCU_NY


def tr(dk):
    dk = int(dk)
    g = date(1970, 1, 1) + timedelta(days=dk // 1440)
    return (datetime(1970, 1, 1) + timedelta(minutes=dk + (3 - sunucu_utc(g)) * 60)).strftime("%Y-%m-%d %H:%M")


def saat_dogrula(semboller):
    global SUNUCU_NY
    bugun = datetime.now(timezone.utc).date()
    beklenen = sunucu_utc(bugun)
    simdi = time.time()
    for s in ["BTCUSD", "ETHUSD", "EURUSD", "GBPUSD"] + list(semboller[:20]):
        try:
            if not mt5.symbol_select(s, True):
                continue
            tk = mt5.symbol_info_tick(s)
        except Exception:
            tk = None
        if tk is None or not getattr(tk, "time", 0):
            continue
        f = (tk.time - simdi) / 3600.0
        y = round(f)
        if abs(f - y) * 60 > 3:
            continue
        if y == beklenen:
            return "MT5 sunucu saati UTC%+d (%s) = New York + %d -> DOGRULANDI." % (y, s, SUNUCU_NY)
        SUNUCU_NY = int(y - ny_utc(bugun))
        return "UYARI: sunucu UTC%+d bulundu (beklenen UTC%+d). Ayarlandi: sunucu = NY %+d." % (y, beklenen, SUNUCU_NY)
    return "MT5 saati kontrol edilemedi; kural: sunucu = New York + %d." % SUNUCU_NY


def masaustu():
    for p in (os.path.join(os.path.expanduser("~"), "Desktop"), os.path.join(os.path.expanduser("~"), "Masaüstü"),
              os.path.join(os.path.expanduser("~"), "OneDrive", "Desktop")):
        if os.path.isdir(p):
            return p
    return os.getcwd()


# ----------------------------------------------------------------- veri
def cek(sembol, tf, bas, bit, parca_gun):
    parcalar, a = [], bas
    kol = ["time", "open", "high", "low", "close", "spread"]
    while a < bit:
        b = min(a + timedelta(days=parca_gun), bit)
        r = None
        for _ in range(3):
            r = mt5.copy_rates_range(sembol, tf, a, b)
            if r is not None:
                break
            time.sleep(0.5)
        if r is not None and len(r):
            d = pd.DataFrame(r)
            if "spread" not in d.columns:
                d["spread"] = 0
            parcalar.append(d[kol])
        a = b
    if not parcalar:
        return None
    return pd.concat(parcalar).drop_duplicates("time").sort_values("time").reset_index(drop=True)


def deger_lot(s, bilgi):
    v = None
    try:
        tk = mt5.symbol_info_tick(s)
        p = float(tk.bid) if tk is not None and tk.bid > 0 else None
        if p:
            d = max(p * 0.001, bilgi.point * 100)
            k = mt5.order_calc_profit(mt5.ORDER_TYPE_BUY, s, 1.0, p, p - d)
            if k is not None and k < 0:
                v = -float(k) / d
    except Exception:
        v = None
    if not v:
        tv = getattr(bilgi, "trade_tick_value_loss", 0) or getattr(bilgi, "trade_tick_value", 0)
        ts = getattr(bilgi, "trade_tick_size", 0)
        if tv and ts:
            v = tv / ts
    return v


def mumlar(T, O, H, L, C, K):
    df = pd.DataFrame({"k": T // K, "o": O, "h": H, "l": L, "c": C}).groupby("k").agg(
        o=("o", "first"), h=("h", "max"), l=("l", "min"), c=("c", "last"))
    return (df.index.to_numpy(np.int64) * K,) + tuple(df[x].to_numpy(float) for x in ("o", "h", "l", "c"))


def atr(h, l, c, n=14):
    pc = np.r_[c[0], c[:-1]]
    t = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
    return pd.Series(t).rolling(n, min_periods=1).mean().to_numpy()




# ----------------------------------------------------------------- gunluk yon (S2)
def yon_ekin(dH, dL, dC):
    n = len(dC)
    ek = np.zeros(n, dtype=np.int8)
    for k in range(2, n):
        y, p = k - 1, k - 2
        if dC[y] > dH[p]:
            ek[k] = 1
        elif dC[y] < dL[p]:
            ek[k] = -1
        else:
            ust, alt = dH[y] > dH[p], dL[y] < dL[p]
            if ust and not alt:
                ek[k] = -1
            elif alt and not ust:
                ek[k] = 1
    return ek


def yon_ict(dH, dL, dC):
    """dun, dolmamis bir gunluk FVG'ye girip saygi duyduysa: bullish FVG = AL (+1), bearish FVG = SAT (-1)"""
    n = len(dC)
    ic = np.zeros(n, dtype=np.int8)
    for k in range(3, n):
        y = k - 1
        bul = ber = False
        for c in range(2, k - 1):
            a = c - 2
            if dH[a] < dL[c] and (c + 1 > k - 2 or dL[c + 1:k - 1].min() > dH[a]):
                if dL[y] <= dL[c] and dC[y] > dH[a]:
                    bul = True
            if dL[a] > dH[c] and (c + 1 > k - 2 or dH[c + 1:k - 1].max() < dL[a]):
                if dH[y] >= dH[c] and dC[y] < dL[a]:
                    ber = True
        ic[k] = 1 if (bul and not ber) else (-1 if (ber and not bul) else 0)
    return ic


# ----------------------------------------------------------------- bir sembol
class Sembol(object):
    def __init__(self, m1, bilgi, vpl, forex, bas_dk):
        self.T = m1["time"].to_numpy(np.int64) // 60
        T = self.T
        self.O, self.H, self.L, self.C = [m1[k].to_numpy(float) for k in ("open", "high", "low", "close")]
        self.SP = m1["spread"].to_numpy(float) * float(bilgi.point)
        self.bilgi, self.vpl, self.forex, self.bas_dk = bilgi, vpl, forex, bas_dk
        self.adim = bilgi.volume_step if bilgi.volume_step > 0 else 0.01
        self.vmax = bilgi.volume_max if bilgi.volume_max > 0 else 1e9
        self.son = int(T[-1])
        self.gunler = np.unique(T // 1440)
        g0 = np.searchsorted(T, self.gunler * 1440)
        g1 = np.searchsorted(T, self.gunler * 1440 + 1440)
        dC = self.C[g1 - 1]
        dH = np.maximum.reduceat(self.H, g0)
        dL = np.minimum.reduceat(self.L, g0)
        self.yon_ek = yon_ekin(dH, dL, dC)
        self.yon_ic = yon_ict(dH, dL, dC)
        self.Y = {}
        SPx = self.SP
        n1 = len(T)
        for y in (-1, 1):
            if y < 0:
                Om, Hm, Lm, Cm = self.O, self.H, self.L, self.C
                F, X, Yt, Cx = self.H, self.H + SPx, self.L + SPx, self.C + SPx
                Em = self.O
            else:
                Om, Hm, Lm, Cm = -self.O, -self.L, -self.H, -self.C
                F, X, Yt, Cx = -(self.L + SPx), -self.L, -self.H, -self.C
                Em = -(self.O + SPx)
            nLm = -Lm
            B = {K: mumlar(T, Om, Hm, Lm, Cm, K) for K in (3, 5, 15, 60, 240, 1440)}
            sw = {}
            for K in (5, 15):
                bt, bo, bh, bl, bc = B[K]
                n = len(bt)
                swl = np.zeros(n, dtype=bool)
                if n > 2:
                    swl[1:-1] = (bl[1:-1] < bl[:-2]) & (bl[1:-1] < bl[2:])
                idx = np.where(swl, np.arange(n), -1)
                sw[K] = np.r_[-1, np.maximum.accumulate(idx)[:-1]] if n else idx
            # --- seviye listeleri: (gecerlilik basi, alinma zamani, fiyat, ad, tolerans orani)
            sev = []
            for K in (60, 240):
                bt, bo, bh, bl, bc = B[K]
                if len(bt) < 3:
                    continue
                at = atr(bh, bl, bc)
                q = np.flatnonzero((bh[1:-1] > bh[:-2]) & (bh[1:-1] > bh[2:])) + 1
                tep = []
                for i in q:
                    t0 = int(bt[i + 1] + K)
                    j0 = int(np.searchsorted(T, t0))
                    tk = ilk(Hm, j0, bh[i], False)
                    tep.append((t0, int(T[tk]) if tk < n1 else 10 ** 12, bh[i], at[i], int(bt[i])))
                for b in range(1, len(tep)):
                    tb, kb, pb, ab, ob = tep[b]
                    for a in range(max(0, b - 30), b):
                        ta, ka, pa, aa, oa = tep[a]
                        if ka <= ob:                       # a, b olusmadan alinmis: aralarinda gecilmis
                            continue
                        oran = abs(pa - pb) / ab if ab > 0 else 9.0
                        if oran > max(ESIT_TOL):
                            continue
                        lv = max(pa, pb)
                        j0 = int(np.searchsorted(T, tb))
                        tk = ilk(Hm, j0, lv, False)
                        sev.append((tb, int(T[tk]) if tk < n1 else 10 ** 12, lv, "ESIT_TEPE", oran))
            for K, ad in ((60, "FVG_1S"), (240, "FVG_4S"), (1440, "FVG_GUNLUK")):
                bt, bo, bh, bl, bc = B[K]
                for c in np.flatnonzero(bl[:-2] > bh[2:]) + 2:
                    t0 = int(bt[c] + K)
                    j0 = int(np.searchsorted(T, t0))
                    tk = ilk(Hm, j0, bh[c], True)
                    sev.append((t0, int(T[tk]) if tk < n1 else 10 ** 12, bh[c], ad, 0.0))
            # --- karsi likidite (TP): 1 saatlik swing dipler, alinana kadar
            kar = []
            bt, bo, bh, bl, bc = B[60]
            for i in np.flatnonzero((bl[1:-1] < bl[:-2]) & (bl[1:-1] < bl[2:])) + 1:
                t0 = int(bt[i + 1] + 60)
                j0 = int(np.searchsorted(T, t0))
                tk = ilk(nLm, j0, -bl[i], False)
                kar.append((t0, int(T[tk]) if tk < n1 else 10 ** 12, bl[i]))
            b5 = B[5]
            bq = np.flatnonzero(b5[2][:-2] < b5[3][2:])
            self.Y[y] = dict(Om=Om, Hm=Hm, Lm=Lm, nLm=nLm, Cm=Cm, F=F, X=X, Yt=Yt, Cx=Cx, Em=Em, B=B, sw=sw,
                             sev=sev, kar=kar, bul5=bq,
                             dH=np.maximum.reduceat(Hm, g0), dL=np.minimum.reduceat(Lm, g0))

    def ix(self, t):
        return int(np.searchsorted(self.T, t))

    def mx(self, arr, a, b):
        i, j = self.ix(a), self.ix(b)
        return arr[i:j].max() if j > i else -np.inf

    def mn(self, arr, a, b):
        i, j = self.ix(a), self.ix(b)
        return arr[i:j].min() if j > i else np.inf

    # ------------------------------------------------- bir killzone icin seviyeler ve karsi likidite
    def seviyeler(self, y, k, ks, ke, kzad):
        """donus: [(supurme_zamani, ad, tolerans)], [karsi fiyatlar]"""
        g = self.Y[y]
        Hm, Lm = g["Hm"], g["Lm"]
        D = int(self.gunler[k] * 1440)
        Dp = int(self.gunler[k - 1] * 1440)
        i0, i1 = self.ix(ks), self.ix(ke)
        hz = Hm[i0:i1]
        vur, karsi = [], []

        def ekle(fiyat, bitis, ad):
            if not np.isfinite(fiyat) or bitis > ks or self.mx(Hm, bitis, ks) > fiyat:
                return
            z = np.flatnonzero(hz > fiyat)
            if z.size:
                vur.append((int(self.T[i0 + int(z[0])]), ad, 0.0))

        def kekle(fiyat, bitis):
            if np.isfinite(fiyat) and bitis <= ks and self.mn(Lm, bitis, ks) >= fiyat:
                karsi.append(fiyat)

        ekle(g["dH"][k - 1], D, "PDH")
        kekle(g["dL"][k - 1], D)
        hafta = (self.gunler + 3) // 7
        w = hafta[k]
        on = np.flatnonzero(hafta == w - 1)
        if on.size:
            hb = int((w * 7 - 3) * 1440)
            ekle(g["dH"][on].max(), hb, "PWH")
            kekle(g["dL"][on].min(), hb)
        ekle(self.mx(Hm, D + 180, D + 420), D + 420, "ASYA")
        kekle(self.mn(Lm, D + 180, D + 420), D + 420)
        if kzad == "NY":
            ekle(self.mx(Hm, D + 540, D + 720), D + 720, "LONDRA")
            kekle(self.mn(Lm, D + 540, D + 720), D + 720)
        ekle(self.mx(Hm, Dp + 1230, Dp + 1380), Dp + 1380, "NY_PM")
        kekle(self.mn(Lm, Dp + 1230, Dp + 1380), Dp + 1380)
        for t0, tk, fiyat, ad, tol in g["sev"]:
            if t0 <= ks < tk and tk < ke:
                vur.append((tk, ad, tol))
        for t0, tk, fiyat in g["kar"]:
            if t0 <= ks < tk:
                karsi.append(fiyat)
        return vur, karsi

    # ------------------------------------------------- kurulumlar
    def kurulumlar(self, sadece=None):
        """anahtar: (s1, s6, s7, s13) -> kurulum listesi"""
        out = {a: [] for a in itertools.product(range(2), range(2), range(2), range(3))}
        if self.forex:
            pen = [(SUNUCU_NY * 60 + 120, SUNUCU_NY * 60 + 300, "LONDRA"), (SUNUCU_NY * 60 + 420, SUNUCU_NY * 60 + 600, "NY")]
        else:
            pen = [(SUNUCU_NY * 60 + 510, SUNUCU_NY * 60 + 660, "NY")]
        for k in range(8, len(self.gunler)):
            D = int(self.gunler[k] * 1440)
            if D + 1440 < self.bas_dk or (NY_KAPAT and D + KAPANIS > self.son):
                continue
            for a_, b_, kzad in pen:
                ks, ke = D + a_, D + b_
                if self.ix(ks) >= len(self.T) or self.T[self.ix(ks)] >= ke:
                    continue
                SAY["pencere"] += 1
                for y in (-1, 1):
                    vur, karsi = self.seviyeler(y, k, ks, ke, kzad)
                    if not vur:
                        continue
                    for s13 in range(3):
                        for s6, kume in ((0, EKIN_SEV), (1, ICT_SEV)):
                            gec = [(t, ad) for t, ad, tol in vur if ad in kume and (ad != "ESIT_TEPE" or tol <= ESIT_TOL[s13])]
                            if not gec:
                                continue
                            for s7 in range(2):
                                for s1 in range(2):
                                    key = (s1, s6, s7, s13)
                                    if sadece is not None and key not in sadece:
                                        continue
                                    bas_t = ks
                                    while True:
                                        kalan = [(t, ad) for t, ad in gec if t >= bas_t]
                                        if not kalan:
                                            break
                                        ts = min(t for t, _ in kalan)
                                        adlar = "+".join(sorted(set(ad for t, ad in kalan if t == ts)))
                                        SAY["supurme"] += 1
                                        x = self.kurulum(y, ts, ke, s1, s7)
                                        if x is None:
                                            break
                                        bas_t = max(x["Td"], ts + 1)
                                        if not x["ok"]:
                                            continue
                                        x.update(y=y, k=k, D=D, kz=kzad, ks=ks, ke=ke, ts=ts, sev=adlar, karsi=karsi,
                                                 yon_ek=int(self.yon_ek[k]), yon_ic=int(self.yon_ic[k]))
                                        out[key].append(x)
                                        SAY["kurulum"] += 1
        for v in out.values():
            v.sort(key=lambda z: (z["Td"], z["y"]))
        return out

    def kurulum(self, y, ts, ke, s1, s7):
        g = self.Y[y]
        Km = 5 if s7 == 0 else 15
        bt, bo, bh, bl, bc = g["B"][Km]
        sonsw = g["sw"][Km]
        n = len(bt)
        i = int(np.searchsorted(bt, ts, side="right")) - 1
        if i < 3:
            return None
        tepe, ref, t_mss = -np.inf, None, None
        for j in range(i, n):
            if bt[j] + Km > ke:
                break
            if bh[j] > tepe:
                tepe = bh[j]
                q = sonsw[j]
                ref = bl[q] if q >= 0 else None
                continue
            if ref is not None and bc[j] < ref:
                t_mss = int(bt[j] + Km)
                break
        # IFVG: likiditeyi alirken (supurmeye giden bacakta, son 5 dk swing dipten tepeye) yukari FVG
        t5, o5, h5, l5, c5 = g["B"][5]
        bq = g["bul5"]
        j0 = int(np.searchsorted(t5, ts, side="right")) - 1
        bacak = max(int(g["sw"][5][j0]), 0) if j0 >= 0 else 0
        aday = bq[(bq >= bacak) & (bq + 2 <= len(t5) - 1)]
        tp5, p5, t_ifvg, inv = -np.inf, -1, None, []
        for j in range(max(j0, 0), len(t5)):
            if t5[j] + 5 > ke:
                break
            if h5[j] > tp5:
                tp5, p5 = h5[j], j
                continue
            for a in aday:
                if a + 2 <= p5 and c5[j] < h5[a] and all(a != z[0] for z in inv):
                    inv.append((a, j))
                    if t_ifvg is None:
                        t_ifvg = int(t5[j] + 5)
        if s1 == 0:
            Td = t_mss
        else:
            Td = min([v for v in (t_mss, t_ifvg) if v is not None], default=None)
        if Td is None:
            return None
        SAY["kirilim"] += 1
        a_, b_ = self.ix(ts), self.ix(Td)
        if b_ <= a_:
            return dict(Td=Td, ok=False)
        Hm = g["Hm"]
        seg = Hm[a_:b_]
        tepe = seg.max()
        t_tepe = int(self.T[a_ + int(np.argmax(seg))])
        fiyat = g["Cm"][b_ - 1]
        k5 = int(np.searchsorted(t5, t_tepe, side="right")) - 1
        tepe_govde = max(o5[k5], c5[k5])
        zon = []
        for K in ((5, 3) if s7 == 0 else (5,)):
            ft, fo, fh, fl, fc = g["B"][K]
            a0 = int(np.searchsorted(ft, t_tepe, side="right")) - 1
            a1 = int(np.searchsorted(ft, Td))
            for a in range(max(a0, 0), a1 - 2):
                c = a + 2
                if ft[c] + K > Td or not (fl[a] > fh[c]):
                    continue
                alt, ust = fh[c], fl[a]
                if alt <= fiyat or self.mx(Hm, ft[c] + K, Td) >= alt:
                    continue
                zon.append((alt, ust, max(fo[a], fc[a]), "FVG"))
            if zon:
                break
        for a, j in inv:
            if t5[j] + 5 > Td or j <= k5 or a + 2 > k5:
                continue
            alt, ust = h5[a], l5[a + 2]
            if alt <= fiyat or self.mx(Hm, t5[j] + 5, Td) >= alt:
                continue
            zon.append((alt, ust, max(o5[j], c5[j]), "IFVG"))
        if not zon:
            return dict(Td=Td, ok=False)
        zon.sort()
        alt, ust, govde, tur = zon[0]
        mum_stop = max([govde] + [z[2] for z in zon[1:]])
        sharp = bool(np.any((bq >= bacak) & (bq + 2 <= k5)))
        return dict(Td=Td, ok=True, tepe=tepe, tepe_govde=tepe_govde, alt=alt, ust=ust, mum_stop=mum_stop, tur=tur,
                    sharp=sharp)


    # ------------------------------------------------- 54 sonuc (S3 x S4 x S5 x S11)
    def sonuclar(self, x):
        g = self.Y[x["y"]]
        F, X, Yt, Cx, Em = g["F"], g["X"], g["Yt"], g["Cx"], g["Em"]
        T = self.T
        z1 = self.ix(x["D"] + KAPANIS) if NY_KAPAT else len(self.T)
        a0 = self.ix(x["Td"])
        n = 54
        r_fill = np.full(n, -1, np.int64)
        r_bit = np.full(n, -1, np.int64)
        r_R = np.zeros(n)
        r_d = np.zeros(n)
        r_k = np.full(n, 9, np.int8)       # 9 yok, 8 iptal, 1 TP, -1 STOP, 0 SURE
        r_E = np.zeros(n)
        r_S = np.zeros(n)
        r_TP = np.zeros(n)
        r_lot = np.zeros(n)
        if a0 >= z1:
            return r_fill, r_bit, r_R, r_d, r_k, r_E, r_S, r_TP, r_lot
        for gi in range(3):
            if gi == 0:
                E = 0.5 * (x["alt"] + x["ust"])
            elif gi == 1:
                E = x["alt"]
            else:
                E = Em[a0]
            for si in range(3):
                S = (x["tepe_govde"], x["mum_stop"], x["tepe"])[si]
                r = S - E
                if not (r > 0):
                    continue
                sp = self.SP[a0]
                lot = np.floor(RISK / (r * self.vpl) / self.adim + 1e-9) * self.adim
                if lot < self.bilgi.volume_min:
                    lot = self.bilgi.volume_min
                lot = min(lot, self.vmax)
                zarar = lot * r * self.vpl
                if zarar > EN_FAZLA + 1e-9 or sp * lot * self.vpl > MAKAS_SINIR + 1e-9:
                    continue
                for ti in range(3):
                    if ti < 2:
                        TP = E - (2.0, 3.0)[ti] * r
                    else:
                        ad = [v for v in x["karsi"] if v <= E - 2.0 * r]
                        if not ad:
                            continue
                        TP = max(ad)
                    for ei in range(2):
                        kk = ((gi * 3 + si) * 3 + ti) * 2 + ei
                        r_E[kk], r_S[kk], r_TP[kk], r_lot[kk] = E, S, TP, lot
                        if gi == 2:
                            f = a0
                        else:
                            c1 = min(self.ix(x["ke"] if ei == 0 else x["Td"] + 120), z1)
                            if c1 <= a0:
                                continue
                            fz = np.flatnonzero(F[a0:c1] >= E)
                            if not fz.size:
                                r_k[kk], r_bit[kk] = 8, int(T[c1 - 1]) + 1
                                continue
                            f = a0 + int(fz[0])
                            if Yt[a0:f + 1].min() <= TP:
                                r_k[kk], r_bit[kk] = 8, int(T[f])
                                continue
                        st = np.flatnonzero(X[f:z1] >= S)
                        tb = Yt[f:z1] <= TP
                        if gi != 2:
                            tb[0] = False
                        hz = np.flatnonzero(tb)
                        s0 = int(st[0]) if st.size else None
                        h0 = int(hz[0]) if hz.size else None
                        if s0 is not None and (h0 is None or s0 <= h0):
                            R, kod, e = -1.0, -1, f + s0
                        elif h0 is not None:
                            R, kod, e = (E - TP) / r, 1, f + h0
                        else:
                            e = z1 - 1
                            R, kod = (E - Cx[e]) / r, 0
                        r_fill[kk], r_bit[kk], r_R[kk], r_d[kk], r_k[kk] = int(T[f]), int(T[e]) + 1, R, R * zarar, kod
        return r_fill, r_bit, r_R, r_d, r_k, r_E, r_S, r_TP, r_lot




MANTIK = [
    ("EURUSD", "MSS=IFVG_YETER YON=ICT GIRIS=ORTA STOP=FVG_MUM TP=2R SEVIYE=EKIN ZAMAN=EKIN_5_3 DISIPLIN=EKIN EMIR=2_SAAT SHARP=SART ESIT_TOL=0.2ATR"),
    ("GBPUSD", "MSS=SART YON=YOK GIRIS=ORTA STOP=SUPURULEN_UC TP=2R SEVIYE=EKIN ZAMAN=ICT_15_5 DISIPLIN=EKIN EMIR=SEANS_SONU SHARP=YOK ESIT_TOL=0.05ATR"),
    ("USDCHF", "MSS=IFVG_YETER YON=ICT GIRIS=KAPANIS STOP=SUPURULEN_UC TP=2R SEVIYE=ICT ZAMAN=EKIN_5_3 DISIPLIN=EKIN EMIR=SEANS_SONU SHARP=YOK ESIT_TOL=0.05ATR"),
    ("USDCAD", "MSS=SART YON=EKIN GIRIS=ORTA STOP=FVG_MUM TP=LIKIDITE SEVIYE=ICT ZAMAN=ICT_15_5 DISIPLIN=YOK EMIR=2_SAAT SHARP=SART ESIT_TOL=0.2ATR"),
    ("AUDNZD", "MSS=IFVG_YETER YON=EKIN GIRIS=ORTA STOP=SWING_GOVDE TP=3R SEVIYE=ICT ZAMAN=ICT_15_5 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=SART ESIT_TOL=0.05ATR"),
    ("AUDCAD", "MSS=IFVG_YETER YON=ICT GIRIS=KENAR STOP=FVG_MUM TP=3R SEVIYE=EKIN ZAMAN=EKIN_5_3 DISIPLIN=EKIN EMIR=SEANS_SONU SHARP=YOK ESIT_TOL=0.05ATR"),
    ("AUDCHF", "MSS=SART YON=EKIN GIRIS=KAPANIS STOP=SUPURULEN_UC TP=2R SEVIYE=EKIN ZAMAN=EKIN_5_3 DISIPLIN=EKIN EMIR=SEANS_SONU SHARP=YOK ESIT_TOL=0.1ATR"),
    ("AUDJPY", "MSS=SART YON=EKIN GIRIS=KAPANIS STOP=SWING_GOVDE TP=LIKIDITE SEVIYE=EKIN ZAMAN=EKIN_5_3 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=YOK ESIT_TOL=0.05ATR"),
    ("CHFJPY", "MSS=IFVG_YETER YON=ICT GIRIS=KENAR STOP=FVG_MUM TP=2R SEVIYE=ICT ZAMAN=ICT_15_5 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=YOK ESIT_TOL=0.05ATR"),
    ("EURGBP", "MSS=SART YON=ICT GIRIS=KENAR STOP=SUPURULEN_UC TP=LIKIDITE SEVIYE=ICT ZAMAN=EKIN_5_3 DISIPLIN=EKIN EMIR=2_SAAT SHARP=YOK ESIT_TOL=0.05ATR"),
    ("EURAUD", "MSS=SART YON=YOK GIRIS=KENAR STOP=SUPURULEN_UC TP=LIKIDITE SEVIYE=ICT ZAMAN=ICT_15_5 DISIPLIN=YOK EMIR=2_SAAT SHARP=YOK ESIT_TOL=0.2ATR"),
    ("EURCHF", "MSS=SART YON=YOK GIRIS=KENAR STOP=SUPURULEN_UC TP=3R SEVIYE=EKIN ZAMAN=ICT_15_5 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=SART ESIT_TOL=0.05ATR"),
    ("EURJPY", "MSS=SART YON=ICT GIRIS=KENAR STOP=FVG_MUM TP=3R SEVIYE=EKIN ZAMAN=ICT_15_5 DISIPLIN=YOK EMIR=2_SAAT SHARP=YOK ESIT_TOL=0.05ATR"),
    ("EURNZD", "MSS=SART YON=YOK GIRIS=KAPANIS STOP=FVG_MUM TP=2R SEVIYE=ICT ZAMAN=ICT_15_5 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=YOK ESIT_TOL=0.1ATR"),
    ("EURCAD", "MSS=SART YON=EKIN GIRIS=KENAR STOP=FVG_MUM TP=3R SEVIYE=ICT ZAMAN=EKIN_5_3 DISIPLIN=EKIN EMIR=2_SAAT SHARP=SART ESIT_TOL=0.2ATR"),
    ("GBPCHF", "MSS=IFVG_YETER YON=ICT GIRIS=ORTA STOP=SWING_GOVDE TP=3R SEVIYE=EKIN ZAMAN=EKIN_5_3 DISIPLIN=EKIN EMIR=2_SAAT SHARP=YOK ESIT_TOL=0.05ATR"),
    ("CADJPY", "MSS=SART YON=EKIN GIRIS=KAPANIS STOP=FVG_MUM TP=2R SEVIYE=ICT ZAMAN=EKIN_5_3 DISIPLIN=EKIN EMIR=SEANS_SONU SHARP=SART ESIT_TOL=0.05ATR"),
    ("GBPAUD", "MSS=SART YON=YOK GIRIS=KAPANIS STOP=FVG_MUM TP=3R SEVIYE=EKIN ZAMAN=ICT_15_5 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=YOK ESIT_TOL=0.05ATR"),
    ("GBPCAD", "MSS=SART YON=EKIN GIRIS=KAPANIS STOP=FVG_MUM TP=2R SEVIYE=ICT ZAMAN=ICT_15_5 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=SART ESIT_TOL=0.2ATR"),
    ("GBPNZD", "MSS=SART YON=EKIN GIRIS=ORTA STOP=FVG_MUM TP=LIKIDITE SEVIYE=EKIN ZAMAN=EKIN_5_3 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=SART ESIT_TOL=0.05ATR"),
    ("NZDCAD", "MSS=SART YON=EKIN GIRIS=KENAR STOP=FVG_MUM TP=2R SEVIYE=ICT ZAMAN=ICT_15_5 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=SART ESIT_TOL=0.2ATR"),
    ("NZDCHF", "MSS=SART YON=EKIN GIRIS=KENAR STOP=SWING_GOVDE TP=2R SEVIYE=ICT ZAMAN=ICT_15_5 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=YOK ESIT_TOL=0.05ATR"),
    ("EURNOK", "MSS=IFVG_YETER YON=EKIN GIRIS=KENAR STOP=SWING_GOVDE TP=LIKIDITE SEVIYE=ICT ZAMAN=ICT_15_5 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=SART ESIT_TOL=0.05ATR"),
    ("USDCZK", "MSS=SART YON=EKIN GIRIS=KENAR STOP=SUPURULEN_UC TP=3R SEVIYE=EKIN ZAMAN=EKIN_5_3 DISIPLIN=YOK EMIR=2_SAAT SHARP=YOK ESIT_TOL=0.05ATR"),
    ("USDHKD", "MSS=IFVG_YETER YON=YOK GIRIS=ORTA STOP=FVG_MUM TP=2R SEVIYE=EKIN ZAMAN=ICT_15_5 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=YOK ESIT_TOL=0.05ATR"),
    ("USDMXN", "MSS=SART YON=EKIN GIRIS=KAPANIS STOP=SWING_GOVDE TP=LIKIDITE SEVIYE=EKIN ZAMAN=ICT_15_5 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=YOK ESIT_TOL=0.1ATR"),
    ("USDNOK", "MSS=IFVG_YETER YON=YOK GIRIS=KENAR STOP=FVG_MUM TP=LIKIDITE SEVIYE=EKIN ZAMAN=EKIN_5_3 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=SART ESIT_TOL=0.05ATR"),
    ("USDPLN", "MSS=IFVG_YETER YON=ICT GIRIS=KAPANIS STOP=FVG_MUM TP=2R SEVIYE=ICT ZAMAN=ICT_15_5 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=SART ESIT_TOL=0.05ATR"),
    ("USDZAR", "MSS=IFVG_YETER YON=YOK GIRIS=ORTA STOP=FVG_MUM TP=2R SEVIYE=EKIN ZAMAN=EKIN_5_3 DISIPLIN=YOK EMIR=2_SAAT SHARP=YOK ESIT_TOL=0.05ATR"),
    ("USDSEK", "MSS=IFVG_YETER YON=YOK GIRIS=KENAR STOP=SWING_GOVDE TP=2R SEVIYE=EKIN ZAMAN=ICT_15_5 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=YOK ESIT_TOL=0.2ATR"),
    ("USDILS", "MSS=IFVG_YETER YON=ICT GIRIS=KAPANIS STOP=FVG_MUM TP=3R SEVIYE=EKIN ZAMAN=ICT_15_5 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=YOK ESIT_TOL=0.05ATR"),
    ("USDSGD", "MSS=IFVG_YETER YON=YOK GIRIS=ORTA STOP=FVG_MUM TP=LIKIDITE SEVIYE=EKIN ZAMAN=ICT_15_5 DISIPLIN=YOK EMIR=2_SAAT SHARP=YOK ESIT_TOL=0.1ATR"),
    ("USDCNH", "MSS=SART YON=YOK GIRIS=ORTA STOP=FVG_MUM TP=2R SEVIYE=EKIN ZAMAN=ICT_15_5 DISIPLIN=YOK EMIR=2_SAAT SHARP=SART ESIT_TOL=0.05ATR"),
    ("GER40.cash", "MSS=IFVG_YETER YON=ICT GIRIS=KAPANIS STOP=FVG_MUM TP=LIKIDITE SEVIYE=EKIN ZAMAN=ICT_15_5 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=YOK ESIT_TOL=0.05ATR"),
    ("UK100.cash", "MSS=SART YON=YOK GIRIS=KAPANIS STOP=FVG_MUM TP=LIKIDITE SEVIYE=ICT ZAMAN=EKIN_5_3 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=YOK ESIT_TOL=0.2ATR"),
    ("US100.cash", "MSS=SART YON=YOK GIRIS=KAPANIS STOP=FVG_MUM TP=3R SEVIYE=EKIN ZAMAN=ICT_15_5 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=YOK ESIT_TOL=0.05ATR"),
    ("US30.cash", "MSS=IFVG_YETER YON=ICT GIRIS=ORTA STOP=SUPURULEN_UC TP=LIKIDITE SEVIYE=ICT ZAMAN=EKIN_5_3 DISIPLIN=YOK EMIR=2_SAAT SHARP=SART ESIT_TOL=0.05ATR"),
    ("US500.cash", "MSS=SART YON=EKIN GIRIS=KENAR STOP=SWING_GOVDE TP=LIKIDITE SEVIYE=ICT ZAMAN=EKIN_5_3 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=YOK ESIT_TOL=0.05ATR"),
    ("AUS200.cash", "MSS=SART YON=YOK GIRIS=ORTA STOP=FVG_MUM TP=3R SEVIYE=EKIN ZAMAN=EKIN_5_3 DISIPLIN=YOK EMIR=2_SAAT SHARP=YOK ESIT_TOL=0.05ATR"),
    ("EU50.cash", "MSS=SART YON=EKIN GIRIS=KENAR STOP=FVG_MUM TP=LIKIDITE SEVIYE=ICT ZAMAN=EKIN_5_3 DISIPLIN=YOK EMIR=2_SAAT SHARP=YOK ESIT_TOL=0.2ATR"),
    ("FRA40.cash", "MSS=IFVG_YETER YON=YOK GIRIS=ORTA STOP=SUPURULEN_UC TP=2R SEVIYE=ICT ZAMAN=EKIN_5_3 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=YOK ESIT_TOL=0.05ATR"),
    ("HK50.cash", "MSS=IFVG_YETER YON=YOK GIRIS=KAPANIS STOP=SUPURULEN_UC TP=LIKIDITE SEVIYE=EKIN ZAMAN=EKIN_5_3 DISIPLIN=EKIN EMIR=SEANS_SONU SHARP=SART ESIT_TOL=0.05ATR"),
    ("JP225.cash", "MSS=IFVG_YETER YON=EKIN GIRIS=KAPANIS STOP=SWING_GOVDE TP=3R SEVIYE=EKIN ZAMAN=EKIN_5_3 DISIPLIN=EKIN EMIR=SEANS_SONU SHARP=SART ESIT_TOL=0.1ATR"),
    ("N25.cash", "MSS=IFVG_YETER YON=YOK GIRIS=KENAR STOP=FVG_MUM TP=3R SEVIYE=EKIN ZAMAN=EKIN_5_3 DISIPLIN=YOK EMIR=2_SAAT SHARP=YOK ESIT_TOL=0.2ATR"),
    ("SPN35.cash", "MSS=IFVG_YETER YON=ICT GIRIS=KAPANIS STOP=SWING_GOVDE TP=3R SEVIYE=ICT ZAMAN=EKIN_5_3 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=YOK ESIT_TOL=0.05ATR"),
    ("US2000.cash", "MSS=IFVG_YETER YON=YOK GIRIS=KAPANIS STOP=FVG_MUM TP=2R SEVIYE=ICT ZAMAN=ICT_15_5 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=SART ESIT_TOL=0.2ATR"),
    ("UKOIL.cash", "MSS=IFVG_YETER YON=YOK GIRIS=ORTA STOP=SWING_GOVDE TP=3R SEVIYE=EKIN ZAMAN=ICT_15_5 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=YOK ESIT_TOL=0.05ATR"),
    ("USOIL.cash", "MSS=IFVG_YETER YON=EKIN GIRIS=KENAR STOP=SUPURULEN_UC TP=LIKIDITE SEVIYE=ICT ZAMAN=ICT_15_5 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=SART ESIT_TOL=0.1ATR"),
    ("XCUUSD", "MSS=IFVG_YETER YON=ICT GIRIS=KENAR STOP=SWING_GOVDE TP=LIKIDITE SEVIYE=EKIN ZAMAN=EKIN_5_3 DISIPLIN=YOK EMIR=2_SAAT SHARP=YOK ESIT_TOL=0.05ATR"),
    ("XAGUSD", "MSS=IFVG_YETER YON=ICT GIRIS=KENAR STOP=SWING_GOVDE TP=3R SEVIYE=EKIN ZAMAN=ICT_15_5 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=YOK ESIT_TOL=0.05ATR"),
    ("XAGAUD", "MSS=IFVG_YETER YON=ICT GIRIS=KAPANIS STOP=SWING_GOVDE TP=LIKIDITE SEVIYE=EKIN ZAMAN=ICT_15_5 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=YOK ESIT_TOL=0.05ATR"),
    ("XAGEUR", "MSS=SART YON=YOK GIRIS=KENAR STOP=FVG_MUM TP=2R SEVIYE=EKIN ZAMAN=EKIN_5_3 DISIPLIN=YOK EMIR=2_SAAT SHARP=SART ESIT_TOL=0.05ATR"),
    ("XAUUSD", "MSS=IFVG_YETER YON=ICT GIRIS=KENAR STOP=FVG_MUM TP=3R SEVIYE=ICT ZAMAN=EKIN_5_3 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=YOK ESIT_TOL=0.05ATR"),
    ("XAUAUD", "MSS=SART YON=YOK GIRIS=ORTA STOP=FVG_MUM TP=LIKIDITE SEVIYE=EKIN ZAMAN=EKIN_5_3 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=SART ESIT_TOL=0.05ATR"),
    ("XAUEUR", "MSS=SART YON=YOK GIRIS=KAPANIS STOP=FVG_MUM TP=2R SEVIYE=EKIN ZAMAN=EKIN_5_3 DISIPLIN=EKIN EMIR=SEANS_SONU SHARP=SART ESIT_TOL=0.05ATR"),
    ("XPTUSD", "MSS=SART YON=YOK GIRIS=KAPANIS STOP=SWING_GOVDE TP=2R SEVIYE=ICT ZAMAN=ICT_15_5 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=SART ESIT_TOL=0.05ATR"),
    ("AAPL", "MSS=IFVG_YETER YON=ICT GIRIS=KAPANIS STOP=SUPURULEN_UC TP=2R SEVIYE=EKIN ZAMAN=EKIN_5_3 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=SART ESIT_TOL=0.05ATR"),
    ("AMZN", "MSS=SART YON=YOK GIRIS=KENAR STOP=SWING_GOVDE TP=2R SEVIYE=EKIN ZAMAN=EKIN_5_3 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=YOK ESIT_TOL=0.05ATR"),
    ("BABA", "MSS=IFVG_YETER YON=YOK GIRIS=ORTA STOP=FVG_MUM TP=2R SEVIYE=ICT ZAMAN=ICT_15_5 DISIPLIN=YOK EMIR=2_SAAT SHARP=YOK ESIT_TOL=0.05ATR"),
    ("BAC", "MSS=IFVG_YETER YON=ICT GIRIS=KAPANIS STOP=FVG_MUM TP=LIKIDITE SEVIYE=ICT ZAMAN=EKIN_5_3 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=YOK ESIT_TOL=0.05ATR"),
    ("MSFT", "MSS=IFVG_YETER YON=ICT GIRIS=KAPANIS STOP=SWING_GOVDE TP=2R SEVIYE=EKIN ZAMAN=ICT_15_5 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=YOK ESIT_TOL=0.05ATR"),
    ("RACE", "MSS=IFVG_YETER YON=ICT GIRIS=KAPANIS STOP=SWING_GOVDE TP=2R SEVIYE=EKIN ZAMAN=ICT_15_5 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=YOK ESIT_TOL=0.05ATR"),
    ("GOOG", "MSS=IFVG_YETER YON=EKIN GIRIS=ORTA STOP=SWING_GOVDE TP=LIKIDITE SEVIYE=EKIN ZAMAN=ICT_15_5 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=SART ESIT_TOL=0.05ATR"),
    ("V", "MSS=SART YON=YOK GIRIS=KENAR STOP=SUPURULEN_UC TP=LIKIDITE SEVIYE=EKIN ZAMAN=EKIN_5_3 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=SART ESIT_TOL=0.05ATR"),
    ("NFLX", "MSS=IFVG_YETER YON=EKIN GIRIS=KENAR STOP=SUPURULEN_UC TP=3R SEVIYE=EKIN ZAMAN=EKIN_5_3 DISIPLIN=YOK EMIR=2_SAAT SHARP=YOK ESIT_TOL=0.05ATR"),
    ("NVDA", "MSS=IFVG_YETER YON=EKIN GIRIS=ORTA STOP=SUPURULEN_UC TP=LIKIDITE SEVIYE=EKIN ZAMAN=ICT_15_5 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=YOK ESIT_TOL=0.05ATR"),
    ("PFE", "MSS=IFVG_YETER YON=EKIN GIRIS=KAPANIS STOP=SWING_GOVDE TP=2R SEVIYE=EKIN ZAMAN=EKIN_5_3 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=YOK ESIT_TOL=0.05ATR"),
    ("TSLA", "MSS=SART YON=YOK GIRIS=ORTA STOP=FVG_MUM TP=LIKIDITE SEVIYE=EKIN ZAMAN=ICT_15_5 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=YOK ESIT_TOL=0.05ATR"),
    ("WMT", "MSS=IFVG_YETER YON=ICT GIRIS=KENAR STOP=SUPURULEN_UC TP=2R SEVIYE=ICT ZAMAN=EKIN_5_3 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=YOK ESIT_TOL=0.05ATR"),
    ("ZM", "MSS=SART YON=YOK GIRIS=ORTA STOP=FVG_MUM TP=2R SEVIYE=EKIN ZAMAN=ICT_15_5 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=YOK ESIT_TOL=0.05ATR"),
    ("META", "MSS=SART YON=ICT GIRIS=KAPANIS STOP=SWING_GOVDE TP=2R SEVIYE=EKIN ZAMAN=ICT_15_5 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=YOK ESIT_TOL=0.05ATR"),
    ("GE", "MSS=IFVG_YETER YON=EKIN GIRIS=KENAR STOP=SUPURULEN_UC TP=LIKIDITE SEVIYE=ICT ZAMAN=EKIN_5_3 DISIPLIN=YOK EMIR=2_SAAT SHARP=YOK ESIT_TOL=0.05ATR"),
    ("BA", "MSS=IFVG_YETER YON=ICT GIRIS=ORTA STOP=SUPURULEN_UC TP=2R SEVIYE=ICT ZAMAN=ICT_15_5 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=YOK ESIT_TOL=0.05ATR"),
    ("RTX", "MSS=SART YON=YOK GIRIS=ORTA STOP=SUPURULEN_UC TP=2R SEVIYE=EKIN ZAMAN=EKIN_5_3 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=SART ESIT_TOL=0.05ATR"),
    ("LMT", "MSS=IFVG_YETER YON=YOK GIRIS=ORTA STOP=SUPURULEN_UC TP=3R SEVIYE=EKIN ZAMAN=EKIN_5_3 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=YOK ESIT_TOL=0.05ATR"),
    ("AMD", "MSS=IFVG_YETER YON=EKIN GIRIS=KAPANIS STOP=SWING_GOVDE TP=3R SEVIYE=ICT ZAMAN=ICT_15_5 DISIPLIN=EKIN EMIR=SEANS_SONU SHARP=SART ESIT_TOL=0.05ATR"),
    ("INTC", "MSS=IFVG_YETER YON=ICT GIRIS=KAPANIS STOP=FVG_MUM TP=3R SEVIYE=ICT ZAMAN=ICT_15_5 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=SART ESIT_TOL=0.05ATR"),
    ("QCOM", "MSS=IFVG_YETER YON=ICT GIRIS=KENAR STOP=SUPURULEN_UC TP=3R SEVIYE=ICT ZAMAN=ICT_15_5 DISIPLIN=YOK EMIR=2_SAAT SHARP=YOK ESIT_TOL=0.05ATR"),
    ("AVGO", "MSS=IFVG_YETER YON=ICT GIRIS=ORTA STOP=SWING_GOVDE TP=2R SEVIYE=EKIN ZAMAN=EKIN_5_3 DISIPLIN=YOK EMIR=2_SAAT SHARP=SART ESIT_TOL=0.05ATR"),
    ("CSCO", "MSS=IFVG_YETER YON=ICT GIRIS=KENAR STOP=SWING_GOVDE TP=LIKIDITE SEVIYE=ICT ZAMAN=ICT_15_5 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=YOK ESIT_TOL=0.05ATR"),
    ("JNJ", "MSS=IFVG_YETER YON=YOK GIRIS=KENAR STOP=SUPURULEN_UC TP=3R SEVIYE=EKIN ZAMAN=ICT_15_5 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=YOK ESIT_TOL=0.05ATR"),
    ("MCD", "MSS=IFVG_YETER YON=ICT GIRIS=ORTA STOP=FVG_MUM TP=LIKIDITE SEVIYE=ICT ZAMAN=EKIN_5_3 DISIPLIN=YOK EMIR=2_SAAT SHARP=SART ESIT_TOL=0.05ATR"),
    ("SBUX", "MSS=IFVG_YETER YON=EKIN GIRIS=KAPANIS STOP=SUPURULEN_UC TP=LIKIDITE SEVIYE=EKIN ZAMAN=EKIN_5_3 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=YOK ESIT_TOL=0.05ATR"),
    ("KO", "MSS=IFVG_YETER YON=ICT GIRIS=KENAR STOP=FVG_MUM TP=2R SEVIYE=EKIN ZAMAN=EKIN_5_3 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=YOK ESIT_TOL=0.05ATR"),
    ("MSTR", "MSS=IFVG_YETER YON=YOK GIRIS=ORTA STOP=FVG_MUM TP=2R SEVIYE=EKIN ZAMAN=EKIN_5_3 DISIPLIN=EKIN EMIR=SEANS_SONU SHARP=SART ESIT_TOL=0.05ATR"),
    ("GME", "MSS=IFVG_YETER YON=EKIN GIRIS=KAPANIS STOP=FVG_MUM TP=LIKIDITE SEVIYE=EKIN ZAMAN=ICT_15_5 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=YOK ESIT_TOL=0.05ATR"),
    ("NKE", "MSS=IFVG_YETER YON=YOK GIRIS=KENAR STOP=FVG_MUM TP=3R SEVIYE=EKIN ZAMAN=EKIN_5_3 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=SART ESIT_TOL=0.05ATR"),
    ("CVX", "MSS=SART YON=EKIN GIRIS=KENAR STOP=FVG_MUM TP=3R SEVIYE=EKIN ZAMAN=EKIN_5_3 DISIPLIN=YOK EMIR=2_SAAT SHARP=SART ESIT_TOL=0.05ATR"),
    ("JPM", "MSS=IFVG_YETER YON=YOK GIRIS=KENAR STOP=SUPURULEN_UC TP=LIKIDITE SEVIYE=EKIN ZAMAN=ICT_15_5 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=SART ESIT_TOL=0.05ATR"),
    ("DIS", "MSS=IFVG_YETER YON=YOK GIRIS=ORTA STOP=FVG_MUM TP=3R SEVIYE=EKIN ZAMAN=EKIN_5_3 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=SART ESIT_TOL=0.05ATR"),
    ("GM", "MSS=IFVG_YETER YON=EKIN GIRIS=ORTA STOP=FVG_MUM TP=2R SEVIYE=EKIN ZAMAN=ICT_15_5 DISIPLIN=YOK EMIR=2_SAAT SHARP=YOK ESIT_TOL=0.05ATR"),
    ("IBM", "MSS=IFVG_YETER YON=EKIN GIRIS=KAPANIS STOP=SWING_GOVDE TP=2R SEVIYE=ICT ZAMAN=ICT_15_5 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=SART ESIT_TOL=0.05ATR"),
    ("ARM", "MSS=IFVG_YETER YON=EKIN GIRIS=KAPANIS STOP=SWING_GOVDE TP=3R SEVIYE=EKIN ZAMAN=ICT_15_5 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=YOK ESIT_TOL=0.05ATR"),
    ("SNOW", "MSS=IFVG_YETER YON=YOK GIRIS=ORTA STOP=SUPURULEN_UC TP=2R SEVIYE=ICT ZAMAN=ICT_15_5 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=YOK ESIT_TOL=0.05ATR"),
    ("ASML", "MSS=IFVG_YETER YON=YOK GIRIS=ORTA STOP=FVG_MUM TP=2R SEVIYE=EKIN ZAMAN=EKIN_5_3 DISIPLIN=YOK EMIR=2_SAAT SHARP=YOK ESIT_TOL=0.05ATR"),
    ("AZN", "MSS=SART YON=YOK GIRIS=ORTA STOP=FVG_MUM TP=3R SEVIYE=EKIN ZAMAN=EKIN_5_3 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=YOK ESIT_TOL=0.05ATR"),
    ("BRK.B", "MSS=SART YON=YOK GIRIS=ORTA STOP=FVG_MUM TP=3R SEVIYE=EKIN ZAMAN=EKIN_5_3 DISIPLIN=YOK EMIR=2_SAAT SHARP=SART ESIT_TOL=0.2ATR"),
    ("XOM", "MSS=IFVG_YETER YON=EKIN GIRIS=KENAR STOP=FVG_MUM TP=LIKIDITE SEVIYE=ICT ZAMAN=EKIN_5_3 DISIPLIN=YOK EMIR=2_SAAT SHARP=YOK ESIT_TOL=0.05ATR"),
    ("ALVG", "MSS=SART YON=YOK GIRIS=KENAR STOP=SUPURULEN_UC TP=2R SEVIYE=EKIN ZAMAN=EKIN_5_3 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=YOK ESIT_TOL=0.05ATR"),
    ("AIRF", "MSS=IFVG_YETER YON=ICT GIRIS=ORTA STOP=SWING_GOVDE TP=3R SEVIYE=EKIN ZAMAN=ICT_15_5 DISIPLIN=YOK EMIR=2_SAAT SHARP=YOK ESIT_TOL=0.05ATR"),
    ("LVMH", "MSS=IFVG_YETER YON=YOK GIRIS=ORTA STOP=FVG_MUM TP=2R SEVIYE=ICT ZAMAN=EKIN_5_3 DISIPLIN=YOK EMIR=2_SAAT SHARP=YOK ESIT_TOL=0.2ATR"),
    ("BAYGn", "MSS=IFVG_YETER YON=YOK GIRIS=KENAR STOP=FVG_MUM TP=2R SEVIYE=EKIN ZAMAN=EKIN_5_3 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=YOK ESIT_TOL=0.2ATR"),
    ("DBKGn", "MSS=SART YON=YOK GIRIS=ORTA STOP=FVG_MUM TP=LIKIDITE SEVIYE=EKIN ZAMAN=EKIN_5_3 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=YOK ESIT_TOL=0.05ATR"),
    ("IBE", "MSS=SART YON=YOK GIRIS=KAPANIS STOP=SUPURULEN_UC TP=2R SEVIYE=ICT ZAMAN=EKIN_5_3 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=YOK ESIT_TOL=0.1ATR"),
    ("TTE", "MSS=IFVG_YETER YON=YOK GIRIS=ORTA STOP=SUPURULEN_UC TP=LIKIDITE SEVIYE=ICT ZAMAN=ICT_15_5 DISIPLIN=YOK EMIR=2_SAAT SHARP=SART ESIT_TOL=0.2ATR"),
    ("ADSGn", "MSS=SART YON=YOK GIRIS=KENAR STOP=FVG_MUM TP=3R SEVIYE=EKIN ZAMAN=EKIN_5_3 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=YOK ESIT_TOL=0.05ATR"),
    ("BMW", "MSS=IFVG_YETER YON=EKIN GIRIS=KENAR STOP=FVG_MUM TP=2R SEVIYE=EKIN ZAMAN=ICT_15_5 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=YOK ESIT_TOL=0.05ATR"),
    ("MBG", "MSS=IFVG_YETER YON=YOK GIRIS=ORTA STOP=FVG_MUM TP=2R SEVIYE=EKIN ZAMAN=EKIN_5_3 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=YOK ESIT_TOL=0.05ATR"),
    ("SIEGn", "MSS=IFVG_YETER YON=YOK GIRIS=ORTA STOP=SUPURULEN_UC TP=LIKIDITE SEVIYE=ICT ZAMAN=EKIN_5_3 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=YOK ESIT_TOL=0.1ATR"),
    ("COFFEE.c", "MSS=IFVG_YETER YON=ICT GIRIS=KENAR STOP=SUPURULEN_UC TP=2R SEVIYE=ICT ZAMAN=ICT_15_5 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=YOK ESIT_TOL=0.05ATR"),
    ("CORN.c", "MSS=SART YON=YOK GIRIS=KENAR STOP=SUPURULEN_UC TP=3R SEVIYE=EKIN ZAMAN=ICT_15_5 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=YOK ESIT_TOL=0.05ATR"),
    ("SOYBEAN.c", "MSS=SART YON=YOK GIRIS=KAPANIS STOP=SUPURULEN_UC TP=3R SEVIYE=ICT ZAMAN=EKIN_5_3 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=YOK ESIT_TOL=0.05ATR"),
    ("DXY.cash", "MSS=IFVG_YETER YON=YOK GIRIS=KENAR STOP=SWING_GOVDE TP=2R SEVIYE=EKIN ZAMAN=EKIN_5_3 DISIPLIN=YOK EMIR=2_SAAT SHARP=SART ESIT_TOL=0.05ATR"),
    ("BTCUSD", "MSS=IFVG_YETER YON=EKIN GIRIS=ORTA STOP=SWING_GOVDE TP=3R SEVIYE=EKIN ZAMAN=ICT_15_5 DISIPLIN=YOK EMIR=2_SAAT SHARP=SART ESIT_TOL=0.2ATR"),
    ("DASHUSD", "MSS=SART YON=YOK GIRIS=KAPANIS STOP=SWING_GOVDE TP=3R SEVIYE=ICT ZAMAN=ICT_15_5 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=YOK ESIT_TOL=0.05ATR"),
    ("ETHUSD", "MSS=IFVG_YETER YON=ICT GIRIS=KENAR STOP=FVG_MUM TP=3R SEVIYE=EKIN ZAMAN=ICT_15_5 DISIPLIN=YOK EMIR=2_SAAT SHARP=YOK ESIT_TOL=0.05ATR"),
    ("LTCUSD", "MSS=IFVG_YETER YON=YOK GIRIS=KENAR STOP=SUPURULEN_UC TP=LIKIDITE SEVIYE=ICT ZAMAN=EKIN_5_3 DISIPLIN=YOK EMIR=2_SAAT SHARP=SART ESIT_TOL=0.2ATR"),
    ("DOTUSD", "MSS=IFVG_YETER YON=YOK GIRIS=ORTA STOP=SWING_GOVDE TP=2R SEVIYE=EKIN ZAMAN=EKIN_5_3 DISIPLIN=YOK EMIR=2_SAAT SHARP=YOK ESIT_TOL=0.05ATR"),
    ("XRPUSD", "MSS=SART YON=EKIN GIRIS=ORTA STOP=SWING_GOVDE TP=LIKIDITE SEVIYE=EKIN ZAMAN=EKIN_5_3 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=YOK ESIT_TOL=0.05ATR"),
    ("ADAUSD", "MSS=SART YON=YOK GIRIS=KENAR STOP=FVG_MUM TP=3R SEVIYE=EKIN ZAMAN=ICT_15_5 DISIPLIN=YOK EMIR=2_SAAT SHARP=YOK ESIT_TOL=0.05ATR"),
    ("SOLUSD", "MSS=IFVG_YETER YON=EKIN GIRIS=KENAR STOP=FVG_MUM TP=2R SEVIYE=EKIN ZAMAN=ICT_15_5 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=YOK ESIT_TOL=0.1ATR"),
    ("AVAUSD", "MSS=IFVG_YETER YON=YOK GIRIS=ORTA STOP=FVG_MUM TP=LIKIDITE SEVIYE=EKIN ZAMAN=EKIN_5_3 DISIPLIN=YOK EMIR=2_SAAT SHARP=SART ESIT_TOL=0.05ATR"),
    ("ETCUSD", "MSS=SART YON=YOK GIRIS=KENAR STOP=SUPURULEN_UC TP=2R SEVIYE=ICT ZAMAN=EKIN_5_3 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=YOK ESIT_TOL=0.2ATR"),
    ("XMRUSD", "MSS=IFVG_YETER YON=EKIN GIRIS=KAPANIS STOP=SWING_GOVDE TP=2R SEVIYE=ICT ZAMAN=EKIN_5_3 DISIPLIN=EKIN EMIR=SEANS_SONU SHARP=YOK ESIT_TOL=0.1ATR"),
    ("NEOUSD", "MSS=IFVG_YETER YON=YOK GIRIS=KENAR STOP=SUPURULEN_UC TP=2R SEVIYE=EKIN ZAMAN=EKIN_5_3 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=YOK ESIT_TOL=0.05ATR"),
    ("DOGEUSD", "MSS=SART YON=YOK GIRIS=ORTA STOP=FVG_MUM TP=3R SEVIYE=EKIN ZAMAN=ICT_15_5 DISIPLIN=EKIN EMIR=2_SAAT SHARP=YOK ESIT_TOL=0.05ATR"),
    ("BNBUSD", "MSS=SART YON=YOK GIRIS=ORTA STOP=FVG_MUM TP=LIKIDITE SEVIYE=EKIN ZAMAN=ICT_15_5 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=YOK ESIT_TOL=0.2ATR"),
    ("SANUSD", "MSS=IFVG_YETER YON=YOK GIRIS=KAPANIS STOP=SUPURULEN_UC TP=3R SEVIYE=EKIN ZAMAN=ICT_15_5 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=YOK ESIT_TOL=0.05ATR"),
    ("LNKUSD", "MSS=SART YON=EKIN GIRIS=KENAR STOP=FVG_MUM TP=2R SEVIYE=EKIN ZAMAN=EKIN_5_3 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=YOK ESIT_TOL=0.05ATR"),
    ("NERUSD", "MSS=IFVG_YETER YON=ICT GIRIS=KAPANIS STOP=FVG_MUM TP=LIKIDITE SEVIYE=EKIN ZAMAN=EKIN_5_3 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=SART ESIT_TOL=0.05ATR"),
    ("ALGUSD", "MSS=SART YON=EKIN GIRIS=KAPANIS STOP=SWING_GOVDE TP=2R SEVIYE=EKIN ZAMAN=ICT_15_5 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=YOK ESIT_TOL=0.05ATR"),
    ("ICPUSD", "MSS=SART YON=YOK GIRIS=KENAR STOP=FVG_MUM TP=2R SEVIYE=ICT ZAMAN=EKIN_5_3 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=YOK ESIT_TOL=0.2ATR"),
    ("AAVUSD", "MSS=IFVG_YETER YON=ICT GIRIS=ORTA STOP=SUPURULEN_UC TP=LIKIDITE SEVIYE=EKIN ZAMAN=EKIN_5_3 DISIPLIN=YOK EMIR=2_SAAT SHARP=YOK ESIT_TOL=0.2ATR"),
    ("BARUSD", "MSS=SART YON=YOK GIRIS=ORTA STOP=SUPURULEN_UC TP=LIKIDITE SEVIYE=ICT ZAMAN=EKIN_5_3 DISIPLIN=YOK EMIR=2_SAAT SHARP=SART ESIT_TOL=0.05ATR"),
    ("GALUSD", "MSS=SART YON=YOK GIRIS=KAPANIS STOP=FVG_MUM TP=3R SEVIYE=EKIN ZAMAN=ICT_15_5 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=YOK ESIT_TOL=0.05ATR"),
    ("GRTUSD", "MSS=IFVG_YETER YON=EKIN GIRIS=KAPANIS STOP=SWING_GOVDE TP=2R SEVIYE=ICT ZAMAN=EKIN_5_3 DISIPLIN=EKIN EMIR=SEANS_SONU SHARP=YOK ESIT_TOL=0.05ATR"),
    ("IMXUSD", "MSS=IFVG_YETER YON=EKIN GIRIS=ORTA STOP=FVG_MUM TP=2R SEVIYE=ICT ZAMAN=ICT_15_5 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=SART ESIT_TOL=0.2ATR"),
    ("MANUSD", "MSS=IFVG_YETER YON=YOK GIRIS=KENAR STOP=SUPURULEN_UC TP=3R SEVIYE=ICT ZAMAN=EKIN_5_3 DISIPLIN=YOK EMIR=2_SAAT SHARP=YOK ESIT_TOL=0.2ATR"),
    ("VECUSD", "MSS=SART YON=YOK GIRIS=KENAR STOP=SWING_GOVDE TP=3R SEVIYE=EKIN ZAMAN=ICT_15_5 DISIPLIN=YOK EMIR=2_SAAT SHARP=YOK ESIT_TOL=0.05ATR"),
    ("XLMUSD", "MSS=SART YON=YOK GIRIS=ORTA STOP=SUPURULEN_UC TP=LIKIDITE SEVIYE=EKIN ZAMAN=ICT_15_5 DISIPLIN=YOK EMIR=2_SAAT SHARP=YOK ESIT_TOL=0.05ATR"),
    ("UNIUSD", "MSS=IFVG_YETER YON=ICT GIRIS=KAPANIS STOP=FVG_MUM TP=2R SEVIYE=EKIN ZAMAN=ICT_15_5 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=YOK ESIT_TOL=0.2ATR"),
    ("XTZUSD", "MSS=IFVG_YETER YON=YOK GIRIS=KAPANIS STOP=FVG_MUM TP=LIKIDITE SEVIYE=ICT ZAMAN=ICT_15_5 DISIPLIN=YOK EMIR=SEANS_SONU SHARP=YOK ESIT_TOL=0.1ATR"),
]


def coz(s):
    d = dict(p.split("=", 1) for p in s.split())
    ads = [q.split("_", 1)[1] for q, _ in SORULAR]
    return tuple(SORULAR[i][1].index(d[a]) for i, a in enumerate(ads))


def gecis(kur, son, s2, s9, s12, kk):
    """bir mantigin gun gun sirali gecisi: alinan kurulumlarin sira numaralari"""
    fill, bit, R, d, kod = son
    alinan, mesgul = [], -1
    kazandi, seans = set(), set()
    for i, x in enumerate(kur):
        if s12 == 1 and not x["sharp"]:
            continue
        istek = 1 if x["y"] > 0 else -1
        if s2 == 1 and x["yon_ek"] != istek:
            continue
        if s2 == 2 and x["yon_ic"] != istek:
            continue
        if x["Td"] < mesgul:
            continue
        if s9 == 1 and (x["k"] in kazandi or (x["k"], x["kz"]) in seans):
            continue
        kd = kod[i, kk]
        if kd == 9:
            continue
        mesgul = bit[i, kk]
        if kd == 8:
            continue
        alinan.append(i)
        if s9 == 1:
            seans.add((x["k"], x["kz"]))
            if R[i, kk] > 0:
                kazandi.add(x["k"])
    return alinan


def kk_coz(m):
    s1, s2, gi, si, ti, s6, s7, s9, ei, s12, s13 = m
    return (s1, s6, s7, s13), s2, s9, s12, ((gi * 3 + si) * 3 + ti) * 2 + ei


def sembol_isle(sb, gun0, ngun, ayk, nay, sadece=None):
    """stat[NM, 6] (islem, TP, STOP, SURE, kazanan, dolar), gunluk[NM, ngun], ay[NM, nay], onbellek"""
    stat = np.zeros((NM, 6))
    gunluk = np.zeros((NM, ngun), np.float32)
    ay = np.zeros((NM, nay))
    kur = sb.kurulumlar(sadece)
    onb = {}
    for key, lst in kur.items():
        if not lst:
            continue
        s1, s6, s7, s13 = key
        arr = [sb.sonuclar(x) for x in lst]
        fill = np.array([a[0] for a in arr])
        bit = np.array([a[1] for a in arr])
        R = np.array([a[2] for a in arr])
        dl = np.array([a[3] for a in arr])
        kod = np.array([a[4] for a in arr])
        gk = np.clip(bit // 1440 - gun0, 0, ngun - 1)
        son = (fill, bit, R, dl, kod)
        onb[key] = (lst, arr, son, gk)
        for s2 in range(3):
            for s9 in range(2):
                for s12 in range(2):
                    for gi in range(3):
                        for si in range(3):
                            for ti in range(3):
                                for ei in range(2):
                                    kk = ((gi * 3 + si) * 3 + ti) * 2 + ei
                                    al = gecis(lst, son, s2, s9, s12, kk)
                                    if not al:
                                        continue
                                    mi = MI[(s1, s2, gi, si, ti, s6, s7, s9, ei, s12, s13)]
                                    al = np.array(al)
                                    kd, rr, dd, gg = kod[al, kk], R[al, kk], dl[al, kk], gk[al, kk]
                                    stat[mi] += (len(al), (kd == 1).sum(), (kd == -1).sum(), (kd == 0).sum(),
                                                 (rr > 0).sum(), dd.sum())
                                    np.add.at(gunluk[mi], gg, dd)
                                    np.add.at(ay[mi], ayk[gg], dd)
    return stat, gunluk, ay, onb


def islemleri_al(onb, m):
    key, s2, s9, s12, kk = kk_coz(m)
    if key not in onb:
        return []
    lst, arr, son, gk = onb[key]
    return [(lst[i], kk, arr[i]) for i in gecis(lst, son, s2, s9, s12, kk)]


def ozet(v):
    n = int(v[0])
    return dict(islem=n, TP=int(v[1]), STOP=int(v[2]), SURE=int(v[3]),
                basari=round(100.0 * v[4] / n, 1) if n else 0.0, dolar=round(float(v[5]), 2))


def st(v):
    o = ozet(v)
    return "%5d %4d %5d %4d %%%5.1f %+10.2f" % (o["islem"], o["TP"], o["STOP"], o["SURE"], o["basari"], o["dolar"])


def hesap(g):
    if not np.any(g):
        return "islem yok"
    bak = BASLANGIC + np.cumsum(g)
    tepe = np.maximum.accumulate(np.r_[BASLANGIC, bak])[1:]
    a = g[g != 0]
    return ("10.000 $ -> %.2f $ (net %+.2f $) | en kotu gun %+.2f $ | en iyi gun %+.2f $ | en buyuk dusus %+.2f $ | "
            "250 $ ustu zarar gunu %d" % (bak[-1], bak[-1] - BASLANGIC, a.min(), a.max(), (bak - tepe).min(),
                                           int((g < -250).sum())))


def kart(s, m, x, kk, a):
    fill, bit, R, d, kod, E, S, TP, lot = [v[kk] for v in a]
    sg = 1 if x["y"] < 0 else -1
    return dict(sembol=s, mantik=mad(m), karar_tr=tr(x["Td"]), seans=x["kz"], yon="SAT" if x["y"] < 0 else "AL",
                supurulen=x["sev"], supurme_tr=tr(x["ts"]), giris_turu=x["tur"], giris=round(sg * E, 6),
                stop=round(sg * S, 6), tp=round(sg * TP, 6), lot=round(lot, 2), dolum_tr=tr(fill), cikis_tr=tr(bit),
                sonuc=SONUC_KOD.get(int(kod), "?"), R=round(R, 3), dolar=round(d, 2), cikis_dk=int(bit))



def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gun", type=int, default=GUN_SAYISI)
    ap.add_argument("--cikti", default="")
    ap.add_argument("--kapatma_yok", action="store_true")
    args = ap.parse_args()
    global NY_KAPAT
    NY_KAPAT = not args.kapatma_yok
    kapyaz = "NY 16:00 KAPATMA ACIK" if NY_KAPAT else "NY 16:00 KAPATMA YOK"
    if mt5 is None:
        sys.exit("MetaTrader5 modulu yok:  py -3.8 -m pip install MetaTrader5")
    if not mt5.initialize():
        sys.exit("MT5 baglantisi kurulamadi: %s" % (mt5.last_error(),))
    semboller = [s for s, _ in MANTIK]
    saat_notu = saat_dogrula(semboller)
    print(saat_notu)
    simdi = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=sunucu_utc(datetime.now(timezone.utc).date()))
    bas = (simdi - timedelta(days=args.gun)).replace(hour=0, minute=0, second=0, microsecond=0)
    bas_dk = int((bas - datetime(1970, 1, 1)).total_seconds() // 60)
    gun0 = bas_dk // 1440
    ngun = int((simdi - bas).days) + 3
    aylar = sorted(set((bas + timedelta(days=d)).strftime("%Y-%m") for d in range(ngun)))
    ayk = np.array([aylar.index((bas + timedelta(days=d)).strftime("%Y-%m")) for d in range(ngun)])
    klasor = args.cikti or os.path.join(masaustu(), "ekin_142_test_%s" % datetime.now().strftime("%Y%m%d_%H%M"))
    if not os.path.isdir(klasor):
        os.makedirs(klasor)
    yaz = dict(sep=";", decimal=",", index=False, encoding="utf-8-sig")
    print("Sembol: %d | %s -> bugun (%d gun, gun gun) | her sembol kendi mantigi | spread dahil | %s"
          % (len(semboller), bas.date(), args.gun, kapyaz))
    print("Sonuclar: %s" % klasor)
    kart_l, yok, t0 = [], [], time.time()
    for n_, (s, ms) in enumerate(MANTIK, 1):
        m = coz(ms)
        try:
            if not mt5.symbol_select(s, True):
                yok.append(s); print("[%d/%d] %s : sembol yok" % (n_, len(MANTIK), s)); continue
            bilgi = mt5.symbol_info(s)
            vpl = deger_lot(s, bilgi) if bilgi is not None else None
            m1 = cek(s, mt5.TIMEFRAME_M1, bas - timedelta(days=45), simdi + timedelta(days=1), 15)
            if bilgi is None or not vpl or m1 is None or len(m1) < 20000:
                yok.append(s); print("[%d/%d] %s : veri yok" % (n_, len(MANTIK), s)); continue
            forex = getattr(bilgi, "trade_calc_mode", 0) in (0, 5)
            sb = Sembol(m1, bilgi, vpl, forex, bas_dk)
            _, _, _, onb = sembol_isle(sb, gun0, ngun, ayk, len(aylar), sadece={kk_coz(m)[0]})
            isl = islemleri_al(onb, m)
        except Exception as h:
            yok.append(s); print("[%d/%d] %s : hata %s" % (n_, len(MANTIK), s, h)); continue
        for x, kk, a in isl:
            c = kart(s, m, x, kk, a)
            if c["sonuc"] == "SURE" and not NY_KAPAT:
                c["sonuc"] = "ACIK"
            c["dolum_dk"] = int(a[0][kk])
            kart_l.append(c)
        z = [c for c in kart_l if c["sembol"] == s]
        print("[%d/%d] %s : %d islem | TP %d | STOP %d | SURE %d | ACIK %d | %+.2f $  (%.0f sn)" % (
            n_, len(MANTIK), s, len(z), sum(c["sonuc"] == "TP" for c in z), sum(c["sonuc"] == "STOP" for c in z),
            sum(c["sonuc"] == "SURE" for c in z), sum(c["sonuc"] == "ACIK" for c in z), sum(c["dolar"] for c in z),
            time.time() - t0))
    mt5.shutdown()
    if not kart_l:
        sys.exit("Hic islem yok.")
    d = pd.DataFrame(kart_l)
    d.drop(columns=["cikis_dk", "dolum_dk"]).to_csv(os.path.join(klasor, "1_islemler.csv"), **yaz)
    kap = d[d["sonuc"] != "ACIK"]
    acik = d[d["sonuc"] == "ACIK"]
    g = np.zeros(ngun)
    for c in kap.itertuples():
        k = int(c.cikis_dk) // 1440 - gun0
        if 0 <= k < ngun:
            g[k] += c.dolar
    # ayni anda acik islem sayisi
    ol = sorted([(int(c.dolum_dk), 1) for c in d.itertuples()] + [(int(c.cikis_dk), -1) for c in kap.itertuples()])
    an, en = 0, 0
    for _, v in ol:
        an += v
        en = max(en, an)

    def tab(z):
        n = len(z)
        tp, stp, ac = int((z["sonuc"] == "TP").sum()), int((z["sonuc"] == "STOP").sum()), int((z["sonuc"] == "ACIK").sum())
        kz = z[z["sonuc"] != "ACIK"]
        bas_ = 100.0 * (kz["R"] > 0).mean() if len(kz) else 0.0
        return n, tp, stp, ac, bas_, float(kz["dolar"].sum()), float(z[z["sonuc"] == "ACIK"]["dolar"].sum()), int((z["sonuc"] == "SURE").sum())

    rows = []
    for s, z in d.groupby("sembol"):
        n, tp, stp, ac, b, dl, ad, su = tab(z)
        rows.append(dict(sembol=s, mantik=z["mantik"].iloc[0], islem=n, TP=tp, STOP=stp, SURE=su, ACIK=ac, basari=round(b, 1),
                         dolar=round(dl, 2), acik_dolar=round(ad, 2)))
    sb_ = pd.DataFrame(rows).sort_values(["basari", "dolar"], ascending=False)
    c = "=" * 140
    n, tp, stp, ac, b, dl, ad, su = tab(d)
    m = [c, "EKIN MODELI - 142 SEMBOL KENDI MANTIGIYLA | %s -> bugun (%d gun) | SPREAD DAHIL | risk 15 $ | %s"
         % (bas.date(), args.gun, kapyaz), "SAAT: " + saat_notu, c, "",
         "GENEL (butun semboller ayni hesapta):",
         "   Islem %d | TP %d | STOP %d | NY 16:00 SURE %d | hala ACIK %d | basari (kapananlarda) %%%.1f" % (n, tp, stp, su, ac, b),
         "   Kapanan islemler: " + hesap(g),
         "   Hala acik %d islemin su anki degeri: %+.2f $" % (ac, ad),
         "   Ayni anda en fazla acik islem: %d  (her biri en fazla ~15 $ risk -> en fazla ~%d $ acik risk)" % (en, en * 15),
         "   ay ay (kapananlar): " + "  ".join("%s %+.0f $" % (a, g[ayk == j].sum()) for j, a in enumerate(aylar)), ""]
    ust = sb_[(sb_["basari"] > 50) & ((sb_["TP"] + sb_["STOP"]) > 0)]
    m += [c, "SEMBOL SEMBOL - BASARIYA GORE (basari = kapanan islemlerde karla kapananlarin orani)", c,
          "%-12s | %5s %4s %5s %5s %5s %7s %10s %11s | MANTIK" % ("SEMBOL", "ISLEM", "TP", "STOP", "SURE", "ACIK", "BASARI", "DOLAR", "ACIK_DEGER")]
    for r in sb_.itertuples():
        m.append("%-12s | %5d %4d %5d %5d %5d %%%6.1f %+10.2f %+11.2f | %s" % (r.sembol, r.islem, r.TP, r.STOP, r.SURE, r.ACIK, r.basari,
                                                                         r.dolar, r.acik_dolar, r.mantik))
    g50 = np.zeros(ngun)
    for cc in kap[kap["sembol"].isin(ust["sembol"])].itertuples():
        k = int(cc.cikis_dk) // 1440 - gun0
        if 0 <= k < ngun:
            g50[k] += cc.dolar
    m += ["", c, "BASARISI %%50 USTU SEMBOLLER: %d" % len(ust), c,
          "%-12s | %5s %4s %5s %5s %5s %7s %10s" % ("SEMBOL", "ISLEM", "TP", "STOP", "SURE", "ACIK", "BASARI", "DOLAR")]
    for r in ust.itertuples():
        m.append("%-12s | %5d %4d %5d %5d %5d %%%6.1f %+10.2f" % (r.sembol, r.islem, r.TP, r.STOP, r.SURE, r.ACIK, r.basari, r.dolar))
    m.append("Sadece bu semboller, 10.000 $ (kapananlar): " + hesap(g50))
    m.append("   ay ay: " + "  ".join("%s %+.0f $" % (a, g50[ayk == j].sum()) for j, a in enumerate(aylar)))
    if yok:
        m += ["", "Verisi olmayan / hata: " + ", ".join(yok)]
    ms = "\n".join(m)
    print("\n" + ms)
    with open(os.path.join(klasor, "0_OZET.txt"), "w", encoding="utf-8") as fh:
        fh.write(ms + "\n")
    sb_.to_csv(os.path.join(klasor, "2_semboller.csv"), **yaz)
    print("\nDosyalar: %s" % os.path.abspath(klasor))


if __name__ == "__main__":
    main()
