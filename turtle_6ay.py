# -*- coding: utf-8 -*-
"""
TURTLE + TURTLE SOUP - 6 AYLIK TEST - BUTUN SEMBOLLER - 10.000 $ ILE BASLASAYDI
==============================================================================
Calistir:   py -3.8 C:\\Users\\User\\Desktop\\turtle_6ay.py
Gerekli:    py -3.8 -m pip install MetaTrader5 pandas numpy
Sadece bazi semboller:   py -3.8 turtle_6ay.py --sembol EURUSD,XAUUSD
MT5 acik olmali. SADECE gecmis veri okur, ISLEM ACMAZ.
Sonuclar MASAUSTUNE:  Masaustu\\turtle_6ay_<tarih>\\0_OZET.txt , 1_semboller.csv , 2_islemler.csv

180 GUN ONCE 10.000 $ ile baslar, bugune kadar gider. Her an sadece o ana kadar olusmus mumlar kullanilir.
Gunluk seviyeler GUNLUK mumdan, giris/cikis sirasi 1 SAATLIK mumdan bulunur.

1) TURTLE (Richard Dennis, 1983 - Sistem 1, Donchian kirilimi)       [LONG; SHORT birebir tersi]
   GIRIS : fiyat son 20 gunun en yuksegini gecer -> o seviyeden alis (bosluklu acilista acilis fiyatindan).
   STOP  : giristen 2N asagi  (N = son 20 gunun ortalama gunluk mum boyu, ATR20).
   CIKIS : hedef YOK. Fiyat son 10 gunun en dusugunun altina inerse cikis (kar ya da zarar).
   1R = 2N.  Gunde yon basina tek giris, sembolde ayni anda tek islem.

2) TURTLE SOUP (Linda Raschke, 1995 - "Street Smarts")               [LONG; SHORT birebir tersi]
   SART  : onceki 20 gunluk dip, en az 4 gun once yapilmis olmali.
   1     : bugun fiyat o dibin ALTINA iner (yeni 20 gunluk dip = likidite supurmesi).
   GIRIS : ayni gun fiyat eski dibin USTUNE geri cikarsa, eski dip seviyesinden alis.
           Ayni gun geri cikmazsa kurulum iptal.
   STOP  : gunun o ana kadarki en dusugu - 1 tick.
   HEDEF : 2R (stopun 2 kati).

ORTAK: islem basina risk 10.000 $'in %1'i = 100 $.  Spread maliyeti 6 $'i gecen islem acilmaz,
       spread maliyeti sonuctan dusulur.  Komisyon, gunluk zarar limiti YOK.
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

GUN = 180
BASLANGIC = 10000.0
RISK_DOLAR = 100.0
MAKAS_DOLAR = 6.0
LISTE_MIN_ISLEM = 5
LISTE_BASARI = 50.0
STRATEJI = ("TURTLE", "TURTLE SOUP")


def masaustu():
    ev = os.path.expanduser("~")
    for p in (os.path.join(ev, "Desktop"), os.path.join(ev, "OneDrive", "Desktop"), os.path.join(ev, "Masaüstü")):
        if os.path.isdir(p):
            return p
    return os.getcwd()


def cek(sembol, tf, bas, bit):
    r = None
    for _ in range(3):
        r = mt5.copy_rates_range(sembol, tf, bas, bit)
        if r is not None:
            break
        time.sleep(0.5)
    if r is None or not len(r):
        return None
    d = pd.DataFrame(r)
    if "spread" not in d.columns:
        d["spread"] = 0
    return d[["time", "open", "high", "low", "close", "spread"]].drop_duplicates("time").reset_index(drop=True)


def zaman(t):
    return datetime.utcfromtimestamp(int(t)).strftime("%Y-%m-%d %H:%M")


def gecis(P, dirn, sembol, kayit):
    if dirn > 0:
        o, h, l, c = P["o"], P["h"], P["l"], P["c"]
        dh, dl = P["dh"], P["dl"]
    else:
        o, h, l, c = -P["o"], -P["l"], -P["h"], -P["c"]
        dh, dl = -P["dl"], -P["dh"]
    T, di, sp, N, tick, sinir = P["t"], P["di"], P["sp"], P["N"], P["tick"], P["sinir"]
    nd, n = len(dh), len(T)
    hi20 = np.full(nd, np.nan); lo20 = np.full(nd, np.nan); lo10 = np.full(nd, np.nan); yas = np.zeros(nd, int)
    for d in range(20, nd):
        hi20[d] = dh[d - 20:d].max()
        lo10[d] = dl[d - 10:d].min()
        k = int(np.argmin(dl[d - 20:d]))
        lo20[d] = dl[d - 20 + k]
        yas[d] = 20 - k                      # eski dip kac gun once
    sg = 1 if dirn > 0 else -1
    yon = "LONG" if dirn > 0 else "SHORT"

    def ekle(st, i_g, i_c, e, s, t, cik, risk, sp_g):
        R = (cik - e) / risk
        mR = sp_g / risk
        kayit.append(dict(strateji=st, sembol=sembol, yon=yon, giris_zaman=zaman(T[i_g]), cikis_zaman=zaman(T[i_c]),
                          cikisT=int(T[i_c]), giris=sg * e, stop=sg * s, hedef=(sg * t if t is not None else ""),
                          cikis=sg * cik, stop_N=round(risk / N[di[i_g]], 2), R=round(R, 3),
                          R_net=round(R - mR, 3), dolar=round((R - mR) * RISK_DOLAR, 2)))

    # ---------------- TURTLE
    acik, son_gun = False, -1
    e = s = risk = spg = 0.0
    ig = 0
    for i in range(n):
        d = di[i]
        if d < 20 or np.isnan(N[d]) or N[d] <= 0:
            continue
        if acik and i > ig:
            lvl = max(s, lo10[d])
            if l[i] <= lvl:
                ekle("TURTLE", ig, i, e, s, None, min(o[i], lvl), risk, spg)
                acik = False
        if not acik and son_gun != d and T[i] >= sinir and h[i] >= hi20[d]:
            son_gun = d
            e0 = max(o[i], hi20[d])
            r0 = 2.0 * N[d]
            if RISK_DOLAR * sp[i] / r0 > MAKAS_DOLAR:
                continue
            acik, ig, e, risk, spg = True, i, e0, r0, sp[i]
            s = e - risk
    # ---------------- TURTLE SOUP
    acik = False
    gun, kirdi, bitti, gdip, kb = -1, False, False, 0.0, 0
    t_ = 0.0
    for i in range(n):
        d = di[i]
        if d != gun:
            gun, kirdi, bitti, gdip = d, False, False, l[i]
        gdip = min(gdip, l[i])
        if acik and i > ig:
            if l[i] <= s:
                ekle("TURTLE SOUP", ig, i, e, s, t_, min(o[i], s), risk, spg)
                acik = False
            elif h[i] >= t_:
                ekle("TURTLE SOUP", ig, i, e, s, t_, max(o[i], t_), risk, spg)
                acik = False
        if acik or bitti or d < 20 or T[i] < sinir or yas[d] < 4:
            continue
        eski = lo20[d]
        if not kirdi and l[i] < eski:
            kirdi, kb = True, i
        if kirdi and ((i > kb and h[i] >= eski) or (i == kb and c[i] > eski)):
            bitti = True
            e0 = max(o[i], eski) if i > kb else eski
            s0 = gdip - tick
            r0 = e0 - s0
            if r0 <= 0 or RISK_DOLAR * sp[i] / r0 > MAKAS_DOLAR:
                continue
            acik, ig, e, s, risk, spg = True, i, e0, s0, r0, sp[i]
            t_ = e + 2.0 * risk


def ozet(g):
    n = len(g)
    k = int((g["R_net"] > 0).sum())
    R = g["R_net"].sum()
    ok = g[g["R_net"] > 0]["R_net"].mean() if k else 0.0
    ko = g[g["R_net"] <= 0]["R_net"].mean() if n - k else 0.0
    return n, k, n - k, (100.0 * k / n if n else 0.0), R, ok, ko


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sembol", default="")
    ap.add_argument("--gun", type=int, default=GUN)
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
    bas = bit - timedelta(days=a.gun + 60)
    sinir = None
    tum = []
    print("Taranacak sembol: %d" % len(liste))
    for no, sb in enumerate(liste, 1):
        try:
            mt5.symbol_select(sb, True)
            bilgi = mt5.symbol_info(sb)
            if sinir is None:
                tk = mt5.symbol_info_tick(sb)
                sinir = (int(tk.time) if tk is not None and tk.time else int(time.time())) - a.gun * 86400
            D = cek(sb, mt5.TIMEFRAME_D1, bas, bit)
            H = cek(sb, mt5.TIMEFRAME_H1, bas, bit)
            if bilgi is None or D is None or H is None or len(D) < 40 or len(H) < 500:
                print("%3d/%d %-14s veri yok/az, atlandi" % (no, len(liste), sb))
                continue
            Dt = D["time"].values.astype(np.int64)
            Ht = H["time"].values.astype(np.int64)
            di = np.searchsorted(Dt, Ht - Ht % 86400, side="right") - 1
            ok = di >= 0
            H, Ht, di = H[ok].reset_index(drop=True), Ht[ok], di[ok]
            dh, dl, dc = D["high"].values, D["low"].values, D["close"].values
            pc = np.r_[dc[0], dc[:-1]]
            tr = np.maximum(dh - dl, np.maximum(np.abs(dh - pc), np.abs(dl - pc)))
            N = pd.Series(tr).rolling(20).mean().shift(1).values      # bugune kadarki 20 gun
            P = dict(t=Ht, o=H["open"].values, h=H["high"].values, l=H["low"].values, c=H["close"].values,
                     sp=H["spread"].values * bilgi.point, di=di, dh=dh, dl=dl, N=N,
                     tick=(getattr(bilgi, "trade_tick_size", 0) or bilgi.point), sinir=sinir)
            k = []
            gecis(P, 1, sb, k)
            gecis(P, -1, sb, k)
            tum.extend(k)
            sat = []
            for st in STRATEJI:
                g = [x for x in k if x["strateji"] == st]
                if g:
                    n, w, lo, b, R, _, _ = ozet(pd.DataFrame(g))
                    sat.append("%s: %d islem %%%.0f %+.1fR" % (st, n, b, R))
                else:
                    sat.append("%s: 0" % st)
            print("%3d/%d %-14s %s" % (no, len(liste), sb, "  |  ".join(sat)))
        except Exception as ex:
            print("%3d/%d %-14s HATA: %s" % (no, len(liste), sb, ex))
    mt5.shutdown()

    klasor = os.path.join(masaustu(), "turtle_6ay_" + datetime.now().strftime("%Y%m%d_%H%M"))
    os.makedirs(klasor, exist_ok=True)
    I = pd.DataFrame(tum)
    sat = ["TURTLE + TURTLE SOUP - 6 AYLIK TEST (%d gun)  %s" % (a.gun, datetime.now().strftime("%d.%m.%Y %H:%M")),
           "Her strateji AYRI hesap: 10.000 $ ile basladi, islem basina risk 100 $ (%1). Spread dahil.",
           "Sure: %.0f dk   Sembol: %d" % ((time.time() - t0) / 60.0, len(liste)),
           "Basari = karla kapanan islem / butun islemler."]
    aciklama = {"TURTLE": "STOP 2N (2 x 20 gunluk ATR) | HEDEF YOK, cikis 10 gunluk dip/tepe kirilinca",
                "TURTLE SOUP": "STOP gunun dibi/tepesi - 1 tick | HEDEF 2R"}
    S_all = []
    if len(I):
        I.drop(columns=["cikisT"]).to_csv(os.path.join(klasor, "2_islemler.csv"), index=False, sep=";", decimal=",")
    for st in STRATEJI:
        sat += ["", "=" * 78, "== %s ==   %s" % (st, aciklama[st]), "=" * 78]
        G = I[I["strateji"] == st].sort_values("cikisT") if len(I) else pd.DataFrame()
        if not len(G):
            sat.append("Hic islem yok.")
            continue
        n, w, lo, b, R, ok, ko = ozet(G)
        bak = BASLANGIC + G["dolar"].cumsum().values
        dd = (np.maximum.accumulate(np.r_[BASLANGIC, bak])[1:] - bak).max()
        sat += ["Islem %d   karli %d   zararli %d   BASARI %%%.1f" % (n, w, lo, b),
                "Toplam %+.1fR  =  %+.0f $     10.000 $  ->  %.0f $     en buyuk dusus %.0f $"
                % (R, R * RISK_DOLAR, BASLANGIC + R * RISK_DOLAR, dd),
                "Ortalama kazanc %+.2fR   ortalama kayip %+.2fR   ortalama stop %.2f N (gunluk ATR)"
                % (ok, ko, G["stop_N"].mean())]
        for y in ("LONG", "SHORT"):
            g = G[G["yon"] == y]
            if len(g):
                n2, w2, l2, b2, R2, _, _ = ozet(g)
                sat.append("  %-5s %4d islem  basari %%%.1f  %+.1fR  %+.0f $" % (y, n2, b2, R2, R2 * RISK_DOLAR))
        S = []
        for sb, g in G.groupby("sembol"):
            n2, w2, l2, b2, R2, ok2, ko2 = ozet(g)
            S.append(dict(strateji=st, sembol=sb, islem=n2, karli=w2, zararli=l2, basari=round(b2, 1),
                          R=round(R2, 2), dolar=round(R2 * RISK_DOLAR, 0), ort_stop_N=round(g["stop_N"].mean(), 2)))
        S = pd.DataFrame(S).sort_values("R", ascending=False)
        S_all.append(S)
        E = S[(S["islem"] >= LISTE_MIN_ISLEM) & (S["basari"] > LISTE_BASARI)]
        sat += ["", "-- BASARI %%%d USTU SEMBOLLER (en az %d islem): %d sembol --" % (LISTE_BASARI, LISTE_MIN_ISLEM, len(E)),
                "%-14s %6s %6s %8s %8s %8s %9s" % ("sembol", "islem", "karli", "basari", "R", "dolar", "stop(N)")]
        for _, r in E.iterrows():
            sat.append("%-14s %6d %6d %7.1f%% %+8.1f %+8.0f %9.2f" % (r["sembol"], r["islem"], r["karli"], r["basari"],
                                                                    r["R"], r["dolar"], r["ort_stop_N"]))
        if len(E):
            Re = E["R"].sum()
            sat.append("SADECE BU SEMBOLLERLE: %+.1fR = %+.0f $  ->  10.000 $ -> %.0f $   (geriye bakarak secildi!)"
                       % (Re, Re * RISK_DOLAR, BASLANGIC + Re * RISK_DOLAR))
        sat += ["", "-- EN IYI 15 SEMBOL (R) --"]
        for _, r in S.head(15).iterrows():
            sat.append("%-14s %4d islem  basari %5.1f%%  %+7.1fR  %+7.0f $" % (r["sembol"], r["islem"], r["basari"],
                                                                            r["R"], r["dolar"]))
    if S_all:
        pd.concat(S_all).to_csv(os.path.join(klasor, "1_semboller.csv"), index=False, sep=";", decimal=",")
    yaz = "\n".join(sat)
    with open(os.path.join(klasor, "0_OZET.txt"), "w", encoding="utf-8") as f:
        f.write(yaz)
    print("\n" + yaz)
    print("\nSonuclar: " + klasor)


if __name__ == "__main__":
    main()
