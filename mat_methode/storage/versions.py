"""Versions d'une manip : un fichier par enregistrement, jamais réécrit.

    donnees\\manips\\<id>\\v000012_<poste>_<alea>.json

Chaque fichier n'est écrit qu'une fois, par un seul poste : la synchronisation OneDrive / SharePoint ne peut donc plus créer de
« copie de conflit ». Un fichier commence par la liste de ses « parents » (les versions dont il découle). La version courante est celle
qui n'est le parent d'aucune autre. Si deux postes ont enregistré en même temps à partir de la même version, il y a deux versions
courantes : un conflit à trancher (voir `Stockage.resoudre_conflit`). Rien n'est jamais écrasé."""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import secrets
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger("mat_methode")

NOM_VERSION = re.compile(r"^v(\d{6})_(.+)\.json$")
ENTETE = re.compile(r'"parents"\s*:\s*\[([^\]]*)\]')
DOSSIER_ANCIEN = "_ancien"  # fichiers de l'ancien format (un fichier par manip), gardés après conversion
VERSIONS_GARDEES = 25


@dataclass
class Version:
    fichier: str
    chemin: Path
    rev: int
    poste: str
    parents: list[str] = field(default_factory=list)
    taille: int = 0
    mtime: int = 0


_cache: dict[tuple[str, int, int], list[str]] = {}  # (chemin, taille, mtime) -> parents


def _parents(chemin: Path, taille: int, mtime: int) -> list[str]:
    cle = (str(chemin), taille, mtime)
    if cle not in _cache:
        try:
            with open(chemin, "rb") as f:
                debut = f.read(4096).decode("utf-8", errors="ignore")
        except OSError:
            return []
        mt = ENTETE.search(debut)
        _cache[cle] = re.findall(r'"([^"]+)"', mt.group(1)) if mt else []
    return _cache[cle]


def versions(dossier: Path) -> list[Version]:
    """Toutes les versions d'une manip (les noms qui ne sont pas des versions sont ignorés)."""
    out = []
    try:
        fichiers = list(dossier.iterdir())
    except OSError:
        return out
    for f in fichiers:
        mt = NOM_VERSION.match(f.name)
        if not mt or not f.is_file():
            continue
        try:
            st = f.stat()
        except OSError:
            continue
        out.append(Version(f.name, f, int(mt.group(1)), mt.group(2), _parents(f, st.st_size, st.st_mtime_ns), st.st_size, st.st_mtime_ns))
    return sorted(out, key=lambda v: (v.rev, v.fichier))


def empreinte(chemin: Path) -> str:
    """Contenu de la version sans la liste des parents (deux postes qui ont écrit la même chose donnent la même empreinte)."""
    try:
        d = json.loads(chemin.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "illisible:" + chemin.name
    d.pop("parents", None)
    return hashlib.sha1(json.dumps(d, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def tetes(dossier: Path) -> list[Version]:
    """Versions courantes : celles dont aucune autre ne découle. Deux versions de même contenu comptent pour une seule."""
    toutes = versions(dossier)
    parents = {p for v in toutes for p in v.parents}
    candidates = [v for v in toutes if v.fichier not in parents]
    if len(candidates) > 1:
        vues: dict[str, Version] = {}
        for v in sorted(candidates, key=lambda v: (v.rev, v.fichier), reverse=True):
            vues.setdefault(empreinte(v.chemin), v)
        candidates = sorted(vues.values(), key=lambda v: (v.rev, v.fichier))
    return candidates


def nom_nouvelle_version(rev: int, poste: str) -> str:
    poste = re.sub(r"[^A-Za-z0-9-]", "", poste) or "PC"
    return f"v{rev:06d}_{poste}_{secrets.token_hex(2)}.json"


def ecrire_version(dossier: Path, rev: int, poste: str, parents: list[str], contenu: dict, ecrire) -> Version:
    """Écrit une nouvelle version (fichier neuf, jamais écrasé). `ecrire(chemin, texte)` fait l'écriture atomique."""
    dossier.mkdir(parents=True, exist_ok=True)
    nom = nom_nouvelle_version(rev, poste)
    texte = json.dumps({"parents": list(parents), **contenu}, ensure_ascii=False, indent=2)
    chemin = dossier / nom
    ecrire(chemin, texte)
    st = chemin.stat()
    return Version(nom, chemin, rev, poste, list(parents), st.st_size, st.st_mtime_ns)


def elaguer(dossier: Path, gardees: int = VERSIONS_GARDEES) -> int:
    """Supprime les plus anciennes versions (jamais une version courante, ni le parent d'une version courante récente)."""
    toutes = versions(dossier)
    if len(toutes) <= gardees:
        return 0
    courantes = {v.fichier for v in tetes(dossier)}
    parents_courants = {p for v in toutes if v.fichier in courantes for p in v.parents}
    n = 0
    for v in toutes[: len(toutes) - gardees]:
        if v.fichier in courantes or v.fichier in parents_courants:
            continue
        try:
            os.remove(v.chemin)
            n += 1
        except OSError:
            pass
    return n
