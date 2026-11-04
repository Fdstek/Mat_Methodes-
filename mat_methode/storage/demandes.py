"""Lecture et écriture des demandes (bugs et idées) dans `donnees\\demandes`, partagées entre les utilisateurs."""
from __future__ import annotations

import json
import logging
import re
import shutil
from pathlib import Path

from mat_methode.domain.demandes import Demande
from mat_methode.storage.stockage import Stockage, ecrire_atomique

log = logging.getLogger("mat_methode")


def dossier(st: Stockage) -> Path:
    return st.donnees / "demandes"


def lister(st: Stockage) -> list[Demande]:
    """Les demandes, la plus récente d'abord (les fichiers illisibles sont ignorés)."""
    out = []
    for f in sorted(dossier(st).glob("*.json")):
        try:
            out.append(Demande.model_validate(json.loads(f.read_text(encoding="utf-8"))))
        except (OSError, ValueError) as ex:
            log.warning("demande illisible %s : %s", f.name, ex)
    return sorted(out, key=lambda d: d.cree, reverse=True)


def enregistrer(st: Stockage, d: Demande) -> None:
    dossier(st).mkdir(parents=True, exist_ok=True)
    ecrire_atomique(dossier(st) / f"{d.id}.json", json.dumps(d.model_dump(), ensure_ascii=False, indent=2))


def relire(st: Stockage, ident: str) -> Demande | None:
    try:
        return Demande.model_validate(json.loads((dossier(st) / f"{ident}.json").read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return None


def dossier_pieces(st: Stockage, d: Demande) -> Path:
    return dossier(st) / "pieces" / d.id


def joindre(st: Stockage, d: Demande, source: str | Path) -> str:
    """Copie un fichier dans le dossier des pièces jointes de la demande ; retourne le nom enregistré."""
    src = Path(source)
    cible_dir = dossier_pieces(st, d)
    cible_dir.mkdir(parents=True, exist_ok=True)
    nom = re.sub(r'[<>:"/\\|?*]', "_", src.name) or "piece"
    cible, k = cible_dir / nom, 1
    while cible.exists():
        k += 1
        cible = cible_dir / f"{src.stem}_{k}{src.suffix}"
    shutil.copy2(src, cible)
    d.pieces = d.pieces + [cible.name]
    return cible.name
