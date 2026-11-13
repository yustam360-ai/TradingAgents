# -*- coding: utf-8 -*-
"""
ALTIN (XAUUSD) + BITCOIN (BTCUSD) - 15 DAKIKALIK - EMA KESISIM - 10.000 $ ILE BASLASAYDI
======================================================================================
Calistir:   py -3.8 C:\\Users\\User\\Desktop\\altin_btc_15dk.py
Gerekli:    py -3.8 -m pip install MetaTrader5 pandas numpy
MT5 acik olmali. SADECE gecmis veri okur, ISLEM ACMAZ.
Sonuc MASAUSTUNE:  Masaustu\\altin_btc_<tarih>\\0_OZET.txt

SURE : son 2 yil. Ozette 2025 ve 2026 (1 Ocak 2026'dan bugune) AYRI AYRI de yazar.
MANTIK (LONG; SHORT tersi): hizli EMA yavas EMA'yi yukari keser VE mum yon EMA'sinin ustunde kapanir
       -> kesisim mumu kapaninca bir sonraki mumun acilisinda giris.  Grafik 15 DAKIKALIK.
HIZ  : 9/26/100 (bizim)   7/21/75   5/15/50   3/10/30   (kucuk = daha erken)
SIK  : A stop 1 ATR hedef 2 ATR | B stop 1 ATR hedef 3 ATR | C stop 2 ATR, ters kesisimde cikis
SPREAD / KOMISYON YOK.  Islem basina risk 25 $ ve 100 $ (ayri yazar).
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

SEMBOLLER = ["XAUUSD", "BTCUSD"]
GUN = 730
Y2026 = datetime(2026, 1, 1)
SERMAYE = 10000.0
RISKLER = (25.0, 100.0)
HIZLAR = [("9/26/100", 9, 26, 100), ("7/21/75", 7, 21, 75), ("5/15/50", 5, 15, 50), ("3/10/30", 3, 10, 30)]
SIK = {"A": (1.0, 2.0), "B": (1.0, 3.0), "C": (2.0, None)}
UFUK = 3000


def masaustu():
    ev = os.path.expanduser("~")
    for p in (os.path.join(ev, "Desktop"), os.path.join(ev, "OneDrive", "Desktop"), os.path.join(ev, "Masaüstü")):
        if os.path.isdir(p):
            return p
    return os.getcwd()


def cek(sembol, bas, bit):
    out, a = [], bas
    while a < bit:
        b = min(a + timedelta(days=90), bit)
        r = None
        for _ in range(3):
            r = mt5.copy_rates_range(sembol, mt5.TIMEFRAME_M15, a, b)
            if r is not None:
                break
            time.sleep(0.5)
        if r is not None and len(r):
            out.append(pd.DataFrame(r)[["time", "open", "high", "low", "close"]])
        a = b
    if not out:
        return None
    return pd.concat(out).drop_duplicates("time").sort_values("time").reset_index(drop=True)


def test(df, f, s, tr):
    T = df["time"].values.astype(np.int64)
    o, h, l, c = (df[k].values.astype(float) for k in ("open", "high", "low", "close"))
    n = len(c)
    pc = np.r_[c[0], c[:-1]]
    atr = pd.Series(np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))).rolling(14).mean().values
    S = pd.Series(c)
    ef, es, et = (S.ewm(span=k, adjust=False).mean().values for k in (f, s, tr))
    d = ef - es
    dp = np.r_[0.0, d[:-1]]
    yuk, asa = (d > 0) & (dp <= 0), (d < 0) & (dp >= 0)
    yi, ai = np.nonzero(yuk)[0], np.nonzero(asa)[0]
    out = {k: [] for k in SIK}
    for i in np.nonzero((yuk & (c > et)) | (asa & (c < et)))[0]:
        j = i + 1
        if i < tr + 10 or j >= n or not atr[i] > 0:
            continue
        y = 1 if yuk[i] else -1
        ters = ai if y > 0 else yi
        q = np.searchsorted(ters, i, "right")
        tk_i = ters[q] if q < len(ters) else -1
        end = min(n, j + UFUK)
        if y > 0:
            lo, hi, op = l[j:end], h[j:end], o[j:end]
        else:
            lo, hi, op = -h[j:end], -l[j:end], -o[j:end]
        ey = y * o[j]
        lmin, hmax = np.minimum.accumulate(lo), np.maximum.accumulate(hi)
        m = end - j
        for k, (sk, tk) in SIK.items():
            risk = sk * atr[i]
            st = ey - risk
            isl = int(np.searchsorted(-lmin, -st, "left"))
            if tk is not None:
                tp = ey + tk * atr[i]
                itp = int(np.searchsorted(hmax, tp, "left"))
                if isl >= m and itp >= m:
                    continue
                ix, px = (isl, min(op[isl], st)) if isl <= itp else (itp, max(op[itp], tp))
            else:
                if tk_i < 0 or tk_i + 1 - j >= m:
                    continue
                kx = tk_i + 1 - j
                ix, px = (isl, min(op[isl], st)) if isl < kx else (kx, op[kx])
            out[k].append((int(T[j]), int(T[j + ix]), (px - ey) / risk))
    return out


def ozet(x, bas_t):
    x = [r for r in x if r[0] >= bas_t]
    if not x:
        return None
    R = np.array([r[2] for r in sorted(x, key=lambda r: r[1])])
    egri = np.cumsum(R)
    dd = (np.maximum.accumulate(np.r_[0.0, egri])[1:] - egri).max()
    gun = max(1.0, (time.time() - bas_t) / 86400.0 * 5.0 / 7.0)
    return dict(n=len(R), b=100.0 * (R > 0).mean(), R=R.sum(), dd=dd, ig=len(R) / gun)


def main():
    if mt5 is None:
        print("MetaTrader5 paketi yok:  py -3.8 -m pip install MetaTrader5 pandas numpy")
        return
    if not mt5.initialize():
        print("MT5'e baglanilamadi. MT5 acik mi?", mt5.last_error())
        return
    simdi = int(time.time())
    bas2 = simdi - GUN * 86400
    b26 = int((Y2026 - datetime(1970, 1, 1)).total_seconds())
    bit = datetime.now() + timedelta(days=1)
    SON = []
    for sb in SEMBOLLER:
        mt5.symbol_select(sb, True)
        df = cek(sb, bit - timedelta(days=GUN + 20), bit)
        if df is None or len(df) < 1000:
            print(sb, "veri yok")
            continue
        for hz, f, s, tr in HIZLAR:
            for k, x in test(df, f, s, tr).items():
                o2, o25, o26 = ozet(x, bas2), ozet([r for r in x if r[0] < b26], bas2), ozet(x, b26)
                if o2:
                    SON.append(dict(sembol=sb, hiz=hz, sik=k, iki=o2, y25=o25, y26=o26))
        print(sb, "tamam")
    mt5.shutdown()

    sat = ["ALTIN + BTC | 15 DAKIKALIK | EMA KESISIM | spread/komisyon YOK | %s" % datetime.now().strftime("%d.%m.%Y"),
           "A: stop 1 ATR hedef 2 ATR   B: stop 1 ATR hedef 3 ATR   C: stop 2 ATR, ters kesisimde cikis",
           "R = risk birimi. 25 $ riskte 1R = 25 $, 100 $ riskte 1R = 100 $."]
    for sb in SEMBOLLER:
        L = [r for r in SON if r["sembol"] == sb]
        if not L:
            continue
        sat += ["", "== %s ==" % sb,
                "%-9s %-3s | %-24s | %-15s | %-24s | %s" % ("hiz", "sik", "2026 BASINDAN BUGUNE", "2025 (2026 once)",
                                                            "2 YIL TOPLAM", "10.000$ -> (2026, 25$/100$)"),
                "%-9s %-3s | %5s %6s %8s %4s | %6s %8s | %5s %6s %8s %6s |" % ("", "", "islem", "basari", "R", "/gun",
                                                                            "basari", "R", "islem", "basari", "R",
                                                                            "dusus")]
        for r in L:
            a, b_, c_ = r["y26"], r["y25"], r["iki"]
            a = a or dict(n=0, b=0.0, R=0.0, ig=0.0)
            b_ = b_ or dict(b=0.0, R=0.0)
            sat.append("%-9s %-3s | %5d %5.1f%% %+8.1f %4.1f | %5.1f%% %+8.1f | %5d %5.1f%% %+8.1f %6.1f | %6.0f / %6.0f"
                       % (r["hiz"], r["sik"], a["n"], a["b"], a["R"], a["ig"], b_["b"], b_["R"], c_["n"], c_["b"],
                          c_["R"], c_["dd"], SERMAYE + a["R"] * 25, SERMAYE + a["R"] * 100))
    # en mantikli
    sat += ["", "== EN MANTIKLISI (her sembol icin) ==",
            "Kural: 2025'te de 2026'da da ARTIDA olan ayarlar icinden, 2 yillik R / en buyuk dusus orani en yuksek olan.",
            "(Iki yilda da kazandiran ve dususu kucuk olan = en saglam. Sadece en cok kazandirani secmek sansa acik.)"]
    secilen = []
    for sb in SEMBOLLER:
        L = [r for r in SON if r["sembol"] == sb and r["y25"] and r["y26"] and r["y25"]["R"] > 0 and r["y26"]["R"] > 0]
        if not L:
            sat.append("%s: iki yilda da artida olan ayar YOK -> bu sembolde guvenilir mantik bulunamadi." % sb)
            continue
        en = max(L, key=lambda r: r["iki"]["R"] / max(1.0, r["iki"]["dd"]))
        secilen.append(en)
        a = en["y26"]
        sat.append("%s: %s, 15 DK, sik %s | 2025 %+.1fR, 2026 %+.1fR | basari %%%.1f | gunde ~%.1f islem | "
                   "en buyuk dusus %.1fR" % (sb, en["hiz"], en["sik"], en["y25"]["R"], a["R"], en["iki"]["b"], a["ig"],
                                             en["iki"]["dd"]))
        for rk in RISKLER:
            sat.append("   %3.0f $ risk: 1 Ocak 2026'da 10.000 $ -> %.0f $  (gunluk ort %+.0f $, en buyuk dusus %.0f $)"
                       % (rk, SERMAYE + a["R"] * rk, a["R"] * rk / max(1.0, a["n"] / max(0.1, a["ig"])),
                          en["iki"]["dd"] * rk))
    if len(secilen) == 2:
        R26 = sum(r["y26"]["R"] for r in secilen)
        sat += ["", "IKISI BIRLIKTE (ayni 10.000 $ hesapta, 1 Ocak 2026'dan bugune):"]
        for rk in RISKLER:
            sat.append("   %3.0f $ risk: 10.000 $ -> %.0f $" % (rk, SERMAYE + R26 * rk))
    yaz = "\n".join(sat)
    klasor = os.path.join(masaustu(), "altin_btc_" + datetime.now().strftime("%Y%m%d_%H%M"))
    os.makedirs(klasor, exist_ok=True)
    with open(os.path.join(klasor, "0_OZET.txt"), "w", encoding="utf-8") as f:
        f.write(yaz)
    print("\n" + yaz)
    print("\nSonuc: " + klasor)


if __name__ == "__main__":
    main()
