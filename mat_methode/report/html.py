"""Rapport HTML imprimable (§11) : bandeau, flux en cartes, texte, détail par phase, tableaux."""
from __future__ import annotations

from html import escape

from mat_methode.domain.models import Manip, Reglages
from mat_methode.domain.regles import echantillons_tries, etiquettes, moment_court, numero_etape
from mat_methode.domain.texte import cap, fmt_dt, fmt_vol
from mat_methode.report.rapport import REPERE, construire, quantite_texte, resume_conditions

STYLE = """body{font:14px/1.6 system-ui,sans-serif;color:#14201D;max-width:860px;margin:24px auto;padding:0 16px}h1{margin:0 0 6px}h2{color:#0F6B5C;margin-top:26px}h3{margin:14px 0 4px}
.meta{background:#E1F0EC;padding:8px 12px;border-radius:6px;margin-bottom:6px}.flow{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:10px}
.c{border:1px solid #BFCBC7;border-radius:8px;padding:8px;font-size:12.5px;break-inside:avoid}.r{font-weight:600}.p{color:#0F6B5C}.e{color:#566360;font-size:11.5px}.s{margin-top:6px;background:#FDF1DC;border:1px solid #8A4B00;color:#8A4B00;border-radius:6px;padding:3px 6px;font-size:11.5px}
table{border-collapse:collapse;width:100%;font-size:12.5px}th,td{border:1px solid #BFCBC7;padding:4px 6px;text-align:left}th{background:#E1F0EC}i,.ph{color:#8A4B00}
@media print{body{margin:0}}.g{color:#0F6B5C;background:#E1F0EC;border-radius:4px;padding:1px 6px;font-size:10.5px;font-weight:700;margin-bottom:4px}"""


def e(s) -> str:
    return escape(str(s if s is not None else ""), quote=True)


def texte_html(s: str) -> str:
    """Échappe et transforme les repères {{?x}} en pastille « x à saisir »."""
    out, pos = [], 0
    for mt in REPERE.finditer(s):
        out.append(e(s[pos:mt.start()]))
        out.append(f'<span class="ph">{e(mt.group(1))} à saisir</span>')
        pos = mt.end()
    out.append(e(s[pos:]))
    return "".join(out)


def td(x) -> str:
    return e(x) if x else "<i>à saisir</i>"


def rapport_html(m: Manip, reglages: Reglages) -> str:
    r, lab, c = construire(m, reglages), etiquettes(m), m.contexte
    ech = echantillons_tries(m)
    cartes = []
    for i, et in enumerate(m.etapes):
        ps = [p for p in ech if numero_etape(m, p) == i + 1]
        cartes.append(
            '<div class="c">'
            + (f'<div class="g">{e(m.groupe(et.groupe_id).nom.upper())}</div>' if m.groupe(et.groupe_id) else "")
            + f'<b>{i + 1}. {e(cap(et.operation))}</b>'
            + "".join(f'<div class="r">{e(x.nom)}{" (" + e(quantite_texte(x.quantite)) + ")" if x.quantite else ""}</div>' for x in et.reactifs if x.nom)
            + f'<div class="p">{e(resume_conditions(et))}</div><div class="e">{e(", ".join(et.equipements))}</div>'
            + "".join(f'<div class="s"><b>{e(lab[p.id])}</b> · {fmt_vol(p.volume_ml or 0)} mL<br><small>{e(moment_court(m, p))}</small></div>' for p in ps)
            + "</div>")
    t1 = ""
    if r.reactifs:
        t1 = ("<h3>Réactifs</h3><table><tr><th>Réactif</th><th>N° Scirius</th><th>Emplacement</th><th>Fournisseur</th><th>Lot</th><th>Étape</th></tr>"
              + "".join(f"<tr><td><b>{e(x.nom)}</b></td><td>{td(x.scirius)}</td><td>{td(x.emplacement)}</td><td>{td(x.fournisseur)}</td>"
                        f"<td>{td(x.lot)}</td><td>{', '.join(map(str, x.etapes))}</td></tr>" for x in r.reactifs) + "</table>")
    t2 = ""
    if r.echantillons:
        t2 = ("<h3>Échantillons</h3><table><tr><th>Éch.</th><th>Étape</th><th>Moment</th><th>Volume</th><th>N° Scirius</th><th>N° Aramis</th><th>Laboratoire</th><th>Analyses</th></tr>"
              + "".join(f"<tr><td>{e(x.id)}</td><td>{e(x.etape)}</td><td>{e(x.moment)}</td><td>{fmt_vol(x.volume or 0)} mL</td><td>{td(x.scirius)}</td>"
                        f"<td>{td(x.aramis)}</td><td>{e(x.labo)}</td><td>{e(', '.join(x.analyses))}</td></tr>" for x in r.echantillons) + "</table>")
    tj = ""
    if m.lancee:
        tj = "<h3>Modifications après lancement</h3>" + (
            "<table><tr><th>Date et heure</th><th>Par</th><th>Modification</th></tr>"
            + "".join(f"<tr><td>{fmt_dt(j.t)}</td><td>{e(j.par)}</td><td>{e(j.txt)}</td></tr>" for j in m.journal) + "</table>"
            if m.journal else "<p>Aucune modification depuis le lancement.</p>")
    phases = "<h3>Détail par phase du flux</h3>" + "".join(
        (f'<h4 style="margin:12px 0 2px;color:#0F6B5C">Grande étape : {e(ph.groupe)} ({e(ph.groupe_plage)})</h4>' if ph.debut_groupe else "")
        + f'<div class="c" style="margin:6px 0"><b>{e(ph.titre)}</b> <span class="p">{e(ph.conditions)}</span>'
        + (f'<div class="e">{e(", ".join(ph.materiel))}</div>' if ph.materiel else "")
        + (("<div><b>Réactifs</b> " + ("".join(
            f"<div>{e(x.nom)}{' · ' + e(x.quantite) if x.quantite else ''} — n° Scirius {td(x.scirius)}, emplacement {td(x.emplacement)}, "
            f"fournisseur {td(x.fournisseur)}, lot {td(x.lot)}</div>" for x in ph.reactifs) or "aucun") + "</div>") if ph.n else "")
        + "<div><b>Échantillons</b> " + ("".join(
            f'<div class="s"><b>{e(x.id)}</b> · {fmt_vol(x.volume or 0)} mL · {e(x.moment)} · {e(x.labo)} · {e(", ".join(x.analyses))} — '
            f"n° Scirius {td(x.scirius)}, n° Aramis {td(x.aramis)}</div>" for x in ph.echantillons) or "aucun") + "</div></div>"
        for ph in r.phases)
    corps = "".join(f"<h3>{e(s.titre)}</h3><p>{texte_html(s.texte)}</p>" for s in r.sections)
    lanc = ""
    if m.lancee:
        lanc = f" · <b>lancée le</b> {fmt_dt(m.lancee.le)} par {e(m.lancee.par)}"
        if m.journal:
            lanc += f' <b style="color:#8A4B00">· modifiée après lancement ({len(m.journal)})</b>'
    meta = (f"<b>Donneur d’ordre :</b> {e(c.donneur) or '<i>à saisir</i>'} &nbsp; "
            + (f"<b>Type :</b> {e(c.type)} &nbsp; " if c.type else "")
            + f"<b>Réf. demande :</b> {e(c.ref) or '<i>à saisir</i>'} &nbsp; <b>Date :</b> {e(c.date)}<br>"
            + f"<b>Version :</b> {m.rev} · enregistrée le {fmt_dt(m.maj)}{lanc}"
            + (f"<br><b>Tags :</b> {' '.join('#' + e(t) for t in m.tags)}" if m.tags else ""))
    return (f'<!DOCTYPE html><html lang="fr"><head><meta charset="utf-8"><title>{e(m.nom)}</title><style>\n{STYLE}</style></head>'
            f'<body><h1>{e(m.nom)}</h1><div class="meta">{meta}</div>\n'
            f'<h2>Flux de prétraitement</h2><div class="flow">{"".join(cartes)}</div><h2>Matériel et méthodes</h2>'
            f"{corps}{phases}{t1}{t2}{tj}"
            '<p style="color:#566360;font-size:11.5px;margin-top:24px">Document généré automatiquement - à relire avant diffusion</p>'
            "</body></html>")
