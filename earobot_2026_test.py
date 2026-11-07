# -*- coding: utf-8 -*-
"""
EAROBOT 2026 TESTI - robot 1 Ocak 2026'da 10.000 $ ile calistirilsaydi ne olurdu
================================================================================
Python 3.8:   py -3.8 earobot_2026_test.py          (baska baslangic: --bas 2025-11-01)
Gerekli:      py -3.8 -m pip install MetaTrader5 pandas numpy

MT5'e baglanir, SADECE gecmis veri okur, ISLEM ACMAZ.  SPREAD / MAKAS / KOMISYON YOK.
Saatler NEW YORK saati (FTMO sunucusu = NY + 7).  Prag = sunucu - 1 saat (gunluk limit gunu).

EAROBOT.mq5 ile AYNI kurallar (61 sembol, 64 kural):
  - 1 saatlik kurallar: mum kapaninca sart, bir sonraki mumun acilisinda giris.
    Stop = stop katsayisi x ATR(14), TP = stopun 2 kati.  5 gunde sonuclanmazsa kapanir (SURE).
  - XAUUSD Asya kirilimi: aralik NY 18:00-01:00, giris 01:00-11:00 ilk kirilim, stop karsi uc,
    TP 2 x (giris - stop), NY 16:00'da kapanir.
  - LOT: stop olursa 15 $ zarar (MT5 order_calc_profit ile).  En kucuk lottan kucukse en kucuk lot;
    en kucuk lotta zarar 30 $'i gecerse islem ACILMAZ.
  - Her kuralda ayni anda tek islem; ayni kural ayni yonde 10 dk icinde tekrar acmaz.
  - GUNLUK LIMIT 250 $: kalan = 250 + bugun kapanan + acik islemlerin anlik kar/zarari (her dakika).
    0'a inerse butun islemler o dakikanin fiyatindan kapanir (LIMIT), o Prag gunu yeni islem yok.
  - Baslangic bakiyesi 10.000 $.
Takip 1 dakikalik mumlarla.  Ayni dakikada stop ve TP = STOP.  Giris dakikasinda TP sayilmaz.
SEANS (giris saatine gore, NY): Asya 19-01, Londra 02-07, NY sabah 08-11, NY ogleden sonra 12-16, Diger 17-18.

CIKTI (earobot_test_<tarih>/):
  0_OZET.txt      ozet + sembol/mantik bazli + seans bazli + gunluk
  1_islemler.csv  butun islemler
  2_mantik.csv    sembol / mantik bazli
  3_seans.csv     seans bazli (alis / satis)
  4_gunluk.csv    gun gun
  5_aylik.csv     ay ay (dolar ve ay sonu bakiyesi)
"""
from __future__ import print_function

import argparse
import os
import sys
import time
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

try:
    import MetaTrader5 as mt5
except ImportError:
    mt5 = None

RISK = 15.0
EN_FAZLA = 30.0
LIMIT = 250.0
BASLANGIC = 10000.0
TEKRAR_DK = 10
MAX_DK = 5 * 1440
ATR_P = 14
SEANSLAR = ["ASYA_19_01", "LONDRA_02_07", "NY_SABAH_08_11", "NY_OGLEDEN_SONRA_12_16", "DIGER_17_18"]

# (sembol, tip, yon, a, b, filtre, stop_katsayisi, ad)   tip: SAAT / RSI / SAKIN / EMA / ASYA
KURALLAR = [
    ("EURCZK", "SAAT", 1, 19, 2, 0, 1.0, "AL - Asya seansi (NY 19-01)"),
    ("EURCZK", "SAAT", -1, 8, 12, 0, 1.0, "SAT - NY sabah (08-11)"),
    ("EURCZK", "RSI", -1, 55, 70, 0, 1.0, "SAT - RSI 55-70"),
    ("USDILS", "SAKIN", -1, 0, 0, 0, 1.0, "SAT - sakin piyasa (ATR < ATR100 x 0.8)"),
    ("USDILS", "SAAT", -1, 12, 17, 0, 1.0, "SAT - NY ogleden sonra (12-16)"),
    ("USDSGD", "RSI", 1, 30, 45, 0, 1.0, "AL - RSI 30-45"),
    ("MANUSD", "RSI", -1, 55, 70, 0, 1.0, "SAT - RSI 55-70"),
    ("XAUUSD", "ASYA", 0, 0, 0, 0, 0.0, "AL/SAT - Asya araligi kirilimi"),
]
_EMA = [
    ("US30.cash", 5, 13, 0, 1.8), ("USDCAD", 8, 21, 100, 1.0), ("AUDUSD", 9, 21, 50, 1.3),
    ("XPTUSD", 9, 21, 50, 0.7), ("WHEAT.c", 5, 13, 50, 1.6), ("HK50.cash", 5, 13, 50, 1.7),
    ("SOYBEAN.c", 12, 26, 0, 1.6), ("AAVUSD", 21, 55, 0, 1.3), ("BTCUSD", 20, 50, 100, 1.0),
    ("CORN.c", 5, 13, 200, 1.6), ("ADAUSD", 20, 50, 0, 1.1), ("EURNZD", 12, 26, 100, 1.2),
    ("ICPUSD", 9, 21, 50, 2.0), ("NVDA", 5, 13, 50, 1.0), ("HEATOIL.c", 12, 26, 100, 1.4),
    ("AUDCHF", 12, 26, 0, 1.9), ("ALVG", 5, 13, 0, 0.7), ("GOOG", 5, 13, 0, 0.9),
    ("XCUUSD", 12, 26, 0, 2.0), ("TTE", 5, 13, 50, 1.1), ("XTZUSD", 20, 50, 0, 1.7),
    ("FRA40.cash", 8, 21, 100, 0.7), ("EU50.cash", 9, 26, 100, 0.8), ("GBPUSD", 8, 21, 100, 1.6),
    ("RTX", 5, 13, 50, 1.2), ("EURHUF", 8, 21, 0, 2.0), ("USDCHF", 20, 50, 0, 1.7),
    ("META", 5, 13, 0, 0.9), ("EURAUD", 12, 26, 0, 2.0), ("GE", 5, 13, 0, 0.9),
    ("MSFT", 9, 21, 0, 0.7), ("EURNOK", 5, 13, 100, 2.0), ("ARM", 5, 13, 0, 1.7),
    ("GRTUSD", 20, 50, 100, 1.5), ("SAN", 8, 21, 0, 0.8), ("AZN", 5, 13, 0, 1.2),
    ("AMD", 5, 13, 0, 1.0), ("QCOM", 9, 21, 0, 1.0), ("T", 5, 13, 0, 0.8),
    ("AAPL", 12, 26, 0, 0.7), ("DIS", 8, 21, 0, 1.6), ("COFFEE.c", 12, 26, 0, 1.1),
    ("BABA", 5, 13, 0, 1.2), ("INTC", 5, 13, 50, 1.2), ("LMT", 9, 21, 0, 0.9),
    ("FDX", 5, 13, 100, 1.0), ("AVGO", 9, 21, 0, 1.3), ("BAC", 5, 13, 100, 1.2),
    ("IBM", 5, 13, 50, 1.0), ("ZM", 5, 13, 50, 1.1), ("UKOIL.cash", 21, 55, 0, 1.9),
    ("JNJ", 5, 13, 0, 1.5), ("CSCO", 8, 21, 50, 1.7), ("BA", 9, 21, 0, 0.7),
    ("RACE", 9, 21, 0, 1.8), ("CVX", 5, 13, 0, 1.8),
]
for _s, _h, _y, _f, _k in _EMA:
    KURALLAR.append((_s, "EMA", 0, _h, _y, _f, _k, "EMA %d/%d filtre %s stop %.1f / TP %.1f ATR"
                     % (_h, _y, ("EMA%d" % _f) if _f else "yok", _k, 2 * _k)))


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


def ema(x, p):
    return pd.Series(x).ewm(span=p, adjust=False).mean().to_numpy()


def rsi(c, p=14):
    d = np.diff(c, prepend=c[0])
    up = pd.Series(np.maximum(d, 0)).ewm(alpha=1.0 / p, adjust=False).mean()
    dn = pd.Series(np.maximum(-d, 0)).ewm(alpha=1.0 / p, adjust=False).mean()
    return (100 - 100 / (1 + up / dn.replace(0, np.nan))).fillna(50).to_numpy()


def seans(saat):
    if saat >= 19 or saat < 2:
        return 0
    if saat < 8:
        return 1
    if saat < 12:
        return 2
    if saat < 17:
        return 3
    return 4


def takip(M, i, yon, e, sl, tp, bitis_ts, be=0.0):
    """i. dakikadan itibaren. donus: R, cikis indeksi, sonuc.
    be > 0: fiyat TP mesafesinin be katina (orn. 0.70) ulasinca stop GIRISE cekilir (bir sonraki dakikadan itibaren)."""
    risk = abs(e - sl)
    j_son = int(np.searchsorted(M["ts"], bitis_ts, side="left"))
    j_son = max(j_son, i + 1)
    hh, ll = M["h"][i:j_son], M["l"][i:j_son]
    if yon > 0:
        st, hd = ll <= sl, hh >= tp
    else:
        st, hd = hh >= sl, ll <= tp
    hd = hd.copy()
    hd[0] = False
    zs, zh = np.flatnonzero(st), np.flatnonzero(hd)
    s0 = zs[0] if zs.size else None
    h0 = zh[0] if zh.size else None
    if be > 0:
        tetik = e + yon * be * abs(tp - e)
        tt = (hh >= tetik) if yon > 0 else (ll <= tetik)
        tt = tt.copy()
        tt[0] = False
        zt = np.flatnonzero(tt)
        t0 = zt[0] if zt.size else None
        if t0 is not None and (s0 is None or s0 > t0) and (h0 is None or h0 > t0):
            gb = (ll <= e) if yon > 0 else (hh >= e)
            zg = np.flatnonzero(gb[t0 + 1:])
            g0 = int(t0 + 1 + zg[0]) if zg.size else None
            if g0 is not None and (h0 is None or g0 <= h0):
                return 0.0, i + g0, "GIRIS"
            if h0 is not None:
                return abs(tp - e) / risk, i + int(h0), "TP"
            k = min(j_son, len(M["c"])) - 1
            return yon * (M["c"][k] - e) / risk, k, "SURE"
    if s0 is not None and (h0 is None or s0 <= h0):
        return -1.0, i + int(s0), "STOP"
    if h0 is not None:
        return abs(tp - e) / risk, i + int(h0), "TP"
    k = min(j_son, len(M["c"])) - 1
    return yon * (M["c"][k] - e) / risk, k, "SURE"


def lot_hesapla(s, bilgi, yon, e, sl):
    """donus: o lotta stop zarari ($) ya da None (30 $ siniri / hesaplanamadi)"""
    kayip1 = None
    try:
        p = mt5.order_calc_profit(mt5.ORDER_TYPE_BUY if yon > 0 else mt5.ORDER_TYPE_SELL, s, 1.0, float(e), float(sl))
        if p is not None and p < 0:
            kayip1 = -float(p)
    except Exception:
        kayip1 = None
    if kayip1 is None:
        tv = getattr(bilgi, "trade_tick_value_loss", 0) or getattr(bilgi, "trade_tick_value", 0)
        ts = getattr(bilgi, "trade_tick_size", 0)
        if tv and ts:
            kayip1 = abs(e - sl) / ts * tv
    if not kayip1 or kayip1 <= 0:
        return None
    adim = bilgi.volume_step if bilgi.volume_step > 0 else 0.01
    lot = np.floor(RISK / kayip1 / adim + 1e-9) * adim
    if lot < bilgi.volume_min:
        lot = bilgi.volume_min
    if bilgi.volume_max > 0 and lot > bilgi.volume_max:
        lot = bilgi.volume_max
    zarar = lot * kayip1
    if zarar > EN_FAZLA + 1e-9:
        return None
    return zarar


def adaylar(s, kural_idx, h1, m1, bilgi, ny_fark, bas_ts, be=0.0):
    """bu sembolun kurallari icin butun sinyaller (tek islem / limit simulasyonda uygulanir)"""
    M = dict(ts=m1["time"].to_numpy(np.int64) // 60, h=m1["high"].to_numpy(float), l=m1["low"].to_numpy(float),
             c=m1["close"].to_numpy(float), o=m1["open"].to_numpy(float))
    M["t"] = M["ts"] - ny_fark * 60
    sonuc, atlanan = [], 0
    saatlik = [ki for ki in kural_idx if KURALLAR[ki][1] != "ASYA"]
    if saatlik:
        ths = h1["time"].to_numpy(np.int64) // 60
        thn = ths - ny_fark * 60
        H, L, C = [h1[k].to_numpy(float) for k in ("high", "low", "close")]
        n = len(C)
        tr = np.r_[H[0] - L[0], np.maximum(H[1:] - L[1:], np.maximum(np.abs(H[1:] - C[:-1]), np.abs(L[1:] - C[:-1])))]
        ATR = pd.Series(tr).rolling(ATR_P).mean().to_numpy()
        ATR100 = pd.Series(ATR).rolling(100).mean().to_numpy()
        R14 = rsi(C)
        ks = np.array([k for k in range(250, n - 1) if ths[k + 1] >= bas_ts and ATR[k] > 0], dtype=int)
        if len(ks):
            gi = np.searchsorted(M["ts"], ths[ks + 1], side="left")
            ok = gi < len(M["ts"])
            ks, gi = ks[ok], gi[ok]
        for ki in saatlik:
            _, tip, yon0, a, b, f, sk, _ad = KURALLAR[ki]
            if not len(ks):
                break
            if tip == "SAAT":
                sa = ((thn[ks] + 60) % 1440) // 60
                m = (sa >= a) & (sa < b) if a < b else (sa >= a) | (sa < b)
                yonler = np.where(m, yon0, 0)
            elif tip == "RSI":
                r = R14[ks]
                yonler = np.where((r >= a) & (r < b), yon0, 0)
            elif tip == "SAKIN":
                oy = ATR[ks] / ATR100[ks]
                yonler = np.where(np.nan_to_num(oy, nan=9.0) < 0.8, yon0, 0)
            else:
                eh, ey = ema(C, a), ema(C, b)
                fark, once = eh[ks] - ey[ks], eh[ks - 1] - ey[ks - 1]
                yuk, asg = (fark > 0) & (once <= 0), (fark < 0) & (once >= 0)
                if f:
                    ef = ema(C, f)
                    yuk &= C[ks] > ef[ks]
                    asg &= C[ks] < ef[ks]
                yonler = np.where(yuk, 1, np.where(asg, -1, 0))
            for z in np.flatnonzero(yonler):
                y = int(yonler[z]); i = int(gi[z]); e = M["o"][i]; d = sk * ATR[ks[z]]
                sl, tp = e - y * d, e + y * 2 * d
                zarar = lot_hesapla(s, bilgi, y, e, sl)
                if zarar is None:
                    atlanan += 1
                    continue
                R, j, son = takip(M, i, y, e, sl, tp, M["ts"][i] + MAX_DK, be)
                sonuc.append(dict(ki=ki, yon=y, e=e, d=d, zarar=zarar, R=R, sonuc=son,
                                  giris_ts=int(M["ts"][i]), cikis_ts=int(M["ts"][j]), cikis_fiyat=float(M["c"][j]),
                                  seans=seans(int((M["t"][i] % 1440) // 60))))
    for ki in [ki for ki in kural_idx if KURALLAR[ki][1] == "ASYA"]:
        for g in np.unique(M["t"] // 1440):
            base = int(g) * 1440
            if base + 60 + ny_fark * 60 < bas_ts:
                continue
            a0 = int(np.searchsorted(M["t"], base - 360, side="left"))
            a1 = int(np.searchsorted(M["t"], base + 60, side="left"))
            if a1 - a0 < 60:
                continue
            rh, rl = M["h"][a0:a1].max(), M["l"][a0:a1].min()
            if not rh > rl:
                continue
            w1 = int(np.searchsorted(M["t"], base + 660, side="left"))
            for i in range(a1, w1):
                ust, alt = M["h"][i] >= rh, M["l"][i] <= rl
                if not (ust or alt):
                    continue
                if ust and alt:
                    break
                y = 1 if ust else -1
                e = max(M["o"][i], rh) if y > 0 else min(M["o"][i], rl)
                sl = rl if y > 0 else rh
                tp = e + y * 2.0 * abs(e - sl)
                zarar = lot_hesapla(s, bilgi, y, e, sl)
                if zarar is None:
                    atlanan += 1
                    break
                R, j, son = takip(M, i, y, e, sl, tp, base + 960 + ny_fark * 60, be)
                if son == "SURE":
                    son = "NY16"
                sonuc.append(dict(ki=ki, yon=y, e=e, d=abs(e - sl), zarar=zarar, R=R, sonuc=son,
                                  giris_ts=int(M["ts"][i]), cikis_ts=int(M["ts"][j]), cikis_fiyat=float(M["c"][j]),
                                  seans=seans(int((M["t"][i] % 1440) // 60))))
                break
    return sonuc, atlanan, M


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bas", default="2026-01-01", help="baslangic tarihi YYYY-AA-GG")
    ap.add_argument("--be", type=float, default=0.0, help="stop girise: TP mesafesinin bu kati (0.7 = %%70), 0 = yok")
    ap.add_argument("--sunucu-ny", type=int, default=7)
    ap.add_argument("--sunucu-prag", type=int, default=1, help="sunucu saati - Prag saati")
    ap.add_argument("--cikti", default="")
    args = ap.parse_args()
    if mt5 is None:
        sys.exit("MetaTrader5 modulu yok:  py -3.8 -m pip install MetaTrader5")
    if not mt5.initialize():
        sys.exit("MT5 baglantisi kurulamadi: %s" % (mt5.last_error(),))
    hs = mt5.account_info()
    print("MT5 bagli: %s  (sadece gecmis veri, islem acilmiyor)" % (hs.server if hs else "?"))

    simdi = datetime.now(timezone.utc).replace(tzinfo=None)
    bit = simdi + timedelta(days=1)
    tbas = datetime.strptime(args.bas, "%Y-%m-%d")
    # sunucu saatine gore baslangic (sunucu = UTC + (NY farki 7 - NY'nin UTC farki 5) ~ UTC+2)
    bas_ts = int((tbas - datetime(1970, 1, 1)).total_seconds() // 60) + 2 * 60
    semboller = []
    for k in KURALLAR:
        if k[0] not in semboller:
            semboller.append(k[0])
    print("Sembol: %d | Kural: %d | %s -> bugun | risk %.0f $, en fazla %.0f $, gunluk limit %.0f $"
          % (len(semboller), len(KURALLAR), tbas.strftime("%Y-%m-%d"), RISK, EN_FAZLA, LIMIT))
    klasor = args.cikti or ("earobot_test_%s" % datetime.now().strftime("%Y%m%d_%H%M"))
    if not os.path.isdir(klasor):
        os.makedirs(klasor)
    yaz = dict(sep=";", decimal=",", index=False, encoding="utf-8-sig")

    tum, Mler, bulunamayan, atlanan_top, t0 = [], {}, [], 0, time.time()
    for n, s in enumerate(semboller, 1):
        if not mt5.symbol_select(s, True):
            bulunamayan.append(s); print("[%d/%d] %s : sembol yok" % (n, len(semboller), s)); continue
        bilgi = mt5.symbol_info(s)
        h1 = cek(s, mt5.TIMEFRAME_H1, tbas - timedelta(days=150), bit, 400)
        m1 = cek(s, mt5.TIMEFRAME_M1, tbas - timedelta(days=2), bit, 15)
        if bilgi is None or h1 is None or m1 is None or len(h1) < 300 or len(m1) < 1000:
            bulunamayan.append(s); print("[%d/%d] %s : veri yok" % (n, len(semboller), s)); continue
        ki_list = [ki for ki, k in enumerate(KURALLAR) if k[0] == s]
        a, atl, M = adaylar(s, ki_list, h1, m1, bilgi, args.sunucu_ny, bas_ts, args.be)
        tum += a; atlanan_top += atl; Mler[s] = M
        print("[%d/%d] %s : %d sinyal  (%.0f sn)" % (n, len(semboller), s, len(a), time.time() - t0))
    mt5.shutdown()
    if not tum:
        sys.exit("Hic sinyal yok.")

    # ---------- ortak zaman cizgisi (sunucu dakikasi) ----------
    G = np.unique(np.concatenate([M["ts"][M["ts"] >= bas_ts] for M in Mler.values()]))
    sem_no = {s: i for i, s in enumerate(Mler)}
    CG = np.zeros((len(Mler), len(G)), dtype=np.float32)
    for s, i in sem_no.items():
        M = Mler[s]
        ix = np.searchsorted(M["ts"], G, side="right") - 1
        CG[i] = np.where(ix >= 0, M["c"][np.maximum(ix, 0)], np.nan)
    girisler = {}
    for cid, x in enumerate(tum):
        if x["giris_ts"] < bas_ts:
            continue
        x["g_giris"] = int(np.searchsorted(G, x["giris_ts"]))
        x["g_cikis"] = int(np.searchsorted(G, x["cikis_ts"]))
        girisler.setdefault(x["g_giris"], []).append(cid)
    for g in girisler:
        girisler[g].sort(key=lambda c: tum[c]["ki"])

    # ---------- simulasyon ----------
    bakiye, tepe, en_dusuk_dd = BASLANGIC, BASLANGIC, 0.0
    acik = {}                       # cid -> True
    kural_acik = set()
    son_giris = {}
    cikislar = {}
    islemler, gunler = [], []
    gun_no, bugun_kap, durdu = None, 0.0, False
    gun_kayit = None
    prag_fark = args.sunucu_prag * 60

    def kapat(cid, g, sonuc_ad, para, fiyat):
        nonlocal bakiye, bugun_kap
        x = tum[cid]
        acik.pop(cid, None)
        kural_acik.discard(x["ki"])
        bakiye += para
        bugun_kap += para
        gun_kayit["islem"] += 1
        gun_kayit["para"] += para
        k = KURALLAR[x["ki"]]
        islemler.append(dict(sembol=k[0], mantik=k[7], yon="AL" if x["yon"] > 0 else "SAT",
                             seans=SEANSLAR[x["seans"]], sonuc=sonuc_ad,
                             giris=datetime(1970, 1, 1) + timedelta(minutes=int(G[x["g_giris"]])),
                             cikis=datetime(1970, 1, 1) + timedelta(minutes=int(G[g])),
                             giris_fiyat=x["e"], cikis_fiyat=fiyat, risk_dolar=round(x["zarar"], 2),
                             R=round(para / x["zarar"], 3), dolar=round(para, 2)))

    for g in range(len(G)):
        gn = (int(G[g]) - prag_fark) // 1440
        if gn != gun_no:
            if gun_kayit is not None:
                gun_kayit["bakiye"] = round(bakiye, 2)
                gunler.append(gun_kayit)
            gun_no, bugun_kap, durdu = gn, 0.0, False
            gun_kayit = dict(prag_gunu=(datetime(1970, 1, 1) + timedelta(days=gn)).strftime("%Y-%m-%d"),
                             islem=0, para=0.0, limit_doldu="")
        if not durdu:
            for cid in girisler.get(g, []):
                x = tum[cid]
                if x["ki"] in kural_acik:
                    continue
                anahtar = (x["ki"], x["yon"])
                if anahtar in son_giris and G[g] - son_giris[anahtar] < TEKRAR_DK:
                    continue
                acik[cid] = True
                kural_acik.add(x["ki"])
                son_giris[anahtar] = int(G[g])
                cikislar.setdefault(x["g_cikis"], []).append(cid)
        for cid in cikislar.pop(g, []):
            if cid in acik:
                x = tum[cid]
                kapat(cid, g, x["sonuc"], x["R"] * x["zarar"], x["cikis_fiyat"])
        yuzen = 0.0
        if acik:
            for cid in acik:
                x = tum[cid]
                c = CG[sem_no[KURALLAR[x["ki"]][0]], g]
                if c == c:
                    yuzen += x["yon"] * (c - x["e"]) / x["d"] * x["zarar"]
        varlik = bakiye + yuzen
        tepe = max(tepe, varlik)
        en_dusuk_dd = min(en_dusuk_dd, varlik - tepe)
        if not durdu and acik and LIMIT + bugun_kap + yuzen <= 0:
            for cid in list(acik):
                x = tum[cid]
                c = CG[sem_no[KURALLAR[x["ki"]][0]], g]
                c = x["e"] if c != c else c
                kapat(cid, g, "LIMIT", x["yon"] * (c - x["e"]) / x["d"] * x["zarar"], c)
            durdu = True
            gun_kayit["limit_doldu"] = "EVET"
        elif not durdu and not acik and LIMIT + bugun_kap <= 0:
            durdu = True
            gun_kayit["limit_doldu"] = "EVET"
    if gun_kayit is not None:
        gun_kayit["bakiye"] = round(bakiye, 2)
        gunler.append(gun_kayit)
    son_acik = []
    for cid in acik:
        x = tum[cid]
        c = CG[sem_no[KURALLAR[x["ki"]][0]], len(G) - 1]
        son_acik.append((KURALLAR[x["ki"]][0], x["yon"] * (c - x["e"]) / x["d"] * x["zarar"] if c == c else 0.0))

    # ---------- raporlar ----------
    di = pd.DataFrame(islemler)
    dg = pd.DataFrame(gunler)
    di.to_csv(os.path.join(klasor, "1_islemler.csv"), **yaz)
    dg.to_csv(os.path.join(klasor, "4_gunluk.csv"), **yaz)

    def grup(x):
        n = len(x)
        return pd.Series(dict(islem=n, TP=int((x["sonuc"] == "TP").sum()), STOP=int((x["sonuc"] == "STOP").sum()), GIRIS=int((x["sonuc"] == "GIRIS").sum()),
                              SURE_16=int(x["sonuc"].isin(["SURE", "NY16"]).sum()), LIMIT=int((x["sonuc"] == "LIMIT").sum()),
                              basari=round(100.0 * (x["dolar"] > 0).mean(), 1) if n else 0.0,
                              dolar=round(x["dolar"].sum(), 2)))

    m = []
    m.append("=" * 118)
    m.append("EAROBOT TESTI - robot %s tarihinde 10.000 $ ile baslatilsaydi (spread yok, risk %.0f $, TP 2 kat, gunluk limit %.0f $)"
             % (tbas.strftime("%Y-%m-%d"), RISK, LIMIT))
    m.append(("STOP GIRISE CEKME: fiyat TP mesafesinin %%%.0f'ine ulasinca stop girise cekilir" % (100 * args.be))
             if args.be > 0 else "STOP GIRISE CEKME: yok (robotun su anki hali)")
    m.append("=" * 118)
    if len(di):
        tp, st = int((di["sonuc"] == "TP").sum()), int((di["sonuc"] == "STOP").sum())
        su, li = int(di["sonuc"].isin(["SURE", "NY16"]).sum()), int((di["sonuc"] == "LIMIT").sum())
        m.append("Baslangic bakiyesi : %10.2f $" % BASLANGIC)
        m.append("Bitis bakiyesi     : %10.2f $   (net %+.2f $, %%%+.1f)" % (bakiye, bakiye - BASLANGIC,
                                                                          100.0 * (bakiye - BASLANGIC) / BASLANGIC))
        if son_acik:
            m.append("Test sonunda acik  : %d islem, anlik %+.2f $ (bakiyeye dahil degil)"
                     % (len(son_acik), sum(v for _, v in son_acik)))
        gi_ = int((di["sonuc"] == "GIRIS").sum())
        m.append("Kapanan islem      : %d  (TP %d / STOP %d / GIRISTE 0 $ %d / 5 gun veya NY16:00 %d / LIMIT %d)"
                 % (len(di), tp, st, gi_, su, li))
        m.append("Basari             : %%%.1f  (kar ile kapanan islem orani)" % (100.0 * (di["dolar"] > 0).mean()))
        m.append("Toplam kar         : %+.2f $" % di.loc[di["dolar"] > 0, "dolar"].sum())
        m.append("Toplam zarar       : %+.2f $" % di.loc[di["dolar"] < 0, "dolar"].sum())
        m.append("Gun sayisi         : %d  | Limit dolan gun: %d" % (len(dg), int((dg["limit_doldu"] == "EVET").sum())))
        m.append("En kotu gun        : %+.2f $" % dg["para"].min())
        m.append("En buyuk dusus     : %+.2f $  (bakiye + acik islemler, tepeden)" % en_dusuk_dd)
        if atlanan_top:
            m.append("En kucuk lotta zarar %.0f $'i gectigi icin acilmayan sinyal: %d" % (EN_FAZLA, atlanan_top))

        dm = di.groupby(["sembol", "mantik"]).apply(grup).reset_index().sort_values("dolar", ascending=False)
        dm.to_csv(os.path.join(klasor, "2_mantik.csv"), **yaz)
        m.append("")
        m.append("-- SEMBOL / MANTIK BAZLI --")
        m.append("%-11s %-46s %5s %4s %4s %5s %5s %5s %7s %10s" % ("SEMBOL", "MANTIK", "ISLEM", "TP", "STOP", "GIRIS", "SURE", "LIMIT",
                                                               "BASARI", "DOLAR"))
        for _, r in dm.iterrows():
            m.append("%-11s %-46s %5d %4d %4d %5d %5d %5d %%%6.1f %+10.2f" % (r["sembol"], r["mantik"][:46], r["islem"], r["TP"],
                                                                        r["STOP"], r["GIRIS"], r["SURE_16"], r["LIMIT"], r["basari"],
                                                                        r["dolar"]))
        ds = di.groupby(["seans", "yon"]).apply(grup).reset_index()
        ds.to_csv(os.path.join(klasor, "3_seans.csv"), **yaz)
        m.append("")
        m.append("-- SEANS BAZLI (giris saatine gore, NY) --")
        m.append("%-24s %-4s %5s %4s %4s %5s %5s %5s %7s %10s" % ("SEANS", "YON", "ISLEM", "TP", "STOP", "GIRIS", "SURE", "LIMIT",
                                                              "BASARI", "DOLAR"))
        for se in SEANSLAR:
            x = di[di["seans"] == se]
            if not len(x):
                continue
            for yon in ("AL", "SAT"):
                y = x[x["yon"] == yon]
                if len(y):
                    r = grup(y)
                    m.append("%-24s %-4s %5d %4d %4d %5d %5d %5d %%%6.1f %+10.2f" % (se, yon, r["islem"], r["TP"], r["STOP"], r["GIRIS"],
                                                                               r["SURE_16"], r["LIMIT"], r["basari"],
                                                                               r["dolar"]))
            r = grup(x)
            m.append("%-24s %-4s %5d %4d %4d %5d %5d %5d %%%6.1f %+10.2f" % (se, "TOP", r["islem"], r["TP"], r["STOP"], r["GIRIS"],
                                                                       r["SURE_16"], r["LIMIT"], r["basari"], r["dolar"]))
        di["ay"] = pd.to_datetime(di["cikis"]).dt.strftime("%Y-%m")
        da = di.groupby("ay").apply(grup).reset_index()
        da["ay_sonu_bakiye"] = (BASLANGIC + da["dolar"].cumsum()).round(2)
        dg["ay"] = dg["prag_gunu"].str[:7]
        lg = dg[dg["limit_doldu"] == "EVET"].groupby("ay").size()
        da["limit_dolan_gun"] = da["ay"].map(lg).fillna(0).astype(int)
        da.to_csv(os.path.join(klasor, "5_aylik.csv"), **yaz)
        m.append("")
        m.append("-- AYLIK (islemin kapandigi aya gore) --")
        m.append("%-8s %5s %4s %4s %5s %5s %5s %7s %10s %13s %6s" % ("AY", "ISLEM", "TP", "STOP", "GIRIS", "SURE", "LIMIT", "BASARI",
                                                                "DOLAR", "AY SONU BAKIYE", "LIM.GUN"))
        for _, r in da.iterrows():
            m.append("%-8s %5d %4d %4d %5d %5d %5d %%%6.1f %+10.2f %13.2f %6d" % (r["ay"], r["islem"], r["TP"], r["STOP"], r["GIRIS"],
                                                                            r["SURE_16"], r["LIMIT"], r["basari"], r["dolar"],
                                                                            r["ay_sonu_bakiye"], r["limit_dolan_gun"]))
        m.append("")
        m.append("-- GUNLUK (Prag gunu) --")
        m.append("%-10s %5s %10s %11s %s" % ("GUN", "ISLEM", "DOLAR", "BAKIYE", "LIMIT"))
        for _, r in dg.iterrows():
            if r["islem"] == 0 and not r["limit_doldu"]:
                continue
            m.append("%-10s %5d %+10.2f %11.2f %s" % (r["prag_gunu"], r["islem"], r["para"], r["bakiye"], r["limit_doldu"]))
    if bulunamayan:
        m.append("")
        m.append("Bulunamayan / verisi olmayan sembol: " + ", ".join(bulunamayan))
    m.append("")
    m.append("SONUC: TP = hedef, STOP = stop, GIRIS = stop girise cekildikten sonra 0 $ ile kapandi, SURE = 5 gun doldu, NY16 = altin 16:00 kapanisi, LIMIT = gunluk limit kapatti.")
    m.append("Not: Kurallar Mayis-Kasim 2026 verisinde secildi. Ocak-Nisan 2026 kurallarin HIC gormedigi donem;")
    m.append("     asil kanit o aylarin sonucudur.")
    m.append("")
    m.append("SONUC: 10.000 $ ile %s tarihinde baslasaydi bugun bakiye %.2f $ olurdu (net %+.2f $)."
             % (tbas.strftime("%d.%m.%Y"), bakiye, bakiye - BASLANGIC))
    ms = "\n".join(m)
    print("\n" + ms)
    with open(os.path.join(klasor, "0_OZET.txt"), "w", encoding="utf-8") as fh:
        fh.write(ms + "\n")
    print("\nDosyalar: %s" % os.path.abspath(klasor))


if __name__ == "__main__":
    main()
