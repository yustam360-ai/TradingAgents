# -*- coding: utf-8 -*-
"""
TRANSKRIPT AL - YouTube oynatma listesinin (ya da tek videonun) butun transkriptlerini
                tek bir metin dosyasi olarak MASAUSTUNE yazar.  Video INDIRILMEZ.

Bir kere kurulum:
    py -3.8 -m pip install -U yt-dlp youtube-transcript-api

Kullanim (komut satirindan):
    py -3.8 Transkript_Al.py
    -> "Oynatma listesi ya da video linki:" sorulur, linki yapistirip Enter'a basin.
ya da linki dogrudan verin:
    py -3.8 Transkript_Al.py "https://www.youtube.com/playlist?list=...."

- Dil: videoda KONUSULAN dil kullanilir (Ingilizce video -> Ingilizce, Turkce video -> Turkce). Ceviri yapilmaz.
- Her satirin basinda videodaki zaman yazar: [12:34]
- Dosya: Masaustu / <oynatma listesi adi>.txt  (Bolum 1, Bolum 2 ... sirasiyla)
- "Kacinci videodan baslasin?" sorusu: yarim kalan listeye kaldigi yerden devam etmek icin.
- YouTube engellerse 30 / 60 / 90 sn bekleyip tekrar dener; alinamazsa sebebini yazar.
"""
from __future__ import print_function

import os
import re
import sys
import time

import json
import urllib.request

try:
    import yt_dlp
except ImportError:
    yt_dlp = None
try:
    from youtube_transcript_api import YouTubeTranscriptApi
except ImportError:
    sys.exit("youtube-transcript-api yok. Kurun:  py -3.8 -m pip install -U yt-dlp youtube-transcript-api")


def masaustu():
    adaylar = []
    up = os.environ.get("USERPROFILE") or os.path.expanduser("~")
    od = os.environ.get("OneDrive")
    if od:
        adaylar += [os.path.join(od, "Desktop"), os.path.join(od, "Masaüstü")]
    adaylar += [os.path.join(up, "Desktop"), os.path.join(up, "Masaüstü"), os.path.expanduser("~/Desktop")]
    for a in adaylar:
        if os.path.isdir(a):
            return a
    return os.getcwd()


def temiz_ad(s):
    s = re.sub(r'[\\/:*?"<>|]+', " ", s or "transkript").strip()
    return s[:120] or "transkript"


def zaman(sn):
    sn = int(sn)
    s, d = sn // 3600, (sn % 3600) // 60
    return "%d:%02d:%02d" % (s, d, sn % 60) if s else "%02d:%02d" % (d, sn % 60)


def _ara(o, anahtar, out):
    if isinstance(o, dict):
        for k, v in o.items():
            if k == anahtar:
                out.append(v)
            _ara(v, anahtar, out)
    elif isinstance(o, list):
        for v in o:
            _ara(v, anahtar, out)


def html_videolar(link):
    """yt-dlp calismazsa: sayfadan oku (oynatma listesinde ilk ~100 video)"""
    req = urllib.request.Request(link, headers={"User-Agent": "Mozilla/5.0", "Accept-Language": "tr,en"})
    html = urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "ignore")
    t = re.search(r"<title>(.*?)</title>", html, re.S)
    baslik = re.sub(r"\s*-\s*YouTube\s*$", "", t.group(1).strip()) if t else "transkript"
    m = re.search(r"var ytInitialData\s*=\s*(\{.*?\});\s*</script>", html, re.S)
    liste = []
    if m and "list=" in link:
        veri = json.loads(m.group(1))
        rend = []
        _ara(veri, "playlistVideoRenderer", rend)
        _ara(veri, "playlistPanelVideoRenderer", rend)
        for r in rend:
            vid = r.get("videoId")
            runs = (r.get("title") or {}).get("runs") or [{}]
            ad = runs[0].get("text") or (r.get("title") or {}).get("simpleText") or vid
            if vid and vid not in [x[0] for x in liste]:
                liste.append((vid, ad))
        if not liste:                                   # yeni sayfa duzeni: lockupViewModel
            lk = []
            _ara(veri, "lockupViewModel", lk)
            for r in lk:
                vid = r.get("contentId")
                bas = []
                _ara(r, "title", bas)
                ad = vid
                for b in bas:
                    if isinstance(b, dict) and b.get("content"):
                        ad = b["content"]
                        break
                if vid and len(vid) == 11 and vid not in [x[0] for x in liste]:
                    liste.append((vid, ad))
    if not liste:
        v = re.search(r"(?:v=|youtu\.be/|shorts/)([A-Za-z0-9_-]{11})", link)
        if v:
            liste = [(v.group(1), baslik)]
    return baslik, liste


def videolar(link):
    lid = re.search(r"[?&]list=([A-Za-z0-9_-]+)", link)
    if lid:                                             # video+liste linki -> sadece liste linki
        link = "https://www.youtube.com/playlist?list=" + lid.group(1)
    sonuc = None
    if yt_dlp is not None:
        try:
            sonuc = _ytdlp_videolar(link)
        except Exception:
            sonuc = None
    if not sonuc or not sonuc[1]:
        sonuc = html_videolar(link)
    return sonuc


def _ytdlp_videolar(link):
    ayar = {"quiet": True, "extract_flat": "in_playlist", "skip_download": True, "ignoreerrors": True}
    with yt_dlp.YoutubeDL(ayar) as ydl:
        bilgi = ydl.extract_info(link, download=False)
    if bilgi is None:
        raise RuntimeError("yt-dlp okuyamadi")
    if bilgi.get("_type") == "playlist" or "entries" in bilgi:
        liste = []
        for e in bilgi.get("entries") or []:
            if e and e.get("id"):
                liste.append((e["id"], e.get("title") or e["id"]))
        return bilgi.get("title") or "oynatma_listesi", liste
    return bilgi.get("title") or bilgi.get("id"), [(bilgi["id"], bilgi.get("title") or bilgi["id"])]


def transkript_listesi(vid):
    if hasattr(YouTubeTranscriptApi, "list_transcripts"):          # eski surum
        return YouTubeTranscriptApi.list_transcripts(vid)
    return YouTubeTranscriptApi().list(vid)                         # yeni surum (1.x)


def transkript(vid):
    """konusulan dildeki transkript: (dil, [(baslangic_sn, metin)])"""
    tl = list(transkript_listesi(vid))
    if not tl:
        return None, []
    otomatik = [t for t in tl if t.is_generated]
    elle = [t for t in tl if not t.is_generated]
    secilen = None
    if otomatik:                                                     # otomatik altyazi = konusulan dil
        dil = otomatik[0].language_code
        ayni = [t for t in elle if t.language_code.split("-")[0] == dil.split("-")[0]]
        secilen = ayni[0] if ayni else otomatik[0]
    else:
        secilen = elle[0]
    veri = secilen.fetch()
    satir = []
    for p in veri:
        if isinstance(p, dict):
            satir.append((p.get("start", 0), p.get("text", "")))
        else:
            satir.append((getattr(p, "start", 0), getattr(p, "text", "")))
    return secilen.language_code, satir


def main():
    link = sys.argv[1] if len(sys.argv) > 1 else ""
    if not link:
        try:
            link = input("Oynatma listesi ya da video linki: ").strip()
        except EOFError:
            link = ""
    if not link:
        sys.exit("Link verilmedi.")
    print("Liste okunuyor...")
    baslik, liste = videolar(link)
    if not liste:
        sys.exit("Listede video bulunamadi.")
    yol = os.path.join(masaustu(), temiz_ad(baslik) + ".txt")
    k = 2
    while os.path.exists(yol):
        yol = os.path.join(masaustu(), "%s (%d).txt" % (temiz_ad(baslik), k))
        k += 1
    print("%d video bulundu: %s" % (len(liste), baslik))
    bas_no = 1
    if len(liste) > 1:
        try:
            g = input("Kacinci videodan baslasin? (bos birakip Enter = 1): ").strip()
            bas_no = max(1, min(len(liste), int(g))) if g else 1
        except (EOFError, ValueError):
            bas_no = 1
    if bas_no > 1:
        yol = yol[:-4] + " (%d-%d).txt" % (bas_no, len(liste))
        k = 2
        while os.path.exists(yol):
            yol = yol[:-4] + " %d.txt" % k
            k += 1
    yok = []
    with open(yol, "w", encoding="utf-8") as f:
        f.write("%s\n%s\nToplam %d video\n\n" % (baslik, link, len(liste)))
        for n, (vid, ad) in enumerate(liste, 1):
            if n < bas_no:
                continue
            sonuc = None
            for deneme in range(4):
                try:
                    sonuc = transkript(vid)
                    break
                except Exception as hata:
                    satirlar_h = [x.strip() for x in str(hata).splitlines() if x.strip()]
                    neden = type(hata).__name__ + (": " + " | ".join(satirlar_h[:3])[:300] if satirlar_h else "")
                    sonuc = ("HATA", neden)
                    if deneme < 3:
                        bekle = 30 * (deneme + 1)
                        print("   [%d] hata: %s -> %d sn bekleyip tekrar denenecek" % (n, type(hata).__name__, bekle))
                        time.sleep(bekle)
            f.write("=" * 100 + "\n")
            f.write("BOLUM %d - %s\nhttps://www.youtube.com/watch?v=%s\n" % (n, ad, vid))
            if sonuc is None or sonuc[0] is None or sonuc[0] == "HATA" or not sonuc[1]:
                neden = sonuc[1] if sonuc and sonuc[0] == "HATA" else "transkript yok"
                f.write("(TRANSKRIPT ALINAMADI: %s)\n\n" % neden)
                yok.append("Bolum %d - %s (%s)" % (n, ad, neden))
                print("[%d/%d] %s : ALINAMADI -> %s" % (n, len(liste), ad[:60], neden[:120]))
                continue
            dil, satirlar = sonuc
            f.write("Dil: %s\n" % dil)
            f.write("=" * 100 + "\n")
            for bas, metin in satirlar:
                metin = " ".join((metin or "").split())
                if metin:
                    f.write("[%s] %s\n" % (zaman(bas), metin))
            f.write("\n")
            f.flush()
            print("[%d/%d] %s : tamam (%s, %d satir)" % (n, len(liste), ad[:60], dil, len(satirlar)))
            time.sleep(3)
        if yok:
            f.write("=" * 100 + "\nTRANSKRIPTI ALINAMAYAN VIDEOLAR:\n" + "\n".join(yok) + "\n")
    print("\nBitti. Dosya: %s" % yol)
    if yok:
        print("%d videonun transkripti alinamadi (dosyanin sonunda listeli)." % len(yok))


if __name__ == "__main__":
    main()
