"""Dossier de l'application et fichiers temporaires (§9.1).

Tout reste dans le dossier de l'application : rien dans %APPDATA%, %TEMP% ni le registre.
"""
from __future__ import annotations

import getpass
import os
import shutil
import socket
import sys
import tempfile
from pathlib import Path


def dossier_application() -> Path:
    """En .exe : le dossier de l'exécutable (jamais __file__ ni le dossier courant).
    En développement : la variable MATMETHODE_DOSSIER, sinon la racine du dépôt."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    if os.environ.get("MATMETHODE_DOSSIER"):
        return Path(os.environ["MATMETHODE_DOSSIER"]).resolve()
    return Path(__file__).resolve().parents[2]


def preparer_temp(racine: Path) -> Path:
    """À appeler au tout début, avant les imports qui écrivent : TMP, TEMP et tempfile -> <app>\\temp."""
    temp = racine / "temp"
    try:
        temp.mkdir(parents=True, exist_ok=True)
        vider_temp(temp)
    except OSError:
        return temp  # dossier en lecture seule : on ne peut rien y faire
    for var in ("TMP", "TEMP", "TMPDIR"):
        os.environ[var] = str(temp)
    tempfile.tempdir = str(temp)
    return temp


def vider_temp(temp: Path) -> None:
    if not temp.exists():
        return
    for p in temp.iterdir():
        try:
            shutil.rmtree(p) if p.is_dir() else p.unlink()
        except OSError:
            pass  # fichier encore ouvert par une autre instance


def utilisateur() -> str:
    try:
        return getpass.getuser() or "inconnu"
    except Exception:
        return os.environ.get("USERNAME") or "inconnu"


def poste() -> str:
    return os.environ.get("COMPUTERNAME") or socket.gethostname() or "PC"
