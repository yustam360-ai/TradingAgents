# -*- coding: utf-8 -*-
"""
TRADINGVIEW'IN EN POPULER 14 GOSTERGESI - BUTUN SEMBOLLER - 2026 (OCAK -> BUGUN) - DURUST TEST
================================================================================================
Python 3.8:   py -3.8 gosterge_tarama_2026.py
Gerekli:      py -3.8 -m pip install MetaTrader5 pandas numpy
Sadece bazi semboller:   py -3.8 gosterge_tarama_2026.py --sembol EURUSD,XAUUSD
TEK DOSYA. MT5'e baglanir, SADECE gecmis veri okur, ISLEM ACMAZ.  Uzun surer (sembol basina ~10-20 sn).

NEDEN "DURUST": Onceki testlerde ayni donemde hem secip hem olctuk, sonuc sisik cikti.  Burada:
  SECIM  donemi : 1 Ocak - 31 Temmuz 2026   -> en iyi mantik BURADA secilir
  KONTROL donemi: 1 Agustos - bugun          -> secilen mantik HIC GORMEDIGI bu donemde olculur
  Raporda "SAGLAM" = secim doneminde secilmis VE kontrol doneminde de kar etmis.

14 GOSTERGE (TradingView'daki standart ayarlariyla; sinyal mum KAPANISINDA, giris sonraki mumun acilisinda)
   1 EMA_9_21     : EMA 9, EMA 21'i yukari keser = AL, asagi = SAT
   2 MACD         : MACD (12,26,9) cizgisi sinyal cizgisini keser
   3 RSI_30_70    : RSI 14, 30'un altindan yukari doner = AL, 70'in ustunden asagi = SAT
   4 SUPERTREND   : Supertrend (10, 3) renk degistirir
   5 UT_BOT       : UT Bot Alerts (anahtar 1, ATR 10) al/sat
   6 BOLLINGER    : Bollinger (20, 2) alt bandin disindan iceri kapanis = AL, ust banttan = SAT
   7 DONCHIAN_20  : 20 mumun tepesinin ustunde kapanis = AL, dibinin altinda = SAT (Turtle)
   8 STOCH_RSI    : Stoch RSI (3,3,14,14) K, D'yi 20'nin altinda yukari keser = AL, 80 ustunde asagi = SAT
   9 PSAR         : Parabolic SAR (0.02, 0.2) yon degistirir
  10 HULL_55      : Hull MA 55 yukari doner = AL, asagi doner = SAT
  11 ICHIMOKU     : Tenkan Kijun'u keser, fiyat bulutun ustunde = AL (altinda = SAT)
  12 SQUEEZE      : Squeeze Momentum (LazyBear 20, 2, 1.5) sikisma biter, momentum yonunde
  13 SSL_10       : SSL Channel 10 yon degistirir
  14 ADX_DI       : +DI, -DI'yi keser ve ADX > 20

SECENEKLER (her gosterge icin 24): ZAMAN DILIMI 15 dk / 1 saat / 4 saat  x  FILTRE YOK / EMA200 (sadece EMA 200
yonunde)  x  STOP 1.5 ATR / 2.5 ATR  x  TP 2R / 3R.   Toplam 14 x 24 = 336 mantik, her sembolde.

GERCEKCI KURALLAR: risk 15 $ / islem, spread dahil (MT5 5 dk mum spread'i; AL ASK'tan, SAT BID'den),
  spread maliyeti 6 $'i gecen islem acilmaz, en kucuk lotta zarar 30 $'i gecerse acilmaz,
  boslukla (gap) stopun otesinde acilirsa o fiyattan cikar, ayni mumda stop ve TP = STOP,
  sembol + mantik basina ayni anda tek islem, islem en fazla 5 gun acik kalir.

CIKTI (gosterge_test_<tarih>/):
  0_OZET.txt        en iyi genel mantiklar, gosterge ligi, SAGLAM semboller, 10.000 $, en altta sonuc
  1_mantiklar.csv   336 mantik x 2 donem (butun semboller toplami)
  2_sembol.csv      mantik x sembol x donem
  3_saglam_islemler.csv  SAGLAM sembollerin butun islemleri (TR saati, giris, stop, TP, sonuc)
"""
from __future__ import print_function

import argparse
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
EN_UZUN = 5 * 1440                    # islem en fazla 5 gun
GOSTERGELER = ["EMA_9_21", "MACD", "RSI_30_70", "SUPERTREND", "UT_BOT", "BOLLINGER", "DONCHIAN_20", "STOCH_RSI",
               "PSAR", "HULL_55", "ICHIMOKU", "SQUEEZE", "SSL_10", "ADX_DI"]
TFLER = (15, 60, 240)
FILTRELER = ("YOK", "EMA200")
STOPLAR = (1.5, 2.5)
HEDEFLER = (2, 3)
MANTIKLAR = [(g, tf, f, s, h) for g in GOSTERGELER for tf in TFLER for f in FILTRELER for s in STOPLAR for h in HEDEFLER]


def mad(m):
    g, tf, f, s, h = m
    return "%s %s %s STOP=%.1fATR TP=%dR" % (g, {15: "15DK", 60: "1S", 240: "4S"}[tf], "FILTRE=" + f, s, h)


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


# ----------------------------------------------------------------- gostergeler (TradingView formulleri)
def ema(x, n):
    return pd.Series(x).ewm(span=n, adjust=False).mean().to_numpy()


def rma(x, n):
    return pd.Series(x).ewm(alpha=1.0 / n, adjust=False).mean().to_numpy()


def sma(x, n):
    return pd.Series(x).rolling(n, min_periods=n).mean().to_numpy()


def wma(x, n):
    w = np.arange(1, n + 1, dtype=float)
    return pd.Series(x).rolling(n, min_periods=n).apply(lambda a: np.dot(a, w) / w.sum(), raw=True).to_numpy()


def tr_(h, l, c):
    pc = np.r_[c[0], c[:-1]]
    return np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))


def atr(h, l, c, n):
    return rma(tr_(h, l, c), n)


def cross(a, b):
    """a, b'yi yukari keser: +1, asagi: -1"""
    s = np.zeros(len(a), dtype=np.int8)
    d = a - b
    p = np.r_[np.nan, d[:-1]]
    s[(p <= 0) & (d > 0)] = 1
    s[(p >= 0) & (d < 0)] = -1
    return s


def degisim(yon):
    s = np.zeros(len(yon), dtype=np.int8)
    p = np.r_[0, yon[:-1]]
    s[(yon == 1) & (p == -1)] = 1
    s[(yon == -1) & (p == 1)] = -1
    return s


def supertrend(h, l, c, n=10, m=3.0):
    a = atr(h, l, c, n)
    hl2 = (h + l) / 2
    ub, lb = hl2 + m * a, hl2 - m * a
    yon = np.ones(len(c), dtype=np.int8)
    fu, fl = ub.copy(), lb.copy()
    for i in range(1, len(c)):
        fl[i] = lb[i] if (lb[i] > fl[i - 1] or c[i - 1] < fl[i - 1]) else fl[i - 1]
        fu[i] = ub[i] if (ub[i] < fu[i - 1] or c[i - 1] > fu[i - 1]) else fu[i - 1]
        if yon[i - 1] == -1:
            yon[i] = 1 if c[i] > fu[i - 1] else -1
        else:
            yon[i] = -1 if c[i] < fl[i - 1] else 1
    return degisim(yon)


def ut_bot(h, l, c, key=1.0, n=10):
    nl = key * atr(h, l, c, n)
    ts = np.zeros(len(c))
    ts[0] = c[0]
    for i in range(1, len(c)):
        p = ts[i - 1]
        if c[i] > p and c[i - 1] > p:
            ts[i] = max(p, c[i] - nl[i])
        elif c[i] < p and c[i - 1] < p:
            ts[i] = min(p, c[i] + nl[i])
        elif c[i] > p:
            ts[i] = c[i] - nl[i]
        else:
            ts[i] = c[i] + nl[i]
    return cross(c, ts)


def psar(h, l, af0=0.02, step=0.02, mx=0.2):
    n = len(h)
    yon = np.ones(n, dtype=np.int8)
    sar, ep, af = l[0], h[0], af0
    for i in range(1, n):
        sar = sar + af * (ep - sar)
        if yon[i - 1] == 1:
            sar = min(sar, l[i - 1], l[i - 2] if i > 1 else l[i - 1])
            if l[i] < sar:
                yon[i], sar, ep, af = -1, ep, l[i], af0
            else:
                yon[i] = 1
                if h[i] > ep:
                    ep, af = h[i], min(af + step, mx)
        else:
            sar = max(sar, h[i - 1], h[i - 2] if i > 1 else h[i - 1])
            if h[i] > sar:
                yon[i], sar, ep, af = 1, ep, h[i], af0
            else:
                yon[i] = -1
                if l[i] < ep:
                    ep, af = l[i], min(af + step, mx)
    return degisim(yon)


def rsi(c, n=14):
    d = np.diff(c, prepend=c[0])
    up, dn = rma(np.maximum(d, 0), n), rma(np.maximum(-d, 0), n)
    with np.errstate(divide="ignore", invalid="ignore"):
        r = 100 - 100 / (1 + up / dn)
    return np.where(dn == 0, 100.0, r)


def linreg_son(y, n):
    """ta.linreg(y, n, 0): son noktadaki dogrusal regresyon degeri"""
    x = np.arange(n, dtype=float)
    sx, sxx = x.sum(), (x * x).sum()
    yy = np.nan_to_num(y)
    sy = pd.Series(yy).rolling(n, min_periods=n).sum().to_numpy()
    sxy = np.full(len(y), np.nan)
    if len(y) >= n:
        sxy[n - 1:] = np.convolve(yy, x[::-1], mode="valid")
    b = (n * sxy - sx * sy) / (n * sxx - sx * sx)
    a = (sy - b * sx) / n
    return a + b * (n - 1)


def sinyaller(o, h, l, c):
    """her gosterge icin +1 / -1 / 0 dizisi (mum kapanisinda)"""
    S = {}
    S["EMA_9_21"] = cross(ema(c, 9), ema(c, 21))
    m = ema(c, 12) - ema(c, 26)
    S["MACD"] = cross(m, ema(m, 9))
    r = rsi(c, 14)
    rp = np.r_[50, r[:-1]]
    x = np.zeros(len(c), dtype=np.int8)
    x[(rp < 30) & (r >= 30)] = 1
    x[(rp > 70) & (r <= 70)] = -1
    S["RSI_30_70"] = x
    S["SUPERTREND"] = supertrend(h, l, c)
    S["UT_BOT"] = ut_bot(h, l, c)
    orta = sma(c, 20)
    sd = pd.Series(c).rolling(20, min_periods=20).std(ddof=0).to_numpy()
    ust, alt = orta + 2 * sd, orta - 2 * sd
    cp = np.r_[np.nan, c[:-1]]
    x = np.zeros(len(c), dtype=np.int8)
    x[(cp < np.r_[np.nan, alt[:-1]]) & (c > alt)] = 1
    x[(cp > np.r_[np.nan, ust[:-1]]) & (c < ust)] = -1
    S["BOLLINGER"] = x
    hh = pd.Series(h).rolling(20, min_periods=20).max().shift(1).to_numpy()
    ll = pd.Series(l).rolling(20, min_periods=20).min().shift(1).to_numpy()
    yon = np.where(c > hh, 1, np.where(c < ll, -1, 0)).astype(np.int8)
    yp = np.r_[0, yon[:-1]]
    x = np.zeros(len(c), dtype=np.int8)
    x[(yon == 1) & (yp != 1)] = 1
    x[(yon == -1) & (yp != -1)] = -1
    S["DONCHIAN_20"] = x
    lo = pd.Series(r).rolling(14, min_periods=14).min().to_numpy()
    hi = pd.Series(r).rolling(14, min_periods=14).max().to_numpy()
    with np.errstate(divide="ignore", invalid="ignore"):
        st = np.where(hi - lo > 0, 100 * (r - lo) / (hi - lo), 50.0)
    k = sma(st, 3)
    d = sma(k, 3)
    cr = cross(k, d)
    x = np.zeros(len(c), dtype=np.int8)
    x[(cr == 1) & (k < 20)] = 1
    x[(cr == -1) & (k > 80)] = -1
    S["STOCH_RSI"] = x
    S["PSAR"] = psar(h, l)
    hull = wma(2 * wma(c, 27) - wma(c, 55), 7)
    dh = np.diff(hull, prepend=np.nan)
    yon = np.where(dh > 0, 1, np.where(dh < 0, -1, 0)).astype(np.int8)
    S["HULL_55"] = degisim(yon)
    ten = (pd.Series(h).rolling(9).max() + pd.Series(l).rolling(9).min()).to_numpy() / 2
    kij = (pd.Series(h).rolling(26).max() + pd.Series(l).rolling(26).min()).to_numpy() / 2
    sa = pd.Series((ten + kij) / 2).shift(25).to_numpy()
    sb = pd.Series((pd.Series(h).rolling(52).max() + pd.Series(l).rolling(52).min()).to_numpy() / 2).shift(25).to_numpy()
    cr = cross(ten, kij)
    x = np.zeros(len(c), dtype=np.int8)
    x[(cr == 1) & (c > np.fmax(sa, sb))] = 1
    x[(cr == -1) & (c < np.fmin(sa, sb))] = -1
    S["ICHIMOKU"] = x
    a20 = sma(tr_(h, l, c), 20)
    bb_u, bb_l = ust, alt                                  # LazyBear: BB 20, 2  /  KC 20, 1.5 (TR ortalamasi)
    kc_u, kc_l = orta + 1.5 * a20, orta - 1.5 * a20
    sqz = (bb_l > kc_l) & (bb_u < kc_u)
    hh20 = pd.Series(h).rolling(20, min_periods=20).max().to_numpy()
    ll20 = pd.Series(l).rolling(20, min_periods=20).min().to_numpy()
    val = linreg_son(c - ((hh20 + ll20) / 2 + orta) / 2, 20)
    bit = np.r_[False, sqz[:-1]] & ~sqz
    x = np.zeros(len(c), dtype=np.int8)
    x[bit & (val > 0)] = 1
    x[bit & (val < 0)] = -1
    S["SQUEEZE"] = x
    smh, sml = sma(h, 10), sma(l, 10)
    hlv = np.zeros(len(c), dtype=np.int8)
    for i in range(1, len(c)):
        hlv[i] = 1 if c[i] > smh[i] else (-1 if c[i] < sml[i] else hlv[i - 1])
    S["SSL_10"] = degisim(hlv)
    up = np.diff(h, prepend=h[0])
    dn = -np.diff(l, prepend=l[0])
    pdm = np.where((up > dn) & (up > 0), up, 0.0)
    mdm = np.where((dn > up) & (dn > 0), dn, 0.0)
    a14 = rma(tr_(h, l, c), 14)
    with np.errstate(divide="ignore", invalid="ignore"):
        pdi = 100 * rma(pdm, 14) / a14
        mdi = 100 * rma(mdm, 14) / a14
        dx = 100 * np.abs(pdi - mdi) / (pdi + mdi)
    adx = rma(np.nan_to_num(dx), 14)
    cr = cross(pdi, mdi)
    S["ADX_DI"] = np.where(adx > 20, cr, 0).astype(np.int8)
    return S


# ----------------------------------------------------------------- bir sembol
def sembol_isle(s, m5, bilgi, vpl, bas_dk, ayrim_dk, gun0, ngun):
    T = m5["time"].to_numpy(np.int64) // 60
    O, H, L, C = [m5[k].to_numpy(float) for k in ("open", "high", "low", "close")]
    SP = m5["spread"].to_numpy(float) * float(bilgi.point)
    adim = bilgi.volume_step if bilgi.volume_step > 0 else 0.01
    vmax = bilgi.volume_max if bilgi.volume_max > 0 else 1e9
    son = int(T[-1])
    HA, LA, CA = H + SP, L + SP, C + SP            # ASK
    sonuc = {}
    for tf in TFLER:
        bt, bo, bh, bl, bc = mumlar(T, O, H, L, C, tf)
        if len(bt) < 300:
            continue
        S = sinyaller(bo, bh, bl, bc)
        a14 = atr(bh, bl, bc, 14)
        e200 = ema(bc, 200)
        gir = np.searchsorted(T, bt + tf)              # sinyal mumunun bitisinden sonraki ilk 5 dk mum
        for g in GOSTERGELER:
            sg = S[g]
            for f in FILTRELER:
                idx = np.flatnonzero(sg != 0)
                if f == "EMA200":
                    idx = idx[((sg[idx] == 1) & (bc[idx] > e200[idx])) | ((sg[idx] == -1) & (bc[idx] < e200[idx]))]
                idx = idx[(idx >= 200) & (bt[idx] + tf >= bas_dk) & (gir[idx] < len(T))]
                for sm in STOPLAR:
                    for hk in HEDEFLER:
                        isl, mesgul = [], -1
                        for i in idx:
                            e = int(gir[i])
                            if T[e] < mesgul or T[e] - (bt[i] + tf) > 3 * 1440:
                                continue
                            y = int(sg[i])
                            d = sm * a14[i]
                            if not (d > 0):
                                continue
                            sp = SP[e]
                            lot = np.floor(RISK / (d * vpl) / adim + 1e-9) * adim
                            if lot < bilgi.volume_min:
                                lot = bilgi.volume_min
                            lot = min(lot, vmax)
                            zarar = lot * d * vpl
                            if zarar > EN_FAZLA + 1e-9 or sp * lot * vpl > MAKAS_SINIR + 1e-9:
                                continue
                            z = int(np.searchsorted(T, T[e] + EN_UZUN))
                            if z <= e:
                                continue
                            if y == 1:
                                E = O[e] + sp
                                Sx, TPx = E - d, E + hk * d
                                st = np.flatnonzero(L[e:z] <= Sx)
                                tp = np.flatnonzero(H[e:z] >= TPx)
                            else:
                                E = O[e]
                                Sx, TPx = E + d, E - hk * d
                                st = np.flatnonzero(HA[e:z] >= Sx)
                                tp = np.flatnonzero(LA[e:z] <= TPx)
                            s0 = int(st[0]) if st.size else None
                            h0 = int(tp[0]) if tp.size else None
                            if s0 is not None and (h0 is None or s0 <= h0):
                                x = e + s0
                                cik = min(Sx, O[x]) if y == 1 else max(Sx, O[x] + SP[x])
                                R, so = (cik - E) / d * y, "STOP"
                            elif h0 is not None:
                                x = e + h0
                                R, so = float(hk), "TP"
                            else:
                                x = z - 1
                                if T[x] + 5 > son - 5:
                                    break                  # henuz bitmemis islem: sayma
                                cik = C[x] if y == 1 else CA[x]
                                R, so = (cik - E) / d * y, "SURE"
                            cik_dk = int(T[x]) + 5
                            mesgul = cik_dk
                            isl.append((int(T[e]), cik_dk, y, E, Sx, TPx, so, R, R * zarar, lot))
                        sonuc[(g, tf, f, sm, hk)] = isl
    return sonuc


def ozet(isl):
    n = len(isl)
    if not n:
        return dict(islem=0, TP=0, STOP=0, SURE=0, basari=0.0, dolar=0.0)
    so = [x[6] for x in isl]
    return dict(islem=n, TP=so.count("TP"), STOP=so.count("STOP"), SURE=so.count("SURE"),
                basari=round(100.0 * sum(1 for x in isl if x[7] > 0) / n, 1), dolar=round(sum(x[8] for x in isl), 2))


def hesap_gunluk(g):
    """g: gunluk kar/zarar dizisi"""
    if not np.any(g):
        return "islem yok"
    bak = BASLANGIC + np.cumsum(g)
    tepe = np.maximum.accumulate(np.r_[BASLANGIC, bak])[1:]
    a = g[g != 0]
    return ("10.000 $ -> %.2f $ (net %+.2f $) | en kotu gun %+.2f $ | en iyi gun %+.2f $ | en buyuk dusus %+.2f $ | "
            "250 $ ustu zarar gunu %d" % (bak[-1], bak[-1] - BASLANGIC, a.min(), a.max(), (bak - tepe).min(), int((g < -250).sum())))


def st(o):
    return "%5d %4d %5d %4d %%%5.1f %+10.2f" % (o["islem"], o["TP"], o["STOP"], o["SURE"], o["basari"], o["dolar"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bas", default="2026-01-01")
    ap.add_argument("--ayrim", default="2026-08-01")
    ap.add_argument("--sembol", default="")
    ap.add_argument("--cikti", default="")
    args = ap.parse_args()
    if mt5 is None:
        sys.exit("MetaTrader5 modulu yok:  py -3.8 -m pip install MetaTrader5")
    if not mt5.initialize():
        sys.exit("MT5 baglantisi kurulamadi: %s" % (mt5.last_error(),))
    semboller = ([x.strip() for x in args.sembol.split(",") if x.strip()] if args.sembol
                 else [x.name for x in (mt5.symbols_get() or [])])
    bas = datetime.strptime(args.bas, "%Y-%m-%d")
    ayrim = datetime.strptime(args.ayrim, "%Y-%m-%d")
    bas_dk = int((bas - datetime(1970, 1, 1)).total_seconds() // 60)
    ayrim_dk = int((ayrim - datetime(1970, 1, 1)).total_seconds() // 60)
    simdi = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=sunucu_utc(datetime.now(timezone.utc).date()))
    gun0 = bas_dk // 1440
    ngun = int((simdi - bas).days) + 3
    ayrim_gun = ayrim_dk // 1440 - gun0
    klasor = args.cikti or ("gosterge_test_%s" % datetime.now().strftime("%Y%m%d_%H%M"))
    if not os.path.isdir(klasor):
        os.makedirs(klasor)
    yaz = dict(sep=";", decimal=",", index=False, encoding="utf-8-sig")
    print("Sembol: %d | %s -> bugun | SECIM < %s <= KONTROL | %d mantik | spread dahil, risk 15 $"
          % (len(semboller), args.bas, args.ayrim, len(MANTIKLAR)))
    satirlar, gunluk, secilen, yok, t0 = [], {m: np.zeros(ngun) for m in MANTIKLAR}, [], [], time.time()
    for n_, s in enumerate(semboller, 1):
        try:
            if not mt5.symbol_select(s, True):
                yok.append(s); continue
            bilgi = mt5.symbol_info(s)
            vpl = deger_lot(s, bilgi) if bilgi is not None else None
            m5 = cek(s, mt5.TIMEFRAME_M5, bas - timedelta(days=75), simdi + timedelta(days=1), 30)
            if bilgi is None or not vpl or m5 is None or len(m5) < 5000:
                yok.append(s); print("[%d/%d] %s : veri yok" % (n_, len(semboller), s)); continue
            sonuc = sembol_isle(s, m5, bilgi, vpl, bas_dk, ayrim_dk, gun0, ngun)
        except Exception as h:
            yok.append(s); print("[%d/%d] %s : hata %s" % (n_, len(semboller), s, h)); continue
        en_iyi = None
        for m, isl in sonuc.items():
            A = [x for x in isl if x[0] < ayrim_dk]
            B = [x for x in isl if x[0] >= ayrim_dk]
            oa, ob = ozet(A), ozet(B)
            satirlar.append(dict(mantik=mad(m), gosterge=m[0], sembol=s, donem="SECIM", **oa))
            satirlar.append(dict(mantik=mad(m), gosterge=m[0], sembol=s, donem="KONTROL", **ob))
            for x in isl:
                k = x[1] // 1440 - gun0
                if 0 <= k < ngun:
                    gunluk[m][k] += x[8]
            if oa["islem"] >= 10 and oa["dolar"] > 0 and (en_iyi is None or oa["dolar"] > en_iyi[0]):
                en_iyi = (oa["dolar"], m, oa, ob, isl)
        if en_iyi is not None:
            secilen.append((s,) + en_iyi[1:])
        print("[%d/%d] %s : en iyi (secim donemi) %s -> SECIM %+.0f $ | KONTROL %+.0f $  (%.0f sn)" % (
            n_, len(semboller), s, mad(en_iyi[1]) if en_iyi else "-", en_iyi[2]["dolar"] if en_iyi else 0,
            en_iyi[3]["dolar"] if en_iyi else 0, time.time() - t0))
    mt5.shutdown()
    if not satirlar:
        sys.exit("Hic sonuc yok.")
    sb = pd.DataFrame(satirlar)
    sb.to_csv(os.path.join(klasor, "2_sembol.csv"), **yaz)
    gm = sb.groupby(["mantik", "gosterge", "donem"])[["islem", "TP", "STOP", "SURE", "dolar"]].sum().reset_index()
    kaz = sb.assign(kaz=sb["basari"] * sb["islem"] / 100.0).groupby(["mantik", "donem"])["kaz"].sum()
    gm["basari"] = [round(100.0 * kaz[(a, b)] / i, 1) if i else 0.0 for a, b, i in zip(gm["mantik"], gm["donem"], gm["islem"])]
    gm.to_csv(os.path.join(klasor, "1_mantiklar.csv"), **yaz)
    A = gm[gm["donem"] == "SECIM"].set_index("mantik")
    B = gm[gm["donem"] == "KONTROL"].set_index("mantik")

    def o_(t, k):
        r = t.loc[k]
        return dict(islem=int(r["islem"]), TP=int(r["TP"]), STOP=int(r["STOP"]), SURE=int(r["SURE"]), basari=r["basari"], dolar=r["dolar"])

    c = "=" * 140
    bsl = "%-46s || SECIM (Oca-Tem): %5s %4s %5s %4s %6s %10s || KONTROL (Agu-bugun): %5s %4s %5s %4s %6s %10s" % (
        "MANTIK", "ISLEM", "TP", "STOP", "SURE", "BASARI", "DOLAR", "ISLEM", "TP", "STOP", "SURE", "BASARI", "DOLAR")
    m = [c, "TRADINGVIEW'IN 14 POPULER GOSTERGESI | %s -> bugun | %d sembol | %d mantik | SPREAD DAHIL | risk 15 $"
         % (args.bas, len(semboller) - len(yok), len(MANTIKLAR)),
         "SECIM donemi %s - %s  |  KONTROL donemi %s - bugun (secilen mantik bu donemi HIC gormedi)"
         % (args.bas, (ayrim - timedelta(days=1)).date(), args.ayrim), c]
    # 1) butun semboller, ayni mantik
    sira = sorted(A.index, key=lambda k: -A.at[k, "dolar"])
    m += ["", "-- 1) BUTUN SEMBOLLERDE AYNI MANTIK: SECIM DONEMINDE EN IYI 20 (yaninda KONTROL sonucu) --", bsl]
    for k in sira[:20]:
        m.append("%-46s || %s || %s" % (k, st(o_(A, k)), st(o_(B, k))))
    iki = [k for k in A.index if A.at[k, "dolar"] > 0 and B.at[k, "dolar"] > 0]
    iki.sort(key=lambda k: -min(A.at[k, "dolar"], B.at[k, "dolar"]))
    m += ["", "-- 2) IKI DONEMDE DE KARLI GENEL MANTIKLAR: %d tane (ilk 15) --" % len(iki), bsl]
    for k in iki[:15]:
        m.append("%-46s || %s || %s" % (k, st(o_(A, k)), st(o_(B, k))))
    if iki:
        mk = [x for x in MANTIKLAR if mad(x) == iki[0]][0]
        m.append("En saglam genel mantik (%s), butun semboller, 10.000 $:" % iki[0])
        m.append("   butun yil  : " + hesap_gunluk(gunluk[mk]))
        m.append("   KONTROL    : " + hesap_gunluk(np.where(np.arange(ngun) >= ayrim_gun, gunluk[mk], 0.0)))
    # 3) gosterge ligi
    m += ["", "-- 3) GOSTERGE LIGI (her gostergenin 24 seceneginin toplami, butun semboller) --",
          "%-12s || SECIM: %6s %%%5s %11s || KONTROL: %6s %%%5s %11s" % ("GOSTERGE", "ISLEM", "BAS.", "DOLAR", "ISLEM", "BAS.", "DOLAR")]
    lig = []
    for g in GOSTERGELER:
        za, zb = A[A["gosterge"] == g], B[B["gosterge"] == g]
        ka = (za["basari"] * za["islem"]).sum() / max(1, za["islem"].sum())
        kb = (zb["basari"] * zb["islem"]).sum() / max(1, zb["islem"].sum())
        lig.append((za["dolar"].sum() + zb["dolar"].sum(), g, za["islem"].sum(), ka, za["dolar"].sum(), zb["islem"].sum(), kb, zb["dolar"].sum()))
    lig.sort(reverse=True)
    for _, g, ia, ka, da, ib, kb, db in lig:
        m.append("%-12s || SECIM: %6d %%%5.1f %+11.2f || KONTROL: %6d %%%5.1f %+11.2f" % (g, ia, ka, da, ib, kb, db))
    # 4) her sembol kendi mantigi
    sag = [x for x in secilen if x[3]["islem"] >= 5 and x[3]["dolar"] > 0]
    sag.sort(key=lambda x: -x[3]["dolar"])
    m += ["", c, "4) HER SEMBOL KENDI EN IYI MANTIGI (SECIM doneminde secildi, en az 10 islem) -> KONTROL doneminde ne yapti?", c,
          "Secilen sembol: %d  |  KONTROL'de de karli (en az 5 islem) = SAGLAM: %d  |  KONTROL'de zarar: %d"
          % (len(secilen), len(sag), sum(1 for x in secilen if x[3]["dolar"] <= 0)),
          "%-12s %-46s || SECIM: %5s %4s %5s %4s %6s %10s || KONTROL: %5s %4s %5s %4s %6s %10s" % (
              "SEMBOL", "MANTIK", "ISLEM", "TP", "STOP", "SURE", "BASARI", "DOLAR", "ISLEM", "TP", "STOP", "SURE", "BASARI", "DOLAR")]
    kartlar, gs = [], np.zeros(ngun)
    for s, mk, oa, ob, isl in sag:
        isa = "  <- iki donemde de %50 ustu" if oa["basari"] > 50 and ob["basari"] > 50 else ""
        m.append("%-12s %-46s || SECIM: %s || KONTROL: %s%s" % (s, mad(mk), st(oa), st(ob), isa))
        for x in isl:
            kartlar.append(dict(sembol=s, mantik=mad(mk), donem="SECIM" if x[0] < ayrim_dk else "KONTROL",
                                giris_tr=tr(x[0]), cikis_tr=tr(x[1]), yon="AL" if x[2] == 1 else "SAT",
                                giris=round(x[3], 6), stop=round(x[4], 6), tp=round(x[5], 6), sonuc=x[6],
                                R=round(x[7], 3), dolar=round(x[8], 2), lot=round(x[9], 2)))
            k = x[1] // 1440 - gun0
            if ayrim_dk <= x[0] and 0 <= k < ngun:
                gs[k] += x[8]
    if kartlar:
        pd.DataFrame(kartlar).to_csv(os.path.join(klasor, "3_saglam_islemler.csv"), **yaz)
    tum_kontrol = sum(x[3]["dolar"] for x in secilen)
    m += ["", "SECILEN BUTUN semboller KONTROL doneminde toplam: %+.2f $   <- bu sayi en durust sonuctur" % tum_kontrol,
          "Sadece SAGLAM semboller, KONTROL donemi, 10.000 $: " + hesap_gunluk(gs),
          "   (dikkat: SAGLAM listesi de KONTROL sonucuna bakilarak suzuldu; gercek beklenti ust satirdaki toplamdir)"]
    # 5) sonuc
    m += ["", c, "5) SONUC - NE MANTIKLI, NE MANTIKSIZ", c]
    m.append("En iyi gosterge  : %s (iki donem toplam %+.0f $)" % (lig[0][1], lig[0][0]))
    m.append("En kotu gosterge : %s (iki donem toplam %+.0f $)" % (lig[-1][1], lig[-1][0]))
    for ad, vals, key in (("ZAMAN DILIMI", ("15DK", "1S", "4S"), lambda k, v: (" " + v + " ") in k),
                          ("FILTRE", ("FILTRE=YOK", "FILTRE=EMA200"), lambda k, v: v in k),
                          ("STOP", ("STOP=1.5ATR", "STOP=2.5ATR"), lambda k, v: v in k),
                          ("TP", ("TP=2R", "TP=3R"), lambda k, v: k.endswith(v))):
        par = []
        for v in vals:
            ks = [k for k in A.index if key(k, v)]
            par.append((A.loc[ks, "dolar"].sum() + B.loc[ks, "dolar"].sum(), v, B.loc[ks, "dolar"].sum()))
        par.sort(reverse=True)
        m.append("%-13s: " % ad + "  >  ".join("%s (%+.0f $, kontrol %+.0f $)" % (v, d, b) for d, v, b in par))
    m.append("Kural: bir mantik hem SECIM hem KONTROL doneminde karliysa 'gercek' olma ihtimali vardir;")
    m.append("sadece SECIM'de karliysa buyuk ihtimalle sanstir.  Robota sadece SAGLAM olanlar adaydir.")
    if yok:
        m += ["", "Verisi olmayan: " + ", ".join(yok)]
    ms = "\n".join(m)
    print("\n" + ms)
    with open(os.path.join(klasor, "0_OZET.txt"), "w", encoding="utf-8") as fh:
        fh.write(ms + "\n")
    print("\nDosyalar: %s" % os.path.abspath(klasor))


if __name__ == "__main__":
    main()
