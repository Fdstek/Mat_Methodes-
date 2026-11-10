"""Photos SamplesTEK retrouvées par le n° Aramis, sur une fausse base « echantillons.db » (même table que SamplesTEK)."""
import sqlite3

import pdfplumber
from PIL import Image

from mat_methode import photos_samplestek as P
from mat_methode.exports.echange import exporter


def base(racine, deplacer=False):
    """Base au format SamplesTEK (db.init_db) avec 3 photos : 2 pour l'Aramis 2026-005555, 1 pour un autre échantillon."""
    racine.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(racine / "echantillons.db")
    con.execute("""CREATE TABLE photos (id INTEGER PRIMARY KEY AUTOINCREMENT, sample_id TEXT NOT NULL, usine TEXT, feedstock TEXT,
                   temperature TEXT, incident INTEGER DEFAULT 0, culot INTEGER DEFAULT 0, comment TEXT, filepath TEXT NOT NULL,
                   created_at TEXT NOT NULL, avg_color_hex TEXT, series_tag TEXT)""")
    for k, (ech, temp, culot, com) in enumerate([("2026-005555", "T° ambiante", 0, ""), ("2026-005555 ", "70°C", 1, "dépôt au fond"),
                                                  ("2026-009999", "50°C", 0, "")]):
        d = racine / "GPS" / "Graisse" / ech.strip()
        d.mkdir(parents=True, exist_ok=True)
        f = d / f"{ech.strip()}_{k}.jpg"
        Image.new("RGB", (1600, 1200), (200, 120 + 40 * k, 30)).save(f, quality=90)
        chemin = str(f) if not deplacer else rf"D:\AncienDossier\GPS\Graisse\{ech.strip()}\{f.name}"
        con.execute("INSERT INTO photos (sample_id, temperature, culot, comment, filepath, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (ech, temp, culot, com, chemin, f"2026-11-10 14:0{k}:00"))
    con.commit()
    con.close()
    return racine


def test_lecture_par_aramis(tmp_path):
    lu = P.lire(str(base(tmp_path / "photos")), ["2026-005555", "2026-000000"])
    assert list(lu.photos) == ["2026-005555"] and len(lu.photos["2026-005555"]) == 2  # « 2026-005555 » avec espace en trop : retrouvé
    ph = lu.photos["2026-005555"]
    assert P.legende(ph[1]) == "70°C · 10/11/2026 14:01 · culot"
    bloc = P.pour_export(lu, [{"id": "S2", "aramis": "2026-005555"}, {"id": "S3", "aramis": ""}])
    assert bloc[0]["id"] == "S2" and bloc[0]["photos"][1]["commentaire"] == "dépôt au fond"
    # dossier déplacé : la photo est retrouvée par son nom sous le dossier de stockage
    lu2 = P.lire(str(base(tmp_path / "deplace", deplacer=True)), ["2026-005555"])
    assert all(x["fichier"].startswith(str(tmp_path / "deplace")) for x in lu2.photos["2026-005555"])
    # base absente : message clair, rien ne casse
    assert "introuvable" in P.lire(str(tmp_path / "rien"), ["2026-005555"]).erreur
    # miniature réduite pour les documents
    m = P.miniature(bloc[0]["photos"][0]["fichier"], tmp_path / "tmp", 300)
    assert max(Image.open(m).size) == 300


def test_documents_avec_photos(ethanol, reglages, tmp_path):
    from mat_methode.exports.pdf import ecrire_pdf
    from mat_methode.exports.protocole import ecrire_protocole
    from mat_methode.exports.word import ecrire_docx
    ethanol.prelevements[1].aramis = "2026-005555"
    data = exporter(ethanol, reglages)
    lu = P.lire(str(base(tmp_path / "photos")), [p["aramis"] for p in data["prelevements"] if p.get("aramis")])
    data["photos"] = P.pour_export(lu, data["prelevements"])
    for ecrire, nom in ((ecrire_pdf, "r.pdf"), (ecrire_protocole, "p.pdf")):
        ecrire(data, tmp_path / nom)
        with pdfplumber.open(tmp_path / nom) as pdf:
            texte = " ".join(" ".join(p.extract_text() for p in pdf.pages).split())
            n = sum(len(p.images) for p in pdf.pages)
        assert "Photos des échantillons (SamplesTEK)" in texte and "n° Aramis 2026-005555" in texte and "70°C" in texte and n >= 2, nom
    import docx
    ecrire_docx(data, tmp_path / "r.docx")
    w = docx.Document(str(tmp_path / "r.docx"))
    assert any("Photos des échantillons" in p.text for p in w.paragraphs) and len(w.inline_shapes) >= 3


def test_carte_photos(qtbot, tmp_path, qapp):
    from mat_methode.storage.stockage import Stockage
    from mat_methode.ui import theme
    from mat_methode.ui.controleur import Controleur
    from mat_methode.ui.fenetre import Fenetre
    from mat_methode.ui.widgets import Expander
    theme.appliquer(qapp, "clair")
    ctrl = Controleur(Stockage(tmp_path, "pierre", "PC1"))
    f = Fenetre(ctrl)
    qtbot.addWidget(f)
    ctrl.demarrer()
    ctrl.choisir_dossier_samplestek(str(base(tmp_path / "photos")))
    m = next(x for x in ctrl.manips if x.nom == "Désacidification éthanol")
    m.prelevements[1].aramis = "2026-005555"
    f.ouvrir(m.id)
    f.p_rapport.rafraichir()
    carte = next(x for x in f.p_rapport.findChildren(Expander) if x._titre == "Photos des échantillons (SamplesTEK)")
    assert carte._note == "2 photos"
    data = exporter(m, ctrl.reglages)
    f._ajouter_resultats(data, m)
    assert len(data["photos"][0]["photos"]) == 2 and all(p["miniature"].endswith(".jpg") for p in data["photos"][0]["photos"])
    ctrl.fermer()
