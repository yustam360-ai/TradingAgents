# -*- coding: utf-8 -*-
"""
ALTIN RANGE BREAKOUT (Rene Balke) - 1 OCAK 2026'DAN BUGUNE - 10.000 $ ILE BASLASAYDI
==================================================================================
Calistir:   py -3.8 C:\\Users\\User\\Desktop\\altin_range_breakout_2026.py
Gerekli:    py -3.8 -m pip install MetaTrader5 pandas numpy
MT5 acik olmali. SADECE gecmis veri okur, ISLEM ACMAZ.  1 dakikalik veri kullanir.
Sonuc MASAUSTUNE:  Masaustu\\range_breakout_<tarih>\\0_OZET.txt , 1_islemler.csv

KURALLAR (videodaki gibi, saatler MT5 SUNUCU saati):
  1) 03:05 - 06:05 arasi en yuksek ve en dusuk fiyat bulunur (aralik).
  2) 06:05'te aralik tepesine BUY STOP, aralik dibine SELL STOP konur.
  3) Biri dolunca digeri iptal. Gunde en fazla 1 islem.
  4) STOP: giris fiyatinin %1'i uzakta.  HEDEF: yok.
  5) 18:55'te acik islem kapatilir, dolmayan emir silinir.
  RISK: her islemde 200 $ (stop olursa -200 $).  Spread dahil (alis ASK, satis BID), komisyon yok.
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

SEMBOL = "XAUUSD"
BASLA = datetime(2026, 1, 1)
SERMAYE = 10000.0
RISK = 200.0
STOP_YUZDE = 1.0
ARALIK_BAS, ARALIK_BIT = 3 * 60 + 5, 6 * 60 + 5     # 03:05 - 06:05
KAPANIS = 18 * 60 + 55                              # 18:55


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


def gun_test(g, pt):
    """Tek gunun 1 dk mumlari (sunucu saati). Donus: islem sozlugu ya da None."""
    dk = (g["time"].values % 86400) // 60
    o, h, l, c = g["open"].values, g["high"].values, g["low"].values, g["close"].values
    sp = g["spread"].values * pt
    ar = (dk >= ARALIK_BAS) & (dk < ARALIK_BIT)
    if ar.sum() < 30:
        return None
    tepe, dip = h[ar].max(), l[ar].min()
    ix = np.nonzero((dk >= ARALIK_BIT) & (dk < KAPANIS))[0]
    kp = np.nonzero(dk >= KAPANIS)[0]
    if not len(ix):
        return None
    yon, gi = 0, -1
    for i in ix:
        al = h[i] + sp[i] >= tepe          # ASK tepeye degdi
        sat = l[i] <= dip                  # BID dibe degdi
        if al and sat:                     # ayni dakikada ikisi: acilisa yakin olan once
            yon = 1 if (tepe - o[i]) <= (o[i] - dip) else -1
        elif al:
            yon = 1
        elif sat:
            yon = -1
        if yon:
            gi = i
            break
    if not yon:
        return dict(sonuc="EMIR DOLMADI")
    if yon > 0:
        giris = max(tepe, o[gi] + sp[gi])
        stop = giris * (1 - STOP_YUZDE / 100.0)
    else:
        giris = min(dip, o[gi])
        stop = giris * (1 + STOP_YUZDE / 100.0)
    mes = abs(giris - stop)
    cikis, neden, ci = None, "", None
    for i in ix[ix > gi]:
        if yon > 0 and l[i] <= stop:
            cikis, neden, ci = min(o[i], stop), "STOP", i
            break
        if yon < 0 and h[i] + sp[i] >= stop:
            cikis, neden, ci = max(o[i] + sp[i], stop), "STOP", i
            break
    if cikis is None:
        if len(kp):
            ci = kp[0]
            cikis = o[ci] if yon > 0 else o[ci] + sp[ci]
        else:                              # 18:55 mumu yoksa gunun son fiyati
            ci = len(c) - 1
            cikis = c[ci] if yon > 0 else c[ci] + sp[ci]
        neden = "18:55 KAPANIS"
    R = yon * (cikis - giris) / mes
    return dict(sonuc=neden, yon="LONG" if yon > 0 else "SHORT", tepe=tepe, dip=dip, giris=giris, stop=stop,
                cikis=cikis, R=R, giris_t=int(g["time"].values[gi]), cikis_t=int(g["time"].values[ci]))


def main():
    if mt5 is None:
        print("MetaTrader5 paketi yok:  py -3.8 -m pip install MetaTrader5 pandas numpy")
        return
    if not mt5.initialize():
        print("MT5'e baglanilamadi. MT5 acik mi?", mt5.last_error())
        return
    mt5.symbol_select(SEMBOL, True)
    bilgi = mt5.symbol_info(SEMBOL)
    df = cek(SEMBOL, BASLA - timedelta(days=1), datetime.now() + timedelta(days=1))
    mt5.shutdown()
    if df is None or bilgi is None:
        print("Veri yok. MT5'te XAUUSD var mi? Grafikteki en fazla cubuk = Sinirsiz mi?")
        return
    bas_t = int((BASLA - datetime(1970, 1, 1)).total_seconds())
    df = df[df["time"] >= bas_t]
    print("1 dk mum:", len(df), " ilk:", datetime.utcfromtimestamp(int(df["time"].iloc[0])),
          " son:", datetime.utcfromtimestamp(int(df["time"].iloc[-1])))
    gunler = df["time"] // 86400
    K, dolmadi = [], 0
    for gk, g in df.groupby(gunler):
        r = gun_test(g, bilgi.point)
        if r is None:
            continue
        if r["sonuc"] == "EMIR DOLMADI":
            dolmadi += 1
            continue
        r["tarih"] = datetime.utcfromtimestamp(gk * 86400).strftime("%Y-%m-%d")
        r["dolar"] = r["R"] * RISK
        K.append(r)
    klasor = os.path.join(masaustu(), "range_breakout_" + datetime.now().strftime("%Y%m%d_%H%M"))
    os.makedirs(klasor, exist_ok=True)
    sat = ["ALTIN RANGE BREAKOUT | 1 Ocak 2026 - %s | 10.000 $ | islem basi 200 $ risk | spread dahil"
           % datetime.now().strftime("%d.%m.%Y"),
           "Aralik 03:05-06:05, stop %1, hedef yok, 18:55 kapanis (MT5 sunucu saati)"]
    if not K:
        sat.append("Hic islem yok.")
    else:
        I = pd.DataFrame(K)
        I.to_csv(os.path.join(klasor, "1_islemler.csv"), index=False, sep=";", decimal=",")
        D = I["dolar"].values
        bak = SERMAYE + np.cumsum(D)
        dd = (np.maximum.accumulate(np.r_[SERMAYE, bak])[1:] - bak).max()
        n, w = len(D), int((D > 0).sum())
        sat += ["",
                "Islem gunu: %d   (emir dolmayan gun: %d)" % (n, dolmadi),
                "Karli: %d   Zararli: %d   Basari: %%%.1f" % (w, n - w, 100.0 * w / n),
                "Stop olan: %d   18:55'te kapanan: %d" % ((I["sonuc"] == "STOP").sum(),
                                                          (I["sonuc"] != "STOP").sum()),
                "Ortalama kazanc: %+.0f $   Ortalama kayip: %+.0f $" % (D[D > 0].mean() if w else 0,
                                                                     D[D <= 0].mean() if n - w else 0),
                "En iyi gun: %+.0f $   En kotu gun: %+.0f $" % (D.max(), D.min()),
                "",
                "SONUC:  10.000 $  ->  %.0f $   (%+.0f $, %+.1fR)" % (bak[-1], D.sum(), I["R"].sum()),
                "En buyuk dusus: %.0f $   (FTMO toplam %%10 siniri = 1.000 $: %s)" % (dd, "ASILDI" if dd > 1000 else "tamam"),
                "", "AY AY:"]
        I["ay"] = I["tarih"].str[:7]
        for ay, g in I.groupby("ay"):
            sat.append("  %s  %3d islem  basari %%%3.0f  %+8.0f $" % (ay, len(g), 100.0 * (g["dolar"] > 0).mean(),
                                                                    g["dolar"].sum()))
    yaz = "\n".join(sat)
    with open(os.path.join(klasor, "0_OZET.txt"), "w", encoding="utf-8") as f:
        f.write(yaz)
    print("\n" + yaz)
    print("\nSonuc: " + klasor)


if __name__ == "__main__":
    main()
