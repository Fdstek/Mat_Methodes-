"""Colonnes communes des tableaux de manips (Définition, Archivées, Protocole, Rapport) : donneur d'ordre, type, tags.

Colonnes centrées ; un clic sur l'en-tête « Donneur d'ordre » ou « Type » (ou sur un nom dans une ligne) trie le tableau
(croissant, puis décroissant, puis ordre d'origine)."""
from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QCheckBox, QLabel, QMenu, QPushButton, QToolButton, QVBoxLayout, QWidget, QWidgetAction

from mat_methode.domain import reglages_ops as O
from mat_methode.domain import regles as R
from mat_methode.domain.texte import norm, prenom
from mat_methode.ui import theme
from mat_methode.ui.widgets import bouton, etiquette, flux_widgets

LARG_DONNEUR, LARG_ATTRIBUE, LARG_TYPE, LARG_ETAPES, LARG_TAGS = 105, 85, 80, 105, 130
COMMUNES = (("DONNEUR", LARG_DONNEUR), ("ATTRIBUÉ", LARG_ATTRIBUE), ("TYPE", LARG_TYPE), ("ÉTAPES", LARG_ETAPES), ("TAGS", LARG_TAGS))
TRIABLES = {"DONNEUR": "donneur", "ATTRIBUÉ": "attribue", "TYPE": "type", "ÉTAPES": "etapes"}
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
    b = Pilule(prenom(m.contexte.donneur), O.couleur_donneur(r, m.contexte.donneur), (lambda: trier("donneur")) if trier else None,
               f"{m.contexte.donneur} : trier par donneur d’ordre" if trier else m.contexte.donneur, LARG_DONNEUR)
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


def cellule_attribue(m, r, trier: Callable[[str], None] | None = None) -> QWidget:
    """Prénom de la personne à qui la manip est attribuée, en tag de couleur (cliquable : tri)."""
    nom = m.contexte.attribue
    if not nom:
        return boite(etiquette("—", secondaire=True), LARG_ATTRIBUE)
    return boite(Pilule(prenom(nom), O.couleur_donneur(r, nom), (lambda: trier("attribue")) if trier else None,
                        f"Attribuée à {nom}" + (" : trier par attribution" if trier else ""), LARG_ATTRIBUE), LARG_ATTRIBUE)


def cellule_etapes(m) -> QWidget:
    """Un tag de couleur par grande étape : initiale et matériel de sa première sous-étape (« D : R1 »)."""
    rep = R.reperes_etapes(m)
    if not rep:
        return boite(etiquette("—", secondaire=True), LARG_ETAPES)
    palette = O.PALETTE_DONNEURS
    puces = [Pilule(f"{i} : {mat}" if mat else i, palette[sum(ord(c) for c in g.lower()) % len(palette)], None,
                    f"{g} : {mat or 'matériel non indiqué'}", LARG_ETAPES) for i, g, mat in rep]
    return fixe(flux_widgets(puces, centre=True), LARG_ETAPES)


def cellules_communes(m, r, clic_tag: Callable[[str], None] | None = None, trier: Callable[[str], None] | None = None) -> list[QWidget]:
    return [cellule_donneur(m, r, trier), cellule_attribue(m, r, trier), cellule_type(m, r, trier), cellule_etapes(m), cellule_tags(m, r, clic_tag)]


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
class ListeMulti(QToolButton):
    """Liste déroulante à choix multiples : « Tous les types » ou « Type : A, B ». La liste reste ouverte entre deux choix."""
    change = Signal()

    def __init__(self, vide: str, options: list[str], choisis: set[str], nom: str):
        super().__init__()
        self._vide, self._choisis = vide, choisis
        self.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.setAccessibleName(nom)
        self.setToolTip(nom + " (plusieurs choix possibles)")
        self.setMinimumWidth(130)
        self.setStyleSheet("QToolButton::menu-indicator{subcontrol-position:right center;right:8px;}QToolButton{padding:5px 26px 5px 10px;text-align:left;}")
        menu = QMenu(self)
        self._cases: list[QCheckBox] = []
        for o in options:
            case = QCheckBox(o)  # une case dans le menu : cliquer ne ferme pas la liste
            case.setChecked(o in choisis)
            case.setStyleSheet("QCheckBox{padding:5px 14px;}")
            case.toggled.connect(lambda on, o=o: self._basculer(o, on))
            act = QWidgetAction(menu)
            act.setDefaultWidget(case)
            menu.addAction(act)
            self._cases.append(case)
        if options:
            menu.addSeparator()
            menu.addAction("Tout décocher", self._vider)
        self.setMenu(menu)
        self._en_attente = False
        menu.aboutToHide.connect(self._fermee)  # la liste n'est reconstruite qu'à la fermeture du menu (sinon elle se refermerait)
        self._texte()

    def _fermee(self):
        if self._en_attente:
            self._en_attente = False
            self.change.emit()

    def _texte(self):
        n = len(self._choisis)
        t = self._vide if not n else (", ".join(sorted(self._choisis)) if n <= 2 else f"{n} sélectionnés")
        self.setText(t.replace("&", "&&"))

    def _basculer(self, o: str, on: bool):
        (self._choisis.add if on else self._choisis.discard)(o)
        self._texte()
        self._en_attente = True

    def _vider(self):
        self._choisis.clear()
        for c in self._cases:
            c.blockSignals(True)
            c.setChecked(False)
            c.blockSignals(False)
        self._texte()
        self._en_attente = True


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
        """Barre de filtres sur une seule ligne (qui passe à la suivante si la fenêtre est étroite) : tags de donneur d'ordre,
        tags de personne attribuée (seulement ceux qui ont des manips) et listes à choix multiples.
        Les noms sont réduits au prénom, puis aux initiales quand il y a beaucoup de tags."""
        from mat_methode.domain.models import initiales_de
        from mat_methode.ui.widgets import bouton_tag_couleur, flux_widgets
        groupes = []  # (titre, texte « tout », noms présents, choisis, valeur)
        for titre, tout, noms, choisis, valeur in (("Donneur d’ordre", "Tous", r.donneurs_proposes, self.donneur, lambda m: m.contexte.donneur),
                                                   ("Manip attribuée à", "Toutes", r.attributions, self.attribue, lambda m: m.contexte.attribue)):
            presents = [n for n in noms if any(valeur(m) == n for m in manips)]
            choisis &= set(presents)
            groupes.append((titre, tout, presents, choisis, valeur))
        court = sum(len(g[2]) for g in groupes) > 6  # beaucoup de tags : initiales seulement

        def libelle(nom: str) -> str:
            return nom if "·" in nom else (initiales_de(nom) if court else prenom(nom))

        widgets: list[QWidget] = []
        for titre, tout, presents, choisis, valeur in groupes:
            widgets.append(etiquette(titre, secondaire=True))
            toutes = bouton(tout, lambda choisis=choisis: (choisis.clear(), change()))
            toutes.setProperty("chip", True)
            toutes.setCheckable(True)
            toutes.setChecked(not choisis)
            widgets.append(toutes)

            def bascule(n, choisis=choisis):
                (choisis.discard if n in choisis else choisis.add)(n)
                change()
            for n in presents:
                b = bouton_tag_couleur(libelle(n), O.couleur_donneur(r, n), sum(1 for m in manips if valeur(m) == n), n in choisis,
                                       lambda n=n, bascule=bascule: bascule(n))
                b.setToolTip(n)
                widgets.append(b)
        for vide, options, choisis, nom in (("Tous les types", [t for t in r.types_demande if any(m.contexte.type == t for m in manips)],
                                             self.type, "Filtrer par type de demande"),
                                            ("Tous les tags", tags, self.tag, "Filtrer par tag")):
            choisis &= set(options)
            lm = ListeMulti(vide, options, choisis, nom)
            lm.change.connect(change)
            widgets.append(lm)
        return flux_widgets(widgets)


# ------------------------------------------------------------------ colonne « Manip » (identique dans Mat & Méthode et Protocole)
def resume_manip(ctrl, m) -> QWidget:
    """Titre, n° d'expérience, objectif, étapes / échantillons / date / version, puis pastilles (à faire, modification en cours, présence)."""
    from PySide6.QtWidgets import QSizePolicy

    from mat_methode.domain.texte import fmt_dt
    from mat_methode.ui.widgets import avatar, pastille
    c = QWidget()
    v = QVBoxLayout(c)
    v.setContentsMargins(0, 0, 0, 0)
    v.setSpacing(3)
    v.addWidget(etiquette(m.nom, "titreCarte", wrap=True))  # titre complet, sur plusieurs lignes si besoin
    if m.contexte.experience:
        v.addWidget(etiquette(sous_titre_manip(m), secondaire=True, wrap=True))
    if m.contexte.objectif:
        o = etiquette(m.contexte.objectif, secondaire=True, wrap=True)
        o.setStyleSheet("font-style:italic;")
        o.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        v.addWidget(o)
    ne = len(m.etapes)
    info = etiquette(f"{ne} étape{'s' if ne > 1 else ''} · {len(m.prelevements)} éch. · {fmt_dt(m.maj)[:10]} · v{m.rev}", secondaire=True)
    info.setMinimumWidth(1)
    info.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
    v.addWidget(info)
    marques = []
    reste = sum(1 for t in m.a_faire if not t.fait)
    if reste:
        marques.append(pastille(f"{reste} à faire", "warn", " ; ".join(t.texte for t in m.a_faire if not t.fait)))
    verrou = ctrl.st.verrou_autre(m.id)
    if verrou:
        marques.append(pastille(f"Modifiée par {ctrl.nom_de(verrou.utilisateur)}", "info"))
    for pr in ctrl.presents_sur(m.id):  # comme dans Excel : initiales de qui a la manip ouverte
        if not (verrou and pr.get("utilisateur") == verrou.utilisateur):
            marques.append(avatar(ctrl.initiales_de(pr.get("utilisateur", ""), pr), f"{ctrl.nom_present(pr)} a cette manip ouverte",
                                  cle=pr.get("utilisateur", "")))
    if marques:
        v.addWidget(flux_widgets(marques))
    return c
