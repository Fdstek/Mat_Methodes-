"""Lien avec ana explorer (PTT Analysis Explorer), sur le même poste.

Mat & Méthode -> ana explorer : bouton à côté du n° d'expérience. Une demande est déposée dans
%LOCALAPPDATA%\\PTTAnalysisExplorer\\lien_matmethode\\demande.json (texte à rechercher, manip, dossier de retour) ;
ana explorer la lit (au démarrage, puis chaque seconde tant qu'il est ouvert), lance la recherche et ouvre l'expérience.
S'il n'est pas ouvert (pas de signe de vie récent dans instance.json), Mat & Méthode le lance.

ana explorer -> Mat & Méthode : bouton « → Mat & Méthode » d'ana explorer. Le tableau et / ou les graphiques sont
enregistrés en PNG dans le dossier de retour, donnees\\analyses\\<id de la manip>\\, avec une fiche .json à côté
(type, titre, date, auteur). Mat & Méthode les affiche (Rapport, Protocole) et les met dans le PDF et le Word.
Aucun champ n'est ajouté aux manips : le contenu du dossier fait foi.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

DOSSIER_LIEN = "lien_matmethode"
VIE_SECONDES = 15  # ana explorer écrit instance.json toutes les 5 s


def dossier_ana() -> Optional[Path]:
    base = os.environ.get("LOCALAPPDATA")
    return Path(base) / "PTTAnalysisExplorer" if base else None


def dossier_lien() -> Optional[Path]:
    d = dossier_ana()
    return d / DOSSIER_LIEN if d else None


def reglages_ana() -> dict:
    d = dossier_ana()
    try:
        r = json.loads((d / "settings.json").read_text(encoding="utf-8")) if d else {}
    except (OSError, ValueError):
        r = {}
    return r if isinstance(r, dict) else {}


def exe_auto() -> str:
    """Programme d'ana explorer noté par ana explorer lui-même au démarrage (clé « exe » de ses réglages)."""
    p = str(reglages_ana().get("exe") or "")
    return p if p and Path(p).exists() else ""


def ana_ouvert(lien: Path | None = None) -> bool:
    lien = lien or dossier_lien()
    try:
        d = json.loads((lien / "instance.json").read_text(encoding="utf-8"))
        return time.time() - float(d.get("t", 0)) < VIE_SECONDES
    except (OSError, ValueError, TypeError, AttributeError):
        return False


def deposer_demande(recherche: str, manip_id: str, manip_nom: str, retour: Path, lien: Path | None = None) -> Path:
    lien = lien or dossier_lien()
    if lien is None:
        raise OSError("dossier LOCALAPPDATA introuvable")
    lien.mkdir(parents=True, exist_ok=True)
    d = {"recherche": recherche.strip(), "manip_id": manip_id, "manip_nom": manip_nom, "retour": str(retour),
         "t": time.time(), "de": "Mat & Méthode"}
    f = lien / "demande.json"
    tmp = f.with_name(f"demande.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, f)
    return f


def commande(exe: str) -> list[str]:
    """Commande qui lance ana explorer : l'EXE, ou le script .py avec Python (pythonw sous Windows : pas de console)."""
    if exe.lower().endswith((".py", ".pyw")):
        py = Path(sys.executable)
        if not getattr(sys, "frozen", False):
            w = py.with_name("pythonw.exe")
            return [str(w if w.exists() else py), exe]
        return ["pyw" if os.name == "nt" else "python3", exe]
    return [exe]


def ouvrir_ana(recherche: str, manip_id: str, manip_nom: str, retour: Path, exe: str = "") -> str:
    """Dépose la demande et lance ana explorer s'il n'est pas déjà ouvert. Retourne un message pour la personne."""
    deposer_demande(recherche, manip_id, manip_nom, retour)
    if ana_ouvert():
        return f"Recherche « {recherche} » envoyée à ana explorer (déjà ouvert)"
    exe = exe or exe_auto()
    if not exe:
        raise FileNotFoundError("programme ana explorer introuvable : choisis-le dans Réglages › Résultats d’analyses "
                                "(ou ouvre ana explorer une fois, il se fera connaître)")
    if not Path(exe).exists():
        raise FileNotFoundError(f"programme ana explorer introuvable : {exe}")
    options = {"cwd": str(Path(exe).parent)}
    if os.name == "nt":
        options["creationflags"] = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    else:
        options["start_new_session"] = True
    subprocess.Popen(commande(exe), **options)
    return f"ana explorer s’ouvre et recherche « {recherche} » (le premier chargement peut prendre un moment)"


# ------------------------------------------------------------------ images renvoyées par ana explorer
TYPES = {"tableau": "Tableau", "graphiques": "Graphiques", "tableau_graphiques": "Tableau + graphiques"}


def dossier_retour(donnees: Path, manip_id: str) -> Path:
    return Path(donnees) / "analyses" / manip_id


def figures(donnees: Path, manip_id: str) -> list[dict]:
    """Images envoyées par ana explorer pour cette manip, de la plus ancienne à la plus récente :
    {"chemin", "titre", "sous_titre", "type", "libelle", "le", "par"}."""
    d = dossier_retour(donnees, manip_id)
    out = []
    try:
        pngs = sorted((p for p in d.glob("*.png") if p.is_file()), key=lambda p: (p.stat().st_mtime_ns, p.name))  # ordre d'arrivée
    except OSError:
        return []
    for p in pngs:
        try:
            fiche = json.loads(p.with_suffix(".json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            fiche = {}
        fiche = fiche if isinstance(fiche, dict) else {}
        typ = str(fiche.get("type") or "graphiques")
        le = str(fiche.get("le") or datetime.fromtimestamp(p.stat().st_mtime).strftime("%d/%m/%Y %H:%M"))
        out.append({"chemin": str(p), "titre": str(fiche.get("titre") or ""), "sous_titre": str(fiche.get("sous_titre") or ""),
                    "type": typ, "libelle": TYPES.get(typ, typ.capitalize()), "le": le, "par": str(fiche.get("par") or "")})
    return out


def retirer(chemin: str) -> None:
    """Retire une image (et sa fiche) de la manip : elle est rangée dans le sous-dossier « retirees », jamais effacée."""
    p = Path(chemin)
    dest = p.parent / "retirees"
    dest.mkdir(parents=True, exist_ok=True)
    for f in (p, p.with_suffix(".json")):
        if f.exists():
            os.replace(f, dest / f.name)


__all__ = ["ouvrir_ana", "deposer_demande", "ana_ouvert", "exe_auto", "dossier_retour", "figures", "retirer", "TYPES"]
