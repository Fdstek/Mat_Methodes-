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
from mat_methode.domain.models import Manip, Reglages, maintenant_iso
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
    presence_changee = Signal()  # quelqu'un a ouvert / fermé l'application ou changé de manip
    scirius_pret = Signal(object)  # lecture du fichier Scirius terminée en arrière-plan
    analyses_pretes = Signal(object)  # lecture des résultats d'analyses (ana explorer) terminée en arrière-plan

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
        self._scirius = None
        self._prechargement = False
        self.scirius_pret.connect(self._scirius_lu)
        self._analyses = None
        self._lecture_analyses = False
        self.analyses_pretes.connect(self._analyses_lues)
        self.presents: list[dict] = []  # autres personnes présentes (fichiers donnees\\presence)
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
        premier = not st.f_reglages.exists() and not st.a_des_manips() if not st.lecture_seule else False
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
        self.actualiser_presence()
        QTimer.singleShot(3000, self.precharger_scirius)  # après l'ouverture de la fenêtre, sans la ralentir
        QTimer.singleShot(6000, self.precharger_analyses)
        self._t_actualiser.start()
        self._t_dossier.start()
        if st.lecture_seule:
            self.statut.emit("Non enregistré : dossier inaccessible", True)

    def _charger_liste(self) -> None:
        precedentes = {m.id: m for m in self.manips}
        self.liste = self.st.lister()
        self.liste.manips += [precedentes[i] for i in self.liste.occupes if i in precedentes]  # fichier tenu un instant : version déjà connue
        en_memoire = {m.id: m for m in self.manips if m.id in self.sales or m.id == self.courante_id}
        self.manips = [en_memoire.get(m.id, m) for m in self.liste.manips]
        for m in self.liste.manips:  # les manips relues remplacent celles de la mémoire : leur version de départ suit
            if m.id not in en_memoire and m.id in self.liste.bases:
                self.st.adopter(m.id, self.liste.bases[m.id])
        if self.liste.converties:  # nouveau format : les réglages sont réécrits (un ancien exécutable les refusera)
            self.reglages_sales = True
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
        self.st.signaler_presence(ident)
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

    def fermer_manip(self) -> None:
        """Quitte la manip ouverte (bouton « ← ») : enregistrement, verrou libéré, présence sans manip."""
        if not self.courante_id:
            return
        self.journaliser()
        self.enregistrer_tout()
        self.st.liberer_verrou(self.courante_id)
        self.courante_id = None
        self.verrou_autre = None
        self.st.signaler_presence(None)

    def fermer(self) -> None:
        self.journaliser()
        self.enregistrer_tout()
        if self.courante_id:
            self.st.liberer_verrou(self.courante_id)
        self.st.retirer_presence()

    def _identite(self) -> None:
        """Nom et initiales écrits dans le signal de présence : les autres postes affichent mes initiales, pas mon IGG."""
        from mat_methode.domain.models import initiales_de
        nom = self.nom_utilisateur()
        p = self.reglages.personne_igg(self.st.utilisateur) or self.reglages.personne(nom)
        self.st.nom_affiche = nom
        self.st.initiales = p.sigle() if p else initiales_de(nom)

    def actualiser_presence(self) -> None:
        """Signale ma présence et relit celle des autres (pastilles aux initiales, comme dans Excel)."""
        self._identite()
        self.st.signaler_presence(self.courante_id)
        avant = [(p.get("utilisateur"), p.get("pc"), p.get("manip")) for p in self.presents]
        self.presents = self.st.presences_autres()
        if [(p.get("utilisateur"), p.get("pc"), p.get("manip")) for p in self.presents] != avant:
            self.presence_changee.emit()

    def presents_sur(self, ident: str | None) -> list[dict]:
        return [p for p in self.presents if ident and p.get("manip") == ident]

    def initiales_de(self, igg: str, presence: dict | None = None) -> str:
        """Initiales d'une personne présente : celles de ses Réglages ici, sinon celles que son poste a envoyées."""
        p = self.reglages.personne_igg(igg)
        if p:
            return p.sigle()
        if presence and presence.get("initiales"):
            return str(presence["initiales"])[:3].upper()
        return (igg or "?")[:2].upper()

    def nom_present(self, presence: dict) -> str:
        p = self.reglages.personne_igg(presence.get("utilisateur", ""))
        return p.nom if p else (presence.get("nom") or self.nom_de(presence.get("utilisateur", "")))

    def _battement(self) -> None:
        self.actualiser_presence()
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
        R.synchroniser_depart(m)  # flux qui commence par des voies : volume et matière de départ = ceux des voies
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
        """Auteur noté dans le journal et au lancement : les initiales de la personne connectée (pas son IGG)."""
        return self.initiales_utilisateur()

    def initiales_utilisateur(self) -> str:
        from mat_methode.domain.models import initiales_de
        p = self.reglages.personne_igg(self.st.utilisateur)
        if p:
            return p.sigle()
        nom = self.nom_utilisateur()
        return initiales_de(nom) if nom != self.st.utilisateur else nom  # IGG inconnu des Réglages : on le garde tel quel

    def lire_scirius(self, forcer: bool = False, etape=lambda t: None):
        """Lignes du fichier Scirius (voir mat_methode.scirius), gardées en mémoire pendant la session."""
        from mat_methode.scirius import SourceScirius
        if not forcer and getattr(self, "_scirius", None) is not None and self._scirius.lignes:
            return self._scirius
        src = SourceScirius(self.st.donnees / "cache", self.reglages.scirius_fichier, self.st.utilisateur)
        self._scirius = src.lire(forcer=forcer, etape=etape)
        return self._scirius

    def precharger_scirius(self) -> None:
        """Lit le fichier Scirius en arrière-plan (fil séparé) : la recherche Scirius est ensuite immédiate."""
        import os
        import threading

        from mat_methode.scirius import SourceScirius
        if os.environ.get("MATMETHODE_SANS_SCIRIUS") or self._prechargement or (self._scirius is not None and self._scirius.lignes):
            return
        self._prechargement = True
        src = SourceScirius(self.st.donnees / "cache", self.reglages.scirius_fichier, self.st.utilisateur)

        def travail():
            try:
                lu = src.lire(forcer=False)
            except Exception as ex:  # jamais d'erreur visible : la recherche relira le fichier
                log.info("Scirius en arrière-plan : %s", ex)
                lu = None
            self.scirius_pret.emit(lu)

        threading.Thread(target=travail, name="scirius", daemon=True).start()

    def _scirius_lu(self, lu) -> None:
        self._prechargement = False
        if lu is not None and getattr(lu, "lignes", None) and not (self._scirius is not None and self._scirius.lignes):
            self._scirius = lu
            log.info("Scirius chargé en arrière-plan : %s lignes (%s)", len(lu.lignes), getattr(lu, "origine", ""))

    # ------------------------------------------------------------ résultats d'analyses (ana explorer)
    def fichier_analyses(self) -> str:
        """Classeur des analyses choisi à la main sur ce poste (préférence personnelle ; vide = recherche automatique)."""
        return str(self.st.lire_preferences().get("analyses_fichier") or "")

    def choisir_fichier_analyses(self, chemin: str) -> None:
        p = self.st.lire_preferences()
        p["analyses_fichier"] = chemin
        self.st.ecrire_preferences(p)
        self._analyses = None

    def _source_analyses(self):
        from mat_methode.analyses_ptt import SourceAnalyses
        return SourceAnalyses(self.st.donnees / "cache", self.fichier_analyses())

    def lire_analyses(self, forcer: bool = False, etape=lambda t: None):
        """Résultats d'analyses du classeur d'ana explorer (voir mat_methode.analyses_ptt), gardés en mémoire pendant la session."""
        if not forcer and self._analyses is not None and not self._analyses.vide:
            return self._analyses
        try:
            self._analyses = self._source_analyses().lire(forcer=forcer, etape=etape)
        except Exception as ex:  # jamais bloquant : les documents sortent sans les résultats
            from mat_methode.analyses_ptt import Resultats
            log.info("Résultats d'analyses : %s", ex)
            self._analyses = Resultats(ecartes=[str(ex)])
        return self._analyses

    def resultats_manip(self, prelevements: list[dict]) -> dict | None:
        """Bloc « resultats » des documents pour ces échantillons (ceux du JSON d'échange), None sans résultat."""
        import os
        if os.environ.get("MATMETHODE_SANS_ANALYSES"):
            return None
        if not any(p.get("aramis") or p.get("scirius") for p in prelevements):
            return None
        return self.lire_analyses().pour_export(prelevements)

    def precharger_analyses(self) -> None:
        import os
        import threading
        if os.environ.get("MATMETHODE_SANS_ANALYSES") or self._lecture_analyses or self._analyses is not None:
            return
        self._lecture_analyses = True
        src = self._source_analyses()

        def travail():
            try:
                lu = src.lire()
            except Exception as ex:
                log.info("Résultats d'analyses en arrière-plan : %s", ex)
                lu = None
            self.analyses_pretes.emit(lu)

        threading.Thread(target=travail, name="analyses", daemon=True).start()

    def _analyses_lues(self, lu) -> None:
        self._lecture_analyses = False
        if lu is not None and self._analyses is None:
            self._analyses = lu
            log.info("Résultats d'analyses chargés : %s n° Aramis (%s)", len(lu.par_aramis), lu.origine)

    def nom_utilisateur(self) -> str:
        """Nom de la personne connectée (liste des personnes des Réglages, retrouvée par son IGG), sinon l'IGG."""
        return self.nom_de(self.st.utilisateur)

    def nom_de(self, igg: str) -> str:
        p = self.reglages.personne_igg(igg)
        return p.nom if p else igg

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
    def versions_en_conflit(self, ident: str) -> list:
        return self.st.versions_en_conflit(ident)

    def resoudre_conflit(self, ident: str, fichier: str, copier: bool) -> str:
        """Garde la version choisie ; retourne un message si c'est impossible (manip ouverte ici ou chez quelqu'un d'autre)."""
        if self.courante_id == ident:
            return "Ferme d’abord cette manip (flèche ← en haut) pour choisir sa version"
        if self.st.verrou_autre(ident):
            return "Impossible : la manip est ouverte en ce moment par quelqu’un d’autre"
        self.st.resoudre_conflit(ident, fichier, copier)
        self.sales.discard(ident)
        self._charger_liste()
        self.liste_changee.emit()
        return ""

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
        m.contexte.operateur = self.nom_utilisateur()
        if base_id:
            m.contexte.date = maintenant_iso()[:10]
            R.reference_auto(m, self.reglages, self.manips)
        self.manips.append(m)
        self.sales.add(m.id)
        self.enregistrer_tout()
        return m

    def dupliquer(self, ident: str) -> Manip:
        c = R.dupliquer(self.manip(ident), self.reglages)
        c.contexte.date = maintenant_iso()[:10]
        moi = self.reglages.personne_igg(self.st.utilisateur)
        if moi is not None:
            c.contexte.donneur = moi.nom  # celui qui duplique devient le donneur d'ordre de la copie
        R.reference_auto(c, self.reglages, self.manips)
        self.manips.append(c)
        self.sales.add(c.id)
        self.enregistrer_tout()
        return c

    def changer_statut(self, m: Manip, statut: str) -> str:
        """Change le statut d'une manip (listes Définition et Protocole). « En cours » lance la manip (journal des modifications).
        Retourne un message si c'est impossible."""
        if m.etat == statut:
            return ""
        v = self.st.verrou_autre(m.id)
        if v:
            return f"Impossible : « {m.nom} » est modifiée en ce moment par {self.nom_de(v.utilisateur)}"
        from mat_methode.domain import journal as J
        from mat_methode.domain.models import ENCOURS
        if R.changer_statut(m, statut, self.reglages, self.st.utilisateur):
            self.toucher_reglages()
        if statut == ENCOURS and not m.lancee:
            J.lancer(m, par=self.operateur(m))
        self.sales.add(m.id)
        self.enregistrer_tout()
        self.modifie.emit(True)
        return ""

    def deplacer_protocole(self, m: Manip, sens: int) -> None:
        if R.deplacer_protocole(self.manips, self.reglages, m, sens):
            self.toucher_reglages()
            self.enregistrer_tout()
            self.modifie.emit(True)

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
            self.reglages.personnes = Reglages().personnes  # des personnes, pas les services des exemples
        else:
            for k in ("laboratoires", "reactifs"):
                noms = {x.nom for x in getattr(self.reglages, k)}
                getattr(self.reglages, k).extend(x for x in getattr(r, k) if x.nom not in noms)
            for k in ("analyses", "types_demande"):
                getattr(self.reglages, k).extend(x for x in getattr(r, k) if x not in getattr(self.reglages, k))
        ids = {m.id for m in self.manips}
        for m in ms:
            if m.id in ids:
                self.manips = [x for x in self.manips if x.id != m.id]
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
        for champ in ("tags", "contexte", "communes", "etapes", "prelevements", "groupes", "a_faire"):
            setattr(actuelle, champ, getattr(m, champ))
        self.toucher(actuelle, structure=True)
        return "Suppression annulée"
