"""Lecture des données du prototype web (format de `donnees_exemple_complete.json`).

Sert pour « Restaurer les exemples » et pour reprendre des données saisies dans le prototype.
"""
from __future__ import annotations

import json
from importlib import resources

from mat_methode.domain.models import (
    Communes,
    Condition,
    Contexte,
    Etape,
    Etat,
    Laboratoire,
    Lancement,
    LigneJournal,
    Manip,
    Prelevement,
    ReactifEtape,
    ReactifInventaire,
    Reglages,
    Vide,
)

TONS = {"": "neutre", "info": "info", "ok": "ok", "warn": "warn", "danger": "danger"}


def _vide(v):
    return Vide(mbar=v.get("mbar")) if isinstance(v, dict) else None


def contexte_depuis(c: dict) -> Contexte:
    return Contexte(
        donneur=c.get("donneur") or "", type=c.get("type") or "", objectif=c.get("objectif") or "",
        idee=c.get("idee") or "", precisions=c.get("precisions") or "", ref=c.get("ref") or "",
        date=c.get("date") or "", operateur=c.get("operateur") or "",
        volume_depart_ml=c.get("volumeDepart", c.get("volume_depart_ml")),
        matiere=c.get("matiere") or "", lot=c.get("lot") or "")


def etape_depuis(e: dict) -> Etape:
    return Etape(
        id=e["id"], operation=e.get("operation") or "étape libre", temperature_c=e.get("temperature"),
        duree_min=e.get("duree"), agitation_trmin=e.get("agitation"), filtre_um=e.get("filtre"),
        vide=_vide(e.get("vide")), equipements=list(e.get("equipement") or []),
        autres=[Condition(nom=a.get("nom", ""), valeur=str(a.get("valeur") or "")) for a in e.get("autres") or []],
        reactifs=[ReactifEtape(nom=r.get("nom", ""), quantite=r.get("quantite") or "") for r in e.get("reactifs") or []],
        remarque=e.get("remarque") or "")


def prelevement_depuis(p: dict) -> Prelevement:
    return Prelevement(id=p["id"], etape_id=p.get("etapeId"), moment=p.get("moment") or "avant", temps_min=p.get("temps"),
                       volume_ml=p.get("volume"), labo=p.get("labo") or "", analyses=list(p.get("analyses") or []),
                       scirius=p.get("scirius") or "", aramis=p.get("aramis") or "")


def _base_depuis(base) -> dict | None:
    """La photo du prototype est une chaîne JSON au format du prototype."""
    if not base:
        return None
    b = json.loads(base) if isinstance(base, str) else base
    return {"contexte": contexte_depuis(b.get("contexte", {})).model_dump(), "tags": list(b.get("tags", [])),
            "etapes": [etape_depuis(e).model_dump() for e in b.get("etapes", [])],
            "prelevements": [prelevement_depuis(p).model_dump() for p in b.get("prelevements", [])]}


def manip_depuis(m: dict) -> Manip:
    c = m.get("communes") or {}
    return Manip(
        id=m["id"], nom=m.get("nom") or "Manip", etat=m.get("statut") or "brouillon", rev=m.get("rev") or 1,
        maj=m.get("maj") or "", modifie_par=(m.get("contexte") or {}).get("operateur") or "",
        lancee=Lancement(**m["lancee"]) if m.get("lancee") else None,
        journal=[LigneJournal(**j) for j in m.get("journal") or []], base=_base_depuis(m.get("base")),
        tags=list(m.get("tags") or []), contexte=contexte_depuis(m.get("contexte") or {}),
        communes=Communes(temperature_c=c.get("temperature"), agitation_trmin=c.get("agitation"), vide=_vide(c.get("vide"))),
        etapes=[etape_depuis(e) for e in m.get("etapes") or []],
        prelevements=[prelevement_depuis(p) for p in m.get("prelevements") or []])


def depuis_prototype(d: dict) -> tuple[Reglages, list[Manip]]:
    r = Reglages(
        laboratoires=[Laboratoire(nom=l["nom"], volume_ml=l.get("volume"), analyses=list(l.get("analyses") or []))
                      if isinstance(l, dict) else Laboratoire(nom=l) for l in d.get("labos") or []],
        analyses=list(d.get("analyses") or []), donneurs_ordre=list(d.get("donneurs") or []),
        types_demande=list(d.get("types") or []),
        etats=[Etat(id=s["id"], nom=s["nom"], ton=TONS.get(s.get("ton") or "", "neutre")) for s in d.get("statuts") or []]
        or Reglages().etats,
        reactifs=[ReactifInventaire(nom=x["nom"], scirius=x.get("scirius") or "", emplacement=x.get("emplacement") or "",
                                    fournisseur=x.get("fournisseur") or "", lot=x.get("lot") or "") for x in d.get("inventaire") or []])
    return r, [manip_depuis(m) for m in d.get("manips") or []]


def exemples() -> tuple[Reglages, list[Manip]]:
    """Données d'exemple livrées avec l'application."""
    txt = resources.files("mat_methode.data").joinpath("exemples.json").read_text(encoding="utf-8")
    return depuis_prototype(json.loads(txt))
