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


def test_fichiers_illisibles_et_ancien_format(tmp_path, ethanol):
    """Ancien format : un fichier par manip ; il est converti en 1re version. Une copie de conflit OneDrive devient une 2e version courante."""
    d = tmp_path / "donnees" / "manips"
    s = _st(tmp_path)
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{ethanol.id}.json").write_text(json.dumps(ethanol.to_json()))
    autre = ethanol.model_copy(deep=True)
    autre.nom = "Version de Marie"
    (d / f"{ethanol.id}-FR-MARIE.json").write_text(json.dumps(autre.to_json()))
    (d / "casse.json").write_text("{pas du json")
    (d / "futur.json").write_text(json.dumps({"schema": 99, "id": "futur"}))
    liste = s.lister()
    assert [m.id for m in liste.manips] == [ethanol.id] and liste.converties == 2
    assert liste.conflits == [ethanol.id] and any(x.startswith("casse.json") for x in liste.illisibles)
    assert any("plus récente" in x for x in liste.illisibles)
    assert len(s.tetes(ethanol.id)) == 2  # deux versions courantes : à trancher
    assert (d / "_ancien" / f"{ethanol.id}-FR-MARIE.json").exists()  # rien n'est supprimé


def test_deux_postes_en_meme_temps_donnent_deux_versions_a_trancher(tmp_path, ethanol):
    """Aucun fichier n'est réécrit : deux enregistrements simultanés donnent deux versions courantes, jamais une copie de conflit."""
    pierre, marie = _st(tmp_path, "pierre", "PC1"), _st(tmp_path, "marie", "PC2")
    pierre.enregistrer_manip(ethanol)
    a, b = pierre.lire_manip(ethanol.id), marie.lire_manip(ethanol.id)
    # la synchronisation n'a pas encore apporté la version de l'autre poste : chacun enregistre à partir de la même version
    import mat_methode.storage.stockage as S
    a.nom = "Version Pierre"
    b.nom = "Version Marie"
    assert pierre.enregistrer_manip(a).ok
    sauve = S.V.tetes
    S.V.tetes = lambda dossier: [v for v in sauve(dossier) if v.poste.startswith("PC1") is False]  # Marie ne voit pas encore la version de Pierre
    try:
        assert marie.enregistrer_manip(b).ok
    finally:
        S.V.tetes = sauve
    assert len(pierre.tetes(ethanol.id)) == 2 and pierre.lister().conflits == [ethanol.id]
    vers = pierre.versions_en_conflit(ethanol.id)
    assert {m.nom for _, m in vers} == {"Version Pierre", "Version Marie"}
    choisie = next(v.fichier for v, m in vers if m.nom == "Version Marie")
    creees = pierre.resoudre_conflit(ethanol.id, choisie, copier_les_autres=True)
    assert len(pierre.tetes(ethanol.id)) == 1 and pierre.lire_manip(ethanol.id).nom == "Version Marie"
    assert len(creees) == 1 and "Version Pierre" in creees[0].nom and pierre.lire_manip(creees[0].id) is not None
    assert pierre.lister().conflits == []


def test_elagage_garde_les_versions_courantes(tmp_path, ethanol):
    s = _st(tmp_path)
    s.enregistrer_manip(ethanol)
    for k in range(40):
        ethanol.nom = f"v{k}"
        assert s.enregistrer_manip(ethanol).ok
    fichiers = list((tmp_path / "donnees" / "manips" / ethanol.id).glob("v*.json"))
    assert 20 <= len(fichiers) <= 26 and s.lire_manip(ethanol.id).nom == "v39" and len(s.tetes(ethanol.id)) == 1


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
    assert isinstance(r, Reglages) and [e.nom for e in r.etats] == ["Brouillon", "À faire", "Lancée", "En cours", "Réalisée", "Terminée"]


def test_migration_etats_a_faire_et_lancee(tmp_path):
    from mat_methode.storage.stockage import migrer
    f = tmp_path / "reglages.json"
    f.write_text("{}", encoding="utf-8")
    d = migrer({"schema": 4, "etats": [{"id": "brouillon", "nom": "Brouillon"}, {"id": "x", "nom": "lancée"}]}, f)
    assert [e["nom"] for e in d["etats"]] == ["Brouillon", "À faire", "lancée", "Réalisée"] and d["schema"] == 22
    d = migrer({"schema": 5, "etats": [{"id": "encours", "nom": "En cours"}, {"id": "terminee", "nom": "Terminée"}]}, f)
    assert [e["nom"] for e in d["etats"]] == ["En cours", "Réalisée", "Terminée"]


def test_presence_des_autres(tmp_path):
    from mat_methode.storage.stockage import Stockage
    moi, autre = Stockage(tmp_path, "pierre", "PC1"), Stockage(tmp_path, "CLAIRE", "PC2")
    for s in (moi, autre):
        s.initialiser()
    autre.signaler_presence("m1")
    moi.signaler_presence(None)
    assert [(p["utilisateur"], p["manip"]) for p in moi.presences_autres()] == [("CLAIRE", "m1")]
    plus_tard = datetime.now(timezone.utc) + timedelta(minutes=5)
    assert moi.presences_autres(plus_tard) == []  # plus de battement depuis 3 min : absente
    autre.retirer_presence()
    assert moi.presences_autres() == []


def test_fichier_illisible_donne_sa_raison(tmp_path):
    st = Stockage(tmp_path, "pierre", "PC")
    st.initialiser()
    (st.d_manips / "aaaaaaaa.json").write_text('{"id": "aaaaaaaa", "etapes": [', encoding="utf-8")
    (st.d_manips / "bbbbbbbb.json").write_text('{"id": "bbbbbbbb", "etat": 5}', encoding="utf-8")
    texte = " | ".join(st.lister().illisibles)
    assert "aaaaaaaa.json (fichier incomplet" in texte and "bbbbbbbb.json (champ « etat »" in texte


def test_fichier_occupe_n_est_pas_illisible(tmp_path, monkeypatch):
    import builtins

    st = Stockage(tmp_path, "pierre", "PC")
    st.initialiser()
    (st.d_manips / "cccccccc.json").write_text('{"id": "cccccccc"}', encoding="utf-8")
    ouvrir = builtins.open

    def occupe(chemin, *a, **k):
        if str(chemin).endswith("cccccccc.json"):
            e = PermissionError(13, "utilisé par un autre processus")
            e.winerror = 32
            raise e
        return ouvrir(chemin, *a, **k)

    monkeypatch.setattr(builtins, "open", occupe)
    monkeypatch.setattr("mat_methode.storage.stockage.time.sleep", lambda s: None)
    liste = st.lister()
    assert liste.occupes == ["cccccccc"] and liste.illisibles == []
