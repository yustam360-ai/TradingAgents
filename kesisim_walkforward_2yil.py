# -*- coding: utf-8 -*-
"""
EMA KESISIM (4 HIZ) x 3 ZAMAN DILIMI x 3 STOP SIKKI - 2 YILLIK GERCEKCI TEST (WALK-FORWARD)
==========================================================================================
Calistir:   py -3.8 C:\\Users\\User\\Desktop\\kesisim_walkforward_2yil.py
Gerekli:    py -3.8 -m pip install MetaTrader5 pandas numpy
Sadece bazi semboller:   py -3.8 kesisim_walkforward_2yil.py --sembol XAUUSD,EURUSD
MT5 acik olmali. SADECE gecmis veri okur, ISLEM ACMAZ.  UZUN SURER (sembol basina birkac saniye - 1 dk).
MT5 > Araclar > Secenekler > Grafikler > "Grafikteki en fazla cubuk" = Sinirsiz (2 yillik 15 dk veri).
Sonuclar MASAUSTUNE:  Masaustu\\kesisim_wf_<tarih>\\0_OZET.txt (kisa) , 1_oyna_semboller.csv , 2_oyna_islemler.csv

MANTIK (LONG; SHORT tersi):  hizli EMA yavas EMA'yi yukari keser VE mum yon EMA'sinin ustunde kapanir
  -> kesisim mumu kapaninca, bir sonraki mumun acilisinda giris.
  HIZ 1 = 9/26/100 (bizim mantik)   HIZ 2 = 7/21/75   HIZ 3 = 5/15/50   HIZ 4 = 3/10/30  (kucuk = daha erken)
ZAMAN DILIMI: 15 DK / 1 SAAT / 4 SAAT
STOP SIKKI (ATR = 14 mumluk ortalama mum boyu)
  A: stop 1 ATR, hedef 2 ATR    B: stop 1 ATR, hedef 3 ATR    C: stop 2 ATR, ters kesisimde cikis
  Her sembolde 4 x 3 x 3 = 36 ayar.  Spread dahil; makas maliyeti 100 $ riskte 6 $'i gecen islem acilmaz.

GERCEKCI TEST (walk-forward): 2 yil once baslar.
  SEC  : gecmis 6 ayda her sembolun 36 ayari icinden en iyisi (en az 20 islem ve karda olmali).
  OYNA : secilen semboller o ayarla SONRAKI 3 AY oynanir (secimde hic gorulmemis donem).
  3 ay kaydir, tekrar sec, tekrar oyna.  SONUC SADECE "OYNA" DONEMLERINDEN.
  10.000 $ ile; islem basina 25 $ ve 100 $ risk icin ayri.  FTMO: gunluk %5, toplam %10 siniri kontrolu.
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

YIL_GUN = 730
SEC_GUN, OYNA_GUN = 182, 91
SERMAYE = 10000.0
RISKLER = (25.0, 100.0)
MAKAS_DOLAR, MAKAS_RISK = 6.0, 100.0
MIN_ISLEM = 20
UFUK = 3000                                   # bir islem en fazla bu kadar mum izlenir
MANTIK = [("9/26/100", 9, 26, 100), ("7/21/75", 7, 21, 75), ("5/15/50", 5, 15, 50), ("3/10/30", 3, 10, 30)]
ZD = [("15DK", "TIMEFRAME_M15"), ("1SAAT", "TIMEFRAME_H1"), ("4SAAT", "TIMEFRAME_H4")]
SIK = {"A": (1.0, 2.0), "B": (1.0, 3.0), "C": (2.0, None)}


def masaustu():
    ev = os.path.expanduser("~")
    for p in (os.path.join(ev, "Desktop"), os.path.join(ev, "OneDrive", "Desktop"), os.path.join(ev, "Masaüstü")):
        if os.path.isdir(p):
            return p
    return os.getcwd()


def cek(sembol, tf, bas, bit):
    out, a = [], bas
    while a < bit:
        b = min(a + timedelta(days=90), bit)
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


def test(D, f, s, tr):
    """Donus: {sik: (giris_t, cikis_t, yon, R)} numpy dizileri."""
    T, o, h, l, c, sp, atr = D["T"], D["o"], D["h"], D["l"], D["c"], D["sp"], D["atr"]
    n = len(c)
    S = pd.Series(c)
    ef, es, et = (S.ewm(span=k, adjust=False).mean().values for k in (f, s, tr))
    d = ef - es
    dp = np.r_[0.0, d[:-1]]
    yuk = (d > 0) & (dp <= 0)
    asa = (d < 0) & (dp >= 0)
    yi, ai = np.nonzero(yuk)[0], np.nonzero(asa)[0]
    out = {k: ([], [], [], []) for k in SIK}
    for i in np.nonzero((yuk & (c > et)) | (asa & (c < et)))[0]:
        j = i + 1
        if i < tr + 10 or j >= n or not atr[i] > 0:
            continue
        y = 1 if yuk[i] else -1
        ters = ai if y > 0 else yi
        q = np.searchsorted(ters, i, "right")
        tk_i = ters[q] if q < len(ters) else -1
        e = o[j] + (sp[j] if y > 0 else 0.0)
        end = min(n, j + UFUK)
        if y > 0:
            lo, hi, op = l[j:end], h[j:end], o[j:end]
        else:
            lo, hi, op = -(h[j:end] + sp[j:end]), -(l[j:end] + sp[j:end]), -(o[j:end] + sp[j:end])
        ey = y * e
        lmin, hmax = np.minimum.accumulate(lo), np.maximum.accumulate(hi)
        m = end - j
        for k, (sk, tk) in SIK.items():
            risk = sk * atr[i]
            if MAKAS_RISK * sp[j] / risk > MAKAS_DOLAR:
                continue
            st = ey - risk
            isl = int(np.searchsorted(-lmin, -st, "left"))
            if tk is not None:
                tp = ey + tk * atr[i]
                itp = int(np.searchsorted(hmax, tp, "left"))
                if isl >= m and itp >= m:
                    continue
                if isl <= itp:
                    ix, px = isl, min(op[isl], st)
                else:
                    ix, px = itp, max(op[itp], tp)
            else:
                if tk_i < 0 or tk_i + 1 - j >= m:
                    continue
                kx = tk_i + 1 - j
                if isl < kx:
                    ix, px = isl, min(op[isl], st)
                else:
                    ix, px = kx, op[kx]
            L = out[k]
            L[0].append(T[j]); L[1].append(T[j + ix]); L[2].append(y); L[3].append((px - ey) / risk)
    return {k: tuple(np.array(x) for x in v) for k, v in out.items()}


def hazirla(df, point):
    T = df["time"].values.astype(np.int64)
    o, h, l, c = (df[k].values.astype(float) for k in ("open", "high", "low", "close"))
    pc = np.r_[c[0], c[:-1]]
    atr = pd.Series(np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))).rolling(14).mean().values
    return dict(T=T, o=o, h=h, l=l, c=c, sp=df["spread"].values.astype(float) * point, atr=atr)


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
    t0 = time.time()
    liste = [x.strip() for x in a.sembol.split(",") if x.strip()] if a.sembol else \
        [x.name for x in (mt5.symbols_get() or []) if getattr(x, "trade_mode", 4) != 0]
    bit = datetime.now() + timedelta(days=1)
    bas = bit - timedelta(days=YIL_GUN + 30)
    simdi = None
    TOP = {}                     # (mantik, zaman, sik) -> [islem, karli, R]   (2 yilin tamami, butun semboller)
    OYN = []                     # oyna donemi islemleri
    print("Taranacak sembol: %d   (2 yil, 36 ayar, walk-forward)" % len(liste))
    for no, sb in enumerate(liste, 1):
        try:
            mt5.symbol_select(sb, True)
            bilgi = mt5.symbol_info(sb)
            if bilgi is None:
                continue
            if simdi is None:
                tk = mt5.symbol_info_tick(sb)
                simdi = int(tk.time) if tk is not None and tk.time else int(time.time())
                ilk = simdi - YIL_GUN * 86400
                PENC = []
                s0 = ilk
                while s0 + (SEC_GUN) * 86400 < simdi:
                    o0 = s0 + SEC_GUN * 86400
                    PENC.append((s0, o0, min(o0 + OYNA_GUN * 86400, simdi)))
                    s0 += OYNA_GUN * 86400
            R_ = {}
            for zad, tfad in ZD:
                df = cek(sb, getattr(mt5, tfad), bas, bit)
                if df is None or len(df) < 400:
                    continue
                D = hazirla(df, bilgi.point)
                for mad, f, s, tr in MANTIK:
                    for k, (tg, tc, y, R) in test(D, f, s, tr).items():
                        if not len(R):
                            continue
                        msk = tg >= ilk
                        R_[(mad, zad, k)] = (tg, tc, y, R)
                        x = TOP.setdefault((mad, zad, k), [0, 0, 0.0])
                        x[0] += int(msk.sum()); x[1] += int((R[msk] > 0).sum()); x[2] += float(R[msk].sum())
            # ---- walk-forward
            secilen = []
            for tur, (s0, o0, o1) in enumerate(PENC, 1):
                en, enR = None, 0.0
                for key, (tg, tc, y, R) in R_.items():
                    m = (tg >= s0) & (tc < o0)
                    if m.sum() >= MIN_ISLEM and R[m].sum() > enR:
                        en, enR = key, R[m].sum()
                if en is None:
                    continue
                tg, tc, y, R = R_[en]
                m = (tg >= o0) & (tg < o1)
                secilen.append("%d:%s" % (tur, "-".join(en)))
                for a_, b_, c_, d_ in zip(tg[m], tc[m], y[m], R[m]):
                    OYN.append((sb, tur, "%s %s %s" % en, int(a_), int(b_), int(c_), float(d_)))
            print("%3d/%d %-12s %s" % (no, len(liste), sb, " ".join(secilen) if secilen else "hic secilmedi"))
        except Exception as ex:
            print("%3d/%d %-12s HATA: %s" % (no, len(liste), sb, ex))
    mt5.shutdown()

    klasor = os.path.join(masaustu(), "kesisim_wf_" + datetime.now().strftime("%Y%m%d_%H%M"))
    os.makedirs(klasor, exist_ok=True)
    gun = lambda t: datetime.utcfromtimestamp(int(t)).strftime("%d.%m.%Y")
    sat = ["EMA KESISIM - 2 YILLIK GERCEKCI TEST (walk-forward)   %s   sure %.0f dk"
           % (datetime.now().strftime("%d.%m.%Y"), (time.time() - t0) / 60.0),
           "Hiz: 9/26/100, 7/21/75, 5/15/50, 3/10/30 | 15DK/1SAAT/4SAAT | A 1:2, B 1:3, C 2ATR+ters kesisim"]
    # 1) butun semboller toplami
    sat += ["", "1) BUTUN SEMBOLLER, 2 YILIN TAMAMI (secim yok) - en iyi 10 ve en kotu 3 ayar",
            "%-9s %-6s %-3s %7s %7s %9s" % ("hiz", "zaman", "sik", "islem", "basari", "R")]
    TT = sorted(TOP.items(), key=lambda x: -x[1][2])
    for (key, (n, w, R)) in TT[:10] + [(("...", "", ""), (0, 0, 0.0))] + TT[-3:]:
        if key[0] == "...":
            sat.append("   ...")
            continue
        sat.append("%-9s %-6s %-3s %7d %6.1f%% %+9.0f" % (key[0], key[1], key[2], n, 100.0 * w / max(1, n), R))
    sat.append("Artida olan ayar: %d / %d" % (sum(1 for _, v in TOP.items() if v[2] > 0), len(TOP)))
    # 2) walk-forward sonucu
    O = pd.DataFrame(OYN, columns=["sembol", "tur", "ayar", "giris_t", "cikis_t", "yon", "R"])
    sat += ["", "2) GERCEKCI SONUC: sadece OYNA donemleri (secimde gorulmemis)"]
    if not len(O):
        sat.append("Hic islem yok.")
    else:
        O = O.sort_values("cikis_t")
        sat.append("%-4s %-23s %8s %7s %7s %9s %9s %9s" % ("tur", "oyna donemi", "sembol", "islem", "basari", "R",
                                                          "25$ risk", "100$ risk"))
        for tur, (s0, o0, o1) in enumerate(PENC, 1):
            g = O[O["tur"] == tur]
            if not len(g):
                continue
            R = g["R"].sum()
            sat.append("%-4d %-23s %8d %7d %6.1f%% %+9.1f %+9.0f %+9.0f"
                       % (tur, gun(o0) + "-" + gun(o1), g["sembol"].nunique(), len(g), 100.0 * (g["R"] > 0).mean(),
                          R, R * 25, R * 100))
        R = O["R"].sum()
        gunler = (PENC[-1][2] - PENC[0][1]) / 86400.0 * 5.0 / 7.0
        sat += ["TOPLAM: %d islem  basari %%%.1f  %+.1fR   ~%.1f islem/gun" % (len(O), 100.0 * (O["R"] > 0).mean(),
                                                                          R, len(O) / max(1, gunler))]
        Rg = O.groupby(O["cikis_t"] // 86400)["R"].sum()
        egri = np.cumsum(O["R"].values)
        dd = (np.maximum.accumulate(np.r_[0.0, egri])[1:] - egri).max()
        dip = min(0.0, egri.min())
        for rk in RISKLER:
            sat.append("  %3.0f $ risk: 10.000 $ -> %.0f $  | gunluk ort %+.0f $ | en buyuk dusus %.0f $ | "
                       "en kotu gun %+.0f $ | FTMO gunluk %%5: %s, toplam %%10: %s"
                       % (rk, SERMAYE + R * rk, R * rk / max(1, gunler), dd * rk, Rg.min() * rk,
                          "ASILDI" if Rg.min() * rk < -500 else "tamam", "ASILDI" if dip * rk < -1000 else "tamam"))
        # 3) sembol bazinda oyna sonuclari
        S = O.groupby("sembol").agg(tur=("tur", "nunique"), islem=("R", "size"), basari=("R", lambda r: 100.0 * (r > 0).mean()),
                                    R=("R", "sum")).sort_values("R", ascending=False)
        S.to_csv(os.path.join(klasor, "1_oyna_semboller.csv"), sep=";", decimal=",")
        O.assign(giris=O["giris_t"].map(gun), cikis=O["cikis_t"].map(gun)).drop(columns=["giris_t", "cikis_t"]) \
            .to_csv(os.path.join(klasor, "2_oyna_islemler.csv"), index=False, sep=";", decimal=",")
        U = S[(S["islem"] >= 10) & (S["basari"] > 50.0)]
        sat += ["", "3) OYNA DONEMINDE BASARI %%50 USTU (en az 10 islem): %d sembol" % len(U)]
        for sb, r in U.iterrows():
            sat.append("   %-12s %d turda secildi  %4d islem  basari %5.1f%%  %+7.1fR" % (sb, r["tur"], r["islem"],
                                                                                   r["basari"], r["R"]))
        sat += ["", "4) OYNA DONEMINDE EN COK KAZANDIRAN 20 SEMBOL (en az 20 islem)"]
        for sb, r in S[S["islem"] >= 20].head(20).iterrows():
            sat.append("   %-12s %d turda secildi  %4d islem  basari %5.1f%%  %+7.1fR" % (sb, r["tur"], r["islem"],
                                                                                   r["basari"], r["R"]))
        sat.append("Oyna doneminde karda olan sembol: %d / %d" % ((S["R"] > 0).sum(), len(S)))
    yaz = "\n".join(sat)
    with open(os.path.join(klasor, "0_OZET.txt"), "w", encoding="utf-8") as f:
        f.write(yaz)
    print("\n" + yaz)
    print("\nSonuclar: " + klasor)


if __name__ == "__main__":
    main()
