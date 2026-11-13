# -*- coding: utf-8 -*-
"""
MSB-OB 23 SEMBOL - SPREAD DAHIL TEST (son 3 ay)
===============================================
Python 3.8:   py -3.8 msb_ob_23_spread.py
Gerekli:      py -3.8 -m pip install MetaTrader5 pandas numpy

MT5'e baglanir, SADECE gecmis veri okur, ISLEM ACMAZ.
msb_ob_test_3ay.py'deki BASARISI %50'NIN USTUNDEKI 23 sembol, her biri KENDI birlesimiyle (asagidaki liste).
Gosterge ve islem kurallari msb_ob_test_3ay.py ile ayni (zigzag 9, kirilim orani 0.273).

SPREAD: MT5 1 dakikalik mumlarindaki spread kullanilir.  Grafik fiyati BID'dir.
  ALIS : limit emir ASK kutunun kenarina inince dolar (bid + spread <= giris).  Stop ve TP BID ile.
  SATIS: limit emir BID kenara cikinca dolar.  Stop ve TP ASK ile (bid + spread).
  Fiyat zaten kutunun icindeyse hemen girilir: alis ASK'tan, satis BID'den.
  SPREAD SINIRI: islem acilirken spread'in maliyeti (15 $ risk icin) 6 $'i gecerse islem ACILMAZ.
Islem basi sabit 15 $ risk (stop = -15 $).  Gunluk limit yok.  Karsilastirma icin ayni test SPREAD'SIZ da yapilir.

CIKTI (msb_ob_23_spread_<tarih>/):  0_OZET.txt, 1_islemler.csv
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
SPREAD_SINIR = 6.0
BASLANGIC = 10000.0
ZZ = 9
FIB = 0.273
MAX_R = 5.0
PARCA = 4096
TF_DK = {"5dk": 5, "15dk": 15}
ISINMA = {"5dk": 20, "15dk": 40}
# sembol: (zaman dilimi, kutu, giris, stop, hedef)
LISTE = {
    "ALVG": ("5dk", "BB", "ORTA", "SWING", "2R"),
    "NEOUSD": ("5dk", "MB", "KENAR", "KUTU", "YAPI"),
    "GALUSD": ("5dk", "OB", "KENAR", "KUTU", "YAPI"),
    "PLTR": ("5dk", "BB", "KENAR", "KUTU", "YAPI"),
    "META": ("5dk", "BB", "KENAR", "ATR", "2R"),
    "USDILS": ("5dk", "MB", "KENAR", "SWING", "YAPI"),
    "JNJ": ("5dk", "MB", "ORTA", "KUTU", "2R"),
    "GM": ("5dk", "MB", "KENAR", "ATR", "YAPI"),
    "SANUSD": ("5dk", "MB", "KENAR", "KUTU", "YAPI"),
    "NVDA": ("5dk", "OB", "KENAR", "SWING", "2R"),
    "VOWG_p": ("5dk", "MB", "KENAR", "KUTU", "2R"),
    "AMD": ("5dk", "MB", "ORTA", "KUTU", "YAPI"),
    "SNOW": ("5dk", "OB", "ORTA", "KUTU", "3R"),
    "NKE": ("5dk", "OB", "ORTA", "KUTU", "3R"),
    "BRK.B": ("5dk", "BB", "KENAR", "SWING", "3R"),
    "COTTON.c": ("5dk", "MB", "KENAR", "ATR", "2R"),
    "EURUSD": ("15dk", "OB", "ORTA", "SWING", "3R"),
    "RACE": ("5dk", "OB", "KENAR", "SWING", "YAPI"),
    "SBUX": ("5dk", "OB", "KENAR", "ATR", "2R"),
    "XAGEUR": ("15dk", "BB", "KENAR", "KUTU", "YAPI"),
    "IBE": ("5dk", "BB", "KENAR", "SWING", "3R"),
    "GBPAUD": ("5dk", "MB", "KENAR", "SWING", "YAPI"),
    "XCUUSD": ("5dk", "MB", "KENAR", "SWING", "YAPI"),
}


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


def ilk(kosul_dizi, bas, bit):
    """kosul_dizi(k0, k1) -> bool dizi; ilk True indeks (bas <= k < bit) ya da -1"""
    k = bas
    while k < bit:
        e = min(k + PARCA, bit)
        z = np.flatnonzero(kosul_dizi(k, e))
        if z.size:
            return k + int(z[0])
        k = e
    return -1


def gosterge(o, h, l, c):
    """EmreKb MSB-OB.  donus: MSB olaylari listesi"""
    n = len(c)
    hh = pd.Series(h).rolling(ZZ).max().to_numpy()
    ll = pd.Series(l).rolling(ZZ).min().to_numpy()
    to_up = np.nan_to_num(h >= hh)
    to_dn = np.nan_to_num(l <= ll)
    trend, son_up, son_dn = 1, -1, -1
    H, HI, L, LI = [], [], [], []
    l0i_g, h0i_g = np.full(n, -1), np.full(n, -1)
    market, son_l0, son_h0 = 1, None, None
    olaylar = []
    for i in range(n):
        once = trend
        if trend == 1 and to_dn[i]:
            trend = -1
        elif trend == -1 and to_up[i]:
            trend = 1
        if trend != once:
            if trend == 1:
                ln = i - son_up - 1 if son_up >= 0 else 1
                ln = ln if ln > 0 else 1
                v = l[i - ln + 1:i + 1].min()
                j = i - int(np.flatnonzero(l[i - ln + 1:i + 1][::-1] == v)[0])
                L.append(v); LI.append(j)
            else:
                ln = i - son_dn - 1 if son_dn >= 0 else 1
                ln = ln if ln > 0 else 1
                v = h[i - ln + 1:i + 1].max()
                j = i - int(np.flatnonzero(h[i - ln + 1:i + 1][::-1] == v)[0])
                H.append(v); HI.append(j)
        if to_up[i]:
            son_up = i
        if to_dn[i]:
            son_dn = i
        if len(H) < 2 or len(L) < 2:
            continue
        h0, h1, h0i, h1i = H[-1], H[-2], HI[-1], HI[-2]
        l0, l1, l0i, l1i = L[-1], L[-2], LI[-1], LI[-2]
        l0i_g[i], h0i_g[i] = l0i, h0i
        if (son_l0 is not None and son_l0 == l0) or (son_h0 is not None and son_h0 == h0):
            continue
        yeni = market
        if market == 1 and l0 < l1 and l0 < l1 - abs(h0 - l1) * FIB:
            yeni = -1
        elif market == -1 and h0 > h1 and h0 > h1 + abs(h1 - l0) * FIB:
            yeni = 1
        if yeni == market:
            continue
        market, son_l0, son_h0 = yeni, l0, h0
        l0i9 = l0i_g[i - ZZ] if i >= ZZ and l0i_g[i - ZZ] >= 0 else l0i
        h0i9 = h0i_g[i - ZZ] if i >= ZZ and h0i_g[i - ZZ] >= 0 else h0i

        def son_mum(a, b, dusus):
            rng = range(a, b + 1) if a <= b else range(a, b - 1, -1)
            sec = -1
            for k in rng:
                if 0 <= k <= i and ((o[k] > c[k]) if dusus else (o[k] < c[k])):
                    sec = k
            return sec
        if market == 1:
            ob = son_mum(h1i, l0i9, True)
            bb = son_mum(l1i - ZZ, h1i, False)
            bb_tur = "BB" if l0 < l1 else "MB"
        else:
            ob = son_mum(l1i, h0i9, False)
            bb = son_mum(h1i - ZZ, l1i, True)
            bb_tur = "BB" if h0 > h1 else "MB"
        olaylar.append(dict(i=i, yon=market, h0=h0, l0=l0, ob=ob, bb=bb, bb_tur=bb_tur))
    return olaylar




def etiketle(yon, E0, hemen, stop_tur, alt_ust, swing, yapi, a_, hedef, a0, c1, M, spr):
    """donus: (R, sonuc, giris_dk, cikis_dk, hedef_kat, spread_maliyet_$) ya da None (islem yok)"""
    T, H, L, O, C = M
    sp = spr
    nM = len(T)
    if yon > 0:
        if hemen:
            f, E = a0, O[a0] + sp[a0]
        else:
            E = E0
            f = ilk(lambda k, e: L[k:e] + sp[k:e] <= E, a0, c1)
            if f < 0:
                return None
        S = alt_ust - 0.1 * a_ if stop_tur == "KUTU" else (swing - 0.1 * a_ if stop_tur == "SWING" else E - a_)
        r = E - S
    else:
        if hemen:
            f, E = a0, O[a0]
        else:
            E = E0
            f = ilk(lambda k, e: H[k:e] >= E, a0, c1)
            if f < 0:
                return None
        S = alt_ust + 0.1 * a_ if stop_tur == "KUTU" else (swing + 0.1 * a_ if stop_tur == "SWING" else E + a_)
        r = S - E
    if not r > 0:
        return None
    if hedef == "2R":
        TP = E + yon * 2 * r
    elif hedef == "3R":
        TP = E + yon * 3 * r
    else:
        if not (yon * (yapi - E) > 0):
            return None
        TP = yapi if abs(yapi - E) <= MAX_R * r else E + yon * MAX_R * r
    maliyet = RISK * sp[f] / r
    if maliyet > SPREAD_SINIR + 1e-9:
        return ("ATLA", maliyet)
    if not hemen:
        if yon > 0:
            t0 = ilk(lambda k, e: H[k:e] >= TP, a0, f + 1)
        else:
            t0 = ilk(lambda k, e: L[k:e] + sp[k:e] <= TP, a0, f + 1)
        if t0 >= 0:
            return None
    if yon > 0:
        s0 = ilk(lambda k, e: L[k:e] <= S, f, nM)
        h0 = ilk(lambda k, e: H[k:e] >= TP, f + 1, nM)
    else:
        s0 = ilk(lambda k, e: H[k:e] + sp[k:e] >= S, f, nM)
        h0 = ilk(lambda k, e: L[k:e] + sp[k:e] <= TP, f + 1, nM)
    if s0 >= 0 and (h0 < 0 or s0 <= h0):
        R, son, cik = -1.0, "STOP", s0
    elif h0 >= 0:
        R, son, cik = abs(TP - E) / r, "TP", h0
    else:
        cik = nM - 1
        cikis = C[cik] if yon > 0 else C[cik] + sp[cik]
        R, son = yon * (cikis - E) / r, "SON"
    return (R, son, int(T[f]), int(T[cik]), abs(TP - E) / r, maliyet)


def sembol_isle(s, ayar, d, m1, nokta, bas_ts, kayit):
    tad, kutu_sec, giris_sec, stop_sec, hedef_sec = ayar
    K = TF_DK[tad]
    T = m1["time"].to_numpy(np.int64) // 60
    M = (T, m1["high"].to_numpy(float), m1["low"].to_numpy(float), m1["open"].to_numpy(float), m1["close"].to_numpy(float))
    SP = m1["spread"].to_numpy(float) * nokta
    SIFIR = np.zeros(len(T))
    son_ts = int(T[-1])
    bt = d["time"].to_numpy(np.int64) // 60
    o, h, l, c = [d[k].to_numpy(float) for k in ("open", "high", "low", "close")]
    tr = np.r_[h[0] - l[0], np.maximum(h[1:] - l[1:], np.maximum(np.abs(h[1:] - c[:-1]), np.abs(l[1:] - c[:-1])))]
    atr = pd.Series(tr).rolling(14, min_periods=1).mean().to_numpy()
    olaylar = gosterge(o, h, l, c)
    for z, ev in enumerate(olaylar):
        i, yon = ev["i"], ev["yon"]
        Td = int(bt[i] + K)
        if Td < bas_ts or Td >= son_ts:
            continue
        ters = [e2 for e2 in olaylar[z + 1:] if e2["yon"] != yon]
        ters_ts = int(bt[ters[0]["i"]] + K) if ters else son_ts
        idx = ev["ob"] if kutu_sec == "OB" else (ev["bb"] if ev["bb_tur"] == kutu_sec else -1)
        if idx < 0:
            continue
        ust, alt = h[idx], l[idx]
        if not ust > alt:
            continue
        if yon > 0:
            if c[i] < alt:
                continue
            E0 = ust if giris_sec == "KENAR" else (ust + alt) / 2.0
            hemen = c[i] <= E0
            kir = np.flatnonzero(c[i + 1:] < alt)
            uc, swing, yapi = alt, ev["l0"], ev["h0"]
        else:
            if c[i] > ust:
                continue
            E0 = alt if giris_sec == "KENAR" else (ust + alt) / 2.0
            hemen = c[i] >= E0
            kir = np.flatnonzero(c[i + 1:] > ust)
            uc, swing, yapi = ust, ev["h0"], ev["l0"]
        kir_ts = int(bt[i + 1 + kir[0]] + K) if kir.size else son_ts
        iptal = min(kir_ts, ters_ts, son_ts)
        a0 = int(np.searchsorted(T, Td, side="left"))
        c1 = int(np.searchsorted(T, iptal, side="left"))
        if a0 >= len(T) or a0 >= c1:
            continue
        for mod, spr in (("SPREAD", SP), ("SPREADSIZ", SIFIR)):
            sonuc = etiketle(yon, E0, hemen, stop_sec, uc, swing, yapi, atr[i], hedef_sec, a0, c1, M, spr)
            if sonuc is None:
                continue
            if sonuc[0] == "ATLA":
                kayit.append((s, mod, "AL" if yon > 0 else "SAT", np.nan, "ATLANDI", Td, Td, np.nan, round(sonuc[1], 2)))
                continue
            R, son, gdk, cdk, hk, mal = sonuc
            kayit.append((s, mod, "AL" if yon > 0 else "SAT", round(R, 4), son, gdk, cdk, round(hk, 3), round(mal, 2)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ay", type=float, default=3.0)
    ap.add_argument("--cikti", default="")
    args = ap.parse_args()
    if mt5 is None:
        sys.exit("MetaTrader5 modulu yok:  py -3.8 -m pip install MetaTrader5")
    if not mt5.initialize():
        sys.exit("MT5 baglantisi kurulamadi: %s" % (mt5.last_error(),))
    hs = mt5.account_info()
    print("MT5 bagli: %s  (sadece gecmis veri, islem acilmiyor)" % (hs.server if hs else "?"))
    simdi = datetime.now(timezone.utc).replace(tzinfo=None)
    tbas = simdi - timedelta(days=30.4 * args.ay)
    bit = simdi + timedelta(days=1)
    bas_ts = int((tbas - datetime(1970, 1, 1)).total_seconds() // 60) + 120
    klasor = args.cikti or ("msb_ob_23_spread_%s" % datetime.now().strftime("%Y%m%d_%H%M"))
    if not os.path.isdir(klasor):
        os.makedirs(klasor)
    yaz = dict(sep=";", decimal=",", index=False, encoding="utf-8-sig")
    tfk = {"5dk": mt5.TIMEFRAME_M5, "15dk": mt5.TIMEFRAME_M15}
    kayit, yok = [], []
    for n, (s, ayar) in enumerate(LISTE.items(), 1):
        if not mt5.symbol_select(s, True):
            yok.append(s); continue
        bilgi = mt5.symbol_info(s)
        nokta = getattr(bilgi, "point", 0.0) if bilgi is not None else 0.0
        if not nokta:
            nokta = getattr(bilgi, "trade_tick_size", 0.0) or 0.0
        m1 = cek(s, mt5.TIMEFRAME_M1, tbas - timedelta(days=1), bit, 15, spread=True)
        d = cek(s, tfk[ayar[0]], tbas - timedelta(days=ISINMA[ayar[0]]), bit, 200)
        if m1 is None or d is None or len(m1) < 5000 or len(d) < 100:
            yok.append(s); continue
        n0 = len(kayit)
        sembol_isle(s, ayar, d, m1, nokta, bas_ts, kayit)
        print("[%d/%d] %s : %d kayit" % (n, len(LISTE), s, len(kayit) - n0))
    mt5.shutdown()
    df = pd.DataFrame(kayit, columns=["sembol", "mod", "yon", "R", "sonuc", "giris_dk", "cikis_dk", "hedef_kat", "spread_maliyet"])
    df["dolar"] = (df["R"] * RISK).round(2)
    df["tarih"] = pd.to_datetime(df["cikis_dk"] * 60, unit="s").dt.strftime("%Y-%m-%d")
    df.to_csv(os.path.join(klasor, "1_islemler.csv"), **yaz)

    def ozet(x):
        y = x[x["sonuc"] != "ATLANDI"]
        n = len(y)
        return dict(islem=n, TP=int((y["sonuc"] == "TP").sum()), STOP=int((y["sonuc"] == "STOP").sum()),
                    SON=int((y["sonuc"] == "SON").sum()), atlanan=int((x["sonuc"] == "ATLANDI").sum()),
                    basari=100.0 * (y["R"] > 0).mean() if n else 0.0, dolar=float(y["dolar"].sum()),
                    hedef=float(y["hedef_kat"].mean()) if n else 0.0, spread=float(y["spread_maliyet"].mean()) if n else 0.0)
    m = []
    m.append("=" * 120)
    m.append("MSB-OB 23 SEMBOL - SON %.0f AY - SPREAD DAHIL (spread maliyeti %.0f $'i gecen islem acilmaz) - islem basi %.0f $ risk"
             % (args.ay, SPREAD_SINIR, RISK))
    m.append("=" * 120)
    m.append("%-10s | %-38s | %-50s | %s" % ("", "SPREAD'SIZ", "SPREAD DAHIL", ""))
    m.append("%-10s | %5s %7s %10s %12s | %5s %4s %4s %4s %7s %10s %6s %8s | %s" % (
        "SEMBOL", "ISLEM", "BASARI", "DOLAR", "", "ISLEM", "TP", "STOP", "SON", "BASARI", "DOLAR", "HEDEF", "ATLANAN", "BIRLESIM"))
    satirlar = []
    for s, ayar in LISTE.items():
        x = df[df["sembol"] == s]
        if not len(x):
            continue
        a, b = ozet(x[x["mod"] == "SPREADSIZ"]), ozet(x[x["mod"] == "SPREAD"])
        satirlar.append((b["dolar"], "%-10s | %5d %%%6.1f %+10.2f %12s | %5d %4d %4d %4d %%%6.1f %+10.2f %5.2fR %8d | %s" % (
            s, a["islem"], a["basari"], a["dolar"], "", b["islem"], b["TP"], b["STOP"], b["SON"], b["basari"], b["dolar"],
            b["hedef"], b["atlanan"], "TF=%s KUTU=%s GIRIS=%s STOP=%s HEDEF=%s" % ayar)))
    for _, t in sorted(satirlar, key=lambda v: -v[0]):
        m.append(t)
    for mod, ad in (("SPREADSIZ", "SPREAD'SIZ"), ("SPREAD", "SPREAD DAHIL")):
        x = df[(df["mod"] == mod) & (df["sonuc"] != "ATLANDI")]
        o = ozet(df[df["mod"] == mod])
        gun = x.groupby("tarih")["dolar"].sum().sort_index()
        bak = BASLANGIC + gun.cumsum()
        dd = float((bak - np.maximum.accumulate(np.r_[BASLANGIC, bak.to_numpy()])[1:]).min()) if len(gun) else 0.0
        kz = x[x["R"] > 0]
        m.append("")
        m.append("-- %s: 10.000 $ ILE 3 AY --" % ad)
        m.append("   Bitis bakiyesi : %.2f $   (net %+.2f $)" % (BASLANGIC + o["dolar"], o["dolar"]))
        m.append("   Islem          : %d  (TP %d / STOP %d / SON %d)   basari %%%.1f   | spread yuzunden acilmayan: %d"
                 % (o["islem"], o["TP"], o["STOP"], o["SON"], o["basari"], o["atlanan"]))
        m.append("   Hedef ortalama stopun %.2f kati (1'e %.2f) | kazanan islem ort. %.2fR = %.2f $ | islem basina %+.2fR = %+.2f $"
                 % (o["hedef"], o["hedef"], kz["R"].mean() if len(kz) else 0, (kz["R"].mean() if len(kz) else 0) * RISK,
                    x["R"].mean() if len(x) else 0, (x["R"].mean() if len(x) else 0) * RISK))
        m.append("   En kotu gun    : %+.2f $   | en buyuk dusus: %+.2f $ (kapanan islemlere gore)" % (
            gun.min() if len(gun) else 0.0, dd))
        if mod == "SPREAD":
            m.append("   Ortalama spread maliyeti: %.2f $ / islem (stop 15 $)" % o["spread"])
    if yok:
        m.append("")
        m.append("Bulunamayan / verisi olmayan: " + ", ".join(yok))
    m.append("")
    m.append("ATLANAN = spread maliyeti %.0f $'i gectigi icin acilmayan islem.  Gunluk limit uygulanmadi." % SPREAD_SINIR)
    ms = "\n".join(m)
    print("\n" + ms)
    with open(os.path.join(klasor, "0_OZET.txt"), "w", encoding="utf-8") as fh:
        fh.write(ms + "\n")
    print("\nDosyalar: %s" % os.path.abspath(klasor))


if __name__ == "__main__":
    main()
