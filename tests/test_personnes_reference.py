"""Personnes (donneurs d'ordre), IGG Windows, référence automatique PB-2026-10-31-01."""
from mat_methode.domain import regles as R
from mat_methode.domain.models import Manip, Personne, Reglages
from mat_methode.storage.chemins import utilisateur


def test_ancien_format_donneurs_ordre():
    r = Reglages.model_validate({"donneurs_ordre": ["Pierre BURGUN", "Interne · R&D"]})
    assert [(p.nom, p.sigle()) for p in r.personnes] == [("Pierre BURGUN", "PB"), ("Interne · R&D", "IR")]
    assert r.donneurs_ordre == ["Pierre BURGUN", "Interne · R&D"] and "donneurs_ordre" not in r.to_json()


def test_reference_automatique():
    r = Reglages(personnes=[Personne(nom="Pierre BURGUN", initiales="PB"), Personne(nom="Claire LACOUX")])
    a, b, c = Manip(), Manip(), Manip()
    for m in (a, b, c):
        m.contexte.date = "2026-10-31"
    a.contexte.donneur = b.contexte.donneur = "Pierre BURGUN"
    c.contexte.donneur = "Claire LACOUX"
    assert R.reference_auto(a, r, [a, b, c]) and a.contexte.ref == "PB-2026-10-31-01"
    assert R.reference_auto(b, r, [a, b, c]) and b.contexte.ref == "PB-2026-10-31-02"
    assert R.reference_auto(c, r, [a, b, c]) and c.contexte.ref == "CL-2026-10-31-01"
    assert not R.reference_auto(a, r, [a, b, c])  # déjà la bonne
    a.contexte.ref = "DA-2026-0158"  # saisie à la main : gardée
    assert not R.reference_auto(a, r, [a, b, c]) and a.contexte.ref == "DA-2026-0158"
    assert R.reference_auto(a, r, [a, b, c], forcer=True) and a.contexte.ref == "PB-2026-10-31-03"
    b.contexte.donneur = "Claire LACOUX"  # changement de donneur : la référence automatique suit
    assert R.reference_auto(b, r, [a, b, c]) and b.contexte.ref == "CL-2026-10-31-02"
    inconnu = Manip()
    inconnu.contexte.donneur = "Quelqu’un"
    assert not R.reference_auto(inconnu, r, [inconnu])


def test_igg_depuis_le_chemin_onedrive(monkeypatch):
    monkeypatch.setenv("OneDriveCommercial", "/Users/j0123456/OneDrive - TotalEnergies")
    monkeypatch.setenv("USERNAME", "autre")
    assert utilisateur() == "J0123456"
    monkeypatch.delenv("OneDriveCommercial")
    monkeypatch.delenv("OneDrive", raising=False)
    monkeypatch.setenv("USERPROFILE", "/home/x")
    assert utilisateur() == "AUTRE"


def test_personne_par_igg():
    r = Reglages(personnes=[Personne(nom="Pierre BURGUN", igg="j0123456")])
    assert r.personne_igg("J0123456").nom == "Pierre BURGUN" and r.personne_igg("") is None


def test_charge_dans_le_texte(ethanol, reglages):
    from mat_methode.report.rapport import construire
    ethanol.contexte.scirius, ethanol.contexte.fournisseur = "000777", "Interne"
    t = construire(ethanol, reglages).sections[0].texte
    assert "Matière étudiée : Graisse animale (lot {{?n°}}, n° Scirius 000777, fournisseur Interne)." in t
