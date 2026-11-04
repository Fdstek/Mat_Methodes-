"""Fenêtre principale : volet de navigation (NavigationView), en-tête avec l'état d'enregistrement,
pages Mes manips / Flux / Rapport / Réglages, raccourcis clavier (§13)."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QFont, QFontDatabase, QGuiApplication, QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QMainWindow,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from mat_methode import DATE_VERSION, NOM_APPLICATION, NOUVEAUTES, VERSION
from mat_methode.domain import reglages_ops as O
from mat_methode.domain.models import ARCHIVEE, REALISEE, STATUTS_PROTOCOLE
from mat_methode.domain.texte import nom_fichier
from mat_methode.exports.echange import ImportInvalide, importer
from mat_methode.exports.echange import exporter as exporter_json
from mat_methode.ui import dialogues as D
from mat_methode.ui import theme
from mat_methode.ui.controleur import Controleur
from mat_methode.ui.page_demandes import PageDemandes
from mat_methode.ui.page_flux import PageFlux
from mat_methode.ui.page_listes import PageProtocoles, PageRapports
from mat_methode.ui.page_manips import PageManips
from mat_methode.ui.page_protocole import PageProtocole
from mat_methode.ui.page_rapport import PageRapport
from mat_methode.ui.page_reglages import PageReglages
from mat_methode.ui.widgets import Toast, avatar, bouton, etiquette, pastille, vider

# Segoe Fluent Icons (Windows 11) ; repli sur des symboles simples
ICONES = {"manips": ("\ue8fd", "≡"), "flux": ("\ue8ab", "⇄"),
          "protocoles": ("\ue9d5", "☑"), "protocole": ("\ue70f", "✎"), "rapports": ("\ue8a5", "▤"), "rapport": ("\ue7c3", "▭"), "reglages": ("\ue713", "⚙"), "demandes": ("\ue8f2", "✉")}
# Menu : (clé, libellé, sous-section ?) ; une sous-section concerne la manip ouverte.
NAV = [("manips", "Mat && Méthode", False), ("flux", "Édition", True),
       ("protocoles", "Protocole", False), ("protocole", "Édition", True),
       ("rapports", "Rapport", False), ("rapport", "Édition", True),
       ("reglages", "Réglages", False)]
LARGEUR_VOLET = 215  # menu de gauche : le reste de la fenêtre sert aux pages
PAGES_MANIP = ("flux", "protocole", "rapport")  # pages qui demandent une manip ouverte
TITRES = {"manips": "Mat & Méthode", "protocoles": "Protocole", "rapports": "Rapport", "reglages": "Réglages",
          "demandes": "Bugs et idées"}


def icone_menu(glyphe: str, famille: str | None, couleur: str) -> QIcon:
    """Icône du menu : le symbole est dessiné (police Segoe Fluent Icons si présente), visible quel que soit le texte du bouton."""
    from PySide6.QtGui import QColor, QPainter, QPixmap
    if famille == "image":  # image fournie (ex. logo « Bugs et idées »)
        from importlib import resources
        return QIcon(str(resources.files("mat_methode.data").joinpath(glyphe)))
    pm = QPixmap(40, 40)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    f = QFont(famille) if famille else QFont()
    f.setPixelSize(30)
    p.setFont(f)
    p.setPen(QColor(couleur))
    p.drawText(pm.rect(), Qt.AlignmentFlag.AlignCenter, glyphe)
    p.end()
    return QIcon(pm)


def police_icones() -> str | None:
    for f in ("Segoe Fluent Icons", "Segoe MDL2 Assets"):
        if f in QFontDatabase.families():
            return f
    return None


class Fenetre(QMainWindow):
    def __init__(self, ctrl: Controleur):
        super().__init__()
        self.ctrl = ctrl
        self.setWindowTitle(NOM_APPLICATION)
        # 1360 × 860 par défaut, minimum 1100 × 700, sauf si l'écran est plus petit (mise à l'échelle 150-200 %)
        ecran = QGuiApplication.primaryScreen().availableGeometry() if QGuiApplication.primaryScreen() else None
        lw, lh = (ecran.width(), ecran.height()) if ecran else (1360, 860)
        self.setMinimumSize(min(1100, lw - 40), min(700, lh - 60))
        self.resize(min(1360, lw), min(860, lh))
        self.page = "manips"
        self.choix: dict[str, str | None] = {"flux": None, "protocole": None, "rapport": None}  # manip choisie par section
        racine = QWidget()
        racine.setObjectName("racine")
        h = QHBoxLayout(racine)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        self.setCentralWidget(racine)

        # ---- volet de navigation
        self.volet = QWidget()
        self.volet.setObjectName("volet")
        self.volet.setFixedWidth(LARGEUR_VOLET)
        v = QVBoxLayout(self.volet)
        v.setContentsMargins(8, 12, 8, 12)
        v.setSpacing(4)
        self.carte_manip = QFrame()
        self.carte_manip.setObjectName("carte")
        cm = QVBoxLayout(self.carte_manip)
        cm.setContentsMargins(12, 10, 12, 10)
        cm.setSpacing(2)
        cm.addWidget(etiquette("Manip ouverte", secondaire=True))
        self.cm_nom = etiquette("", "titreCarte", wrap=True)
        self.cm_info = etiquette("", secondaire=True, wrap=True)
        cm.addWidget(self.cm_nom)
        cm.addWidget(self.cm_info)
        v.addWidget(self.carte_manip)
        self.carte_manip.hide()  # carte « Manip ouverte » retirée (le titre de la page donne déjà la manip)
        v.addSpacing(8)
        self.nav = {}
        pi = police_icones()
        for k, t, sous in NAV:
            v.addWidget(self._nav(k, t, pi, sous))
        v.addStretch(1)
        v.addWidget(self._nav("demandes", "Bugs et idées", pi, False))  # en bas du menu, comme dans l'application Claude
        self.version = bouton(f"Version {VERSION} · {DATE_VERSION}", self._nouveautes, lien=True,
                              tip=f"Version {VERSION}, mise à jour du {DATE_VERSION} : voir les nouveautés")
        self.version.setAccessibleName("Version de l’application et nouveautés")
        v.addWidget(self.version)
        h.addWidget(self.volet)

        # ---- contenu
        contenu = QWidget()
        cv = QVBoxLayout(contenu)
        cv.setContentsMargins(0, 0, 0, 0)
        cv.setSpacing(0)
        tete = QHBoxLayout()
        tete.setContentsMargins(24, 22, 24, 6)
        titres = QVBoxLayout()
        self.titre = etiquette("", "titrePage", wrap=True)
        # « ← » : quitter la manip choisie et revenir à la liste de la section (Flux, Édition, Rapport de la manip)
        self.retour = bouton("←", self.quitter_manip, tip="Revenir à la liste (quitter cette manip)")
        self.retour.setAccessibleName("Revenir à la liste")
        self.retour.setFixedSize(36, 36)
        self.retour.setStyleSheet("QPushButton{font-size:14pt;padding:0;}")
        tete.addWidget(self.retour, 0, Qt.AlignmentFlag.AlignTop)
        self.sous_titre = QWidget()
        QHBoxLayout(self.sous_titre).setContentsMargins(0, 0, 0, 0)
        titres.addWidget(self.titre)
        titres.addWidget(self.sous_titre)
        tete.addLayout(titres, 1)
        self.enregistrement = etiquette("", "enregistrement")
        self.enregistrement.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
        self.enregistrement.setAccessibleName("État de l’enregistrement")
        self.presents = QWidget()  # pastilles aux initiales des autres personnes présentes
        self.presents.setAccessibleName("Autres personnes présentes")
        QHBoxLayout(self.presents).setContentsMargins(0, 0, 12, 0)
        self.presents.layout().setSpacing(2)
        tete.addWidget(self.presents, 0, Qt.AlignmentFlag.AlignTop)
        tete.addWidget(self.enregistrement, 0, Qt.AlignmentFlag.AlignTop)
        cv.addLayout(tete)
        self.zone_fixe = QWidget()  # bandeau de statut de Flux / Édition : ne défile pas avec la page
        zf = QVBoxLayout(self.zone_fixe)
        zf.setContentsMargins(24, 4, 24 + 16, 4)
        cv.addWidget(self.zone_fixe)
        self.pile = QStackedWidget()
        cv.addWidget(self.pile, 1)
        h.addWidget(contenu, 1)

        self.p_manips = PageManips(ctrl)
        self.p_flux = PageFlux(ctrl)
        self.p_rapport = PageRapport(ctrl)
        self.p_protocole = PageProtocole(ctrl)
        self.p_reglages = PageReglages(ctrl)
        self.p_protocoles = PageProtocoles(ctrl)
        self.p_rapports = PageRapports(ctrl)
        self.p_demandes = PageDemandes(ctrl)
        self.pages = {"manips": self.p_manips, "flux": self.p_flux, "protocoles": self.p_protocoles, "protocole": self.p_protocole,
                      "rapports": self.p_rapports, "rapport": self.p_rapport, "reglages": self.p_reglages, "demandes": self.p_demandes}
        self._bandeau()  # les bandeaux de statut entrent tout de suite dans la fenêtre (jamais de fenêtre à part)
        for k, page in self.pages.items():  # actions dans une page : reconstruction sans remonter en haut
            page.sur_place = lambda k=k: self._sur_place(k)
        self.p_protocole.flux.sur_place = lambda: self._sur_place("protocole")
        self.defilements = {}
        for k, p in self.pages.items():
            s = QScrollArea()
            s.setWidgetResizable(True)
            s.setFrameShape(QFrame.Shape.NoFrame)
            s.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)  # fenêtre étroite : défilement plutôt que colonnes coupées
            boite = QWidget()
            boite.setObjectName("page")
            bl = QVBoxLayout(boite)
            bl.setContentsMargins(24, 8, 24, 36)
            bl.addWidget(p)
            s.setWidget(boite)
            self.pile.addWidget(s)
            self.defilements[k] = s
        self.toast = Toast(self)

        # ---- signaux
        ctrl.statut.connect(self._statut)
        ctrl.toast.connect(self.toast.montrer)
        ctrl.modifie.connect(self._modifie)
        ctrl.liste_changee.connect(self._liste_changee)
        ctrl.reglages_changes.connect(self._reglages_changes)
        ctrl.conflit.connect(self._conflit)
        ctrl.retour_dossier.connect(self._retour_dossier)
        ctrl.alerte.connect(lambda t: D.informer(self, "Attention", t))
        ctrl.presence_changee.connect(self._presence)
        self.p_manips.ouvrir.connect(self.ouvrir)
        self.p_manips.nouvelle.connect(self.nouvelle)
        self.p_manips.importer.connect(self.importer)
        self.p_manips.importer_mm.connect(lambda: self.importer(mm=True))
        self.p_manips.exporter.connect(lambda i: self.autres_formats(i))
        self.p_flux.voir_rapport.connect(self._apres_flux)
        self.p_flux.voir_reglages.connect(lambda section: self.aller("reglages", section))
        self.p_flux.dupliquer.connect(self._dupliquer_ouvrir)
        f2 = self.p_protocole.flux  # éditeur du flux dans Protocole › Édition
        f2.voir_rapport.connect(self._apres_flux)
        f2.voir_reglages.connect(lambda section: self.aller("reglages", section))
        f2.dupliquer.connect(self._dupliquer_ouvrir)
        self.p_protocoles.ouvrir.connect(self.ouvrir_protocole)
        self.p_rapports.ouvrir.connect(self.ouvrir_rapport)
        self.p_rapport.exporter_pdf.connect(lambda: self.exporter_fichier("pdf"))
        self.p_rapport.exporter_word.connect(lambda: self.exporter_fichier("docx"))
        self.p_rapport.autres_formats.connect(lambda: self.autres_formats())
        self.p_protocole.exporter_pdf.connect(lambda: self.exporter_fichier("protocole"))
        self.p_protocole.ouvrir_fichier.connect(self.ouvrir_fichier)
        self.p_protocole.ouvrir_dossier.connect(lambda: self.ouvrir_fichier(str(self.dossier_documents(protocole=True))))
        self.p_demandes.ouvrir_fichier.connect(self.ouvrir_fichier)
        self.p_rapport.ouvrir_fichier.connect(self.ouvrir_fichier)
        self.p_rapport.ouvrir_dossier.connect(lambda: self.ouvrir_fichier(str(self.dossier_documents())))
        self.p_rapport.journal.connect(lambda: D.journal(self, ctrl.courante, ctrl.reglages))

        for seq, f in (("Ctrl+N", self.nouvelle), ("Ctrl+F", self._recherche), ("Ctrl+E", lambda: self.autres_formats()),
                       ("Ctrl+Z", self._annuler), ("Alt+Left", self.p_flux.precedente), ("Alt+Right", self.p_flux.suivante),
                       ("F5", ctrl.actualiser)):
            QShortcut(QKeySequence(seq), self, activated=f)

    def _nav(self, k, texte, pi, sous=False) -> QWidget:
        b = bouton("")
        b.setProperty("nav", True)
        b.setProperty("sous", sous)
        b.setAccessibleName(texte.replace("&&", "&"))
        b.setToolTip(texte.replace("&&", "&"))
        b._glyphe = ("bug.png", "image") if k == "demandes" else (ICONES[k][0], pi) if pi else (ICONES[k][1], None)
        b._textes = (texte, "")
        b.setText(b._textes[0])
        b.setIconSize(QSize(20, 20))
        b.setIcon(icone_menu(*b._glyphe, theme.P.texte))
        b.clicked.connect(lambda *_: self.aller(k))
        self.nav[k] = b
        return b

    def _nouveautes(self):
        texte = "\n\n".join(f"Version {v} — {d}\n" + "\n".join(f"  • {x}" for x in lignes) for v, d, lignes in NOUVEAUTES)
        D.informer(self, f"Nouveautés · version {VERSION} du {DATE_VERSION}", texte)

    # ------------------------------------------------------------ navigation
    def choisie(self, page: str):
        """Manip choisie dans la liste de cette section (Flux : Définition ; Édition : Protocole ; Rapport de la manip : Rapport),
        si elle y est toujours."""
        m = self.ctrl.manip(self.choix.get(page)) if self.choix.get(page) else None
        if m is None:
            return None
        if page == "protocole" and m.etat not in STATUTS_PROTOCOLE:
            return None
        if page == "rapport" and m.etat != REALISEE:
            return None
        return m

    def aller(self, page: str, section: str | None = None):
        if page in PAGES_MANIP:
            m = self.choisie(page)
            if m is None:  # une sous-section ne s'ouvre qu'après un choix dans sa liste
                return
            if self.ctrl.courante_id != m.id:
                self.ctrl.ouvrir(m.id)
                if page == "flux":
                    self.p_flux.ouvrir("comp" if m.etapes else "def")
                elif page == "protocole":
                    self.p_protocole.ouvrir()
        if page == "reglages":
            self.p_reglages.section = section  # le menu ramène aux cartes ; un lien ouvre directement la bonne carte
        self.ctrl.journaliser()
        self.page = page
        self.pile.setCurrentIndex(list(self.pages).index(page))
        self.rafraichir()
        self.defilements[page].verticalScrollBar().setValue(0)

    def ouvrir(self, ident: str, mode: str = "comp"):
        self.choix["flux"] = ident
        self.ctrl.ouvrir(ident)
        m = self.ctrl.courante
        self.p_flux.ouvrir(mode if m and m.etapes else "def")
        self.aller("flux")
        self._memoriser(ident)

    def _apres_flux(self):
        """« Étape suivante » sur la dernière étape : le rapport si la manip est réalisée, sinon l'aperçu du protocole."""
        m = self.ctrl.courante
        if m is None:
            return
        if m.etat == REALISEE:
            self.ouvrir_rapport(m.id)
        elif m.etat in STATUTS_PROTOCOLE:
            self.ouvrir_protocole(m.id)
        else:
            self.toast.montrer("Passe la manip « Validée » (bandeau du haut) pour la retrouver dans Protocole")

    def ouvrir_protocole(self, ident: str, mode: str = "apercu"):
        """Protocole › Édition de cette manip."""
        self.choix["protocole"] = ident
        self.ctrl.ouvrir(ident)
        self.p_protocole.ouvrir(mode)
        self.aller("protocole")
        self._memoriser(ident)

    def ouvrir_rapport(self, ident: str):
        self.choix["rapport"] = ident
        self.ctrl.ouvrir(ident)
        self.aller("rapport")
        self._memoriser(ident)

    def quitter_manip(self):
        """« ← » : ferme la manip en cours (dans toutes les sous-sections) et revient à la liste de la section."""
        listes = {"flux": "manips", "protocole": "protocoles", "rapport": "rapports"}
        if self.page not in listes:
            return
        ident = self.ctrl.courante_id
        for k in self.choix:  # la manip en cours est fermée partout (Flux, Édition, Rapport de la manip)
            if self.choix[k] == ident:
                self.choix[k] = None
        self.choix[self.page] = None
        self.ctrl.fermer_manip()  # enregistrée, verrou libéré, plus « ouverte » pour les autres (présence)
        self.aller(listes[self.page])

    def _memoriser(self, ident: str):
        p = self.ctrl.st.lire_preferences()
        p["derniere_manip"] = ident
        self.ctrl.st.ecrire_preferences(p)

    def rafraichir(self):
        m, ctrl = self.ctrl.courante, self.ctrl
        listes = {"flux": "manips", "protocole": "protocoles", "rapport": "rapports"}
        if self.page in PAGES_MANIP and self.choisie(self.page) is None:
            self.page = listes[self.page]  # la manip a quitté la liste de la section (statut changé, supprimée…)
            self.pile.setCurrentIndex(list(self.pages).index(self.page))
        aides = {"flux": "Choisis une manip dans Mat & Méthode", "protocole": "Ouvre un protocole dans la liste Protocole",
                 "rapport": "Ouvre un rapport dans la liste Rapport (manips réalisées)"}
        for k, b in self.nav.items():
            b.setProperty("actif", k == self.page)
            ok = k not in PAGES_MANIP or self.choisie(k) is not None
            b.setEnabled(ok)
            if k in PAGES_MANIP:
                b.setToolTip(f"{b.accessibleName()} : {self.choisie(k).nom}" if ok else aides[k])
            b.style().unpolish(b)
            b.style().polish(b)
        for b in list(self.nav.values()):
            b.setIcon(icone_menu(*b._glyphe, theme.P.texte if b.isEnabled() else theme.P.texte2))
        self._bandeau()
        self._carte()
        self.retour.setVisible(self.page in PAGES_MANIP)
        sous = self.sous_titre.layout()
        vider(sous)
        if self.page in TITRES:
            self.titre.setText(TITRES[self.page])
            self.pages[self.page].rafraichir()
        elif m is not None:
            self.titre.setText({"flux": m.nom, "protocole": f"Protocole · {m.nom}", "rapport": f"Rapport · {m.nom}"}[self.page])
            sous.addWidget(etiquette(O.nom_etat(ctrl.reglages, m.etat)[0], secondaire=True))
            if ctrl.lecture_seule:
                sous.addWidget(pastille("Lecture seule", "info"))
            sous.addStretch(1)
            self.pages[self.page].rafraichir()
        self._statut(self._texte_statut() if not ctrl.st.lecture_seule else "Non enregistré : dossier inaccessible",
                     ctrl.st.lecture_seule)

    def _presence(self):
        """Pastilles des personnes présentes (en haut à droite) ; les listes et le bandeau de la manip se mettent à jour."""
        lay = self.presents.layout()
        vider(lay)
        noms = {m.id: m.nom for m in self.ctrl.manips}
        for p in self.ctrl.presents:
            qui = self.ctrl.nom_present(p)
            ou = noms.get(p.get("manip") or "", "")
            lay.addWidget(avatar(self.ctrl.initiales_de(p.get("utilisateur", ""), p),
                                 f"{qui} ({p.get('pc', '')}) est dans l’application" + (f" · manip ouverte : {ou}" if ou else ""),
                                 cle=p.get("utilisateur", "")))
        self.presents.setVisible(bool(self.ctrl.presents))
        if self.page in ("manips", "protocoles", "rapports"):
            self.pages[self.page].rafraichir()
        elif self.page in ("flux", "protocole"):
            {"flux": self.p_flux, "protocole": self.p_protocole.flux}[self.page]._remplir_lancement()

    def _bandeau(self):
        """Montre le bandeau de statut de la page (Flux ou Protocole › Édition) dans la zone fixe. Les deux bandeaux
        restent toujours dans la fenêtre (jamais détachés : un widget sans parent deviendrait une fenêtre à part)."""
        lay = self.zone_fixe.layout()
        bandeaux = {"flux": self.p_flux.bandeau, "protocole": self.p_protocole.flux.bandeau}
        for w in bandeaux.values():
            if w.parentWidget() is not self.zone_fixe:
                lay.addWidget(w)
        voulu = bandeaux.get(self.page) if self.ctrl.courante is not None else None
        for w in bandeaux.values():
            w.setVisible(w is voulu)
        self.zone_fixe.setVisible(voulu is not None)

    def _carte(self):
        m = self.ctrl.courante
        self.carte_manip.setVisible(False)
        if m is None:
            return
        self.cm_nom.setText(m.nom)
        ne = len(m.etapes)
        self.cm_info.setText(f"{O.nom_etat(self.ctrl.reglages, m.etat)[0]} · {ne} étape{'s' if ne > 1 else ''} · "
                             f"{len(m.prelevements)} éch.")

    def _texte_statut(self) -> str:
        return self.ctrl.texte_statut(manip=self.page in PAGES_MANIP)

    def _statut(self, texte: str, erreur: bool):
        if texte.startswith("Enregistré automatiquement"):
            texte = self._texte_statut()
        self.enregistrement.setText(texte)
        self.enregistrement.setProperty("erreur", erreur)
        self.enregistrement.style().unpolish(self.enregistrement)
        self.enregistrement.style().polish(self.enregistrement)

    def _modifie(self, structure: bool):
        self._carte()
        m = self.ctrl.courante
        if structure:
            self.rafraichir_sur_place()
        elif self.page == "flux":
            self.p_flux.rafraichir(structure=False)
            if m and self.titre.text() != m.nom:
                self.titre.setText(m.nom)
        elif self.page == "protocole":
            self.p_protocole.rafraichir(structure=False)

    def _sur_place(self, page: str):
        if self.page == page:
            self.rafraichir_sur_place()
        else:
            self.pages[page].rafraichir()

    def rafraichir_sur_place(self):
        """Reconstruit la page sans la faire remonter : la hauteur du contenu est gardée pendant la reconstruction
        (sinon la barre de défilement retombe à 0), puis la position est rétablie une fois la mise en page faite."""
        zone = self.defilements[self.page]
        sb, contenu = zone.verticalScrollBar(), zone.widget()
        pos = sb.value()
        contenu.setMinimumHeight(contenu.height())
        self.rafraichir()
        essais = [0]

        def retablir():
            essais[0] += 1
            if sb.maximum() < pos and essais[0] < 10:  # mise en page pas encore terminée
                QTimer.singleShot(15, retablir)
                return
            sb.setValue(pos)
            contenu.setMinimumHeight(0)
            QTimer.singleShot(0, lambda: sb.setValue(pos))

        QTimer.singleShot(0, retablir)

    def _liste_changee(self):
        if self.page in ("manips", "protocoles", "rapports"):
            self.pages[self.page].rafraichir()
        self._carte()
        if not self.ctrl.sales:
            self._statut(self._texte_statut(), self.ctrl.st.lecture_seule)

    def _reglages_changes(self):
        if self.page == "reglages":
            return  # la page se met à jour elle-même (pas de reconstruction pendant la frappe)
        if self.page in ("rapport", "protocoles"):
            self.pages[self.page].rafraichir()
        elif self.page == "protocole" and self.p_protocole.mode != "modifier":
            self.p_protocole.rafraichir()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        etroit = self.width() < 1000  # volet replié en icônes
        self.volet.setFixedWidth(64 if etroit else LARGEUR_VOLET)
        self.carte_manip.setVisible(False)
        for b in self.nav.values():
            b.setText(b._textes[1] if etroit else b._textes[0])  # replié : icônes seules

    # ------------------------------------------------------------ actions
    def _recherche(self):
        self.aller("manips")
        self.p_manips.focus_recherche()

    def _annuler(self):
        msg = self.ctrl.annuler()
        if msg:
            self.toast.montrer(msg)
            self.rafraichir()

    def nouvelle(self):
        choix = D.nouvelle_manip(self, [(m.id, m.nom) for m in self.ctrl.manips if m.etat != ARCHIVEE])
        if choix:
            m = self.ctrl.nouvelle(*choix)
            self.toast.montrer("Manip créée")
            self.ouvrir(m.id, "def" if not m.etapes else "comp")

    def _dupliquer_ouvrir(self, ident):
        c = self.ctrl.dupliquer(ident)
        self.toast.montrer(f"Copie créée : {c.nom}")
        self.ouvrir(c.id)

    def importer(self, mm: bool = False):
        res = {}

        def traiter(data) -> str:
            try:
                m, a_verifier = importer(data, self.ctrl.reglages)
            except ImportInvalide as ex:
                return f"Import impossible : {ex}"
            except Exception as ex:
                return f"Fichier non reconnu : {ex}"
            self.ctrl.ajouter_importee(m)
            res.update(m=m, a_verifier=a_verifier, alertes=data.get("alertes", []) if isinstance(data, dict) else [])
            return ""

        if (D.importer_mm if mm else D.importer)(self, str(self.ctrl.st.d_exports), traiter):
            m = res["m"]
            self.ouvrir(m.id, "comp")
            msg = f"{len(m.etapes)} étape{'s' if len(m.etapes) > 1 else ''} importée{'s' if len(m.etapes) > 1 else ''}. Les réactifs trouvés ont été ajoutés aux Réglages."
            if res["a_verifier"]:
                msg += f" À relire : étape{'s' if len(res['a_verifier']) > 1 else ''} {', '.join(map(str, res['a_verifier']))} (plusieurs opérations détectées)."
            D.informer(self, "Manip importée", msg + " Vérifie chaque étape : l’extraction repose sur des mots-clés.")

    def dossier_documents(self, protocole: bool = False) -> Path:
        """Dossier partagé des documents : donnees\\exports\\Protocoles ou donnees\\exports\\Rapports (pas de dossier par personne)."""
        d = self.ctrl.st.d_exports / ("Protocoles" if protocole else "Rapports")
        try:
            d.mkdir(parents=True, exist_ok=True)
        except OSError:
            return self.ctrl.st.d_exports
        return d

    def exporter_fichier(self, fmt: str, ident: str | None = None):
        """fmt : pdf, docx, md, html, json, ou « protocole » (protocole de paillasse en PDF)."""
        m = self.ctrl.manip(ident) if ident else self.ctrl.courante
        if m is None:
            return
        self.ctrl.journaliser()
        self.ctrl.enregistrer_tout()
        ext = {"pdf": "PDF (*.pdf)", "protocole": "PDF (*.pdf)", "docx": "Document Word (*.docx)", "md": "Texte Markdown (*.md)",
               "html": "Page HTML (*.html)", "json": "Données JSON (*.json)"}[fmt]
        base = nom_fichier(f"{m.contexte.ref} - {m.nom}" if m.contexte.ref.strip() else m.nom)
        nom = f"{base} - Protocole.pdf" if fmt == "protocole" else f"{base}.{fmt}"
        f, _ = QFileDialog.getSaveFileName(self, "Enregistrer sous", str(self.dossier_documents(fmt == "protocole") / nom), ext)
        if not f:
            return
        try:
            data = exporter_json(m, self.ctrl.reglages)
            if fmt == "pdf":
                from mat_methode.exports.pdf import ecrire_pdf
                ecrire_pdf(data, f)
            elif fmt == "protocole":
                from mat_methode.exports.protocole import ecrire_protocole
                ecrire_protocole(data, f)
            elif fmt == "docx":
                from mat_methode.exports.word import ecrire_docx
                ecrire_docx(data, f)
            else:
                Path(f).write_text(self._contenu(m, fmt), encoding="utf-8")
        except OSError as ex:
            D.informer(self, "Export impossible", f"Le fichier n’a pas pu être écrit : {ex.strerror or ex}. Ferme-le s’il est ouvert dans Word ou un lecteur PDF.")
            return
        if fmt in ("pdf", "docx", "protocole"):  # documents émis : retrouvables depuis les onglets Rapport et Protocole
            from mat_methode.domain.models import RapportEmis, maintenant_iso
            m.rapports.append(RapportEmis(type="protocole" if fmt == "protocole" else "rapport", fmt="pdf" if fmt == "protocole" else fmt,
                                          chemin=str(f), le=maintenant_iso(), par=self.ctrl.nom_utilisateur()))
            del m.rapports[:-30]
            self.ctrl.toucher(m, structure=self.page in ("rapport", "protocole"))
        self.toast.montrer(f"Fichier enregistré : {Path(f).name}")
        if fmt in ("pdf", "docx", "protocole"):
            self.ouvrir_fichier(str(f))  # le document s'ouvre tout de suite

    def ouvrir_fichier(self, chemin: str) -> None:
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        if not Path(chemin).exists():
            self.toast.montrer("Fichier introuvable : il a été déplacé ou supprimé")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(chemin)))

    def _contenu(self, m, fmt: str) -> str:
        import json

        from mat_methode.report.html import rapport_html
        from mat_methode.report.rapport import markdown
        if fmt == "md":
            return markdown(m, self.ctrl.reglages)
        if fmt == "html":
            return rapport_html(m, self.ctrl.reglages)
        return json.dumps(exporter_json(m, self.ctrl.reglages), ensure_ascii=False, indent=2)

    def autres_formats(self, ident: str | None = None):
        m = self.ctrl.manip(ident) if ident else self.ctrl.courante
        if m is None:
            return
        self.ctrl.journaliser()
        D.exporter(self, f"Exporter · {m.nom}", lambda fmt: self._contenu(m, fmt), lambda fmt: self.exporter_fichier(fmt, m.id))

    def _conflit(self, mienne, disque):
        choix = D.conflit(self, self.ctrl.nom_de(disque.modifie_par) if disque.modifie_par else "un autre utilisateur")
        if choix == "recharger":
            self.ctrl.recharger_disque(disque)
            self.toast.montrer(f"Version de {self.ctrl.nom_de(disque.modifie_par) if disque.modifie_par else 'l’autre utilisateur'} rechargée")
        else:
            c = self.ctrl.enregistrer_comme_copie(mienne, disque)
            self.toast.montrer(f"Ta version est enregistrée : {c.nom}")
        self.rafraichir()

    def _retour_dossier(self, n: int):
        if D.confirmer(self, "Le dossier est de nouveau accessible", f"{n} élément{'s' if n > 1 else ''} en attente. Les enregistrer maintenant ?",
                       "Enregistrer", danger=False):
            self.ctrl.enregistrer_tout()
            self.ctrl.actualiser()
        self.rafraichir()

    def closeEvent(self, e):
        self.ctrl.fermer()
        p = self.ctrl.st.lire_preferences()
        p["taille"] = [self.width(), self.height()]
        self.ctrl.st.ecrire_preferences(p)
        super().closeEvent(e)


