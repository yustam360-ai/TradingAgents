# -*- coding: utf-8 -*-
"""
MSB-OB TESTI - EmreKb "Market Structure Break & Order Block" gostergesi, BUTUN semboller, son 3 ay
==================================================================================================
Python 3.8:   py -3.8 msb_ob_test_3ay.py
Gerekli:      py -3.8 -m pip install MetaTrader5 pandas numpy

MT5'e baglanir, SADECE gecmis veri okur, ISLEM ACMAZ.  SPREAD / MAKAS / KOMISYON YOK.
Islem basi sabit 15 $ risk: stop olursa -15 $, kazanc = (TP mesafesi / stop mesafesi) x 15 $.

GOSTERGE (koddaki gibi): ZigZag 9, Fib Factor 0.273.
  - Zigzag: mum son 9 mumun en yuksegine cikarsa yukari, en dusugune inerse asagi; yon donunce son
    tepe/dip kaydedilir (h0, h1 = son iki tepe; l0, l1 = son iki dip).
  - MSB yukari: h0 > h1 + (h1 - l0) x 0.273.   MSB asagi: l0 < l1 - (h0 - l1) x 0.273.
  - Bu-OB: h1 ile l0 arasindaki son dusus mumu.  Be-OB: l1 ile h0 arasindaki son yukselis mumu.
  - Bu-BB / Bu-MB: l1 ile h1 arasindaki son yukselis mumu (l0 < l1 ise BB = dip supurulmus, degilse MB).
    Be-BB / Be-MB: h1 ile l1 arasindaki son dusus mumu (h0 > h1 ise BB, degilse MB).
  - Kutu, fiyat kutunun obur ucunun otesinde KAPANINCA kirilmis sayilir.

ISLEM (alis anlatiliyor, satis tersi):
  MSB'yi yapan mum kapaninca kutuya ALIS LIMIT konur.  Fiyat zaten kutunun icindeyse hemen alinir.
  Emir silinir: kutu kirilirsa, ters yonde MSB olursa ya da fiyat emir dolmadan hedefe ulasirsa.
  Her kutuda tek islem.
DENENENLER:
  ZAMAN DILIMI : 5 dk / 15 dk / 1 saat / 4 saat
  KUTU         : OB / BB / MB
  GIRIS        : KENAR (kutunun ust kenari) / ORTA (kutunun %50'si, "mean threshold")
  STOP         : KUTU (kutunun dibi - 0.1 ATR) / SWING (son dip l0 - 0.1 ATR) / ATR (giris - 1 ATR)
  HEDEF        : YAPI (yapiyi kiran tepe h0, en fazla 5R) / 2R / 3R
  Toplam 4 x 3 x 2 x 3 x 3 = 216 birlesim.
1 dk takip: ayni dakikada stop ve hedef = STOP; dolum dakikasinda hedef sayilmaz.  Test sonunda acik
kalan islem son fiyattan kapatilir (SON).

CIKTI (msb_ob_<tarih>/):
  0_OZET.txt   en iyi birlesimler, en iyinin sembol sonuclari, her sembolun kendi en iyisi,
               en altta basarisi %50'nin ustundeki semboller ve 10.000 $ hesabin sonucu
  1_birlesimler.csv, 2_sembol_en_iyi.csv, 3_islemler_50ustu.csv
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
BASLANGIC = 10000.0
ZZ = 9
FIB = 0.273
MAX_R = 5.0
TF_LISTE = [("5dk", 5, 20), ("15dk", 15, 40), ("1saat", 60, 120), ("4saat", 240, 400)]   # ad, dakika, isinma gunu
KUTULAR = ["OB", "BB", "MB"]
GIRISLER = ["KENAR", "ORTA"]
STOPLAR = ["KUTU", "SWING", "ATR"]
HEDEFLER = ["YAPI", "2R", "3R"]
PARCA = 4096


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


def ilk_ge(arr, bas, bit, x):
    """arr[k] >= x olan ilk k (bas <= k < bit), yoksa -1"""
    k = bas
    while k < bit:
        e = min(k + PARCA, bit)
        z = np.flatnonzero(arr[k:e] >= x)
        if z.size:
            return k + int(z[0])
        k = e
    return -1


def ilk_le(arr, bas, bit, x):
    k = bas
    while k < bit:
        e = min(k + PARCA, bit)
        z = np.flatnonzero(arr[k:e] <= x)
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


def sembol_isle(s, veriler, m1, bas_ts, son_ts, kayit):
    Tm = m1["time"].to_numpy(np.int64) // 60
    Hm, Lm, Om, Cm = [m1[k].to_numpy(float) for k in ("high", "low", "open", "close")]
    gor = {1: (Hm, Lm, Om, Cm), -1: (-Lm, -Hm, -Om, -Cm)}
    nM = len(Tm)
    for tad, K, _ in TF_LISTE:
        d = veriler.get(tad)
        if d is None or len(d) < 100:
            continue
        bt = d["time"].to_numpy(np.int64) // 60
        o, h, l, c = [d[k].to_numpy(float) for k in ("open", "high", "low", "close")]
        tr = np.r_[h[0] - l[0], np.maximum(h[1:] - l[1:], np.maximum(np.abs(h[1:] - c[:-1]), np.abs(l[1:] - c[:-1])))]
        atr = pd.Series(tr).rolling(14, min_periods=1).mean().to_numpy()
        olaylar = gosterge(o, h, l, c)
        for z, ev in enumerate(olaylar):
            i, yon = ev["i"], ev["yon"]
            Td = int(bt[i] + K)                                  # MSB mumunun kapanisi
            if Td < bas_ts or Td >= son_ts:
                continue
            ters = [e2 for e2 in olaylar[z + 1:] if e2["yon"] != yon]
            ters_ts = int(bt[ters[0]["i"]] + K) if ters else son_ts
            Hv, Lv, Ov, Cv = gor[yon]
            for kutu_ad, idx in (("OB", ev["ob"]), (ev["bb_tur"], ev["bb"])):
                if idx < 0:
                    continue
                if yon == 1:
                    ust, alt, swing, yapi, cv = h[idx], l[idx], ev["l0"], ev["h0"], c
                else:
                    ust, alt, swing, yapi, cv = -l[idx], -h[idx], -ev["h0"], -ev["l0"], -c
                if not ust > alt or cv[i] < alt:
                    continue
                kir = np.flatnonzero(cv[i + 1:] < alt)                 # kutu kirildi (kapanis)
                kir_ts = int(bt[i + 1 + kir[0]] + K) if kir.size else son_ts
                iptal = min(kir_ts, ters_ts, son_ts)
                a0 = int(np.searchsorted(Tm, Td, side="left"))
                c1 = int(np.searchsorted(Tm, iptal, side="left"))
                if a0 >= nM or a0 >= c1:
                    continue
                a_ = atr[i]
                for gi, gad in enumerate(GIRISLER):
                    E0 = ust if gad == "KENAR" else (ust + alt) / 2.0
                    hemen = cv[i] <= E0
                    for si, sad in enumerate(STOPLAR):
                        for hi_, had in enumerate(HEDEFLER):
                            if hemen:
                                f, E = a0, Ov[a0]
                            else:
                                E = E0
                                f = ilk_le(Lv, a0, c1, E)
                                if f < 0:
                                    continue
                            S = alt - 0.1 * a_ if sad == "KUTU" else (swing - 0.1 * a_ if sad == "SWING" else E - a_)
                            r = E - S
                            if not r > 0:
                                continue
                            if had == "2R":
                                TP = E + 2 * r
                            elif had == "3R":
                                TP = E + 3 * r
                            else:
                                if not yapi > E:
                                    continue
                                TP = min(yapi, E + MAX_R * r)
                            if not hemen:
                                t0 = ilk_ge(Hv, a0, f + 1, TP)            # emir dolmadan hedefe ulasti
                                if t0 >= 0:
                                    continue
                            s0 = ilk_le(Lv, f, nM, S)
                            h0_ = ilk_ge(Hv, f + 1, nM, TP)
                            if s0 >= 0 and (h0_ < 0 or s0 <= h0_):
                                R, son, cik = -1.0, "STOP", s0
                            elif h0_ >= 0:
                                R, son, cik = (TP - E) / r, "TP", h0_
                            else:
                                R, son, cik = (Cv[nM - 1] - E) / r, "SON", nM - 1
                            kayit.append((s, tad, kutu_ad, gad, sad, had, "AL" if yon == 1 else "SAT",
                                          int(Tm[f]), int(Tm[cik]), round(R, 4), son, round((TP - E) / r, 3)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ay", type=float, default=3.0)
    ap.add_argument("--min-islem", type=int, default=100, help="birlesim siralamasi icin en az islem")
    ap.add_argument("--min-islem-sembol", type=int, default=10, help="sembolun kendi en iyisi icin en az islem")
    ap.add_argument("--sembol", default="", help="sadece bu semboller (virgulle); bos = butun semboller")
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
    bas_ts = int((tbas - datetime(1970, 1, 1)).total_seconds() // 60) + 120     # sunucu ~ UTC+2
    semboller = ([x.strip() for x in args.sembol.split(",") if x.strip()] if args.sembol
                 else [x.name for x in (mt5.symbols_get() or [])])
    klasor = args.cikti or ("msb_ob_%s" % datetime.now().strftime("%Y%m%d_%H%M"))
    if not os.path.isdir(klasor):
        os.makedirs(klasor)
    yaz = dict(sep=";", decimal=",", index=False, encoding="utf-8-sig")
    tfk = {"5dk": mt5.TIMEFRAME_M5, "15dk": mt5.TIMEFRAME_M15, "1saat": mt5.TIMEFRAME_H1, "4saat": mt5.TIMEFRAME_H4}
    print("Sembol: %d | %s -> bugun | 216 birlesim | islem basi %.0f $ risk" % (len(semboller), tbas.strftime("%Y-%m-%d"), RISK))
    kayit, yok, t0 = [], [], time.time()
    for n, s in enumerate(semboller, 1):
        if not mt5.symbol_select(s, True):
            yok.append(s); print("[%d/%d] %s : sembol yok" % (n, len(semboller), s)); continue
        m1 = cek(s, mt5.TIMEFRAME_M1, tbas - timedelta(days=1), bit, 15)
        if m1 is None or len(m1) < 5000:
            yok.append(s); print("[%d/%d] %s : veri yok" % (n, len(semboller), s)); continue
        son_ts = int(m1["time"].iloc[-1] // 60)
        veriler = {}
        for tad, K, isinma in TF_LISTE:
            veriler[tad] = cek(s, tfk[tad], tbas - timedelta(days=isinma), bit, 200)
        n0 = len(kayit)
        sembol_isle(s, veriler, m1, bas_ts, son_ts, kayit)
        print("[%d/%d] %s : %d islem  (%.0f sn)" % (n, len(semboller), s, len(kayit) - n0, time.time() - t0))
    mt5.shutdown()
    if not kayit:
        sys.exit("Hic islem yok.")

    df = pd.DataFrame(kayit, columns=["sembol", "tf", "kutu", "giris", "stop", "hedef", "yon", "giris_ts", "cikis_ts",
                                      "R", "sonuc", "hedef_kat"])
    df["dolar"] = (df["R"] * RISK).round(2)
    df["birlesim"] = ("TF=" + df["tf"] + " | KUTU=" + df["kutu"] + " | GIRIS=" + df["giris"] + " | STOP=" + df["stop"]
                      + " | HEDEF=" + df["hedef"])
    orta = (df["giris_ts"].min() + df["giris_ts"].max()) / 2.0
    df["yari"] = np.where(df["giris_ts"] < orta, 1, 2)
    df["tarih"] = pd.to_datetime(df["cikis_ts"] * 60, unit="s").dt.strftime("%Y-%m-%d")

    def ozet(x):
        n = len(x)
        kz = x[x["R"] > 0]
        return pd.Series(dict(islem=n, TP=int((x["sonuc"] == "TP").sum()), STOP=int((x["sonuc"] == "STOP").sum()),
                              SON=int((x["sonuc"] == "SON").sum()),
                              basari=round(100.0 * (x["R"] > 0).mean(), 1) if n else 0.0,
                              net_R=round(x["R"].sum(), 1), dolar=round(x["dolar"].sum(), 2),
                              ort_hedef_kat=round(x["hedef_kat"].mean(), 2) if n else 0.0,
                              ort_kazanc_R=round(kz["R"].mean(), 2) if len(kz) else 0.0,
                              yari1_R=round(x.loc[x["yari"] == 1, "R"].sum(), 1),
                              yari2_R=round(x.loc[x["yari"] == 2, "R"].sum(), 1)))
    db = df.groupby("birlesim").apply(ozet).reset_index().sort_values("dolar", ascending=False)
    db.to_csv(os.path.join(klasor, "1_birlesimler.csv"), **yaz)
    uy = db[db["islem"] >= args.min_islem]

    m = []
    m.append("=" * 130)
    m.append("MSB-OB TESTI - son %.0f ay, %d sembol, 216 birlesim, spread yok, islem basi %.0f $ risk (stop = -%.0f $)"
             % (args.ay, len(semboller) - len(yok), RISK, RISK))
    m.append("=" * 130)
    bas = "%6s %5s %5s %4s %7s %8s %10s %6s %7s %7s  %s" % ("ISLEM", "TP", "STOP", "SON", "BASARI", "NET R", "DOLAR",
                                                           "HEDEF", "1.YARI", "2.YARI", "BIRLESIM")

    def satir(r):
        return "%6d %5d %5d %4d %%%6.1f %+8.1f %+10.2f %5.2fR %+7.1f %+7.1f  %s" % (
            r["islem"], r["TP"], r["STOP"], r["SON"], r["basari"], r["net_R"], r["dolar"], r["ort_hedef_kat"],
            r["yari1_R"], r["yari2_R"], r["birlesim"])
    m.append("")
    m.append("-- EN COK KAZANDIRAN 20 BIRLESIM (en az %d islem) --" % args.min_islem)
    m.append(bas)
    for _, r in uy.sort_values("dolar", ascending=False).head(20).iterrows():
        m.append(satir(r))
    m.append("")
    m.append("-- EN BASARILI 20 BIRLESIM (en az %d islem) --" % args.min_islem)
    m.append(bas)
    for _, r in uy.sort_values(["basari", "dolar"], ascending=False).head(20).iterrows():
        m.append(satir(r))

    if len(uy):
        en = uy.iloc[0]
        x = df[df["birlesim"] == en["birlesim"]]
        m.append("")
        m.append("=" * 130)
        m.append("EN COK KAZANDIRAN BIRLESIM: %s" % en["birlesim"])
        m.append("Baslangic %.0f $ -> bitis %.2f $ (net %+.2f $) | %d islem, basari %%%.1f" % (
            BASLANGIC, BASLANGIC + en["dolar"], en["dolar"], en["islem"], en["basari"]))
        m.append("-- bu birlesimde sembol sembol --")
        m.append("%-12s %5s %4s %4s %4s %7s %10s" % ("SEMBOL", "ISLEM", "TP", "STOP", "SON", "BASARI", "DOLAR"))
        for s_, y in sorted(x.groupby("sembol"), key=lambda v: -v[1]["dolar"].sum()):
            o_ = ozet(y)
            m.append("%-12s %5d %4d %4d %4d %%%6.1f %+10.2f" % (s_, o_["islem"], o_["TP"], o_["STOP"], o_["SON"],
                                                              o_["basari"], o_["dolar"]))

    # her sembolun kendi en iyi birlesimi
    ds = df.groupby(["sembol", "birlesim"]).apply(ozet).reset_index()
    ds = ds[ds["islem"] >= args.min_islem_sembol].sort_values("dolar", ascending=False)
    se = ds.groupby("sembol").head(1).sort_values("dolar", ascending=False)
    se.to_csv(os.path.join(klasor, "2_sembol_en_iyi.csv"), **yaz)
    m.append("")
    m.append("=" * 130)
    m.append("-- HER SEMBOLUN KENDI EN IYI BIRLESIMI (en az %d islem) --" % args.min_islem_sembol)
    m.append("%-12s %5s %4s %4s %4s %7s %10s %6s  %s" % ("SEMBOL", "ISLEM", "TP", "STOP", "SON", "BASARI", "DOLAR",
                                                        "HEDEF", "BIRLESIM"))
    for _, r in se.iterrows():
        m.append("%-12s %5d %4d %4d %4d %%%6.1f %+10.2f %5.2fR  %s" % (r["sembol"], r["islem"], r["TP"], r["STOP"], r["SON"],
                                                                     r["basari"], r["dolar"], r["ort_hedef_kat"],
                                                                     r["birlesim"]))
    if yok:
        m.append("")
        m.append("Bulunamayan / verisi olmayan sembol: " + ", ".join(yok))

    # en altta: basarisi %50'nin ustundeki semboller ve 10.000 $ hesap
    ust = se[se["basari"] > 50.0].sort_values("basari", ascending=False)
    m.append("")
    m.append("=" * 130)
    m.append("-- BASARISI %%50'NIN USTUNDE OLAN SEMBOLLER (kendi en iyi birlesimiyle): %d adet --" % len(ust))
    m.append("%-12s %5s %4s %4s %4s %7s %10s %6s  %s" % ("SEMBOL", "ISLEM", "TP", "STOP", "SON", "BASARI", "DOLAR",
                                                        "HEDEF", "BIRLESIM"))
    for _, r in ust.iterrows():
        m.append("%-12s %5d %4d %4d %4d %%%6.1f %+10.2f %5.2fR  %s" % (r["sembol"], r["islem"], r["TP"], r["STOP"], r["SON"],
                                                                     r["basari"], r["dolar"], r["ort_hedef_kat"],
                                                                     r["birlesim"]))
    if len(ust):
        sec = pd.concat([df[(df["sembol"] == r["sembol"]) & (df["birlesim"] == r["birlesim"])] for _, r in ust.iterrows()])
        sec.sort_values("cikis_ts").to_csv(os.path.join(klasor, "3_islemler_50ustu.csv"), **yaz)
        gun = sec.groupby("tarih")["dolar"].sum().sort_index()
        bak = BASLANGIC + gun.cumsum()
        dd = float((bak - np.maximum.accumulate(np.r_[BASLANGIC, bak.to_numpy()])[1:]).min()) if len(gun) else 0.0
        kz = sec[sec["R"] > 0]
        m.append("")
        m.append("10.000 $ ILE BU %d SEMBOL (her biri kendi birlesimiyle, islem basi 15 $ risk) 3 AY ISLEM YAPSAYDI:" % len(ust))
        m.append("   Bitis bakiyesi : %.2f $   (net %+.2f $)" % (BASLANGIC + sec["dolar"].sum(), sec["dolar"].sum()))
        m.append("   Islem          : %d  (TP %d / STOP %d / SON %d)  basari %%%.1f" % (
            len(sec), int((sec["sonuc"] == "TP").sum()), int((sec["sonuc"] == "STOP").sum()),
            int((sec["sonuc"] == "SON").sum()), 100.0 * (sec["R"] > 0).mean()))
        m.append("   En kotu gun    : %+.2f $   | en buyuk dusus: %+.2f $ (kapanan islemlere gore)" % (
            gun.min() if len(gun) else 0.0, dd))
        m.append("")
        m.append("ACIKLAMA: Stop olunca 15 $ kaybedilir.  Hedef ortalama stopun %.2f kati uzakta (yani 1'e %.2f);"
                 % (sec["hedef_kat"].mean(), sec["hedef_kat"].mean()))
        m.append("   kazanan islem ortalama %.2fR = %.2f $ kazandirdi.  Islem basina ortalama %+.2fR = %+.2f $."
                 % (kz["R"].mean() if len(kz) else 0.0, (kz["R"].mean() if len(kz) else 0.0) * RISK,
                    sec["R"].mean(), sec["R"].mean() * RISK))
    m.append("")
    m.append("Not: her sembol 216 birlesim icinden kendi en iyisini %d+ islemle secti; bu liste sansla da iyi gorunebilir."
             % args.min_islem_sembol)
    m.append("Gunluk limit uygulanmadi.  1.YARI / 2.YARI: 3 ayin iki yarisindaki net R; iyi birlesim iki yarida da artida olmali.")
    ms = "\n".join(m)
    print("\n" + ms)
    with open(os.path.join(klasor, "0_OZET.txt"), "w", encoding="utf-8") as fh:
        fh.write(ms + "\n")
    print("\nDosyalar: %s" % os.path.abspath(klasor))


if __name__ == "__main__":
    main()
