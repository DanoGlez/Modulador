"""Ventana del modulador: la voz robótica sale por un cable virtual hacia FiveM."""

from __future__ import annotations

import ctypes
import sys
import webbrowser
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def _enable_windows_dpi() -> None:
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("modulador.voz.robot")
    except Exception:
        pass


_enable_windows_dpi()

import customtkinter as ctk

from app.cables import (
    fivem_input_name,
    is_cable_recording_end,
    is_virtual_playback,
    looks_like_headphones,
)
from app.engine import (
    AudioDevice,
    AudioEngine,
    default_device_indices,
    list_devices,
    preferred_cable,
    preferred_input,
    preferred_monitor,
    preferred_output_fallback,
)
from app.robot import PRESET_ORDER, PRESETS

CABLE_HELP_URL = "https://vb-audio.com/Cable/"
MONITOR_OFF = "No escucharme"
_STATUS_COLORS = {
    "info": "#C8C8C8",
    "good": "#8FDBA8",
    "bad": "#E07A7A",
    "warn": "#E6C07B",
}


class App(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        self.title("Modulador")
        self.geometry("540x820")
        self.minsize(500, 700)

        self.engine = AudioEngine()
        self.inputs: list[AudioDevice] = []
        self.outputs: list[AudioDevice] = []
        self._default_in: int | None = None
        self._default_out: int | None = None
        self._running = False
        self._alive = True
        self._syncing = False
        self._bulk = False
        self._next = 0

        self.grid_columnconfigure(0, weight=1)
        self.body = ctk.CTkFrame(self, fg_color="transparent")
        self.body.grid(row=0, column=0, sticky="nsew", padx=22, pady=16)
        self.body.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._label(
            "Modulador",
            size=26,
            weight="bold",
            color="#9AD7FF",
            pady=(0, 2),
        )
        self._label(
            "Tu voz entra al servidor de FiveM por un cable virtual.",
            size=14,
            wrap=480,
        )
        self._label(
            "Usa auriculares para escucharte. Si el efecto sale por los altavoces, el micrófono lo vuelve a tomar.",
            size=13,
            color="#E6C07B",
            wrap=480,
            pady=(0, 12),
        )

        self._label("Micrófono", size=13)
        self.mic_combo = self._combo(self._on_mic_selected)
        self._label("Salida hacia FiveM", size=13)
        self.cable_combo = self._combo(self._on_cable_selected)
        self._label("Escucharte", size=13)
        self.monitor_combo = self._combo(None)
        self.refresh_button = ctk.CTkButton(
            self.body,
            text="Actualizar dispositivos",
            command=self._refresh,
        )
        self._place(self.refresh_button, pady=(2, 10))

        self.hint = self._label("", size=13, wrap=480, pady=(0, 8))
        self.banner = ctk.CTkFrame(self.body, fg_color="#3f3424")
        self.banner.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(
            self.banner,
            text=(
                "FiveM necesita un cable virtual. Instala VB-Audio Cable, "
                "reinicia Windows y pulsa Actualizar. Luego elige la salida CABLE Input."
            ),
            wraplength=460,
            justify="left",
            anchor="w",
        ).grid(row=0, column=0, sticky="ew", padx=12, pady=(10, 6))
        ctk.CTkButton(
            self.banner,
            text="Descargar VB-Audio Cable",
            command=self._open_cable_help,
        ).grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 12))
        self._place(self.banner, pady=(0, 10))

        self.presets = ctk.CTkSegmentedButton(
            self.body,
            values=list(PRESET_ORDER),
            command=self._apply_preset,
        )
        self._place(self.presets, pady=(4, 12))

        self.mix_slider, self.mix_value = self._slider("Intensidad", 0, 100, 100)
        self.freq_slider, self.freq_value = self._slider("Frecuencia", 20, 400, 380)
        self.crush_slider, self.crush_value = self._slider("Triturado", 0, 100, 100)

        meter_row = ctk.CTkFrame(self.body, fg_color="transparent")
        meter_row.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(meter_row, text="Entrada", anchor="w").grid(row=0, column=0, padx=(0, 10))
        self.meter = ctk.CTkProgressBar(meter_row)
        self.meter.grid(row=0, column=1, sticky="ew")
        self.meter.set(0)
        self._place(meter_row, pady=(8, 10))

        self.button = ctk.CTkButton(self.body, text="Activar", height=42, command=self._toggle)
        self._place(self.button, pady=(0, 8))
        self._start_fg = self.button.cget("fg_color")
        self._start_hover = self.button.cget("hover_color")

        self.status = self._label("Leyendo dispositivos…", size=13, wrap=480, pady=(0, 4))
        self.latency = self._label(self._latency_text(), size=12, color="gray70", wrap=480, pady=(0, 0))

        self._apply_preset("Clásico")
        self.presets.set("Clásico")
        self._load_devices(keep=False)
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.after(50, self._tick)

    def _label(
        self,
        text: str,
        *,
        size: int,
        weight: str = "normal",
        color: str | None = None,
        wrap: int | None = None,
        pady: tuple[int, int] = (0, 4),
    ) -> ctk.CTkLabel:
        label = ctk.CTkLabel(
            self.body,
            text=text,
            font=ctk.CTkFont(size=size, weight=weight),
            text_color=color,
            wraplength=wrap or 0,
            justify="left",
            anchor="w",
        )
        self._place(label, pady=pady)
        return label

    def _combo(self, command) -> ctk.CTkComboBox:
        combo = ctk.CTkComboBox(
            self.body,
            values=["…"],
            state="readonly",
            command=command,
            width=480,
        )
        self._place(combo, pady=(0, 8))
        return combo

    def _slider(
        self,
        title: str,
        from_: float,
        to: float,
        steps: int,
    ) -> tuple[ctk.CTkSlider, ctk.CTkLabel]:
        frame = ctk.CTkFrame(self.body, fg_color="transparent")
        frame.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(frame, text=title, anchor="w").grid(row=0, column=0, sticky="w")
        value = ctk.CTkLabel(frame, text="", anchor="e")
        value.grid(row=0, column=1, sticky="e")
        slider = ctk.CTkSlider(
            frame,
            from_=from_,
            to=to,
            number_of_steps=steps,
            command=self._on_slider,
        )
        slider.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(4, 0))
        self._place(frame, pady=(0, 8))
        return slider, value

    def _place(self, widget, pady: tuple[int, int]) -> None:
        widget.grid(row=self._next, column=0, sticky="ew", pady=pady)
        self._next += 1

    def _latency_text(self) -> str:
        rate = self.engine.sample_rate or AudioEngine.SAMPLE_RATE
        milliseconds = 1000.0 * AudioEngine.BLOCK / rate
        return (
            f"El cable recibe la voz en bloques de unos {milliseconds:.0f} ms, "
            "más lo que tarde Windows."
        )

    def _load_devices(self, keep: bool) -> None:
        previous_mic = self.mic_combo.get() if keep else ""
        previous_cable = self.cable_combo.get() if keep else ""
        previous_monitor = self.monitor_combo.get() if keep else ""
        self._syncing = True
        try:
            try:
                self.inputs, self.outputs = list_devices()
                self._default_in, self._default_out = default_device_indices()
                error = None
            except Exception as exc:
                self.inputs = []
                self.outputs = []
                self._default_in = None
                self._default_out = None
                error = str(exc)

            mic_choice = self._kept(previous_mic, self.inputs, preferred_input(self.inputs, self._default_in))
            self._set_combo(self.mic_combo, [item["label"] for item in self.inputs], mic_choice, "No hay micrófonos")

            cable_pref = preferred_cable(self.outputs) or preferred_output_fallback(
                self.outputs,
                self._default_out,
            )
            cable_choice = self._kept(previous_cable, self.outputs, cable_pref)
            self._set_combo(
                self.cable_combo,
                [item["label"] for item in self.outputs],
                cable_choice,
                "No hay salidas",
            )

            monitor_labels = [MONITOR_OFF, *[item["label"] for item in self.outputs]]
            if keep and previous_monitor in monitor_labels:
                monitor_choice = previous_monitor
            else:
                cable = self._find(self.cable_combo, self.outputs)
                cable_index = None if cable is None else cable["index"]
                monitor = preferred_monitor(self.outputs, cable_index, self._default_out)
                if monitor is not None and not looks_like_headphones(monitor["name"]):
                    monitor = None
                monitor_choice = MONITOR_OFF if monitor is None else monitor["label"]
            self._set_combo(
                self.monitor_combo,
                monitor_labels if self.outputs else [MONITOR_OFF],
                monitor_choice,
                MONITOR_OFF,
            )
        finally:
            self._syncing = False

        self._sync_hint()
        self._update_start_enabled()
        if self._running:
            return
        if error:
            self._set_status(f"No pude leer los dispositivos de audio. {error}", "bad")
        elif preferred_cable(self.outputs) is None:
            self._set_status("Instala VB-Audio Cable para que FiveM pueda usar esta voz.", "warn")
        else:
            self._set_status("Elige el micrófono, confirma el cable y pulsa Activar.", "info")

    def _kept(self, previous: str, devices: list[AudioDevice], preferred: AudioDevice | None) -> str:
        if previous and any(item["label"] == previous for item in devices):
            return previous
        if preferred is None:
            return ""
        return preferred["label"]

    def _set_combo(self, combo: ctk.CTkComboBox, values: list[str], selected: str, placeholder: str) -> None:
        if not values:
            values = [placeholder]
            selected = placeholder
        if selected not in values:
            selected = values[0]
        combo.configure(values=values)
        combo.set(selected)

    def _find(self, combo: ctk.CTkComboBox, devices: list[AudioDevice]) -> AudioDevice | None:
        label = combo.get()
        for device in devices:
            if device["label"] == label:
                return device
        return None

    def _find_monitor(self) -> AudioDevice | None:
        if self.monitor_combo.get() == MONITOR_OFF:
            return None
        return self._find(self.monitor_combo, self.outputs)

    def _sync_hint(self) -> None:
        cable = self._find(self.cable_combo, self.outputs)
        if cable is None:
            self.hint.configure(text="No hay dispositivo de salida.")
            self.banner.grid()
            return
        fivem_name = fivem_input_name(cable["name"])
        if fivem_name:
            self.banner.grid_remove()
            self.hint.configure(
                text=(
                    f"En Windows pon «{fivem_name}» como entrada y como dispositivo de comunicaciones. "
                    "En el servidor de FiveM elige ese mismo micrófono."
                )
            )
        elif cable["virtual"]:
            self.banner.grid_remove()
            self.hint.configure(
                text="En FiveM elige el extremo de entrada de este cable, no tu micrófono real."
            )
        else:
            self.banner.grid()
            self.hint.configure(
                text="FiveM no verá los altavoces como micrófono. La salida tiene que ser CABLE Input."
            )

    def _on_cable_selected(self, _value: str | None = None) -> None:
        if self._syncing:
            return
        cable = self._find(self.cable_combo, self.outputs)
        monitor = self._find_monitor()
        if cable is not None and monitor is not None and monitor["index"] == cable["index"]:
            replacement = preferred_monitor(self.outputs, cable["index"], self._default_out)
            if replacement is not None and not looks_like_headphones(replacement["name"]):
                replacement = None
            self.monitor_combo.set(MONITOR_OFF if replacement is None else replacement["label"])
        self._sync_hint()

    def _on_mic_selected(self, _value: str | None = None) -> None:
        if self._syncing or self._running:
            return
        mic = self._find(self.mic_combo, self.inputs)
        if mic is not None and is_cable_recording_end(mic["name"]):
            self._set_status(
                "Ese es el micrófono del cable. Elige el micrófono con el que hablas.",
                "warn",
            )

    def _refresh(self) -> None:
        if self._running:
            return
        self._load_devices(keep=True)

    def _apply_preset(self, name: str) -> None:
        preset = PRESETS[name]
        self._bulk = True
        try:
            self.mix_slider.set(preset["mix"] * 100)
            self.freq_slider.set(preset["carrier_hz"])
            self.crush_slider.set(preset["crush"] * 100)
            self._update_slider_labels()
        finally:
            self._bulk = False
        self._push_params()

    def _on_slider(self, _value: float | None = None) -> None:
        self._update_slider_labels()
        if not self._bulk:
            self._push_params()

    def _update_slider_labels(self) -> None:
        self.mix_value.configure(text=f"{int(round(self.mix_slider.get()))} %")
        self.freq_value.configure(text=f"{int(round(self.freq_slider.get()))} Hz")
        self.crush_value.configure(text=f"{int(round(self.crush_slider.get()))} %")

    def _push_params(self) -> None:
        self.engine.params = (
            float(self.mix_slider.get()) / 100.0,
            float(self.freq_slider.get()),
            float(self.crush_slider.get()) / 100.0,
        )

    def _update_start_enabled(self) -> None:
        if self._running:
            return
        ready = self._find(self.mic_combo, self.inputs) is not None and self._find(
            self.cable_combo,
            self.outputs,
        ) is not None
        self.button.configure(state="normal" if ready else "disabled")

    def _toggle(self) -> None:
        if self._running:
            self.engine.stop()
            self._set_running_ui(False)
            self._set_status("Detenido.", "info")
            self._sync_hint()
            return

        mic = self._find(self.mic_combo, self.inputs)
        cable = self._find(self.cable_combo, self.outputs)
        if mic is None or cable is None:
            self._set_status("Elige un micrófono y una salida.", "bad")
            return
        if is_cable_recording_end(mic["name"]):
            self._set_status(
                "Ese es el extremo del cable. Elige el micrófono con el que hablas.",
                "bad",
            )
            return
        monitor = self._find_monitor()
        monitor_index = None if monitor is None else monitor["index"]
        if monitor_index == cable["index"]:
            monitor_index = None
        try:
            self.engine.start(mic["index"], cable["index"], monitor_index, mic["name"])
        except Exception as exc:
            self.engine.stop()
            self._set_status(_friendly_error(exc), "bad")
            return

        self._set_running_ui(True)
        self.latency.configure(text=self._latency_text())
        message = _running_message(cable["name"])
        if self.engine.monitor_error:
            message = f"{message} {self.engine.monitor_error}"
        kind = "good" if is_virtual_playback(cable["name"]) else "warn"
        self._set_status(message, kind)

    def _set_running_ui(self, running: bool) -> None:
        self._running = running
        if running:
            self.button.configure(text="Detener", fg_color="#9B3A3A", hover_color="#7A2E2E")
        else:
            self.button.configure(
                text="Activar",
                fg_color=self._start_fg,
                hover_color=self._start_hover,
            )
        state = "disabled" if running else "readonly"
        for combo in (self.mic_combo, self.cable_combo, self.monitor_combo):
            combo.configure(state=state)
        self.refresh_button.configure(state="disabled" if running else "normal")
        self.presets.configure(state="normal")
        self._update_start_enabled()

    def _set_status(self, text: str, kind: str) -> None:
        self.status.configure(text=text, text_color=_STATUS_COLORS[kind])

    def _tick(self) -> None:
        if not self._alive:
            return
        self.meter.set(min(1.0, self.engine.level * 8.0))
        if self._running and (
            self.engine.callback_error or self.engine.unexpected_stop or not self.engine.active
        ):
            if self.engine.callback_error:
                message = f"El audio se detuvo. {self.engine.callback_error}"
            else:
                message = "El audio se detuvo. Revisa el micrófono y el cable, y pulsa Activar otra vez."
            self.engine.stop()
            self._set_running_ui(False)
            self._set_status(message, "bad")
        if self._alive:
            self.after(50, self._tick)

    def _open_cable_help(self) -> None:
        webbrowser.open(CABLE_HELP_URL)

    def _close(self) -> None:
        self._alive = False
        self.engine.stop()
        self.destroy()


def _running_message(cable_name: str) -> str:
    fivem_name = fivem_input_name(cable_name)
    if fivem_name:
        return (
            f"FiveM ya puede oírte. En Windows y en el servidor elige el micrófono «{fivem_name}»."
        )
    if is_virtual_playback(cable_name):
        return "El cable virtual está recibiendo la voz. En FiveM elige su entrada, no tu micrófono."
    return "El efecto se oye en esa salida, pero FiveM no. Elige CABLE Input."


def _friendly_error(exc: Exception) -> str:
    message = str(exc).strip()
    if message.startswith(("No se pudo", "Ese ", "Elige ")):
        return message
    return f"No se pudo abrir el audio. {message}"


def main() -> None:
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
