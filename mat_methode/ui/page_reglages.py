"""Page « Réglages » (§6.5, maquette W05) : valables pour toutes les manips, partagés par tous."""
from __future__ import annotations

from PySide6.QtWidgets import QFrame, QVBoxLayout, QWidget

from mat_methode import NOM_APPLICATION, VERSION
from mat_methode.domain import reglages_ops as O
from mat_methode.domain.regles import basculer_analyse, tous_les_tags
from mat_methode.domain.texte import norm
from mat_methode.ui import theme
from mat_methode.ui.controleur import Controleur
from mat_methode.ui.dialogues import confirmer
from mat_methode.ui.widgets import (
    ChampTexte,
    ChipSupprimable,
    Expander,
    Liste,
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
    def __init__(self, ctrl: Controleur):
        super().__init__()
        self.ctrl = ctrl
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(0, 0, 0, 0)
        self.lay.setSpacing(12)
        self._ouverts: dict[str, bool] = {}

    @property
    def r(self):
        return self.ctrl.reglages

    def _changer(self, manips=()):
        for m in manips:
            self.ctrl.toucher(m)
        self.ctrl.toucher_reglages()

    def _section(self, titre: str, note: str = "") -> Expander:
        x = Expander(titre, note, ouvert=self._ouverts.get(titre, titre == "Laboratoires"))
        x.tete.clicked.connect(lambda *_: self._ouverts.__setitem__(titre, x.ouvert))
        self.lay.addWidget(x)
        return x

    def rafraichir(self, *_):
        vider(self.lay)
        self.lay.addWidget(etiquette("Réglages de base de l’application : ils servent pour toutes les manips et sont partagés "
                                     "avec les autres utilisateurs du dossier.", secondaire=True, wrap=True))
        lecture_seule = self.ctrl.st.lecture_seule
        self._laboratoires()
        self._operations()
        self._liste_simple("Réactifs", [x.nom for x in self.r.reactifs], self._suppr_reactif, self._ajout_reactif, "Nouveau réactif",
                           "Seul le nom se règle ici. Le n° Scirius, l’emplacement, le fournisseur et le lot se renseignent dans l’étape "
                           "et sont gardés pour la prochaine fois.",
                           renommer=self._ren(O.renommer_reactif, lambda: [x.nom for x in self.r.reactifs]))
        self._liste_simple("Analyses disponibles", self.r.analyses, self._suppr_analyse,
                           lambda v: O.ajouter_analyse(self.r, v), "Nouvelle analyse",
                           renommer=self._ren(O.renommer_analyse, lambda: self.r.analyses))
        self._liste_simple("Donneurs d’ordre", self.r.donneurs_ordre, lambda v: self.r.donneurs_ordre.remove(v),
                           lambda v: O.ajouter_simple(self.r.donneurs_ordre, v), "Nouveau donneur d’ordre",
                           "Chaque donneur d’ordre devient un tag coloré dans « Mes manips ». ✎ renomme aussi dans toutes les manips.",
                           renommer=self._ren(O.renommer_donneur, lambda: self.r.donneurs_ordre))
        self._liste_simple("Types de demande", self.r.types_demande, lambda v: self.r.types_demande.remove(v),
                           lambda v: O.ajouter_simple(self.r.types_demande, v), "Nouveau type",
                           "Dans une manip, on choisit seulement dans cette liste. « Idée testée » apparaît pour un type contenant « test ».",
                           renommer=self._ren(O.renommer_type, lambda: self.r.types_demande))
        self._liste_simple("Grandes étapes", self.r.grandes_etapes, lambda v: self.r.grandes_etapes.remove(v),
                           lambda v: O.ajouter_simple(self.r.grandes_etapes, v), "Nouvelle grande étape",
                           "Noms proposés pour regrouper des étapes du flux (ex. Degumming : chauffage, ajout d’acide, centrifugation…).",
                           renommer=self._ren(O.renommer_grande_etape, lambda: self.r.grandes_etapes))
        self._etats()
        self._tags()
        a = etiquette(f"{NOM_APPLICATION} · version {VERSION} · données : {self.ctrl.st.donnees}", secondaire=True, wrap=True)
        a.setAccessibleName("À propos")
        self.lay.addWidget(a)
        self.lay.addStretch(1)
        for i in range(self.lay.count()):
            w = self.lay.itemAt(i).widget()
            if isinstance(w, Expander):
                w.corps.setEnabled(not lecture_seule)

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
            haut = icone("↑", f"Monter {o.nom}", lambda i=i: (O.deplacer_operation(self.r, i, -1), self._changer(), self.rafraichir()))
            haut.setEnabled(i > 0)
            bas = icone("↓", f"Descendre {o.nom}", lambda i=i: (O.deplacer_operation(self.r, i, 1), self._changer(), self.rafraichir()))
            bas.setEnabled(i < n - 1)
            x.ajouter(ligne(champ("Opération", nom), champ("Participe passé (texte)", part),
                            etiquette(f"{nb} étape{'s' if nb > 1 else ''}", secondaire=True), "stretch", haut, bas,
                            icone("✕", f"Supprimer {o.nom}", lambda o=o: self._suppr_operation(o), danger=True)))
        nouveau = ChampTexte("", "ex. neutralisation")
        npart = ChampTexte("", "ex. neutralisé")

        def ajout():
            if O.ajouter_operation(self.r, nouveau.text(), npart.text()):
                self._changer()
                self.rafraichir()
            elif nouveau.text().strip():
                self.ctrl.toast.emit("Cette opération existe déjà")

        nouveau.returnPressed.connect(ajout)
        npart.returnPressed.connect(ajout)
        x.ajouter(ligne(champ("Nouvelle opération", nouveau), champ("Participe passé", npart), bouton("Ajouter", ajout), "stretch"))

    def _renommer_operation(self, o, nouveau):
        nouveau = nouveau.strip()
        if not nouveau or nouveau == o.nom:
            return
        ancien = o.nom
        ch = O.renommer_operation(self.r, self.ctrl.manips, ancien, nouveau)
        if o.nom == ancien:
            self.ctrl.toast.emit("Impossible : cette opération existe déjà")
            self.rafraichir()
            return
        self._changer(ch)
        self.ctrl.toast.emit(f"Opération renommée ({len(ch)} manip{'s' if len(ch) > 1 else ''} mise{'s' if len(ch) > 1 else ''} à jour)")

    def _suppr_operation(self, o):
        if confirmer(self, "Retirer cette opération ?", f"« {o.nom} » ne sera plus proposée dans « Définir le flux ». "
                     "Les étapes existantes qui l’utilisent ne changent pas.", "Retirer"):
            O.supprimer_operation(self.r, o.nom)
            self._changer()
            self.rafraichir()

    # ------------------------------------------------------------ laboratoires
    def _laboratoires(self):
        x = self._section("Laboratoires", f"{len(self.r.laboratoires)}")
        x.ajouter(etiquette("Pour chaque laboratoire : le volume à prélever et les analyses demandées. Chaque nouvel échantillon les reprend ; "
                            "on peut toujours les changer échantillon par échantillon.", secondaire=True, wrap=True))
        tous = [p for m in self.ctrl.manips for p in m.prelevements]
        for lab in self.r.laboratoires:
            f = QFrame()
            f.setObjectName("sousCarte")
            v = QVBoxLayout(f)
            v.setContentsMargins(12, 10, 12, 10)
            n = sum(1 for p in tous if p.labo == lab.nom)
            nom = ChampTexte(lab.nom)
            nom.editingFinished.connect(lambda nom=nom, lab=lab: self._renommer_labo(lab.nom, nom.text()))
            vol = NumberBox(lab.volume_ml, "mL")
            vol.valeur.connect(lambda val, lab=lab: (setattr(lab, "volume_ml", val), self.ctrl.toucher_reglages()))
            v.addWidget(ligne(champ("Nom du laboratoire", nom), champ("Volume par échantillon", vol), "stretch",
                              etiquette(f"utilisé dans {n} échantillon{'s' if n > 1 else ''}", secondaire=True),
                              icone("✕", f"Supprimer {lab.nom}", lambda lab=lab: self._suppr_labo(lab.nom), danger=True)))
            an = []
            for a in self.r.analyses:
                b = bouton(a, lambda lab=lab, a=a: (setattr(lab, "analyses", basculer_analyse(lab.analyses, a)), self.ctrl.toucher_reglages()))
                b.setProperty("chip", True)
                b.setCheckable(True)
                b.setChecked(a in lab.analyses)
                an.append(b)
            v.addWidget(champ("Analyses demandées", flux_widgets(an)))
            x.ajouter(f)
        nouveau = ChampTexte("", "Nouveau laboratoire")
        ajout = lambda: O.ajouter_laboratoire(self.r, nouveau.text()) and (self._changer(), self.rafraichir())
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
            self.rafraichir()

    # ------------------------------------------------------------ listes simples
    def _liste_simple(self, titre, items, supprimer, ajouter, libelle, aide="", renommer=None):
        x = self._section(titre, f"{len(items)}")
        if aide:
            x.ajouter(etiquette(aide, secondaire=True, wrap=True))
        x.ajouter(flux_widgets([ChipSupprimable(a, lambda a=a: (supprimer(a), self._changer(), self.rafraichir()), f"Supprimer {a}",
                                                renommer=(lambda a=a: self._renommer(titre, a, renommer)) if renommer else None)
                                for a in items]) if items else etiquette("Aucun pour l’instant", secondaire=True))
        nouveau = ChampTexte("", libelle)

        def ajout():
            if ajouter(nouveau.text()):
                self._changer()
                self.rafraichir()

        nouveau.returnPressed.connect(ajout)
        x.ajouter(ligne(champ(libelle, nouveau), bouton("Ajouter", ajout), "stretch"))

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
        self.rafraichir()

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
                self, "Supprimer ce réactif ?", f"Le n° Scirius, l’emplacement, le fournisseur et le lot mémorisés pour « {nom} » seront aussi effacés.",
                "Supprimer"):
            return
        O.supprimer_reactif(self.r, nom)

    def _suppr_analyse(self, nom):
        O.supprimer_analyse(self.r, nom)

    # ------------------------------------------------------------ états
    def _etats(self):
        x = self._section("États des manips", f"{len(self.r.etats)}")
        x.ajouter(etiquette("Les états proposés dans « Mes manips » et dans le Rapport. Le premier de la liste est celui d’une nouvelle manip, "
                            "d’une copie et d’une manip restaurée. « Archivée » est fixe : il sert à ranger les manips.", secondaire=True, wrap=True))
        n = len(self.r.etats)
        for i, e in enumerate(self.r.etats):
            nb = sum(1 for m in self.ctrl.manips if m.etat == e.id)
            nom = ChampTexte(e.nom)
            nom.modifie.connect(lambda v, e=e: (setattr(e, "nom", v), self.ctrl.toucher_reglages()))
            ton = Liste(list(theme.TONS), e.ton, vide=None, libelles=theme.TONS)
            ton.choisi.connect(lambda v, e=e: (setattr(e, "ton", v), self._changer(), self.rafraichir()))
            haut = icone("↑", f"Monter {e.nom}", lambda i=i: (O.deplacer_etat(self.r, i, -1), self._changer(), self.rafraichir()))
            haut.setEnabled(i > 0)
            bas = icone("↓", f"Descendre {e.nom}", lambda i=i: (O.deplacer_etat(self.r, i, 1), self._changer(), self.rafraichir()))
            bas.setEnabled(i < n - 1)
            sup = icone("✕", f"Supprimer {e.nom}", lambda i=i: self._suppr_etat(i), danger=True)
            sup.setEnabled(n > 1)
            x.ajouter(ligne(pastille(e.nom, e.ton), champ("Nom de l’état", nom), champ("Couleur", ton),
                            etiquette(f"{nb} manip{'s' if nb > 1 else ''}", secondaire=True), "stretch", haut, bas, sup))
        nouveau = ChampTexte("", "Ex. En attente de résultats")

        def ajout():
            if O.ajouter_etat(self.r, nouveau.text()):
                self._changer()
                self.rafraichir()

        nouveau.returnPressed.connect(ajout)
        x.ajouter(ligne(champ("Nouvel état", nouveau), bouton("Ajouter", ajout), "stretch"))

    def _suppr_etat(self, i):
        ch, msg = O.supprimer_etat(self.r, self.ctrl.manips, i)
        self._changer(ch)
        if msg:
            self.ctrl.toast.emit(msg)
        self.rafraichir()

    # ------------------------------------------------------------ tags
    def _tags(self):
        ts = tous_les_tags(self.ctrl.manips)
        x = self._section("Tags utilisés", f"{len(ts)}")
        x.ajouter(etiquette("Les tags se créent dans la manip (carte « Ma demande »). Ici, on peut en renommer (✎) ou en retirer (✕) un dans toutes les manips.",
                            secondaire=True, wrap=True))
        chips = []
        for t in ts:
            nb = sum(1 for m in self.ctrl.manips if any(norm(y) == norm(t) for y in m.tags))
            chips.append(ChipSupprimable(f"#{t}  {nb}", lambda t=t: self._retirer_tag(t), f"Retirer {t} de toutes les manips",
                                         renommer=lambda t=t: self._renommer("Tags", t, lambda a, b: O.renommer_tag(self.ctrl.manips, a, b) or None,
                                                                             tag=True),
                                         tip_renommer=f"Renommer le tag {t} dans toutes les manips"))
        x.ajouter(flux_widgets(chips) if chips else etiquette("Aucun tag pour l’instant", secondaire=True))

    def _retirer_tag(self, t):
        if confirmer(self, "Retirer ce tag ?", f"#{t} sera retiré de toutes les manips.", "Retirer"):
            for m in O.retirer_tag_partout(self.ctrl.manips, t):
                self.ctrl.toucher(m)
            self.ctrl.toast.emit("Tag retiré de toutes les manips")
            self.rafraichir()

