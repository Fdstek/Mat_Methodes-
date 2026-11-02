"""Page « Protocole › Édition » : aperçu du PDF de paillasse ou modification du flux, puis export PDF."""
from __future__ import annotations

import logging
import tempfile
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from mat_methode.domain import regles as R
from mat_methode.exports.echange import exporter
from mat_methode.ui.controleur import Controleur
from mat_methode.ui.page_flux import PageFlux
from mat_methode.ui.page_rapport import ligne_emis
from mat_methode.ui.widgets import InfoBar, Segmente, bouton, carte, etiquette, ligne, vider

LARGEUR_APERCU = 820  # px


def pages_png(chemin_pdf: Path, largeur: int = LARGEUR_APERCU) -> list[QImage]:
    """Rend chaque page du PDF en image (pypdfium2, livré avec pdfplumber)."""
    import pypdfium2 as pdfium
    doc = pdfium.PdfDocument(str(chemin_pdf))
    try:
        out = []
        for page in doc:
            echelle = largeur / page.get_width()
            img = page.render(scale=echelle).to_pil().convert("RGB")
            q = QImage(img.tobytes("raw", "RGB"), img.width, img.height, img.width * 3, QImage.Format.Format_RGB888)
            out.append(q.copy())  # copie : les octets de PIL ne survivent pas à la fonction
        return out
    finally:
        doc.close()


class PageProtocole(QWidget):
    exporter_pdf = Signal()
    ouvrir_fichier = Signal(str)
    ouvrir_dossier = Signal()

    def __init__(self, ctrl: Controleur):
        super().__init__()
        self.ctrl = ctrl
        racine = QVBoxLayout(self)
        racine.setContentsMargins(0, 0, 0, 0)
        racine.setSpacing(14)
        self.haut = QWidget()
        self.lay = QVBoxLayout(self.haut)
        self.lay.setContentsMargins(0, 0, 0, 0)
        self.lay.setSpacing(14)
        racine.addWidget(self.haut)
        self.flux = PageFlux(ctrl)  # « Modifier » : le même éditeur que Définition › Flux
        racine.addWidget(self.flux)
        self.apercu = QWidget()
        self.l_apercu = QVBoxLayout(self.apercu)
        self.l_apercu.setContentsMargins(0, 0, 0, 0)
        self.l_apercu.setSpacing(14)
        racine.addWidget(self.apercu)
        self.mode = "apercu"
        self.nb_pages = 0

    def ouvrir(self, mode: str = "apercu"):
        self.mode = mode
        self.flux.ouvrir("comp" if self.ctrl.courante and self.ctrl.courante.etapes else "def")

    def _mode(self, mode: str):
        self.mode = mode
        self.rafraichir()

    def rafraichir(self, structure=True):
        m, r = self.ctrl.courante, self.ctrl.reglages
        if m is None:
            return
        if self.mode == "modifier" and not structure:
            self.flux.rafraichir(structure=False)
            return
        vider(self.lay)
        seg = Segmente([("apercu", "Aperçu du protocole"), ("modifier", "Modifier")], self.mode)
        seg.change.connect(self._mode)
        self.lay.addWidget(ligne(seg, bouton("Exporter le protocole (PDF)", self.exporter_pdf.emit, accent=True,
                                             tip="Enregistrer le protocole en PDF dans le dossier de mes documents"),
                                 "stretch", bouton("Dossier de mes documents", self.ouvrir_dossier.emit, lien=True,
                                                   tip="Ouvrir le dossier où sont rangés mes rapports et protocoles")))
        self.lay.addWidget(ligne_emis(m, ("protocole", "ordre"), self.ouvrir_fichier.emit, [], "Aucun protocole émis pour l’instant."))
        self.flux.setVisible(self.mode == "modifier")
        self.apercu.setVisible(self.mode != "modifier")
        if self.mode == "modifier":
            self.lay.addWidget(etiquette("Les modifications sont enregistrées automatiquement ; reviens sur « Aperçu du protocole » "
                                         "pour le relire, puis exporte-le en PDF.", secondaire=True, wrap=True))
            self.flux.rafraichir()
            return
        vider(self.l_apercu)
        self.lay.addWidget(etiquette("Document de paillasse : titre, cartouche, contexte, flux, réactifs, puis chaque phase avec ses "
                                     "échantillons et des cases pour noter à la main les n° Scirius et Aramis.",
                                     secondaire=True, wrap=True))
        reste = [t for t in m.a_faire if not t.fait]
        if reste:
            self.l_apercu.addWidget(InfoBar(" ; ".join(f"{t.categorie} : {t.texte}" for t in reste[:5]) + (" …" if len(reste) > 5 else ""),
                                       niveau="info", titre=f"{len(reste)} point{'s' if len(reste) > 1 else ''} encore à faire"))
        if not m.etapes:
            self.l_apercu.addWidget(InfoBar("Ajoute des étapes avec « Modifier » pour obtenir un protocole.", titre="Flux vide"))
        f, cl = carte()
        cl.addWidget(etiquette("Aperçu", "titreCarte"))
        try:
            from mat_methode.exports.protocole import ecrire_protocole
            with tempfile.TemporaryDirectory() as d:
                chemin = Path(d) / "protocole.pdf"
                ecrire_protocole(exporter(m, r), chemin)
                images = pages_png(chemin)
        except Exception as ex:  # l'aperçu n'empêche jamais l'export
            logging.getLogger(__name__).warning("Aperçu du protocole impossible : %s", ex)
            images = []
            cl.addWidget(etiquette(f"Aperçu indisponible ({ex}). L’export PDF reste possible.", secondaire=True, wrap=True))
        self.nb_pages = len(images)
        for k, img in enumerate(images):
            cl.addWidget(etiquette(f"Page {k + 1} / {len(images)}", secondaire=True))
            lab = QLabel()
            lab.setPixmap(QPixmap.fromImage(img))
            lab.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            lab.setStyleSheet("border:1px solid #c8d0ce;background:white;")
            lab.setAccessibleName(f"Aperçu du protocole, page {k + 1}")
            cl.addWidget(lab, 0, Qt.AlignmentFlag.AlignHCenter)
        if R.numeros_a_saisir(m):
            cl.addWidget(etiquette("Les numéros Scirius / Aramis non saisis apparaissent en cases vides, à remplir à la main.",
                                   secondaire=True, wrap=True))
        self.l_apercu.addWidget(f)
        self.l_apercu.addStretch(1)
