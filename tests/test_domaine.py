

def test_etapes_en_parallele_voies_et_convergence(exemples):
    from mat_methode.domain import regles as R
    m = exemples[1][0].copie()
    ids = [e.id for e in m.etapes]
    p = R.creer_parallele(m)
    a, b = p.voies[0].id, p.voies[1].id
    assert R.placer_dans_voie(m, ids[1], p.id, a) and R.placer_dans_voie(m, ids[2], p.id, b) and R.placer_dans_voie(m, ids[3], p.id, a)
    # le bloc reste d'un seul tenant, voie A puis voie B
    ordre = [e.id for e in m.etapes]
    assert ordre == [ids[0], ids[1], ids[3], ids[2], ids[4]]
    seg = R.segments(m)
    assert [s[0] for s in seg] == ["seq", "par", "seq"] and seg[1][2] == [[1, 2], [3]] and seg[2][2] == [4]
    assert [R.lettre_voie(m, e.parallele_id, e.voie_id) for e in m.etapes[1:4]] == ["A", "A", "B"]
    # une étape ne peut pas être à la fois en voie et en grande étape
    g = R.creer_groupe(m, "Degumming")
    R.placer_dans_groupe(m, ids[1], g.id)
    assert m.etape(ids[1]).parallele_id is None
    # sortir du bloc : l'étape se place après lui
    assert R.sortir_de_parallele(m, ids[2])
    assert [e.id for e in m.etapes][-2:] == [ids[2], ids[4]] or m.etape(ids[2]).parallele_id is None
    # une 3e voie, puis suppression : les étapes passent dans la 1re voie ; moins de 2 voies refusé
    assert R.ajouter_voie(m, p.id) and len(p.voies) == 3
    assert R.supprimer_voie(m, p.id, p.voies[2].id) and not R.supprimer_voie(m, p.id, p.voies[1].id)
    # copie : nouveaux identifiants, voies conservées
    from mat_methode.domain.models import Reglages
    c = R.dupliquer(m, Reglages())
    assert c.paralleles and c.paralleles[0].id != p.id and all(e.parallele_id in (None, c.paralleles[0].id) for e in c.etapes)
    R.defaire_parallele(m, p.id)
    assert not m.paralleles and all(e.parallele_id is None for e in m.etapes)


def test_historique_des_statuts_en_initiales_jamais_igg(reglages):
    from mat_methode.domain import reglages_ops as O
    from mat_methode.domain.models import Personne
    reglages.personnes.append(Personne(nom="Pierre BURGUN", igg="J0034240", initiales="PB"))
    assert O.auteur(reglages, "J0034240") == "PB" and O.nom_auteur(reglages, "J0034240") == "PB"
    assert O.auteur(reglages, "J9999999") == "?"  # IGG inconnu : jamais affiché
    assert O.auteur(reglages, "Alice LIMOGES") == "AL"


def test_volume_apres_reunion_compte_les_reactifs_liquides(exemples):
    from mat_methode.domain import regles as R
    from mat_methode.domain.models import ReactifEtape
    from mat_methode.domain.volumes import volumes_par_etape
    m = exemples[1][0].copie()
    ids = [e.id for e in m.etapes]
    p = R.creer_parallele(m)
    R.placer_dans_voie(m, ids[1], p.id, p.voies[0].id)
    R.placer_dans_voie(m, ids[2], p.id, p.voies[1].id)
    m.contexte.volume_depart_ml = 100
    reunion = next(i for i, e in enumerate(m.etapes) if e.parallele_id is None and i > 0 and m.etapes[i - 1].parallele_id)
    avant = {lg.indice: lg for lg in volumes_par_etape(m)}[reunion]
    m.etapes[reunion].reactifs = [ReactifEtape(nom="Acide", quantite="5", unite="mL"), ReactifEtape(nom="Terre", quantite="3", unite="g")]
    apres = {lg.indice: lg for lg in volumes_par_etape(m)}[reunion]
    assert apres.ajoute == 5 and abs(apres.sortie - (avant.sortie + 5)) < 1e-9  # les grammes ne comptent pas dans le volume


def test_export_demandes_avec_pieces_jointes():
    from mat_methode.domain.demandes import Demande, vers_markdown
    d = Demande(auteur="x", type="Bug", titre="t", texte="d", pieces=["capture.png", "journal.txt"])
    md = vers_markdown([d], lambda a: a, "1.8.0", lambda dem, nom: f"export_pieces/{nom}")
    assert "![capture.png](export_pieces/capture.png)" in md and "[journal.txt](export_pieces/journal.txt)" in md
