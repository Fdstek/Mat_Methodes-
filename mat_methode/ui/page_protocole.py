"""Page « Protocole › Édition » : le protocole en lecture (même vue que Flux), « Modifier », statut, puis export PDF."""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QVBoxLayout, QWidget

from mat_methode.domain.models import ENCOURS, STATUTS, STATUTS_PROTOCOLE
from mat_methode.ui.controleur import Controleur
from mat_methode.ui.page_flux import PageFlux
from mat_methode.ui.page_rapport import ligne_emis
from mat_methode.ui.widgets import InfoBar, Segmente, bouton, etiquette, ligne, vider


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
        racine.addWidget(self.flux)

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

    def _statut(self, statut: str):
        m = self.ctrl.courante
        if m is None or statut == m.etat:
            return
        msg = self.ctrl.changer_statut(m, statut)
        if msg:
            self.ctrl.toast.emit(msg)
        elif statut == ENCOURS:
            self.ctrl.toast.emit("En cours : la manip est lancée, chaque modification sera notée")
        elif statut == "realisee":
            self.ctrl.toast.emit("Réalisée : le rapport est maintenant dans Rapport")

    def rafraichir(self, structure=True):
        m = self.ctrl.courante
        if m is None:
            return
        if not structure:
            self.flux.rafraichir(structure=False)
            return
        vider(self.lay)
        modifier = bouton("Terminer la modification" if self.flux.edition else "✎  Modifier",
                          lambda: self._mode("apercu" if self.flux.edition else "modifier"), accent=not self.flux.edition,
                          tip="Rendre le protocole modifiable (même éditeur que Flux)")
        modifier.setEnabled(not self.ctrl.lecture_seule)
        seg = Segmente([(k, STATUTS[k][0]) for k in STATUTS_PROTOCOLE], m.etat)
        seg.setAccessibleName("Statut du protocole")
        seg.change.connect(self._statut)
        seg.setEnabled(not self.ctrl.lecture_seule)
        self.lay.addWidget(ligne(modifier, seg, bouton("Exporter le protocole (PDF)", self.exporter_pdf.emit, accent=True,
                                                       tip="Enregistrer le protocole de paillasse en PDF dans le dossier de mes documents"),
                                 "stretch", bouton("Dossier de mes documents", self.ouvrir_dossier.emit, lien=True,
                                                   tip="Ouvrir le dossier où sont rangés mes rapports et protocoles")))
        self.lay.addWidget(ligne_emis(m, ("protocole", "ordre"), self.ouvrir_fichier.emit, [], "Aucun protocole émis pour l’instant."))
        self.lay.addWidget(etiquette(
            "Modification en cours : les changements sont enregistrés automatiquement." if self.flux.edition else
            "Vue en lecture du protocole. « Modifier » pour le changer ; le PDF de paillasse reprend ce contenu avec des cases "
            "pour noter à la main les n° Scirius et Aramis.", secondaire=True, wrap=True))
        reste = [t for t in m.a_faire if not t.fait]
        if reste:
            self.lay.addWidget(InfoBar(" ; ".join(f"{t.categorie} : {t.texte}" for t in reste[:5]) + (" …" if len(reste) > 5 else ""),
                                       niveau="info", titre=f"{len(reste)} point{'s' if len(reste) > 1 else ''} encore à faire"))
        self.flux.rafraichir()
