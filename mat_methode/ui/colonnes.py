"""Colonnes communes des tableaux de manips (Définition, Archivées, Protocole, Rapport) : donneur d'ordre, type, tags.

Colonnes centrées ; un clic sur l'en-tête « Donneur d'ordre » ou « Type » (ou sur un nom dans une ligne) trie le tableau
(croissant, puis décroissant, puis ordre d'origine)."""
from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QHBoxLayout, QLabel, QMenu, QPushButton, QToolButton, QVBoxLayout, QWidget

from mat_methode.domain import reglages_ops as O
from mat_methode.domain import regles as R
from mat_methode.domain.texte import norm
from mat_methode.ui import theme
from mat_methode.ui.widgets import bouton, etiquette, flux_widgets

LARG_DONNEUR, LARG_ATTRIBUE, LARG_TYPE, LARG_ETAPES, LARG_TAGS = 135, 95, 80, 105, 135
COMMUNES = (("DONNEUR D’ORDRE", LARG_DONNEUR), ("ATTRIBUÉ À", LARG_ATTRIBUE), ("TYPE", LARG_TYPE), ("ÉTAPES", LARG_ETAPES), ("TAGS", LARG_TAGS))
TRIABLES = {"DONNEUR D’ORDRE": "donneur", "ATTRIBUÉ À": "attribue", "TYPE": "type", "ÉTAPES": "etapes"}
Tri = tuple[str, bool] | None  # (« donneur » ou « type », croissant)


def fixe(w: QWidget, largeur: int) -> QWidget:
    w.setFixedWidth(largeur)
    return w


def boite(contenu: QWidget, largeur: int, centre: bool = True) -> QWidget:
    """Contenu dans une colonne de largeur fixe (centré par défaut)."""
    b = QWidget()
    v = QVBoxLayout(b)
    v.setContentsMargins(0, 0, 0, 0)
    v.addWidget(contenu, 0, Qt.AlignmentFlag.AlignHCenter if centre else Qt.AlignmentFlag.AlignLeft)
    return fixe(b, largeur)


# ------------------------------------------------------------------ tri
def basculer_tri(tri: Tri, cle: str) -> Tri:
    """Croissant -> décroissant -> sans tri."""
    if not tri or tri[0] != cle:
        return (cle, True)
    return (cle, False) if tri[1] else None


def trier_manips(manips: list, tri: Tri) -> list:
    if not tri:
        return list(manips)
    cle, croissant = tri
    valeur = {"donneur": lambda m: norm(m.contexte.donneur), "attribue": lambda m: norm(m.contexte.attribue),
              "type": lambda m: norm(m.contexte.type), "etapes": lambda m: norm(R.texte_reperes(m))}[cle]
    vides = [m for m in manips if not valeur(m)]  # sans donneur / type : toujours à la fin
    pleins = sorted((m for m in manips if valeur(m)), key=valeur, reverse=not croissant)
    return pleins + vides


# ------------------------------------------------------------------ cellules
class Pilule(QLabel):
    """Nom en couleur (donneur d'ordre, type), cliquable ; passe à la ligne au lieu d'être coupé."""

    def __init__(self, texte: str, couleur: str, clic: Callable | None = None, tip: str = "", largeur: int = 0):
        super().__init__(texte)
        p = theme.P
        c = QColor(couleur)
        fg = c.lighter(160).name() if p.sombre else c.name()
        self.setObjectName("pilule")
        self.setStyleSheet(f"QLabel#pilule{{background:rgba({c.red()},{c.green()},{c.blue()},{40 if p.sombre else 28});color:{fg};"
                           f"border:1px solid {c.name()};border-radius:10px;padding:2px 9px;font-size:9pt;font-weight:600;}}")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if largeur and self.fontMetrics().horizontalAdvance(texte) + 26 > largeur:
            self.setWordWrap(True)  # trop long pour la colonne : sur plusieurs lignes, sur toute la largeur
            self.setFixedWidth(largeur)
        self.setToolTip(tip)
        self._clic = clic
        if clic:
            self.setCursor(Qt.CursorShape.PointingHandCursor)

    def mousePressEvent(self, e):
        if self._clic and e.button() == Qt.MouseButton.LeftButton:
            self._clic()
        super().mousePressEvent(e)


def pilule(texte: str, couleur: str, clic: Callable | None = None, tip: str = "") -> QPushButton:
    """Tag en couleur (bouton), cliquable si `clic` est donné."""
    p = theme.P
    b = bouton(texte, clic or (lambda: None), tip=tip)
    c = QColor(couleur)
    fg = c.lighter(160).name() if p.sombre else c.name()
    b.setStyleSheet(f"QPushButton{{background:rgba({c.red()},{c.green()},{c.blue()},{40 if p.sombre else 28});color:{fg};"
                    f"border:1px solid {c.name()};border-radius:10px;padding:2px 9px;font-size:9pt;font-weight:600;text-align:center;}}")
    if not clic:
        b.setCursor(Qt.CursorShape.ArrowCursor)
    return b


def cellule_donneur(m, r, trier: Callable[[str], None] | None = None) -> QWidget:
    if not m.contexte.donneur:
        return boite(etiquette("—", secondaire=True), LARG_DONNEUR)
    b = Pilule(m.contexte.donneur, O.couleur_donneur(r, m.contexte.donneur), (lambda: trier("donneur")) if trier else None,
               "Trier par donneur d’ordre" if trier else "", LARG_DONNEUR)
    return boite(b, LARG_DONNEUR)


def cellule_type(m, r, trier: Callable[[str], None] | None = None) -> QWidget:
    if not m.contexte.type:
        return boite(etiquette("—", secondaire=True), LARG_TYPE)
    b = Pilule(m.contexte.type, O.couleur_type(r, m.contexte.type), (lambda: trier("type")) if trier else None,
               "Trier par type" if trier else "", LARG_TYPE)
    return boite(b, LARG_TYPE)


def bouton_tag(t: str, r, clic: Callable | None = None):
    """Tag en couleur, cliquable (filtre) si `clic` est donné."""
    b = pilule(f"#{t}", O.couleur_tag(r, t), clic, f"Filtrer sur le tag {t}" if clic else "")
    b.setStyleSheet(b.styleSheet().replace("border-radius:10px", "border-radius:4px"))
    return b


def cellule_tags(m, r, clic: Callable[[str], None] | None = None) -> QWidget:
    if not m.tags:
        return boite(etiquette("—", secondaire=True), LARG_TAGS)
    return fixe(flux_widgets([bouton_tag(t, r, (lambda t=t: clic(t)) if clic else None) for t in m.tags], centre=True), LARG_TAGS)


def _texte_centre(texte: str, largeur: int, tip: str = "", clic: Callable | None = None) -> QWidget:
    if not texte:
        return boite(etiquette("—", secondaire=True), largeur)
    lab = etiquette(texte, wrap=True)
    lab.setAlignment(Qt.AlignmentFlag.AlignHCenter)
    lab.setToolTip(tip)
    return fixe(lab, largeur)


def cellule_attribue(m, trier: Callable[[str], None] | None = None) -> QWidget:
    return _texte_centre(m.contexte.attribue, LARG_ATTRIBUE, "Manip attribuée à " + m.contexte.attribue)


def cellule_etapes(m) -> QWidget:
    """Initiale de chaque grande étape et matériel de sa première sous-étape (« D : R1 »), un repère par ligne."""
    rep = R.reperes_etapes(m)
    return _texte_centre("\n".join(f"{i} : {mat}" if mat else i for i, _, mat in rep), LARG_ETAPES,
                         "\n".join(f"{g} : {mat or 'matériel non indiqué'}" for _, g, mat in rep))


def cellules_communes(m, r, clic_tag: Callable[[str], None] | None = None, trier: Callable[[str], None] | None = None) -> list[QWidget]:
    return [cellule_donneur(m, r, trier), cellule_attribue(m, trier), cellule_type(m, r, trier), cellule_etapes(m), cellule_tags(m, r, clic_tag)]


def sous_titre_manip(m) -> str:
    """Ligne « n° d'expérience » sous le titre de la manip dans les listes."""
    return f"Expérience {m.contexte.experience}" if m.contexte.experience else ""


# ------------------------------------------------------------------ en-têtes
def entetes_communes(tri: Tri = None, trier: Callable[[str], None] | None = None) -> list[QWidget]:
    """En-têtes centrés ; « Donneur d'ordre » et « Type » sont cliquables pour trier quand `trier` est donné."""
    out = []
    for t, lg in COMMUNES:
        cle = TRIABLES.get(t)
        if cle and trier:
            fleche = (" ▲" if tri[1] else " ▼") if tri and tri[0] == cle else " ⇅"
            b = bouton(t + fleche, lambda cle=cle: trier(cle), tip=f"Trier par {t.lower()} (croissant, décroissant, sans tri)")
            b.setStyleSheet(f"QPushButton{{border:none;background:transparent;padding:0;font-size:9.5pt;"
                            f"color:{theme.P.accent if tri and tri[0] == cle else theme.P.texte2};}}")
            out.append(boite(b, lg))
        else:
            lab = etiquette(t, "etiquetteChamp")
            lab.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            out.append(fixe(lab, lg))
    return out


# ------------------------------------------------------------------ filtres (choix multiples)
class _MenuCoche(QMenu):
    """Menu dont les cases se cochent sans le fermer (plusieurs choix à la suite)."""

    def mouseReleaseEvent(self, e):
        a = self.actionAt(e.position().toPoint())
        if a is not None and a.isCheckable() and a.isEnabled():
            a.toggle()
            return
        super().mouseReleaseEvent(e)


class ListeMulti(QToolButton):
    """Liste déroulante à choix multiples : « Tous les types » ou « Type : A, B »."""
    change = Signal()

    def __init__(self, vide: str, options: list[str], choisis: set[str], nom: str):
        super().__init__()
        self._vide, self._choisis = vide, choisis
        self.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.setAccessibleName(nom)
        self.setToolTip(nom + " (plusieurs choix possibles)")
        self.setMinimumWidth(150)
        self.setStyleSheet("QToolButton::menu-indicator{subcontrol-position:right center;right:8px;}QToolButton{padding:5px 26px 5px 10px;text-align:left;}")
        menu = _MenuCoche(self)
        for o in options:
            a = menu.addAction(o)
            a.setCheckable(True)
            a.setChecked(o in choisis)
            a.toggled.connect(lambda on, o=o: self._basculer(o, on))
        if options:
            menu.addSeparator()
            menu.addAction("Tout décocher", self._vider)
        self.setMenu(menu)
        self._texte()

    def _texte(self):
        n = len(self._choisis)
        t = self._vide if not n else (", ".join(sorted(self._choisis)) if n <= 2 else f"{n} sélectionnés")
        self.setText(t.replace("&", "&&"))

    def _basculer(self, o: str, on: bool):
        (self._choisis.add if on else self._choisis.discard)(o)
        self._texte()
        self.change.emit()

    def _vider(self):
        self._choisis.clear()
        for a in self.menu().actions():
            if a.isCheckable():
                a.blockSignals(True)
                a.setChecked(False)
                a.blockSignals(False)
        self._texte()
        self.change.emit()


class Filtres:
    """Filtres communs aux listes (Définition, Archivées, Protocole, Rapport) : plusieurs choix par critère.
    Les boutons de donneur d'ordre n'apparaissent que pour les donneurs qui ont des manips dans la liste."""

    def __init__(self):
        self.donneur: set[str] = set()
        self.attribue: set[str] = set()
        self.type: set[str] = set()
        self.tag: set[str] = set()

    def actif(self) -> bool:
        return bool(self.donneur or self.attribue or self.type or self.tag)

    def passe(self, m) -> bool:
        c = m.contexte
        return ((not self.donneur or c.donneur in self.donneur) and (not self.attribue or c.attribue in self.attribue)
                and (not self.type or c.type in self.type)
                and (not self.tag or any(norm(t) in {norm(x) for x in self.tag} for t in m.tags)))

    def appliquer(self, manips: list) -> list:
        return [m for m in manips if self.passe(m)]

    def barre(self, manips: list, r, change: Callable[[], None], tags: list[str]) -> QWidget:
        """Barre de filtres ; `manips` = toutes les manips de la liste (avant filtre) pour les compteurs."""
        from mat_methode.ui.widgets import bouton_tag_couleur, flux_widgets
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        h.addWidget(etiquette("Donneur d’ordre", secondaire=True))
        presents = [n for n in r.donneurs_ordre if any(m.contexte.donneur == n for m in manips)]
        self.donneur &= set(presents)
        tous = bouton("Tous", lambda: (self.donneur.clear(), change()))
        tous.setProperty("chip", True)
        tous.setCheckable(True)
        tous.setChecked(not self.donneur)
        h.addWidget(tous)

        def bascule(n):
            (self.donneur.discard if n in self.donneur else self.donneur.add)(n)
            change()
        puces = [bouton_tag_couleur(n, O.couleur_donneur(r, n), sum(1 for m in manips if m.contexte.donneur == n), n in self.donneur,
                                    lambda n=n: bascule(n)) for n in presents]
        h.addWidget(flux_widgets(puces), 1)
        for vide, options, choisis, nom in (("Tous les attribués", [n for n in r.attributions if any(m.contexte.attribue == n for m in manips)],
                                             self.attribue, "Filtrer par personne attribuée"),
                                            ("Tous les types", [t for t in r.types_demande if any(m.contexte.type == t for m in manips)],
                                             self.type, "Filtrer par type de demande"),
                                            ("Tous les tags", tags, self.tag, "Filtrer par tag")):
            choisis &= set(options)
            lm = ListeMulti(vide, options, choisis, nom)
            lm.change.connect(change)
            h.addWidget(lm)
        return w
