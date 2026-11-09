# -*- coding: utf-8 -*-
"""
EKIN YUZBASIOGLU - "BILMENIZ GEREKEN TEK STRATEJI" (Bootcamp bolum 20, ekrandaki 7 kural) - SON 3 AY, BUTUN SEMBOLLER
====================================================================================================================
Python 3.8:   py -3.8 ekin_model_test_3ay.py
Gerekli:      py -3.8 -m pip install MetaTrader5 pandas numpy
Sadece bazi semboller:   py -3.8 ekin_model_test_3ay.py --sembol EURUSD,GBPUSD
TEK DOSYA. MT5'e baglanir, SADECE gecmis veri okur, ISLEM ACMAZ.  Her islem gecmiste mum mum, o ana kadar
olusmus veriyle aranir (gelecek gorulmez).

EKRANDAKI 7 KURAL (satis anlatiliyor, alis birebir tersi)
  1) Onemli likidite seviyelerinden tepki bekle (1H 4H 1D) (FVG, LIKIDITE)
       -> 1 saat / 4 saat / gunluk grafikte alinmamis swing tepeler + onceki gunun tepesi (PDH)
          ve doldurulmamis bearish FVG'ler.  Fiyat tepenin ustune cikar ya da FVG'ye girer = TEPKI ARANIR.
  2) Kucuk zaman diliminde reversal isaretlerine bak (DISPLACEMENT, IFVG, SHARP TURN)
       -> kirilim hareketinde FVG (displacement) ya da yukari FVG'nin asagi kapanisla bozulmasi (IFVG) olmali.
  3) MSS bekle  -> kucuk zaman diliminde bir mum son swing dibin ALTINDA KAPANIR (govde).
  4) IFVG ya da FVG'den giris yap  -> o FVG / IFVG'ye limit satis emri.
  5) Stop en son olusan swing high'in govdesine ya da FVG'yi baslatan mumun govdesine (agresif stoploss).
  6) 1:2 1:3 RR hedefle.
  7) Bakiyenin %1 %0.5 riske et  -> senin istegin: her islem 15 $ risk, baslangic 10.000 $.

EKRANDA YAZMAYAN, ESKI DERSLERDEN ALINAN (Ekin'in kendi kurali)
  - Saat: Asya yok.  FOREX: Londra killzone NY 02:00-05:00 + NY killzone NY 07:00-10:00
                     DIGER (endeks, emtia, hisse, kripto): NY 08:30-11:00.   MSS bu saatlerde olmali.

KARARSIZ KALINAN YERLER -> HEPSI AYRI AYRI DENENIR (16 secenek)
  TF    : kucuk zaman dilimi 1 dk mi 5 dk mi                        -> 1DK / 5DK
  GIRIS : FVG'nin kenari mi ortasi mi                                -> KENAR / ORTA
  STOP  : swing high govdesi mi FVG'yi baslatan mumun govdesi mi    -> SWING / FVG_MUM
  TP    : 1:2 mi 1:3 mu                                              -> 2R / 3R

BENIM SECTIGIM (Ekin belirtmemis) - degistirmek istersen soyle
  - Swing = 3 mumluk tepe/dip.  Seviye ne kadar eski olabilir: 1H 3 gun, 4H 10 gun, gunluk 30 gun.
  - Tepkiden sonra MSS en gec 2 saat icinde olmali.  Limit emir MSS'ten sonra 2 saat gecerli;
    dolmadan TP seviyesine gelirse iptal.  Acik islem NY 16:00'da (TR kis 00:00) kapatilir.
  - Birden fazla FVG varsa fiyata en yakin olan.  Sembolde ayni anda tek islem.
  - SPREAD DAHIL (MT5 1 dk mum spread'i), spread maliyeti 6 $'i gecen islem acilmaz, en kucuk lotta
    zarar 30 $'i gecerse acilmaz (onceki testlerle ayni kurallar).  Ayni dakikada stop ve TP = STOP.

CIKTI (ekin_test_<tarih>/):
  0_OZET.txt      16 secenek, en iyi secenekte %50 ustu semboller, her sembolun en iyisi, 10.000 $,
                  EN ALTTA: hangi kural mantikli / mantiksiz
  1_islemler.csv  butun islemler - KONTROL KARTI (TR saati, tepki verilen seviye, MSS, FVG, giris, stop, TP, sonuc)
  2_sembol.csv    secenek x sembol
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
EN_FAZLA = 30.0
MAKAS_SINIR = 6.0
SPREAD_DAHIL = True
BASLANGIC = 10000.0
SUNUCU_NY = 7                      # FTMO sunucu saati = New York + 7
MSS_PENCERE = 120                  # tepkiden sonra MSS icin en fazla dakika
EMIR_SURE = 120                    # limit emrin gecerlilik suresi (dk)
KAPANIS = 23 * 60                  # sunucu 23:00 = NY 16:00
SEVIYE_TF = ((60, "1H", 3), (240, "4H", 10), (1440, "1D", 30))
TFLER = (1, 5)
SECENEKLER = [(tf, gr, st, tp) for tf in TFLER for gr in ("KENAR", "ORTA") for st in ("SWING", "FVG_MUM") for tp in (2, 3)]
SAY = {"tepki": 0, "mss": 0, "fvg": 0}


def sec_ad(tf, gr, st, tp):
    return "TF=%dDK GIRIS=%s STOP=%s TP=%dR" % (tf, gr, st, tp)


# ----------------------------------------------------------------- saat
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


def pencereler(forex):
    """sunucu gunu icindeki dakika: (bas, bit, ad).  NY saati + SUNUCU_NY"""
    n = SUNUCU_NY * 60
    if forex:
        return [(n + 120, n + 300, "LONDRA"), (n + 420, n + 600, "NY")]
    return [(n + 510, n + 660, "NY")]


# ----------------------------------------------------------------- veri
def cek(sembol, tf, bas, bit, parca_gun):
    parcalar, a = [], bas
    kol = ["time", "open", "high", "low", "close", "spread"]
    while a < bit:
        b = min(a + timedelta(days=parca_gun), bit)
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
            parcalar.append(d[kol])
        a = b
    if not parcalar:
        return None
    return pd.concat(parcalar).drop_duplicates("time").sort_values("time").reset_index(drop=True)


def deger_lot(s, bilgi):
    """1 lotta 1.0 fiyat hareketinin hesap parasi karsiligi"""
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


# ----------------------------------------------------------------- bir sembol, bir yon (ayna: hep "satis" gibi)
def tepkiler(T, Om, Hm, Lm, Cm, bas_dk):
    """Kural 1: 1H/4H/1D alinmamis tepeler + PDH + doldurulmamis bearish FVG.  Ilk dokunus = tepki.
    donus: {dakika: [(seviye adi, fiyat), ...]}"""
    sev = []
    for K, ad, gun in SEVIYE_TF:
        bt, bo, bh, bl, bc = mumlar(T, Om, Hm, Lm, Cm, K)
        n = len(bt)
        if n < 3:
            continue
        for q in np.flatnonzero((bh[1:-1] > bh[:-2]) & (bh[1:-1] > bh[2:])) + 1:
            t0 = int(bt[q + 1] + K)
            sev.append((t0, t0 + gun * 1440, bh[q], ad + "_TEPE", True))
        for q in np.flatnonzero(bl[:-2] > bh[2:]):
            t0 = int(bt[q + 2] + K)
            sev.append((t0, t0 + gun * 1440, bh[q + 2], ad + "_FVG", False))
        if K == 1440:
            for q in range(n - 1):
                sev.append((int(bt[q] + K), int(bt[q + 1] + K), bh[q], "PDH", True))
    out = {}
    for t0, t1, lv, ad, tepe in sev:
        if t1 < bas_dk - 1440:
            continue
        a, b = int(np.searchsorted(T, t0)), int(np.searchsorted(T, t1))
        if b <= a:
            continue
        z = np.flatnonzero(Hm[a:b] > lv) if tepe else np.flatnonzero(Hm[a:b] >= lv)
        if not z.size:
            continue
        t = int(T[a + int(z[0])])
        if t < bas_dk - 180:
            continue
        out.setdefault(t, []).append((ad, lv))
    return out


def kurulumlar(T, Om, Hm, Lm, Cm, K, tep, forex, bas_dk):
    """Kural 2-5: tepkiden sonra K dk grafikte MSS (govde kapanisi) + FVG / IFVG.  Gelecek kullanilmaz:
    her sey MSS mumunun kapanisina kadar olan mumlarla bulunur."""
    bt, bo, bh, bl, bc = mumlar(T, Om, Hm, Lm, Cm, K)
    n = len(bt)
    swl = np.zeros(n, dtype=bool)
    if n > 2:
        swl[1:-1] = (bl[1:-1] < bl[:-2]) & (bl[1:-1] < bl[2:])
    idx = np.where(swl, np.arange(n), -1)
    sonswl = np.r_[-1, np.maximum.accumulate(idx)[:-1]] if n else idx      # sonswl[j]: dogrulanmis son swing dip (f+1 <= j)
    pen = pencereler(forex)
    out, son_jk = [], -1
    for tt in sorted(tep):
        i = int(np.searchsorted(bt, tt, side="right")) - 1
        if i < 3 or i <= son_jk:
            continue
        SAY["tepki"] += 1
        tepe, p, ref, jk = -np.inf, -1, None, -1
        for j in range(i, n):
            if bt[j] > tt + MSS_PENCERE:
                break
            if bh[j] > tepe:
                tepe, p = bh[j], j
                q = sonswl[j]
                ref = bl[q] if q >= 0 else None
                continue
            if ref is not None and bc[j] < ref:
                jk = j
                break
        if jk < 0:
            continue
        Td = int(bt[jk] + K)
        D = Td // 1440 * 1440
        dk = Td - D
        seans = None
        for a_, b_, ad in pen:
            if a_ < dk <= b_:
                seans = ad
        if seans is None or Td < bas_dk:
            continue
        son_jk = jk
        SAY["mss"] += 1
        fiyat = bc[jk]
        aday = []
        # FVG (displacement): tepe mumundan kirilima kadar
        for a in range(p, jk - 1):
            c = a + 2
            if bl[a] > bh[c]:
                alt, ust = bh[c], bl[a]
                if alt <= fiyat or (c < jk and bh[c + 1:jk + 1].max() >= alt):
                    continue
                aday.append((alt, ust, max(bo[a], bc[a]), "FVG", int(bt[a])))
        # IFVG: yukari yondeki FVG asagi kapanisla bozulmus
        for a in range(max(0, i - 30), p):
            c = a + 2
            if c > jk or not (bh[a] < bl[c]):
                continue
            alt, ust = bh[a], bl[c]
            v = -1
            for w in range(c + 1, jk + 1):
                if bc[w] < alt:
                    v = w
                    break
            if v < 0 or v < p:
                continue
            if v < jk and bh[v + 1:jk + 1].max() >= alt:
                continue
            if alt <= fiyat:
                continue
            aday.append((alt, ust, max(bo[v], bc[v]), "IFVG", int(bt[a])))
        if not aday:
            continue
        SAY["fvg"] += 1
        alt, ust, mum_govde, tur, fvg_t = min(aday)
        sevler = tep[tt]
        out.append(dict(Td=Td, D=D, seans=seans, tt=tt, sev="+".join(sorted(set(x[0] for x in sevler))),
                        sevf=max(x[1] for x in sevler), tepe=tepe, tepe_govde=max(bo[p], bc[p]), mss=ref,
                        alt=alt, ust=ust, mum_govde=mum_govde, tur=tur, fvg_t=fvg_t))
    return out


def sembol_isle(s, m1, bilgi, vpl, forex, bas_dk, test_dk):
    T = m1["time"].to_numpy(np.int64) // 60
    O, H, L, C = [m1[k].to_numpy(float) for k in ("open", "high", "low", "close")]
    SP = m1["spread"].to_numpy(float) * float(bilgi.point)
    SPx = SP if SPREAD_DAHIL else 0.0 * SP
    adim = bilgi.volume_step if bilgi.volume_step > 0 else 0.01
    vmax = bilgi.volume_max if bilgi.volume_max > 0 else 1e9
    son_dk = int(T[-1])
    kur = {tf: [] for tf in TFLER}
    G = {}
    for y in (-1, 1):
        if y < 0:      # satis: grafik BID; satis limit BID ile dolar, stop / TP ASK ile
            Om, Hm, Lm, Cm = O, H, L, C
            F, X, Y, Cx = H, H + SPx, L + SPx, C + SPx
        else:          # alis: ayna; alis limit ASK ile dolar, stop / TP BID ile
            Om, Hm, Lm, Cm = -O, -L, -H, -C
            F, X, Y, Cx = -(L + SPx), -L, -H, -C
        G[y] = (F, X, Y, Cx)
        tep = tepkiler(T, Om, Hm, Lm, Cm, bas_dk)
        for tf in TFLER:
            for x in kurulumlar(T, Om, Hm, Lm, Cm, tf, tep, forex, bas_dk):
                x["y"] = y
                kur[tf].append(x)
    for tf in TFLER:
        kur[tf].sort(key=lambda z: (z["Td"], z["y"]))

    def ix(t):
        return int(np.searchsorted(T, t))

    islem = []
    for tf, giris, stop, hk in SECENEKLER:
        sec = sec_ad(tf, giris, stop, hk)
        mesgul = -1
        for x in kur[tf]:
            z_bit = x["D"] + KAPANIS
            if x["Td"] < mesgul or z_bit > son_dk:
                continue
            F, X, Y, Cx = G[x["y"]]
            E = x["alt"] if giris == "KENAR" else 0.5 * (x["alt"] + x["ust"])
            S = x["tepe_govde"] if stop == "SWING" else x["mum_govde"]
            r = S - E
            if not (r > 0):
                continue
            TP = E - hk * r
            a0 = ix(x["Td"])
            z1 = ix(z_bit)
            c1 = min(ix(x["Td"] + EMIR_SURE), z1)
            if a0 >= c1:
                continue
            sp = SP[a0]
            rpl = r * vpl
            lot = np.floor(RISK / rpl / adim + 1e-9) * adim
            if lot < bilgi.volume_min:
                lot = bilgi.volume_min
            lot = min(lot, vmax)
            zarar = lot * rpl
            if zarar > EN_FAZLA + 1e-9:
                continue
            if SPREAD_DAHIL and sp * lot * vpl > MAKAS_SINIR + 1e-9:
                continue
            fz = np.flatnonzero(F[a0:c1] >= E)
            if not fz.size:
                mesgul = int(T[c1 - 1]) + 1
                continue
            f = a0 + int(fz[0])
            if Y[a0:f + 1].min() <= TP:
                mesgul = int(T[f])
                continue
            st = np.flatnonzero(X[f:z1] >= S)
            tpb = Y[f:z1] <= TP
            tpb[0] = False
            hz = np.flatnonzero(tpb)
            s0 = int(st[0]) if st.size else None
            h0 = int(hz[0]) if hz.size else None
            if s0 is not None and (h0 is None or s0 <= h0):
                R, sonuc, e = -1.0, "STOP", f + s0
            elif h0 is not None:
                R, sonuc, e = float(hk), "TP", f + h0
            else:
                e = z1 - 1
                R, sonuc = (E - Cx[e]) / r, "SURE"
            cik = int(T[e]) + 1
            mesgul = cik
            sg = 1 if x["y"] < 0 else -1
            lo, hi = sorted((sg * x["alt"], sg * x["ust"]))
            islem.append(dict(secenek=sec, sembol=s, donem="SON_1_AY" if x["Td"] >= test_dk else "ILK_2_AY",
                              karar_tr=tr(x["Td"]), seans=x["seans"], yon="SAT" if x["y"] < 0 else "AL",
                              tepki_seviye=x["sev"], tepki_fiyat=round(sg * x["sevf"], 6), tepki_tr=tr(x["tt"]),
                              tepe=round(sg * x["tepe"], 6), mss_fiyat=round(sg * x["mss"], 6), giris_turu=x["tur"],
                              fvg_alt=round(lo, 6), fvg_ust=round(hi, 6), fvg_tr=tr(x["fvg_t"]),
                              giris=round(sg * E, 6), stop=round(sg * S, 6), tp=round(sg * TP, 6),
                              lot=round(lot, 2), dolum_tr=tr(T[f]), cikis_tr=tr(cik), sonuc=sonuc,
                              R=round(R, 3), dolar=round(R * zarar, 2), cikis_dk=cik))
    return islem, len(kur[1]) + len(kur[5])


# ----------------------------------------------------------------- rapor
def ozet(x):
    n = len(x)
    if not n:
        return dict(islem=0, TP=0, STOP=0, SURE=0, basari=0.0, dolar=0.0)
    s = x["sonuc"]
    return dict(islem=n, TP=int((s == "TP").sum()), STOP=int((s == "STOP").sum()), SURE=int((s == "SURE").sum()),
                basari=round(100.0 * (x["R"] > 0).mean(), 1), dolar=round(x["dolar"].sum(), 2))


def hesap(x):
    if not len(x):
        return "islem yok"
    d = x.sort_values("cikis_dk")
    bak = BASLANGIC + d["dolar"].cumsum().to_numpy()
    tepe = np.maximum.accumulate(np.r_[BASLANGIC, bak])[1:]
    gunluk = d.groupby(d["cikis_dk"] // 1440)["dolar"].sum()
    return ("10.000 $ -> %.2f $ (net %+.2f $) | en kotu gun %+.2f $ | en iyi gun %+.2f $ | en buyuk dusus %+.2f $ | "
            "gunluk 300 $ asilan gun %d" % (bak[-1], bak[-1] - BASLANGIC, gunluk.min(), gunluk.max(),
                                            (bak - tepe).min(), int((gunluk < -300).sum())))


def satir(o):
    return "%5d %5d %5d %5d %%%6.1f %+10.2f" % (o["islem"], o["TP"], o["STOP"], o["SURE"], o["basari"], o["dolar"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ay", type=float, default=3.0)
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
    simdi = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=sunucu_utc(datetime.now(timezone.utc).date()))
    bas = (simdi - timedelta(days=int(round(args.ay * 30.5)))).replace(hour=0, minute=0, second=0, microsecond=0)
    test = (simdi - timedelta(days=30)).replace(hour=0, minute=0, second=0, microsecond=0)
    bas_dk = int((bas - datetime(1970, 1, 1)).total_seconds() // 60)
    test_dk = int((test - datetime(1970, 1, 1)).total_seconds() // 60)
    klasor = args.cikti or ("ekin_test_%s" % datetime.now().strftime("%Y%m%d_%H%M"))
    if not os.path.isdir(klasor):
        os.makedirs(klasor)
    yaz = dict(sep=";", decimal=",", index=False, encoding="utf-8-sig")
    print("Sembol: %d | %s -> bugun | spread dahil | %d secenek" % (len(semboller), bas.date(), len(SECENEKLER)))
    tum, yok, t0 = [], [], time.time()
    ornek = sec_ad(5, "KENAR", "SWING", 2)
    for n_, s in enumerate(semboller, 1):
        try:
            if not mt5.symbol_select(s, True):
                yok.append(s); print("[%d/%d] %s : sembol yok" % (n_, len(semboller), s)); continue
            bilgi = mt5.symbol_info(s)
            vpl = deger_lot(s, bilgi) if bilgi is not None else None
            m1 = cek(s, mt5.TIMEFRAME_M1, bas - timedelta(days=35), simdi + timedelta(days=1), 15)
            if bilgi is None or not vpl or m1 is None or len(m1) < 20000:
                yok.append(s); print("[%d/%d] %s : veri yok" % (n_, len(semboller), s)); continue
            forex = getattr(bilgi, "trade_calc_mode", 0) in (0, 5)
            isl, nk = sembol_isle(s, m1, bilgi, vpl, forex, bas_dk, test_dk)
        except Exception as h:
            yok.append(s); print("[%d/%d] %s : hata %s" % (n_, len(semboller), s, h)); continue
        tum += isl
        x = pd.DataFrame(isl)
        a = x[x["secenek"] == ornek] if len(x) else x
        print("[%d/%d] %s : %d kurulum | ornek (5DK KENAR SWING 2R): %d islem, TP %d, STOP %d, %+.0f $  (%.0f sn)" % (
            n_, len(semboller), s, nk, len(a), (a["sonuc"] == "TP").sum() if len(a) else 0,
            (a["sonuc"] == "STOP").sum() if len(a) else 0, a["dolar"].sum() if len(a) else 0, time.time() - t0))
    mt5.shutdown()
    if not tum:
        sys.exit("Hic islem yok.")
    di = pd.DataFrame(tum)
    di.drop(columns=["cikis_dk"]).to_csv(os.path.join(klasor, "1_islemler.csv"), **yaz)
    sb = pd.DataFrame([dict(secenek=a, sembol=b, **ozet(x)) for (a, b), x in di.groupby(["secenek", "sembol"])])
    sb.to_csv(os.path.join(klasor, "2_sembol.csv"), **yaz)

    c = "=" * 130
    m = [c, "EKIN - BILMENIZ GEREKEN TEK STRATEJI (7 kural) | %s -> bugun | %d sembol | SPREAD DAHIL | risk 15 $"
         % (bas.date(), len(semboller) - len(yok)), "SAAT: " + saat_notu,
         "HUNI (iki TF toplam): tepki %d | MSS (killzone icinde) %d | FVG/IFVG'li kurulum %d" % (SAY["tepki"], SAY["mss"], SAY["fvg"]), c]
    bas_ = "%-42s | %5s %5s %5s %5s %7s %10s" % ("SECENEK", "ISLEM", "TP", "STOP", "SURE", "BASARI", "DOLAR")
    m += ["", "-- 16 SECENEK (butun semboller, son 3 ay) --", bas_]
    sira = []
    for tf, gr, st, tp in SECENEKLER:
        sec = sec_ad(tf, gr, st, tp)
        o = ozet(di[di["secenek"] == sec])
        sira.append((o["dolar"], sec))
        m.append("%-42s | %s" % (sec, satir(o)))
    sira.sort(reverse=True)
    en_iyi = sira[0][1]
    x = di[di["secenek"] == en_iyi]
    m += ["", c, "EN IYI SECENEK: " + en_iyi, c,
          "10.000 $ (butun semboller): " + hesap(x),
          "ILK 2 AY : " + satir(ozet(x[x["donem"] == "ILK_2_AY"])) + "    (islem TP STOP SURE basari dolar)",
          "SON 1 AY : " + satir(ozet(x[x["donem"] == "SON_1_AY"]))]
    p = sb[sb["secenek"] == en_iyi].set_index("sembol")
    ok = [s_ for s_ in p.index if p.at[s_, "islem"] >= 5 and p.at[s_, "basari"] > 50]
    m += ["", "-- BU SECENEKTE BASARISI %%50'NIN USTUNDE OLAN SEMBOLLER (en az 5 islem): %d --" % len(ok),
          "%-12s | %5s %5s %5s %5s %7s %10s || SON 1 AY: %5s %7s %10s" % ("SEMBOL", "ISLEM", "TP", "STOP", "SURE", "BASARI",
                                                                         "DOLAR", "ISLEM", "BASARI", "DOLAR")]
    for s_ in sorted(ok, key=lambda z: -p.at[z, "dolar"]):
        z = x[x["sembol"] == s_]
        o2 = ozet(z[z["donem"] == "SON_1_AY"])
        m.append("%-12s | %s || %15d %%%6.1f %+10.2f" % (s_, satir(ozet(z)), o2["islem"], o2["basari"], o2["dolar"]))
    if ok:
        m.append("Sadece bu semboller, 10.000 $: " + hesap(x[x["sembol"].isin(ok)]))
    # her sembolun kendi en iyisi
    m += ["", c, "HER SEMBOLUN KENDI EN IYI SECENEGI (basari %50 ustu, en az 5 islem) - DIKKAT: 3 ayin sonucuna bakarak secildi", c,
          "%-12s %-42s | %5s %5s %5s %5s %7s %10s || SON 1 AY: %5s %7s %10s" % ("SEMBOL", "SECENEK", "ISLEM", "TP", "STOP", "SURE",
                                                                              "BASARI", "DOLAR", "ISLEM", "BASARI", "DOLAR")]
    secili = []
    for s_, z in sb.groupby("sembol"):
        z = z[(z["islem"] >= 5) & (z["basari"] > 50) & (z["dolar"] > 0)]
        if not len(z):
            continue
        r_ = z.sort_values("dolar", ascending=False).iloc[0]
        secili.append((r_["dolar"], s_, r_["secenek"]))
    secili.sort(reverse=True)
    parca = []
    for _, s_, sec in secili:
        z = di[(di["sembol"] == s_) & (di["secenek"] == sec)]
        parca.append(z)
        o2 = ozet(z[z["donem"] == "SON_1_AY"])
        m.append("%-12s %-42s | %s || %15d %%%6.1f %+10.2f" % (s_, sec, satir(ozet(z)), o2["islem"], o2["basari"], o2["dolar"]))
    if parca:
        hep = pd.concat(parca)
        m.append("Hepsi birlikte (her sembol kendi mantigiyla), 10.000 $: " + hesap(hep))
        m.append("   SON 1 AY: " + satir(ozet(hep[hep["donem"] == "SON_1_AY"])))
    # mantikli / mantiksiz
    m += ["", c, "HANGI KURAL MANTIKLI, HANGISI MANTIKSIZ (butun semboller, 8'er secenegin toplami)", c]
    for ad, deg, f_ in (("ZAMAN DILIMI", ("1DK", "5DK"), lambda s_, v: ("TF=" + v) in s_),
                        ("GIRIS", ("KENAR", "ORTA"), lambda s_, v: ("GIRIS=" + v + " ") in s_),
                        ("STOP", ("SWING", "FVG_MUM"), lambda s_, v: ("STOP=" + v + " ") in s_),
                        ("TP", ("2R", "3R"), lambda s_, v: s_.endswith("TP=" + v))):
        par = []
        for v in deg:
            z = di[di["secenek"].map(lambda s_: f_(s_, v))]
            o = ozet(z)
            par.append((o["dolar"], v, o))
        par.sort(reverse=True)
        m.append("%-13s: daha iyi %-8s (%+.0f $, basari %%%.1f)  |  daha kotu %-8s (%+.0f $, basari %%%.1f)" % (
            ad, par[0][1], par[0][0], par[0][2]["basari"], par[1][1], par[1][0], par[1][2]["basari"]))
    m.append("EN MANTIKLI SECENEK : %s (%+.2f $)" % (sira[0][1], sira[0][0]))
    m.append("EN MANTIKSIZ SECENEK: %s (%+.2f $)" % (sira[-1][1], sira[-1][0]))
    m.append("Not: SON 1 AY sutunu kontrol icindir; secilen sembol son ayda da artidaysa daha guvenilir.")
    if yok:
        m += ["", "Verisi olmayan: " + ", ".join(yok)]
    m += ["", "BASARI = kar ile kapanan islem orani.  SURE = NY 16:00'da acik kapanan islem.",
          "1_islemler.csv: her islemin TR saati, tepki verilen seviye, MSS, FVG/IFVG, giris, stop, TP -> grafikte kontrol."]
    ms = "\n".join(m)
    print("\n" + ms)
    with open(os.path.join(klasor, "0_OZET.txt"), "w", encoding="utf-8") as fh:
        fh.write(ms + "\n")
    print("\nDosyalar: %s" % os.path.abspath(klasor))


if __name__ == "__main__":
    main()
