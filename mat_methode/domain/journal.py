"""Lancement d'une manip et journal des modifications (§8.9).

Après le lancement, chaque modification d'un élément suivi est notée par comparaison avec une
photo de référence (« base »). Le journal est en ajout seulement.
"""
from __future__ import annotations

from mat_methode.domain.models import Lancement, LigneJournal, Manip, maintenant_iso
from mat_methode.domain.regles import etiquettes, moment_court
from mat_methode.domain.texte import cap, fmt_num, fmt_vol, norm

SUIVI_DEMANDE = {
    "donneur": "donneur d’ordre", "type": "type de demande", "objectif": "objectif", "idee": "idée testée",
    "precisions": "contexte", "ref": "référence", "volume_depart_ml": "volume de départ", "matiere": "matière",
    "lot": "lot", "scirius": "n° Scirius de la charge", "fournisseur": "fournisseur de la charge", "date": "date", "operateur": "opérateur",
}
SUIVI_ETAPE = [("operation", "opération", ""), ("temperature_c", "température", " °C"), ("duree_min", "durée", " min"),
               ("agitation_trmin", "agitation", " tr/min"), ("filtre_um", "membrane", " µm"), ("remarque", "remarque", "")]
SUIVI_ECH = [("volume_ml", "volume", " mL"), ("moment", "moment", ""), ("temps_min", "temps", " min"),
             ("labo", "laboratoire", ""), ("scirius", "n° Scirius", ""), ("aramis", "n° Aramis", "")]


def operateur(m: Manip) -> str:
    return (m.contexte.operateur or "").strip() or "Opérateur"


def photo(m: Manip) -> dict:
    """Contenu suivi : demande, tags, étapes, échantillons."""
    d = m.model_dump(include={"contexte", "tags", "etapes", "prelevements", "groupes"})
    return d


def _v(x) -> str:
    if x is None or x == "":
        return "vide"
    if isinstance(x, (int, float)) and not isinstance(x, bool):
        return fmt_num(x)
    return str(x)


def _eq(a, b) -> bool:
    return (a if a is not None else "") == (b if b is not None else "")


def _moment(m: Manip, p: dict) -> str:
    from mat_methode.domain.models import Prelevement
    return moment_court(m, Prelevement.model_validate(p))


def differences(a: dict, b: dict, m: Manip) -> list[str]:
    """Lignes de journal entre la photo « a » (référence) et « b » (actuelle) de la manip m."""
    out: list[str] = []
    lab = etiquettes(m)
    ca, cb = a.get("contexte", {}), b.get("contexte", {})
    for k, nom in SUIVI_DEMANDE.items():
        if not _eq(ca.get(k), cb.get(k)):
            out.append(f"Demande · {nom} : {_v(ca.get(k))} → {_v(cb.get(k))}{' mL' if k == 'volume_depart_ml' else ''}")
    ta, tb = a.get("tags", []), b.get("tags", [])
    out += [f"Tag ajouté : #{t}" for t in tb if not any(norm(x) == norm(t) for x in ta)]
    out += [f"Tag retiré : #{t}" for t in ta if not any(norm(x) == norm(t) for x in tb)]

    ga = {g["id"]: g["nom"] for g in a.get("groupes", [])}
    gb = {g["id"]: g["nom"] for g in b.get("groupes", [])}
    for k, nom in gb.items():
        if k in ga and ga[k] != nom:
            out.append(f"Grande étape renommée : {ga[k]} → {nom}")
    ea, eb = a.get("etapes", []), b.get("etapes", [])
    ia = {e["id"]: (e, i) for i, e in enumerate(ea)}
    ids_b = {e["id"] for e in eb}
    ordre_a = [e["id"] for e in ea if e["id"] in ids_b]
    ordre_b = [e["id"] for e in eb if e["id"] in ia]
    for i, e in enumerate(eb):
        lb = f"Étape {i + 1} · {cap(e['operation'])}"
        if e["id"] not in ia:
            out.append(f"Étape ajoutée : {lb}" + (f" (dans {gb[e['groupe_id']]})" if e.get("groupe_id") in gb else ""))
            continue
        oe, oi = ia[e["id"]]
        if ordre_a.index(e["id"]) != ordre_b.index(e["id"]):
            out.append(f"{lb} : déplacée (étape {oi + 1} → {i + 1})")
        if oe.get("groupe_id") != e.get("groupe_id"):
            out.append(f"{lb} : grande étape {ga.get(oe.get('groupe_id'), 'aucune')} → {gb.get(e.get('groupe_id'), 'aucune')}")
        for k, nom, u in SUIVI_ETAPE:
            if not _eq(oe.get(k), e.get(k)):
                out.append(f"{lb} : {nom} {_v(oe.get(k))} → {_v(e.get(k))}{u}")
        va, vb = oe.get("vide"), e.get("vide")
        if bool(va) != bool(vb):
            out.append(f"{lb} : sous vide {'activé' if vb else 'désactivé'}")
        elif vb and not _eq(va.get("mbar"), vb.get("mbar")):
            out.append(f"{lb} : pression {_v(va.get('mbar'))} → {_v(vb.get('mbar'))} mbar")
        out += [f"{lb} : matériel ajouté ({x})" for x in e["equipements"] if x not in oe["equipements"]]
        out += [f"{lb} : matériel retiré ({x})" for x in oe["equipements"] if x not in e["equipements"]]
        ra = {norm(r["nom"]): r for r in oe["reactifs"]}
        rb = {norm(r["nom"]): r for r in e["reactifs"]}
        for k, r in rb.items():
            if k not in ra:
                out.append(f"{lb} : réactif ajouté ({r['nom']}{', ' + r['quantite'] if r['quantite'] else ''})")
            elif not _eq(ra[k]["quantite"], r["quantite"]):
                out.append(f"{lb} : réactif {r['nom']}, quantité {_v(ra[k]['quantite'])} → {_v(r['quantite'])}")
        out += [f"{lb} : réactif retiré ({r['nom']})" for k, r in ra.items() if k not in rb]
        aa = {norm(x["nom"]): x for x in oe.get("autres", []) if x["nom"]}
        ab = {norm(x["nom"]): x for x in e.get("autres", []) if x["nom"]}
        for k, x in ab.items():
            if k not in aa:
                out.append(f"{lb} : condition ajoutée ({(x['nom'] + ' ' + (x['valeur'] or '')).strip()})")
            elif not _eq(aa[k]["valeur"], x["valeur"]):
                out.append(f"{lb} : {x['nom']} {_v(aa[k]['valeur'])} → {_v(x['valeur'])}")
        out += [f"{lb} : condition retirée ({x['nom']})" for k, x in aa.items() if k not in ab]
    out += [f"Étape supprimée : {cap(e['operation'])} (était l’étape {i + 1})" for i, e in enumerate(ea) if e["id"] not in ids_b]

    pa = {p["id"]: p for p in a.get("prelevements", [])}
    pb = {p["id"] for p in b.get("prelevements", [])}
    for p in b.get("prelevements", []):
        lb = lab.get(p["id"], "échantillon")
        o = pa.get(p["id"])
        if o is None:
            out.append(f"Échantillon ajouté : {lb} ({fmt_vol(p['volume_ml'] or 0)} mL, {_moment(m, p)})")
            continue
        for k, nom, u in SUIVI_ECH:
            if not _eq(o.get(k), p.get(k)):
                out.append(f"Échantillon {lb} : {nom} {_v(o.get(k))} → {_v(p.get(k))}{u}")
        out += [f"Échantillon {lb} : analyse ajoutée ({x})" for x in p["analyses"] if x not in o["analyses"]]
        out += [f"Échantillon {lb} : analyse retirée ({x})" for x in o["analyses"] if x not in p["analyses"]]
    out += [f"Échantillon supprimé : {fmt_vol(p['volume_ml'] or 0)} mL ({_moment(m, p)})"
            for p in a.get("prelevements", []) if p["id"] not in pb]
    return out


def journaliser(m: Manip, t: str | None = None, par: str | None = None) -> list[LigneJournal]:
    """Compare à la photo de référence et ajoute les lignes au journal. Rien avant le lancement."""
    if not m.lancee:
        return []
    cur = photo(m)
    if m.base is None:
        m.base = cur
        return []
    lignes = [LigneJournal(t=t or maintenant_iso(), par=par or operateur(m), txt=x) for x in differences(m.base, cur, m)]
    if lignes:
        m.journal.extend(lignes)
        m.base = cur
    return lignes


def rattraper(m: Manip) -> list[LigneJournal]:
    """À la réouverture : modifications non journalisées (fermeture brutale), datées de la dernière modification."""
    return journaliser(m, t=m.maj)


def lancer(m: Manip, par: str | None = None, t: str | None = None) -> None:
    m.lancee = Lancement(le=t or maintenant_iso(), par=par or operateur(m))
    m.journal = []
    m.base = photo(m)


def peut_annuler_lancement(m: Manip) -> bool:
    return m.lancee is not None and not m.journal


def annuler_lancement(m: Manip) -> bool:
    if not peut_annuler_lancement(m):
        return False
    m.lancee, m.base = None, None
    return True
