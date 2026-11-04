"""Micrófono real hacia un cable virtual, con escucha opcional en auriculares."""

from __future__ import annotations

import threading
from typing import TypedDict

import numpy as np
import sounddevice as sd

from app.cables import host_rank, is_cable_recording_end, is_virtual_playback, output_sort_key
from app.robot import PRESETS, RobotVoice


class AudioDevice(TypedDict):
    index: int
    name: str
    host: str
    label: str
    virtual: bool
    channels: int
    default_samplerate: int


class MonoRing:
    """Cola de audio mono entre el cable y la escucha."""

    def __init__(self, capacity: int) -> None:
        if capacity < 1:
            raise ValueError("capacity")
        self.buf = np.zeros(capacity, dtype=np.float32)
        self.capacity = capacity
        self.write_at = 0
        self.available = 0
        self._lock = threading.Lock()

    def write(self, samples: np.ndarray) -> None:
        data = np.asarray(samples, dtype=np.float32).reshape(-1)
        count = int(data.shape[0])
        if count == 0:
            return
        with self._lock:
            cap = self.capacity
            if count >= cap:
                self.buf[:] = np.ascontiguousarray(data[-cap:])
                self.write_at = 0
                self.available = cap
                return
            overflow = self.available + count - cap
            if overflow > 0:
                self.available -= overflow
            end = self.write_at + count
            if end <= cap:
                self.buf[self.write_at:end] = data
            else:
                first = cap - self.write_at
                self.buf[self.write_at:] = data[:first]
                self.buf[: count - first] = data[first:]
            self.write_at = end % cap
            self.available += count

    def read(self, count: int, *, max_buffered: int | None = None) -> np.ndarray:
        out = np.zeros(count, dtype=np.float32)
        if count <= 0:
            return out
        with self._lock:
            if max_buffered is not None and self.available > max_buffered:
                self.available = max_buffered
            take = min(count, self.available)
            if take == 0:
                return out
            start = (self.write_at - self.available) % self.capacity
            if start + take <= self.capacity:
                out[:take] = self.buf[start : start + take]
            else:
                first = self.capacity - start
                out[:first] = self.buf[start:]
                out[first:take] = self.buf[: take - first]
            self.available -= take
        return out


def list_devices() -> tuple[list[AudioDevice], list[AudioDevice]]:
    hostapis = sd.query_hostapis()
    inputs: list[AudioDevice] = []
    outputs: list[AudioDevice] = []
    for index, device in enumerate(sd.query_devices()):
        name = str(device["name"]).strip()
        host = str(hostapis[int(device["hostapi"])]["name"]).strip()
        rate = int(round(float(device["default_samplerate"])))
        in_channels = int(device["max_input_channels"])
        out_channels = int(device["max_output_channels"])
        if in_channels > 0:
            inputs.append(
                _device(index, name, host, in_channels, rate, is_cable_recording_end(name))
            )
        if out_channels > 0:
            outputs.append(
                _device(index, name, host, out_channels, rate, is_virtual_playback(name))
            )
    _assign_labels(inputs)
    _assign_labels(outputs)
    inputs.sort(key=lambda item: (item["virtual"], host_rank(item["host"]), item["name"].casefold()))
    outputs.sort(key=lambda item: output_sort_key(item["name"], item["host"], item["virtual"]))
    return inputs, outputs


def default_device_indices() -> tuple[int | None, int | None]:
    try:
        mic = int(sd.default.device[0])
        speaker = int(sd.default.device[1])
    except Exception:
        return None, None
    return (mic if mic >= 0 else None, speaker if speaker >= 0 else None)


def preferred_input(inputs: list[AudioDevice], default_index: int | None) -> AudioDevice | None:
    by_index = {item["index"]: item for item in inputs}
    current = by_index.get(default_index) if default_index is not None else None
    if current is not None and not current["virtual"]:
        return current
    real = [item for item in inputs if not item["virtual"]]
    if not real:
        return None
    return min(real, key=lambda item: (host_rank(item["host"]), item["name"].casefold()))


def preferred_cable(outputs: list[AudioDevice]) -> AudioDevice | None:
    virtual = [item for item in outputs if item["virtual"]]
    if not virtual:
        return None
    return min(virtual, key=lambda item: output_sort_key(item["name"], item["host"], True))


def preferred_output_fallback(
    outputs: list[AudioDevice],
    default_index: int | None,
) -> AudioDevice | None:
    if not outputs:
        return None
    by_index = {item["index"]: item for item in outputs}
    if default_index in by_index:
        return by_index[default_index]
    return outputs[0]


def preferred_monitor(
    outputs: list[AudioDevice],
    cable_index: int | None,
    default_index: int | None,
) -> AudioDevice | None:
    candidates = [
        item for item in outputs if item["index"] != cable_index and not item["virtual"]
    ]
    if not candidates:
        return None
    by_index = {item["index"]: item for item in candidates}
    if default_index in by_index:
        return by_index[default_index]
    return min(candidates, key=lambda item: (host_rank(item["host"]), item["name"].casefold()))


def _device(
    index: int,
    name: str,
    host: str,
    channels: int,
    rate: int,
    virtual: bool,
) -> AudioDevice:
    return {
        "index": index,
        "name": name,
        "host": host,
        "label": "",
        "virtual": virtual,
        "channels": channels,
        "default_samplerate": rate,
    }


def _assign_labels(devices: list[AudioDevice]) -> None:
    counts: dict[str, int] = {}
    bases = []
    for device in devices:
        base = f"{device['name']} ({device['host']})"
        bases.append(base)
        counts[base] = counts.get(base, 0) + 1
    for device, base in zip(devices, bases):
        if counts[base] == 1:
            device["label"] = base
        else:
            device["label"] = f"{base} #{device['index']}"


def _open_attempts(max_in: int, max_out: int, native_rate: int):
    rates = [AudioEngine.SAMPLE_RATE]
    if native_rate > 0 and native_rate not in rates:
        rates.append(native_rate)
    in_channels: list[int] = []
    for channels in (1, min(max_in, 2)):
        if channels >= 1 and channels not in in_channels:
            in_channels.append(channels)
    out_channels: list[int] = []
    for channels in (min(max_out, 2), 1):
        if channels >= 1 and channels not in out_channels:
            out_channels.append(channels)
    for rate in rates:
        for mic_channels in in_channels:
            for cable_channels in out_channels:
                for latency in ("low", "high"):
                    yield rate, mic_channels, cable_channels, latency


class AudioEngine:
    SAMPLE_RATE = 48000
    BLOCK = 512

    def __init__(self) -> None:
        classic = PRESETS["Clásico"]
        self.robot = RobotVoice(self.SAMPLE_RATE)
        self.params = (classic["mix"], classic["carrier_hz"], classic["crush"])
        self.level = 0.0
        self.sample_rate = self.SAMPLE_RATE
        self.callback_error: str | None = None
        self.monitor_error: str | None = None
        self.unexpected_stop = False
        self._cable: sd.Stream | None = None
        self._monitor: sd.OutputStream | None = None
        self._monitor_ring: MonoRing | None = None
        self._user_stop = False
        self._token: object | None = None

    @property
    def active(self) -> bool:
        stream = self._cable
        if stream is None:
            return False
        try:
            return bool(stream.active)
        except Exception:
            return False

    def start(
        self,
        mic_index: int,
        cable_index: int,
        monitor_index: int | None,
        mic_name: str,
    ) -> None:
        self.stop()
        if is_cable_recording_end(mic_name):
            raise RuntimeError(
                "Ese dispositivo es la entrada de FiveM. Elige tu micrófono real."
            )
        if mic_index == cable_index:
            raise RuntimeError(
                "El micrófono y la salida hacia FiveM tienen que ser dispositivos distintos."
            )

        self._user_stop = False
        self.unexpected_stop = False
        self.callback_error = None
        self.monitor_error = None
        token = object()
        self._token = token

        mic_info = sd.query_devices(mic_index, "input")
        cable_info = sd.query_devices(cable_index, "output")
        max_in = int(mic_info["max_input_channels"])
        max_out = int(cable_info["max_output_channels"])
        if max_in < 1 or max_out < 1:
            raise RuntimeError("Ese dispositivo no tiene canales de audio útiles.")
        native_rate = int(round(float(cable_info["default_samplerate"])))

        if monitor_index == cable_index:
            monitor_index = None
        if monitor_index is not None:
            self._monitor_ring = MonoRing(self.BLOCK * 32)

        last_error: Exception | None = None
        opened = False
        for rate, in_ch, out_ch, latency in _open_attempts(max_in, max_out, native_rate):
            try:
                self._open_cable(mic_index, cable_index, rate, in_ch, out_ch, latency, token)
                opened = True
                break
            except sd.PortAudioError as exc:
                last_error = exc
        if not opened:
            self._monitor_ring = None
            raise RuntimeError(f"No se pudo abrir el micrófono o el cable. {last_error}")

        if monitor_index is not None:
            self._open_monitor(monitor_index, self.sample_rate)

    def stop(self) -> None:
        self._user_stop = True
        self._token = object()
        self._close_stream("_cable")
        self._close_stream("_monitor")
        self._monitor_ring = None
        self.level = 0.0
        self.robot.reset()

    def _open_cable(
        self,
        mic_index: int,
        cable_index: int,
        rate: int,
        in_channels: int,
        out_channels: int,
        latency: str,
        token: object,
    ) -> None:
        self.robot.sample_rate = rate
        self.robot.reset()
        self.sample_rate = rate
        stream = sd.Stream(
            device=(mic_index, cable_index),
            samplerate=rate,
            blocksize=self.BLOCK,
            dtype="float32",
            channels=(in_channels, out_channels),
            callback=self._cable_callback,
            finished_callback=self._make_finished(token),
            latency=latency,
        )
        try:
            stream.start()
        except Exception:
            stream.close()
            raise
        self._cable = stream

    def _open_monitor(self, index: int, rate: int) -> None:
        last_error: Exception | None = None
        try:
            info = sd.query_devices(index, "output")
            channels = 2 if int(info["max_output_channels"]) >= 2 else 1
            options = [channels] if channels == 1 else [channels, 1]
            for channel_count in options:
                for latency in ("low", "high"):
                    stream = None
                    try:
                        stream = sd.OutputStream(
                            device=index,
                            samplerate=rate,
                            blocksize=self.BLOCK,
                            dtype="float32",
                            channels=channel_count,
                            callback=self._monitor_callback,
                            latency=latency,
                        )
                        stream.start()
                    except Exception as exc:
                        last_error = exc
                        if stream is not None:
                            try:
                                stream.close()
                            except Exception:
                                pass
                        continue
                    self._monitor = stream
                    return
        except Exception as exc:
            last_error = exc
        self._monitor_ring = None
        self.monitor_error = (
            "No pude abrir los auriculares. El cable hacia FiveM sigue activo. "
            f"{last_error}"
        )

    def _cable_callback(self, indata, outdata, frames, _time_info, _status) -> None:
        if self.callback_error:
            outdata.fill(0)
            return
        try:
            mono = np.mean(np.asarray(indata, dtype=np.float32), axis=1)
            self.level = float(np.sqrt(np.dot(mono, mono) / max(len(mono), 1)))
            mix, carrier_hz, crush = self.params
            processed = self.robot.process(mono, carrier_hz, mix, crush)
            if processed.shape[0] != outdata.shape[0]:
                fitted = np.zeros(outdata.shape[0], dtype=np.float32)
                count = min(len(processed), len(fitted))
                fitted[:count] = processed[:count]
                processed = fitted
            outdata[:] = processed[:, None]
            ring = self._monitor_ring
            if ring is not None:
                ring.write(processed)
        except Exception as exc:
            self.callback_error = str(exc)
            outdata.fill(0)

    def _monitor_callback(self, outdata, frames, _time_info, _status) -> None:
        ring = self._monitor_ring
        if ring is None:
            outdata.fill(0)
            return
        try:
            samples = ring.read(int(frames), max_buffered=int(frames) * 2)
            outdata[:] = samples[:, None]
        except Exception:
            outdata.fill(0)

    def _make_finished(self, token: object):
        def finished() -> None:
            if self._token is token and not self._user_stop:
                self.unexpected_stop = True

        return finished

    def _close_stream(self, attr: str) -> None:
        stream = getattr(self, attr)
        setattr(self, attr, None)
        if stream is None:
            return
        try:
            if stream.active:
                stream.abort()
        except Exception:
            pass
        try:
            stream.close()
        except Exception:
            pass
