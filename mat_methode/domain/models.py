"""Modèle de données (cahier des charges §7)."""
from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from mat_methode import SCHEMA_DONNEES

Moment = Literal["avant", "pendant", "effluent"]
Ton = Literal["neutre", "info", "ok", "warn", "danger"]
ARCHIVEE = "archivee"


def nouvel_id() -> str:
    return secrets.token_hex(4)


def maintenant_iso() -> str:
    """Date-heure UTC au format ISO 8601 avec « Z » (ex. 2026-10-30T21:10:00Z)."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class _Modele(BaseModel):
    model_config = ConfigDict(extra="ignore", validate_assignment=True)


# ------------------------------------------------------------------ Réglages
class Laboratoire(_Modele):
    nom: str
    volume_ml: Optional[float] = 50
    analyses: list[str] = Field(default_factory=list)


class Etat(_Modele):
    id: str
    nom: str
    ton: Ton = "neutre"


class ReactifInventaire(_Modele):
    """Un nom de réactif des Réglages, avec les informations mémorisées depuis les étapes."""
    nom: str
    scirius: str = ""
    emplacement: str = ""
    fournisseur: str = ""
    lot: str = ""


ETATS_DEFAUT = [Etat(id="brouillon", nom="Brouillon", ton="warn"),
                Etat(id="encours", nom="En cours", ton="info"),
                Etat(id="terminee", nom="Terminée", ton="ok")]
TYPES_DEFAUT = ["Support", "R&D", "Technologique", "Test d’idée"]
ANALYSES_DEFAUT = ["FFA / indice d’acide", "Teneur en eau", "Impuretés insolubles", "Métaux (ICP)", "Phosphore"]
DONNEURS_DEFAUT = ["Interne · R&D", "Interne · Production", "Client externe"]
GRANDES_ETAPES_DEFAUT = ["Degumming", "Neutralisation", "Blanchiment", "Désodorisation", "Winterisation"]


class Reglages(_Modele):
    schema_: int = Field(default=SCHEMA_DONNEES, alias="schema")
    rev: int = 0
    maj: str = ""
    modifie_par: str = ""
    laboratoires: list[Laboratoire] = Field(default_factory=lambda: [
        Laboratoire(nom="Labo interne", volume_ml=50, analyses=ANALYSES_DEFAUT[:3]),
        Laboratoire(nom="Labo externe", volume_ml=100, analyses=ANALYSES_DEFAUT[3:])])
    analyses: list[str] = Field(default_factory=lambda: list(ANALYSES_DEFAUT))
    donneurs_ordre: list[str] = Field(default_factory=lambda: list(DONNEURS_DEFAUT))
    types_demande: list[str] = Field(default_factory=lambda: list(TYPES_DEFAUT))
    etats: list[Etat] = Field(default_factory=lambda: [e.model_copy() for e in ETATS_DEFAUT])
    reactifs: list[ReactifInventaire] = Field(default_factory=list)
    grandes_etapes: list[str] = Field(default_factory=lambda: list(GRANDES_ETAPES_DEFAUT))

    model_config = ConfigDict(extra="ignore", populate_by_name=True, validate_assignment=True)

    def etat_initial(self) -> str:
        return self.etats[0].id if self.etats else "brouillon"

    def etat(self, ident: str) -> Optional[Etat]:
        return next((e for e in self.etats if e.id == ident), None)

    def laboratoire(self, nom: str) -> Optional[Laboratoire]:
        return next((l for l in self.laboratoires if l.nom == nom), None)

    def reactif(self, nom: str) -> Optional[ReactifInventaire]:
        from mat_methode.domain.texte import norm
        k = norm(nom)
        return next((r for r in self.reactifs if norm(r.nom) == k), None)

    def assurer_reactif(self, nom: str) -> ReactifInventaire | None:
        """Ajoute le nom à la liste s'il n'y est pas (import d'un ancien rapport)."""
        nom = (nom or "").strip()
        if not nom:
            return None
        r = self.reactif(nom)
        if r is None:
            r = ReactifInventaire(nom=nom)
            self.reactifs.append(r)
        return r

    def to_json(self) -> dict:
        return self.model_dump(by_alias=True)


# ------------------------------------------------------------------ Manip
class Vide(_Modele):
    mbar: Optional[float] = None


class Condition(_Modele):
    nom: str = ""
    valeur: str = ""


class ReactifEtape(_Modele):
    nom: str = ""
    quantite: str = ""


class Etape(_Modele):
    id: str = Field(default_factory=nouvel_id)
    operation: str
    temperature_c: Optional[float] = None
    duree_min: Optional[float] = None
    agitation_trmin: Optional[float] = None
    filtre_um: Optional[float] = None
    vide: Optional[Vide] = None
    equipements: list[str] = Field(default_factory=list)
    autres: list[Condition] = Field(default_factory=list)
    reactifs: list[ReactifEtape] = Field(default_factory=list)
    remarque: str = ""
    groupe_id: Optional[str] = None  # grande étape (Degumming…) qui contient cette étape


class Prelevement(_Modele):
    id: str = Field(default_factory=nouvel_id)
    etape_id: Optional[str] = None  # None = entrée (avant traitement)
    moment: Moment = "avant"
    temps_min: Optional[float] = None
    volume_ml: Optional[float] = 50
    labo: str = ""
    analyses: list[str] = Field(default_factory=list)
    scirius: str = ""
    aramis: str = ""


class Contexte(_Modele):
    donneur: str = ""
    type: str = ""
    objectif: str = ""
    idee: str = ""
    precisions: str = ""
    ref: str = ""
    date: str = ""
    operateur: str = ""
    volume_depart_ml: Optional[float] = 1000
    matiere: str = "Graisse animale"
    lot: str = ""


class Communes(_Modele):
    temperature_c: Optional[float] = None
    agitation_trmin: Optional[float] = None
    vide: Optional[Vide] = None


class Lancement(_Modele):
    le: str
    par: str


class LigneJournal(_Modele):
    t: str
    par: str
    txt: str


class Groupe(_Modele):
    """Grande étape (ex. Degumming) : regroupe des étapes consécutives du flux."""
    id: str = Field(default_factory=nouvel_id)
    nom: str


class Manip(_Modele):
    schema_: int = Field(default=SCHEMA_DONNEES, alias="schema")
    id: str = Field(default_factory=nouvel_id)
    nom: str = "Nouvelle manip"
    etat: str = "brouillon"
    rev: int = 1
    maj: str = Field(default_factory=maintenant_iso)
    modifie_par: str = ""
    lancee: Optional[Lancement] = None
    journal: list[LigneJournal] = Field(default_factory=list)
    base: Optional[dict] = None  # photo de référence du contenu suivi (§8.9)
    tags: list[str] = Field(default_factory=list)
    contexte: Contexte = Field(default_factory=Contexte)
    communes: Communes = Field(default_factory=Communes)
    etapes: list[Etape] = Field(default_factory=list)
    prelevements: list[Prelevement] = Field(default_factory=list)
    groupes: list[Groupe] = Field(default_factory=list)

    model_config = ConfigDict(extra="ignore", populate_by_name=True, validate_assignment=True)

    @property
    def archivee(self) -> bool:
        return self.etat == ARCHIVEE

    def etape(self, ident: str | None) -> Optional[Etape]:
        return next((e for e in self.etapes if e.id == ident), None)

    def groupe(self, ident: str | None) -> Optional[Groupe]:
        return next((g for g in self.groupes if g.id == ident), None)

    def prelevement(self, ident: str) -> Optional[Prelevement]:
        return next((p for p in self.prelevements if p.id == ident), None)

    def to_json(self) -> dict:
        return self.model_dump(by_alias=True)

    def copie(self) -> "Manip":
        return Manip.model_validate(self.to_json())
