"""Page « Protocole › Édition » : le protocole en lecture (même vue que Flux), « Modifier », statut, puis export PDF."""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QVBoxLayout, QWidget

from mat_methode.ui.controleur import Controleur
from mat_methode.ui.page_flux import PageFlux
from mat_methode.ui.page_rapport import carte_figures, carte_resultats, ligne_emis
from mat_methode.ui.widgets import InfoBar, bouton, etiquette, vider


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
        self.flux = PageFlux(ctrl, contexte="protocole")  # même vue que Définition › Flux, en lecture sauf « Modifier »
        self.flux.actions_bandeau = self._actions  # bandeau de statut toujours visible : Modifier, statut, exporter
        self.flux.edition_changee.connect(self.rafraichir)
        racine.addWidget(self.flux)
        ctrl.analyses_pretes.connect(lambda _: self.isVisible() and not self.flux.edition and self.rafraichir())
        ctrl.figures_changees.connect(lambda: self.isVisible() and not self.flux.edition and self.rafraichir())

    def _actions(self) -> list:
        return [bouton("Exporter le protocole (PDF)", self.exporter_pdf.emit, accent=True,
                       tip="Enregistrer le protocole de paillasse en PDF (dossier des protocoles) puis l’ouvrir"),
                bouton("Dossier des protocoles", self.ouvrir_dossier.emit, lien=True,
                       tip="Ouvrir le dossier partagé des protocoles (donnees\\exports\\Protocoles)")]

    @property
    def mode(self) -> str:
        return "modifier" if self.flux.edition else "apercu"

    def ouvrir(self, mode: str = "apercu"):
        m = self.ctrl.courante
        self.flux.ouvrir("comp" if m and m.etapes else "def")
        self.flux.edition = mode == "modifier"

    def _mode(self, mode: str):
        self.flux.edition = mode == "modifier"
        self.rafraichir()

    def rafraichir(self, structure=True):
        m = self.ctrl.courante
        if m is None:
            return
        if not structure:
            self.flux.rafraichir(structure=False)
            return
        vider(self.lay)
        self.lay.addWidget(ligne_emis(m, ("protocole", "ordre"), self.ouvrir_fichier.emit, [], "Aucun protocole émis pour l’instant."))
        self.lay.addWidget(etiquette(
            "Modification en cours : les changements sont enregistrés automatiquement." if self.flux.edition else
            "Vue en lecture du protocole (« ✎ Modifier » dans le bandeau pour le changer). Le PDF de paillasse reprend ce contenu "
            "avec des cases pour noter à la main les n° Scirius et Aramis.", secondaire=True, wrap=True))
        reste = [t for t in m.a_faire if not t.fait]
        if reste:
            self.lay.addWidget(InfoBar(" ; ".join(f"{t.categorie} : {t.texte}" for t in reste[:5]) + (" …" if len(reste) > 5 else ""),
                                       niveau="info", titre=f"{len(reste)} point{'s' if len(reste) > 1 else ''} encore à faire"))
        if not self.flux.edition:  # résultats déjà rendus par les labos (ana explorer)
            res = carte_resultats(self.ctrl, m, self.rafraichir, ouvert=False)
            if res is not None:
                self.lay.addWidget(res)
            figs = carte_figures(self.ctrl, m, self.rafraichir, self.ouvrir_fichier.emit, ouvert=False)
            if figs is not None:
                self.lay.addWidget(figs)
        self.flux.rafraichir()
