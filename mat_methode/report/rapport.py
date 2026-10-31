"""Génération du texte « Matériel et méthodes » (§10) et des données du rapport.

Une seule source : `construire()` produit sections, détail par phase et tableaux ; Markdown, HTML,
PDF, Word et JSON en dérivent. Une donnée manquante devient un repère {{?libellé}}.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from mat_methode.domain.catalogue import est_centrifugation, participe
from mat_methode.domain.models import Etape, Manip, Prelevement, Reglages
from mat_methode.domain.regles import (
    blocs,
    echantillons_tries,
    est_entree,
    est_test,
    etiquettes,
    moment_court,
    numero_etape,
    plage,
    total_preleve,
)
from mat_methode.domain.texte import (
    cap,
    de,
    etapes_txt,
    fmt_dur,
    fmt_num,
    fmt_vol,
    liste,
    minuscule_initiale,
    norm,
    phrase,
)

REPERE = re.compile(r"\{\{\?([^}]*)\}\}")


def ph(libelle: str) -> str:
    return f"{{{{?{libelle}}}}}"


def vers_markdown(s: str) -> str:
    return REPERE.sub(lambda mt: f"[{mt.group(1)} à saisir]", s)


@dataclass
class Section:
    titre: str
    texte: str


@dataclass
class LigneReactif:
    nom: str
    quantite: str = ""
    scirius: str = ""
    emplacement: str = ""
    fournisseur: str = ""
    lot: str = ""
    etapes: list[int] = field(default_factory=list)


@dataclass
class LigneEchantillon:
    id: str
    etape: str  # « entrée » ou « 3 · désacidification »
    n_etape: int
    moment: str
    volume: float | None
    scirius: str
    aramis: str
    labo: str
    analyses: list[str]


@dataclass
class Phase:
    n: int  # 0 = Départ
    titre: str
    conditions: str
    materiel: list[str]
    reactifs: list[LigneReactif]
    echantillons: list[LigneEchantillon]
    groupe: str = ""  # grande étape (ex. « Degumming »)
    groupe_plage: str = ""  # « étapes 2 à 4 »
    debut_groupe: bool = False  # première phase de sa grande étape


@dataclass
class Rapport:
    sections: list[Section]
    reactifs: list[LigneReactif]
    echantillons: list[LigneEchantillon]
    phases: list[Phase]


# ------------------------------------------------------------------ résumés
def resume_conditions(e: Etape) -> str:
    """« 25 °C · 15 min · 300 tr/min · sous vide · 5 µm » (carte du flux, détail par phase)."""
    out = []
    if e.temperature_c is not None:
        out.append(f"{fmt_num(e.temperature_c)} °C")
    if e.duree_min is not None:
        out.append(fmt_dur(e.duree_min))
    if e.agitation_trmin is not None:
        out.append(f"{fmt_num(e.agitation_trmin)} tr/min")
    if e.vide is not None:
        out.append("sous vide" + (f" {fmt_num(e.vide.mbar)} mbar" if e.vide.mbar else ""))
    if e.filtre_um is not None:
        out.append(f"{fmt_num(e.filtre_um)} µm")
    return " · ".join(out)


def autres_conditions(e: Etape) -> list[str]:
    return [f"{a.nom.strip()} {a.valeur or ''}".strip() for a in e.autres if a.nom and a.nom.strip()]


def conditions_phase(e: Etape) -> str:
    return " · ".join(x for x in [resume_conditions(e)] + autres_conditions(e) if x)


def quantite_texte(q: str) -> str:
    """« 1 : 1 (v/v) » -> « 1 : 1, v/v » pour éviter les doubles parenthèses (§14.1)."""
    q = (q or "").strip()
    return re.sub(r"\s*\(([^()]*)\)\s*$", r", \1", q)


def clause_etape(e: Etape, reglages: Reglages | None = None) -> str:
    """« filtré sous vide sur membrane de 5 µm pendant 10 min »."""
    b = []
    if e.vide is not None:
        b.append("sous vide" + (f" ({fmt_num(e.vide.mbar)} mbar)" if e.vide.mbar else ""))
    if e.filtre_um is not None:
        b.append(f"sur membrane de {fmt_num(e.filtre_um)} µm")
    reacs = [r for r in e.reactifs if r.nom]
    if reacs:
        b.append("en présence " + liste([de(minuscule_initiale(r.nom)) + (f" ({quantite_texte(r.quantite)})" if r.quantite.strip() else "")
                                          for r in reacs]))
    if e.temperature_c is not None:
        b.append(f"à {fmt_num(e.temperature_c)} °C")
    if e.duree_min is not None:
        b.append(f"pendant {fmt_dur(e.duree_min)}")
    if e.agitation_trmin is not None:
        b.append(f"à {fmt_num(e.agitation_trmin)} tr/min" if est_centrifugation(e.operation)
                 else f"sous agitation à {fmt_num(e.agitation_trmin)} tr/min")
    b += autres_conditions(e)
    rem = e.remarque.strip()
    part = reglages.participe(e.operation) if reglages is not None else participe(e.operation)
    return part + ("".join(" " + x for x in b)) + (f" ({rem})" if rem else "")


def sujet(i: int, n: int) -> str:
    """Début de la phrase de l'étape i (0..n-1) : varie les liaisons (§14.1)."""
    if i == 0:
        return "le produit a été"
    if i == n - 1 and n >= 3:
        return "il a enfin été"
    return "il a ensuite été" if i % 2 == 1 else "il a été"


def moment_phrase(m: Manip, p: Prelevement) -> str:
    n = numero_etape(m, p)
    if est_entree(m, p):
        return "avant traitement (entrée du flux)"
    e = m.etapes[n - 1]
    if p.moment == "pendant":
        return f"pendant l’étape {n} ({e.operation})" + (f", à {fmt_dur(p.temps_min)}" if p.temps_min is not None else "")
    return f"à l’effluent de l’étape {n} ({e.operation})"


def reactifs_utilises(m: Manip) -> list[tuple[str, list[int]]]:
    out: list[tuple[str, list[int]]] = []
    for i, e in enumerate(m.etapes):
        for r in e.reactifs:
            if not r.nom:
                continue
            x = next((o for o in out if norm(o[0]) == norm(r.nom)), None)
            if x is None:
                x = (r.nom, [])
                out.append(x)
            if i + 1 not in x[1]:
                x[1].append(i + 1)
    return out


def _inv(reglages: Reglages, nom: str):
    r = reglages.reactif(nom)
    return r.model_dump() if r else {}


# ------------------------------------------------------------------ rapport
def construire(m: Manip, reglages: Reglages) -> Rapport:
    c, lab, ech = m.contexte, etiquettes(m), echantillons_tries(m)
    ns, ne = len(m.prelevements), len(m.etapes)
    grands = [(g, idx) for g, idx in blocs(m) if g is not None]
    sections = []

    t21 = (f"Demande : {c.donneur or ph('donneur d’ordre')}{', type ' + c.type if c.type else ''} (réf. {c.ref or ph('n°')}). "
           + phrase("Objectif", c.objectif) + (phrase("Idée testée", c.idee) if est_test(c.type) else "")
           + phrase("Contexte", c.precisions)
           + f"Matière étudiée : {c.matiere or ph('matière')} (lot {c.lot or ph('n°')}). "
           + "Volume de départ : " + (f"{fmt_vol(c.volume_depart_ml)} mL" if c.volume_depart_ml is not None else ph("volume de départ"))
           + (f", dont {fmt_vol(total_preleve(m))} mL prélevés sous forme de {ns} échantillon{'s' if ns > 1 else ''}" if ns else "")
           + "."
           + (f" Le flux comporte {ne} étape{'s' if ne > 1 else ''}{f' (étapes 1 à {ne})' if ne > 1 else ''}, décrites en 2.3." if ne else "")
           + (" Grandes étapes : " + " ; ".join(f"{g.nom} ({plage([i + 1 for i in idx])})" for g, idx in grands) + "." if grands else ""))
    sections.append(Section("2.1 Échantillon", t21))

    materiel: list[str] = []
    materiel_etapes: dict[str, list[int]] = {}
    for i, e in enumerate(m.etapes):
        for x in e.equipements:
            k = norm(x)
            if k not in materiel_etapes:
                materiel.append(x)
                materiel_etapes[k] = []
            if i + 1 not in materiel_etapes[k]:
                materiel_etapes[k].append(i + 1)
    reacs = reactifs_utilises(m)
    reac_txt = []
    for nom, et in reacs:
        f = _inv(reglages, nom)
        reac_txt.append(f"{minuscule_initiale(nom)} ({etapes_txt(et)}, fournisseur {f.get('fournisseur') or ph('nom')}, lot {f.get('lot') or ph('n°')})")
    t22 = ("Matériel : " + (", ".join(f"{minuscule_initiale(x)} ({etapes_txt(materiel_etapes[norm(x)])})" for x in materiel) if materiel else ph("matériel"))
           + "." + (f" Réactifs : {' ; '.join(reac_txt)}." if reac_txt else ""))
    sections.append(Section("2.2 Matériel et réactifs", t22))

    morceaux23 = []
    for g, idx in blocs(m):
        if g is not None:
            morceaux23.append(f"{g.nom} ({plage([i + 1 for i in idx])}).")
        morceaux23 += [f"Étape {i + 1} : {sujet(i, ne)} {clause_etape(m.etapes[i], reglages)}." for i in idx]
    t23 = " ".join(morceaux23) if ne else ph("protocole")
    sections.append(Section("2.3 Méthodes", t23))

    if ns:
        morceaux = []
        for p in ech:
            labo = f"au {p.labo}" if p.labo else ph("laboratoire")
            ids = ", ".join(x for x in [f"n° Scirius {p.scirius}" if p.scirius else "", f"n° Aramis {p.aramis}" if p.aramis else ""] if x)
            morceaux.append(f"Un échantillon de {fmt_vol(p.volume_ml or 0)} mL ({lab[p.id]}) a été prélevé {moment_phrase(m, p)}, puis analysé {labo}"
                            + (f" ({', '.join(p.analyses)})" if p.analyses else "") + (f" [{ids}]" if ids else "") + ".")
        sections.append(Section("2.4 Prélèvements", " ".join(morceaux)))

    tab_reac = []
    for nom, et in reacs:
        f = _inv(reglages, nom)
        tab_reac.append(LigneReactif(nom=nom, scirius=f.get("scirius", ""), emplacement=f.get("emplacement", ""),
                                     fournisseur=f.get("fournisseur", ""), lot=f.get("lot", ""), etapes=et))

    def ligne_ech(p: Prelevement) -> LigneEchantillon:
        n = numero_etape(m, p)
        return LigneEchantillon(id=lab[p.id], etape=f"{n} · {m.etapes[n - 1].operation}" if n else "entrée", n_etape=n,
                                moment=moment_court(m, p), volume=p.volume_ml, scirius=p.scirius, aramis=p.aramis,
                                labo=p.labo, analyses=list(p.analyses))

    tab_ech = [ligne_ech(p) for p in ech]
    phases = [Phase(0, "Départ", "", [], [], [x for x in tab_ech if x.n_etape == 0])]
    for i, e in enumerate(m.etapes):
        rs = []
        for r in e.reactifs:
            if r.nom:
                f = _inv(reglages, r.nom)
                rs.append(LigneReactif(nom=r.nom, quantite=r.quantite, scirius=f.get("scirius", ""), emplacement=f.get("emplacement", ""),
                                       fournisseur=f.get("fournisseur", ""), lot=f.get("lot", ""), etapes=[i + 1]))
        g = m.groupe(e.groupe_id)
        nums = [k + 1 for gg, idx in blocs(m) if gg is g and i in idx for k in idx] if g else []
        phases.append(Phase(i + 1, f"{i + 1} · {cap(e.operation)}", conditions_phase(e), list(e.equipements), rs,
                            [ligne_ech(p) for p in ech if p.etape_id == e.id], groupe=g.nom if g else "",
                            groupe_plage=plage(nums) if g else "", debut_groupe=bool(g) and nums[0] == i + 1))
    return Rapport(sections, tab_reac, tab_ech, phases)


# ------------------------------------------------------------------ en-tête commun aux exports
def ligne_version(m: Manip) -> str:
    from mat_methode.domain.texte import fmt_dt
    s = f"Version {m.rev} · enregistrée le {fmt_dt(m.maj)}"
    if m.lancee:
        s += f" · lancée le {fmt_dt(m.lancee.le)} par {m.lancee.par}"
    return s


def mention_modifiee(m: Manip) -> str:
    n = len(m.journal)
    if not (m.lancee and n):
        return ""
    return f"Modifiée après lancement ({n} modification{'s' if n > 1 else ''})"


def a_saisir(v) -> str:
    return str(v) if v not in (None, "") else "à saisir"


# ------------------------------------------------------------------ Markdown
def markdown(m: Manip, reglages: Reglages) -> str:
    from mat_methode.domain.texte import fmt_dt
    r, c = construire(m, reglages), m.contexte
    ln = [f"# {m.nom}", "",
          f"Donneur d’ordre : {c.donneur or '[à saisir]'}{' · Type : ' + c.type if c.type else ''} · Réf. : {c.ref or '[à saisir]'}"]
    if m.tags:
        ln += ["", "Tags : " + " ".join("#" + t for t in m.tags)]
    ln += ["", ligne_version(m)]
    if mention_modifiee(m):
        ln += ["", f"⚠ {mention_modifiee(m)}, voir la fin du document."]
    ln += ["", "## 2. Matériel et méthodes", ""]
    for s in r.sections:
        ln += [f"### {s.titre}", "", vers_markdown(s.texte), ""]
    ln += ["### Détail par phase du flux", ""]
    for p in r.phases:
        if p.debut_groupe:
            ln += [f"**Grande étape : {p.groupe} ({p.groupe_plage})**", ""]
        ln += [f"#### {p.titre}", ""]
        if p.conditions:
            ln.append(f"- Conditions : {p.conditions}")
        if p.materiel:
            ln.append(f"- Matériel : {', '.join(p.materiel)}")
        if p.n:
            ln.append(f"- Réactifs : {'' if p.reactifs else 'aucun'}")
            ln += [f"  - {x.nom}{' · ' + x.quantite if x.quantite else ''} · n° Scirius {a_saisir(x.scirius)} · emplacement {a_saisir(x.emplacement)}"
                   f" · fournisseur {a_saisir(x.fournisseur)} · lot {a_saisir(x.lot)}" for x in p.reactifs]
        ln.append(f"- Échantillons : {'' if p.echantillons else 'aucun'}")
        ln += [f"  - {x.id} · {fmt_vol(x.volume or 0)} mL · {x.moment} · {x.labo} · {', '.join(x.analyses) or 'aucune analyse'}"
               f" · n° Scirius {a_saisir(x.scirius)} · n° Aramis {a_saisir(x.aramis)}" for x in p.echantillons]
        ln.append("")
    if r.reactifs:
        ln += ["### Réactifs", "", "| Réactif | N° Scirius | Emplacement | Fournisseur | Lot | Étape |", "|---|---|---|---|---|---|"]
        ln += [f"| {x.nom} | {a_saisir(x.scirius)} | {a_saisir(x.emplacement)} | {a_saisir(x.fournisseur)} | {a_saisir(x.lot)} | {', '.join(map(str, x.etapes))} |"
               for x in r.reactifs]
        ln.append("")
    if r.echantillons:
        ln += ["### Échantillons", "", "| Éch. | Étape | Moment | Volume | N° Scirius | N° Aramis | Laboratoire | Analyses |",
               "|---|---|---|---|---|---|---|---|"]
        ln += [f"| {x.id} | {x.etape} | {x.moment} | {fmt_vol(x.volume or 0)} mL | {a_saisir(x.scirius)} | {a_saisir(x.aramis)} | {x.labo} | {', '.join(x.analyses)} |"
               for x in r.echantillons]
        ln.append("")
    if m.lancee:
        ln += ["### Modifications après lancement", ""]
        if m.journal:
            ln += ["| Date et heure | Par | Modification |", "|---|---|---|"]
            ln += [f"| {fmt_dt(j.t)} | {j.par} | {j.txt} |" for j in m.journal]
        else:
            ln.append("Aucune modification depuis le lancement.")
        ln.append("")
    return "\n".join(ln)
