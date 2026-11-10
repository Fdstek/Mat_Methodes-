"""Photos des échantillons prises avec SamplesTEK (« Suivi Photos Échantillons »), retrouvées par le n° Aramis.

SamplesTEK range ses photos dans son dossier de stockage (par défaut C:\\PhotosEchantillons) :
la base SQLite « echantillons.db » (table « photos ») donne, pour chaque photo, le n° d'échantillon lu sur le QR code
de l'étiquette (colonne sample_id), la température, culot / incident, le commentaire et le chemin du fichier.
Mat & Méthode ouvre cette base en LECTURE SEULE : rien n'est jamais modifié côté SamplesTEK.
"""
from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

DOSSIER_DEFAUT = r"C:\PhotosEchantillons"
BASE = "echantillons.db"
COLONNES = ("id", "sample_id", "temperature", "incident", "culot", "comment", "filepath", "created_at",
            "aspect_label", "avg_color_hex", "series_tag")


def cle(v) -> str:
    """Même comparaison que SamplesTEK (majuscules, sans espaces autour), espaces intérieurs ignorés."""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return str(v or "").strip().upper().replace(" ", "")


@dataclass
class Lecture:
    photos: dict[str, list[dict]] = field(default_factory=dict)  # clé Aramis -> photos (plus anciennes d'abord)
    dossier: str = ""
    erreur: str = ""


def dossier_effectif(choisi: str = "") -> str:
    """Dossier de stockage SamplesTEK : celui choisi dans les Réglages, sinon C:\\PhotosEchantillons."""
    return (choisi or "").strip() or DOSSIER_DEFAUT


def _retrouver(chemin: str, racine: Path) -> str:
    """Chemin de la photo : celui de la base, sinon le même nom de fichier sous le dossier de stockage (dossier déplacé)."""
    if chemin and Path(chemin).exists():
        return chemin
    nom = Path(str(chemin).replace("\\", "/")).name
    if not nom:
        return ""
    base = len(racine.parts)
    for courant, dossiers, fichiers in os.walk(racine):
        if len(Path(courant).parts) - base >= 4:  # usine / type de produit / échantillon
            dossiers[:] = []
        if nom in fichiers:
            return str(Path(courant) / nom)
    return ""


def lire(dossier: str, aramis: list[str]) -> Lecture:
    """Photos des n° Aramis demandés, lues dans <dossier>\\echantillons.db (lecture seule)."""
    res = Lecture(dossier=dossier)
    voulus = {cle(a) for a in aramis if cle(a)}
    if not voulus:
        return res
    racine = Path(dossier)
    db = racine / BASE
    if not db.exists():
        res.erreur = f"base SamplesTEK introuvable : {db}"
        return res
    try:
        con = sqlite3.connect(f"{db.as_uri()}?mode=ro", uri=True, timeout=5)
        try:
            presentes = {r[1] for r in con.execute("PRAGMA table_info(photos)")}
            cols = [c for c in COLONNES if c in presentes]
            lignes = con.execute(f"SELECT {', '.join(cols)} FROM photos ORDER BY created_at ASC, id ASC").fetchall()
        finally:
            con.close()
    except sqlite3.Error as ex:
        res.erreur = f"base SamplesTEK illisible : {ex}"
        return res
    for ligne in lignes:
        p = dict(zip(cols, ligne))
        k = cle(p.get("sample_id"))
        if k not in voulus:
            continue
        p["fichier"] = _retrouver(str(p.get("filepath") or ""), racine)
        res.photos.setdefault(k, []).append(p)
    return res


def legende(p: dict) -> str:
    """« 50°C · 10/11/2026 14:05 · culot · incident » ; le commentaire à part."""
    quand = str(p.get("created_at") or "")
    if len(quand) >= 16 and quand[4] == "-":  # 2026-11-10 14:05:33 -> 10/11/2026 14:05
        quand = f"{quand[8:10]}/{quand[5:7]}/{quand[0:4]} {quand[11:16]}"
    morceaux = [str(p.get("temperature") or "").strip(), quand]
    if p.get("culot"):
        morceaux.append("culot")
    if p.get("incident"):
        morceaux.append("incident")
    return " · ".join(x for x in morceaux if x)


def pour_export(lu: Lecture, prelevements: list[dict]) -> list[dict]:
    """Bloc « photos » du JSON d'échange : [{"id": "S2", "aramis", "photos": [{"fichier", "legende", "commentaire"}]}]."""
    out = []
    for p in prelevements:
        ph = lu.photos.get(cle(p.get("aramis")), []) if p.get("aramis") else []
        ph = [x for x in ph if x.get("fichier")]
        if ph:
            out.append({"id": p["id"], "aramis": p.get("aramis") or "",
                        "photos": [{"fichier": x["fichier"], "legende": legende(x), "commentaire": str(x.get("comment") or "").strip()}
                                   for x in ph]})
    return out


def miniature(fichier: str, dossier_tmp: Path, cote: int = 900) -> str:
    """Copie réduite (JPEG, côté maximal `cote` px) pour les PDF / Word : une photo 4K ne gonfle pas le document."""
    from PIL import Image, ImageOps
    dossier_tmp.mkdir(parents=True, exist_ok=True)
    st = Path(fichier).stat()
    import hashlib
    cible = dossier_tmp / (hashlib.md5(f"{fichier}|{st.st_mtime_ns}|{cote}".encode()).hexdigest() + ".jpg")
    if not cible.exists():
        with Image.open(fichier) as im:
            im = ImageOps.exif_transpose(im).convert("RGB")
            im.thumbnail((cote, cote))
            im.save(cible, "JPEG", quality=85)
    return str(cible)


__all__ = ["DOSSIER_DEFAUT", "Lecture", "lire", "legende", "pour_export", "miniature", "dossier_effectif", "cle"]
