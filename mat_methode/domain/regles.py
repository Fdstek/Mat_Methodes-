"""Règles métier (cahier des charges §8) : étiquettes, bilan, conditions communes, défauts labo,
duplication, tags, opérations sur le flux."""
from __future__ import annotations

import re
from dataclasses import dataclass

from mat_methode.domain.catalogue import DEFAUTS_CONDITIONS, est_centrifugation
from mat_methode.domain.models import (
    Etape,
    Manip,
    Prelevement,
    Reglages,
    Vide,
    maintenant_iso,
    nouvel_id,
)
from mat_methode.domain.texte import fmt_dur, norm

# ------------------------------------------------------------------ étiquettes (§8.1)


def numero_etape(m: Manip, p: Prelevement) -> int:
    """0 pour l'entrée, sinon le numéro de l'étape (1..n)."""
    if not p.etape_id:
        return 0
    for i, e in enumerate(m.etapes):
        if e.id == p.etape_id:
            return i + 1
    return 0


def _rang(p: Prelevement) -> float:
    if p.moment == "avant":
        return -1
    if p.moment == "pendant":
        return p.temps_min or 0
    return 1e9


def echantillons_tries(m: Manip) -> list[Prelevement]:
    """Ordre : étape, puis avant < pendant (temps croissant) < effluent, puis ordre de saisie."""
    idx = list(enumerate(m.prelevements))
    idx.sort(key=lambda x: (numero_etape(m, x[1]), _rang(x[1]), x[0]))
    return [p for _, p in idx]


def etiquettes(m: Manip) -> dict[str, str]:
    groupes: dict[int, list[Prelevement]] = {}
    for p in echantillons_tries(m):
        groupes.setdefault(numero_etape(m, p), []).append(p)
    out = {}
    for n, ps in groupes.items():
        for i, p in enumerate(ps):
            out[p.id] = f"S{n}" + (chr(97 + i) if len(ps) > 1 else "")
    return out


def code_badge(etiquette: str) -> str:
    """S3a -> « a », S2 -> « 2 », S0 -> « 0 »."""
    mt = re.match(r"^S(\d+)([a-z]*)$", etiquette or "")
    if not mt:
        return (etiquette or "")[:2]
    return mt.group(2) or mt.group(1)


def est_entree(m: Manip, p: Prelevement) -> bool:
    return p.moment == "avant" or numero_etape(m, p) == 0


def moment_court(m: Manip, p: Prelevement) -> str:
    """« avant traitement », « pendant · à 10 min », « effluent »."""
    if est_entree(m, p):
        return "avant traitement"
    if p.moment == "pendant":
        return "pendant" + (f" · à {fmt_dur(p.temps_min)}" if p.temps_min is not None else "")
    return "effluent"


# ------------------------------------------------------------------ bilan (§8.3)
@dataclass
class Bilan:
    depart: float
    preleve: float
    n: int
    restant: float
    numeros_a_saisir: int

    @property
    def depassement(self) -> bool:
        return self.restant < 0


def total_preleve(m: Manip) -> float:
    return sum(p.volume_ml or 0 for p in m.prelevements)


def numeros_a_saisir(m: Manip) -> int:
    return sum((0 if p.scirius.strip() else 1) + (0 if p.aramis.strip() else 1) for p in m.prelevements)


def bilan(m: Manip) -> Bilan:
    vd = m.contexte.volume_depart_ml or 0
    tot = total_preleve(m)
    return Bilan(vd, tot, len(m.prelevements), vd - tot, numeros_a_saisir(m))


# ------------------------------------------------------------------ conditions (§6.3, §8.5)
def basculer_condition(e: Etape, cle: str) -> None:
    """Active (avec la valeur par défaut) ou désactive (efface) une condition d'étape."""
    if cle == "vide":
        e.vide = None if e.vide else Vide()
    else:
        setattr(e, cle, None if getattr(e, cle) is not None else DEFAUTS_CONDITIONS[cle])


def basculer_commune(m: Manip, cle: str) -> None:
    c = m.communes
    if cle == "vide":
        c.vide = None if c.vide else Vide()
    else:
        setattr(c, cle, None if getattr(c, cle) is not None else DEFAUTS_CONDITIONS[cle])


def appliquer_communes(m: Manip, remplacer: bool = False) -> int:
    """Écrit les conditions communes actives dans chaque étape (seulement si vide, sauf
    « remplacer »). L'agitation ne s'applique pas à la centrifugation. Retourne le nombre d'étapes changées."""
    c, n = m.communes, 0
    for e in m.etapes:
        ch = False
        if c.temperature_c is not None and (remplacer or e.temperature_c is None):
            e.temperature_c, ch = c.temperature_c, True
        if c.agitation_trmin is not None and not est_centrifugation(e.operation) and (remplacer or e.agitation_trmin is None):
            e.agitation_trmin, ch = c.agitation_trmin, True
        if c.vide is not None and (remplacer or e.vide is None):
            e.vide, ch = c.vide.model_copy(), True
        n += ch
    return n


def heriter_communes(m: Manip, e: Etape) -> None:
    c = m.communes
    if c.temperature_c is not None and e.temperature_c is None:
        e.temperature_c = c.temperature_c
    if c.agitation_trmin is not None and e.agitation_trmin is None and not est_centrifugation(e.operation):
        e.agitation_trmin = c.agitation_trmin
    if c.vide is not None and e.vide is None:
        e.vide = c.vide.model_copy()


# ------------------------------------------------------------------ flux
def ajouter_etape(m: Manip, operation: str, apres: int | None = None) -> Etape:
    """Ajoute une étape à la fin, ou après l'index « apres » (-1 = au début). Hérite des communes."""
    e = Etape(operation=operation.strip())
    heriter_communes(m, e)
    if apres is None:
        m.etapes.append(e)
    else:
        m.etapes.insert(apres + 1, e)
    return e


def dupliquer_etape(m: Manip, etape_id: str) -> Etape:
    i = [e.id for e in m.etapes].index(etape_id)
    c = m.etapes[i].model_copy(deep=True)
    c.id = nouvel_id()
    m.etapes.insert(i + 1, c)
    return c


def deplacer_etape(m: Manip, etape_id: str, sens: int) -> bool:
    i = [e.id for e in m.etapes].index(etape_id)
    j = i + sens
    if not 0 <= j < len(m.etapes):
        return False
    m.etapes[i], m.etapes[j] = m.etapes[j], m.etapes[i]
    return True


def supprimer_etape(m: Manip, etape_id: str) -> None:
    """Supprimer une étape supprime ses échantillons (§8.2)."""
    m.etapes = [e for e in m.etapes if e.id != etape_id]
    m.prelevements = [p for p in m.prelevements if p.etape_id != etape_id]


# ------------------------------------------------------------------ échantillons (§8.6)
def nouvel_echantillon(m: Manip, reglages: Reglages, etape_id: str | None) -> Prelevement:
    """Laboratoire du dernier échantillon de la manip (sinon le premier de la liste) ; volume et
    analyses du laboratoire (sinon 50 mL et les analyses du dernier échantillon)."""
    dernier = m.prelevements[-1] if m.prelevements else None
    labo_nom = dernier.labo if dernier else (reglages.laboratoires[0].nom if reglages.laboratoires else "")
    labo = reglages.laboratoire(labo_nom)
    volume = labo.volume_ml if labo and labo.volume_ml is not None else 50
    analyses = list(labo.analyses) if labo and labo.analyses else (list(dernier.analyses) if dernier else [])
    p = Prelevement(etape_id=etape_id, moment="effluent" if etape_id else "avant",
                    volume_ml=volume, labo=labo_nom or "", analyses=analyses)
    m.prelevements.append(p)
    return p


def changer_labo(p: Prelevement, reglages: Reglages, nom: str) -> None:
    p.labo = nom
    labo = reglages.laboratoire(nom)
    if labo:
        if labo.volume_ml is not None:
            p.volume_ml = labo.volume_ml
        p.analyses = list(labo.analyses)


def changer_moment(p: Prelevement, moment: str) -> None:
    p.moment = moment  # type: ignore[assignment]
    if moment != "pendant":
        p.temps_min = None


def basculer_analyse(liste_analyses: list[str], a: str) -> list[str]:
    return [x for x in liste_analyses if x != a] if a in liste_analyses else liste_analyses + [a]


# ------------------------------------------------------------------ duplication (§6.1)
def dupliquer(m: Manip, reglages: Reglages, nom: str | None = None) -> Manip:
    """Copie sans lancement ni journal (version 1), sans référence, lot ni numéros Scirius/Aramis."""
    c = m.copie()
    c.id = nouvel_id()
    c.nom = nom or f"{m.nom} (copie)"
    c.etat = reglages.etat_initial()
    c.rev, c.lancee, c.journal, c.base = 1, None, [], None
    c.maj = maintenant_iso()
    c.contexte.ref = ""
    c.contexte.lot = ""
    corresp = {}
    for e in c.etapes:
        corresp[e.id] = e.id = nouvel_id()
    for p in c.prelevements:
        p.id = nouvel_id()
        if p.etape_id:
            p.etape_id = corresp.get(p.etape_id)
        p.scirius = p.aramis = ""
    return c


# ------------------------------------------------------------------ tags (§8.7 bis)
def tous_les_tags(manips: list[Manip]) -> list[str]:
    out: list[str] = []
    for m in manips:
        for t in m.tags:
            if not any(norm(x) == norm(t) for x in out):
                out.append(t)
    return sorted(out, key=norm)


def ajouter_tags(m: Manip, saisie: str, existants: list[str]) -> list[str]:
    """« nouveau tag, pilote » -> 2 tags ; l'orthographe déjà utilisée ailleurs est reprise."""
    ajoutes = []
    for v in (x.strip().lstrip("#").strip() for x in saisie.split(",")):
        if not v:
            continue
        ex = next((x for x in existants if norm(x) == norm(v)), v)
        if not any(norm(x) == norm(ex) for x in m.tags):
            m.tags.append(ex)
            ajoutes.append(ex)
    return ajoutes


def retirer_tag(m: Manip, tag: str) -> None:
    m.tags = [x for x in m.tags if norm(x) != norm(tag)]


def est_test(type_demande: str) -> bool:
    return "test" in norm(type_demande)


# ------------------------------------------------------------------ contrôles de saisie (§14.4)
def avertissements(m: Manip, autres: list[Manip] | None = None) -> list[str]:
    """Doublons de numéros et prélèvement après la fin de l'étape. Ne bloque jamais la saisie."""
    out, lab = [], etiquettes(m)
    for p in m.prelevements:
        e = m.etape(p.etape_id)
        if e and p.moment == "pendant" and p.temps_min is not None and e.duree_min is not None and p.temps_min > e.duree_min:
            out.append(f"{lab[p.id]} : prélevé à {fmt_dur(p.temps_min)}, après la fin de l’étape ({fmt_dur(e.duree_min)})")
    for champ, libelle in (("scirius", "Scirius"), ("aramis", "Aramis")):
        miens: dict[str, str] = {}
        for p in echantillons_tries(m):
            v = getattr(p, champ).strip()
            if not v:
                continue
            if v in miens:
                out.append(f"N° {libelle} {v} en double : {miens[v]} et {lab[p.id]}")
            else:
                miens[v] = lab[p.id]
        signales = set()
        for mm in autres or []:
            if mm.id == m.id:
                continue
            lb = etiquettes(mm)
            for p in mm.prelevements:
                v = getattr(p, champ).strip()
                if v in miens and v not in signales:
                    signales.add(v)
                    out.append(f"N° {libelle} {v} ({miens[v]}) déjà utilisé : {lb[p.id]} de « {mm.nom} »")
    return out
