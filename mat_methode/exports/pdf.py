"""Export PDF avec le schéma du flux (§11, V13), à partir du JSON d'échange (`echange.exporter`).

Repris de `scripts/export_pdf_flux.py`, avec : hauteur des cartes adaptée au contenu (§14.6),
repères « à saisir » en ambre dans le texte, bandeau complet (type, tags, version, lancement).
"""
from __future__ import annotations

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

from mat_methode.domain.regles import plage
from mat_methode.domain.texte import fmt_dt, fmt_dur, fmt_num, fmt_vol
from mat_methode.exports.disposition import disposer
from mat_methode.exports.polices import trouver

TEAL, TEAL_L = colors.HexColor("#0F6B5C"), colors.HexColor("#E1F0EC")
INK, MUTED, LINE = colors.HexColor("#14201D"), colors.HexColor("#566360"), colors.HexColor("#BFCBC7")
AMBER, AMBER_L = colors.HexColor("#8A4B00"), colors.HexColor("#FDF1DC")
# une couleur par voie (A, B, C, D) : trait, fond clair, texte — les blocs d'une même voie se reconnaissent d'un coup d'œil
COULEURS_VOIES = [(colors.HexColor("#2F6FB8"), colors.HexColor("#E6F0FA"), colors.HexColor("#1F4F86")),
                  (colors.HexColor("#8A4FB0"), colors.HexColor("#F1E8F8"), colors.HexColor("#5E3380")),
                  (colors.HexColor("#C4631A"), colors.HexColor("#FBEBDD"), colors.HexColor("#8A4400")),
                  (colors.HexColor("#B03A6E"), colors.HexColor("#F8E6EE"), colors.HexColor("#7D234B"))]
VERT, VERT_L, VERT_T = colors.HexColor("#4AA064"), colors.HexColor("#E8F6EE"), colors.HexColor("#1B6B2A")
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
        out.append(f"{fmt_num(p['agitation_trmin'])} {'g' if p.get('vitesse_unite') == 'g' else 'tr/min'}")
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


def avec_departs(etapes: list[dict]) -> list[dict]:
    """Ajoute une carte virtuelle « Départ · voie X » avant la 1re étape de chaque voie d'un bloc qui ouvre le flux."""
    out = []
    for e in etapes:
        par = e.get("parallele") or {}
        reu = e.get("reunion")
        if reu and reu.get("voies"):  # étape qui réunit des voies : carte « Réunion » avec le volume de chaque voie et le total
            out.append({"virtuel": True, "n": None, "operation": "Réunion · voies " + " + ".join(v["lettre"] for v in reu["voies"]),
                        "depart": {"volume_ml": reu.get("volume_ml"), "reunion": True,
                                   "matieres": [{"nom": f"Voie {v['lettre']}", "quantite": f"{fmt_vol(v['volume_ml'])} mL"} for v in reu["voies"]]},
                        "parametres": {}, "reactifs_detail": [], "autres": [], "equipement": []})
        if par.get("depart") is not None:
            out.append({"virtuel": True, "n": None, "operation": f"Départ · voie {par.get('lettre', '')}", "parallele": par, "depart": par["depart"],
                        "parametres": {}, "reactifs_detail": [], "autres": [], "equipement": []})
        out.append(e)
    return out


class Flux(Flowable):
    """Cartes d'étapes reliées par des flèches ; badges sur la frise ; noms des échantillons sous les cartes."""

    PAR_LIGNE, GAP, CARTE_MIN, ESPACE, PAS, TETE = 5, 6 * mm, 40 * mm, 9 * mm, 12.4 * mm, 15 * mm

    def __init__(self, etapes, prelevements, largeur):
        super().__init__()
        self.font, self.fontb = polices()
        etapes = avec_departs(etapes)  # bloc en parallèle au départ : une carte « Départ » par voie
        if any(e.get("parallele") for e in etapes):
            self.ESPACE = 16 * mm  # place pour le cadre « en parallèle » et les flèches de séparation
            if any((e.get("parallele") or {}).get("depart") is not None for e in etapes):
                self.TETE = 25 * mm  # bloc au départ : la flèche d'entrée passe au-dessus du cadre
        self.etapes, self.largeur = etapes, largeur
        self.carte_w = (largeur - (self.PAR_LIGNE - 1) * self.GAP) / self.PAR_LIGNE
        self.cases, self.liens, self.lettres = disposer(etapes, self.PAR_LIGNE)  # étapes en parallèle : une colonne par voie
        self.lignes = max([r for r, _ in self.cases] + [0]) + 1
        self.par_apres: dict[int, list] = {}
        for p in prelevements:
            self.par_apres.setdefault(p["apres_etape"], []).append(p)
        if self.par_apres.get(0):
            self.TETE = max(self.TETE, 27 * mm)  # échantillons d'entrée : la flèche ENTRÉE passe sous leurs pastilles
        self.contenus = [self._contenu(e) for e in etapes]
        self.bandes, self.h_cartes = [], []
        for r in range(self.lignes):
            grp = [i for i, (rr, _) in enumerate(self.cases) if rr == r]
            self.bandes.append(max([len(self.par_apres.get(etapes[i]["n"], [])) for i in grp] + [0]))
            self.h_cartes.append(max([self.CARTE_MIN] + [self.contenus[i]["h"] for i in grp]))
        self.hauteurs = [hc + b * self.PAS + self.ESPACE for hc, b in zip(self.h_cartes, self.bandes)]
        self.haut = self.TETE + sum(self.hauteurs) + 4 * mm

    def _contenu(self, e: dict) -> dict:
        """Lignes de la carte ; la police des textes est réduite si la carte devient trop haute (§14.6)."""
        w = self.carte_w
        if e.get("virtuel"):  # Départ d'une voie : matières et volume
            dep = e["depart"]
            lignes = []
            for x in dep.get("matieres", []):
                lignes += [(ln, self.fontb, 7.5, INK) for ln in simpleSplit(f"{x['nom']} {x.get('quantite') or ''}".strip(), self.fontb, 7.5, w - 6 * mm)]
                if x.get("reference"):
                    lignes += [(ln, self.font, 7, MUTED) for ln in simpleSplit(str(x["reference"]), self.font, 7, w - 6 * mm)]
            if len(dep.get("matieres", [])) != 1 or not dep.get("volume_ml"):  # une seule matière : son volume est déjà écrit
                lignes.append((("Total " if dep.get("reunion") else "") + f"{fmt_vol(dep['volume_ml'])} mL" if dep.get("volume_ml") else "matière à saisir", self.font, 7.5, TEAL))
            return {"titre": [e["operation"].upper()], "taille_t": 7.5, "lignes": lignes, "h": 12 * mm + sum(t + 1.6 for _, _, t, _ in lignes) + 3 * mm}
        titre, taille_t = titre_lignes(e["operation"][:1].upper() + e["operation"][1:], w - 11 * mm, self.fontb)
        detail = e.get("reactifs_detail") or [{"nom": n, "quantite": ""} for n in e.get("reactifs", [])]
        cond = " · ".join(x for x in [conditions(e["parametres"])] + [f"{a['nom']} {a.get('valeur', '')}".strip() for a in e.get("autres", [])] if x)
        for echelle in (1.0, 0.9, 0.8):
            textes = []
            for r in detail:  # un point par réactif : nom et quantité, puis temps de contact et consigne
                if r.get("nom"):
                    textes.append(("• " + r["nom"] + (" " + r["quantite"] if r.get("quantite") else ""), self.fontb, 7.5 * echelle, INK))
                    if r.get("contact"):
                        textes.append((f"   contact {r['contact']}", self.font, 7 * echelle, MUTED))
                    if r.get("consigne"):
                        textes.append((f"   Consigne : {r['consigne']}", self.font, 7 * echelle, AMBER))
            textes.append((cond, self.font, 7.5 * echelle, TEAL))
            textes += [(eq, self.font, 7 * echelle, MUTED) for eq in e.get("equipement", [])]
            if e.get("remarque"):
                textes.append((f"Consigne : {e['remarque']}", self.font, 7 * echelle, AMBER))
            lignes = []
            for texte, police, taille, couleur in textes:
                if texte:
                    lignes += [(ln, police, taille, couleur) for ln in simpleSplit(texte, police, taille, w - 6 * mm)]
            frise = bool(e["parametres"].get("duree_min") or self.par_apres.get(e["n"]))
            h = (4.5 * mm if e.get("groupe") else 0) + 12 * mm + (len(titre) - 1) * (taille_t + 1.2) + sum(t + 1.6 for _, _, t, _ in lignes) + (11 * mm if frise else 3 * mm)
            if h <= 75 * mm:
                break
        return {"titre": titre, "taille_t": taille_t, "lignes": lignes, "h": h}

    def wrap(self, dispo_l=0, dispo_h=0, *_):
        """Un flux plus haut que la page (étapes en parallèle sur plusieurs lignes) est réduit pour tenir sur une page."""
        cible = min(215 * mm, dispo_h - 22 * mm) if dispo_h else self.haut  # reste de la 1re page après l'en-tête, avec titre et légende
        self.echelle = min(1.0, max(0.4, cible / self.haut))
        return self.largeur * self.echelle, self.haut * self.echelle

    def badge(self, c, x, y, code):
        c.setFillColor(AMBER)
        c.circle(x, y, 1.9 * mm, stroke=0, fill=1)
        c.setFillColor(colors.white)
        c.setFont(self.fontb, 6)
        c.drawCentredString(x, y - 0.75 * mm, code)

    def pastille(self, c, x, y, ligne1, ligne2="", code=None, labo=""):
        """Pastille d'échantillon : nom et volume, moment, puis le laboratoire (petite étiquette)."""
        decal = 6 * mm if code else 2 * mm
        h = 10.8 * mm if labo else 8 * mm
        y0 = y - (h - 8 * mm)  # la pastille grandit vers le bas
        w = max(stringWidth(ligne1, self.fontb, 7), stringWidth(ligne2, self.font, 6.3),
                stringWidth(labo, self.fontb, 5.8) + 2 * mm) + decal + 2 * mm
        c.setFillColor(AMBER_L)
        c.setStrokeColor(AMBER)
        c.setLineWidth(0.8)
        c.roundRect(x, y0, w, h, 1.6 * mm, stroke=1, fill=1)
        if code:
            self.badge(c, x + 3.2 * mm, y + 4 * mm, code)
        c.setFillColor(AMBER)
        c.setFont(self.fontb, 7)
        c.drawString(x + decal, y + 4.7 * mm, ligne1)
        c.setFont(self.font, 6.3)
        c.drawString(x + decal, y + 1.7 * mm, ligne2)
        if labo:  # étiquette du laboratoire
            lw = stringWidth(labo, self.fontb, 5.8) + 2 * mm
            c.setFillColor(TEAL_L)
            c.setStrokeColor(TEAL)
            c.setLineWidth(0.5)
            c.roundRect(x + decal, y0 + 0.6 * mm, lw, 2.6 * mm, 0.8 * mm, stroke=1, fill=1)
            c.setFillColor(TEAL)
            c.setFont(self.fontb, 5.8)
            c.drawString(x + decal + 1 * mm, y0 + 1.25 * mm, labo)
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
        return f"{p['id']} · {fmt_vol(p['volume_ml'] or 0)} mL", moment_texte(p), code_badge(p["id"]), p.get("labo") or ""

    def draw(self):
        c, w = self.canv, self.carte_w
        s = getattr(self, "echelle", 1.0)
        if s < 1.0:
            c.scale(s, s)
        c.setFont(self.fontb, 7.5)
        c.setFillColor(MUTED)
        c.drawString(0, self.haut - 4 * mm, "ENTRÉE")
        x = stringWidth("ENTRÉE", self.fontb, 7.5) + 3 * mm
        for pre in self.par_apres.get(0, []):
            x += self.pastille(c, x, self.haut - 11 * mm, *self.etiquette(pre)) + 1.5 * mm

        positions = []
        for i in range(len(self.etapes)):
            r, k = self.cases[i]
            h = self.h_cartes[r]
            positions.append((k * (w + self.GAP), self.haut - self.TETE - sum(self.hauteurs[:r]) - h, r, h))
        self._cadres_en_parallele(c, positions)  # derrière les cartes
        for i, e in enumerate(self.etapes):
            cx, cy, r, h = positions[i]
            ct = self.contenus[i]
            par_e = e.get("parallele") or None
            voie_c = COULEURS_VOIES[par_e["voie"] % len(COULEURS_VOIES)] if par_e and par_e.get("voie") is not None else None
            c.setFillColor(voie_c[1] if voie_c else (VERT_L if e.get("virtuel") else colors.white))
            c.setStrokeColor(voie_c[0] if voie_c else (VERT if e.get("virtuel") else LINE))
            c.setLineWidth(1.4 if e.get("virtuel") or voie_c else 1)
            c.roundRect(cx, cy, w, h, 2.5 * mm, stroke=1, fill=1)
            haut = cy + h
            if i in self.lettres:  # début d'une voie : « VOIE A » au-dessus de la carte
                c.setFillColor(voie_c[2] if voie_c else AMBER)
                c.setFont(self.fontb, 6.5)
                c.drawString(cx + 1 * mm, cy + h + 1.3 * mm, f"VOIE {self.lettres[i]}")
            if e.get("virtuel"):  # Départ d'une voie : matières et volume
                c.setFillColor(voie_c[2] if voie_c else VERT_T)
                c.setFont(self.fontb, ct["taille_t"])
                c.drawString(cx + 3 * mm, haut - 6 * mm, ct["titre"][0])
                y = haut - 11.5 * mm
                for ligne, police, taille, couleur in ct["lignes"]:
                    c.setFont(police, taille)
                    c.setFillColor(couleur)
                    c.drawString(cx + 3 * mm, y, ligne)
                    y -= taille + 1.6
                continue
            if e.get("groupe"):  # bandeau de la grande étape (ex. DEGUMMING)
                c.setFillColor(TEAL_L)
                c.roundRect(cx + 0.5, cy + h - 4.5 * mm, w - 1, 4.5 * mm - 0.5, 2.2 * mm, stroke=0, fill=1)
                c.setFillColor(TEAL)
                c.setFont(self.fontb, 6)
                nom = e["groupe"].upper()
                while len(nom) > 3 and stringWidth(nom, self.fontb, 6) > w - 5 * mm:
                    nom = nom[:-2] + "…"
                c.drawString(cx + 2.5 * mm, cy + h - 3.1 * mm, nom)
                haut = cy + h - 4.5 * mm
            c.setFillColor(TEAL)
            c.circle(cx + 4.6 * mm, haut - 5 * mm, 3 * mm, stroke=0, fill=1)
            c.setFillColor(colors.white)
            c.setFont(self.fontb, 7.5)
            c.drawCentredString(cx + 4.6 * mm, haut - 6.2 * mm, str(e["n"]))
            c.setFillColor(INK)
            for k_l, ligne in enumerate(ct["titre"]):
                c.setFont(self.fontb, ct["taille_t"])
                c.drawString(cx + 9 * mm, haut - 6 * mm - k_l * (ct["taille_t"] + 1.2), ligne)
            y = haut - 12 * mm - (len(ct["titre"]) - 1) * (ct["taille_t"] + 1.2)
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

        for ia, ib in self.liens:
            (x1, y1, r1, h1), (x2, y2, r2, h2) = positions[ia], positions[ib]
            if r1 == r2 and self.cases[ib][1] == self.cases[ia][1] + 1:
                ym = y1 + h1 - 5 * mm
                self.fleche(c, [(x1 + w + 0.8 * mm, ym), (x2 - 0.4 * mm, ym)], "droite")
            elif r2 > r1:  # vers une autre ligne : on descend, on traverse l'espace entre les lignes, puis on entre par le haut
                xa, xb = x1 + w - 3 * mm, x2 + w - 3 * mm
                depart = y1 if self.bandes[r1] == 0 else y1 - self.bandes[r1] * self.PAS
                en_parallele = any((self.etapes[k].get("parallele") or {}).get("id") for k in range(len(self.etapes)) if self.cases[k][0] == r2)
                ym = y2 + h2 + self.ESPACE * (0.86 if en_parallele else 0.5)  # milieu de l'espace entre les rangées (au-dessus du cadre « en parallèle »)
                self.fleche(c, [(xa, depart), (xa, ym), (xb, ym), (xb, y2 + h2 + 0.4 * mm)], "bas")

        entrants, sortants = {ib for _, ib in self.liens}, {ia for ia, _ in self.liens}
        premiers = [k for k in range(len(self.etapes)) if k not in entrants]
        y_entree = max((positions[k][1] + positions[k][3] + (self.ESPACE * 0.78 if (self.etapes[k].get("parallele") or {}).get("id") else 0) for k in premiers),
                       default=self.haut - self.TETE) + 2.5 * mm  # au-dessus du cadre en parallèle s'il y en a un
        for i in premiers:  # ENTRÉE → première(s) carte(s)
            cx, cy, r, h = positions[i]
            self.fleche(c, [(3.5 * mm, self.haut - 5.5 * mm), (3.5 * mm, y_entree), (cx + w - 3 * mm, y_entree), (cx + w - 3 * mm, cy + h + 0.4 * mm)], "bas")
        c.setFont(self.fontb, 7.5)
        c.setFillColor(MUTED)
        c.drawRightString(self.largeur, 1.5 * mm, "SORTIE · produit prétraité")
        x_sortie = self.largeur - stringWidth("SORTIE · produit prétraité", self.fontb, 7.5) - 2 * mm
        for i in (k for k in range(len(self.etapes)) if k not in sortants):  # dernière(s) carte(s) → SORTIE
            cx, cy, r, h = positions[i]
            bas = cy - self.bandes[r] * self.PAS
            xa = cx + w - 3 * mm
            if xa >= x_sortie:  # au-dessus du libellé : on descend droit dessus
                self.fleche(c, [(xa, bas), (xa, 5.4 * mm)], "bas")
            else:  # à gauche du libellé : on descend, on avance, puis on entre par le haut du libellé
                x_fin = x_sortie + 6 * mm
                self.fleche(c, [(xa, bas), (xa, 7.5 * mm), (x_fin, 7.5 * mm), (x_fin, 5.4 * mm)], "bas")

    def _cadres_en_parallele(self, c, positions):
        """Cadre ambre autour de chaque bloc en parallèle, avec le signe « || » dessiné (la police ne l'a pas toujours) et le mot EN PARALLÈLE."""
        blocs: dict[str, list[int]] = {}
        for i, e in enumerate(self.etapes):
            pid = (e.get("parallele") or {}).get("id")
            if pid:
                blocs.setdefault(pid, []).append(i)
        for idx in blocs.values():
            x0 = min(positions[i][0] for i in idx) - 3 * mm
            x1 = max(positions[i][0] for i in idx) + self.carte_w + 3 * mm
            y_haut = max(positions[i][1] + positions[i][3] for i in idx) + self.ESPACE * 0.78
            y_bas = min(positions[i][1] - self.bandes[positions[i][2]] * self.PAS for i in idx) - 2.5 * mm
            c.saveState()
            c.setFillColor(AMBER_L)
            c.setStrokeColor(AMBER)
            c.setLineWidth(1.2)
            c.setDash(3, 2)
            c.roundRect(x0, y_bas, x1 - x0, y_haut - y_bas, 3 * mm, stroke=1, fill=1)
            c.restoreState()
            c.saveState()
            c.setStrokeColor(AMBER)
            c.setLineWidth(1.3)
            yt = y_haut - 4.6 * mm
            c.line(x0 + 3 * mm, yt - 0.4 * mm, x0 + 3 * mm, yt + 2.6 * mm)
            c.line(x0 + 4.6 * mm, yt - 0.4 * mm, x0 + 4.6 * mm, yt + 2.6 * mm)
            c.restoreState()
            c.setFillColor(AMBER)
            c.setFont(self.fontb, 7.5)
            c.drawString(x0 + 6.5 * mm, yt, "EN PARALLÈLE")


def _ou(v):
    return escape(str(v)) if v not in (None, "") else MANQUE


def couleur_phase(ph: dict):
    """(trait, fond, texte) de la voie d'une phase « EN PARALLÈLE · VOIE B » ; couleurs habituelles pour les autres phases."""
    if ph.get("reunion_voies"):
        return VERT, VERT_L, VERT_T  # la réunion des voies : même vert que sa carte du schéma
    mt = re.search(r"VOIE ([A-D])", ph.get("parallele") or "")
    return COULEURS_VOIES[ord(mt.group(1)) - 65] if mt else (LINE, TEAL_L, AMBER)


def _depart_commun(ph: dict, i: int) -> bool:
    """Phase « Départ » commune (matière et volume de la manip) ; un « Départ · voie X » se présente comme une étape de sa voie."""
    return not ph.get("depart_voie") and not ph.get("entree_voies") and not ph.get("reunion_voies") and (ph["n"] == 0 if "n" in ph else i == 0)


def blocs_phases(data: dict, corps) -> list:
    """Une fiche par phase (jamais coupée entre deux pages)."""
    petit = ParagraphStyle("ph", parent=corps, fontSize=8.5, leading=11.5)
    blocs = []
    for i, ph in enumerate(data.get("phases", [])):
        if _depart_commun(ph, i):
            ctx = data.get("contexte", {})
            sous = escape(f"{ctx.get('matiere') or ''}") + (
                f" · n° Scirius {escape(ctx['scirius'])}" if ctx.get("scirius") else "") + (
                f" · fournisseur {escape(ctx['fournisseur'])}" if ctx.get("fournisseur") else "") + (
                f" · emplacement {escape(ctx['emplacement'])}" if ctx.get("emplacement") else "") + (
                f" · {fmt_vol(ctx['volumeDepart'])} mL" if ctx.get("volumeDepart") is not None else "")
        elif ph.get("reunion_voies"):  # volume de chaque voie, puis le total
            sous = "<br/>".join(f"<b>{escape(r['nom'])}</b> · {escape(r['quantite'])}" for r in ph["reactifs"]) + f"<br/><b>{escape(ph.get('conditions') or '')}</b>"
        else:
            sous = escape(ph.get("conditions") or ("" if ph.get("entree_voies") else "conditions à compléter")) + (
                f"<br/><font color='#566360'>{escape(', '.join(ph['materiel']))}</font>" if ph.get("materiel") else "") + (
                f"<br/><i>Consigne / remarque : {escape(ph['remarque'])}</i>" if ph.get("remarque") else "")
        trait, fond, texte_c = couleur_phase(ph)
        tete = ((f"<font size='7' color='{texte_c.hexval().replace('0x', '#')}'><b>{escape(ph['parallele'])}</b></font><br/>" if ph.get("parallele") else "")
                + (f"<font size='7' color='#0F6B5C'><b>{escape(ph['groupe'].upper())}</b></font><br/>" if ph.get("groupe") else "") + f"<b>{escape(ph['titre'])}</b>"
                + (f"<br/><font size='7' color='#0F6B5C'><b>{escape(ph['reunion'])}</b></font>" if ph.get("reunion") else ""))
        lignes = [[Paragraph(tete, petit), Paragraph(sous, petit)]]
        if not _depart_commun(ph, i) and not ph.get("entree_voies") and not ph.get("reunion_voies"):
            txt = "<br/>".join(
                f"• <b>{escape(r['nom'])}</b>{' · ' + escape(r['quantite']) if r.get('quantite') else ''}"
                f"{' · contact ' + escape(r['contact']) if r.get('contact') else ''}"
                f"{'<br/><i>Consigne : ' + escape(r['consigne']) + '</i>' if r.get('consigne') else ''}"
                f"<br/><font color='#566360'>n° Scirius</font> {_ou(r.get('scirius'))} · <font color='#566360'>emplacement</font> {_ou(r.get('emplacement'))} · "
                f"<font color='#566360'>fournisseur</font> {_ou(r.get('fournisseur'))}"
                for r in ph["reactifs"]) or "aucun"
            lignes.append([Paragraph("Réactifs", petit), Paragraph(txt, petit)])
        txt = "<br/>".join(
            f"<b>{escape(x['id'])}</b> · {fmt_vol(x['volume'] or 0)} mL · {escape(x['moment'])} · {escape(x.get('labo') or '')}"
            f" · {escape(', '.join(x.get('analyses', [])) or 'aucune analyse')}"
            f"<br/><font color='#566360'>n° Scirius</font> {_ou(x.get('scirius'))} · <font color='#566360'>n° Aramis</font> {_ou(x.get('aramis'))}"
            + (f"<br/><i>Commentaire : {escape(x['commentaire'])}</i>" if x.get("commentaire") else "")
            for x in ph["echantillons"]) or "aucun"
        if not ph.get("depart_voie") and not ph.get("reunion_voies"):
            lignes.append([Paragraph("Échantillons", petit), Paragraph(txt, petit)])
        t = Table(lignes, colWidths=[34 * mm, 140 * mm])
        t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, trait), ("BACKGROUND", (0, 0), (-1, 0), fond), ("BOX", (0, 0), (-1, -1), 1.2, trait),
                               ("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
        blocs.append(KeepTogether([t, Spacer(1, 2.5 * mm)]))
    return blocs


def styles() -> dict:
    font, fontb = polices()
    st = getSampleStyleSheet()
    corps = ParagraphStyle("corps", parent=st["Normal"], fontName=font, fontSize=9.5, leading=14, textColor=INK)
    cell = ParagraphStyle("c", parent=corps, fontSize=8.5, leading=11)
    return {
        "font": font, "fontb": fontb, "corps": corps, "cell": cell,
        "petit": ParagraphStyle("petit", parent=corps, fontSize=8, leading=11, textColor=MUTED),
        "h1": ParagraphStyle("h1", parent=st["Title"], fontName=fontb, fontSize=18, alignment=0, textColor=INK, spaceAfter=4),
        "h2": ParagraphStyle("h2", parent=st["Heading2"], fontName=fontb, fontSize=12, textColor=TEAL, spaceBefore=10, spaceAfter=5,
                             keepWithNext=1),  # un titre ne reste jamais seul en bas de page
        "h3": ParagraphStyle("h3", parent=corps, fontName=fontb, spaceBefore=5, spaceAfter=2, keepWithNext=1),
        "cellb": ParagraphStyle("cb", parent=cell, fontName=fontb),
    }


def document(chemin, titre: str, pied_texte: str = "Document généré automatiquement - à relire avant diffusion"):
    font = polices()[0]

    def pied(canvas, doc):
        canvas.saveState()
        canvas.setFont(font, 7.5)
        canvas.setFillColor(MUTED)
        canvas.drawString(18 * mm, 10 * mm, pied_texte)
        canvas.drawRightString(192 * mm, 10 * mm, f"Mat & Méthode · page {doc.page}")
        canvas.restoreState()

    doc = SimpleDocTemplate(str(chemin), pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=16 * mm, bottomMargin=18 * mm, title=titre, author="Mat & Méthode")
    return doc, pied


def cartouche(data: dict, s: dict) -> Table:
    """Bandeau du haut : donneur d'ordre, référence, type, date, tags, version et lancement."""
    ctx, corps = data.get("contexte", {}), s["corps"]
    lanc, jr = data.get("lancee"), data.get("journal") or []
    meta = [[("Donneur d’ordre", _ou(ctx.get("donneur"))), ("Réf. demande", _ou(ctx.get("ref")))],
            [("Type", escape(ctx.get("type") or "-")), ("Date", escape(ctx.get("date") or "-"))]]
    if ctx.get("experience") or ctx.get("attribue"):
        meta.append([("N° d’expérience", escape(ctx.get("experience") or "-")), ("Attribuée à", escape(ctx.get("attribue") or "-"))])
    rep = ctx.get("reperes") or []
    if rep:
        meta.append([("Étapes", escape(" ; ".join(f"{x['initiale']} : {x['materiel']}" if x["materiel"] else x["initiale"] for x in rep))), ("", "")])
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
                          + [("SPAN", (1, k), (3, k)) for k in range(2, len(rows) - 1) if meta[k][1] == ("", "")]))
    return t


def bloc_a_faire(data: dict, s: dict) -> list:
    """Points « À faire » du flux qui ne sont pas cochés (rapport et protocole), s'il y en a."""
    af = data.get("a_faire") or []
    if not af:
        return []
    cell = s["cell"]
    lignes = [[Paragraph(f"<b>{h}</b>", cell) for h in ("", "Catégorie", "À faire")]]
    lignes += [[Paragraph("☐", cell), Paragraph(escape(x.get("categorie") or ""), cell), Paragraph(escape(x.get("texte") or ""), cell)] for x in af]
    t = Table(lignes, colWidths=[8 * mm, 42 * mm, 124 * mm], repeatRows=1)
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), TEAL_L), ("GRID", (0, 0), (-1, -1), 0.4, LINE), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    return [KeepTogether([Paragraph(f"À faire ({len(af)} point{'s' if len(af) > 1 else ''} non coché{'s' if len(af) > 1 else ''})", s["h2"]), t])]


def bloc_statuts(data: dict, s: dict) -> list:
    """Historique des changements de statut (date, qui, de → vers), s'il y en a."""
    st = data.get("statuts") or []
    if not st:
        return []
    cell = s["cell"]
    lignes = [[Paragraph(f"<b>{h}</b>", cell) for h in ("Date et heure", "Par", "Changement de statut")]]
    lignes += [[Paragraph(fmt_dt(c["t"]), cell), Paragraph(escape(c.get("nom") or c.get("par") or ""), cell),
                Paragraph(f"{escape(c.get('de', ''))} → <b>{escape(c.get('vers', ''))}</b>", cell)] for c in st]
    t = Table(lignes, colWidths=[36 * mm, 50 * mm, 88 * mm], repeatRows=1)
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), TEAL_L), ("GRID", (0, 0), (-1, -1), 0.4, LINE), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    return [KeepTogether([Paragraph("Historique des statuts", s["h2"]), t])]


def volumes(data: dict) -> dict:
    """Volumes depuis le JSON d'échange : prélevé en amont (avant traitement, hors volume engagé), engagé, prélevé pendant
    le flux, restant, total à prévoir, et le reste après chaque échantillon (None pour un échantillon pris en amont)."""
    vd = data.get("contexte", {}).get("volumeDepart")
    pre = data.get("prelevements", [])
    amont = [p for p in pre if not p.get("apres_etape")]
    flux = [p for p in pre if p.get("apres_etape")]
    va, vp = sum(p["volume_ml"] or 0 for p in amont), sum(p["volume_ml"] or 0 for p in flux)
    reste, suivi = vd or 0, []
    for p in pre:
        if p.get("apres_etape"):
            reste -= p["volume_ml"] or 0
            suivi.append((p, reste))
        else:
            suivi.append((p, None))
    return {"depart": vd, "amont": va, "n_amont": len(amont), "preleve": vp, "n": len(flux),
            "restant": (vd or 0) - vp, "total": (vd or 0) + va, "suivi": suivi}


def phrase_volumes(data: dict) -> str:
    v = volumes(data)
    if v["depart"] is None:
        return ""
    t = (f"Volume : {fmt_vol(v['amont'])} mL prélevés en amont (hors manip) ; " if v["n_amont"] else "Volume : ")
    t += f"{fmt_vol(v['depart'])} mL engagés, {fmt_vol(v['preleve'])} mL prélevés pendant le flux, " + (
        f"{fmt_vol(v['restant'])} mL restants." if v["restant"] >= 0 else f"dépassement de {fmt_vol(-v['restant'])} mL.")
    if v["n_amont"]:
        t += f" Charge à prévoir : {fmt_vol(v['total'])} mL."
    return t


def legende_flux(data: dict) -> str:
    etapes = data["etapes"]
    total = sum(e["parametres"].get("duree_min") or 0 for e in etapes)
    legende = (f"Durée cumulée des étapes chronométrées : {fmt_dur(total)}. Chaque prélèvement a un badge : dans la carte de l’étape, "
               "posé à son moment sur la frise (à l’extrémité droite pour un prélèvement à l’effluent), et sous la carte avec son nom, son volume et son moment.")
    if data.get("grandes_etapes"):
        legende += " Grandes étapes (bandeau en haut des cartes) : " + " ; ".join(
            f"{g['nom']} ({plage(g['etapes'])})" for g in data["grandes_etapes"]) + "."
    if phrase_volumes(data):
        legende += " " + phrase_volumes(data)
    return legende


def table_reactifs(data: dict, s: dict) -> Table | None:
    etapes, cell, cellb = data["etapes"], s["cell"], s["cellb"]
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
    if not noms:
        return None
    lignes = [[Paragraph(h, cellb) for h in ["Réactif", "N° Scirius", "Emplacement", "Fournisseur", "Étape"]]]
    for nom, ns in noms:
        f = inv.get(nom.lower(), {})
        lignes.append([Paragraph(f"<b>{escape(nom)}</b>", cell)] + [Paragraph(_ou(f.get(k)), cell) for k in ("scirius", "emplacement", "fournisseur")]
                      + [Paragraph(", ".join(ns), cell)])
    tab = Table(lignes, colWidths=[34 * mm, 24 * mm, 60 * mm, 36 * mm, 20 * mm], repeatRows=1)
    tab.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, LINE), ("BACKGROUND", (0, 0), (-1, 0), TEAL_L), ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
    return tab


def table_echantillons(data: dict, s: dict, a_remplir: bool = False) -> Table | None:
    """Tableau des échantillons. `a_remplir` : cases vides (hautes) pour noter les numéros à la main."""
    etapes, pre, cell, cellb = data["etapes"], data.get("prelevements", []), s["cell"], s["cellb"]
    if not pre:
        return None
    vide = "" if a_remplir else MANQUE
    lignes = [[Paragraph(h, cellb) for h in ["Éch.", "Étape", "Moment", "Volume", "N° Scirius", "N° Aramis", "Labo" if a_remplir else "Laboratoire", "Analyses"]]]
    for p in pre:
        etape = "entrée" if p["apres_etape"] == 0 else f"{p['apres_etape']} · {etapes[p['apres_etape'] - 1]['operation']}"
        lignes.append([Paragraph(f"<b>{escape(p['id'])}</b>", cell), Paragraph(escape(etape), cell), Paragraph(escape(moment_texte(p)), cell),
                       Paragraph(f"{fmt_vol(p['volume_ml'] or 0)} mL", cell),
                       Paragraph(escape(p["scirius"]) if p.get("scirius") else vide, cell),
                       Paragraph(escape(p["aramis"]) if p.get("aramis") else vide, cell), Paragraph(escape(p.get("labo") or ""), cell),
                       Paragraph(escape(", ".join(p.get("analyses", []))), cell)])
    larg = [12 * mm, 28 * mm, 26 * mm, 17 * mm, 19 * mm, 19 * mm, 22 * mm, 31 * mm]
    if a_remplir:  # colonnes des numéros plus larges, lignes plus hautes pour écrire à la main
        larg = [11 * mm, 24 * mm, 22 * mm, 17 * mm, 25 * mm, 25 * mm, 18 * mm, 32 * mm]
    tab = Table(lignes, colWidths=larg, repeatRows=1)
    tab.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, LINE), ("BACKGROUND", (0, 0), (-1, 0), TEAL_L), ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]
                            + ([("TOPPADDING", (0, 1), (-1, -1), 8), ("BOTTOMPADDING", (0, 1), (-1, -1), 8)] if a_remplir else [])))
    return tab


def bloc_resultats(data: dict, s: dict) -> list:
    """Résultats d'analyses des échantillons lus dans ana explorer (une ligne par analyse, une colonne par échantillon), s'il y en a."""
    from mat_methode.analyses_ptt import tableaux
    res = data.get("resultats")
    if not res or not res.get("echantillons"):
        return []
    cell, cellb, petit = s["cell"], s["cellb"], s["petit"]
    n = len(res["echantillons"])
    bloc = [Paragraph("Résultats d’analyses", s["h2"]),
            Paragraph(escape(f"{n} échantillon{'s' if n > 1 else ''} avec des résultats, retrouvé{'s' if n > 1 else ''} par le n° Aramis "
                             f"dans ana explorer" + (f" ({res['source']})" if res.get("source") else "") + ". « — » : pas de résultat."), petit),
            Spacer(1, 2 * mm)]
    sortie = []
    for k, (entetes, lignes) in enumerate(tableaux(res)):
        nb = len(entetes) - 1
        larg = [50 * mm] + [124 * mm / max(nb, 1)] * nb
        rows = [[Paragraph(escape(h).replace("\n", "<br/><font size='6.5' color='#566360'>") + ("</font>" if "\n" in h else ""), cellb) for h in entetes]]
        rows += [[Paragraph(escape(ln[0]), cellb if i == len(lignes) - 1 else cell)]
                 + [Paragraph(escape(v), cell) for v in ln[1:]] for i, ln in enumerate(lignes)]
        t = Table(rows, colWidths=larg, repeatRows=1)
        t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, LINE), ("BACKGROUND", (0, 0), (-1, 0), TEAL_L),
                               ("BACKGROUND", (0, len(rows) - 1), (-1, len(rows) - 1), colors.HexColor("#F4F6F5")),
                               ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
                               ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]))
        if k == 0:
            sortie.append(KeepTogether(bloc + [t]) if len(rows) < 40 else bloc + [t])
        else:
            sortie.append(Spacer(1, 3 * mm))
            sortie.append(t)
    out = []
    for x in sortie:
        out += x if isinstance(x, list) else [x]
    return out


def ecrire_pdf(data: dict, chemin) -> None:
    s = styles()
    corps, petit, h1, h2, h3, cell = s["corps"], s["petit"], s["h1"], s["h2"], s["h3"], s["cell"]
    etapes, pre = data["etapes"], data.get("prelevements", [])
    titre = data.get("titre") or "Manip"
    doc, pied = document(chemin, titre)
    largeur = A4[0] - 36 * mm - 12
    lanc, jr = data.get("lancee"), data.get("journal") or []
    story = [Paragraph(escape(titre), h1), cartouche(data, s), *bloc_a_faire(data, s),
             KeepTogether([Paragraph("Flux de prétraitement", h2), Flux(etapes, pre, largeur), Spacer(1, 3 * mm),
                           Paragraph(escape(legende_flux(data)), petit)])]

    # chaque sous-section reste entière quand elle tient sur une page ; un titre n'est jamais seul en bas de page
    premiere = True
    for b in data.get("sous_sections", []):
        if b.get("texte"):
            bloc = ([Paragraph("Matériel et méthodes", h2)] if premiere else []) + [Paragraph(escape(b["titre"]), h3)]
            story.append(KeepTogether(bloc + [Paragraph(avec_reperes(x), corps) for x in b["texte"].split("\n") if x]))
            premiere = False

    phases = blocs_phases(data, corps)
    story.append(KeepTogether([Paragraph("Détail par phase du flux", h2)] + phases[:1]))
    story += phases[1:]
    tab = table_reactifs(data, s)
    if tab is not None:
        story.append(KeepTogether([Paragraph("Réactifs", h2), tab]))
    tab = table_echantillons(data, s)
    if tab is not None:
        story.append(KeepTogether([Paragraph("Échantillons", h2), tab]))
    story += bloc_resultats(data, s)  # résultats lus dans ana explorer

    if lanc:
        story.append(Paragraph("Modifications après lancement", h2))  # keepWithNext : suit le tableau
        if jr:
            lignes = [[Paragraph("<b>Date et heure</b>", cell), Paragraph("<b>Par</b>", cell), Paragraph("<b>Modification</b>", cell)]]
            lignes += [[Paragraph(fmt_dt(j["t"]), cell), Paragraph(escape(j["par"]), cell), Paragraph(escape(j["txt"]), cell)] for j in jr]
            tj = Table(lignes, colWidths=[36 * mm, 24 * mm, 114 * mm], repeatRows=1)
            tj.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), TEAL_L), ("GRID", (0, 0), (-1, -1), 0.4, LINE), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
            story.append(tj)
        else:
            story.append(Paragraph("Aucune modification depuis le lancement.", corps))
    story += bloc_statuts(data, s)
    doc.build(story, onFirstPage=pied, onLaterPages=pied)
