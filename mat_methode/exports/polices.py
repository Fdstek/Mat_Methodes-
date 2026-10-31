"""Polices TrueType pour les exports (sans police TrueType, le « µ » disparaît).

Ordre : Segoe UI (Windows 11), Arial, Liberation Sans, DejaVu Sans, puis Vera (livrée avec reportlab,
donc toujours présente dans l'.exe)."""
from __future__ import annotations

import os
from pathlib import Path

WINDIR = os.environ.get("WINDIR", "C:/Windows")


def _reportlab_vera() -> tuple[str, str]:
    import reportlab
    d = Path(reportlab.__file__).parent / "fonts"
    return str(d / "Vera.ttf"), str(d / "VeraBd.ttf")


def paires() -> list[tuple[str, str]]:
    return [
        (f"{WINDIR}/Fonts/segoeui.ttf", f"{WINDIR}/Fonts/segoeuib.ttf"),
        (f"{WINDIR}/Fonts/arial.ttf", f"{WINDIR}/Fonts/arialbd.ttf"),
        ("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf", "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"),
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        _reportlab_vera(),
    ]


def trouver() -> tuple[str, str] | None:
    for normal, gras in paires():
        if os.path.exists(normal) and os.path.exists(gras):
            return normal, gras
    return None
