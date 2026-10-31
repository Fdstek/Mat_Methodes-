"""Opérations de la page Réglages (§6.5). Chaque fonction retourne les manips modifiées
(à enregistrer) et, si utile, un message court."""
from __future__ import annotations

from mat_methode.domain.models import ARCHIVEE, NON_REALISEE, Etat, Laboratoire, Manip, Operation, Reglages, nouvel_id
from mat_methode.domain.texte import minuscule_initiale, norm


def ajouter_laboratoire(r: Reglages, nom: str) -> bool:
    nom = nom.strip()
    if not nom or r.laboratoire(nom):
        return False
    r.laboratoires.append(Laboratoire(nom=nom, volume_ml=50, analyses=[]))
    return True


def renommer_laboratoire(r: Reglages, manips: list[Manip], ancien: str, nouveau: str) -> list[Manip]:
    """Renommer met à jour les échantillons existants."""
    nouveau = nouveau.strip()
    lab = r.laboratoire(ancien)
    if not lab or not nouveau or (nouveau != ancien and r.laboratoire(nouveau)):
        return []
    lab.nom = nouveau
    changees = []
    for m in manips:
        touche = False
        for p in m.prelevements:
            if p.labo == ancien:
                p.labo, touche = nouveau, True
        if touche:
            changees.append(m)
    return changees


def supprimer_laboratoire(r: Reglages, nom: str) -> None:
    """Les échantillons existants gardent leur libellé (§8.2)."""
    r.laboratoires = [l for l in r.laboratoires if l.nom != nom]


def ajouter_analyse(r: Reglages, nom: str) -> bool:
    nom = nom.strip()
    if not nom or nom in r.analyses:
        return False
    r.analyses.append(nom)
    return True


def supprimer_analyse(r: Reglages, nom: str) -> None:
    """Retire aussi l'analyse des laboratoires (pas des échantillons existants)."""
    r.analyses = [a for a in r.analyses if a != nom]
    for l in r.laboratoires:
        l.analyses = [a for a in l.analyses if a != nom]


def ajouter_simple(liste: list[str], nom: str) -> bool:
    nom = nom.strip()
    if not nom or any(norm(x) == norm(nom) for x in liste):
        return False
    liste.append(nom)
    return True


def ajouter_reactif(r: Reglages, nom: str) -> bool:
    nom = nom.strip()
    if not nom or r.reactif(nom):
        return False
    r.assurer_reactif(nom)
    return True


def supprimer_reactif(r: Reglages, nom: str) -> None:
    """Efface aussi le n° Scirius, l'emplacement, le fournisseur et le lot mémorisés (confirmation dans l'interface)."""
    r.reactifs = [x for x in r.reactifs if x.nom != nom]


def reactif_a_des_infos(r: Reglages, nom: str) -> bool:
    x = r.reactif(nom)
    return bool(x and (x.scirius or x.emplacement or x.fournisseur or x.lot))


def ajouter_etat(r: Reglages, nom: str) -> bool:
    nom = nom.strip()
    if not nom:
        return False
    r.etats.append(Etat(id="s" + nouvel_id(), nom=nom, ton="neutre"))
    return True


def supprimer_etat(r: Reglages, manips: list[Manip], index: int) -> tuple[list[Manip], str]:
    """Déplace les manips vers le premier état restant ; il faut en garder au moins un."""
    if len(r.etats) < 2 or not 0 <= index < len(r.etats):
        return [], ""
    x = r.etats.pop(index)
    cible = r.etats[0]
    changees = [m for m in manips if m.etat == x.id]
    for m in changees:
        m.etat = cible.id
    n = len(changees)
    msg = f"{n} manip{'s' if n > 1 else ''} passée{'s' if n > 1 else ''} en « {cible.nom} »" if n else "État supprimé"
    return changees, msg


def deplacer_etat(r: Reglages, index: int, sens: int) -> bool:
    j = index + sens
    if not (0 <= index < len(r.etats) and 0 <= j < len(r.etats)):
        return False
    r.etats[index], r.etats[j] = r.etats[j], r.etats[index]
    return True


def retirer_tag_partout(manips: list[Manip], tag: str) -> list[Manip]:
    changees = []
    for m in manips:
        avant = len(m.tags)
        m.tags = [t for t in m.tags if norm(t) != norm(tag)]
        if len(m.tags) != avant:
            changees.append(m)
    return changees


# ------------------------------------------------------------------ renommer (met à jour les manips)
def _renommer_liste(liste: list[str], ancien: str, nouveau: str) -> bool:
    """Renomme dans une liste de chaînes ; refuse un nom vide ou déjà pris par une autre entrée."""
    nouveau = nouveau.strip()
    if not nouveau or ancien not in liste or nouveau == ancien:
        return False
    if any(norm(x) == norm(nouveau) and x != ancien for x in liste):
        return False
    liste[liste.index(ancien)] = nouveau
    return True


def renommer_donneur(r: Reglages, manips: list[Manip], ancien: str, nouveau: str) -> list[Manip]:
    if not _renommer_liste(r.donneurs_ordre, ancien, nouveau):
        return []
    ch = [m for m in manips if m.contexte.donneur == ancien]
    for m in ch:
        m.contexte.donneur = nouveau.strip()
    return ch


def renommer_type(r: Reglages, manips: list[Manip], ancien: str, nouveau: str) -> list[Manip]:
    if not _renommer_liste(r.types_demande, ancien, nouveau):
        return []
    ch = [m for m in manips if m.contexte.type == ancien]
    for m in ch:
        m.contexte.type = nouveau.strip()
    return ch


def renommer_analyse(r: Reglages, manips: list[Manip], ancien: str, nouveau: str) -> list[Manip]:
    if not _renommer_liste(r.analyses, ancien, nouveau):
        return []
    nouveau = nouveau.strip()
    for lab in r.laboratoires:
        lab.analyses = [nouveau if a == ancien else a for a in lab.analyses]
    ch = []
    for m in manips:
        if any(ancien in p.analyses for p in m.prelevements):
            for p in m.prelevements:
                p.analyses = [nouveau if a == ancien else a for a in p.analyses]
            ch.append(m)
    return ch


def renommer_grande_etape(r: Reglages, manips: list[Manip], ancien: str, nouveau: str) -> list[Manip]:
    if not _renommer_liste(r.grandes_etapes, ancien, nouveau):
        return []
    ch = []
    for m in manips:
        gs = [g for g in m.groupes if g.nom == ancien]
        for g in gs:
            g.nom = nouveau.strip()
        if gs:
            ch.append(m)
    return ch


def renommer_reactif(r: Reglages, manips: list[Manip], ancien: str, nouveau: str) -> list[Manip]:
    """Le n° Scirius, l'emplacement, le fournisseur et le lot mémorisés suivent le nouveau nom."""
    nouveau = nouveau.strip()
    x = r.reactif(ancien)
    if x is None or not nouveau or nouveau == x.nom or (r.reactif(nouveau) and norm(nouveau) != norm(ancien)):
        return []
    x.nom = nouveau
    ch = []
    for m in manips:
        touche = False
        for e in m.etapes:
            for re_ in e.reactifs:
                if norm(re_.nom) == norm(ancien):
                    re_.nom, touche = nouveau, True
        if touche:
            ch.append(m)
    return ch


def renommer_tag(manips: list[Manip], ancien: str, nouveau: str) -> list[Manip]:
    """Renomme un tag dans toutes les manips (sans créer de doublon)."""
    nouveau = nouveau.strip().lstrip("#").strip()
    if not nouveau:
        return []
    ch = []
    for m in manips:
        if not any(norm(t) == norm(ancien) for t in m.tags):
            continue
        tags: list[str] = []
        for t in m.tags:
            v = nouveau if norm(t) == norm(ancien) else t
            if not any(norm(v) == norm(x) for x in tags):
                tags.append(v)
        if tags != m.tags:
            m.tags = tags
            ch.append(m)
    return ch


# ------------------------------------------------------------------ opérations (sous-étapes)
def ajouter_operation(r: Reglages, nom: str, participe: str = "") -> bool:
    nom = minuscule_initiale(nom.strip())
    if not nom or r.operation(nom):
        return False
    r.operations.append(Operation(nom=nom, participe=participe.strip()))
    return True


def renommer_operation(r: Reglages, manips: list[Manip], ancien: str, nouveau: str) -> list[Manip]:
    """Renomme l'opération dans la liste et dans les étapes de toutes les manips."""
    nouveau = minuscule_initiale(nouveau.strip())
    o = r.operation(ancien)
    if o is None or not nouveau or nouveau == o.nom or (r.operation(nouveau) and norm(nouveau) != norm(ancien)):
        return []
    ancien_nom, o.nom = o.nom, nouveau
    ch = []
    for m in manips:
        es = [e for e in m.etapes if norm(e.operation) == norm(ancien_nom)]
        for e in es:
            e.operation = nouveau
        if es:
            ch.append(m)
    return ch


def supprimer_operation(r: Reglages, nom: str) -> None:
    """Retire l'opération de la liste ; les étapes existantes gardent leur nom."""
    r.operations = [o for o in r.operations if o.nom != nom]


def deplacer_operation(r: Reglages, index: int, sens: int) -> bool:
    j = index + sens
    if not (0 <= index < len(r.operations) and 0 <= j < len(r.operations)):
        return False
    r.operations[index], r.operations[j] = r.operations[j], r.operations[index]
    return True


# ------------------------------------------------------------------ non réalisée
def basculer_non_realisee(r: Reglages, m: Manip) -> bool:
    """Marque la manip « non réalisée » (ou revient au premier état). Retourne True si elle vient d'être marquée."""
    if m.etat == NON_REALISEE:
        m.etat = r.etat_initial()
        return False
    m.etat = NON_REALISEE
    return True


def peut_supprimer(m: Manip) -> bool:
    """Seules les manips archivées ou non réalisées peuvent être supprimées."""
    return m.etat in (ARCHIVEE, NON_REALISEE)


def nom_etat(r: Reglages, ident: str) -> tuple[str, str]:
    """(libellé, ton) d'un état, y compris les états fixes."""
    if ident == ARCHIVEE:
        return "Archivée", "neutre"
    if ident == NON_REALISEE:
        return "Non réalisée", "danger"
    e = r.etat(ident)
    return (e.nom, e.ton) if e else ("—", "neutre")


def archiver_ou_restaurer(r: Reglages, m: Manip) -> bool:
    """Retourne True si la manip vient d'être archivée. Restaurer = premier état."""
    if m.etat == ARCHIVEE:
        m.etat = r.etat_initial()
        return False
    m.etat = ARCHIVEE
    return True


PALETTE_DONNEURS = ["#0F7B6C", "#2F6FB8", "#B26B00", "#7A4EB0", "#B8366B", "#4E7D1E"]  # 6 teintes, se répète


def couleur_donneur(r: Reglages, nom: str) -> str:
    """Couleur attribuée par le rang dans la liste des Réglages (ne change pas quand on filtre)."""
    try:
        i = r.donneurs_ordre.index(nom)
    except ValueError:
        i = 0
    return PALETTE_DONNEURS[i % len(PALETTE_DONNEURS)]
