"""Interface (pytest-qt, sans écran) : parcours principal, enregistrement automatique, journal,
lecture seule, annulation, exports (critères 14, 23, 25, 29, 30, 31)."""
import json
from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QFrame  # noqa: E402

from mat_methode.storage.stockage import Stockage  # noqa: E402
from mat_methode.ui import dialogues as D  # noqa: E402
from mat_methode.ui import theme  # noqa: E402
from mat_methode.ui.controleur import Controleur  # noqa: E402
from mat_methode.ui.fenetre import Fenetre  # noqa: E402
from mat_methode.ui.widgets import NumberBox, ToggleSwitch  # noqa: E402


@pytest.fixture
def fen(qtbot, tmp_path, qapp):
    theme.appliquer(qapp, "clair")
    ctrl = Controleur(Stockage(tmp_path, "pierre", "PC1"))
    f = Fenetre(ctrl)
    qtbot.addWidget(f)
    ctrl.demarrer()
    f.aller("manips")
    f.show()
    yield f
    ctrl.fermer()


def ethanol(f):
    return next(m for m in f.ctrl.manips if m.nom == "Désacidification éthanol")


def fichier(f, m) -> dict:
    return json.loads((f.ctrl.st.d_manips / f"{m.id}.json").read_text(encoding="utf-8"))


def test_premier_lancement_cree_donnees_et_exemples(fen, tmp_path):
    assert (tmp_path / "donnees" / "reglages.json").exists()
    assert len(fen.ctrl.manips) == 4
    assert fen.p_manips.b_actives.text() == "Mes manips (3)"


def test_crit29_enregistrement_automatique(fen, qtbot):
    m = ethanol(fen)
    m.lancee, m.journal, m.base = None, [], None
    fen.ouvrir(m.id)
    rev = fichier(fen, m)["rev"]
    m.etapes[0].temperature_c = 65
    fen.ctrl.toucher(m)
    assert fen.enregistrement.text() == "Enregistrement automatique…"
    qtbot.waitUntil(lambda: fichier(fen, m)["rev"] == rev + 1, timeout=2000)
    assert fichier(fen, m)["etapes"][0]["temperature_c"] == 65
    assert fen.enregistrement.text().startswith("Enregistré automatiquement") and f"version {rev + 1}" in fen.enregistrement.text()


def test_crit30_31_journal_une_ligne_par_saisie(fen, qtbot):
    m = ethanol(fen)
    fen.ouvrir(m.id)
    fen.p_flux.aller(m.etapes[2].id)
    n = len(m.journal)
    boites = [b for b in fen.p_flux.findChildren(NumberBox) if b.text() == "25"]
    assert boites
    qtbot.keyClick(boites[0], Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
    qtbot.keyClicks(boites[0], "30")  # deux frappes
    qtbot.waitUntil(lambda: len(m.journal) == n + 1, timeout=2000)
    assert m.journal[-1].txt == "Étape 3 · Désacidification : température 25 → 30 °C" and m.journal[-1].par == "Pierre"
    qtbot.wait(800)
    assert len(m.journal) == n + 1


def test_parcours_nouvelle_manip(fen, qtbot, monkeypatch):
    monkeypatch.setattr(D, "nouvelle_manip", lambda *a: ("Essai pilote", ""))
    fen.nouvelle()
    m = fen.ctrl.courante
    assert m.nom == "Essai pilote" and m.contexte.operateur == "pierre" and fen.page == "flux" and fen.p_flux.mode == "def"
    fen.p_flux._ajouter_etape("chauffage")
    fen.p_flux._ajouter_etape("Neutralisation")
    assert [e.operation for e in m.etapes] == ["chauffage", "neutralisation"]
    fen.p_flux._vers_completer()
    fen.p_flux.aller(m.etapes[0].id)
    t = next(x for x in fen.p_flux.findChildren(ToggleSwitch) if x.text() == "Chauffage")
    t.click()
    assert m.etapes[0].temperature_c == 60
    fen.p_flux._ajouter_ech(m.etapes[0])
    assert m.prelevements[0].labo == "Labo interne" and m.prelevements[0].moment == "effluent"
    fen.p_flux.suivante()
    fen.p_flux.suivante()
    assert fen.page == "rapport"
    qtbot.waitUntil(lambda: (fen.ctrl.st.d_manips / f"{m.id}.json").exists(), timeout=2000)


def test_crit23_type_test_affiche_idee(fen):
    m = ethanol(fen)
    fen.ouvrir(m.id)
    assert fen.p_flux._idee is None
    m.contexte.type = "Test d’idée"
    fen.ctrl.toucher(m, structure=True)
    assert fen.p_flux._idee is not None


def test_crit25_lecture_seule(fen, tmp_path):
    m = ethanol(fen)
    marie = Stockage(tmp_path, "marie", "PC2")
    marie.initialiser()
    marie.prendre_verrou(m.id)
    fen.ouvrir(m.id)
    assert fen.ctrl.lecture_seule and fen.ctrl.verrou_autre.utilisateur == "marie"
    m.nom = "Changé"
    fen.ctrl.toucher(m)
    assert m.id not in fen.ctrl.sales  # rien n'est enregistré
    marie.liberer_verrou(m.id)
    fen.ouvrir(next(x for x in fen.ctrl.manips if x.id != m.id).id)
    fen.ouvrir(m.id)
    assert not fen.ctrl.lecture_seule


def test_ctrl_z_annule_suppression_etape(fen):
    m = ethanol(fen)
    fen.ouvrir(m.id, "def")
    fen.p_flux._supprimer_etape(m.etapes[3])
    assert len(m.etapes) == 4 and len(m.prelevements) == 6
    fen.p_flux._supprimer_etape(m.etapes[3])  # séchage et ses 2 échantillons
    assert len(m.prelevements) == 4
    fen._annuler()
    assert len(m.etapes) == 4 and len(m.prelevements) == 6


def test_crit18_exports_depuis_le_rapport(fen, tmp_path, monkeypatch):
    m = ethanol(fen)
    fen.ouvrir(m.id)
    fen.aller("rapport")
    for fmt in ("pdf", "docx", "md", "html", "json"):
        cible = tmp_path / f"sortie.{fmt}"
        monkeypatch.setattr("mat_methode.ui.fenetre.QFileDialog.getSaveFileName", lambda *a, c=cible: (str(c), ""))
        fen.exporter_fichier(fmt)
        assert cible.exists() and cible.stat().st_size > 500, fmt
    assert "Modifications après lancement" in (tmp_path / "sortie.md").read_text(encoding="utf-8")
    assert fen.ctrl.st.lire_preferences()["dossier_export"] == str(tmp_path)


def test_import_pdf(fen):
    from mat_methode.extraction.extract_mm import extraire
    data = extraire(Path(__file__).resolve().parents[1] / "docs/cahier_des_charges/exemples/rapport_exemple.pdf")
    from mat_methode.exports.echange import importer
    m, _ = importer(data, fen.ctrl.reglages)
    fen.ctrl.ajouter_importee(m)
    assert m in fen.ctrl.manips and len(m.etapes) == 5 and m.etapes[1].vide is not None


def test_crit14_raccourcis(fen, qtbot):
    m = ethanol(fen)
    fen.ouvrir(m.id, "comp")
    assert fen.p_flux.etape_id == "depart"
    qtbot.keyClick(fen, Qt.Key.Key_Right, Qt.KeyboardModifier.AltModifier)
    assert fen.p_flux.etape_id == m.etapes[0].id
    qtbot.keyClick(fen, Qt.Key.Key_Left, Qt.KeyboardModifier.AltModifier)
    assert fen.p_flux.etape_id == "depart"
    qtbot.keyClick(fen, Qt.Key.Key_F, Qt.KeyboardModifier.ControlModifier)
    assert fen.page == "manips"


def test_pages_sans_erreur_en_sombre(fen, qapp):
    theme.appliquer(qapp, "sombre")
    m = ethanol(fen)
    fen.ouvrir(m.id, "def")
    for p in ("flux", "rapport", "reglages", "manips"):
        fen.aller(p)
    fen.setMinimumSize(600, 400)
    fen.resize(900, 700)  # volet replié en icônes
    assert fen.volet.width() == 64


def test_grande_etape_dans_definir_et_completer(fen):
    from mat_methode.domain import regles as R
    m = ethanol(fen)
    fen.ouvrir(m.id, "def")
    fl = fen.p_flux
    fl._commencer_groupe("Degumming")
    g = m.groupes[0]
    assert fl.groupe_cible == g.id
    fl._ajouter_etape("chauffage")
    fl._ajouter_etape("centrifugation")
    assert R.numeros_groupe(m, g.id) == [6, 7]
    fl._finir_groupe()
    fl._ajouter_etape("lavage")
    assert m.etapes[-1].groupe_id is None
    fl._viser_groupe(g.id)
    fl._ajouter_etape("agitation")  # ajoutée après la dernière sous-étape
    assert R.numeros_groupe(m, g.id) == [6, 7, 8] and m.etapes[7].operation == "agitation"
    fl._vers_completer()
    fl.aller(m.etapes[6].id)
    cadres = [w for w in fl.findChildren(QFrame) if w.objectName() == "groupe"]
    assert cadres
    fl._defaire_groupe(g)
    assert m.groupes == []


def test_non_realisee_puis_suppression(fen, monkeypatch):
    from mat_methode.domain.models import NON_REALISEE
    monkeypatch.setattr(D, "confirmer", lambda *a, **k: True)
    m = next(x for x in fen.ctrl.manips if x.nom == "Désacidification acétone")
    fen.aller("manips")
    fen.p_manips._non_realisee(m)
    assert m.etat == NON_REALISEE and fichier(fen, m)["etat"] == NON_REALISEE
    fen.p_manips._supprimer(m)
    assert m not in fen.ctrl.manips and not (fen.ctrl.st.d_manips / f"{m.id}.json").exists()
    fen._annuler()  # Ctrl+Z
    assert any(x.id == m.id for x in fen.ctrl.manips)


def test_renommer_donneur_depuis_reglages(fen, monkeypatch):
    monkeypatch.setattr(D, "demander_texte", lambda *a, **k: "R&D Lyon")
    fen.aller("reglages")
    pr = fen.p_reglages
    pr._renommer("Donneurs d’ordre", "Interne · R&D", pr._ren(__import__("mat_methode.domain.reglages_ops", fromlist=["x"]).renommer_donneur,
                                                              lambda: pr.r.donneurs_ordre))
    assert "R&D Lyon" in fen.ctrl.reglages.donneurs_ordre
    assert sum(1 for m in fen.ctrl.manips if m.contexte.donneur == "R&D Lyon") == 3
    assert fen.ctrl.reglages_sales or (fen.ctrl.st.f_reglages.exists())
