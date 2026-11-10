# -*- coding: utf-8 -*-
"""
EKIN YUZBASIOGLU MODELI - TAM TEST - SON 6 AY - BUTUN SEMBOLLER - GUN GUN
==========================================================================
Python 3.8:   py -3.8 ekin_tam_test_6ay.py
Gerekli:      py -3.8 -m pip install MetaTrader5 pandas numpy
Sadece bazi semboller:   py -3.8 ekin_tam_test_6ay.py --sembol US100.cash,EURUSD
TEK DOSYA. MT5'e baglanir, SADECE gecmis veri okur, ISLEM ACMAZ.  UZUN SUREBILIR (sembol basina ~10-30 sn).
SONUCLAR MASAUSTUNE yazilir:  Masaustu\\ekin_tam_test_<tarih>\\0_OZET.txt

GUN GUN: her gun, o gunun killzone'unda, sadece O ANA KADAR olusmus mumlara bakilir (gelecek gorulmez).
6 ay ikiye bolunur:  SECIM (ilk 4 ay) - en iyi mantik burada secilir  /  KONTROL (son 2 ay) - secilen
mantik hic gormedigi bu donemde olculur.  Boylece "en iyi donemi secme" olmaz.

MODEL (Ekin bolum 34, 38, 39, 40, 41 + ICT 2022; SATIS anlatiliyor, ALIS birebir tersi)
  1) SEVIYE   : killzone basinda ALINMAMIS onemli seviye; fiyat ustune cikar (ya da FVG'ye girer) = SUPURME
  2) KIRILIM  : supurmeden sonra son swing dibin ALTINDA GOVDE KAPANISI (MSS)  [ya da IFVG, asagida]
  3) GIRIS    : kirilim bacagindaki FVG / IFVG'den (fiyata en yakin olan); yoksa islem yok
  4) STOP / TP / saat / risk asagidaki secenekler.   Risk 15 $, spread dahil (6 $ kurali), en kucuk lotta 30 $ kurali.
  SAAT (sabit, soru 8): FOREX Londra NY 02:00-05:00 + NY 07:00-10:00 | DIGER NY 08:30-11:00.  Asya yok.
                        Acik islem NY 16:00'da kapanir.

SORULAR VE DENENEN BUTUN CEVAPLAR  (2x3x3x3x3x2x2x2x2x2 = 5184 mantik, her sembolde)
  S1 MSS      : SART (38/39, ICT)  |  IFVG_YETER (34: IFVG olusursa MSS beklenmez)
  S2 YON      : YOK  |  EKIN (dun govdeyle onceki gunun tepesi ustunde kapandi=AL, fitille gecip icerde kapandi=SAT;
                      dipte tersi)  |  ICT (dun gunluk FVG'ye girip saygi duydu: bullish FVG=AL, bearish FVG=SAT)
  S3 GIRIS    : ORTA (FVG %50)  |  KENAR (FVG basi)  |  KAPANIS (kirilim mumu kapaninca piyasa emri)
  S4 STOP     : SWING_GOVDE (tepe mumunun govdesi)  |  FVG_MUM (FVG'yi baslatan mumun govdesi; ust uste FVG
                varsa ustteki)  |  SUPURULEN_UC (ICT: supuren tepenin fitili)
  S5 TP       : 2R  |  3R  |  LIKIDITE (en yakin karsi likidite, en az 2R; yoksa islem yok)
  S6 SEVIYE   : EKIN (onceki gun, onceki hafta, Asya, Londra, onceki NY ogleden sonra, esit tepeler, 1S/4S FVG)
                ICT  (onceki gun, esit tepeler, 1S/4S/gunluk FVG)
  S7 ZAMAN    : EKIN_5_3 (kirilim 5 dk, FVG 5 dk; yoksa 3 dk)  |  ICT_15_5 (kirilim 15 dk, FVG 5 dk)
  S9 DISIPLIN : YOK  |  EKIN (sembolde: kazanan islemden sonra o gun bitti; seans basina tek islem)
  S11 EMIR    : SEANS_SONU (limit emir killzone bitene kadar)  |  2_SAAT
  S12 SHARP   : YOK  |  SART (supurmeye giderken yukari FVG birakmis olmali = U donusu)

CIKTI:  0_OZET.txt  (her sorunun her cevabi, en iyi genel mantik, %50 ustu semboller, 10.000 $, sonuc)
        1_mantiklar.csv  (5184 mantik x 2 donem)   2_sembol_secimi.csv   3_islemler.csv
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
KAPANIS = 23 * 60            # sunucu 23:00 = NY 16:00
SORULAR = [("S1_MSS", ["SART", "IFVG_YETER"]), ("S2_YON", ["YOK", "EKIN", "ICT"]),
           ("S3_GIRIS", ["ORTA", "KENAR", "KAPANIS"]), ("S4_STOP", ["SWING_GOVDE", "FVG_MUM", "SUPURULEN_UC"]),
           ("S5_TP", ["2R", "3R", "LIKIDITE"]), ("S6_SEVIYE", ["EKIN", "ICT"]), ("S7_ZAMAN", ["EKIN_5_3", "ICT_15_5"]),
           ("S9_DISIPLIN", ["YOK", "EKIN"]), ("S11_EMIR", ["SEANS_SONU", "2_SAAT"]), ("S12_SHARP", ["YOK", "SART"])]
SQ = [s for s, _ in SORULAR]
MANTIKLAR = list(itertools.product(*[range(len(v)) for _, v in SORULAR]))
MI = {m: i for i, m in enumerate(MANTIKLAR)}
NM = len(MANTIKLAR)
SONUC_KOD = {1: "TP", -1: "STOP", 0: "SURE"}
SAY = {"pencere": 0, "supurme": 0, "kirilim": 0, "kurulum": 0}
# alanlar: islem, TP, STOP, SURE, kazanan, dolar
ALAN = 6


def mad(m):
    return " ".join("%s=%s" % (SORULAR[i][0].split("_", 1)[1], SORULAR[i][1][v]) for i, v in enumerate(m))


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
def yonler(dO, dH, dL, dC):
    n = len(dC)
    ek = np.zeros(n, dtype=np.int8)
    ic = np.zeros(n, dtype=np.int8)
    for k in range(2, n):
        y, p = k - 1, k - 2
        if dC[y] > dH[p]:
            ek[k] = 1
        elif dC[y] < dL[p]:
            ek[k] = -1
        else:
            ust = dH[y] > dH[p]
            alt = dL[y] < dL[p]
            if ust and not alt:
                ek[k] = -1
            elif alt and not ust:
                ek[k] = 1
        bul, ber = False, False
        for c in range(max(2, k - 21), k - 1):
            a = c - 2
            if dH[a] < dL[c] and (c + 1 > k - 2 or dL[c + 1:k - 1].min() > dH[a]):
                if dL[y] <= dL[c] and dC[y] > dH[a]:
                    bul = True
            if dL[a] > dH[c] and (c + 1 > k - 2 or dH[c + 1:k - 1].max() < dL[a]):
                if dH[y] >= dH[c] and dC[y] < dL[a]:
                    ber = True
        ic[k] = 1 if (bul and not ber) else (-1 if (ber and not bul) else 0)
    return ek, ic


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
        gun = T // 1440
        self.gunler = np.unique(gun)
        g0 = np.searchsorted(T, self.gunler * 1440)
        g1 = np.searchsorted(T, self.gunler * 1440 + 1440)
        self.g0, self.g1 = g0, g1
        dO = self.O[g0]
        dC = self.C[g1 - 1]
        dH = np.maximum.reduceat(self.H, g0)
        dL = np.minimum.reduceat(self.L, g0)
        self.yon_ek, self.yon_ic = yonler(dO, dH, dL, dC)
        self.Y = {}
        SPx = self.SP
        for y in (-1, 1):
            if y < 0:
                Om, Hm, Lm, Cm = self.O, self.H, self.L, self.C
                F, X, Yt, Cx = self.H, self.H + SPx, self.L + SPx, self.C + SPx
                Em = self.O                       # piyasa satis: BID acilis
            else:
                Om, Hm, Lm, Cm = -self.O, -self.L, -self.H, -self.C
                F, X, Yt, Cx = -(self.L + SPx), -self.L, -self.H, -self.C
                Em = -(self.O + SPx)              # piyasa alis: ASK acilis
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
            b60 = B[60]
            a60 = atr(b60[2], b60[3], b60[4])
            h60, l60 = b60[2], b60[3]
            k1 = np.flatnonzero((h60[1:-1] > h60[:-2]) & (h60[1:-1] > h60[2:])) + 1
            d1 = np.flatnonzero((l60[1:-1] < l60[:-2]) & (l60[1:-1] < l60[2:])) + 1
            sw60t = (b60[0][k1 + 1] + 60, h60[k1], a60[k1])          # dogrulanma zamani, fiyat, atr
            sw60d = (b60[0][d1 + 1] + 60, l60[d1])
            fvg = {}
            for K in (60, 240, 1440):
                bt, bo, bh, bl, bc = B[K]
                q = np.flatnonzero(bl[:-2] > bh[2:])                     # ayna uzayinda ustteki (satis) FVG
                fvg[K] = (bt[q + 2] + K, bh[q + 2])
            b5 = B[5]
            bq = np.flatnonzero(b5[2][:-2] < b5[3][2:])                   # yukari (alis) FVG, 5 dk
            self.Y[y] = dict(Om=Om, Hm=Hm, Lm=Lm, Cm=Cm, F=F, X=X, Yt=Yt, Cx=Cx, Em=Em, B=B, sw=sw,
                             sw60t=sw60t, sw60d=sw60d, fvg=fvg, bul5=bq,
                             dH=np.maximum.reduceat(Hm, g0), dL=np.minimum.reduceat(Lm, g0))

    def ix(self, t):
        return int(np.searchsorted(self.T, t))

    def mx(self, arr, a, b):
        i, j = self.ix(a), self.ix(b)
        return arr[i:j].max() if j > i else -np.inf

    def mn(self, arr, a, b):
        i, j = self.ix(a), self.ix(b)
        return arr[i:j].min() if j > i else np.inf

    # ------------------------------------------------- seviyeler (S6) ve karsi likidite (TP)
    def seviyeler(self, y, k, ks, kzad):
        g = self.Y[y]
        Hm, Lm = g["Hm"], g["Lm"]
        D = int(self.gunler[k] * 1440)
        Dp = int(self.gunler[k - 1] * 1440)
        lv, karsi = [], []

        def ekle(fiyat, bitis, ad, fvg=False):
            if not np.isfinite(fiyat) or bitis > ks:
                return
            m = self.mx(Hm, bitis, ks)
            if (m < fiyat) if fvg else (m <= fiyat):
                lv.append((fiyat, ad, fvg))

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
        ct, cp, ca = g["sw60t"]
        sec = np.flatnonzero((ct <= ks) & (ct >= ks - 5 * 1440))
        for bi in range(1, len(sec)):
            for ai in range(max(0, bi - 8), bi):
                a, b = sec[ai], sec[bi]
                if abs(cp[a] - cp[b]) <= 0.1 * ca[b]:
                    ekle(max(cp[a], cp[b]), int(ct[b]), "ESIT_TEPE")
        dt, dp = g["sw60d"]
        for q in np.flatnonzero((dt <= ks) & (dt >= ks - 3 * 1440)):
            kekle(dp[q], int(dt[q]))
        for K, ad, gun in ((60, "FVG_1S", 5), (240, "FVG_4S", 5), (1440, "FVG_GUNLUK", 20)):
            ft, fp = g["fvg"][K]
            for q in np.flatnonzero((ft <= ks) & (ft >= ks - gun * 1440)):
                ekle(fp[q], int(ft[q]), ad, fvg=True)
        return lv, karsi

    # ------------------------------------------------- kurulumlar (S1, S6, S7 + S12/S2 etiketleri)
    def kurulumlar(self):
        out = {}
        EKIN_SEV = {"PDH", "PWH", "ASYA", "LONDRA", "NY_PM", "ESIT_TEPE", "FVG_1S", "FVG_4S"}
        ICT_SEV = {"PDH", "ESIT_TEPE", "FVG_1S", "FVG_4S", "FVG_GUNLUK"}
        if self.forex:
            pen = [(SUNUCU_NY * 60 + 120, SUNUCU_NY * 60 + 300, "LONDRA"), (SUNUCU_NY * 60 + 420, SUNUCU_NY * 60 + 600, "NY")]
        else:
            pen = [(SUNUCU_NY * 60 + 510, SUNUCU_NY * 60 + 660, "NY")]
        for s1 in range(2):
            for s6 in range(2):
                for s7 in range(2):
                    out[(s1, s6, s7)] = []
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
                    g = self.Y[y]
                    lv, karsi = self.seviyeler(y, k, ks, kzad)
                    if not lv:
                        continue
                    i0, i1 = self.ix(ks), self.ix(ke)
                    hz = g["Hm"][i0:i1]
                    vur = {}
                    for fiyat, ad, fvg in lv:
                        z = np.flatnonzero(hz >= fiyat) if fvg else np.flatnonzero(hz > fiyat)
                        if z.size:
                            vur.setdefault(ad, []).append((int(self.T[i0 + int(z[0])]), fiyat))
                    for s6, kume in ((0, EKIN_SEV), (1, ICT_SEV)):
                        ad_t = [(min(v)[0], ad, min(v)[1]) for ad, v in vur.items() if ad in kume]
                        if not ad_t:
                            continue
                        ts = min(x[0] for x in ad_t)
                        adlar = "+".join(sorted(x[1] for x in ad_t if x[0] == ts))
                        SAY["supurme"] += 1
                        for s7 in range(2):
                            for s1 in range(2):
                                x = self.kurulum(y, ts, ke, s1, s7)
                                if x is None:
                                    continue
                                x.update(y=y, k=k, D=D, kz=kzad, ks=ks, ke=ke, ts=ts, sev=adlar, karsi=karsi,
                                         yon_ek=int(self.yon_ek[k]), yon_ic=int(self.yon_ic[k]))
                                out[(s1, s6, s7)].append(x)
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
        tepe, p, ref, t_mss = -np.inf, -1, None, None
        for j in range(i, n):
            if bt[j] + Km > ke:
                break
            if bh[j] > tepe:
                tepe, p = bh[j], j
                q = sonsw[j]
                ref = bl[q] if q >= 0 else None
                continue
            if ref is not None and bc[j] < ref:
                t_mss = int(bt[j] + Km)
                break
        # IFVG: 5 dk'da supurmeye giderken olusan yukari FVG'nin tepe sonrasi govdeyle bozulmasi
        t5, o5, h5, l5, c5 = g["B"][5]
        bq = g["bul5"]
        j0 = int(np.searchsorted(t5, ts, side="right")) - 1
        aday = bq[(t5[bq] >= ts - 60) & (bq + 2 <= len(t5) - 1)]
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
            Td = min([x for x in (t_mss, t_ifvg) if x is not None], default=None)
        if Td is None:
            return None
        SAY["kirilim"] += 1
        a_, b_ = self.ix(ts), self.ix(Td)
        if b_ <= a_:
            return None
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
            return None
        zon.sort()
        alt, ust, govde, tur = zon[0]
        ustte = [z for z in zon[1:]]
        mum_stop = max([govde] + [z[2] for z in ustte])
        sharp = bool(np.any((t5[bq] >= ts - 60) & (bq + 2 <= k5)))
        return dict(Td=Td, tepe=tepe, tepe_govde=tepe_govde, alt=alt, ust=ust, mum_stop=mum_stop, tur=tur,
                    sharp=sharp, fiyat=fiyat, mss=ref)

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
    """bir mantigin sirali gecisi: alinan kurulumlarin sira numaralari"""
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


def sembol_isle(sb, ayrim, gun0, ngun, sec=None):
    """butun mantiklarin istatistigi: stat[NM, 2, ALAN], gunluk[NM, ngun]; sec verilirse o mantigin islemleri"""
    stat = np.zeros((NM, 2, ALAN), np.float32)
    gunluk = np.zeros((NM, ngun), np.float32)
    kur = sb.kurulumlar()
    islemler = {}
    for (s1, s6, s7), lst in kur.items():
        if not lst:
            continue
        arr = [sb.sonuclar(x) for x in lst]
        fill = np.array([a[0] for a in arr])
        bit = np.array([a[1] for a in arr])
        R = np.array([a[2] for a in arr])
        dl = np.array([a[3] for a in arr])
        kod = np.array([a[4] for a in arr])
        don = np.array([1 if x["Td"] >= ayrim else 0 for x in lst])
        gk = np.clip(bit // 1440 - gun0, 0, ngun - 1)
        son = (fill, bit, R, dl, kod)
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
                                    m = (s1, s2, gi, si, ti, s6, s7, s9, ei, s12)
                                    mi = MI[m]
                                    al = np.array(al)
                                    kd, rr, dd, dn = kod[al, kk], R[al, kk], dl[al, kk], don[al]
                                    for p in (0, 1):
                                        w = dn == p
                                        if w.any():
                                            stat[mi, p] += (w.sum(), (kd[w] == 1).sum(), (kd[w] == -1).sum(),
                                                            (kd[w] == 0).sum(), (rr[w] > 0).sum(), dd[w].sum())
                                    np.add.at(gunluk[mi], gk[al, kk], dd)
                                    if sec is not None and m in sec:
                                        islemler[m] = [(lst[i], kk, arr[i]) for i in al]
    return stat, gunluk, islemler


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
                sonuc=SONUC_KOD.get(int(kod), "?"), R=round(R, 3), dolar=round(d, 2))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ay", type=float, default=6.0)
    ap.add_argument("--kontrol_ay", type=float, default=2.0)
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
    bas = (simdi - timedelta(days=int(round(args.ay * 30.5)))).replace(hour=0, minute=0, second=0, microsecond=0)
    ayr = (simdi - timedelta(days=int(round(args.kontrol_ay * 30.5)))).replace(hour=0, minute=0, second=0, microsecond=0)
    bas_dk = int((bas - datetime(1970, 1, 1)).total_seconds() // 60)
    ayrim = int((ayr - datetime(1970, 1, 1)).total_seconds() // 60)
    gun0 = bas_dk // 1440
    ngun = int((simdi - bas).days) + 3
    ayrim_gun = ayrim // 1440 - gun0
    klasor = args.cikti or os.path.join(masaustu(), "ekin_tam_test_%s" % datetime.now().strftime("%Y%m%d_%H%M"))
    if not os.path.isdir(klasor):
        os.makedirs(klasor)
    yaz = dict(sep=";", decimal=",", index=False, encoding="utf-8-sig")
    print("Sembol: %d | %s -> bugun | SECIM < %s <= KONTROL | %d mantik | spread dahil, risk 15 $"
          % (len(semboller), bas.date(), ayr.date(), NM))
    print("Sonuclar: %s" % klasor)
    TOP = np.zeros((NM, 2, ALAN))
    GUN = np.zeros((NM, ngun))
    hepsi, secilen, yok, t0 = {}, [], [], time.time()

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

    for n_, s in enumerate(semboller, 1):
        try:
            sb = veri(s)
            if sb is None:
                yok.append(s); print("[%d/%d] %s : veri yok" % (n_, len(semboller), s)); continue
            stat, gunluk, _ = sembol_isle(sb, ayrim, gun0, ngun)
        except Exception as h:
            yok.append(s); print("[%d/%d] %s : hata %s" % (n_, len(semboller), s, h)); continue
        TOP += stat
        GUN += gunluk
        hepsi[s] = stat
        A = stat[:, 0]
        ok = np.flatnonzero(A[:, 0] >= 8)
        en = None
        if ok.size:
            b = ok[np.argmax(A[ok, 5])]
            if A[b, 5] > 0:
                en = b
                secilen.append((s, b, stat[b, 0].copy(), stat[b, 1].copy(), gunluk[b].copy()))
        print("[%d/%d] %s : en iyi (secim) %s -> SECIM %+.0f $ | KONTROL %+.0f $  (%.0f sn)" % (
            n_, len(semboller), s, mad(MANTIKLAR[en]) if en is not None else "-",
            stat[en, 0, 5] if en is not None else 0, stat[en, 1, 5] if en is not None else 0, time.time() - t0))
    if not hepsi:
        mt5.shutdown()
        sys.exit("Hic sonuc yok.")
    # ------------------------------------------------- genel en iyi (SECIM'de), %50 ustu semboller -> islemleri yeniden al
    huni = dict(SAY)
    A, B = TOP[:, 0], TOP[:, 1]
    sira = np.argsort(-A[:, 5])
    gen = int(sira[0])
    gen_m = MANTIKLAR[gen]
    yuzde50 = []
    for s, stt in hepsi.items():
        a, b = stt[gen, 0], stt[gen, 1]
        if a[0] >= 5 and b[0] >= 2 and a[4] / a[0] > 0.5 and b[4] / b[0] > 0.5:
            yuzde50.append(s)
    kartlar, g50 = [], np.zeros(ngun)
    sec_ms = {s: MANTIKLAR[b] for s, b, _, _, _ in secilen}
    sag = [x for x in secilen if x[3][0] >= 3 and x[3][5] > 0]
    gerek = set(yuzde50) | set(x[0] for x in sag)
    print("\nIslem kartlari icin %d sembol yeniden okunuyor..." % len(gerek))
    for s in sorted(gerek):
        try:
            sb = veri(s)
            ist = {gen_m}
            if s in sec_ms:
                ist.add(sec_ms[s])
            _, _, isl = sembol_isle(sb, ayrim, gun0, ngun, sec=ist)
        except Exception as h:
            print("   %s : hata %s" % (s, h)); continue
        for m, lst in isl.items():
            for x, kk, a in lst:
                c = kart(s, m, x, kk, a)
                c["liste"] = ("GENEL_%50" if (m == gen_m and s in yuzde50) else "") + (
                    " SEMBOL_KENDI" if sec_ms.get(s) == m else "")
                kartlar.append(c)
                if m == gen_m and s in yuzde50:
                    k = int(a[1][kk]) // 1440 - gun0
                    if 0 <= k < ngun:
                        g50[k] += a[3][kk]
    mt5.shutdown()
    if kartlar:
        pd.DataFrame(kartlar).to_csv(os.path.join(klasor, "3_islemler.csv"), **yaz)
    rows = []
    for i, m in enumerate(MANTIKLAR):
        r = dict(zip(SQ, [SORULAR[q][1][v] for q, v in enumerate(m)]))
        for p, ad in ((0, "SECIM"), (1, "KONTROL")):
            o = ozet(TOP[i, p])
            r.update({"%s_%s" % (ad, k): v for k, v in o.items()})
        rows.append(r)
    pd.DataFrame(rows).to_csv(os.path.join(klasor, "1_mantiklar.csv"), **yaz)
    pd.DataFrame([dict(sembol=s, mantik=mad(MANTIKLAR[b]), **{"SECIM_" + k: v for k, v in ozet(a).items()},
                       **{"KONTROL_" + k: v for k, v in ozet(bb).items()}) for s, b, a, bb, _ in secilen]
                 ).to_csv(os.path.join(klasor, "2_sembol_secimi.csv"), **yaz)

    c = "=" * 150
    bsl = "%-100s || SECIM: %5s %4s %5s %4s %6s %10s || KONTROL: %5s %4s %5s %4s %6s %10s" % (
        "MANTIK", "ISLEM", "TP", "STOP", "SURE", "BASARI", "DOLAR", "ISLEM", "TP", "STOP", "SURE", "BASARI", "DOLAR")
    m = [c, "EKIN MODELI TAM TEST | %s -> bugun | %d sembol | %d mantik | SPREAD DAHIL | risk 15 $"
         % (bas.date(), len(hepsi), NM),
         "SECIM: %s - %s (en iyi burada secildi)  |  KONTROL: %s - bugun (secilen mantik bu donemi HIC gormedi)"
         % (bas.date(), (ayr - timedelta(days=1)).date(), ayr.date()), "SAAT: " + saat_notu,
         "HUNI: killzone penceresi %d | supurme %d | kirilim %d | kurulum %d" % (
             huni["pencere"], huni["supurme"], huni["kirilim"], huni["kurulum"]), c]
    m += ["", "1) HER SORUNUN HER CEVABI (o cevabi iceren butun mantiklarin toplami, butun semboller)",
          "%-14s %-14s || SECIM: %7s %6s %12s || KONTROL: %7s %6s %12s" % ("SORU", "CEVAP", "ISLEM", "BAS.", "DOLAR",
                                                                         "ISLEM", "BAS.", "DOLAR")]
    MA = np.array(MANTIKLAR)
    for q, (sq, cev) in enumerate(SORULAR):
        par = []
        for v, ad in enumerate(cev):
            w = MA[:, q] == v
            a, b = A[w].sum(0), B[w].sum(0)
            par.append((a[5] + b[5], ad, a, b))
        par.sort(key=lambda z: -z[0])
        for j, (_, ad, a, b) in enumerate(par):
            m.append("%-14s %-14s || SECIM: %7d %%%5.1f %+12.2f || KONTROL: %7d %%%5.1f %+12.2f%s" % (
                sq if j == 0 else "", ad, a[0], 100.0 * a[4] / max(1, a[0]), a[5], b[0], 100.0 * b[4] / max(1, b[0]),
                b[5], "   <- en iyi" if j == 0 else ""))
    m += ["", c, "2) BUTUN SEMBOLLERDE TEK MANTIK: SECIM'de en iyi 15 (yaninda KONTROL)", c, bsl]
    for i in sira[:15]:
        m.append("%-100s || SECIM: %s || KONTROL: %s" % (mad(MANTIKLAR[i]), st(A[i]), st(B[i])))
    iki = [i for i in range(NM) if A[i, 5] > 0 and B[i, 5] > 0 and A[i, 0] >= 20]
    iki.sort(key=lambda i: -min(A[i, 5], B[i, 5] * 2))
    m += ["", "-- IKI DONEMDE DE KARLI tek mantiklar: %d tane (ilk 10) --" % len(iki), bsl]
    for i in iki[:10]:
        m.append("%-100s || SECIM: %s || KONTROL: %s" % (mad(MANTIKLAR[i]), st(A[i]), st(B[i])))
    m += ["", "EN IYI GENEL MANTIK (SECIM'e gore): " + mad(gen_m),
          "   butun semboller, 6 ay    : " + hesap(GUN[gen]),
          "   butun semboller, KONTROL : " + hesap(np.where(np.arange(ngun) >= ayrim_gun, GUN[gen], 0.0))]
    m += ["", "-- BU MANTIKTA IKI DONEMDE DE BASARISI %%50 USTU SEMBOLLER (secim >= 5, kontrol >= 2 islem): %d --" % len(yuzde50),
          "%-14s || SECIM: %5s %4s %5s %4s %6s %10s || KONTROL: %5s %4s %5s %4s %6s %10s" % (
              "SEMBOL", "ISLEM", "TP", "STOP", "SURE", "BASARI", "DOLAR", "ISLEM", "TP", "STOP", "SURE", "BASARI", "DOLAR")]
    for s in sorted(yuzde50, key=lambda z: -(hepsi[z][gen, 0, 5] + hepsi[z][gen, 1, 5])):
        m.append("%-14s || SECIM: %s || KONTROL: %s" % (s, st(hepsi[s][gen, 0]), st(hepsi[s][gen, 1])))
    if yuzde50:
        m.append("Sadece bu semboller kullanilsaydi, 6 ay, 10.000 $: " + hesap(g50))
        m.append("   KONTROL donemi            : " + hesap(np.where(np.arange(ngun) >= ayrim_gun, g50, 0.0)))
    # her sembol kendi mantigi
    m += ["", c, "3) HER SEMBOL KENDI EN IYI MANTIGI (SECIM'de secildi, en az 8 islem) -> KONTROL'de ne yapti?", c]
    tum_b = sum(float(x[3][5]) for x in secilen)
    m.append("Secilen sembol %d | KONTROL'de de karli (en az 3 islem) = SAGLAM %d | secilenlerin KONTROL toplami %+.2f $  "
             "<- en durust sayi" % (len(secilen), len(sag), tum_b))
    m.append("%-14s %-100s || SECIM: %5s %4s %5s %4s %6s %10s || KONTROL: %5s %4s %5s %4s %6s %10s" % (
        "SEMBOL", "MANTIK", "ISLEM", "TP", "STOP", "SURE", "BASARI", "DOLAR", "ISLEM", "TP", "STOP", "SURE", "BASARI", "DOLAR"))
    gs6, gsk = np.zeros(ngun), np.zeros(ngun)
    for s, b, a, bb, gg in sorted(sag, key=lambda z: -z[3][5]):
        isa = "  <- iki donemde %50 ustu" if a[4] / max(1, a[0]) > 0.5 and bb[4] / max(1, bb[0]) > 0.5 else ""
        m.append("%-14s %-100s || SECIM: %s || KONTROL: %s%s" % (s, mad(MANTIKLAR[b]), st(a), st(bb), isa))
        gs6 += gg
        gsk += np.where(np.arange(ngun) >= ayrim_gun, gg, 0.0)
    if sag:
        m.append("SAGLAM semboller kendi mantiklariyla, 6 ay, 10.000 $: " + hesap(gs6))
        m.append("   KONTROL donemi                                 : " + hesap(gsk))
    # sonuc
    gen_b = float(B[gen, 5])
    m += ["", c, "4) SONUC", c,
          "Tek mantik (en iyi genel) KONTROL'de : %+.2f $" % gen_b,
          "Her sembol kendi mantigi KONTROL'de  : %+.2f $" % tum_b,
          "Hangisi KONTROL'de daha iyiyse o yontem daha guvenilir.  Her sorunun en iyi cevabi 1. bolumde.",
          "Robota sadece IKI DONEMDE DE kar eden mantik / semboller aday olur; sadece SECIM'de iyi olan buyuk ihtimalle sanstir."]
    if yok:
        m += ["", "Verisi olmayan: " + ", ".join(yok)]
    ms = "\n".join(m)
    print("\n" + ms)
    with open(os.path.join(klasor, "0_OZET.txt"), "w", encoding="utf-8") as fh:
        fh.write(ms + "\n")
    print("\nDosyalar: %s" % os.path.abspath(klasor))


if __name__ == "__main__":
    main()
