# -*- coding: utf-8 -*-
"""
EMA CROSS (TradingView, 10/20 EMA kesisimi) - 2026 BASINDAN BUGUNE - BUTUN SEMBOLLER
=====================================================================================
Calistir:   py -3.8 C:\\Users\\User\\Desktop\\ema_cross_2026.py
Gerekli:    py -3.8 -m pip install MetaTrader5 pandas numpy
Sadece bazi semboller:   py -3.8 ema_cross_2026.py --sembol XAUUSD,EURUSD
MT5 acik olmali. SADECE gecmis veri okur, ISLEM ACMAZ.
Sonuclar MASAUSTUNE:  Masaustu\\ema_cross_2026_<tarih>\\0_OZET.txt (kisa) , 1_semboller.csv

1 OCAK 2026'da 10.000 $ ile baslasaydi. (2025 sonu verisi sadece EMA'larin isinmasi icin.)
MANTIK (LONG; SHORT tersi)
  10 EMA, 20 EMA'yi yukari keser -> kesisim mumu KAPANINCA, bir sonraki mumun acilisinda LONG.
  (TradingView "EMA Cross Strategy" kodundaki kesisim. Yon filtresi YOK.)
ZAMAN DILIMI: 15 DK / 1 SAAT / 4 SAAT
STOP / HEDEF (ATR = 14 mumluk ortalama mum boyu)
  A : stop 1 ATR , hedef 2 ATR  (1:2)
  B : stop 1 ATR , hedef 3 ATR  (1:3)
  C : stop 2 ATR , hedef YOK - ters kesisimde (10 EMA 20'yi tersine kesince) cikis
RISK: islem basina 100 $ (10.000 $'in %1'i).  Spread maliyeti 6 $'i gecen islem acilmaz; spread dahil.
Ayni stop mumunda hem stop hem hedef olursa STOP sayilir.  Acik kalan islem sayilmaz.
"""
from __future__ import print_function

import argparse
import os
import time
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

try:
    import MetaTrader5 as mt5
except ImportError:
    mt5 = None

BASLA = datetime(2026, 1, 1)
SERMAYE = 10000.0
RISK = 100.0
MAKAS_DOLAR = 6.0
ZD = [("15DK", "TIMEFRAME_M15", 20), ("1SAAT", "TIMEFRAME_H1", 40), ("4SAAT", "TIMEFRAME_H4", 90)]
SIKLAR = {"A": (1.0, 2.0), "B": (1.0, 3.0), "C": (2.0, None)}
MIN_ISLEM = 20


def masaustu():
    ev = os.path.expanduser("~")
    for p in (os.path.join(ev, "Desktop"), os.path.join(ev, "OneDrive", "Desktop"), os.path.join(ev, "Masaüstü")):
        if os.path.isdir(p):
            return p
    return os.getcwd()


def cek(sembol, tf, bas, bit):
    out, a = [], bas
    while a < bit:
        b = min(a + timedelta(days=60), bit)
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
            out.append(d[["time", "open", "high", "low", "close", "spread"]])
        a = b
    if not out:
        return None
    return pd.concat(out).drop_duplicates("time").sort_values("time").reset_index(drop=True)


def test(df, point, sinir):
    """Donus: {sik: [(giris_zamani, yon, R)]}"""
    T = df["time"].values.astype(np.int64)
    o, h, l, c = (df[k].values.astype(float) for k in ("open", "high", "low", "close"))
    sp = df["spread"].values.astype(float) * point
    s = pd.Series(c)
    e10, e20 = (s.ewm(span=n, adjust=False).mean().values for n in (10, 20))
    pc = np.r_[c[0], c[:-1]]
    atr = pd.Series(np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))).rolling(14).mean().values
    d = e10 - e20
    dp = np.r_[0.0, d[:-1]]
    yuk = (d > 0) & (dp <= 0)
    asa = (d < 0) & (dp >= 0)
    n = len(c)
    kes_idx = np.nonzero(yuk | asa)[0]
    sonuc = {k: [] for k in SIKLAR}
    for i in np.nonzero(yuk | asa)[0]:
        j = i + 1
        if i < 40 or j >= n or T[j] < sinir or not atr[i] > 0:
            continue
        y = 1 if yuk[i] else -1
        e = o[j] + (sp[j] if y > 0 else 0.0)            # long ASK, short BID
        # bid ile: long stop/hedef low/high ; short icin ask = bid + spread
        lo = l[j:] if y > 0 else -(h[j:] + sp[j:])
        hi = h[j:] if y > 0 else -(l[j:] + sp[j:])
        op = o[j:] if y > 0 else -(o[j:] + sp[j:])
        ey = y * e
        lmin, hmax = np.minimum.accumulate(lo), np.maximum.accumulate(hi)
        m = n - j
        tersi = kes_idx[(kes_idx > i) & ((yuk if y < 0 else asa)[kes_idx])]
        for sik, (sk, tk) in SIKLAR.items():
            risk = sk * atr[i]
            if RISK * sp[j] / risk > MAKAS_DOLAR:
                continue
            st = ey - risk
            isl = int(np.searchsorted(-lmin, -st, "left"))
            if tk is not None:
                tp = ey + tk * atr[i]
                itp = int(np.searchsorted(hmax, tp, "left"))
                if isl >= m and itp >= m:
                    continue
                if isl <= itp:
                    px = min(op[isl], st)
                else:
                    px = max(op[itp], tp)
            else:
                if not len(tersi) or tersi[0] + 1 >= n:
                    continue
                kx = tersi[0] + 1 - j                    # ters kesisimden sonraki mumun acilisi
                if isl < kx:
                    px = min(op[isl], st)
                else:
                    px = op[kx]
            sonuc[sik].append((int(T[j]), y, (px - ey) / risk))
    return sonuc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sembol", default="")
    a = ap.parse_args()
    if mt5 is None:
        print("MetaTrader5 paketi yok:  py -3.8 -m pip install MetaTrader5 pandas numpy")
        return
    if not mt5.initialize():
        print("MT5'e baglanilamadi. MT5 acik mi?", mt5.last_error())
        return
    t0 = time.time()
    liste = [x.strip() for x in a.sembol.split(",") if x.strip()] if a.sembol else \
        [x.name for x in (mt5.symbols_get() or []) if getattr(x, "trade_mode", 4) != 0]
    bit = datetime.now() + timedelta(days=1)
    sinir = int((BASLA - datetime(1970, 1, 1)).total_seconds())
    yari = sinir + (int(time.time()) - sinir) // 2
    S = []
    print("Taranacak sembol: %d   (1 Ocak 2026 - bugun)" % len(liste))
    for no, sb in enumerate(liste, 1):
        try:
            mt5.symbol_select(sb, True)
            bilgi = mt5.symbol_info(sb)
            if bilgi is None:
                continue
            kisa = []
            for zad, tfad, isinma in ZD:
                df = cek(sb, getattr(mt5, tfad), BASLA - timedelta(days=isinma), bit)
                if df is None or len(df) < 300:
                    continue
                for sik, lst in test(df, bilgi.point, sinir).items():
                    if not lst:
                        continue
                    R = np.array([x[2] for x in lst])
                    t = np.array([x[0] for x in lst])
                    yon = np.array([x[1] for x in lst])
                    w = int((R > 0).sum())
                    S.append(dict(sembol=sb, zaman=zad, sik=sik, islem=len(R), karli=w,
                                  basari=round(100.0 * w / len(R), 1), R=round(R.sum(), 1),
                                  dolar=round(R.sum() * RISK, 0), R_long=round(R[yon > 0].sum(), 1),
                                  R_short=round(R[yon < 0].sum(), 1), R_ilk_yari=round(R[t < yari].sum(), 1),
                                  R_son_yari=round(R[t >= yari].sum(), 1)))
                    kisa.append("%s-%s %+.0fR" % (zad.replace("SAAT", "S").replace("DK", "D"), sik, R.sum()))
            print("%3d/%d %-12s %s" % (no, len(liste), sb, " ".join(kisa)))
        except Exception as ex:
            print("%3d/%d %-12s HATA: %s" % (no, len(liste), sb, ex))
    mt5.shutdown()

    klasor = os.path.join(masaustu(), "ema_cross_2026_" + datetime.now().strftime("%Y%m%d_%H%M"))
    os.makedirs(klasor, exist_ok=True)
    S = pd.DataFrame(S)
    sat = ["EMA CROSS 10/20 (TradingView)  |  1 Ocak 2026 - %s  |  10.000 $, islem basi 100 $ risk"
           % datetime.now().strftime("%d.%m.%Y"),
           "A: stop 1 ATR hedef 2 ATR   B: stop 1 ATR hedef 3 ATR   C: stop 2 ATR, ters kesisimde cikis",
           "Basabas basari: A %%33, B %%25, C degisken.   Sure %.0f dk" % ((time.time() - t0) / 60.0)]
    if not len(S):
        sat.append("Hic islem yok.")
    else:
        S.to_csv(os.path.join(klasor, "1_semboller.csv"), index=False, sep=";", decimal=",")
        sat += ["", "1) BUTUN SEMBOLLER TOPLAMI (her zaman dilimi x sik)",
                "%-6s %-3s %7s %7s %9s %10s %9s" % ("zaman", "sik", "islem", "basari", "R", "dolar", "karli sem.")]
        top = []
        for (z, k), g in S.groupby(["zaman", "sik"]):
            n, w, R = g["islem"].sum(), g["karli"].sum(), g["R"].sum()
            top.append((z, k, R))
            sat.append("%-6s %-3s %7d %6.1f%% %+9.0f %+10.0f %5d/%-3d"
                       % (z, k, n, 100.0 * w / max(1, n), R, R * RISK, (g["R"] > 0).sum(), len(g)))
        en = max(top, key=lambda x: x[2])
        sat.append("EN IYISI: %s %s  (%+.0fR = %+.0f $)" % (en[0], en[1], en[2], en[2] * RISK))

        E = S[(S["islem"] >= MIN_ISLEM) & (S["basari"] > 50.0)].sort_values("R", ascending=False)
        sat += ["", "2) BASARI %%50 USTU (en az %d islem): %d kayit" % (MIN_ISLEM, len(E)),
                "%-12s %-6s %-3s %6s %7s %8s %8s  %s" % ("sembol", "zaman", "sik", "islem", "basari", "R", "dolar",
                                                     "ilk/son yari R")]
        for _, r in E.head(40).iterrows():
            sat.append("%-12s %-6s %-3s %6d %6.1f%% %+8.1f %+8.0f  %+.1f / %+.1f"
                       % (r["sembol"], r["zaman"], r["sik"], r["islem"], r["basari"], r["R"], r["dolar"],
                          r["R_ilk_yari"], r["R_son_yari"]))

        B = S[S["islem"] >= MIN_ISLEM].sort_values("R", ascending=False).drop_duplicates("sembol")
        B = B[B["R"] > 0]
        iki = B[(B["R_ilk_yari"] > 0) & (B["R_son_yari"] > 0)]
        sat += ["", "3) HER SEMBOLUN EN IYI ZAMAN DILIMI + SIKKI (karda olanlar, en az %d islem): %d sembol"
                % (MIN_ISLEM, len(B)),
                "   Bunlardan yilin iki yarisinda da karda olan: %d  (* ile isaretli)" % len(iki)]
        for _, r in B.head(40).iterrows():
            yildiz = "*" if (r["R_ilk_yari"] > 0 and r["R_son_yari"] > 0) else " "
            sat.append("%s %-12s %-6s %-3s %4d islem  basari %5.1f%%  %+7.1fR  %+7.0f $"
                       % (yildiz, r["sembol"], r["zaman"], r["sik"], r["islem"], r["basari"], r["R"], r["dolar"]))
        sat += ["", "NOT: 2 ve 3 sonuca bakilarak secilir; sans payi vardir. * isaretliler daha guvenilir."]
    yaz = "\n".join(sat)
    with open(os.path.join(klasor, "0_OZET.txt"), "w", encoding="utf-8") as f:
        f.write(yaz)
    print("\n" + yaz)
    print("\nSonuclar: " + klasor)


if __name__ == "__main__":
    main()
