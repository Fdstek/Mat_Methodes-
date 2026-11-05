"""Opérations de la page Réglages (§6.5). Chaque fonction retourne les manips modifiées
(à enregistrer) et, si utile, un message court."""
from __future__ import annotations

from mat_methode.domain.models import ANNULEE, ARCHIVEE, STATUTS, Condition, ConditionMateriel, Laboratoire, Manip, Operation, Reglages
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
    p = r.personne(ancien)
    nouveau = nouveau.strip()
    if p is None or not nouveau or nouveau == ancien or any(norm(x.nom) == norm(nouveau) and x is not p for x in r.personnes):
        return []
    p.nom = nouveau
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
    if norm(ancien) in r.couleurs_types:  # la couleur choisie suit le nouveau nom
        c = r.couleurs_types[norm(ancien)]
        r.couleurs_types = {**{k: v for k, v in r.couleurs_types.items() if k != norm(ancien)}, norm(nouveau): c}
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


def renommer_materiel(r: Reglages, manips: list[Manip], ancien: str, nouveau: str) -> list[Manip]:
    """Renomme un matériel dans la liste et dans les étapes de toutes les manips."""
    if not _renommer_liste(r.materiels, ancien, nouveau):
        return []
    if ancien in r.conditions_materiel:  # ses conditions particulières suivent
        r.conditions_materiel = {(nouveau.strip() if k == ancien else k): v for k, v in r.conditions_materiel.items()}
    ch = []
    for m in manips:
        touche = False
        for e in m.etapes:
            if ancien in e.equipements:
                e.equipements = [nouveau.strip() if x == ancien else x for x in e.equipements]
                touche = True
        if touche:
            ch.append(m)
    return ch


def ajouter_condition_materiel(r: Reglages, materiel: str, nom: str, unite: str = "", defaut: str = "") -> bool:
    nom = nom.strip()
    liste = r.conditions_materiel.get(materiel, [])
    if not nom or any(norm(c.nom) == norm(nom) for c in liste):
        return False
    r.conditions_materiel = {**r.conditions_materiel, materiel: liste + [ConditionMateriel(nom=nom, unite=unite.strip(), defaut=defaut.strip())]}
    return True


def retirer_condition_materiel(r: Reglages, materiel: str, nom: str) -> None:
    """Les étapes qui ont déjà cette condition la gardent."""
    liste = [c for c in r.conditions_materiel.get(materiel, []) if c.nom != nom]
    r.conditions_materiel = {**{k: v for k, v in r.conditions_materiel.items() if k != materiel}, **({materiel: liste} if liste else {})}


def appliquer_conditions_materiel(r: Reglages, e) -> list[str]:
    """Ajoute à l'étape les conditions particulières de son matériel (valeur par défaut), sans doublon. Retourne les noms ajoutés."""
    ajoutees = []
    for mat in e.equipements:
        for c in r.conditions_materiel.get(mat, []):
            if not any(norm(a.nom) == norm(c.nom) for a in e.autres):
                e.autres.append(Condition(nom=c.nom, valeur=f"{c.defaut} {c.unite}".strip()))
                ajoutees.append(c.nom)
    return ajoutees


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


# ------------------------------------------------------------------ volumes d'échantillon
def ajouter_volume(r: Reglages, v: float | None) -> bool:
    if v is None or v <= 0 or v in r.volumes_ml:
        return False
    r.volumes_ml = sorted(r.volumes_ml + [v])
    return True


def supprimer_volume(r: Reglages, v: float) -> None:
    """Les échantillons et laboratoires qui l'utilisent gardent leur volume."""
    r.volumes_ml = [x for x in r.volumes_ml if x != v]


def ajouter_vitesse(r: Reglages, v: float | None, unite: str = "tr/min") -> bool:
    """Vitesse proposée (tr/min, ou g pour la centrifugation), liste triée."""
    liste = r.vitesses_rcf if unite == "g" else r.vitesses_agitation
    if v is None or v <= 0 or v in liste:
        return False
    nouvelle = sorted(liste + [float(v)])
    if unite == "g":
        r.vitesses_rcf = nouvelle
    else:
        r.vitesses_agitation = nouvelle
    return True


def supprimer_vitesse(r: Reglages, v: float, unite: str = "tr/min") -> None:
    """Les étapes qui utilisent cette vitesse la gardent."""
    if unite == "g":
        r.vitesses_rcf = [x for x in r.vitesses_rcf if x != v]
    else:
        r.vitesses_agitation = [x for x in r.vitesses_agitation if x != v]


def ajouter_unite_duree(r: Reglages, unite: str) -> bool:
    from mat_methode.domain.models import DUREES
    if unite not in DUREES or unite in r.unites_duree:
        return False
    r.unites_duree = [u for u in DUREES if u in r.unites_duree or u == unite]  # ordre naturel : s, min, h, jour, semaine
    return True


def retirer_unite_duree(r: Reglages, unite: str) -> bool:
    """Au moins une unité doit rester proposée ; les étapes qui l'utilisent la gardent."""
    if unite not in r.unites_duree or len(r.unites_duree) <= 1:
        return False
    r.unites_duree = [u for u in r.unites_duree if u != unite]
    return True


def regler_defauts_operation(r: Reglages, nom: str, defauts: dict[str, float]) -> bool:
    o = r.operation(nom)
    if o is None:
        return False
    o.defauts = dict(defauts)
    return True


def renommer_unite(r: Reglages, manips: list[Manip], ancien: str, nouveau: str) -> list[Manip]:
    """Renomme une unité de réactif dans la liste et dans les étapes de toutes les manips."""
    if not _renommer_liste(r.unites_reactifs, ancien, nouveau):
        return []
    ch = []
    for m in manips:
        touche = False
        for e in m.etapes:
            for x in e.reactifs:
                if x.unite == ancien:
                    x.unite, touche = nouveau.strip(), True
        if touche:
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


# ------------------------------------------------------------------ ordre des listes
def deplacer_dans(liste: list, index: int, sens: int) -> bool:
    """Déplace l'élément `index` d'un cran (-1 : avant, +1 : après) dans une liste des Réglages."""
    j = index + sens
    if not (0 <= index < len(liste) and 0 <= j < len(liste)):
        return False
    liste[index], liste[j] = liste[j], liste[index]
    return True


# ------------------------------------------------------------------ statuts
def peut_supprimer(m: Manip) -> bool:
    """Seules les manips archivées ou annulées peuvent être supprimées."""
    return m.etat in (ARCHIVEE, ANNULEE)


def nom_etat(r: Reglages | None, ident: str) -> tuple[str, str]:
    """(libellé, ton) d'un statut."""
    if ident == ARCHIVEE:
        return "Archivée", "neutre"
    return STATUTS.get(ident, ("—", "neutre"))


def archiver_ou_restaurer(r: Reglages, m: Manip) -> bool:
    """Retourne True si la manip vient d'être archivée. Restaurer = premier état."""
    if m.etat == ARCHIVEE:
        m.etat = r.etat_initial()
        return False
    m.etat = ARCHIVEE
    return True


PALETTE_DONNEURS = ["#0F7B6C", "#2F6FB8", "#B26B00", "#7A4EB0", "#B8366B", "#4E7D1E"]  # 6 teintes, se répète


PALETTE_TAGS = ["#2F6FB8", "#0F7B6C", "#B26B00", "#7A4EB0", "#B8366B", "#4E7D1E", "#1F7A99", "#A34A28", "#5B5FC7", "#8A6D00"]


def couleur_tag(r: Reglages, tag: str) -> str:
    """Couleur d'un tag : celle choisie dans les Réglages, sinon une couleur fixe tirée de son nom."""
    import zlib
    cle = norm(tag)
    return r.couleurs_tags.get(cle) or PALETTE_TAGS[zlib.crc32(cle.encode("utf-8")) % len(PALETTE_TAGS)]


def couleur_tag_suivante(r: Reglages, tag: str) -> str:
    """Passe le tag à la couleur suivante de la palette (Réglages › Tags)."""
    actuelle = couleur_tag(r, tag)
    i = PALETTE_TAGS.index(actuelle) if actuelle in PALETTE_TAGS else -1
    r.couleurs_tags = {**r.couleurs_tags, norm(tag): PALETTE_TAGS[(i + 1) % len(PALETTE_TAGS)]}
    return r.couleurs_tags[norm(tag)]


def auteur(r: Reglages | None, par: str) -> str:
    """Auteur d'une ligne du journal (ou du lancement) affiché par ses initiales : une personne des Réglages retrouvée
    par son IGG ou son nom ; sinon le texte tel quel (anciennes lignes)."""
    if r is None or not par:
        return par
    p = r.personne_igg(par) or r.personne(par)
    return p.sigle() if p else par


def nom_auteur(r: Reglages | None, igg: str) -> str:
    p = r.personne_igg(igg) if r is not None else None
    return p.nom if p else igg


def texte_statut(r: Reglages | None, c) -> str:
    """« Validée le 04/11/2026 à 11:40 par Pierre BURGUN » (nom complet si la personne est dans les Réglages)."""
    from mat_methode.domain.texte import fmt_dt
    p = r.personne_igg(c.par) if r is not None else None
    return f"{nom_etat(r, c.vers)[0]} le {fmt_dt(c.t)} par {p.nom if p else (c.par or '?')}"


def journal_complet(r: Reglages | None, m: Manip) -> list[tuple[str, str, str]]:
    """Journal de l'application : modifications après lancement + changements de statut, du plus récent au plus ancien.
    (date ISO, auteur en initiales, texte). Les changements de statut ne vont pas dans les documents exportés."""
    lignes = [(j.t, auteur(r, j.par), j.txt) for j in m.journal]
    lignes += [(c.t, auteur(r, c.par), f"Statut : {nom_etat(r, c.de)[0]} → {nom_etat(r, c.vers)[0]}") for c in m.statuts]
    return sorted(lignes, key=lambda x: x[0], reverse=True)


def couleur_type(r: Reglages, typ: str) -> str:
    """Couleur d'un type de demande : celle choisie dans les Réglages, sinon une couleur fixe tirée de son nom."""
    import zlib
    cle = norm(typ)
    return r.couleurs_types.get(cle) or PALETTE_TAGS[(zlib.crc32(cle.encode("utf-8")) + 3) % len(PALETTE_TAGS)]


def couleur_type_suivante(r: Reglages, typ: str) -> str:
    actuelle = couleur_type(r, typ)
    i = PALETTE_TAGS.index(actuelle) if actuelle in PALETTE_TAGS else -1
    r.couleurs_types = {**r.couleurs_types, norm(typ): PALETTE_TAGS[(i + 1) % len(PALETTE_TAGS)]}
    return r.couleurs_types[norm(typ)]


def couleur_donneur(r: Reglages, nom: str) -> str:
    """Couleur attribuée par le rang dans la liste des Réglages (ne change pas quand on filtre)."""
    try:
        i = r.donneurs_ordre.index(nom)
    except ValueError:
        i = 0
    return PALETTE_DONNEURS[i % len(PALETTE_DONNEURS)]
