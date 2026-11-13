# -*- coding: utf-8 -*-
"""
GOLDEN CROSS EA - 6 AYLIK GECMIS TEST - BUTUN SEMBOLLER
=======================================================
Calistir:   py -3.8 C:\\Users\\User\\Desktop\\golden_cross_6ay.py
Gerekli:    py -3.8 -m pip install MetaTrader5 pandas numpy
Sadece bazi semboller:   py -3.8 golden_cross_6ay.py --sembol EURUSD,XAUUSD
MT5 acik olmali. SADECE gecmis veri okur, ISLEM ACMAZ.
NOT: MT5 > Araclar > Secenekler > Grafikler > "Grafikteki en fazla cubuk" = Sinirsiz olmali (1 dk veri).
Sonuclar MASAUSTUNE:  Masaustu\\golden_cross_6ay_<tarih>\\0_OZET.txt , 1_semboller.csv , 2_islemler.csv

180 GUN ONCE BASLAR, GUNUMUZE KADAR GIDER. Her an sadece o ana kadar olusmus mumlar kullanilir.
Donem bolunmez, sembol secilmez, ayar secilmez.

MANTIK = Golden_Cross_EA.mq5 BIREBIR (AL anlatiliyor, SAT tersi)
  1) Yon   : fiyat 100 EMA'nin ustunde (1 saatlik).
  2) Tetik : 9 EMA, 26 EMA'yi asagidan yukari keser.
  Mum kapanisi BEKLENMEZ: acik 1 saatlik mum her dakika kontrol edilir (EA 10 sn'de bir; burada 1 dk veri),
  iki sart tuttugu anda giris. Bir mumda tek islem.
  ATR(14) acik mum dahil (EA'daki gibi).  Makas > ATR x 0.12 ise islem yok.  Buyuk mum filtresi KAPALI.
  TEKRAR KILIDI: LONG acildiysa ters kesisim olmadan ikinci LONG yok (SHORT icin de ayni).
  Haric liste EA'daki ile ayni.
  Giris ASK (alis) / BID (satis); stop ve hedef EA'daki gibi o fiyattan; spread dahil.

DENENEN STOP / HEDEF (hedef her zaman stopun 2 kati = 1:2)
  stop 0.70 ATR - hedef 1.40 ATR , 0.80-1.60 , 0.90-1.80 , 1.00-2.00 , 1.10-2.20 , 1.20-2.40 ,
  1.30-2.60 , 1.40-2.80 , 1.50-3.00
  Giris noktalari hepsinde AYNI; sadece stop/hedef mesafesi degisir.
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
HIZLI, YAVAS, TREND, ATR_P = 9, 26, 100, 14
MAKAS_SINIR = 0.12
STOPLAR = [0.70, 0.80, 0.90, 1.00, 1.10, 1.20, 1.30, 1.40, 1.50]
RR = 2.0
HARIC = "USDCHF,USDDKK,EURGBP,EURHUF,USDHKD,USDHUF,XPTUSD,SPCX,INTC,ADAUSD,CADCHF,AUDSGD"
LISTE_MIN_ISLEM = 5          # %50 ustu listesinde en az islem
BAKIS = 60 * 1440            # bir islem en fazla 60 gun izlenir (1 dk mum)


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


def ema(x, n):
    k = 2.0 / (n + 1.0)
    e = np.empty(len(x))
    e[0] = x[0]
    for i in range(1, len(x)):
        e[i] = x[i] * k + e[i - 1] * (1.0 - k)
    return e


def sembol_isle(sb, bas_h1, bas_m1, bit, sinir):
    bilgi = mt5.symbol_info(sb)
    if bilgi is None:
        return None, "bilgi yok"
    h1 = cek(sb, mt5.TIMEFRAME_H1, bas_h1, bit, 60)
    m1 = cek(sb, mt5.TIMEFRAME_M1, bas_m1, bit, 10)
    if h1 is None or m1 is None or len(h1) < TREND + 50 or len(m1) < 2000:
        return None, "veri yok/az"
    pt = bilgi.point
    HT = h1["time"].values.astype(np.int64)
    HH, HL, HC = h1["high"].values, h1["low"].values, h1["close"].values
    eh, es, et = ema(HC, HIZLI), ema(HC, YAVAS), ema(HC, TREND)
    kh, ks = 2.0 / (HIZLI + 1.0), 2.0 / (YAVAS + 1.0)
    pc = np.r_[HC[0], HC[:-1]]
    trc = np.maximum(HH - HL, np.maximum(np.abs(HH - pc), np.abs(HL - pc)))
    cs = np.r_[0.0, np.cumsum(trc)]
    lo20 = pd.Series(HL).rolling(20, min_periods=1).min().values
    hi20 = pd.Series(HH).rolling(20, min_periods=1).max().values

    MT = m1["time"].values.astype(np.int64)
    MH, ML, MC = m1["high"].values, m1["low"].values, m1["close"].values
    MS = m1["spread"].values.astype(float) * pt
    saat = MT - MT % 3600
    hi = np.searchsorted(HT, saat)
    hic = np.clip(hi, 0, len(HT) - 1)
    ok = (hi < len(HT)) & (HT[hic] == saat) & (hic >= TREND + 20) & (MT >= sinir)
    idx = np.nonzero(ok)[0]
    if len(idx) == 0:
        return None, "donemde veri yok"
    i = hic[idx]
    pr = i - 1
    p = MC[idx]
    pstar = (es[pr] * (1 - ks) - eh[pr] * (1 - kh)) / (kh - ks)   # bu fiyatin ustu = 9 EMA 26'nin ustunde
    up_ok = eh[pr] <= es[pr]
    dn_ok = eh[pr] >= es[pr]
    upS = up_ok & (p > pstar)
    dnS = dn_ok & (p < pstar)
    alS = upS & (p > et[pr])          # acik mumda kapanis > 100 EMA  <=>  fiyat > onceki 100 EMA
    satS = dnS & (p < et[pr])
    hr = pd.Series(MH[idx]).groupby(i).cummax().values
    lr = pd.Series(ML[idx]).groupby(i).cummin().values
    cp = HC[pr]
    trf = np.maximum(hr - lr, np.maximum(np.abs(hr - cp), np.abs(lr - cp)))
    atr = (cs[i] - cs[i - (ATR_P - 1)] + trf) / ATR_P
    sp = MS[idx]

    islemler = []
    kilit, son = 0, -1
    for q in np.nonzero(upS | dnS)[0]:
        if kilit == 1 and dnS[q]:
            kilit = 0
        if kilit == -1 and upS[q]:
            kilit = 0
        if son == i[q]:
            continue
        a_, s_ = alS[q], satS[q]
        if not (a_ or s_):
            continue
        if a_ and kilit == 1:
            continue
        if s_ and kilit == -1:
            continue
        A = atr[q]
        if A <= 0 or sp[q] > MAKAS_SINIR * A:
            continue
        yon = 1 if a_ else -1
        son, kilit = i[q], yon
        mi = idx[q]
        giris = p[q] + sp[q] if yon > 0 else p[q]
        gec = (giris - lo20[pr[q]]) / A if yon > 0 else (hi20[pr[q]] - giris) / A
        j0, j1 = mi + 1, min(len(MT), mi + 1 + BAKIS)
        kayit = dict(sembol=sb, zaman=datetime.utcfromtimestamp(int(MT[mi])).strftime("%Y-%m-%d %H:%M"),
                     yon="LONG" if yon > 0 else "SHORT", giris=giris, ATR=A, gec_ATR=round(gec, 2))
        if j0 >= j1:
            for s in STOPLAR:
                kayit["s%.2f" % s] = "ACIK"
                kayit["y%.2f" % s] = False
            islemler.append(kayit)
            continue
        if yon > 0:
            lmin = np.minimum.accumulate(ML[j0:j1])          # bid ile stop
            hmax = np.maximum.accumulate(MH[j0:j1])          # bid ile hedef
        else:
            hmax = np.maximum.accumulate(MH[j0:j1] + MS[j0:j1])   # ask ile stop
            lmin = np.minimum.accumulate(ML[j0:j1] + MS[j0:j1])   # ask ile hedef
        m = j1 - j0
        for s in STOPLAR:
            d = s * A
            if yon > 0:
                isl = np.searchsorted(-lmin, -(giris - d), "left")
                itp = np.searchsorted(hmax, giris + RR * d, "left")
                i1 = np.searchsorted(hmax, giris + d, "left")
            else:
                isl = np.searchsorted(hmax, giris + d, "left")
                itp = np.searchsorted(-lmin, -(giris - RR * d), "left")
                i1 = np.searchsorted(-lmin, -(giris - d), "left")
            if isl >= m and itp >= m:
                snc = "ACIK"
            elif itp < isl:
                snc = "TP"
            else:
                snc = "STOP"
            kayit["s%.2f" % s] = snc
            kayit["y%.2f" % s] = bool(snc == "STOP" and i1 < isl)   # once +1R gordu sonra stop
        islemler.append(kayit)
    return islemler, ""


def sayim(df, s):
    k = df["s%.2f" % s]
    tp, sl = int((k == "TP").sum()), int((k == "STOP").sum())
    n = tp + sl
    return n, tp, sl, (100.0 * tp / n if n else 0.0), tp * RR - sl, int((k == "ACIK").sum())


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
    haric = set(x.strip().upper() for x in HARIC.split(",") if x.strip())
    if a.sembol:
        liste = [x.strip() for x in a.sembol.split(",") if x.strip()]
    else:
        liste = [x.name for x in (mt5.symbols_get() or []) if x.name.upper() not in haric]
    bit = datetime.now() + timedelta(days=1)
    bas_m1 = bit - timedelta(days=a.gun + 2)
    bas_h1 = bit - timedelta(days=a.gun + 60)
    sinir = None
    tum = []
    print("Taranacak sembol: %d" % len(liste))
    for no, sb in enumerate(liste, 1):
        try:
            mt5.symbol_select(sb, True)
            if sinir is None:
                tk = mt5.symbol_info_tick(sb)
                simdi = int(tk.time) if tk is not None and tk.time else int(time.time())
                sinir = simdi - a.gun * 86400
            isl, neden = sembol_isle(sb, bas_h1, bas_m1, bit, sinir)
            if isl is None:
                print("%3d/%d %-14s atlandi (%s)" % (no, len(liste), sb, neden))
                continue
            tum.extend(isl)
            d = pd.DataFrame(isl) if isl else None
            if d is not None and len(d):
                n, tp, sl, b, R, ac = sayim(d, 1.00)
                print("%3d/%d %-14s islem %3d   (stop 1.0 ATR: TP %3d STOP %3d basari %5.1f%% %+6.1fR)"
                      % (no, len(liste), sb, len(d), tp, sl, b, R))
            else:
                print("%3d/%d %-14s islem   0" % (no, len(liste), sb))
        except Exception as ex:
            print("%3d/%d %-14s HATA: %s" % (no, len(liste), sb, ex))
    mt5.shutdown()

    klasor = os.path.join(masaustu(), "golden_cross_6ay_" + datetime.now().strftime("%Y%m%d_%H%M"))
    os.makedirs(klasor, exist_ok=True)
    I = pd.DataFrame(tum)
    sat = ["GOLDEN CROSS EA - 6 AYLIK TEST (%d gun)  %s" % (a.gun, datetime.now().strftime("%d.%m.%Y %H:%M")),
           "Mantik EA ile birebir. Hedef her zaman stopun 2 kati (1:2). Basabas icin basari en az %33.4 olmali.",
           "Sure: %.0f dk   Sembol: %d" % ((time.time() - t0) / 60.0, len(liste))]
    if not len(I):
        sat.append("Hic islem yok.")
    else:
        I.to_csv(os.path.join(klasor, "2_islemler.csv"), index=False, sep=";", decimal=",")
        # --- stop/hedef tablosu
        sat += ["", "== STOP / HEDEF (butun semboller) ==",
                "%-17s %6s %5s %5s %8s %9s %6s" % ("stop - hedef", "islem", "TP", "STOP", "basari", "R", "acik")]
        sonuc = []
        for s in STOPLAR:
            n, tp, sl, b, R, ac = sayim(I, s)
            sonuc.append((s, n, tp, sl, b, R))
            sat.append("%.2f - %.2f ATR     %6d %5d %5d %7.1f%% %+9.1f %6d" % (s, RR * s, n, tp, sl, b, R, ac))
        en = max(sonuc, key=lambda x: x[5])
        s_en = en[0]
        sat.append("EN IYI: stop %.2f ATR - hedef %.2f ATR  (%+.1fR, basari %%%.1f)" % (s_en, RR * s_en, en[5], en[4]))
        # --- sembol tablosu
        satirlar = []
        for sb, g in I.groupby("sembol"):
            r = dict(sembol=sb)
            for s in STOPLAR:
                n, tp, sl, b, R, ac = sayim(g, s)
                r["islem_%.2f" % s], r["basari_%.2f" % s], r["R_%.2f" % s] = n, round(b, 1), R
            satirlar.append(r)
        S = pd.DataFrame(satirlar)
        S.sort_values("R_%.2f" % s_en, ascending=False).to_csv(os.path.join(klasor, "1_semboller.csv"),
                                                              index=False, sep=";", decimal=",")
        # --- long / short
        sat += ["", "== LONG / SHORT (stop %.2f ATR) ==" % s_en]
        for y in ("LONG", "SHORT"):
            n, tp, sl, b, R, ac = sayim(I[I["yon"] == y], s_en)
            sat.append("%-6s islem %5d  TP %5d  STOP %5d  basari %5.1f%%  %+8.1fR" % (y, n, tp, sl, b, R))
        # --- gec giris
        sat += ["", "== GEC GIRIS: son 20 mumun dibinden (LONG) / tepesinden (SHORT) girise kadar kac ATR gidilmis ==",
                "(stop %.2f ATR)" % s_en]
        kova = [(0, 1), (1, 2), (2, 3), (3, 4), (4, 99)]
        gb = []
        for lo, up in kova:
            g = I[(I["gec_ATR"] >= lo) & (I["gec_ATR"] < up)]
            n, tp, sl, b, R, ac = sayim(g, s_en)
            gb.append((lo, up, n, b, R))
            sat.append("%-10s islem %5d  basari %5.1f%%  %+8.1fR"
                       % (("%d-%d ATR" % (lo, up)) if up < 99 else ("%d+ ATR" % lo), n, b, R))
        # --- +1R gorup stop olanlar
        y = I["y%.2f" % s_en]
        st = (I["s%.2f" % s_en] == "STOP")
        yuzde_y = 100.0 * y.sum() / max(1, st.sum())
        sat += ["", "== HEDEFE YARI YOLDA DONENLER (stop %.2f ATR) ==" % s_en,
                "STOP olan %d islemin %d tanesi (%%%.1f) once +1R kara gitmis, sonra stop olmus."
                % (st.sum(), y.sum(), yuzde_y)]
        # --- %50 ustu semboller
        for s in STOPLAR:
            E = S[(S["islem_%.2f" % s] >= LISTE_MIN_ISLEM) & (S["basari_%.2f" % s] > 50.0)]
            E = E.sort_values("R_%.2f" % s, ascending=False)
            sat += ["", "== BASARI %%50 USTU SEMBOLLER - stop %.2f / hedef %.2f ATR (en az %d islem) : %d sembol =="
                    % (s, RR * s, LISTE_MIN_ISLEM, len(E)),
                    "%-14s %6s %8s %8s" % ("sembol", "islem", "basari", "R")]
            for _, r in E.iterrows():
                sat.append("%-14s %6d %7.1f%% %+8.1f" % (r["sembol"], r["islem_%.2f" % s], r["basari_%.2f" % s],
                                                        r["R_%.2f" % s]))
        # --- otomatik yorum
        yorum = ["", "== TARAYICI YORUMU (sayilardan otomatik) =="]
        if en[5] > 0:
            yorum.append("- Butun semboller toplaminda en iyi ayar ARTIDA: stop %.2f ATR (%+.1fR)." % (s_en, en[5]))
        else:
            yorum.append("- Hicbir stop/hedef ayari butun semboller toplaminda artiya gecmiyor (en iyi %+.1fR)." % en[5])
        ilk = [x for x in gb if x[2] >= 30]
        if len(ilk) >= 2:
            erken, gec_ = ilk[0], ilk[-1]
            if erken[3] - gec_[3] >= 5:
                yorum.append("- GEC GIRIS ZARAR VERIYOR: hareketin basinda (%d-%d ATR) basari %%%.1f, gec girislerde "
                             "(%s ATR) %%%.1f. Daha erken giris daha iyi olurdu."
                             % (erken[0], erken[1], erken[3], ("%d+" % gec_[0]) if gec_[1] >= 99 else
                                ("%d-%d" % (gec_[0], gec_[1])), gec_[3]))
            elif gec_[3] - erken[3] >= 5:
                yorum.append("- Gec girisler daha basarili (%%%.1f), erken girisler (%%%.1f) daha kotu: "
                             "trend oturduktan sonra girmek ise yariyor." % (gec_[3], erken[3]))
            else:
                yorum.append("- Girisin gec ya da erken olmasi basariyi pek degistirmiyor.")
        if yuzde_y >= 30:
            yorum.append("- Stop olan islemlerin %%%.1f'i once +1R kara gitmis: +1R'de stopu girise cekmek (basabas) "
                         "bu islemlerin zararini sifirlardi." % yuzde_y)
        nl, _, _, bl, Rl, _ = sayim(I[I["yon"] == "LONG"], s_en)
        ns, _, _, bs, Rs, _ = sayim(I[I["yon"] == "SHORT"], s_en)
        if abs(bl - bs) >= 5:
            yorum.append("- %s daha basarili (%%%.1f) , %s (%%%.1f)." % (("LONG", bl, "SHORT", bs) if bl > bs
                                                                        else ("SHORT", bs, "LONG", bl)))
        sat += yorum
    yaz = "\n".join(sat)
    with open(os.path.join(klasor, "0_OZET.txt"), "w", encoding="utf-8") as f:
        f.write(yaz)
    print("\n" + yaz)
    print("\nSonuclar: " + klasor)


if __name__ == "__main__":
    main()
