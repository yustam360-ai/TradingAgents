# -*- coding: utf-8 -*-
"""
RANGE BREAKOUT (Rene Balke kurallari) - BUTUN SEMBOLLER - 1 OCAK 2025'TEN BUGUNE
=============================================================================
Calistir:   py -3.8 C:\\Users\\User\\Desktop\\range_breakout_tum.py
Gerekli:    py -3.8 -m pip install MetaTrader5 pandas numpy
Sadece bazi semboller:   py -3.8 range_breakout_tum.py --sembol XAUUSD,USDJPY
MT5 acik olmali. SADECE gecmis veri okur, ISLEM ACMAZ.  5 dakikalik veri.
MT5 > Araclar > Secenekler > Grafikler > "Grafikteki en fazla cubuk" = Sinirsiz.
Sonuc MASAUSTUNE:  Masaustu\\rb_tum_<tarih>\\0_OZET.txt (kisa) , 1_semboller.csv

KURALLAR (videodaki XAUUSD kurallari, BUTUN sembollerde AYNI; saatler MT5 SUNUCU saati):
  03:05-06:05 en yuksek / en dusuk -> 06:05'te tepeye BUY STOP, dibe SELL STOP; biri dolunca digeri iptal.
  STOP giris fiyatinin %1'i. HEDEF yok. 18:55'te kapanis. Gunde 1 islem.
  Risk her islemde 200 $. Spread dahil, komisyon yok. 03:05-06:05'te islem gormeyen sembol (hisseler) atlanir.
EK ANALIZ (senin fikrin): 18:55'te kapanan islemler gun icinde en fazla kac R kara cikmisti, saat kacta?
  Ve ayni girislerle: hedef 1R / 1.5R / 2R / 3R  ya da  14:00 / 16:00'da kapatsaydik ne olurdu?
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

BASLA = datetime(2025, 1, 1)
Y2026 = datetime(2026, 1, 1)
RISK = 200.0
SERMAYE = 10000.0
STOP_YUZDE = 1.0
A_BAS, A_BIT, KAPAN = 3 * 60 + 5, 6 * 60 + 5, 18 * 60 + 55
HEDEFLER = [1.0, 1.5, 2.0, 3.0]
ERKEN = [14 * 60, 16 * 60]
MIN_ISLEM = 30


def masaustu():
    ev = os.path.expanduser("~")
    for p in (os.path.join(ev, "Desktop"), os.path.join(ev, "OneDrive", "Desktop"), os.path.join(ev, "Masaüstü")):
        if os.path.isdir(p):
            return p
    return os.getcwd()


def cek(sembol, bas, bit):
    out, a = [], bas
    while a < bit:
        b = min(a + timedelta(days=60), bit)
        r = None
        for _ in range(3):
            r = mt5.copy_rates_range(sembol, mt5.TIMEFRAME_M5, a, b)
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


def gun(T, o, h, l, c, sp):
    dk = (T % 86400) // 60
    ar = (dk >= A_BAS) & (dk < A_BIT)
    if ar.sum() < 20:
        return None
    tepe, dip = h[ar].max(), l[ar].min()
    ix = np.nonzero((dk >= A_BIT) & (dk < KAPAN))[0]
    if not len(ix):
        return None
    yon, gi = 0, -1
    for i in ix:
        al, sat = h[i] + sp[i] >= tepe, l[i] <= dip
        if al and sat:
            yon = 1 if (tepe - o[i]) <= (o[i] - dip) else -1
        elif al:
            yon = 1
        elif sat:
            yon = -1
        if yon:
            gi = i
            break
    if not yon:
        return None
    if yon > 0:
        e = max(tepe, o[gi] + sp[gi])
        st = e * (1 - STOP_YUZDE / 100.0)
    else:
        e = min(dip, o[gi])
        st = e * (1 + STOP_YUZDE / 100.0)
    m = abs(e - st)
    kp = np.nonzero(dk >= KAPAN)[0]
    son = kp[0] if len(kp) else len(T) - 1
    j = np.arange(gi + 1, son)
    # yon uzayinda (long gibi): lehte = yuksek, aleyhte = dusuk ; short icin ASK = BID + spread
    if yon > 0:
        lehte, aleyh, acl = h[j], l[j], o[j]
        cikis_son = o[son] if len(kp) else c[son]
        ey, sty = e, st
    else:
        lehte, aleyh, acl = -(l[j] + sp[j]), -(h[j] + sp[j]), -(o[j] + sp[j])
        cikis_son = -((o[son] if len(kp) else c[son]) + sp[son])
        ey, sty = -e, -st
    sb = np.nonzero(aleyh <= sty)[0]
    stop_i = sb[0] if len(sb) else len(j)
    if stop_i < len(j):
        R = (min(acl[stop_i], sty) - ey) / m
        neden = "STOP"
    else:
        R = (cikis_son - ey) / m
        neden = "18:55"
    # MFE: stop'a kadar gorulen en yuksek kar
    pre = lehte[:stop_i]
    mfe = (pre.max() - ey) / m if len(pre) else 0.0
    mfe_saat = int(dk[j[int(np.argmax(pre))]] // 60) if len(pre) else -1
    alt = {}
    for k in HEDEFLER:
        hit = np.nonzero(lehte[:stop_i] - ey >= k * m)[0]
        alt["TP %.1fR" % k] = k if len(hit) else R
    for t in ERKEN:
        q = np.nonzero(dk[j] >= t)[0]
        if len(q) and q[0] < stop_i:
            alt["%02d:00 kapanis" % (t // 60)] = (acl[q[0]] - ey) / m
        else:
            alt["%02d:00 kapanis" % (t // 60)] = R
    return dict(t=int(T[gi]), yon=yon, R=R, neden=neden, mfe=mfe, mfe_saat=mfe_saat, alt=alt)


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
    bas_t = int((BASLA - datetime(1970, 1, 1)).total_seconds())
    t26 = int((Y2026 - datetime(1970, 1, 1)).total_seconds())
    tum = []
    print("Taranacak sembol: %d   (1 Ocak 2025 - bugun, 5 dk)" % len(liste))
    for no, sb in enumerate(liste, 1):
        try:
            mt5.symbol_select(sb, True)
            bilgi = mt5.symbol_info(sb)
            df = cek(sb, BASLA - timedelta(days=1), datetime.now() + timedelta(days=1))
            if bilgi is None or df is None or len(df) < 2000:
                print("%3d/%d %-12s veri yok/az" % (no, len(liste), sb))
                continue
            df = df[df["time"] >= bas_t]
            T = df["time"].values.astype(np.int64)
            o, h, l, c = (df[k].values.astype(float) for k in ("open", "high", "low", "close"))
            sp = df["spread"].values.astype(float) * bilgi.point
            gk = T // 86400
            sinir = np.r_[0, np.nonzero(np.diff(gk))[0] + 1, len(T)]
            n0 = len(tum)
            for x in range(len(sinir) - 1):
                p, q = sinir[x], sinir[x + 1]
                r = gun(T[p:q], o[p:q], h[p:q], l[p:q], c[p:q], sp[p:q])
                if r:
                    r["sembol"] = sb
                    tum.append(r)
            k = tum[n0:]
            if k:
                R = np.array([z["R"] for z in k])
                print("%3d/%d %-12s %4d islem  basari %5.1f%%  %+7.1fR  %+8.0f $"
                      % (no, len(liste), sb, len(R), 100.0 * (R > 0).mean(), R.sum(), R.sum() * RISK))
            else:
                print("%3d/%d %-12s islem yok (03-06 arasi kapali)" % (no, len(liste), sb))
        except Exception as ex:
            print("%3d/%d %-12s HATA: %s" % (no, len(liste), sb, ex))
    mt5.shutdown()

    klasor = os.path.join(masaustu(), "rb_tum_" + datetime.now().strftime("%Y%m%d_%H%M"))
    os.makedirs(klasor, exist_ok=True)
    sat = ["RANGE BREAKOUT - BUTUN SEMBOLLER | 1 Ocak 2025 - %s | islem basi 200 $ risk | spread dahil | sure %.0f dk"
           % (datetime.now().strftime("%d.%m.%Y"), (time.time() - t0) / 60.0),
           "03:05-06:05 aralik, stop %1, hedef yok, 18:55 kapanis (MT5 sunucu saati), butun sembollerde ayni"]
    if not tum:
        sat.append("Hic islem yok.")
    else:
        I = pd.DataFrame([{k: v for k, v in z.items() if k != "alt"} for z in tum])
        A = pd.DataFrame([z["alt"] for z in tum])
        S = []
        for sb, g in I.groupby("sembol"):
            R = g["R"].values
            egri = np.cumsum(R[np.argsort(g["t"].values)])
            dd = (np.maximum.accumulate(np.r_[0.0, egri])[1:] - egri).max()
            S.append(dict(sembol=sb, islem=len(R), basari=round(100.0 * (R > 0).mean(), 1), R=round(R.sum(), 1),
                          dolar=round(R.sum() * RISK), dusus_dolar=round(dd * RISK),
                          R_2025=round(g[g["t"] < t26]["R"].sum(), 1), R_2026=round(g[g["t"] >= t26]["R"].sum(), 1)))
        S = pd.DataFrame(S).sort_values("R", ascending=False)
        S.to_csv(os.path.join(klasor, "1_semboller.csv"), index=False, sep=";", decimal=",")
        n, w, R = len(I), int((I["R"] > 0).sum()), I["R"].sum()
        sat += ["", "1) BUTUN SEMBOLLER TOPLAMI: %d islem, basari %%%.1f, %+.0fR = %+.0f $   (karda olan sembol: %d / %d)"
                % (n, 100.0 * w / n, R, R * RISK, (S["R"] > 0).sum(), len(S))]
        # 2) cikis alternatifleri
        sat += ["", "2) AYNI GIRISLER, FARKLI CIKIS (butun semboller toplami)",
                "   %-16s %8s %9s" % ("cikis", "basari", "R"),
                "   %-16s %7.1f%% %+9.0f   <- simdiki kural" % ("18:55 (hedef yok)", 100.0 * w / n, R)]
        for col in A.columns:
            sat.append("   %-16s %7.1f%% %+9.0f" % (col, 100.0 * (A[col] > 0).mean(), A[col].sum()))
        # 3) MFE
        K = I[I["neden"] == "18:55"]
        if len(K):
            sat += ["", "3) 18:55'TE KAPANAN %d ISLEM: gun icinde ne kadar kara cikmisti?" % len(K),
                    "   Ortalama kapanis: %+.2fR   Ortalama gun ici en yuksek kar: %+.2fR"
                    % (K["R"].mean(), K["mfe"].mean()),
                    "   1R+ kara cikip daha az karla kapanan: %d (%%%.0f)   2R+ kara cikip: %d (%%%.0f)"
                    % (((K["mfe"] >= 1) & (K["R"] < 1)).sum(), 100.0 * ((K["mfe"] >= 1) & (K["R"] < 1)).mean(),
                       ((K["mfe"] >= 2) & (K["R"] < 2)).sum(), 100.0 * ((K["mfe"] >= 2) & (K["R"] < 2)).mean()),
                    "   En yuksek karin goruldugu saat (sunucu): " +
                    "  ".join("%02d:%d" % (s, v) for s, v in K["mfe_saat"].value_counts().sort_index().items()
                              if s >= 0)]
        # 4) listeler
        U = S[(S["islem"] >= MIN_ISLEM) & (S["basari"] >= 60.0)]
        sat += ["", "4) BASARI %%60 VE USTU (en az %d islem): %d sembol" % (MIN_ISLEM, len(U)),
                "   %-12s %6s %7s %8s %8s %8s %8s %8s" % ("sembol", "islem", "basari", "R", "dolar", "dusus$",
                                                       "R 2025", "R 2026")]
        for _, r in U.iterrows():
            sat.append("   %-12s %6d %6.1f%% %+8.1f %+8.0f %8.0f %+8.1f %+8.1f %s"
                       % (r["sembol"], r["islem"], r["basari"], r["R"], r["dolar"], r["dusus_dolar"], r["R_2025"],
                          r["R_2026"], "*" if r["R_2025"] > 0 and r["R_2026"] > 0 else ""))
        V = S[(S["islem"] >= MIN_ISLEM) & (S["basari"] >= 50.0) & (S["basari"] < 60.0) & (S["R"] > 0)]
        sat += ["", "5) BASARI %%50-60 ARASI VE KARDA (en az %d islem): %d sembol" % (MIN_ISLEM, len(V))]
        for _, r in V.head(30).iterrows():
            sat.append("   %-12s %6d %6.1f%% %+8.1f %+8.0f %8.0f %+8.1f %+8.1f %s"
                       % (r["sembol"], r["islem"], r["basari"], r["R"], r["dolar"], r["dusus_dolar"], r["R_2025"],
                          r["R_2026"], "*" if r["R_2025"] > 0 and r["R_2026"] > 0 else ""))
        sat += ["   * = 2025'te de 2026'da da karda (daha guvenilir)", "",
                "6) EN KOTU 10: " + ", ".join("%s %+.0fR" % (r["sembol"], r["R"]) for _, r in S.tail(10).iterrows())]
    yaz = "\n".join(sat)
    with open(os.path.join(klasor, "0_OZET.txt"), "w", encoding="utf-8") as f:
        f.write(yaz)
    print("\n" + yaz)
    print("\nSonuc: " + klasor)


if __name__ == "__main__":
    main()
