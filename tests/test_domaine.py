

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
