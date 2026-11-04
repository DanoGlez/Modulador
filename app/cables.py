"""Nombres de cables virtuales y el micrófono que debe elegir FiveM."""

from __future__ import annotations

import re

# El programa escribe en el extremo de reproducción ("… Input").
# FiveM graba el otro extremo ("… Output").
_ENDPOINT = re.compile(r"^(.*?)\s+(input|output)\b", re.IGNORECASE)


def _split_endpoint(name: str) -> tuple[str, str] | None:
    match = _ENDPOINT.search(name)
    if not match:
        return None
    return match.group(1), match.group(2).casefold()


def _cable_family(head: str) -> bool:
    folded = head.casefold().strip()
    if "voicemeeter" in folded:
        return True
    if re.fullmatch(r"cable(-[a-d])?", folded):
        return True
    return folded in {"hi-fi cable", "hifi cable", "virtual cable"}


def fivem_input_name(playback_name: str) -> str | None:
    """Micrófono que FiveM tiene que usar para oír esta salida."""
    parts = _split_endpoint(playback_name)
    if parts is None:
        return None
    head, kind = parts
    if kind != "input" or not _cable_family(head):
        return None
    return f"{head} Output"


def is_virtual_playback(name: str) -> bool:
    """True si este dispositivo de salida es un cable que otro programa puede grabar."""
    if fivem_input_name(name):
        return True
    folded = name.casefold()
    return "blackhole" in folded or "virtual cable" in folded


def is_cable_recording_end(name: str) -> bool:
    """True si este micrófono es el extremo que debe usar FiveM, no este programa."""
    parts = _split_endpoint(name)
    if parts is None:
        return False
    head, kind = parts
    return kind == "output" and _cable_family(head)


_HEADPHONES = (
    "headphone",
    "headset",
    "auricular",
    "airpod",
    "audifono",
    "audífono",
    "earpod",
    "earbuds",
)


def looks_like_headphones(name: str) -> bool:
    folded = name.casefold()
    return any(hint in folded for hint in _HEADPHONES)


def host_rank(host: str) -> int:
    folded = host.casefold()
    if "wasapi" in folded or "core audio" in folded:
        return 0
    if "mme" in folded:
        return 1
    if "directsound" in folded:
        return 2
    return 3


def output_sort_key(name: str, host: str, virtual: bool) -> tuple:
    wide = 1 if "16ch" in name.casefold() else 0
    return (0 if virtual else 1, wide, host_rank(host), name.casefold())
