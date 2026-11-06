# Audio input

How to connect the receiver to the sound card and which factors affect
decoding.

## Signal path

```
NFM receiver ──► headphone output ──► (attenuator) ──► USB sound card mic input ──► ALSA
```

Sound card: GeneralPlus USB Audio Device, USB `1b3f:2008`.

| Parameter | Value |
|---|---|
| Capture format | mono, S16_LE |
| Sample rates | 44100 and 48000 Hz only |
| Gain control | `Mic` (capture), range 0–30, 100% = +33 dB |
| AGC | `Auto Gain Control`, off by default |

multimon-ng requires 22050 Hz; ALSA `plughw` converts the card's rate.

The card has no serial number. It is identified by VID:PID in
`/sys/class/sound` (`/proc/asound` is not available inside containers), not by
its ALSA card number, which can change after re-plugging. Several identical
cards would have to be distinguished by USB port, which is not implemented.

## Echo

The DSP-50 controller feeds the tones electrically into the transmitter, and
the receiver outputs them electrically on the headphone jack, so this path has
no room reverberation. Radio multipath delays are in the microsecond range and
FM captures the stronger signal.

The echo limitation described in
[STQC.md](https://github.com/marmurek/multimon-ng/blob/feature/stqc/STQC.md)
applies to loudspeaker audio recorded in a room, not to a receiver connected
by cable.

## Input level

The microphone input is very sensitive and a headphone output delivers a high
level. At the card's default gain (+33 dB) the signal will clip.

- Tone peaks should be around −6 dBFS.
- The card's AGC must stay off, because it changes the level within a
  sequence.
- If the signal clips even at the minimum `Mic` gain, an attenuator (voltage
  divider) is needed in the cable.

The decoder tolerates clipping (+30 dB overdrive is tested), but harmonics
reduce the margin against noise.

## Squelch

Opening the receiver's squelch can cut the beginning of the first tone. The
decoder needs about 30 ms of clean tone plus a 40 ms analysis window. The
first tone is almost always tone 4 (2105 Hz); losing it shortens the sequence
but does not change its value, and the address still forms a call with the
following command.

Start with the squelch open or set low. Continuous noise does not produce
false detections (tested with white and band-limited noise).

## Weak signal

On FM a weak signal shows up as noise, not as a lower level. The decoder works
at about +4 dB SNR in the 300–3000 Hz band (tested), and in measurements down
to about −2 dB.

## Receiver characteristics

De-emphasis and output filters of the receiver can make the 980 Hz and
2105 Hz tones differ in level, estimated at a few dB. This is within the
decoder's thresholds (−12 dB level limit) but should be measured on the actual
path.

The receiver must be analog (NFM). Digital radios (DMR) pass audio through a
speech codec that distorts the tones.

## Mains interference

A ground loop between the radio, the computer and the power supply can add
50 Hz hum and its harmonics. The hum is far from the STQC tones, but at a high
level it reduces the tone's share of the total signal energy. A common power
supply or an audio isolation transformer helps.

## Verifying the path

The first recording from the actual receiver should be checked like the
existing samples:

- deviation of the tone frequencies from nominal (up to ±6 Hz so far),
- level of the tones and of the background between them,
- tone durations and the pause between address and command,
- decoding result matching a `gen-ng` resynthesis of the sequences.
