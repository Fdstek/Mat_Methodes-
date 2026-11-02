"""Listes « Protocole » (manips validées, dans l'ordre de réalisation) et « Rapport » (manips réalisées)."""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QVBoxLayout, QWidget

from mat_methode.domain import regles as R
from mat_methode.domain.models import ANNULEE, REALISEE, STATUTS_PROTOCOLE
from mat_methode.domain.texte import fmt_dt
from mat_methode.ui import theme
from mat_methode.ui.controleur import Controleur
from mat_methode.ui.widgets import bouton, etiquette, icone, liste_statut, numero, pastille, vider


def _cadre_liste() -> tuple[QFrame, QVBoxLayout]:
    f = QFrame()
    f.setObjectName("carte")
    v = QVBoxLayout(f)
    v.setContentsMargins(0, 0, 0, 0)
    v.setSpacing(0)
    return f, v


def _ligne_cadre(derniere: bool) -> tuple[QFrame, QGridLayout]:
    w = QFrame()
    w.setObjectName("ligneManip")
    w.setStyleSheet("" if derniere else f"QFrame#ligneManip{{border-bottom:1px solid {theme.P.trait};}}")
    g = QGridLayout(w)
    g.setContentsMargins(14, 10, 14, 10)
    g.setHorizontalSpacing(12)
    return w, g


def _resume(m) -> QWidget:
    """Nom (cliquable), référence, donneur d'ordre."""
    c = QWidget()
    v = QVBoxLayout(c)
    v.setContentsMargins(0, 0, 0, 0)
    v.setSpacing(2)
    v.addWidget(etiquette(m.nom, "titreCarte", wrap=True))
    infos = " · ".join(x for x in (m.contexte.ref, m.contexte.donneur, m.contexte.type) if x)
    v.addWidget(etiquette(infos or "—", secondaire=True, wrap=True))
    return c


class PageProtocoles(QWidget):
    """Liste des protocoles : « À réaliser » (Validée, En cours) dans l'ordre de réalisation, et « Clôturés »."""
    ouvrir = Signal(str)

    def __init__(self, ctrl: Controleur):
        super().__init__()
        self.ctrl = ctrl
        self.clotures = False
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(0, 0, 0, 0)
        self.lay.setSpacing(14)

    def _onglet(self, clotures: bool):
        self.clotures = clotures
        self.rafraichir()

    def rafraichir(self):
        ctrl, r = self.ctrl, self.ctrl.reglages
        vider(self.lay)
        a_faire = R.protocoles(ctrl.manips, r.ordre_protocoles)
        clos = R.protocoles(ctrl.manips, r.ordre_protocoles, (REALISEE, ANNULEE))
        piv = QHBoxLayout()
        for texte, val in ((f"À réaliser ({len(a_faire)})", False), (f"Clôturés ({len(clos)})", True)):
            b = bouton(texte, lambda v=val: self._onglet(v))
            b.setProperty("pivot", True)
            b.setProperty("actif", self.clotures == val)
            piv.addWidget(b)
        piv.addStretch(1)
        w = QWidget()
        w.setLayout(piv)
        self.lay.addWidget(w)
        self.lay.addWidget(etiquette(
            "Les manips réalisées ou annulées. Une manip réalisée apparaît dans Rapport." if self.clotures else
            "Les manips validées dans « Définition Mat & Méthode », dans l’ordre de réalisation (↑ ↓ pour le changer). "
            "Passe le statut à « En cours » au démarrage, puis à « Réalisée » : elle part dans Rapport.", secondaire=True, wrap=True))
        liste = clos if self.clotures else a_faire
        f, v = _cadre_liste()
        if not liste:
            vide = etiquette("Aucun protocole clôturé." if self.clotures else
                             "Aucun protocole à réaliser : valide une manip dans « Définition Mat & Méthode ».", secondaire=True)
            vide.setContentsMargins(16, 24, 16, 24)
            v.addWidget(vide)
        for i, m in enumerate(liste):
            v.addWidget(self._ligne(m, i, len(liste)))
        self.lay.addWidget(f)
        self.lay.addStretch(1)

    def _ligne(self, m, i: int, n: int) -> QWidget:
        w, g = _ligne_cadre(i == n - 1)
        col = 0
        if not self.clotures:
            g.addWidget(numero(i + 1), 0, col)
            col += 1
        g.addWidget(_resume(m), 0, col)
        g.setColumnStretch(col, 1)
        ne = len(m.etapes)
        g.addWidget(etiquette(f"{ne} étape{'s' if ne > 1 else ''} · {len(m.prelevements)} éch."
                              + (f"<br>lancée le {fmt_dt(m.lancee.le)[:10]}" if m.lancee else ""), secondaire=True), 0, col + 1)
        st = liste_statut(m, STATUTS_PROTOCOLE)
        st.choisi.connect(lambda val, m=m: self._statut(m, val))
        g.addWidget(st, 0, col + 2)
        if not self.clotures:
            haut = icone("↑", f"Réaliser avant : {m.nom}", lambda m=m: self.ctrl.deplacer_protocole(m, -1))
            haut.setEnabled(i > 0)
            bas = icone("↓", f"Réaliser après : {m.nom}", lambda m=m: self.ctrl.deplacer_protocole(m, 1))
            bas.setEnabled(i < n - 1)
            g.addWidget(haut, 0, col + 3)
            g.addWidget(bas, 0, col + 4)
        g.addWidget(bouton("Ouvrir", lambda m=m: self.ouvrir.emit(m.id), accent=True, tip=f"Voir et modifier le protocole de {m.nom}"), 0, col + 5)
        return w

    def _statut(self, m, statut: str):
        msg = self.ctrl.changer_statut(m, statut)
        if msg:
            self.ctrl.toast.emit(msg)
        elif statut == REALISEE:
            self.ctrl.toast.emit("Réalisée : le rapport est maintenant dans Rapport")
        self.rafraichir()


class PageRapports(QWidget):
    """Liste des rapports : seulement les protocoles clôturés comme « Réalisée »."""
    ouvrir = Signal(str)

    def __init__(self, ctrl: Controleur):
        super().__init__()
        self.ctrl = ctrl
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(0, 0, 0, 0)
        self.lay.setSpacing(14)

    def rafraichir(self):
        vider(self.lay)
        liste = R.rapports_clotures(self.ctrl.manips)
        self.lay.addWidget(etiquette("Les manips réalisées (protocoles clôturés dans Protocole), la plus récente d’abord.",
                                     secondaire=True, wrap=True))
        f, v = _cadre_liste()
        if not liste:
            vide = etiquette("Aucun rapport : passe un protocole au statut « Réalisée » dans Protocole.", secondaire=True)
            vide.setContentsMargins(16, 24, 16, 24)
            v.addWidget(vide)
        for i, m in enumerate(liste):
            w, g = _ligne_cadre(i == len(liste) - 1)
            g.addWidget(_resume(m), 0, 0)
            g.setColumnStretch(0, 1)
            emis = [x for x in m.rapports if x.type == "rapport"]
            g.addWidget(etiquette(f"modifiée le {fmt_dt(m.maj)[:10]}<br>{len(emis)} rapport{'s' if len(emis) > 1 else ''} émis",
                                  secondaire=True), 0, 1)
            if m.journal:
                g.addWidget(pastille(f"Modifiée après lancement ({len(m.journal)})", "warn"), 0, 2)
            g.addWidget(bouton("Voir le rapport", lambda m=m: self.ouvrir.emit(m.id), accent=True, tip=f"Rapport de {m.nom}"), 0, 3)
            v.addWidget(w)
        self.lay.addWidget(f)
        self.lay.addStretch(1)
