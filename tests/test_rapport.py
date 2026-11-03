"""Texte « Matériel et méthodes » (§10) : fichiers de référence et critères 2, 16, 19."""
from mat_methode.domain import regles as R
from mat_methode.domain.models import Manip, ReactifEtape
from mat_methode.domain.texte import fmt_dur, fmt_vol
from mat_methode.report.html import rapport_html
from mat_methode.report.rapport import clause_etape, construire, markdown, quantite_texte

from .conftest import EXEMPLES


def test_crit2_markdown_identique_a_la_reference(ethanol, reglages):
    assert markdown(ethanol, reglages) == (EXEMPLES / "rapport_attendu.md").read_text(encoding="utf-8")


def test_html_identique_a_la_reference(ethanol, reglages):
    assert rapport_html(ethanol, reglages) == (EXEMPLES / "rapport_attendu.html").read_text(encoding="utf-8")


def test_seules_les_corrections_attendues_different_du_prototype(ethanol, reglages):
    """Une fois les lignes recollées, le texte ne diffère de la référence du prototype que sur 2.2 et 2.3 (corrections §14)."""
    from mat_methode.report.rapport import vers_markdown
    proto = (EXEMPLES / "rapport_attendu_prototype.md").read_text(encoding="utf-8").splitlines()
    textes = {s.titre: vers_markdown(" ".join(s.texte.split("\n"))) for s in construire(ethanol, reglages).sections}
    # 2.1 et 2.2 : sans le lot (03/11) ; 2.2 et 2.3 : corrections §14
    for titre, egal in (("2.1 Échantillon", False), ("2.2 Matériel et réactifs", False), ("2.3 Méthodes", False), ("2.4 Prélèvements", True)):
        ancien = proto[proto.index(f"### {titre}") + 2]
        assert (ancien == textes[titre]) is egal, titre


def test_une_idee_par_ligne(ethanol, reglages):
    s = construire(ethanol, reglages).sections
    assert s[0].texte.split("\n")[0].startswith("Demande :") and len(s[0].texte.split("\n")) == 6
    assert s[1].texte.split("\n")[1].startswith("Réactifs :")
    assert [x[:8] for x in s[2].texte.split("\n")] == [f"Étape {i} " for i in range(1, 6)]
    assert len(s[3].texte.split("\n")) == 6


def test_corrections_14_1(ethanol, reglages):
    t = construire(ethanol, reglages).sections[2].texte
    assert "(1 : 1, v/v)" in t and "(v/v))" not in t
    assert "filtré sous vide sur membrane de 5 µm pendant 10 min" in t
    assert t.count("il a ensuite été") == 2 and "il a enfin été séché" in t


def test_crit16_detail_par_phase(ethanol, reglages):
    ph = construire(ethanol, reglages).phases
    assert [p.titre for p in ph] == ["Départ", "1 · Chauffage", "2 · Filtration", "3 · Désacidification", "4 · Décantation", "5 · Séchage"]
    assert [r.scirius for r in ph[3].reactifs] == ["001245", ""] and ph[3].reactifs[0].emplacement.startswith("Armoire")
    assert [e.id for e in ph[3].echantillons] == ["S3a", "S3b"]
    assert ph[1].reactifs == [] and ph[4].reactifs == []
    md = markdown(ethanol, reglages)
    assert "#### 1 · Chauffage\n\n- Conditions : 60 °C · 30 min · 300 tr/min\n- Matériel : Plaque chauffante agitatrice\n- Réactifs : aucun" in md


def test_crit19_references_aux_etapes(ethanol, reglages):
    s = construire(ethanol, reglages).sections
    assert "Le flux comporte 5 étapes (étapes 1 à 5)" in s[0].texte
    assert "ampoule à décanter 500 mL (étapes 3, 4)" in s[1].texte and "éthanol 96 % (étape 3," in s[1].texte
    assert all(f"Étape {i} :" in s[2].texte for i in range(1, 6))
    R.ajouter_etape(ethanol, "broyage", apres=-1)
    s = construire(ethanol, reglages).sections
    assert "(étapes 4, 5)" in s[1].texte and "Étape 6 :" in s[2].texte and "pendant l’étape 4 (désacidification)" in s[3].texte


def test_reperes_jamais_inventes(reglages):
    m = Manip(nom="Vide")
    m.contexte.donneur = ""
    m.contexte.volume_depart_ml = None
    r = construire(m, reglages)
    assert "{{?donneur d’ordre}}" in r.sections[0].texte and "{{?volume de départ}}" in r.sections[0].texte
    assert r.sections[2].texte == "{{?protocole}}" and len(r.sections) == 3
    assert "[protocole à saisir]" in markdown(m, reglages)
    assert '<span class="ph">protocole à saisir</span>' in rapport_html(m, reglages)


def test_phrases_facultatives(ethanol, reglages):
    c = ethanol.contexte
    c.type, c.idee, c.objectif, c.precisions = "Test d’idée", "Remplacer le solvant.", "Objectif. ", ""
    t = construire(ethanol, reglages).sections[0].texte
    assert "Idée testée : Remplacer le solvant." in t and "Objectif : Objectif." in t and "Contexte" not in t
    c.type = "R&D"
    assert "Idée testée" not in construire(ethanol, reglages).sections[0].texte


def test_clause_etape():
    m = Manip()
    e = R.ajouter_etape(m, "centrifugation")
    e.agitation_trmin, e.duree_min = 4000, 90
    assert clause_etape(e) == "centrifugé pendant 1 h 30 à 4 000 tr/min"
    e = R.ajouter_etape(m, "neutralisation")
    e.reactifs = [ReactifEtape(nom="Soude", quantite="2 g"), ReactifEtape(nom="Hexane")]
    e.remarque = "à l’abri de la lumière"
    e.autres = [{"nom": "pH", "valeur": "7"}]
    assert clause_etape(e) == "traité (neutralisation) en présence de soude (2 g) et d’hexane pH 7 (à l’abri de la lumière)"


def test_formats():
    assert [fmt_dur(x) for x in (30, 60, 120, 65, 90)] == ["30 min", "1 h", "2 h", "1 h 05", "1 h 30"]
    assert fmt_vol(1000) == "1 000" and fmt_vol(2.5) == "2,5"
    assert quantite_texte("1 : 1 (v/v)") == "1 : 1, v/v" and quantite_texte("10 mL") == "10 mL"


def test_mention_lancement(ethanol, reglages):
    md = markdown(ethanol, reglages)
    assert "Version 4 · enregistrée le 30/10/2026 à 22:10 · lancée le 30/10/2026 à 20:45 par Pierre" in md
    assert "⚠ Modifiée après lancement (2 modifications)" in md and "### Modifications après lancement" in md
    ethanol.lancee, ethanol.journal = None, []
    md = markdown(ethanol, reglages)
    assert "Version 4 · enregistrée" in md and "lancement" not in md.lower()


def test_plus_de_lot_dans_les_documents(ethanol, reglages):
    md = markdown(ethanol, reglages)
    import re
    assert not re.search(r"\blot\b", md, re.I) and "| Lot |" not in md
