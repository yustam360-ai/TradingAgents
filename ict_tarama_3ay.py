# -*- coding: utf-8 -*-
"""
ICT TARAMASI - BUTUN semboller, son 3 ay, 6480 farkli ICT kural birlesimi
=========================================================================
Python 3.8:   py -3.8 ict_tarama_3ay.py
Gerekli:      py -3.8 -m pip install MetaTrader5 pandas numpy

MT5'e baglanir, SADECE gecmis veri okur, ISLEM ACMAZ.  SPREAD / MAKAS / KOMISYON YOK.
Saatler NEW YORK saati (FTMO sunucusu = NY + 7).  Islem basi 15 $ risk (1R = 15 $).

ANA MANTIK (satis anlatiliyor, alis birebir tersi):
  1) YON (bias)       : YOK (iki yon) / SUPURME (dun eski 3 gunluk dip supurulup ustunde kapandiysa sadece alis,
                        tepe supurulup altinda kapandiysa sadece satis) / KAPANIS (dun onceki gunun tepesinin
                        ustunde kapandiysa alis, dibinin altinda kapandiysa satis).
  2) LIKIDITE         : onceki gun, onceki 3 gun, Asya (onceki gun 19-24), Londra (02-05), gece (00:00-seans basi)
                        tepeleri.  Seanstan once alinmamis olmali.  Seans icinde fiyat birini gecerse = SUPURME.
  3) YAPI KIRILIMI    : supurmeden sonra 20 mum icinde, son kisa vadeli swing dip kirilir:
                        FITIL (fitil yeter) / GOVDE (mum altinda kapanmali) / SERT (altinda kapanmali ve mum
                        govdesi >= 1 ATR).  Zaman dilimi: 1 / 3 / 5 / 15 dakika.
  4) FVG              : supurme tepesinden kirilimdan 1 mum sonrasina kadarki bacakta 3 mumluk bosluk.
                        Yoksa islem yok.  Birden coksa fiyata en yakini.
  5) PREMIUM/DISCOUNT : YOK / VAR (satista giris fiyati bacagin %50'sinin ustunde olmali).
  6) ZAMAN            : LON (02:00-05:00) / NYAM (08:30-11:00) / NYPM (13:30-16:00) /
                        SB = Silver Bullet (03-04, 10-11, 14-15) / HEPSI (LON + NYAM + NYPM).
  7) GIRIS (limit)    : FVG_KENAR (boslugun alt kenari) / FVG_ORTA (boslugun ortasi) /
                        OTE (bacagin %70.5 geri cekilmesi).
  8) STOP             : SUPURME (supurme tepesi + 0.1 ATR) / FVG (boslugun 1. mumunun tepesi).
  9) HEDEF            : LIK (girisin altindaki en yakin likidite: onceki gun/3 gun/Asya/Londra/gece dibi, en az 1R,
                        en fazla 5R; daha uzaksa hedef 5R)
                        / 2R / 3R.
  Seans basina sembol basina tek emir.  Dolmayan emir silinir: LON 05:30, NYAM 11:30, NYPM 16:00
  ya da fiyat emir dolmadan hedefe ulasirsa.  Acik islem NY 16:00'da kapanir.
  1 dk takip: ayni dakikada stop ve hedef = STOP; dolum dakikasinda hedef sayilmaz, stop sayilir.

CIKTI (ict_tarama_<tarih>/):
  0_OZET.txt          en cok kazandiran 20 + en basarili 20 birlesim, en iyinin sembol/seans/gun/ay sonucu
  1_tum_birlesimler.csv  6480 birlesimin hepsi
  2_en_iyi_islemler.csv  en cok kazandiran birlesimin butun islemleri
  3_sembol_en_iyi.csv    her sembolun kendi en iyi birlesimi (TP / STOP / basari)
  En altta: basarisi %50'nin ustunde olan pariteler.
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
    import MetaTrader5 as mt5
except ImportError:
    mt5 = None

RISK = 15.0
BASLANGIC = 10000.0
SEMBOLLER = ["EURCZK", "USDILS", "USDSGD", "MANUSD", "XAUUSD",
             "US30.cash", "USDCAD", "AUDUSD", "XPTUSD", "WHEAT.c", "HK50.cash", "SOYBEAN.c", "AAVUSD", "BTCUSD",
             "CORN.c", "ADAUSD", "EURNZD", "ICPUSD", "NVDA", "HEATOIL.c", "AUDCHF", "ALVG", "GOOG", "XCUUSD", "TTE",
             "XTZUSD", "FRA40.cash", "EU50.cash", "GBPUSD", "RTX", "EURHUF", "USDCHF", "META", "EURAUD", "GE", "MSFT",
             "EURNOK", "ARM", "GRTUSD", "SAN", "AZN", "AMD", "QCOM", "T", "AAPL", "DIS", "COFFEE.c", "BABA", "INTC",
             "LMT", "FDX", "AVGO", "BAC", "IBM", "ZM", "UKOIL.cash", "JNJ", "CSCO", "BA", "RACE", "CVX"]
SEANS = {"LON": (120, 300, 330), "NYAM": (510, 660, 690), "NYPM": (810, 960, 960)}   # bas, bit, emir iptal (NY dk)
SEANS_AD = ["LON", "NYAM", "NYPM"]
SB_PENCERE = [(180, 240), (600, 660), (840, 900)]
KAPANIS = 960
TFLER = [1, 3, 5, 15]
KIRILIMLAR = ["FITIL", "GOVDE", "SERT"]
GIRISLER = ["FVG_KENAR", "FVG_ORTA", "OTE"]
STOPLAR = ["SUPURME", "FVG"]
HEDEFLER = ["LIK", "2R", "3R"]
YONLER = ["YOK", "SUPURME", "KAPANIS"]
SEANS_SEC = ["LON", "NYAM", "NYPM", "SB", "HEPSI"]
MAX_KIRILIM_MUM = 20
MAX_KURULUM = 5


def cek(sembol, tf, bas, bit, parca_gun):
    parcalar, a = [], bas
    while a < bit:
        b = min(a + timedelta(days=parca_gun), bit)
        r = None
        for _ in range(3):
            r = mt5.copy_rates_range(sembol, tf, a, b)
            if r is not None:
                break
            time.sleep(0.5)
        if r is not None and len(r):
            parcalar.append(pd.DataFrame(r)[["time", "open", "high", "low", "close"]])
        a = b
    if not parcalar:
        return None
    return pd.concat(parcalar).drop_duplicates("time").sort_values("time").reset_index(drop=True)


def mumlar(t, o, h, l, c, K):
    """1 dk -> K dk mum (NY saatine hizali). donus: bas_dk, o, h, l, c, atr14"""
    if K == 1:
        bt, bo, bh, bl, bc = t.copy(), o.copy(), h.copy(), l.copy(), c.copy()
    else:
        key = t // K
        df = pd.DataFrame({"k": key, "o": o, "h": h, "l": l, "c": c}).groupby("k").agg(
            o=("o", "first"), h=("h", "max"), l=("l", "min"), c=("c", "last"))
        bt = df.index.to_numpy(np.int64) * K
        bo, bh, bl, bc = [df[x].to_numpy(float) for x in ("o", "h", "l", "c")]
    tr = np.r_[bh[0] - bl[0], np.maximum(bh[1:] - bl[1:], np.maximum(np.abs(bh[1:] - bc[:-1]), np.abs(bl[1:] - bc[:-1])))]
    atr = pd.Series(tr).rolling(14, min_periods=1).mean().to_numpy()
    return bt, bo, bh, bl, bc, atr


def tespit(B, K, ws, we, seviyeler, karsi, maxH, kirilim):
    """SATIS gorunumunde kurulumlar. B: (bt,bo,bh,bl,bc,atr). seviyeler: [(fiyat, olusum_bitis)] tepeler.
    karsi: [(fiyat, bilinme_ani)] hedef icin dipler.  maxH(t0, t1): 1 dk en yuksek."""
    bt, bo, bh, bl, bc, atr = B
    n = len(bt)
    i0, i1 = int(np.searchsorted(bt, ws)), int(np.searchsorted(bt, we))
    acik = []
    for L, fe in seviyeler:
        if L != L:
            continue
        m = maxH(fe, ws)
        if m is None or m <= L:
            acik.append(L)
    if not acik:
        return []
    swl = np.zeros(n, dtype=bool)
    if n > 2:
        swl[1:-1] = (bl[1:-1] < bl[:-2]) & (bl[1:-1] < bl[2:])
    out = []
    i = i0
    while i < i1 and len(out) < MAX_KURULUM:
        if bt[i] + K > we:
            break
        vur = [L for L in acik if bh[i] > L]
        if not vur:
            i += 1
            continue
        for L in vur:
            acik.remove(L)
        f = i - 1                                          # dogrulanmis son swing dip (f+1 <= i)
        while f >= 1 and not swl[f]:
            f -= 1
        if f < 1 or not swl[f]:
            i += 1
            continue
        ref = bl[f]
        sh, shi, j_kir = bh[i], i, -1
        for j in range(i + 1, min(i + 1 + MAX_KIRILIM_MUM, n)):
            if bt[j] + K > we:
                break
            if bh[j] > sh:
                sh, shi = bh[j], j
            if kirilim == "FITIL":
                ok = bl[j] < ref
            elif kirilim == "GOVDE":
                ok = bc[j] < ref
            else:
                ok = bc[j] < ref and (bo[j] - bc[j]) >= atr[j - 1]
            if ok:
                j_kir = j
                break
        if j_kir < 0:
            i += 1
            continue
        dec = j_kir + 1
        if dec >= n:
            break
        Td = int(bt[dec] + K)                              # karar ani (dec mumunun kapanisi)
        en_iyi = None
        for b in range(shi + 1, dec):
            a, cc = b - 1, b + 1
            if a < shi or cc > dec:
                continue
            if bl[a] > bh[cc]:
                ust, alt = bl[a], bh[cc]
                if bc[dec] >= alt:
                    continue
                if cc + 1 <= dec and bh[cc + 1:dec + 1].max() >= alt:
                    continue
                if en_iyi is None or alt < en_iyi[1]:
                    en_iyi = (ust, alt, a)
        if en_iyi is None:
            i = j_kir + 1
            continue
        ust, alt, a = en_iyi
        hi, lo = sh, bl[shi:dec + 1].min()
        girisler = [alt, (ust + alt) / 2.0, lo + 0.705 * (hi - lo)]
        stoplar = [hi + 0.1 * atr[dec], bh[a]]
        pd_ok = [g >= lo + 0.5 * (hi - lo) for g in girisler]
        hedef_sev = [p for p, bil in karsi if p == p and bil <= Td]
        out.append(dict(Td=Td, giris=girisler, stop=stoplar, pd=pd_ok, fiyat=bc[dec], karsi=hedef_sev))
        i = dec + 1
    return out


def etiketle(kur, Tm, Hv, Lv, Cv, gun_bas, iptal):
    """kurulum x giris(3) x stop(2) x hedef(3) -> R (nan = islem yok), sonuc kodu"""
    R = np.full(18, np.nan)
    kod = np.full(18, 9, dtype=np.int8)
    a0 = int(np.searchsorted(Tm, kur["Td"], side="left"))
    c1 = int(np.searchsorted(Tm, iptal, side="left"))
    z1 = int(np.searchsorted(Tm, gun_bas + KAPANIS, side="left"))
    if a0 >= c1 or a0 >= z1:
        return R, kod
    for gi, E in enumerate(kur["giris"]):
        if not (E > kur["fiyat"]):
            continue
        for si, S in enumerate(kur["stop"]):
            r = S - E
            if not (r > 0):
                continue
            for hi_, hd in enumerate(HEDEFLER):
                k = gi * 6 + si * 3 + hi_
                if hd == "2R":
                    TP = E - 2 * r
                elif hd == "3R":
                    TP = E - 3 * r
                else:
                    aday = [p for p in kur["karsi"] if E - p >= r]
                    if not aday:
                        continue
                    TP = max(aday)
                    if E - TP > 5 * r:                     # likidite 5R'den uzaksa hedef 5R
                        TP = E - 5 * r
                hh, ll = Hv[a0:c1], Lv[a0:c1]
                fz = np.flatnonzero(hh >= E)
                if not fz.size:
                    kod[k] = 8
                    continue
                f = a0 + int(fz[0])
                tz = np.flatnonzero(ll <= TP)
                if tz.size and a0 + int(tz[0]) <= f:
                    kod[k] = 8
                    continue
                H2, L2 = Hv[f:z1], Lv[f:z1]
                sz = np.flatnonzero(H2 >= S)
                tp2 = L2 <= TP
                if tp2.size:
                    tp2 = tp2.copy()
                    tp2[0] = False
                hz = np.flatnonzero(tp2)
                s0 = int(sz[0]) if sz.size else None
                h0 = int(hz[0]) if hz.size else None
                if s0 is not None and (h0 is None or s0 <= h0):
                    R[k], kod[k] = -1.0, -1
                elif h0 is not None:
                    R[k], kod[k] = (E - TP) / r, 1
                else:
                    R[k], kod[k] = (E - Cv[z1 - 1]) / r, 0
    return R, kod


def sembol_isle(s, m1, ny_fark, bas_gun, kayit, kod_kayit):
    T = m1["time"].to_numpy(np.int64) // 60 - ny_fark * 60
    O, H, L, C = [m1[k].to_numpy(float) for k in ("open", "high", "low", "close")]
    gunler = np.unique(T // 1440)
    gh, gl, gc = {}, {}, {}
    for g in gunler:
        a, b = np.searchsorted(T, g * 1440), np.searchsorted(T, g * 1440 + 1440)
        if b > a:
            gh[g], gl[g], gc[g] = H[a:b].max(), L[a:b].min(), C[b - 1]
    gl_list = sorted(gh)

    def aralik(arr, fn, t0, t1):
        a, b = np.searchsorted(T, t0), np.searchsorted(T, t1)
        return fn(arr[a:b]) if b > a else None

    goruler = {
        -1: (H, L, C),            # satis gorunumu
        1: (-L, -H, -C),          # alis gorunumu (fiyatlar ters)
    }
    mum_cache = {}
    for K in TFLER:
        bt, bo, bh, bl, bc, atr = mumlar(T, O, H, L, C, K)
        mum_cache[K] = {-1: (bt, bo, bh, bl, bc, atr), 1: (bt, -bo, -bl, -bh, -bc, atr)}
    n0 = len(kayit)
    for p, g in enumerate(gl_list):
        if g < bas_gun or p < 4:
            continue
        g1, g2, g3, g4 = gl_list[p - 1], gl_list[p - 2], gl_list[p - 3], gl_list[p - 4]
        D = g * 1440
        # yon (bias)
        eski_dip = min(gl[g2], gl[g3], gl[g4]); eski_tepe = max(gh[g2], gh[g3], gh[g4])
        sup_al = gl[g1] < eski_dip and gc[g1] > eski_dip
        sup_sat = gh[g1] > eski_tepe and gc[g1] < eski_tepe
        bias_sup = 1 if (sup_al and not sup_sat) else (-1 if (sup_sat and not sup_al) else 0)
        bias_kap = 1 if gc[g1] > gh[g2] else (-1 if gc[g1] < gl[g2] else 0)
        pdh, pdl = gh[g1], gl[g1]
        p3h, p3l = max(gh[g1], gh[g2], gh[g3]), min(gl[g1], gl[g2], gl[g3])
        asy_h, asy_l = aralik(H, np.max, D - 300, D), aralik(L, np.min, D - 300, D)
        lon_h, lon_l = aralik(H, np.max, D + 120, D + 300), aralik(L, np.min, D + 120, D + 300)
        for sn, sa in enumerate(SEANS_AD):
            ws, we, ip = SEANS[sa]
            ws, we, ip = D + ws, D + we, D + ip
            gece_h, gece_l = aralik(H, np.max, D, ws), aralik(L, np.min, D, ws)
            for yon in (-1, 1):
                Hv, Lv, Cv = goruler[yon]
                if yon < 0:
                    tep = [(pdh, D), (p3h, D), (asy_h, D), (gece_h, ws)]
                    dip = [(pdl, D), (p3l, D), (asy_l, D), (gece_l, ws)]
                    if sa != "LON":
                        tep.append((lon_h, D + 300)); dip.append((lon_l, D + 300))
                else:
                    tep = [(-pdl, D), (-p3l, D), (-asy_l if asy_l is not None else None, D), (-gece_l if gece_l is not None else None, ws)]
                    dip = [(-pdh, D), (-p3h, D), (-asy_h if asy_h is not None else None, D), (-gece_h if gece_h is not None else None, ws)]
                    if sa != "LON":
                        tep.append((-lon_l if lon_l is not None else None, D + 300))
                        dip.append((-lon_h if lon_h is not None else None, D + 300))
                tep = [(np.nan if v is None else v, fe) for v, fe in tep]
                dip = [(np.nan if v is None else v, fe) for v, fe in dip]

                def maxH(t0, t1, Hv=Hv):
                    a, b = np.searchsorted(T, t0), np.searchsorted(T, t1)
                    return Hv[a:b].max() if b > a else -np.inf

                for K in TFLER:
                    B = mum_cache[K][yon]
                    for kr in KIRILIMLAR:
                        for kur in tespit(B, K, ws, we, tep, dip, maxH, kr):
                            R, kod = etiketle(kur, T, Hv, Lv, Cv, D, ip)
                            sb = any(a <= (kur["Td"] - D) < b for a, b in SB_PENCERE)
                            kayit.append(dict(sembol=s, gun=int(g), seans=sn, sb=sb, tf=K, kirilim=kr, yon=yon,
                                              bias_sup=bias_sup, bias_kap=bias_kap, Td=kur["Td"],
                                              pd0=kur["pd"][0], pd1=kur["pd"][1], pd2=kur["pd"][2]))
                            kod_kayit.append((R, kod))
    return len(kayit) - n0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ay", type=float, default=3.0)
    ap.add_argument("--sunucu-ny", type=int, default=7)
    ap.add_argument("--min-islem", type=int, default=60, help="siralamaya girmek icin en az islem")
    ap.add_argument("--min-islem-sembol", type=int, default=15, help="sembolun en iyi birlesimi icin en az islem")
    ap.add_argument("--sembol", default="", help="sadece bu semboller (virgulle); bos = butun semboller")
    ap.add_argument("--cikti", default="")
    args = ap.parse_args()
    if mt5 is None:
        sys.exit("MetaTrader5 modulu yok:  py -3.8 -m pip install MetaTrader5")
    if not mt5.initialize():
        sys.exit("MT5 baglantisi kurulamadi: %s" % (mt5.last_error(),))
    hs = mt5.account_info()
    print("MT5 bagli: %s  (sadece gecmis veri, islem acilmiyor)" % (hs.server if hs else "?"))
    simdi = datetime.now(timezone.utc).replace(tzinfo=None)
    tbas = simdi - timedelta(days=30.4 * args.ay)
    bas_gun = (int((tbas - datetime(1970, 1, 1)).total_seconds() // 60) - 5 * 60) // 1440
    semboller = ([x.strip() for x in args.sembol.split(",") if x.strip()] if args.sembol
                 else [x.name for x in (mt5.symbols_get() or [])])
    klasor = args.cikti or ("ict_tarama_%s" % datetime.now().strftime("%Y%m%d_%H%M"))
    if not os.path.isdir(klasor):
        os.makedirs(klasor)
    yaz = dict(sep=";", decimal=",", index=False, encoding="utf-8-sig")
    print("Sembol: %d | %s -> bugun | %d birlesim" % (len(semboller), tbas.strftime("%Y-%m-%d"),
                                                     len(SEANS_SEC) * len(YONLER) * len(TFLER) * len(KIRILIMLAR) * 2 * 18))
    kayit, kod_kayit, yok, t0 = [], [], [], time.time()
    for n, s in enumerate(semboller, 1):
        if not mt5.symbol_select(s, True):
            yok.append(s); print("[%d/%d] %s : sembol yok" % (n, len(semboller), s)); continue
        m1 = cek(s, mt5.TIMEFRAME_M1, tbas - timedelta(days=10), simdi + timedelta(days=1), 15)
        if m1 is None or len(m1) < 5000:
            yok.append(s); print("[%d/%d] %s : veri yok" % (n, len(semboller), s)); continue
        k = sembol_isle(s, m1, args.sunucu_ny, bas_gun, kayit, kod_kayit)
        print("[%d/%d] %s : %d kurulum  (%.0f sn)" % (n, len(semboller), s, k, time.time() - t0))
    mt5.shutdown()
    if not kayit:
        sys.exit("Hic kurulum yok.")

    df = pd.DataFrame(kayit)
    RR = np.vstack([r for r, _ in kod_kayit])
    KK = np.vstack([k for _, k in kod_kayit])
    sira = np.lexsort((df["Td"].to_numpy(), df["seans"].to_numpy(), df["gun"].to_numpy(), df["sembol"].to_numpy()))
    df = df.iloc[sira].reset_index(drop=True)
    RR, KK = RR[sira], KK[sira]
    grup_id = pd.factorize(df["sembol"] + "_" + df["gun"].astype(str) + "_" + df["seans"].astype(str))[0]
    gun_arr = df["gun"].to_numpy()
    yari = gun_arr >= (gun_arr.min() + gun_arr.max()) / 2.0
    tf_a, kr_a, sn_a, sb_a = df["tf"].to_numpy(), df["kirilim"].to_numpy(), df["seans"].to_numpy(), df["sb"].to_numpy()
    yon_a, bs_a, bk_a = df["yon"].to_numpy(), df["bias_sup"].to_numpy(), df["bias_kap"].to_numpy()
    pd_a = [df["pd0"].to_numpy(), df["pd1"].to_numpy(), df["pd2"].to_numpy()]

    sonuc, secimler = [], {}
    sem_kod, sem_ad = pd.factorize(df["sembol"])
    NS = len(sem_ad)
    b_R = np.full(NS, -np.inf); b_n = np.zeros(NS); b_w = np.zeros(NS); b_tp = np.zeros(NS); b_st = np.zeros(NS)
    b_su = np.zeros(NS); b_ad = np.array([""] * NS, dtype=object)
    for K in TFLER:
        for kr in KIRILIMLAR:
            m_tk = (tf_a == K) & (kr_a == kr)
            for ss in SEANS_SEC:
                if ss == "HEPSI":
                    m_s = m_tk
                elif ss == "SB":
                    m_s = m_tk & sb_a
                else:
                    m_s = m_tk & (sn_a == SEANS_AD.index(ss))
                for yn in YONLER:
                    if yn == "YOK":
                        m_y = m_s
                    elif yn == "SUPURME":
                        m_y = m_s & (yon_a == bs_a)
                    else:
                        m_y = m_s & (yon_a == bk_a)
                    for pdv in ("YOK", "VAR"):
                        for gi, gad in enumerate(GIRISLER):
                            m_p = m_y & pd_a[gi] if pdv == "VAR" else m_y
                            for si, sad in enumerate(STOPLAR):
                                for hi_, had in enumerate(HEDEFLER):
                                    k = gi * 6 + si * 3 + hi_
                                    m = m_p & (KK[:, k] != 9)          # gecerli emir
                                    idx = np.flatnonzero(m)
                                    if idx.size:
                                        g = grup_id[idx]
                                        idx = idx[np.r_[True, g[1:] != g[:-1]]]
                                    r = RR[idx, k]
                                    ok = ~np.isnan(r)
                                    r2, idx2 = r[ok], idx[ok]
                                    kd = KK[idx2, k]
                                    ad = "SEANS=%s | YON=%s | TF=%ddk | KIRILIM=%s | PD=%s | GIRIS=%s | STOP=%s | HEDEF=%s" % (
                                        ss, yn, K, kr, pdv, gad, sad, had)
                                    nn = len(r2)
                                    sonuc.append(dict(birlesim=ad, seans=ss, yon=yn, tf=K, kirilim=kr, pd=pdv, giris=gad,
                                                      stop=sad, hedef=had, islem=nn, TP=int((kd == 1).sum()),
                                                      STOP=int((kd == -1).sum()), SURE=int((kd == 0).sum()),
                                                      basari=round(100.0 * (r2 > 0).mean(), 1) if nn else 0.0,
                                                      net_R=round(float(r2.sum()), 1), dolar=round(float(r2.sum()) * RISK, 2),
                                                      ilk_yari_R=round(float(r2[~yari[idx2]].sum()), 1),
                                                      son_yari_R=round(float(r2[yari[idx2]].sum()), 1)))
                                    secimler[ad] = (idx2, k)
                                    if nn:
                                        sc = sem_kod[idx2]
                                        s_n = np.bincount(sc, minlength=NS)
                                        s_R = np.bincount(sc, weights=r2, minlength=NS)
                                        yeni = (s_n >= args.min_islem_sembol) & (s_R > b_R)
                                        if yeni.any():
                                            b_R[yeni] = s_R[yeni]; b_n[yeni] = s_n[yeni]
                                            b_w[yeni] = np.bincount(sc, weights=(r2 > 0), minlength=NS)[yeni]
                                            b_tp[yeni] = np.bincount(sc, weights=(kd == 1), minlength=NS)[yeni]
                                            b_st[yeni] = np.bincount(sc, weights=(kd == -1), minlength=NS)[yeni]
                                            b_su[yeni] = np.bincount(sc, weights=(kd == 0), minlength=NS)[yeni]
                                            b_ad[yeni] = ad
    ds = pd.DataFrame(sonuc)
    ds.sort_values("dolar", ascending=False).to_csv(os.path.join(klasor, "1_tum_birlesimler.csv"), **yaz)
    uy = ds[ds["islem"] >= args.min_islem]
    m = []
    m.append("=" * 140)
    m.append("ICT TARAMASI - son %.0f ay, %d sembol, %d birlesim, spread yok, islem basi %.0f $ risk"
             % (args.ay, len(semboller) - len(yok), len(ds), RISK))
    m.append("Siralamaya giren: en az %d islem yapan birlesimler (%d adet)." % (args.min_islem, len(uy)))
    m.append("=" * 140)
    bas = "%5s %4s %4s %4s %7s %8s %10s %7s %7s  %s" % ("ISLEM", "TP", "STOP", "SURE", "BASARI", "NET R", "DOLAR",
                                                        "1.YARI", "2.YARI", "BIRLESIM")

    def satir(r):
        return "%5d %4d %4d %4d %%%6.1f %+8.1f %+10.2f %+7.1f %+7.1f  %s" % (r["islem"], r["TP"], r["STOP"], r["SURE"],
                                                                            r["basari"], r["net_R"], r["dolar"],
                                                                            r["ilk_yari_R"], r["son_yari_R"], r["birlesim"])
    m.append("")
    m.append("-- EN COK KAZANDIRAN 20 BIRLESIM --")
    m.append(bas)
    for _, r in uy.sort_values("dolar", ascending=False).head(20).iterrows():
        m.append(satir(r))
    m.append("")
    m.append("-- EN BASARILI 20 BIRLESIM (kar ile kapanan islem orani) --")
    m.append(bas)
    for _, r in uy.sort_values(["basari", "dolar"], ascending=False).head(20).iterrows():
        m.append(satir(r))
    if len(uy):
        en = uy.sort_values("dolar", ascending=False).iloc[0]
        idx2, k = secimler[en["birlesim"]]
        sec = df.iloc[idx2].copy()
        sec["R"] = RR[idx2, k]
        sec["sonuc"] = pd.Series(KK[idx2, k]).map({1: "TP", -1: "STOP", 0: "SURE"}).values
        sec["dolar"] = (sec["R"] * RISK).round(2)
        sec["tarih"] = sec["gun"].apply(lambda g: (datetime(1970, 1, 1) + timedelta(days=int(g))).strftime("%Y-%m-%d"))
        sec["seans_ad"] = sec["seans"].map(dict(enumerate(SEANS_AD)))
        sec["yon_ad"] = sec["yon"].map({1: "AL", -1: "SAT"})
        sec[["tarih", "sembol", "seans_ad", "yon_ad", "sonuc", "R", "dolar"]].to_csv(
            os.path.join(klasor, "2_en_iyi_islemler.csv"), **yaz)
        m.append("")
        m.append("=" * 140)
        m.append("EN COK KAZANDIRAN BIRLESIM: " + en["birlesim"])
        m.append("=" * 140)

        def ozet(x):
            n = len(x)
            return (n, int((x["sonuc"] == "TP").sum()), int((x["sonuc"] == "STOP").sum()), int((x["sonuc"] == "SURE").sum()),
                    100.0 * (x["R"] > 0).mean() if n else 0.0, x["dolar"].sum())
        m.append("-- SEMBOL BAZLI --")
        m.append("%-11s %5s %4s %4s %4s %7s %10s" % ("SEMBOL", "ISLEM", "TP", "STOP", "SURE", "BASARI", "DOLAR"))
        so = sorted(((ozet(x), s_) for s_, x in sec.groupby("sembol")), key=lambda v: -v[0][5])
        for o_, s_ in so:
            m.append("%-11s %5d %4d %4d %4d %%%6.1f %+10.2f" % ((s_,) + o_))
        m.append("")
        m.append("-- SEANS BAZLI --")
        m.append("%-6s %-4s %5s %4s %4s %4s %7s %10s" % ("SEANS", "YON", "ISLEM", "TP", "STOP", "SURE", "BASARI", "DOLAR"))
        for sa in SEANS_AD:
            for yn in ("AL", "SAT"):
                x = sec[(sec["seans_ad"] == sa) & (sec["yon_ad"] == yn)]
                if len(x):
                    m.append("%-6s %-4s %5d %4d %4d %4d %%%6.1f %+10.2f" % ((sa, yn) + ozet(x)))
        gunluk = sec.groupby("tarih")["dolar"].sum().sort_index()
        bak = BASLANGIC + gunluk.cumsum()
        dd = (bak - np.maximum.accumulate(np.r_[BASLANGIC, bak.to_numpy()])[1:]).min()
        aylik = sec.assign(ay=sec["tarih"].str[:7]).groupby("ay")["dolar"].sum()
        m.append("")
        m.append("-- AYLIK --")
        b_ = BASLANGIC
        for ay, v in aylik.items():
            b_ += v
            m.append("%-8s %+10.2f   ay sonu bakiye %10.2f" % (ay, v, b_))
        m.append("")
        m.append("Baslangic %.2f $ -> bitis %.2f $  (net %+.2f $) | islem gunu %d | en kotu gun %+.2f $ | en buyuk dusus %+.2f $"
                 % (BASLANGIC, BASLANGIC + sec["dolar"].sum(), sec["dolar"].sum(), len(gunluk), gunluk.min(), dd))
        m.append("(gunluk limit uygulanmadi; kapanan islemlere gore)")
    sb_df = pd.DataFrame(dict(sembol=list(sem_ad), islem=b_n.astype(int), TP=b_tp.astype(int), STOP=b_st.astype(int),
                              SURE=b_su.astype(int), basari=np.round(np.where(b_n > 0, 100.0 * b_w / np.maximum(b_n, 1), 0), 1),
                              net_R=np.round(np.where(np.isfinite(b_R), b_R, 0), 1), birlesim=b_ad))
    sb_df = sb_df[sb_df["islem"] > 0].copy()
    sb_df["dolar"] = (sb_df["net_R"] * RISK).round(2)
    sb_df = sb_df.sort_values("dolar", ascending=False)
    sb_df.to_csv(os.path.join(klasor, "3_sembol_en_iyi.csv"), **yaz)
    m.append("")
    m.append("=" * 140)
    m.append("-- SEMBOL BAZLI: her sembolun KENDI en iyi birlesimi (en az %d islem) --" % args.min_islem_sembol)
    m.append("%-11s %5s %4s %4s %4s %7s %10s  %s" % ("SEMBOL", "ISLEM", "TP", "STOP", "SURE", "BASARI", "DOLAR", "BIRLESIM"))
    for _, r in sb_df.iterrows():
        m.append("%-11s %5d %4d %4d %4d %%%6.1f %+10.2f  %s" % (r["sembol"], r["islem"], r["TP"], r["STOP"], r["SURE"],
                                                              r["basari"], r["dolar"], r["birlesim"]))
    if yok:
        m.append("")
        m.append("Bulunamayan / verisi olmayan sembol: " + ", ".join(yok))
    m.append("")
    m.append("1.YARI / 2.YARI = 3 ayin ilk ve ikinci yarisindaki net R. Iyi bir birlesim iki yarida da artida olmali.")
    m.append("Not: %d birlesim ayni 3 ayda denendi; en iyisinin bir kismi sans olabilir." % len(ds))
    ust = sb_df[sb_df["basari"] > 50.0].sort_values("basari", ascending=False)
    m.append("")
    m.append("=" * 140)
    m.append("-- BASARISI %%50'NIN USTUNDE OLAN PARITELER (kendi en iyi birlesimiyle): %d adet --" % len(ust))
    m.append("%-11s %5s %4s %4s %4s %7s %10s  %s" % ("SEMBOL", "ISLEM", "TP", "STOP", "SURE", "BASARI", "DOLAR", "BIRLESIM"))
    for _, r in ust.iterrows():
        m.append("%-11s %5d %4d %4d %4d %%%6.1f %+10.2f  %s" % (r["sembol"], r["islem"], r["TP"], r["STOP"], r["SURE"],
                                                              r["basari"], r["dolar"], r["birlesim"]))
    ms = "\n".join(m)
    print("\n" + ms)
    with open(os.path.join(klasor, "0_OZET.txt"), "w", encoding="utf-8") as fh:
        fh.write(ms + "\n")
    print("\nDosyalar: %s" % os.path.abspath(klasor))


if __name__ == "__main__":
    main()
