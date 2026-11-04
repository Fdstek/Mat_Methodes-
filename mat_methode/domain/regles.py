"""Règles métier (cahier des charges §8) : étiquettes, bilan, conditions communes, défauts labo,
duplication, tags, opérations sur le flux."""
from __future__ import annotations

import re
from dataclasses import dataclass

from mat_methode.domain.catalogue import DEFAUTS_CONDITIONS, est_centrifugation
from mat_methode.domain.models import (
    ENCOURS,
    REALISEE,
    VALIDEE,
    Etape,
    Groupe,
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


def echantillons_tries(m: Manip) -> list[Prelevement]:
    """Ordre : étape, puis ordre d'ajout. Un échantillon ajouté se met à la suite des existants (S3a, S3b, puis S3c),
    quel que soit son moment : les étiquettes déjà notées ne changent pas."""
    idx = list(enumerate(m.prelevements))
    idx.sort(key=lambda x: (numero_etape(m, x[1]), x[0]))
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
    """Volumes : les échantillons pris avant traitement (S0) sont prélevés EN AMONT, hors du volume engagé dans la manip."""
    depart: float  # volume engagé dans la manip (volume de départ)
    preleve: float  # prélevé pendant le flux
    n: int
    restant: float  # engagé - prélevé pendant le flux
    numeros_a_saisir: int
    amont: float = 0  # prélevé avant traitement, en plus du volume engagé
    n_amont: int = 0

    @property
    def depassement(self) -> bool:
        return self.restant < 0

    @property
    def total(self) -> float:
        """Charge à prévoir : prélèvements en amont + volume engagé."""
        return self.depart + self.amont


def total_preleve(m: Manip) -> float:
    """Prélevé pendant le flux (sans les échantillons pris en amont, avant traitement)."""
    return sum(p.volume_ml or 0 for p in m.prelevements if not est_entree(m, p))


def total_amont(m: Manip) -> float:
    return sum(p.volume_ml or 0 for p in m.prelevements if est_entree(m, p))


def numeros_a_saisir(m: Manip) -> int:
    return sum((0 if p.scirius.strip() else 1) + (0 if p.aramis.strip() else 1) for p in m.prelevements)


def suivi_volumes(m: Manip) -> list[tuple[str, str, float, float | None]]:
    """Échantillons dans l'ordre du flux : (étiquette, où et quand, volume prélevé, volume restant ensuite).
    Un échantillon pris en amont (avant traitement) ne compte pas dans le volume engagé : reste = None."""
    lab, reste, out = etiquettes(m), m.contexte.volume_depart_ml or 0, []
    for p in echantillons_tries(m):
        n = numero_etape(m, p)
        if est_entree(m, p):
            out.append((lab[p.id], "en amont, avant traitement (hors volume engagé)", p.volume_ml or 0, None))
            continue
        reste -= p.volume_ml or 0
        out.append((lab[p.id], f"étape {n} ({m.etapes[n - 1].operation}) · {moment_court(m, p)}", p.volume_ml or 0, reste))
    return out


def bilan(m: Manip) -> Bilan:
    vd = m.contexte.volume_depart_ml or 0
    tot = total_preleve(m)
    amont = [p for p in m.prelevements if est_entree(m, p)]
    return Bilan(vd, tot, len(m.prelevements) - len(amont), vd - tot, numeros_a_saisir(m),
                 amont=sum(p.volume_ml or 0 for p in amont), n_amont=len(amont))


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


def copier_conditions_precedentes(m: Manip, etape_id: str) -> Etape | None:
    """Reprend les conditions opératoires de l'étape précédente (température, durée, agitation, membrane,
    sous vide, autres conditions). Ni les réactifs, ni le matériel, ni les échantillons. Retourne l'étape source."""
    ids = [e.id for e in m.etapes]
    if etape_id not in ids or ids.index(etape_id) == 0:
        return None
    src, e = m.etapes[ids.index(etape_id) - 1], m.etape(etape_id)
    e.temperature_c, e.duree_min, e.filtre_um = src.temperature_c, src.duree_min, src.filtre_um
    e.agitation_trmin = src.agitation_trmin
    e.vide = src.vide.model_copy() if src.vide else None
    e.autres = [a.model_copy() for a in src.autres]
    return src


def heriter_communes(m: Manip, e: Etape) -> None:
    c = m.communes
    if c.temperature_c is not None and e.temperature_c is None:
        e.temperature_c = c.temperature_c
    if c.agitation_trmin is not None and e.agitation_trmin is None and not est_centrifugation(e.operation):
        e.agitation_trmin = c.agitation_trmin
    if c.vide is not None and e.vide is None:
        e.vide = c.vide.model_copy()


# ------------------------------------------------------------------ flux
def ajouter_etape(m: Manip, operation: str, apres: int | None = None, groupe_id: str | None = None) -> Etape:
    """Ajoute une étape à la fin, ou après l'index « apres » (-1 = au début). Hérite des communes.

    Sans grande étape demandée, une étape insérée au milieu d'une grande étape en fait partie."""
    e = Etape(operation=operation.strip(), groupe_id=groupe_id)
    heriter_communes(m, e)
    if apres is None:
        m.etapes.append(e)
    else:
        if groupe_id is None and 0 <= apres < len(m.etapes) - 1:
            g = m.etapes[apres].groupe_id
            if g and m.etapes[apres + 1].groupe_id == g:
                e.groupe_id = g
        m.etapes.insert(apres + 1, e)
    return e


# ------------------------------------------------------------------ grandes étapes
def plage(nums: list[int]) -> str:
    """[2, 3, 4] -> « étapes 2 à 4 » ; [3] -> « étape 3 » ; [2, 5] -> « étapes 2, 5 »."""
    if not nums:
        return "aucune étape"
    if len(nums) == 1:
        return f"étape {nums[0]}"
    if nums == list(range(nums[0], nums[-1] + 1)):
        return f"étapes {nums[0]} à {nums[-1]}"
    return "étapes " + ", ".join(map(str, nums))


def numeros_groupe(m: Manip, groupe_id: str) -> list[int]:
    return [i + 1 for i, e in enumerate(m.etapes) if e.groupe_id == groupe_id]


def blocs(m: Manip) -> list[tuple[Groupe | None, list[int]]]:
    """Le flux découpé en blocs consécutifs : (grande étape ou None, index des étapes)."""
    out: list[tuple[Groupe | None, list[int]]] = []
    for i, e in enumerate(m.etapes):
        g = m.groupe(e.groupe_id)
        if out and out[-1][0] is g and g is not None:
            out[-1][1].append(i)
        else:
            out.append((g, [i]))
    return out


def creer_groupe(m: Manip, nom: str) -> Groupe:
    g = Groupe(nom=nom.strip() or "Grande étape")
    m.groupes.append(g)
    return g


def placer_dans_groupe(m: Manip, etape_id: str, groupe_id: str | None) -> None:
    """Range une étape dans une grande étape (ou l'en sort). L'étape est déplacée juste après la
    dernière étape de la grande étape pour que celle-ci reste d'un seul tenant."""
    e = m.etape(etape_id)
    if e is None or e.groupe_id == groupe_id:
        return
    e.groupe_id = groupe_id
    if groupe_id is None:
        return
    i = m.etapes.index(e)
    autres = [k for k, x in enumerate(m.etapes) if x.groupe_id == groupe_id and x is not e]
    if not autres or (i - 1 in autres or i + 1 in autres):
        return  # déjà à côté de la grande étape : on ne bouge rien
    m.etapes.remove(e)
    dernier = max(k for k, x in enumerate(m.etapes) if x.groupe_id == groupe_id and x is not e)
    m.etapes.insert(dernier + 1, e)


def defaire_groupe(m: Manip, groupe_id: str) -> None:
    """Supprime la grande étape ; ses étapes restent dans le flux."""
    for e in m.etapes:
        if e.groupe_id == groupe_id:
            e.groupe_id = None
    m.groupes = [g for g in m.groupes if g.id != groupe_id]


def deplacer_groupe(m: Manip, groupe_id: str, sens: int) -> bool:
    """Monte ou descend toute la grande étape d'un bloc."""
    bl = blocs(m)
    k = next((j for j, (g, _) in enumerate(bl) if g is not None and g.id == groupe_id), None)
    if k is None or not 0 <= k + sens < len(bl):
        return False
    bl[k], bl[k + sens] = bl[k + sens], bl[k]
    m.etapes = [m.etapes[i] for _, idx in bl for i in idx]
    return True


def dupliquer_groupe(m: Manip, groupe_id: str, fois: int = 1, echantillons: bool = False) -> list[Groupe]:
    """Recopie une grande étape (ses étapes, conditions, réactifs, matériel) « fois » fois, juste après elle.
    Les échantillons sont recopiés sur demande, sans leurs numéros Scirius / Aramis."""
    g = m.groupe(groupe_id)
    idx = [i for i, e in enumerate(m.etapes) if e.groupe_id == groupe_id]
    if g is None or not idx or fois < 1:
        return []
    modeles = [m.etapes[i] for i in idx]
    pos, nouveaux = idx[-1] + 1, []
    for _ in range(fois):
        ng = Groupe(nom=g.nom)
        m.groupes.insert(m.groupes.index(g) + len(nouveaux) + 1, ng)
        nouveaux.append(ng)
        for e in modeles:
            c = e.model_copy(deep=True)
            c.id, c.groupe_id = nouvel_id(), ng.id
            m.etapes.insert(pos, c)
            pos += 1
            if echantillons:
                for p in [p for p in m.prelevements if p.etape_id == e.id]:
                    q = p.model_copy(deep=True)
                    q.id, q.etape_id, q.scirius, q.aramis = nouvel_id(), c.id, "", ""
                    m.prelevements.append(q)
    return nouveaux


def dupliquer_echantillon(m: Manip, ech_id: str, fois: int = 1) -> list[Prelevement]:
    """Recopie un échantillon (moment, volume, labo, analyses, commentaire) « fois » fois, sans ses n° Scirius / Aramis.
    Les copies prennent les lettres suivantes de la même étape."""
    p = m.prelevement(ech_id)
    if p is None or fois < 1:
        return []
    copies = []
    for _ in range(fois):
        q = p.model_copy(deep=True)
        q.id, q.scirius, q.aramis = nouvel_id(), "", ""
        copies.append(q)
    m.prelevements = m.prelevements + copies
    return copies


def dupliquer_etape(m: Manip, etape_id: str) -> Etape:
    i = [e.id for e in m.etapes].index(etape_id)
    c = m.etapes[i].model_copy(deep=True)
    c.id = nouvel_id()
    m.etapes.insert(i + 1, c)
    return c


def deplacer_tache(m: Manip, tache_id: str, sens: int) -> bool:
    """Change l'ordre de réalisation des points « à faire »."""
    i = next((k for k, t in enumerate(m.a_faire) if t.id == tache_id), None)
    if i is None or not 0 <= i + sens < len(m.a_faire):
        return False
    m.a_faire[i], m.a_faire[i + sens] = m.a_faire[i + sens], m.a_faire[i]
    return True


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
    defaut = reglages.volumes_ml[0] if reglages.volumes_ml else 50
    volume = labo.volume_ml if labo and labo.volume_ml is not None else defaut
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


def analyses_possibles(reglages: Reglages, p: Prelevement) -> list[str]:
    """Analyses proposées pour un échantillon : celles de son laboratoire (Réglages), plus celles déjà cochées ;
    toutes les analyses si le laboratoire n'en a pas de définies."""
    labo = reglages.laboratoire(p.labo)
    base = [a for a in reglages.analyses if a in labo.analyses] + [a for a in labo.analyses if a not in reglages.analyses] \
        if labo and labo.analyses else list(reglages.analyses)  # dans l'ordre des Réglages
    return base + [a for a in p.analyses if a not in base]


def changer_moment(p: Prelevement, moment: str) -> None:
    p.moment = moment  # type: ignore[assignment]
    if moment != "pendant":
        p.temps_min = None


def basculer_analyse(liste_analyses: list[str], a: str) -> list[str]:
    return [x for x in liste_analyses if x != a] if a in liste_analyses else liste_analyses + [a]


# ------------------------------------------------------------------ référence automatique
REF_AUTO = re.compile(r"^[A-Z]{1,6}-\d{4}-\d{2}-\d{2}-\d{2,}$")


def generer_reference(manips: list[Manip], initiales: str, jour: str) -> str:
    """« PB-2026-10-31-01 » : initiales du donneur d'ordre, date (AAAA-MM-JJ), numéro du jour pour ces initiales."""
    prefixe = f"{(initiales or 'XX').upper()}-{jour}-"
    nums = [int(m.contexte.ref[len(prefixe):]) for m in manips
            if m.contexte.ref.startswith(prefixe) and m.contexte.ref[len(prefixe):].isdigit()]
    return f"{prefixe}{(max(nums) + 1 if nums else 1):02d}"


def reference_auto(m: Manip, reglages: Reglages, manips: list[Manip], jour: str | None = None, forcer: bool = False) -> bool:
    """Donne une référence automatique si elle est vide (ou déjà automatique, ou si `forcer`). Retourne True si changée."""
    p = reglages.personne(m.contexte.donneur)
    if p is None or not p.sigle():
        return False
    if not (forcer or not m.contexte.ref.strip() or REF_AUTO.match(m.contexte.ref.strip())):
        return False
    jour = jour or (m.contexte.date or maintenant_iso()[:10])
    if REF_AUTO.match(m.contexte.ref.strip()) and m.contexte.ref.startswith(f"{p.sigle()}-{jour}-") and not forcer:
        return False  # déjà la bonne
    m.contexte.ref = generer_reference([x for x in manips if x.id != m.id], p.sigle(), jour)
    return True


# ------------------------------------------------------------------ duplication (§6.1)
def dupliquer(m: Manip, reglages: Reglages, nom: str | None = None) -> Manip:
    """Copie sans lancement ni journal (version 1), sans référence, lot ni numéros Scirius/Aramis."""
    c = m.copie()
    c.id = nouvel_id()
    c.nom = nom or f"{m.nom} (copie)"
    c.etat = reglages.etat_initial()
    c.rev, c.lancee, c.journal, c.base = 1, None, [], None
    c.a_faire = []  # la liste « à faire » est propre à chaque manip
    c.rapports = []
    c.statuts = []  # nouvel historique des statuts
    c.maj = maintenant_iso()
    c.contexte.ref = ""
    c.contexte.lot = ""
    corresp, groupes = {}, {}
    for g in c.groupes:
        groupes[g.id] = g.id = nouvel_id()
    for e in c.etapes:
        corresp[e.id] = e.id = nouvel_id()
        if e.groupe_id:
            e.groupe_id = groupes.get(e.groupe_id)
    for p in c.prelevements:
        p.id = nouvel_id()
        if p.etape_id:
            p.etape_id = corresp.get(p.etape_id)
        p.scirius = p.aramis = ""
    return c


# ------------------------------------------------------------------ statuts et ordre des protocoles
A_REALISER = (VALIDEE, ENCOURS)  # liste « Protocole › À réaliser »


def protocoles(manips: list[Manip], ordre: list[str], statuts=A_REALISER) -> list[Manip]:
    """Manips de ces statuts, dans l'ordre de réalisation des Réglages ; les non classées à la fin (les plus anciennes d'abord)."""
    rang = {i: k for k, i in enumerate(ordre)}
    ms = [m for m in manips if m.etat in statuts]
    return sorted(ms, key=lambda m: (m.id not in rang, rang.get(m.id, 0), m.maj))


def noter_statut(m: Manip, avant: str, apres: str, par: str = "") -> None:
    """Ajoute le changement de statut à l'historique (qui, quand, de quoi vers quoi)."""
    from mat_methode.domain.models import ChangementStatut
    if avant != apres:
        m.statuts = m.statuts + [ChangementStatut(t=maintenant_iso(), par=par, de=avant, vers=apres)]


def changer_statut(m: Manip, statut: str, reglages: Reglages, par: str = "") -> bool:
    """Change le statut (noté dans l'historique avec `par`) ; une manip qui devient « Validée » ou « En cours » prend la
    dernière place de la liste Protocole. Retourne True si l'ordre des protocoles (Réglages) a changé."""
    noter_statut(m, m.etat, statut, par)
    m.etat = statut
    if statut in A_REALISER and m.id not in reglages.ordre_protocoles:
        reglages.ordre_protocoles = reglages.ordre_protocoles + [m.id]
        return True
    return False


def deplacer_protocole(manips: list[Manip], reglages: Reglages, m: Manip, sens: int) -> bool:
    """Monte (-1) ou descend (+1) une manip dans la liste « À réaliser » (ordre gardé dans les Réglages)."""
    liste = protocoles(manips, reglages.ordre_protocoles)
    if m not in liste:
        return False
    i = liste.index(m)
    j = i + sens
    if not 0 <= j < len(liste):
        return False
    liste[i], liste[j] = liste[j], liste[i]
    actifs = {x.id for x in liste}
    reglages.ordre_protocoles = [x.id for x in liste] + [x for x in reglages.ordre_protocoles if x not in actifs]
    return True


def rapports_clotures(manips: list[Manip]) -> list[Manip]:
    """Manips réalisées (protocoles clôturés), la plus récente d'abord."""
    return sorted((m for m in manips if m.etat == REALISEE), key=lambda m: m.maj, reverse=True)


# ------------------------------------------------------------------ tags (§8.7 bis)
def tous_les_tags(manips: list[Manip], ordre: list[str] | None = None) -> list[str]:
    """Tags utilisés et tags créés dans les Réglages (`ordre`), dans l'ordre choisi, puis les autres par ordre alphabétique."""
    out: list[str] = [t for t in (ordre or []) if t.strip()]
    for m in manips:
        for t in m.tags:
            if not any(norm(x) == norm(t) for x in out):
                out.append(t)
    rang = {norm(t): k for k, t in enumerate(ordre or [])}
    return sorted(out, key=lambda t: (rang.get(norm(t), len(rang)), norm(t)))


def deplacer_tag(manips: list[Manip], reglages: Reglages, tag: str, sens: int) -> bool:
    """Avance (-1) ou recule (+1) un tag dans l'ordre des Réglages."""
    ts = tous_les_tags(manips, reglages.ordre_tags)
    i = next((k for k, t in enumerate(ts) if norm(t) == norm(tag)), None)
    if i is None or not 0 <= i + sens < len(ts):
        return False
    ts[i], ts[i + sens] = ts[i + sens], ts[i]
    reglages.ordre_tags = ts
    return True


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
