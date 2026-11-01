"""Gera a trilha sonora original (sintetizada) do vídeo promocional.

Rock em Mi menor a 120 BPM, com quebra para guitarra limpa e ambiência
na cena do louvor. Saída: trilha.wav (estéreo, 44,1 kHz).
"""
import sys
import wave

import numpy as np

SR = 44100
BPM = 120
BEAT = 60 / BPM
EIGHTH = BEAT / 2
TOTAL = 37.0
E2 = 82.41
rng = np.random.default_rng(7)


def hz(semi, base=E2):
    return base * 2 ** (semi / 12)


def spectral_filter(x, lo=None, hi=None, order=2):
    """Filtro passa-faixa suave no domínio da frequência."""
    n = len(x)
    spec = np.fft.rfft(x)
    f = np.fft.rfftfreq(n, 1 / SR)
    resp = np.ones_like(f)
    if hi:
        resp *= 1 / np.sqrt(1 + (f / hi) ** (2 * order))
    if lo:
        resp *= 1 / np.sqrt(1 + (lo / np.maximum(f, 1e-3)) ** (2 * order))
    return np.fft.irfft(spec * resp, n)


def saw(freq, t, detune=0.0):
    ph = (t * freq * (1 + detune) + rng.random()) % 1.0
    return 2 * ph - 1


def power_chord(semi, dur, muted=False, ring=None, gain=9.0):
    """Acorde de quinta distorcido (fundamental, quinta e oitava)."""
    length = ring if ring else dur
    t = np.arange(int(length * SR)) / SR
    f = hz(semi)
    sig = np.zeros_like(t)
    for mult, amp in ((1, 1.0), (1.4983, 0.8), (2, 0.6)):
        for det in (-0.003, 0.003):
            sig += amp * saw(f * mult, t, det)
    sig /= 4.8
    if muted:
        env = np.exp(-t / 0.07)
        sig = spectral_filter(sig, hi=900)
    else:
        env = np.exp(-t / (1.4 if ring else 0.6))
    env *= np.minimum(1, t / 0.004)
    tail = int(0.012 * SR)
    if not ring and len(env) > tail:
        env[-tail:] *= np.linspace(1, 0, tail)
    out = np.tanh(gain * sig * env)
    out = spectral_filter(out, lo=90, hi=4200, order=3)  # caixa 4x12 simplificada
    return out * (0.75 if muted else 1.0)


def clean_note(freq, dur):
    t = np.arange(int(dur * SR)) / SR
    sig = (np.sin(2 * np.pi * freq * t) + 0.35 * np.sin(4 * np.pi * freq * t)
           + 0.12 * np.sin(6 * np.pi * freq * t))
    env = np.exp(-t / 1.1) * np.minimum(1, t / 0.003)
    return sig * env * 0.5


def kick():
    t = np.arange(int(0.45 * SR)) / SR
    f = 50 + 110 * np.exp(-t / 0.035)
    ph = 2 * np.pi * np.cumsum(f) / SR
    return np.sin(ph) * np.exp(-t / 0.16) * 1.1


def snare():
    t = np.arange(int(0.3 * SR)) / SR
    body = np.sin(2 * np.pi * 190 * t) * np.exp(-t / 0.05)
    noise = spectral_filter(rng.standard_normal(len(t)), lo=1500, hi=9000) * np.exp(-t / 0.09)
    return 0.6 * body + 0.9 * noise


def hat(open_=False):
    t = np.arange(int((0.25 if open_ else 0.06) * SR)) / SR
    n = spectral_filter(rng.standard_normal(len(t)), lo=7000)
    return n * np.exp(-t / (0.09 if open_ else 0.015)) * 0.35


def crash():
    t = np.arange(int(2.2 * SR)) / SR
    n = spectral_filter(rng.standard_normal(len(t)), lo=4000)
    return n * np.exp(-t / 0.7) * 0.4


class Track:
    def __init__(self):
        self.L = np.zeros(int(TOTAL * SR) + SR * 3)
        self.R = np.zeros_like(self.L)

    def add(self, sig, at, gain=1.0, pan=0.0):
        i = int(at * SR)
        j = min(i + len(sig), len(self.L))
        s = sig[: j - i] * gain
        self.L[i:j] += s * np.sqrt((1 - pan) / 2) * 1.414
        self.R[i:j] += s * np.sqrt((1 + pan) / 2) * 1.414


def riff_bar(tr, start, variant):
    """Uma frase de dois compassos em colcheias (m = abafada, None = pausa)."""
    bars = {
        0: [(0, 'm'), (0, 'm'), (0, 'o'), None, (0, 'm'), (0, 'm'), (3, 'o'), (5, 'o')],
        1: [(0, 'm'), (0, 'm'), (0, 'o'), None, (0, 'm'), (0, 'm'), (6, 'o'), (5, 'o')],
        2: [(-2, 'L'), None, None, None, (-4, 'L'), None, (-2, 'o'), (0, 'o')],
    }
    for k, ev in enumerate(bars[variant]):
        if ev is None:
            continue
        semi, kind = ev
        at = start + k * EIGHTH
        dur = EIGHTH * (4 if kind == 'L' else 1)
        # Dobra de guitarra: duas execuções levemente diferentes, abertas no estéreo.
        for pan, jitter in ((-0.85, 0.0), (0.85, 0.006)):
            tr.add(power_chord(semi, dur, muted=(kind == 'm')), at + jitter, 0.42, pan)
        tr.add(spectral_filter(power_chord(semi - 12, dur, muted=(kind == 'm'), gain=3), hi=400),
               at, 0.5)  # baixo


def drums_bar(tr, start, fill=False):
    for b in range(4):
        t0 = start + b * BEAT
        if b in (0, 2):
            tr.add(kick(), t0, 0.9)
        if b in (1, 3):
            tr.add(snare(), t0, 0.75)
        if b == 2:
            tr.add(kick(), t0 - EIGHTH, 0.7)
        for h in range(2):
            tr.add(hat(open_=(h == 1 and b == 3)), t0 + h * EIGHTH, 0.8, 0.3)
    if fill:
        for k in range(4):
            tr.add(snare(), start + 3 * BEAT + k * BEAT / 4, 0.5 + 0.1 * k)


def build():
    tr = Track()
    # 0–3 s — gancho: acorde cheio soando + subida de ruído.
    for pan in (-0.8, 0.8):
        tr.add(power_chord(0, 3.0, ring=3.0), 0.0, 0.5, pan)
    tr.add(crash(), 0.0, 0.8)
    # 3–6 s — tensão: abafadas em semicolcheia e caixa acelerando.
    for k in range(12):
        at = 3.0 + k * EIGHTH
        for pan in (-0.8, 0.8):
            tr.add(power_chord(0, EIGHTH, muted=True), at, 0.32 + 0.015 * k, pan)
        tr.add(hat(), at, 0.8)
    for k in range(8):
        tr.add(snare(), 5.0 + k * BEAT / 4, 0.35 + 0.07 * k)
    t = np.arange(int(3.0 * SR)) / SR
    tr.add(spectral_filter(rng.standard_normal(len(t)), lo=3000) * (t / 3.0) ** 3 * 0.35, 3.0)

    # 6–28 s — riff principal (compassos de 2 s).
    order = [0, 1, 0, 2]
    for i, start in enumerate(np.arange(6.0, 28.0, 2.0)):
        riff_bar(tr, start, order[i % 4])
        drums_bar(tr, start, fill=(order[i % 4] == 2))
        if i % 4 == 0:
            tr.add(crash(), start, 0.7)

    # 28–30 s — louvor: guitarra limpa com eco e colchão.
    arp = [hz(s, 164.8) for s in (0, 7, 14, 15, 19, 14, 7, 3)]
    for k, f in enumerate(arp):
        at = 28.0 + k * EIGHTH
        n = clean_note(f, 2.0)
        for rep in range(5):
            tr.add(n, at + rep * 0.375, 0.5 * 0.45 ** rep, (-0.5, 0.5)[rep % 2])
    t = np.arange(int(2.6 * SR)) / SR
    pad = sum(np.sin(2 * np.pi * hz(s, 164.8) * t) for s in (0, 7, 10, 14)) / 4
    tr.add(pad * np.minimum(1, t / 0.6) * np.exp(-t / 2.5) * 0.25, 28.0)

    # 30–34 s — retorno ao riff para a chamada final.
    for i, start in enumerate((30.0, 32.0)):
        riff_bar(tr, start, (0, 2)[i])
        drums_bar(tr, start, fill=(i == 1))
    tr.add(crash(), 30.0, 0.8)
    # 34 s — acorde final soando até o fim.
    for pan in (-0.8, 0.8):
        tr.add(power_chord(0, 3.0, ring=3.0), 34.0, 0.5, pan)
    tr.add(crash(), 34.0, 0.9)
    tr.add(kick(), 34.0, 1.0)

    mix = np.stack([tr.L, tr.R])[:, : int(TOTAL * SR)]
    mix /= np.max(np.abs(mix)) + 1e-9
    mix = np.tanh(1.6 * mix) / np.tanh(1.6)  # limitador suave
    fade = int(1.5 * SR)
    mix[:, -fade:] *= np.linspace(1, 0, fade)
    return (mix.T * 0.92 * 32767).astype(np.int16)


if __name__ == '__main__':
    out = sys.argv[1] if len(sys.argv) > 1 else 'trilha.wav'
    data = build()
    with wave.open(out, 'wb') as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(data.tobytes())
    print('ok', out, data.shape[0] / SR, 's')
