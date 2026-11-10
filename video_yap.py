# -*- coding: utf-8 -*-
"""
VIDEO_YAP - METINDEN YOUTUBE VIDEOSU (seslendirme + stok video)
=========================================================================
Python 3.8:  py -3.8 C:\\Users\\User\\Desktop\\video_yap.py
Kurulum (BIR KERE):
    py -3.8 -m pip install edge-tts requests pillow imageio-ffmpeg
TEK DOSYA.  FFmpeg ayrica kurulmaz (imageio-ffmpeg icinde gelir).

KLASORLER (program kendisi olusturur):
    Masaustu\\pixabay_anahtar.txt        -> Pixabay API anahtari (tek satir)
    Masaustu\\videolar\\metinler\\*.txt   -> video metinleri (her dosya bir video)
    Masaustu\\videolar\\cikti\\            -> hazir videolar (.mp4) + YouTube bilgileri (_youtube.txt)
    Masaustu\\videolar\\onbellek\\         -> indirilen stok videolar / gecici dosyalar

METIN DOSYASI BICIMI:
    TITLE: How the 2008 Financial Crisis Happened
    DESCRIPTION: ...            (YouTube aciklamasi, tek satir; \\n ile alt satir)
    TAGS: finance, 2008, ...
    [VISUAL: wall street; stock market crash]
    Bu sahnede okunacak metin...
    [VISUAL: house; mortgage]
    Sonraki sahnenin metni...

CALISMA: her metin icin -> her sahne seslendirilir (Microsoft yapay zeka sesi, ucretsiz) ->
         Pixabay'den sahneye uygun stok videolar indirilir (yoksa fotograf) ->
         sahneler birlestirilir -> cikti\\<dosya_adi>.mp4
         Videosu zaten olan metin atlanir (program tekrar calistirilinca kaldigi yerden devam eder).

AYARLAR: --ses en-US-GuyNeural (varsayilan) | en-US-ChristopherNeural ...
         --hiz +0%  (ornek: +5% daha hizli, -5% daha yavas)
         --kalite 1080 | 720   (eski bilgisayarda 720 daha hizli)
         --altyazi   (videoya altyazi yakar; varsayilan YOK, YouTube kendi altyazisini olusturur)
"""
from __future__ import print_function

import argparse
import asyncio
import json
import os
import re
import shutil
import subprocess
import sys
import time

try:
    import requests
    import edge_tts
    import imageio_ffmpeg
    from PIL import Image, ImageDraw, ImageFont
except ImportError as _h:
    sys.exit("Eksik modul (%s). Once kurun:\n  py -3.8 -m pip install edge-tts requests pillow imageio-ffmpeg" % _h)

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
FPS = 30
PARCA_EN_FAZLA = 7.0          # bir stok videodan en fazla kac saniye kullanilir
PARCA_EN_AZ = 2.5


def masaustu():
    for p in (os.path.join(os.path.expanduser("~"), "Desktop"), os.path.join(os.path.expanduser("~"), "Masaüstü"),
              os.path.join(os.path.expanduser("~"), "OneDrive", "Desktop"),
              os.path.join(os.path.expanduser("~"), "OneDrive", "Masaüstü")):
        if os.path.isdir(p):
            return p
    return os.getcwd()


def ff(args, sessiz=True):
    """ffmpeg calistir; hata olursa son satirlari goster"""
    k = [FFMPEG, "-hide_banner", "-loglevel", "error", "-y"] + args
    r = subprocess.run(k, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if r.returncode != 0:
        raise RuntimeError("ffmpeg hatasi: " + r.stderr.decode("utf-8", "ignore")[-800:])


def sure(dosya):
    r = subprocess.run([FFMPEG, "-hide_banner", "-i", dosya], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    m = re.search(r"Duration: (\d+):(\d+):(\d+\.\d+)", r.stderr.decode("utf-8", "ignore"))
    if not m:
        return 0.0
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))


# ----------------------------------------------------------------- metin
def metin_oku(yol):
    bilgi = {"TITLE": "", "DESCRIPTION": "", "TAGS": ""}
    sahneler = []
    with open(yol, encoding="utf-8-sig") as f:
        satirlar = f.read().splitlines()
    anahtar, govde = None, []

    def bitir():
        if anahtar is not None:
            t = " ".join(x.strip() for x in govde if x.strip())
            if t:
                sahneler.append((anahtar, t))

    for s in satirlar:
        st = s.strip()
        m = re.match(r"^(TITLE|DESCRIPTION|TAGS)\s*:\s*(.*)$", st)
        if m and anahtar is None:
            bilgi[m.group(1)] = m.group(2).strip()
            continue
        m = re.match(r"^\[VISUAL\s*:\s*(.*)\]$", st, re.I)
        if m:
            bitir()
            anahtar = [k.strip() for k in m.group(1).split(";") if k.strip()]
            govde = []
            continue
        if anahtar is not None:
            govde.append(st)
    bitir()
    return bilgi, sahneler


# ----------------------------------------------------------------- ses (Microsoft Edge yapay zeka sesi)
async def _tts(metin, ses, hiz, mp3):
    try:
        com = edge_tts.Communicate(metin, ses, rate=hiz, boundary="WordBoundary")
    except TypeError:
        com = edge_tts.Communicate(metin, ses, rate=hiz)
    kelimeler = []
    with open(mp3, "wb") as f:
        async for ch in com.stream():
            if ch["type"] == "audio":
                f.write(ch["data"])
            elif ch["type"] in ("WordBoundary", "SentenceBoundary"):
                kelimeler.append((ch["offset"] / 1e7, ch["duration"] / 1e7, ch["text"], ch["type"]))
    return kelimeler


def seslendir(metin, ses, hiz, mp3):
    for deneme in range(4):
        try:
            return asyncio.run(_tts(metin, ses, hiz, mp3))
        except Exception as h:
            print("   ses hatasi (%s), tekrar deneniyor..." % h)
            time.sleep(3 + deneme * 3)
    raise RuntimeError("Seslendirme yapilamadi (internet baglantisini kontrol edin).")


def altyazi_parcalari(kelimeler):
    """[(bas, bit, yazi)] - en fazla ~7 kelime / 42 karakter, cumle sonunda bolunur"""
    sozcuk = []
    for bas, sr, yazi, tip in kelimeler:
        if tip == "WordBoundary":
            sozcuk.append((bas, bas + sr, yazi))
        else:                                   # cumle: kelimelere esit bolunur
            k = yazi.split()
            if not k:
                continue
            top = float(sum(len(x) + 1 for x in k))
            t = bas
            for x in k:
                d = sr * (len(x) + 1) / top
                sozcuk.append((t, t + d, x))
                t += d
    out, cur = [], []
    for s in sozcuk:
        cur.append(s)
        yazi = " ".join(x[2] for x in cur)
        if len(cur) >= 7 or len(yazi) >= 42 or re.search(r"[.!?;:]$", s[2]):
            out.append((cur[0][0], cur[-1][1], yazi))
            cur = []
    if cur:
        out.append((cur[0][0], cur[-1][1], " ".join(x[2] for x in cur)))
    # bosluk kalmasin: her parca bir sonrakinin basina kadar ekranda
    son = []
    for i, (a, b, y) in enumerate(out):
        if i + 1 < len(out):
            b = max(b, min(out[i + 1][0], b + 0.6))
        son.append((a, b, y))
    return son


def font_bul(boy):
    for f in ("C:\\Windows\\Fonts\\arialbd.ttf", "C:\\Windows\\Fonts\\segoeuib.ttf", "C:\\Windows\\Fonts\\arial.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"):
        if os.path.exists(f):
            return ImageFont.truetype(f, boy)
    return ImageFont.load_default()


def altyazi_png(yazi, W, H, dosya):
    boy = int(H * 0.058)
    font = font_bul(boy)
    img = Image.new("RGBA", (W, int(H * 0.22)), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # satira bol (genislik %85)
    kel, satir, cur = yazi.split(), [], ""
    for k in kel:
        dene = (cur + " " + k).strip()
        if d.textlength(dene, font=font) > W * 0.85 and cur:
            satir.append(cur)
            cur = k
        else:
            cur = dene
    if cur:
        satir.append(cur)
    satir = satir[-2:]
    y = img.size[1] - len(satir) * int(boy * 1.25) - int(H * 0.01)
    for s in satir:
        w = d.textlength(s, font=font)
        d.text(((W - w) / 2, y), s, font=font, fill=(255, 255, 255, 255), stroke_width=max(3, boy // 14),
               stroke_fill=(0, 0, 0, 255))
        y += int(boy * 1.25)
    img.save(dosya)


# ----------------------------------------------------------------- Pixabay
class Pixabay(object):
    def __init__(self, anahtar, klasor, W):
        self.k, self.kl, self.W = anahtar, klasor, W
        self.kullanilan = set()
        self.ara_onbellek = {}

    def _get(self, url, params):
        for deneme in range(4):
            try:
                r = requests.get(url, params=params, timeout=40)
                if r.status_code == 429:
                    time.sleep(30)
                    continue
                if r.status_code in (400, 401, 403):
                    raise RuntimeError("Pixabay anahtari gecersiz ya da hatali (kod %d)." % r.status_code)
                r.raise_for_status()
                return r.json()
            except RuntimeError:
                raise
            except Exception as h:
                print("   Pixabay baglanti hatasi (%s), tekrar..." % h)
                time.sleep(3 + deneme * 3)
        return {"hits": []}

    def videolar(self, q):
        if ("v", q) in self.ara_onbellek:
            return self.ara_onbellek[("v", q)]
        js = self._get("https://pixabay.com/api/videos/",
                       {"key": self.k, "q": q[:100], "per_page": 30, "safesearch": "true", "order": "popular"})
        out = []
        for h in js.get("hits", []):
            v = h.get("videos", {})
            secim = None
            sira = ("medium", "large", "small") if self.W <= 1280 else ("large", "medium", "small")
            for ad in sira:
                x = v.get(ad) or {}
                if x.get("url") and x.get("width", 0) >= 1280 and x.get("width", 0) <= 2560:
                    secim = x["url"]
                    break
            if not secim:
                for ad in sira:
                    x = v.get(ad) or {}
                    if x.get("url"):
                        secim = x["url"]
                        break
            if secim and float(h.get("duration", 0)) >= PARCA_EN_AZ:
                out.append(("v%d" % h["id"], secim, float(h.get("duration", 0))))
        self.ara_onbellek[("v", q)] = out
        return out

    def fotolar(self, q):
        if ("f", q) in self.ara_onbellek:
            return self.ara_onbellek[("f", q)]
        js = self._get("https://pixabay.com/api/",
                       {"key": self.k, "q": q[:100], "image_type": "photo", "orientation": "horizontal",
                        "per_page": 30, "safesearch": "true", "min_width": 1280})
        out = [("f%d" % h["id"], h.get("largeImageURL") or h.get("webformatURL"), 0.0) for h in js.get("hits", [])
               if h.get("largeImageURL") or h.get("webformatURL")]
        self.ara_onbellek[("f", q)] = out
        return out

    def indir(self, kimlik, url):
        uz = ".mp4" if kimlik.startswith("v") else ".jpg"
        yol = os.path.join(self.kl, kimlik + uz)
        if os.path.exists(yol) and os.path.getsize(yol) > 10000:
            return yol
        for deneme in range(3):
            try:
                with requests.get(url, stream=True, timeout=120) as r:
                    r.raise_for_status()
                    with open(yol + ".part", "wb") as f:
                        for p in r.iter_content(1 << 16):
                            f.write(p)
                os.replace(yol + ".part", yol)
                return yol
            except Exception as h:
                print("   indirme hatasi (%s), tekrar..." % h)
                time.sleep(3)
        return None


# ----------------------------------------------------------------- sahne
def gorsel_sec(px, anahtarlar, gereken):
    """sahne icin (dosya, sure, tur) listesi; once hic kullanilmamis videolar"""
    adaylar = []
    for q in anahtarlar:
        adaylar += [a for a in px.videolar(q) if a[0] not in px.kullanilan and a[0] not in [x[0] for x in adaylar]]
    if not adaylar:
        for q in anahtarlar + ["business", "finance", "city"]:
            adaylar += [a for a in px.fotolar(q) if a[0] not in px.kullanilan and a[0] not in [x[0] for x in adaylar]]
            if adaylar:
                break
    if not adaylar:                                  # hepsi kullanildiysa tekrar kullanilir
        for q in anahtarlar:
            adaylar += px.videolar(q) or px.fotolar(q)
    secilen, top = [], 0.0
    i = 0
    while top < gereken and adaylar and i < 60:
        kimlik, url, ds = adaylar[i % len(adaylar)]
        i += 1
        yol = px.indir(kimlik, url)
        if not yol:
            continue
        px.kullanilan.add(kimlik)
        if kimlik.startswith("v"):
            uz = min(PARCA_EN_FAZLA, max(PARCA_EN_AZ, ds - 0.3))
            secilen.append((yol, uz, "v"))
        else:
            uz = 5.0
            secilen.append((yol, uz, "f"))
        top += uz
    if not secilen:
        raise RuntimeError("Sahne icin gorsel bulunamadi: %s" % ", ".join(anahtarlar))
    return secilen


def parca_hazirla(yol, uz, tur, W, H, cikis):
    olc = "scale=%d:%d:force_original_aspect_ratio=increase,crop=%d:%d,setsar=1" % (W, H, W, H)
    if tur == "v":
        ff(["-t", "%.3f" % uz, "-i", yol, "-vf", olc + ",fps=%d" % FPS, "-an", "-c:v", "libx264", "-preset", "veryfast",
            "-crf", "22", "-pix_fmt", "yuv420p", cikis])
    else:
        n = int(uz * FPS)
        ff(["-loop", "1", "-framerate", str(FPS), "-t", "%.3f" % uz, "-i", yol, "-vf",
            olc + ",zoompan=z='1+0.0007*on':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s=%dx%d:fps=%d" % (W, H, FPS),
            "-frames:v", str(n), "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "22", "-pix_fmt", "yuv420p", cikis])


def sahne_yap(px, anahtarlar, metin, ses, hiz, W, H, gecici, no, altyazi):
    mp3 = os.path.join(gecici, "s%03d.mp3" % no)
    kel = seslendir(metin, ses, hiz, mp3)
    D = sure(mp3) + 0.35                               # sahne sonunda kisa nefes
    secilen = gorsel_sec(px, anahtarlar, D)
    parcalar = []
    kalan = D
    j = 0
    while kalan > 0.05:
        yol, uz, tur = secilen[j % len(secilen)]
        u = min(uz, kalan)
        if 0 < kalan - u < 1.2:                         # cok kisa son parca kalmasin
            u = kalan
        p = os.path.join(gecici, "s%03d_p%02d.mp4" % (no, j))
        parca_hazirla(yol, u, tur, W, H, p)
        parcalar.append(p)
        kalan -= u
        j += 1
    liste = os.path.join(gecici, "s%03d_liste.txt" % no)
    with open(liste, "w", encoding="utf-8") as f:
        for p in parcalar:
            f.write("file '%s'\n" % p.replace("\\", "/"))
    ham = os.path.join(gecici, "s%03d_ham.mp4" % no)
    ff(["-f", "concat", "-safe", "0", "-i", liste, "-c", "copy", ham])
    # altyazi + ses
    cikis = os.path.join(gecici, "s%03d.mp4" % no)
    girdiler = ["-i", ham, "-i", mp3]
    filtre, son = [], "0:v"
    if altyazi:
        parc = altyazi_parcalari(kel)
        for i, (a, b, y) in enumerate(parc):
            png = os.path.join(gecici, "s%03d_a%03d.png" % (no, i))
            altyazi_png(y, W, H, png)
            girdiler += ["-i", png]
            yeni = "v%d" % i
            filtre.append("[%s][%d:v]overlay=x=0:y=H-h-%d:enable='between(t,%.3f,%.3f)'[%s]"
                          % (son, i + 2, int(H * 0.05), a, b, yeni))
            son = yeni
    args = girdiler[:]
    if filtre:
        fdosya = os.path.join(gecici, "s%03d_filtre.txt" % no)
        with open(fdosya, "w", encoding="utf-8") as f:
            f.write(";\n".join(filtre))
        args += ["-filter_complex_script", fdosya, "-map", "[%s]" % son]
    else:
        args += ["-map", "0:v"]
    args += ["-map", "1:a", "-af", "apad", "-t", "%.3f" % D, "-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
             "-pix_fmt", "yuv420p", "-r", str(FPS), "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2", cikis]
    ff(args)
    return cikis, D


def video_yap(px, metin_yol, cikti, onbellek, ses, hiz, W, H, altyazi):
    ad = os.path.splitext(os.path.basename(metin_yol))[0]
    hedef = os.path.join(cikti, ad + ".mp4")
    if os.path.exists(hedef):
        print("[%s] zaten var, atlandi." % ad)
        return
    bilgi, sahneler = metin_oku(metin_yol)
    if not sahneler:
        print("[%s] metinde [VISUAL: ...] sahnesi yok, atlandi." % ad)
        return
    gecici = os.path.join(onbellek, "is_" + re.sub(r"[^A-Za-z0-9_-]", "_", ad))
    if os.path.isdir(gecici):
        shutil.rmtree(gecici, ignore_errors=True)
    os.makedirs(gecici)
    t0 = time.time()
    print("[%s] %d sahne: %s" % (ad, len(sahneler), bilgi["TITLE"]))
    dosyalar, top = [], 0.0
    for i, (anahtar, metin) in enumerate(sahneler):
        d, D = sahne_yap(px, anahtar, metin, ses, hiz, W, H, gecici, i, altyazi)
        dosyalar.append(d)
        top += D
        print("   sahne %d/%d hazir (%.0f sn video, gecen %.0f dk)" % (i + 1, len(sahneler), D, (time.time() - t0) / 60))
    liste = os.path.join(gecici, "liste.txt")
    with open(liste, "w", encoding="utf-8") as f:
        for p in dosyalar:
            f.write("file '%s'\n" % p.replace("\\", "/"))
    ff(["-f", "concat", "-safe", "0", "-i", liste, "-c", "copy", "-movflags", "+faststart", hedef + ".part.mp4"])
    os.replace(hedef + ".part.mp4", hedef)
    with open(os.path.join(cikti, ad + "_youtube.txt"), "w", encoding="utf-8") as f:
        f.write("BASLIK:\n%s\n\nACIKLAMA:\n%s\n\nETIKETLER:\n%s\n" % (
            bilgi["TITLE"], bilgi["DESCRIPTION"].replace("\\n", "\n"), bilgi["TAGS"]))
    shutil.rmtree(gecici, ignore_errors=True)
    print("[%s] HAZIR: %s  (%d dk %d sn video, %.0f dk surdu)" % (ad, hedef, int(top) // 60, int(top) % 60,
                                                                  (time.time() - t0) / 60))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ses", default="en-US-GuyNeural")
    ap.add_argument("--hiz", default="+0%")
    ap.add_argument("--kalite", type=int, default=1080, choices=(720, 1080))
    ap.add_argument("--altyazi", action="store_true")
    args = ap.parse_args()
    W, H = (1920, 1080) if args.kalite == 1080 else (1280, 720)
    ms = masaustu()
    kok = os.path.join(ms, "videolar")
    metinler, cikti, onbellek = [os.path.join(kok, x) for x in ("metinler", "cikti", "onbellek")]
    for k in (metinler, cikti, onbellek):
        if not os.path.isdir(k):
            os.makedirs(k)
    anahtar_yol = os.path.join(ms, "pixabay_anahtar.txt")
    if not os.path.exists(anahtar_yol):
        sys.exit("Masaustunde pixabay_anahtar.txt yok. Pixabay anahtarini bu dosyaya yazip kaydedin.")
    with open(anahtar_yol, encoding="utf-8-sig") as f:
        anahtar = f.read().strip()
    if not anahtar:
        sys.exit("pixabay_anahtar.txt bos.")
    dosyalar = sorted(x for x in os.listdir(metinler) if x.lower().endswith(".txt"))
    if not dosyalar:
        sys.exit("Metin yok. Video metinlerini (.txt) su klasore koyun:\n  %s" % metinler)
    print("Ses: %s  hiz %s  kalite %dp  altyazi %s" % (args.ses, args.hiz, H, "var" if args.altyazi else "yok"))
    print("Metin klasoru: %s\nCikti klasoru: %s\n" % (metinler, cikti))
    px = Pixabay(anahtar, onbellek, W)
    for d in dosyalar:
        try:
            video_yap(px, os.path.join(metinler, d), cikti, onbellek, args.ses, args.hiz, W, H, args.altyazi)
        except Exception as h:
            print("[%s] HATA: %s" % (d, h))
    print("\nBitti. Videolar: %s" % cikti)


if __name__ == "__main__":
    main()
