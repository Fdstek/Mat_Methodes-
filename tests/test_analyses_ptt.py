"""Résultats d'analyses lus dans le classeur d'ana explorer (« Récapitulatif Analyses PTT.xlsm »), sur un faux classeur."""
import json
import os

import pdfplumber
from openpyxl import Workbook

from mat_methode import analyses_ptt as A
from mat_methode.exports.echange import exporter

ENTETE = ["N° expérience", "Produit", "Contexte", "Date", "Type expérience", "N° ARAMIS", "N° SCIRIUS", "Labo",
          "Phosphore", "Azote", "Chlore total", "FFA Exprimé en acide oléique", "Phosphore2", "Indice de peroxyde", "Commentaire"]
UNITES = ["", "", "", "", "", "", "", "", "mg/kg", "mg/kg", "mg/kg", "% (m/m)", "mg/kg", "meq AO/kg", ""]


def classeur(chemin):
    wb = Workbook()
    ws = wb.active
    ws.title = "Suivi analyses"
    ws.cell(1, 1, "Récapitulatif des analyses PTT")
    for i, u in enumerate(UNITES, start=1):
        ws.cell(3, i, u or None)
    for i, h in enumerate(ENTETE, start=1):
        ws.cell(4, i, h)
    lignes = [
        ["12", "Graisse", "essai", "2026-10-02", "1-charge", 2026001234.0, "001245", "CRES", 12.5, 300, None, "1,2", None, None, "ok"],
        ["12", "Graisse", "essai", "2026-10-03", "1-charge", "2026001234", "001245", "ATCO", None, None, 41, None, None, None, ""],
        ["12", "Graisse", "essai", "2026-10-05", "1-charge", "2026-005555", "", "BV Inspectorate", None, "<5", None, None, 3.4, 2.1, ""],
        ["12", "Graisse", "essai", "2026-10-05", "1-charge", "-", "", "CRES", None, None, None, None, None, None, "pas de n°"],
    ]
    for k, ln in enumerate(lignes, start=5):
        for i, v in enumerate(ln, start=1):
            ws.cell(k, i, v)
    wb.save(chemin)
    return chemin


def test_lecture_et_consolidation(tmp_path):
    d = A.lire_classeur(classeur(tmp_path / A.FICHIER))
    assert len(d["lignes"]) == 3  # la ligne sans n° est ignorée
    assert d["analyses"][:4] == ["Phosphore", "Azote", "Chlore total", "FFA"] and "Indice de peroxyde" in d["analyses"]
    assert "Commentaire" not in d["analyses"]
    assert d["unites"]["Phosphore"] == "ppm" and d["unites"]["FFA"] == "%" and d["unites"]["Indice de peroxyde"] == "meq AO/kg"
    r = A.Resultats.depuis(d)
    assert len(r.lignes_de("2026001234", None)) == 2  # CRES + ATCO, « 2026001234.0 » = « 2026001234 »
    res = r.pour_export([{"id": "S1", "aramis": "2026001234", "scirius": None}, {"id": "S2", "aramis": "2026-005555"},
                         {"id": "S3", "aramis": "", "scirius": "001245"}, {"id": "S4", "aramis": "999"}])
    e1, e2, e3 = res["echantillons"]
    assert [e["id"] for e in res["echantillons"]] == ["S1", "S2", "S3"]  # S4 : pas de résultat ; S3 retrouvé par son n° Scirius
    assert e1["valeurs"] == {"Phosphore": "12,5", "Azote": "300", "Chlore total": "41", "FFA": "1,2"}
    assert e1["sources"]["Chlore total"] == "ATCO" and e1["labos"] == ["CRES", "ATCO"]
    assert e2["valeurs"]["Phosphore"] == "3,4" and e2["sources"]["Phosphore"] == "BV Inspectorate"  # colonne BV « Phosphore2 »
    assert e2["valeurs"]["Azote"] == "<5" and "Phosphore2" not in e2["valeurs"]
    assert A.resume_echantillon(res, "S2").startswith("Phosphore 3,4 ppm · Azote <5")
    entetes, lignes = A.tableaux(res)[0]
    assert entetes[:3] == ["Échantillon", "Phosphore (ppm)", "Azote (ppm)"]
    assert lignes[0][:3] == ["S1\n2026001234\nCRES, ATCO", "12,5", "300"] and lignes[1][2] == "<5" and len(lignes) == 3
    assert len(A.tableaux(res, 2)) == 3  # 5 analyses, 2 par tableau


def test_source_et_cache(tmp_path):
    (tmp_path / "Data").mkdir()
    f = classeur(tmp_path / "Data" / A.FICHIER)
    src = A.SourceAnalyses(tmp_path / "cache", racines=[], ana_explorer=lambda: f)
    r = src.lire()
    assert "fichier d’ana explorer" in r.origine and "2026001234" in r.par_aramis
    assert json.loads((tmp_path / "cache" / A.CACHE).read_text(encoding="utf-8"))["source"] == str(f)
    # classeur inaccessible : la dernière lecture partagée sert encore
    os.remove(f)
    r2 = A.SourceAnalyses(tmp_path / "cache", racines=[], ana_explorer=lambda: f).lire()
    assert "dernière lecture" in r2.origine and "2026001234" in r2.par_aramis
    vide = A.SourceAnalyses(tmp_path / "autre", racines=[], ana_explorer=lambda: None).lire()
    assert vide.vide and "introuvable" in vide.ecartes[0]


def test_documents_avec_resultats(ethanol, reglages, tmp_path):
    from mat_methode.exports.pdf import ecrire_pdf
    from mat_methode.exports.protocole import ecrire_protocole
    from mat_methode.exports.word import ecrire_docx
    ethanol.prelevements[0].aramis = "2026001234"
    data = exporter(ethanol, reglages)
    r = A.Resultats.depuis(A.lire_classeur(classeur(tmp_path / A.FICHIER)), "essai")
    data["resultats"] = r.pour_export(data["prelevements"])
    ident = data["resultats"]["echantillons"][0]["id"]
    for ecrire, nom in ((ecrire_pdf, "r.pdf"), (ecrire_protocole, "p.pdf")):
        ecrire(data, tmp_path / nom)
        with pdfplumber.open(tmp_path / nom) as pdf:
            texte = " ".join(" ".join(p.extract_text() for p in pdf.pages).split())
        assert "Résultats d’analyses" in texte and "Phosphore (ppm)" in texte and "12,5" in texte, nom
    assert f"Résultats {ident} : Phosphore 12,5 ppm" in texte  # protocole : résultats sous l'échantillon, dans sa phase
    import docx
    ecrire_docx(data, tmp_path / "r.docx")
    d = docx.Document(str(tmp_path / "r.docx"))
    assert any("Résultats d’analyses" in p.text for p in d.paragraphs)
    assert any(c.text == "12,5" for t in d.tables for row in t.rows for c in row.cells)


def test_carte_resultats_rapport_et_protocole(qtbot, tmp_path, qapp):
    from PySide6.QtWidgets import QTableWidget

    from mat_methode.storage.stockage import Stockage
    from mat_methode.ui import theme
    from mat_methode.ui.controleur import Controleur
    from mat_methode.ui.fenetre import Fenetre
    from mat_methode.ui.widgets import Expander
    theme.appliquer(qapp, "clair")
    ctrl = Controleur(Stockage(tmp_path, "pierre", "PC1"))
    f = Fenetre(ctrl)
    qtbot.addWidget(f)
    ctrl.demarrer()
    m = next(x for x in ctrl.manips if x.nom == "Désacidification éthanol")
    m.prelevements[0].aramis = "2026001234"
    ctrl._analyses = A.Resultats.depuis(A.lire_classeur(classeur(tmp_path / A.FICHIER)), "essai")
    f.ouvrir(m.id)
    f.p_rapport.rafraichir()
    carte = next(x for x in f.p_rapport.findChildren(Expander) if x._titre == "Résultats d’analyses")
    t = carte.findChild(QTableWidget)
    assert t.horizontalHeaderItem(3).text() == "PHOSPHORE (PPM)" and t.item(0, 0).text() == "S0" and t.item(0, 3).text() == "12,5"
    assert "ATCO" in t.item(0, 5).toolTip() and t.item(0, 2).text() == "CRES, ATCO"
    f.p_protocole.rafraichir()
    assert any(x._titre == "Résultats d’analyses" for x in f.p_protocole.findChildren(Expander))
    ctrl.fermer()
