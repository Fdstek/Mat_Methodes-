"""Format d'échange JSON (§7) : `manip-pour-script-pdf.json`.

Sert à produire le PDF et le Word, et à ré-importer une manip (export de l'application ou
JSON issu de l'extraction d'un ancien rapport PDF).
"""
from __future__ import annotations

from datetime import date

from mat_methode.domain.models import (
    UNITES_VITESSE,
    Etape,
    Groupe,
    Lancement,
    LigneJournal,
    Manip,
    Matiere,
    Parallele,
    Prelevement,
    ReactifEtape,
    Reglages,
    Vide,
    Voie,
)
from mat_methode.domain.prototype import contexte_depuis
from mat_methode.domain.reglages_ops import auteur, nom_auteur, nom_etat
from mat_methode.domain.regles import bloc_au_depart, blocs, echantillons_tries, etiquettes, lettre_voie, numero_etape, reperes_etapes
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
    if c.scirius:
        d["scirius"] = c.scirius
    if c.fournisseur:
        d["fournisseur"] = c.fournisseur
    if c.emplacement:
        d["emplacement"] = c.emplacement
    if c.experience:
        d["experience"] = c.experience
    if c.attribue:
        d["attribue"] = c.attribue
    d["tags"] = list(m.tags)
    if reperes_etapes(m):
        d["reperes"] = [{"initiale": i.replace("∥", "voie "), "groupe": g, "materiel": mat} for i, g, mat in reperes_etapes(m)]
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
        if e.agitation_trmin is not None and e.vitesse_unite != "tr/min":
            par["vitesse_unite"] = e.vitesse_unite
        etapes.append({"n": i + 1, "operation": e.operation, "parametres": par, "equipement": list(e.equipements),
                       "reactifs": [minuscule_initiale(x.nom) for x in e.reactifs if x.nom],
                       "reactifs_detail": [{"nom": x.nom, "quantite": x.quantite_complete, **({"contact": x.contact} if x.contact.strip() else {}),
                                           **({"consigne": x.consigne} if x.consigne.strip() else {})} for x in e.reactifs],
                       "autres": [a.model_dump() for a in e.autres if a.nom], "remarque": e.remarque})
        if m.groupe(e.groupe_id):
            etapes[-1]["groupe"] = m.groupe(e.groupe_id).nom
        par = m.parallele(e.parallele_id)
        if par is not None:  # étape en parallèle : bloc, voie (A, B…) et nombre de voies
            voie = next((v for v in par.voies if v.id == e.voie_id), par.voies[0])
            etapes[-1]["parallele"] = {"id": par.id, "voie": par.voies.index(voie), "lettre": lettre_voie(m, par.id, voie.id),
                                       "nvoies": len(par.voies), "nom_voie": voie.nom}
            if voie.part is not None:
                etapes[-1]["parallele"].update({"part": voie.part, "part_unite": voie.part_unite})
            if voie.autres:
                etapes[-1]["parallele"]["autres"] = [a.model_dump() for a in voie.autres]
            premiere = not any(x.parallele_id == par.id and x.voie_id == voie.id for x in m.etapes[:i])
            if premiere and bloc_au_depart(m) is par:  # le bloc ouvre le flux : Départ propre à la voie (matières, volume)
                from mat_methode.domain.volumes import volume_ajoute
                etapes[-1]["parallele"]["depart"] = {"volume_ml": _nombre(volume_ajoute(voie)), "matieres": [
                    {"nom": a.nom, "quantite": a.quantite_complete, "reference": (reglages.reactif(a.nom).scirius if reglages.reactif(a.nom) else "") or a.reference}
                    for a in voie.autres if a.nom]}
        if e.apports and i > 0 and m.parallele(m.etapes[i - 1].parallele_id):  # étape qui réunit des voies : quantité prise de chacune
            pp = m.parallele(m.etapes[i - 1].parallele_id)
            etapes[-1]["apports"] = {str(k): v for k, vo in enumerate(pp.voies) if (v := e.apports.get(vo.id)) is not None}
    materiel: list[str] = []
    for e in m.etapes:
        materiel += [x for x in e.equipements if x not in materiel]
    used = reactifs_utilises(m)
    d = {
        "titre": m.nom, "contexte": contexte_vers(m), "version": m.rev, "enregistree_le": m.maj,
        "lancee": ({**m.lancee.model_dump(), "par": auteur(reglages, m.lancee.par)} if m.lancee else None),
        "journal": [{**j.model_dump(), "par": auteur(reglages, j.par)} for j in m.journal],
        **({"statuts": [{"t": c.t, "par": auteur(reglages, c.par), "nom": nom_auteur(reglages, c.par),
                         "de": nom_etat(reglages, c.de)[0], "vers": nom_etat(reglages, c.vers)[0]} for c in m.statuts]}
           if m.statuts else {}),
        **({"a_faire": [{"categorie": t.categorie, "texte": t.texte} for t in m.a_faire if not t.fait]}
           if any(not t.fait for t in m.a_faire) else {}),
        "etapes": etapes,
        "sous_sections": [{"titre": s.titre, "texte": vers_markdown(s.texte)} for s in r.sections],
        "materiel": materiel,
        "reactifs": [minuscule_initiale(n) for n, _ in used],
        "prelevements": [{"id": lab[p.id], "apres_etape": numero_etape(m, p),
                          "moment": p.moment if numero_etape(m, p) else "avant", "temps_min": _nombre(p.temps_min),
                          "volume_ml": _nombre(p.volume_ml), "scirius": p.scirius or None, "aramis": p.aramis or None,
                          "labo": p.labo, "analyses": list(p.analyses),
                          **({"commentaire": p.commentaire.strip()} if p.commentaire.strip() else {})} for p in echantillons_tries(m)],
        "phases": [{**({"n": ph.n} if any(x.depart_voie for x in r.phases) else {}), "titre": ph.titre, "conditions": ph.conditions, "materiel": ph.materiel,
                    "reactifs": [{"nom": x.nom, "quantite": x.quantite, "scirius": x.scirius, "emplacement": x.emplacement,
                                  "fournisseur": x.fournisseur, "lot": x.lot,
                                  **({"contact": x.contact} if x.contact else {}), **({"consigne": x.consigne} if x.consigne else {})} for x in ph.reactifs],
                    "echantillons": [{"id": x.id, "volume": _nombre(x.volume), "moment": x.moment, "labo": x.labo, "analyses": x.analyses,
                                      "scirius": x.scirius, "aramis": x.aramis,
                                      **({"commentaire": x.commentaire} if x.commentaire else {})} for x in ph.echantillons],
                    **({"remarque": ph.remarque} if ph.remarque else {}),
                    **({"parallele": ph.parallele} if ph.parallele else {}), **({"reunion": ph.reunion} if ph.reunion else {}),
                    **({"depart_voie": True} if ph.depart_voie else {}), **({"entree_voies": True} if ph.entree_voies else {})} for ph in r.phases],
        "inventaire_reactifs": [{"nom": minuscule_initiale(n), **{k: (getattr(reglages.reactif(n), k, "") or None)
                                                                 for k in ("scirius", "emplacement", "fournisseur", "lot")}}
                                for n, _ in used],
    }
    grands = [(g, idx) for g, idx in blocs(m) if g is not None]
    if grands:  # clé absente sans grande étape : format identique à celui du prototype
        d["grandes_etapes"] = [{"nom": g.nom, "etapes": [i + 1 for i in idx]} for g, idx in grands]
        for ph, x in zip(r.phases, d["phases"]):
            if ph.groupe:
                x["groupe"] = ph.groupe
    return d


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
                  vitesse_unite=p.get("vitesse_unite") if p.get("vitesse_unite") in UNITES_VITESSE else "tr/min",
                  vide=Vide(mbar=p.get("vide_mbar")) if p.get("vide") else None,
                  equipements=list(x.get("equipement") or []),
                  autres=[a for a in x.get("autres") or [] if isinstance(a, dict)],
                  reactifs=[ReactifEtape(nom=rd.get("nom", ""), quantite=rd.get("quantite") or "", contact=rd.get("contact") or "",
                                           consigne=rd.get("consigne") or "") for rd in detail],
                  remarque=x.get("remarque") or "")
        if p.get("ratio") and len(e.reactifs) >= 1 and not e.reactifs[0].quantite:
            e.reactifs[0].quantite = f"{p['ratio'].replace(':', ' : ')} (v/v)" if ":" in p["ratio"] else p["ratio"]
        nom_groupe = (x.get("groupe") or "").strip()
        if nom_groupe:  # étapes consécutives de même nom = une grande étape
            prec = m.groupe(m.etapes[-1].groupe_id) if m.etapes else None
            if prec is None or prec.nom != nom_groupe:
                prec = Groupe(nom=nom_groupe)
                m.groupes.append(prec)
            e.groupe_id = prec.id
            if nom_groupe not in reglages.grandes_etapes:
                reglages.grandes_etapes.append(nom_groupe)
        pj = x.get("parallele")
        if isinstance(pj, dict) and pj.get("id"):  # étape en parallèle : on recrée le bloc et ses voies
            bloc = next((q for q in m.paralleles if q.id == f"import-{pj['id']}"), None)
            if bloc is None:
                bloc = Parallele(id=f"import-{pj['id']}", voies=[Voie() for _ in range(max(2, int(pj.get("nvoies") or 2)))])
                m.paralleles.append(bloc)
            k = min(max(int(pj.get("voie") or 0), 0), len(bloc.voies) - 1)
            bloc.voies[k].nom = pj.get("nom_voie") or bloc.voies[k].nom
            if pj.get("part") is not None:
                bloc.voies[k].part = float(pj["part"])
                bloc.voies[k].part_unite = "mL" if pj.get("part_unite") == "mL" else "%"
            if pj.get("autres") and not bloc.voies[k].autres:
                bloc.voies[k].autres = [Matiere(nom=a.get("nom", ""), quantite=a.get("quantite", ""), unite=a.get("unite", "")) for a in pj["autres"]
                                        if isinstance(a, dict)]
            e.parallele_id, e.voie_id, e.groupe_id = bloc.id, bloc.voies[k].id, None
        if isinstance(x.get("apports"), dict) and m.etapes and m.parallele(m.etapes[-1].parallele_id):  # quantités prises de chaque voie
            bloc_prec = m.parallele(m.etapes[-1].parallele_id)
            for cle, val in x["apports"].items():
                if str(cle).isdigit() and int(cle) < len(bloc_prec.voies) and isinstance(val, (int, float)):
                    e.apports[bloc_prec.voies[int(cle)].id] = float(val)
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
            analyses=list(p.get("analyses") or []), commentaire=p.get("commentaire") or ""))
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
