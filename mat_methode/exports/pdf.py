"""Export PDF avec le schéma du flux (§11, V13), à partir du JSON d'échange (`echange.exporter`).

Repris de `scripts/export_pdf_flux.py`, avec : hauteur des cartes adaptée au contenu (§14.6),
repères « à saisir » en ambre dans le texte, bandeau complet (type, tags, version, lancement).
"""
from __future__ import annotations

import math
import re
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.lib.utils import simpleSplit
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Flowable, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from mat_methode.domain.texte import fmt_dt, fmt_dur, fmt_num, fmt_vol
from mat_methode.exports.polices import trouver

TEAL, TEAL_L = colors.HexColor("#0F6B5C"), colors.HexColor("#E1F0EC")
INK, MUTED, LINE = colors.HexColor("#14201D"), colors.HexColor("#566360"), colors.HexColor("#BFCBC7")
AMBER, AMBER_L = colors.HexColor("#8A4B00"), colors.HexColor("#FDF1DC")
MANQUE = '<font color="#8A4B00"><b>à saisir</b></font>'

_POLICES: tuple[str, str] | None = None


def polices() -> tuple[str, str]:
    global _POLICES
    if _POLICES is None:
        paire = trouver()
        if paire:
            pdfmetrics.registerFont(TTFont("Corps", paire[0]))
            pdfmetrics.registerFont(TTFont("Corps-Bold", paire[1]))
            pdfmetrics.registerFontFamily("Corps", normal="Corps", bold="Corps-Bold", italic="Corps", boldItalic="Corps-Bold")
            _POLICES = ("Corps", "Corps-Bold")
        else:
            _POLICES = ("Helvetica", "Helvetica-Bold")
    return _POLICES


def conditions(p: dict) -> str:
    out = []
    if p.get("temperature_c") is not None:
        out.append(f"{fmt_num(p['temperature_c'])} °C")
    if p.get("duree_min") is not None:
        out.append(fmt_dur(p["duree_min"]))
    if p.get("agitation_trmin") is not None:
        out.append(f"{fmt_num(p['agitation_trmin'])} tr/min")
    if p.get("vide"):
        out.append("sous vide" + (f" {fmt_num(p['vide_mbar'])} mbar" if p.get("vide_mbar") else ""))
    if p.get("filtre_um") is not None:
        out.append(f"{fmt_num(p['filtre_um'])} µm")
    return " · ".join(out)


def code_badge(ident: str) -> str:
    mt = re.match(r"^\D*(\d+)(.*)$", ident)
    return (mt.group(2) or mt.group(1))[:2] if mt else ident[:2]


def moment_texte(p: dict) -> str:
    m = p.get("moment") or ("avant" if p["apres_etape"] == 0 else "effluent")
    if m == "avant" or p["apres_etape"] == 0:
        return "avant traitement"
    if m == "pendant":
        return f"pendant · à {fmt_dur(p['temps_min'])}" if p.get("temps_min") is not None else "pendant l’étape"
    return "effluent"


def titre_lignes(texte: str, largeur: float, police: str, taille=8.5, mini=6.5):
    """Réduit la police par pas de 0,5 pt si un mot est trop large, puis passe à la ligne entre les mots."""
    while taille > mini and any(stringWidth(m, police, taille) > largeur for m in texte.split()):
        taille -= 0.5
    mots = []
    for mot in texte.split():  # à la taille minimale, un mot encore trop large est coupé (avec un trait d'union)
        while stringWidth(mot, police, taille) > largeur and len(mot) > 2:
            k = len(mot) - 1
            while k > 1 and stringWidth(mot[:k] + "-", police, taille) > largeur:
                k -= 1
            mots.append(mot[:k] + "-")
            mot = mot[k:]
        mots.append(mot)
    lignes, cur = [], ""
    for mot in mots:
        test = (cur + " " + mot).strip()
        if cur and (cur.endswith("-") or stringWidth(test, police, taille) > largeur):
            lignes.append(cur)
            cur = mot
        else:
            cur = test
    return (lignes + [cur] if cur else lignes) or [texte], taille


def avec_reperes(texte: str) -> str:
    """Échappe et met les « [xxx à saisir] » en ambre."""
    return re.sub(r"\[([^\]]*) à saisir\]", lambda mt: f'<font color="#8A4B00"><b>[{mt.group(1)} à saisir]</b></font>', escape(texte))


class Flux(Flowable):
    """Cartes d'étapes reliées par des flèches ; badges sur la frise ; noms des échantillons sous les cartes."""

    PAR_LIGNE, GAP, CARTE_MIN, ESPACE, PAS, TETE = 5, 6 * mm, 40 * mm, 9 * mm, 9.6 * mm, 12 * mm

    def __init__(self, etapes, prelevements, largeur):
        super().__init__()
        self.font, self.fontb = polices()
        self.etapes, self.largeur = etapes, largeur
        self.carte_w = (largeur - (self.PAR_LIGNE - 1) * self.GAP) / self.PAR_LIGNE
        self.lignes = max(1, math.ceil(len(etapes) / self.PAR_LIGNE))
        self.par_apres: dict[int, list] = {}
        for p in prelevements:
            self.par_apres.setdefault(p["apres_etape"], []).append(p)
        self.contenus = [self._contenu(e) for e in etapes]
        self.bandes, self.h_cartes = [], []
        for r in range(self.lignes):
            grp = range(r * self.PAR_LIGNE, min(len(etapes), (r + 1) * self.PAR_LIGNE))
            self.bandes.append(max([len(self.par_apres.get(etapes[i]["n"], [])) for i in grp] + [0]))
            self.h_cartes.append(max([self.CARTE_MIN] + [self.contenus[i]["h"] for i in grp]))
        self.hauteurs = [hc + b * self.PAS + self.ESPACE for hc, b in zip(self.h_cartes, self.bandes)]
        self.haut = self.TETE + sum(self.hauteurs) + 4 * mm

    def _contenu(self, e: dict) -> dict:
        """Lignes de la carte ; la police des textes est réduite si la carte devient trop haute (§14.6)."""
        w = self.carte_w
        titre, taille_t = titre_lignes(e["operation"][:1].upper() + e["operation"][1:], w - 11 * mm, self.fontb)
        detail = e.get("reactifs_detail") or [{"nom": n, "quantite": ""} for n in e.get("reactifs", [])]
        cond = " · ".join(x for x in [conditions(e["parametres"])] + [f"{a['nom']} {a.get('valeur', '')}".strip() for a in e.get("autres", [])] if x)
        for echelle in (1.0, 0.9, 0.8):
            textes = [((r["nom"] + (" " + r["quantite"] if r.get("quantite") else "")), self.fontb, 7.5 * echelle, INK) for r in detail if r.get("nom")]
            textes.append((cond, self.font, 7.5 * echelle, TEAL))
            textes += [(eq, self.font, 7 * echelle, MUTED) for eq in e.get("equipement", [])]
            lignes = []
            for texte, police, taille, couleur in textes:
                if texte:
                    lignes += [(ln, police, taille, couleur) for ln in simpleSplit(texte, police, taille, w - 6 * mm)]
            frise = bool(e["parametres"].get("duree_min") or self.par_apres.get(e["n"]))
            h = 12 * mm + (len(titre) - 1) * (taille_t + 1.2) + sum(t + 1.6 for _, _, t, _ in lignes) + (11 * mm if frise else 3 * mm)
            if h <= 75 * mm:
                break
        return {"titre": titre, "taille_t": taille_t, "lignes": lignes, "h": h}

    def wrap(self, *_):
        return self.largeur, self.haut

    def badge(self, c, x, y, code):
        c.setFillColor(AMBER)
        c.circle(x, y, 1.9 * mm, stroke=0, fill=1)
        c.setFillColor(colors.white)
        c.setFont(self.fontb, 6)
        c.drawCentredString(x, y - 0.75 * mm, code)

    def pastille(self, c, x, y, ligne1, ligne2="", code=None):
        decal = 6 * mm if code else 2 * mm
        w = max(stringWidth(ligne1, self.fontb, 7), stringWidth(ligne2, self.font, 6.3)) + decal + 2 * mm
        c.setFillColor(AMBER_L)
        c.setStrokeColor(AMBER)
        c.setLineWidth(0.8)
        c.roundRect(x, y, w, 8 * mm, 1.6 * mm, stroke=1, fill=1)
        if code:
            self.badge(c, x + 3.2 * mm, y + 4 * mm, code)
        c.setFillColor(AMBER)
        c.setFont(self.fontb, 7)
        c.drawString(x + decal, y + 4.7 * mm, ligne1)
        c.setFont(self.font, 6.3)
        c.drawString(x + decal, y + 1.7 * mm, ligne2)
        return w

    def fleche(self, c, points, sens):
        c.setStrokeColor(MUTED)
        c.setFillColor(MUTED)
        c.setLineWidth(1)
        p = c.beginPath()
        p.moveTo(*points[0])
        for pt in points[1:]:
            p.lineTo(*pt)
        c.drawPath(p, stroke=1, fill=0)
        x2, y2 = points[-1]
        a = 1.4 * mm
        t = c.beginPath()
        if sens == "droite":
            t.moveTo(x2, y2); t.lineTo(x2 - 2 * a, y2 + a); t.lineTo(x2 - 2 * a, y2 - a)
        else:
            t.moveTo(x2, y2); t.lineTo(x2 - a, y2 + 2 * a); t.lineTo(x2 + a, y2 + 2 * a)
        t.close()
        c.drawPath(t, stroke=0, fill=1)

    def etiquette(self, p):
        return f"{p['id']} · {fmt_vol(p['volume_ml'] or 0)} mL", moment_texte(p), code_badge(p["id"])

    def draw(self):
        c, w = self.canv, self.carte_w
        c.setFont(self.fontb, 7.5)
        c.setFillColor(MUTED)
        c.drawString(0, self.haut - 4 * mm, "ENTRÉE")
        x = stringWidth("ENTRÉE", self.fontb, 7.5) + 3 * mm
        for pre in self.par_apres.get(0, []):
            x += self.pastille(c, x, self.haut - self.TETE + 1.2 * mm, *self.etiquette(pre)) + 1.5 * mm

        positions = []
        for i, e in enumerate(self.etapes):
            r, k = divmod(i, self.PAR_LIGNE)
            h = self.h_cartes[r]
            cx = k * (w + self.GAP)
            cy = self.haut - self.TETE - sum(self.hauteurs[:r]) - h
            positions.append((cx, cy, r, h))
            ct = self.contenus[i]
            c.setFillColor(colors.white)
            c.setStrokeColor(LINE)
            c.setLineWidth(1)
            c.roundRect(cx, cy, w, h, 2.5 * mm, stroke=1, fill=1)
            c.setFillColor(TEAL)
            c.circle(cx + 4.6 * mm, cy + h - 5 * mm, 3 * mm, stroke=0, fill=1)
            c.setFillColor(colors.white)
            c.setFont(self.fontb, 7.5)
            c.drawCentredString(cx + 4.6 * mm, cy + h - 6.2 * mm, str(e["n"]))
            c.setFillColor(INK)
            for k_l, ligne in enumerate(ct["titre"]):
                c.setFont(self.fontb, ct["taille_t"])
                c.drawString(cx + 9 * mm, cy + h - 6 * mm - k_l * (ct["taille_t"] + 1.2), ligne)
            y = cy + h - 12 * mm - (len(ct["titre"]) - 1) * (ct["taille_t"] + 1.2)
            for ligne, police, taille, couleur in ct["lignes"]:
                c.setFont(police, taille)
                c.setFillColor(couleur)
                c.drawString(cx + 3 * mm, y, ligne)
                y -= taille + 1.6
            dur = e["parametres"].get("duree_min")
            prels = self.par_apres.get(e["n"], [])
            if dur or prels:
                x0, x1, yb = cx + 3 * mm, cx + w - 3 * mm, cy + 6 * mm
                c.setStrokeColor(LINE)
                c.setLineWidth(1.6)
                c.line(x0, yb, x1, yb)
                c.setFillColor(MUTED)
                c.setFont(self.font, 6)
                c.drawString(x0, yb - 4.2 * mm, "0")
                c.drawRightString(x1, yb - 4.2 * mm, fmt_dur(dur) if dur else "fin")
                for pre in prels:
                    mo = pre.get("moment", "effluent")
                    if mo == "pendant" and dur and pre.get("temps_min") is not None:
                        xm = x0 + (x1 - x0) * max(0.0, min(1.0, pre["temps_min"] / dur))
                    elif mo == "pendant":
                        xm = (x0 + x1) / 2
                    else:
                        xm = x1
                    self.badge(c, xm, yb, code_badge(pre["id"]))
            for j, pre in enumerate(prels):
                self.pastille(c, cx, cy - (j + 1) * self.PAS, *self.etiquette(pre))

        for i in range(len(self.etapes) - 1):
            (x1, y1, r1, h1), (x2, y2, r2, h2) = positions[i], positions[i + 1]
            if r1 == r2:
                ym = y1 + h1 - 5 * mm
                self.fleche(c, [(x1 + w + 0.8 * mm, ym), (x2 - 0.4 * mm, ym)], "droite")
            else:
                xa, xb = x1 + w - 3 * mm, x2 + w - 3 * mm
                bas = y1 - self.bandes[r1] * self.PAS
                ym = bas - self.ESPACE / 2
                self.fleche(c, [(xa, y1 if self.bandes[r1] == 0 else bas), (xa, ym), (xb, ym), (xb, y2 + h2 + 0.4 * mm)], "bas")

        c.setFont(self.fontb, 7.5)
        c.setFillColor(MUTED)
        c.drawRightString(self.largeur, 1.5 * mm, "SORTIE · produit prétraité")


def _ou(v):
    return escape(str(v)) if v not in (None, "") else MANQUE


def blocs_phases(data: dict, corps) -> list:
    """Une fiche par phase (jamais coupée entre deux pages)."""
    petit = ParagraphStyle("ph", parent=corps, fontSize=8.5, leading=11.5)
    blocs = []
    for i, ph in enumerate(data.get("phases", [])):
        if i == 0:
            ctx = data.get("contexte", {})
            sous = escape(f"{ctx.get('matiere') or ''}") + f" (lot {_ou(ctx.get('lot'))})" + (
                f" · {fmt_vol(ctx['volumeDepart'])} mL" if ctx.get("volumeDepart") is not None else "")
        else:
            sous = escape(ph.get("conditions") or "conditions à compléter") + (
                f"<br/><font color='#566360'>{escape(', '.join(ph['materiel']))}</font>" if ph.get("materiel") else "")
        lignes = [[Paragraph(f"<b>{escape(ph['titre'])}</b>", petit), Paragraph(sous, petit)]]
        if i:
            txt = "<br/>".join(
                f"<b>{escape(r['nom'])}</b>{' · ' + escape(r['quantite']) if r.get('quantite') else ''}"
                f"<br/><font color='#566360'>n° Scirius</font> {_ou(r.get('scirius'))} · <font color='#566360'>emplacement</font> {_ou(r.get('emplacement'))} · "
                f"<font color='#566360'>fournisseur</font> {_ou(r.get('fournisseur'))} · <font color='#566360'>lot</font> {_ou(r.get('lot'))}"
                for r in ph["reactifs"]) or "aucun"
            lignes.append([Paragraph("Réactifs", petit), Paragraph(txt, petit)])
        txt = "<br/>".join(
            f"<b>{escape(x['id'])}</b> · {fmt_vol(x['volume'] or 0)} mL · {escape(x['moment'])} · {escape(x.get('labo') or '')}"
            f" · {escape(', '.join(x.get('analyses', [])) or 'aucune analyse')}"
            f"<br/><font color='#566360'>n° Scirius</font> {_ou(x.get('scirius'))} · <font color='#566360'>n° Aramis</font> {_ou(x.get('aramis'))}"
            for x in ph["echantillons"]) or "aucun"
        lignes.append([Paragraph("Échantillons", petit), Paragraph(txt, petit)])
        t = Table(lignes, colWidths=[34 * mm, 140 * mm])
        t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, LINE), ("BACKGROUND", (0, 0), (-1, 0), TEAL_L),
                               ("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
        blocs.append(KeepTogether([t, Spacer(1, 2.5 * mm)]))
    return blocs


def ecrire_pdf(data: dict, chemin) -> None:
    font, fontb = polices()
    ctx, etapes, pre = data.get("contexte", {}), data["etapes"], data.get("prelevements", [])
    titre = data.get("titre") or "Manip"
    st = getSampleStyleSheet()
    corps = ParagraphStyle("corps", parent=st["Normal"], fontName=font, fontSize=9.5, leading=14, textColor=INK)
    petit = ParagraphStyle("petit", parent=corps, fontSize=8, leading=11, textColor=MUTED)
    h1 = ParagraphStyle("h1", parent=st["Title"], fontName=fontb, fontSize=18, alignment=0, textColor=INK, spaceAfter=4)
    h2 = ParagraphStyle("h2", parent=st["Heading2"], fontName=fontb, fontSize=12, textColor=TEAL, spaceBefore=10, spaceAfter=5)
    h3 = ParagraphStyle("h3", parent=corps, fontName=fontb, spaceBefore=5, spaceAfter=2)
    cell = ParagraphStyle("c", parent=corps, fontSize=8.5, leading=11)
    cellb = ParagraphStyle("cb", parent=cell, fontName=fontb)

    def pied(canvas, doc):
        canvas.saveState()
        canvas.setFont(font, 7.5)
        canvas.setFillColor(MUTED)
        canvas.drawString(18 * mm, 10 * mm, "Document généré automatiquement - à relire avant diffusion")
        canvas.drawRightString(192 * mm, 10 * mm, f"Mat & Méthode · page {doc.page}")
        canvas.restoreState()

    doc = SimpleDocTemplate(str(chemin), pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=16 * mm, bottomMargin=18 * mm, title=titre, author="Mat & Méthode")
    largeur = A4[0] - 36 * mm - 12
    story = [Paragraph(escape(titre), h1)]

    lanc, jr = data.get("lancee"), data.get("journal") or []
    meta = [[("Donneur d’ordre", _ou(ctx.get("donneur"))), ("Réf. demande", _ou(ctx.get("ref")))],
            [("Type", escape(ctx.get("type") or "-")), ("Date", escape(ctx.get("date") or "-"))]]
    if ctx.get("tags"):
        meta.append([("Tags", escape("  ".join("#" + t for t in ctx["tags"]))), ("", "")])
    ver = f"{data.get('version', 1)} · enregistrée le {fmt_dt(data.get('enregistree_le'))}"
    if lanc:
        ver += f" · lancée le {fmt_dt(lanc.get('le'))} par {lanc.get('par', '')}"
    ligne_v = escape(ver) + (f' <font color="#8A4B00"><b>· Modifiée après lancement ({len(jr)})</b></font>' if lanc and jr else "")
    rows = [[Paragraph(f"<b>{a}</b>", corps), Paragraph(b, corps), Paragraph(f"<b>{c}</b>", corps), Paragraph(d, corps)] for (a, b), (c, d) in meta]
    rows.append([Paragraph("<b>Version</b>", corps), Paragraph(ligne_v, corps), "", ""])
    t = Table(rows, colWidths=[32 * mm, 62 * mm, 28 * mm, 52 * mm])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), TEAL_L), ("BOX", (0, 0), (-1, -1), 0.5, LINE), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                           ("SPAN", (1, len(rows) - 1), (3, len(rows) - 1)),
                           ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]
                          + ([("SPAN", (1, 2), (3, 2))] if ctx.get("tags") else [])))
    story += [t, Paragraph("Flux de prétraitement", h2), Flux(etapes, pre, largeur), Spacer(1, 3 * mm)]

    total = sum(e["parametres"].get("duree_min") or 0 for e in etapes)
    legende = (f"Durée cumulée des étapes chronométrées : {fmt_dur(total)}. Chaque prélèvement a un badge : dans la carte de l’étape, "
               "posé à son moment sur la frise (à l’extrémité droite pour un prélèvement à l’effluent), et sous la carte avec son nom, son volume et son moment.")
    vd = ctx.get("volumeDepart")
    if vd is not None:
        pris = sum(p["volume_ml"] or 0 for p in pre)
        reste = vd - pris
        legende += (f" Volume : {fmt_vol(vd)} mL au départ, {fmt_vol(pris)} mL prélevés, "
                    + (f"{fmt_vol(reste)} mL restants." if reste >= 0 else f"dépassement de {fmt_vol(-reste)} mL."))
    story.append(Paragraph(escape(legende), petit))

    story.append(Paragraph("Matériel et méthodes", h2))
    for b in data.get("sous_sections", []):
        if b.get("texte"):
            story += [Paragraph(escape(b["titre"]), h3), Paragraph(avec_reperes(b["texte"]), corps)]

    story.append(Paragraph("Détail par phase du flux", h2))
    story += blocs_phases(data, corps)

    inv = {r["nom"].lower(): r for r in data.get("inventaire_reactifs", [])}
    noms: list[tuple[str, list[str]]] = []
    for e in etapes:
        for r in e.get("reactifs_detail") or [{"nom": n} for n in e.get("reactifs", [])]:
            if not r.get("nom"):
                continue
            x = next((y for y in noms if y[0].lower() == r["nom"].lower()), None)
            if x is None:
                x = (r["nom"], [])
                noms.append(x)
            if str(e["n"]) not in x[1]:
                x[1].append(str(e["n"]))
    if noms:
        lignes = [[Paragraph(h, cellb) for h in ["Réactif", "N° Scirius", "Emplacement", "Fournisseur", "Lot", "Étape"]]]
        for nom, ns in noms:
            f = inv.get(nom.lower(), {})
            lignes.append([Paragraph(f"<b>{escape(nom)}</b>", cell)] + [Paragraph(_ou(f.get(k)), cell) for k in ("scirius", "emplacement", "fournisseur", "lot")]
                          + [Paragraph(", ".join(ns), cell)])
        tab = Table(lignes, colWidths=[30 * mm, 22 * mm, 52 * mm, 30 * mm, 20 * mm, 20 * mm], repeatRows=1)
        tab.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, LINE), ("BACKGROUND", (0, 0), (-1, 0), TEAL_L), ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
        story.append(KeepTogether([Paragraph("Réactifs", h2), tab]))

    if pre:
        lignes = [[Paragraph(h, cellb) for h in ["Éch.", "Étape", "Moment", "Volume", "N° Scirius", "N° Aramis", "Laboratoire", "Analyses"]]]
        for p in pre:
            etape = "entrée" if p["apres_etape"] == 0 else f"{p['apres_etape']} · {etapes[p['apres_etape'] - 1]['operation']}"
            lignes.append([Paragraph(f"<b>{escape(p['id'])}</b>", cell), Paragraph(escape(etape), cell), Paragraph(escape(moment_texte(p)), cell),
                           Paragraph(f"{fmt_vol(p['volume_ml'] or 0)} mL", cell), Paragraph(_ou(p.get("scirius")), cell),
                           Paragraph(_ou(p.get("aramis")), cell), Paragraph(escape(p.get("labo") or ""), cell),
                           Paragraph(escape(", ".join(p.get("analyses", []))), cell)])
        tab = Table(lignes, colWidths=[12 * mm, 28 * mm, 26 * mm, 17 * mm, 19 * mm, 19 * mm, 22 * mm, 31 * mm], repeatRows=1)
        tab.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, LINE), ("BACKGROUND", (0, 0), (-1, 0), TEAL_L), ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
        story.append(KeepTogether([Paragraph("Échantillons", h2), tab]))

    if lanc:
        story.append(Paragraph("Modifications après lancement", h2))
        if jr:
            lignes = [[Paragraph("<b>Date et heure</b>", cell), Paragraph("<b>Par</b>", cell), Paragraph("<b>Modification</b>", cell)]]
            lignes += [[Paragraph(fmt_dt(j["t"]), cell), Paragraph(escape(j["par"]), cell), Paragraph(escape(j["txt"]), cell)] for j in jr]
            tj = Table(lignes, colWidths=[36 * mm, 24 * mm, 114 * mm], repeatRows=1)
            tj.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), TEAL_L), ("GRID", (0, 0), (-1, -1), 0.4, LINE), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
            story.append(tj)
        else:
            story.append(Paragraph("Aucune modification depuis le lancement.", corps))
    doc.build(story, onFirstPage=pied, onLaterPages=pied)
