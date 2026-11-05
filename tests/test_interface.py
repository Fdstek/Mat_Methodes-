"""Interface (pytest-qt, sans écran) : parcours principal, enregistrement automatique, journal,
lecture seule, annulation, exports (critères 14, 23, 25, 29, 30, 31)."""
import json
from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QFrame, QPushButton  # noqa: E402

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
    return json.loads(f.ctrl.st.chemin_manip(m.id).read_text(encoding="utf-8"))


def test_premier_lancement_cree_donnees_et_exemples(fen, tmp_path):
    assert (tmp_path / "donnees" / "reglages.json").exists()
    assert len(fen.ctrl.manips) == 4
    assert fen.p_manips.b_actives.text() == "Manips (3)"


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
    fen.p_flux.basculer_edition()  # manip en cours : en lecture tant qu'on n'appuie pas sur « Modifier »
    fen.p_flux.aller(m.etapes[2].id)
    n = len(m.journal)
    boites = [b for b in fen.p_flux.findChildren(NumberBox) if b.text() == "25"]
    assert boites
    qtbot.keyClick(boites[0], Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
    qtbot.keyClicks(boites[0], "30")  # deux frappes
    qtbot.waitUntil(lambda: len(m.journal) == n + 1, timeout=2000)
    assert m.journal[-1].txt == "Étape 3 · Désacidification : température 25 → 30 °C" and m.journal[-1].par == fen.ctrl.initiales_utilisateur()
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
    assert m.etapes[0].temperature_c == 60 and m.etapes[0].agitation_trmin == 300  # conditions par défaut de « chauffage » (Réglages)
    t = next(x for x in fen.p_flux.findChildren(ToggleSwitch) if x.text() == "Chauffage")
    t.click()
    assert m.etapes[0].temperature_c is None
    t = next(x for x in fen.p_flux.findChildren(ToggleSwitch) if x.text() == "Chauffage")
    t.click()
    assert m.etapes[0].temperature_c == 60
    fen.p_flux._ajouter_ech(m.etapes[0])
    assert m.prelevements[0].labo == "Labo interne" and m.prelevements[0].moment == "effluent"
    fen.p_flux.suivante()
    fen.p_flux.suivante()
    assert fen.page == "flux"  # brouillon : ni protocole ni rapport tant qu'elle n'est pas validée
    assert not fen.nav["rapport"].isEnabled() and not fen.nav["protocole"].isEnabled()
    fen.p_flux._statut("validee")  # bouton « Validée » du bandeau
    assert m.etat == "validee" and m.id in fen.ctrl.reglages.ordre_protocoles
    assert fen.p_flux.consultation  # validée : en lecture, sauf « Modifier »
    fen.p_flux.suivante()
    assert fen.page == "protocole"
    qtbot.waitUntil(lambda: fen.ctrl.st.chemin_manip(m.id).exists(), timeout=2000)


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
    assert [r.fmt for r in m.rapports][-2:] == ["pdf", "docx"]  # documents émis gardés sur la manip (pas md/html/json)


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


def test_annulee_puis_suppression(fen, monkeypatch):
    from mat_methode.domain.models import ANNULEE
    monkeypatch.setattr(D, "confirmer", lambda *a, **k: True)
    m = next(x for x in fen.ctrl.manips if x.nom == "Désacidification acétone")
    fen.aller("manips")
    fen.p_manips._statut(m, ANNULEE)
    assert m.etat == ANNULEE and fichier(fen, m)["etat"] == ANNULEE
    fen.p_manips._supprimer(m)
    assert m not in fen.ctrl.manips and not fen.ctrl.st.chemin_manip(m.id).exists()
    fen._annuler()  # Ctrl+Z
    assert any(x.id == m.id for x in fen.ctrl.manips)


def test_renommer_donneur_depuis_reglages(fen, monkeypatch):
    from mat_methode.domain import reglages_ops as O
    monkeypatch.setattr(D, "demander_texte", lambda *a, **k: "Pierre BURGUN-MARTIN")
    for m in fen.ctrl.manips[:2]:
        m.contexte.donneur = "Pierre BURGUN"
    fen.aller("reglages")
    pr = fen.p_reglages
    pr._renommer("Personnes", "Pierre BURGUN", pr._ren(O.renommer_donneur, lambda: pr.r.donneurs_ordre))
    assert "Pierre BURGUN-MARTIN" in fen.ctrl.reglages.donneurs_ordre
    assert sum(1 for m in fen.ctrl.manips if m.contexte.donneur == "Pierre BURGUN-MARTIN") == 2


def test_volume_et_nouveau_reactif_depuis_le_flux(fen, monkeypatch):
    from mat_methode.ui.widgets import ChoixVolume
    m = ethanol(fen)
    fen.ouvrir(m.id, "comp")
    fen.p_flux.aller(m.etapes[2].id)
    choix = fen.p_flux.findChildren(ChoixVolume)
    assert choix and [choix[0].itemText(i) for i in range(choix[0].count())][:3] == ["30 mL", "50 mL  (hors liste)", "60 mL"]
    choix = fen.p_flux.findChildren(ChoixVolume)[0]
    i = choix.findText("1 L")
    choix.setCurrentIndex(i)
    choix.activated.emit(i)
    assert 1000 in [p.volume_ml for p in m.prelevements]
    monkeypatch.setattr(D, "demander_texte", lambda *a, **k: "Acide phosphorique 85 %")
    fen.p_flux._nouveau_reactif(m.etapes[2].reactifs[0])
    assert fen.ctrl.reglages.reactif("Acide phosphorique 85 %") is not None
    assert m.etapes[2].reactifs[0].nom == "Acide phosphorique 85 %"


def test_scirius_charge_et_reactif(fen, monkeypatch):
    ligne_charge = {"product": "Graisse animale brute", "batch": "GA-2026-09", "stock_item": "000777", "supplier": "Interne",
                    "storage": "Chambre froide"}
    monkeypatch.setattr(D, "chercher_scirius", lambda *a, **k: dict(ligne_charge))
    m = ethanol(fen)
    fen.ouvrir(m.id, "comp")
    fen.p_flux._scirius_charge()
    c = m.contexte
    assert (c.matiere, c.lot, c.scirius, c.fournisseur) == ("Graisse animale brute", "GA-2026-09", "000777", "Interne")
    re_ = m.etapes[2].reactifs[1]  # Eau distillée
    fen.p_flux._scirius_reactif(re_)
    inv = fen.ctrl.reglages.reactif("Eau distillée")
    assert inv.scirius == "000777" and inv.emplacement == "Chambre froide" and re_.nom == "Eau distillée"


def test_reglages_en_cartes_et_reference(fen):
    fen.aller("reglages")
    assert fen.p_reglages.section is None
    cles = [c for c, *_ in fen.p_reglages.sections()]
    assert {"personnes", "laboratoires", "operations", "reactifs", "scirius"} <= set(cles)
    for c in cles:
        fen.p_reglages.ouvrir(c)  # chaque carte s'ouvre sans erreur
    fen.aller("reglages")
    assert fen.p_reglages.section is None
    m = ethanol(fen)
    fen.ouvrir(m.id, "def")
    fen.ctrl.reglages.personnes[0].initiales = "PB"
    m.contexte.ref = ""
    fen.p_flux._choisir_donneur(fen.ctrl.reglages.personnes[0].nom)
    assert m.contexte.ref.startswith("PB-2026-10-30-")


def test_a_faire_grande_etape_en_premier_et_copie(fen, monkeypatch):
    from mat_methode.domain import regles as R
    m = ethanol(fen)
    fen.ouvrir(m.id, "def")
    fl = fen.p_flux
    fl._choisir_cible("n:Degumming")  # choisir la grande étape d'abord
    fl._ajouter_etape("chauffage")
    g = m.groupes[0]
    assert R.numeros_groupe(m, g.id) == [6]
    fl._choisir_cible("")
    fl._ajouter_etape("lavage")
    assert m.etapes[-1].groupe_id is None
    fl._choisir_cible(f"g:{g.id}")
    fl._ajouter_etape("centrifugation")
    assert R.numeros_groupe(m, g.id) == [6, 7]
    fl._vers_completer()
    fl.aller(m.etapes[6].id)
    fl._copier_conditions(m.etapes[6])
    assert m.etapes[6].duree_min == m.etapes[5].duree_min
    n = len(m.a_faire)
    fl.rafraichir()
    from mat_methode.domain.models import Tache
    m.a_faire.append(Tache(categorie="Matériel manquant", texte="Ampoule 1 L"))
    fen.ctrl.toucher(m, True)
    assert len(m.a_faire) == n + 1
    fen.aller("manips")
    fen.aller("rapport")


def test_materiel_molette_et_titre(fen, qtbot):
    from PySide6.QtCore import QPoint, QPointF
    from PySide6.QtGui import QWheelEvent

    from mat_methode.ui.widgets import Liste, ListeSaisie
    m = ethanol(fen)
    fen.ouvrir(m.id, "comp")
    fen.p_flux.aller(m.etapes[0].id)
    ls = next(x for x in fen.p_flux.findChildren(ListeSaisie) if x.accessibleName() != "Ajouter un tag")
    assert "Étuve" in [ls.itemText(i) for i in range(ls.count())]
    fen.p_flux._ajouter_materiel(m.etapes[0], "Thermomètre")
    assert "Thermomètre" in m.etapes[0].equipements and "Thermomètre" in fen.ctrl.reglages.materiels
    # molette sur une liste fermée : la valeur ne change pas
    liste = fen.p_flux.findChildren(Liste)[0]
    avant = liste.currentIndex()
    ev = QWheelEvent(QPointF(5, 5), QPointF(5, 5), QPoint(0, 0), QPoint(0, -120), Qt.MouseButton.NoButton,
                     Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False)
    liste.wheelEvent(ev)
    assert liste.currentIndex() == avant and not ev.isAccepted()


def test_documents_emis_dossiers_partages(fen, monkeypatch):
    from mat_methode.domain.models import Personne
    fen.ctrl.reglages.personnes.append(Personne(nom="Claire LACOUX", igg="PIERRE"))  # IGG du poste de test : « pierre »
    m = ethanol(fen)
    fen.ouvrir(m.id)
    fen.aller("rapport")
    vus = {}
    monkeypatch.setattr("mat_methode.ui.fenetre.QFileDialog.getSaveFileName", lambda _p, _t, chemin, _f: (vus.setdefault("chemin", chemin), "")[0:2])
    ouverts = []
    monkeypatch.setattr("PySide6.QtGui.QDesktopServices.openUrl", lambda url: ouverts.append(url.toLocalFile()))
    fen.exporter_fichier("protocole")
    chemin = vus["chemin"]
    assert Path(chemin).parent.name == "Protocoles" and chemin.endswith("DA-2026-0158 - Désacidification éthanol - Protocole.pdf")
    assert m.rapports and m.rapports[-1].type == "protocole" and m.rapports[-1].par == "Claire LACOUX"
    assert [Path(x) for x in ouverts] == [Path(chemin)]  # le PDF s'ouvre après l'export (Windows : « / » ou « \\ »)
    vus.clear()
    fen.exporter_fichier("pdf")
    assert Path(vus["chemin"]).parent.name == "Rapports"
    fen.p_rapport.rafraichir()


def test_onglet_protocole_apercu(fen):
    from PySide6.QtWidgets import QLineEdit

    from mat_methode.domain.models import RapportEmis
    m = ethanol(fen)
    fen.ouvrir(m.id)
    assert not fen.nav["protocole"].isEnabled()  # rien de choisi dans la liste Protocole
    fen.aller("protocole")
    assert fen.page == "flux"
    m.rapports.append(RapportEmis(type="ordre", chemin="x.pdf", le="2026-11-02T10:00:00", par="Pierre"))  # ancien nom
    fen.ouvrir_protocole(m.id)
    assert fen.page == "protocole" and fen.titre.text() == f"Protocole · {m.nom}" and fen.nav["protocole"].isEnabled()
    nom = next(x for x in fen.p_protocole.flux.findChildren(QLineEdit) if x.text() == m.nom)
    assert nom.isReadOnly()  # même vue que Flux, en lecture
    from mat_methode.ui.widgets import Liste
    bandeau = fen.p_protocole.flux.bandeau
    assert bandeau.parentWidget() is fen.zone_fixe and fen.zone_fixe.isVisible()  # toujours visible, hors de la zone qui défile
    st = next(x for x in bandeau.findChildren(Liste) if x.accessibleName() == f"Statut de {m.nom}")
    assert [st.itemText(i) for i in range(st.count())] == ["Validée", "En cours", "Réalisée", "Annulée"]
    textes = [b.text() for b in bandeau.findChildren(QPushButton)]
    assert "✎  Modifier" in textes and "Exporter le protocole (PDF)" in textes
    assert "Ouvrir le dernier protocole émis" in [b.text() for b in fen.p_protocole.findChildren(QPushButton)]
    fen.p_protocole._mode("modifier")
    nom = next(x for x in fen.p_protocole.flux.findChildren(QLineEdit) if x.text() == m.nom)
    assert not nom.isReadOnly()
    fen.p_protocole.flux._statut("realisee")
    fen.ouvrir_rapport(m.id)
    assert "Ouvrir le dernier protocole émis" not in [b.text() for b in fen.p_rapport.findChildren(QPushButton)]


def test_parcours_definition_protocole_rapport(fen, monkeypatch):
    """Brouillon -> Validée (Définition) -> Protocole (ordre, En cours = lancée) -> Réalisée -> Rapport."""
    from mat_methode.domain import regles as R
    from mat_methode.domain.models import BROUILLON, ENCOURS, REALISEE, VALIDEE
    from mat_methode.ui.widgets import Liste
    ctrl = fen.ctrl
    a, b = (next(x for x in ctrl.manips if x.nom == n) for n in ("Désacidification acétone", "Désacidification éthanol"))
    for m in (a, b):
        m.etat, m.lancee, m.journal = BROUILLON, None, []
    fen.aller("manips")
    st = next(x for x in fen.p_manips.findChildren(Liste) if x.accessibleName() == f"Statut de {b.nom}")
    assert [st.itemText(i) for i in range(st.count())] == ["Brouillon", "Validée", "Annulée"]
    st.choisi.emit(VALIDEE)
    fen.p_manips._statut(a, VALIDEE)
    assert b.etat == VALIDEE and R.protocoles(ctrl.manips, ctrl.reglages.ordre_protocoles)[:2] == [b, a]
    fen.aller("protocoles")
    assert fen.titre.text() == "Protocole" and not fen.nav["protocole"].isEnabled() or ctrl.courante
    ctrl.deplacer_protocole(a, -1)
    assert R.protocoles(ctrl.manips, ctrl.reglages.ordre_protocoles)[:2] == [a, b]
    assert ctrl.changer_statut(a, ENCOURS) == "" and a.lancee is not None
    fen.ouvrir_protocole(a.id)
    assert fen.page == "protocole" and fen.titre.text() == f"Protocole · {a.nom}" and fen.p_protocole.flux.consultation
    fen.p_protocole._mode("modifier")
    assert not fen.p_protocole.flux.consultation
    fen.p_protocole._mode("apercu")
    fen.aller("rapports")
    assert a not in R.rapports_clotures(ctrl.manips)
    ctrl.changer_statut(a, REALISEE)
    fen.aller("rapports")
    assert R.rapports_clotures(ctrl.manips)[0] is a
    fen.ouvrir_rapport(a.id)
    assert fen.page == "rapport" and fen.titre.text() == f"Rapport · {a.nom}"
    assert fichier(fen, a)["etat"] == REALISEE


def test_lancer_passe_en_cours(fen, monkeypatch):
    from mat_methode.domain.models import ENCOURS, VALIDEE
    m = ethanol(fen)
    m.lancee, m.journal, m.etat = None, [], VALIDEE
    fen.ouvrir(m.id, "def")
    monkeypatch.setattr("mat_methode.ui.dialogues.confirmer", lambda *a, **k: True)
    fen.p_flux._lancer()
    assert m.lancee and m.etat == ENCOURS and m.id in fen.ctrl.reglages.ordre_protocoles


def test_dupliquer_grande_etape_et_ordre_a_faire(fen, monkeypatch):
    from mat_methode.domain import regles as R
    from mat_methode.domain.models import Tache
    m = ethanol(fen)
    fen.ouvrir(m.id, "def")
    g = R.creer_groupe(m, "Degumming")
    R.placer_dans_groupe(m, m.etapes[1].id, g.id)
    R.placer_dans_groupe(m, m.etapes[2].id, g.id)
    n, ne = len(m.etapes), len(m.prelevements)
    monkeypatch.setattr("mat_methode.ui.dialogues.dupliquer_groupe", lambda *a: (2, True))
    fen.p_flux._dupliquer_groupe(g)
    assert len(m.etapes) == n + 4 and len(m.groupes) == 3 and [x.nom for x in m.groupes] == ["Degumming"] * 3
    assert len(m.prelevements) > ne
    m.a_faire = [Tache(texte="a"), Tache(texte="b")]
    assert R.deplacer_tache(m, m.a_faire[1].id, -1) and [t.texte for t in m.a_faire] == ["b", "a"]


def test_tags_en_liste_et_section_volumes(fen):
    from mat_methode.ui.widgets import ListeSaisie
    m = ethanol(fen)
    fen.ouvrir(m.id, "def")
    tag = next(x for x in fen.p_flux.findChildren(ListeSaisie) if x.accessibleName() == "Ajouter un tag")
    choix = [tag.itemText(i) for i in range(tag.count())]
    assert choix and not set(choix) & set(m.tags)
    tag.valide.emit(choix[0])
    assert choix[0] in m.tags
    x = fen.p_flux._volumes_x
    assert "50 mL en amont · 1\u202f000 mL engagés · 275 mL prélevés · 725 mL restants" in x.tete.text()
    textes = [w.text() for w in fen.p_flux._volumes.findChildren(type(fen.titre))]
    assert "ENGAGÉ" in textes and "RESTANT" in textes and "S5b" in " ".join(textes)


def test_ordre_dans_les_reglages(fen):
    from mat_methode.domain.regles import tous_les_tags
    from mat_methode.ui.widgets import Liste
    r = fen.ctrl.reglages
    fen.aller("reglages")
    p = fen.p_reglages
    t0 = list(r.types_demande)
    p._deplacer(r.types_demande, 1, -1)
    assert r.types_demande == [t0[1], t0[0]] + t0[2:]
    p0 = [x.nom for x in r.personnes]
    r.personnes.append(type(r.personnes[0])(nom="Claire LACOUX"))
    p._deplacer(r.personnes, len(r.personnes) - 1, -1)
    assert [x.nom for x in r.personnes][-2:] == ["Claire LACOUX", p0[-1]]
    ts = tous_les_tags(fen.ctrl.manips, r.ordre_tags)
    p._deplacer_tag(ts[-1], -1)
    assert tous_les_tags(fen.ctrl.manips, r.ordre_tags)[-2] == ts[-1]
    m = next(x for x in fen.ctrl.manips if x.nom == "Désacidification éthanol")
    fen.ouvrir(m.id, "def")
    typ = next(x for x in fen.p_flux.findChildren(Liste) if r.types_demande[0] in [x.itemText(i) for i in range(x.count())])
    assert [typ.itemText(i) for i in range(typ.count())][1:3] == r.types_demande[:2]


def test_tag_cree_dans_les_reglages_et_ordre_des_cartes(fen, monkeypatch):
    from mat_methode.domain.regles import tous_les_tags
    from mat_methode.ui.widgets import ChampTexte, ListeSaisie
    fen.aller("reglages", "tags")
    champ = next(x for x in fen.p_reglages.findChildren(ChampTexte) if x.placeholderText() == "Nouveau tag")
    champ.setText("pilote")
    champ.returnPressed.emit()
    assert "pilote" in tous_les_tags(fen.ctrl.manips, fen.ctrl.reglages.ordre_tags)
    m = ethanol(fen)
    fen.ouvrir(m.id, "def")
    fen.p_flux.basculer_edition()
    tag = next(x for x in fen.p_flux.findChildren(ListeSaisie) if x.accessibleName() == "Ajouter un tag")
    assert "pilote" in [tag.itemText(i) for i in range(tag.count())]
    fen.aller("reglages")
    premiere = fen.p_reglages._sections_ordonnees()[0][0]
    fen.p_reglages._deplacer_carte(premiere, 1)
    assert fen.p_reglages._sections_ordonnees()[1][0] == premiere
    fen.aller("manips")
    from PySide6.QtWidgets import QPushButton
    textes = [w.text() for w in fen.p_manips.findChildren(type(fen.titre))] + [b.text() for b in fen.p_manips.findChildren(QPushButton)]
    assert {"DONNEUR ⇅", "TYPE ⇅", "TAGS", "STATUT"} <= set(textes)  # en-têtes triables : flèche


def test_tri_couleur_des_types_presence_et_defilement(fen, qtbot, tmp_path):
    from mat_methode.domain import reglages_ops as O
    from mat_methode.storage.stockage import Stockage
    r = fen.ctrl.reglages
    c = O.couleur_type(r, "R&D")
    assert O.couleur_type_suivante(r, "R&D") != c and O.couleur_type(r, "r&d") != c
    fen.aller("manips")
    fen.p_manips._trier("type")
    types = [m.contexte.type for m in fen.p_manips._visibles()]
    assert types == sorted(types, key=lambda t: t.lower())
    fen.p_manips._trier("type")
    assert [m.contexte.type for m in fen.p_manips._visibles()] == sorted(types, key=lambda t: t.lower(), reverse=True)
    # présence : un autre poste a la manip ouverte -> pastille aux initiales
    m = ethanol(fen)
    Stockage(fen.ctrl.st.racine, "CLAIRE", "PC2").signaler_presence(m.id)
    fen.ctrl.actualiser_presence()
    assert fen.ctrl.presents_sur(m.id) and fen.presents.isVisible()
    # défilement : ajouter un échantillon ne fait pas remonter la page
    m.etat = "brouillon"
    fen.ouvrir(m.id, "comp")
    fen.p_flux.aller(m.etapes[2].id)
    qtbot.wait(200)
    sb = fen.defilements["flux"].verticalScrollBar()
    sb.setValue(sb.maximum() - 20)
    pos = sb.value()
    fen.p_flux._ajouter_ech(m.etapes[2])
    qtbot.wait(300)
    assert sb.value() == pos


def test_retour_liste_sans_fenetre_en_trop_et_initiales(fen, qapp):
    from mat_methode.storage.stockage import Stockage
    m = ethanol(fen)
    fen.ouvrir(m.id, "comp")
    fen.ouvrir_protocole(m.id)
    fen.aller("flux")
    fen.aller("protocole")
    assert [w for w in qapp.topLevelWidgets() if w.isVisible()] == [fen]  # le bandeau ne devient jamais une fenêtre à part
    assert fen.retour.isVisible()
    fen.quitter_manip()  # « ← » dans Protocole › Édition : la manip en cours est fermée partout
    assert fen.page == "protocoles" and fen.ctrl.courante is None
    assert not fen.nav["protocole"].isEnabled() and not fen.nav["flux"].isEnabled()
    assert fen.ctrl.st.lire_verrou(m.id) is None  # verrou libéré
    fen.ouvrir(m.id, "comp")
    fen.quitter_manip()
    assert fen.page == "manips" and fen.ctrl.courante is None and not fen.retour.isVisible()
    autre = Stockage(fen.ctrl.st.racine, "J0034240", "PC2")
    autre.nom_affiche, autre.initiales = "Alice LIMOGES", "AL"
    autre.signaler_presence(m.id)
    fen.ctrl.actualiser_presence()
    p = fen.ctrl.presents[0]
    assert fen.ctrl.initiales_de(p["utilisateur"], p) == "AL" and fen.ctrl.nom_present(p) == "Alice LIMOGES"


def test_historique_des_statuts_et_ecran_d_ouverture(fen, tmp_path):
    import docx
    import pdfplumber

    from mat_methode.domain.models import Personne
    from mat_methode.exports.echange import exporter
    from mat_methode.exports.pdf import ecrire_pdf
    from mat_methode.exports.protocole import ecrire_protocole
    from mat_methode.exports.word import ecrire_docx
    from mat_methode.ui.demarrage import EcranDemarrage
    r = fen.ctrl.reglages
    r.personnes.append(Personne(nom="Claire LACOUX", initiales="CL", igg="PIERRE"))  # IGG du poste de test : « pierre »
    m = ethanol(fen)
    m.etat = "brouillon"
    fen.ouvrir(m.id, "def")
    fen.p_flux._statut("validee")
    c = m.statuts[-1]
    assert (c.de, c.vers, c.par) == ("brouillon", "validee", "pierre")
    textes = [w.text() for w in fen.p_flux.bandeau.findChildren(type(fen.titre))]
    assert any(t.startswith("Validée le ") and t.endswith("par CL") for t in textes)  # initiales, jamais l’IGG
    from mat_methode.domain.reglages_ops import journal_complet
    assert journal_complet(r, m)[0][1:] == ("CL", "Statut : Brouillon → Validée")
    d = exporter(m, r)
    assert d["statuts"][-1]["vers"] == "Validée" and d["statuts"][-1]["nom"] == "CL"
    for i, ecrire in enumerate((ecrire_pdf, ecrire_protocole)):
        ecrire(d, tmp_path / f"{i}.pdf")
        with pdfplumber.open(tmp_path / f"{i}.pdf") as pdf:
            t = " ".join(p.extract_text() for p in pdf.pages)
        assert "Historique des statuts" in t and " CL " in t and "PIERRE" not in t
    ecrire_docx(d, tmp_path / "r.docx")
    w = docx.Document(str(tmp_path / "r.docx"))
    assert "Brouillon → Validée" in "\n".join(c.text for tb in w.tables for row in tb.rows for c in row.cells)
    e = EcranDemarrage("Mat & Méthode", "1.0.0")
    e.avancer(55, "Lecture des réglages et des manips…")
    assert e.barre.value() == 55 and e.etape.text().startswith("Lecture")
    e.close()


def test_experience_attribution_etapes_filtres_et_demandes(fen, tmp_path):
    import pdfplumber

    from mat_methode.domain import regles as R
    from mat_methode.domain.demandes import Demande, vers_markdown
    from mat_methode.domain.models import Personne
    from mat_methode.exports.echange import exporter
    from mat_methode.exports.pdf import ecrire_pdf
    from mat_methode.storage import demandes as S
    from mat_methode.ui import colonnes as C
    r = fen.ctrl.reglages
    r.personnes.append(Personne(nom="Claire LACOUX", initiales="CL", igg="PIERRE", manipule=False))
    r.personnes.append(Personne(nom="Zoé MARTIN", initiales="ZM", manipule=True))
    assert r.attributions[0] == "Zoé MARTIN"  # ceux qui font des manips d'abord
    m = ethanol(fen)
    m.contexte.experience, m.contexte.attribue = "EXP-2026-014", "Zoé MARTIN"
    # duplicata : la personne connectée devient donneur d'ordre
    c = fen.ctrl.dupliquer(m.id)
    assert c.contexte.donneur == "Claire LACOUX" and c.contexte.experience == ""
    c.contexte.attribue = ""
    # repères de grandes étapes
    g = R.creer_groupe(m, "Degumming")
    R.placer_dans_groupe(m, m.etapes[0].id, g.id)
    m.etapes[0].equipements = ["R1"]
    assert R.texte_reperes(m) == "D : R1"
    d = exporter(m, r)
    assert d["contexte"]["experience"] == "EXP-2026-014" and d["contexte"]["attribue"] == "Zoé MARTIN"
    ecrire_pdf(d, tmp_path / "r.pdf")
    with pdfplumber.open(tmp_path / "r.pdf") as pdf:
        t = " ".join(p.extract_text() for p in pdf.pages)
    assert "EXP-2026-014" in t and "Zoé MARTIN" in t
    # filtres à choix multiples
    f = C.Filtres()
    f.attribue = {"Zoé MARTIN", "Autre"}
    assert f.appliquer([m, c]) == [m]
    f.attribue = set()
    f.donneur = {m.contexte.donneur, c.contexte.donneur}
    assert len(f.appliquer([m, c])) == 2
    assert C.trier_manips([c, m], ("attribue", False))[0] is m
    # listes : le numéro d'expérience et la colonne Étapes ne cassent pas la mise en page
    fen.resize(1700, 860)  # large écran : les polices de Windows sont plus larges que celles de ce test
    for page in ("manips", "protocoles", "rapports"):
        fen.aller(page)
        QTest.qWait(50)
        assert fen.pages[page].minimumSizeHint().width() <= fen.width() - 272
    # demandes
    fen.ouvrir_demandes()
    p = fen.p_demandes
    p.titre_saisi, p.texte_saisi = "Bouton trop petit", "Dans Réglages"
    pj = tmp_path / "capture.png"
    pj.write_bytes(b"png")
    p.joints = [str(pj)]
    p._envoyer()
    lst = S.lister(fen.ctrl.st)
    assert len(lst) == 1 and lst[0].pieces == ["capture.png"] and lst[0].statut == "Nouvelle"
    p._statut(lst[0], "Traitée")
    lst = S.lister(fen.ctrl.st)
    assert lst[0].statut == "Traitée" and lst[0].historique[-1].par == "pierre"
    assert "Bouton trop petit" in vers_markdown(lst, fen.ctrl.nom_de) and isinstance(lst[0], Demande)


def test_export_des_nouvelles_demandes_et_fait_des_manips(fen, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog

    from mat_methode.domain.demandes import Demande
    from mat_methode.domain.models import Personne
    from mat_methode.domain.texte import prenom
    from mat_methode.storage import demandes as S
    st = fen.ctrl.st
    S.enregistrer(st, Demande(titre="A", texte="un", auteur="pierre"))
    ancien = Demande(titre="B", texte="deux", auteur="pierre", statut="En cours")  # ancien nom du statut
    S.enregistrer(st, ancien)
    assert S.relire(st, ancien.id).statut == "À vérifier"
    cible = tmp_path / "export.md"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(cible), "")))
    fen.ouvrir_demandes()
    fen.p_demandes.ouvrir_fichier.disconnect()
    fen.p_demandes._exporter()
    texte = cible.read_text(encoding="utf-8")
    assert "un" in texte and "deux" not in texte  # seulement les nouvelles
    assert {d.titre: d.statut for d in S.lister(st)} == {"A": "À vérifier", "B": "À vérifier"}
    # « Fait des manips » remonte la personne en tête
    r = fen.ctrl.reglages
    r.personnes += [Personne(nom="Anne DUPONT"), Personne(nom="Zoé MARTIN")]
    fen.aller("reglages")
    fen.p_reglages._fait_des_manips(r.personne("Zoé MARTIN"), True)
    assert r.personnes[0].nom == "Zoé MARTIN" and r.attributions[0] == "Zoé MARTIN"
    assert prenom("Pierre BURGUN") == "Pierre" and prenom("Interne · R&D") == "Interne · R&D"


def test_glisser_deposer_etapes_groupes_et_echantillons(fen):
    from PySide6.QtCore import QMimeData, QPointF, Qt
    from PySide6.QtGui import QDropEvent

    from mat_methode.domain import regles as R
    from mat_methode.ui.glisser import MIME, lire
    m = ethanol(fen)
    ids = [e.id for e in m.etapes]
    assert len(ids) >= 4
    # étape : la 1re passe après la 3e
    assert R.deplacer_etape_vers(m, ids[0], ids[2], avant=False)
    assert [e.id for e in m.etapes][:3] == [ids[1], ids[2], ids[0]]
    # grande étape : se place avant une étape ; elle reste d'un seul tenant
    g = R.creer_groupe(m, "Degumming")
    R.placer_dans_groupe(m, ids[1], g.id)
    R.placer_dans_groupe(m, ids[2], g.id)
    assert R.deplacer_groupe_vers(m, g.id, ids[3], avant=False)
    assert [e.groupe_id for e in m.etapes if e.id in (ids[1], ids[2])] == [g.id, g.id]
    pos = [e.id for e in m.etapes]
    assert abs(pos.index(ids[1]) - pos.index(ids[2])) == 1 and pos.index(ids[3]) < pos.index(ids[1])
    # bord de grande étape : déposer avant la 1re sous-étape sort de la grande étape
    assert R.deplacer_etape_vers(m, ids[3], ids[1], avant=True) and m.etape(ids[3]).groupe_id is None
    # échantillon : vers le départ, puis vers une étape
    p = next(x for x in m.prelevements if x.etape_id)
    assert R.deplacer_echantillon_vers(m, p.id, None) and p.etape_id is None and p.moment == "avant"
    assert R.deplacer_echantillon_vers(m, p.id, ids[3]) and p.etape_id == ids[3] and p.moment == "effluent"
    # vrai lâcher de souris sur une ligne d'étape du flux (brouillon : modifiable)
    m.etat = "brouillon"
    fen.ouvrir(m.id, "def")
    fen.p_flux.rafraichir()
    QTest.qWait(50)
    from PySide6.QtWidgets import QFrame
    lignes = [f for f in fen.p_flux.findChildren(QFrame) if f.objectName() == "sousCarte" and f.acceptDrops()]
    assert len(lignes) >= 2
    m = fen.ctrl.courante  # la manip ouverte (relue) : c'est elle qui est modifiée
    avant_ordre = [e.id for e in m.etapes]
    mime = QMimeData()
    mime.setData(MIME, f"etape:{avant_ordre[-1]}".encode())
    assert lire(mime) == ("etape", avant_ordre[-1])
    cible = lignes[0]
    ev = QDropEvent(QPointF(5, 2), Qt.DropAction.MoveAction, mime, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    filtre = next(x for x in cible.children() if type(x).__name__ == "_Cible")
    assert filtre.eventFilter(cible, ev)  # le lâcher est pris en charge par la zone de dépôt
    assert [e.id for e in m.etapes] != avant_ordre and m.etapes[-1].id != avant_ordre[-1]


def test_demandes_modifiables_a_faire_dans_les_pdf_et_listes_identiques(fen, tmp_path):
    import pdfplumber

    from mat_methode.domain.demandes import vers_markdown
    from mat_methode.domain.models import Personne, Tache
    from mat_methode.exports.echange import exporter
    from mat_methode.exports.pdf import ecrire_pdf
    from mat_methode.exports.protocole import ecrire_protocole
    from mat_methode.storage import demandes as S
    from mat_methode.ui import colonnes as C
    st, r = fen.ctrl.st, fen.ctrl.reglages
    # demandes : menus concernés (plusieurs) puis modification
    fen.ouvrir_demandes()
    p = fen.p_demandes
    p.titre_saisi, p.texte_saisi = "Colonne trop étroite", "Dans la liste"
    p.tags_saisis = {"Mat & Méthode", "Protocole"}
    p._envoyer()
    d = S.lister(st)[0]
    assert d.tags == ["Mat & Méthode", "Protocole"]
    p._modifier(d)
    assert p.edition == d.id and p.titre_saisi == "Colonne trop étroite"
    p.titre_saisi, p.tags_saisis = "Colonne trop large", {"Rapport"}
    p._envoyer()
    d2 = S.lister(st)
    assert len(d2) == 1 and d2[0].titre == "Colonne trop large" and d2[0].tags == ["Rapport"] and p.edition is None
    md = vers_markdown(d2, fen.ctrl.nom_de)
    assert "Consigne : si besoin, tu me poses des questions sur mes demandes." in md and "Menus concernés : Rapport" in md
    # « Fait des Mat & Méthode » : en tête des donneurs d'ordre
    r.personnes += [Personne(nom="Anne DUPONT"), Personne(nom="Zoé MARTIN")]
    fen.aller("reglages")
    fen.p_reglages._fait_mm(r.personne("Zoé MARTIN"), True)
    assert r.donneurs_proposes[0] == "Zoé MARTIN"
    # à faire non cochés : dans les PDF
    m = ethanol(fen)
    m.a_faire = [Tache(categorie="Matériel", texte="Réserver le réacteur R1"), Tache(categorie="Sécurité", texte="Lire la fiche", fait=True)]
    d = exporter(m, r)
    assert [x["texte"] for x in d["a_faire"]] == ["Réserver le réacteur R1"]
    for i, ecrire in enumerate((ecrire_pdf, ecrire_protocole)):
        ecrire(d, tmp_path / f"{i}.pdf")
        with pdfplumber.open(tmp_path / f"{i}.pdf") as pdf:
            t = " ".join(pg.extract_text() for pg in pdf.pages)
        assert "Réserver le réacteur R1" in t and "Lire la fiche" not in t
    # listes Mat & Méthode et Protocole : même colonne « Manip »
    ref = C.resume_manip(fen.ctrl, m)
    assert ref.findChildren(type(fen.titre))[0].text() == m.nom


def test_etapes_en_parallele_dans_l_editeur_les_documents_et_unites(fen, tmp_path):
    import pdfplumber
    from PySide6.QtWidgets import QFrame

    from mat_methode.domain import regles as R
    from mat_methode.domain.models import ReactifEtape
    from mat_methode.exports.echange import exporter, importer
    from mat_methode.exports.pdf import ecrire_pdf
    from mat_methode.exports.word import image_flux
    from mat_methode.report.rapport import construire
    from mat_methode.ui.widgets import ChoixVitesse
    m = ethanol(fen)
    m.etat = "brouillon"
    fen.ouvrir(m.id, "def")
    page = fen.p_flux
    m = fen.ctrl.courante
    ids = [e.id for e in m.etapes]
    # création d'un bloc en parallèle par la liste « Où ajouter l'étape ? » puis ajout de sous-étapes dans les voies
    page._choisir_cible("p:new")
    assert len(m.paralleles) == 1 and page.voie_cible
    pid, va = page.voie_cible
    page._ajouter_etape("lavage")
    page._viser_voie(pid, m.paralleles[0].voies[1].id)
    page._ajouter_etape("centrifugation")
    page._finir_voie()
    seg = R.segments(m)
    assert [s[0] for s in seg] == ["seq", "par"] and [len(v) for v in seg[1][2]] == [1, 1]
    page.rafraichir()
    QTest.qWait(50)
    assert any(f.objectName() == "voie" for f in page.findChildren(QFrame))
    # glisser une étape dans une voie
    page._deposer_dans_voie(ids[0], pid, va)
    assert m.etape(ids[0]).voie_id == va
    # l'étape suivante réunit les voies : texte du rapport, PDF et image du Word
    page._finir_voie()
    page._ajouter_etape("séchage")
    d = exporter(m, fen.ctrl.reglages)
    assert [e["parallele"]["lettre"] for e in d["etapes"] if e.get("parallele")] == ["A", "A", "B"]
    texte = construire(m, fen.ctrl.reglages).sections[2].texte
    assert "voie A, en parallèle" in texte and "réunion des voies A et B" in texte
    ecrire_pdf(d, tmp_path / "p.pdf")
    with pdfplumber.open(tmp_path / "p.pdf") as pdf:
        assert "EN PARALLÈLE" in " ".join(pg.extract_text() for pg in pdf.pages)
    assert image_flux(d["etapes"], d["prelevements"]).size[1] > 600
    # aller-retour par l'export JSON
    m2, _ = importer(d, fen.ctrl.reglages)
    assert len(m2.paralleles) == 1 and [e.parallele_id is not None for e in m2.etapes].count(True) == 3
    # unités des réactifs et vitesses d'agitation (listes des Réglages)
    r = fen.ctrl.reglages
    assert r.unites_reactifs[0] == "mL" and 300 in r.vitesses_agitation
    e = m.etapes[0]
    e.reactifs = [ReactifEtape(nom="Éthanol", quantite="250", unite="mL")]
    assert e.reactifs[0].quantite_complete == "250 mL"
    assert exporter(m, r)["etapes"][0]["reactifs_detail"][0]["quantite"] == "250 mL"
    from mat_methode.domain import reglages_ops as O
    assert O.ajouter_vitesse(r, 650) and not O.ajouter_vitesse(r, 650) and 650 in r.vitesses_agitation
    assert O.renommer_unite(r, [m], "mL", "ml") == [m] and e.reactifs[0].unite == "ml"
    lv = ChoixVitesse(r.vitesses_agitation, 325.0)  # valeur hors liste : reste affichée
    assert "(hors liste)" in lv.currentText() and lv.findText("Autre valeur…") >= 0
    page.ouvrir("comp")
    page.etape_id = m.etapes[0].id
    page.rafraichir()
    fen.aller("reglages")
    for section in ("unites", "vitesses"):
        fen.p_reglages.ouvrir(section)
        QTest.qWait(30)


def test_matiere_par_voie_unites_de_duree_vitesses_en_g_et_conditions_par_defaut(fen, tmp_path):
    import pdfplumber
    from PySide6.QtWidgets import QFrame

    from mat_methode.domain import reglages_ops as O
    from mat_methode.domain import regles as R
    from mat_methode.domain.models import DUREES, Matiere
    from mat_methode.domain.volumes import volumes_par_etape
    from mat_methode.exports.echange import exporter, importer
    from mat_methode.exports.pdf import ecrire_pdf
    from mat_methode.report.rapport import construire
    r = fen.ctrl.reglages
    m = ethanol(fen)
    m.etat = "brouillon"
    ids = [e.id for e in m.etapes]
    p = R.creer_parallele(m)
    R.placer_dans_voie(m, ids[1], p.id, p.voies[0].id)
    R.placer_dans_voie(m, ids[2], p.id, p.voies[1].id)
    p.voies[0].part, p.voies[0].autres = 40, [Matiere(nom="Éthanol", quantite="200", unite="mL")]
    p.voies[1].part = 60
    conv = m.etapes[3]
    conv.apports = {p.voies[1].id: 300}
    v = {lg.indice: lg for lg in volumes_par_etape(m)}
    assert v[1].entree == 400 and v[1].ajoute == 200 and v[2].entree == 600 and v[3].entree == v[1].sortie + 300
    # l'éditeur affiche les cartes de matière par voie, la réunion des voies et le tableau « Volumes par étape »
    fen.ouvrir(m.id, "def")
    page = fen.p_flux
    page.rafraichir()
    QTest.qWait(50)
    textes = " ".join(lb.text() for lb in page.findChildren(type(fen.titre)))
    assert "Matière reçue" in textes and "matière reçue des voies en parallèle" in textes and "Volumes par étape" in textes
    voies_ui = lambda: [f for f in page.findChildren(QFrame) if f.objectName() == "voie"]  # noqa: E731
    assert not any(f.findChild(QFrame, "menuAjout") for f in voies_ui())  # par défaut, le choix reste en bas de page
    page._viser_voie(p.id, p.voies[1].id)
    QTest.qWait(50)
    assert any(f.findChild(QFrame, "menuAjout") for f in voies_ui())  # le choix s'ouvre sous la voie concernée
    # export / import : parts, autres matières et quantités prises
    d = exporter(m, r)
    m2, _ = importer(d, r)
    p2 = m2.paralleles[0]
    assert p2.voies[0].part == 40 and p2.voies[0].autres[0].nom == "Éthanol" and list(m2.etapes[3].apports.values()) == [300.0]
    # copie : les quantités prises suivent les nouvelles voies
    c = R.dupliquer(m, r)
    assert list(c.etapes[3].apports) == [c.paralleles[0].voies[1].id]
    # le repère « Étapes » des listes contient les voies en parallèle
    assert [x[0] for x in R.reperes_etapes(m)] == ["∥A", "∥B"]
    # unités de durée : 2 h saisies = 120 min stockées ; la liste est gérée dans Réglages
    assert set(r.unites_duree) == set(DUREES) and not O.retirer_unite_duree(type("R", (), {"unites_duree": ["min"]})(), "min")
    assert O.retirer_unite_duree(r, "semaine") and "semaine" not in r.unites_duree and O.ajouter_unite_duree(r, "semaine")
    e = m.etapes[4]
    e.duree_unite, e.duree_min = "h", 120
    page.ouvrir("comp")
    page.etape_id = e.id
    page.rafraichir()
    # vitesse en g (RCF) : texte du rapport et des PDF
    cen = R.ajouter_etape(m, "centrifugation", None, reglages=r)
    cen.vitesse_unite, cen.agitation_trmin = "g", 3000
    assert "000\u202fg" in construire(m, r).sections[2].texte.replace(" g.", "\u202fg.").replace("3\u202f000 g", "3\u202f000\u202fg") or " g." in construire(m, r).sections[2].texte
    ecrire_pdf(exporter(m, r), tmp_path / "g.pdf")
    with pdfplumber.open(tmp_path / "g.pdf") as pdf:
        assert " g" in " ".join(pg.extract_text() for pg in pdf.pages)
    assert O.ajouter_vitesse(r, 4000, "g") and 4000 in r.vitesses_rcf and 4000 not in r.vitesses_agitation
    # conditions par défaut d'une opération (Réglages) : appliquées à l'ajout d'une étape
    assert O.regler_defauts_operation(r, "lavage", {"temperature_c": 25.0, "vide": 0.0})
    lav = R.ajouter_etape(m, "lavage", None, reglages=r)
    assert lav.temperature_c == 25 and lav.vide is not None and lav.vide.mbar is None
    ch = R.ajouter_etape(m, "chauffage", None, reglages=r)
    assert ch.temperature_c == 60 and ch.agitation_trmin == 300


def test_conflit_entre_deux_postes_choix_de_la_version(fen, monkeypatch):
    from mat_methode.storage.stockage import Stockage
    st = fen.ctrl.st
    m = ethanol(fen)
    fen.ctrl.enregistrer_tout()
    marie = Stockage(st.racine, "marie", "PC2")
    marie.initialiser()
    b = marie.lire_manip(m.id)
    b.nom = "Version Marie"
    import mat_methode.storage.stockage as S
    sauve = S.V.tetes
    S.V.tetes = lambda dossier: [v for v in sauve(dossier) if v.poste.startswith("PC2")] or sauve(dossier)  # la synchronisation n'a rien apporté
    try:
        fen.ctrl.st.enregistrer_manip(m, forcer=False)  # (aucun changement : sans effet sur le test)
        S.V.tetes = lambda dossier: []  # Marie enregistre sans voir la version de Pierre
        assert marie.enregistrer_manip(b).ok
    finally:
        S.V.tetes = sauve
    fen.ctrl.actualiser()
    assert fen.ctrl.liste.conflits == [m.id]
    fen.aller("manips")
    QTest.qWait(50)
    textes = " ".join(lb.text() for lb in fen.p_manips.findChildren(type(fen.titre)))
    assert "deux versions à choisir" in textes
    versions = fen.ctrl.versions_en_conflit(m.id)
    assert len(versions) == 2
    msg = fen.ctrl.resoudre_conflit(m.id, versions[0][0].fichier, False)
    assert msg == "" and fen.ctrl.liste.conflits == []


def test_consigne_en_parallele_dans_les_pdf_conditions_par_materiel_et_fenetre_des_demandes(fen, tmp_path):
    import pdfplumber

    from mat_methode.domain import reglages_ops as O
    from mat_methode.domain import regles as R
    from mat_methode.exports.echange import exporter
    from mat_methode.exports.pdf import ecrire_pdf
    from mat_methode.exports.protocole import ecrire_protocole
    r = fen.ctrl.reglages
    m = ethanol(fen)
    ids = [e.id for e in m.etapes]
    p = R.creer_parallele(m)
    R.placer_dans_voie(m, ids[1], p.id, p.voies[0].id)
    R.placer_dans_voie(m, ids[2], p.id, p.voies[1].id)
    m.etapes[0].remarque = "Chauffer sans dépasser 60 °C"
    d = exporter(m, r)
    assert [ph.get("parallele") for ph in d["phases"][1:4]] == [None, "EN PARALLÈLE · VOIE A", "EN PARALLÈLE · VOIE B"]
    assert d["phases"][4]["reunion"] == "Réunit les voies A et B"
    for i, ecrire in enumerate((ecrire_pdf, ecrire_protocole)):
        ecrire(d, tmp_path / f"{i}.pdf")
        with pdfplumber.open(tmp_path / f"{i}.pdf") as pdf:
            t = " ".join(" ".join(pg.extract_text() for pg in pdf.pages).split())
        assert "EN PARALLÈLE · VOIE A" in t and "Réunit les voies A et B" in t and "Chauffer sans dépasser 60 °C" in t
    # conditions particulières d'un matériel : ajoutées à l'étape avec leur valeur par défaut
    assert O.ajouter_condition_materiel(r, "Étuve", "Humidité", "%", "40") and not O.ajouter_condition_materiel(r, "Étuve", "humidité")
    e = m.etapes[4]
    e.equipements = ["Étuve"]
    assert O.appliquer_conditions_materiel(r, e) == ["Humidité"] and e.autres[-1].valeur == "40 %"
    assert O.appliquer_conditions_materiel(r, e) == []  # pas de doublon
    assert O.renommer_materiel(r, [m], "Étuve", "Étuve ventilée") is not None and "Étuve ventilée" in r.conditions_materiel
    fen.aller("reglages")
    fen.p_reglages.ouvrir("cond_materiel")
    QTest.qWait(30)
    # fenêtre « Bugs et idées » : flottante, qui ne bloque pas l'application
    assert not fen.fen_demandes.isVisible()
    fen.nav["demandes"].click()
    assert fen.fen_demandes.isVisible() and fen.page == "reglages" and not fen.fen_demandes.isModal()
    fen.fen_demandes.hide()
    # boutons à côté du titre
    fen.aller("manips")
    assert [b.text().replace("&&", "&") for b in fen.actions_titre.findChildren(type(fen.nav["manips"]))] == ["+  Nouvelle manip", "Importer un ancien Mat & Méthode"]
    fen.aller("rapports")
    assert [b.text() for b in fen.actions_titre.findChildren(type(fen.nav["manips"]))] == ["Importer un ancien rapport"]


def test_tableau_de_matieres_scirius_ou_a_la_main(fen):
    from mat_methode.domain.models import ReactifEtape
    from mat_methode.report.rapport import construire
    r = fen.ctrl.reglages
    m = ethanol(fen)
    m.etat = "brouillon"
    fen.ouvrir(m.id, "def")
    page = fen.p_flux
    m = fen.ctrl.courante
    e = m.etapes[1]
    avant = len(e.reactifs)
    page._ajouter_a_la_main(e.reactifs)  # ligne vide : unité par défaut
    assert len(e.reactifs) == avant + 1 and e.reactifs[-1].unite == r.unites_reactifs[0]
    re_ = e.reactifs[-1]
    re_.nom, re_.reference, re_.quantite = "Acide citrique", "lot AC-42", "5"
    page._inv_par_nom(re_, "scirius", "1234567")  # n° mémorisé pour ce produit, créé dans les Réglages
    inv = r.reactif("Acide citrique")
    assert inv is not None and inv.scirius == "1234567"
    # plusieurs matières dans une même voie, avec la référence à la main dans le détail des phases
    from mat_methode.domain import regles as R
    p = R.creer_parallele(m)
    R.placer_dans_voie(m, m.etapes[2].id, p.id, p.voies[0].id)
    p.voies[0].autres = [ReactifEtape(nom="Eau déminéralisée", reference="lot EA-42", quantite="50", unite="mL"),
                         ReactifEtape(nom="Acide citrique", quantite="5", unite="g")]
    phases = construire(m, r).phases
    ph = next(x for x in phases if x.n == m.etapes.index(m.etapes[2]) + 1)
    noms = {x.nom: x.scirius for x in ph.reactifs}
    assert noms.get("Eau déminéralisée") == "lot EA-42" and noms.get("Acide citrique") == "1234567"
    page.rafraichir()
    QTest.qWait(50)
    textes = " ".join(lb.text() for lb in page.findChildren(type(fen.titre)))
    assert "Autres matières de la voie" in textes


def test_depart_par_voie_matiere_recue_dans_completer_et_schema_du_pdf(fen, tmp_path):
    import pdfplumber
    from PySide6.QtWidgets import QFrame

    from mat_methode.domain import regles as R
    from mat_methode.domain.models import Manip, ReactifEtape
    from mat_methode.exports.echange import exporter
    from mat_methode.exports.pdf import ecrire_pdf
    from mat_methode.exports.word import image_flux
    r = fen.ctrl.reglages
    m = Manip(nom="Départ en parallèle", etat="brouillon")
    m.contexte.volume_depart_ml = 1
    fen.ctrl.manips.append(m)
    p = R.creer_parallele(m)
    for op, v in (("filtration", 0), ("décantation", 0), ("lavage", 1)):
        e = R.ajouter_etape(m, op, None, reglages=r)
        R.placer_dans_voie(m, e.id, p.id, p.voies[v].id)
    R.ajouter_etape(m, "mélange", None, reglages=r)
    p.voies[0].autres = [ReactifEtape(nom="Graisse animale", quantite="12", unite="mL")]
    p.voies[1].autres = [ReactifEtape(nom="Huile de colza", quantite="8", unite="mL", reference="lot EA-42")]
    fen.ctrl.toucher(m)  # volume et matière de départ = ceux des voies
    assert m.contexte.volume_depart_ml == 20 and m.contexte.matiere == "Graisse animale + Huile de colza"
    fen.ouvrir(m.id, "comp")
    page = fen.p_flux
    assert page.ordre()[:2] == [f"depart:{p.voies[0].id}", f"depart:{p.voies[1].id}"] and page.etape_id == page.ordre()[0]
    page.rafraichir()
    QTest.qWait(50)
    textes = " ".join(lb.text() for lb in page.findChildren(type(fen.titre)))
    assert "Départ · voie A" in textes and "Départ · voie B" in textes and "Reçoit : voie A" in textes  # un Départ par voie, réunion visible
    assert "Matière de départ de la voie A" in textes  # éditeur du départ de la voie
    page.aller(m.etapes[2].id)  # 1re étape de la voie B : sa matière reçue reste modifiable dans l'éditeur
    QTest.qWait(50)
    assert "Matière de départ de la voie B" in " ".join(lb.text() for lb in page.findChildren(type(fen.titre)))
    # PDF et Word : cartes « Départ · voie X », cadre, flèches
    d = exporter(m, r)
    assert d["etapes"][0]["parallele"]["depart"]["volume_ml"] == 12 and d["etapes"][2]["parallele"]["depart"]["matieres"][0]["reference"] == "lot EA-42"
    ecrire_pdf(d, tmp_path / "d.pdf")
    with pdfplumber.open(tmp_path / "d.pdf") as pdf:
        t = " ".join(pg.extract_text() for pg in pdf.pages)
    assert "DÉPART · VOIE A" in t and "DÉPART · VOIE B" in t and "EN PARALLÈLE" in t and "SORTIE" in t and "ENTRÉE" in t
    assert image_flux(d["etapes"], d["prelevements"]).size[1] > 500
    assert not any(f.objectName() == "menuAjout" for f in page.findChildren(QFrame))


def test_unite_de_vitesse_tr_min_ou_g_pour_l_agitation_et_les_conditions_communes(fen):
    from mat_methode.domain import regles as R
    from mat_methode.report.rapport import construire
    r = fen.ctrl.reglages
    m = ethanol(fen)
    m.etat = "brouillon"
    fen.ouvrir(m.id, "def")
    page = fen.p_flux
    m = fen.ctrl.courante
    # conditions communes : agitation en g (RCF), appliquée aux étapes
    m.communes.agitation_trmin = 3000.0
    page._changer_unite_vitesse_commune("g")
    assert m.communes.vitesse_unite == "g" and m.communes.agitation_trmin == r.vitesses_rcf[0]
    n = R.appliquer_communes(m, remplacer=True)
    assert n > 0 and all(e.vitesse_unite == "g" for e in m.etapes if e.agitation_trmin is not None and e.operation != "centrifugation")
    # une étape d'agitation (pas seulement la centrifugation) peut passer de tr/min à g, et revenir
    e = next(x for x in m.etapes if x.operation != "centrifugation" and x.agitation_trmin is not None)
    page._changer_unite_vitesse(e, "tr/min")
    assert e.vitesse_unite == "tr/min" and e.agitation_trmin == r.vitesses_agitation[0]
    page._changer_unite_vitesse(e, "g")
    assert "g" in construire(m, r).sections[2].texte
    from PySide6.QtWidgets import QComboBox
    page.ouvrir("comp")
    page.aller(e.id)
    QTest.qWait(50)
    assert any(c.findText("RCF (g)") >= 0 for c in page.findChildren(QComboBox))  # sélecteur tr/min ou RCF (g) sur une étape d’agitation


def test_ton_flux_reste_en_place_pendant_le_defilement(fen, qtbot):
    from PySide6.QtWidgets import QScrollArea
    fen.resize(1400, 650)
    m = ethanol(fen)
    fen.ouvrir(m.id, "def")
    fen.p_flux._mode("comp")
    fen.p_flux.aller(m.etapes[3].id)
    qtbot.wait(150)
    defil = fen.defilements["flux"]
    assert isinstance(fen.p_flux._zone_flux, QScrollArea)
    barre = defil.verticalScrollBar()
    barre.setValue(barre.maximum())
    qtbot.wait(150)
    hote, zone = fen.p_flux._hote_flux, fen.p_flux._zone_flux
    # la colonne suit le défilement : elle a quitté le haut de son hôte et reste visible dans la page
    haut_visible = zone.mapTo(defil.viewport(), zone.rect().topLeft()).y()
    assert zone.y() > 0 and haut_visible + zone.height() > 0 and haut_visible < defil.viewport().height()
    assert zone.y() + zone.height() <= hote.height()
