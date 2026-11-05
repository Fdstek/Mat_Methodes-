"""Données partagées dans le dossier de l'application (§9.1).

    donnees\\reglages.json             réglages partagés (contrôle de révision + fusion)
    donnees\\manips\\<id>.json         UNE manip = UN fichier
    donnees\\verrous\\<id>.lock        qui édite quelle manip (battement toutes les 30 s, expire après 3 min)
    donnees\\preferences\\<user>.json  préférences propres à chacun
    donnees\\sauvegardes\\AAAA-MM-JJ\\  copie à la 1re ouverture du jour, 10 jours conservés
    donnees\\exports\\, logs\\

Pas de SQLite. Écritures atomiques dans le dossier du fichier visé (fichier.tmp puis os.replace).
"""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from mat_methode import SCHEMA_DONNEES
from mat_methode.domain.models import Manip, Reglages, maintenant_iso
from mat_methode.domain.texte import norm
from mat_methode.storage.fusion import LISTES, fusionner

log = logging.getLogger("mat_methode")

BATTEMENT_S = 30
EXPIRATION_VERROU_S = 180
JOURS_SAUVEGARDE = 10
NOM_VALIDE = re.compile(r"^[A-Za-z0-9_-]+\.json$")


class DonneesTropRecentes(Exception):
    """Fichier écrit par une version plus récente de l'application."""


def ecrire_atomique(chemin: Path, contenu: str) -> None:
    tmp = chemin.with_name(chemin.name + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(contenu)
        f.flush()
        os.fsync(f.fileno())
    for essai in range(8):  # Windows : le fichier peut être tenu un instant par la synchronisation OneDrive / SharePoint
        try:
            os.replace(tmp, chemin)
            return
        except PermissionError:
            if essai == 7:
                raise
            time.sleep(0.25)


def fichier_occupe(ex: BaseException) -> bool:
    """Vrai si le fichier est simplement tenu par un autre processus (WinError 32 ou 5) : à relire dans un instant."""
    return isinstance(ex, PermissionError) or getattr(ex, "winerror", None) in (5, 32)


def lire_json(chemin: Path, essais: int = 6, attente: float = 0.25) -> dict:
    """Lit un fichier JSON ; s'il est occupé par un autre processus, réessaie quelques fois avant d'abandonner."""
    for k in range(essais):
        try:
            with open(chemin, encoding="utf-8") as f:
                return json.load(f)
        except OSError as ex:
            if not fichier_occupe(ex) or k == essais - 1:
                raise
            time.sleep(attente)
    raise OSError(f"{chemin.name} : lecture impossible")  # inatteignable


def _dumps(d) -> str:
    return json.dumps(d, ensure_ascii=False, indent=2)


def etats_v5(etats: list) -> list:
    """Ajoute « À faire » et « Lancée » (après le premier état) s'ils manquent."""
    etats = list(etats)
    noms = {norm(e.get("nom", "")) for e in etats if isinstance(e, dict)}
    ids = {e.get("id") for e in etats if isinstance(e, dict)}
    pos = 1 if etats else 0
    for ident, nom, ton in (("afaire", "À faire", "neutre"), ("lancee", "Lancée", "info")):
        if ident not in ids and norm(nom) not in noms:
            etats.insert(pos, {"id": ident, "nom": nom, "ton": ton})
            pos += 1
    return etats


def etats_v6(etats: list) -> list:
    """Ajoute « Réalisée » (après « En cours », sinon à la fin) s'il manque."""
    etats = list(etats)
    if any(isinstance(e, dict) and (e.get("id") == "realisee" or norm(e.get("nom", "")) == "realisee") for e in etats):
        return etats
    pos = next((k + 1 for k, e in enumerate(etats) if isinstance(e, dict) and e.get("id") == "encours"), len(etats))
    etats.insert(pos, {"id": "realisee", "nom": "Réalisée", "ton": "ok"})
    return etats


def raison_illisible(ex: Exception) -> str:
    """Cause d'un fichier illisible, en une phrase courte (affichée dans la liste et gardée dans les logs)."""
    if isinstance(ex, json.JSONDecodeError):
        return "fichier incomplet ou abîmé, souvent une synchronisation interrompue"
    if hasattr(ex, "errors"):
        try:
            e = ex.errors()[0]
            return f"champ « {'.'.join(str(x) for x in e['loc'])} » : {e['msg']}"
        except Exception:
            pass
    return f"{type(ex).__name__} : {str(ex)[:80]}"


def migrer(d: dict, chemin: Path) -> dict:
    """Vérifie le numéro de schéma ; sauvegarde puis migre les données anciennes."""
    s = d.get("schema", 1)
    if s > SCHEMA_DONNEES:
        raise DonneesTropRecentes(f"{chemin.name} a été écrit par une version plus récente de Mat & Méthode. Mets à jour l’application.")
    if s < SCHEMA_DONNEES:
        shutil.copy2(chemin, chemin.with_name(chemin.name + f".schema{s}.bak"))
        # 1 -> 2 : grandes étapes (champs nouveaux avec valeurs par défaut, rien à convertir)
        if s < 5 and isinstance(d.get("etats"), list):  # Réglages, 4 -> 5 : états « À faire » et « Lancée » proposés
            d["etats"] = etats_v5(d["etats"])
        if s < 6 and isinstance(d.get("etats"), list):  # Réglages, 5 -> 6 : état « Réalisée » ; manips : commentaire d'échantillon
            d["etats"] = etats_v6(d["etats"])
        if s < 16 and isinstance(d.get("operations"), list):  # Réglages, 15 -> 16 : conditions par défaut des opérations
            from mat_methode.domain.models import DEFAUTS_OPERATIONS
            for o in d["operations"]:
                if isinstance(o, dict) and "defauts" not in o and o.get("nom") in DEFAUTS_OPERATIONS:
                    o["defauts"] = dict(DEFAUTS_OPERATIONS[o["nom"]])
        d["schema"] = SCHEMA_DONNEES
    return d


@dataclass
class Verrou:
    utilisateur: str
    pc: str
    depuis: str
    battement: str

    def expire(self, maintenant: datetime | None = None) -> bool:
        maintenant = maintenant or datetime.now(timezone.utc)
        try:
            b = datetime.fromisoformat(self.battement.replace("Z", "+00:00"))
        except ValueError:
            return True
        return (maintenant - b).total_seconds() > EXPIRATION_VERROU_S


@dataclass
class ResultatEnregistrement:
    ok: bool
    conflit: Optional[Manip] = None  # version trouvée sur le disque
    erreur: str = ""


@dataclass
class Liste:
    manips: list[Manip] = field(default_factory=list)
    illisibles: list[str] = field(default_factory=list)
    conflits: list[str] = field(default_factory=list)  # fichiers de conflit SharePoint / OneDrive
    occupes: list[str] = field(default_factory=list)  # identifiants des fichiers tenus un instant par un autre processus (relus plus tard)


class Stockage:
    def __init__(self, racine: Path, utilisateur: str, pc: str = "PC"):
        self.racine = Path(racine)
        self.donnees = self.racine / "donnees"
        self.utilisateur, self.pc = utilisateur, pc
        self.lecture_seule = False
        self.message = ""
        self._reglages_lus: Optional[Reglages] = None

    # ------------------------------------------------------------ dossiers
    @property
    def d_manips(self) -> Path:
        return self.donnees / "manips"

    @property
    def d_verrous(self) -> Path:
        return self.donnees / "verrous"

    @property
    def d_presence(self) -> Path:
        return self.donnees / "presence"

    @property
    def d_exports(self) -> Path:
        return self.donnees / "exports"

    @property
    def f_reglages(self) -> Path:
        return self.donnees / "reglages.json"

    def initialiser(self) -> bool:
        """Crée les dossiers. Retourne False (lecture seule) si le dossier est inaccessible."""
        try:
            for d in ("manips", "verrous", "preferences", "sauvegardes", "exports", "logs"):
                (self.donnees / d).mkdir(parents=True, exist_ok=True)
            essai = self.donnees / f".essai-{self.utilisateur}.tmp"
            essai.write_text("ok", encoding="utf-8")
            essai.unlink()
            self.lecture_seule, self.message = False, ""
            return True
        except OSError as ex:
            self.lecture_seule = True
            self.message = "Dossier inaccessible : ouverture en lecture seule. Tes modifications sont gardées en mémoire."
            log.warning("dossier inaccessible : %s", ex)
            return False

    def accessible(self) -> bool:
        try:
            essai = self.donnees / f".essai-{self.utilisateur}.tmp"
            essai.write_text("ok", encoding="utf-8")
            essai.unlink()
            return True
        except OSError:
            return False

    def configurer_logs(self) -> None:
        try:
            f = self.donnees / "logs" / f"{self.utilisateur}-{date.today().isoformat()}.log"
            h = logging.FileHandler(f, encoding="utf-8")
            h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
            log.addHandler(h)
            log.setLevel(logging.INFO)
        except OSError:
            pass

    # ------------------------------------------------------------ sauvegardes
    def sauvegarde_du_jour(self, aujourdhui: date | None = None) -> Optional[Path]:
        """Copie datée à la 1re ouverture du jour ; ne garde que les 10 derniers jours."""
        if self.lecture_seule:
            return None
        aujourdhui = aujourdhui or date.today()
        racine = self.donnees / "sauvegardes"
        cible = racine / aujourdhui.isoformat()
        try:
            if not cible.exists():
                tmp = racine / (aujourdhui.isoformat() + ".en-cours")
                shutil.rmtree(tmp, ignore_errors=True)
                tmp.mkdir(parents=True)
                if self.f_reglages.exists():
                    shutil.copy2(self.f_reglages, tmp / "reglages.json")
                if self.d_manips.exists():
                    shutil.copytree(self.d_manips, tmp / "manips")
                os.replace(tmp, cible)
            limite = aujourdhui - timedelta(days=JOURS_SAUVEGARDE)
            for d in racine.iterdir():
                try:
                    if d.is_dir() and date.fromisoformat(d.name) <= limite:
                        shutil.rmtree(d, ignore_errors=True)
                except ValueError:
                    continue
            return cible
        except OSError as ex:
            log.warning("sauvegarde impossible : %s", ex)
            return None

    # ------------------------------------------------------------ réglages
    def charger_reglages(self) -> Reglages:
        if self.f_reglages.exists():
            r = Reglages.model_validate(migrer(lire_json(self.f_reglages), self.f_reglages))
        else:
            r = Reglages()
        self._reglages_lus = r.model_copy(deep=True)
        return r

    def enregistrer_reglages(self, r: Reglages) -> str:
        """Enregistre ; en cas de modification simultanée, fusionne les listes. Retourne un message
        d'information (vide si rien de particulier). `r` est mis à jour avec le résultat."""
        if self.lecture_seule:
            raise OSError("lecture seule")
        info = ""
        base = self._reglages_lus or Reglages(rev=r.rev)
        if self.f_reglages.exists():
            disque = Reglages.model_validate(lire_json(self.f_reglages))
            if disque.rev != r.rev:
                fusion = fusionner(base, r, disque)
                for k in LISTES:  # toutes les listes fusionnables des Réglages
                    setattr(r, k, getattr(fusion, k))
                r.rev = disque.rev
                info = f"Réglages fusionnés avec les modifications de {disque.modifie_par or 'un autre utilisateur'}."
        r.rev += 1
        r.maj, r.modifie_par = maintenant_iso(), self.utilisateur
        ecrire_atomique(self.f_reglages, _dumps(r.to_json()))
        self._reglages_lus = r.model_copy(deep=True)
        return info

    def reglages_ont_change(self, r: Reglages) -> bool:
        try:
            return self.f_reglages.exists() and lire_json(self.f_reglages).get("rev", 0) != r.rev
        except (OSError, ValueError):
            return False

    # ------------------------------------------------------------ manips
    def chemin_manip(self, ident: str) -> Path:
        return self.d_manips / f"{ident}.json"

    def lister(self) -> Liste:
        res = Liste()
        if not self.d_manips.exists():
            return res
        for f in sorted(self.d_manips.glob("*.json")):
            try:
                d = lire_json(f, essais=3, attente=0.15)
                m = Manip.model_validate(migrer(d, f))
            except OSError as ex:
                if fichier_occupe(ex):  # pas un fichier abîmé : on garde la version en mémoire et on relit au prochain passage
                    log.info("fichier occupé %s : relu plus tard", f.name)
                    res.occupes.append(f.stem)
                    continue
                log.warning("fichier illisible %s : %s", f.name, ex)
                res.illisibles.append(f"{f.name} ({raison_illisible(ex)})")
                continue
            except DonneesTropRecentes as ex:
                res.illisibles.append(str(ex))
                continue
            except Exception as ex:  # un fichier illisible n'empêche jamais l'ouverture des autres
                log.warning("fichier illisible %s : %s", f.name, ex)
                res.illisibles.append(f"{f.name} ({raison_illisible(ex)})")
                continue
            if f.stem != m.id or not NOM_VALIDE.match(f.name):
                res.conflits.append(f.name)  # ex. « k97omty-PC-MARIE.json », « k97omty (1).json »
                continue
            res.manips.append(m)
        return res

    def lire_manip(self, ident: str) -> Optional[Manip]:
        f = self.chemin_manip(ident)
        if not f.exists():
            return None
        return Manip.model_validate(migrer(lire_json(f), f))

    def enregistrer_manip(self, m: Manip, forcer: bool = False) -> ResultatEnregistrement:
        """Contrôle de révision : si le fichier a changé depuis la lecture, on n'écrase pas."""
        if self.lecture_seule:
            return ResultatEnregistrement(False, erreur="Non enregistré : dossier inaccessible")
        f = self.chemin_manip(m.id)
        try:
            if f.exists() and not forcer:
                try:
                    disque = Manip.model_validate(lire_json(f))
                except Exception:
                    disque = None
                if disque is not None and disque.rev != m.rev:
                    return ResultatEnregistrement(False, conflit=disque)
                m.rev += 1
            m.maj, m.modifie_par = maintenant_iso(), self.utilisateur
            ecrire_atomique(f, _dumps(m.to_json()))
            return ResultatEnregistrement(True)
        except OSError as ex:
            log.warning("enregistrement impossible %s : %s", m.id, ex)
            return ResultatEnregistrement(False, erreur="Non enregistré : dossier inaccessible")

    def ecrire_tel_quel(self, m: Manip) -> None:
        """Écrit la manip sans toucher à sa version ni à sa date (restauration des exemples)."""
        ecrire_atomique(self.chemin_manip(m.id), _dumps(m.to_json()))

    def supprimer_manip(self, ident: str) -> None:
        f = self.chemin_manip(ident)
        if f.exists():
            f.unlink()
        self.liberer_verrou(ident)

    # ------------------------------------------------------------ verrous
    def lire_verrou(self, ident: str) -> Optional[Verrou]:
        f = self.d_verrous / f"{ident}.lock"
        try:
            return Verrou(**lire_json(f))
        except (OSError, ValueError, TypeError):
            return None

    def verrou_autre(self, ident: str) -> Optional[Verrou]:
        """Verrou valide posé par quelqu'un d'autre (ou par moi sur un autre PC), sinon None."""
        v = self.lire_verrou(ident)
        if v is None or v.expire() or (v.utilisateur == self.utilisateur and v.pc == self.pc):
            return None
        return v

    def prendre_verrou(self, ident: str) -> Optional[Verrou]:
        """Pose le verrou. Retourne le verrou de l'autre si la manip est déjà en cours d'édition."""
        autre = self.verrou_autre(ident)
        if autre:
            return autre
        if self.lecture_seule:
            return None
        v = self.lire_verrou(ident)
        depuis = v.depuis if v and v.utilisateur == self.utilisateur and v.pc == self.pc else maintenant_iso()
        try:
            ecrire_atomique(self.d_verrous / f"{ident}.lock",
                            _dumps({"utilisateur": self.utilisateur, "pc": self.pc, "depuis": depuis, "battement": maintenant_iso()}))
        except OSError:
            pass
        return None

    def battement(self, ident: str) -> None:
        self.prendre_verrou(ident)

    def liberer_verrou(self, ident: str) -> None:
        v = self.lire_verrou(ident)
        if v and v.utilisateur == self.utilisateur and v.pc == self.pc:
            try:
                (self.d_verrous / f"{ident}.lock").unlink()
            except OSError:
                pass

    # ------------------------------------------------------------ présence (qui a l'application ouverte, et sur quelle manip)
    def _f_presence(self) -> Path:
        return self.d_presence / f"{self.utilisateur}_{self.pc}.json".replace("\\", "_").replace("/", "_")

    def signaler_presence(self, manip: str | None) -> None:
        """Battement de présence (toutes les 30 s) : utilisateur, poste, manip ouverte."""
        if self.lecture_seule:
            return
        try:
            self.d_presence.mkdir(parents=True, exist_ok=True)
            ecrire_atomique(self._f_presence(), _dumps({"utilisateur": self.utilisateur, "pc": self.pc, "manip": manip or "",
                                                        "nom": getattr(self, "nom_affiche", ""), "initiales": getattr(self, "initiales", ""),
                                                        "battement": maintenant_iso()}))
        except OSError:
            pass

    def retirer_presence(self) -> None:
        try:
            self._f_presence().unlink()
        except OSError:
            pass

    def presences_autres(self, maintenant: datetime | None = None) -> list[dict]:
        """Les autres personnes (ou moi sur un autre poste) dont la présence date de moins de 3 minutes."""
        maintenant = maintenant or datetime.now(timezone.utc)
        out = []
        try:
            fichiers = sorted(self.d_presence.glob("*.json"))
        except OSError:
            return out
        for f in fichiers:
            try:
                d = lire_json(f)
                b = datetime.fromisoformat(str(d.get("battement", "")).replace("Z", "+00:00"))
            except (OSError, ValueError, TypeError):
                continue
            if (maintenant - b).total_seconds() > EXPIRATION_VERROU_S:
                continue
            if d.get("utilisateur") == self.utilisateur and d.get("pc") == self.pc:
                continue
            out.append(d)
        return out

    # ------------------------------------------------------------ préférences
    def lire_preferences(self) -> dict:
        try:
            return lire_json(self.donnees / "preferences" / f"{self.utilisateur}.json")
        except (OSError, ValueError):
            return {}

    def ecrire_preferences(self, p: dict) -> None:
        if self.lecture_seule:
            return
        try:
            ecrire_atomique(self.donnees / "preferences" / f"{self.utilisateur}.json", _dumps(p))
        except OSError:
            pass
