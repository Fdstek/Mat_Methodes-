"""Mat & Méthode : description d'une manip de prétraitement et génération du « Matériel et méthodes »."""

NOM_APPLICATION = "Mat & Méthode"
VERSION = "1.5.0"
DATE_VERSION = "05/11/2026"  # date de mise à jour, affichée à l'ouverture et dans le menu
NOUVEAUTES = [
    ("1.5.0", "05/11/2026", ["Fin des copies de conflit OneDrive : un fichier par version de chaque manip, jamais réécrit",
                             "Si deux postes enregistrent en même temps, les deux versions sont gardées et on choisit laquelle conserver",
                             "Les anciens fichiers sont convertis au premier lancement (originaux gardés dans manips\\_ancien)"]),
    ("1.4.0", "05/11/2026", ["Le choix de l'étape à ajouter s'ouvre juste sous l'étape, la grande étape ou la voie concernée",
                             "Voies en parallèle : matière reçue (% ou mL), autres matières, quantité prise à la réunion, tableau « Volumes par étape »",
                             "Voies en parallèle dans la colonne « Étapes » des listes",
                             "Unités de durée (s, min, h, jour, semaine) et vitesses de centrifugation en tr/min ou RCF (g) gérées dans Réglages",
                             "Conditions par défaut de chaque opération gérées dans Réglages › Opérations"]),
    ("1.3.0", "05/11/2026", ["Étapes en parallèle : cadre avec des voies côte à côte, l'étape suivante réunit les voies (flux, rapport, PDF, Word)",
                             "Unités des réactifs et vitesses d'agitation : listes gérées dans Réglages"]),
    ("1.2.0", "04/11/2026", ["Glisser-déposer : étapes, grandes étapes (poignée ⠿) et échantillons (vers une autre étape)",
                             "Listes Mat & Méthode et Protocole : même présentation",
                             "Points « À faire » non cochés repris dans les PDF et le Word",
                             "Bugs et idées : menus concernés (tags), modification des demandes, nouveau logo",
                             "Filtre « Manip attribuée à » en tags ; « Fait des Mat & Méthode » en tête des donneurs d'ordre"]),
    ("1.1.2", "04/11/2026", ["Fichier tenu un instant par OneDrive ou un autre poste : relu automatiquement, plus de faux « fichier illisible »",
                             "Fichier vraiment illisible : la cause est indiquée"]),
    ("1.1.1", "04/11/2026", ["Menu : Mat & Méthode › Édition, plus de place pour les pages", "Icônes du menu visibles",
                             "Donneurs d'ordre et attribués : prénoms en tags de couleur ; colonne Étapes en tags",
                             "Listes à choix multiples qui restent ouvertes entre deux choix",
                             "« Fait des manips » remonte la personne en tête des listes",
                             "Bugs et idées : export des nouvelles demandes seulement, daté, puis statut « À vérifier »"]),
    ("1.1.0", "05/11/2026", ["Journal des bugs et idées (bas du menu)", "N° d'expérience et attribution de la manip",
                             "Filtres à choix multiples dans toutes les listes", "Colonne « Étapes » (grande étape + matériel)",
                             "Écran d'ouverture immédiat, version et date de mise à jour"]),
    ("1.0.0", "04/11/2026", ["Écran d'ouverture, historique des statuts"]),
]
SCHEMA_DONNEES = 18  # version du format des fichiers de données (2 : grandes étapes ; 3 : personnes, Scirius de la charge ; 4 : à faire) ; voir storage.stockage.migrer
