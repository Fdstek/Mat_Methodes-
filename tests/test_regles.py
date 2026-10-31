"""Règles métier (§8) et critères d'acceptation §17 n° 1, 3 à 7, 21 à 23."""
from mat_methode.domain import reglages_ops as O
from mat_methode.domain import regles as R
from mat_methode.domain.models import ARCHIVEE, Etape, Manip, Prelevement


def test_crit1_manip_exemple(ethanol):
    b = R.bilan(ethanol)
    assert (len(ethanol.etapes), b.n, b.preleve, b.restant, b.numeros_a_saisir) == (5, 6, 325, 675, 8)


def test_crit3_etiquettes(ethanol):
    lab = R.etiquettes(ethanol)
    assert sorted(lab.values()) == ["S0", "S2", "S3a", "S3b", "S5a", "S5b"]
    e3 = ethanol.etapes[2]
    s3 = [p for p in R.echantillons_tries(ethanol) if p.etape_id == e3.id]
    assert [lab[p.id] for p in s3] == ["S3a", "S3b"] and s3[0].moment == "pendant" and s3[1].moment == "effluent"
    ethanol.prelevements.remove(s3[0])
    assert R.etiquettes(ethanol)[s3[1].id] == "S3"


def test_ordre_avant_pendant_effluent():
    m = Manip()
    e = R.ajouter_etape(m, "chauffage")
    p_eff = Prelevement(etape_id=e.id, moment="effluent")
    p_20 = Prelevement(etape_id=e.id, moment="pendant", temps_min=20)
    p_5 = Prelevement(etape_id=e.id, moment="pendant", temps_min=5)
    m.prelevements = [p_eff, p_20, p_5]
    lab = R.etiquettes(m)
    assert (lab[p_5.id], lab[p_20.id], lab[p_eff.id]) == ("S1a", "S1b", "S1c")


def test_code_badge():
    assert (R.code_badge("S3a"), R.code_badge("S2"), R.code_badge("S0")) == ("a", "2", "0")


def test_crit4_conditions_communes():
    m = Manip()
    for op in ("chauffage", "désacidification", "centrifugation", "séchage"):
        R.ajouter_etape(m, op)
    m.etapes[0].agitation_trmin = 300
    m.etapes[1].agitation_trmin = 300
    m.etapes[2].agitation_trmin = 4000
    R.basculer_commune(m, "agitation_trmin")
    m.communes.agitation_trmin = 250
    R.appliquer_communes(m)
    assert [e.agitation_trmin for e in m.etapes] == [300, 300, 4000, 250]
    R.appliquer_communes(m, remplacer=True)
    assert [e.agitation_trmin for e in m.etapes] == [250, 250, 4000, 250]
    # une étape créée ensuite hérite des conditions communes, sauf l'agitation pour une centrifugation
    assert R.ajouter_etape(m, "lavage").agitation_trmin == 250
    assert R.ajouter_etape(m, "centrifugation").agitation_trmin is None


def test_crit5_inserer_apres_etape_1(ethanol):
    lab_avant = R.etiquettes(ethanol)
    s2 = next(p for p in ethanol.prelevements if lab_avant[p.id] == "S2")
    e = R.ajouter_etape(ethanol, "lavage", apres=0)
    assert ethanol.etapes[1] is e and len(ethanol.etapes) == 6
    lab = R.etiquettes(ethanol)
    assert lab[s2.id] == "S3"  # l'échantillon suit son étape (filtration, devenue 3)
    assert sorted(lab.values()) == ["S0", "S3", "S4a", "S4b", "S6a", "S6b"]
    R.ajouter_etape(ethanol, "broyage", apres=-1)  # au début
    assert ethanol.etapes[0].operation == "broyage"


def test_supprimer_etape_supprime_ses_echantillons(ethanol):
    e3 = ethanol.etapes[2]
    R.supprimer_etape(ethanol, e3.id)
    assert len(ethanol.etapes) == 4 and len(ethanol.prelevements) == 4


def test_deplacer_dupliquer(ethanol):
    ids = [e.id for e in ethanol.etapes]
    assert R.deplacer_etape(ethanol, ids[0], +1)
    assert [e.id for e in ethanol.etapes][:2] == [ids[1], ids[0]]
    assert not R.deplacer_etape(ethanol, ids[4], +1)
    c = R.dupliquer_etape(ethanol, ids[2])
    assert c.id != ids[2] and c.operation == "désacidification" and ethanol.etapes.index(c) == 3


def test_crit6_changer_labo(ethanol, reglages):
    p = ethanol.prelevements[0]
    R.changer_labo(p, reglages, "Labo externe")
    assert p.volume_ml == 100 and p.analyses == ["Métaux (ICP)", "Phosphore"]


def test_nouvel_echantillon_reprend_dernier_labo(ethanol, reglages):
    p = R.nouvel_echantillon(ethanol, reglages, ethanol.etapes[0].id)
    assert p.labo == "Labo externe" and p.volume_ml == 100 and p.moment == "effluent"
    vide = Manip()
    p0 = R.nouvel_echantillon(vide, reglages, None)
    assert p0.labo == "Labo interne" and p0.volume_ml == 50 and p0.moment == "avant"


def test_conditions_bascule():
    e = Etape(operation="chauffage")
    R.basculer_condition(e, "temperature_c")
    R.basculer_condition(e, "filtre_um")
    R.basculer_condition(e, "vide")
    assert (e.temperature_c, e.filtre_um, e.vide.mbar) == (60, 5, None)
    R.basculer_condition(e, "temperature_c")
    assert e.temperature_c is None


def test_crit7_dupliquer(ethanol, reglages):
    c = R.dupliquer(ethanol, reglages)
    assert c.nom == "Désacidification éthanol (copie)" and c.id != ethanol.id
    assert c.contexte.ref == "" and c.contexte.lot == ""
    assert all(p.scirius == "" and p.aramis == "" for p in c.prelevements)
    assert c.etat == "brouillon" and c.rev == 1 and c.lancee is None and c.journal == []
    assert c.tags == ethanol.tags and c.contexte.objectif == ethanol.contexte.objectif
    assert [e.operation for e in c.etapes] == [e.operation for e in ethanol.etapes]
    assert {p.etape_id for p in c.prelevements} <= {e.id for e in c.etapes} | {None}
    assert sorted(R.etiquettes(c).values()) == sorted(R.etiquettes(ethanol).values())


def test_crit21_couleur_donneur(reglages, exemples):
    manips = exemples[1]
    prod = [m for m in manips if not m.archivee and m.contexte.donneur == "Interne · Production"]
    assert len(prod) == 1
    assert O.couleur_donneur(reglages, "Interne · R&D") != O.couleur_donneur(reglages, "Interne · Production")


def test_crit22_etats(reglages, exemples):
    manips = exemples[1]
    i = [e.id for e in reglages.etats].index("encours")
    reglages.etats[i].nom, reglages.etats[i].ton = "En attente de résultats", "danger"
    assert reglages.etat(manips[0].etat).nom == "En attente de résultats"
    manips[0].etat = "brouillon"
    changees, msg = O.supprimer_etat(reglages, manips, 0)
    assert manips[0] in changees and manips[0].etat == "encours" and "passée" in msg
    while len(reglages.etats) > 1:
        O.supprimer_etat(reglages, manips, 0)
    assert O.supprimer_etat(reglages, manips, 0) == ([], "")
    assert len(reglages.etats) == 1 and ARCHIVEE not in [e.id for e in reglages.etats]


def test_archiver_restaurer(reglages, ethanol):
    assert O.archiver_ou_restaurer(reglages, ethanol) and ethanol.archivee
    assert not O.archiver_ou_restaurer(reglages, ethanol) and ethanol.etat == reglages.etat_initial()


def test_crit23_tags(ethanol, exemples):
    tous = R.tous_les_tags(exemples[1])
    ajoutes = R.ajouter_tags(ethanol, "nouveau tag, pilote, ffa, #Séchage", tous)
    assert ajoutes == ["nouveau tag", "pilote", "séchage"]  # « ffa » = « FFA » déjà là ; orthographe reprise
    assert R.est_test("Test d’idée") and not R.est_test("R&D")


def test_reglages_laboratoires_et_analyses(reglages, exemples):
    manips = exemples[1]
    ch = O.renommer_laboratoire(reglages, manips, "Labo externe", "Labo Lyon")
    assert ch and all(p.labo != "Labo externe" for m in manips for p in m.prelevements)
    O.supprimer_analyse(reglages, "Phosphore")
    assert "Phosphore" not in reglages.laboratoire("Labo Lyon").analyses
    O.supprimer_laboratoire(reglages, "Labo Lyon")
    assert any(p.labo == "Labo Lyon" for p in manips[0].prelevements)  # le libellé reste


def test_avertissements(ethanol, exemples):
    p = next(p for p in ethanol.prelevements if p.temps_min == 10)
    p.temps_min = 20  # étape de 15 min
    p.aramis = "000873"  # déjà utilisé par S0
    msgs = R.avertissements(ethanol, exemples[1])
    assert any("après la fin de l’étape" in x for x in msgs)
    assert any("Aramis 000873 en double" in x for x in msgs)


def test_analyses_possibles_selon_le_labo(ethanol, reglages):
    p = next(p for p in ethanol.prelevements if p.labo == "Labo externe")
    assert R.analyses_possibles(reglages, p) == ["Métaux (ICP)", "Phosphore"]
    p.analyses.append("Teneur en eau")  # déjà cochée hors labo : reste visible
    assert R.analyses_possibles(reglages, p)[-1] == "Teneur en eau"
    p.labo = "Labo inconnu"
    assert R.analyses_possibles(reglages, p)[:5] == reglages.analyses
