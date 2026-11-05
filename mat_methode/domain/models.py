"""Modèle de données (cahier des charges §7)."""
from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from mat_methode import SCHEMA_DONNEES
from mat_methode.domain.catalogue import OPERATIONS

Moment = Literal["avant", "pendant", "effluent"]
Ton = Literal["neutre", "info", "ok", "warn", "danger"]
ARCHIVEE = "archivee"
# Statuts (fixes) : Brouillon -> Validée (Définition) -> En cours -> Réalisée (Protocole) ; Annulée possible partout.
BROUILLON, VALIDEE, ENCOURS, REALISEE, ANNULEE = "brouillon", "validee", "encours", "realisee", "annulee"
NON_REALISEE = ANNULEE  # ancien nom
STATUTS: dict[str, tuple[str, str]] = {BROUILLON: ("Brouillon", "warn"), VALIDEE: ("Validée", "info"), ENCOURS: ("En cours", "info"),
                                       REALISEE: ("Réalisée", "ok"), ANNULEE: ("Annulée", "danger")}
STATUTS_DEFINITION = [BROUILLON, VALIDEE, ANNULEE]  # choisis dans « Définition Mat & Méthode »
STATUTS_PROTOCOLE = [VALIDEE, ENCOURS, REALISEE, ANNULEE]  # choisis dans « Protocole »
ANCIENS_ETATS = {"afaire": VALIDEE, "lancee": ENCOURS, "terminee": REALISEE, "non_realisee": ANNULEE}  # schéma < 7


def statut_connu(etat: str) -> str:
    """Ramène un ancien état (ou un état personnalisé des Réglages) sur les statuts fixes."""
    if etat == ARCHIVEE or etat in STATUTS:
        return etat
    return ANCIENS_ETATS.get(etat, BROUILLON)


def nouvel_id() -> str:
    return secrets.token_hex(4)


def maintenant_iso() -> str:
    """Date-heure UTC au format ISO 8601 avec « Z » (ex. 2026-10-30T21:10:00Z)."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


UNITES_REACTIFS_DEFAUT = ["mL", "g", "µL", "mg", "%", "mol/L"]
VITESSES_DEFAUT = [100.0, 200.0, 300.0, 500.0, 800.0]
VITESSES_RCF_DEFAUT = [500.0, 1000.0, 3000.0, 5000.0, 10000.0]  # force centrifuge relative (g)
UNITES_VITESSE = ("tr/min", "g")  # g = RCF (force centrifuge relative)
DUREES = {"s": 1 / 60, "min": 1.0, "h": 60.0, "jour": 1440.0, "semaine": 10080.0}  # unité de durée -> minutes
UNITES_DUREE_DEFAUT = list(DUREES)
CONDITIONS_OPERATION = (("temperature_c", "Chauffage", "°C"), ("agitation_trmin", "Agitation / vitesse", "tr/min"),
                        ("vide", "Sous vide", "mbar"), ("filtre_um", "Membrane filtrante", "µm"), ("duree_min", "Durée", "min"))
DEFAUTS_OPERATIONS = {"chauffage": {"temperature_c": 60.0, "agitation_trmin": 300.0}, "filtration": {"filtre_um": 5.0}}


class _Modele(BaseModel):
    model_config = ConfigDict(extra="ignore", validate_assignment=True)


# ------------------------------------------------------------------ Réglages
class Laboratoire(_Modele):
    nom: str
    volume_ml: Optional[float] = 50
    analyses: list[str] = Field(default_factory=list)


class Operation(_Modele):
    """Opération proposée dans « Définir le flux » (sous-étape), avec le participe passé utilisé dans le texte 2.3."""
    nom: str
    participe: str = ""
    defauts: dict[str, float] = Field(default_factory=dict)  # conditions actives d'office pour cette opération (clé -> valeur par défaut ; vide : 0 = sans pression)


def initiales_de(nom: str) -> str:
    """« Pierre BURGUN » -> « PB » ; « Jean-Marc DUPONT » -> « JMD »."""
    out = ""
    for mot in (nom or "").replace("·", " ").split():
        for part in mot.split("-"):
            lettres = [c for c in part if c.isalpha()]
            if lettres:
                out += lettres[0].upper()
    return out


class Personne(_Modele):
    """Donneur d'ordre (ou opérateur) : nom affiché, initiales (référence des manips), IGG Windows."""
    nom: str
    initiales: str = ""
    igg: str = ""
    manipule: bool = False  # fait des manips : proposé en tête de la liste « Attribué à »
    fait_mm: bool = False  # fait des Mat & Méthode : proposé en tête de la liste « Donneur d'ordre »

    def sigle(self) -> str:
        return (self.initiales or initiales_de(self.nom)).strip().upper()


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
                Etat(id="afaire", nom="À faire", ton="neutre"),
                Etat(id="lancee", nom="Lancée", ton="info"),
                Etat(id="encours", nom="En cours", ton="info"),
                Etat(id="realisee", nom="Réalisée", ton="ok"),
                Etat(id="terminee", nom="Terminée", ton="ok")]
TYPES_DEFAUT = ["Support", "R&D", "Technologique", "Test d’idée"]
ANALYSES_DEFAUT = ["FFA / indice d’acide", "Teneur en eau", "Impuretés insolubles", "Métaux (ICP)", "Phosphore"]
DONNEURS_DEFAUT = ["Pierre BURGUN"]
VOLUMES_DEFAUT = [30, 60, 120, 250, 500, 1000]  # mL ; 1000 = 1 L
MATERIEL_DEFAUT = ["Plaque chauffante agitatrice", "Entonnoir Büchner", "Fiole à vide", "Membrane 5 µm", "Ampoule à décanter 500 mL",
                   "Étuve", "Centrifugeuse", "Broyeur", "Bain-marie", "Évaporateur rotatif"]
CATEGORIES_A_FAIRE_DEFAUT = ["Réflexion", "Matériel manquant", "Réactif manquant", "Autre"]
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
    personnes: list[Personne] = Field(default_factory=lambda: [Personne(nom=n, initiales=initiales_de(n)) for n in DONNEURS_DEFAUT])
    scirius_noms: list[str] = Field(default_factory=lambda: ["C.LACOUX", "P.BURGUN"])  # destinataires filtrés par défaut
    scirius_fichier: str = ""  # chemin d'un fichier Scirius choisi à la main (sinon recherche automatique)
    types_demande: list[str] = Field(default_factory=lambda: list(TYPES_DEFAUT))
    etats: list[Etat] = Field(default_factory=lambda: [e.model_copy() for e in ETATS_DEFAUT])
    reactifs: list[ReactifInventaire] = Field(default_factory=list)
    grandes_etapes: list[str] = Field(default_factory=lambda: list(GRANDES_ETAPES_DEFAUT))
    materiels: list[str] = Field(default_factory=lambda: list(MATERIEL_DEFAUT))  # matériel proposé dans les étapes
    categories_a_faire: list[str] = Field(default_factory=lambda: list(CATEGORIES_A_FAIRE_DEFAUT))
    volumes_ml: list[float] = Field(default_factory=lambda: list(VOLUMES_DEFAUT))  # volumes proposés pour un échantillon
    operations: list[Operation] = Field(default_factory=lambda: [Operation(nom=k, participe=v, defauts=dict(DEFAUTS_OPERATIONS.get(k, {}))) for k, v in OPERATIONS.items()])
    unites_reactifs: list[str] = Field(default_factory=lambda: list(UNITES_REACTIFS_DEFAUT))  # unités proposées pour les quantités de réactifs
    vitesses_agitation: list[float] = Field(default_factory=lambda: list(VITESSES_DEFAUT))  # vitesses d'agitation proposées (tr/min)
    vitesses_rcf: list[float] = Field(default_factory=lambda: list(VITESSES_RCF_DEFAUT))  # vitesses de centrifugation proposées en g (RCF)
    unites_duree: list[str] = Field(default_factory=lambda: list(UNITES_DUREE_DEFAUT))  # unités de durée proposées (s, min, h, jour, semaine)
    ordre_protocoles: list[str] = Field(default_factory=list)  # identifiants des manips, dans l'ordre de réalisation (Protocole)
    ordre_tags: list[str] = Field(default_factory=list)  # ordre choisi des tags (Réglages › Tags) ; les autres suivent, par ordre alphabétique
    couleurs_tags: dict[str, str] = Field(default_factory=dict)  # tag (sans casse ni accents) -> couleur choisie ; sinon couleur automatique
    couleurs_types: dict[str, str] = Field(default_factory=dict)  # type de demande -> couleur choisie ; sinon couleur automatique

    model_config = ConfigDict(extra="ignore", populate_by_name=True, validate_assignment=True)

    @model_validator(mode="before")
    @classmethod
    def _ancien_format(cls, d):
        """Schéma 2 : « donneurs_ordre » était une liste de noms."""
        if isinstance(d, dict) and "personnes" not in d and isinstance(d.get("donneurs_ordre"), list):
            d = dict(d)
            d["personnes"] = [{"nom": n, "initiales": initiales_de(n)} for n in d.pop("donneurs_ordre") if n]
        return d

    @property
    def donneurs_ordre(self) -> list[str]:
        return [p.nom for p in self.personnes]

    @property
    def donneurs_proposes(self) -> list[str]:
        """Donneurs d'ordre proposés : ceux qui font des Mat & Méthode d'abord (ordre des Réglages), puis les autres."""
        return [p.nom for p in self.personnes if p.fait_mm] + [p.nom for p in self.personnes if not p.fait_mm]

    @property
    def attributions(self) -> list[str]:
        """Personnes proposées dans « Attribué à » : celles qui font des manips d'abord (ordre des Réglages), puis les autres."""
        return [p.nom for p in self.personnes if p.manipule] + [p.nom for p in self.personnes if not p.manipule]

    def personne(self, nom: str | None) -> Optional[Personne]:
        return next((p for p in self.personnes if p.nom == nom), None)

    def personne_igg(self, igg: str) -> Optional[Personne]:
        igg = (igg or "").strip().upper()
        return next((p for p in self.personnes if igg and p.igg.strip().upper() == igg), None)

    def etat_initial(self) -> str:
        return BROUILLON

    def etat(self, ident: str) -> Optional[Etat]:
        return next((e for e in self.etats if e.id == ident), None)

    def laboratoire(self, nom: str) -> Optional[Laboratoire]:
        return next((l for l in self.laboratoires if l.nom == nom), None)

    def reactif(self, nom: str) -> Optional[ReactifInventaire]:
        from mat_methode.domain.texte import norm
        k = norm(nom)
        return next((r for r in self.reactifs if norm(r.nom) == k), None)

    def operation(self, nom: str) -> Optional[Operation]:
        from mat_methode.domain.texte import norm
        k = norm(nom)
        return next((o for o in self.operations if norm(o.nom) == k), None)

    def participe(self, operation: str) -> str:
        """Participe passé d'une opération (« filtré ») ; sinon « traité (nom de l'étape) »."""
        o = self.operation(operation)
        if o is not None and o.participe.strip():
            return o.participe.strip()
        return OPERATIONS.get(operation, f"traité ({operation})")

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
    unite: str = ""  # unité choisie dans la liste des Réglages (vide = quantité écrite en texte libre)

    @property
    def quantite_complete(self) -> str:
        """« 250 mL » : la quantité suivie de son unité."""
        return (f"{self.quantite} {self.unite}".strip() if self.quantite.strip() else "")


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
    apports: dict[str, float] = Field(default_factory=dict)  # étape qui réunit des voies : voie -> quantité prise (mL) ; absent = toute la sortie
    duree_unite: str = "min"  # unité choisie pour saisir la durée (la durée reste stockée en minutes)
    vitesse_unite: str = "tr/min"  # « tr/min » ou « g » (RCF) pour l'agitation / la centrifugation
    parallele_id: Optional[str] = None  # bloc « en parallèle » qui contient cette étape (jamais avec une grande étape)
    voie_id: Optional[str] = None  # voie du bloc en parallèle (A, B…)


class Matiere(_Modele):
    """Autre matière apportée à une voie en parallèle (réactif, quantité et unité)."""
    nom: str = ""
    quantite: str = ""
    unite: str = ""


class Voie(_Modele):
    id: str = Field(default_factory=nouvel_id)
    nom: str = ""  # facultatif (ex. « phase huile ») : la lettre A, B… vient de la place de la voie
    part: Optional[float] = None  # part de la sortie de l'étape précédente (ou du volume de départ) reçue par la voie ; vide = part égale
    part_unite: str = "%"  # « % » ou « mL »
    autres: list[Matiere] = Field(default_factory=list)  # autres matières ajoutées au début de la voie


class Parallele(_Modele):
    """Étapes réalisées en même temps (voies côte à côte) ; l'étape qui suit le bloc réunit les voies."""
    id: str = Field(default_factory=nouvel_id)
    voies: list[Voie] = Field(default_factory=lambda: [Voie(), Voie()])


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
    commentaire: str = ""  # une ligne libre (ex. « prélever sous agitation »)


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
    scirius: str = ""  # n° Scirius de la charge de départ
    fournisseur: str = ""  # fournisseur de la charge de départ
    emplacement: str = ""  # où est stockée la charge de départ (armoire, chambre froide…)
    experience: str = ""  # n° d'expérience (sous le titre de la manip, dans les listes et les PDF)
    attribue: str = ""  # personne à qui la manip est attribuée (nom, voir Réglages › Personnes)


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


class ChangementStatut(_Modele):
    """Qui a changé le statut, quand, et de quoi vers quoi (visible dans l'application, pas dans les documents)."""
    t: str
    par: str  # IGG de la personne (le nom est retrouvé dans les Réglages à l'affichage)
    de: str
    vers: str


class Groupe(_Modele):
    """Grande étape (ex. Degumming) : regroupe des étapes consécutives du flux."""
    id: str = Field(default_factory=nouvel_id)
    nom: str


class Tache(_Modele):
    """Point « à faire » d'une manip : réflexion, matériel ou réactif manquant… (n'apparaît pas dans le rapport)."""
    id: str = Field(default_factory=nouvel_id)
    categorie: str = ""
    texte: str = ""
    fait: bool = False
    par: str = ""
    le: str = ""


class RapportEmis(_Modele):
    """Document émis pour une manip (rapport PDF/Word, protocole…) : où il a été enregistré, quand, par qui."""
    type: str = "rapport"  # rapport | protocole (« ordre » : ancien nom du protocole)
    fmt: str = "pdf"
    chemin: str = ""
    le: str = ""
    par: str = ""


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
    paralleles: list[Parallele] = Field(default_factory=list)  # blocs d'étapes en parallèle
    a_faire: list[Tache] = Field(default_factory=list)
    rapports: list[RapportEmis] = Field(default_factory=list)  # documents émis, le plus récent en dernier
    statuts: list[ChangementStatut] = Field(default_factory=list)  # historique des changements de statut

    model_config = ConfigDict(extra="ignore", populate_by_name=True, validate_assignment=True)

    @model_validator(mode="before")
    @classmethod
    def _anciens_etats(cls, d):
        if isinstance(d, dict) and isinstance(d.get("etat"), str) and d["etat"] != statut_connu(d["etat"]):
            d = dict(d, etat=statut_connu(d["etat"]))
        return d

    @property
    def archivee(self) -> bool:
        return self.etat == ARCHIVEE

    def etape(self, ident: str | None) -> Optional[Etape]:
        return next((e for e in self.etapes if e.id == ident), None)

    def groupe(self, ident: str | None) -> Optional[Groupe]:
        return next((g for g in self.groupes if g.id == ident), None)

    def parallele(self, ident: str | None) -> Optional[Parallele]:
        return next((p for p in self.paralleles if p.id == ident), None)

    def prelevement(self, ident: str) -> Optional[Prelevement]:
        return next((p for p in self.prelevements if p.id == ident), None)

    def to_json(self) -> dict:
        return self.model_dump(by_alias=True)

    def copie(self) -> "Manip":
        return Manip.model_validate(self.to_json())
