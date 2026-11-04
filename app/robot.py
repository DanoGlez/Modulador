"""Efecto de voz robótica por bloques, sin recorrer muestra a muestra."""

from __future__ import annotations

import math

import numpy as np

PRESET_ORDER = ("Clásico", "Cyborg", "Radio", "8-bit")

PRESETS: dict[str, dict[str, float]] = {
    "Clásico": {"mix": 0.92, "carrier_hz": 35.0, "crush": 0.0},
    "Cyborg": {"mix": 0.88, "carrier_hz": 95.0, "crush": 0.40},
    "Radio": {"mix": 0.97, "carrier_hz": 220.0, "crush": 0.18},
    "8-bit": {"mix": 1.0, "carrier_hz": 55.0, "crush": 1.0},
}

_WET_GAIN = np.float32(1.7)


class RobotVoice:
    """Modulación en anillo con triturado y recorte suave."""

    def __init__(self, sample_rate: int = 48000) -> None:
        self.sample_rate = int(sample_rate)
        self.phase = 0.0
        self.hold_value = 0.0
        self.hold_count = 0

    def reset(self) -> None:
        self.phase = 0.0
        self.hold_value = 0.0
        self.hold_count = 0

    def process(
        self,
        samples: np.ndarray,
        carrier_hz: float,
        mix: float,
        crush: float,
    ) -> np.ndarray:
        audio = np.nan_to_num(
            np.asarray(samples, dtype=np.float32),
            nan=0.0,
            posinf=0.0,
            neginf=0.0,
        )
        count = int(audio.shape[0])
        if count == 0:
            return audio

        carrier_hz = float(min(max(carrier_hz, 20.0), 2000.0))
        mix = float(min(max(mix, 0.0), 1.0))
        crush = float(min(max(crush, 0.0), 1.0))

        hold_len = 1 if crush < 0.02 else int(round(1 + crush * 28))
        stepped = self._sample_hold(audio, hold_len)
        wet = stepped * self._carrier(count, carrier_hz, crush) * _WET_GAIN
        if crush > 0.02:
            wet = _quantize(wet, crush)
        drive = np.float32(1.0 + 0.4 * crush)
        wet = np.tanh(wet * drive).astype(np.float32)
        mixed = (1.0 - mix) * audio + mix * wet
        return np.ascontiguousarray(np.clip(mixed, -1.0, 1.0), dtype=np.float32)

    def _carrier(self, count: int, carrier_hz: float, crush: float) -> np.ndarray:
        increment = 2.0 * math.pi * carrier_hz / self.sample_rate
        positions = np.arange(count, dtype=np.float64)
        sine = np.sin(self.phase + increment * positions).astype(np.float32)
        self.phase = math.fmod(self.phase + increment * count, 2.0 * math.pi)
        if self.phase < 0.0:
            self.phase += 2.0 * math.pi
        if crush <= 0.45:
            return sine
        blend = np.float32((crush - 0.45) / 0.55)
        square = np.where(sine >= 0.0, np.float32(1.0), np.float32(-1.0))
        return ((1.0 - blend) * sine + blend * square).astype(np.float32)

    def _sample_hold(self, audio: np.ndarray, hold_len: int) -> np.ndarray:
        count = int(audio.shape[0])
        if hold_len <= 1:
            self.hold_count = 0
            if count:
                self.hold_value = float(audio[-1])
            return audio

        if self.hold_count >= hold_len:
            self.hold_count %= hold_len

        positions = np.arange(count, dtype=np.int64) + self.hold_count
        origin = positions // hold_len * hold_len - self.hold_count
        held = np.empty(count, dtype=np.float32)
        continued = origin < 0
        held[continued] = np.float32(self.hold_value)
        fresh = ~continued
        held[fresh] = audio[origin[fresh]]

        last_origin = int(origin[-1])
        if last_origin >= 0:
            self.hold_value = float(audio[last_origin])
        self.hold_count = int((self.hold_count + count) % hold_len)
        return held


def _quantize(audio: np.ndarray, crush: float) -> np.ndarray:
    levels = np.float32(2.0 ** (12.0 - 9.0 * crush))
    return np.round(audio * levels) / levels
