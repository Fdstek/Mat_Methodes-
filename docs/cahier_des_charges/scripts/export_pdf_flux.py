"""Exporte une manip en PDF : schéma de flux + texte « Matériel et méthodes » + échantillons.

Usage :
  python3 export_pdf_flux.py mm_extrait.json --prelevements prelevements_exemple.json \
      --donneur "Interne - R&D" --ref DA-2026-0158 --volume-depart 1000 --out manip_flux.pdf

Entrée : le JSON produit par extract_mm.py (clés "etapes" et "sous_sections").
"""
import argparse
import json
import math
import re
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.lib.utils import simpleSplit
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.platypus import Flowable, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

import os

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# Police TrueType (pour afficher µ, °, accents) : première paire trouvée, sinon Helvetica.
POLICES = [
    ("C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/segoeuib.ttf"),  # Windows 11 : Segoe UI
    ("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf", "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"),
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    ("C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/arialbd.ttf"),
    ("/Library/Fonts/Arial.ttf", "/Library/Fonts/Arial Bold.ttf"),
]
FONT, FONTB = "Helvetica", "Helvetica-Bold"
for _normal, _gras in POLICES:
    if os.path.exists(_normal) and os.path.exists(_gras):
        pdfmetrics.registerFont(TTFont("Corps", _normal))
        pdfmetrics.registerFont(TTFont("Corps-Bold", _gras))
        pdfmetrics.registerFontFamily("Corps", normal="Corps", bold="Corps-Bold")
        FONT, FONTB = "Corps", "Corps-Bold"
        break

TEAL, TEAL_L = colors.HexColor("#0F6B5C"), colors.HexColor("#E1F0EC")
INK, MUTED, LINE = colors.HexColor("#14201D"), colors.HexColor("#566360"), colors.HexColor("#BFCBC7")
AMBER, AMBER_L = colors.HexColor("#8A4B00"), colors.HexColor("#FDF1DC")


def vol(v):
    return f"{v:,.0f}".replace(",", " ")


def duree(minutes):
    h, m = divmod(int(round(minutes)), 60)
    if h and m:
        return f"{h} h {m:02d}"
    return f"{h} h" if h else f"{m} min"


def lignes_parametres(p):
    morceaux = []
    if "temperature_c" in p:
        morceaux.append(f"{p['temperature_c']:g} °C")
    if "duree_min" in p:
        morceaux.append(duree(p["duree_min"]))
    if "agitation_trmin" in p:
        morceaux.append(f"{p['agitation_trmin']} tr/min")
    if "ratio" in p:
        morceaux.append(f"ratio {p['ratio']}")
    if p.get("vide"):
        morceaux.append("sous vide" + (f" {p['vide_mbar']:g} mbar" if p.get("vide_mbar") else ""))
    if "filtre_um" in p:
        morceaux.append(f"{p['filtre_um']:g} µm")
    return " · ".join(morceaux)


def code_echantillon(ident):
    """Texte du badge : suffixe de l'identifiant (S2a -> a), sinon son numéro (S0 -> 0)."""
    m = re.match(r"^\D*(\d+)(.*)$", ident)
    return (m.group(2) or m.group(1))[:2] if m else ident[:2]


def moment_texte(p):
    """Moment du prélèvement : avant traitement, pendant la réaction (à t min) ou à l'effluent."""
    m = p.get("moment") or ("avant" if p["apres_etape"] == 0 else "effluent")
    if m == "avant":
        return "avant traitement"
    if m == "pendant":
        return f"pendant · à {duree(p['temps_min'])}" if p.get("temps_min") is not None else "pendant la réaction"
    return "effluent"


def fmt_dt(iso):
    """2026-10-30T21:10:00Z -> 30/10/2026 à 22:10 (heure locale)."""
    from datetime import datetime
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone().strftime("%d/%m/%Y à %H:%M")
    except Exception:
        return str(iso or "")


def titre_lignes(texte, largeur, taille=8.5, mini=6.5):
    """Titre d'étape : réduit un peu la police si un mot est trop large, puis passe à la ligne entre les mots."""
    while taille > mini and any(stringWidth(m, FONTB, taille) > largeur for m in texte.split()):
        taille -= 0.5
    lignes, cur = [], ""
    for mot in texte.split():
        test = (cur + " " + mot).strip()
        if cur and stringWidth(test, FONTB, taille) > largeur:
            lignes.append(cur)
            cur = mot
        else:
            cur = test
    return (lignes + [cur] if cur else lignes) or [texte], taille


class Flux(Flowable):
    """Cartes d'étapes reliées par des flèches ; pastilles ambre sous la carte = prélèvements
    (autant que nécessaire par étape)."""

    PAR_LIGNE, GAP, CARTE_H, ESPACE, PAS, TETE = 5, 6 * mm, 40 * mm, 9 * mm, 9.6 * mm, 12 * mm

    def __init__(self, etapes, prelevements, largeur):
        super().__init__()
        self.etapes, self.largeur = etapes, largeur
        self.carte_w = (largeur - (self.PAR_LIGNE - 1) * self.GAP) / self.PAR_LIGNE
        self.lignes = max(1, math.ceil(len(etapes) / self.PAR_LIGNE))
        self.par_apres = {}
        for p in prelevements:
            self.par_apres.setdefault(p["apres_etape"], []).append(p)
        self.bandes = []  # nombre maximal de pastilles sous une carte, pour chaque ligne
        for r in range(self.lignes):
            ns = [e["n"] for e in etapes[r * self.PAR_LIGNE:(r + 1) * self.PAR_LIGNE]]
            self.bandes.append(max([len(self.par_apres.get(n, [])) for n in ns] + [0]))
        self.hauteurs = [self.CARTE_H + b * self.PAS + self.ESPACE for b in self.bandes]
        self.haut = self.TETE + sum(self.hauteurs) + 4 * mm

    def wrap(self, *_):
        return self.largeur, self.haut

    def badge(self, c, x, y, code):
        """Logo de l'échantillon : rond ambre foncé avec son code (a, b, 0, 1...)."""
        c.setFillColor(AMBER)
        c.circle(x, y, 1.9 * mm, stroke=0, fill=1)
        c.setFillColor(colors.white)
        c.setFont(FONTB, 6)
        c.drawCentredString(x, y - 0.75 * mm, code)

    def pastille(self, c, x, y, ligne1, ligne2="", code=None):
        """Nom de l'échantillon sous la carte : badge + (échantillon · volume) / moment."""
        decal = 6 * mm if code else 2 * mm
        w = max(stringWidth(ligne1, FONTB, 7), stringWidth(ligne2, FONT, 6.3)) + decal + 2 * mm
        c.setFillColor(AMBER_L)
        c.setStrokeColor(AMBER)
        c.setLineWidth(0.8)
        c.roundRect(x, y, w, 8 * mm, 1.6 * mm, stroke=1, fill=1)
        if code:
            self.badge(c, x + 3.2 * mm, y + 4 * mm, code)
        c.setFillColor(AMBER)
        c.setFont(FONTB, 7)
        c.drawString(x + decal, y + 4.7 * mm, ligne1)
        c.setFont(FONT, 6.3)
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
        return f"{p['id']} · {p['volume_ml']:g} mL", moment_texte(p), code_echantillon(p["id"])

    def draw(self):
        c, w, h = self.canv, self.carte_w, self.CARTE_H

        # Entrée (prélèvements avant traitement, en ligne)
        c.setFont(FONTB, 7.5)
        c.setFillColor(MUTED)
        c.drawString(0, self.haut - 4 * mm, "ENTRÉE")
        x = stringWidth("ENTRÉE", FONTB, 7.5) + 3 * mm
        for pre in self.par_apres.get(0, []):
            x += self.pastille(c, x, self.haut - self.TETE + 1.2 * mm, *self.etiquette(pre)) + 1.5 * mm

        positions = []
        for i, e in enumerate(self.etapes):
            r, k = divmod(i, self.PAR_LIGNE)
            cx = k * (w + self.GAP)
            cy = self.haut - self.TETE - sum(self.hauteurs[:r]) - h
            positions.append((cx, cy, r))
            c.setFillColor(colors.white)
            c.setStrokeColor(LINE)
            c.setLineWidth(1)
            c.roundRect(cx, cy, w, h, 2.5 * mm, stroke=1, fill=1)
            c.setFillColor(TEAL)
            c.circle(cx + 4.6 * mm, cy + h - 5 * mm, 3 * mm, stroke=0, fill=1)
            c.setFillColor(colors.white)
            c.setFont(FONTB, 7.5)
            c.drawCentredString(cx + 4.6 * mm, cy + h - 6.2 * mm, str(e["n"]))
            c.setFillColor(INK)
            titre, taille_t = titre_lignes(e["operation"].capitalize(), w - 11 * mm)
            for k_l, ligne in enumerate(titre):
                c.setFont(FONTB, taille_t)
                c.drawString(cx + 9 * mm, cy + h - 6 * mm - k_l * (taille_t + 1.2), ligne)
            y = cy + h - 12 * mm - (len(titre) - 1) * (taille_t + 1.2)
            reactifs = e.get("reactifs") or ([e["reactif"]] if e.get("reactif") else [])
            textes = [(r, FONTB, 7.5, INK) for r in reactifs] + [(lignes_parametres(e["parametres"]), FONT, 7.5, TEAL)]
            for eq in e.get("equipement", []):
                textes.append((eq, FONT, 7, MUTED))
            for texte, police, taille, couleur in textes:
                if not texte:
                    continue
                for ligne in simpleSplit(texte, police, taille, w - 6 * mm):
                    c.setFont(police, taille)
                    c.setFillColor(couleur)
                    c.drawString(cx + 3 * mm, y, ligne)
                    y -= taille + 1.6
            # frise de l'étape : 0 -> durée ; le badge d'un échantillon est posé à son moment
            # (extrémité droite = effluent). Son nom est écrit sous la carte.
            dur = e["parametres"].get("duree_min")
            prels = self.par_apres.get(e["n"], [])
            if dur or prels:  # une étape sans durée connue a quand même sa frise si elle a des prélèvements
                x0, x1, yb = cx + 3 * mm, cx + w - 3 * mm, cy + 6 * mm
                c.setStrokeColor(LINE)
                c.setLineWidth(1.6)
                c.line(x0, yb, x1, yb)
                c.setFillColor(MUTED)
                c.setFont(FONT, 6)
                c.drawString(x0, yb - 4.2 * mm, "0")
                c.drawRightString(x1, yb - 4.2 * mm, duree(dur) if dur else "fin")
                for pre in prels:
                    m = pre.get("moment", "effluent")
                    if m == "pendant" and dur and pre.get("temps_min") is not None and pre["temps_min"] <= dur:
                        xm = x0 + (x1 - x0) * pre["temps_min"] / dur
                    elif m == "pendant":
                        xm = (x0 + x1) / 2  # temps inconnu : badge au milieu
                    elif m == "effluent":
                        xm = x1
                    else:
                        continue
                    self.badge(c, xm, yb, code_echantillon(pre["id"]))
            # prélèvements après cette étape : une pastille par échantillon, empilées sous la carte
            for j, pre in enumerate(self.par_apres.get(e["n"], [])):
                self.pastille(c, cx, cy - (j + 1) * self.PAS, *self.etiquette(pre))

        # Flèches
        for i in range(len(self.etapes) - 1):
            (x1, y1, r1), (x2, y2, r2) = positions[i], positions[i + 1]
            if r1 == r2:
                ym = y1 + h / 2
                self.fleche(c, [(x1 + w + 0.8 * mm, ym), (x2 - 0.4 * mm, ym)], "droite")
            else:  # retour à la ligne : on descend à droite de la pile de pastilles
                xa, xb = x1 + w - 3 * mm, x2 + w - 3 * mm
                bas = y1 - self.bandes[r1] * self.PAS
                ym = bas - self.ESPACE / 2
                self.fleche(c, [(xa, y1 if self.bandes[r1] == 0 else bas), (xa, ym), (xb, ym), (xb, y2 + h + 0.4 * mm)], "bas")

        c.setFont(FONTB, 7.5)
        c.setFillColor(MUTED)
        c.drawRightString(self.largeur, 1.5 * mm, "SORTIE · produit prétraité")


def blocs_phases(etapes, pre, inventaire_data, corps):
    """Une fiche par phase du flux : conditions, réactifs (n° Scirius, emplacement...) et échantillons."""
    inv = {r["nom"].lower(): r for r in (inventaire_data or [])}
    manque = '<font color="#8A4B00">à saisir</font>'
    petit = ParagraphStyle("ph", parent=corps, fontSize=8.5, leading=11.5)
    ou = lambda v: escape(str(v)) if v else manque
    phases = [(0, "Départ", "", [], [])]
    for e in etapes:
        detail = e.get("reactifs_detail") or [{"nom": n, "quantite": ""} for n in e.get("reactifs", [])]
        phases.append((e["n"], f"{e['n']} · {e['operation'].capitalize()}", lignes_parametres(e["parametres"]), e.get("equipement", []), detail))
    blocs = []
    for n, titre, cond, equip, reacs in phases:
        lignes = [[Paragraph(f"<b>{escape(titre)}</b>", petit),
                   Paragraph(escape(cond) + (f"<br/><font color='#566360'>{escape(', '.join(equip))}</font>" if equip else ""), petit)]]
        if n:
            txt = "<br/>".join(
                f"<b>{escape(r['nom'])}</b>{' · ' + escape(r['quantite']) if r.get('quantite') else ''}"
                f"<br/><font color='#566360'>n° Scirius</font> {ou(inv.get(r['nom'].lower(), {}).get('scirius'))} · "
                f"<font color='#566360'>emplacement</font> {ou(inv.get(r['nom'].lower(), {}).get('emplacement'))} · "
                f"<font color='#566360'>fournisseur</font> {ou(inv.get(r['nom'].lower(), {}).get('fournisseur'))} · "
                f"<font color='#566360'>lot</font> {ou(inv.get(r['nom'].lower(), {}).get('lot'))}"
                for r in reacs) or "aucun"
            lignes.append([Paragraph("Réactifs", petit), Paragraph(txt, petit)])
        ps = [p for p in pre if p["apres_etape"] == n]
        txt = "<br/>".join(
            f"<b>{escape(p['id'])}</b> · {p['volume_ml']:g} mL · {escape(moment_texte(p))} · {escape(p.get('labo') or '')}"
            f" · {escape(', '.join(p.get('analyses', [])) or 'aucune analyse')}"
            f"<br/><font color='#566360'>n° Scirius</font> {ou(p.get('scirius'))} · <font color='#566360'>n° Aramis</font> {ou(p.get('aramis'))}"
            for p in ps) or "aucun"
        lignes.append([Paragraph("Échantillons", petit), Paragraph(txt, petit)])
        t = Table(lignes, colWidths=[34 * mm, 140 * mm])
        t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, LINE), ("BACKGROUND", (0, 0), (-1, 0), TEAL_L),
                               ("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
        blocs.append(KeepTogether([t, Spacer(1, 2.5 * mm)]))
    return blocs


def table_reactifs(etapes, reactifs_section, fichier, corps, inventaire_data=None):
    """Tableau des réactifs : n° Scirius, emplacement, fournisseur, lot, étapes où ils servent."""
    inventaire = {}
    if fichier:
        inventaire = {r["nom"].lower(): r for r in json.load(open(fichier, encoding="utf-8"))}
    elif inventaire_data:  # export du Cahier de manip : tout est dans le même JSON
        inventaire = {r["nom"].lower(): r for r in inventaire_data}
    etapes_par_reactif = {}
    for e in etapes:
        for nom in e.get("reactifs", []):
            etapes_par_reactif.setdefault(nom, []).append(str(e["n"]))
    for nom in reactifs_section:
        etapes_par_reactif.setdefault(nom, [])
    if not etapes_par_reactif:
        return None
    manque = '<font color="#8A4B00">à saisir</font>'
    cell = ParagraphStyle("cr", parent=corps, fontSize=8.5, leading=11)
    cellb = ParagraphStyle("crb", parent=cell, fontName=FONTB)
    lignes = [[Paragraph(t, cellb) for t in ["Réactif", "N° Scirius", "Emplacement", "Fournisseur", "Lot", "Étape"]]]
    for nom, ns in etapes_par_reactif.items():
        r = inventaire.get(nom.lower(), {})
        champs = [r.get(k) for k in ("scirius", "emplacement", "fournisseur", "lot")]
        lignes.append([Paragraph(f"<b>{escape(nom)}</b>", cell)]
                      + [Paragraph(escape(str(v)) if v else manque, cell) for v in champs]
                      + [Paragraph(", ".join(ns) or "-", cell)])
    tab = Table(lignes, colWidths=[30 * mm, 22 * mm, 52 * mm, 30 * mm, 20 * mm, 20 * mm], repeatRows=1)
    tab.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, LINE), ("BACKGROUND", (0, 0), (-1, 0), TEAL_L),
                             ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
    return tab


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("json")
    ap.add_argument("--prelevements")
    ap.add_argument("--reactifs", help="JSON : nom, scirius, emplacement, fournisseur, lot")
    ap.add_argument("--donneur", default="à renseigner")
    ap.add_argument("--ref", default="à renseigner")
    ap.add_argument("--volume-depart", type=float)
    ap.add_argument("--titre", default="Prétraitement d'une graisse animale")
    ap.add_argument("--out", default="manip_flux.pdf")
    a = ap.parse_args()

    data = json.load(open(a.json, encoding="utf-8"))
    pre = json.load(open(a.prelevements, encoding="utf-8")) if a.prelevements else data.get("prelevements", [])
    ctx = data.get("contexte", {})
    if a.donneur == "à renseigner" and ctx.get("donneur"):
        a.donneur = ctx["donneur"]
    if a.ref == "à renseigner" and ctx.get("ref"):
        a.ref = ctx["ref"]
    if a.volume_depart is None and ctx.get("volumeDepart"):
        a.volume_depart = float(ctx["volumeDepart"])
    if data.get("titre") and a.titre == "Prétraitement d'une graisse animale":
        a.titre = data["titre"]
    etapes = data["etapes"]

    st = getSampleStyleSheet()
    corps = ParagraphStyle("corps", parent=st["Normal"], fontName=FONT, fontSize=9.5, leading=14, textColor=INK)
    petit = ParagraphStyle("petit", parent=corps, fontSize=8, leading=11, textColor=MUTED)
    h1 = ParagraphStyle("h1", parent=st["Title"], fontName=FONTB, fontSize=18, alignment=0,
                        textColor=INK, spaceAfter=4)
    h2 = ParagraphStyle("h2", parent=st["Heading2"], fontName=FONTB, fontSize=12, textColor=TEAL,
                        spaceBefore=10, spaceAfter=5)
    h3 = ParagraphStyle("h3", parent=corps, fontName=FONTB, spaceBefore=5, spaceAfter=2)

    def pied(canvas, doc):
        canvas.saveState()
        canvas.setFont(FONT, 7.5)
        canvas.setFillColor(MUTED)
        canvas.drawString(18 * mm, 10 * mm, "Document généré automatiquement - à relire avant diffusion")
        canvas.drawRightString(192 * mm, 10 * mm, f"Page {doc.page}")
        canvas.restoreState()

    doc = SimpleDocTemplate(a.out, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=16 * mm, bottomMargin=18 * mm, title=a.titre)
    largeur = A4[0] - 36 * mm - 12  # 12 pt = marges internes du cadre
    story = [Paragraph(escape(a.titre), h1)]

    meta = [["Donneur d'ordre", a.donneur, "Réf. demande", a.ref]]
    if ctx.get("type") or ctx.get("tags"):
        meta.append(["Type", ctx.get("type") or "-", "Tags", "  ".join("#" + t for t in ctx.get("tags", [])) or "-"])
    if data.get("version"):
        lanc = data.get("lancee") or {}
        jr = data.get("journal") or []
        meta.append(["Version", f"{data['version']} · enregistrée le {fmt_dt(data.get('enregistree_le'))}",
                     "Lancement", (f"le {fmt_dt(lanc.get('le'))} par {lanc.get('par', '')}" + (f" - MODIFIÉE ({len(jr)})" if jr else "")) if lanc else "-"])
    t = Table([[Paragraph(f"<b>{escape(x)}</b>" if i % 2 == 0 else escape(x), corps) for i, x in enumerate(r)]
               for r in meta], colWidths=[32 * mm, 62 * mm, 28 * mm, 52 * mm])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), TEAL_L), ("BOX", (0, 0), (-1, -1), 0.5, LINE),
                           ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
    story += [t, Paragraph("Flux de prétraitement", h2), Flux(etapes, pre, largeur), Spacer(1, 3 * mm)]

    total = sum(e["parametres"].get("duree_min", 0) for e in etapes)
    legende = f"Durée cumulée des étapes chronométrées : {duree(total)}. Chaque prélèvement a un badge : dans la carte de l’étape, posé à son moment sur la frise (à l’extrémité droite pour un prélèvement à l’effluent), et sous la carte avec son nom, son volume et son moment."
    if a.volume_depart and pre:
        pris = sum(p["volume_ml"] for p in pre)
        legende += f" Volume : {vol(a.volume_depart)} mL au départ, {vol(pris)} mL prélevés, {vol(a.volume_depart - pris)} mL restants."
    story.append(Paragraph(escape(legende), petit))

    story.append(Paragraph("Matériel et méthodes", h2))
    for b in data["sous_sections"]:
        if b["texte"]:
            story += [Paragraph(escape(b["titre"]), h3), Paragraph(escape(b["texte"]), corps)]

    inv_data = data.get("inventaire_reactifs")
    if a.reactifs:
        inv_data = json.load(open(a.reactifs, encoding="utf-8"))
    story.append(Paragraph("Détail par phase du flux", h2))
    story += blocs_phases(etapes, pre, inv_data, corps)
    tab_r = table_reactifs(etapes, data.get("reactifs", []), a.reactifs, corps, data.get("inventaire_reactifs"))
    if tab_r is not None:
        story.append(KeepTogether([Paragraph("Réactifs", h2), tab_r]))

    if pre:
        titre_ech = Paragraph("Échantillons", h2)
        ouvert = lambda s: f'<font color="#8A4B00">{s}</font>'
        lignes = [["Éch.", "Étape", "Moment", "Volume", "N° Scirius", "N° Aramis", "Laboratoire", "Analyses"]]
        for p in pre:
            etape = "entrée" if p["apres_etape"] == 0 else f"{p['apres_etape']} · {etapes[p['apres_etape'] - 1]['operation']}"
            lignes.append([p["id"], etape, moment_texte(p), f"{p['volume_ml']:g} mL", p["scirius"] or "à saisir",
                           p["aramis"] or "à saisir", p["labo"], ", ".join(p.get("analyses", []))])
        tab = Table([[Paragraph(ouvert("à saisir") if c == "à saisir" else escape(str(c)),
                                ParagraphStyle("c", parent=corps, fontSize=8.5, leading=11,
                                               fontName=FONTB if i == 0 else FONT))
                      for c in r] for i, r in enumerate(lignes)],
                    colWidths=[12 * mm, 28 * mm, 26 * mm, 17 * mm, 19 * mm, 19 * mm, 22 * mm, 31 * mm], repeatRows=1)
        tab.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, LINE), ("BACKGROUND", (0, 0), (-1, 0), TEAL_L),
                                 ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
        story.append(KeepTogether([titre_ech, tab]))

    if data.get("lancee"):
        jr = data.get("journal") or []
        story.append(Paragraph("Modifications après lancement", h2))
        if jr:
            lignes = [[Paragraph("<b>Date et heure</b>", corps), Paragraph("<b>Par</b>", corps), Paragraph("<b>Modification</b>", corps)]]
            lignes += [[Paragraph(fmt_dt(j["t"]), corps), Paragraph(escape(j["par"]), corps), Paragraph(escape(j["txt"]), corps)] for j in jr]
            tj = Table(lignes, colWidths=[36 * mm, 24 * mm, 114 * mm], repeatRows=1)
            tj.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), TEAL_L), ("GRID", (0, 0), (-1, -1), 0.4, LINE),
                                    ("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
            story.append(tj)
        else:
            story.append(Paragraph("Aucune modification depuis le lancement.", corps))
    doc.build(story, onFirstPage=pied, onLaterPages=pied)
    print("PDF écrit :", a.out)


if __name__ == "__main__":
    main()
