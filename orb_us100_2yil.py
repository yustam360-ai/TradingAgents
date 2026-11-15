# -*- coding: utf-8 -*-
"""
US100 - NEW YORK ACILISI RANGE BREAKOUT (ORB) - SON 2 YIL - ISLEM BASI 200 $ RISK
================================================================================
Calistir:   py -3.8 C:\\Users\\User\\Desktop\\orb_us100_2yil.py
Gerekli:    py -3.8 -m pip install MetaTrader5 pandas numpy
MT5 acik olmali. SADECE gecmis veri okur, ISLEM ACMAZ.  1 dakikalik veri.
MT5 > Araclar > Secenekler > Grafikler > "Grafikteki en fazla cubuk" = Sinirsiz.
Sonuc MASAUSTUNE:  Masaustu\\orb_us100_<tarih>\\0_OZET.txt

KURAL:
  NY acilisi 09:30 = FTMO sunucu saati 16:30 (sunucu her zaman NY + 7 saat).
  16:30'dan itibaren ilk N dakikanin en yuksek / en dusugu = aralik  (N = 5, 15, 30, 60 dk ayri ayri)
  Aralik bitince tepeye BUY STOP, dibe SELL STOP, biri dolunca digeri iptal (gunde 1 islem).
  STOP = araligin karsi ucu.
  HEDEF (TP) ayri ayri:  YOK (kapanisa kadar) / 1R / 2R / 3R   (R = stop mesafesi)
  KAPANIS: sunucu 22:55 (NY 15:55).  Ayni dakikada hem stop hem TP gorulurse STOP sayilir (temkinli).
  RISK: her islemde stop olursa tam 200 $. Spread dahil, komisyon yok.
"""
from __future__ import print_function

import os
import time
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

try:
    import MetaTrader5 as mt5
except ImportError:
    mt5 = None

GUN = 730
RISK = 200.0
SERMAYE = 10000.0
ADAYLAR = ["US100.cash", "US100", "NAS100", "USTEC", "NDX100"]   # brokerdaki ad farkliysa buraya ekleyin
ACILIS = "16:30"      # sunucu saati (NY 09:30)
KAPANIS = "22:55"     # sunucu saati (NY 15:55)
SURELER = [5, 15, 30, 60]          # aralik suresi (dakika)
HEDEFLER = [None, 1.0, 2.0, 3.0]   # TP (R cinsinden), None = hedef yok


def dk(s):
    h, m = s.split(":")
    return int(h) * 60 + int(m)


def masaustu():
    ev = os.path.expanduser("~")
    for p in (os.path.join(ev, "Desktop"), os.path.join(ev, "OneDrive", "Desktop"), os.path.join(ev, "Masaüstü")):
        if os.path.isdir(p):
            return p
    return os.getcwd()


def cek(sembol, bas, bit):
    out, a = [], bas
    while a < bit:
        b = min(a + timedelta(days=15), bit)
        r = None
        for _ in range(3):
            r = mt5.copy_rates_range(sembol, mt5.TIMEFRAME_M1, a, b)
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


def gun(T, o, h, l, c, sp, ab, ai, kp, tp):
    m = (T % 86400) // 60
    ar = (m >= ab) & (m < ai)
    if ar.sum() < 0.5 * (ai - ab):
        return None
    tepe, dip = h[ar].max(), l[ar].min()
    if not tepe > dip:
        return None
    ix = np.nonzero((m >= ai) & (m < kp))[0]
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
    k = np.nonzero(m >= kp)[0]
    son = k[0] if len(k) else len(T) - 1
    j = np.arange(gi + 1, son)
    if yon > 0:
        e = max(tepe, o[gi] + sp[gi])
        ey, sty = e, dip
        ale, ahi, acl = l[j], h[j], o[j]
        cik = o[son] if len(k) else c[son]
    else:
        e = min(dip, o[gi])
        ey, sty = -e, -tepe
        ale, ahi, acl = -(h[j] + sp[j]), -(l[j] + sp[j]), -(o[j] + sp[j])
        cik = -((o[son] if len(k) else c[son]) + sp[son])
    risk = ey - sty
    if risk <= 0:
        return None
    sb = np.nonzero(ale <= sty)[0]
    s_i = sb[0] if len(sb) else None
    t_i = None
    if tp is not None:
        hd = ey + tp * risk
        tb = np.nonzero(ahi >= hd)[0]
        t_i = tb[0] if len(tb) else None
    if s_i is not None and (t_i is None or s_i <= t_i):
        px = min(acl[s_i], sty)
    elif t_i is not None:
        px = max(acl[t_i], hd)
    else:
        px = cik
    return (px - ey) / risk


def main():
    if mt5 is None:
        print("MetaTrader5 paketi yok:  py -3.8 -m pip install MetaTrader5 pandas numpy")
        return
    if not mt5.initialize():
        print("MT5'e baglanilamadi. MT5 acik mi?", mt5.last_error())
        return
    sb = None
    for x in ADAYLAR:
        if mt5.symbol_select(x, True) and mt5.symbol_info(x) is not None:
            sb = x
            break
    if sb is None:
        print("US100 sembolu bulunamadi (%s). ADAYLAR listesine brokerdaki adi ekleyin." % ",".join(ADAYLAR))
        mt5.shutdown()
        return
    print("Sembol: %s  veri cekiliyor..." % sb)
    bit = datetime.now() + timedelta(days=1)
    bas = bit - timedelta(days=GUN + 1)
    pt = mt5.symbol_info(sb).point
    df = cek(sb, bas, bit)
    mt5.shutdown()
    if df is None or len(df) < 10000:
        print("veri yok/az")
        return
    df = df[df["time"] >= int(time.time()) - GUN * 86400]
    T = df["time"].values.astype(np.int64)
    o, h, l, c = (df[k].values.astype(float) for k in ("open", "high", "low", "close"))
    sp = df["spread"].values.astype(float) * pt
    gk = T // 86400
    s = np.r_[0, np.nonzero(np.diff(gk))[0] + 1, len(T)]
    ab, kp = dk(ACILIS), dk(KAPANIS)
    S = []
    for n in SURELER:
        for tp in HEDEFLER:
            K = []
            for x in range(len(s) - 1):
                a, b = s[x], s[x + 1]
                R = gun(T[a:b], o[a:b], h[a:b], l[a:b], c[a:b], sp[a:b], ab, ab + n, kp, tp)
                if R is not None:
                    K.append((datetime.utcfromtimestamp(int(T[a])).year, R * RISK))
            if not K:
                continue
            D = np.array([d for _, d in K])
            egri = np.cumsum(D)
            dd = (np.maximum.accumulate(np.r_[0.0, egri])[1:] - egri).max()
            yil = {}
            for y, d in K:
                yil[y] = yil.get(y, 0.0) + d
            ad = "%d dk aralik, TP %s" % (n, "YOK" if tp is None else "%gR" % tp)
            S.append(dict(ad=ad, islem=len(D), basari=100.0 * (D > 0).mean(), dolar=D.sum(), dusus=dd,
                          kotu=D.min(), y2025=yil.get(2025, 0.0), y2026=yil.get(2026, 0.0)))
            print("%-24s %4d islem  basari %5.1f%%  %+9.0f $" % (ad, len(D), 100.0 * (D > 0).mean(), D.sum()))
    if not S:
        print("islem yok")
        return
    S.sort(key=lambda r: -r["dolar"])
    sat = ["US100 NY ACILISI ORB | %s | son 2 yil | islem basi 200 $ risk | spread dahil | %s"
           % (sb, datetime.now().strftime("%d.%m.%Y")),
           "Aralik 16:30'dan (NY 09:30) itibaren, stop karsi uc, kapanis 22:55.  10.000 $ -> = 10.000 + toplam.", "",
           "%-24s %5s %7s %9s %9s %9s %10s %8s %8s" % ("ayar", "islem", "basari", "2025", "2026", "TOPLAM",
                                                       "10.000->", "dusus", "kotu gun")]
    for r in S:
        sat.append("%-24s %5d %6.1f%% %+9.0f %+9.0f %+9.0f %10.0f %8.0f %+8.0f"
                   % (r["ad"], r["islem"], r["basari"], r["y2025"], r["y2026"], r["dolar"], SERMAYE + r["dolar"],
                      r["dusus"], r["kotu"]))
    iyi = [r for r in S if r["y2025"] > 0 and r["y2026"] > 0]
    sat += ["", "2025'TE DE 2026'DA DA KARDA OLANLAR:"]
    sat += ["  %-24s %+8.0f $  basari %%%.1f  dusus %.0f $" % (r["ad"], r["dolar"], r["basari"], r["dusus"])
            for r in iyi] or ["  yok"]
    en = max(S, key=lambda r: r["y2025"])
    sat += ["", "DURUST KONTROL: 2025'in en iyisini secseydik 2026'da ne olurdu?",
            "  2025 en iyisi: %s  (2025: %+.0f $)  ->  2026: %+.0f $" % (en["ad"], en["y2025"], en["y2026"])]
    sat += ["", "Not: 2024 son 1.5 ayi toplama dahil, ayri sutun yok. 16 ayar denendi; en iyisi sans da olabilir."]
    yaz = "\n".join(sat)
    klasor = os.path.join(masaustu(), "orb_us100_" + datetime.now().strftime("%Y%m%d_%H%M"))
    os.makedirs(klasor, exist_ok=True)
    with open(os.path.join(klasor, "0_OZET.txt"), "w", encoding="utf-8") as f:
        f.write(yaz)
    print("\n" + yaz)
    print("\nSonuc: " + klasor)


if __name__ == "__main__":
    main()
