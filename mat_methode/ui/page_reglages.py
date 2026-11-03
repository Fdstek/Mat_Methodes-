"""Page « Réglages » (§6.5, maquette W05) : valables pour toutes les manips, partagés par tous."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QGridLayout, QVBoxLayout, QWidget

from mat_methode import NOM_APPLICATION, VERSION
from mat_methode.domain import reglages_ops as O
from mat_methode.domain.models import Personne, initiales_de
from mat_methode.domain.regles import basculer_analyse, deplacer_tag, tous_les_tags
from mat_methode.domain.texte import libelle_volume, norm
from mat_methode.ui.controleur import Controleur
from mat_methode.ui.dialogues import confirmer
from mat_methode.ui.widgets import (
    ChampTexte,
    ChipSupprimable,
    ChoixVolume,
    Expander,
    NumberBox,
    bouton,
    champ,
    etiquette,
    flux_widgets,
    icone,
    ligne,
    pastille,
    vider,
)


class PageReglages(QWidget):

    def _actualiser(self):
        """Reconstruit la page sans la faire remonter (position gardée par la fenêtre)."""
        f = getattr(self, "sur_place", None)
        f() if f else self.rafraichir()
    def __init__(self, ctrl: Controleur):
        super().__init__()
        self.ctrl = ctrl
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(0, 0, 0, 0)
        self.lay.setSpacing(12)
        self.section: str | None = None  # carte ouverte (None = toutes les cartes)

    @property
    def r(self):
        return self.ctrl.reglages

    def _changer(self, manips=()):
        for m in manips:
            self.ctrl.toucher(m)
        self.ctrl.toucher_reglages()

    def _section(self, titre: str, note: str = "") -> Expander:
        x = Expander(titre, note, ouvert=True)
        x.tete.clicked.disconnect(x.basculer)  # une seule section à la fois : pas de repli
        x.tete.setCursor(Qt.CursorShape.ArrowCursor)
        self.lay.addWidget(x)
        return x

    def sections(self) -> list[tuple[str, str, str, str, object]]:
        """(clé, titre, description, compteur, fonction) de chaque carte de la page Réglages."""
        r = self.r
        return [
            ("personnes", "Personnes", "Donneurs d’ordre : nom, initiales (références), IGG", f"{len(r.personnes)}", self._personnes),
            ("laboratoires", "Laboratoires", "Volume par défaut et analyses de chaque labo", f"{len(r.laboratoires)}", self._laboratoires),
            ("operations", "Opérations", "Sous-étapes du flux (chauffage, filtration…) et texte", f"{len(r.operations)}", self._operations),
            ("materiel", "Matériel", "Matériel proposé dans les étapes (plaque chauffante, étuve…)", f"{len(r.materiels)}", self._materiel),
            ("reactifs", "Réactifs", "Noms des réactifs proposés dans les étapes", f"{len(r.reactifs)}", self._reactifs),
            ("volumes", "Volumes d’échantillon", "30 mL … 1 L", f"{len(r.volumes_ml)}", self._volumes),
            ("analyses", "Analyses", "Analyses disponibles pour les laboratoires", f"{len(r.analyses)}", self._analyses),
            ("types", "Types de demande", "Support, R&D, Test d’idée…", f"{len(r.types_demande)}", self._types),
            ("grandes", "Grandes étapes", "Degumming, Neutralisation…", f"{len(r.grandes_etapes)}", self._grandes),
            ("a_faire", "Catégories « À faire »", "Réflexion, Matériel manquant, Réactif manquant…",
             f"{len(r.categories_a_faire)}", self._categories),
            ("tags", "Tags", "Ajouter, renommer, retirer, ordre et couleur des tags", f"{len(tous_les_tags(self.ctrl.manips))}", self._tags),
            ("scirius", "Fichier Scirius", "Lien avec le suivi des enregistrements Scirius (SharePoint)",
             "choisi" if r.scirius_fichier else "auto", self._scirius),
        ]

    def ouvrir(self, cle: str | None):
        self.section = cle
        self.rafraichir()

    def rafraichir(self, *_):
        vider(self.lay)
        sec = getattr(self, "section", None)
        lecture_seule = self.ctrl.st.lecture_seule
        if sec is None:
            self.lay.addWidget(etiquette("Réglages de base de l’application, partagés avec les autres utilisateurs du dossier. "
                                         "Clique une carte pour l’ouvrir ; ◂ ▸ changent l’ordre des cartes (pour toi seulement).", secondaire=True, wrap=True))
            grille = QGridLayout()
            grille.setSpacing(12)
            cartes = self._sections_ordonnees()
            for k, (cle, titre, desc, compte, _) in enumerate(cartes):
                grille.addWidget(self._carte(cle, titre, desc, compte, k, len(cartes)), k // 3, k % 3)
            for c in range(3):
                grille.setColumnStretch(c, 1)
            w = QWidget()
            w.setLayout(grille)
            self.lay.addWidget(w)
            a = etiquette(f"{NOM_APPLICATION} · version {VERSION} · vous : {self.ctrl.nom_utilisateur()} (IGG {self.ctrl.st.utilisateur}) · "
                          f"données : {self.ctrl.st.donnees}", secondaire=True, wrap=True)
            a.setAccessibleName("À propos")
            self.lay.addWidget(a)
            self.lay.addStretch(1)
            return
        self.lay.addWidget(ligne(bouton("←  Tous les réglages", lambda: self.ouvrir(None)), "stretch"))
        dict((c, f) for c, _, _, _, f in self.sections())[sec]()
        self.lay.addStretch(1)
        for i in range(self.lay.count()):
            w = self.lay.itemAt(i).widget()
            if isinstance(w, Expander):
                w.corps.setEnabled(not lecture_seule)

    def _sections_ordonnees(self) -> list:
        """Cartes dans l'ordre choisi par la personne (préférences), les nouvelles à la fin."""
        ordre = self.ctrl.st.lire_preferences().get("ordre_reglages") or []
        rang = {c: k for k, c in enumerate(ordre)}
        return sorted(self.sections(), key=lambda x: rang.get(x[0], len(rang)))

    def _deplacer_carte(self, cle: str, sens: int):
        cles = [x[0] for x in self._sections_ordonnees()]
        i = cles.index(cle)
        j = i + sens
        if not 0 <= j < len(cles):
            return
        cles[i], cles[j] = cles[j], cles[i]
        p = self.ctrl.st.lire_preferences()
        p["ordre_reglages"] = cles
        self.ctrl.st.ecrire_preferences(p)
        self._actualiser()

    def _carte(self, cle, titre, desc, compte, k: int = 0, n: int = 1) -> QWidget:
        f = QFrame()
        f.setObjectName("carteFlux")
        f.setCursor(Qt.CursorShape.PointingHandCursor)
        f.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        f.setAccessibleName(f"Réglages : {titre}")
        v = QVBoxLayout(f)
        v.setContentsMargins(16, 14, 16, 14)
        v.addWidget(ligne(etiquette(titre, "titreCarte"), "stretch", pastille(compte)))
        v.addWidget(etiquette(desc, secondaire=True, wrap=True))
        avant = icone("◂", f"Placer « {titre} » avant", lambda: self._deplacer_carte(cle, -1))
        avant.setEnabled(k > 0)
        apres = icone("▸", f"Placer « {titre} » après", lambda: self._deplacer_carte(cle, 1))
        apres.setEnabled(k < n - 1)
        v.addWidget(ligne("stretch", avant, apres))
        f.mousePressEvent = lambda _e: self.ouvrir(cle)
        f.keyPressEvent = lambda ev: self.ouvrir(cle) if ev.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space) else None
        f.setMinimumHeight(96)
        return f

    def _reactifs(self):
        self._liste_simple("Réactifs", [x.nom for x in self.r.reactifs], self._suppr_reactif, self._ajout_reactif, "Nouveau réactif",
                           "Seul le nom se règle ici. Le n° Scirius, l’emplacement et le fournisseur se renseignent dans l’étape "
                           "(ou depuis Scirius) et sont gardés pour la prochaine fois. On peut aussi ajouter un réactif depuis une étape.",
                           renommer=self._ren(O.renommer_reactif, lambda: [x.nom for x in self.r.reactifs]), ordre=self.r.reactifs)

    def _analyses(self):
        self._liste_simple("Analyses disponibles", self.r.analyses, self._suppr_analyse,
                           lambda v: O.ajouter_analyse(self.r, v), "Nouvelle analyse",
                           renommer=self._ren(O.renommer_analyse, lambda: self.r.analyses))

    def _types(self):
        self._liste_simple("Types de demande", self.r.types_demande, lambda v: self.r.types_demande.remove(v),
                           lambda v: O.ajouter_simple(self.r.types_demande, v), "Nouveau type",
                           "Dans une manip, on choisit seulement dans cette liste. « Idée testée » apparaît pour un type contenant « test ». ● change la couleur du type (tableaux).",
                           renommer=self._ren(O.renommer_type, lambda: self.r.types_demande),
                           couleur=lambda t: O.couleur_type(self.r, t), changer_couleur=lambda t: O.couleur_type_suivante(self.r, t))

    def _materiel(self):
        self._liste_simple("Matériel", self.r.materiels, lambda v: self.r.materiels.remove(v),
                           lambda v: O.ajouter_simple(self.r.materiels, v), "Nouveau matériel",
                           "Proposé dans « Matériel utilisé » de chaque étape. Un matériel tapé à la main dans une étape est ajouté ici. "
                           "✎ renomme aussi dans les étapes de toutes les manips ; ✕ ne touche pas les étapes existantes.",
                           renommer=self._ren(O.renommer_materiel, lambda: self.r.materiels))

    def _categories(self):
        self._liste_simple("Catégories « À faire »", self.r.categories_a_faire, lambda v: self.r.categories_a_faire.remove(v),
                           lambda v: O.ajouter_simple(self.r.categories_a_faire, v), "Nouvelle catégorie",
                           "Catégories proposées pour la liste « À faire » de chaque manip (carte sous « Ma demande »).")

    def _grandes(self):
        self._liste_simple("Grandes étapes", self.r.grandes_etapes, lambda v: self.r.grandes_etapes.remove(v),
                           lambda v: O.ajouter_simple(self.r.grandes_etapes, v), "Nouvelle grande étape",
                           "Noms proposés pour regrouper des étapes du flux (ex. Degumming : chauffage, ajout d’acide, centrifugation…).",
                           renommer=self._ren(O.renommer_grande_etape, lambda: self.r.grandes_etapes))

    # ------------------------------------------------------------ personnes (donneurs d'ordre)
    def _personnes(self):
        x = self._section("Personnes (donneurs d’ordre)", f"{len(self.r.personnes)}")
        x.ajouter(etiquette("Les donneurs d’ordre proposés dans « Ma demande ». Les initiales forment la référence des manips "
                            "(ex. PB-2026-10-31-01). L’IGG (identifiant Windows) permet de reconnaître la personne connectée : "
                            f"sur ce poste, l’IGG est {self.ctrl.st.utilisateur}.", secondaire=True, wrap=True))
        n_p = len(self.r.personnes)
        for i, p in enumerate(self.r.personnes):
            nom = ChampTexte(p.nom)
            nom.editingFinished.connect(lambda nom=nom, p=p: self._renommer_personne(p, nom.text()))
            ini = ChampTexte(p.initiales, initiales_de(p.nom), mono=True)
            ini.setMaximumWidth(90)
            ini.modifie.connect(lambda v, p=p: (setattr(p, "initiales", v.strip().upper()), self.ctrl.toucher_reglages()))
            igg = ChampTexte(p.igg, "ex. J0123456", mono=True)
            igg.setMaximumWidth(160)
            igg.modifie.connect(lambda v, p=p: (setattr(p, "igg", v.strip().upper()), self.ctrl.toucher_reglages()))
            nb = sum(1 for m in self.ctrl.manips if m.contexte.donneur == p.nom)
            moi = pastille("c’est vous", "ok") if p.igg and p.igg.upper() == self.ctrl.st.utilisateur else None
            x.ajouter(ligne(champ("Prénom NOM", nom), champ("Initiales", ini), champ("IGG", igg),
                            etiquette(f"{nb} manip{'s' if nb > 1 else ''}", secondaire=True), *( [moi] if moi else []), "stretch",
                            *self._fleches(self.r.personnes, i, n_p, p.nom),
                            icone("✕", f"Supprimer {p.nom}", lambda p=p: self._suppr_personne(p), danger=True)))
        nouveau = ChampTexte("", "ex. Pierre BURGUN")
        nigg = ChampTexte("", "IGG (facultatif)", mono=True)
        nigg.setMaximumWidth(160)

        def ajout():
            nom = nouveau.text().strip()
            if not nom or self.r.personne(nom):
                return
            self.r.personnes.append(Personne(nom=nom, initiales=initiales_de(nom), igg=nigg.text().strip().upper()))
            self._changer()
            self._actualiser()

        nouveau.returnPressed.connect(ajout)
        nigg.returnPressed.connect(ajout)
        moi = bouton("Me remplir (IGG de ce poste)", lambda: nigg.setText(self.ctrl.st.utilisateur), lien=True)
        x.ajouter(ligne(champ("Nouvelle personne", nouveau), champ("IGG", nigg), bouton("Ajouter", ajout), moi, "stretch"))

    def _fleches(self, liste: list, i: int, n: int, nom: str) -> list:
        """↑ ↓ pour changer l'ordre d'une ligne (personnes, laboratoires)."""
        haut = icone("↑", f"Monter {nom}", lambda: self._deplacer(liste, i, -1))
        haut.setEnabled(i > 0)
        bas = icone("↓", f"Descendre {nom}", lambda: self._deplacer(liste, i, 1))
        bas.setEnabled(i < n - 1)
        return [haut, bas]

    def _renommer_personne(self, p, nouveau):
        nouveau = nouveau.strip()
        if not nouveau or nouveau == p.nom:
            return
        ch = O.renommer_donneur(self.r, self.ctrl.manips, p.nom, nouveau)
        if p.nom != nouveau:
            self.ctrl.toast.emit("Impossible : cette personne existe déjà")
            self._actualiser()
            return
        self._changer(ch)
        self.ctrl.toast.emit(f"Renommée ({len(ch)} manip{'s' if len(ch) > 1 else ''} mise{'s' if len(ch) > 1 else ''} à jour)")

    def _suppr_personne(self, p):
        if confirmer(self, "Retirer cette personne ?", f"« {p.nom} » ne sera plus proposée comme donneur d’ordre. "
                     "Les manips existantes gardent ce nom.", "Retirer"):
            self.r.personnes = [x for x in self.r.personnes if x is not p]
            self._changer()
            self._actualiser()

    # ------------------------------------------------------------ fichier Scirius
    def _scirius(self):
        from mat_methode import scirius as S
        x = self._section("Fichier Scirius")
        x.ajouter(etiquette(f"Le fichier « {S.FICHIER} » (SharePoint du magasin) sert à remplir la charge de départ et les réactifs. "
                            "Il est cherché automatiquement : dans tes dossiers OneDrive / SharePoint synchronisés, puis ouvert par Excel "
                            "depuis SharePoint, puis la dernière copie partagée. Tu peux aussi choisir un fichier ici.",
                            secondaire=True, wrap=True))
        chemin = ChampTexte(self.r.scirius_fichier, "automatique")
        chemin.setReadOnly(True)

        def parcourir():
            from PySide6.QtWidgets import QFileDialog
            f, _ = QFileDialog.getOpenFileName(self, "Choisir le fichier Scirius", "", "Classeur Excel (*.xlsx *.xlsm)")
            if f:
                self.r.scirius_fichier = f
                self._changer()
                self._actualiser()

        def auto():
            self.r.scirius_fichier = ""
            self._changer()
            self._actualiser()

        resultat = etiquette("", secondaire=True, wrap=True)

        def tester():
            from PySide6.QtWidgets import QApplication
            resultat.setText("Lecture en cours…")
            QApplication.processEvents()
            lu = self.ctrl.lire_scirius(True, lambda t: (resultat.setText(t), QApplication.processEvents()))
            resultat.setText(f"{len(lu.lignes)} lignes lues · {lu.origine}" if lu.lignes else
                             "Fichier introuvable ou illisible : " + (" | ".join(lu.ecartes[:3]) or "aucune source"))

        x.ajouter(ligne(champ("Fichier choisi", chemin), bouton("Parcourir…", parcourir), bouton("Automatique", auto),
                        bouton("Tester la lecture", tester, accent=True), "stretch"))
        x.ajouter(resultat)
        x.ajouter(etiquette("Noms des destinataires affichés par défaut dans la recherche (format Scirius, ex. P.BURGUN). "
                            "Une case dans la fenêtre de recherche permet de tout afficher.", secondaire=True, wrap=True))
        x.ajouter(flux_widgets([ChipSupprimable(n, lambda n=n: (self.r.scirius_noms.remove(n), self._changer(), self._actualiser()),
                                                f"Retirer {n}") for n in self.r.scirius_noms]) if self.r.scirius_noms
                  else etiquette("Aucun : toutes les lignes sont affichées", secondaire=True))
        nom = ChampTexte("", "ex. P.BURGUN")

        def ajout_nom():
            v = nom.text().strip().upper().replace(" ", "")
            if v and v not in self.r.scirius_noms:
                self.r.scirius_noms.append(v)
                self._changer()
                self._actualiser()

        nom.returnPressed.connect(ajout_nom)
        x.ajouter(ligne(champ("Nouveau nom", nom), bouton("Ajouter", ajout_nom), "stretch"))

    # ------------------------------------------------------------ opérations (sous-étapes)
    def _operations(self):
        ops = self.r.operations
        x = self._section("Opérations (sous-étapes du flux)", f"{len(ops)}")
        x.ajouter(etiquette("Les boutons proposés dans « Définir le flux ». Le participe passé sert au texte : « Étape 2 : il a ensuite été "
                            "filtré… ». Renommer une opération met à jour les étapes de toutes les manips ; la supprimer de la liste "
                            "ne touche pas les étapes existantes.", secondaire=True, wrap=True))
        n = len(ops)
        for i, o in enumerate(ops):
            nom = ChampTexte(o.nom)
            nom.editingFinished.connect(lambda nom=nom, o=o: self._renommer_operation(o, nom.text()))
            part = ChampTexte(o.participe, f"ex. {o.nom[:-3] + 'é' if o.nom.endswith('age') else 'traité'}")
            part.modifie.connect(lambda v, o=o: (setattr(o, "participe", v), self.ctrl.toucher_reglages()))
            nb = sum(1 for m in self.ctrl.manips for e in m.etapes if norm(e.operation) == norm(o.nom))
            haut = icone("↑", f"Monter {o.nom}", lambda i=i: (O.deplacer_operation(self.r, i, -1), self._changer(), self._actualiser()))
            haut.setEnabled(i > 0)
            bas = icone("↓", f"Descendre {o.nom}", lambda i=i: (O.deplacer_operation(self.r, i, 1), self._changer(), self._actualiser()))
            bas.setEnabled(i < n - 1)
            x.ajouter(ligne(champ("Opération", nom), champ("Participe passé (texte)", part),
                            etiquette(f"{nb} étape{'s' if nb > 1 else ''}", secondaire=True), "stretch", haut, bas,
                            icone("✕", f"Supprimer {o.nom}", lambda o=o: self._suppr_operation(o), danger=True)))
        nouveau = ChampTexte("", "ex. neutralisation")
        npart = ChampTexte("", "ex. neutralisé")

        def ajout():
            if O.ajouter_operation(self.r, nouveau.text(), npart.text()):
                self._changer()
                self._actualiser()
            elif nouveau.text().strip():
                self.ctrl.toast.emit("Cette opération existe déjà")

        nouveau.returnPressed.connect(ajout)
        npart.returnPressed.connect(ajout)
        x.ajouter(ligne(champ("Nouvelle opération", nouveau), champ("Participe passé", npart), bouton("Ajouter", ajout), "stretch"))

    def _volumes(self):
        vs = self.r.volumes_ml
        x = self._section("Volumes d’échantillon", f"{len(vs)}")
        x.ajouter(etiquette("Volumes proposés pour chaque échantillon et pour le volume par défaut des laboratoires. "
                            "Retirer un volume ne change pas les échantillons existants.", secondaire=True, wrap=True))
        x.ajouter(flux_widgets([ChipSupprimable(libelle_volume(v), lambda v=v: (O.supprimer_volume(self.r, v), self._changer(), self._actualiser()),
                                                f"Retirer {libelle_volume(v)}") for v in vs]) if vs else etiquette("Aucun", secondaire=True))
        nouveau = NumberBox(None, "mL", "ex. 1000 pour 1 L")
        nouveau.setMaximumWidth(200)

        def ajout():
            if O.ajouter_volume(self.r, nouveau.lire()):
                self._changer()
                self._actualiser()

        nouveau.returnPressed.connect(ajout)
        x.ajouter(ligne(champ("Nouveau volume", nouveau), bouton("Ajouter", ajout), "stretch"))

    def _renommer_operation(self, o, nouveau):
        nouveau = nouveau.strip()
        if not nouveau or nouveau == o.nom:
            return
        ancien = o.nom
        ch = O.renommer_operation(self.r, self.ctrl.manips, ancien, nouveau)
        if o.nom == ancien:
            self.ctrl.toast.emit("Impossible : cette opération existe déjà")
            self._actualiser()
            return
        self._changer(ch)
        self.ctrl.toast.emit(f"Opération renommée ({len(ch)} manip{'s' if len(ch) > 1 else ''} mise{'s' if len(ch) > 1 else ''} à jour)")

    def _suppr_operation(self, o):
        if confirmer(self, "Retirer cette opération ?", f"« {o.nom} » ne sera plus proposée dans « Définir le flux ». "
                     "Les étapes existantes qui l’utilisent ne changent pas.", "Retirer"):
            O.supprimer_operation(self.r, o.nom)
            self._changer()
            self._actualiser()

    # ------------------------------------------------------------ laboratoires
    def _laboratoires(self):
        x = self._section("Laboratoires", f"{len(self.r.laboratoires)}")
        x.ajouter(etiquette("Pour chaque laboratoire : le volume à prélever et les analyses qu’il réalise. Choisir ce laboratoire pour un échantillon "
                            "n’affiche que ces analyses (toutes cochées au départ) ; "
                            "on peut toujours les changer échantillon par échantillon.", secondaire=True, wrap=True))
        tous = [p for m in self.ctrl.manips for p in m.prelevements]
        n_l = len(self.r.laboratoires)
        for i, lab in enumerate(self.r.laboratoires):
            f = QFrame()
            f.setObjectName("sousCarte")
            v = QVBoxLayout(f)
            v.setContentsMargins(12, 10, 12, 10)
            n = sum(1 for p in tous if p.labo == lab.nom)
            nom = ChampTexte(lab.nom)
            nom.editingFinished.connect(lambda nom=nom, lab=lab: self._renommer_labo(lab.nom, nom.text()))
            vol = ChoixVolume(self.r.volumes_ml, lab.volume_ml)
            vol.choisi.connect(lambda val, lab=lab: (setattr(lab, "volume_ml", val), self.ctrl.toucher_reglages()))
            v.addWidget(ligne(champ("Nom du laboratoire", nom), champ("Volume par échantillon", vol), "stretch",
                              etiquette(f"utilisé dans {n} échantillon{'s' if n > 1 else ''}", secondaire=True),
                              *self._fleches(self.r.laboratoires, i, n_l, lab.nom),
                              icone("✕", f"Supprimer {lab.nom}", lambda lab=lab: self._suppr_labo(lab.nom), danger=True)))
            an = []
            for a in self.r.analyses:
                b = bouton(a, lambda lab=lab, a=a: (setattr(lab, "analyses", basculer_analyse(lab.analyses, a)), self.ctrl.toucher_reglages()))
                b.setProperty("chip", True)
                b.setCheckable(True)
                b.setChecked(a in lab.analyses)
                an.append(b)
            v.addWidget(champ("Analyses possibles (proposées et cochées sur un nouvel échantillon)", flux_widgets(an)))
            x.ajouter(f)
        nouveau = ChampTexte("", "Nouveau laboratoire")
        ajout = lambda: O.ajouter_laboratoire(self.r, nouveau.text()) and (self._changer(), self._actualiser())
        nouveau.returnPressed.connect(ajout)
        x.ajouter(ligne(champ("Nouveau laboratoire", nouveau), bouton("Ajouter", ajout), "stretch"))

    def _renommer_labo(self, ancien, nouveau):
        nouveau = nouveau.strip()
        if nouveau == ancien or not nouveau:
            return
        ch = O.renommer_laboratoire(self.r, self.ctrl.manips, ancien, nouveau)
        self._changer(ch)
        self.ctrl.toast.emit(f"Laboratoire renommé ({len(ch)} manip{'s' if len(ch) > 1 else ''} mise{'s' if len(ch) > 1 else ''} à jour)")

    def _suppr_labo(self, nom):
        if confirmer(self, "Supprimer ce laboratoire ?", f"« {nom} » disparaît de la liste. Les échantillons existants gardent ce nom.", "Supprimer"):
            O.supprimer_laboratoire(self.r, nom)
            self._changer()
            self._actualiser()

    # ------------------------------------------------------------ listes simples
    def _liste_simple(self, titre, items, supprimer, ajouter, libelle, aide="", renommer=None, ordre: list | None = None,
                      couleur=None, changer_couleur=None):
        """`ordre` : la liste des Réglages à réordonner (◂ ▸) ; par défaut `items` lui-même."""
        ordre = items if ordre is None else ordre
        x = self._section(titre, f"{len(items)}")
        x.ajouter(etiquette((aide + " " if aide else "") + "◂ ▸ : changer l’ordre (c’est l’ordre des listes déroulantes).",
                            secondaire=True, wrap=True))
        n = len(items)
        x.ajouter(flux_widgets([ChipSupprimable(a, lambda a=a: (supprimer(a), self._changer(), self._actualiser()), f"Supprimer {a}",
                                                renommer=(lambda a=a: self._renommer(titre, a, renommer)) if renommer else None,
                                                deplacer=lambda sens, i=i: self._deplacer(ordre, i, sens), bornes=(i == 0, i == n - 1),
                                                couleur=couleur(a) if couleur else None,
                                                changer_couleur=(lambda a=a: (changer_couleur(a), self._changer(), self._actualiser()))
                                                if changer_couleur else None)
                                for i, a in enumerate(items)]) if items else etiquette("Aucun pour l’instant", secondaire=True))
        nouveau = ChampTexte("", libelle)

        def ajout():
            if ajouter(nouveau.text()):
                self._changer()
                self._actualiser()

        nouveau.returnPressed.connect(ajout)
        x.ajouter(ligne(champ(libelle, nouveau), bouton("Ajouter", ajout), "stretch"))

    def _deplacer(self, liste: list, i: int, sens: int) -> None:
        if O.deplacer_dans(liste, i, sens):
            self._changer()
            self._actualiser()

    def _renommer(self, titre: str, ancien: str, fn, tag=False) -> None:
        """Renomme une entrée et met à jour toutes les manips qui l'utilisent."""
        from mat_methode.ui.dialogues import demander_texte
        nouveau = demander_texte(self, f"Renommer « {ancien} »", "Nouveau nom", ancien,
                                 f"{titre} : toutes les manips qui utilisent « {ancien} » seront mises à jour.")
        if not nouveau or nouveau == ancien:
            return
        ch = fn(ancien, nouveau)
        if ch is None:
            self.ctrl.toast.emit("Impossible : ce nom existe déjà")
            return
        for m in ch:
            self.ctrl.toucher(m)
        if not tag:
            self.ctrl.toucher_reglages()
        n = len(ch)
        self.ctrl.toast.emit(f"Renommé en « {nouveau} »" + (f" ({n} manip{'s' if n > 1 else ''} mise{'s' if n > 1 else ''} à jour)" if n else ""))
        self._actualiser()

    def _ren(self, fn, liste_apres):
        """Adapte une fonction de reglages_ops : None si le renommage a été refusé."""
        def f(a, b):
            ch = fn(self.r, self.ctrl.manips, a, b)
            return ch if b.strip() in liste_apres() or ch else None
        return f

    def _ajout_reactif(self, v):
        return O.ajouter_reactif(self.r, v)

    def _suppr_reactif(self, nom):
        if O.reactif_a_des_infos(self.r, nom) and not confirmer(
                self, "Supprimer ce réactif ?", f"Le n° Scirius, l’emplacement et le fournisseur mémorisés pour « {nom} » seront aussi effacés.",
                "Supprimer"):
            return
        O.supprimer_reactif(self.r, nom)

    def _suppr_analyse(self, nom):
        O.supprimer_analyse(self.r, nom)

    # ------------------------------------------------------------ tags
    def _tags(self):
        ts = tous_les_tags(self.ctrl.manips, self.r.ordre_tags)
        x = self._section("Tags utilisés", f"{len(ts)}")
        x.ajouter(etiquette("Les tags se créent dans la manip (carte « Ma demande »). Ici, on peut en renommer (✎) ou en retirer (✕) un "
                            "dans toutes les manips, changer leur ordre (◂ ▸ : c’est l’ordre des listes déroulantes) et leur couleur (●).",
                            secondaire=True, wrap=True))
        chips = []
        n = len(ts)
        for i, t in enumerate(ts):
            nb = sum(1 for m in self.ctrl.manips if any(norm(y) == norm(t) for y in m.tags))
            chips.append(ChipSupprimable(f"#{t}  {nb}", lambda t=t: self._retirer_tag(t), f"Retirer {t} de toutes les manips",
                                         renommer=lambda t=t: self._renommer("Tags", t, self._renommer_tag, tag=True),
                                         tip_renommer=f"Renommer le tag {t} dans toutes les manips",
                                         deplacer=lambda sens, t=t: self._deplacer_tag(t, sens), bornes=(i == 0, i == n - 1),
                                         couleur=O.couleur_tag(self.r, t),
                                         changer_couleur=lambda t=t: (O.couleur_tag_suivante(self.r, t), self._changer(), self._actualiser())))
        x.ajouter(flux_widgets(chips) if chips else etiquette("Aucun tag pour l’instant", secondaire=True))
        nouveau = ChampTexte("", "Nouveau tag")

        def ajout():
            t = nouveau.text().strip().lstrip("#").strip()
            if not t or any(norm(t) == norm(y) for y in tous_les_tags(self.ctrl.manips, self.r.ordre_tags)):
                return
            self.r.ordre_tags = tous_les_tags(self.ctrl.manips, self.r.ordre_tags) + [t]  # proposé dans les listes déroulantes de tags
            self._changer()
            self._actualiser()

        nouveau.returnPressed.connect(ajout)
        x.ajouter(ligne(champ("Nouveau tag", nouveau), bouton("Ajouter", ajout), "stretch"))

    def _renommer_tag(self, a: str, b: str):
        if norm(a) != norm(b) and any(norm(x) == norm(b) for x in tous_les_tags(self.ctrl.manips, self.r.ordre_tags)):
            return None  # ce tag existe déjà
        ch = O.renommer_tag(self.ctrl.manips, a, b)
        dans_liste = any(norm(x) == norm(a) for x in self.r.ordre_tags)
        if ch or dans_liste:  # l'ordre choisi suit le nouveau nom
            self.r.ordre_tags = [b if norm(x) == norm(a) else x for x in self.r.ordre_tags]
            if norm(a) in self.r.couleurs_tags:
                self.r.couleurs_tags = {**{k: v for k, v in self.r.couleurs_tags.items() if k != norm(a)}, norm(b): self.r.couleurs_tags[norm(a)]}
            self.ctrl.toucher_reglages()
        return ch if (ch or dans_liste) else None

    def _deplacer_tag(self, t: str, sens: int):
        if deplacer_tag(self.ctrl.manips, self.r, t, sens):
            self._changer()
            self._actualiser()

    def _retirer_tag(self, t):
        if confirmer(self, "Retirer ce tag ?", f"#{t} sera retiré de toutes les manips et de la liste des tags.", "Retirer"):
            self.r.ordre_tags = [y for y in self.r.ordre_tags if norm(y) != norm(t)]
            self.ctrl.toucher_reglages()
            for m in O.retirer_tag_partout(self.ctrl.manips, t):
                self.ctrl.toucher(m)
            self.ctrl.toast.emit("Tag retiré de toutes les manips")
            self._actualiser()

