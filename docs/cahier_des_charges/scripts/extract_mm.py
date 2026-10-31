"""Extrait la section « Matériel et méthodes » d'un rapport PDF.

Usage : python3 extract_mm.py rapport.pdf [--json mm.json] [--md mm.md]

Étapes : texte par page -> retrait des en-têtes/pieds de page -> repérage des titres
-> section M&M découpée en sous-sections -> matériel, réactifs et étapes structurés.
Heuristique : les étapes sont à relire (champ "a_verifier").
"""
import argparse
import json
import re
import unicodedata
from collections import Counter

import pdfplumber


def sans_accent(t):
    return "".join(c for c in unicodedata.normalize("NFD", t or "") if unicodedata.category(c) != "Mn").lower()


# --- Titres ---------------------------------------------------------------------------
TITRE_NUM = re.compile(r"^(\d{1,2}(?:\.\d{1,2})*)\.?\s+(\S.*)$")
DEBUT_MM = re.compile(r"^(materiels?\s*(et|&)\s*methodes?|materials\s+and\s+methods?)\b")
TITRE_CONNU = re.compile(r"^(introduction|resultats?|discussion|conclusions?|references|bibliographie|annexes?|"
                         r"results|materiels?\s*(et|&)\s*methodes?|materials\s+and\s+methods?)\b")
SOMMAIRE = re.compile(r"(\.{3,}|\s\.\s\.)\s*\d*\s*$")  # « ....... 2 » : ligne de sommaire


def analyser_titre(ligne):
    """Retourne (niveau, numéro, titre) si la ligne ressemble à un titre, sinon None."""
    if SOMMAIRE.search(ligne):
        return None
    m = TITRE_NUM.match(ligne)
    if m and m.group(2)[0].isupper() and len(ligne) < 80 and not ligne.endswith("."):
        return len(m.group(1).split(".")), m.group(1), m.group(2)
    if TITRE_CONNU.match(sans_accent(ligne)) and len(ligne) < 40:
        return 1, "", ligne  # titre non numéroté (liste de titres connus, pour éviter les faux positifs)
    return None


# --- Lecture du PDF ---------------------------------------------------------------------
def lignes_propres(pdf):
    """Lignes (page, texte) sans en-têtes ni pieds de page répétés."""
    pages = [(p.extract_text() or "").splitlines() for p in pdf.pages]
    cle = lambda l: re.sub(r"\d+", "#", l.strip())
    bords = Counter(cle(l) for lignes in pages for l in lignes[:2] + lignes[-2:])
    sortie = []
    for n, lignes in enumerate(pages, 1):
        for i, l in enumerate(lignes):
            en_bord = i < 2 or i >= len(lignes) - 2
            if l.strip() and not (en_bord and bords[cle(l)] >= 2 and len(pages) > 1):
                sortie.append((n, l.strip()))
    return sortie


def trouver_section(lignes):
    debut = niveau = None
    for i, (_, l) in enumerate(lignes):
        t = analyser_titre(l)
        if t and DEBUT_MM.match(sans_accent(t[2])):
            debut, niveau = i, t[0]
            break
    if debut is None:
        return None
    fin = len(lignes)
    for j in range(debut + 1, len(lignes)):
        t = analyser_titre(lignes[j][1])
        if t and t[0] <= niveau:
            fin = j
            break
    return lignes[debut:fin], niveau


def decouper(section, niveau):
    """Sous-sections [{titre, texte, pages}] ; les lignes sont recollées en paragraphes."""
    blocs, courant = [], {"titre": section[0][1], "lignes": [], "pages": set()}
    for page, l in section[1:]:
        t = analyser_titre(l)
        if t and t[0] > niveau:
            blocs.append(courant)
            courant = {"titre": l, "lignes": [], "pages": set()}
        else:
            courant["lignes"].append(l)
            courant["pages"].add(page)
    blocs.append(courant)
    for b in blocs:
        texte = ""
        for l in b.pop("lignes"):
            texte = texte[:-1] + l if texte.endswith("-") and l[:1].islower() else (texte + " " + l).strip()
        b["texte"], b["pages"] = texte, sorted(b["pages"])
    return blocs


# --- Vocabulaires et paramètres ---------------------------------------------------------
EQUIPEMENTS = ["plaque chauffante agitatrice", "entonnoir Büchner", "fiole à vide", "ampoule à décanter",
               "étuve", "centrifugeuse", "bain-marie", "broyeur", "évaporateur rotatif", "membrane"]
REACTIF = re.compile(
    r"\b(?:éthanol|ethanol|acétone|acetone|hexane|méthanol|methanol|isopropanol|"
    r"eau distillée|eau déminéralisée|eau distillee|acide (?:phosphorique|citrique|sulfurique|chlorhydrique)|"
    r"soude|hydroxyde de sodium|chlorure de sodium)"
    r"(?:\s+(?:à\s+)?(\d+(?:[.,]\d+)?)\s*%|\s+absolu)?", re.I)
OPERATIONS = {"chauffage": "chauff", "filtration": "filtr", "désacidification": "désacidif",
              "décantation": "décant", "séchage": "séch", "centrifugation": "centrifug",
              "lavage": "lav[ée]", "broyage": "broy"}
NB = r"(\d+(?:[.,]\d+)?)"


def nombre(s):
    return float(s.replace(",", "."))


def lister_equipements(texte):
    t = sans_accent(texte)
    return [e for e in EQUIPEMENTS if sans_accent(e) in t]


def lister_reactifs(texte):
    vus = []
    for m in REACTIF.finditer(texte):
        nom = m.group(0).lower().replace("à ", "").strip()
        nom = re.sub(r"\s+", " ", nom).replace("ethanol", "éthanol").replace("acetone", "acétone")
        nom = nom.replace("distillee", "distillée")
        nom = re.sub(r"(\d+)\s*%", r"\1 %", nom)
        if nom not in vus:
            vus.append(nom)
    return vus


def parametres(clause):
    p = {}
    for cle, motif, conv in [
        ("temperature_c", NB + r"\s*°\s*C", nombre),
        ("agitation_trmin", r"(\d+)\s*tr/min", int),
        ("filtre_um", NB + r"\s*µm", nombre),
    ]:
        m = re.search(motif, clause)
        if m:
            p[cle] = conv(m.group(1))
    m = re.search(NB + r"\s*(min|h)\b", clause)
    if m:
        p["duree_min"] = nombre(m.group(1)) * (60 if m.group(2) == "h" else 1)
    m = re.search(r"(\d+)\s*:\s*(\d+)", clause)
    if m:
        p["ratio"] = f"{m.group(1)}:{m.group(2)}"
    return p


def extraire_etapes(texte):
    etapes = []
    phrases = re.split(r"(?<=[.!?])\s+(?=[A-ZÉÈÀÂÊÎÔÛ])", texte)
    for phrase in phrases:
        for clause in re.split(r",\s*(?:puis|enfin|et enfin)\s+|;\s+", phrase):
            sans_materiel = clause
            for e in EQUIPEMENTS:  # « ampoule à décanter » ne doit pas compter comme une décantation
                sans_materiel = re.sub(re.escape(e), " ", sans_materiel, flags=re.I)
            ops = sorted((m.start(), nom) for nom, motif in OPERATIONS.items()
                         for m in [re.search(motif, sans_materiel, re.I)] if m)
            if not ops:
                continue
            reactifs = lister_reactifs(clause)
            etapes.append({
                "n": len(etapes) + 1, "operation": ops[0][1], "phrase": clause.strip(" ."),
                "parametres": parametres(clause), "equipement": lister_equipements(clause),
                "reactifs": reactifs,
                "a_verifier": len({nom for _, nom in ops}) > 1,
            })
    return etapes


# --- Programme --------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("--json", default="mm_extrait.json")
    ap.add_argument("--md", default="mm_extrait.md")
    a = ap.parse_args()

    with pdfplumber.open(a.pdf) as pdf:
        lignes = lignes_propres(pdf)
    alertes = []
    if not lignes:
        alertes.append("Aucun texte : PDF scanné ? Une étape OCR est nécessaire.")
    trouve = trouver_section(lignes) if lignes else None
    if lignes and not trouve:
        alertes.append("Section « Matériel et méthodes » introuvable.")

    res = {"source": a.pdf, "alertes": alertes}
    if trouve:
        section, niveau = trouve
        blocs = decouper(section, niveau)
        tout = " ".join(b["texte"] for b in blocs)
        res.update({
            "titre": section[0][1],
            "pages": sorted({p for p, _ in section}),
            "sous_sections": blocs,
            "materiel": lister_equipements(tout),
            "reactifs": lister_reactifs(tout),
            "etapes": extraire_etapes(next(
                (b["texte"] for b in blocs if re.match(r"methodes?\b", sans_accent(re.sub(r"^[\d.]+\s*", "", b["titre"])))),
                tout)),
        })
        if not res["etapes"]:
            alertes.append("Aucune étape reconnue : à saisir à la main.")
        md = [f"## {res['titre']}", ""]
        for b in blocs:
            md += [f"### {b['titre']}", "", b["texte"], ""] if b["texte"] else []
        with open(a.md, "w", encoding="utf-8") as f:
            f.write("\n".join(md))
    with open(a.json, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=2)
    print(json.dumps(res, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
