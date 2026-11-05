"""Volumes étape par étape, avec des voies en parallèle : entrée, matière ajoutée, prélevé, sortie.

Le volume de départ (Ma demande) est la « sortie » d'une étape 0. Un bloc en parallèle reçoit une part de la sortie précédente
(en % ou en mL, part égale si non précisée) ; l'étape qui réunit les voies prend toute la sortie de chaque voie, ou la quantité
indiquée. Seules les matières ajoutées en mL (autres matières d'une voie) comptent comme volume ajouté."""
from __future__ import annotations

from dataclasses import dataclass

from mat_methode.domain.models import Manip, Voie
from mat_methode.domain.regles import lettre_voie, segments


@dataclass
class LigneVolume:
    indice: int  # index de l'étape dans m.etapes
    voie: str  # lettre de la voie (vide hors bloc en parallèle)
    entree: float
    ajoute: float
    preleve: float
    sortie: float
    alerte: str = ""


def _nombre(texte: str) -> float | None:
    try:
        return float(str(texte).strip().replace(",", ".").replace(" ", ""))
    except ValueError:
        return None


def volume_ajoute(v: Voie) -> float:
    """Autres matières de la voie exprimées en mL."""
    return sum(n for x in v.autres if x.unite == "mL" and (n := _nombre(x.quantite)) is not None)


def volume_reactifs(e) -> float:
    """Réactifs liquides ajoutés à l'étape (mL, µL ou L), en mL : ils s'ajoutent au volume qui sort de l'étape."""
    facteur = {"mL": 1.0, "ml": 1.0, "µL": 0.001, "ul": 0.001, "L": 1000.0, "l": 1000.0}
    return sum(n * facteur[x.unite] for x in e.reactifs if x.unite in facteur and (n := _nombre(x.quantite)) is not None)


def volume_depart_voie(v: Voie, volume_demande: float, nvoies: int) -> float:
    """Voie d'un bloc qui ouvre le flux : somme des mL de ses matières de départ ; sans volume saisi, part égale du volume de Ma demande."""
    propre = volume_ajoute(v)
    return propre if propre > 0 else volume_demande / max(nvoies, 1)


def part_voie(v: Voie, sortie_precedente: float, nvoies: int) -> float:
    """Volume reçu par la voie : % ou mL de la sortie précédente ; sans valeur, part égale."""
    if v.part is None:
        return sortie_precedente / max(nvoies, 1)
    return sortie_precedente * v.part / 100 if v.part_unite == "%" else v.part


def volumes_par_etape(m: Manip) -> list[LigneVolume]:
    preleve = {e.id: sum(p.volume_ml or 0 for p in m.prelevements if p.etape_id == e.id and p.moment != "avant") for e in m.etapes}
    lignes: dict[int, LigneVolume] = {}
    sortie = m.contexte.volume_depart_ml or 0
    sorties_voies: dict[str, float] = {}  # voie -> sortie de sa dernière étape (pour l'étape qui réunit)
    bloc_precedent = None
    for rang_segment, (genre, par, voies) in enumerate(segments(m)):
        if genre == "par":
            premier = rang_segment == 0  # bloc qui ouvre le flux : chaque voie part de sa propre matière
            recu = sum(volume_depart_voie(v, sortie, len(par.voies)) if premier else part_voie(v, sortie, len(par.voies)) for v in par.voies)
            sorties_voies = {}
            for k, v in enumerate(par.voies):
                courant = volume_depart_voie(v, sortie, len(par.voies)) if premier else part_voie(v, sortie, len(par.voies))
                ajoute = 0.0 if premier else volume_ajoute(v)
                for rang, i in enumerate(voies[k]):
                    e = m.etapes[i]
                    entree = courant
                    add = (ajoute if rang == 0 else 0) + volume_reactifs(e)
                    sort = entree + add - preleve[e.id]
                    alerte = "plus de volume prélevé que reçu" if sort < 0 else ""
                    if rang == 0 and not premier and sortie and recu > sortie + 1e-9 and v.part is not None:
                        alerte = "les voies reçoivent plus que la sortie précédente"
                    lignes[i] = LigneVolume(i, lettre_voie(m, par.id, v.id), entree, add, preleve[e.id], sort, alerte)
                    courant = sort
                sorties_voies[v.id] = courant if voies[k] else courant + ajoute
            bloc_precedent = par
            sortie = sum(sorties_voies.values())  # sans étape de réunion : tout est repris
            continue
        for rang, i in enumerate(voies):
            e = m.etapes[i]
            if rang == 0 and bloc_precedent is not None:  # première étape après un bloc : elle réunit les voies
                entree = sum(min(e.apports.get(v.id, sorties_voies.get(v.id, 0)), sorties_voies.get(v.id, 0)) for v in bloc_precedent.voies)
                alerte_conv = ""
            else:
                entree, alerte_conv = sortie, ""
            add = volume_reactifs(e)
            sort = entree + add - preleve[e.id]
            lignes[i] = LigneVolume(i, "", entree, add, preleve[e.id], sort, alerte_conv or ("plus de volume prélevé que reçu" if sort < 0 else ""))
            sortie = sort
        if voies:
            bloc_precedent = None
    return [lignes[i] for i in sorted(lignes)]
