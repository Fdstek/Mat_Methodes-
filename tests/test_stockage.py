"""Stockage partagé (§9.1) : critères 11, 25 à 28 et fichiers temporaires (24)."""
import json
import os
import tempfile
from datetime import date, datetime, timedelta, timezone

from mat_methode.domain.models import Manip, Reglages
from mat_methode.storage.chemins import preparer_temp
from mat_methode.storage.stockage import Stockage


def _st(tmp_path, user="pierre", pc="PC1"):
    s = Stockage(tmp_path, user, pc)
    assert s.initialiser()
    return s


def test_crit11_conservation_et_sauvegarde(tmp_path, ethanol):
    s = _st(tmp_path)
    assert s.enregistrer_manip(ethanol).ok
    s2 = _st(tmp_path)
    liste = s2.lister()
    assert [m.nom for m in liste.manips] == ["Désacidification éthanol"]
    assert liste.manips[0].to_json() == ethanol.to_json()
    cible = s2.sauvegarde_du_jour()
    assert (cible / "manips" / f"{ethanol.id}.json").exists()
    assert (tmp_path / "donnees" / "sauvegardes" / date.today().isoformat()).is_dir()


def test_sauvegardes_10_jours(tmp_path):
    s = _st(tmp_path)
    for k in range(15):
        s.sauvegarde_du_jour(date(2026, 10, 1) + timedelta(days=k))
    restants = sorted(p.name for p in (tmp_path / "donnees" / "sauvegardes").iterdir())
    assert len(restants) == 10 and restants[-1] == "2026-10-15"


def test_version_augmente(tmp_path, ethanol):
    s = _st(tmp_path)
    s.enregistrer_manip(ethanol)
    rev = ethanol.rev
    ethanol.nom = "x"
    assert s.enregistrer_manip(ethanol).ok and ethanol.rev == rev + 1 and ethanol.modifie_par == "pierre"
    assert s.lire_manip(ethanol.id).rev == rev + 1


def test_crit25_verrous(tmp_path, ethanol):
    pierre, marie = _st(tmp_path, "pierre"), _st(tmp_path, "marie", "PC2")
    assert pierre.prendre_verrou(ethanol.id) is None
    v = marie.prendre_verrou(ethanol.id)
    assert v and v.utilisateur == "pierre"
    pierre.liberer_verrou(ethanol.id)
    assert marie.prendre_verrou(ethanol.id) is None
    # verrou abandonné (plantage) : expiré après 3 minutes sans battement
    f = tmp_path / "donnees" / "verrous" / f"{ethanol.id}.lock"
    d = json.loads(f.read_text())
    d["battement"] = (datetime.now(timezone.utc) - timedelta(minutes=4)).isoformat().replace("+00:00", "Z")
    f.write_text(json.dumps(d))
    assert pierre.prendre_verrou(ethanol.id) is None


def test_crit26_conflit(tmp_path, ethanol):
    pierre, marie = _st(tmp_path, "pierre"), _st(tmp_path, "marie", "PC2")
    pierre.enregistrer_manip(ethanol)
    a, b = pierre.lire_manip(ethanol.id), marie.lire_manip(ethanol.id)
    a.nom = "Version Pierre"
    assert pierre.enregistrer_manip(a).ok
    b.nom = "Version Marie"
    res = marie.enregistrer_manip(b)
    assert not res.ok and res.conflit.nom == "Version Pierre"
    assert pierre.lire_manip(ethanol.id).nom == "Version Pierre"  # rien d'écrasé
    # deux manips différentes : aucun conflit
    autre = Manip(nom="Autre")
    assert marie.enregistrer_manip(autre).ok and pierre.enregistrer_manip(a).ok


def test_crit27_reglages_fusionnes(tmp_path):
    pierre, marie = _st(tmp_path, "pierre"), _st(tmp_path, "marie", "PC2")
    pierre.enregistrer_reglages(pierre.charger_reglages())
    rp, rm = pierre.charger_reglages(), marie.charger_reglages()
    rm.assurer_reactif("Hexane")
    assert marie.enregistrer_reglages(rm) == ""
    from mat_methode.domain.models import Laboratoire
    rp.laboratoires.append(Laboratoire(nom="Labo Lyon"))
    rp.analyses.remove("Phosphore")
    msg = pierre.enregistrer_reglages(rp)
    assert "fusionnés" in msg
    final = marie.charger_reglages()
    assert final.reactif("Hexane") and final.laboratoire("Labo Lyon") and "Phosphore" not in final.analyses


def test_crit28_dossier_inaccessible(tmp_path, ethanol):
    racine = tmp_path / "ro"
    racine.mkdir()
    (racine / "donnees").write_text("pas un dossier")  # impossible d'y créer les sous-dossiers
    s = Stockage(racine, "pierre")
    assert not s.initialiser() and s.lecture_seule and "lecture seule" in s.message
    res = s.enregistrer_manip(ethanol)
    assert not res.ok and res.erreur == "Non enregistré : dossier inaccessible"


def test_fichiers_illisibles_et_conflits(tmp_path, ethanol):
    s = _st(tmp_path)
    s.enregistrer_manip(ethanol)
    d = tmp_path / "donnees" / "manips"
    (d / "casse.json").write_text("{pas du json")
    (d / f"{ethanol.id}-PC-MARIE.json").write_text((d / f"{ethanol.id}.json").read_text())
    (d / "futur.json").write_text(json.dumps({"schema": 99, "id": "futur"}))
    liste = s.lister()
    assert [m.id for m in liste.manips] == [ethanol.id]
    assert liste.conflits == [f"{ethanol.id}-PC-MARIE.json"] and "casse.json" in liste.illisibles
    assert any("plus récente" in x for x in liste.illisibles)
    assert (d / f"{ethanol.id}-PC-MARIE.json").exists()  # jamais supprimé


def test_preferences(tmp_path):
    s = _st(tmp_path)
    s.ecrire_preferences({"theme": "sombre"})
    assert s.lire_preferences() == {"theme": "sombre"}
    assert (tmp_path / "donnees" / "preferences" / "pierre.json").exists()


def test_crit24_temp_dans_le_dossier(tmp_path, monkeypatch):
    for k in ("TMP", "TEMP", "TMPDIR"):
        monkeypatch.setenv(k, os.environ.get(k, ""))
    ancien = tempfile.tempdir
    try:
        (tmp_path / "temp").mkdir()
        (tmp_path / "temp" / "reste.txt").write_text("x")
        t = preparer_temp(tmp_path)
        assert t == tmp_path / "temp" and not any(t.iterdir())
        assert tempfile.gettempdir() == str(t) and os.environ["TEMP"] == str(t)
    finally:
        tempfile.tempdir = ancien


def test_reglages_par_defaut(tmp_path):
    r = _st(tmp_path).charger_reglages()
    assert isinstance(r, Reglages) and [e.nom for e in r.etats] == ["Brouillon", "En cours", "Terminée"]
