"""Lancement et journal des modifications (§8.9) : critères 30 et 31."""
from mat_methode.domain import journal as J
from mat_methode.domain import regles as R
from mat_methode.domain.regles import etiquettes


def _lancee(m):
    m.lancee, m.journal, m.base = None, [], None
    J.lancer(m, par="Pierre")
    return m


def test_crit30_modification_journalisee(ethanol):
    _lancee(ethanol)
    assert J.peut_annuler_lancement(ethanol)
    ethanol.etapes[2].temperature_c = 30
    lignes = J.journaliser(ethanol, par="Pierre")
    assert [x.txt for x in lignes] == ["Étape 3 · Désacidification : température 25 → 30 °C"]
    assert ethanol.journal[0].par == "Pierre" and not J.peut_annuler_lancement(ethanol)
    assert not J.annuler_lancement(ethanol) and ethanol.lancee is not None


def test_crit31_une_ligne_par_saisie(ethanol):
    _lancee(ethanol)
    ethanol.etapes[2].temperature_c = 3
    ethanol.etapes[2].temperature_c = 30  # deux frappes regroupées : un seul journaliser() après 0,6 s
    assert len(J.journaliser(ethanol)) == 1
    assert J.journaliser(ethanol) == []  # rien de neuf


def test_crit31_suppression_sans_deplacement(ethanol):
    _lancee(ethanol)
    R.supprimer_etape(ethanol, ethanol.etapes[3].id)
    txt = [x.txt for x in J.journaliser(ethanol)]
    assert txt == ["Étape supprimée : Décantation (était l’étape 4)"]


def test_deplacement_note(ethanol):
    _lancee(ethanol)
    R.deplacer_etape(ethanol, ethanol.etapes[0].id, +1)
    txt = [x.txt for x in J.journaliser(ethanol)]
    assert "Étape 2 · Chauffage : déplacée (étape 1 → 2)" in txt and "Étape 1 · Filtration : déplacée (étape 2 → 1)" in txt


def test_rien_avant_lancement(ethanol):
    ethanol.lancee, ethanol.journal, ethanol.base = None, [], None
    ethanol.etapes[0].temperature_c = 70
    assert J.journaliser(ethanol) == [] and ethanol.journal == []


def test_exemples_de_lignes(ethanol, reglages):
    _lancee(ethanol)
    lab = etiquettes(ethanol)
    s3a = next(p for p in ethanol.prelevements if lab[p.id] == "S3a")
    s3a.volume_ml = 40
    ethanol.etapes[2].reactifs[0].quantite = "1 : 2 (v/v)"
    ethanol.contexte.objectif = "Nouvel objectif"
    R.ajouter_tags(ethanol, "pilote", [])
    R.ajouter_etape(ethanol, "lavage")
    p = R.nouvel_echantillon(ethanol, reglages, ethanol.etapes[2].id)
    p.volume_ml = 25
    txt = [x.txt for x in J.journaliser(ethanol)]
    assert "Échantillon S3a : volume 50 → 40 mL" in txt
    assert "Étape 3 · Désacidification : réactif Éthanol 96 %, quantité 1 : 1 (v/v) → 1 : 2 (v/v)" in txt
    assert any(t.startswith("Demande · objectif : Réduire") and t.endswith("→ Nouvel objectif") for t in txt)
    assert "Tag ajouté : #pilote" in txt and "Étape ajoutée : Étape 6 · Lavage" in txt
    assert "Échantillon ajouté : S3c (25 mL, effluent)" in txt


def test_rattrapage_apres_fermeture_brutale(ethanol):
    """La photo de référence est enregistrée avec la manip : à la réouverture, on retrouve l'écart."""
    from mat_methode.domain.models import Manip
    _lancee(ethanol)
    ethanol.etapes[0].duree_min = 45  # modifié puis fermé avant la journalisation
    relue = Manip.model_validate(ethanol.to_json())
    lignes = J.rattraper(relue)
    assert [x.txt for x in lignes] == ["Étape 1 · Chauffage : durée 30 → 45 min"] and lignes[0].t == relue.maj


def test_duplication_sans_journal(ethanol, reglages):
    c = R.dupliquer(ethanol, reglages)
    assert c.lancee is None and c.journal == [] and c.base is None and c.rev == 1
