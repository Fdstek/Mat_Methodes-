"""Export Word (.docx) à partir du JSON d'échange (repris de `scripts/export_word.py`).

Le schéma du flux est une image PNG (Pillow) ; tout le reste est du vrai texte modifiable.
Les « à saisir » sont surlignés en jaune.
"""
from __future__ import annotations

import io
import re
from pathlib import Path

from docx import Document
from docx.enum.text import WD_COLOR_INDEX
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor
from PIL import Image, ImageDraw, ImageFont

from mat_methode.domain.regles import plage
from mat_methode.domain.texte import fmt_dt, fmt_dur, fmt_vol
from mat_methode.exports.disposition import disposer
from mat_methode.exports.pdf import _depart_commun, avec_departs, code_badge, conditions, moment_texte, phrase_volumes
from mat_methode.exports.polices import trouver

TEAL, AMBER, MUTED = "0F6B5C", "8A4B00", "566360"
REPERE = re.compile(r"(\[[^\]]*à saisir\])")


def police(gras: bool, taille: int):
    paire = trouver()
    if paire:
        return ImageFont.truetype(paire[1] if gras else paire[0], taille)
    return ImageFont.load_default()


def _lignes(draw, texte, font, w):
    out, cur = [], ""
    for mot in texte.split():
        test = (cur + " " + mot).strip()
        if draw.textlength(test, font=font) > w and cur:
            out.append(cur)
            cur = mot
        else:
            cur = test
    return out + ([cur] if cur else [])


def _titre(draw, texte, w):
    """Titre d'étape : police réduite si un mot est trop large (26 -> 18 px), puis coupure du mot."""
    taille = 26
    while taille > 18 and any(draw.textlength(m, font=police(True, taille)) > w for m in texte.split()):
        taille -= 1
    f = police(True, taille)
    mots = []
    for mot in texte.split():
        while draw.textlength(mot, font=f) > w and len(mot) > 2:
            k = len(mot) - 1
            while k > 1 and draw.textlength(mot[:k] + "-", font=f) > w:
                k -= 1
            mots.append(mot[:k] + "-")
            mot = mot[k:]
        mots.append(mot)
    lignes, cur = [], ""
    for mot in mots:
        test = (cur + " " + mot).strip()
        if cur and (cur.endswith("-") or draw.textlength(test, font=f) > w):
            lignes.append(cur)
            cur = mot
        else:
            cur = test
    return (lignes + [cur] if cur else lignes) or [texte], f, int(taille * 1.1)


def image_flux(etapes, prelevements, largeur=1900) -> Image.Image:
    """Cartes d'étapes, frise du temps et badges ; noms des échantillons sous les cartes."""
    f_n, f_s, f_b, f_bs = police(False, 21), police(False, 18), police(True, 21), police(True, 17)
    par_ligne, gap = 5, 26
    etapes = avec_departs(etapes)  # bloc en parallèle au départ : une carte « Départ » par voie
    cw = (largeur - (par_ligne - 1) * gap) // par_ligne
    par_apres: dict[int, list] = {}
    for p in prelevements:
        par_apres.setdefault(p["apres_etape"], []).append(p)
    tmp = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    cartes = []
    for e in etapes:
        if e.get("virtuel"):  # Départ d'une voie : matières et volume
            dep = e["depart"]
            ls = []
            for x in dep.get("matieres", []):
                ls += [(t, f_b, "#14201D") for t in _lignes(tmp, f"{x['nom']} {x.get('quantite') or ''}".strip(), f_b, cw - 28)]
                if x.get("reference"):
                    ls += [(t, f_s, "#566360") for t in _lignes(tmp, str(x["reference"]), f_s, cw - 28)]
            if len(dep.get("matieres", [])) != 1 or not dep.get("volume_ml"):
                ls.append((("Total " if dep.get("reunion") else "") + f"{fmt_vol(dep['volume_ml'])} mL" if dep.get("volume_ml") else "matière à saisir", f_n, "#0F6B5C"))
            cartes.append({"e": e, "ls": ls, "ps": [], "tl": [e["operation"].upper()], "tfont": f_bs, "pas": 24, "extra": 0, "bande": 0, "h": 80 + 30 * len(ls)})
            continue
        ls = []
        for r in (e.get("reactifs_detail") or [{"nom": n, "quantite": ""} for n in e.get("reactifs", [])]):
            if r.get("nom"):
                ls += [(t, f_b, "#14201D") for t in _lignes(tmp, "• " + r["nom"] + (" " + r["quantite"] if r.get("quantite") else ""), f_b, cw - 28)]
                if r.get("contact"):
                    ls += [(t, f_n, "#566360") for t in _lignes(tmp, f"   contact {r['contact']}", f_n, cw - 28)]
                if r.get("consigne"):
                    ls += [(t, f_n, "#8A4B00") for t in _lignes(tmp, f"   Consigne : {r['consigne']}", f_n, cw - 28)]
        cond = " · ".join(x for x in [conditions(e["parametres"])] + [f"{a['nom']} {a.get('valeur', '')}".strip() for a in e.get("autres", [])] if x)
        if cond:
            ls += [(t, f_n, "#0F6B5C") for t in _lignes(tmp, cond, f_n, cw - 28)]
        if e.get("equipement"):
            ls += [(t, f_s, "#566360") for t in _lignes(tmp, ", ".join(e["equipement"]), f_s, cw - 28)]
        if e.get("remarque"):
            ls += [(t, f_s, "#8A4B00") for t in _lignes(tmp, f"Consigne : {e['remarque']}", f_s, cw - 28)]
        tl, tfont, pas = _titre(tmp, e["operation"][:1].upper() + e["operation"][1:], cw - 72)
        extra = pas * (len(tl) - 1)
        ps = par_apres.get(e["n"], [])
        cartes.append({"e": e, "ls": ls, "ps": ps, "tl": tl, "tfont": tfont, "pas": pas, "extra": extra, "bande": 30 if e.get("groupe") else 0,
                       "h": (30 if e.get("groupe") else 0) + 70 + extra + 30 * len(ls) + 90})
    cases, liens, lettres = disposer(etapes, par_ligne)  # étapes en parallèle : une colonne par voie
    nb = max([r for r, _ in cases] + [0]) + 1
    hauteurs, hc_lignes = [], []
    for r in range(nb):
        grp = [cartes[i] for i, (rr, _) in enumerate(cases) if rr == r] or [{"h": 120, "ps": []}]
        hc_lignes.append(max(c["h"] for c in grp))
        hauteurs.append(hc_lignes[-1] + 64 * max(len(c["ps"]) for c in grp) + 50)
    haut_entree = 70 + (110 if any((e.get("parallele") or {}).get("depart") is not None for e in etapes) else 0)  # place pour la flèche d'entrée au-dessus du cadre
    img = Image.new("RGB", (largeur, haut_entree + sum(hauteurs) + 50), "white")
    d = ImageDraw.Draw(img)

    def pastille(x, y, p):
        l1 = f"{p['id']} · {fmt_vol(p['volume_ml'] or 0)} mL"
        l2 = moment_texte(p) + (f" · {p['labo']}" if p.get("labo") else "")  # laboratoire de l'échantillon
        w = int(max(d.textlength(l1, font=f_bs), d.textlength(l2, font=f_s)) + 64)
        d.rounded_rectangle([x, y, x + w, y + 54], 8, fill="#FDF1DC", outline="#8A4B00", width=2)
        d.ellipse([x + 8, y + 12, x + 38, y + 42], fill="#8A4B00")
        d.text((x + 23, y + 27), code_badge(p["id"]), font=f_bs, fill="white", anchor="mm")
        d.text((x + 48, y + 6), l1, font=f_bs, fill="#8A4B00")
        d.text((x + 48, y + 30), l2, font=f_s, fill="#8A4B00")
        return w

    d.text((0, 14), "ENTRÉE", font=f_bs, fill="#566360")
    px = d.textlength("ENTRÉE", font=f_bs) + 18
    for p in par_apres.get(0, []):
        px += pastille(px, 4, p) + 12
    ys, y = [], haut_entree
    for r in range(nb):
        ys.append(y)
        y += hauteurs[r]
    positions = []
    for idx, c in enumerate(cartes):
        r, k = cases[idx]
        positions.append((k * (cw + gap), ys[r], hc_lignes[r], r, k))
    blocs: dict[str, list[int]] = {}
    for idx, c in enumerate(cartes):
        pid = (c["e"].get("parallele") or {}).get("id")
        if pid:
            blocs.setdefault(pid, []).append(idx)
    for ids in blocs.values():  # cadre ambre autour de chaque bloc en parallèle
        x0 = min(positions[i][0] for i in ids) - 14
        x1 = max(positions[i][0] for i in ids) + cw + 14
        y_haut = min(positions[i][1] for i in ids) - 62
        y_bas = max(positions[i][1] + positions[i][2] + 64 * max(len(cartes[i]["ps"]) for i in ids) for i in ids) + 14
        d.rounded_rectangle([x0, y_haut, x1, y_bas], 16, fill="#FDF1DC", outline="#8A4B00", width=3)
        d.line([x0 + 18, y_haut + 12, x0 + 18, y_haut + 40], fill="#8A4B00", width=4)
        d.line([x0 + 30, y_haut + 12, x0 + 30, y_haut + 40], fill="#8A4B00", width=4)
        d.text((x0 + 46, y_haut + 26), "EN PARALLÈLE", font=f_bs, fill="#8A4B00", anchor="lm")
    for idx, c in enumerate(cartes):
        x, y0, hc, r, k = positions[idx]
        e = c["e"]
        if idx in lettres:  # début d'une voie
            d.text((x + 4, y0 - 20), f"VOIE {lettres[idx]}", font=f_bs, fill="#8A4B00")
        if e.get("virtuel"):  # Départ d'une voie : carte verte
            d.rounded_rectangle([x, y0, x + cw, y0 + hc], 12, fill="#E8F6EE", outline="#4AA064", width=4)
            d.text((x + 14, y0 + 14), c["tl"][0], font=f_bs, fill="#1B6B2A")
            ly = y0 + 50
            for t, font, coul in c["ls"]:
                d.text((x + 14, ly), t, font=font, fill=coul)
                ly += 30
            continue
        d.rounded_rectangle([x, y0, x + cw, y0 + hc], 12, fill="white", outline="#BFCBC7", width=3)
        yt = y0 + c["bande"]
        if c["bande"]:  # bandeau de la grande étape (ex. DEGUMMING)
            d.rounded_rectangle([x + 2, y0 + 2, x + cw - 2, y0 + 30], 10, fill="#E1F0EC")
            nom = e["groupe"].upper()
            while len(nom) > 3 and d.textlength(nom, font=f_bs) > cw - 30:
                nom = nom[:-2] + "…"
            d.text((x + 14, y0 + 16), nom, font=f_bs, fill="#0F6B5C", anchor="lm")
        d.ellipse([x + 12, yt + 12, x + 48, yt + 48], fill="#0F6B5C")
        d.text((x + 30, yt + 30), str(e["n"]), font=f_bs, fill="white", anchor="mm")
        for k_l, lg in enumerate(c["tl"]):
            d.text((x + 60, yt + 14 + k_l * c["pas"]), lg, font=c["tfont"], fill="#14201D")
        ly = yt + 62 + c["extra"]
        for t, font, coul in c["ls"]:
            d.text((x + 14, ly), t, font=font, fill=coul)
            ly += 30
        dur = e["parametres"].get("duree_min")
        if dur or c["ps"]:
            fy = y0 + hc - 66
            x0, x1 = x + 22, x + cw - 22
            d.line([x0, fy + 12, x1, fy + 12], fill="#C9D3CF", width=5)
            d.text((x0, fy + 36), "0", font=f_s, fill="#566360")
            dl = fmt_dur(dur) if dur else "fin"
            d.text((x1 - d.textlength(dl, font=f_s), fy + 36), dl, font=f_s, fill="#566360")
            for p in c["ps"]:
                pct = 1.0
                if p.get("moment") == "pendant":
                    pct = min(1, max(0, p["temps_min"] / dur)) if dur and p.get("temps_min") is not None else 0.5
                bx = x0 + (x1 - x0) * pct
                d.ellipse([bx - 15, fy - 3, bx + 15, fy + 27], fill="#8A4B00")
                d.text((bx, fy + 12), code_badge(p["id"]), font=f_bs, fill="white", anchor="mm")
        for j, p in enumerate(c["ps"]):
            pastille(x, y0 + hc + 12 + j * 64, p)
    gris = "#566360"
    for ia, ib in liens:
        xa0, ya0, ha, ra, ka = positions[ia]
        xb0, yb0, hb, rb, kb = positions[ib]
        if ra == rb and kb == ka + 1:
            ay = ya0 + 30
            d.line([xa0 + cw + 4, ay, xa0 + cw + gap - 8, ay], fill=gris, width=3)
            d.polygon([(xa0 + cw + gap - 4, ay), (xa0 + cw + gap - 14, ay - 7), (xa0 + cw + gap - 14, ay + 7)], fill=gris)
        elif rb > ra:
            xa, xb = xa0 + cw - 40, xb0 + cw - 40
            depart = ya0 + ha + 64 * len(cartes[ia]["ps"]) + 4
            ym = yb0 - 22
            d.line([xa, depart, xa, ym, xb, ym, xb, yb0 - 10], fill=gris, width=3, joint="curve")
            d.polygon([(xb, yb0 - 2), (xb - 8, yb0 - 14), (xb + 8, yb0 - 14)], fill=gris)
    entrants, sortants = {ib for _, ib in liens}, {ia for ia, _ in liens}
    y_entree = min((positions[i][1] - (62 if (cartes[i]["e"].get("parallele") or {}).get("id") else 0) for i in range(len(cartes)) if i not in entrants),
                   default=haut_entree) - 28
    d.line([8, 40, 8, max(y_entree, 44)], fill=gris, width=3)
    for i in (k for k in range(len(cartes)) if k not in entrants):  # ENTRÉE → première(s) carte(s)
        x, y0 = positions[i][0], positions[i][1]
        xe = x + cw - 40
        d.line([8, max(y_entree, 44), xe, max(y_entree, 44), xe, y0 - 10], fill=gris, width=3, joint="curve")
        d.polygon([(xe, y0 - 2), (xe - 8, y0 - 14), (xe + 8, y0 - 14)], fill=gris)
    y = ys[-1] + hauteurs[-1]
    so = "SORTIE · produit prétraité"
    x_so = largeur - d.textlength(so, font=f_bs) - 16
    for i in (k for k in range(len(cartes)) if k not in sortants):  # dernière(s) carte(s) → SORTIE
        x, y0, hc, r, k = positions[i]
        bas = y0 + hc + 64 * len(cartes[i]["ps"]) + 6
        xs = x + cw - 40
        d.line([xs, bas, xs, y - 20, x_so - 6, y - 20], fill=gris, width=3, joint="curve")
        d.polygon([(x_so, y - 20), (x_so - 12, y - 27), (x_so - 12, y - 13)], fill=gris)
    d.text((largeur - d.textlength(so, font=f_bs), y - 30), so, font=f_bs, fill="#566360")
    return img


def ecrire(par, texte, taille=None, gras=False, couleur=None):
    """Ajoute du texte ; les repères « [… à saisir] » sont surlignés en jaune."""
    for seg in REPERE.split(texte):
        if not seg:
            continue
        run = par.add_run(seg)
        run.bold = gras
        if taille:
            run.font.size = Pt(taille)
        if couleur:
            run.font.color.rgb = RGBColor.from_string(couleur)
        if REPERE.fullmatch(seg):
            run.font.highlight_color = WD_COLOR_INDEX.YELLOW
            run.font.color.rgb = RGBColor.from_string("7A4A00")


def fond(cell, couleur):
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), couleur)
    tc_pr.append(shd)


def manque(v):
    return str(v) if v not in (None, "") else "[à saisir]"


def ecrire_docx(data: dict, chemin) -> None:
    ctx, etapes, pre = data.get("contexte", {}), data["etapes"], data.get("prelevements", [])
    inv = {r["nom"].lower(): r for r in data.get("inventaire_reactifs", [])}
    doc = Document()
    doc.core_properties.title = data.get("titre", "Manip")
    doc.core_properties.author = "Mat & Méthode"
    sec = doc.sections[0]
    sec.page_width, sec.page_height = Cm(21), Cm(29.7)
    sec.left_margin = sec.right_margin = sec.top_margin = sec.bottom_margin = Cm(2)
    normal = doc.styles["Normal"]
    normal.font.name = "Segoe UI"
    normal.font.size = Pt(10)
    normal.element.rPr.rFonts.set(qn("w:eastAsia"), "Segoe UI")
    for nom, taille, coul in (("Title", 20, "14201D"), ("Heading 1", 14, TEAL), ("Heading 2", 12, TEAL), ("Heading 3", 10.5, "14201D")):
        st = doc.styles[nom]
        st.font.name, st.font.size, st.font.bold = "Segoe UI", Pt(taille), True
        st.font.color.rgb = RGBColor.from_string(coul)

    doc.add_paragraph(data.get("titre", "Manip"), style="Title")
    t = doc.add_table(rows=1, cols=1)
    t.style = "Table Grid"
    c0 = t.rows[0].cells[0]
    fond(c0, "E1F0EC")
    p0 = c0.paragraphs[0]
    ecrire(p0, "Donneur d’ordre : ", gras=True)
    ecrire(p0, f"{manque(ctx.get('donneur'))}     ")
    if ctx.get("type"):
        ecrire(p0, "Type : ", gras=True)
        ecrire(p0, f"{ctx['type']}     ")
    ecrire(p0, "Réf. demande : ", gras=True)
    ecrire(p0, f"{manque(ctx.get('ref'))}     ")
    ecrire(p0, "Date : ", gras=True)
    ecrire(p0, str(ctx.get("date", "")))
    if ctx.get("experience") or ctx.get("attribue"):
        pe = c0.add_paragraph()
        ecrire(pe, "N° d’expérience : ", gras=True)
        ecrire(pe, f"{ctx.get('experience') or '-'}     ")
        ecrire(pe, "Attribuée à : ", gras=True)
        ecrire(pe, ctx.get("attribue") or "-")
    if ctx.get("reperes"):
        pr = c0.add_paragraph()
        ecrire(pr, "Étapes : ", gras=True)
        ecrire(pr, " ; ".join(f"{x['initiale']} : {x['materiel']}" if x["materiel"] else x["initiale"] for x in ctx["reperes"]))
    if ctx.get("tags"):
        p1 = c0.add_paragraph()
        ecrire(p1, "Tags : ", gras=True)
        ecrire(p1, "  ".join("#" + x for x in ctx["tags"]))
    lanc, jr = data.get("lancee"), data.get("journal") or []
    p2 = c0.add_paragraph()
    ecrire(p2, "Version : ", gras=True)
    ecrire(p2, f"{data.get('version', 1)} · enregistrée le {fmt_dt(data.get('enregistree_le'))}"
           + (f" · lancée le {fmt_dt(lanc['le'])} par {lanc['par']}" if lanc else ""))
    if lanc and jr:
        ecrire(c0.add_paragraph(), f"Modifiée après lancement ({len(jr)})", gras=True, couleur=AMBER)

    if data.get("a_faire"):
        doc.add_heading(f"À faire ({len(data['a_faire'])} point(s) non coché(s))", level=2)
        taf = doc.add_table(rows=1, cols=2)
        taf.style = "Table Grid"
        for k, h in enumerate(("Catégorie", "À faire")):
            fond(taf.rows[0].cells[k], "E1F0EC")
            ecrire(taf.rows[0].cells[k].paragraphs[0], h, 8.5, gras=True)
        for x in data["a_faire"]:
            cells = taf.add_row().cells
            ecrire(cells[0].paragraphs[0], "☐ " + (x.get("categorie") or ""), 8.5)
            ecrire(cells[1].paragraphs[0], x.get("texte") or "", 8.5)

    doc.add_heading("Flux de prétraitement", level=1)
    buf = io.BytesIO()
    image_flux(etapes, pre).save(buf, format="PNG", dpi=(250, 250))
    buf.seek(0)
    doc.add_picture(buf, width=Cm(17))
    doc.inline_shapes[-1]._inline.docPr.set("descr", "Schéma du flux : une carte par étape, badges des échantillons sur la frise du temps")
    if data.get("grandes_etapes"):
        ecrire(doc.add_paragraph(), "Grandes étapes : " + " ; ".join(f"{g['nom']} ({plage(g['etapes'])})" for g in data["grandes_etapes"]) + ".",
               8.5, couleur=MUTED)
    vd = ctx.get("volumeDepart")
    if phrase_volumes(data):
        ecrire(doc.add_paragraph(), phrase_volumes(data) + " Chaque badge marque un prélèvement : sa place sur la frise donne le moment (bord droit = sortie de l’étape).", 8.5, couleur=MUTED)

    doc.add_heading("Matériel et méthodes", level=1)
    for ss in data.get("sous_sections", []):
        if ss.get("texte"):
            doc.add_heading(ss["titre"], level=3)
            for x in ss["texte"].split("\n"):  # un paragraphe par ligne
                if x:
                    ecrire(doc.add_paragraph(), x)

    doc.add_heading("Détail par phase du flux", level=1)
    for i, ph in enumerate(data.get("phases", [])):
        if _depart_commun(ph, i):
            entete = (f"{ctx.get('matiere') or ''}" + (f" · n° Scirius {ctx['scirius']}" if ctx.get("scirius") else "")
                      + (f" · fournisseur {ctx['fournisseur']}" if ctx.get("fournisseur") else "")
                      + (f" · emplacement {ctx['emplacement']}" if ctx.get("emplacement") else "")) + (f" · {fmt_vol(vd)} mL" if vd is not None else "")
        elif ph.get("reunion_voies"):  # volume de chaque voie, puis le total
            entete = "\n".join(f"{r['nom']} · {r['quantite']}" for r in ph["reactifs"]) + f"\n{ph.get('conditions') or ''}"
        else:
            entete = (ph.get("conditions") or ("" if ph.get("entree_voies") else "conditions à compléter")) + (" — " + ", ".join(ph["materiel"]) if ph.get("materiel") else "") + (
                f"\nConsigne / remarque : {ph['remarque']}" if ph.get("remarque") else "")
        lignes = [((ph["parallele"] + "\n" if ph.get("parallele") else "") + (ph["groupe"].upper() + " · " if ph.get("groupe") else "") + ph["titre"]
                   + ("\n" + ph["reunion"] if ph.get("reunion") else ""), entete)]
        if not _depart_commun(ph, i) and not ph.get("entree_voies") and not ph.get("reunion_voies"):
            lignes.append(("Réactifs", "\n".join(
                f"• {r['nom']}{' · ' + r['quantite'] if r.get('quantite') else ''}{' · contact ' + r['contact'] if r.get('contact') else ''}"
                f"{' · Consigne : ' + r['consigne'] if r.get('consigne') else ''} — n° Scirius {manque(r.get('scirius'))}, "
                f"emplacement {manque(r.get('emplacement'))}, fournisseur {manque(r.get('fournisseur'))}"
                for r in ph["reactifs"]) or "aucun"))
        if not ph.get("depart_voie") and not ph.get("reunion_voies"):
            lignes.append(("Échantillons", "\n".join(
                f"{x['id']} · {fmt_vol(x['volume'] or 0)} mL · {x['moment']} · {x.get('labo', '')} · {', '.join(x.get('analyses', [])) or 'aucune analyse'} — "
                f"n° Scirius {manque(x.get('scirius'))}, n° Aramis {manque(x.get('aramis'))}"
                + (f"\nCommentaire : {x['commentaire']}" if x.get("commentaire") else "") for x in ph["echantillons"]) or "aucun"))
        tab = doc.add_table(rows=len(lignes), cols=2)
        tab.style = "Table Grid"
        tab.autofit = False
        for k, (lab, txt) in enumerate(lignes):
            c1, c2 = tab.rows[k].cells
            c1.width, c2.width = Cm(3), Cm(14)
            ecrire(c1.paragraphs[0], lab, 9, gras=True, couleur=TEAL if k == 0 else MUTED)
            ecrire(c2.paragraphs[0], txt, 9)
            if k == 0:
                fond(c1, "E1F0EC")
                fond(c2, "E1F0EC")
        doc.add_paragraph().paragraph_format.space_after = Pt(2)

    def tableau(titre, entetes, lignes, largeurs):
        doc.add_heading(titre, level=2)
        tb = doc.add_table(rows=1, cols=len(entetes))
        tb.style = "Table Grid"
        tb.autofit = False
        for k, h in enumerate(entetes):
            cell = tb.rows[0].cells[k]
            cell.width = Cm(largeurs[k])
            fond(cell, "E1F0EC")
            ecrire(cell.paragraphs[0], h, 8.5, gras=True)
        for ligne in lignes:
            cells = tb.add_row().cells
            for k, v in enumerate(ligne):
                cells[k].width = Cm(largeurs[k])
                ecrire(cells[k].paragraphs[0], manque(v), 8.5)

    noms: list[tuple[str, list[int]]] = []
    for e in etapes:
        for r in e.get("reactifs_detail") or [{"nom": n} for n in e.get("reactifs", [])]:
            if not r.get("nom"):
                continue
            x = next((y for y in noms if y[0].lower() == r["nom"].lower()), None)
            if x is None:
                noms.append((r["nom"], [e["n"]]))
            elif e["n"] not in x[1]:
                x[1].append(e["n"])
    if noms:
        tableau("Réactifs", ["Réactif", "N° Scirius", "Emplacement", "Fournisseur", "Étape"],
                [[nm] + [inv.get(nm.lower(), {}).get(k) for k in ("scirius", "emplacement", "fournisseur")] + [", ".join(map(str, st))]
                 for nm, st in noms], [3.6, 2.4, 5.2, 3.4, 2.4])
    if pre:
        tableau("Échantillons", ["Éch.", "Étape", "Moment", "Volume", "N° Scirius", "N° Aramis", "Laboratoire", "Analyses"],
                [[p["id"], "entrée" if not p["apres_etape"] else f"{p['apres_etape']} · {etapes[p['apres_etape'] - 1]['operation']}", moment_texte(p),
                  f"{fmt_vol(p['volume_ml'] or 0)} mL", p.get("scirius"), p.get("aramis"), p.get("labo"), ", ".join(p.get("analyses", []))] for p in pre],
                [1.2, 3.0, 2.4, 1.7, 1.9, 1.9, 2.0, 2.9])
    res = data.get("resultats")
    if res and res.get("echantillons"):  # résultats lus dans ana explorer
        from mat_methode.analyses_ptt import tableaux
        n = len(res["echantillons"])
        for k, (entetes, lignes) in enumerate(tableaux(res, 6)):
            nb = len(entetes) - 1
            tableau("Résultats d’analyses" if k == 0 else "Résultats d’analyses (suite)", entetes,
                    [[ln[0].replace("\n", " · ")] + ln[1:] for ln in lignes], [3.5] + [13.5 / max(nb, 1)] * nb)
            if k == 0:
                ecrire(doc.add_paragraph(), f"{n} échantillon{'s' if n > 1 else ''} avec des résultats, retrouvé{'s' if n > 1 else ''} par le n° Aramis dans ana explorer"
                       + (f" ({res['source']})" if res.get("source") else "") + ". « — » : pas de résultat.", 8, couleur=MUTED)
    figs = [f for f in data.get("figures_ana") or [] if Path(f.get("chemin", "")).exists()]
    if figs:  # tableau / graphiques envoyés depuis ana explorer
        doc.add_heading("Tableaux et graphiques (ana explorer)", level=2)
        for f in figs:
            try:
                doc.add_picture(f["chemin"], width=Cm(17))
            except Exception:  # image illisible : ignorée
                continue
            ecrire(doc.add_paragraph(), f"{f.get('libelle', '')}" + (f" · {f['titre']}" if f.get("titre") else "")
                   + (f" — {f['sous_titre']}" if f.get("sous_titre") else "") + f" (ana explorer, {f.get('le', '')})", 8, couleur=MUTED)
    if data.get("photos"):  # photos SamplesTEK des échantillons, 3 par ligne
        doc.add_heading("Photos des échantillons (SamplesTEK)", level=2)
        for e in data["photos"]:
            ph = [x for x in e.get("photos", []) if Path(x.get("miniature") or x.get("fichier") or "").exists()]
            if not ph:
                continue
            ecrire(doc.add_paragraph(), f"{e['id']} · n° Aramis {e.get('aramis', '')}", 9.5, gras=True)
            tb = doc.add_table(rows=(len(ph) + 2) // 3, cols=3)
            for k, x in enumerate(ph):
                cell = tb.rows[k // 3].cells[k % 3]
                try:
                    cell.paragraphs[0].add_run().add_picture(x.get("miniature") or x["fichier"], width=Cm(5.3))
                except Exception:  # photo illisible : ignorée
                    continue
                ecrire(cell.add_paragraph(), x.get("legende", "") + (f"\n{x['commentaire']}" if x.get("commentaire") else ""), 8, couleur=MUTED)
    if lanc:
        if jr:
            tableau("Modifications après lancement", ["Date et heure", "Par", "Modification"],
                    [[fmt_dt(j["t"]), j["par"], j["txt"]] for j in jr], [3.6, 2.6, 10.8])
        else:
            doc.add_heading("Modifications après lancement", level=2)
            ecrire(doc.add_paragraph(), "Aucune modification depuis le lancement.")

    if data.get("statuts"):
        tableau("Historique des statuts", ["Date et heure", "Par", "Changement de statut"],
                [[fmt_dt(c["t"]), c.get("nom") or c.get("par"), f"{c.get('de', '')} → {c.get('vers', '')}"] for c in data["statuts"]],
                [3.6, 4.6, 8.8])

    ecrire(sec.footer.paragraphs[0], "Document généré automatiquement - à relire avant diffusion", 8, couleur=MUTED)
    doc.save(str(chemin))
