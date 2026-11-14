# -*- coding: utf-8 -*-
"""
RENE BALKE RANGE BREAKOUT - SEMBOL SEMBOL - SON 2 YIL - ISLEM BASI 200 $ RISK
===========================================================================
Calistir:   py -3.8 C:\\Users\\User\\Desktop\\rene_semboller_2yil.py
Gerekli:    py -3.8 -m pip install MetaTrader5 pandas numpy
MT5 acik olmali. SADECE gecmis veri okur, ISLEM ACMAZ.  1 dakikalik veri.
MT5 > Araclar > Secenekler > Grafikler > "Grafikteki en fazla cubuk" = Sinirsiz.
Sonuc MASAUSTUNE:  Masaustu\\rene_semboller_<tarih>\\0_OZET.txt

KURAL (her sembolde ayni mantik, saatler MT5 SUNUCU saati):
  Aralik baslangici - bitisi arasi en yuksek / en dusuk -> bitiste tepeye BUY STOP, dibe SELL STOP,
  biri dolunca digeri iptal (gunde 1 islem), HEDEF YOK, kapanis saatinde cikis.
  STOP iki turlu denenir:  %1  (giris fiyatinin %1'i)   ve   KARSI UC (araligin diger ucu)
  RISK: her islemde stop olursa tam 200 $ (lot stop mesafesine gore). Spread dahil, komisyon yok.
SAATLER (Rene'nin canli hesap ekrani ve videolari):
  XAUUSD 03:05-06:05 / 18:55 (stop %1)  | USDJPY 03:00-06:00 / 18:00 (stop karsi uc)
  BTCUSD 05:00-09:00 / 20:00 (karsi uc) | EURJPY 04:00-10:00 / 18:00 | GBPUSD 04:00-11:30 / 18:00
  DE40   07:00-11:00 / 20:00            | US30   11:00-13:00 / 18:00
  EURUSD 03:00-06:00 / 18:00  (Rene saatini soylemedi -> TAHMINI, USDJPY ile ayni alindi)
  * = Rene'nin kendi kullandigi stop turu (bilinenler).
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
# sembol adlari brokerda farkliysa burada duzeltin (FTMO: GER40.cash, US30.cash)
AYAR = [
    # ad, [aday sembol adlari], aralik bas, aralik bit, kapanis, Rene'nin stopu ("%1" / "KARSI UC" / None)
    ("XAUUSD", ["XAUUSD"], "03:05", "06:05", "18:55", "%1"),
    ("USDJPY", ["USDJPY"], "03:00", "06:00", "18:00", "KARSI UC"),
    ("BTCUSD", ["BTCUSD"], "05:00", "09:00", "20:00", "KARSI UC"),
    ("EURJPY", ["EURJPY"], "04:00", "10:00", "18:00", None),
    ("GBPUSD", ["GBPUSD"], "04:00", "11:30", "18:00", None),
    ("DE40", ["GER40.cash", "DE40", "GER40", "DE40.cash"], "07:00", "11:00", "20:00", None),
    ("US30", ["US30.cash", "US30", "DJ30"], "11:00", "13:00", "18:00", None),
    ("EURUSD (tahmini saat)", ["EURUSD"], "03:00", "06:00", "18:00", None),
]


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


def gun(T, o, h, l, c, sp, ab, ai, kp, stopmod):
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
        st = e * 0.99 if stopmod == "%1" else dip
        ale, acl = l[j], o[j]
        cik = o[son] if len(k) else c[son]
        ey, sty = e, st
    else:
        e = min(dip, o[gi])
        st = e * 1.01 if stopmod == "%1" else tepe
        ale, acl = -(h[j] + sp[j]), -(o[j] + sp[j])
        cik = -((o[son] if len(k) else c[son]) + sp[son])
        ey, sty = -e, -st
    risk = ey - sty
    if risk <= 0:
        return None
    sb = np.nonzero(ale <= sty)[0]
    px = min(acl[sb[0]], sty) if len(sb) else cik
    return (px - ey) / risk


def main():
    if mt5 is None:
        print("MetaTrader5 paketi yok:  py -3.8 -m pip install MetaTrader5 pandas numpy")
        return
    if not mt5.initialize():
        print("MT5'e baglanilamadi. MT5 acik mi?", mt5.last_error())
        return
    bit = datetime.now() + timedelta(days=1)
    bas = bit - timedelta(days=GUN + 1)
    sinir = int(time.time()) - GUN * 86400
    S = []
    for ad, adaylar, ab, ai, kp, rene in AYAR:
        sb, df = None, None
        for x in adaylar:
            if mt5.symbol_select(x, True) and mt5.symbol_info(x) is not None:
                sb = x
                break
        if sb is None:
            print("%-22s sembol bulunamadi (%s)" % (ad, ",".join(adaylar)))
            continue
        pt = mt5.symbol_info(sb).point
        df = cek(sb, bas, bit)
        if df is None or len(df) < 10000:
            print("%-22s veri yok/az" % ad)
            continue
        df = df[df["time"] >= sinir]
        T = df["time"].values.astype(np.int64)
        o, h, l, c = (df[k].values.astype(float) for k in ("open", "high", "low", "close"))
        sp = df["spread"].values.astype(float) * pt
        gk = T // 86400
        s = np.r_[0, np.nonzero(np.diff(gk))[0] + 1, len(T)]
        for mod in ("%1", "KARSI UC"):
            K = []
            for x in range(len(s) - 1):
                a, b = s[x], s[x + 1]
                R = gun(T[a:b], o[a:b], h[a:b], l[a:b], c[a:b], sp[a:b], dk(ab), dk(ai), dk(kp), mod)
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
            S.append(dict(ad=ad, sembol=sb, saat="%s-%s / %s" % (ab, ai, kp), stop=mod, rene=(mod == rene),
                          islem=len(D), basari=100.0 * (D > 0).mean(), dolar=D.sum(), dusus=dd, kotu=D.min(),
                          y2025=yil.get(2025, 0.0), y2026=yil.get(2026, 0.0)))
            print("%-22s stop %-8s %4d islem  basari %5.1f%%  %+9.0f $" % (ad, mod, len(D), 100.0 * (D > 0).mean(),
                                                                          D.sum()))
    mt5.shutdown()
    S.sort(key=lambda r: -r["dolar"])
    sat = ["RENE RANGE BREAKOUT - SEMBOL SEMBOL | son 2 yil | islem basi 200 $ risk | spread dahil | %s"
           % datetime.now().strftime("%d.%m.%Y"),
           "* = Rene'nin kendi kullandigi stop.  10.000 $ -> = 10.000 + toplam.", "",
           "%-22s %-24s %-9s %5s %7s %9s %9s %9s %10s %8s %8s" % ("sembol", "saat (aralik / kapanis)", "stop", "islem",
                                                              "basari", "2025", "2026", "TOPLAM", "10.000->",
                                                              "dusus", "kotu gun")]
    for r in S:
        sat.append("%-22s %-24s %-9s %5d %6.1f%% %+9.0f %+9.0f %+9.0f %10.0f %8.0f %+8.0f"
                   % (r["ad"], r["saat"], r["stop"] + ("*" if r["rene"] else ""), r["islem"], r["basari"],
                      r["y2025"], r["y2026"], r["dolar"], SERMAYE + r["dolar"], r["dusus"], r["kotu"]))
    iyi = [r for r in S if r["y2025"] > 0 and r["y2026"] > 0]
    sat += ["", "2025'TE DE 2026'DA DA KARDA OLANLAR (adaylar):"]
    sat += ["  %-22s stop %-9s %+8.0f $  basari %%%.1f  dusus %.0f $" % (r["ad"], r["stop"], r["dolar"], r["basari"],
                                                                         r["dusus"]) for r in iyi] or ["  yok"]
    sat += ["", "Not: 2024 son 1.5 ayi toplama dahil, ayri sutun yok. Her sembolun her gunu ayni kural, secim yok."]
    yaz = "\n".join(sat)
    klasor = os.path.join(masaustu(), "rene_semboller_" + datetime.now().strftime("%Y%m%d_%H%M"))
    os.makedirs(klasor, exist_ok=True)
    with open(os.path.join(klasor, "0_OZET.txt"), "w", encoding="utf-8") as f:
        f.write(yaz)
    print("\n" + yaz)
    print("\nSonuc: " + klasor)


if __name__ == "__main__":
    main()
