# -*- coding: utf-8 -*-
"""
NEW YORK ACILISI RANGE BREAKOUT (ORB) - BUTUN SEMBOLLER - SON 2 YIL - ISLEM BASI 200 $ RISK
==========================================================================================
Calistir:   py -3.8 C:\\Users\\User\\Desktop\\orb_tum_semboller.py
Tek sembol: py -3.8 C:\\Users\\User\\Desktop\\orb_tum_semboller.py --sembol XAUUSD,US100.cash
Gerekli:    py -3.8 -m pip install MetaTrader5 pandas numpy
MT5 acik olmali. SADECE gecmis veri okur, ISLEM ACMAZ.  1 dakikalik veri (uzun surer, 30-60 dk).
MT5 > Araclar > Secenekler > Grafikler > "Grafikteki en fazla cubuk" = Sinirsiz.
Sonuc MASAUSTUNE:  Masaustu\\orb_tum_<tarih>\\0_OZET.txt  ve  1_HEPSI.txt

KURAL (US100 testiyle ayni, her sembolde):
  Aralik 16:30'dan (NY 09:30) itibaren ilk N dakika (N = 5, 15, 30, 60), tepeye BUY STOP, dibe SELL STOP,
  biri dolunca digeri iptal (gunde 1 islem). STOP = araligin karsi ucu. TP = YOK / 1R / 2R / 3R.
  Kapanis 22:55. Ayni dakikada stop ve TP birlikte gorulurse STOP sayilir. Spread dahil, komisyon yok.
LISTE: 2025'te VE 2026'da basari %50'den fazla VE iki yilda da karda olan sembol + ayar.
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

GUN = 730
RISK = 200.0
SERMAYE = 10000.0
ACILIS = "16:30"      # sunucu saati (NY 09:30)
KAPANIS = "22:55"     # sunucu saati (NY 15:55)
SURELER = [5, 15, 30, 60]
HEDEFLER = [None, 1.0, 2.0, 3.0]
ESIK = 50.0           # basari esigi (%)


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


def satir(r):
    return ("%-14s %-20s %5d %6.1f%% %6.1f%% %6.1f%% %+8.0f %+8.0f %+8.0f %7.0f %+7.0f"
            % (r["sembol"], r["ayar"], r["islem"], r["basari"], r["b25"], r["b26"], r["y2025"], r["y2026"],
               r["dolar"], r["dusus"], r["kotu"]))


BASLIK = "%-14s %-20s %5s %7s %7s %7s %8s %8s %8s %7s %7s" % ("sembol", "ayar", "islem", "basari", "bas25",
                                                              "bas26", "2025 $", "2026 $", "TOPLAM", "dusus",
                                                              "kotugun")


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
    liste = [x.strip() for x in a.sembol.split(",") if x.strip()] if a.sembol else \
        [x.name for x in (mt5.symbols_get() or []) if getattr(x, "trade_mode", 4) != 0]
    bit = datetime.now() + timedelta(days=1)
    bas = bit - timedelta(days=GUN + 1)
    sinir = int(time.time()) - GUN * 86400
    ab, kp = dk(ACILIS), dk(KAPANIS)
    t0 = time.time()
    S = []
    print("Taranacak sembol: %d  (son 2 yil, 1 dk veri)" % len(liste))
    for no, sb in enumerate(liste, 1):
        try:
            mt5.symbol_select(sb, True)
            bilgi = mt5.symbol_info(sb)
            df = cek(sb, bas, bit) if bilgi is not None else None
            if df is None or len(df) < 10000:
                print("%3d/%d %-14s veri yok/az" % (no, len(liste), sb))
                continue
            df = df[df["time"] >= sinir]
            T = df["time"].values.astype(np.int64)
            o, h, l, c = (df[k].values.astype(float) for k in ("open", "high", "low", "close"))
            sp = df["spread"].values.astype(float) * bilgi.point
            gk = T // 86400
            s = np.r_[0, np.nonzero(np.diff(gk))[0] + 1, len(T)]
            yillar = [datetime.utcfromtimestamp(int(T[s[x]])).year for x in range(len(s) - 1)]
            en = None
            for n in SURELER:
                for tp in HEDEFLER:
                    K = []
                    for x in range(len(s) - 1):
                        p, q = s[x], s[x + 1]
                        R = gun(T[p:q], o[p:q], h[p:q], l[p:q], c[p:q], sp[p:q], ab, ab + n, kp, tp)
                        if R is not None:
                            K.append((yillar[x], R * RISK))
                    if len(K) < 20:
                        continue
                    D = np.array([d for _, d in K])
                    Y = np.array([y for y, _ in K])
                    egri = np.cumsum(D)
                    dd = (np.maximum.accumulate(np.r_[0.0, egri])[1:] - egri).max()
                    d25, d26 = D[Y == 2025], D[Y == 2026]
                    r = dict(sembol=sb, ayar="%d dk, TP %s" % (n, "YOK" if tp is None else "%gR" % tp),
                             islem=len(D), basari=100.0 * (D > 0).mean(), dolar=D.sum(), dusus=dd, kotu=D.min(),
                             b25=100.0 * (d25 > 0).mean() if len(d25) else 0.0,
                             b26=100.0 * (d26 > 0).mean() if len(d26) else 0.0,
                             y2025=d25.sum(), y2026=d26.sum())
                    S.append(r)
                    if en is None or r["dolar"] > en["dolar"]:
                        en = r
            if en is not None:
                print("%3d/%d %-14s en iyi: %-16s %+8.0f $  (%.0f sn)" % (no, len(liste), sb, en["ayar"],
                                                                          en["dolar"], time.time() - t0))
        except Exception as hata:
            print("%3d/%d %-14s HATA: %s" % (no, len(liste), sb, hata))
    mt5.shutdown()
    if not S:
        print("sonuc yok")
        return
    S.sort(key=lambda r: -r["dolar"])
    iyi = [r for r in S if r["b25"] > ESIK and r["b26"] > ESIK and r["y2025"] > 0 and r["y2026"] > 0]
    tarih = datetime.now().strftime("%d.%m.%Y")
    oz = ["NY ACILISI ORB - BUTUN SEMBOLLER | son 2 yil | islem basi 200 $ risk | spread dahil | %s" % tarih,
          "Aralik 16:30'dan (NY 09:30) itibaren, stop karsi uc, kapanis 22:55.",
          "", "LISTE: 2025'te VE 2026'da basari %%%.0f'den fazla VE iki yilda da karda  (toplam kara gore sirali)" % ESIK,
          "Denenen sembol x ayar: %d   ->   listeye giren: %d" % (len(S), len(iyi)), "", BASLIK]
    oz += [satir(r) for r in iyi] or ["  yok"]
    oz += ["",
           "NOT 1: Basari %50 tek basina yetmez (TP 1R ile basari yuksek ama kar az olabilir), o yuzden kar sarti da var.",
           "NOT 2: Cok sayida sembol x ayar denendi; bir kismi sadece SANS ile listeye girer.",
           "       Ayni sembolde birden fazla ayar listedeyse (komsu ayarlar da iyiyse) daha guvenilir.",
           "NOT 3: 2024 son 1.5 ayi TOPLAM'a dahil, ayri sutun yok. Butun sonuclar: 1_HEPSI.txt"]
    hepsi = ["NY ACILISI ORB - BUTUN SEMBOL x AYAR (toplam kara gore) | %s" % tarih, "", BASLIK] + [satir(r) for r in S]
    klasor = os.path.join(masaustu(), "orb_tum_" + datetime.now().strftime("%Y%m%d_%H%M"))
    os.makedirs(klasor, exist_ok=True)
    with open(os.path.join(klasor, "0_OZET.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(oz))
    with open(os.path.join(klasor, "1_HEPSI.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(hepsi))
    print("\n" + "\n".join(oz))
    print("\nSonuc: " + klasor)


if __name__ == "__main__":
    main()
