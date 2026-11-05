# Mat & Méthode — mémo pour Claude Code

Application de bureau Windows 11 (Python, PySide6) livrée en `.exe` portable sur SharePoint.
Elle sert à décrire une manip de prétraitement étape par étape (le flux), puis à générer le « Matériel et méthodes »
(sections 2.1 à 2.4), le PDF du rapport (avec le schéma du flux), le Word, et le PDF « Protocole » (document de paillasse, onglet Protocole).
Les données sont partagées entre plusieurs utilisateurs.
Utilisateur : Pierre BURGUN, technicien de labo, francophone. **Toute l'interface, les documents et les réponses sont en français**, sans jargon.
Le cahier des charges complet est dans `docs/cahier_des_charges/`.

## Règles de travail
- Branche de développement : `claude/new-session-d3mduz`. Pull request vers `main` **seulement sur demande**.
- L'utilisateur fusionne souvent `main` dans la branche : avant de pousser, faire `git fetch origin claude/new-session-d3mduz`, puis un rebase, puis un push normal. **Jamais de force-push** (il a déjà été refusé).
- Après chaque modification :
  `ruff check . && QT_QPA_PLATFORM=offscreen python3 -m pytest -q` (environ 117 tests, à peu près 100 s, tous verts attendus).
- Dans un conteneur neuf, installer d'abord :
  `pip install --break-system-packages -r requirements.txt PySide6 pytest-qt ruff pyinstaller openpyxl`
  puis `apt-get install -y libegl1 libgl1 libxkbcommon0 libfontconfig1 libdbus-1-3`.
- Pour les captures Qt hors écran : appeler `QTest.qWait(...)` avant `grab()`. Pour vérifier qu'il n'y a pas de débordement horizontal, comparer `minimumSizeHint().width()` à la largeur disponible.
- `widgets.bouton()` double déjà les `&` : y écrire `&` ; seul un `setText` direct sur un QPushButton (ex. le menu) demande `&&`. Dans le QSS, cibler les widgets par `#objectName` pour éviter les fuites de style.
- Après une PR : s'abonner (`subscribe_pr_activity`) et programmer une vérification avec `send_later` (environ 50 min) ; l'annuler une fois la PR fusionnée.

## Pile technique
- Python 3.12 ou 3.13, PySide6 avec une feuille de style Fluent maison (`ui/theme.py`, aucune bibliothèque GPL), pydantic v2.
- reportlab (PDF), python-docx et Pillow (Word, image du flux), pdfplumber (extraction), openpyxl (Scirius), pywin32 (Excel COM, Windows seulement).
- Construction : `build/build.ps1`, enregistré en **UTF-8 avec BOM et en CRLF**. Il garde la fenêtre ouverte à la fin et écrit `build\build.log` ; `build\Construire.bat` le lance par double-clic. Il cherche `py -3.12`, puis `py -3.13`, puis `python`, crée un venv, lance pytest, puis PyInstaller avec `build/MatMethode.spec` (`--onedir --windowed`).
  Le résultat est `build\dist\MatMethode_1.0\`. Tout nouveau fichier de `mat_methode/data/` doit être ajouté au `.spec`.

## Données (à côté de l'exe, sans base SQLite)
- `donnees\reglages.json` et `donnees\manips\<id>.json` : écriture atomique, contrôle de `rev`, fusion à trois voies des Réglages (`storage/fusion.py`, `LISTES`).
- `verrous\` (battement de 30 s, expiration à 3 min), `preferences\<user>.json`, `sauvegardes\AAAA-MM-JJ` (gardées 10 jours).
- `exports\Rapports\` et `exports\Protocoles\` (partagés, pas de dossier par personne ; le document s'ouvre après l'export). On y trouve aussi `cache\` (Scirius, 30 min), `logs\` et `temp\` (TMP et TEMP y sont redirigés).
- `SCHEMA_DONNEES = 15` (5-6 : états, commentaire d'échantillon ; 7 : statuts fixes Brouillon / Validée / En cours / Réalisée / Annulée, `Reglages.ordre_protocoles` ; 8 : `Reglages.ordre_tags` ; 9 : `Reglages.couleurs_tags` ; 10 : `Reglages.couleurs_types` ; 11 : `Contexte.emplacement` ; 12 : `Manip.statuts` (historique des statuts) ; 13 : `Contexte.experience`, `Contexte.attribue`, `Personne.manipule` ; 14 : `Personne.fait_mm`, `Demande.tags` ; 15 : `Manip.paralleles`, `Etape.parallele_id / voie_id`, `ReactifEtape.unite`, `Reglages.unites_reactifs / vitesses_agitation`) (dans `mat_methode/__init__.py`). Une version plus ancienne de l'application refuse un fichier plus récent. Incrémenter ce numéro à chaque ajout de champ persistant.
- Identité : l'IGG est lu dans le chemin OneDrive ou dans USERPROFILE (`C:\Users\<IGG>`), en majuscules. Le nom affiché vient de `reglages.personnes`.

## Carte du code (`mat_methode/`)
- `domain/models.py` : `Reglages` (personnes, labos, analyses, opérations, matériels, réactifs, volumes, grandes étapes, catégories « À faire », Scirius), `Manip`, `Etape` (avec `groupe_id`), `Groupe` (grande étape), `Tache`, `RapportEmis`.
- `domain/regles.py` : étiquettes S + n° d'étape (S2, S3a…), grandes étapes (`blocs`, `creer_groupe`, `placer_dans_groupe`…), copie des conditions de l'étape précédente, référence automatique `PB-2026-10-31-01` (initiales du donneur d'ordre), `dupliquer`, avertissements.
- `domain/reglages_ops.py` : renommer, ajouter ou supprimer les éléments des Réglages ; « non réalisée » ; archivage.
- `domain/journal.py` : modifications après le lancement d'une manip.
- `report/rapport.py` (texte 2.1 à 2.4, **une idée par ligne** séparée par `\n`), `report/html.py`.
- `exports/pdf.py` (blocs communs : `styles`, `document`, `cartouche`, `Flux`…), `exports/protocole.py` (Protocole de paillasse : échantillons dans chaque phase, cases à remplir à la main), `exports/word.py`, `exports/echange.py` (JSON).
- `scirius.py` : fichier `Suivi enregistrements scirius.xlsx`, feuille « Suivi General », en-tête en ligne 8.
  - Le n° Scirius est la colonne « Stock Item » ; le nom vient de « Product Name souhaité », sinon de « Nom du produit ».
  - Filtre par défaut sur les destinataires C.LACOUX et P.BURGUN.
  - Sources essayées dans l'ordre : fichier choisi, fichier synchronisé, Excel COM, copie partagée.
  - Le projet de référence est `Fdstek/Fractionnement`.
- `storage/` : chemins, stockage, fusion.
- `ui/` :
  - `fenetre.py` : navigation et exports ;
  - menu : Définition Mat & Méthode (`page_manips.py`) › Flux (`page_flux.py`) ; Protocole (`page_listes.PageProtocoles`) › Édition
    (`page_protocole.py`, aperçu ou « Modifier » avec un 2e `PageFlux`) ; Rapport (`page_listes.PageRapports`, manips réalisées) ›
    Rapport de la manip (`page_rapport.py`) ; Réglages ;
  - statuts fixes dans `domain/models.py` (`STATUTS`, `STATUTS_DEFINITION`, `STATUTS_PROTOCOLE`, anciens états convertis à la lecture) ;
    `regles.protocoles / changer_statut / deplacer_protocole / rapports_clotures` ; `Controleur.changer_statut` (« En cours » lance la manip) ;
  - `page_manips.py` : liste « Définition Mat & Méthode » (colonne Statut) ;
  - `page_flux.py` : édition du flux, Scirius, réactifs, matériel, « À faire » ; `contexte` (definition / protocole), `consultation`
    (vue en lecture via `widgets.figer`, sauf `edition` = « Modifier »), bandeau de statut ;
  - `Fenetre.choix` : manip choisie par section ; une sous-section n'est active qu'après « Ouvrir » dans sa liste (`choisie`) ;
  - `page_rapport.py` : exports, dernier rapport émis (`ligne_emis`) ;
  - `page_protocole.py` : même vue que Flux en lecture (2e `PageFlux`, contexte protocole) ; Modifier, statut et export dans le bandeau fixe ;
  - `page_reglages.py` : cartes des Réglages (ordre par personne : préférence `ordre_reglages`) ;
  - `colonnes.py` : colonnes communes des tableaux (donneur d'ordre, type, tags) ;
  - `widgets.py` : `SansMolette`, `ListeSaisie`, `ChipSupprimable`, `Expander` ;
  - `dialogues.py`, `controleur.py`.
- `tests/` : pytest et pytest-qt. Les références `docs/cahier_des_charges/exemples/rapport_attendu.md/.html` sont à régénérer si le texte du rapport change.

## État au 02/11/2026
- Lots livrés et fusionnés jusqu'à la PR n° 38 ; la construction de l'exe sous Windows réussit (02/11).
- Lot du 04/11 11h38 (écran d'ouverture `ui/demarrage.py` ; historique des statuts `Manip.statuts`, `regles.noter_statut`,
  `reglages_ops.texte_statut / journal_complet`, bandeau, Rapport, journal, export JSON « statuts », PDF / Word / protocole
  « Historique des statuts ») : poussé sur la branche.
- Lot du 04/11 18h20 (version 1.1.0) : journal « Bugs et idées » (`domain/demandes.py`, `storage/demandes.py`, `ui/page_demandes.py`, dossier
  `donnees\demandes`, export .md) ; n° d'expérience et « Attribuée à » (`Personne.manipule` = en tête de liste) ; filtres à choix multiples
  (`colonnes.Filtres`, `ListeMulti`) dans Définition, Protocole, Rapport ; colonne « Étapes » (`regles.reperes_etapes`) ; duplicata = donneur d'ordre
  de la personne connectée ; `VERSION`, `DATE_VERSION`, `NOUVEAUTES` dans `mat_methode/__init__.py` (à mettre à jour à chaque lot) ; écran d'ouverture
  affiché avant les modules lourds : poussé sur la branche.
- Lot du 04/11 19h33 (version 1.1.1) : menu « Mat & Méthode › Édition » (icônes dessinées par `fenetre.icone_menu`, volet de 215 px) ;
  prénoms (`texte.prenom`) et tags de couleur pour donneur / attribué / étapes ; `ListeMulti` à cases dans le menu (reconstruction à la fermeture) ;
  « Fait des manips » remonte la personne dans `Reglages.personnes` ; Bugs et idées : export des seules « Nouvelle » (fichier daté) puis
  statut « À vérifier » (ancien « En cours » converti) : poussé sur la branche.
- Lot du 04/11 20h48 (version 1.2.0) : glisser-déposer (`ui/glisser.py` : `Poignee`, `rendre_cible`, `rendre_source` ; `regles.deplacer_etape_vers /
  deplacer_groupe_vers / deplacer_echantillon_vers`) ; `colonnes.resume_manip` partagé par Mat & Méthode et Protocole ; `bloc_a_faire` dans les PDF / Word
  (clé JSON `a_faire`) ; demandes : tags `MENUS_DEMANDE`, modification, consigne dans le .md ; `Filtres.barre` (rangées de tags donneur / attribué) ;
  `Personne.fait_mm` / `Reglages.donneurs_proposes` : poussé sur la branche.
- Lot du 05/11 (version 1.3.0) : étapes en parallèle (`Manip.paralleles` : `Parallele` à 2-4 `Voie` ; `Etape.parallele_id / voie_id` ; un bloc est
  d'un seul tenant dans `Manip.etapes`, classé par voie, `regles.normaliser` ; `regles.segments / creer_parallele / placer_dans_voie /
  sortir_de_parallele / defaire_parallele` ; jamais dans une grande étape) ; l'étape qui suit le bloc les réunit ; disposition du schéma
  `exports/disposition.py` (PDF `Flux`, Word `image_flux`, schéma réduit pour tenir sur une page) ; texte du rapport (`phrase_paralleles`, « voie A, en
  parallèle », « réunion des voies A et B ») ; éditeur : `PageFlux._bloc_parallele`, choix « Où ajouter l'étape ? » (`voie_cible`).
  Unités des réactifs (`ReactifEtape.quantite_complete`) et vitesses d'agitation (`ChoixVitesse`) gérées dans Réglages : poussé sur la branche.
- À vérifier par l'utilisateur sous Windows :
  - l'icône dans la barre des tâches (voir `donnees\logs` : ligne « Icône : … ») ;
  - la lecture réelle de Scirius (Réglages › Fichier Scirius › « Tester la lecture ») ;
  - la police Segoe UI dans les PDF.
- L'utilisateur envoie ses demandes sous forme de fichiers markdown « Correctifs à faire ». Les traiter point par point, envoyer des captures ou des PDF d'exemple, puis proposer la PR.
