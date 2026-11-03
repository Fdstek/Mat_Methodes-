"""Colonnes communes des tableaux de manips (Définition, Archivées, Protocole, Rapport) : donneur d'ordre, type, tags.

Colonnes centrées ; un clic sur l'en-tête « Donneur d'ordre » ou « Type » (ou sur un nom dans une ligne) trie le tableau
(croissant, puis décroissant, puis ordre d'origine)."""
from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

from mat_methode.domain import reglages_ops as O
from mat_methode.domain.texte import norm
from mat_methode.ui import theme
from mat_methode.ui.widgets import bouton, etiquette, flux_widgets

LARG_DONNEUR, LARG_TYPE, LARG_TAGS = 145, 100, 150
COMMUNES = (("DONNEUR D’ORDRE", LARG_DONNEUR), ("TYPE", LARG_TYPE), ("TAGS", LARG_TAGS))
TRIABLES = {"DONNEUR D’ORDRE": "donneur", "TYPE": "type"}
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
    valeur = (lambda m: norm(m.contexte.donneur)) if cle == "donneur" else (lambda m: norm(m.contexte.type))
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


def cellules_communes(m, r, clic_tag: Callable[[str], None] | None = None, trier: Callable[[str], None] | None = None) -> list[QWidget]:
    return [cellule_donneur(m, r, trier), cellule_type(m, r, trier), cellule_tags(m, r, clic_tag)]


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
