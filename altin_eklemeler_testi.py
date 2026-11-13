# -*- coding: utf-8 -*-
"""
ALTIN RANGE BREAKOUT - EKLEMELER TESTI (her mantik AYRI AYRI) - 0.03 LOT - 2024 / 2025 / 2026
==========================================================================================
Calistir:   py -3.8 C:\\Users\\User\\Desktop\\altin_eklemeler_testi.py
Gerekli:    py -3.8 -m pip install MetaTrader5 pandas numpy
MT5 acik olmali. SADECE gecmis veri okur, ISLEM ACMAZ.  1 dakikalik veri.
MT5 > Araclar > Secenekler > Grafikler > "Grafikteki en fazla cubuk" = Sinirsiz.
Sonuc MASAUSTUNE:  Masaustu\\altin_eklemeler_<tarih>\\0_OZET.txt

TEMEL KURAL (robotun aynisi, saatler MT5 sunucu saati):
  03:05-06:05 aralik -> 06:05'te tepeye BUY STOP, dibe SELL STOP, biri dolunca digeri iptal,
  stop girisin %1'i, hedef yok, 18:55 kapanis.  0.03 lot (altinda 1 $ hareket = 3 $).  Spread dahil.
DENENEN EKLEMELER (her biri TEK BASINA, digerleri yokmus gibi):
  1) TP 150 $ / TP 200 $ / TP 300 $ : kar bu kadar olunca kapat
  2) BASABAS        : kar +100 $ olunca stop giris fiyatina cekilir
  3) YARISINI KORU  : kar en az +100 $ gorduyse, gorulen en yuksek karin yarisina dusunce kapat
  4) ARALIK FILTRESI: 03:05-06:05 araligi son 20 gunun ortalama araliginin 1.5 katindan BUYUK
                      ya da yarisindan KUCUKSE o gun islem yok
  5) TREND FILTRESI : dunku kapanis 50 gunluk ortalamanin ustundeyse SADECE LONG (buy stop),
                      altindaysa SADECE SHORT (sell stop)
Bir ekleme ancak 2024, 2025 ve 2026'nin UCUNDE DE mevcut kuraldan iyiyse "SAGLAM" sayilir.
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
BASLA = datetime(2024, 1, 1)
LOT_CARPAN = 3.0                       # 0.03 lot x 100 ons: 1 $ fiyat hareketi = 3 $
SERMAYE = 10000.0
A_BAS, A_BIT, KAPAN = 3 * 60 + 5, 6 * 60 + 5, 18 * 60 + 55
STOP_YUZDE = 1.0
CESITLER = ["MEVCUT", "TP 150 $", "TP 200 $", "TP 300 $", "BASABAS", "YARISINI KORU", "ARALIK FILTRESI",
            "TREND FILTRESI"]


def masaustu():
    ev = os.path.expanduser("~")
    for p in (os.path.join(ev, "Desktop"), os.path.join(ev, "OneDrive", "Desktop"), os.path.join(ev, "Masaüstü")):
        if os.path.isdir(p):
            return p
    return os.getcwd()


def cek(bas, bit):
    out, a = [], bas
    while a < bit:
        b = min(a + timedelta(days=15), bit)
        r = None
        for _ in range(3):
            r = mt5.copy_rates_range(SEMBOL, mt5.TIMEFRAME_M1, a, b)
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


def cikis(e, st, leh, ale, acl, son_px, mod, p):
    """Long uzayinda (short icin fiyatlar ters cevrilmis). Donus: cikis fiyati."""
    stop = st
    tp = e + p if mod == "tp" else None
    maxf = 0.0
    for k in range(len(leh)):
        if mod == "yari" and maxf >= p:
            koru = e + 0.5 * maxf
            if ale[k] <= koru:
                return min(acl[k], koru)
        if ale[k] <= stop:
            return min(acl[k], stop)
        if tp is not None and leh[k] >= tp:
            return max(acl[k], tp)
        if mod == "be" and leh[k] - e >= p:
            stop = max(stop, e)
        maxf = max(maxf, leh[k] - e)
    return son_px


def gun(T, o, h, l, c, sp, izin):
    """izin: +1 sadece long, -1 sadece short, 0 ikisi. Donus: (yon, giris, stop, kollar) ya da None."""
    dk = (T % 86400) // 60
    ix = np.nonzero((dk >= A_BIT) & (dk < KAPAN))[0]
    ar = (dk >= A_BAS) & (dk < A_BIT)
    tepe, dip = h[ar].max(), l[ar].min()
    yon, gi = 0, -1
    for i in ix:
        al = izin >= 0 and h[i] + sp[i] >= tepe
        sat = izin <= 0 and l[i] <= dip
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
    kp = np.nonzero(dk >= KAPAN)[0]
    son = kp[0] if len(kp) else len(T) - 1
    j = np.arange(gi + 1, son)
    if yon > 0:
        e = max(tepe, o[gi] + sp[gi])
        leh, ale, acl = h[j], l[j], o[j]
        son_px = o[son] if len(kp) else c[son]
    else:
        e = -min(dip, o[gi])
        leh, ale, acl = -(l[j] + sp[j]), -(h[j] + sp[j]), -(o[j] + sp[j])
        son_px = -((o[son] if len(kp) else c[son]) + sp[son])
    st = e - abs(e) * STOP_YUZDE / 100.0
    return yon, e, st, leh, ale, acl, son_px


def main():
    if mt5 is None:
        print("MetaTrader5 paketi yok:  py -3.8 -m pip install MetaTrader5 pandas numpy")
        return
    if not mt5.initialize():
        print("MT5'e baglanilamadi. MT5 acik mi?", mt5.last_error())
        return
    mt5.symbol_select(SEMBOL, True)
    bilgi = mt5.symbol_info(SEMBOL)
    df = cek(BASLA - timedelta(days=100), datetime.now() + timedelta(days=1))
    mt5.shutdown()
    if df is None or bilgi is None:
        print("Veri yok.")
        return
    T = df["time"].values.astype(np.int64)
    o, h, l, c = (df[k].values.astype(float) for k in ("open", "high", "low", "close"))
    sp = df["spread"].values.astype(float) * bilgi.point
    gk = T // 86400
    sinir = np.r_[0, np.nonzero(np.diff(gk))[0] + 1, len(T)]
    bas_t = int((BASLA - datetime(1970, 1, 1)).total_seconds())
    print("1 dk mum:", len(T), " ilk:", datetime.utcfromtimestamp(int(T[0])), " son:", datetime.utcfromtimestamp(int(T[-1])))
    kapanislar, araliklar = [], []
    K = {k: [] for k in CESITLER}           # (tarih, yil, dolar)
    for x in range(len(sinir) - 1):
        a, b = sinir[x], sinir[x + 1]
        Tg = T[a:b]
        dk = (Tg % 86400) // 60
        ar = (dk >= A_BAS) & (dk < A_BIT)
        gun_ok = ar.sum() >= 30 and Tg[0] >= bas_t and datetime.utcfromtimestamp(int(Tg[0])).weekday() < 5
        rng = h[a:b][ar].max() - l[a:b][ar].min() if ar.sum() >= 30 else None
        if gun_ok:
            tarih = datetime.utcfromtimestamp(int(Tg[0]))
            ort_r = np.mean(araliklar[-20:]) if len(araliklar) >= 10 else None
            sma = np.mean(kapanislar[-50:]) if len(kapanislar) >= 50 else None
            trend = 0 if sma is None else (1 if kapanislar[-1] > sma else -1)
            args = (T[a:b], o[a:b], h[a:b], l[a:b], c[a:b], sp[a:b])
            r = gun(*args, izin=0)
            if r:
                yon, e, st, leh, ale, acl, son_px = r
                for ad, mod, p in [("MEVCUT", "yok", 0), ("TP 150 $", "tp", 150 / LOT_CARPAN),
                                   ("TP 200 $", "tp", 200 / LOT_CARPAN), ("TP 300 $", "tp", 300 / LOT_CARPAN),
                                   ("BASABAS", "be", 100 / LOT_CARPAN), ("YARISINI KORU", "yari", 100 / LOT_CARPAN)]:
                    K[ad].append((tarih, tarih.year, (cikis(e, st, leh, ale, acl, son_px, mod, p) - e) * LOT_CARPAN))
                if ort_r is None or 0.5 * ort_r <= rng <= 1.5 * ort_r:
                    K["ARALIK FILTRESI"].append((tarih, tarih.year, (cikis(e, st, leh, ale, acl, son_px, "yok", 0) - e) * LOT_CARPAN))
            r2 = gun(*args, izin=trend)
            if r2:
                yon, e, st, leh, ale, acl, son_px = r2
                K["TREND FILTRESI"].append((tarih, tarih.year, (cikis(e, st, leh, ale, acl, son_px, "yok", 0) - e) * LOT_CARPAN))
        if rng is not None:
            araliklar.append(rng)
        kapanislar.append(c[b - 1])

    yillar = sorted(set(y for v in K.values() for _, y, _ in v))
    taban = {y: sum(d for _, yy, d in K["MEVCUT"] if yy == y) for y in yillar}
    sat = ["ALTIN RANGE BREAKOUT - EKLEMELER (her biri AYRI) | 0.03 lot | spread dahil | %s"
           % datetime.now().strftime("%d.%m.%Y"),
           "Dolar = 0.03 lot ile. 10.000 $ ile baslasaydi son bakiye = 10.000 + TOPLAM.", "",
           "%-16s %6s %6s " % ("mantik", "islem", "basari") + " ".join("%9s" % y for y in yillar) +
           " %9s %9s %8s %8s  %s" % ("TOPLAM", "10.000->", "dusus", "kotu gun", "3 yilda da iyi?")]
    ozet = []
    for ad in CESITLER:
        v = K[ad]
        if not v:
            continue
        D = np.array([d for _, _, d in v])
        egri = np.cumsum(D)
        dd = (np.maximum.accumulate(np.r_[0.0, egri])[1:] - egri).max()
        yil = {y: sum(d for _, yy, d in v if yy == y) for y in yillar}
        iyi = ad != "MEVCUT" and all(yil[y] > taban[y] for y in yillar)
        ozet.append((ad, D.sum(), iyi))
        sat.append("%-16s %6d %5.1f%% " % (ad, len(D), 100.0 * (D > 0).mean()) +
                   " ".join("%+9.0f" % yil[y] for y in yillar) +
                   " %+9.0f %9.0f %8.0f %+8.0f  %s" % (D.sum(), SERMAYE + D.sum(), dd, D.min(),
                                                     "-" if ad == "MEVCUT" else ("EVET" if iyi else "hayir")))
    en = max(ozet, key=lambda z: z[1])
    sag = [z for z in ozet if z[2]]
    sat += ["", "EN COK KAZANDIRAN: %s (%+.0f $)" % (en[0], en[1]),
            "SAGLAM (3 yilda da mevcut kuraldan iyi): " + (", ".join("%s (%+.0f $)" % (z[0], z[1]) for z in sag) if sag
                                                         else "YOK -> mevcut kural kalsin"),
            "", "NOT: 2026 bugune kadar. Filtre ayarlari (1.5 kat / yari, 50 gun) bastan secildi, oynanmadi."]
    klasor = os.path.join(masaustu(), "altin_eklemeler_" + datetime.now().strftime("%Y%m%d_%H%M"))
    os.makedirs(klasor, exist_ok=True)
    yaz = "\n".join(sat)
    with open(os.path.join(klasor, "0_OZET.txt"), "w", encoding="utf-8") as f:
        f.write(yaz)
    print("\n" + yaz)
    print("\nSonuc: " + klasor)


if __name__ == "__main__":
    main()
