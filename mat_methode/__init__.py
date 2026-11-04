"""Mat & Méthode : description d'une manip de prétraitement et génération du « Matériel et méthodes »."""

NOM_APPLICATION = "Mat & Méthode"
VERSION = "1.2.0"
DATE_VERSION = "04/11/2026"  # date de mise à jour, affichée à l'ouverture et dans le menu
NOUVEAUTES = [
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
SCHEMA_DONNEES = 14  # version du format des fichiers de données (2 : grandes étapes ; 3 : personnes, Scirius de la charge ; 4 : à faire) ; voir storage.stockage.migrer
