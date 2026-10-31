"""Thème Windows 11 (§13) : clair/sombre selon Windows, couleur d'accentuation de Windows,
feuille de style Qt (QSS) « Fluent » maison (pas de bibliothèque sous licence GPL)."""
from __future__ import annotations

import sys
from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPalette

TONS = {"neutre": "Neutre", "info": "Bleu", "ok": "Vert", "warn": "Orange", "danger": "Rouge"}


@dataclass
class Palette:
    sombre: bool
    fond: str
    volet: str
    carte: str
    trait: str
    texte: str
    texte2: str
    accent: str
    accent_texte: str
    selection: str
    ambre_texte: str
    ambre_fond: str
    ambre_trait: str
    succes: str
    succes_fond: str
    danger: str
    info_fond: str
    info_texte: str
    champ: str
    champ_survol: str
    bouton: str
    bouton_survol: str

    def ton(self, t: str) -> tuple[str, str]:
        """(texte, fond) d'une pastille d'état."""
        if t == "ok":
            return self.succes, self.succes_fond
        if t == "warn":
            return self.ambre_texte, self.ambre_fond
        if t == "danger":
            return self.danger, ("#FDE7E9" if not self.sombre else "#442726")
        if t == "info":
            return self.info_texte, self.info_fond
        return self.texte2, ("#EBEBEB" if not self.sombre else "#3A3A3A")


CLAIR = dict(sombre=False, fond="#F3F3F3", volet="#EEEEEE", carte="#FFFFFF", trait="#E5E5E5", texte="#1A1A1A", texte2="#5F5F5F",
             accent="#0067C0", accent_texte="#FFFFFF", selection="#E4E4E4", ambre_texte="#8A4B00", ambre_fond="#FFF4CE",
             ambre_trait="#D9A93E", succes="#0F7B0F", succes_fond="#DFF6DD", danger="#C42B1C", info_fond="#E5F0FB", info_texte="#0F4C81",
             champ="#FFFFFF", champ_survol="#F9F9F9", bouton="#FBFBFB", bouton_survol="#F3F3F3")
SOMBRE = dict(sombre=True, fond="#202020", volet="#1C1C1C", carte="#2B2B2B", trait="#3A3A3A", texte="#FFFFFF", texte2="#D0D0D0",
              accent="#60CDFF", accent_texte="#00283D", selection="#333333", ambre_texte="#F7C46C", ambre_fond="#4A3510",
              ambre_trait="#A8802A", succes="#6CCB5F", succes_fond="#233A22", danger="#FF99A4", info_fond="#1F3347", info_texte="#9CD3FF",
              champ="#2D2D2D", champ_survol="#323232", bouton="#2D2D2D", bouton_survol="#333333")

P: Palette = Palette(**CLAIR)


def contraste_eleve() -> bool:
    """Thème à contraste élevé de Windows : on laisse alors les couleurs du système."""
    if sys.platform != "win32":
        return False
    try:
        import ctypes

        class HIGHCONTRAST(ctypes.Structure):
            _fields_ = [("cbSize", ctypes.c_uint), ("dwFlags", ctypes.c_uint), ("lpszDefaultScheme", ctypes.c_wchar_p)]

        hc = HIGHCONTRAST()
        hc.cbSize = ctypes.sizeof(HIGHCONTRAST)
        ctypes.windll.user32.SystemParametersInfoW(0x0042, hc.cbSize, ctypes.byref(hc), 0)
        return bool(hc.dwFlags & 1)
    except Exception:
        return False


def systeme_sombre() -> bool:
    try:
        return QGuiApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark
    except AttributeError:
        return False


def accent_windows(sombre: bool) -> str | None:
    """Couleur d'accentuation lue par Qt (Windows 11). En sombre, on éclaircit pour le contraste."""
    try:
        c = QGuiApplication.palette().color(QPalette.ColorRole.Accent)
    except AttributeError:
        return None
    if not c.isValid() or sys.platform != "win32":
        return None
    if sombre:
        c = c.lighter(160) if c.lightness() < 150 else c
    else:
        c = c.darker(115) if c.lightness() > 140 else c
    return c.name()


def appliquer(app, preference: str = "systeme") -> Palette:
    """preference : « systeme », « clair » ou « sombre »."""
    global P
    sombre = systeme_sombre() if preference == "systeme" else preference == "sombre"
    P = Palette(**(SOMBRE if sombre else CLAIR))
    acc = accent_windows(sombre)
    if acc:
        P.accent = acc
        P.accent_texte = "#000000" if QColor(acc).lightness() > 150 else "#FFFFFF"
    police = QFont("Segoe UI Variable Text")
    if not police.exactMatch():
        police = QFont("Segoe UI")
    police.setPointSizeF(10.5)  # ≈ 14 px à 100 %
    app.setFont(police)
    if contraste_eleve():
        app.setStyleSheet("")
        return P
    app.setStyleSheet(qss(P))
    return P


def fleche(p: Palette) -> str:
    """Chemin de l'image de la flèche des listes déroulantes (visible en clair et en sombre)."""
    from importlib import resources
    nom = "fleche_bas_sombre.png" if p.sombre else "fleche_bas_clair.png"
    return str(resources.files("mat_methode.data").joinpath(nom)).replace("\\", "/")


def qss(p: Palette) -> str:
    return f"""
* {{ color: {p.texte}; }}
QMainWindow, QWidget#racine, QStackedWidget, QScrollArea, QScrollArea > QWidget > QWidget#page {{ background: {p.fond}; }}
QWidget#volet {{ background: {p.volet}; }}
QFrame#carte, QFrame[carte="true"] {{ background: {p.carte}; border: 1px solid {p.trait}; border-radius: 8px; }}
QFrame#sousCarte {{ background: {p.fond}; border: 1px solid {p.trait}; border-radius: 8px; }}
QFrame#carteFlux {{ background: {p.carte}; border: 1px solid {p.trait}; border-radius: 8px; }}
QFrame#carteFlux[sel="true"] {{ background: {p.info_fond}; border: 1px solid {p.accent}; border-left: 3px solid {p.accent}; }}
QFrame#carteFlux:hover {{ border-color: {p.texte2}; }}
QLabel {{ background: transparent; }}
QLabel#titrePage {{ font-size: 21pt; font-weight: 600; }}
QLabel#sousTitre {{ font-size: 15pt; font-weight: 600; }}
QLabel#titreCarte {{ font-size: 11pt; font-weight: 600; }}
QLabel#secondaire, QLabel[secondaire="true"] {{ color: {p.texte2}; }}
QLabel#mono {{ font-family: "Cascadia Mono", Consolas, monospace; }}
QLabel#enregistrement {{ color: {p.texte2}; font-size: 9pt; }}
QLabel#enregistrement[erreur="true"] {{ color: {p.danger}; font-weight: 600; }}
QLabel#etiquetteChamp {{ color: {p.texte2}; font-size: 9.5pt; }}
QLabel#conditions {{ color: {p.accent if not p.sombre else p.accent}; font-family: "Cascadia Mono", Consolas, monospace; font-size: 9pt; }}
QLabel#aCompleter {{ color: {p.ambre_texte}; font-style: italic; }}
QLabel#numero {{ background: {p.accent}; color: {p.accent_texte}; border-radius: 11px; font-weight: 700; qproperty-alignment: AlignCenter; }}
QLabel#badge {{ background: {p.ambre_texte}; color: {p.carte}; border-radius: 9px; font-weight: 700; font-size: 8pt; qproperty-alignment: AlignCenter; }}
QLabel#pastille {{ border-radius: 4px; padding: 2px 8px; font-size: 9pt; }}
QLabel#ambre {{ background: {p.ambre_fond}; color: {p.ambre_texte}; border: 1px solid {p.ambre_trait}; border-radius: 4px; padding: 1px 6px;
  font-family: "Cascadia Mono", Consolas, monospace; font-size: 9pt; }}
QPushButton, QToolButton {{ background: {p.bouton}; border: 1px solid {p.trait}; border-bottom-color: {"#D0D0D0" if not p.sombre else "#2A2A2A"};
  border-radius: 4px; padding: 5px 12px; min-height: 20px; }}
QPushButton:hover, QToolButton:hover {{ background: {p.bouton_survol}; }}
QPushButton:pressed {{ color: {p.texte2}; }}
QPushButton:disabled {{ color: {"#A0A0A0" if not p.sombre else "#777777"}; }}
QPushButton:focus, QToolButton:focus {{ border: 2px solid {p.texte}; }}
QPushButton[accent="true"] {{ background: {p.accent}; color: {p.accent_texte}; border: 1px solid {p.accent}; }}
QPushButton[accent="true"]:hover {{ background: {QColor(p.accent).lighter(110).name() if not p.sombre else QColor(p.accent).darker(110).name()}; }}
QPushButton[accent="true"]:disabled {{ background: {p.selection}; color: {p.texte2}; border-color: {p.trait}; }}
QPushButton[danger="true"] {{ color: {p.danger}; }}
QPushButton[lien="true"] {{ background: transparent; border: none; color: {p.accent}; padding: 2px 4px; text-align: left; }}
QPushButton[lien="true"]:hover {{ text-decoration: underline; }}
QPushButton[icone="true"] {{ padding: 4px; min-width: 24px; max-width: 32px; }}
QPushButton[nav="true"] {{ background: transparent; border: none; text-align: left; padding: 8px 12px; border-radius: 4px; }}
QPushButton[nav="true"]:hover {{ background: {p.selection}; }}
QPushButton[nav="true"][actif="true"] {{ background: {p.selection}; font-weight: 600; border-left: 3px solid {p.accent}; }}
QPushButton[pivot="true"] {{ background: transparent; border: none; border-bottom: 3px solid transparent; border-radius: 0; padding: 6px 4px; font-size: 12pt; color: {p.texte2}; }}
QPushButton[pivot="true"][actif="true"] {{ color: {p.texte}; font-weight: 600; border-bottom: 3px solid {p.accent}; }}
QPushButton[seg="true"] {{ border-radius: 0; padding: 5px 12px; }}
QPushButton[seg="true"]:checked {{ background: {p.accent}; color: {p.accent_texte}; border-color: {p.accent}; }}
QPushButton[chip="true"] {{ border-radius: 4px; padding: 3px 10px; }}
QPushButton[chip="true"]:checked {{ background: {p.info_fond}; color: {p.info_texte}; border: 1px solid {p.accent}; }}
QPushButton[ajout="true"] {{ border-style: dashed; }}
QLineEdit, QPlainTextEdit, QTextEdit, QComboBox {{ background: {p.champ}; border: 1px solid {p.trait};
  border-bottom: 1px solid {"#8A8A8A" if not p.sombre else "#9A9A9A"}; border-radius: 4px; padding: 5px 8px; selection-background-color: {p.accent};
  selection-color: {p.accent_texte}; }}
QLineEdit:hover, QComboBox:hover, QPlainTextEdit:hover {{ background: {p.champ_survol}; }}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QComboBox:focus {{ border-bottom: 2px solid {p.accent}; }}
QLineEdit:read-only {{ color: {p.texte2}; }}
QLineEdit[mono="true"] {{ font-family: "Cascadia Mono", Consolas, monospace; }}
QComboBox::drop-down {{ border: none; width: 28px; subcontrol-origin: padding; subcontrol-position: center right; }}
QComboBox::down-arrow {{ image: url("{fleche(p)}"); width: 12px; height: 12px; }}
QComboBox {{ padding-right: 28px; }}
QComboBox QAbstractItemView {{ background: {p.carte}; border: 1px solid {p.trait}; selection-background-color: {p.selection}; selection-color: {p.texte}; }}
QScrollBar:vertical {{ background: {"#E6E6E6" if not p.sombre else "#2E2E2E"}; width: 16px; margin: 0; border-left: 1px solid {p.trait}; }}
QScrollBar::handle:vertical {{ background: {"#8A8A8A" if not p.sombre else "#9A9A9A"}; border-radius: 5px; min-height: 48px; margin: 2px 3px; }}
QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover {{ background: {p.accent}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
QScrollBar:horizontal {{ height: 16px; background: {"#E6E6E6" if not p.sombre else "#2E2E2E"}; border-top: 1px solid {p.trait}; }}
QScrollBar::handle:horizontal {{ background: {"#8A8A8A" if not p.sombre else "#9A9A9A"}; border-radius: 5px; min-width: 48px; margin: 3px 2px; }}
QFrame#infobar {{ border-radius: 6px; border: 1px solid {p.trait}; }}
QFrame#infobar[niveau="warn"] {{ background: {p.ambre_fond}; border-color: {p.ambre_trait}; }}
QFrame#infobar[niveau="info"] {{ background: {p.info_fond}; }}
QFrame#infobar[niveau="danger"] {{ background: {"#FDE7E9" if not p.sombre else "#442726"}; }}
QFrame#infobar[niveau="ok"] {{ background: {p.succes_fond}; }}
QFrame#lancement {{ background: {p.carte}; border: 1px solid {p.trait}; border-radius: 8px; }}
QFrame#lancement[lancee="true"] {{ border: 1px solid {p.accent}; }}
QLabel#toast {{ background: {"#2B2B2B" if not p.sombre else "#F3F3F3"}; color: {"#FFFFFF" if not p.sombre else "#1A1A1A"}; border-radius: 6px; padding: 10px 16px; }}
QDialog {{ background: {p.carte}; }}
QWidget#scrim {{ background: rgba(0,0,0,90); }}
QTableWidget {{ background: {p.carte}; border: 1px solid {p.trait}; border-radius: 6px; gridline-color: {p.trait}; }}
QHeaderView::section {{ background: {p.fond}; border: none; border-bottom: 1px solid {p.trait}; padding: 6px; font-weight: 600; color: {p.texte2}; }}
QTextBrowser {{ background: {p.carte}; border: 1px solid {p.trait}; border-radius: 8px; padding: 12px; }}
QToolTip {{ background: {p.carte}; color: {p.texte}; border: 1px solid {p.trait}; padding: 4px; }}
QMenu {{ background: {p.carte}; border: 1px solid {p.trait}; padding: 4px; border-radius: 6px; }}
QMenu::item {{ padding: 6px 24px 6px 12px; border-radius: 4px; }}
QMenu::item:selected {{ background: {p.selection}; }}
"""
