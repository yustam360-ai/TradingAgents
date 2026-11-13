# -*- coding: utf-8 -*-
"""
ICT 2022 MODELI v2 - GUN GUN TARAMA (sade ICT mantigi, ekstra sert sart yok)
=============================================================================
Python 3.8:   py -3.8 ict_model_test_v2.py
Gerekli:      py -3.8 -m pip install MetaTrader5 pandas numpy
Sadece bazi semboller:   py -3.8 ict_model_test_v2.py --sembol EURUSD,GBPUSD
TEK DOSYA. MT5'e baglanir, SADECE gecmis veri okur, ISLEM ACMAZ.
SPREAD YOK, KOMISYON YOK, HABER FILTRESI YOK.  Donem: 1 Ocak 2026 -> bugun (her gun tek tek).
Rapor iki parca: OCAK-TEMMUZ ve AGUSTOS-BUGUN.

ONCEKI TESTTEN FARKLAR (ICT'nin sozune gore gevsetildi):
  - Gunluk yon: YOK (iki yon de aranir) ya da GEVSEK (asagiya bakiniz) - ikisi de denenir
  - Supurulecek seviye: butun belirgin swing tepeler (1 saat ve 15 dk), onceki gun tepesi, esit tepeler,
    Asya ve Londra araligi tepesi  ("every swing high has buy stops above it" - bolum 11)
  - Kirilim icin 2 saat siniri YOK (killzone icinde olsun yeter)
  - Acilis fiyati sarti YOK
  - Hedef: 2R / 3R / EN_YAKIN (en yakin karsi hedef, en az 2R) - ucu de denenir
  - Forex'te Londra killzone da var

HER GUN, HER SEMBOL ICIN (SATIS anlatiliyor, ALIS birebir tersi)
  1) YON  YOK    : iki yon de aranir
          GEVSEK : satis icin dun ya da bugun fiyat ustteki bir gunluk bearish FVG'ye girdi, YA DA son 10 gunun
                   en yuksek tepesini gecti, YA DA dun onceki gunun tepesini asip altinda kapandi
  2) LIKIDITE    : killzone basinda alinmamis olan: onceki gunun tepesi (PDH), 1 saatlik swing tepeler (son 3 gun),
                   1 saatlik esit tepeler (EQH), 15 dk swing tepeler (son 1 gun), Asya araligi tepesi (NY 19-24),
                   Londra araligi tepesi (NY 02-05, sadece NY killzone icin)
  3) SAAT        : FOREX  Londra killzone NY 02:00-05:00 (TR kis 10-13) + NY killzone NY 07:00-10:00 (TR kis 15-18)
                   DIGER  NY 08:30-10:45 (TR kis 16:30-18:45)
  4) SUPURME     : killzone icinde 15 dk mum bu tepelerden birinin ustune cikar
  5) MSS         : sonra (killzone bitmeden) bir 15 dk mum son swing dibin (3 mum) ALTINDA kapanir
  6) FVG         : kirilim hareketinde 5 dk (yoksa 15 dk) FVG, hareketin ust yarisinda, doldurulmamis
  7) GIRIS       : FVG alt kenari ya da OTE (%62 geri cekilme), limit emir
                   (Londra emri NY 06:00'ya, NY emri NY 12:00'ye kadar gecerli; dolmadan TP gelirse iptal)
  8) STOP        : SWING = supuren tepe + 1 tick   ya da   FVG_MUM = FVG 1. mumunun tepesi + 1 tick
  9) TP          : 2R / 3R / EN_YAKIN (hareket dibi, 15 dk swing dip, onceki gun dibi, esit dipler; en az 2R)
 10) STOP YONETIMI (ICT 41): hedef yolunun %50'sinde stop %25 yaklasir, %75'inde girise cekilir
 11) Sembolde ayni anda tek islem; sembol STOP olursa o gun o sembolde yeni islem yok (digerleri devam).
     Acik islem NY 16:00'da kapanir.  Risk 15 $; en kucuk lotta zarar 30 $'i gecerse islem yok.
  24 secenek: YON (2) x GIRIS (2) x STOP (2) x TP (3).

CIKTI (ict_model2_<tarih>/):
  0_OZET.txt     24 secenek x 2 donem; OCAK-TEMMUZ'da en iyi 3 secenegin ayrintisi (aylik, 10.000 $, %50 ustu pariteler)
  1_islemler.csv butun islemler - KONTROL KARTI (TR saati, yon sebebi, supurulen seviye, MSS, FVG, giris, stop, TP)
  2_sembol.csv   secenek x sembol x donem
"""
from __future__ import print_function

import argparse
import os
import sys
import time
from datetime import date, datetime, timedelta, timezone

import numpy as np
import pandas as pd

try:
    import MetaTrader5 as mt5
except ImportError:
    mt5 = None

RISK = 15.0
SAY = {"gun": 0, "likidite": 0, "supurme": 0, "mss": 0, "fvg": 0}
EN_FAZLA = 30.0
BASLANGIC = 10000.0
SUNUCU_NY = 7
SECENEKLER = [(yn, gr, st, tp) for yn in ("YOK", "GEVSEK") for gr in ("FVG", "OTE") for st in ("SWING", "FVG_MUM")
              for tp in ("2R", "3R", "EN_YAKIN")]


# ----------------------------------------------------------------- saat (yaz / kis otomatik)
def _pazar(y, ay, kacinci):
    if kacinci > 0:
        d = date(y, ay, 1)
        d += timedelta(days=(6 - d.weekday()) % 7)
        return d + timedelta(days=7 * (kacinci - 1))
    d = date(y, ay + 1, 1) - timedelta(days=1)
    return d - timedelta(days=(d.weekday() - 6) % 7)


def ny_utc(d):
    return -4 if _pazar(d.year, 3, 2) <= d < _pazar(d.year, 11, 1) else -5


def sunucu_utc(d):
    return ny_utc(d) + SUNUCU_NY


def tr(dk):
    dk = int(dk)
    g = date(1970, 1, 1) + timedelta(days=dk // 1440)
    return (datetime(1970, 1, 1) + timedelta(minutes=dk + (3 - sunucu_utc(g)) * 60)).strftime("%Y-%m-%d %H:%M")


def saat_dogrula(semboller):
    global SUNUCU_NY
    bugun = datetime.now(timezone.utc).date()
    beklenen = sunucu_utc(bugun)
    simdi = time.time()
    for s in ["BTCUSD", "ETHUSD", "EURUSD", "GBPUSD"] + list(semboller[:20]):
        try:
            if not mt5.symbol_select(s, True):
                continue
            tk = mt5.symbol_info_tick(s)
        except Exception:
            tk = None
        if tk is None or not getattr(tk, "time", 0):
            continue
        f = (tk.time - simdi) / 3600.0
        y = round(f)
        if abs(f - y) * 60 > 3:
            continue
        if y == beklenen:
            return "MT5 sunucu saati UTC%+d (%s) = New York + %d -> DOGRULANDI." % (y, s, SUNUCU_NY)
        SUNUCU_NY = int(y - ny_utc(bugun))
        return "UYARI: sunucu UTC%+d bulundu (beklenen UTC%+d). Ayarlandi: sunucu = NY %+d." % (y, beklenen, SUNUCU_NY)
    return "MT5 saati kontrol edilemedi; kural: sunucu = New York + %d." % SUNUCU_NY


# ----------------------------------------------------------------- veri
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


def deger_lot(s, bilgi):
    v = None
    try:
        tk = mt5.symbol_info_tick(s)
        p = float(tk.bid) if tk is not None and tk.bid > 0 else None
        if p:
            d = max(p * 0.001, bilgi.point * 100)
            k = mt5.order_calc_profit(mt5.ORDER_TYPE_BUY, s, 1.0, p, p - d)
            if k is not None and k < 0:
                v = -float(k) / d
    except Exception:
        v = None
    if not v:
        tv = getattr(bilgi, "trade_tick_value_loss", 0) or getattr(bilgi, "trade_tick_value", 0)
        ts = getattr(bilgi, "trade_tick_size", 0)
        if tv and ts:
            v = tv / ts
    return v


def mumlar(T, O, H, L, C, K):
    df = pd.DataFrame({"k": T // K, "o": O, "h": H, "l": L, "c": C}).groupby("k").agg(
        o=("o", "first"), h=("h", "max"), l=("l", "min"), c=("c", "last"))
    return (df.index.to_numpy(np.int64) * K,) + tuple(df[x].to_numpy(float) for x in ("o", "h", "l", "c"))


def atr_hesap(h, l, c, p=14):
    tr_ = np.r_[h[0] - l[0], np.maximum(h[1:] - l[1:], np.maximum(np.abs(h[1:] - c[:-1]), np.abs(l[1:] - c[:-1])))]
    return pd.Series(tr_).rolling(p, min_periods=1).mean().to_numpy()


def swinglar(bt, v, K, tepe):
    """3 mumluk swing: (dogrulanma zamani, fiyat, olusma zamani). tepe=True: v'nin tepeleri, False: dipleri"""
    if len(v) < 3:
        return np.array([], np.int64), np.array([]), np.array([], np.int64)
    m = v[1:-1]
    ok = (m > v[:-2]) & (m > v[2:]) if tepe else (m < v[:-2]) & (m < v[2:])
    k = np.flatnonzero(ok) + 1
    return bt[k + 1] + K, v[k], bt[k]




# ----------------------------------------------------------------- bir sembol
def sembol_isle(s, m1, d1, bilgi, vpl, forex, bas_gun, test_gun):
    T = m1["time"].to_numpy(np.int64) // 60
    O, H, L, C = [m1[k].to_numpy(float) for k in ("open", "high", "low", "close")]
    dT = d1["time"].to_numpy(np.int64) // 60
    adim = bilgi.volume_step if bilgi.volume_step > 0 else 0.01
    vmax = bilgi.volume_max if bilgi.volume_max > 0 else 1e9
    nokta = float(bilgi.point)
    son_dk = int(T[-1])
    G = {}
    for y in (-1, 1):
        if y < 0:
            vh, vl, vc, vo = H, L, C, O
            dh, dl, dc = d1["high"].to_numpy(float), d1["low"].to_numpy(float), d1["close"].to_numpy(float)
        else:
            vh, vl, vc, vo = -L, -H, -C, -O
            dh, dl, dc = -d1["low"].to_numpy(float), -d1["high"].to_numpy(float), -d1["close"].to_numpy(float)
        B = {K: mumlar(T, vo, vh, vl, vc, K) for K in (5, 15, 60)}
        a60 = atr_hesap(B[60][2], B[60][3], B[60][4])
        G[y] = dict(vh=vh, vl=vl, vc=vc, vo=vo, dh=dh, dl=dl, dc=dc, B=B, a60=a60,
                    sw15d=swinglar(B[15][0], B[15][3], 15, False),
                    sw15t=swinglar(B[15][0], B[15][2], 15, True),
                    sw60t=swinglar(B[60][0], B[60][2], 60, True),
                    sw60d=swinglar(B[60][0], B[60][3], 60, False))

    def ix(t):
        return int(np.searchsorted(T, t))

    def alinmadi(g, lv, bil, ws, tepe=True):
        a_, b_ = ix(bil), ix(ws)
        if b_ <= a_:
            return True
        return g["vh"][a_:b_].max() <= lv if tepe else g["vl"][a_:b_].min() >= lv

    def esitler(g, ct, cp, ot, tbit, tepe):
        out = []
        sec = np.flatnonzero((ct <= tbit) & (ot >= tbit - 5 * 1440))
        bt60, a60 = g["B"][60][0], g["a60"]
        for bi in range(1, len(sec)):
            for ai in range(bi):
                a, b = sec[ai], sec[bi]
                k = max(0, int(np.searchsorted(bt60, ot[b])) - 1)
                if abs(cp[a] - cp[b]) > 0.1 * a60[min(k, len(a60) - 1)]:
                    continue
                lv = max(cp[a], cp[b]) if tepe else min(cp[a], cp[b])
                if alinmadi(g, lv, int(ot[a]) + 60, tbit, tepe):
                    out.append((lv, int(ct[b])))
        return out

    adaylar = []
    for gun in np.unique(T // 1440):
        if gun < bas_gun:
            continue
        D = int(gun * 1440)
        nyMid = D + SUNUCU_NY * 60
        if forex:
            pencereler = [("LONDRA", nyMid + 120, nyMid + 300, nyMid + 360), ("NY", nyMid + 420, nyMid + 600, nyMid + 720)]
        else:
            pencereler = [("NY", nyMid + 510, nyMid + 645, nyMid + 720)]
        kapanis = nyMid + 960
        d = int(np.searchsorted(dT, D)) - 1
        if d < 22 or ix(nyMid) >= len(T):
            continue
        SAY["gun"] += 1
        for y in (-1, 1):
            g = G[y]
            sg = 1 if y < 0 else -1
            dh, dl, dc = g["dh"], g["dl"], g["dc"]
            for pad, ws, we, iptal in pencereler:
                if ix(ws) >= len(T):
                    continue
                # 1) gevsek yon
                i0, i1 = ix(D), ix(ws)
                bugun_tepe = g["vh"][i0:i1].max() if i1 > i0 else -np.inf
                yon = ""
                for a in range(d - 21, d - 2):
                    c = a + 2
                    if dl[a] > dh[c]:
                        alt = dh[c]
                        once = dh[c + 1:d].max() if d > c + 1 else -np.inf
                        if once < alt and (dh[d] >= alt or bugun_tepe >= alt):
                            yon = "GUNLUK_FVG"
                            break
                if not yon and max(dh[d], bugun_tepe) > dh[d - 10:d].max():
                    yon = "10_GUN_TEPESI"
                if not yon and dh[d] > dh[d - 1] and dc[d] < dh[d - 1]:
                    yon = "TURTLE"
                # 2) likidite
                sev = [(dh[d], D, "PDH" if y < 0 else "PDL")]
                j0, j1 = ix(nyMid - 300), ix(nyMid)
                if j1 > j0:
                    sev.append((g["vh"][j0:j1].max(), nyMid, "ASYA"))
                if pad == "NY":
                    j0, j1 = ix(nyMid + 120), ix(nyMid + 300)
                    if j1 > j0:
                        sev.append((g["vh"][j0:j1].max(), nyMid + 300, "LONDRA"))
                ct, cp, ot = g["sw60t"]
                for k in np.flatnonzero((ct <= ws) & (ot >= ws - 3 * 1440)):
                    sev.append((cp[k], int(ct[k]), "1S_SWING"))
                for lv, bil in esitler(g, ct, cp, ot, ws, True):
                    sev.append((lv, bil, "EQH" if y < 0 else "EQL"))
                ct, cp, ot = g["sw15t"]
                for k in np.flatnonzero((ct <= ws) & (ot >= ws - 1440)):
                    sev.append((cp[k], int(ct[k]), "15DK_SWING"))
                acik = [(lv, ad) for lv, bil, ad in sev if lv == lv and bil <= ws and alinmadi(g, lv, bil, ws)]
                if not acik:
                    continue
                SAY["likidite"] += 1
                hedef0 = [(dl[d], "PDL" if y < 0 else "PDH")]
                ct, cp, ot = g["sw60d"]
                for lv, bil in esitler(g, ct, cp, ot, ws, False):
                    hedef0.append((lv, "EQL" if y < 0 else "EQH"))
                # 4) supurme (15 dk)
                bt, bo, bh, bl, bc = g["B"][15]
                j0, j1 = int(np.searchsorted(bt, ws)), int(np.searchsorted(bt, we))
                sw_ct, sw_cp, sw_ot = g["sw15d"]
                for i in range(j0, j1):
                    if bt[i] + 15 > we:
                        break
                    vur = [(lv, ad) for lv, ad in acik if bh[i] > lv]
                    if not vur:
                        continue
                    acik = [x for x in acik if x not in vur]
                    SAY["supurme"] += 1
                    sevf, sevad = max(vur)
                    # 5) MSS (15 dk), killzone bitmeden
                    q = int(np.searchsorted(sw_ct, bt[i] + 15, side="right")) - 1
                    if q < 0:
                        continue
                    ref = sw_cp[q]
                    jk = -1
                    for j in range(i + 1, len(bt)):
                        if bt[j] + 15 > we:
                            break
                        if bc[j] < ref:
                            jk = j
                            break
                    if jk < 0:
                        continue
                    SAY["mss"] += 1
                    Td = int(bt[jk] + 15)
                    shi = i + int(np.argmax(bh[i:jk + 1]))
                    tepe = bh[i:jk + 1].max()
                    dip = bl[shi:jk + 1].min()
                    fiyat = bc[jk]
                    # 6) FVG (5 dk, yoksa 15 dk)
                    fv = None
                    for K in (5, 15):
                        b5t, _, b5h, b5l, _ = g["B"][K]
                        a0, a1 = int(np.searchsorted(b5t, bt[shi])), int(np.searchsorted(b5t, Td))
                        for a in range(a0, a1 - 2):
                            c = a + 2
                            if b5t[c] + K > Td:
                                break
                            if b5l[a] > b5h[c]:
                                alt, ust = b5h[c], b5l[a]
                                if fiyat >= alt or alt < dip + 0.5 * (tepe - dip):
                                    continue
                                if c + 1 < a1 and b5h[c + 1:a1].max() >= alt:
                                    continue
                                if fv is None or alt < fv[0]:
                                    fv = (alt, ust, b5h[a])
                        if fv is not None:
                            break
                    if fv is None:
                        continue
                    SAY["fvg"] += 1
                    hed = list(hedef0) + [(dip, "BACAK_DIBI")]
                    for k in np.flatnonzero((sw_ct <= Td) & (sw_ot >= Td - 2 * 1440)):
                        if alinmadi(g, sw_cp[k], int(sw_ot[k]) + 15, Td, tepe=False):
                            hed.append((sw_cp[k], "15DK_DIP"))
                    adaylar.append(dict(y=y, sg=sg, gun=int(gun), pencere=pad, Td=Td, iptal=iptal, kapanis=kapanis,
                                        yon=yon, sev=sevad, sevf=sevf, tsup=int(bt[i]), mssf=ref,
                                        tepe=tepe, dip=dip, fvg=fv, hed=hed, test=bool(gun >= test_gun)))
    adaylar.sort(key=lambda x: (x["Td"], x["y"]))

    islem = []
    for yn, giris, stop, hdf in SECENEKLER:
        sec = "YON=%s GIRIS=%s STOP=%s TP=%s" % (yn, giris, stop, hdf)
        mesgul, durdu = -1, set()
        for x in adaylar:
            if yn == "GEVSEK" and not x["yon"]:
                continue
            if x["Td"] < mesgul or x["gun"] in durdu or x["kapanis"] > son_dk:
                continue
            g = G[x["y"]]
            alt, ust, ilk = x["fvg"]
            E = alt if giris == "FVG" else x["dip"] + 0.62 * (x["tepe"] - x["dip"])
            S = (x["tepe"] if stop == "SWING" else ilk) + nokta
            r = S - E
            if not (r > 0):
                continue
            if hdf == "2R":
                TP, tpad = E - 2.0 * r, "2R"
            elif hdf == "3R":
                TP, tpad = E - 3.0 * r, "3R"
            else:
                ad = [(lv, n) for lv, n in x["hed"] if E - lv >= 2.0 * r]
                if not ad:
                    continue
                TP, tpad = max(ad)
            rpl = r * vpl
            lot = np.floor(RISK / rpl / adim + 1e-9) * adim
            if lot < bilgi.volume_min:
                lot = bilgi.volume_min
            lot = min(lot, vmax)
            zarar = lot * rpl
            if zarar > EN_FAZLA + 1e-9:
                continue
            a0, c1, z1 = ix(x["Td"]), ix(x["iptal"]), ix(x["kapanis"])
            vh, vl, vc = g["vh"], g["vl"], g["vc"]
            fz = np.flatnonzero(vh[a0:c1] >= E)
            if not fz.size:
                mesgul = x["iptal"]
                continue
            f = a0 + int(fz[0])
            if f > a0 and vl[a0:f].min() <= TP:
                mesgul = int(T[f])
                continue
            Sm, asama, sonuc, R, cik = S, 0, None, 0.0, None
            yol = E - TP
            for m in range(f, z1):
                if vh[m] >= Sm:
                    R = (E - Sm) / r
                    sonuc = "STOP" if asama == 0 else ("STOP_-0.75R" if asama == 1 else "BASABAS")
                    cik = int(T[m])
                    break
                if m > f and vl[m] <= TP:
                    R, sonuc, cik = yol / r, "TP", int(T[m])
                    break
                ilerleme = (E - vl[m]) / yol
                if asama < 2 and ilerleme >= 0.75:
                    Sm, asama = E, 2
                elif asama < 1 and ilerleme >= 0.5:
                    Sm, asama = S - 0.25 * r, 1
            if sonuc is None:
                R, sonuc, cik = (E - vc[z1 - 1]) / r, "SURE", int(T[z1 - 1]) + 1
            mesgul = cik
            if R < 0:
                durdu.add(x["gun"])
            sg = x["sg"]
            lo, hi = sorted((sg * alt, sg * ust))
            islem.append(dict(secenek=sec, sembol=s, donem="AGUSTOS-BUGUN" if x["test"] else "OCAK-TEMMUZ",
                              karar_tr=tr(x["Td"]), seans=x["pencere"], yon="SAT" if x["y"] < 0 else "AL",
                              yon_sebebi=x["yon"] or "-", supurulen=x["sev"], supurulen_fiyat=round(sg * x["sevf"], 6),
                              supurme_tr=tr(x["tsup"]), mss_fiyat=round(sg * x["mssf"], 6), fvg_alt=round(lo, 6),
                              fvg_ust=round(hi, 6), giris=round(sg * E, 6), stop=round(sg * S, 6), tp=round(sg * TP, 6),
                              tp_hedef=tpad, tp_R=round(yol / r, 2), dolum_tr=tr(T[f]), cikis_tr=tr(cik), sonuc=sonuc,
                              R=round(R, 3), dolar=round(R * zarar, 2), cikis_dk=cik))
    return islem, len(adaylar)


# ----------------------------------------------------------------- rapor
def ozet(x):
    n = len(x)
    if not n:
        return dict(islem=0, TP=0, STOP=0, KISMI=0, BASABAS=0, SURE=0, basari=0.0, R=0.0, dolar=0.0)
    s = x["sonuc"]
    return dict(islem=n, TP=int((s == "TP").sum()), STOP=int((s == "STOP").sum()), KISMI=int((s == "STOP_-0.75R").sum()),
                BASABAS=int((s == "BASABAS").sum()), SURE=int((s == "SURE").sum()),
                basari=round(100.0 * (x["R"] > 0).mean(), 1), R=round(x["R"].sum(), 1), dolar=round(x["dolar"].sum(), 2))


def hesap(x):
    if not len(x):
        return "islem yok"
    d = x.sort_values("cikis_dk")
    bak = BASLANGIC + d["dolar"].cumsum().to_numpy()
    tepe = np.maximum.accumulate(np.r_[BASLANGIC, bak])[1:]
    gunluk = d.groupby(d["cikis_dk"] // 1440)["dolar"].sum()
    return ("10.000 $ -> %.2f $ (net %+.2f $) | en kotu gun %+.2f $ | en iyi gun %+.2f $ | en buyuk dusus %+.2f $ | "
            "en dusuk bakiye %.2f $ | gunluk 300 $ asilan gun %d" % (bak[-1], bak[-1] - BASLANGIC, gunluk.min(), gunluk.max(),
                                                                     (bak - tepe).min(), min(BASLANGIC, bak.min()),
                                                                     int((gunluk < -300).sum())))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bas", default="2026-01-01")
    ap.add_argument("--test", default="2026-08-01")
    ap.add_argument("--sembol", default="")
    ap.add_argument("--cikti", default="")
    args = ap.parse_args()
    if mt5 is None:
        sys.exit("MetaTrader5 modulu yok:  py -3.8 -m pip install MetaTrader5")
    if not mt5.initialize():
        sys.exit("MT5 baglantisi kurulamadi: %s" % (mt5.last_error(),))
    semboller = ([x.strip() for x in args.sembol.split(",") if x.strip()] if args.sembol
                 else [x.name for x in (mt5.symbols_get() or [])])
    saat_notu = saat_dogrula(semboller)
    print(saat_notu)
    bas = datetime.strptime(args.bas, "%Y-%m-%d")
    bas_gun = int((bas - datetime(1970, 1, 1)).total_seconds() // 86400)
    test_gun = int((datetime.strptime(args.test, "%Y-%m-%d") - datetime(1970, 1, 1)).total_seconds() // 86400)
    simdi = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=sunucu_utc(datetime.now(timezone.utc).date()))
    klasor = args.cikti or ("ict_model2_%s" % datetime.now().strftime("%Y%m%d_%H%M"))
    if not os.path.isdir(klasor):
        os.makedirs(klasor)
    yaz = dict(sep=";", decimal=",", index=False, encoding="utf-8-sig")
    print("Sembol: %d | %s -> bugun | spread yok | %d secenek" % (len(semboller), args.bas, len(SECENEKLER)))
    tum, yok, t0 = [], [], time.time()
    for n_, s in enumerate(semboller, 1):
        if not mt5.symbol_select(s, True):
            yok.append(s); print("[%d/%d] %s : sembol yok" % (n_, len(semboller), s)); continue
        bilgi = mt5.symbol_info(s)
        vpl = deger_lot(s, bilgi) if bilgi is not None else None
        m1 = cek(s, mt5.TIMEFRAME_M1, bas - timedelta(days=8), simdi + timedelta(days=1), 15)
        d1 = cek(s, mt5.TIMEFRAME_D1, bas - timedelta(days=60), simdi + timedelta(days=1), 400)
        if bilgi is None or not vpl or m1 is None or len(m1) < 20000 or d1 is None or len(d1) < 30:
            yok.append(s); print("[%d/%d] %s : veri yok" % (n_, len(semboller), s)); continue
        forex = bilgi.trade_calc_mode in (0, 5)
        isl, nk = sembol_isle(s, m1, d1, bilgi, vpl, forex, bas_gun, test_gun)
        tum += isl
        x = pd.DataFrame(isl)
        ana = x[x["secenek"] == "YON=YOK GIRIS=FVG STOP=SWING TP=2R"] if len(x) else x
        print("[%d/%d] %s : %d kurulum | ornek secenek (YON=YOK FVG SWING 2R): %d islem, TP %d, STOP %d, %+.0f $  (%.0f sn)" % (
            n_, len(semboller), s, nk, len(ana), (ana["sonuc"] == "TP").sum() if len(ana) else 0,
            (ana["sonuc"] == "STOP").sum() if len(ana) else 0, ana["dolar"].sum() if len(ana) else 0, time.time() - t0))
    mt5.shutdown()
    if not tum:
        sys.exit("Hic islem yok.")
    di = pd.DataFrame(tum)
    di.drop(columns=["cikis_dk"]).to_csv(os.path.join(klasor, "1_islemler.csv"), **yaz)
    sb = pd.DataFrame([dict(secenek=a, sembol=b, donem=c, **ozet(x)) for (a, b, c), x in di.groupby(["secenek", "sembol", "donem"])])
    sb.to_csv(os.path.join(klasor, "2_sembol.csv"), **yaz)

    m = []
    c = "=" * 150
    m.append(c)
    m.append("ICT 2022 MODELI v2 (sade) - GUN GUN | %s -> bugun | %d sembol | SPREAD YOK | risk 15 $" % (args.bas, len(semboller) - len(yok)))
    m.append("SAAT: " + saat_notu)
    m.append("KURULUM HUNISI: sembol-gun %d | alinmamis likidite olan killzone %d | supurme %d | MSS %d | FVG (kurulum) %d"
             % (SAY["gun"], SAY["likidite"], SAY["supurme"], SAY["mss"], SAY["fvg"]))
    m.append(c)
    b = "%-44s %-14s | %6s %5s %5s %6s %7s %5s %7s %8s %10s" % ("SECENEK", "DONEM", "ISLEM", "TP", "STOP", "-0.75R",
                                                              "BASABAS", "SURE", "BASARI", "NET R", "DOLAR")
    m.append("")
    m.append("-- 24 SECENEK x 2 DONEM (butun semboller) --")
    m.append(b)
    sira = []
    for yn, gr, st, tp in SECENEKLER:
        sec = "YON=%s GIRIS=%s STOP=%s TP=%s" % (yn, gr, st, tp)
        for dn in ("OCAK-TEMMUZ", "AGUSTOS-BUGUN"):
            o = ozet(di[(di["secenek"] == sec) & (di["donem"] == dn)])
            if dn == "OCAK-TEMMUZ":
                sira.append((o["R"], sec))
            m.append("%-44s %-14s | %6d %5d %5d %6d %7d %5d %%%6.1f %+8.1f %+10.2f" % (
                sec, dn, o["islem"], o["TP"], o["STOP"], o["KISMI"], o["BASABAS"], o["SURE"], o["basari"], o["R"], o["dolar"]))
    sira.sort(reverse=True)
    for _, sec in sira[:3]:
        x = di[di["secenek"] == sec]
        m.append("")
        m.append(c)
        m.append(sec + "   (OCAK-TEMMUZ'da ilk 3)")
        m.append(c)
        m.append("-- AYLIK --")
        for ay, z in x.groupby(x["cikis_tr"].str[:7]):
            o = ozet(z)
            m.append("   %-8s islem %4d | TP %4d | STOP %4d | -0.75R %3d | BASABAS %3d | SURE %3d | basari %%%5.1f | %+9.2f $"
                     % (ay, o["islem"], o["TP"], o["STOP"], o["KISMI"], o["BASABAS"], o["SURE"], o["basari"], o["dolar"]))
        m.append("-- SEANS --")
        for sn, z in x.groupby("seans"):
            o = ozet(z)
            m.append("   %-8s islem %4d | TP %4d | STOP %4d | basari %%%5.1f | %+9.2f $" % (sn, o["islem"], o["TP"], o["STOP"], o["basari"], o["dolar"]))
        m.append("10.000 $ (OCAK-BUGUN)    : " + hesap(x))
        m.append("10.000 $ (AGUSTOS-BUGUN) : " + hesap(x[x["donem"] == "AGUSTOS-BUGUN"]))
        p = sb[sb["secenek"] == sec]
        a = p[p["donem"] == "OCAK-TEMMUZ"].set_index("sembol")
        t = p[p["donem"] == "AGUSTOS-BUGUN"].set_index("sembol")
        ok = [s_ for s_ in a.index if s_ in t.index and a.at[s_, "islem"] >= 3 and t.at[s_, "islem"] >= 3
              and a.at[s_, "basari"] > 50 and t.at[s_, "basari"] > 50]
        m.append("-- IKI DONEMDE DE BASARISI %%50'NIN USTUNDE OLAN PARITELER (her donem en az 3 islem): %d --" % len(ok))
        m.append("%-12s | %5s %4s %5s %7s %10s || %5s %4s %5s %7s %10s" % ("SEMBOL", "ISLEM", "TP", "STOP", "BASARI", "DOLAR",
                                                                           "ISLEM", "TP", "STOP", "BASARI", "DOLAR"))
        for s_ in sorted(ok, key=lambda z: -(a.at[z, "dolar"] + t.at[z, "dolar"])):
            m.append("%-12s | %5d %4d %5d %%%6.1f %+10.2f || %5d %4d %5d %%%6.1f %+10.2f" % (
                s_, a.at[s_, "islem"], a.at[s_, "TP"], a.at[s_, "STOP"], a.at[s_, "basari"], a.at[s_, "dolar"],
                t.at[s_, "islem"], t.at[s_, "TP"], t.at[s_, "STOP"], t.at[s_, "basari"], t.at[s_, "dolar"]))
        if ok:
            m.append("Sadece bu pariteler (OCAK-BUGUN): " + hesap(x[x["sembol"].isin(ok)]))
    if yok:
        m.append("")
        m.append("Verisi olmayan: " + ", ".join(yok))
    m.append("")
    m.append("BASARI = kar ile kapanan islem orani.  -0.75R = stop %25 yaklastiktan sonra stop.  BASABAS = stop girise")
    m.append("cekildikten sonra stop (0 R).  SURE = NY 16:00'da acik kapanan islem.")
    m.append("1_islemler.csv: her islemin tarihi (TR), seans, yon sebebi, supurulen seviye, MSS, FVG, giris, stop, TP -> grafikte kontrol.")
    ms = "\n".join(m)
    print("\n" + ms)
    with open(os.path.join(klasor, "0_OZET.txt"), "w", encoding="utf-8") as fh:
        fh.write(ms + "\n")
    print("\nDosyalar: %s" % os.path.abspath(klasor))


if __name__ == "__main__":
    main()
