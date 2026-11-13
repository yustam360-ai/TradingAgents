# EA_MONEY_ROBOT - bekleyen kararlar

## Cikarilacak semboller (kullanici karari, 11.11.2026)
3 aylik test (2026.08.01 - 2026.11.09, EA_MONEY_ROBOT 2.01, gercek tik, rastgele gecikme) sonucunda zararda kalanlar.
UYGULANDI: EA_MONEY_ROBOT / EAROBOT_ICT 2.02 (11.11.2026). Kesisim 26 sembol/26 kural, ICT 78 sembol.

ICT (4):      SNOW, ASML, AUDCHF, ALVG
KESISIM (13): EURNOK, MANUSD, ALVG, GOOG, EURNZD, AZN, MSFT, IBM, ZM, SAN, T, BA, LMT

Not: ALVG iki listede de var (toplam 17 kayit, 16 farkli sembol).

## Test ozeti (1x risk, 15 $)
- Net +8.117 $ (ICT +5.789, Kesisim +2.328), kar faktoru 1.60, max dusus 360 $
- En kotu gun 29.10.2026 -240 $ (GOOG kazanc acilisi gap, tek islem -288 $)
- Buyuk kayiplarin tamami Kesisim'in gece tutulan hisseleri (acilis gap)

## 13.11.2026 - Yarin yapilacaklar (kullanici "yaz" deyince)
Tek dosyalik Python programi (MT5'ten veri okur, islem acmaz), semboller: BTCUSD, XAUUSD (+ istenirse US100.cash, EURUSD):
1. Seviye turu testi: PDH/PWH, Asya, Londra, NY PM, esit tepeler, 1S/4S/gunluk FVG. Ozellikten sonuca olcum (kac kez olustu, sonra 2R/3R yukari-asagi, rastgele noktaya gore fark).
2. Long / short ayri.
3. "Sadece FVG" taban cizgisi (supurme ve MSS olmadan) ile "supurme + MSS + FVG" kiyasi.
4. Sonuclar Ocak-Temmuz ve Agustos-Kasim yan yana; iki donemde de tutan gercek sayilir.
5. Sabit kural (Ekin'in videosu: MSS govde kapanisi, FVG ortasindan giris, swing govdesine stop, 2R/3R), sembol bazli ince ayar YOK.

Bulgular (12-13.11): Ocak-Temmuz testi -466 $ (AZN veri hatasi haric), ICT -2.474 / Kesisim -779; Agustos-Kasim +8.117 $. Long/short arasinda tutarli fark yok.
Bekleyen: Kesisim hisselerini NY 16:00'da kapatma, DIS GE CVX META AUDCHF cikarma karari, Golden Cross EA test raporu (kullanici calistiriyor).
