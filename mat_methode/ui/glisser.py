"""Glisser-déposer : poignée « ⠿ » pour attraper une étape, une grande étape ou un échantillon, et zones où les déposer.

Le contenu glissé est un petit texte « genre:identifiant » ; la zone de dépôt reçoit (genre, identifiant, avant) où
`avant` dit si le curseur est dans la moitié haute de la zone."""
from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QEvent, QMimeData, QObject, Qt
from PySide6.QtGui import QDrag
from PySide6.QtWidgets import QApplication, QLabel, QWidget

MIME = "application/x-matmethode"


def _demarrer(source: QWidget, genre: str, ident: str, apercu: QWidget | None = None) -> None:
    mime = QMimeData()
    mime.setData(MIME, f"{genre}:{ident}".encode("utf-8"))
    drag = QDrag(source)
    drag.setMimeData(mime)
    cible = apercu or source
    drag.setPixmap(cible.grab().scaledToWidth(min(cible.width(), 360), Qt.TransformationMode.SmoothTransformation))
    drag.exec(Qt.DropAction.MoveAction)


def lire(mime: QMimeData) -> tuple[str, str] | None:
    if not mime.hasFormat(MIME):
        return None
    genre, _, ident = bytes(mime.data(MIME).data()).decode("utf-8").partition(":")
    return (genre, ident) if ident else None


class Poignee(QLabel):
    """« ⠿ » : on l'attrape pour déplacer l'étape, la grande étape ou l'échantillon."""

    def __init__(self, genre: str, ident: str, nom: str, apercu: QWidget | None = None):
        super().__init__("⠿")
        self.genre, self.ident, self.apercu, self._debut = genre, ident, apercu, None
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setToolTip(f"Glisser pour déplacer {nom}")
        self.setAccessibleName(f"Déplacer {nom} (glisser-déposer)")
        self.setStyleSheet("font-size:14pt;padding:0 4px;color:gray;background:transparent;border:none;")

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._debut = e.position().toPoint()

    def mouseMoveEvent(self, e):
        if self._debut is not None and (e.position().toPoint() - self._debut).manhattanLength() >= QApplication.startDragDistance():
            self._debut = None
            _demarrer(self, self.genre, self.ident, self.apercu)

    def mouseReleaseEvent(self, e):
        self._debut = None


class _Source(QObject):
    """Filtre d'événements : glisser un widget (un clic simple appelle `clic`)."""

    def __init__(self, w: QWidget, genre: str, ident: str, clic):
        super().__init__(w)
        self.w, self.genre, self.ident, self.clic, self.debut = w, genre, ident, clic, None

    def eventFilter(self, obj, e):
        t = e.type()
        if t == QEvent.Type.MouseButtonPress and e.button() == Qt.MouseButton.LeftButton:
            self.debut = e.position().toPoint()
            return True
        if t == QEvent.Type.MouseMove and self.debut is not None:
            if (e.position().toPoint() - self.debut).manhattanLength() >= QApplication.startDragDistance():
                self.debut = None
                _demarrer(self.w, self.genre, self.ident)
            return True
        if t == QEvent.Type.MouseButtonRelease:
            if self.debut is not None and self.clic:
                self.clic()
            self.debut = None
            return True
        return False


def rendre_source(w: QWidget, genre: str, ident: str, clic: Callable[[], None] | None = None) -> None:
    """Un widget (ex. pastille d'échantillon) qu'on peut glisser ; un simple clic appelle `clic`."""
    w.installEventFilter(_Source(w, genre, ident, clic))
    w.setCursor(Qt.CursorShape.OpenHandCursor)


def _marquer(w: QWidget, valeur: str) -> None:
    if w.property("depot") != (valeur or None):
        w.setProperty("depot", valeur or None)
        w.style().unpolish(w)
        w.style().polish(w)


class _Cible(QObject):
    """Filtre d'événements : zone où l'on peut déposer."""

    def __init__(self, w: QWidget, acceptes: dict[str, str], depot):
        super().__init__(w)
        self.w, self.acceptes, self.depot = w, acceptes, depot

    def _repere(self, e, genre):
        if self.acceptes[genre] == "dedans":
            return "dedans", True
        haut = e.position().y() < self.w.height() / 2
        return ("avant" if haut else "apres"), haut

    def eventFilter(self, obj, e):
        t = e.type()
        if t in (QEvent.Type.DragEnter, QEvent.Type.DragMove):
            lu = lire(e.mimeData())
            if lu and lu[0] in self.acceptes:
                e.acceptProposedAction()
                _marquer(self.w, self._repere(e, lu[0])[0])
            else:
                e.ignore()
            return True
        if t == QEvent.Type.DragLeave:
            _marquer(self.w, "")
            return True
        if t == QEvent.Type.Drop:
            lu = lire(e.mimeData())
            _marquer(self.w, "")
            if lu and lu[0] in self.acceptes:
                e.acceptProposedAction()
                self.depot(lu[0], lu[1], self._repere(e, lu[0])[1])
            else:
                e.ignore()
            return True
        return False


def rendre_cible(w: QWidget, acceptes: dict[str, str], depot: Callable[[str, str, bool], None]) -> None:
    """Zone où l'on peut déposer. `acceptes` : genre -> « avant » (bord haut ou bas selon la moitié visée) ou « dedans »
    (toute la zone). `depot(genre, identifiant, avant)` est appelé au lâcher."""
    w.setAcceptDrops(True)
    w.installEventFilter(_Cible(w, acceptes, depot))
