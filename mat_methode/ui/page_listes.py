"""Listes « Protocole » (manips validées, dans l'ordre de réalisation) et « Rapport » (manips réalisées)."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QVBoxLayout, QWidget

from mat_methode.domain import regles as R
from mat_methode.domain.models import ANNULEE, REALISEE, STATUTS_PROTOCOLE
from mat_methode.domain.regles import tous_les_tags
from mat_methode.domain.texte import fmt_dt
from mat_methode.ui import colonnes as C
from mat_methode.ui import theme
from mat_methode.ui.controleur import Controleur
from mat_methode.ui.widgets import bouton, etiquette, flux_widgets, icone, liste_statut, numero, pastille, vider


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
    g.setHorizontalSpacing(16)
    return w, g


def _resume(m, *lignes: str, marques: list | None = None) -> QWidget:
    """Nom, référence et informations de la manip (colonne « Manip »)."""
    c = QWidget()
    v = QVBoxLayout(c)
    v.setContentsMargins(0, 0, 0, 0)
    v.setSpacing(2)
    v.addWidget(etiquette(m.nom, "titreCarte", wrap=True))
    for t in (C.sous_titre_manip(m), m.contexte.ref, *lignes):
        if t:
            v.addWidget(etiquette(t, secondaire=True, wrap=True))
    if marques:
        v.addWidget(flux_widgets(marques))
    return c


def _rangee(cellules: list[QWidget], largeurs: list[int | None], derniere: bool, entete: bool = False) -> QFrame:
    """Une ligne du tableau : largeurs fixes (None = colonne qui prend la place restante), alignées sur l'en-tête."""
    w, g = _ligne_cadre(derniere)
    if entete:
        g.setContentsMargins(14, 8, 14, 8)
        w.setStyleSheet(f"QFrame#ligneManip{{border-bottom:1px solid {theme.P.trait};}}")
    for k, (c, lg) in enumerate(zip(cellules, largeurs)):
        if lg is None:
            g.setColumnStretch(k, 1)
        else:
            g.setColumnMinimumWidth(k, lg)
            c.setFixedWidth(lg)
        g.addWidget(c, 0, k, Qt.AlignmentFlag.AlignVCenter)
    return w


def _titre(t: str) -> QWidget:
    return etiquette(t, "etiquetteChamp")


class PageProtocoles(QWidget):
    """Liste des protocoles : « À réaliser » (Validée, En cours) dans l'ordre de réalisation, et « Clôturés »."""
    ouvrir = Signal(str)

    def _actualiser(self):
        """Reconstruit la page sans la faire remonter (position gardée par la fenêtre)."""
        f = getattr(self, "sur_place", None)
        f() if f else self.rafraichir()

    def __init__(self, ctrl: Controleur):
        super().__init__()
        self.ctrl = ctrl
        self.clotures = False
        self.tri = None  # tri par donneur d'ordre ou type (clic sur l'en-tête)
        self.filtres = C.Filtres()
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
            "Les manips validées dans « Mat & Méthode », dans l’ordre de réalisation (↑ ↓ pour le changer). "
            "Passe le statut à « En cours » au démarrage, puis à « Réalisée » : elle part dans Rapport.", secondaire=True, wrap=True))
        base = clos if self.clotures else a_faire
        self.lay.addWidget(self.filtres.barre(base, r, self._actualiser, tous_les_tags(base, r.ordre_tags)))
        liste = C.trier_manips(self.filtres.appliquer(base), self.tri)
        if self.tri and not self.clotures and liste:
            self.lay.addWidget(etiquette("Tableau trié : ↑ ↓ (ordre de réalisation) sont désactivées. Clique de nouveau l’en-tête "
                                         "pour revenir à l’ordre de réalisation.", secondaire=True, wrap=True))
        f, v = _cadre_liste()
        if not liste:
            vide = etiquette("Aucun protocole ne correspond aux filtres." if base else "Aucun protocole clôturé." if self.clotures else
                             "Aucun protocole à réaliser : valide une manip dans « Mat & Méthode ».", secondaire=True)
            vide.setContentsMargins(16, 24, 16, 24)
            v.addWidget(vide)
        else:
            v.addWidget(self._entete())
        for i, m in enumerate(liste):
            v.addWidget(self._ligne(m, i, len(liste)))
        self.lay.addWidget(f)
        self.lay.addStretch(1)

    def _largeurs(self) -> list[int | None]:
        debut = [] if self.clotures else [30]
        fin = [125] + ([] if self.clotures else [34, 34]) + [75]
        return debut + [None] + [lg for _, lg in C.COMMUNES] + fin

    def _entete(self) -> QWidget:
        cel = ([] if self.clotures else [_titre("N°")]) + [_titre("PROTOCOLE")] + C.entetes_communes(self.tri, self._trier) + [_titre("STATUT")]
        cel += ([] if self.clotures else [QWidget(), QWidget()]) + [QWidget()]
        return _rangee(cel, self._largeurs(), False, entete=True)

    def _ligne(self, m, i: int, n: int) -> QWidget:
        ne = len(m.etapes)
        cel = [] if self.clotures else [C.boite(numero(i + 1), 30)]
        cel.append(_resume(m, f"{ne} étape{'s' if ne > 1 else ''} · {len(m.prelevements)} éch."
                           + (f" · lancée le {fmt_dt(m.lancee.le)[:10]}" if m.lancee else "")))
        cel += C.cellules_communes(m, self.ctrl.reglages, trier=self._trier)
        st = liste_statut(m, STATUTS_PROTOCOLE)
        st.setMinimumWidth(0)
        st.setMinimumContentsLength(6)
        st.choisi.connect(lambda val, m=m: self._statut(m, val))
        if m.statuts:
            from mat_methode.domain.reglages_ops import texte_statut
            st.setToolTip(texte_statut(self.ctrl.reglages, m.statuts[-1]))
        cel.append(st)
        if not self.clotures:
            haut = icone("↑", f"Réaliser avant : {m.nom}", lambda m=m: self.ctrl.deplacer_protocole(m, -1))
            haut.setEnabled(i > 0 and not self.tri)
            bas = icone("↓", f"Réaliser après : {m.nom}", lambda m=m: self.ctrl.deplacer_protocole(m, 1))
            bas.setEnabled(i < n - 1 and not self.tri)
            cel += [haut, bas]
        cel.append(bouton("Ouvrir", lambda m=m: self.ouvrir.emit(m.id), accent=True, tip=f"Voir et modifier le protocole de {m.nom}"))
        return _rangee(cel, self._largeurs(), i == n - 1)

    def _trier(self, cle: str):
        self.tri = C.basculer_tri(self.tri, cle)
        self._actualiser()

    def _statut(self, m, statut: str):
        msg = self.ctrl.changer_statut(m, statut)
        if msg:
            self.ctrl.toast.emit(msg)
        elif statut == REALISEE:
            self.ctrl.toast.emit("Réalisée : le rapport est maintenant dans Rapport")
        self._actualiser()


class PageRapports(QWidget):
    """Liste des rapports : seulement les protocoles clôturés comme « Réalisée »."""
    ouvrir = Signal(str)

    def _actualiser(self):
        """Reconstruit la page sans la faire remonter (position gardée par la fenêtre)."""
        f = getattr(self, "sur_place", None)
        f() if f else self.rafraichir()

    def __init__(self, ctrl: Controleur):
        super().__init__()
        self.ctrl = ctrl
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(0, 0, 0, 0)
        self.lay.setSpacing(14)

    def _trier(self, cle: str):
        self.tri = C.basculer_tri(getattr(self, "tri", None), cle)
        self._actualiser()

    def rafraichir(self):
        vider(self.lay)
        base = R.rapports_clotures(self.ctrl.manips)
        if not hasattr(self, "filtres"):
            self.filtres = C.Filtres()
        liste = C.trier_manips(self.filtres.appliquer(base), getattr(self, "tri", None))
        self.lay.addWidget(etiquette("Les manips réalisées (protocoles clôturés dans Protocole), la plus récente d’abord.",
                                     secondaire=True, wrap=True))
        if base:
            self.lay.addWidget(self.filtres.barre(base, self.ctrl.reglages, self._actualiser, tous_les_tags(base, self.ctrl.reglages.ordre_tags)))
        f, v = _cadre_liste()
        if not liste and base:
            vide = etiquette("Aucun rapport ne correspond aux filtres.", secondaire=True)
            vide.setContentsMargins(16, 24, 16, 24)
            v.addWidget(vide)
        elif not liste:
            vide = etiquette("Aucun rapport : passe un protocole au statut « Réalisée » dans Protocole.", secondaire=True)
            vide.setContentsMargins(16, 24, 16, 24)
            v.addWidget(vide)
        largeurs = [None] + [lg for _, lg in C.COMMUNES] + [125]
        if liste:
            v.addWidget(_rangee([_titre("RAPPORT")] + C.entetes_communes(getattr(self, "tri", None), self._trier) + [QWidget()], largeurs,
                                False, entete=True))
        for i, m in enumerate(liste):
            emis = [x for x in m.rapports if x.type == "rapport"]
            marques = [pastille(f"Modifiée après lancement ({len(m.journal)})", "warn")] if m.journal else []
            cel = [_resume(m, f"modifiée le {fmt_dt(m.maj)[:10]} · {len(emis)} rapport{'s' if len(emis) > 1 else ''} émis", marques=marques)]
            cel += C.cellules_communes(m, self.ctrl.reglages, trier=self._trier)
            cel.append(bouton("Voir le rapport", lambda m=m: self.ouvrir.emit(m.id), accent=True, tip=f"Rapport de {m.nom}"))
            v.addWidget(_rangee(cel, largeurs, i == len(liste) - 1))
        self.lay.addWidget(f)
        self.lay.addStretch(1)
