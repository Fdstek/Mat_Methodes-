"""Contrôles Windows 11 faits avec PySide6 seul : ToggleSwitch, NumberBox, pastilles, Expander,
SegmentedControl, InfoBar, toast, FlowLayout."""
from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtCore import Property, QEasingCurve, QPoint, QPropertyAnimation, QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QAbstractButton,
    QComboBox,
    QCompleter,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLayout,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from mat_methode.domain.texte import fmt_num
from mat_methode.ui import theme


# ------------------------------------------------------------------ fabriques
def bouton(texte: str, clic: Callable | None = None, accent=False, danger=False, lien=False, ajout=False, tip: str = "") -> QPushButton:
    b = QPushButton(texte.replace("&", "&&"))
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    for k, v in (("accent", accent), ("danger", danger), ("lien", lien), ("ajout", ajout)):
        if v:
            b.setProperty(k, True)
    if tip:
        b.setToolTip(tip)
        b.setAccessibleName(tip)
    if clic:
        b.clicked.connect(lambda *_: clic())
    return b


def icone(symbole: str, tip: str, clic: Callable | None = None, danger=False) -> QPushButton:
    """Petit bouton carré (↑ ↓ ⧉ ✕…) avec un nom accessible."""
    b = bouton(symbole, clic, danger=danger, tip=tip)
    b.setProperty("icone", True)
    return b


def etiquette(texte: str, nom: str = "", secondaire=False, wrap=False) -> QLabel:
    l = QLabel(texte)
    if nom:
        l.setObjectName(nom)
    if secondaire:
        l.setProperty("secondaire", True)
    l.setWordWrap(wrap)
    return l


def carte(nom="carte") -> tuple[QFrame, QVBoxLayout]:
    f = QFrame()
    f.setObjectName(nom)
    lay = QVBoxLayout(f)
    lay.setContentsMargins(16, 14, 16, 14)
    lay.setSpacing(10)
    return f, lay


def champ(libelle: str, w: QWidget) -> QWidget:
    """Libellé visible au-dessus de chaque champ (accessibilité)."""
    c = QWidget()
    lay = QVBoxLayout(c)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(4)
    lb = etiquette(libelle, "etiquetteChamp")
    lb.setBuddy(w)
    lay.addWidget(lb)
    lay.addWidget(w)
    w.setAccessibleName(libelle)
    return c


def ligne(*widgets, espacement=8, etirer=True) -> QWidget:
    w = QWidget()
    lay = QHBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(espacement)
    for x in widgets:
        if x == "stretch":
            lay.addStretch(1)
        else:
            lay.addWidget(x, 0, Qt.AlignmentFlag.AlignBottom)
    return w


def vider(layout: QLayout) -> None:
    while layout.count():
        it = layout.takeAt(0)
        w = it.widget()
        if w is not None:
            w.hide()
            w.setParent(None)
            w.deleteLater()
        elif it.layout() is not None:
            vider(it.layout())


# ------------------------------------------------------------------ texte
class ChampTexte(QLineEdit):
    """QLineEdit qui signale chaque modification faite par l'utilisateur."""
    modifie = Signal(str)

    def __init__(self, texte: str = "", placeholder: str = "", mono=False, suggestions: list[str] | None = None):
        super().__init__(texte or "")
        self.setPlaceholderText(placeholder)
        if mono:
            self.setProperty("mono", True)
        self.textEdited.connect(self.modifie.emit)
        self.setCursorPosition(0)
        if suggestions:
            c = QCompleter(suggestions, self)
            c.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
            c.setFilterMode(Qt.MatchFlag.MatchContains)
            self.setCompleter(c)


class NumberBox(QLineEdit):
    """Champ numérique avec unité (accepte la virgule). Émet None si vide ou invalide."""
    valeur = Signal(object)

    def __init__(self, v: float | None = None, unite: str = "", placeholder: str = ""):
        super().__init__("" if v is None else fmt_num(v).replace(" ", ""))
        self.setProperty("mono", True)
        self.setPlaceholderText(placeholder)
        self._unite = QLabel(unite, self)
        self._unite.setProperty("secondaire", True)
        self._unite.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setTextMargins(0, 0, self._unite.sizeHint().width() + 6 if unite else 0, 0)
        self.textEdited.connect(lambda t: self.valeur.emit(self.lire()))
        self.setMinimumWidth(90)

    def lire(self) -> float | None:
        t = self.text().strip().replace(" ", "").replace(" ", "").replace(",", ".")
        if not t:
            return None
        try:
            return float(t)
        except ValueError:
            return None

    def resizeEvent(self, e):
        super().resizeEvent(e)
        s = self._unite.sizeHint()
        self._unite.setGeometry(self.width() - s.width() - 10, (self.height() - s.height()) // 2, s.width(), s.height())


class Liste(QComboBox):
    """ComboBox fermée ; une valeur absente de la liste reste affichée comme option (§8.7)."""
    choisi = Signal(str)

    def __init__(self, options: list[str], valeur: str = "", vide: str | None = "Choisir…", libelles: dict | None = None):
        super().__init__()
        self.setMinimumWidth(140)
        if vide is not None:
            self.addItem(vide, "")
        opts = list(options) + ([valeur] if valeur and valeur not in options else [])
        for o in opts:
            self.addItem((libelles or {}).get(o, o), o)
        i = self.findData(valeur)
        self.setCurrentIndex(max(0, i))
        self.activated.connect(lambda i: self.choisi.emit(self.itemData(i) or ""))


# ------------------------------------------------------------------ ToggleSwitch
class ToggleSwitch(QAbstractButton):
    def __init__(self, texte: str = "", coche=False):
        super().__init__()
        self.setCheckable(True)
        self.setChecked(coche)
        self.setText(texte)
        self.setAccessibleName(texte)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._x = 1.0 if coche else 0.0
        self._anim = QPropertyAnimation(self, b"pos_bouton", self)
        self._anim.setDuration(120)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.toggled.connect(self._animer)

    def _animer(self, c):
        self._anim.stop()
        self._anim.setEndValue(1.0 if c else 0.0)
        self._anim.start()

    def _get(self):
        return self._x

    def _set(self, v):
        self._x = v
        self.update()

    pos_bouton = Property(float, _get, _set)

    def sizeHint(self):
        return QSize(44 + 10 + self.fontMetrics().horizontalAdvance(self.text()), 28)

    def paintEvent(self, _):
        p = theme.P
        q = QPainter(self)
        q.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRect(1, (self.height() - 20) // 2, 40, 20)
        if self.isChecked():
            q.setBrush(QColor(p.accent))
            q.setPen(QColor(p.accent))
        else:
            q.setBrush(QColor(p.champ))
            q.setPen(QColor(p.texte2))
        q.drawRoundedRect(r, 10, 10)
        d = 12
        x = r.x() + 4 + int(self._x * (r.width() - d - 8))
        q.setPen(Qt.PenStyle.NoPen)
        q.setBrush(QColor(p.accent_texte if self.isChecked() else p.texte2))
        q.drawEllipse(x, r.y() + 4, d, d)
        if self.hasFocus():
            q.setBrush(Qt.BrushStyle.NoBrush)
            q.setPen(QColor(p.texte))
            q.drawRoundedRect(r.adjusted(-2, -2, 2, 2), 12, 12)
        q.setPen(QColor(p.texte))
        q.drawText(QRect(r.right() + 10, 0, self.width() - r.right() - 10, self.height()), Qt.AlignmentFlag.AlignVCenter, self.text())


# ------------------------------------------------------------------ pastilles
def pastille(texte: str, ton: str = "neutre", tip: str = "") -> QLabel:
    """Pastille d'état colorée (la couleur n'est jamais seule : le texte porte le sens)."""
    l = QLabel(texte)
    l.setObjectName("pastille")
    fg, bg = theme.P.ton(ton)
    l.setStyleSheet(f"color:{fg};background:{bg};border-radius:4px;padding:2px 8px;")
    if tip:
        l.setToolTip(tip)
    return l


def pastille_couleur(texte: str, couleur: str, compteur: int | None = None) -> QLabel:
    c = QColor(couleur)
    fond = QColor(c)
    fond.setAlpha(40 if theme.P.sombre else 28)
    fg = c.lighter(160).name() if theme.P.sombre else c.name()
    l = QLabel(texte + (f"  {compteur}" if compteur is not None else ""))
    l.setStyleSheet(f"color:{fg};background:rgba({fond.red()},{fond.green()},{fond.blue()},{fond.alpha()});"
                    f"border:1px solid {c.name()};border-radius:11px;padding:2px 10px;font-weight:600;font-size:9pt;")
    return l


def bouton_tag_couleur(texte: str, couleur: str, compteur: int, actif: bool, clic: Callable) -> QPushButton:
    c = QColor(couleur)
    fg = c.lighter(160).name() if theme.P.sombre else c.name()
    b = QPushButton(f"{texte}  {compteur}".replace("&", "&&"))
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    b.setCheckable(True)
    b.setChecked(actif)
    b.setAccessibleName(f"Filtrer par donneur d’ordre {texte}, {compteur} manips")
    b.setStyleSheet(f"QPushButton{{color:{fg};background:rgba({c.red()},{c.green()},{c.blue()},30);border:{'2' if actif else '1'}px solid {c.name()};"
                    f"border-radius:12px;padding:3px 12px;font-weight:600;}}QPushButton:focus{{border:2px solid {theme.P.texte};}}")
    b.clicked.connect(lambda *_: clic())
    return b


def ambre(texte: str, code: str | None = None) -> QWidget:
    """Pastille ambre d'un prélèvement, avec son badge."""
    w = QWidget()
    lay = QHBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(0)
    l = QLabel(texte)
    l.setObjectName("ambre")
    if code is not None:
        b = badge(code)
        l.setText(texte)
        cont = QFrame()
        cont.setObjectName("pilule")
        cont.setStyleSheet(f"QFrame#pilule{{background:{theme.P.ambre_fond};border:1px solid {theme.P.ambre_trait};border-radius:4px;}}")
        cl = QHBoxLayout(cont)
        cl.setContentsMargins(3, 1, 6, 1)
        cl.setSpacing(5)
        cl.addWidget(b)
        t = QLabel(texte)
        t.setStyleSheet(f"color:{theme.P.ambre_texte};font-family:'Cascadia Mono',Consolas,monospace;font-size:9pt;border:none;background:transparent;")
        cl.addWidget(t)
        lay.addWidget(cont)
    else:
        lay.addWidget(l)
    lay.addStretch(1)
    return w


def badge(code: str) -> QLabel:
    b = QLabel(code)
    b.setObjectName("badge")
    b.setFixedSize(18, 18)
    return b


def numero(n: int, taille=22) -> QLabel:
    l = QLabel(str(n))
    l.setObjectName("numero")
    l.setFixedSize(taille, taille)
    l.setStyleSheet(f"border-radius:{taille // 2}px;")
    return l


class ChipSupprimable(QFrame):
    """Pastille avec ✕ (retirer) et, si `renommer` est donné, ✎ (renommer)."""

    def __init__(self, texte: str, retirer: Callable, tip: str = "", renommer: Callable | None = None, tip_renommer: str = ""):
        super().__init__()
        self.setObjectName("chip")
        self.setStyleSheet(f"QFrame#chip{{background:{theme.P.bouton};border:1px solid {theme.P.trait};border-radius:4px;}}")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 2, 2, 2)
        lay.setSpacing(4)
        l = QLabel(texte)
        l.setStyleSheet("border:none;")
        lay.addWidget(l)
        if renommer is not None:
            r = QPushButton("✎")
            r.setCursor(Qt.CursorShape.PointingHandCursor)
            r.setAccessibleName(tip_renommer or f"Renommer {texte}")
            r.setToolTip(tip_renommer or f"Renommer {texte}")
            r.setStyleSheet("QPushButton{border:none;background:transparent;padding:2px 4px;font-size:9pt;}")
            r.clicked.connect(lambda *_: renommer())
            lay.addWidget(r)
        x = QPushButton("✕")
        x.setCursor(Qt.CursorShape.PointingHandCursor)
        x.setAccessibleName(tip or f"Retirer {texte}")
        x.setToolTip(tip or f"Retirer {texte}")
        x.setStyleSheet("QPushButton{border:none;background:transparent;padding:2px 6px;font-size:8pt;}")
        x.clicked.connect(lambda *_: retirer())
        lay.addWidget(x)


# ------------------------------------------------------------------ FlowLayout
class FlowLayout(QLayout):
    """Dispose les widgets en lignes qui passent à la ligne (pastilles, tags)."""

    def __init__(self, parent=None, espace=6):
        super().__init__(parent)
        self._items = []
        self._esp = espace
        self.setContentsMargins(0, 0, 0, 0)

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, i):
        return self._items[i] if 0 <= i < len(self._items) else None

    def takeAt(self, i):
        return self._items.pop(i) if 0 <= i < len(self._items) else None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, w):
        return self._placer(QRect(0, 0, w, 0), True)

    def setGeometry(self, r):
        super().setGeometry(r)
        self._placer(r, False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        s = QSize()
        for it in self._items:
            s = s.expandedTo(it.minimumSize())
        return s + QSize(2, 2)

    def _placer(self, r, test):
        x, y, h = r.x(), r.y(), 0
        for it in self._items:
            if it.widget() and not it.widget().isVisibleTo(it.widget().parentWidget()):
                continue
            s = it.sizeHint()
            if x + s.width() > r.right() and h > 0:
                x, y, h = r.x(), y + h + self._esp, 0
            if not test:
                it.setGeometry(QRect(QPoint(x, y), s))
            x += s.width() + self._esp
            h = max(h, s.height())
        return y + h - r.y()


def flux_widgets(widgets: list[QWidget]) -> QWidget:
    w = QWidget()
    fl = FlowLayout(w)
    for x in widgets:
        fl.addWidget(x)
    return w


# ------------------------------------------------------------------ Expander
class Expander(QFrame):
    """Carte repliable : en-tête cliquable (titre + note) et contenu."""

    def __init__(self, titre: str, note: str = "", ouvert=True):
        super().__init__()
        self.setObjectName("carte")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 10, 16, 14)
        lay.setSpacing(10)
        self.tete = QPushButton()
        self.tete.setCursor(Qt.CursorShape.PointingHandCursor)
        self.tete.setStyleSheet("QPushButton{border:none;background:transparent;text-align:left;padding:4px 0;font-weight:600;font-size:11pt;}")
        self._titre, self._note = titre, note
        self.tete.clicked.connect(self.basculer)
        lay.addWidget(self.tete)
        self.corps = QWidget()
        self.contenu = QVBoxLayout(self.corps)
        self.contenu.setContentsMargins(0, 0, 0, 0)
        self.contenu.setSpacing(10)
        lay.addWidget(self.corps)
        self.ouvert = ouvert
        self.corps.setVisible(ouvert)
        self._maj()

    def _maj(self):
        fl = "▾" if self.ouvert else "▸"
        self.tete.setText(f"{fl}   {self._titre}    {self._note}".rstrip())
        self.tete.setAccessibleName(f"{self._titre}, {'ouvert' if self.ouvert else 'replié'}")

    def basculer(self):
        self.ouvert = not self.ouvert
        self.corps.setVisible(self.ouvert)
        self._maj()

    def ajouter(self, w: QWidget):
        self.contenu.addWidget(w)


# ------------------------------------------------------------------ SegmentedControl
class Segmente(QWidget):
    change = Signal(str)

    def __init__(self, options: list[tuple[str, str]], valeur: str):
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self._b = {}
        for k, t in options:
            b = QPushButton(t.replace("&", "&&"))
            b.setProperty("seg", True)
            b.setCheckable(True)
            b.setChecked(k == valeur)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda *_, k=k: self._choisir(k))
            lay.addWidget(b)
            self._b[k] = b
        lay.addStretch(1)

    def _choisir(self, k):
        for kk, b in self._b.items():
            b.setChecked(kk == k)
        self.change.emit(k)


# ------------------------------------------------------------------ InfoBar
class InfoBar(QFrame):
    def __init__(self, texte: str, niveau="warn", actions: list[QPushButton] | None = None, titre: str = ""):
        super().__init__()
        self.setObjectName("infobar")
        self.setProperty("niveau", niveau)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 8, 8, 8)
        sym = {"warn": "⚠", "danger": "⛔", "info": "ℹ", "ok": "✓"}[niveau]
        s = QLabel(sym)
        s.setStyleSheet(f"color:{theme.P.ambre_texte if niveau == 'warn' else theme.P.danger if niveau == 'danger' else theme.P.accent};font-size:13pt;")
        lay.addWidget(s)
        t = QLabel((f"<b>{titre}</b>  " if titre else "") + texte)
        t.setWordWrap(True)
        t.setTextFormat(Qt.TextFormat.RichText)
        lay.addWidget(t, 1)
        for a in actions or []:
            lay.addWidget(a)


# ------------------------------------------------------------------ toast
class Toast(QLabel):
    """Message bref en bas de la fenêtre (« Copie créée », « Appliqué à 3 étapes »)."""

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setObjectName("toast")
        self.hide()
        self._t = QTimer(self)
        self._t.setSingleShot(True)
        self._t.timeout.connect(self.hide)
        self.setAccessibleName("Notification")

    def montrer(self, texte: str, ms: int = 2400):
        self.setText(texte)
        self.adjustSize()
        p = self.parentWidget()
        self.move((p.width() - self.width()) // 2, p.height() - self.height() - 28)
        self.raise_()
        self.show()
        self._t.start(ms)


def espace(h=8) -> QWidget:
    w = QWidget()
    w.setFixedHeight(h)
    return w


def separateur() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.Shape.HLine)
    f.setStyleSheet(f"color:{theme.P.trait};")
    return f


def politique_etendue(w: QWidget) -> QWidget:
    w.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
    return w


def premier(liste: list, defaut=None) -> Optional[object]:
    return liste[0] if liste else defaut
