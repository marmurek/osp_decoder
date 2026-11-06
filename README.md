# OSP Radio Decoder

Lekki dekoder sygnalizacji selektywnego wywołania odbieranej z radia przez kartę
dźwiękową. Wykryte sekwencje są publikowane jako zdarzenia JSON do niezależnych
aplikacji odbiorczych przez WebSocket.

> **Status:** projekt we wczesnej fazie (etap 1: weryfikacja dekodera i platformy).
> Interfejsy i format zdarzeń mogą się jeszcze zmienić.

## Założenia

- Platforma docelowa: Raspberry Pi 1 Model B (ARMv6, 32-bit) z DietPi.
  Platforma testowa: PC z Linuksem.
- Dekodowanie wykonuje [multimon-ng](https://github.com/EliasOenal/multimon-ng).
  Projekt nie implementuje własnych algorytmów dekodowania sygnałów.
- Obsługiwane protokoły: wszystkie protokoły tonowe dostępne w multimon-ng
  (DTMF, ZVEI1/2/3, DZVEI, PZVEI, CCIR, EEA, EIA) oraz STQC, stosowany
  w polskich systemach alarmowania OSP (Digitex DSP-50, DSP-52L).
- Wejście audio: karta USB przez ALSA (identyfikowana po USB VID:PID, nie po
  numerze karty) albo pliki WAV podczas testów. Audio nie jest zapisywane na dysk.
  Podłączenie odbiornika i ustawienia toru audio opisuje
  [docs/audio-input.md](docs/audio-input.md).
- Dekoder nie interpretuje kodów i nie przypisuje ich do jednostek. Zajmuje się
  tym osobna aplikacja odbiorcza, która nie jest częścią tego projektu.

## Architektura

```
ALSA / WAV ──► audio capture ──► multimon-ng ──► event parser ──► WebSocket publisher ──► odbiorcy
                    (arecord / sox)                                  (broadcast JSON)
```

Dekoder działa jako serwer WebSocket i rozsyła każde zdarzenie do wszystkich
podłączonych odbiorców. Odbiorca może się rozłączyć i połączyć ponownie;
brak odbiorców nie wstrzymuje dekodowania. Zdarzenia nieodebrane przez
odbiorcę nie są ponawiane.

## Format zdarzeń

Każda wiadomość WebSocket zawiera jedno kompletne zdarzenie JSON. Schemat jest
wersjonowany polem `schema_version`. Przykład:

```json
{
  "schema_version": 1,
  "event": "sequence_detected",
  "event_id": "4f0c2c4e-8a7e-4d3e-9d1b-1f2a3b4c5d6e",
  "protocol": "stqc",
  "sequence": "4204123",
  "timestamp": "2026-11-05T10:31:00.120Z",
  "source": "radio_1"
}
```

- `sequence` jest zawsze stringiem; zera wiodące są zachowane.
- `timestamp` oznacza moment zakończenia wykrywania sekwencji (UTC).
- `protocol` identyfikuje sposób kodowania; nowe protokoły nie zmieniają
  struktury zdarzenia.

Pełna specyfikacja schematu powstanie w katalogu `schema/`.

## Uruchamianie

Projekt jest dystrybuowany jako obraz Docker budowany dla `linux/amd64`
oraz `linux/arm/v6`. Instrukcje budowania i uruchamiania zostaną dodane
wraz z pierwszą działającą wersją.

## Licencja

Copyright (C) 2026 Wojciech Marmurowicz

Projekt jest udostępniony na licencji GNU General Public License w wersji 3
lub (według uznania) dowolnej późniejszej (GPL-3.0-or-later). Pełny tekst
licencji znajduje się w pliku [LICENSE](LICENSE).

Program jest rozpowszechniany bez jakiejkolwiek gwarancji (sekcje 15 i 16
licencji). Każdy może go używać, modyfikować i rozpowszechniać; zmodyfikowane
wersje rozpowszechniane dalej muszą pozostać na tej samej licencji.

Obraz Docker zawiera [multimon-ng](https://github.com/marmurek/multimon-ng)
(GPL-2.0-or-later) z demodulatorem STQC opartym na dekoderze
[Jacka Lipkowskiego SQ5BPF](https://github.com/sq5bpf/multimon-ng-stqc).
