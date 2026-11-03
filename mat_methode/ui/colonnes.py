"""Colonnes communes des tableaux de manips (Définition, Archivées, Protocole, Rapport) : donneur d'ordre, type, tags."""
from __future__ import annotations

from typing import Callable

from PySide6.QtGui import QColor
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from mat_methode.domain import reglages_ops as O
from mat_methode.ui import theme
from mat_methode.ui.widgets import bouton, etiquette, flux_widgets, pastille, pastille_couleur

LARG_DONNEUR, LARG_TYPE, LARG_TAGS = 125, 95, 150
COMMUNES = (("DONNEUR D’ORDRE", LARG_DONNEUR), ("TYPE", LARG_TYPE), ("TAGS", LARG_TAGS))


def fixe(w: QWidget, largeur: int) -> QWidget:
    w.setFixedWidth(largeur)
    return w


def boite(contenu: QWidget, largeur: int) -> QWidget:
    """Contenu aligné à gauche dans une colonne de largeur fixe."""
    b = QWidget()
    v = QVBoxLayout(b)
    v.setContentsMargins(0, 0, 0, 0)
    v.addWidget(contenu)
    return fixe(b, largeur)


def cellule_donneur(m, r) -> QWidget:
    if not m.contexte.donneur:
        return boite(etiquette("—", secondaire=True), LARG_DONNEUR)
    p = pastille_couleur(m.contexte.donneur, O.couleur_donneur(r, m.contexte.donneur))
    p.setWordWrap(True)
    p.setMaximumWidth(LARG_DONNEUR)
    return boite(p, LARG_DONNEUR)


def cellule_type(m) -> QWidget:
    if not m.contexte.type:
        return boite(etiquette("—", secondaire=True), LARG_TYPE)
    p = pastille(m.contexte.type)
    if isinstance(p, QLabel):
        p.setWordWrap(True)
    p.setMaximumWidth(LARG_TYPE)
    return boite(p, LARG_TYPE)


def bouton_tag(t: str, r, clic: Callable | None = None):
    """Tag en couleur, cliquable (filtre) si `clic` est donné."""
    p = theme.P
    b = bouton(f"#{t}", clic or (lambda: None), tip=f"Filtrer sur le tag {t}" if clic else "")
    c = QColor(O.couleur_tag(r, t))
    fg = c.lighter(160).name() if p.sombre else c.name()
    b.setStyleSheet(f"QPushButton{{background:rgba({c.red()},{c.green()},{c.blue()},{40 if p.sombre else 28});color:{fg};"
                    f"border:1px solid {c.name()};border-radius:4px;padding:2px 8px;font-size:9pt;font-weight:600;}}")
    return b


def cellule_tags(m, r, clic: Callable[[str], None] | None = None) -> QWidget:
    if not m.tags:
        return boite(etiquette("—", secondaire=True), LARG_TAGS)
    return fixe(flux_widgets([bouton_tag(t, r, (lambda t=t: clic(t)) if clic else None) for t in m.tags]), LARG_TAGS)


def cellules_communes(m, r, clic_tag: Callable[[str], None] | None = None) -> list[QWidget]:
    return [cellule_donneur(m, r), cellule_type(m), cellule_tags(m, r, clic_tag)]


def entetes_communes() -> list[QWidget]:
    return [fixe(etiquette(t, "etiquetteChamp"), lg) for t, lg in COMMUNES]
