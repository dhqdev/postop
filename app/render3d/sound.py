"""Som gerado por código: efeitos sincronizados com as ações e ambiente de cada cenário.

Nada de arquivos de áudio nem IA: tudo é sintetizado com numpy (osciladores, ruído filtrado
por FFT e envelopes). `scene_audio` olha os atores da cena (o que cada um faz e quando) e
monta a trilha de efeitos + ambiente; `mix_soundtrack` junta as cenas com a narração e a
música (que abaixa sozinha quando a narração fala).
"""

from __future__ import annotations

import math
import subprocess
import wave
from pathlib import Path

import numpy as np

SR = 44100
F32 = np.float32
TAU = math.tau


# ------------------------------------------------------------------ blocos básicos
def _n(sec: float) -> int:
    return max(1, int(round(sec * SR)))


def _t(n: int) -> np.ndarray:
    return np.arange(n, dtype=F32) / SR


def env(n: int, decay: float, attack: float = 0.002) -> np.ndarray:
    t = _t(n)
    return (np.minimum(1.0, t / max(attack, 1e-4)) * np.exp(-t / max(decay, 1e-4))).astype(F32)


def swell(n: int, attack: float, release: float) -> np.ndarray:
    t = _t(n)
    total = n / SR
    a = np.clip(t / max(attack, 1e-4), 0, 1)
    r = np.clip((total - t) / max(release, 1e-4), 0, 1)
    return (a * r).astype(F32)


def osc(freq, n: int, phase: float = 0.0) -> np.ndarray:
    f = np.broadcast_to(np.asarray(freq, np.float64), (n,))
    return np.sin(TAU * np.cumsum(f) / SR + phase).astype(F32)


def glide(f0: float, f1: float, n: int) -> np.ndarray:
    """Frequência indo de f0 a f1 (exponencial)."""
    return (f0 * (f1 / f0) ** np.linspace(0, 1, n)).astype(F32)


def noise(n: int, rng: np.random.Generator, color: str = "white") -> np.ndarray:
    w = rng.standard_normal(n)
    if color == "white" or n < 4:
        return w.astype(F32)
    spec = np.fft.rfft(w)
    f = np.fft.rfftfreq(n, 1 / SR)
    f[0] = f[1]
    spec = spec / (np.sqrt(f) if color == "pink" else f)
    out = np.fft.irfft(spec, n)
    return (out / max(float(np.std(out)), 1e-9)).astype(F32)


def band(x: np.ndarray, lo: float | None = None, hi: float | None = None, order: int = 2) -> np.ndarray:
    """Filtro passa-faixa suave (resposta tipo Butterworth aplicada na FFT)."""
    n = len(x)
    if n < 4:
        return x
    spec = np.fft.rfft(x)
    f = np.fft.rfftfreq(n, 1 / SR)
    g = np.ones_like(f)
    if lo:
        g /= 1 + (lo / np.maximum(f, 1.0)) ** (2 * order)
    if hi:
        g /= 1 + (f / hi) ** (2 * order)
    return np.fft.irfft(spec * g, n).astype(F32)


def norm(x: np.ndarray, peak: float = 1.0) -> np.ndarray:
    m = float(np.max(np.abs(x))) if len(x) else 0.0
    return (x * (peak / m)).astype(F32) if m > 1e-9 else x.astype(F32)


def lfo(n: int, rng: np.random.Generator, speed: float = 0.2, depth: float = 0.5) -> np.ndarray:
    """Variação lenta e irregular de volume (rajadas de vento, ondas, multidão)."""
    t = _t(n)
    v = np.zeros(n, F32)
    for _ in range(3):
        v += np.sin(TAU * speed * rng.uniform(0.5, 1.6) * t + rng.uniform(0, TAU)).astype(F32)
    v = v / 3
    return (1 - depth + depth * (0.5 + 0.5 * v)).astype(F32)


# ------------------------------------------------------------------ efeitos
def s_step(rng, hard: float = 0.5) -> np.ndarray:
    n = _n(0.11)
    click = band(noise(n, rng), 300, 3500) * env(n, 0.016) * (0.5 + hard)
    thump = osc(glide(110, 55, n), n) * env(n, 0.035) * 0.9
    return norm(click * 0.4 + thump, 0.9)


def s_thud(rng, size: float = 1.0) -> np.ndarray:
    n = _n(0.45)
    sub = osc(glide(85 / max(size, 0.5) ** 0.3, 42, n), n) * env(n, 0.14)
    hit = band(noise(n, rng), 80, 1500) * env(n, 0.035) * 0.6
    return norm(sub + hit, 1.0)


def s_knock(rng, pitch: float = 1.0) -> np.ndarray:
    n = _n(0.18)
    body = osc(520 * pitch, n) * env(n, 0.06) + osc(1340 * pitch, n) * env(n, 0.025) * 0.6
    click = band(noise(n, rng), 1500, 8000) * env(n, 0.006) * 0.5
    return norm(body + click, 0.9)


def s_click(rng) -> np.ndarray:
    n = _n(0.06)
    return norm(
        osc(2600, n) * env(n, 0.012)
        + osc(4200, n) * env(n, 0.008) * 0.7
        + band(noise(n, rng), 3000) * env(n, 0.004),
        0.7,
    )


def s_clack(rng) -> np.ndarray:
    n = _n(0.07)
    return norm(band(noise(n, rng), 1200, 6500) * env(n, 0.012) + osc(1850, n) * env(n, 0.02) * 0.5, 0.85)


def s_pop(rng) -> np.ndarray:
    n = _n(0.13)
    return norm(osc(glide(320, 1150, n), n) * env(n, 0.05, 0.004), 0.8)


def s_unpop(rng) -> np.ndarray:
    n = _n(0.22)
    return norm(osc(glide(1100, 260, n), n) * env(n, 0.09, 0.004), 0.7)


def s_boing(rng) -> np.ndarray:
    n = _n(0.55)
    t = _t(n)
    f = 210 * (1 + 0.28 * np.sin(TAU * 17 * t) * np.exp(-t * 4))
    return norm(osc(f, n) * env(n, 0.2), 0.75)


def s_whoosh(rng, sec: float = 0.45, up: bool = True) -> np.ndarray:
    n = _n(sec)
    k = np.linspace(0, 1, n, dtype=F32)
    if not up:
        k = 1 - k
    lo = band(noise(n, rng), 200, 1200)
    hi = band(noise(n, rng), 1600, 7000)
    shape = np.sin(np.pi * np.linspace(0, 1, n)) ** 2
    return norm((lo * (1 - k) + hi * k) * shape, 0.55)


def s_sweep(rng, f0: float, f1: float, sec: float) -> np.ndarray:
    n = _n(sec)
    return norm(osc(glide(f0, f1, n), n) * swell(n, 0.02, sec * 0.4), 0.45)


def s_boom(rng, sec: float = 1.8) -> np.ndarray:
    n = _n(sec)
    rumble = band(noise(n, rng, "brown"), 25, 700) * env(n, 0.45, 0.004)
    sub = osc(glide(60, 30, n), n) * env(n, 0.32) * 1.3
    crack = band(noise(n, rng), 800) * env(n, 0.03) * 0.7
    return norm(rumble + sub + crack, 1.0)


def s_chime(rng, notes=(1046.5, 1318.5, 1568.0, 2093.0), gap: float = 0.07) -> np.ndarray:
    total = gap * len(notes) + 0.6
    out = np.zeros(_n(total), F32)
    for i, f in enumerate(notes):
        n = _n(0.6)
        tone = osc(f, n) + osc(f * 2.76, n) * 0.25
        s = _n(gap * i)
        out[s : s + n] += tone * env(n, 0.3)
    return norm(out, 0.5)


def s_ding(rng, f: float = 1480.0) -> np.ndarray:
    n = _n(1.2)
    return norm(
        osc(f, n) * env(n, 0.5)
        + osc(f * 2.76, n) * env(n, 0.22) * 0.4
        + osc(f * 5.4, n) * env(n, 0.08) * 0.2,
        0.6,
    )


def s_coin(rng) -> np.ndarray:
    a, b = _n(0.07), _n(0.35)
    first = (osc(988, a) + osc(2964, a) * 0.3) * env(a, 0.05)
    second = (osc(1319, b) + osc(3957, b) * 0.3) * env(b, 0.16)
    return norm(np.concatenate([first, second]), 0.5)


def s_sparkle(rng, sec: float = 0.7) -> np.ndarray:
    out = np.zeros(_n(sec), F32)
    for _ in range(9):
        n = _n(0.18)
        s = int(rng.uniform(0, max(1, len(out) - n)))
        out[s : s + n] += osc(rng.uniform(2800, 6500), n) * env(n, 0.05) * rng.uniform(0.4, 1.0)
    return norm(out, 0.35)


def s_rattle(rng, sec: float = 0.5) -> np.ndarray:
    out = np.zeros(_n(sec), F32)
    for k in range(int(sec * 24)):
        n = _n(0.03)
        s = _n(k / 24 + rng.uniform(0, 0.01))
        if s + n <= len(out):
            out[s : s + n] += band(noise(n, rng), 600, 5000) * env(n, 0.008)
    return norm(out, 0.5)


def s_rumble(rng, sec: float, lo: float = 25, hi: float = 220) -> np.ndarray:
    n = _n(sec)
    return norm(band(noise(n, rng, "brown"), lo, hi) * swell(n, 0.25, 0.4) * lfo(n, rng, 0.8, 0.3), 0.6)


def s_rocket(rng, sec: float) -> np.ndarray:
    n = _n(sec)
    roar = band(noise(n, rng, "pink"), 40, 2500) + band(noise(n, rng, "brown"), 20, 200) * 1.2
    grow = np.clip(np.linspace(0.3, 1.0, n), 0, 1).astype(F32)
    crackle = np.zeros(n, F32)
    hits = rng.integers(0, n, int(sec * 60))
    crackle[hits] = rng.uniform(-1, 1, len(hits))
    crackle = band(crackle, 1000, 6000) * 6
    return norm((roar + crackle * 0.3) * grow * swell(n, 0.15, 0.6), 0.85)


def s_engine(rng, sec: float, base: float = 52.0) -> np.ndarray:
    n = _n(sec)
    t = _t(n)
    f = base * (1 + 0.06 * np.sin(TAU * 0.7 * t))
    tone = sum(osc(f * k, n) / k for k in range(1, 9))
    grit = band(noise(n, rng), 100, 1200) * 0.25
    return norm((tone * 0.6 + grit) * swell(n, 0.4, 0.5), 0.5)


def s_hum(rng, sec: float, f: float = 120.0, wobble: float = 0.0) -> np.ndarray:
    n = _n(sec)
    t = _t(n)
    ff = f * (1 + wobble * np.sin(TAU * 5 * t))
    return norm((osc(ff, n) + osc(ff * 3, n) * 0.2) * swell(n, 0.3, 0.4), 0.3)


def s_flaps(rng, sec: float, rate: float = 3.5) -> np.ndarray:
    out = np.zeros(_n(sec), F32)
    k = 0
    while k / rate < sec:
        n = _n(0.09)
        s = _n(k / rate + rng.uniform(0, 0.02))
        if s + n <= len(out):
            out[s : s + n] += band(noise(n, rng), 300, 2500) * swell(n, 0.02, 0.06)
        k += 1
    return norm(out, 0.35)


def s_buzz(rng, sec: float, f: float = 220.0) -> np.ndarray:
    n = _n(sec)
    t = _t(n)
    ff = f * (1 + 0.03 * np.sin(TAU * 7 * t))
    tone = sum(osc(ff * k, n) / k for k in range(1, 6))
    return norm(tone * (0.7 + 0.3 * np.sin(TAU * 31 * t)) * swell(n, 0.1, 0.2), 0.25)


def s_splash(rng) -> np.ndarray:
    n = _n(0.6)
    return norm(
        band(noise(n, rng), 700, 8000) * env(n, 0.14, 0.005)
        + osc(glide(320, 110, n), n) * env(n, 0.06) * 0.6,
        0.8,
    )


def s_bubbles(rng, sec: float, count: int = 8) -> np.ndarray:
    out = np.zeros(_n(sec), F32)
    for _ in range(count):
        n = _n(0.035)
        s = int(rng.uniform(0, max(1, len(out) - n)))
        out[s : s + n] += osc(glide(rng.uniform(350, 600), rng.uniform(900, 1500), n), n) * env(n, 0.015)
    return norm(out, 0.35)


def s_applause(rng, sec: float = 1.8, density: float = 45.0) -> np.ndarray:
    out = np.zeros(_n(sec), F32)
    for _ in range(int(sec * density)):
        n = _n(0.025)
        s = int(rng.uniform(0, max(1, len(out) - n)))
        out[s : s + n] += band(noise(n, rng), 900, 7000) * env(n, 0.006) * rng.uniform(0.4, 1)
    return norm(out * swell(len(out), 0.15, 0.6), 0.55)


def s_crowd(rng, sec: float = 2.0) -> np.ndarray:
    n = _n(sec)
    voices = band(noise(n, rng), 250, 2400) * lfo(n, rng, 3.0, 0.5)
    return norm(voices * swell(n, 0.2, 0.8) + s_applause(rng, sec)[:n] * 0.6, 0.55)


def s_heartbeat(rng, sec: float) -> np.ndarray:
    out = np.zeros(_n(sec), F32)
    k = 0.0
    while k < sec:
        for off, f, d in ((0.0, 62, 0.07), (0.16, 50, 0.09)):
            n = _n(0.25)
            s = _n(k + off)
            if s + n <= len(out):
                out[s : s + n] += osc(f, n) * env(n, d)
        k += 0.8
    return norm(out, 0.8)


def s_sting(rng, sec: float = 1.8) -> np.ndarray:
    n = _n(sec)
    low = sum(osc(f, n) for f in (110.0, 116.6, 164.8, 233.1)) / 4
    high = (osc(2200, n) + osc(2331, n)) * 0.15
    air = band(noise(n, rng), 1500, 6000) * 0.08
    return norm((low + high + air) * swell(n, 0.25, 0.9), 0.75)


def s_woo(rng, sec: float = 1.4) -> np.ndarray:
    n = _n(sec)
    t = _t(n)
    f = 360 + 200 * np.sin(np.pi * t / sec) + 9 * np.sin(TAU * 6 * t)
    breath = band(noise(n, rng), 300, 1500) * 0.15
    return norm((osc(f, n) + osc(f * 2, n) * 0.15 + breath) * swell(n, 0.3, 0.5), 0.5)


def s_creak(rng, sec: float = 0.9) -> np.ndarray:
    out = np.zeros(_n(sec), F32)
    t = 0.0
    while t < sec - 0.02:
        n = _n(0.012)
        s = _n(t)
        out[s : s + n] += osc(rng.uniform(800, 1500), n) * env(n, 0.003)
        t += rng.uniform(0.012, 0.03)
    return norm(band(out, 300, 3000) * swell(len(out), 0.08, 0.2), 0.45)


def s_howl(rng, sec: float = 2.2) -> np.ndarray:
    n = _n(sec)
    t = _t(n)
    f = np.interp(t, [0, 0.5, sec - 0.5, sec], [330, 620, 600, 420]) + 10 * np.sin(TAU * 5.5 * t)
    return norm((osc(f, n) + osc(f * 2, n) * 0.25) * swell(n, 0.3, 0.6), 0.5)


def s_crunch(rng, sec: float = 0.5) -> np.ndarray:
    out = np.zeros(_n(sec), F32)
    for k in range(3):
        n = _n(0.06)
        s = _n(k * sec / 3)
        if s + n <= len(out):
            out[s : s + n] += band(noise(n, rng), 1500, 7000) * env(n, 0.02)
    return norm(out, 0.4)


def s_snore(rng, sec: float) -> np.ndarray:
    n = _n(sec)
    t = _t(n)
    breath = np.clip(np.sin(TAU * t / 2.6), 0, 1) ** 2
    return norm(band(noise(n, rng), 70, 500) * breath + osc(55, n) * breath * 0.3, 0.3)


def s_tick(rng) -> np.ndarray:
    n = _n(0.02)
    return norm(osc(3200, n) * env(n, 0.003), 0.3)


def s_chirp(rng) -> np.ndarray:
    out = np.zeros(_n(0.4), F32)
    base = rng.uniform(2200, 3600)
    for k in range(int(rng.integers(2, 5))):
        n = _n(rng.uniform(0.04, 0.07))
        s = _n(k * 0.09)
        if s + n <= len(out):
            out[s : s + n] += osc(glide(base, base * rng.uniform(1.3, 1.7), n), n) * swell(n, 0.005, 0.02)
    return norm(out, 0.3)


def s_owl(rng) -> np.ndarray:
    parts = []
    for d in (0.35, 0.15, 0.5):
        n = _n(d)
        parts.append(osc(glide(400, 360, n), n) * swell(n, 0.05, 0.12))
        parts.append(np.zeros(_n(0.08), F32))
    return norm(np.concatenate(parts), 0.3)


def s_drip(rng) -> np.ndarray:
    n = _n(0.6)
    one = osc(glide(1100, 1700, _n(0.04)), _n(0.04)) * env(_n(0.04), 0.02)
    out = np.zeros(n, F32)
    for k, g in enumerate((1.0, 0.35, 0.15)):
        s = _n(k * 0.13)
        out[s : s + len(one)] += one * g
    return norm(out, 0.3)


def s_thunder(rng, sec: float = 3.5) -> np.ndarray:
    n = _n(sec)
    crack = band(noise(n, rng), 300) * env(n, 0.05) * 0.8
    roll = band(noise(n, rng, "brown"), 20, 400) * env(n, 1.1, 0.08) * lfo(n, rng, 2.0, 0.5)
    return norm(crack + roll * 1.5, 0.9)


def s_crackle(rng, sec: float) -> np.ndarray:
    n = _n(sec)
    out = np.zeros(n, F32)
    for _ in range(int(sec * 22)):
        m = _n(rng.uniform(0.004, 0.015))
        s = int(rng.uniform(0, max(1, n - m)))
        out[s : s + m] += band(noise(m, rng), 900, 6000) * env(m, 0.003) * rng.uniform(0.3, 1)
    bed = band(noise(n, rng, "brown"), 40, 300) * 0.25
    return norm(out + bed, 0.4)


# ------------------------------------------------------------------ ambientes
def amb_wind(rng, sec: float, strength: float = 0.5) -> np.ndarray:
    n = _n(sec)
    return norm(band(noise(n, rng, "pink"), 120, 1400) * lfo(n, rng, 0.15, 0.7), 0.25 * strength + 0.05)


def amb_birds(rng, sec: float, rate: float = 0.8) -> np.ndarray:
    out = np.zeros(_n(sec), F32)
    for _ in range(int(rng.poisson(rate * sec)) + 1):
        c = s_chirp(rng) * rng.uniform(0.3, 1.0)
        s = int(rng.uniform(0, max(1, len(out) - len(c))))
        out[s : s + len(c)] += c[: len(out) - s]
    return out * 0.5


def amb_crickets(rng, sec: float) -> np.ndarray:
    n = _n(sec)
    t = _t(n)
    carrier = osc(4600, n) + osc(4630, n) * 0.5
    pulses = (np.sin(TAU * 30 * t) > 0.6).astype(F32)
    trains = (np.sin(TAU * 1.7 * t + rng.uniform(0, 6)) > 0.2).astype(F32)
    return norm(band(carrier * pulses * trains, 3000, 7000), 0.06)


def amb_waves(rng, sec: float) -> np.ndarray:
    n = _n(sec)
    t = _t(n)
    sw = (0.5 + 0.5 * np.sin(TAU * t / 6.5 + rng.uniform(0, 6))) ** 2
    return norm(band(noise(n, rng, "pink"), 80, 3000) * (0.25 + sw), 0.3)


def amb_water(rng, sec: float) -> np.ndarray:
    n = _n(sec)
    return norm(band(noise(n, rng, "pink"), 300, 3500) * lfo(n, rng, 1.5, 0.25), 0.16)


def amb_rain(rng, sec: float, heavy: float = 1.0) -> np.ndarray:
    n = _n(sec)
    hiss = band(noise(n, rng), 1200, 9000) * 0.6
    drops = np.zeros(n, F32)
    hits = rng.integers(0, n, int(sec * 90 * heavy))
    drops[hits] = rng.uniform(0.2, 1.0, len(hits))
    drops = band(drops, 1500, 8000) * 3
    return norm(hiss + drops, 0.28 * heavy)


def amb_traffic(rng, sec: float) -> np.ndarray:
    n = _n(sec)
    hum = band(noise(n, rng, "brown"), 35, 350) * 0.6
    out = hum.copy()
    for _ in range(max(1, int(sec / 3))):
        m = _n(2.5)
        s = int(rng.uniform(0, max(1, n - m)))
        out[s : s + m] += band(noise(m, rng), 150, 1800) * np.sin(np.linspace(0, np.pi, m)) ** 2 * 0.6
    if rng.random() < 0.5 and n > _n(2):
        m = _n(0.35)
        s = int(rng.uniform(0, n - m))
        horn = (osc(415, m) + osc(523, m)) * swell(m, 0.02, 0.05)
        out[s : s + m] += band(horn, 200, 3000) * 0.25
    return norm(out, 0.22)


def amb_drone(rng, sec: float, freqs=(55.0, 82.5, 110.0), level: float = 0.18) -> np.ndarray:
    n = _n(sec)
    out = sum(osc(f, n) + osc(f + 0.25, n) for f in freqs) / (2 * len(freqs))
    out = out + band(noise(n, rng), 150, 1500) * 0.05
    return norm(out * lfo(n, rng, 0.1, 0.3), level)


def amb_murmur(rng, sec: float) -> np.ndarray:
    n = _n(sec)
    return norm(band(noise(n, rng), 300, 1600) * lfo(n, rng, 4.0, 0.6), 0.12)


def amb_room(rng, sec: float) -> np.ndarray:
    n = _n(sec)
    return norm(band(noise(n, rng, "pink"), 60, 900), 0.035)


def ambience(setting: str, time: str, weather: str, sec: float, rng) -> np.ndarray:
    n = _n(sec)
    out = np.zeros(n, F32)
    night = time == "night"

    def add(x, gain=1.0):
        out[: len(x)] += x[:n] * gain

    outdoor_green = setting in (
        "forest",
        "park",
        "village",
        "farm",
        "castle",
        "temple",
        "river",
        "jungle",
        "mountains",
    )
    if outdoor_green:
        add(amb_wind(rng, sec, 0.3))
        if night:
            add(amb_crickets(rng, sec))
        else:
            add(amb_birds(rng, sec, 1.6 if setting == "jungle" else 0.8))
        if setting == "jungle":
            add(norm(band(noise(n, rng), 5000, 9000) * lfo(n, rng, 6, 0.6), 0.03))
        if setting == "river":
            add(amb_water(rng, sec))
    elif setting in ("beach", "ocean"):
        add(amb_waves(rng, sec))
        add(amb_wind(rng, sec, 0.3), 0.6)
    elif setting == "underwater":
        add(amb_drone(rng, sec, (45.0, 67.5), 0.12))
        add(norm(band(noise(n, rng, "brown"), 30, 300), 0.12))
        add(s_bubbles(rng, sec, int(sec * 3)), 0.5)
    elif setting in ("desert", "egypt", "mars", "snow", "sky", "road"):
        add(amb_wind(rng, sec, 0.8 if setting in ("snow", "mars") else 0.5))
        if setting == "road":
            add(amb_traffic(rng, sec), 0.5)
    elif setting == "city":
        add(amb_traffic(rng, sec))
        if not night:
            add(amb_birds(rng, sec, 0.2), 0.5)
    elif setting == "graveyard":
        add(amb_wind(rng, sec, 0.7))
        add(amb_crickets(rng, sec), 0.8)
        if sec > 3 and rng.random() < 0.7:
            o = s_owl(rng)
            s = int(rng.uniform(0.3, max(0.4, sec - 2)) * SR)
            out[s : s + len(o)] += o[: max(0, n - s)]
    elif setting == "cave":
        add(amb_drone(rng, sec, (40.0, 60.0), 0.1))
        for _ in range(max(1, int(sec / 1.5))):
            d = s_drip(rng)
            s = int(rng.uniform(0, max(1, n - len(d))))
            out[s : s + len(d)] += d
    elif setting in ("room", "office", "lab"):
        add(amb_room(rng, sec))
        if setting == "lab":
            add(s_hum(rng, sec, 120, 0.0), 0.2)
    elif setting == "stage":
        add(amb_murmur(rng, sec))
    elif setting in ("space", "moon"):
        add(amb_drone(rng, sec, (41.2, 61.7, 82.4), 0.16))
    elif setting == "volcano":
        add(s_rumble(rng, sec, 20, 160), 0.6)
        add(s_crackle(rng, sec), 0.5)
    if weather in ("rain", "storm"):
        add(amb_rain(rng, sec, 1.4 if weather == "storm" else 1.0))
    elif weather in ("snow", "leaves") and not outdoor_green:
        add(amb_wind(rng, sec, 0.6), 0.6)
    elif weather == "fireflies" and not night:
        add(amb_crickets(rng, sec), 0.6)
    elif weather == "embers":
        add(s_crackle(rng, sec), 0.35)
    elif weather == "bubbles" and setting != "underwater":
        add(s_bubbles(rng, sec, int(sec * 2)), 0.4)
    elif weather == "sparkles":
        for k in range(int(sec / 1.2)):
            sp = s_sparkle(rng)
            s = _n(k * 1.2 + rng.uniform(0, 0.5))
            out[s : s + len(sp)] += sp[: max(0, n - s)] * 0.4
    return out


# ------------------------------------------------------------------ eventos da cena
class Track:
    """Trilha estéreo onde os sons são colocados no tempo, com volume e pan."""

    def __init__(self, sec: float):
        self.n = _n(sec)
        self.buf = np.zeros((self.n, 2), F32)

    def add(self, x: np.ndarray, t: float, gain: float = 1.0, pan: float = 0.0) -> None:
        s = int(round(t * SR))
        if s >= self.n or gain <= 0 or not len(x):
            return
        if s < 0:
            x = x[-s:]
            s = 0
        x = x[: self.n - s]
        a = (pan + 1) * math.pi / 4  # pan de potência constante
        self.buf[s : s + len(x), 0] += x * gain * math.cos(a)
        self.buf[s : s + len(x), 1] += x * gain * math.sin(a)

    def add_bed(self, x: np.ndarray, gain: float = 1.0) -> None:
        self.add(x, 0.0, gain, 0.0)


def _place(scene, a, t: float) -> tuple[float, float]:
    """(volume, pan) pela posição do ator na tela e distância da câmera."""
    try:
        eye, target, _roll, _fov = scene.camera(t)
        p = a.root_pos(t)
        f = target - eye
        f = f / max(float(np.linalg.norm(f)), 1e-6)
        r = np.cross(f, np.array((0, 1, 0), F32))
        r = r / max(float(np.linalg.norm(r)), 1e-6)
        rel = p - eye
        z = max(float(rel @ f), 0.3)
        x = float(rel @ r) / z / 0.27  # ~ -1..1 dentro do quadro (meia largura horizontal)
        dist = float(np.linalg.norm(rel))
        gain = 1.0 / (1 + max(0.0, dist - scene.cam_dist) / max(scene.cam_dist, 2.0))
        return float(np.clip(gain, 0.15, 1.0)), float(np.clip(x * 0.6, -0.8, 0.8))
    except Exception:  # noqa: BLE001 — som nunca pode derrubar a cena
        return 0.8, 0.0


def scene_events(scene) -> list[tuple[float, str, dict]]:
    """Lista (tempo, som, opções) a partir do que cada ator faz na cena."""
    ev: list[tuple[float, str, dict]] = []
    T = scene.T
    seen_group: set[tuple[int, str]] = set()
    for a in scene.actors:
        cat, kind, tags = a.cat, a.kind, a.model.tags
        size = a.model.height * a.scale
        heavy = size > 2.5
        small = size < 0.6
        for name, t0, t1 in a.segs:
            dur = max(t1 - t0, 1e-3)
            gkey = (id(getattr(a, "group", a)), name)
            first = gkey not in seen_group
            seen_group.add(gkey)
            if name in ("walk", "run", "push", "approach", "retreat", "climb") and cat in (
                "person",
                "animal",
                "bird",
            ):
                if cat == "person":
                    freq = (2.6 if name == "run" else 1.1 if name == "push" else 1.8) / math.sqrt(
                        max(a.stride, 0.2)
                    )
                    step = 1 / (2 * freq)
                else:
                    step = 0.18 if name == "run" else 0.32
                t = t0 + step * 0.5
                while t < t1:
                    ev.append((t, "step", {"a": a, "soft": small or cat != "person"}))
                    t += step
            elif name == "jump":
                n = max(1, round(dur / (1.6 if cat == "fish" else 1.2 if cat == "animal" else 1.1)))
                per = dur / n
                for k in range(n):
                    if cat == "fish":
                        ev += [
                            (t0 + per * k + 0.05, "splash", {"a": a}),
                            (t0 + per * (k + 1) - 0.05, "splash", {"a": a}),
                        ]
                    elif cat in ("person", "animal"):
                        ev += [
                            (t0 + per * k + per * 0.22, "whoosh_up", {"a": a, "g": 0.4}),
                            (t0 + per * k + per * 0.8, "thud", {"a": a, "g": 0.6}),
                        ]
                    else:
                        ev.append((t0 + per * k, "boing", {"a": a}))
            elif name == "bounce":
                t = t0
                while t < t1:
                    ev.append((t, "boing" if not heavy else "thud", {"a": a, "g": 0.7}))
                    t += 0.75
            elif name in ("drop", "fall") and cat != "person":
                fd = min(dur, 1.6)
                ev.append((t0, "whoosh_down", {"a": a, "g": 0.35}))
                for q, g in ((0.3636, 1.0), (0.7273, 0.45), (0.9091, 0.2)):
                    ev.append(
                        (
                            t0 + fd * q,
                            "knock" if kind in ("block", "brick", "dice", "domino") else "thud",
                            {"a": a, "g": g},
                        )
                    )
            elif name == "fall":
                ev.append((t0 + min(1.0, dur * 0.6), "thud", {"a": a, "g": 0.8}))
            elif name == "stack":
                n = max(a.gn, 1)
                start = dur * 0.8 * a.gi / n
                fd = min(0.9, dur * 0.35)
                ev.append(
                    (
                        t0 + start + fd * 0.3636,
                        "click" if kind == "brick" else "knock",
                        {"a": a, "pitch": 0.9 + 0.2 * (a.gi % 4) / 3},
                    )
                )
            elif name == "build":
                start = dur * 0.75 * a.gi / max(a.gn, 1)
                ev.append(
                    (
                        t0 + start + min(1.1, dur * 0.4),
                        "click" if kind == "brick" else "knock",
                        {"a": a, "pitch": 1.1},
                    )
                )
                if a.gi == 0:
                    ev.append((t0, "whoosh_up", {"a": a, "g": 0.4}))
            elif name == "domino":
                start = dur * 0.15 + a.gi * min(0.22, dur * 0.7 / max(a.gn, 1))
                ev.append((t0 + start + 0.33, "clack", {"a": a}))
            elif name == "explode":
                if a.gn <= 1 or a.gi == 0:
                    tb = t0 + dur * (0.35 if a.gn > 1 else 0.4)
                    ev += [(t0, "rattle", {"a": a, "g": 0.5}), (tb, "boom", {"a": a, "g": 1.0})]
                if a.gn > 1 and a.gi % 3 == 0:
                    ev.append((t0 + dur * 0.35 + 0.9 + 0.05 * a.gi, "knock", {"a": a, "g": 0.35}))
            elif name == "rain":
                per = 1.6
                t = t0 + (per - (a.phase * 0.5) % per)
                while t < t1:
                    ev.append((t, "coin" if kind == "coin" else "click", {"a": a, "g": 0.4}))
                    t += per
            elif name in ("pop", "appear", "grow") and first:
                ev.append((t0 + 0.03, "pop", {"a": a}))
                if kind in ("lightbulb", "star", "gem", "crystal", "heart", "crown", "trophy"):
                    ev.append((t0 + 0.1, "ding" if kind == "lightbulb" else "sparkle", {"a": a, "g": 0.6}))
            elif name in ("shrink", "vanish") and first:
                ev.append((t0, "unpop", {"a": a}))
                if name == "vanish":
                    ev.append((t0 + 0.2, "sparkle", {"a": a, "g": 0.5}))
            elif (
                name in ("spin", "flip", "swing", "orbit", "circle", "scatter", "assemble", "attack", "slide")
                and first
            ):
                ev.append((t0 + 0.05, "whoosh_up", {"a": a, "g": 0.45}))
                if name == "attack":
                    t = t0 + 0.9 * 0.4
                    while t < t1:
                        ev.append((t, "whoosh_down", {"a": a, "g": 0.4}))
                        t += 0.9
            elif name == "shake":
                ev.append((t0, "rattle", {"a": a, "g": 0.5}))
            elif name in ("glow", "pulse", "blink") and first:
                ev.append((t0 + 0.05, "ding" if kind == "lightbulb" else "chime", {"a": a, "g": 0.5}))
            elif name in ("roll", "tumble"):
                if name == "tumble":
                    t = t0 + 0.6
                    while t < t1:
                        ev.append((t, "knock", {"a": a, "g": 0.5, "pitch": 0.7}))
                        t += 0.6
                else:
                    ev.append((t0, "rumble", {"a": a, "sec": dur, "g": 0.5}))
            elif name == "rise":
                ev.append((t0, "sweep_up", {"a": a, "sec": min(dur, 1.5)}))
            elif name == "sink":
                ev.append((t0, "sweep_down", {"a": a, "sec": min(dur, 1.5)}))
                if scene.spec.setting in ("ocean", "underwater", "river", "beach"):
                    ev.append((t0 + 0.3, "bubbles", {"a": a, "sec": dur}))
            elif name == "launch" or (name == "rise" and "rocket" in tags):
                ev += [
                    (t0, "boom", {"a": a, "g": 0.5}),
                    (t0 + dur * 0.1, "rocket", {"a": a, "sec": dur * 0.95}),
                ]
            elif name == "drive" and cat == "prop":
                if "boat" in tags:
                    ev.append((t0, "water", {"a": a, "sec": dur}))
                else:
                    ev.append((t0, "engine", {"a": a, "sec": dur, "base": 40 if heavy else 55}))
            elif name == "fly":
                if cat == "bird" or (cat == "animal" and "flies" in tags):
                    ev.append(
                        (t0, "flaps", {"a": a, "sec": dur, "rate": 1.4 if cat == "animal" else 3.5, "g": 0.6})
                    )
                elif cat == "insect":
                    ev.append((t0, "buzz", {"a": a, "sec": dur}))
                elif kind in ("ufo", "airplane", "rocket", "satellite"):
                    ev.append(
                        (t0, "engine" if kind == "airplane" else "hum", {"a": a, "sec": dur, "base": 70})
                    )
                else:
                    ev.append((t0, "whoosh_up", {"a": a, "g": 0.6}))
            elif name == "swim" and cat in ("fish", "creature", "person"):
                ev.append((t0 + 0.2, "bubbles", {"a": a, "sec": min(dur, 2.0), "g": 0.5}))
            elif name == "open":
                ev.append((t0, "creak", {"a": a}))
                if kind in ("chest", "treasure"):
                    ev.append((t0 + 0.5, "sparkle", {"a": a, "g": 0.8}))
                if kind == "elevator":
                    ev.append((t0, "ding", {"a": a, "g": 0.6}))
            elif name == "scare":
                ev += [(t0 + 0.1, "sting", {"a": a}), (t0, "woo", {"a": a})]
            elif name == "float" and cat == "ghost" and first:
                ev.append((t0 + 0.3, "woo", {"a": a, "g": 0.5}))
            elif name == "scared":
                ev.append((t0, "heartbeat", {"a": a, "sec": dur, "g": 0.6}))
            elif name in ("cheer", "celebrate") and first:
                ev.append((t0 + 0.1, "crowd" if a.gn > 1 else "applause", {"a": a, "sec": min(dur, 2.5)}))
            elif name == "clap" and first:
                ev.append((t0, "applause", {"a": a, "sec": min(dur, 2.5), "g": 0.6 if a.gn == 1 else 1.0}))
            elif name == "dance" and first:
                t = t0
                while t < t1:
                    ev.append((t, "click", {"a": a, "g": 0.25}))
                    t += 1 / 1.1
            elif name == "howl":
                ev.append((t0 + 0.4, "howl", {"a": a}))
            elif name == "eat":
                t = t0
                while t < t1:
                    ev.append((t, "crunch", {"a": a, "g": 0.5}))
                    t += 1.0
            elif name == "sleep":
                ev.append((t0 + 0.8, "snore", {"a": a, "sec": max(0.5, dur - 0.8), "g": 0.4}))
        # sons contínuos do próprio modelo
        if "fire" in tags and kind != "volcano" and (a.gn <= 1 or a.gi == 0):
            ev.append((0.0, "crackle", {"a": a, "sec": T, "g": 0.6}))
        if kind == "ufo":
            ev.append((0.0, "hum", {"a": a, "sec": T, "base": 300, "wobble": 0.04}))
        if "clock" in tags:
            t = 0.0
            while t < T:
                ev.append((t, "tick", {"a": a}))
                t += 0.5
    return ev


def _render_event(name: str, o: dict, rng) -> np.ndarray | None:
    sec = float(o.get("sec", 1.0))
    if name == "step":
        return s_step(rng, 0.2 if o.get("soft") else 0.6) * (0.45 if o.get("soft") else 0.7)
    simple = {
        "thud": s_thud, "knock": None, "click": s_click, "clack": s_clack, "pop": s_pop, "unpop": s_unpop, "boing": s_boing,
        "boom": s_boom, "chime": s_chime, "ding": s_ding, "coin": s_coin, "sparkle": s_sparkle, "rattle": s_rattle,
        "splash": s_splash, "sting": s_sting, "woo": s_woo, "creak": s_creak, "howl": s_howl, "crunch": s_crunch,
        "tick": s_tick,
    }  # fmt: skip
    if name == "knock":
        return s_knock(rng, float(o.get("pitch", 1.0)))
    if name in simple:
        return simple[name](rng)
    if name == "whoosh_up":
        return s_whoosh(rng, 0.4, True)
    if name == "whoosh_down":
        return s_whoosh(rng, 0.4, False)
    if name == "sweep_up":
        return s_sweep(rng, 300, 1400, sec)
    if name == "sweep_down":
        return s_sweep(rng, 1200, 200, sec)
    continuous = {
        "rumble": lambda: s_rumble(rng, sec),
        "rocket": lambda: s_rocket(rng, sec),
        "engine": lambda: s_engine(rng, sec, float(o.get("base", 55))),
        "hum": lambda: s_hum(rng, sec, float(o.get("base", 120)), float(o.get("wobble", 0.0))),
        "flaps": lambda: s_flaps(rng, sec, float(o.get("rate", 3.5))),
        "buzz": lambda: s_buzz(rng, sec),
        "bubbles": lambda: s_bubbles(rng, sec, max(3, int(sec * 4))),
        "water": lambda: amb_water(rng, sec) * 2,
        "applause": lambda: s_applause(rng, sec),
        "crowd": lambda: s_crowd(rng, sec),
        "heartbeat": lambda: s_heartbeat(rng, sec),
        "snore": lambda: s_snore(rng, sec),
        "crackle": lambda: s_crackle(rng, sec),
    }
    fn = continuous.get(name)
    return fn() if fn else None


def scene_audio(scene, seed: int = 0) -> np.ndarray:
    """Trilha estéreo (efeitos + ambiente) com a duração da cena."""
    rng = np.random.default_rng(seed + 4242)
    T = scene.T
    tr = Track(T)
    bed = ambience(scene.spec.setting, scene.time, scene.spec.weather, T, rng)
    tr.add_bed(bed * swell(len(bed), 0.3, 0.3), 1.0)
    for ft in getattr(scene, "flash_times", []):
        tr.add(s_thunder(rng), ft + 0.25, 0.8)
    cache: dict[tuple, np.ndarray] = {}
    for t, name, o in sorted(scene_events(scene), key=lambda e: e[0]):
        if t >= T:
            continue
        a = o.get("a")
        key = (name, round(float(o.get("sec", 0)), 1), o.get("soft"), o.get("pitch"), int(rng.integers(0, 3)))
        x = cache.get(key)
        if x is None:
            x = _render_event(name, o, rng)
            if x is None:
                continue
            cache[key] = x
        gain, pan = _place(scene, a, t) if a is not None else (1.0, 0.0)
        tr.add(x, t, gain * float(o.get("g", 1.0)) * 0.8, pan)
    return tr.buf


# ------------------------------------------------------------------ arquivos e mixagem
def write_wav(path: str | Path, audio: np.ndarray, sr: int = SR) -> Path:
    a = np.asarray(audio, F32)
    if a.ndim == 1:
        a = np.stack([a, a], axis=1)
    pcm = (np.clip(a, -1, 1) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(a.shape[1])
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())
    return Path(path)


def read_wav(path: str | Path) -> np.ndarray:
    with wave.open(str(path), "rb") as w:
        ch, sr, n = w.getnchannels(), w.getframerate(), w.getnframes()
        data = np.frombuffer(w.readframes(n), dtype="<i2").astype(F32) / 32768
    data = data.reshape(-1, ch)
    if ch == 1:
        data = np.repeat(data, 2, axis=1)
    if sr != SR:
        data = resample(data, sr)
    return data


def resample(x: np.ndarray, sr: int, to: int = SR) -> np.ndarray:
    """Reamostragem linear (suficiente para voz e efeitos)."""
    if sr == to or not len(x):
        return np.asarray(x, F32)
    n_out = int(round(len(x) * to / sr))
    src = np.linspace(0, len(x) - 1, n_out)
    if x.ndim == 1:
        return np.interp(src, np.arange(len(x)), x).astype(F32)
    return np.stack([np.interp(src, np.arange(len(x)), x[:, c]) for c in range(x.shape[1])], axis=1).astype(
        F32
    )


def decode_audio(path: str | Path, seconds: float) -> np.ndarray | None:
    """Decodifica qualquer áudio (mp3, m4a...) com o ffmpeg, em loop até `seconds`."""
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-stream_loop", "-1", "-i", str(path), "-t", f"{seconds:.3f}",
           "-f", "f32le", "-ac", "2", "-ar", str(SR), "-"]  # fmt: skip
    try:
        out = subprocess.run(cmd, capture_output=True, timeout=300, check=True).stdout
    except (subprocess.SubprocessError, OSError):
        return None
    data = np.frombuffer(out, dtype="<f4").reshape(-1, 2)
    return data.astype(F32) if len(data) else None


def _envelope(x: np.ndarray, attack: float = 0.05, release: float = 0.4) -> np.ndarray:
    """Envelope suave (0..1) de presença de voz, para abaixar a música (ducking)."""
    mono = np.abs(x).astype(F32)
    hop = 441
    frames = np.add.reduceat(mono, np.arange(0, len(mono), hop)) / hop if len(mono) else mono
    on = (frames > 0.01).astype(F32)
    k_r = max(1, int(release * SR / hop))
    k_a = max(1, int(attack * SR / hop))
    held = np.convolve(on, np.ones(k_r, F32), "full")[: len(on)] > 0  # segura depois que a voz para
    held = np.convolve(held.astype(F32), np.ones(k_a, F32) / k_a, "same")
    return np.repeat(np.clip(held, 0, 1), hop)[: len(mono)].astype(F32)


def mix_soundtrack(
    total: float,
    scene_tracks: list[tuple[float, np.ndarray | None]],
    voices: list[tuple[float, np.ndarray]],
    music: str | Path | None = None,
    fade: float = 0.5,
    whooshes: list[float] | None = None,
    seed: int = 0,
) -> np.ndarray:
    """Mistura efeitos/ambiente de cada cena, narração e música (com ducking) numa trilha estéreo."""
    rng = np.random.default_rng(seed)
    n = _n(total + 0.3)
    sfx = np.zeros((n, 2), F32)
    for i, (offset, tr) in enumerate(scene_tracks):
        if tr is None or not len(tr):
            continue
        tr = tr.copy()
        k = min(_n(fade), len(tr) // 2)
        ramp = np.linspace(0, 1, k, dtype=F32)[:, None]
        if i > 0:
            tr[:k] *= ramp
        if i < len(scene_tracks) - 1:
            tr[-k:] *= ramp[::-1]
        s = _n(offset)
        m = min(len(tr), n - s)
        if m > 0:
            sfx[s : s + m] += tr[:m]
    for t in whooshes or []:
        w = s_whoosh(rng, 0.5, True) * 0.35
        s = max(0, _n(t - 0.25))
        m = min(len(w), n - s)
        sfx[s : s + m] += w[:m, None]
    voice = np.zeros(n, F32)
    for offset, v in voices:
        s = _n(offset)
        m = min(len(v), n - s)
        if m > 0:
            voice[s : s + m] += v[:m]
    duck = _envelope(voice)
    has_voice = bool(np.any(voice))
    out = sfx * (1 - 0.45 * duck)[:, None] + voice[:, None] * 0.95
    if music:
        mus = decode_audio(music, total + 0.3)
        if mus is not None:
            mus = np.pad(mus, ((0, max(0, n - len(mus))), (0, 0)))[:n]
            fade_in = np.clip(np.arange(n) / (SR * 1.0), 0, 1)
            fade_out = np.clip((n - np.arange(n)) / (SR * 1.5), 0, 1)
            level = 0.42 if has_voice else 0.6
            out += mus * (level * fade_in * fade_out * (1 - 0.7 * duck))[:, None].astype(F32)
    peak = float(np.max(np.abs(out))) if len(out) else 0.0
    if peak > 0.98:
        out = np.tanh(out * (1.6 / peak)) / np.tanh(1.6) * 0.98  # limitador suave
    return out.astype(F32)
