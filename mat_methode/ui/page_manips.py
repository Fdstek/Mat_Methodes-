"""Page « Définition Mat & Méthode » (anciennement « Mes manips », §6.1) : liste des manips et leur statut."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLineEdit, QMenu, QSizePolicy, QVBoxLayout, QWidget

from mat_methode.domain import reglages_ops as O
from mat_methode.domain.models import ARCHIVEE, STATUTS_DEFINITION
from mat_methode.domain.regles import tous_les_tags
from mat_methode.domain.texte import fmt_dt, norm
from mat_methode.ui import colonnes as C
from mat_methode.ui import theme
from mat_methode.ui.controleur import Controleur
from mat_methode.ui.widgets import (
    InfoBar,
    Liste,
    bouton,
    bouton_tag_couleur,
    etiquette,
    flux_widgets,
    liste_statut,
    pastille,
    vider,
)


class PageManips(QWidget):
    ouvrir = Signal(str, str)  # id, mode (« comp » / « def »)
    nouvelle = Signal()
    importer = Signal()
    importer_mm = Signal()
    exporter = Signal(str)

    def __init__(self, ctrl: Controleur):
        super().__init__()
        self.ctrl = ctrl
        self.archives = False
        self.f_donneur = ""
        self.f_type = ""
        self.f_tag = ""
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(14)

        barre = QHBoxLayout()
        barre.addWidget(bouton("+  Nouvelle manip", self.nouvelle.emit, accent=True, tip="Nouvelle manip (Ctrl+N)"))
        barre.addWidget(bouton("Importer un ancien rapport", self.importer.emit, tip="Rapport PDF ou fichier JSON exporté"))
        barre.addWidget(bouton("Importer un ancien Mat & Méthode", self.importer_mm.emit, tip="Fichier Word ou texte, ou texte collé"))
        barre.addStretch(1)
        self.recherche = QLineEdit()  # placée à droite des onglets Manips / Archivées
        self.recherche.setPlaceholderText("Rechercher une manip, un tag, un objectif…")
        self.recherche.setAccessibleName("Rechercher une manip (Ctrl+F)")
        self.recherche.setClearButtonEnabled(True)
        self.recherche.setMinimumWidth(180)
        self.recherche.textChanged.connect(lambda *_: self.rafraichir())
        lay.addLayout(barre)

        self.pivot = QHBoxLayout()
        self.b_actives = bouton("", lambda: self._onglet(False))
        self.b_archives = bouton("", lambda: self._onglet(True))
        for b in (self.b_actives, self.b_archives):
            b.setProperty("pivot", True)
            self.pivot.addWidget(b)
        self.pivot.addStretch(1)
        self.pivot.addWidget(self.recherche)
        lay.addLayout(self.pivot)

        self.filtres = QHBoxLayout()
        lay.addLayout(self.filtres)
        self.bandeaux = QVBoxLayout()
        lay.addLayout(self.bandeaux)
        self.liste = QFrame()
        self.liste.setObjectName("carte")
        self.l_liste = QVBoxLayout(self.liste)
        self.l_liste.setContentsMargins(0, 0, 0, 0)
        self.l_liste.setSpacing(0)
        lay.addWidget(self.liste)
        bas = QHBoxLayout()
        bas.addWidget(etiquette("Modifier le flux, Dupliquer, Exporter, Archiver : menu « … » de chaque ligne.", secondaire=True, wrap=True), 1)
        bas.addStretch(1)
        bas.addWidget(bouton("Actualiser", self._actualiser))
        bas.addWidget(bouton("Restaurer les exemples", self._exemples))
        lay.addLayout(bas)
        lay.addStretch(1)

    # ------------------------------------------------------------ actions
    def _onglet(self, archives: bool):
        self.archives = archives
        self.rafraichir()

    def _actualiser(self):
        self.ctrl.actualiser()
        self.ctrl.toast.emit("Liste actualisée")

    def _exemples(self):
        from mat_methode.ui.dialogues import confirmer
        if confirmer(self, "Restaurer les exemples ?", "Les manips d’exemple sont remises à leur état d’origine et les réglages "
                     "d’exemple sont ajoutés. Tes autres manips ne sont pas touchées.", "Restaurer"):
            self.ctrl.restaurer_exemples()
            self.ctrl.toast.emit("Exemples restaurés")
            self.rafraichir()

    def _visibles(self):
        q = norm(self.recherche.text())
        out = []
        for m in self.ctrl.manips:
            if (m.etat == ARCHIVEE) != self.archives:
                continue
            c = m.contexte
            if q and q not in norm(" ".join([m.nom, c.donneur, c.ref, c.type, c.objectif, c.idee, " ".join(m.tags)])):
                continue
            if self.f_donneur and c.donneur != self.f_donneur:
                continue
            if self.f_type and c.type != self.f_type:
                continue
            if self.f_tag and not any(norm(t) == norm(self.f_tag) for t in m.tags):
                continue
            out.append(m)
        return sorted(out, key=lambda m: m.maj, reverse=True)

    def _filtre_donneur(self, nom: str):
        self.f_donneur = "" if nom == self.f_donneur else nom
        self.rafraichir()

    # ------------------------------------------------------------ affichage
    def rafraichir(self):
        ctrl, r = self.ctrl, self.ctrl.reglages
        n_a = sum(1 for m in ctrl.manips if m.etat != ARCHIVEE)
        n_r = len(ctrl.manips) - n_a
        self.b_actives.setText(f"Manips ({n_a})")
        self.b_archives.setText(f"Archivées ({n_r})")
        for b, actif in ((self.b_actives, not self.archives), (self.b_archives, self.archives)):
            b.setProperty("actif", actif)
            b.style().unpolish(b)
            b.style().polish(b)

        vider(self.filtres)
        self.filtres.addWidget(etiquette("Donneur d’ordre", secondaire=True))
        tous = bouton("Tous", lambda: self._filtre_donneur(""))
        tous.setProperty("chip", True)
        tous.setCheckable(True)
        tous.setChecked(not self.f_donneur)
        self.filtres.addWidget(tous)
        for nom in r.donneurs_ordre:
            n = sum(1 for m in ctrl.manips if m.contexte.donneur == nom and (m.etat == ARCHIVEE) == self.archives)
            self.filtres.addWidget(bouton_tag_couleur(nom, O.couleur_donneur(r, nom), n, self.f_donneur == nom,
                                                      lambda nom=nom: self._filtre_donneur(nom)))
        types = Liste(r.types_demande, self.f_type, vide="Tous les types")
        types.setAccessibleName("Filtrer par type de demande")
        types.choisi.connect(lambda v: (setattr(self, "f_type", v), self.rafraichir()))
        self.filtres.addWidget(types)
        tags = Liste(tous_les_tags(ctrl.manips, ctrl.reglages.ordre_tags), self.f_tag, vide="Tous les tags")
        tags.setAccessibleName("Filtrer par tag")
        tags.choisi.connect(lambda v: (setattr(self, "f_tag", v), self.rafraichir()))
        self.filtres.addWidget(tags)
        self.filtres.addStretch(1)

        vider(self.bandeaux)
        if ctrl.liste.conflits:
            n = len(ctrl.liste.conflits)
            self.bandeaux.addWidget(InfoBar(f"{', '.join(ctrl.liste.conflits)} : copie créée par la synchronisation SharePoint / OneDrive. "
                                            "Compare-la à la manip d’origine ; l’application ne la supprime jamais.",
                                            titre=f"{n} conflit{'s' if n > 1 else ''} de synchronisation à vérifier"))
        if ctrl.liste.illisibles:
            self.bandeaux.addWidget(InfoBar("Ignoré(s) : " + " ; ".join(ctrl.liste.illisibles), titre="Fichier illisible"))

        vider(self.l_liste)
        lignes = self._visibles()
        if not lignes:
            vide = etiquette("Aucune manip archivée." if self.archives else "Aucune manip. Crée-en une avec « Nouvelle manip ».", secondaire=True)
            vide.setContentsMargins(16, 24, 16, 24)
            self.l_liste.addWidget(vide)
        else:
            self.l_liste.addWidget(self._entete())
        for i, m in enumerate(lignes):
            self.l_liste.addWidget(self._ligne(m, i == len(lignes) - 1))

    # colonnes alignées sur l'en-tête : donneur, type, tags, statut, Ouvrir, « … »
    LARGEURS = (C.LARG_DONNEUR, C.LARG_TYPE, C.LARG_TAGS, 125, 75, 40)

    def _grille(self, g: QGridLayout):
        g.setContentsMargins(14, 12, 14, 12)
        g.setHorizontalSpacing(12)
        g.setColumnStretch(0, 1)
        for k, lg in enumerate(self.LARGEURS, start=1):
            g.setColumnMinimumWidth(k, lg)

    def _fixe(self, w: QWidget, k: int) -> QWidget:
        w.setFixedWidth(self.LARGEURS[k - 1])
        return w

    def _entete(self) -> QWidget:
        w = QFrame()
        w.setObjectName("ligneManip")
        w.setStyleSheet(f"QFrame#ligneManip{{border-bottom:1px solid {theme.P.trait};}}")
        g = QGridLayout(w)
        self._grille(g)
        g.setContentsMargins(14, 8, 14, 8)
        g.addWidget(etiquette("MANIP", "etiquetteChamp"), 0, 0)
        for k, x in enumerate(C.entetes_communes(), start=1):
            g.addWidget(x, 0, k)
        g.addWidget(self._fixe(etiquette("STATUT", "etiquetteChamp"), 4), 0, 4)
        for k in (5, 6):
            g.addWidget(self._fixe(QWidget(), k), 0, k)
        return w

    def _ligne(self, m, derniere: bool) -> QWidget:
        r, p = self.ctrl.reglages, theme.P
        w = QFrame()
        w.setStyleSheet("" if derniere else f"QFrame#ligneManip{{border-bottom:1px solid {p.trait};}}")
        w.setObjectName("ligneManip")
        g = QGridLayout(w)
        self._grille(g)
        gauche = QVBoxLayout()
        gauche.setSpacing(3)
        gauche.addWidget(etiquette(m.nom, "titreCarte", wrap=True))  # titre complet, sur plusieurs lignes si besoin
        if m.contexte.objectif:
            o = etiquette("", secondaire=True)
            o.setStyleSheet("font-style:italic;")
            o.setText(o.fontMetrics().elidedText(m.contexte.objectif, Qt.TextElideMode.ElideRight, 330))
            o.setMinimumWidth(1)
            o.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
            o.setToolTip(m.contexte.objectif)
            gauche.addWidget(o)
        ne = len(m.etapes)
        info = etiquette(f"{ne} étape{'s' if ne > 1 else ''} · {len(m.prelevements)} éch. · {fmt_dt(m.maj)[:10]} · v{m.rev}", secondaire=True)
        info.setMinimumWidth(1)
        info.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        gauche.addWidget(info)
        marques = []
        reste = sum(1 for t in m.a_faire if not t.fait)
        if reste:
            marques.append(pastille(f"{reste} à faire", "warn", " ; ".join(t.texte for t in m.a_faire if not t.fait)))
        v = self.ctrl.st.verrou_autre(m.id)
        if v:
            marques.append(pastille(f"Modifiée par {self.ctrl.nom_de(v.utilisateur)}", "info"))
        if marques:
            gauche.addWidget(flux_widgets(marques))
        cg = QWidget()
        cg.setLayout(gauche)
        gauche.setContentsMargins(0, 0, 0, 0)
        g.addWidget(cg, 0, 0)
        for k, x in enumerate(C.cellules_communes(m, r, lambda t: (setattr(self, "f_tag", t), self.rafraichir())), start=1):
            g.addWidget(x, 0, k)
        if m.etat == ARCHIVEE:
            g.addWidget(self._fixe(etiquette("Archivée", secondaire=True), 4), 0, 4)
        else:
            st = liste_statut(m, STATUTS_DEFINITION)
            st.setMinimumWidth(0)
            st.setMinimumContentsLength(6)
            st.choisi.connect(lambda v, m=m: self._statut(m, v))
            g.addWidget(self._fixe(st, 4), 0, 4)
        g.addWidget(self._fixe(bouton("Ouvrir", lambda: self.ouvrir.emit(m.id, "comp" if m.etapes else "def"), accent=True,
                                      tip=f"Ouvrir le flux de {m.nom}"), 5), 0, 5)
        plus = bouton("…", tip=f"Autres actions pour {m.nom}")
        menu = QMenu(plus)
        menu.addAction("Modifier le flux (étapes)", lambda: self.ouvrir.emit(m.id, "def"))
        menu.addAction("Dupliquer", lambda: self._dupliquer(m.id))
        menu.addAction("Exporter", lambda: self.exporter.emit(m.id))
        menu.addAction("Restaurer" if m.etat == ARCHIVEE else "Archiver", lambda: self._archiver(m))
        if O.peut_supprimer(m):
            menu.addAction("Supprimer", lambda: self._supprimer(m))
        plus.setMenu(menu)
        plus.setStyleSheet("QPushButton::menu-indicator{width:0;}")
        self._fixe(plus, 6)
        g.addWidget(plus, 0, 6)
        for k in range(1, 7):
            g.setAlignment(g.itemAtPosition(0, k).widget(), Qt.AlignmentFlag.AlignVCenter)
        return w

    def _dupliquer(self, ident):
        c = self.ctrl.dupliquer(ident)
        self.ctrl.toast.emit(f"Copie créée : {c.nom}")
        self.rafraichir()

    def _archiver(self, m):
        if self.ctrl.st.verrou_autre(m.id):
            self.ctrl.toast.emit("Impossible : la manip est modifiée en ce moment par quelqu’un d’autre")
            return
        from mat_methode.ui.dialogues import confirmer
        if m.etat != ARCHIVEE and not confirmer(
                self, "Archiver cette manip ?", f"« {m.nom} » passera dans l’onglet Archivées. Elle reste consultable et peut être restaurée.",
                "Archiver", danger=False):
            return
        a = O.archiver_ou_restaurer(self.ctrl.reglages, m)
        self.ctrl.toucher(m)
        self.ctrl.enregistrer_tout()
        self.ctrl.toast.emit("Archivée" if a else "Restaurée")
        self.rafraichir()

    def _statut(self, m, statut: str):
        msg = self.ctrl.changer_statut(m, statut)
        if msg:
            self.ctrl.toast.emit(msg)
        elif statut == "validee":
            self.ctrl.toast.emit("Validée : elle apparaît maintenant dans Protocole")
        self.rafraichir()

    def _supprimer(self, m):
        from mat_methode.ui.dialogues import confirmer
        if confirmer(self, "Supprimer définitivement ?", f"« {m.nom} » sera supprimée. Une copie reste dans les sauvegardes du jour ; "
                     "Ctrl+Z annule tant que l’application est ouverte.", "Supprimer"):
            self.ctrl.supprimer(m.id)
            self.ctrl.toast.emit("Manip supprimée (Ctrl+Z pour annuler)")
            self.rafraichir()

    def tous_tags(self):
        return tous_les_tags(self.ctrl.manips, self.ctrl.reglages.ordre_tags)

    def focus_recherche(self):
        self.recherche.setFocus()
        self.recherche.selectAll()

