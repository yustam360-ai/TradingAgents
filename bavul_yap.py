# -*- coding: utf-8 -*-
"""
BAVUL_YAP - SECIMLI HIKAYE SERISI ICIN DIKEY VIDEO (Shorts / Reels / TikTok)
===========================================================================
Python 3.8:  py -3.8 C:\\Users\\User\\Desktop\\bavul_yap.py 1
             (sondaki sayi bolum numarasi; yazmazsan hepsini yapar)
Kurulum (BIR KERE, video_yap.py icin kurduysan tekrar gerekmez):
    py -3.8 -m pip install edge-tts requests pillow imageio-ffmpeg numpy
TEK DOSYA.

KLASORLER:
    Masaustu\\videolar\\bavul\\bolum1\\bolum.txt        -> bolumun metni (asagidaki bicim)
    Masaustu\\videolar\\bavul\\bolum1\\storyboard1.jpg, storyboard2.jpg ... -> Gemini'nin kare kare resimleri
                                                     (program boler, sirayla sahne1, sahne2 ... olur)
         ya da sahne1.png, sahne2.png ...              -> ayri ayri resimler
    Masaustu\\videolar\\bavul\\bolum1\\muzik.mp3        -> (istege bagli) arka plan muzigi, kisik sesle eklenir
    Masaustu\\videolar\\bavul\\bolum1\\ses1.wav, ses2.wav -> (istege bagli) hazir seslendirme (Google AI Studio ya da
                                                     kendi sesin); her [..] blogu icin sirayla bir dosya.
                                                     Yoksa Microsoft sesi kullanilir.
    Masaustu\\videolar\\bavul\\bolum1\\anlatim.wav       -> (istege bagli) TEK dosyada butun seslendirme; program
                                                     sahnelere kendisi boler (sessizliklerden)
    ALTYAZI: VAR  (bolum.txt basina yazilirsa altyazi eklenir; varsayilan YOK)
    Masaustu\\videolar\\bavul\\cikti\\bolum1.mp4        -> HAZIR VIDEO (1080x1920)

BOLUM.TXT BICIMI:
    SERI: BAVUL
    BOLUM: 1
    BASLIK: PIKNIK
    SES: tr-TR-AhmetNeural
    HIZ: +0%
    GOSTERGE: PARA=0 ₺ | TAKIP=%0 | EMRE GUVEN=%90

    [KAPAK sahne=5]
    YAZI: USTTEKI BUYUK YAZI | IKINCI SATIR
    METIN: seslendirilecek metin

    [SAHNE sahne=1]
    METIN: seslendirilecek metin
    GOSTERGE: TAKIP=%5          (sadece degisen deger yazilir; sayi ise sayarak degisir)

    [OYLAMA sahne=1]            (2. bolumden itibaren: onceki bolumun oylama sonucu)
    SONUC: SAKLA=64 | PAYLAS=36
    METIN: ...

    [SECIM sahne=8]
    A: SAKLA | Kimseye soyleme
    B: PAYLAS | Emre'yi cagir
    METIN: ...
    ALT: Yorumlara A ya da B yaz
"""
from __future__ import print_function

import asyncio
import math
import os
import re
import shutil
import subprocess
import sys
import time

try:
    import numpy as np
    import edge_tts
    import imageio_ffmpeg
    from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageEnhance
except ImportError as _h:
    sys.exit("Eksik modul (%s). Once kurun:\n  py -3.8 -m pip install edge-tts pillow imageio-ffmpeg numpy" % _h)

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
W, H, FPS = 1080, 1920, 30
PAY = 0.45                       # her sahne sonunda kisa sessizlik (sn)


# ----------------------------------------------------------------- genel
def masaustu():
    for p in (os.path.join(os.path.expanduser("~"), "Desktop"), os.path.join(os.path.expanduser("~"), "Masaüstü"),
              os.path.join(os.path.expanduser("~"), "OneDrive", "Desktop"),
              os.path.join(os.path.expanduser("~"), "OneDrive", "Masaüstü")):
        if os.path.isdir(p):
            return p
    return os.getcwd()


def ff(args):
    r = subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-y"] + args,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if r.returncode != 0:
        raise RuntimeError("ffmpeg hatasi: " + r.stderr.decode("utf-8", "ignore")[-800:])


def sure(dosya):
    r = subprocess.run([FFMPEG, "-hide_banner", "-i", dosya], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    m = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", r.stderr.decode("utf-8", "ignore"))
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3)) if m else 0.0


_FONT = {}


def font(boy, kalin=True, siyah=False):
    anahtar = (boy, kalin, siyah)
    if anahtar in _FONT:
        return _FONT[anahtar]
    adaylar = []
    if siyah:
        adaylar += ["C:\\Windows\\Fonts\\ariblk.ttf", "C:\\Windows\\Fonts\\impact.ttf"]
    adaylar += (["C:\\Windows\\Fonts\\arialbd.ttf", "C:\\Windows\\Fonts\\segoeuib.ttf"] if kalin else
                ["C:\\Windows\\Fonts\\arial.ttf", "C:\\Windows\\Fonts\\segoeui.ttf"])
    adaylar += ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if kalin else
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]
    f = None
    for a in adaylar:
        if os.path.exists(a):
            f = ImageFont.truetype(a, boy)
            break
    if f is None:
        f = ImageFont.load_default()
    _FONT[anahtar] = f
    return f


def yazi_kenarli(d, xy, t, f, renk=(255, 255, 255), kenar=None, anchor="mm"):
    k = kenar if kenar is not None else max(3, f.size // 12)
    d.text(xy, t, font=f, fill=renk, stroke_width=k, stroke_fill=(0, 0, 0), anchor=anchor)


def satirla(d, metin, f, genislik):
    kel, satir, cur = metin.split(), [], ""
    for k in kel:
        dene = (cur + " " + k).strip()
        if d.textlength(dene, font=f) > genislik and cur:
            satir.append(cur)
            cur = k
        else:
            cur = dene
    if cur:
        satir.append(cur)
    return satir


# ----------------------------------------------------------------- bolum metni
def bolum_oku(yol):
    bas = {"SERI": "BAVUL", "BOLUM": "1", "BASLIK": "", "SES": "tr-TR-AhmetNeural", "HIZ": "+0%", "GOSTERGE": ""}
    sahneler = []
    cur = None
    with open(yol, encoding="utf-8-sig") as f:
        for ham in f.read().splitlines():
            s = ham.strip()
            if not s or s.startswith("#"):
                continue
            m = re.match(r"^\[(KAPAK|SAHNE|SECIM|OYLAMA)\s*(?:sahne\s*=\s*(\d+))?\s*\]$", s, re.I)
            if m:
                cur = {"tur": m.group(1).upper(), "resim": int(m.group(2)) if m.group(2) else None,
                       "METIN": "", "YAZI": "", "GOSTERGE": "", "A": "", "B": "", "ALT": "", "SONUC": ""}
                sahneler.append(cur)
                continue
            m = re.match(r"^([A-ZÇĞİÖŞÜ]+)\s*:\s*(.*)$", s)
            if not m:
                if cur is not None:
                    cur["METIN"] = (cur["METIN"] + " " + s).strip()
                continue
            k, v = m.group(1).upper(), m.group(2).strip()
            if cur is None:
                bas[k] = v
            elif k == "METIN":
                cur["METIN"] = (cur["METIN"] + " " + v).strip()
            else:
                cur[k] = v
    return bas, sahneler


def gosterge_coz(s):
    """'PARA=0 ₺ | TAKIP=%0' -> [(ad, deger)]"""
    out = []
    for p in s.split("|"):
        if "=" in p:
            a, b = p.split("=", 1)
            out.append((a.strip(), b.strip()))
    return out


def sayi_al(v):
    """'100.000.000 ₺' -> (100000000, '', ' ₺'), '%45' -> (45, '%', '')"""
    m = re.match(r"^(\D*?)([\d.]+)(\D*)$", v)
    if not m:
        return None
    try:
        return int(m.group(2).replace(".", "")), m.group(1), m.group(3)
    except ValueError:
        return None


def sayi_yaz(n, on, son):
    return on + "{:,}".format(int(round(n))).replace(",", ".") + son


# ----------------------------------------------------------------- resimler
def oluk(o, alt, mn=2, mx=40):
    n = len(o)
    k = o > alt
    out, i = [], 0
    while i < n:
        if k[i]:
            j = i
            while j < n and k[j]:
                j += 1
            if mn <= j - i <= mx:
                out.append((i, j))
            i = j
        else:
            i += 1
    return out


def araliklar(ol, n, enaz):
    s = [0] + [v for ab in ol for v in ab] + [n]
    return [(s[i], s[i + 1]) for i in range(0, len(s), 2) if s[i + 1] - s[i] > enaz]


def storyboard_bol(yol):
    """kare kare resmi siyah ya da beyaz oluklardan boler (once satirlar, sonra her satirin sutunlari)"""
    im = Image.open(yol).convert("RGB")
    g = np.asarray(im).astype(float).mean(axis=2)
    h, w = g.shape
    en = []
    for m in (g < 20, g > 235):
        sat = araliklar([ab for ab in oluk(m.mean(axis=1), 0.9) if 0.03 * h < ab[0] < 0.97 * h], h, 0.05 * h)
        out = []
        for r0, r1 in sat:
            sut = araliklar([ab for ab in oluk(m[r0:r1].mean(axis=0), 0.9) if 0.05 * w < ab[0] < 0.95 * w], w, 0.1 * w)
            out += [(r0, c0, r1, c1) for c0, c1 in sut]
        if len(out) > len(en):
            en = out
    return [im.crop((c0 + 2, r0 + 2, c1 - 2, r1 - 2)) for r0, c0, r1, c1 in en]


def resimleri_yukle(klasor):
    ayri = {}
    for d in os.listdir(klasor):
        m = re.match(r"^sahne(\d+)\.(png|jpg|jpeg|webp)$", d, re.I)
        if m:
            ayri[int(m.group(1))] = Image.open(os.path.join(klasor, d)).convert("RGB")
    if ayri:
        return ayri
    sb = []
    for d in os.listdir(klasor):
        m = re.match(r"^storyboard(\d*)\.(png|jpg|jpeg|webp)$", d, re.I)
        if m:
            sb.append((int(m.group(1)) if m.group(1) else 0, d))
    out = {}
    for _, d in sorted(sb):                       # storyboard1, storyboard2 ... sirayla
        parca = storyboard_bol(os.path.join(klasor, d))
        print("   %s: %d kareye bolundu" % (d, len(parca)))
        for p in parca:
            out[len(out) + 1] = p
    return out


# ----------------------------------------------------------------- ses
async def _tts(metin, ses, hiz, mp3):
    try:
        com = edge_tts.Communicate(metin, ses, rate=hiz, boundary="WordBoundary")
    except TypeError:
        com = edge_tts.Communicate(metin, ses, rate=hiz)
    kel = []
    with open(mp3, "wb") as f:
        async for ch in com.stream():
            if ch["type"] == "audio":
                f.write(ch["data"])
            elif ch["type"] in ("WordBoundary", "SentenceBoundary"):
                kel.append((ch["offset"] / 1e7, ch["duration"] / 1e7, ch["text"], ch["type"]))
    return kel


def seslendir(metin, ses, hiz, mp3):
    if sys.platform.startswith("win"):
        try:
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        except Exception:
            pass
    for deneme in range(4):
        try:
            return asyncio.run(_tts(metin, ses, hiz, mp3))
        except Exception as h:
            print("   ses hatasi (%s), tekrar deneniyor..." % h)
            time.sleep(3 + deneme * 3)
    raise RuntimeError("Seslendirme yapilamadi (internet baglantisini kontrol edin).")


def altyazi_parcalari(kel):
    sozcuk = []
    for bas, sr, yazi, tip in kel:
        if tip == "WordBoundary":
            sozcuk.append((bas, bas + sr, yazi))
        else:
            k = yazi.split()
            if not k:
                continue
            top = float(sum(len(x) + 1 for x in k))
            t = bas
            for x in k:
                dd = sr * (len(x) + 1) / top
                sozcuk.append((t, t + dd, x))
                t += dd
    out, cur = [], []
    for s in sozcuk:
        cur.append(s)
        yazi = " ".join(x[2] for x in cur)
        if len(cur) >= 5 or len(yazi) >= 28 or re.search(r"[.!?;:,]$", s[2]):
            out.append([cur[0][0], cur[-1][1], yazi])
            cur = []
    if cur:
        out.append([cur[0][0], cur[-1][1], " ".join(x[2] for x in cur)])
    for i in range(len(out) - 1):
        out[i][1] = max(out[i][1], min(out[i + 1][0], out[i][1] + 0.5))
    return out


def sessizlikler(dosya):
    """[(bas, bit)] sessiz araliklar (sn)"""
    r = subprocess.run([FFMPEG, "-hide_banner", "-i", dosya, "-af", "silencedetect=noise=-38dB:d=0.25", "-f", "null", "-"],
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    t = r.stderr.decode("utf-8", "ignore")
    bas = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", t)]
    bit = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", t)]
    return list(zip(bas, bit))


def anlatim_bol(dosya, metinler, gecici):
    """tek seslendirme dosyasini sahnelere boler.
    Her sahne sinirinin yeri metin uzunluguna gore tahmin edilir; sessizlikler arasindan,
    sirayla, hem UZUN hem de tahmine YAKIN olanlar dinamik programlamayla birlikte secilir.
    Hicbir sahne, tahmini suresinin %35'inden kisa olamaz."""
    toplam = sure(dosya)
    n = len(metinler)
    uz = [max(1, len(m)) for m in metinler]
    top = float(sum(uz))
    pay = [toplam * u / top for u in uz]                       # sahne basina tahmini sure
    tahmin, b = [], 0.0
    for k in range(n - 1):
        b += pay[k]
        tahmin.append(b)
    sess = [((a + c) / 2.0, c - a) for a, c in sessizlikler(dosya) if 0.05 < (a + c) / 2.0 < toplam - 0.05]
    m = len(sess)
    if n <= 1:
        kes = []
    elif m < n - 1:
        kes = tahmin
    else:
        en_uzun = max(d for _, d in sess) or 1.0
        def puan(k, j):
            orta, d = sess[j]
            yakin = abs(orta - tahmin[k]) / max(1.0, pay[k] + pay[k + 1])
            return d / en_uzun - 2.5 * yakin
        NEG = -1e18
        dp = [[NEG] * m for _ in range(n - 1)]
        geri = [[-1] * m for _ in range(n - 1)]
        for j in range(m):
            if sess[j][0] >= 0.35 * pay[0]:
                dp[0][j] = puan(0, j)
        for k in range(1, n - 1):
            for j in range(m):
                bas = NEG
                bi = -1
                for i2 in range(j):
                    if dp[k - 1][i2] > bas and sess[j][0] - sess[i2][0] >= 0.35 * pay[k]:
                        bas, bi = dp[k - 1][i2], i2
                if bi >= 0:
                    dp[k][j] = bas + puan(k, j)
                    geri[k][j] = bi
        son = n - 2
        aday = [(dp[son][j], j) for j in range(m) if dp[son][j] > NEG and toplam - sess[j][0] >= 0.35 * pay[-1]]
        if not aday:
            kes = tahmin
        else:
            j = max(aday)[1]
            secim = []
            for k in range(son, -1, -1):
                secim.append(j)
                j = geri[k][j]
            kes = [sess[x][0] for x in reversed(secim)]
    sinir = [0.0] + kes + [toplam]
    out = []
    for i in range(n):
        w = os.path.join(gecici, "anlatim_%02d.wav" % i)
        ff(["-ss", "%.3f" % sinir[i], "-to", "%.3f" % sinir[i + 1], "-i", dosya, "-ar", "48000", "-ac", "2", w])
        out.append(w)
    print("   anlatim bolme noktalari (sn): %s" % ", ".join("%.1f" % x for x in kes))
    supheli = [i + 1 for i in range(n) if not (0.5 * pay[i] <= sinir[i + 1] - sinir[i] <= 1.8 * pay[i])]
    if supheli:
        raise RuntimeError(
            "Tek anlatim dosyasi guvenle bolunemedi (supheli sahneler: %s). Ses ile resim kayabilir, video YAPILMADI.\n"
            "   Cozum: her sahnenin sesini AYRI dosya yapin (ses1, ses2 ... ) ve anlatim dosyasini klasorden cikarin."
            % ", ".join(str(x) for x in supheli))
    return out


# ----------------------------------------------------------------- cizim katmanlari
def arka_plan(resim):
    """resmin bulanik, karartilmis hali tam ekran"""
    r = resim.copy()
    olc = max(W / r.width, H / r.height)
    r = r.resize((int(r.width * olc) + 2, int(r.height * olc) + 2), Image.BILINEAR)
    x, y = (r.width - W) // 2, (r.height - H) // 2
    r = r.crop((x, y, x + W, y + H)).filter(ImageFilter.GaussianBlur(28))
    return ImageEnhance.Brightness(r).enhance(0.45)


def on_resim(resim, zoom_en=1.08):
    """sahne resmi: genislik 1080, en fazla yukseklik 1250; zoom icin buyuk hali"""
    gen = W
    yuk = int(resim.height * W / resim.width)
    if yuk > 1250:
        yuk = 1250
        gen = int(resim.width * 1250 / resim.height)
    hedef = (int(gen * zoom_en), int(yuk * zoom_en))
    ara = resim
    # kucuk resim kademeli buyutulur (her adimda en fazla 2 kat), her adimda hafif keskinlestirme
    while ara.width * 2 < hedef[0]:
        ara = ara.resize((ara.width * 2, ara.height * 2), Image.LANCZOS).filter(ImageFilter.UnsharpMask(1.2, 60, 1))
    buyuk = ara.resize(hedef, Image.LANCZOS)
    buyuk = buyuk.filter(ImageFilter.UnsharpMask(1.6, 90, 2))
    return buyuk, gen, yuk


def gosterge_resmi(degerler, vurgu=None):
    """ust panel: kutular. degerler: [(ad, deger)]"""
    img = Image.new("RGBA", (W, 230), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    n = max(1, len(degerler))
    bosluk = 18
    kg = (W - 60 - bosluk * (n - 1)) // n
    for i, (ad, v) in enumerate(degerler):
        x0 = 30 + i * (kg + bosluk)
        renk = (255, 214, 64) if vurgu and ad in vurgu else (255, 255, 255)
        d.rounded_rectangle((x0, 90, x0 + kg, 210), radius=22, fill=(10, 14, 28, 205),
                            outline=(255, 214, 64, 230) if vurgu and ad in vurgu else (255, 255, 255, 60), width=3)
        d.text((x0 + kg / 2, 118), ad, font=font(26), fill=(190, 200, 220), anchor="mm")
        fv = font(46)
        while d.textlength(v, font=fv) > kg - 24 and fv.size > 24:
            fv = font(fv.size - 2)
        d.text((x0 + kg / 2, 168), v, font=fv, fill=renk, anchor="mm")
    return img


def ust_etiket(seri, bolum, baslik):
    img = Image.new("RGBA", (W, 80), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    t = "%s  •  BÖLÜM %s%s" % (seri, bolum, ("  •  " + baslik) if baslik else "")
    f = font(30)
    w = d.textlength(t, font=f)
    d.rounded_rectangle(((W - w) / 2 - 22, 18, (W + w) / 2 + 22, 72), radius=27, fill=(200, 30, 45, 230))
    d.text((W / 2, 45), t, font=f, fill=(255, 255, 255), anchor="mm")
    return img


def altyazi_resmi(yazi):
    img = Image.new("RGBA", (W, 300), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    f = font(66)
    sat = satirla(d, yazi, f, W - 120)[-2:]
    y = 150 - (len(sat) - 1) * 40
    for s in sat:
        yazi_kenarli(d, (W / 2, y), s, f, (255, 255, 255), 7)
        y += 80
    return img


def kapak_yazisi(yazi):
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    satirlar = [s.strip() for s in yazi.split("|") if s.strip()]
    f = font(86, siyah=True)
    y = 330
    for i, s in enumerate(satirlar):
        for t in satirla(d, s, f, W - 100):
            yazi_kenarli(d, (W / 2, y), t, f, (255, 214, 64) if i == 0 else (255, 255, 255), 9)
            y += 110
    return img


def secim_resmi(a, b, alt):
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    yazi_kenarli(d, (W / 2, 420), "ŞİMDİ KARAR SENİN", font(84, siyah=True), (255, 214, 64), 8)
    for i, (harf, sec, renk) in enumerate((("A", a, (220, 45, 60)), ("B", b, (40, 110, 230)))):
        bas, acik = (sec.split("|", 1) + [""])[:2]
        y0 = 560 + i * 380
        d.rounded_rectangle((70, y0, W - 70, y0 + 320), radius=40, fill=renk + (235,), outline=(255, 255, 255, 255), width=6)
        d.ellipse((110, y0 + 80, 270, y0 + 240), fill=(255, 255, 255, 255))
        d.text((190, y0 + 160), harf, font=font(110, siyah=True), fill=renk, anchor="mm")
        d.text((310, y0 + 115), bas.strip(), font=font(78, siyah=True), fill=(255, 255, 255), anchor="lm")
        fa = font(44, kalin=False)
        for j, t in enumerate(satirla(d, acik.strip(), fa, W - 70 - 310 - 40)[:2]):
            d.text((310, y0 + 200 + j * 52), t, font=fa, fill=(255, 255, 255), anchor="lm")
    if alt:
        fa = font(46)
        for j, t in enumerate(satirla(d, alt, fa, W - 120)[:2]):
            yazi_kenarli(d, (W / 2, 1400 + j * 60), t, fa, (255, 255, 255), 5)
    return img


def oylama_resmi(sonuc, bolum):
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    try:
        onceki = int(bolum) - 1
    except ValueError:
        onceki = ""
    yazi_kenarli(d, (W / 2, 430), "BÖLÜM %s · OYLADINIZ" % onceki, font(70, siyah=True), (255, 214, 64), 7)
    secimler = gosterge_coz(sonuc)
    for i, (ad, v) in enumerate(secimler[:3]):
        y0 = 600 + i * 230
        try:
            yuzde = float(re.sub(r"[^\d.]", "", v))
        except ValueError:
            yuzde = 0.0
        d.text((90, y0), ad, font=font(70, siyah=True), fill=(255, 255, 255), anchor="ls")
        d.text((W - 90, y0), "%%%d" % yuzde, font=font(70, siyah=True), fill=(255, 214, 64), anchor="rs")
        d.rounded_rectangle((90, y0 + 30, W - 90, y0 + 80), radius=25, fill=(255, 255, 255, 70))
        x1 = 90 + (W - 180) * max(0.0, min(1.0, yuzde / 100.0))
        if x1 > 120:
            d.rounded_rectangle((90, y0 + 30, x1, y0 + 80), radius=25, fill=(230, 50, 80, 255) if i == 0 else (200, 200, 210, 255))
    return img


# ----------------------------------------------------------------- bolum videosu
def bolum_yap(klasor, cikti_klasor):
    bas, sahneler = bolum_oku(os.path.join(klasor, "bolum.txt"))
    no = bas.get("BOLUM", "1")
    hedef = os.path.join(cikti_klasor, "bolum%s.mp4" % no)
    resimler = resimleri_yukle(klasor)
    if not resimler:
        raise RuntimeError("Klasorde resim yok (storyboard.jpg ya da sahne1.png ...): %s" % klasor)
    if not sahneler:
        raise RuntimeError("bolum.txt icinde [SAHNE] yok.")
    gecici = os.path.join(klasor, "_gecici")
    shutil.rmtree(gecici, ignore_errors=True)
    os.makedirs(gecici)
    t0 = time.time()
    print("[BOLUM %s] %d sahne, %d resim" % (no, len(sahneler), len(resimler)))

    # 1) seslendirme
    ses_listesi, plan = [], []
    hazir = {}
    for d in os.listdir(klasor):
        m = re.match(r"^ses(\d+)\.(wav|mp3|m4a|ogg|aac|flac|opus)$", d, re.I)
        if m:
            hazir[int(m.group(1))] = os.path.join(klasor, d)
    altyazi_acik = bas.get("ALTYAZI", "YOK").strip().upper() in ("VAR", "EVET", "ACIK", "AÇIK")
    if not hazir:
        for d in os.listdir(klasor):
            if re.match(r"^anlatim\.(wav|mp3|m4a|ogg|aac|flac|opus)$", d, re.I):
                parca = anlatim_bol(os.path.join(klasor, d), [s["METIN"] for s in sahneler], gecici)
                hazir = {i + 1: p for i, p in enumerate(parca)}
                print("   tek anlatim dosyasi %d sahneye bolundu: %s" % (len(parca), d))
                break
    elif hazir:
        print("   hazir ses dosyalari kullaniliyor: %d dosya (ses1, ses2 ...)" % len(hazir))
    for i, s in enumerate(sahneler):
        metin = s["METIN"]
        kel = []
        if (i + 1) in hazir:
            mp3 = os.path.join(gecici, "s%02d_h.wav" % i)
            # bas ve sondaki sessizlik kirpilir
            ff(["-i", hazir[i + 1], "-af", "silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.05,"
                "areverse,silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.05,areverse",
                "-ar", "48000", "-ac", "2", mp3])
            var = True
        elif metin:
            mp3 = os.path.join(gecici, "s%02d.mp3" % i)
            kel = seslendir(metin, bas["SES"], bas["HIZ"], mp3)
            var = True
        else:
            var = False
        dur = (sure(mp3) if var else 2.5) + PAY
        if s["tur"] == "SECIM":
            dur += 2.5                       # oylama ekrani biraz daha ekranda kalsin
        plan.append((s, dur, altyazi_parcalari(kel) if (altyazi_acik and s["tur"] in ("SAHNE", "KAPAK")) else []))
        wav = os.path.join(gecici, "s%02d.wav" % i)
        if var:
            ff(["-i", mp3, "-af", "apad", "-t", "%.3f" % dur, "-ar", "48000", "-ac", "2", wav])
        else:
            ff(["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-t", "%.3f" % dur, wav])
        ses_listesi.append(wav)
        print("   ses %d/%d hazir (%.1f sn)" % (i + 1, len(sahneler), dur))
    liste = os.path.join(gecici, "ses.txt")
    with open(liste, "w", encoding="utf-8") as f:
        for w in ses_listesi:
            f.write("file '%s'\n" % w.replace("\\", "/"))
    ses = os.path.join(gecici, "ses.wav")
    ff(["-f", "concat", "-safe", "0", "-i", liste, "-c", "copy", ses])
    muzik = None
    for d in os.listdir(klasor):
        if re.match(r"^muzik\.(mp3|wav|m4a)$", d, re.I):
            muzik = os.path.join(klasor, d)
    if muzik:
        karisik = os.path.join(gecici, "ses_muzik.wav")
        ff(["-i", ses, "-stream_loop", "-1", "-i", muzik, "-filter_complex",
            "[1:a]volume=0.12[m];[0:a][m]amix=inputs=2:duration=first:dropout_transition=0[a]", "-map", "[a]", karisik])
        ses = karisik

    # 2) goruntu: kareler ffmpeg'e akitilir
    toplam = sum(p[1] for p in plan)
    hedef_gecici = os.path.join(gecici, "video.mp4")
    proc = subprocess.Popen([FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
                             "-s", "%dx%d" % (W, H), "-r", str(FPS), "-i", "-", "-i", ses, "-c:v", "libx264",
                             "-preset", "medium", "-tune", "animation", "-crf", "16", "-profile:v", "high", "-level", "4.2",
                             "-maxrate", "16M", "-bufsize", "32M", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "256k", "-ar", "48000",
                             "-shortest", "-movflags", "+faststart", hedef_gecici], stdin=subprocess.PIPE)
    etiket = ust_etiket(bas["SERI"], no, bas["BASLIK"])
    gst = gosterge_coz(bas["GOSTERGE"])
    kare_say = 0
    for si, (s, dur, alt) in enumerate(plan):
        resim = resimler.get(s["resim"] or (si + 1)) or resimler[sorted(resimler)[min(si, len(resimler) - 1)]]
        bg = arka_plan(resim)
        buyuk, gen, yuk = on_resim(resim)
        cy = 900 if s["tur"] == "SAHNE" else (1150 if s["tur"] == "KAPAK" else 960)
        # gosterge degisimi
        eski = dict(gst)
        yeni = list(gst)
        for ad, v in gosterge_coz(s["GOSTERGE"]):
            yeni = [(a, v if a == ad else b) for a, b in yeni] if any(a == ad for a, _ in yeni) else yeni + [(ad, v)]
        degisen = [a for a, b in yeni if eski.get(a) != b]
        ust = None
        if s["tur"] == "KAPAK":
            ust = kapak_yazisi(s["YAZI"] or bas["BASLIK"])
        elif s["tur"] == "SECIM":
            ust = secim_resmi(s["A"], s["B"], s["ALT"])
        elif s["tur"] == "OYLAMA":
            ust = oylama_resmi(s["SONUC"], no)
        alt_res = {}
        n = int(round(dur * FPS))
        yon = 1 if si % 2 == 0 else -1
        sabit_gst = gosterge_resmi(yeni, degisen if degisen else None)
        for k in range(n):
            t = k / float(FPS)
            ilerleme = k / float(max(1, n - 1))
            # ken burns: yavas yakinlasma + hafif kaydirma
            z = 1.0 + 0.07 * (ilerleme if yon > 0 else 1 - ilerleme)
            cw, ch = buyuk.width / z, buyuk.height / z
            cx = buyuk.width / 2 + yon * (buyuk.width - cw) / 2 * (ilerleme - 0.5) * 0.8
            cyy = buyuk.height / 2
            kesit = buyuk.crop((int(cx - cw / 2), int(cyy - ch / 2), int(cx + cw / 2), int(cyy + ch / 2))).resize((gen, yuk), Image.BICUBIC)
            kare = bg.copy()
            if s["tur"] in ("SECIM", "OYLAMA"):
                kare.paste(ImageEnhance.Brightness(kesit).enhance(0.35), ((W - gen) // 2, cy - yuk // 2))
            else:
                kare.paste(kesit, ((W - gen) // 2, cy - yuk // 2))
            kare = kare.convert("RGBA")
            kare.alpha_composite(etiket, (0, 0))
            # gosterge: sayilar sahne basinda 1.2 sn icinde sayarak degisir
            if degisen and t < 1.4 and s["tur"] != "SECIM":
                oran = min(1.0, t / 1.2)
                oran = 1 - (1 - oran) ** 3
                anlik = []
                for a, b in yeni:
                    e = eski.get(a)
                    se, sy = (sayi_al(e) if e else None), sayi_al(b)
                    if a in degisen and se and sy:
                        anlik.append((a, sayi_yaz(se[0] + (sy[0] - se[0]) * oran, sy[1], sy[2])))
                    else:
                        anlik.append((a, b))
                kare.alpha_composite(gosterge_resmi(anlik, degisen), (0, 0))
            elif s["tur"] != "SECIM":
                kare.alpha_composite(sabit_gst, (0, 0))
            if ust is not None:
                kare.alpha_composite(ust, (0, 0))
            for j, (a0, a1, yazi) in enumerate(alt):
                if a0 <= t < a1:
                    if j not in alt_res:
                        alt_res[j] = altyazi_resmi(yazi)
                    kare.alpha_composite(alt_res[j], (0, 1500))
                    break
            # gecis: sahne basinda kisa kararma
            if k < 6 and si > 0:
                kare = Image.blend(Image.new("RGBA", (W, H), (0, 0, 0, 255)), kare, (k + 1) / 7.0)
            proc.stdin.write(kare.convert("RGB").tobytes())
            kare_say += 1
        gst = yeni
        print("   goruntu sahne %d/%d hazir (gecen %.0f sn)" % (si + 1, len(plan), time.time() - t0))
    proc.stdin.close()
    if proc.wait() != 0:
        raise RuntimeError("ffmpeg video olusturamadi.")
    os.replace(hedef_gecici, hedef)
    shutil.rmtree(gecici, ignore_errors=True)
    print("[BOLUM %s] HAZIR: %s  (%.0f sn video, %.1f dk surdu)" % (no, hedef, toplam, (time.time() - t0) / 60))


def main():
    kok = os.path.join(masaustu(), "videolar", "bavul")
    cikti = os.path.join(kok, "cikti")
    for k in (kok, cikti):
        if not os.path.isdir(k):
            os.makedirs(k)
    hangi = sys.argv[1] if len(sys.argv) > 1 else None
    klasorler = sorted(d for d in os.listdir(kok) if re.match(r"^bolum\d+$", d) and (hangi is None or d == "bolum" + hangi))
    if not klasorler:
        sys.exit("Bolum klasoru yok. Ornek: %s" % os.path.join(kok, "bolum1"))
    for d in klasorler:
        try:
            bolum_yap(os.path.join(kok, d), cikti)
        except Exception as h:
            print("[%s] HATA: %s" % (d, h))
    print("\nBitti. Videolar: %s" % cikti)


if __name__ == "__main__":
    main()
