"""PDF « Protocole » : document de paillasse, à emporter pendant la manip.

Contenu : le titre « Protocole : <nom de la manip> », le cartouche du rapport, le contexte (2.1), le schéma du flux,
les réactifs, puis le détail du flux par phase ; chaque phase porte le tableau de ses échantillons, avec des cases
vides pour noter à la main les numéros (Scirius, Aramis) et l'heure réelle du prélèvement, et une case Observations.
Construit à partir du même JSON d'échange que le rapport.
"""
from __future__ import annotations

from xml.sax.saxutils import escape

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import KeepTogether, Paragraph, Spacer, Table, TableStyle

from mat_methode.domain.texte import fmt_vol
from mat_methode.exports.pdf import (
    LINE,
    TEAL_L,
    Flux,
    avec_reperes,
    cartouche,
    document,
    legende_flux,
    moment_texte,
    styles,
    table_reactifs,
)


def _case(texte: str | None, cell) -> Paragraph:
    """Valeur déjà connue, sinon case vide à remplir à la main."""
    return Paragraph(f"<b>{escape(texte)}</b>" if texte else "", cell)


def phases_a_remplir(data: dict, s: dict) -> list:
    """Une fiche par phase (Départ, puis chaque étape), jamais coupée entre deux pages."""
    cell, cellb, petit = s["cell"], s["cellb"], s["petit"]
    blocs = []
    pre = data.get("prelevements", [])
    ctx = data.get("contexte", {})
    for i, ph in enumerate(data.get("phases", [])):
        n = 0 if i == 0 else data["etapes"][i - 1]["n"]
        titre = (f"<font size='7' color='#0F6B5C'><b>{escape(ph['groupe'].upper())}</b></font><br/>" if ph.get("groupe") else "") + \
            f"<b>{escape(ph['titre'])}</b>"
        if i == 0:
            info = escape(ctx.get("matiere") or "") + (f" · lot {escape(ctx['lot'])}" if ctx.get("lot") else " · lot : ……………") + (
                f" · n° Scirius {escape(ctx['scirius'])}" if ctx.get("scirius") else "") + (
                f" · {fmt_vol(ctx['volumeDepart'])} mL" if ctx.get("volumeDepart") is not None else "")
        else:
            info = escape(ph.get("conditions") or "conditions à compléter") + (
                f"<br/><font color='#566360'>Matériel : {escape(', '.join(ph['materiel']))}</font>" if ph.get("materiel") else "")
            if ph.get("reactifs"):
                info += "<br/>" + "<br/>".join(
                    f"<b>{escape(r['nom'])}</b>{' · ' + escape(r['quantite']) if r.get('quantite') else ''}"
                    + (f" · n° Scirius {escape(r['scirius'])}" if r.get("scirius") else "")
                    + (f" · {escape(r['emplacement'])}" if r.get("emplacement") else "") for r in ph["reactifs"])
        tete = Table([[Paragraph(titre, cell), Paragraph(info, cell)]], colWidths=[40 * mm, 134 * mm])
        tete.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), TEAL_L), ("BOX", (0, 0), (-1, -1), 0.5, LINE),
                                  ("VALIGN", (0, 0), (-1, -1), "TOP")]))
        contenu = [tete]
        ps = [p for p in pre if p["apres_etape"] == n]
        if ps:
            lignes = [[Paragraph(h, cellb) for h in ["Éch.", "Volume · moment", "Labo · analyses", "N° Scirius", "N° Aramis", "Heure réelle"]]]
            for p in ps:
                lignes.append([Paragraph(f"<b>{escape(p['id'])}</b>", cell),
                               Paragraph(f"{fmt_vol(p['volume_ml'] or 0)} mL<br/>{escape(moment_texte(p))}"
                                         + (f"<br/><i>{escape(p['commentaire'])}</i>" if p.get("commentaire") else ""), cell),
                               Paragraph(f"{escape(p.get('labo') or '')}<br/><font color='#566360'>{escape(', '.join(p.get('analyses', [])))}</font>", cell),
                               _case(p.get("scirius"), cell), _case(p.get("aramis"), cell), Paragraph("", cell)])
            t = Table(lignes, colWidths=[13 * mm, 30 * mm, 50 * mm, 27 * mm, 27 * mm, 27 * mm], repeatRows=1)
            t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, LINE), ("BACKGROUND", (0, 0), (-1, 0), TEAL_L),
                                   ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                                   ("TOPPADDING", (0, 1), (-1, -1), 9), ("BOTTOMPADDING", (0, 1), (-1, -1), 9)]))
            contenu.append(t)
        else:
            contenu.append(Paragraph("Aucun prélèvement prévu.", petit))
        obs = Table([[Paragraph("<font color='#566360'>Observations :</font>", cell)]], colWidths=[174 * mm], rowHeights=[14 * mm])
        obs.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.5, LINE), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
        contenu += [obs, Spacer(1, 4 * mm)]
        blocs.append(KeepTogether(contenu))
    return blocs


def ecrire_protocole(data: dict, chemin) -> None:
    s = styles()
    h1, h2, corps, petit = s["h1"], s["h2"], s["corps"], s["petit"]
    titre = data.get("titre") or "Manip"
    doc, pied = document(chemin, f"Protocole : {titre}", "Protocole - à compléter à la main pendant la manip")
    largeur = A4[0] - 36 * mm - 12
    story = [Paragraph(f"Protocole : {escape(titre)}", h1), cartouche(data, s)]
    contexte = next((b for b in data.get("sous_sections", []) if b.get("titre", "").startswith("2.1")), None)
    if contexte:
        story.append(Paragraph("Contexte", h2))
        story += [Paragraph(avec_reperes(x.replace(", décrites en 2.3", "")), corps) for x in contexte["texte"].split("\n") if x]
    story += [Paragraph("Flux de prétraitement", h2), Flux(data["etapes"], data.get("prelevements", []), largeur),
              Spacer(1, 3 * mm), Paragraph(escape(legende_flux(data)), petit)]
    tab = table_reactifs(data, s)
    if tab is not None:
        story.append(KeepTogether([Paragraph("Réactifs", h2), tab]))
    story.append(Paragraph("Détail du flux par phase", h2))
    story.append(Paragraph("Pour chaque phase : ses échantillons (cases vides : numéros et heure réelle à noter à la main) et les observations.", petit))
    story += phases_a_remplir(data, s)
    doc.build(story, onFirstPage=pied, onLaterPages=pied)


__all__ = ["ecrire_protocole"]
