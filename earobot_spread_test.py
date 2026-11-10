# -*- coding: utf-8 -*-
"""
EAROBOT SPREAD TESTI - son 3 ay, SPREAD DAHIL (6 $ spread kurali ile) ve SPREAD'SIZ karsilastirma
================================================================================================
Python 3.8:   py -3.8 earobot_spread_test.py          (baska baslangic: --bas 2026-08-01)
Gerekli:      py -3.8 -m pip install MetaTrader5 pandas numpy

MT5'e baglanir, SADECE gecmis veri okur, ISLEM ACMAZ.
EAROBOT.mq5 kurallari; HARIC listesindeki 12 sembol CIKARILDI:
  AAPL, JNJ, XAUUSD (Asya kirilimi), RACE, CSCO, BABA, FRA40.cash, EU50.cash,
  USDILS (2 kural), USDSGD, EURCZK (3 kural), SOYBEAN.c.
  - 1 saatlik kurallar: mum kapaninca sart, bir sonraki mumun acilisinda PIYASA emriyle giris.
    Stop = stop katsayisi x ATR(14), TP = stopun 2 kati.  5 gunde sonuclanmazsa kapanir (SURE).
  - LOT: stop olursa 15 $ zarar.  En kucuk lottan kucukse en kucuk lot; en kucuk lotta zarar 30 $'i
    gecerse islem ACILMAZ.  Her kuralda ayni anda tek islem; ayni kural ayni yonde 10 dk icinde tekrar acmaz.
  - GUNLUK LIMIT 250 $ (acik islemler dahil, Prag gunu).  Baslangic 10.000 $.
SPREAD (MT5 1 dakikalik mumlarindaki spread; grafik fiyati BID):
  ALIS : ASK'tan girilir (acilis + spread).  Stop ve TP BID ile tetiklenir.
  SATIS: BID'den girilir.  Stop ve TP ASK ile (bid + spread) tetiklenir.  Sure dolunca ASK'tan kapanir.
  ROBOTTAKI KURAL: islem acilirken spread'in maliyeti (o lotta) 6 $'i gecerse islem ACILMAZ.
Ayni test SPREAD'SIZ da yapilir; sonda iki sonuc yan yana verilir.

CIKTI (earobot_spread_<tarih>/):
  0_OZET.txt   spread dahil tam rapor + spread'siz ozet + sembol sembol karsilastirma
  1_islemler_spread.csv, 1_islemler_spreadsiz.csv
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


SPREAD_SINIR = 6.0
HARIC = {"AAPL", "JNJ", "XAUUSD", "RACE", "CSCO", "BABA", "FRA40.cash", "EU50.cash",
         "USDILS", "USDSGD", "EURCZK", "SOYBEAN.c"}
KURALLAR = [k for k in KURALLAR if k[0] not in HARIC]


def cek(sembol, tf, bas, bit, parca_gun, spread=False):
    parcalar, a = [], bas
    kol = ["time", "open", "high", "low", "close"] + (["spread"] if spread else [])
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
            if spread and "spread" not in d.columns:
                d["spread"] = 0
            parcalar.append(d[kol])
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


def takip(M, i, yon, e, sl, tp, bitis_ts, sp_on):
    """i. dakikadan itibaren.  donus: R, cikis indeksi, sonuc, cikis fiyati.
    sp_on: alista stop/TP BID ile; satista stop/TP ASK (bid + spread) ile."""
    risk = abs(e - sl)
    j_son = int(np.searchsorted(M["ts"], bitis_ts, side="left"))
    j_son = max(j_son, i + 1)
    hh, ll = M["h"][i:j_son], M["l"][i:j_son]
    s = M["sp"][i:j_son] if sp_on else 0.0
    if yon > 0:
        st, hd = ll <= sl, hh >= tp
    else:
        st, hd = hh + s >= sl, ll + s <= tp
    hd = hd.copy()
    hd[0] = False
    zs, zh = np.flatnonzero(st), np.flatnonzero(hd)
    s0 = zs[0] if zs.size else None
    h0 = zh[0] if zh.size else None
    if s0 is not None and (h0 is None or s0 <= h0):
        return -1.0, i + int(s0), "STOP", sl
    if h0 is not None:
        return abs(tp - e) / risk, i + int(h0), "TP", tp
    k = min(j_son, len(M["c"])) - 1
    cik = M["c"][k] + (M["sp"][k] if (sp_on and yon < 0) else 0.0)
    return yon * (cik - e) / risk, k, "SURE", cik


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


def adaylar(s, kural_idx, h1, m1, bilgi, ny_fark, bas_ts, sp_on):
    """bu sembolun kurallari icin butun sinyaller.  donus: sinyaller, lot atlanan, spread atlanan, M"""
    nokta = getattr(bilgi, "point", 0.0) or getattr(bilgi, "trade_tick_size", 0.0) or 0.0
    M = dict(ts=m1["time"].to_numpy(np.int64) // 60, h=m1["high"].to_numpy(float), l=m1["low"].to_numpy(float),
             c=m1["close"].to_numpy(float), o=m1["open"].to_numpy(float), sp=m1["spread"].to_numpy(float) * nokta)
    M["t"] = M["ts"] - ny_fark * 60
    sonuc, atlanan, atl_sp = [], 0, 0
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
    for ki in kural_idx:
        _, tip, yon0, a, b, f, sk, _ad = KURALLAR[ki]
        if not len(ks) or tip == "ASYA":
            continue
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
            y = int(yonler[z]); i = int(gi[z]); d = sk * ATR[ks[z]]
            e = M["o"][i] + (M["sp"][i] if (sp_on and y > 0) else 0.0)      # alis ASK'tan, satis BID'den
            sl, tp = e - y * d, e + y * 2 * d
            zarar = lot_hesapla(s, bilgi, y, e, sl)
            if zarar is None:
                atlanan += 1
                continue
            maliyet = zarar * M["sp"][i] / d if sp_on else 0.0                # o lotta spread maliyeti ($)
            if maliyet > SPREAD_SINIR + 1e-9:
                atl_sp += 1
                continue
            R, j, son, cikis = takip(M, i, y, e, sl, tp, M["ts"][i] + MAX_DK, sp_on)
            sonuc.append(dict(ki=ki, yon=y, e=e, d=d, zarar=zarar, R=R, sonuc=son, maliyet=maliyet,
                              giris_ts=int(M["ts"][i]), cikis_ts=int(M["ts"][j]), cikis_fiyat=float(cikis),
                              seans=seans(int((M["t"][i] % 1440) // 60))))
    return sonuc, atlanan, atl_sp, M


def simule(tum, Mler, bas_ts, prag_fark):
    """hesap simulasyonu (gunluk limit dahil).  donus: islemler, gunler, bakiye, en buyuk dusus, acik kalanlar"""
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
    st = dict(bakiye=BASLANGIC, tepe=BASLANGIC, dd=0.0, bugun=0.0)
    acik, kural_acik, son_giris, cikislar = {}, set(), {}, {}
    islemler, gunler = [], []
    gun_no, durdu, gun_kayit = None, False, None

    def kapat(cid, g, sonuc_ad, para, fiyat):
        x = tum[cid]
        acik.pop(cid, None)
        kural_acik.discard(x["ki"])
        st["bakiye"] += para
        st["bugun"] += para
        gun_kayit["islem"] += 1
        gun_kayit["para"] += para
        k = KURALLAR[x["ki"]]
        islemler.append(dict(sembol=k[0], mantik=k[7], yon="AL" if x["yon"] > 0 else "SAT",
                             seans=SEANSLAR[x["seans"]], sonuc=sonuc_ad,
                             giris=datetime(1970, 1, 1) + timedelta(minutes=int(G[x["g_giris"]])),
                             cikis=datetime(1970, 1, 1) + timedelta(minutes=int(G[g])),
                             giris_fiyat=x["e"], cikis_fiyat=fiyat, risk_dolar=round(x["zarar"], 2),
                             spread_maliyet=round(x["maliyet"], 2), R=round(para / x["zarar"], 3), dolar=round(para, 2)))

    for g in range(len(G)):
        gn = (int(G[g]) - prag_fark) // 1440
        if gn != gun_no:
            if gun_kayit is not None:
                gun_kayit["bakiye"] = round(st["bakiye"], 2)
                gunler.append(gun_kayit)
            gun_no, durdu = gn, False
            st["bugun"] = 0.0
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
        for cid in acik:
            x = tum[cid]
            c = CG[sem_no[KURALLAR[x["ki"]][0]], g]
            if c == c:
                yuzen += x["yon"] * (c - x["e"]) / x["d"] * x["zarar"]
        varlik = st["bakiye"] + yuzen
        st["tepe"] = max(st["tepe"], varlik)
        st["dd"] = min(st["dd"], varlik - st["tepe"])
        if not durdu and acik and LIMIT + st["bugun"] + yuzen <= 0:
            for cid in list(acik):
                x = tum[cid]
                c = CG[sem_no[KURALLAR[x["ki"]][0]], g]
                c = x["e"] if c != c else c
                kapat(cid, g, "LIMIT", x["yon"] * (c - x["e"]) / x["d"] * x["zarar"], c)
            durdu = True
            gun_kayit["limit_doldu"] = "EVET"
        elif not durdu and not acik and LIMIT + st["bugun"] <= 0:
            durdu = True
            gun_kayit["limit_doldu"] = "EVET"
    if gun_kayit is not None:
        gun_kayit["bakiye"] = round(st["bakiye"], 2)
        gunler.append(gun_kayit)
    son_acik = 0.0
    for cid in acik:
        x = tum[cid]
        c = CG[sem_no[KURALLAR[x["ki"]][0]], len(G) - 1]
        son_acik += x["yon"] * (c - x["e"]) / x["d"] * x["zarar"] if c == c else 0.0
    return pd.DataFrame(islemler), pd.DataFrame(gunler), st["bakiye"], st["dd"], len(acik), son_acik


def grup(x):
    n = len(x)
    return pd.Series(dict(islem=n, TP=int((x["sonuc"] == "TP").sum()), STOP=int((x["sonuc"] == "STOP").sum()),
                          SURE=int((x["sonuc"] == "SURE").sum()), LIMIT=int((x["sonuc"] == "LIMIT").sum()),
                          basari=round(100.0 * (x["dolar"] > 0).mean(), 1) if n else 0.0,
                          dolar=round(x["dolar"].sum(), 2)))


def ozet_satirlari(ad, di, dg, bakiye, dd, n_acik, acik_para, atl_lot, atl_sp):
    m = ["-- %s --" % ad]
    if not len(di):
        m.append("   islem yok")
        return m
    m.append("   Bitis bakiyesi : %.2f $   (net %+.2f $, %%%+.1f)" % (bakiye, bakiye - BASLANGIC,
                                                                  100.0 * (bakiye - BASLANGIC) / BASLANGIC))
    if n_acik:
        m.append("   Test sonunda acik: %d islem, anlik %+.2f $ (bakiyeye dahil degil)" % (n_acik, acik_para))
    m.append("   Kapanan islem  : %d  (TP %d / STOP %d / 5 gun %d / LIMIT %d)   basari %%%.1f" % (
        len(di), int((di["sonuc"] == "TP").sum()), int((di["sonuc"] == "STOP").sum()), int((di["sonuc"] == "SURE").sum()),
        int((di["sonuc"] == "LIMIT").sum()), 100.0 * (di["dolar"] > 0).mean()))
    m.append("   Toplam kar %+.2f $ | toplam zarar %+.2f $ | islem basina %+.2f $" % (
        di.loc[di["dolar"] > 0, "dolar"].sum(), di.loc[di["dolar"] < 0, "dolar"].sum(), di["dolar"].mean()))
    m.append("   En kotu gun %+.2f $ | en buyuk dusus %+.2f $ | limit dolan gun %d" % (
        dg["para"].min(), dd, int((dg["limit_doldu"] == "EVET").sum())))
    m.append("   Acilmayan sinyal: en kucuk lotta zarar %.0f $'i gecen %d, spread maliyeti %.0f $'i gecen %d" % (
        EN_FAZLA, atl_lot, SPREAD_SINIR, atl_sp))
    if "spread_maliyet" in di and di["spread_maliyet"].sum() > 0:
        m.append("   Ortalama spread maliyeti: %.2f $ / islem" % di["spread_maliyet"].mean())
    return m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bas", default="", help="baslangic tarihi YYYY-AA-GG (bos = son 3 ay)")
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
    tbas = datetime.strptime(args.bas, "%Y-%m-%d") if args.bas else (simdi - timedelta(days=91)).replace(hour=0, minute=0, second=0, microsecond=0)
    bas_ts = int((tbas - datetime(1970, 1, 1)).total_seconds() // 60) + 2 * 60
    semboller = []
    for k in KURALLAR:
        if k[0] not in semboller:
            semboller.append(k[0])
    print("Sembol: %d | Kural: %d | %s -> bugun | risk %.0f $, en fazla %.0f $, spread siniri %.0f $, gunluk limit %.0f $"
          % (len(semboller), len(KURALLAR), tbas.strftime("%Y-%m-%d"), RISK, EN_FAZLA, SPREAD_SINIR, LIMIT))
    print("Haric: " + ", ".join(sorted(HARIC)))
    klasor = args.cikti or ("earobot_spread_%s" % datetime.now().strftime("%Y%m%d_%H%M"))
    if not os.path.isdir(klasor):
        os.makedirs(klasor)
    yaz = dict(sep=";", decimal=",", index=False, encoding="utf-8-sig")
    tum = {True: [], False: []}
    atl = {True: [0, 0], False: [0, 0]}
    Mler, bulunamayan, t0 = {}, [], time.time()
    for n, s in enumerate(semboller, 1):
        if not mt5.symbol_select(s, True):
            bulunamayan.append(s); print("[%d/%d] %s : sembol yok" % (n, len(semboller), s)); continue
        bilgi = mt5.symbol_info(s)
        h1 = cek(s, mt5.TIMEFRAME_H1, tbas - timedelta(days=150), bit, 400)
        m1 = cek(s, mt5.TIMEFRAME_M1, tbas - timedelta(days=2), bit, 15, spread=True)
        if bilgi is None or h1 is None or m1 is None or len(h1) < 300 or len(m1) < 1000:
            bulunamayan.append(s); print("[%d/%d] %s : veri yok" % (n, len(semboller), s)); continue
        ki_list = [ki for ki, k in enumerate(KURALLAR) if k[0] == s]
        for sp_on in (True, False):
            a, al, asp, M = adaylar(s, ki_list, h1, m1, bilgi, args.sunucu_ny, bas_ts, sp_on)
            tum[sp_on] += a; atl[sp_on][0] += al; atl[sp_on][1] += asp
        Mler[s] = M
        print("[%d/%d] %s  (%.0f sn)" % (n, len(semboller), s, time.time() - t0))
    mt5.shutdown()

    sonuc = {}
    for sp_on in (True, False):
        di, dg, bak, dd, n_acik, acik_para = simule(tum[sp_on], Mler, bas_ts, args.sunucu_prag * 60)
        sonuc[sp_on] = (di, dg, bak, dd, n_acik, acik_para)
        di.to_csv(os.path.join(klasor, "1_islemler_%s.csv" % ("spread" if sp_on else "spreadsiz")), **yaz)
    di, dg, bak, dd, n_acik, acik_para = sonuc[True]
    di0, dg0, bak0, dd0, n_acik0, acik_para0 = sonuc[False]

    m = []
    m.append("=" * 120)
    m.append("EAROBOT SPREAD TESTI - %s -> bugun, 10.000 $, risk %.0f $, TP 2 kat, gunluk limit %.0f $, spread kurali %.0f $"
             % (tbas.strftime("%Y-%m-%d"), RISK, LIMIT, SPREAD_SINIR))
    m.append("Haric (cikarilan %d): " % len(HARIC) + "" + ", ".join(sorted(HARIC)))
    m.append("=" * 120)
    m += ozet_satirlari("SPREAD DAHIL (robotun gercek hali)", di, dg, bak, dd, n_acik, acik_para, atl[True][0], atl[True][1])
    m.append("")
    m += ozet_satirlari("SPREAD'SIZ (karsilastirma)", di0, dg0, bak0, dd0, n_acik0, acik_para0, atl[False][0], atl[False][1])
    if len(di):
        a = di.groupby(["sembol", "mantik"]).apply(grup).reset_index()
        b = di0.groupby(["sembol", "mantik"]).apply(grup).reset_index() if len(di0) else a.iloc[0:0]
        k = a.merge(b, on=["sembol", "mantik"], how="outer", suffixes=("", "_0")).fillna(0).sort_values("dolar", ascending=False)
        k.to_csv(os.path.join(klasor, "2_sembol_karsilastirma.csv"), **yaz)
        m.append("")
        m.append("-- SEMBOL / MANTIK: SPREAD DAHIL ve SPREAD'SIZ --")
        m.append("%-11s %-44s | %5s %4s %4s %4s %7s %10s | %5s %7s %10s" % (
            "SEMBOL", "MANTIK", "ISLEM", "TP", "STOP", "SURE", "BASARI", "DOLAR", "ISLEM", "BASARI", "SPREADSIZ $"))
        for _, r in k.iterrows():
            m.append("%-11s %-44s | %5d %4d %4d %4d %%%6.1f %+10.2f | %5d %%%6.1f %+10.2f" % (
                r["sembol"], str(r["mantik"])[:44], r["islem"], r["TP"], r["STOP"], r["SURE"], r["basari"], r["dolar"],
                r["islem_0"], r["basari_0"], r["dolar_0"]))
        zarar_eden = k[k["dolar"] < 0]
        m.append("")
        m.append("SPREAD DAHIL ZARAR EDEN %d sembol/mantik: %s" % (len(zarar_eden), ", ".join(zarar_eden["sembol"].astype(str))))
        di["ay"] = pd.to_datetime(di["cikis"]).dt.strftime("%Y-%m")
        da = di.groupby("ay").apply(grup).reset_index()
        m.append("")
        m.append("-- AYLIK (spread dahil) --")
        b_ = BASLANGIC
        for _, r in da.iterrows():
            b_ += r["dolar"]
            m.append("%-8s %5d islem  basari %%%5.1f  %+10.2f $   ay sonu bakiye %10.2f" % (r["ay"], r["islem"], r["basari"], r["dolar"], b_))
    if bulunamayan:
        m.append("")
        m.append("Bulunamayan / verisi olmayan sembol: " + ", ".join(bulunamayan))
    m.append("")
    m.append("SONUC: 10.000 $ ile %s tarihinde baslasaydi -> SPREAD DAHIL %.2f $ (net %+.2f $) | SPREAD'SIZ %.2f $ (net %+.2f $)"
             % (tbas.strftime("%d.%m.%Y"), bak, bak - BASLANGIC, bak0, bak0 - BASLANGIC))
    ms = "\n".join(m)
    print("\n" + ms)
    with open(os.path.join(klasor, "0_OZET.txt"), "w", encoding="utf-8") as fh:
        fh.write(ms + "\n")
    print("\nDosyalar: %s" % os.path.abspath(klasor))


if __name__ == "__main__":
    main()
