"""Lien avec ana explorer : demande de recherche, lancement, images renvoyées (tableau, graphiques) dans les documents."""
import json
import time

import pdfplumber
from PIL import Image

from mat_methode import lien_ana as L
from mat_methode.exports.echange import exporter


def image(chemin, couleur=(15, 108, 189), fiche=None):
    chemin.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (800, 400), couleur).save(chemin)
    if fiche is not None:
        chemin.with_suffix(".json").write_text(json.dumps(fiche, ensure_ascii=False), encoding="utf-8")
    return chemin


def test_demande_et_lancement(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    lien = L.dossier_lien()
    assert not L.ana_ouvert()
    # ana explorer déjà ouvert (signe de vie récent) : la demande suffit, rien n'est lancé
    lien.mkdir(parents=True)
    (lien / "instance.json").write_text(json.dumps({"pid": 1, "t": time.time()}), encoding="utf-8")
    lances = []
    monkeypatch.setattr(L.subprocess, "Popen", lambda *a, **k: lances.append(a))
    msg = L.ouvrir_ana("EXP-2026-014", "abc", "Essai", tmp_path / "donnees" / "analyses" / "abc")
    d = json.loads((lien / "demande.json").read_text(encoding="utf-8"))
    assert d["recherche"] == "EXP-2026-014" and d["retour"].endswith("abc") and "déjà ouvert" in msg and not lances
    # ana explorer fermé : il est lancé, avec le programme qu'il a noté dans ses réglages
    (lien / "instance.json").write_text(json.dumps({"pid": 1, "t": time.time() - 60}), encoding="utf-8")
    exe = tmp_path / "PTT_Analysis_Explorer.exe"
    exe.write_bytes(b"")
    (L.dossier_ana() / "settings.json").write_text(json.dumps({"exe": str(exe)}), encoding="utf-8")
    assert L.exe_auto() == str(exe)
    L.ouvrir_ana("EXP-2026-014", "abc", "Essai", tmp_path / "r")
    assert lances and lances[0][0] == [str(exe)]
    assert L.commande("C:/x/ptt_analysis_app_v48.py")[-1] == "C:/x/ptt_analysis_app_v48.py" and L.commande("C:/x/a.exe") == ["C:/x/a.exe"]
    # programme introuvable : message clair
    (L.dossier_ana() / "settings.json").write_text("{}", encoding="utf-8")
    try:
        L.ouvrir_ana("X", "abc", "Essai", tmp_path / "r")
        raise AssertionError("aurait dû échouer")
    except FileNotFoundError as ex:
        assert "Réglages" in str(ex)


def test_figures_documents_et_retrait(ethanol, reglages, tmp_path):
    from mat_methode.exports.pdf import ecrire_pdf
    from mat_methode.exports.protocole import ecrire_protocole
    from mat_methode.exports.word import ecrire_docx
    d = L.dossier_retour(tmp_path, ethanol.id)
    image(d / "20261110-101500_tableau.png", fiche={"type": "tableau", "titre": "EXP-2026-014 | Graisse", "le": "10/11/2026 10:15", "par": "PB"})
    image(d / "20261110-101600_graphiques.png", (247, 99, 12))
    figs = L.figures(tmp_path, ethanol.id)
    assert [f["libelle"] for f in figs] == ["Tableau", "Graphiques"] and figs[0]["titre"] == "EXP-2026-014 | Graisse"
    data = exporter(ethanol, reglages)
    data["figures_ana"] = figs
    for ecrire, nom in ((ecrire_pdf, "r.pdf"), (ecrire_protocole, "p.pdf")):
        ecrire(data, tmp_path / nom)
        with pdfplumber.open(tmp_path / nom) as pdf:
            texte = " ".join(" ".join(p.extract_text() for p in pdf.pages).split())
            n_images = sum(len(p.images) for p in pdf.pages)
        assert "Tableaux et graphiques (ana explorer)" in texte and "EXP-2026-014 | Graisse" in texte and n_images >= 2, nom
    import docx
    ecrire_docx(data, tmp_path / "r.docx")
    w = docx.Document(str(tmp_path / "r.docx"))
    assert any("Tableaux et graphiques" in p.text for p in w.paragraphs) and len(w.inline_shapes) >= 3  # schéma du flux + 2 images
    L.retirer(figs[0]["chemin"])
    assert [f["libelle"] for f in L.figures(tmp_path, ethanol.id)] == ["Graphiques"]
    assert (d / "retirees" / "20261110-101500_tableau.png").exists() and (d / "retirees" / "20261110-101500_tableau.json").exists()


def test_bouton_et_carte(qtbot, tmp_path, qapp, monkeypatch):
    from PySide6.QtWidgets import QPushButton

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
    m.contexte.experience = "EXP-2026-014"
    appels = []
    monkeypatch.setattr(L, "ouvrir_ana", lambda *a: appels.append(a) or "ok")
    f.ouvrir(m.id)
    f.p_flux.rafraichir()
    b = next(x for x in f.p_flux.findChildren(QPushButton) if "ana explorer" in x.text())
    assert b.isEnabled()  # même dans la vue en lecture (manip lancée)
    b.click()
    assert appels and appels[0][0] == "EXP-2026-014" and appels[0][1] == m.id and str(appels[0][3]).endswith(m.id)
    image(L.dossier_retour(ctrl.st.donnees, m.id) / "20261110-101500_tableau.png", fiche={"type": "tableau", "titre": "EXP-2026-014"})
    f.p_rapport.rafraichir()
    assert any(x._titre == "Tableaux et graphiques d’ana explorer" for x in f.p_rapport.findChildren(Expander))
    ctrl.fermer()
