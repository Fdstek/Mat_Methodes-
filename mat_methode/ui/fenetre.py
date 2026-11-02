"""Fenêtre principale : volet de navigation (NavigationView), en-tête avec l'état d'enregistrement,
pages Mes manips / Flux / Rapport / Réglages, raccourcis clavier (§13)."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QFontDatabase, QGuiApplication, QKeySequence, QShortcut
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

from mat_methode import NOM_APPLICATION
from mat_methode.domain import reglages_ops as O
from mat_methode.domain.models import ARCHIVEE, REALISEE
from mat_methode.domain.texte import nom_fichier
from mat_methode.exports.echange import ImportInvalide, importer
from mat_methode.exports.echange import exporter as exporter_json
from mat_methode.ui import dialogues as D
from mat_methode.ui.controleur import Controleur
from mat_methode.ui.page_flux import PageFlux
from mat_methode.ui.page_listes import PageProtocoles, PageRapports
from mat_methode.ui.page_manips import PageManips
from mat_methode.ui.page_protocole import PageProtocole
from mat_methode.ui.page_rapport import PageRapport
from mat_methode.ui.page_reglages import PageReglages
from mat_methode.ui.widgets import Toast, bouton, etiquette, pastille, vider

# Segoe Fluent Icons (Windows 11) ; repli sur des symboles simples
ICONES = {"manips": ("\ue8fd", "≡"), "flux": ("\ue8ab", "⇄"),
          "protocoles": ("\ue9d5", "☑"), "protocole": ("\ue70f", "✎"), "rapports": ("\ue8a5", "▤"), "rapport": ("\ue7c3", "▭"), "reglages": ("\ue713", "⚙")}
# Menu : (clé, libellé, sous-section ?) ; une sous-section concerne la manip ouverte.
NAV = [("manips", "Définition Mat && Méthode", False), ("flux", "Flux", True),
       ("protocoles", "Protocole", False), ("protocole", "Édition", True),
       ("rapports", "Rapport", False), ("rapport", "Rapport de la manip", True),
       ("reglages", "Réglages", False)]
PAGES_MANIP = ("flux", "protocole", "rapport")  # pages qui demandent une manip ouverte
TITRES = {"manips": "Définition Mat & Méthode", "protocoles": "Protocole", "rapports": "Rapport", "reglages": "Réglages"}


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
        racine = QWidget()
        racine.setObjectName("racine")
        h = QHBoxLayout(racine)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        self.setCentralWidget(racine)

        # ---- volet de navigation
        self.volet = QWidget()
        self.volet.setObjectName("volet")
        self.volet.setFixedWidth(272)
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
        v.addSpacing(8)
        self.nav = {}
        pi = police_icones()
        for k, t, sous in NAV:
            v.addWidget(self._nav(k, t, pi, sous))
        v.addStretch(1)
        h.addWidget(self.volet)

        # ---- contenu
        contenu = QWidget()
        cv = QVBoxLayout(contenu)
        cv.setContentsMargins(0, 0, 0, 0)
        cv.setSpacing(0)
        tete = QHBoxLayout()
        tete.setContentsMargins(36, 22, 36, 6)
        titres = QVBoxLayout()
        self.titre = etiquette("", "titrePage", wrap=True)
        self.sous_titre = QWidget()
        QHBoxLayout(self.sous_titre).setContentsMargins(0, 0, 0, 0)
        titres.addWidget(self.titre)
        titres.addWidget(self.sous_titre)
        tete.addLayout(titres, 1)
        self.enregistrement = etiquette("", "enregistrement")
        self.enregistrement.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
        self.enregistrement.setAccessibleName("État de l’enregistrement")
        tete.addWidget(self.enregistrement, 0, Qt.AlignmentFlag.AlignTop)
        cv.addLayout(tete)
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
        self.pages = {"manips": self.p_manips, "flux": self.p_flux, "protocoles": self.p_protocoles, "protocole": self.p_protocole,
                      "rapports": self.p_rapports, "rapport": self.p_rapport, "reglages": self.p_reglages}
        self.defilements = {}
        for k, p in self.pages.items():
            s = QScrollArea()
            s.setWidgetResizable(True)
            s.setFrameShape(QFrame.Shape.NoFrame)
            s.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff if k in ("manips", "protocoles", "rapports") else Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            boite = QWidget()
            boite.setObjectName("page")
            bl = QVBoxLayout(boite)
            bl.setContentsMargins(36, 8, 36, 36)
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
        self.p_manips.ouvrir.connect(self.ouvrir)
        self.p_manips.nouvelle.connect(self.nouvelle)
        self.p_manips.importer.connect(self.importer)
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
        self.p_protocole.ouvrir_dossier.connect(lambda: self.ouvrir_fichier(str(self.dossier_rapports())))
        self.p_rapport.ouvrir_fichier.connect(self.ouvrir_fichier)
        self.p_rapport.ouvrir_dossier.connect(lambda: self.ouvrir_fichier(str(self.dossier_rapports())))
        self.p_rapport.journal.connect(lambda: D.journal(self, ctrl.courante))

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
        icone = ICONES[k][0] if pi else ICONES[k][1]
        b._textes = (f"{icone}    {texte}", icone)
        b.setText(b._textes[0])
        if pi:
            f = QFont(b.font())
            b.setFont(f)
        b.clicked.connect(lambda *_: self.aller(k))
        self.nav[k] = b
        return b

    # ------------------------------------------------------------ navigation
    def aller(self, page: str, section: str | None = None):
        if page in PAGES_MANIP and self.ctrl.courante is None:
            return
        if page == "rapport" and self.ctrl.courante.etat != REALISEE:
            self.toast.montrer("Le rapport est disponible quand le protocole est « Réalisée » (Protocole)")
            return
        if page == "reglages":
            self.p_reglages.section = section  # le menu ramène aux cartes ; un lien ouvre directement la bonne carte
        self.ctrl.journaliser()
        self.page = page
        self.pile.setCurrentIndex(list(self.pages).index(page))
        self.rafraichir()
        self.defilements[page].verticalScrollBar().setValue(0)

    def ouvrir(self, ident: str, mode: str = "comp"):
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
            self.aller("rapport")
        else:
            self.ouvrir_protocole(m.id)

    def ouvrir_protocole(self, ident: str, mode: str = "apercu"):
        """Protocole › Édition de cette manip."""
        self.ctrl.ouvrir(ident)
        self.p_protocole.ouvrir(mode)
        self.aller("protocole")
        self._memoriser(ident)

    def ouvrir_rapport(self, ident: str):
        self.ctrl.ouvrir(ident)
        self.aller("rapport")
        self._memoriser(ident)

    def _memoriser(self, ident: str):
        p = self.ctrl.st.lire_preferences()
        p["derniere_manip"] = ident
        self.ctrl.st.ecrire_preferences(p)

    def rafraichir(self):
        m, ctrl = self.ctrl.courante, self.ctrl
        if self.page == "rapport" and (m is None or m.etat != REALISEE):
            self.page = "rapports"  # plus de rapport tant que le protocole n'est pas réalisé
            self.pile.setCurrentIndex(list(self.pages).index("rapports"))
        for k, b in self.nav.items():
            b.setProperty("actif", k == self.page)
            b.setEnabled(k not in PAGES_MANIP or (m is not None and (k != "rapport" or m.etat == REALISEE)))
            if k == "rapport":
                b.setToolTip("Rapport de la manip ouverte" if b.isEnabled() else "Disponible quand le protocole de la manip est « Réalisée »")
            b.style().unpolish(b)
            b.style().polish(b)
        self._carte()
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

    def _carte(self):
        m = self.ctrl.courante
        self.carte_manip.setVisible(m is not None)
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
            pos = self.defilements[self.page].verticalScrollBar().value()
            self.rafraichir()
            QTimer.singleShot(0, lambda: self.defilements[self.page].verticalScrollBar().setValue(pos))
        elif self.page == "flux":
            self.p_flux.rafraichir(structure=False)
            if m and self.titre.text() != m.nom:
                self.titre.setText(m.nom)
        elif self.page == "protocole":
            self.p_protocole.rafraichir(structure=False)

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
        self.volet.setFixedWidth(64 if etroit else 272)
        self.carte_manip.setVisible(not etroit and self.ctrl.courante is not None)
        for b in self.nav.values():
            b.setText(b._textes[1] if etroit else b._textes[0])

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

    def importer(self):
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

        if D.importer(self, str(self.ctrl.st.d_exports), traiter):
            m = res["m"]
            self.ouvrir(m.id, "comp")
            msg = f"{len(m.etapes)} étape{'s' if len(m.etapes) > 1 else ''} importée{'s' if len(m.etapes) > 1 else ''}. Les réactifs trouvés ont été ajoutés aux Réglages."
            if res["a_verifier"]:
                msg += f" À relire : étape{'s' if len(res['a_verifier']) > 1 else ''} {', '.join(map(str, res['a_verifier']))} (plusieurs opérations détectées)."
            D.informer(self, "Manip importée", msg + " Vérifie chaque étape : l’extraction repose sur des mots-clés.")

    def dossier_rapports(self) -> Path:
        """Dossier des documents de la personne qui édite : donnees\\exports\\<Prénom NOM>."""
        d = self.ctrl.st.d_exports / nom_fichier(self.ctrl.nom_utilisateur())
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
        f, _ = QFileDialog.getSaveFileName(self, "Enregistrer sous", str(self.dossier_rapports() / nom), ext)
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


