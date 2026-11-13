# -*- coding: utf-8 -*-
"""
TURTLE SOUP - 1 YILLIK TEST - BUTUN SEMBOLLER - 10.000 $ ILE BASLASAYDI - STOP x HEDEF CESITLERI
================================================================================================
Calistir:   py -3.8 C:\\Users\\User\\Desktop\\turtle_soup_1yil.py
Gerekli:    py -3.8 -m pip install MetaTrader5 pandas numpy
Sadece bazi semboller:   py -3.8 turtle_soup_1yil.py --sembol BTCUSD,US100.cash
MT5 acik olmali. SADECE gecmis veri okur, ISLEM ACMAZ.
Sonuclar MASAUSTUNE:  Masaustu\\turtle_soup_1yil_<tarih>\\0_OZET.txt , 1_semboller.csv , 2_islemler.csv

365 GUN ONCE 10.000 $ ile baslar, bugune kadar gider. Her an sadece o ana kadar olusmus mumlar kullanilir.
Gunluk seviyeler GUNLUK mumdan, giris/cikis sirasi 1 SAATLIK mumdan.

TURTLE SOUP (Linda Raschke, 1995)                                   [LONG; SHORT birebir tersi]
  SART  : onceki 20 gunluk dip, en az 4 gun once yapilmis olmali.
  1     : bugun fiyat o dibin ALTINA iner (yeni 20 gunluk dip = supurme).
  GIRIS : ayni gun fiyat eski dibin USTUNE geri cikarsa eski dipten alis. Ayni gun cikmazsa iptal.
          (Kirilim ve geri donus ayni saatlik mumdaysa: o mumun kapanisindan.)
STOP CESITLERI
  GUN_DIBI : giris anindan ONCEKI gunun en dusugu - 1 tick.  (ONCEKI 6 aylik testte giris mumunun
             tamami kullaniliyordu, iyimserdi; DUZELTILDI.  Giris mumu stopun altina inerse ZARAR sayilir.)
  0.5_ATR  : giristen 0.5 x gunluk ATR(20) asagi
  1.0_ATR  : giristen 1.0 x gunluk ATR(20) asagi
HEDEF CESITLERI
  2R / 3R / 4R : stopun 2 / 3 / 4 kati
  20G_TEPE     : son 20 gunun en yuksegi (karsi taraf likiditesi); girisin ustunde degilse o cesitte islem yok
Butun cesitlerde GIRISLER AYNI, sadece stop ve hedef degisir.  Sinyaller birbirini engellemez.
ORTAK: islem basina risk 10.000 $'in %1'i = 100 $.  Spread maliyeti 6 $'i gecen islem acilmaz,
       spread maliyeti sonuctan dusulur.  Boslukla acilista stop/hedef acilis fiyatindan.
LISTE: en az 10 islem ve basari: 2R'de %40, 3R'de %30, 4R'de %25, 20G_TEPE'de %35 ustu.
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

GUN = 365
BASLANGIC = 10000.0
RISK_DOLAR = 100.0
MAKAS_DOLAR = 6.0
STOPLAR = ["GUN_DIBI", "0.5_ATR", "1.0_ATR"]
HEDEFLER = ["2R", "3R", "4R", "20G_TEPE"]
ESIK = {"2R": 40.0, "3R": 30.0, "4R": 25.0, "20G_TEPE": 35.0}
LISTE_MIN_ISLEM = 10


def masaustu():
    ev = os.path.expanduser("~")
    for p in (os.path.join(ev, "Desktop"), os.path.join(ev, "OneDrive", "Desktop"), os.path.join(ev, "Masaüstü")):
        if os.path.isdir(p):
            return p
    return os.getcwd()


def cek(sembol, tf, bas, bit, parca):
    out, a = [], bas
    while a < bit:
        b = min(a + timedelta(days=parca), bit)
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
    hi20 = np.full(nd, np.nan); lo20 = np.full(nd, np.nan); yas = np.zeros(nd, int)
    for d in range(20, nd):
        hi20[d] = dh[d - 20:d].max()
        k = int(np.argmin(dl[d - 20:d]))
        lo20[d] = dl[d - 20 + k]
        yas[d] = 20 - k
    sg = 1 if dirn > 0 else -1
    gun, kirdi, bitti, kb = -1, False, False, 0
    gdip_once = np.inf
    for i in range(n):
        d = di[i]
        if d != gun:
            gun, kirdi, bitti, gdip_once = d, False, False, np.inf
        if bitti or d < 20 or T[i] < sinir or yas[d] < 4 or np.isnan(N[d]) or N[d] <= 0:
            gdip_once = min(gdip_once, l[i])
            continue
        eski = lo20[d]
        if not kirdi and l[i] < eski:
            kirdi, kb = True, i
        giris = False
        if kirdi and i > kb and h[i] >= eski:
            e = max(o[i], eski)
            sdip = min(gdip_once, o[i]) - tick      # giris anindan onceki gun dibi (bu mumun dibi BILINMIYOR)
            giris = True
        elif kirdi and i == kb and c[i] > eski:
            e = c[i]                                 # kirilim ve donus ayni mumda: kapanistan
            sdip = min(gdip_once, l[i]) - tick
            giris = True
        gdip_once = min(gdip_once, l[i])
        if not giris:
            continue
        bitti = True
        j0 = i + 1
        if j0 >= n:
            continue
        lmin = np.minimum.accumulate(l[j0:])
        hmax = np.maximum.accumulate(h[j0:])
        m = n - j0
        for st in STOPLAR:
            s = sdip if st == "GUN_DIBI" else e - (0.5 if st == "0.5_ATR" else 1.0) * N[d]
            risk = e - s
            if risk <= 0 or RISK_DOLAR * sp[i] / risk > MAKAS_DOLAR:
                continue
            for hd in HEDEFLER:
                if hd == "20G_TEPE":
                    t = hi20[d]
                    if not t > e:
                        continue
                else:
                    t = e + float(hd[0]) * risk
                if l[i] <= s and st == "GUN_DIBI" and i > kb:
                    snc, px, ic = "STOP", s, i          # giris mumu stopun altina indi: zarar say
                else:
                    isl = int(np.searchsorted(-lmin, -s, "left"))
                    itp = int(np.searchsorted(hmax, t, "left"))
                    if isl >= m and itp >= m:
                        continue                         # hala acik, sayilmaz
                    if isl <= itp:
                        ic = j0 + isl
                        snc, px = "STOP", min(o[ic], s)
                    else:
                        ic = j0 + itp
                        snc, px = "HEDEF", max(o[ic], t)
                R = (px - e) / risk
                mR = sp[i] / risk
                kayit.append(dict(stop_tipi=st, hedef_tipi=hd, sembol=sembol, yon="LONG" if dirn > 0 else "SHORT",
                                  giris_zaman=zaman(T[i]), cikis_zaman=zaman(T[ic]), cikisT=int(T[ic]),
                                  giris=sg * e, stop=sg * s, hedef=sg * t, cikis=sg * px, sonuc=snc,
                                  stop_ATR=round(risk / N[d], 2), R=round(R, 3), R_net=round(R - mR, 3),
                                  dolar=round((R - mR) * RISK_DOLAR, 2)))


def ozet(g):
    n = len(g)
    w = int((g["sonuc"] == "HEDEF").sum())
    R = g["R_net"].sum()
    return n, w, n - w, (100.0 * w / n if n else 0.0), R


def dusus(g):
    g = g.sort_values("cikisT")
    bak = BASLANGIC + g["dolar"].cumsum().values
    return float((np.maximum.accumulate(np.r_[BASLANGIC, bak])[1:] - bak).max()) if len(bak) else 0.0


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
    print("Taranacak sembol: %d   (%d gun)" % (len(liste), a.gun))
    for no, sb in enumerate(liste, 1):
        try:
            mt5.symbol_select(sb, True)
            bilgi = mt5.symbol_info(sb)
            if sinir is None:
                tk = mt5.symbol_info_tick(sb)
                sinir = (int(tk.time) if tk is not None and tk.time else int(time.time())) - a.gun * 86400
            D = cek(sb, mt5.TIMEFRAME_D1, bas, bit, 400)
            H = cek(sb, mt5.TIMEFRAME_H1, bas, bit, 120)
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
            N = pd.Series(tr).rolling(20).mean().shift(1).values
            P = dict(t=Ht, o=H["open"].values, h=H["high"].values, l=H["low"].values, c=H["close"].values,
                     sp=H["spread"].values * bilgi.point, di=di, dh=dh, dl=dl, N=N,
                     tick=(getattr(bilgi, "trade_tick_size", 0) or bilgi.point), sinir=sinir)
            k = []
            gecis(P, 1, sb, k)
            gecis(P, -1, sb, k)
            tum.extend(k)
            g = [x for x in k if x["stop_tipi"] == "GUN_DIBI" and x["hedef_tipi"] == "2R"]
            if g:
                n, w, lo, b, R = ozet(pd.DataFrame(g))
                print("%3d/%d %-14s GUN_DIBI+2R: %3d islem  basari %5.1f%%  %+6.1fR" % (no, len(liste), sb, n, b, R))
            else:
                print("%3d/%d %-14s GUN_DIBI+2R: 0 islem" % (no, len(liste), sb))
        except Exception as ex:
            print("%3d/%d %-14s HATA: %s" % (no, len(liste), sb, ex))
    mt5.shutdown()

    klasor = os.path.join(masaustu(), "turtle_soup_1yil_" + datetime.now().strftime("%Y%m%d_%H%M"))
    os.makedirs(klasor, exist_ok=True)
    I = pd.DataFrame(tum)
    sat = ["TURTLE SOUP - %d GUNLUK TEST  %s" % (a.gun, datetime.now().strftime("%d.%m.%Y %H:%M")),
           "Her cesit AYRI hesap: 10.000 $ ile basladi, islem basina risk 100 $ (%1). Spread dahil.",
           "Sure: %.0f dk   Sembol: %d" % ((time.time() - t0) / 60.0, len(liste)),
           "Basari = hedefe giden islem / butun islemler."]
    if not len(I):
        sat.append("Hic islem yok.")
    else:
        I.drop(columns=["cikisT"]).to_csv(os.path.join(klasor, "2_islemler.csv"), index=False, sep=";", decimal=",")
        sat += ["", "== BUTUN SEMBOLLER: STOP x HEDEF ==",
                "%-9s %-9s %6s %6s %6s %8s %9s %10s %10s %9s" % ("stop", "hedef", "islem", "hedef", "stop", "basari",
                                                                "R", "dolar", "10.000->", "dusus")]
        sonuc = []
        for st in STOPLAR:
            for hd in HEDEFLER:
                g = I[(I["stop_tipi"] == st) & (I["hedef_tipi"] == hd)]
                if not len(g):
                    continue
                n, w, lo, b, R = ozet(g)
                dd = dusus(g)
                sonuc.append((st, hd, R))
                sat.append("%-9s %-9s %6d %6d %6d %7.1f%% %+9.1f %+10.0f %10.0f %9.0f"
                           % (st, hd, n, w, lo, b, R, R * RISK_DOLAR, BASLANGIC + R * RISK_DOLAR, dd))
            sat.append("")
        en = max(sonuc, key=lambda x: x[2])
        sat.append("EN IYI: stop %s + hedef %s  (%+.1fR)" % en)
        for st, hd, _ in [en, ("GUN_DIBI", "2R", 0)]:
            g = I[(I["stop_tipi"] == st) & (I["hedef_tipi"] == hd)]
            for y in ("LONG", "SHORT"):
                n, w, lo, b, R = ozet(g[g["yon"] == y])
                sat.append("  %s+%s %-5s %4d islem  basari %%%.1f  %+.1fR" % (st, hd, y, n, b, R))
        S_all = []
        for st in STOPLAR:
            for hd in HEDEFLER:
                g = I[(I["stop_tipi"] == st) & (I["hedef_tipi"] == hd)]
                if not len(g):
                    continue
                S = []
                for sb, gg in g.groupby("sembol"):
                    n, w, lo, b, R = ozet(gg)
                    S.append(dict(stop_tipi=st, hedef_tipi=hd, sembol=sb, islem=n, hedef=w, stop=lo,
                                  basari=round(b, 1), R=round(R, 2), dolar=round(R * RISK_DOLAR, 0)))
                S = pd.DataFrame(S).sort_values("R", ascending=False)
                S_all.append(S)
                E = S[(S["islem"] >= LISTE_MIN_ISLEM) & (S["basari"] > ESIK[hd])]
                sat += ["", "-- %s + %s : basari %%%d ustu, en az %d islem : %d sembol --"
                        % (st, hd, ESIK[hd], LISTE_MIN_ISLEM, len(E))]
                for _, r in E.iterrows():
                    sat.append("   %-14s %4d islem  basari %5.1f%%  %+7.1fR  %+7.0f $"
                               % (r["sembol"], r["islem"], r["basari"], r["R"], r["dolar"]))
                if len(E):
                    Re = E["R"].sum()
                    sat.append("   SADECE BUNLARLA: %+.1fR -> 10.000 $ -> %.0f $  (geriye bakarak secildi!)"
                               % (Re, BASLANGIC + Re * RISK_DOLAR))
        pd.concat(S_all).to_csv(os.path.join(klasor, "1_semboller.csv"), index=False, sep=";", decimal=",")
    yaz = "\n".join(sat)
    with open(os.path.join(klasor, "0_OZET.txt"), "w", encoding="utf-8") as f:
        f.write(yaz)
    print("\n" + yaz)
    print("\nSonuclar: " + klasor)


if __name__ == "__main__":
    main()
