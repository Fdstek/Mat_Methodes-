"""Petites fonctions de mise en forme du texte (français)."""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime

ESPACE_FINE = " "  # séparateur des milliers (comme fr-FR)


def norm(s: str | None) -> str:
    """Comparaison sans casse ni accents."""
    t = unicodedata.normalize("NFD", str(s or ""))
    return "".join(c for c in t if unicodedata.category(c) != "Mn").lower().strip()


def cap(s: str) -> str:
    return s[:1].upper() + s[1:] if s else s


def minuscule_initiale(s: str) -> str:
    """« Étuve » -> « étuve », mais garde les sigles (« ICP », « FFA »)."""
    if not s:
        return s
    if len(s) > 1 and s[1].isupper():
        return s
    return s[:1].lower() + s[1:]


def fmt_num(v: float | int | None) -> str:
    """60 -> « 60 », 2.5 -> « 2,5 », 4000 -> « 4 000 »."""
    if v is None:
        return ""
    v = round(float(v), 3)
    if v == int(v):
        entier, dec = int(abs(v)), ""
    else:
        txt = f"{abs(v):.3f}".rstrip("0")
        e, d = txt.split(".")
        entier, dec = int(e), "," + d
    groupes = f"{entier:,}".replace(",", ESPACE_FINE)
    return ("-" if v < 0 else "") + groupes + dec


fmt_vol = fmt_num


def fmt_vol_ou(v) -> str:
    return "?" if v is None else fmt_vol(v)


def fmt_dur(minutes: float | None) -> str:
    """< 60 min en « min », multiples de 60 en « h », sinon « 1 h 05 »."""
    if minutes is None:
        return ""
    m = int(round(float(minutes)))
    h, r = divmod(m, 60)
    if not h:
        return f"{m} min"
    return f"{h} h {r:02d}" if r else f"{h} h"


def parse_iso(iso: str | None) -> datetime | None:
    if not iso:
        return None
    try:
        return datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except ValueError:
        return None


def fmt_dt(iso: str | None) -> str:
    """2026-10-30T21:10:00Z -> « 30/10/2026 à 22:10 » (heure locale)."""
    d = parse_iso(iso)
    if d is None:
        return ""
    return d.astimezone().strftime("%d/%m/%Y à %H:%M")


def liste(a: list[str]) -> str:
    """[a, b, c] -> « a, b et c »."""
    if len(a) < 2:
        return "".join(a)
    return ", ".join(a[:-1]) + " et " + a[-1]


def de(s: str) -> str:
    """Élision : « d’éthanol », « de soude »."""
    return ("d’" if re.match(r"^[aeiouyhéèêàâîôû]", s, re.I) else "de ") + s


def etapes_txt(nums: list[int]) -> str:
    return ("étapes " + ", ".join(map(str, nums))) if len(nums) > 1 else f"étape {nums[0]}"


def phrase(libelle: str, t: str | None) -> str:
    """« Objectif : xxx. » ; vide si le champ est vide ; la ponctuation finale saisie est retirée."""
    t = (t or "").strip()
    if not t:
        return ""
    return f"{libelle} : {re.sub(r'[.\s]+$', '', t)}. "


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", norm(s)).strip("-") or "manip"


def nom_fichier(s: str) -> str:
    """Nom de fichier Windows lisible (garde accents et espaces, retire les caractères interdits)."""
    t = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "-", s or "").strip(" .")
    return t or "manip"
