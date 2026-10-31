"""Opérations modifiables dans les Réglages, renommage (tags, donneurs…), état « Non réalisée »."""
from mat_methode.domain import reglages_ops as O
from mat_methode.domain import regles as R
from mat_methode.domain.models import ARCHIVEE, NON_REALISEE, Manip, Reglages
from mat_methode.report.rapport import construire


def test_operations_par_defaut_et_participe():
    r = Reglages()
    assert [o.nom for o in r.operations][:3] == ["chauffage", "filtration", "désacidification"]
    assert r.participe("filtration") == "filtré" and r.participe("neutralisation") == "traité (neutralisation)"


def test_ajouter_renommer_supprimer_operation(exemples):
    r, manips = exemples
    assert O.ajouter_operation(r, "Neutralisation", "neutralisé")
    assert not O.ajouter_operation(r, "neutralisation")  # déjà là
    m = Manip()
    R.ajouter_etape(m, "neutralisation")
    assert "Étape 1 : le produit a été neutralisé." in construire(m, r).sections[2].texte
    ch = O.renommer_operation(r, manips, "filtration", "filtration sous vide")
    assert ch and all(e.operation != "filtration" for mm in manips for e in mm.etapes)
    assert r.participe("filtration sous vide") == "filtré"  # le participe suit l'opération
    assert O.renommer_operation(r, manips, "chauffage", "séchage") == []  # nom déjà pris
    O.supprimer_operation(r, "broyage")
    assert r.operation("broyage") is None
    assert O.deplacer_operation(r, 0, 1) and r.operations[1].nom == "chauffage"


def test_participe_modifiable():
    r = Reglages()
    r.operation("séchage").participe = "séché à l’étuve"
    m = Manip()
    R.ajouter_etape(m, "séchage")
    assert "le produit a été séché à l’étuve." in construire(m, r).sections[2].texte


def test_renommer_donneur_type_analyse(exemples):
    r, manips = exemples
    ch = O.renommer_donneur(r, manips, "Interne · R&D", "R&D Lyon")
    assert len(ch) == 3 and "R&D Lyon" in r.donneurs_ordre and "Interne · R&D" not in r.donneurs_ordre
    assert all(m.contexte.donneur != "Interne · R&D" for m in manips)
    assert O.renommer_donneur(r, manips, "R&D Lyon", "client externe") == []  # déjà pris (casse ignorée)
    assert O.renommer_type(r, manips, "R&D", "Recherche") and manips[0].contexte.type == "Recherche"
    O.renommer_analyse(r, manips, "Phosphore", "Phosphore total")
    assert "Phosphore total" in r.laboratoire("Labo externe").analyses
    assert any("Phosphore total" in p.analyses for p in manips[0].prelevements)


def test_renommer_reactif_garde_les_infos(exemples):
    r, manips = exemples
    ch = O.renommer_reactif(r, manips, "Éthanol 96 %", "Éthanol 96 % (Carlo Erba)")
    assert ch and r.reactif("Éthanol 96 % (Carlo Erba)").scirius == "001245"
    assert manips[0].etapes[2].reactifs[0].nom == "Éthanol 96 % (Carlo Erba)"


def test_renommer_grande_etape():
    r = Reglages()
    m = Manip()
    g = R.creer_groupe(m, "Degumming")
    assert O.renommer_grande_etape(r, [m], "Degumming", "Dégommage") == [m] and g.nom == "Dégommage"


def test_renommer_tag_sans_doublon(exemples):
    _, manips = exemples
    ch = O.renommer_tag(manips, "ffa", "acides gras libres")
    assert len(ch) == 2 and all("FFA" not in m.tags for m in manips)
    # fusion de deux tags : pas de doublon dans une manip qui avait les deux
    manips[0].tags.append("graisse")
    O.renommer_tag(manips, "graisse", "graisse animale")
    assert manips[0].tags.count("graisse animale") == 1


def test_non_realisee(reglages, ethanol):
    assert not O.peut_supprimer(ethanol)
    assert O.basculer_non_realisee(reglages, ethanol) and ethanol.etat == NON_REALISEE
    assert O.peut_supprimer(ethanol) and O.nom_etat(reglages, ethanol.etat) == ("Non réalisée", "danger")
    assert O.archiver_ou_restaurer(reglages, ethanol) and ethanol.etat == ARCHIVEE and O.peut_supprimer(ethanol)
    ethanol.etat = NON_REALISEE
    assert not O.basculer_non_realisee(reglages, ethanol) and ethanol.etat == reglages.etat_initial()


def test_fusion_operations():
    from mat_methode.storage.fusion import fusionner
    base = Reglages()
    mien, leur = base.model_copy(deep=True), base.model_copy(deep=True)
    O.ajouter_operation(mien, "neutralisation", "neutralisé")
    O.ajouter_operation(leur, "hydrogénation", "hydrogéné")
    noms = [o.nom for o in fusionner(base, mien, leur).operations]
    assert "neutralisation" in noms and "hydrogénation" in noms


def test_volumes_echantillon():
    from mat_methode.domain.texte import libelle_volume
    r = Reglages()
    assert r.volumes_ml == [30, 60, 120, 250, 500, 1000]
    assert [libelle_volume(v) for v in (30, 250, 1000, 2000)] == ["30 mL", "250 mL", "1 L", "2 L"]
    assert O.ajouter_volume(r, 2000) and not O.ajouter_volume(r, 60) and not O.ajouter_volume(r, None)
    O.supprimer_volume(r, 30)
    assert r.volumes_ml == [60, 120, 250, 500, 1000, 2000]
    r.laboratoires = []
    p = R.nouvel_echantillon(Manip(), r, None)
    assert p.volume_ml == 60  # sans laboratoire : premier volume de la liste
