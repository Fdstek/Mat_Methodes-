"""État de l'application et enregistrement automatique (§8.8, §8.9, §9.1).

Toute modification passe par `toucher()` : enregistrement < 1 s après la dernière frappe (les frappes
rapprochées comptent pour un seul enregistrement), journal après 0,6 s sans frappe si la manip est lancée.
"""
from __future__ import annotations

import logging
from typing import Optional

from PySide6.QtCore import QObject, QTimer, Signal

from mat_methode.domain import journal as J
from mat_methode.domain import regles as R
from mat_methode.domain.models import ARCHIVEE, NON_REALISEE, Manip, Reglages, maintenant_iso
from mat_methode.domain.prototype import exemples
from mat_methode.domain.texte import fmt_dt
from mat_methode.storage.stockage import Liste, Stockage, Verrou

log = logging.getLogger("mat_methode")


class Controleur(QObject):
    modifie = Signal(bool)  # True = changement de structure (reconstruire l'éditeur)
    liste_changee = Signal()
    reglages_changes = Signal()
    statut = Signal(str, bool)  # texte, erreur
    toast = Signal(str)
    conflit = Signal(object, object)  # ma version, version du disque
    retour_dossier = Signal(int)  # nombre de manips en attente d'enregistrement
    alerte = Signal(str)

    def __init__(self, stockage: Stockage):
        super().__init__()
        self.st = stockage
        self.reglages = Reglages()
        self.manips: list[Manip] = []
        self.liste = Liste()
        self.courante_id: Optional[str] = None
        self.verrou_autre: Optional[Verrou] = None
        self.sales: set[str] = set()
        self.reglages_sales = False
        self.annulations: list[tuple[str, object]] = []
        self.dernier_enregistrement: str = ""
        self._t_save = QTimer(self, singleShot=True, interval=700)
        self._t_save.timeout.connect(self.enregistrer_tout)
        self._t_journal = QTimer(self, singleShot=True, interval=600)
        self._t_journal.timeout.connect(self.journaliser)
        self._t_battement = QTimer(self, interval=30_000)
        self._t_battement.timeout.connect(self._battement)
        self._t_actualiser = QTimer(self, interval=60_000)
        self._t_actualiser.timeout.connect(self.actualiser)
        self._t_dossier = QTimer(self, interval=15_000)
        self._t_dossier.timeout.connect(self._verifier_dossier)

    # ------------------------------------------------------------ démarrage
    def demarrer(self) -> None:
        st = self.st
        st.initialiser()
        st.configurer_logs()
        premier = not st.f_reglages.exists() and not any(st.d_manips.glob("*.json")) if not st.lecture_seule else False
        st.sauvegarde_du_jour()
        try:
            self.reglages = st.charger_reglages()
        except Exception as ex:
            self.alerte.emit(str(ex))
            self.reglages = Reglages()
        if premier:
            self.restaurer_exemples(confirmer=False)
        self._charger_liste()
        for m in self.manips:  # fermeture brutale : rattrapage du journal
            if m.lancee and J.rattraper(m):
                self.sales.add(m.id)
        if self.sales:
            self._t_save.start()
        self._t_battement.start()
        self._t_actualiser.start()
        self._t_dossier.start()
        if st.lecture_seule:
            self.statut.emit("Non enregistré : dossier inaccessible", True)

    def _charger_liste(self) -> None:
        self.liste = self.st.lister()
        en_memoire = {m.id: m for m in self.manips if m.id in self.sales or m.id == self.courante_id}
        self.manips = [en_memoire.get(m.id, m) for m in self.liste.manips]
        self.manips += [m for i, m in en_memoire.items() if i not in {x.id for x in self.manips}]
        if self.manips and not self.dernier_enregistrement:
            self.dernier_enregistrement = max(m.maj for m in self.manips)

    def actualiser(self) -> None:
        """Relit les fichiers (bouton « Actualiser » et toutes les 60 s)."""
        if self.st.lecture_seule:
            return
        if not self.reglages_sales and self.st.reglages_ont_change(self.reglages):
            self.reglages = self.st.charger_reglages()
            self.reglages_changes.emit()
        cur = self.courante
        if cur is not None and self.verrou_autre is not None:  # lecture seule : on montre la version à jour
            self.sales.discard(cur.id)
            self.courante_id = None
            self._charger_liste()
            self.courante_id = cur.id
            self.verrou_autre = self.st.verrou_autre(cur.id)
            if self.verrou_autre is None:
                self.st.prendre_verrou(cur.id)
            self.modifie.emit(True)
        else:
            self._charger_liste()
        self.liste_changee.emit()

    # ------------------------------------------------------------ manip ouverte
    @property
    def courante(self) -> Optional[Manip]:
        return next((m for m in self.manips if m.id == self.courante_id), None)

    @property
    def lecture_seule(self) -> bool:
        return self.verrou_autre is not None

    def manip(self, ident: str) -> Optional[Manip]:
        return next((m for m in self.manips if m.id == ident), None)

    def ouvrir(self, ident: str) -> None:
        if self.courante_id and self.courante_id != ident:
            self.enregistrer_tout()
            self.st.liberer_verrou(self.courante_id)
        self.courante_id = ident
        self.verrou_autre = self.st.prendre_verrou(ident)
        if self.verrou_autre is None:  # on relit la dernière version avant de modifier
            m = self.manip(ident)
            if m is not None and ident not in self.sales:
                try:
                    disque = self.st.lire_manip(ident)
                    if disque is not None and disque.rev != m.rev:
                        self.manips[self.manips.index(m)] = disque
                except Exception:
                    pass
        self.modifie.emit(True)

    def fermer(self) -> None:
        self.journaliser()
        self.enregistrer_tout()
        if self.courante_id:
            self.st.liberer_verrou(self.courante_id)

    def _battement(self) -> None:
        if self.courante_id and not self.st.lecture_seule:
            autre = self.st.prendre_verrou(self.courante_id)
            if autre and not self.verrou_autre:
                self.verrou_autre = autre
                self.modifie.emit(True)

    # ------------------------------------------------------------ modifications
    def toucher(self, m: Manip | None = None, structure: bool = False) -> None:
        m = m or self.courante
        if m is None or (m.id == self.courante_id and self.lecture_seule):
            return
        self.sales.add(m.id)
        self.statut.emit("Enregistrement automatique…", False)
        if m.lancee:
            self._t_journal.start()
        self._t_save.start()
        self.modifie.emit(structure)

    def toucher_reglages(self) -> None:
        self.reglages_sales = True
        self.statut.emit("Enregistrement automatique…", False)
        self._t_save.start()
        self.reglages_changes.emit()

    def journaliser(self) -> None:
        for ident in list(self.sales):
            m = self.manip(ident)
            if m and m.lancee and J.journaliser(m, par=self.operateur(m)):
                self.modifie.emit(False)

    def operateur(self, m: Manip) -> str:
        return (m.contexte.operateur or "").strip() or self.st.utilisateur

    def enregistrer_tout(self) -> None:
        self._t_save.stop()
        if self._t_journal.isActive():
            self._t_journal.stop()
            self.journaliser()
        if self.st.lecture_seule:
            if self.sales or self.reglages_sales:
                self.statut.emit("Non enregistré : dossier inaccessible", True)
            return
        erreur = ""
        if self.reglages_sales:
            try:
                info = self.st.enregistrer_reglages(self.reglages)
                self.reglages_sales = False
                if info:
                    self.toast.emit(info)
                    self.reglages_changes.emit()
            except OSError:
                erreur = "Non enregistré : dossier inaccessible"
        for ident in list(self.sales):
            m = self.manip(ident)
            if m is None:
                self.sales.discard(ident)
                continue
            res = self.st.enregistrer_manip(m)
            if res.ok:
                self.sales.discard(ident)
                self.dernier_enregistrement = m.maj
            elif res.conflit is not None:
                self.sales.discard(ident)
                self.conflit.emit(m, res.conflit)
            else:
                erreur = res.erreur
        if erreur:
            self.st.lecture_seule = True
            self.statut.emit(erreur, True)
        else:
            self.dernier_enregistrement = self.dernier_enregistrement or maintenant_iso()
            self.statut.emit(self.texte_statut(), False)
        self.liste_changee.emit()

    def texte_statut(self, manip: bool = True) -> str:
        m = self.courante if manip else None
        if m is not None:
            return f"Enregistré automatiquement\n{fmt_dt(m.maj)} · version {m.rev}"
        return f"Enregistré automatiquement\n{fmt_dt(self.dernier_enregistrement or maintenant_iso())}"

    def _verifier_dossier(self) -> None:
        if self.st.lecture_seule and self.st.accessible():
            self.st.initialiser()
            n = len(self.sales) + (1 if self.reglages_sales else 0)
            if n:
                self.retour_dossier.emit(n)
            else:
                self.statut.emit(self.texte_statut(), False)
                self.actualiser()

    # ------------------------------------------------------------ conflit
    def recharger_disque(self, disque: Manip) -> None:
        i = next(k for k, m in enumerate(self.manips) if m.id == disque.id)
        self.manips[i] = disque
        self.modifie.emit(True)
        self.liste_changee.emit()

    def enregistrer_comme_copie(self, mienne: Manip, disque: Manip) -> Manip:
        c = R.dupliquer(mienne, self.reglages, nom=f"{mienne.nom} (copie de {self.st.utilisateur})")
        c.contexte.ref, c.contexte.lot = mienne.contexte.ref, mienne.contexte.lot
        for a, b in zip(c.prelevements, mienne.prelevements):
            a.scirius, a.aramis = b.scirius, b.aramis
        self.manips.append(c)
        self.recharger_disque(disque)
        self.sales.add(c.id)
        self.enregistrer_tout()
        return c

    # ------------------------------------------------------------ bibliothèque
    def nouvelle(self, nom: str, base_id: str | None = None) -> Manip:
        if base_id and self.manip(base_id):
            m = R.dupliquer(self.manip(base_id), self.reglages, nom=nom)
        else:
            m = Manip(nom=nom, etat=self.reglages.etat_initial())
            m.contexte.date = maintenant_iso()[:10]
        m.contexte.operateur = self.st.utilisateur
        self.manips.append(m)
        self.sales.add(m.id)
        self.enregistrer_tout()
        return m

    def dupliquer(self, ident: str) -> Manip:
        c = R.dupliquer(self.manip(ident), self.reglages)
        self.manips.append(c)
        self.sales.add(c.id)
        self.enregistrer_tout()
        return c

    def supprimer(self, ident: str) -> None:
        m = self.manip(ident)
        if m is None:
            return
        self.memoriser("manip", m.to_json())
        self.st.supprimer_manip(ident)
        self.manips.remove(m)
        self.sales.discard(ident)
        if self.courante_id == ident:
            self.courante_id = None
        self.liste_changee.emit()

    def ajouter_importee(self, m: Manip) -> None:
        self.manips.append(m)
        self.sales.add(m.id)
        self.reglages_sales = True
        self.enregistrer_tout()

    def restaurer_exemples(self, confirmer=True) -> None:
        """Ajoute les manips d'exemple et complète les réglages (ne supprime rien dans le dossier partagé)."""
        r, ms = exemples()
        if not confirmer:
            self.reglages = r
        else:
            for k in ("laboratoires", "reactifs"):
                noms = {x.nom for x in getattr(self.reglages, k)}
                getattr(self.reglages, k).extend(x for x in getattr(r, k) if x.nom not in noms)
            for k in ("analyses", "donneurs_ordre", "types_demande"):
                getattr(self.reglages, k).extend(x for x in getattr(r, k) if x not in getattr(self.reglages, k))
        ids = {m.id for m in self.manips}
        for m in ms:
            if m.id in ids:
                self.manips = [x for x in self.manips if x.id != m.id]
            if m.etat not in (ARCHIVEE, NON_REALISEE) and not self.reglages.etat(m.etat):
                m.etat = self.reglages.etat_initial()
            self.manips.append(m)
            if not self.st.lecture_seule:
                self.st.ecrire_tel_quel(m)
        self.reglages_sales = True
        self.enregistrer_tout()

    # ------------------------------------------------------------ annuler (Ctrl+Z)
    def memoriser(self, quoi: str, donnees) -> None:
        """Avant une suppression : garde de quoi revenir en arrière."""
        self.annulations.append((quoi, donnees))
        del self.annulations[:-20]

    def memoriser_manip(self, m: Manip | None = None) -> None:
        m = m or self.courante
        if m is not None:
            self.memoriser("contenu", m.to_json())

    def annuler(self) -> str:
        if not self.annulations:
            return ""
        quoi, d = self.annulations.pop()
        m = Manip.model_validate(d)
        actuelle = self.manip(m.id)
        if quoi == "manip":
            m.rev = 1
            self.manips.append(m)
            self.sales.add(m.id)
            self.enregistrer_tout()
            return f"« {m.nom} » restaurée"
        if actuelle is None:
            return ""
        for champ in ("tags", "contexte", "communes", "etapes", "prelevements"):
            setattr(actuelle, champ, getattr(m, champ))
        self.toucher(actuelle, structure=True)
        return "Suppression annulée"
