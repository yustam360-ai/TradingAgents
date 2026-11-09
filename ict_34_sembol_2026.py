# -*- coding: utf-8 -*-
"""
ICT 34 SEMBOL TESTI - 2026 basindan bugune, her sembol KENDI mantigiyla (3 aylik testte bulunan, hic degistirilmedi)
================================================================================================================
Python 3.8:   py -3.8 ict_34_sembol_2026.py
Baska baslangic:   py -3.8 ict_34_sembol_2026.py --bas 2026-03-01
TEK DOSYA: baska dosya gerekmez.

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
import shutil
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
BASLANGIC = 10000.0
EMIR_SURE = 60          # dk
KAPANIS_NY = 16 * 60    # NY 16:00
TARAMA_BIT_NY = 15 * 60  # NY 15:00'den sonra yeni kurulum yok
MAX_KIRILIM_MUM = 20

TFLER = [1, 3, 5, 15]
KIRILIMLAR = ["FITIL", "GOVDE", "DISP"]
LIKLER = ["SAAT", "GUN", "SWING", "ESIT", "HEPSI"]
LIK_BIT = {"SAAT": 1, "GUN": 2, "SWING": 4, "ESIT": 8, "HEPSI": 15}
GIRISLER = ["FVG_KENAR", "FVG_ORTA", "OB"]
STOPLAR = ["SUP_MAKAS", "SUP_01ATR", "SUP_02ATR", "FVG1", "FLUX"]
HEDEFLER = [2.0, 3.0]
ONAYLAR = ["YOK", "H1", "H4", "GUN_SUP", "GUN_KAP"]
PDLER = ["YOK", "VAR"]
NL = len(GIRISLER) * len(STOPLAR) * len(HEDEFLER)   # 30 etiket

# temel pencereler: (ad, sehir, bas dk, bit dk)  sehir: NY / LON / TYO  (o sehrin yerel saati)
TEMEL = [("SB_LON", "NY", 180, 240), ("SB_NYAM", "NY", 600, 660), ("SB_NYPM", "NY", 840, 900),
         ("KZ_ASYA", "NY", 1200, 1440), ("KZ_LON", "LON", 420, 600), ("KZ_NY", "NY", 420, 540),
         ("KZ_LONKAP", "LON", 900, 1020),
         ("AC_ASYA", "TYO", 540, 720), ("AC_LON", "LON", 480, 660), ("AC_NY", "NY", 480, 660)]
TI = {t[0]: i for i, t in enumerate(TEMEL)}
PENCERELER = [("SB", ["SB_LON", "SB_NYAM", "SB_NYPM"]), ("SB_LON", ["SB_LON"]), ("SB_NYAM", ["SB_NYAM"]),
              ("SB_NYPM", ["SB_NYPM"]), ("KZ_ASYA", ["KZ_ASYA"]), ("KZ_LON", ["KZ_LON"]), ("KZ_NY", ["KZ_NY"]),
              ("KZ_LONKAP", ["KZ_LONKAP"]), ("KZ_HEPSI", ["KZ_ASYA", "KZ_LON", "KZ_NY", "KZ_LONKAP"]),
              ("AC_ASYA", ["AC_ASYA"]), ("AC_LON", ["AC_LON"]), ("AC_NY", ["AC_NY"]),
              ("AC_HEPSI", ["AC_ASYA", "AC_LON", "AC_NY"])]
PEN_AD = [p[0] for p in PENCERELER]
PEN_TR = {"SB": "Silver Bullet (3 pencere)", "SB_LON": "Silver Bullet Londra", "SB_NYAM": "Silver Bullet NY sabah",
          "SB_NYPM": "Silver Bullet NY ogleden sonra", "KZ_ASYA": "Asya killzone", "KZ_LON": "Londra killzone",
          "KZ_NY": "New York killzone", "KZ_LONKAP": "Londra kapanis killzone",
          "KZ_HEPSI": "butun killzone'lar", "AC_ASYA": "Asya (Tokyo) acilisi ilk 3 saat",
          "AC_LON": "Londra acilisi ilk 3 saat", "AC_NY": "New York acilisi ilk 3 saat",
          "AC_HEPSI": "uc seansin acilis saatleri"}

SEVIYE_AD = ["ONCEKI_SAAT", "ONCEKI_GUN", "ONCEKI_3GUN", "ASYA_ARALIGI", "LONDRA_ARALIGI", "SWING", "ESIT"]
SEVIYE_TR = {"ONCEKI_SAAT": "onceki saatin", "ONCEKI_GUN": "onceki gunun", "ONCEKI_3GUN": "onceki 3 gunun",
             "ASYA_ARALIGI": "Asya araliginin", "LONDRA_ARALIGI": "Londra araliginin",
             "SWING": "15 dk swing", "ESIT": "esit"}
SEVIYE_BIT = [1, 2, 2, 2, 2, 4, 4 | 8]


# ----------------------------------------------------------------- saat (yaz / kis otomatik)
def _pazar(y, ay, kacinci):
    """ayin kacinci pazari (kacinci=-1: son pazar)"""
    if kacinci > 0:
        d = date(y, ay, 1)
        d += timedelta(days=(6 - d.weekday()) % 7)
        return d + timedelta(days=7 * (kacinci - 1))
    d = date(y, ay + 1, 1) - timedelta(days=1)
    return d - timedelta(days=(d.weekday() - 6) % 7)


def abd_yaz(d):
    return _pazar(d.year, 3, 2) <= d < _pazar(d.year, 11, 1)


def avrupa_yaz(d):
    return _pazar(d.year, 3, -1) <= d < _pazar(d.year, 10, -1)


def ny_utc(d):
    return -4 if abd_yaz(d) else -5


def sehir_utc(sehir, d):
    if sehir == "NY":
        return ny_utc(d)
    if sehir == "LON":
        return 1 if avrupa_yaz(d) else 0
    return 9


SUNUCU_NY = 7
SPREAD_DAHIL = True     # False: fiyat hareketinde spread yok, 6 $ kurali yok (stop payi olarak makas yine eklenir)


def sunucu_utc(d):
    return ny_utc(d) + SUNUCU_NY


def gun_tarih(g):
    return date(1970, 1, 1) + timedelta(days=int(g))


def yerel_to_sunucu(dk, sehir, d):
    return int((dk - sehir_utc(sehir, d) * 60 + sunucu_utc(d) * 60) % 1440)


def tr_saat(sunucu_dk_mutlak):
    """sunucu dakikasi (1970'ten) -> TR saati datetime"""
    g = int(sunucu_dk_mutlak // 1440)
    fark = 3 - sunucu_utc(gun_tarih(g))
    return datetime(1970, 1, 1) + timedelta(minutes=int(sunucu_dk_mutlak) + fark * 60)


def pencere_tr_metni(ad):
    """penceredeki temel pencerelerin TR saatleri (kis / yaz)"""
    kis, yaz = date(2026, 12, 1), date(2026, 7, 1)
    parca = []
    for t in dict(PENCERELER)[ad]:
        _, sehir, a, b = TEMEL[TI[t]]
        sat = []
        for d in (kis, yaz):
            fark = 3 - sunucu_utc(d)
            sa = (yerel_to_sunucu(a, sehir, d) + fark * 60) % 1440
            sb = (yerel_to_sunucu(b, sehir, d) + fark * 60) % 1440
            sat.append("%02d:%02d-%02d:%02d" % (sa // 60, sa % 60, sb // 60, sb % 60))
        parca.append("%s TR kis %s / yaz %s" % (t, sat[0], sat[1]))
    return "; ".join(parca)


def saat_dogrula(semboller):
    """MT5 sunucu saatini bilgisayar saatiyle karsilastirir.  donus: metin"""
    global SUNUCU_NY
    bugun = datetime.now(timezone.utc).date()
    beklenen = sunucu_utc(bugun)
    adaylar = ["BTCUSD", "ETHUSD", "EURUSD", "GBPUSD", "XAUUSD"] + list(semboller[:20])
    simdi = time.time()
    for s in adaylar:
        try:
            if not mt5.symbol_select(s, True):
                continue
            tk = mt5.symbol_info_tick(s)
        except Exception:
            tk = None
        if tk is None or not getattr(tk, "time", 0):
            continue
        fark_sa = (tk.time - simdi) / 3600.0
        en_yakin = round(fark_sa)
        if abs(fark_sa - en_yakin) * 60 > 3:            # tick taze degil (piyasa kapali olabilir)
            continue
        if en_yakin == beklenen:
            return ("MT5 sunucu saati UTC%+d (%s son fiyatina gore) = New York + %d -> DOGRULANDI. "
                    "Turkiye = sunucu %+d saat." % (en_yakin, s, SUNUCU_NY, 3 - en_yakin))
        SUNUCU_NY = int(en_yakin - ny_utc(bugun))
        return ("UYARI: MT5 sunucu saati UTC%+d bulundu, beklenen UTC%+d idi. Program kendini ayarladi: "
                "sunucu = New York %+d." % (en_yakin, beklenen, SUNUCU_NY))
    return ("MT5 saati kontrol edilemedi (piyasa kapali). Kural kullanildi: sunucu = New York + %d "
            "(kis UTC+2, yaz UTC+3)." % SUNUCU_NY)


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
    if K == 1:
        return T.copy(), O.copy(), H.copy(), L.copy(), C.copy()
    df = pd.DataFrame({"k": T // K, "o": O, "h": H, "l": L, "c": C}).groupby("k").agg(
        o=("o", "first"), h=("h", "max"), l=("l", "min"), c=("c", "last"))
    return (df.index.to_numpy(np.int64) * K,) + tuple(df[x].to_numpy(float) for x in ("o", "h", "l", "c"))


def atr_hesap(h, l, c, p):
    tr = np.r_[h[0] - l[0], np.maximum(h[1:] - l[1:], np.maximum(np.abs(h[1:] - c[:-1]), np.abs(l[1:] - c[:-1])))]
    return pd.Series(tr).rolling(p, min_periods=1).mean().to_numpy()


def yapi_trend(T, O, H, L, C, K):
    """K dk mumlarda yapi trendi (+1 / -1 / 0); donus: mum kapanis zamanlari, trend"""
    bt, bo, bh, bl, bc = mumlar(T, O, H, L, C, K)
    n = len(bt)
    tr = np.zeros(n, dtype=np.int8)
    ph = pl = None
    t = 0
    for i in range(n):
        p = i - 2                                       # 2 sol / 2 sag fraktal, i. mumda dogrulanir
        if p >= 2:
            if bh[p] > bh[p - 1] and bh[p] > bh[p - 2] and bh[p] > bh[p + 1] and bh[p] > bh[p + 2]:
                ph = bh[p]
            if bl[p] < bl[p - 1] and bl[p] < bl[p - 2] and bl[p] < bl[p + 1] and bl[p] < bl[p + 2]:
                pl = bl[p]
        if ph is not None and bc[i] > ph:
            t, ph = 1, None
        elif pl is not None and bc[i] < pl:
            t, pl = -1, None
        tr[i] = t
    return bt + K, tr


# ----------------------------------------------------------------- seviyeler
def seviyeler(gorunum, T, Hm, D, gunler, p, gh, Tg, H15):
    """satis gorunumunde (tepeler) bu gunun seviyeleri: (fiyat, bilinme, gecerlilik_sonu, seviye_kodu)"""
    ny0 = D + SUNUCU_NY * 60                            # bu islem gununun NY gece yarisi (sunucu dk)
    out = []
    g1, g2, g3 = gunler[p - 1], gunler[p - 2], gunler[p - 3]
    out.append((gh[g1], D, D + 1440, 1))
    out.append((max(gh[g1], gh[g2], gh[g3]), D, D + 1440, 2))

    def ust(a, b):
        i, j = np.searchsorted(T, a), np.searchsorted(T, b)
        return Hm[i:j].max() if j > i else None
    asy = ust(ny0 - 300, ny0)                            # NY 19:00-24:00 (onceki gece)
    if asy is not None:
        out.append((asy, ny0, D + 1440, 3))
    lon = ust(ny0 + 120, ny0 + 300)                      # NY 02:00-05:00
    if lon is not None:
        out.append((lon, ny0 + 300, D + 1440, 4))
    for h in range(-1, 23):                              # onceki saat (sadece bir sonraki saat gecerli)
        a = D + h * 60
        v = ust(a, a + 60)
        if v is not None:
            out.append((v, a + 60, a + 120, 0))
    # 15 dk swing tepeler (5 sol / 5 sag), son 2 gun
    bt15, bh15, atr15 = H15
    i0 = int(np.searchsorted(bt15, D - 2880))
    i1 = int(np.searchsorted(bt15, D + 1440))
    sw = []
    for k in range(max(i0, 5), min(i1, len(bh15) - 5)):
        v = bh15[k]
        if v >= bh15[k - 5:k].max() and v > bh15[k + 1:k + 6].max():
            sw.append((v, int(bt15[k + 5] + 15), atr15[k]))
    for n_, (v, bil, at) in enumerate(sw):
        esit = any(abs(v - w) <= 0.1 * at for w, b2, _ in sw[:n_] if b2 <= bil)
        out.append((v, bil, D + 1440, 6 if esit else 5))
    return out


def supurmeler(T, Hm, D, sev, bit):
    """her seviye icin ilk supurme dakikasi (bilinmeden once alinmamis olmali)"""
    ev = []
    for L, bil, son, kod in sev:
        if L != L or bil >= bit:
            continue
        a = int(np.searchsorted(T, bil))
        b = int(np.searchsorted(T, min(son, bit)))
        if b <= a:
            continue
        z = np.flatnonzero(Hm[a:b] > L)
        if z.size:
            ev.append((int(T[a + z[0]]), L, kod))
    return ev


# ----------------------------------------------------------------- kurulum + etiket
def kurulumlar(B, K, D, olaylar, bit):
    """satis gorunumu.  B: bt,bo,bh,bl,bc,atr14,atr5,disp,son_swl.  olaylar: [(dk, fiyat, kod)]"""
    bt, bo, bh, bl, bc, atr, atr5, disp, sonswl = B
    n = len(bt)
    bar = {}
    for dk, L, kod in olaylar:
        i = int(np.searchsorted(bt, dk, side="right")) - 1
        if i < 1 or bt[i] < D:
            continue
        bar.setdefault(i, []).append((L, kod))
    out = []
    for i in sorted(bar):
        f = sonswl[i]
        if f < 1:
            continue
        ref = bl[f]
        j1 = min(i + 1 + MAX_KIRILIM_MUM, n)
        J = np.arange(i + 1, j1)
        J = J[bt[J] + K <= bit]
        if not J.size:
            continue
        kosul = {"FITIL": bl[J] < ref, "GOVDE": bc[J] < ref}
        kosul["DISP"] = kosul["GOVDE"] & disp[J]
        lik_bit, isim = 0, []
        for L, kod in bar[i]:
            lik_bit |= SEVIYE_BIT[kod]
            isim.append(kod)
        sup_fiyat = max(L for L, _ in bar[i])
        goruldu = {}
        for kr in KIRILIMLAR:
            z = np.flatnonzero(kosul[kr])
            if not z.size:
                continue
            jk = int(J[z[0]])
            dec = jk + 1
            if dec >= n or bt[dec] + K > bit:
                continue
            if jk in goruldu:                            # ayni kirilim mumu: ayni kurulum, sadece etiket
                out[goruldu[jk]]["kir"].append(kr)
                continue
            shi = i + int(np.argmax(bh[i:jk + 1]))
            sh = bh[i:dec + 1].max()
            Td = int(bt[dec] + K)
            en_iyi = None
            for a in range(shi, dec - 1):
                c = a + 2
                if bl[a] > bh[c]:
                    ust_, alt = bl[a], bh[c]
                    if bc[dec] >= alt:
                        continue
                    if c + 1 <= dec and bh[c + 1:dec + 1].max() >= alt:
                        continue
                    if en_iyi is None or alt < en_iyi[1]:
                        en_iyi = (ust_, alt, a)
            if en_iyi is None:
                continue
            ust_, alt, a = en_iyi
            ob = -1
            for k in range(jk, shi - 1, -1):
                if bc[k] > bo[k]:
                    ob = k
                    break
            if ob < 0:
                ob = shi
            out.append(dict(Td=Td, i=i, shi=shi, sh=sh, ref=ref, fiyat=bc[dec], atr=atr[dec],
                            giris=[alt, (ust_ + alt) / 2.0, bl[ob]],
                            stop_ham=[sh, sh + 0.1 * atr[dec], sh + 0.2 * atr[dec], bh[a],
                                      bh[max(0, dec - 9):dec + 1].max() + 5.5 * atr5[dec]],
                            makas_ek=[True, False, False, True, False],
                            lik=lik_bit, isim=isim, sup=sup_fiyat, sup_dk=int(bt[i]), kir=[kr]))
            goruldu[jk] = len(out) - 1
    return out


def etiketle(kur, Tm, F, X, Y, Cx, SP, z_bit, vpl, bilgi):
    """30 etiket: R, kod, risk $, dolum dk, cikis dk.
    kod: 9 gecersiz, 7 en kucuk lot 30 $ ustu, 6 spread 6 $ ustu, 8 dolmadi/iptal, 1 TP, -1 STOP, 0 SURE"""
    R = np.full(NL, np.nan, dtype=np.float32)
    kod = np.full(NL, 9, dtype=np.int8)
    rk = np.zeros(NL, dtype=np.float32)
    fd = np.full(NL, -1, dtype=np.int16)
    cd = np.full(NL, -1, dtype=np.int16)
    a0 = int(np.searchsorted(Tm, kur["Td"]))
    z1 = int(np.searchsorted(Tm, z_bit))
    c1 = min(int(np.searchsorted(Tm, kur["Td"] + EMIR_SURE)), z1)
    if a0 >= c1:
        return R, kod, rk, fd, cd
    sp = SP[a0]
    adim = bilgi.volume_step if bilgi.volume_step > 0 else 0.01
    vmax = bilgi.volume_max if bilgi.volume_max > 0 else 1e9
    for gi, E in enumerate(kur["giris"]):
        if not (E > kur["fiyat"]):
            continue
        fz = np.flatnonzero(F[a0:c1] >= E)
        f = a0 + int(fz[0]) if fz.size else -1
        for si in range(len(STOPLAR)):
            S = kur["stop_ham"][si] + (sp if kur["makas_ek"][si] else 0.0)
            r = S - E
            if not (r > 0):
                continue
            rpl = r * vpl
            lot = np.floor(RISK / rpl / adim + 1e-9) * adim
            if lot < bilgi.volume_min:
                lot = bilgi.volume_min
            lot = min(lot, vmax)
            zarar = lot * rpl
            maliyet = sp * lot * vpl if SPREAD_DAHIL else 0.0
            for hi, hk in enumerate(HEDEFLER):
                k = (gi * len(STOPLAR) + si) * len(HEDEFLER) + hi
                rk[k] = zarar
                if zarar > EN_FAZLA + 1e-9:
                    kod[k] = 7
                    continue
                if maliyet > MAKAS_SINIR + 1e-9:
                    kod[k] = 6
                    continue
                TP = E - hk * r
                if f < 0:
                    kod[k] = 8
                    continue
                tz = np.flatnonzero(Y[a0:f + 1] <= TP)
                if tz.size:
                    kod[k] = 8
                    continue
                st = np.flatnonzero(X[f:z1] >= S)
                tpb = Y[f:z1] <= TP
                tpb[0] = False
                hz = np.flatnonzero(tpb)
                s0 = int(st[0]) if st.size else None
                h0 = int(hz[0]) if hz.size else None
                fd[k] = int(Tm[f] - kur["Td"])
                if s0 is not None and (h0 is None or s0 <= h0):
                    R[k], kod[k], e = -1.0, -1, f + s0
                elif h0 is not None:
                    R[k], kod[k], e = hk, 1, f + h0
                else:
                    e = z1 - 1
                    R[k], kod[k] = (E - Cx[e]) / r, 0
                cd[k] = int(min(Tm[e] - kur["Td"], 32000))
    return R, kod, rk, fd, cd


def sembol_isle(s, m1, bilgi, vpl, bas_gun):
    T = m1["time"].to_numpy(np.int64) // 60
    O, H, L, C = [m1[k].to_numpy(float) for k in ("open", "high", "low", "close")]
    SP = m1["spread"].to_numpy(float) * float(bilgi.point)
    gun = T // 1440
    gunler = list(np.unique(gun))
    gh, gl, gc = {}, {}, {}
    for g in gunler:
        a, b = np.searchsorted(T, g * 1440), np.searchsorted(T, g * 1440 + 1440)
        gh[g], gl[g], gc[g] = H[a:b].max(), L[a:b].min(), C[b - 1]
    h1_t, h1_tr = yapi_trend(T, O, H, L, C, 60)
    h4_t, h4_tr = yapi_trend(T, O, H, L, C, 240)
    gorunum = {}
    for yon in (-1, 1):
        SPx = SP if SPREAD_DAHIL else 0.0 * SP
        if yon < 0:
            Hm, Lm, Cm, Om = H, L, C, O
            F, X, Y, Cx = H, H + SPx, L + SPx, C + SPx
        else:
            Hm, Lm, Cm, Om = -L, -H, -C, -O
            F, X, Y, Cx = -(L + SPx), -L, -H, -C
        tf = {}
        for K in TFLER:
            bt, bo, bh, bl, bc = mumlar(T, Om, Hm, Lm, Cm, K)
            atr = atr_hesap(bh, bl, bc, 14)
            atr5 = atr_hesap(bh, bl, bc, 5)
            govde = bo - bc
            ort = pd.Series(np.abs(govde)).shift(1).rolling(5, min_periods=1).mean().to_numpy()
            disp = (govde > ort) & (govde >= 0.6 * (bh - bl))
            swl = np.zeros(len(bt), dtype=bool)
            if len(bt) > 2:
                swl[1:-1] = (bl[1:-1] < bl[:-2]) & (bl[1:-1] < bl[2:])
            # son_swl[k] = k'den once dogrulanmis son swing dip (f+1 <= k)
            idx = np.where(swl, np.arange(len(bt)), -1)
            sonswl = np.r_[-1, np.maximum.accumulate(idx)[:-1]]   # sonswl[k]: f <= k-1 (f+1 <= k ile dogrulanmis)
            tf[K] = (bt, bo, bh, bl, bc, atr, atr5, disp, sonswl)
        b15 = tf[15]
        gorunum[yon] = dict(Hm=Hm, F=F, X=X, Y=Y, Cx=Cx, tf=tf, H15=(b15[0], b15[2], b15[5]))
    satir, RR, KK, RK, FD, CD = [], [], [], [], [], []
    for p, g in enumerate(gunler):
        if g < bas_gun or p < 4:
            continue
        D = int(g * 1440)
        d = gun_tarih(g)
        g1, g2, g3, g4 = gunler[p - 1], gunler[p - 2], gunler[p - 3], gunler[p - 4]
        eski_dip = min(gl[g2], gl[g3], gl[g4]); eski_tepe = max(gh[g2], gh[g3], gh[g4])
        sa = gl[g1] < eski_dip and gc[g1] > eski_dip
        ss = gh[g1] > eski_tepe and gc[g1] < eski_tepe
        b_sup = 1 if (sa and not ss) else (-1 if (ss and not sa) else 0)
        b_kap = 1 if gc[g1] > gh[g2] else (-1 if gc[g1] < gl[g2] else 0)
        orta = (gh[g1] + gl[g1]) / 2.0
        pen = []
        for ad, sehir, a, b in TEMEL:
            sa_ = yerel_to_sunucu(a, sehir, d)
            sb_ = sa_ + (b - a)
            pen.append((D + sa_, D + sb_))
        ny0 = D + SUNUCU_NY * 60                         # bu islem gununun NY gece yarisi (sunucu 00:00 = NY 17:00)
        bit = ny0 + TARAMA_BIT_NY
        z_bit = ny0 + KAPANIS_NY
        for yon in (-1, 1):
            G = gorunum[yon]
            ghv = gh if yon < 0 else {k: -v for k, v in gl.items()}
            sev = seviyeler(yon, T, G["Hm"], D, gunler, p, ghv, None, G["H15"])
            olay = supurmeler(T, G["Hm"], D, sev, bit)
            if not olay:
                continue
            mid = orta if yon < 0 else -orta
            for K in TFLER:
                for kur in kurulumlar(G["tf"][K], K, D, olay, bit):
                    td = kur["Td"]
                    uyelik = 0
                    for ti, (pa, pb) in enumerate(pen):
                        if pa <= td < pb:
                            uyelik |= 1 << ti
                    if not uyelik:
                        continue
                    R, kd, rk, fd, cd = etiketle(kur, T, G["F"], G["X"], G["Y"], G["Cx"], SP, z_bit, vpl, bilgi)
                    if not (kd != 9).any():
                        continue
                    i1 = int(np.searchsorted(h1_t, td, side="right")) - 1
                    i4 = int(np.searchsorted(h4_t, td, side="right")) - 1
                    t1 = h1_tr[i1] if i1 >= 0 else 0
                    t4 = h4_tr[i4] if i4 >= 0 else 0
                    kb = 0
                    for kr in kur["kir"]:
                        kb |= 1 << KIRILIMLAR.index(kr)
                    sg = 1 if yon < 0 else -1                # gorunum fiyati -> gercek fiyat
                    isim_bit = 0
                    for c in kur["isim"]:
                        isim_bit |= 1 << c
                    gir = kur["giris"]
                    st = [kur["stop_ham"][q] + (SP[min(int(np.searchsorted(T, td)), len(SP) - 1)]
                                                 if kur["makas_ek"][q] else 0.0) for q in range(len(STOPLAR))]
                    satir.append((g, td, K, kb, kur["lik"], uyelik, yon,
                                  t1 == yon, t4 == yon, b_sup == yon, b_kap == yon,
                                  gir[0] > mid, gir[1] > mid, gir[2] > mid,
                                  isim_bit, kur["sup_dk"], sg * kur["sup"],
                                  sg * gir[0], sg * gir[1], sg * gir[2],
                                  sg * st[0], sg * st[1], sg * st[2], sg * st[3], sg * st[4]))
                    RR.append(R); KK.append(kd); RK.append(rk); FD.append(fd); CD.append(cd)
    if not satir:
        return None
    kol = ["gun", "Td", "tf", "kir", "lik", "uye", "yon", "o_h1", "o_h4", "o_sup", "o_kap", "pd0", "pd1", "pd2",
           "isim", "sup_dk", "sup", "e0", "e1", "e2", "s0", "s1", "s2", "s3", "s4"]
    df = pd.DataFrame(satir, columns=kol)
    RR, KK, RK, FD, CD = np.vstack(RR), np.vstack(KK), np.vstack(RK), np.vstack(FD), np.vstack(CD)
    sira = np.lexsort((df["Td"].to_numpy(), df["gun"].to_numpy()))
    df = df.iloc[sira].reset_index(drop=True)
    return df, RR[sira], KK[sira], RK[sira], FD[sira], CD[sira]


# ----------------------------------------------------------------- birlesim toplama
def maske_listesi():
    """(tf, kir, lik, pen, onay, pd) her birlesim maskesi"""
    out = []
    for K in TFLER:
        for kr in KIRILIMLAR:
            for lk in LIKLER:
                for pn in PEN_AD:
                    for on in ONAYLAR:
                        for pdv in PDLER:
                            out.append((K, kr, lk, pn, on, pdv))
    return out


MASKELER = maske_listesi()
NM = len(MASKELER)
ETIKET = [(g, s, h) for g in GIRISLER for s in STOPLAR for h in HEDEFLER]
GIR_IDX = np.array([GIRISLER.index(g) for g, _, _ in ETIKET])


def ilk_alinan(grp, M):
    """grp: satir grup numarasi (bitisik), M: (n, NL) gecerli emir -> her grupta ilk gecerli emir"""
    cs = np.cumsum(M, axis=0, dtype=np.int32)
    bas = np.r_[True, grp[1:] != grp[:-1]]
    gi = np.cumsum(bas) - 1
    taban = (cs - M)[bas]
    return M & ((cs - taban[gi]) == 1)


class Veri(object):
    def __init__(self, df, RR, KK, RK, FD, CD, yari_gun):
        self.df, self.RR, self.KK, self.RK, self.FD, self.CD = df, RR, KK, RK, FD, CD
        self.gecerli = (KK != 9) & (KK != 7) & (KK != 6)
        self.alindi = (KK == 1) | (KK == -1) | (KK == 0)
        self.tf = df["tf"].to_numpy()
        self.kir = df["kir"].to_numpy()
        self.lik = df["lik"].to_numpy()
        self.uye = df["uye"].to_numpy()
        self.gun = df["gun"].to_numpy()
        self.onay = {"YOK": np.ones(len(df), bool), "H1": df["o_h1"].to_numpy(bool), "H4": df["o_h4"].to_numpy(bool),
                     "GUN_SUP": df["o_sup"].to_numpy(bool), "GUN_KAP": df["o_kap"].to_numpy(bool)}
        pdm = np.vstack([df["pd0"].to_numpy(bool), df["pd1"].to_numpy(bool), df["pd2"].to_numpy(bool)]).T
        self.pdcol = pdm[:, GIR_IDX]
        self.ikinci = self.gun >= yari_gun
        self.temel_id = {}
        for pn, tl in PENCERELER:
            tid = np.full(len(df), -1, dtype=np.int16)
            for t in reversed(tl):
                tid = np.where((self.uye >> TI[t]) & 1 == 1, TI[t], tid)
            self.temel_id[pn] = tid

    def tara(self, cb):
        """her maske icin cb(mi, idx, alinan(n,NL))"""
        mi = 0
        for K in TFLER:
            m_tf = self.tf == K
            for kr in KIRILIMLAR:
                m_k = m_tf & ((self.kir >> KIRILIMLAR.index(kr)) & 1 == 1)
                for lk in LIKLER:
                    m_l = m_k & ((self.lik & LIK_BIT[lk]) != 0)
                    for pn in PEN_AD:
                        tid = self.temel_id[pn]
                        m_p = m_l & (tid >= 0)
                        for on in ONAYLAR:
                            m_o = m_p & self.onay[on]
                            idx = np.flatnonzero(m_o)
                            for pdv in PDLER:
                                if idx.size:
                                    M = self.gecerli[idx]
                                    if pdv == "VAR":
                                        M = M & self.pdcol[idx]
                                    grp = self.gun[idx].astype(np.int64) * 16 + tid[idx]
                                    al = ilk_alinan(grp, M) & self.alindi[idx]
                                    cb(mi, idx, al)
                                mi += 1


class Toplam(object):
    ALAN = ["n", "w", "tp", "st", "su", "R", "dolar", "R1", "R2"]

    def __init__(self):
        for a in self.ALAN:
            setattr(self, a, np.zeros((NM, NL)))

    def ekle(self, V):
        RR0 = np.nan_to_num(V.RR.astype(np.float64))
        D0 = RR0 * V.RK

        def cb(mi, idx, al):
            if not al.any():
                return
            r = np.where(al, RR0[idx], 0.0)
            kd = V.KK[idx]
            self.n[mi] += al.sum(0)
            self.w[mi] += (al & (r > 0)).sum(0)
            self.tp[mi] += (al & (kd == 1)).sum(0)
            self.st[mi] += (al & (kd == -1)).sum(0)
            self.su[mi] += (al & (kd == 0)).sum(0)
            self.R[mi] += r.sum(0)
            self.dolar[mi] += np.where(al, D0[idx], 0.0).sum(0)
            ik = V.ikinci[idx][:, None]
            self.R1[mi] += np.where(~ik, r, 0.0).sum(0)
            self.R2[mi] += np.where(ik, r, 0.0).sum(0)
        V.tara(cb)


def islemler(V, s, secim):
    """secim: {(mi, k): etiket}  -> islem satirlari"""
    out = []
    lazim = {}
    for (mi, k), et in secim.items():
        lazim.setdefault(mi, []).append((k, et))

    def cb(mi, idx, al):
        if mi not in lazim:
            return
        for k, et in lazim[mi]:
            for j in idx[al[:, k]]:
                out.append((et, j, k))
    V.tara(cb)
    rows = []
    df = V.df
    for et, j, k in out:
        r = df.iloc[j]
        gi, si, hi = k // (len(STOPLAR) * len(HEDEFLER)), (k // len(HEDEFLER)) % len(STOPLAR), k % len(HEDEFLER)
        E, S = r["e%d" % gi], r["s%d" % si]
        yon = int(r["yon"])
        TP = E + yon * HEDEFLER[hi] * abs(S - E)
        R = float(V.RR[j, k])
        kd = int(V.KK[j, k])
        isim = [SEVIYE_AD[c] for c in range(len(SEVIYE_AD)) if (int(r["isim"]) >> c) & 1]
        rows.append(dict(birlesim=et, sembol=s, gun=int(r["gun"]),
                         karar_tr=tr_saat(r["Td"]).strftime("%Y-%m-%d %H:%M"),
                         supurme_tr=tr_saat(r["sup_dk"]).strftime("%Y-%m-%d %H:%M"),
                         dolum_tr=tr_saat(r["Td"] + int(V.FD[j, k])).strftime("%Y-%m-%d %H:%M"),
                         cikis_tr=tr_saat(r["Td"] + int(V.CD[j, k])).strftime("%Y-%m-%d %H:%M"),
                         cikis_dk=int(r["Td"]) + int(V.CD[j, k]),
                         yon="AL" if yon > 0 else "SAT", tf="%ddk" % int(r["tf"]),
                         supurulen=("dip " if yon > 0 else "tepe ") + "+".join(isim),
                         supurulen_fiyat=round(float(r["sup"]), 6),
                         giris=round(float(E), 6), stop=round(float(S), 6), tp=round(float(TP), 6),
                         sonuc={1: "TP", -1: "STOP", 0: "SURE"}[kd], R=round(R, 3),
                         risk_dolar=round(float(V.RK[j, k]), 2), dolar=round(R * float(V.RK[j, k]), 2)))
    return rows


# ----------------------------------------------------------------- rapor yardimcilari
def birlesim_ad(mi, k):
    K, kr, lk, pn, on, pdv = MASKELER[mi]
    g, st, h = ETIKET[k]
    return "TF=%ddk | LIK=%s | KIRILIM=%s | PENCERE=%s | ONAY=%s | PD=%s | GIRIS=%s | STOP=%s | HEDEF=%.0fR" % (
        K, lk, kr, pn, on, pdv, g, st, h)


def aciklama(mi, k, girinti="     "):
    K, kr, lk, pn, on, pdv = MASKELER[mi]
    g, st, h = ETIKET[k]
    lik_m = {"SAAT": "bir onceki saatin tepesi (satis) / dibi (alis)",
             "GUN": "onceki gun, onceki 3 gun, Asya araligi (NY 19-24) ya da Londra araligi (NY 02-05) tepesi/dibi",
             "SWING": "15 dk grafikteki son 2 gunun alinmamis swing tepesi/dibi",
             "ESIT": "esit tepeler / esit dipler (aralarinda 0.1 ATR'den az fark)",
             "HEPSI": "herhangi bir likidite (onceki saat, gun, Asya/Londra araligi, swing, esit tepe/dip)"}[lk]
    kir_m = {"FITIL": "son swing dibin altina fitil atmasi yeter",
             "GOVDE": "mum son swing dibin altinda KAPANMALI",
             "DISP": "guclu (displacement) mum son swing dibin altinda kapanmali"}[kr]
    gir_m = {"FVG_KENAR": "FVG'nin yakin kenarina limit emir (satista alt kenar, alista ust kenar)",
             "FVG_ORTA": "FVG'nin ortasina limit emir",
             "OB": "order block'a limit emir (satista kirilimdan onceki son yukari mumun dibi, alista tersi)"}[g]
    st_m = {"SUP_MAKAS": "supurmeyi yapan tepenin makas kadar ustu (alista dibin makas kadar alti)",
            "SUP_01ATR": "supurmeyi yapan tepenin 0.1 ATR ustu (alista dibin 0.1 ATR alti)",
            "SUP_02ATR": "supurmeyi yapan tepenin 0.2 ATR ustu (alista dibin 0.2 ATR alti)",
            "FVG1": "FVG'nin ilk mumunun tepesi + makas (alista dibi - makas)",
            "FLUX": "son 10 mumun tepesi + 5.5 x ATR(5) (Flux indikator kurali)"}[st]
    on_m = {"YOK": "yok (iki yonde de islem)",
            "H1": "1 saatlikte son yapi kirilimi islem yonunde olmali",
            "H4": "4 saatlikte son yapi kirilimi islem yonunde olmali",
            "GUN_SUP": "dun eski 3 gunluk dip supurulup ustunde kapandiysa sadece alis, tepe supurulup altinda kapandiysa sadece satis",
            "GUN_KAP": "dun onceki gunun tepesi ustunde kapandiysa sadece alis, dibi altinda kapandiysa sadece satis"}[on]
    pd_m = {"YOK": "yok", "VAR": "satis girisi onceki gun araliginin ortasinin ustunde (premium), alis altinda (discount)"}[pdv]
    sat = ["Zaman      : %s  (%s)" % (PEN_TR[pn], pencere_tr_metni(pn)),
           "Grafik     : %d dakikalik mum" % K,
           "Ust onay   : %s" % on_m,
           "Supurulen  : %s" % lik_m,
           "Kirilim    : supurmeden sonra en fazla 20 mum icinde %s" % kir_m,
           "Giris      : %s, emir 60 dk gecerli" % gir_m,
           "Stop       : %s" % st_m,
           "TP         : %.0fR (stop mesafesinin %.0f kati); acik islem NY 16:00'da (TR kis 00:00 / yaz 23:00) kapanir" % (h, h),
           "PD         : %s" % pd_m]
    return "\n".join(girinti + x for x in sat)


def hesap_sim(isl):
    """10.000 $ hesap: kapanis sirasina gore"""
    if not isl:
        return None
    d = pd.DataFrame(isl).sort_values("cikis_dk")
    bak = BASLANGIC + d["dolar"].cumsum().to_numpy()
    tepe = np.maximum.accumulate(np.r_[BASLANGIC, bak])[1:]
    gunluk = d.groupby(d["cikis_dk"] // 1440)["dolar"].sum()
    hedef = np.flatnonzero(bak >= BASLANGIC + 1000)
    return dict(bitis=bak[-1], net=bak[-1] - BASLANGIC, en_dusuk=min(BASLANGIC, bak.min()),
                dusus=(bak - tepe).min(), en_kotu_gun=gunluk.min(), en_iyi_gun=gunluk.max(), gun=len(gunluk),
                hedef_tarih=(d.iloc[hedef[0]]["cikis_tr"][:10] if hedef.size else "-"),
                gunluk_ihlal=int((gunluk < -300).sum()), max_ihlal=bool(bak.min() < BASLANGIC - 1000))


def sim_metni(sm):
    if sm is None:
        return "   (islem yok)"
    return ("   10.000 $ -> %.2f $  (net %+.2f $) | en kotu gun %+.2f $ | en iyi gun %+.2f $ | en buyuk dusus %+.2f $ | "
            "en dusuk bakiye %.2f $\n   FTMO: 1.000 $ hedefe ulasma %s | gunluk 300 $ limiti asilan gun %d | "
            "1.000 $ max zarar %s" % (sm["bitis"], sm["net"], sm["en_kotu_gun"], sm["en_iyi_gun"], sm["dusus"],
                                      sm["en_dusuk"], sm["hedef_tarih"], sm["gunluk_ihlal"],
                                      "ASILDI" if sm["max_ihlal"] else "asilmadi"))


SISTEMLER = [
    ("FLUX SILVER BULLET (indikatorun kendi kurali; TP 0.99R yerine 2R/3R)",
     dict(tf=[1, 3, 5], lik=["SAAT"], kir=["FITIL"], pen=["SB"], onay=["YOK"], pd=["YOK"], giris=["FVG_KENAR"], stop=["FLUX"])),
    ("LUXALGO SILVER BULLET (SB saatleri, trend yonunde FVG; indikatorde stop yok -> stop tepe ustu)",
     dict(tf=[1, 3, 5, 15], pen=["SB", "SB_LON", "SB_NYAM", "SB_NYPM"], onay=["H1", "H4"], giris=["FVG_KENAR", "FVG_ORTA"],
          stop=["SUP_MAKAS", "SUP_01ATR", "SUP_02ATR"])),
    ("ICT CONCEPTS (LuxAlgo: displacement MSS, killzone, OB / FVG)",
     dict(kir=["DISP"], pen=["KZ_ASYA", "KZ_LON", "KZ_NY", "KZ_LONKAP", "KZ_HEPSI"], onay=["YOK"])),
    ("SMC CONCEPTS (LuxAlgo: ust zaman yapisi + premium/discount + swing / esit tepe-dip)",
     dict(kir=["GOVDE"], onay=["H1", "H4"], pd=["VAR"], lik=["SWING", "ESIT"])),
    ("BENIM ONERIM (gun likiditesi supurme -> govde/displacement MSS -> FVG/OB, H1/H4 onay, killzone/SB, stop tepe+pay)",
     dict(lik=["GUN"], kir=["GOVDE", "DISP"], onay=["H1", "H4"],
          pen=["SB", "SB_LON", "SB_NYAM", "KZ_LON", "KZ_NY", "KZ_HEPSI"], stop=["SUP_MAKAS", "SUP_01ATR", "SUP_02ATR"])),
    ("BUTUN BIRLESIMLER ICINDE EN IYI", dict()),
]


def secim_maskesi(kosul):
    mm = np.ones(NM, bool)
    for mi, (K, kr, lk, pn, on, pdv) in enumerate(MASKELER):
        for ad, v in (("tf", K), ("kir", kr), ("lik", lk), ("pen", pn), ("onay", on), ("pd", pdv)):
            if ad in kosul and v not in kosul[ad]:
                mm[mi] = False
    ek = np.ones(NL, bool)
    for k, (g, st, h) in enumerate(ETIKET):
        if "giris" in kosul and g not in kosul["giris"]:
            ek[k] = False
        if "stop" in kosul and st not in kosul["stop"]:
            ek[k] = False
    return mm[:, None] & ek[None, :]


def main_3ay():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ay", type=float, default=3.0)
    ap.add_argument("--min-islem", type=int, default=60, help="genel siralama icin en az islem")
    ap.add_argument("--min-islem-sembol", type=int, default=15, help="sembolun kendi birlesimi icin en az islem")
    ap.add_argument("--sembol", default="", help="sadece bu semboller (virgulle); bos = butun semboller")
    ap.add_argument("--cikti", default="")
    args = ap.parse_args()
    if mt5 is None:
        sys.exit("MetaTrader5 modulu yok:  py -3.8 -m pip install MetaTrader5")
    if not mt5.initialize():
        sys.exit("MT5 baglantisi kurulamadi: %s" % (mt5.last_error(),))
    hs = mt5.account_info()
    print("MT5 bagli: %s  (sadece gecmis veri, islem acilmiyor)" % (hs.server if hs else "?"))
    semboller = ([x.strip() for x in args.sembol.split(",") if x.strip()] if args.sembol
                 else [x.name for x in (mt5.symbols_get() or [])])
    saat_notu = saat_dogrula(semboller)
    print(saat_notu)
    simdi = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=sunucu_utc(datetime.now(timezone.utc).date()))
    tbas = simdi - timedelta(days=30.4 * args.ay)
    bas_gun = int((tbas - datetime(1970, 1, 1)).total_seconds() // 86400)
    bit_gun = int((simdi - datetime(1970, 1, 1)).total_seconds() // 86400)
    yari_gun = (bas_gun + bit_gun) / 2.0
    klasor = args.cikti or ("ict_spread_%s" % datetime.now().strftime("%Y%m%d_%H%M"))
    onbellek = os.path.join(klasor, "_gecici")
    for k in (klasor, onbellek):
        if not os.path.isdir(k):
            os.makedirs(k)
    yaz = dict(sep=";", decimal=",", index=False, encoding="utf-8-sig")
    print("Sembol: %d | %s -> bugun | %d birlesim | spread dahil, 6 $ kurali, risk 15 $"
          % (len(semboller), tbas.strftime("%Y-%m-%d"), NM * NL))
    TOP = Toplam()
    sem_en = []           # (sembol, mi, k, n, w, R, dolar, tp, st, su)  en cok kazandiran
    sem_50 = {}           # sembol -> (mi, k) basari > %50 olanlarin en cok kazandirani
    isl_50 = []
    yok, t0 = [], time.time()
    for n_, s in enumerate(semboller, 1):
        if not mt5.symbol_select(s, True):
            yok.append(s); print("[%d/%d] %s : sembol yok" % (n_, len(semboller), s)); continue
        bilgi = mt5.symbol_info(s)
        vpl = deger_lot(s, bilgi) if bilgi is not None else None
        m1 = cek(s, mt5.TIMEFRAME_M1, tbas - timedelta(days=10), simdi + timedelta(days=1), 15)
        if bilgi is None or not vpl or m1 is None or len(m1) < 5000:
            yok.append(s); print("[%d/%d] %s : veri yok" % (n_, len(semboller), s)); continue
        sonuc = sembol_isle(s, m1, bilgi, vpl, bas_gun)
        if sonuc is None:
            print("[%d/%d] %s : kurulum yok" % (n_, len(semboller), s)); continue
        V = Veri(*(sonuc + (yari_gun,)))
        ST = Toplam()
        ST.ekle(V)
        for a in Toplam.ALAN:
            getattr(TOP, a).__iadd__(getattr(ST, a))
        ok = ST.n >= args.min_islem_sembol
        if ok.any():
            Rm = np.where(ok, ST.R, -np.inf)
            mi, k = np.unravel_index(int(np.argmax(Rm)), Rm.shape)
            sem_en.append((s, mi, k, ST.n[mi, k], ST.w[mi, k], ST.R[mi, k], ST.dolar[mi, k], ST.tp[mi, k],
                           ST.st[mi, k], ST.su[mi, k]))
            ok50 = ok & (ST.w > 0.5 * ST.n)
            if ok50.any():
                R5 = np.where(ok50, ST.R, -np.inf)
                m5, k5 = np.unravel_index(int(np.argmax(R5)), R5.shape)
                sem_50[s] = (m5, k5, ST.n[m5, k5], ST.w[m5, k5], ST.R[m5, k5], ST.dolar[m5, k5],
                             ST.tp[m5, k5], ST.st[m5, k5], ST.su[m5, k5], ST.R1[m5, k5], ST.R2[m5, k5])
                isl_50 += islemler(V, s, {(m5, k5): birlesim_ad(m5, k5)})
        np.savez_compressed(os.path.join(onbellek, "%d.npz" % n_), RR=V.RR, KK=V.KK, RK=V.RK, FD=V.FD, CD=V.CD,
                            **{c: V.df[c].to_numpy() for c in V.df.columns})
        print("[%d/%d] %s : %d kurulum  (%.0f sn)" % (n_, len(semboller), s, len(V.df), time.time() - t0))
    mt5.shutdown()
    if TOP.n.sum() == 0:
        sys.exit("Hic islem yok.")

    # ------------------------------------------------ en iyiler
    basari = np.where(TOP.n > 0, 100.0 * TOP.w / np.maximum(TOP.n, 1), 0.0)
    yeterli = TOP.n >= args.min_islem
    secilen = {}
    sistem_sonuc = []
    for ad, kosul in SISTEMLER:
        sm = secim_maskesi(kosul) & yeterli
        if not sm.any():
            sistem_sonuc.append((ad, None)); continue
        Rm = np.where(sm, TOP.R, -np.inf)
        mi, k = np.unravel_index(int(np.argmax(Rm)), Rm.shape)
        Bm = np.where(sm, basari + 1e-6 * TOP.R, -np.inf)
        mb, kb = np.unravel_index(int(np.argmax(Bm)), Bm.shape)
        sistem_sonuc.append((ad, (mi, k, mb, kb)))
        secilen[(mi, k)] = birlesim_ad(mi, k)
    # tum islemler (secilen birlesimler) onbellekten
    tum_isl = []
    dosyalar = sorted(os.listdir(onbellek), key=lambda x: int(x.split(".")[0]))
    for fn in dosyalar:
        z = np.load(os.path.join(onbellek, fn), allow_pickle=False)
        s = semboller[int(fn.split(".")[0]) - 1]
        df = pd.DataFrame({c: z[c] for c in z.files if c not in ("RR", "KK", "RK", "FD", "CD")})
        V = Veri(df, z["RR"], z["KK"], z["RK"], z["FD"], z["CD"], yari_gun)
        tum_isl += islemler(V, s, secilen)
    shutil.rmtree(onbellek, ignore_errors=True)
    isl_df = pd.DataFrame(tum_isl)

    # ------------------------------------------------ dosyalar
    satirlar = []
    for mi in range(NM):
        for k in range(NL):
            if TOP.n[mi, k] > 0:
                satirlar.append((birlesim_ad(mi, k), int(TOP.n[mi, k]), int(TOP.tp[mi, k]), int(TOP.st[mi, k]),
                                 int(TOP.su[mi, k]), round(basari[mi, k], 1), round(TOP.R[mi, k], 1),
                                 round(TOP.dolar[mi, k], 2), round(TOP.R1[mi, k], 1), round(TOP.R2[mi, k], 1)))
    ds = pd.DataFrame(satirlar, columns=["birlesim", "islem", "TP", "STOP", "SURE", "basari", "net_R", "dolar",
                                         "ilk_yari_R", "son_yari_R"])
    ds.sort_values("dolar", ascending=False).to_csv(os.path.join(klasor, "1_tum_birlesimler.csv"), **yaz)

    m = []
    cizgi = "=" * 150
    m.append(cizgi)
    m.append("ICT TESTI - son %.0f ay (%s -> bugun), %d sembol, %d birlesim | SPREAD DAHIL, spread maliyeti 6 $'i gecen islem "
             "acilmaz | risk 15 $ (en kucuk lotta en fazla 30 $) | TP 2R / 3R" % (args.ay, tbas.strftime("%Y-%m-%d"),
                                                                             len(semboller) - len(yok), NM * NL))
    m.append("SAAT: " + saat_notu)
    m.append(cizgi)
    m.append("")
    m.append("-- SEANS / PENCERE SAATLERI (TURKIYE saati, yaz-kis otomatik) --")
    for pn in PEN_AD:
        if pn in ("SB", "KZ_HEPSI", "AC_HEPSI"):
            continue
        m.append("   %-10s %-34s %s" % (pn, PEN_TR[pn], pencere_tr_metni(pn).split(" TR ")[1]))
    bas = "%5s %4s %4s %4s %7s %8s %10s %7s %7s  %s" % ("ISLEM", "TP", "STOP", "SURE", "BASARI", "NET R", "DOLAR",
                                                        "1.YARI", "2.YARI", "BIRLESIM")

    def satir(mi, k):
        return "%5d %4d %4d %4d %%%6.1f %+8.1f %+10.2f %+7.1f %+7.1f  %s" % (
            TOP.n[mi, k], TOP.tp[mi, k], TOP.st[mi, k], TOP.su[mi, k], basari[mi, k], TOP.R[mi, k], TOP.dolar[mi, k],
            TOP.R1[mi, k], TOP.R2[mi, k], birlesim_ad(mi, k))

    m.append("")
    m.append(cizgi)
    m.append("-- GONDERILEN INDIKATORLERIN KURALLARI + BENIM ONERIM (butun semboller birlikte, en az %d islem) --"
             % args.min_islem)
    m.append(cizgi)
    for ad, sec in sistem_sonuc:
        m.append("")
        m.append(">> " + ad)
        if sec is None:
            m.append("   yeterli islem yok"); continue
        mi, k, mb, kb = sec
        m.append("   EN COK KAZANDIRAN:")
        m.append("   " + bas)
        m.append("   " + satir(mi, k))
        m.append(aciklama(mi, k))
        x = isl_df[isl_df["birlesim"] == birlesim_ad(mi, k)] if len(isl_df) else isl_df
        m.append(sim_metni(hesap_sim(x.to_dict("records"))))
        m.append("   EN BASARILI (kar ile kapanan orani):")
        m.append("   " + satir(mb, kb))
    m.append("")
    m.append(cizgi)
    uy = np.flatnonzero(yeterli.ravel())
    m.append("-- EN COK KAZANDIRAN 20 BIRLESIM (en az %d islem) --" % args.min_islem)
    m.append(bas)
    for f in uy[np.argsort(-TOP.dolar.ravel()[uy])][:20]:
        m.append(satir(*np.unravel_index(f, TOP.n.shape)))
    m.append("")
    m.append("-- EN BASARILI 20 BIRLESIM (en az %d islem) --" % args.min_islem)
    m.append(bas)
    for f in uy[np.lexsort((-TOP.dolar.ravel()[uy], -basari.ravel()[uy]))][:20]:
        m.append(satir(*np.unravel_index(f, TOP.n.shape)))
    # en iyi birlesim detay
    en = sistem_sonuc[-1][1]
    if en is not None and len(isl_df):
        mi, k = en[0], en[1]
        sec = isl_df[isl_df["birlesim"] == birlesim_ad(mi, k)].copy()
        sec.drop(columns=["cikis_dk"]).to_csv(os.path.join(klasor, "2_en_iyi_islemler.csv"), **yaz)
        m.append("")
        m.append(cizgi)
        m.append("EN COK KAZANDIRAN BIRLESIM: " + birlesim_ad(mi, k))
        m.append(cizgi)
        m.append(aciklama(mi, k, "  "))
        m.append("-- SEMBOL BAZLI --")
        m.append("%-12s %5s %4s %4s %4s %7s %10s" % ("SEMBOL", "ISLEM", "TP", "STOP", "SURE", "BASARI", "DOLAR"))
        for s_, x in sorted(sec.groupby("sembol"), key=lambda v: -v[1]["dolar"].sum()):
            m.append("%-12s %5d %4d %4d %4d %%%6.1f %+10.2f" % (s_, len(x), (x["sonuc"] == "TP").sum(),
                                                               (x["sonuc"] == "STOP").sum(), (x["sonuc"] == "SURE").sum(),
                                                               100.0 * (x["R"] > 0).mean(), x["dolar"].sum()))
        m.append("-- AYLIK --")
        b_ = BASLANGIC
        for ay, v in sec.groupby(sec["cikis_tr"].str[:7])["dolar"].sum().items():
            b_ += v
            m.append("   %-8s %+10.2f   ay sonu bakiye %10.2f" % (ay, v, b_))
        m.append(sim_metni(hesap_sim(sec.to_dict("records"))))
    # sembol bazli
    sb = pd.DataFrame([dict(sembol=s, islem=int(n), TP=int(tp), STOP=int(st), SURE=int(su),
                            basari=round(100.0 * w / n, 1), net_R=round(R, 1), dolar=round(dl, 2),
                            birlesim=birlesim_ad(mi, k))
                       for s, mi, k, n, w, R, dl, tp, st, su in sem_en])
    if len(sb):
        sb = sb.sort_values("dolar", ascending=False)
        sb.to_csv(os.path.join(klasor, "3_sembol_en_iyi.csv"), **yaz)
        m.append("")
        m.append(cizgi)
        m.append("-- SEMBOL BAZLI: her sembolun KENDI en cok kazandiran birlesimi (en az %d islem) --" % args.min_islem_sembol)
        m.append("%-12s %5s %4s %4s %4s %7s %10s  %s" % ("SEMBOL", "ISLEM", "TP", "STOP", "SURE", "BASARI", "DOLAR", "BIRLESIM"))
        for _, r in sb.iterrows():
            m.append("%-12s %5d %4d %4d %4d %%%6.1f %+10.2f  %s" % (r["sembol"], r["islem"], r["TP"], r["STOP"], r["SURE"],
                                                                   r["basari"], r["dolar"], r["birlesim"]))
    if yok:
        m.append("")
        m.append("Bulunamayan / verisi olmayan sembol: " + ", ".join(yok))
    m.append("")
    m.append("1.YARI / 2.YARI = 3 ayin ilk ve ikinci yarisindaki net R. Iyi bir birlesim iki yarida da artida olmali.")
    m.append("Not: %d birlesim ayni 3 ayda denendi; en iyilerin bir kismi sans olabilir." % (NM * NL))
    # %50 ustu
    m.append("")
    m.append(cizgi)
    m.append("-- BASARISI %%50'NIN USTUNDE OLAN PARITELER (her parite kendi en cok kazandiran %%50+ birlesimiyle, "
             "en az %d islem): %d adet --" % (args.min_islem_sembol, len(sem_50)))
    m.append(cizgi)
    i50 = pd.DataFrame(isl_50)
    if len(i50):
        i50.drop(columns=["cikis_dk"]).to_csv(os.path.join(klasor, "4_yuzde50_islemler.csv"), **yaz)
    sira = sorted(sem_50.items(), key=lambda v: -v[1][5])
    for s, (mi, k, n, w, R, dl, tp, st, su, R1, R2) in sira:
        m.append("")
        m.append("%s  ->  islem %d | TP %d | STOP %d | SURE %d | basari %%%.1f | net %+.1f R | %+.2f $ | 1.yari %+.1f R, "
                 "2.yari %+.1f R" % (s, n, tp, st, su, 100.0 * w / n, R, dl, R1, R2))
        m.append("   Mantik: " + birlesim_ad(mi, k))
        m.append(aciklama(mi, k))
        x = i50[i50["sembol"] == s] if len(i50) else i50
        if len(x):
            al, sat_ = (x["yon"] == "AL").sum(), (x["yon"] == "SAT").sum()
            m.append("     Islemler  : %d alis, %d satis" % (al, sat_))
            m.append("     En cok supurulen: " + ", ".join("%s (%d)" % (a, b) for a, b in
                                                            x["supurulen"].value_counts().head(4).items()))
            m.append("   Tek basina bu parite:")
            m.append(sim_metni(hesap_sim(x.to_dict("records"))))
    if len(i50):
        m.append("")
        m.append(cizgi)
        m.append("BU %d PARITE BIRLIKTE (her biri kendi mantigiyla), 10.000 $ hesap:" % len(sem_50))
        m.append(sim_metni(hesap_sim(i50.to_dict("records"))))
        m.append("Not: %50 ustu secimi ayni 3 ayin icinden yapildi; bu toplam iyimser bir ust sinirdir.")
    ms = "\n".join(m)
    print("\n" + ms)
    with open(os.path.join(klasor, "0_OZET.txt"), "w", encoding="utf-8") as fh:
        fh.write(ms + "\n")
    print("\nDosyalar: %s" % os.path.abspath(klasor))



# ======================= 34 SEMBOL TESTI =======================

import argparse
import os
import sys
import time
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

T = sys.modules[__name__]
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
