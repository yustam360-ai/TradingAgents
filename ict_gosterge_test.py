# -*- coding: utf-8 -*-
"""
ICT GOSTERGE TESTI - ICT_Gosterge.mq5 ile AYNI MANTIK, butun semboller, 2026 basindan bugune
============================================================================================
Python 3.8:   py -3.8 ict_gosterge_test.py
Gerekli:      py -3.8 -m pip install MetaTrader5 pandas numpy
Sadece bazi semboller:   py -3.8 ict_gosterge_test.py --sembol EURUSD,GBPUSD
TEK DOSYA. MT5'e baglanir, SADECE gecmis veri okur, ISLEM ACMAZ.  SPREAD YOK, KOMISYON YOK.

DURUST TEST (ezber olmasin diye):
  SECIM DONEMI : 1 Ocak - 31 Temmuz 2026  -> ayarlar SADECE burada karsilastirilir, en iyisi burada secilir
  TEST DONEMI  : 1 Agustos 2026 - bugun   -> secilen ayar buna HIC dokunmadan denenir. Asil karar bu.
  Butun semboller icin TEK ORTAK mantik secilir. (Parite bazli liste de ayrica verilir, o da secim
  doneminde secilip test doneminde olculur.)

MANTIK (satis anlatiliyor, alis birebir tersi):
  1) YON       : gunluk grafikte son 20 gunun araliginin ortasinin ustunde ise satis, altinda ise alis  (FILTRE)
  2) GECE YARISI ACILISI: satis sadece NY gece yarisi acilis fiyatinin ustunde                       (FILTRE)
  3) SAAT      : FOREX  Londra killzone NY 02-05, NY killzone NY 07-10
                 DIGER  NY 08:30-11:00 ve 13:30-16:00          (sembol forex ise forex saatleri)
  4) LIKIDITE  : GUN_HAFTA = onceki gunun ve onceki haftanin tepesi
                 SEANS     = Asya araligi (NY 19-24) ve Londra araligi (NY 02-05) tepesi
                 ESIT      = esit tepeler (15 dk, iki swing tepe arasi fark 0.1 ATR'den az)
                 HEPSI     = hangisi olursa
  5) SUPURME   : killzone icinde fiyat bu tepelerden birinin ustune cikar
  6) MSS       : supurmeden sonra en fazla 20 mum icinde mum son swing dibin ALTINDA kapanir.
                 Zaman dilimi: 5 dk ya da 15 dk.
                 Swing dip (tepe/dip ne kadar gercek): SW3 = 3 mum, SW5 = 5 mum (o grafikte),
                 SW15 = 15 dk grafikte 3 mum, SW60 = 1 saatlik grafikte 3 mum
  7) FVG       : kirilim bacaginda bosluk (5 dk'da: 5,4,3,2,1 dk; 15 dk'da: 15,5,4,3,2,1 dk sirasiyla),
                 bacagin %50 ustunde, fiyata en yakin.
  8) GIRIS     : FVG alt kenarina satis limit; killzone bitiminden 30 dk sonra iptal; dolmadan TP gelirse iptal.
  9) STOP      : TEPE / TEPE_025 / TEPE_05 = supuren tepe + 0 / 0.25 / 0.5 x ATR,  FVG1 = FVG 1. mumunun tepesi
 10) TP        : 2R / 3R / 4R / ICT (asagidaki ilk karsi likidite: bacak dibi, onceki gun/hafta dibi,
                 Asya/Londra dibi; en az 2R)
 11) Bir setup bulununca o killzone'da karar mumuna kadar yeni setup aranmaz (gostergedeki gibi).
     Acik islem NY 16:00'da kapanir.  Risk 15 $; en kucuk lotta zarar 30 $'i gecerse islem yok.
  Denenen: 2 zaman dilimi x 4 swing x 4 likidite x 2 filtre x 4 stop x 4 TP = 1024 ayar (234.000 degil).

CIKTI (ict_gosterge_<tarih>/):
  0_OZET.txt            ortak mantik (secim + test), sembol listesi, %50 ustu pariteler, 10.000 $,
                        parite bazli liste, EN ALTTA dogru mantik
  1_tum_ayarlar.csv     1024 ayarin secim ve test sonucu
  2_ortak_islemler.csv  ortak mantigin butun islemleri (TR saati)
  3_ortak_sembol.csv    ortak mantikta sembol sembol sonuc
  4_parite_bazli.csv    her paritenin secim doneminde secilen kendi mantigi + test sonucu
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
BASLANGIC = 10000.0
SUNUCU_NY = 7

TFLER = [5, 15]
SWINGLER = ["SW3", "SW5", "SW15", "SW60"]
LIKLER = [("GUN_HAFTA", 1), ("SEANS", 2), ("ESIT", 4), ("HEPSI", 7)]
FILTRELER = ["VAR", "YOK"]
STOPLAR = [("TEPE", 0.0), ("TEPE_025", 0.25), ("TEPE_05", 0.5), ("FVG1", None)]
HEDEFLER = [2.0, 3.0, 4.0, "ICT"]
NL = len(STOPLAR) * len(HEDEFLER)
MASKELER = [(tf, sw, lk, fl) for tf in TFLER for sw in SWINGLER for lk in LIKLER for fl in FILTRELER]
NM = len(MASKELER)


# ----------------------------------------------------------------- saat (yaz / kis otomatik)
def _pazar(y, ay, kacinci):
    if kacinci > 0:
        d = date(y, ay, 1)
        d += timedelta(days=(6 - d.weekday()) % 7)
        return d + timedelta(days=7 * (kacinci - 1))
    d = date(y, ay + 1, 1) - timedelta(days=1)
    return d - timedelta(days=(d.weekday() - 6) % 7)


def abd_yaz(d):
    return _pazar(d.year, 3, 2) <= d < _pazar(d.year, 11, 1)


def ny_utc(d):
    return -4 if abd_yaz(d) else -5


def sunucu_utc(d):
    return ny_utc(d) + SUNUCU_NY


def gun_tarih(g):
    return date(1970, 1, 1) + timedelta(days=int(g))


def tr_saat(dk):
    g = int(dk // 1440)
    return datetime(1970, 1, 1) + timedelta(minutes=int(dk) + (3 - sunucu_utc(gun_tarih(g))) * 60)


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


# ----------------------------------------------------------------- veri
def cek(sembol, tf, bas, bit, parca_gun):
    parcalar, a = [], bas
    while a < bit:
        b = min(a + timedelta(days=parca_gun), bit)
        r = None
        for _ in range(3):
            r = mt5.copy_rates_range(sembol, tf, a, b)
            if r is not None:
                break
            time.sleep(0.5)
        if r is not None and len(r):
            parcalar.append(pd.DataFrame(r)[["time", "open", "high", "low", "close"]])
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
    if K == 1:
        return T.copy(), O.copy(), H.copy(), L.copy(), C.copy()
    df = pd.DataFrame({"k": T // K, "o": O, "h": H, "l": L, "c": C}).groupby("k").agg(
        o=("o", "first"), h=("h", "max"), l=("l", "min"), c=("c", "last"))
    return (df.index.to_numpy(np.int64) * K,) + tuple(df[x].to_numpy(float) for x in ("o", "h", "l", "c"))


def atr_hesap(h, l, c, p=14):
    tr = np.r_[h[0] - l[0], np.maximum(h[1:] - l[1:], np.maximum(np.abs(h[1:] - c[:-1]), np.abs(l[1:] - c[:-1])))]
    return pd.Series(tr).rolling(p, min_periods=1).mean().to_numpy()


def swing_dip(bt, vl, K, sol, sag):
    """gorunumde swing dipler: (dogrulanma zamani, fiyat) - zamana gore sirali"""
    n = len(vl)
    ok = np.zeros(n, dtype=bool)
    if n > sol + sag:
        ok[sol:n - sag] = True
        for d in range(1, sol + 1):
            ok[sol:n - sag] &= vl[sol:n - sag] < vl[sol - d:n - sag - d]
        for d in range(1, sag + 1):
            ok[sol:n - sag] &= vl[sol:n - sag] < vl[sol + d:n - sag + d]
    k = np.flatnonzero(ok)
    return bt[k + sag] + K, vl[k]


# ----------------------------------------------------------------- bir sembol
def sembol_isle(s, m1, d1, w1, bilgi, vpl, forex, bas_gun, test_gun):
    T = m1["time"].to_numpy(np.int64) // 60
    O, H, L, C = [m1[k].to_numpy(float) for k in ("open", "high", "low", "close")]
    d1t = d1["time"].to_numpy(np.int64) // 60
    w1t = w1["time"].to_numpy(np.int64) // 60
    adim = bilgi.volume_step if bilgi.volume_step > 0 else 0.01
    vmax = bilgi.volume_max if bilgi.volume_max > 0 else 1e9
    nokta = float(bilgi.point)
    son_dk = int(T[-1])
    GOR = {}
    for y in (-1, 1):
        if y < 0:
            vh1, vl1, vc1, vo1 = H, L, C, O
        else:
            vh1, vl1, vc1, vo1 = -L, -H, -C, -O
        B = {}
        for K in (1, 2, 3, 4, 5, 15, 60):
            bt, bo, bh, bl, bc = mumlar(T, vo1, vh1, vl1, vc1, K)
            B[K] = (bt, bo, bh, bl, bc)
        atr = {K: atr_hesap(B[K][2], B[K][3], B[K][4]) for K in (5, 15)}
        sw = {}
        for tf in TFLER:
            bt, _, _, bl, _ = B[tf]
            sw[(tf, "SW3")] = swing_dip(bt, bl, tf, 1, 1)
            sw[(tf, "SW5")] = swing_dip(bt, bl, tf, 2, 2)
            sw[(tf, "SW15")] = swing_dip(B[15][0], B[15][3], 15, 1, 1)
            sw[(tf, "SW60")] = swing_dip(B[60][0], B[60][3], 60, 1, 1)
        GOR[y] = dict(vh1=vh1, vl1=vl1, vc1=vc1, vo1=vo1, B=B, atr=atr, sw=sw)

    def maxvh(y, a, b):
        i, j = np.searchsorted(T, a), np.searchsorted(T, b)
        return GOR[y]["vh1"][i:j].max() if j > i else None

    def minvl(y, a, b):
        i, j = np.searchsorted(T, a), np.searchsorted(T, b)
        return GOR[y]["vl1"][i:j].min() if j > i else None

    def fvg_bul(y, tf, t0, tkarar, fiyat, dip, tepe):
        sira = [5, 4, 3, 2, 1] if tf == 5 else [15, 5, 4, 3, 2, 1]
        for K in sira:
            bt, _, bh, bl, _ = GOR[y]["B"][K]
            a0, a1 = int(np.searchsorted(bt, t0)), int(np.searchsorted(bt, tkarar))
            en = None
            for a in range(a0, a1 - 2):
                c = a + 2
                if bt[c] + K > tkarar:
                    break
                if bl[a] > bh[c]:
                    alt, ust = bh[c], bl[a]
                    if fiyat >= alt:
                        continue
                    if c + 1 < a1 and bh[c + 1:a1].max() >= alt:
                        continue
                    if alt < dip + 0.5 * (tepe - dip):
                        continue
                    if en is None or alt < en[0]:
                        en = (alt, ust, bh[a])
            if en is not None:
                return en
        return None

    def simule(y, Td, E, tepe, ilk, atrv, karsi, iptal, kapanis):
        R = np.full(NL, np.nan, dtype=np.float32)
        kod = np.full(NL, 9, dtype=np.int8)
        rk = np.zeros(NL, dtype=np.float32)
        cik = np.zeros(NL, dtype=np.int64)
        if son_dk < kapanis:
            return R, kod, rk, cik                       # gun bitmedi
        g = GOR[y]
        vh1, vl1, vc1 = g["vh1"], g["vl1"], g["vc1"]
        a0 = int(np.searchsorted(T, Td))
        c1 = int(np.searchsorted(T, iptal))
        z1 = int(np.searchsorted(T, kapanis))
        if a0 >= c1:
            return R, kod, rk, cik
        fz = np.flatnonzero(vh1[a0:c1] >= E)
        f = a0 + int(fz[0]) if fz.size else -1
        on_dip = vl1[a0:(f if f >= 0 else c1)].min() if (f if f >= 0 else c1) > a0 else np.inf
        for si, (sad, pay) in enumerate(STOPLAR):
            S = tepe + pay * atrv if pay is not None else ilk + nokta
            r = S - E
            if not (r > 0):
                continue
            rpl = r * vpl
            lot = np.floor(RISK / rpl / adim + 1e-9) * adim
            if lot < bilgi.volume_min:
                lot = bilgi.volume_min
            lot = min(lot, vmax)
            zarar = lot * rpl
            for hi, hd in enumerate(HEDEFLER):
                k = si * len(HEDEFLER) + hi
                rk[k] = zarar
                if hd == "ICT":
                    ad = [x for x in karsi if E - x >= 2.0 * r]
                    if not ad:
                        continue
                    TP = max(ad)
                else:
                    TP = E - hd * r
                if zarar > EN_FAZLA + 1e-9:
                    kod[k] = 7
                    continue
                if f < 0 or on_dip <= TP:
                    kod[k] = 8
                    continue
                st = np.flatnonzero(vh1[f:z1] >= S)
                tp = np.flatnonzero(vl1[f + 1:z1] <= TP)
                s0 = int(st[0]) if st.size else None
                h0 = int(tp[0]) + 1 if tp.size else None
                if s0 is not None and (h0 is None or s0 <= h0):
                    R[k], kod[k], cik[k] = -1.0, -1, T[f + s0]
                elif h0 is not None:
                    R[k], kod[k], cik[k] = (E - TP) / r, 1, T[f + h0]
                else:
                    R[k], kod[k], cik[k] = (E - vc1[z1 - 1]) / r, 0, T[z1 - 1] + 1
        return R, kod, rk, cik

    satir, RR, KK, RK, CK = [], [], [], [], []
    gunler = np.unique(T // 1440)
    for g in gunler:
        if g < bas_gun:
            continue
        D = int(g * 1440)
        nyMid = D + SUNUCU_NY * 60
        kapanis = nyMid + 960
        if forex:
            pen = [(nyMid + 120, nyMid + 300), (nyMid + 420, nyMid + 600)]
        else:
            pen = [(nyMid + 510, nyMid + 660), (nyMid + 810, nyMid + 960)]
        im = int(np.searchsorted(T, nyMid))
        if im >= len(T):
            continue
        d = int(np.searchsorted(d1t, D)) - 1
        if d < 20:
            continue
        w = int(np.searchsorted(w1t, D, side="right")) - 1
        yari = (d1["high"].iloc[d - 19:d + 1].max() + d1["low"].iloc[d - 19:d + 1].min()) / 2.0
        for y in (-1, 1):
            G = GOR[y]
            sg = 1 if y < 0 else -1
            pdh = d1["high"].iloc[d] if y < 0 else -d1["low"].iloc[d]
            pdl = d1["low"].iloc[d] if y < 0 else -d1["high"].iloc[d]
            sev = [(pdh, D, 1, "PD")]
            karsi0 = [(pdl, D)]
            if w >= 1:
                sev.append((w1["high"].iloc[w - 1] if y < 0 else -w1["low"].iloc[w - 1], D, 1, "PW"))
                karsi0.append((w1["low"].iloc[w - 1] if y < 0 else -w1["high"].iloc[w - 1], D))
            a = maxvh(y, nyMid - 300, nyMid)
            if a is not None:
                sev.append((a, nyMid, 2, "ASYA"))
                karsi0.append((minvl(y, nyMid - 300, nyMid), nyMid))
            a = maxvh(y, nyMid + 120, nyMid + 300)
            if a is not None:
                sev.append((a, nyMid + 300, 2, "LON"))
                karsi0.append((minvl(y, nyMid + 120, nyMid + 300), nyMid + 300))
            b15, _, h15, _, _ = G["B"][15]
            s0, s1 = int(np.searchsorted(b15, D - 3 * 1440)), int(np.searchsorted(b15, kapanis))
            swt = [k for k in range(max(s0, 1), min(s1, len(h15) - 1)) if h15[k] > h15[k - 1] and h15[k] > h15[k + 1]]
            for bi in range(1, len(swt)):
                for ai in range(bi):
                    ka, kb = swt[ai], swt[bi]
                    if abs(h15[ka] - h15[kb]) <= 0.1 * G["atr"][15][kb]:
                        ust = max(h15[ka], h15[kb])
                        if kb - ka < 2 or h15[ka + 1:kb].max() < ust:
                            sev.append((ust, int(b15[kb + 1] + 15), 4, "EQ"))
            gece = G["vo1"][im]
            yari_v = yari if y < 0 else -yari
            for p, (ws, we) in enumerate(pen):
                iptal = min(we + 30, kapanis)
                acik = []
                for (lv, bil, bit, ad) in sev:
                    if bil > ws or lv != lv:
                        continue
                    m = maxvh(y, bil, ws)
                    if m is None or m <= lv:
                        acik.append((lv, bit, ad))
                if not acik:
                    continue
                karsi = [x for x, bil in karsi0 if x == x]
                for tf in TFLER:
                    bt, bo, bh, bl, bc = G["B"][tf]
                    i0, i1 = int(np.searchsorted(bt, ws)), int(np.searchsorted(bt, we - tf + 1))
                    if i1 <= i0:
                        continue
                    olay = {}
                    for lv, bit, ad in acik:
                        z = np.flatnonzero(bh[i0:i1] > lv)
                        if z.size:
                            i = i0 + int(z[0])
                            o = olay.setdefault(i, [0, [], -np.inf])
                            o[0] |= bit
                            o[1].append(ad)
                            o[2] = max(o[2], lv)
                    onbellek = {}
                    for i in sorted(olay):
                        bits, adlar, _ = olay[i]
                        for swn in SWINGLER:
                            ct, cp = G["sw"][(tf, swn)]
                            q = int(np.searchsorted(ct, bt[i] + tf, side="right")) - 1
                            if q < 0:
                                continue
                            ref = cp[q]
                            jk = -1
                            for j in range(i + 1, min(i + 21, len(bt))):
                                if bt[j] + tf > iptal:
                                    break
                                if bc[j] < ref:
                                    jk = j
                                    break
                            if jk < 0:
                                continue
                            dec = jk + 1
                            if dec >= len(bt) or bt[dec] + tf > iptal:
                                continue
                            Td = int(bt[dec] + tf)
                            anahtar = (i, jk)
                            if anahtar not in onbellek:
                                shi = i + int(np.argmax(bh[i:jk + 1]))
                                tepe = bh[i:dec + 1].max()
                                dip = bl[shi:dec + 1].min()
                                fv = fvg_bul(y, tf, int(bt[shi]), Td, bc[dec], dip, tepe)
                                if fv is None:
                                    onbellek[anahtar] = None
                                else:
                                    E, ust, ilk = fv
                                    atrv = G["atr"][tf][dec]
                                    kr = [dip] + [x for x, bil in karsi0 if bil <= Td and x == x]
                                    sim = simule(y, Td, E, tepe, ilk, atrv, kr, iptal, kapanis)
                                    onbellek[anahtar] = (E, tepe, sim)
                            v = onbellek[anahtar]
                            if v is None:
                                continue
                            E, tepe, (R, kd, rk, ck) = v
                            satir.append((int(g), p, y, tf, SWINGLER.index(swn), bits, int(bt[i]), Td, tf,
                                          bool(E > gece), bool(E > yari_v), bool(g >= test_gun),
                                          "+".join(adlar), sg * E, sg * tepe))
                            RR.append(R); KK.append(kd); RK.append(rk); CK.append(ck)
    if not satir:
        return None
    kol = ["gun", "pen", "yon", "tf", "sw", "bits", "tsup", "Td", "K", "f_gece", "f_gun", "test", "sev", "E", "tepe"]
    df = pd.DataFrame(satir, columns=kol)
    RR, KK, RK, CK = np.vstack(RR), np.vstack(KK), np.vstack(RK), np.vstack(CK)
    sira = np.lexsort((df["Td"].to_numpy(), df["tsup"].to_numpy(), df["yon"].to_numpy(), df["pen"].to_numpy(),
                       df["gun"].to_numpy()))
    df = df.iloc[sira].reset_index(drop=True)
    return dict(df=df, R=RR[sira], K=KK[sira], RK=RK[sira], CK=CK[sira])


# ----------------------------------------------------------------- birlesim
def zincir(df, m):
    """gostergedeki gibi: ayni gun/killzone/yonde, onceki setup'in karar mumundan once yeni setup yok"""
    idx = np.flatnonzero(m)
    al = np.zeros(len(df), dtype=bool)
    if not idx.size:
        return al
    g = (df["gun"].to_numpy() * 10 + df["pen"].to_numpy()) * 3 + df["yon"].to_numpy()
    ts, td, kk = df["tsup"].to_numpy(), df["Td"].to_numpy(), df["K"].to_numpy()
    son_g, son_td = None, None
    for i in idx:
        if g[i] != son_g:
            al[i] = True
            son_g, son_td = g[i], td[i] - kk[i]
        elif ts[i] >= son_td:
            al[i] = True
            son_td = td[i] - kk[i]
    return al


def maske(V, mi):
    tf, sw, (lk, bit), fl = MASKELER[mi]
    df = V["df"]
    m = (df["tf"].to_numpy() == tf) & (df["sw"].to_numpy() == SWINGLER.index(sw)) & ((df["bits"].to_numpy() & bit) != 0)
    al = zincir(df, m)
    if fl == "VAR":
        al &= df["f_gece"].to_numpy() & df["f_gun"].to_numpy()
    return al


def istatistik(V):
    """donus: (2 donem, NM, NL) n, w, tp, st, su, R, dolar"""
    out = np.zeros((7, 2, NM, NL))
    R0 = np.nan_to_num(V["R"].astype(np.float64))
    D0 = R0 * V["RK"]
    gecerli = (V["K"] == 1) | (V["K"] == -1) | (V["K"] == 0)
    test = V["df"]["test"].to_numpy()
    onb = {}
    for mi in range(NM):
        tf, sw, lk, fl = MASKELER[mi]
        anahtar = (tf, sw, lk[0])
        if anahtar not in onb:
            df = V["df"]
            m = (df["tf"].to_numpy() == tf) & (df["sw"].to_numpy() == SWINGLER.index(sw)) & ((df["bits"].to_numpy() & lk[1]) != 0)
            onb[anahtar] = zincir(df, m)
        al = onb[anahtar].copy()
        if fl == "VAR":
            al &= V["df"]["f_gece"].to_numpy() & V["df"]["f_gun"].to_numpy()
        for dn, dm in enumerate((~test, test)):
            A = (al & dm)[:, None] & gecerli
            if not A.any():
                continue
            r = np.where(A, R0, 0.0)
            out[0, dn, mi] += A.sum(0)
            out[1, dn, mi] += (A & (R0 > 0)).sum(0)
            out[2, dn, mi] += (A & (V["K"] == 1)).sum(0)
            out[3, dn, mi] += (A & (V["K"] == -1)).sum(0)
            out[4, dn, mi] += (A & (V["K"] == 0)).sum(0)
            out[5, dn, mi] += r.sum(0)
            out[6, dn, mi] += np.where(A, D0, 0.0).sum(0)
    return out


def islemler(V, s, mi, k):
    al = maske(V, mi)
    df = V["df"]
    out = []
    for j in np.flatnonzero(al):
        kd = int(V["K"][j, k])
        if kd not in (1, -1, 0):
            continue
        r = df.iloc[j]
        R = float(V["R"][j, k])
        out.append(dict(sembol=s, donem="TEST" if r["test"] else "SECIM",
                        karar_tr=tr_saat(r["Td"]).strftime("%Y-%m-%d %H:%M"),
                        cikis_tr=tr_saat(V["CK"][j, k]).strftime("%Y-%m-%d %H:%M"), cikis_dk=int(V["CK"][j, k]),
                        yon="AL" if r["yon"] > 0 else "SAT", supurulen=r["sev"], giris=round(float(r["E"]), 6),
                        sonuc={1: "TP", -1: "STOP", 0: "SURE"}[kd], R=round(R, 3),
                        dolar=round(R * float(V["RK"][j, k]), 2)))
    return out


def ad(mi, k):
    tf, sw, lk, fl = MASKELER[mi]
    st = STOPLAR[k // len(HEDEFLER)][0]
    hd = HEDEFLER[k % len(HEDEFLER)]
    return "TF=%ddk | SWING=%s | LIK=%s | FILTRE=%s | STOP=%s | TP=%s" % (
        tf, sw, lk[0], fl, st, ("%.0fR" % hd) if hd != "ICT" else "ICT")


def aciklama(mi, k, g="   "):
    tf, sw, lk, fl = MASKELER[mi]
    st = STOPLAR[k // len(HEDEFLER)]
    hd = HEDEFLER[k % len(HEDEFLER)]
    swm = {"SW3": "%d dk grafikte 3 mumluk dip (ortadaki en dusuk)" % tf,
           "SW5": "%d dk grafikte 5 mumluk dip (iki yanindaki ikiser mumdan dusuk)" % tf,
           "SW15": "15 dk grafikte 3 mumluk dip", "SW60": "1 saatlik grafikte 3 mumluk dip"}[sw]
    lkm = {"GUN_HAFTA": "onceki gunun ya da onceki haftanin tepesi (alista dibi)",
           "SEANS": "Asya araligi (NY 19-24) ya da Londra araligi (NY 02-05) tepesi (alista dibi)",
           "ESIT": "esit tepeler (alista esit dipler), 15 dk grafik",
           "HEPSI": "onceki gun/hafta, Asya/Londra araligi ya da esit tepe (alista dip)"}[lk[0]]
    stm = ("FVG'nin 1. mumunun tepesi (alista dibi)" if st[1] is None else
           "supuren tepenin %s ustu (alista dibin alti)" % ("tam" if st[1] == 0 else "%.2f ATR" % st[1]))
    hdm = ("stop mesafesinin %.0f kati" % hd) if hd != "ICT" else "asagidaki ilk karsi likidite (en az 2R)"
    s = ["Saat     : FOREX'te Londra killzone (TR kis 10-13 / yaz 09-12) + NY killzone (TR kis 15-18 / yaz 14-17);",
         "           digerlerinde NY 08:30-11:00 ve 13:30-16:00 (TR kis 16:30-19 ve 21:30-24 / yaz bir saat erken)",
         "Supurulen: " + lkm,
         "Kirilim  : %d dk mum, %s ALTINDA kapanir (alista ustunde)" % (tf, swm),
         "FVG/Giris: kirilim hareketinin ust yarisindaki FVG'nin kenarina limit emir",
         "Stop     : " + stm,
         "TP       : " + hdm,
         "Filtre   : " + ("gunluk yon (20 gun araligi) + gece yarisi acilisi" if fl == "VAR" else "yok")]
    return "\n".join(g + x for x in s)


def hesap(isl):
    if not len(isl):
        return None
    d = pd.DataFrame(isl).sort_values("cikis_dk")
    bak = BASLANGIC + d["dolar"].cumsum().to_numpy()
    tepe = np.maximum.accumulate(np.r_[BASLANGIC, bak])[1:]
    gunluk = d.groupby(d["cikis_dk"] // 1440)["dolar"].sum()
    return "10.000 $ -> %.2f $ (net %+.2f $) | en kotu gun %+.2f $ | en buyuk dusus %+.2f $ | en dusuk bakiye %.2f $" % (
        bak[-1], bak[-1] - BASLANGIC, gunluk.min(), (bak - tepe).min(), min(BASLANGIC, bak.min()))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bas", default="2026-01-01")
    ap.add_argument("--test", default="2026-08-01", help="test doneminin basi")
    ap.add_argument("--min-ortak", type=int, default=300, help="ortak mantik icin secim doneminde en az islem")
    ap.add_argument("--min-sembol", type=int, default=15, help="parite bazli secimde en az islem")
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
    bas = datetime.strptime(args.bas, "%Y-%m-%d")
    bas_gun = int((bas - datetime(1970, 1, 1)).total_seconds() // 86400)
    test_gun = int((datetime.strptime(args.test, "%Y-%m-%d") - datetime(1970, 1, 1)).total_seconds() // 86400)
    simdi = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=sunucu_utc(datetime.now(timezone.utc).date()))
    klasor = args.cikti or ("ict_gosterge_%s" % datetime.now().strftime("%Y%m%d_%H%M"))
    if not os.path.isdir(klasor):
        os.makedirs(klasor)
    yaz = dict(sep=";", decimal=",", index=False, encoding="utf-8-sig")
    print("Sembol: %d | secim %s -> %s | test %s -> bugun | %d ayar | spread yok"
          % (len(semboller), args.bas, args.test, args.test, NM * NL))
    TOP = np.zeros((7, 2, NM, NL))
    VERI, SIST, yok, t0 = {}, {}, [], time.time()
    for n_, s in enumerate(semboller, 1):
        if not mt5.symbol_select(s, True):
            yok.append(s); print("[%d/%d] %s : sembol yok" % (n_, len(semboller), s)); continue
        bilgi = mt5.symbol_info(s)
        vpl = deger_lot(s, bilgi) if bilgi is not None else None
        m1 = cek(s, mt5.TIMEFRAME_M1, bas - timedelta(days=12), simdi + timedelta(days=1), 15)
        d1 = cek(s, mt5.TIMEFRAME_D1, bas - timedelta(days=60), simdi + timedelta(days=1), 400)
        w1 = cek(s, mt5.TIMEFRAME_W1, bas - timedelta(days=60), simdi + timedelta(days=1), 400)
        if bilgi is None or not vpl or m1 is None or len(m1) < 20000 or d1 is None or w1 is None:
            yok.append(s); print("[%d/%d] %s : veri yok" % (n_, len(semboller), s)); continue
        forex = bilgi.trade_calc_mode in (0, 5)
        V = sembol_isle(s, m1, d1, w1, bilgi, vpl, forex, bas_gun, test_gun)
        if V is None:
            print("[%d/%d] %s : kurulum yok" % (n_, len(semboller), s)); continue
        st = istatistik(V)
        TOP += st
        VERI[s], SIST[s] = V, st
        print("[%d/%d] %s : %d kurulum  (%.0f sn)" % (n_, len(semboller), s, len(V["df"]), time.time() - t0))
    mt5.shutdown()
    if not VERI:
        sys.exit("Hic kurulum yok.")

    def bas_(a, dn):
        return np.where(a[0, dn] > 0, 100.0 * a[1, dn] / np.maximum(a[0, dn], 1), 0.0)

    # ---- tum ayarlar
    satirlar = []
    for mi in range(NM):
        for k in range(NL):
            r = dict(ayar=ad(mi, k))
            for dn, dad in ((0, "secim"), (1, "test")):
                r.update({"%s_islem" % dad: int(TOP[0, dn, mi, k]), "%s_TP" % dad: int(TOP[2, dn, mi, k]),
                          "%s_STOP" % dad: int(TOP[3, dn, mi, k]), "%s_basari" % dad: round(bas_(TOP, dn)[mi, k], 1),
                          "%s_R" % dad: round(TOP[5, dn, mi, k], 1), "%s_dolar" % dad: round(TOP[6, dn, mi, k], 2)})
            satirlar.append(r)
    pd.DataFrame(satirlar).sort_values("secim_R", ascending=False).to_csv(os.path.join(klasor, "1_tum_ayarlar.csv"), **yaz)

    yeter = TOP[0, 0] >= args.min_ortak
    if not yeter.any():
        yeter = TOP[0, 0] >= 1
    Rm = np.where(yeter, TOP[5, 0], -np.inf)
    sira = np.argsort(-Rm.ravel())
    mi0, k0 = np.unravel_index(int(sira[0]), Rm.shape)

    m = []
    c = "=" * 150
    m.append(c)
    m.append("ICT GOSTERGE TESTI | SECIM %s -> %s | TEST %s -> bugun | %d sembol | %d ayar | SPREAD YOK | risk 15 $"
             % (args.bas, args.test, args.test, len(VERI), NM * NL))
    m.append("SAAT: " + saat_notu)
    m.append(c)
    bsl = "%-62s | %6s %5s %5s %7s %8s %10s || %6s %5s %5s %7s %8s %10s" % (
        "AYAR", "ISLEM", "TP", "STOP", "BASARI", "NET R", "DOLAR", "ISLEM", "TP", "STOP", "BASARI", "NET R", "DOLAR")

    def st_satir(a, mi, k, et=None):
        x = []
        for dn in (0, 1):
            x.append("%6d %5d %5d %%%6.1f %+8.1f %+10.2f" % (a[0, dn, mi, k], a[2, dn, mi, k], a[3, dn, mi, k],
                                                           bas_(a, dn)[mi, k], a[5, dn, mi, k], a[6, dn, mi, k]))
        return "%-62s | %s || %s" % ((et or ad(mi, k))[:62], x[0], x[1])

    m.append("")
    m.append("-- SECIM DONEMINDE EN COK KAZANDIRAN 10 AYAR (en az %d islem) ve TEST DONEMINDEKI SONUCLARI --" % args.min_ortak)
    m.append("%-62s | %-48s || %-48s" % ("", "SECIM DONEMI (Ocak-Temmuz)", "TEST DONEMI (Agustos-bugun)"))
    m.append(bsl)
    for f in sira[:10]:
        mi, k = np.unravel_index(int(f), Rm.shape)
        if not np.isfinite(Rm[mi, k]):
            break
        m.append(st_satir(TOP, mi, k))
    m.append("")
    m.append(c)
    m.append("ORTAK MANTIK (secim doneminde 1. olan): " + ad(mi0, k0))
    m.append(c)
    m.append(aciklama(mi0, k0))
    m.append("")
    m.append(bsl)
    m.append(st_satir(TOP, mi0, k0, "HEPSI"))
    # ortak mantik sembol bazli + islemler
    tum, sb = [], []
    for s, V in VERI.items():
        isl = islemler(V, s, mi0, k0)
        tum += isl
        a = SIST[s]
        sb.append(dict(sembol=s, **{"%s_%s" % (dad, x): (int(a[i, dn, mi0, k0]) if i < 5 else round(a[i, dn, mi0, k0], 2))
                                    for dn, dad in ((0, "secim"), (1, "test"))
                                    for i, x in ((0, "islem"), (2, "TP"), (3, "STOP"), (4, "SURE"), (6, "dolar"))}))
    sb = pd.DataFrame(sb)
    sb["secim_basari"] = np.round(100.0 * np.array([SIST[s][1, 0, mi0, k0] for s in sb["sembol"]]) / np.maximum(sb["secim_islem"], 1), 1)
    sb["test_basari"] = np.round(100.0 * np.array([SIST[s][1, 1, mi0, k0] for s in sb["sembol"]]) / np.maximum(sb["test_islem"], 1), 1)
    sb = sb.sort_values("test_dolar", ascending=False)
    sb.to_csv(os.path.join(klasor, "3_ortak_sembol.csv"), **yaz)
    di = pd.DataFrame(tum)
    if len(di):
        di.drop(columns=["cikis_dk"]).to_csv(os.path.join(klasor, "2_ortak_islemler.csv"), **yaz)
        m.append("")
        m.append("-- ORTAK MANTIK AYLIK --")
        for ay, x in di.groupby(di["cikis_tr"].str[:7]):
            m.append("   %-8s islem %4d | TP %4d | STOP %4d | SURE %4d | %+10.2f $   %s" % (
                ay, len(x), (x["sonuc"] == "TP").sum(), (x["sonuc"] == "STOP").sum(), (x["sonuc"] == "SURE").sum(),
                x["dolar"].sum(), "(TEST)" if (x["donem"] == "TEST").all() else ""))
        m.append("")
        m.append("ORTAK MANTIK 10.000 $ - SADECE TEST DONEMI (Agustos-bugun): " + str(hesap(di[di["donem"] == "TEST"].to_dict("records"))))
        m.append("ORTAK MANTIK 10.000 $ - TUM DONEM (Ocak-bugun)           : " + str(hesap(di.to_dict("records"))))
    m.append("")
    m.append("-- ORTAK MANTIKTA TEST DONEMINDE BASARISI %50'NIN USTUNDE OLAN PARITELER (en az 5 islem) --")
    m.append("%-12s | %6s %5s %5s %5s %7s %10s || %6s %5s %5s %7s %10s" % ("SEMBOL", "ISLEM", "TP", "STOP", "SURE", "BASARI",
                                                                          "DOLAR", "SECIM:", "TP", "STOP", "BASARI", "DOLAR"))
    u = sb[(sb["test_islem"] >= 5) & (sb["test_basari"] > 50)]
    for _, r in u.iterrows():
        m.append("%-12s | %6d %5d %5d %5d %%%6.1f %+10.2f || %6d %5d %5d %%%6.1f %+10.2f" % (
            r["sembol"], r["test_islem"], r["test_TP"], r["test_STOP"], r["test_SURE"], r["test_basari"], r["test_dolar"],
            r["secim_islem"], r["secim_TP"], r["secim_STOP"], r["secim_basari"], r["secim_dolar"]))
    m.append("Toplam %d parite.  Iki donemde de kazanan: %s" % (
        len(u), ", ".join(sb[(sb["test_dolar"] > 0) & (sb["secim_dolar"] > 0) & (sb["test_islem"] >= 5)]["sembol"])))

    # ---- parite bazli
    pb, pisl = [], []
    for s, V in VERI.items():
        a = SIST[s]
        ok = a[0, 0] >= args.min_sembol
        if not ok.any():
            continue
        Rs = np.where(ok, a[5, 0], -np.inf)
        mi, k = np.unravel_index(int(np.argmax(Rs)), Rs.shape)
        if a[5, 0, mi, k] <= 0:
            continue
        pb.append(dict(sembol=s, ayar=ad(mi, k),
                       secim_islem=int(a[0, 0, mi, k]), secim_TP=int(a[2, 0, mi, k]), secim_STOP=int(a[3, 0, mi, k]),
                       secim_basari=round(100.0 * a[1, 0, mi, k] / a[0, 0, mi, k], 1), secim_dolar=round(a[6, 0, mi, k], 2),
                       test_islem=int(a[0, 1, mi, k]), test_TP=int(a[2, 1, mi, k]), test_STOP=int(a[3, 1, mi, k]),
                       test_SURE=int(a[4, 1, mi, k]),
                       test_basari=round(100.0 * a[1, 1, mi, k] / max(a[0, 1, mi, k], 1), 1), test_dolar=round(a[6, 1, mi, k], 2)))
        pisl += [x for x in islemler(V, s, mi, k) if x["donem"] == "TEST"]
    pb = pd.DataFrame(pb)
    m.append("")
    m.append(c)
    m.append("PARITE BAZLI: her parite icin SECIM doneminde en cok kazandiran ayar, TEST doneminde olculdu (%d parite)" % len(pb))
    m.append(c)
    if len(pb):
        pb = pb.sort_values("test_dolar", ascending=False)
        pb.to_csv(os.path.join(klasor, "4_parite_bazli.csv"), **yaz)
        m.append("TEST DONEMINDE BASARISI %50'NIN USTUNDE OLANLAR (en az 5 islem):")
        m.append("%-12s | %6s %5s %5s %5s %7s %10s | %s" % ("SEMBOL", "ISLEM", "TP", "STOP", "SURE", "BASARI", "DOLAR", "AYAR"))
        for _, r in pb[(pb["test_islem"] >= 5) & (pb["test_basari"] > 50)].iterrows():
            m.append("%-12s | %6d %5d %5d %5d %%%6.1f %+10.2f | %s" % (r["sembol"], r["test_islem"], r["test_TP"], r["test_STOP"],
                                                                     r["test_SURE"], r["test_basari"], r["test_dolar"], r["ayar"]))
        m.append("Test doneminde kazanan: %d / %d parite" % ((pb["test_dolar"] > 0).sum(), len(pb)))
        m.append("PARITE BAZLI 10.000 $ - SADECE TEST DONEMI: " + str(hesap(pisl)))
    if yok:
        m.append("")
        m.append("Verisi olmayan: " + ", ".join(yok))
    # ---- en altta dogru mantik
    m.append("")
    m.append(c)
    tst = TOP[:, 1, mi0, k0]
    m.append("DOGRU MANTIK (secim doneminde secildi, TEST doneminde hic gorulmeden olculdu):")
    m.append("   " + ad(mi0, k0))
    m.append(aciklama(mi0, k0))
    m.append("   TEST DONEMI: %d islem | TP %d | STOP %d | SURE %d | basari %%%.1f | %+.1f R | %+.2f $" % (
        tst[0], tst[2], tst[3], tst[4], 100.0 * tst[1] / max(tst[0], 1), tst[5], tst[6]))
    m.append("   " + ("TEST DONEMINDE DE KAZANDI." if tst[5] > 0 else "TEST DONEMINDE KAZANMADI - bu mantik robota konmamali."))
    m.append(c)
    m.append("BASARI = kar ile kapanan islem orani.  SURE = NY 16:00'da acik kapanan islem.")
    ms = "\n".join(m)
    print("\n" + ms)
    with open(os.path.join(klasor, "0_OZET.txt"), "w", encoding="utf-8") as fh:
        fh.write(ms + "\n")
    print("\nDosyalar: %s" % os.path.abspath(klasor))


if __name__ == "__main__":
    main()
