# -*- coding: utf-8 -*-
"""
EKIN YUZBASIOGLU MODELI - TAM TEST - SON 6 AY (180 GUN) - BUTUN SEMBOLLER - GUN GUN
====================================================================================
Python 3.8:   py -3.8 ekin_tam_test_6ay.py
Gerekli:      py -3.8 -m pip install MetaTrader5 pandas numpy
Sadece bazi semboller:   py -3.8 ekin_tam_test_6ay.py --sembol US100.cash,EURUSD
TEK DOSYA. MT5'e baglanir, SADECE gecmis veri okur, ISLEM ACMAZ.  UZUN SURER (sembol basina ~20-60 sn).
SONUCLAR MASAUSTUNE yazilir:  Masaustu\\ekin_tam_test_<tarih>\\0_OZET.txt

GUN GUN: 180 gun once baslar; her gun her sembolde, o gunun killzone'unda SADECE O ANA KADAR olusmus
mumlara bakilir, sartlar olustuysa islem acilir; sonra ertesi gune gecilir, bugune kadar.
Donem bolunmez, secim yapilmaz: her mantik 180 gunun TAMAMINDA test edilir.  Ay ay dokum sadece bilgi.

MODEL (Ekin 34, 36, 38, 39, 40, 41, 42 + ICT 2022; SATIS anlatiliyor, ALIS birebir tersi)
  1) SEVIYE   : killzone basinda ALINMAMIS onemli seviye; fiyat ustune cikar (FVG'ye girer) = SUPURME.
                Seviye ALINANA kadar, FVG DOLANA kadar gecerli (yas siniri yok).
  2) KIRILIM  : supurmeden sonra son swing dibin (3 mum, Ekin 39) ALTINDA GOVDE KAPANISI = MSS  [ya da IFVG]
  3) GIRIS    : kirilim bacagindaki FVG / IFVG; birden fazlaysa fiyata en yakin olan ("ilk FVG'ye girecegiz", Ekin 39)
     IFVG     : likiditeyi ALIRKEN (supurulen seviyeye giden bacakta) birakilan yukari FVG'nin govdeyle bozulmasi (Ekin 34)
  4) Seans icinde arama devam eder; DISIPLIN=EKIN ise SEMBOL BAZINDA: seansta tek islem, kazandiysa o sembolde
     o gun bitti, kaybettiyse sonraki seansta tekrar bakilir (Ekin 36, 39).  Diger semboller bundan etkilenmez.
  Risk 15 $.  En kucuk lotta zarar 30 $'i gecerse islem yok.  SPREAD DAHIL (MT5 1 dk spread'i, 6 $ kurali).
  SAAT (soru 8): FOREX Londra NY 02:00-05:00 + NY 07:00-10:00 | DIGER NY 08:30-11:00.  Asya yok.
  Acik islem NY 16:00'da kapanir (Ekin 42: "gun icinde cikmak").
  Seans seviyeleri (ICT): Asya NY 20:00-24:00, Londra 02:00-05:00, onceki gun NY ogleden sonra 13:30-16:00.
  ESIT TEPE: 1 saatlik ya da 4 saatlik grafikte birbirine yakin iki swing tepe; aralarinda fiyat o seviyeyi
             gecmemis (fiyat gelip gecemeyip donmus); alinana kadar gecerli.

SORULAR VE DENENEN BUTUN CEVAPLAR (her sembolde 15.552 mantik, hepsi ayri ayri)
  S1 MSS        : SART  |  IFVG_YETER (Ekin 34: IFVG olusursa MSS beklenmez)
  S2 YON        : YOK  |  EKIN (dun govdeyle onceki gunun tepesi ustunde kapandi=AL, fitille gecip icerde kapandi=SAT)
                  |  ICT (dun gunluk FVG'ye girip saygi duydu: bullish FVG=AL, bearish FVG=SAT)
  S3 GIRIS      : ORTA (FVG %50)  |  KENAR (FVG basi)  |  KAPANIS (kirilim mumu kapaninca piyasa emri)
  S4 STOP       : SWING_GOVDE  |  FVG_MUM (FVG'yi baslatan mumun govdesi; ust uste FVG varsa ustteki)  |  SUPURULEN_UC
  S5 TP         : 2R  |  3R  |  LIKIDITE (en yakin karsi likidite, en az 2R)
  S6 SEVIYE     : EKIN (onceki gun, onceki hafta, Asya, Londra, onceki NY PM, esit tepeler, 1S/4S FVG)
                  |  ICT (onceki gun, esit tepeler, 1S/4S/gunluk FVG)
  S7 ZAMAN      : EKIN_5_3 (kirilim 5 dk, FVG 5 dk; yoksa 3 dk)  |  ICT_15_5 (kirilim 15 dk, FVG 5 dk)
  S9 DISIPLIN   : YOK  |  EKIN (yukarida)
  S11 EMIR      : SEANS_SONU  |  2_SAAT
  S12 SHARP     : YOK  |  SART (likiditeyi alirken yukari FVG birakmis olmali = U donusu)
  S13 ESIT_TOL  : esit tepe icin iki tepe arasi fark  0.05 / 0.1 / 0.2 ATR  (kaynaklarda sayi yok, ucu de denenir)

CIKTI:  0_OZET.txt  (her sorunun her cevabi, en iyi mantiklar ay ay, %50 ustu semboller, 10.000 $)
        1_mantiklar.csv   2_sembol_en_iyi.csv   3_islemler.csv (her islemin karti: TR saati, giris, stop, TP, sonuc)
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
GUN_SAYISI = 180
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
            if D + 1440 < self.bas_dk or D + KAPANIS > self.son:
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
        z1 = self.ix(x["D"] + KAPANIS)
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
    ap.add_argument("--sembol", default="")
    ap.add_argument("--cikti", default="")
    args = ap.parse_args()
    if mt5 is None:
        sys.exit("MetaTrader5 modulu yok:  py -3.8 -m pip install MetaTrader5")
    if not mt5.initialize():
        sys.exit("MT5 baglantisi kurulamadi: %s" % (mt5.last_error(),))
    semboller = ([x.strip() for x in args.sembol.split(",") if x.strip()] if args.sembol
                 else [x.name for x in (mt5.symbols_get() or [])])
    saat_notu = saat_dogrula(semboller)
    print(saat_notu)
    simdi = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=sunucu_utc(datetime.now(timezone.utc).date()))
    bas = (simdi - timedelta(days=args.gun)).replace(hour=0, minute=0, second=0, microsecond=0)
    bas_dk = int((bas - datetime(1970, 1, 1)).total_seconds() // 60)
    gun0 = bas_dk // 1440
    ngun = int((simdi - bas).days) + 3
    aylar = sorted(set((bas + timedelta(days=d)).strftime("%Y-%m") for d in range(ngun)))
    ayk = np.array([aylar.index((bas + timedelta(days=d)).strftime("%Y-%m")) for d in range(ngun)])
    nay = len(aylar)
    klasor = args.cikti or os.path.join(masaustu(), "ekin_tam_test_%s" % datetime.now().strftime("%Y%m%d_%H%M"))
    if not os.path.isdir(klasor):
        os.makedirs(klasor)
    yaz = dict(sep=";", decimal=",", index=False, encoding="utf-8-sig")
    print("Sembol: %d | %s -> bugun (%d gun, gun gun) | %d mantik | spread dahil, risk 15 $"
          % (len(semboller), bas.date(), args.gun, NM))
    print("Sonuclar: %s" % klasor)
    TOP = np.zeros((NM, 6))
    GUN = np.zeros((NM, ngun))
    AY = np.zeros((NM, nay))
    hepsi, kendi, yok, t0 = {}, [], [], time.time()

    def veri(s):
        if not mt5.symbol_select(s, True):
            return None
        bilgi = mt5.symbol_info(s)
        vpl = deger_lot(s, bilgi) if bilgi is not None else None
        m1 = cek(s, mt5.TIMEFRAME_M1, bas - timedelta(days=45), simdi + timedelta(days=1), 15)
        if bilgi is None or not vpl or m1 is None or len(m1) < 20000:
            return None
        forex = getattr(bilgi, "trade_calc_mode", 0) in (0, 5)
        return Sembol(m1, bilgi, vpl, forex, bas_dk)

    kartlar = []
    for n_, s in enumerate(semboller, 1):
        try:
            sb = veri(s)
            if sb is None:
                yok.append(s); print("[%d/%d] %s : veri yok" % (n_, len(semboller), s)); continue
            stat, gunluk, ay, onb = sembol_isle(sb, gun0, ngun, ayk, nay)
        except Exception as h:
            yok.append(s); print("[%d/%d] %s : hata %s" % (n_, len(semboller), s, h)); continue
        TOP += stat
        GUN += gunluk
        AY += ay
        hepsi[s] = stat.astype(np.float32)
        # bu sembolun kendi en iyisi: en az 5 islem, basari %50 ustu, en cok kar
        ok = np.flatnonzero((stat[:, 0] >= 5) & (stat[:, 4] > 0.5 * stat[:, 0]) & (stat[:, 5] > 0))
        en = int(ok[np.argmax(stat[ok, 5])]) if ok.size else None
        if en is not None:
            m = MANTIKLAR[en]
            isl = islemleri_al(onb, m)
            gg = np.zeros(ngun)
            for x, kk, a in isl:
                c = kart(s, m, x, kk, a)
                c["liste"] = "SEMBOL_KENDI_EN_IYI"
                kartlar.append(c)
                k = int(a[1][kk]) // 1440 - gun0
                if 0 <= k < ngun:
                    gg[k] += a[3][kk]
            kendi.append((s, en, stat[en].copy(), gg))
        del onb
        print("[%d/%d] %s : kendi en iyisi %s -> %s  (%.0f sn)" % (
            n_, len(semboller), s, mad(MANTIKLAR[en]) if en is not None else "- (%50 ustu yok)",
            st(stat[en]) if en is not None else "", time.time() - t0))
    if not hepsi:
        mt5.shutdown()
        sys.exit("Hic sonuc yok.")
    huni = dict(SAY)
    # ------------------------------------------------- en iyi tek mantik: %50 ustu semboller -> islemleri al
    sira = np.argsort(-TOP[:, 5])
    gen = int(sira[0])
    gen_m = MANTIKLAR[gen]
    y50 = [s for s, v in hepsi.items() if v[gen, 0] >= 5 and v[gen, 4] > 0.5 * v[gen, 0]]
    g50 = np.zeros(ngun)
    a50 = np.zeros(nay)
    print("\nEn iyi tek mantigin %%50 ustu %d sembolu icin islem kartlari aliniyor..." % len(y50))
    key = kk_coz(gen_m)[0]
    for s in y50:
        try:
            sb = veri(s)
            _, _, _, onb = sembol_isle(sb, gun0, ngun, ayk, nay, sadece={key})
        except Exception as h:
            print("   %s : hata %s" % (s, h)); continue
        for x, kk, a in islemleri_al(onb, gen_m):
            c = kart(s, gen_m, x, kk, a)
            c["liste"] = "EN_IYI_TEK_MANTIK_%50_USTU"
            kartlar.append(c)
            k = int(a[1][kk]) // 1440 - gun0
            if 0 <= k < ngun:
                g50[k] += a[3][kk]
                a50[ayk[k]] += a[3][kk]
    mt5.shutdown()
    if kartlar:
        pd.DataFrame(kartlar).drop(columns=["cikis_dk"]).to_csv(os.path.join(klasor, "3_islemler.csv"), **yaz)
    rows = []
    for i, m in enumerate(MANTIKLAR):
        r = dict(zip(SQ, [SORULAR[q][1][v] for q, v in enumerate(m)]))
        r.update(ozet(TOP[i]))
        r.update({"ay_" + a: round(AY[i, j], 2) for j, a in enumerate(aylar)})
        rows.append(r)
    pd.DataFrame(rows).sort_values("dolar", ascending=False).to_csv(os.path.join(klasor, "1_mantiklar.csv"), **yaz)
    pd.DataFrame([dict(sembol=s, mantik=mad(MANTIKLAR[b]), **ozet(v)) for s, b, v, _ in kendi]
                 ).to_csv(os.path.join(klasor, "2_sembol_en_iyi.csv"), **yaz)

    c = "=" * 150
    aybas = " ".join("%9s" % a for a in aylar)
    bsl = "%-5s %5s %4s %5s %4s %6s %10s || AY AY: %s" % ("SIRA", "ISLEM", "TP", "STOP", "SURE", "BASARI", "DOLAR", aybas)
    m = [c, "EKIN MODELI TAM TEST | %s -> bugun (%d gun, gun gun) | %d sembol | %d mantik | SPREAD DAHIL | risk 15 $"
         % (bas.date(), args.gun, len(hepsi), NM), "SAAT: " + saat_notu,
         "HUNI: killzone penceresi %d | supurme %d | kirilim %d | kurulum %d" % (
             huni["pencere"], huni["supurme"], huni["kirilim"], huni["kurulum"]), c]
    m += ["", "1) HER SORUNUN HER CEVABI (o cevabi iceren butun mantiklarin toplami - sadece karsilastirma icin)",
          "%-16s %-14s | %9s %7s %14s" % ("SORU", "CEVAP", "ISLEM", "BASARI", "DOLAR")]
    MA = np.array(MANTIKLAR)
    for q, (sq, cev) in enumerate(SORULAR):
        par = []
        for v, ad in enumerate(cev):
            t = TOP[MA[:, q] == v].sum(0)
            par.append((t[5], ad, t))
        par.sort(key=lambda z: -z[0])
        for j, (_, ad, t) in enumerate(par):
            m.append("%-16s %-14s | %9d %%%6.1f %+14.2f%s" % (sq if j == 0 else "", ad, t[0], 100.0 * t[4] / max(1, t[0]),
                                                           t[5], "   <- en iyi" if j == 0 else ""))
    m += ["", c, "2) BUTUN SEMBOLLERDE TEK MANTIK - EN COK KAZANDIRAN 20 (180 gun) ve AY AY", c, bsl]
    for r, i in enumerate(sira[:20], 1):
        m.append("%-5d %s || AY AY: %s" % (r, st(TOP[i]), " ".join("%+9.0f" % v for v in AY[i])))
        m.append("      " + mad(MANTIKLAR[i]))
    herayi = [i for i in sira[:2000] if np.all(AY[i] > 0) and TOP[i, 0] >= 30]
    m += ["", "-- HER AY ARTIDA KAPATAN tek mantiklar (en az 30 islem): %d tane (ilk 10) --" % len(herayi), bsl]
    for r, i in enumerate(herayi[:10], 1):
        m.append("%-5d %s || AY AY: %s" % (r, st(TOP[i]), " ".join("%+9.0f" % v for v in AY[i])))
        m.append("      " + mad(MANTIKLAR[i]))
    m += ["", c, "3) EN COK KAZANDIRAN TEK MANTIK: " + mad(gen_m), c,
          "Butun semboller, 10.000 $ : " + hesap(GUN[gen]),
          "-- BU MANTIKTA BASARISI %%50 USTU SEMBOLLER (en az 5 islem): %d --" % len(y50),
          "%-14s | %5s %4s %5s %4s %6s %10s" % ("SEMBOL", "ISLEM", "TP", "STOP", "SURE", "BASARI", "DOLAR")]
    for s in sorted(y50, key=lambda z: -hepsi[z][gen, 5]):
        m.append("%-14s | %s" % (s, st(hepsi[s][gen])))
    if y50:
        m.append("SADECE BU SEMBOLLER kullanilsaydi, 10.000 $ : " + hesap(g50))
        m.append("   ay ay: " + "  ".join("%s %+.0f $" % (a, v) for a, v in zip(aylar, a50)))
    m += ["", c, "4) HER SEMBOL KENDI EN IYI MANTIGIYLA (basari %%50 ustu, en az 5 islem, karda): %d sembol" % len(kendi), c,
          "%-14s | %5s %4s %5s %4s %6s %10s | MANTIK" % ("SEMBOL", "ISLEM", "TP", "STOP", "SURE", "BASARI", "DOLAR")]
    gk_ = np.zeros(ngun)
    ak_ = np.zeros(nay)
    for s, b, v, gg in sorted(kendi, key=lambda z: -z[2][5]):
        m.append("%-14s | %s | %s" % (s, st(v), mad(MANTIKLAR[b])))
        gk_ += gg
        for d in np.flatnonzero(gg):
            ak_[ayk[d]] += gg[d]
    if kendi:
        m.append("BU SEMBOLLER kendi mantiklariyla kullanilsaydi, 10.000 $ : " + hesap(gk_))
        m.append("   ay ay: " + "  ".join("%s %+.0f $" % (a, v) for a, v in zip(aylar, ak_)))
    m += ["", c, "5) SONUC", c,
          "Tek mantik, butun semboller : %+.2f $   | tek mantik, %%50 ustu semboller : %+.2f $" % (TOP[gen, 5], g50.sum()),
          "Her sembol kendi mantigiyla : %+.2f $" % gk_.sum(),
          "Not: 4. bolumde her sembol 15.552 mantik icinden kendi en iyisini aldigi icin sonuc iyi gorunur;",
          "AY AY dokum her ay ayni sekilde kazandirip kazandirmadigini gosterir.  Her sorunun en iyi cevabi 1. bolumde."]
    if yok:
        m += ["", "Verisi olmayan: " + ", ".join(yok)]
    ms = "\n".join(m)
    print("\n" + ms)
    with open(os.path.join(klasor, "0_OZET.txt"), "w", encoding="utf-8") as fh:
        fh.write(ms + "\n")
    print("\nDosyalar: %s" % os.path.abspath(klasor))


if __name__ == "__main__":
    main()
