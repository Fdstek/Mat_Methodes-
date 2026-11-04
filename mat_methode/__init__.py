"""Mat & Méthode : description d'une manip de prétraitement et génération du « Matériel et méthodes »."""

NOM_APPLICATION = "Mat & Méthode"
VERSION = "1.1.0"
DATE_VERSION = "05/11/2026"  # date de mise à jour, affichée à l'ouverture et dans le menu
NOUVEAUTES = [
    ("1.1.0", "05/11/2026", ["Journal des bugs et idées (bas du menu)", "N° d'expérience et attribution de la manip",
                             "Filtres à choix multiples dans toutes les listes", "Colonne « Étapes » (grande étape + matériel)",
                             "Écran d'ouverture immédiat, version et date de mise à jour"]),
    ("1.0.0", "04/11/2026", ["Écran d'ouverture, historique des statuts"]),
]
SCHEMA_DONNEES = 13  # version du format des fichiers de données (2 : grandes étapes ; 3 : personnes, Scirius de la charge ; 4 : à faire) ; voir storage.stockage.migrer
