"""Format d'échange JSON (§7) : `manip-pour-script-pdf.json`.

Sert à produire le PDF et le Word, et à ré-importer une manip (export de l'application ou
JSON issu de l'extraction d'un ancien rapport PDF).
"""
from __future__ import annotations

from datetime import date

from mat_methode.domain.models import (
    Etape,
    Lancement,
    LigneJournal,
    Manip,
    Prelevement,
    ReactifEtape,
    Reglages,
    Vide,
)
from mat_methode.domain.prototype import contexte_depuis
from mat_methode.domain.regles import echantillons_tries, etiquettes, numero_etape
from mat_methode.domain.texte import cap, minuscule_initiale
from mat_methode.report.rapport import construire, reactifs_utilises, vers_markdown


def _sans_none(d: dict) -> dict:
    return {k: v for k, v in d.items() if v is not None}


def contexte_vers(m: Manip) -> dict:
    c = m.contexte
    d = {"donneur": c.donneur, "ref": c.ref, "date": c.date, "operateur": c.operateur, "volumeDepart": c.volume_depart_ml,
         "matiere": c.matiere, "lot": c.lot, "type": c.type, "objectif": c.objectif, "precisions": c.precisions}
    if c.idee:
        d["idee"] = c.idee
    d["tags"] = list(m.tags)
    return d


def _nombre(v):
    return int(v) if isinstance(v, float) and v.is_integer() else v


def exporter(m: Manip, reglages: Reglages) -> dict:
    r, lab = construire(m, reglages), etiquettes(m)
    etapes = []
    for i, e in enumerate(m.etapes):
        par = _sans_none({"temperature_c": _nombre(e.temperature_c), "duree_min": _nombre(e.duree_min),
                          "agitation_trmin": _nombre(e.agitation_trmin), "filtre_um": _nombre(e.filtre_um)})
        if e.vide is not None:
            par.update({"vide": True, "vide_mbar": _nombre(e.vide.mbar)})
        etapes.append({"n": i + 1, "operation": e.operation, "parametres": par, "equipement": list(e.equipements),
                       "reactifs": [minuscule_initiale(x.nom) for x in e.reactifs if x.nom],
                       "reactifs_detail": [{"nom": x.nom, "quantite": x.quantite} for x in e.reactifs],
                       "autres": [a.model_dump() for a in e.autres if a.nom], "remarque": e.remarque})
    materiel: list[str] = []
    for e in m.etapes:
        materiel += [x for x in e.equipements if x not in materiel]
    used = reactifs_utilises(m)
    return {
        "titre": m.nom, "contexte": contexte_vers(m), "version": m.rev, "enregistree_le": m.maj,
        "lancee": m.lancee.model_dump() if m.lancee else None, "journal": [j.model_dump() for j in m.journal],
        "etapes": etapes,
        "sous_sections": [{"titre": s.titre, "texte": vers_markdown(s.texte)} for s in r.sections],
        "materiel": materiel,
        "reactifs": [minuscule_initiale(n) for n, _ in used],
        "prelevements": [{"id": lab[p.id], "apres_etape": numero_etape(m, p),
                          "moment": p.moment if numero_etape(m, p) else "avant", "temps_min": _nombre(p.temps_min),
                          "volume_ml": _nombre(p.volume_ml), "scirius": p.scirius or None, "aramis": p.aramis or None,
                          "labo": p.labo, "analyses": list(p.analyses)} for p in echantillons_tries(m)],
        "phases": [{"titre": ph.titre, "conditions": ph.conditions, "materiel": ph.materiel,
                    "reactifs": [{"nom": x.nom, "quantite": x.quantite, "scirius": x.scirius, "emplacement": x.emplacement,
                                  "fournisseur": x.fournisseur, "lot": x.lot} for x in ph.reactifs],
                    "echantillons": [{"id": x.id, "volume": _nombre(x.volume), "moment": x.moment, "labo": x.labo, "analyses": x.analyses,
                                      "scirius": x.scirius, "aramis": x.aramis} for x in ph.echantillons]} for ph in r.phases],
        "inventaire_reactifs": [{"nom": minuscule_initiale(n), **{k: (getattr(reglages.reactif(n), k, "") or None)
                                                                 for k in ("scirius", "emplacement", "fournisseur", "lot")}}
                                for n, _ in used],
    }


class ImportInvalide(ValueError):
    pass


def importer(d, reglages: Reglages) -> tuple[Manip, list[int]]:
    """Crée une manip (premier état) à partir d'un JSON d'échange ou d'extraction.

    Les réactifs rencontrés sont ajoutés à la liste des Réglages. Retourne aussi les numéros des
    étapes marquées « a_verifier » par l'extraction, à relire."""
    if isinstance(d, list):
        if not d:
            raise ImportInvalide("la liste est vide.")
        d = d[0]
    if not isinstance(d, dict) or not isinstance(d.get("etapes"), list):
        raise ImportInvalide("il manque la liste « etapes ».")
    titre = d.get("titre") or ""
    if not titre or titre.strip().lower().startswith("2. mat"):
        titre = f"Import du {date.today().strftime('%d/%m/%Y')}" + (f" ({d['source']})" if d.get("source") else "")
    m = Manip(nom=titre, etat=reglages.etat_initial())
    m.contexte.date = date.today().isoformat()
    if isinstance(d.get("contexte"), dict):
        ctx = dict(d["contexte"])
        tags = ctx.pop("tags", None)
        m.contexte = contexte_depuis(ctx)
        if isinstance(tags, list):
            m.tags = [str(t) for t in tags]
    a_verifier = []
    for i, x in enumerate(d["etapes"]):
        if not isinstance(x, dict):
            raise ImportInvalide(f"l’étape {i + 1} n’est pas un objet.")
        p = x.get("parametres") or {}
        detail = x.get("reactifs_detail")
        if detail is None:
            detail = [{"nom": cap(n), "quantite": ""} for n in x.get("reactifs") or []]
        for rd in detail:
            reglages.assurer_reactif(rd.get("nom", ""))
        e = Etape(operation=(x.get("operation") or "étape libre").strip(), temperature_c=p.get("temperature_c"),
                  duree_min=p.get("duree_min"), agitation_trmin=p.get("agitation_trmin"), filtre_um=p.get("filtre_um"),
                  vide=Vide(mbar=p.get("vide_mbar")) if p.get("vide") else None,
                  equipements=list(x.get("equipement") or []),
                  autres=[a for a in x.get("autres") or [] if isinstance(a, dict)],
                  reactifs=[ReactifEtape(nom=rd.get("nom", ""), quantite=rd.get("quantite") or "") for rd in detail],
                  remarque=x.get("remarque") or "")
        if p.get("ratio") and len(e.reactifs) >= 1 and not e.reactifs[0].quantite:
            e.reactifs[0].quantite = f"{p['ratio'].replace(':', ' : ')} (v/v)" if ":" in p["ratio"] else p["ratio"]
        m.etapes.append(e)
        if x.get("a_verifier"):
            a_verifier.append(i + 1)
    for p in d.get("prelevements") or []:
        n = p.get("apres_etape") or 0
        e = m.etapes[n - 1] if 0 < n <= len(m.etapes) else None
        m.prelevements.append(Prelevement(
            etape_id=e.id if e else None, moment=("pendant" if p.get("moment") == "pendant" else "effluent") if e else "avant",
            temps_min=p.get("temps_min"), volume_ml=p.get("volume_ml") if p.get("volume_ml") is not None else 50,
            scirius=p.get("scirius") or "", aramis=p.get("aramis") or "", labo=p.get("labo") or "",
            analyses=list(p.get("analyses") or [])))
    for r in d.get("inventaire_reactifs") or []:
        f = reglages.assurer_reactif(cap(r.get("nom") or ""))
        if f:
            for k in ("scirius", "emplacement", "fournisseur", "lot"):
                if not getattr(f, k) and r.get(k):
                    setattr(f, k, r[k])
    if d.get("lancee") and isinstance(d.get("journal"), list):
        # ré-import d'un export complet : le lancement et le journal sont conservés tels quels
        m.lancee = Lancement(**d["lancee"])
        m.journal = [LigneJournal(**j) for j in d["journal"]]
        from mat_methode.domain.journal import photo
        m.base = photo(m)
    return m, a_verifier
