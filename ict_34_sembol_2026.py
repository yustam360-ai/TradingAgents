# -*- coding: utf-8 -*-
"""
ICT 34 SEMBOL TESTI - 2026 basindan bugune, her sembol KENDI mantigiyla (3 aylik testte bulunan, hic degistirilmedi)
================================================================================================================
Python 3.8:   py -3.8 ict_34_sembol_2026.py
Baska baslangic:   py -3.8 ict_34_sembol_2026.py --bas 2026-03-01
GEREKLI: ict_spread_test_3ay.py AYNI KLASORDE olmali (mantik oradan aliniyor).

MT5'e baglanir, SADECE gecmis veri okur, ISLEM ACMAZ.
  - SPREAD YOK, KOMISYON YOK (giris / stop / TP grafik fiyatiyla; 6 $ spread kurali yok).
    Not: "stop = tepe + makas" ve "FVG 1. mum + makas" ayarlarinda stopun YERI degismesin diye
    o anki makas yine stop payi olarak eklenir (mantik 3 aylik testteki gibi kalsin).
  - Islem basi 15 $ risk; en kucuk lotta zarar 30 $'i gecerse islem acilmaz.
  - TP her sembolun kendi ayari (2R ya da 3R).  Acik islem NY 16:00'da kapanir.
  - Saatler otomatik (yaz / kis), raporda TURKIYE saati.

CIKTI (ict_34_<tarih>/):
  0_OZET.txt         sembol bazli islem / TP / STOP / SURE / basari / R / $, aylik, 10.000 $ hesap
                     (gunluk limitsiz ve 250 $ gunluk limitli)
  1_islemler.csv     butun islemler (TR saati, ne supuruldu, giris, stop, TP, sonuc)
"""
from __future__ import print_function

import argparse
import os
import sys
import time
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

try:
    import ict_spread_test_3ay as T
except ImportError:
    sys.exit("ict_spread_test_3ay.py bu dosyayla AYNI KLASORDE olmali.")

mt5 = T.mt5
GUNLUK_LIMIT = 250.0

MANTIK = [
    ("EURUSD", "TF=5dk | LIK=SAAT | KIRILIM=GOVDE | PENCERE=KZ_HEPSI | ONAY=H1 | PD=YOK | GIRIS=FVG_KENAR | STOP=FVG1 | HEDEF=2R"),
    ("JP225.cash", "TF=3dk | LIK=SAAT | KIRILIM=GOVDE | PENCERE=AC_HEPSI | ONAY=H1 | PD=YOK | GIRIS=FVG_KENAR | STOP=SUP_02ATR | HEDEF=2R"),
    ("LNKUSD", "TF=1dk | LIK=HEPSI | KIRILIM=GOVDE | PENCERE=KZ_LONKAP | ONAY=H4 | PD=YOK | GIRIS=FVG_KENAR | STOP=FVG1 | HEDEF=3R"),
    ("XAUAUD", "TF=3dk | LIK=HEPSI | KIRILIM=GOVDE | PENCERE=AC_HEPSI | ONAY=H4 | PD=YOK | GIRIS=FVG_KENAR | STOP=SUP_02ATR | HEDEF=2R"),
    ("USDJPY", "TF=3dk | LIK=SAAT | KIRILIM=FITIL | PENCERE=AC_HEPSI | ONAY=YOK | PD=VAR | GIRIS=FVG_KENAR | STOP=FLUX | HEDEF=2R"),
    ("BNBUSD", "TF=1dk | LIK=SAAT | KIRILIM=GOVDE | PENCERE=KZ_LONKAP | ONAY=YOK | PD=YOK | GIRIS=FVG_ORTA | STOP=SUP_MAKAS | HEDEF=3R"),
    ("DOGEUSD", "TF=3dk | LIK=SAAT | KIRILIM=DISP | PENCERE=KZ_HEPSI | ONAY=GUN_KAP | PD=YOK | GIRIS=OB | STOP=SUP_02ATR | HEDEF=3R"),
    ("NZDCAD", "TF=5dk | LIK=HEPSI | KIRILIM=FITIL | PENCERE=KZ_LON | ONAY=H4 | PD=YOK | GIRIS=FVG_KENAR | STOP=SUP_MAKAS | HEDEF=2R"),
    ("NZDJPY", "TF=3dk | LIK=SWING | KIRILIM=GOVDE | PENCERE=KZ_HEPSI | ONAY=YOK | PD=VAR | GIRIS=FVG_ORTA | STOP=FVG1 | HEDEF=3R"),
    ("AAVUSD", "TF=1dk | LIK=HEPSI | KIRILIM=GOVDE | PENCERE=KZ_HEPSI | ONAY=GUN_SUP | PD=YOK | GIRIS=FVG_ORTA | STOP=FVG1 | HEDEF=3R"),
    ("MANUSD", "TF=1dk | LIK=HEPSI | KIRILIM=GOVDE | PENCERE=AC_LON | ONAY=YOK | PD=VAR | GIRIS=FVG_KENAR | STOP=SUP_MAKAS | HEDEF=3R"),
    ("EURCHF", "TF=5dk | LIK=SAAT | KIRILIM=FITIL | PENCERE=AC_LON | ONAY=YOK | PD=YOK | GIRIS=FVG_KENAR | STOP=FVG1 | HEDEF=2R"),
    ("COFFEE.c", "TF=3dk | LIK=HEPSI | KIRILIM=GOVDE | PENCERE=KZ_HEPSI | ONAY=YOK | PD=VAR | GIRIS=FVG_KENAR | STOP=FVG1 | HEDEF=2R"),
    ("AUDNZD", "TF=15dk | LIK=HEPSI | KIRILIM=FITIL | PENCERE=AC_HEPSI | ONAY=YOK | PD=VAR | GIRIS=FVG_KENAR | STOP=FVG1 | HEDEF=2R"),
    ("AUDCHF", "TF=3dk | LIK=HEPSI | KIRILIM=FITIL | PENCERE=AC_LON | ONAY=H1 | PD=YOK | GIRIS=FVG_KENAR | STOP=FVG1 | HEDEF=3R"),
    ("XRPUSD", "TF=1dk | LIK=SAAT | KIRILIM=DISP | PENCERE=AC_NY | ONAY=YOK | PD=YOK | GIRIS=FVG_ORTA | STOP=SUP_01ATR | HEDEF=3R"),
    ("VECUSD", "TF=15dk | LIK=SAAT | KIRILIM=FITIL | PENCERE=KZ_HEPSI | ONAY=H1 | PD=YOK | GIRIS=FVG_KENAR | STOP=SUP_01ATR | HEDEF=2R"),
    ("GBPNZD", "TF=5dk | LIK=HEPSI | KIRILIM=GOVDE | PENCERE=KZ_LON | ONAY=YOK | PD=YOK | GIRIS=FVG_ORTA | STOP=SUP_01ATR | HEDEF=2R"),
    ("US2000.cash", "TF=5dk | LIK=SAAT | KIRILIM=DISP | PENCERE=AC_LON | ONAY=H1 | PD=YOK | GIRIS=FVG_KENAR | STOP=SUP_MAKAS | HEDEF=3R"),
    ("NERUSD", "TF=3dk | LIK=SAAT | KIRILIM=DISP | PENCERE=KZ_ASYA | ONAY=H1 | PD=YOK | GIRIS=FVG_ORTA | STOP=SUP_MAKAS | HEDEF=2R"),
    ("AAPL", "TF=1dk | LIK=HEPSI | KIRILIM=FITIL | PENCERE=SB | ONAY=H4 | PD=YOK | GIRIS=FVG_ORTA | STOP=FVG1 | HEDEF=3R"),
    ("EU50.cash", "TF=3dk | LIK=HEPSI | KIRILIM=DISP | PENCERE=KZ_HEPSI | ONAY=YOK | PD=VAR | GIRIS=OB | STOP=SUP_01ATR | HEDEF=2R"),
    ("GBPCHF", "TF=3dk | LIK=HEPSI | KIRILIM=FITIL | PENCERE=KZ_HEPSI | ONAY=GUN_SUP | PD=YOK | GIRIS=OB | STOP=SUP_MAKAS | HEDEF=3R"),
    ("USDCHF", "TF=1dk | LIK=GUN | KIRILIM=GOVDE | PENCERE=AC_HEPSI | ONAY=YOK | PD=VAR | GIRIS=FVG_KENAR | STOP=FVG1 | HEDEF=3R"),
    ("GBPJPY", "TF=5dk | LIK=SWING | KIRILIM=FITIL | PENCERE=AC_LON | ONAY=YOK | PD=YOK | GIRIS=FVG_KENAR | STOP=SUP_01ATR | HEDEF=3R"),
    ("USDMXN", "TF=5dk | LIK=SAAT | KIRILIM=GOVDE | PENCERE=AC_NY | ONAY=H1 | PD=YOK | GIRIS=FVG_KENAR | STOP=FVG1 | HEDEF=3R"),
    ("DXY.cash", "TF=3dk | LIK=SAAT | KIRILIM=FITIL | PENCERE=SB_LON | ONAY=YOK | PD=YOK | GIRIS=FVG_KENAR | STOP=SUP_MAKAS | HEDEF=2R"),
    ("CADCHF", "TF=1dk | LIK=GUN | KIRILIM=FITIL | PENCERE=AC_HEPSI | ONAY=YOK | PD=YOK | GIRIS=FVG_KENAR | STOP=SUP_MAKAS | HEDEF=2R"),
    ("SPN35.cash", "TF=3dk | LIK=HEPSI | KIRILIM=FITIL | PENCERE=KZ_HEPSI | ONAY=YOK | PD=VAR | GIRIS=OB | STOP=FLUX | HEDEF=3R"),
    ("N25.cash", "TF=15dk | LIK=HEPSI | KIRILIM=GOVDE | PENCERE=KZ_HEPSI | ONAY=H1 | PD=YOK | GIRIS=FVG_KENAR | STOP=FVG1 | HEDEF=2R"),
    ("AVAUSD", "TF=3dk | LIK=HEPSI | KIRILIM=FITIL | PENCERE=KZ_HEPSI | ONAY=GUN_SUP | PD=YOK | GIRIS=OB | STOP=FLUX | HEDEF=3R"),
    ("DOTUSD", "TF=3dk | LIK=SWING | KIRILIM=FITIL | PENCERE=AC_HEPSI | ONAY=YOK | PD=VAR | GIRIS=FVG_ORTA | STOP=FVG1 | HEDEF=2R"),
    ("MBG", "TF=15dk | LIK=HEPSI | KIRILIM=FITIL | PENCERE=AC_HEPSI | ONAY=YOK | PD=YOK | GIRIS=FVG_ORTA | STOP=SUP_01ATR | HEDEF=3R"),
    ("EURNOK", "TF=5dk | LIK=SAAT | KIRILIM=GOVDE | PENCERE=KZ_LON | ONAY=YOK | PD=YOK | GIRIS=FVG_ORTA | STOP=SUP_MAKAS | HEDEF=2R"),
]


def indeks_tablosu():
    tab = {}
    for mi in range(T.NM):
        for k in range(T.NL):
            tab[T.birlesim_ad(mi, k)] = (mi, k)
    return tab


def dk_tr_to_sunucu(tr_metin, gun):
    t = datetime.strptime(tr_metin, "%Y-%m-%d %H:%M")
    dk = int((t - datetime(1970, 1, 1)).total_seconds() // 60)
    return dk - (3 - T.sunucu_utc(T.gun_tarih(gun))) * 60


def hesap(isl, limit):
    """10.000 $ hesap.  limit: o gun kapanan islemlerin zarari limit'e ulastiysa o gun yeni islem acilmaz"""
    if not len(isl):
        return None, isl
    d = isl.sort_values("dolum_dk").reset_index(drop=True)
    alinan = np.ones(len(d), bool)
    if limit:
        for i in range(len(d)):
            g = d.at[i, "dolum_dk"] // 1440
            onceki = d[alinan & (np.arange(len(d)) < i) & (d["cikis_dk"] // 1440 == g) & (d["cikis_dk"] <= d.at[i, "dolum_dk"])]
            if onceki["dolar"].sum() <= -limit:
                alinan[i] = False
    x = d[alinan].sort_values("cikis_dk")
    bak = T.BASLANGIC + x["dolar"].cumsum().to_numpy()
    tepe = np.maximum.accumulate(np.r_[T.BASLANGIC, bak])[1:]
    gunluk = x.groupby(x["cikis_dk"] // 1440)["dolar"].sum()
    hedef = np.flatnonzero(bak >= T.BASLANGIC + 1000)
    return dict(bitis=bak[-1], net=bak[-1] - T.BASLANGIC, en_dusuk=min(T.BASLANGIC, bak.min()), dusus=(bak - tepe).min(),
                en_kotu_gun=gunluk.min(), en_iyi_gun=gunluk.max(), atlanan=int((~alinan).sum()),
                hedef_tarih=(x.iloc[hedef[0]]["cikis_tr"][:10] if hedef.size else "-"),
                gunluk_ihlal=int((gunluk < -300).sum()), max_ihlal=bool(bak.min() < T.BASLANGIC - 1000)), x


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bas", default="2026-01-01", help="baslangic tarihi (YYYY-AA-GG)")
    ap.add_argument("--cikti", default="")
    args = ap.parse_args()
    if mt5 is None:
        sys.exit("MetaTrader5 modulu yok:  py -3.8 -m pip install MetaTrader5")
    if not mt5.initialize():
        sys.exit("MT5 baglantisi kurulamadi: %s" % (mt5.last_error(),))
    T.SPREAD_DAHIL = False
    hs = mt5.account_info()
    print("MT5 bagli: %s  (sadece gecmis veri, islem acilmiyor)" % (hs.server if hs else "?"))
    saat_notu = T.saat_dogrula([s for s, _ in MANTIK])
    print(saat_notu)
    tab = indeks_tablosu()
    for s, ad in MANTIK:
        if ad not in tab:
            sys.exit("Mantik bulunamadi: %s %s" % (s, ad))
    bas = datetime.strptime(args.bas, "%Y-%m-%d")
    bas_gun = int((bas - datetime(1970, 1, 1)).total_seconds() // 86400)
    simdi = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=T.sunucu_utc(datetime.now(timezone.utc).date()))
    klasor = args.cikti or ("ict_34_%s" % datetime.now().strftime("%Y%m%d_%H%M"))
    if not os.path.isdir(klasor):
        os.makedirs(klasor)
    yaz = dict(sep=";", decimal=",", index=False, encoding="utf-8-sig")
    tum_tf = list(T.TFLER)
    print("Sembol: %d | %s -> bugun | spread yok, risk 15 $" % (len(MANTIK), args.bas))
    tum, satir, yok, t0 = [], [], [], time.time()
    for n_, (s, ad) in enumerate(MANTIK, 1):
        mi, k = tab[ad]
        if not mt5.symbol_select(s, True):
            yok.append(s); print("[%d/%d] %s : sembol yok" % (n_, len(MANTIK), s)); continue
        bilgi = mt5.symbol_info(s)
        vpl = T.deger_lot(s, bilgi) if bilgi is not None else None
        m1 = T.cek(s, mt5.TIMEFRAME_M1, bas - timedelta(days=10), simdi + timedelta(days=1), 15)
        if bilgi is None or not vpl or m1 is None or len(m1) < 5000:
            yok.append(s); print("[%d/%d] %s : veri yok" % (n_, len(MANTIK), s)); continue
        ilk = datetime(1970, 1, 1) + timedelta(seconds=int(m1["time"].iloc[0]))
        K = T.MASKELER[mi][0]
        T.TFLER = sorted(set([K, 15]))                   # sadece gereken zaman dilimi (hiz icin)
        sonuc = T.sembol_isle(s, m1, bilgi, vpl, bas_gun)
        T.TFLER = tum_tf
        isl = []
        if sonuc is not None:
            V = T.Veri(*(sonuc + (bas_gun,)))
            isl = T.islemler(V, s, {(mi, k): ad})
        for r in isl:
            r["dolum_dk"] = dk_tr_to_sunucu(r["dolum_tr"], r["gun"])
        tum += isl
        x = pd.DataFrame(isl)
        n = len(x)
        tp = int((x["sonuc"] == "TP").sum()) if n else 0
        st = int((x["sonuc"] == "STOP").sum()) if n else 0
        su = int((x["sonuc"] == "SURE").sum()) if n else 0
        satir.append(dict(sembol=s, islem=n, TP=tp, STOP=st, SURE=su,
                          basari=round(100.0 * (x["R"] > 0).mean(), 1) if n else 0.0,
                          net_R=round(x["R"].sum(), 1) if n else 0.0, dolar=round(x["dolar"].sum(), 2) if n else 0.0,
                          veri_bas=ilk.strftime("%Y-%m-%d"), mantik=ad))
        print("[%d/%d] %s : %d islem, TP %d, STOP %d, SURE %d, %+.2f $  (%.0f sn)"
              % (n_, len(MANTIK), s, n, tp, st, su, satir[-1]["dolar"], time.time() - t0))
    mt5.shutdown()
    if not tum:
        sys.exit("Hic islem yok.")
    di = pd.DataFrame(tum)
    di.drop(columns=["cikis_dk", "dolum_dk", "gun"]).to_csv(os.path.join(klasor, "1_islemler.csv"), **yaz)
    ds = pd.DataFrame(satir).sort_values("dolar", ascending=False)

    m = []
    c = "=" * 150
    m.append(c)
    m.append("ICT 34 SEMBOL - %s -> bugun | her sembol kendi mantigiyla | SPREAD YOK, KOMISYON YOK | risk 15 $ "
             "(en kucuk lotta en fazla 30 $) | TP 2R / 3R" % args.bas)
    m.append("SAAT: " + saat_notu)
    m.append(c)
    m.append("")
    m.append("-- SEMBOL BAZLI --")
    m.append("%-12s %6s %5s %5s %5s %7s %8s %10s  %-10s %s" % ("SEMBOL", "ISLEM", "TP", "STOP", "SURE", "BASARI", "NET R",
                                                            "DOLAR", "VERI BAS.", "MANTIK"))
    for _, r in ds.iterrows():
        m.append("%-12s %6d %5d %5d %5d %%%6.1f %+8.1f %+10.2f  %-10s %s" % (r["sembol"], r["islem"], r["TP"], r["STOP"],
                                                                          r["SURE"], r["basari"], r["net_R"], r["dolar"],
                                                                          r["veri_bas"], r["mantik"]))
    n = len(di)
    m.append("%-12s %6d %5d %5d %5d %%%6.1f %+8.1f %+10.2f" % ("TOPLAM", n, (di["sonuc"] == "TP").sum(),
                                                             (di["sonuc"] == "STOP").sum(), (di["sonuc"] == "SURE").sum(),
                                                             100.0 * (di["R"] > 0).mean(), di["R"].sum(), di["dolar"].sum()))
    tp_fazla = ds[ds["TP"] > ds["STOP"]]
    m.append("")
    m.append("TP sayisi STOP'tan fazla olan: %d sembol -> %s" % (len(tp_fazla), ", ".join(tp_fazla["sembol"])))
    m.append("Zararda olan: %d sembol -> %s" % ((ds["dolar"] < 0).sum(), ", ".join(ds[ds["dolar"] < 0]["sembol"])))
    m.append("")
    m.append("-- AYLIK (gunluk limitsiz) --")
    b_ = T.BASLANGIC
    for ay, v in di.groupby(di["cikis_tr"].str[:7])["dolar"].sum().items():
        b_ += v
        x = di[di["cikis_tr"].str[:7] == ay]
        m.append("   %-8s islem %4d | TP %4d | STOP %4d | SURE %4d | %+10.2f $ | ay sonu bakiye %10.2f"
                 % (ay, len(x), (x["sonuc"] == "TP").sum(), (x["sonuc"] == "STOP").sum(), (x["sonuc"] == "SURE").sum(), v, b_))
    m.append("")
    m.append(c)
    m.append("10.000 $ HESAP")
    m.append(c)
    for baslik, lim in (("GUNLUK LIMITSIZ", 0), ("250 $ GUNLUK LIMITLI (o gun kapanan zarar 250 $'a ulasinca o gun yeni islem acilmaz)",
                                                  GUNLUK_LIMIT)):
        sm, _ = hesap(di, lim)
        m.append(baslik + ":")
        if sm is None:
            m.append("   islem yok"); continue
        m.append("   10.000 $ -> %.2f $  (net %+.2f $) | en kotu gun %+.2f $ | en iyi gun %+.2f $ | en buyuk dusus %+.2f $ | "
                 "en dusuk bakiye %.2f $%s" % (sm["bitis"], sm["net"], sm["en_kotu_gun"], sm["en_iyi_gun"], sm["dusus"],
                                               sm["en_dusuk"], (" | limit yuzunden acilmayan %d islem" % sm["atlanan"]) if lim else ""))
        m.append("   FTMO: 1.000 $ hedefe ulasma %s | gunluk 300 $ limiti asilan gun %d | 1.000 $ max zarar %s"
                 % (sm["hedef_tarih"], sm["gunluk_ihlal"], "ASILDI" if sm["max_ihlal"] else "asilmadi"))
    if yok:
        m.append("")
        m.append("Bulunamayan / verisi olmayan sembol: " + ", ".join(yok))
    m.append("")
    m.append("BASARI = kar ile kapanan islem orani (TP + kar ile biten SURE).  SURE = NY 16:00'da acik kapanan islem.")
    m.append("VERI BAS. = MT5'te o sembolun 1 dk verisinin basladigi gun; %s'den sonraysa test oradan baslar." % args.bas)
    ms = "\n".join(m)
    print("\n" + ms)
    with open(os.path.join(klasor, "0_OZET.txt"), "w", encoding="utf-8") as fh:
        fh.write(ms + "\n")
    print("\nDosyalar: %s" % os.path.abspath(klasor))


if __name__ == "__main__":
    main()
