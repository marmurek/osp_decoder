# Wejście audio

Opis podłączenia odbiornika radiowego do karty dźwiękowej oraz czynników, które
wpływają na skuteczność dekodowania.

## Tor sygnału

```
odbiornik NFM ──► wyjście słuchawkowe ──► (tłumik) ──► wejście mikrofonowe karty USB ──► ALSA
```

Docelowa karta: GeneralPlus USB Audio Device, USB `1b3f:2008`.

| Parametr | Wartość |
|---|---|
| Nagrywanie | mono, S16_LE |
| Częstotliwości próbkowania | tylko 44100 i 48000 Hz |
| Regulacja wzmocnienia | `Mic` (capture), zakres 0–30, 100% = +33 dB |
| AGC | `Auto Gain Control`, domyślnie wyłączone |

multimon-ng wymaga 22050 Hz. Przy 44100 Hz konwersja polega na zmniejszeniu
częstotliwości dokładnie o połowę, więc jest tania obliczeniowo.

Karta nie ma numeru seryjnego. Jest identyfikowana po VID:PID
(`/proc/asound/card*/usbid`), a nie po numerze karty ALSA, który może się
zmieniać po ponownym podłączeniu. Przy kilku identycznych kartach trzeba je
rozróżniać po porcie USB.

## Echo

Sterownik DSP-50 podaje tony elektrycznie na wejście nadajnika, a odbiornik
oddaje je elektrycznie na wyjście słuchawkowe. W tym torze nie ma pogłosu
pomieszczenia. Odbicia fal radiowych dają opóźnienia rzędu mikrosekund,
a w FM silniejszy sygnał i tak przejmuje odbiornik.

Ograniczenie opisane w
[STQC.md](https://github.com/marmurek/multimon-ng/blob/feature/stqc/STQC.md)
(ogon echa w przerwie między adresem a komendą) dotyczy nagrań z głośnika
w pomieszczeniu, a nie bezpośredniego podłączenia odbiornika.

## Poziom wejścia

Wejście mikrofonowe jest bardzo czułe, a wyjście słuchawkowe radia daje
sygnał o dużym poziomie. Przy domyślnym wzmocnieniu karty (+33 dB) sygnał
będzie przesterowany.

- Szczyty tonów powinny wypadać około −6 dBFS.
- AGC karty musi pozostać wyłączone, bo zmienia poziom w trakcie sekwencji.
- Jeśli przesterowanie występuje nawet przy minimalnym wzmocnieniu `Mic`,
  potrzebny jest tłumik (dzielnik napięcia) na kablu.

Dekoder toleruje przesterowanie (test +30 dB przechodzi), ale harmoniczne
zmniejszają margines przy jednoczesnym szumie.

## Blokada szumów (squelch)

Otwieranie blokady szumów może uciąć początek pierwszego tonu. Dekoder
potrzebuje około 30 ms czystego tonu oraz 40 ms okna analizy. Pierwszym tonem
jest prawie zawsze ton 4 (2105 Hz). Jego utrata zmienia długość sekwencji,
ale nie wartość.

Zalecana konfiguracja początkowa: blokada szumów wyłączona albo ustawiona
nisko. Ciągły szum nie powoduje fałszywych wykryć (sprawdzone testami na
szumie białym i paśmowym).

## Słaby sygnał

W FM słaby sygnał objawia się szumem, a nie spadkiem głośności. Dekoder
działa przy SNR około +4 dB w paśmie 300–3000 Hz (test), a w pomiarach także
przy około −2 dB.

## Charakterystyka odbiornika

Deemfaza i filtry wyjściowe odbiornika mogą powodować różnicę poziomów między
tonami 980 Hz i 2105 Hz, szacunkowo do kilku dB. Mieści się to w progach
dekodera (próg poziomu −12 dB), ale należy to zmierzyć na rzeczywistym torze.

Odbiornik musi być analogowy (NFM). Radiotelefony cyfrowe (DMR) przepuszczają
dźwięk przez kodek mowy, który zniekształca tony.

## Zakłócenia sieciowe

Pętla masy między radiem, komputerem i zasilaczem może wprowadzić brum 50 Hz
i jego harmoniczne. Brum leży daleko od tonów STQC, ale przy dużym poziomie
zmniejsza udział tonu w całkowitej energii sygnału. Pomaga wspólne zasilanie
albo transformator separujący audio.

## Weryfikacja toru

Pierwsze nagranie z rzeczywistego odbiornika należy sprawdzić tak samo jak
dotychczasowe próbki:

- odchyłka częstotliwości tonów od nominalnych (dotychczas do ±6 Hz),
- poziom tonów i poziom tła między tonami,
- długość tonów i przerwy między adresem a komendą,
- zgodność wyniku dekodowania z resyntezą sekwencji przez `gen-ng`.
