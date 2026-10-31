"""Opérations de la page Réglages (§6.5). Chaque fonction retourne les manips modifiées
(à enregistrer) et, si utile, un message court."""
from __future__ import annotations

from mat_methode.domain.models import ARCHIVEE, Etat, Laboratoire, Manip, Reglages, nouvel_id
from mat_methode.domain.texte import norm


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
