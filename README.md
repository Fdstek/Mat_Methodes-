# Mat & Méthode

Application de bureau **Windows 11** (Python, livrée en `.exe` portable) pour décrire une manip de prétraitement
étape par étape et produire automatiquement le « Matériel et méthodes », un **PDF** et un **Word** avec le schéma du flux.

Le cahier des charges complet, le prototype web et les fichiers d'exemple sont dans
[`docs/cahier_des_charges/`](docs/cahier_des_charges/CAHIER_DES_CHARGES.md).

## Pour les utilisateurs

1. Dans SharePoint, **Synchroniser** le dossier `MatMethode_1.0`, puis clic droit sur le dossier :
   **« Toujours conserver sur cet appareil »**.
2. Lancer `MatMethode.exe` depuis le dossier synchronisé (jamais depuis le navigateur).
3. Au premier lancement, Windows peut afficher **SmartScreen** (fichier non signé) : « Informations complémentaires »
   puis « Exécuter quand même ». Sinon : clic droit sur `MatMethode.exe` > Propriétés > **Débloquer**.
   Demander à l'informatique d'autoriser l'exécutable si l'antivirus le bloque.

Tout est enregistré **automatiquement** (pas de bouton Enregistrer). L'en-tête indique en permanence
« Enregistré automatiquement · date à heure · version n ».

Les données sont **à côté de l'application**, partagées par tous :

```text
MatMethode_1.0\
  MatMethode.exe, _internal\       l'application (à remplacer lors d'une mise à jour)
  donnees\                         à CONSERVER lors d'une mise à jour
    reglages.json                  laboratoires, réactifs, analyses, donneurs d'ordre, types, états
    manips\<id>.json               une manip = un fichier
    verrous\                       qui modifie quelle manip en ce moment
    preferences\<utilisateur>.json dernière manip, taille de fenêtre, dernier dossier d'export
    sauvegardes\AAAA-MM-JJ\        copie à la 1re ouverture du jour (10 jours gardés)
    exports\  logs\
  temp\                            fichiers temporaires, vidé au démarrage et à la fermeture
```

Plusieurs personnes : une manip ouverte par quelqu'un d'autre s'ouvre en **lecture seule**
(« Modifiée en ce moment par Marie », bouton « Dupliquer pour travailler dessus »). Si deux personnes enregistrent
la même manip, rien n'est écrasé : on choisit « Recharger la version de … » ou « Enregistrer ma version comme copie ».
Les réglages modifiés en même temps sont fusionnés.

**Grandes étapes** : dans « Définir le flux », « + Commencer une grande étape » (ex. Degumming), puis on ajoute ses
sous-étapes (chauffage, ajout d'acide, centrifugation…). Les numéros restent continus sur tout le flux (étapes 2 à 4,
échantillon S4…) ; la grande étape apparaît comme un cadre à l'écran, un bandeau sur les cartes du PDF et du Word, et une
phrase « Degumming (étapes 2 à 4). » dans le texte. La liste des noms se règle dans Réglages.

Raccourcis : `Ctrl+N` nouvelle manip · `Ctrl+F` recherche · `Ctrl+E` exporter · `Ctrl+Z` annuler la dernière
suppression · `Alt+←/→` étape précédente/suivante · `F5` actualiser.

## Construire l'exécutable (sur un Windows 11 64 bits)

Prérequis : Python 3.12 64 bits (`py -3.12`).

```powershell
powershell -ExecutionPolicy Bypass -File build\build.ps1
```

Le script crée un environnement virtuel propre, installe `requirements.txt`, lance les tests, construit avec
PyInstaller (`build\MatMethode.spec`, mode **--onedir --windowed**, jamais --onefile qui passe par `%TEMP%`)
et calcule le SHA-256 de l'exe. Résultat : `build\dist\MatMethode_1.0\`.

Mise à jour : déposer le nouveau dossier (`MatMethode_1.1\`…) **en y déplaçant le dossier `donnees\`**.
Chaque fichier porte un numéro de `schema` ; une version plus ancienne de l'application refuse d'ouvrir des données plus
récentes (« Mets à jour l'application »).

## Développement

```bash
pip install -r requirements.txt
python -m pytest            # 67 tests ; les références sont dans docs/cahier_des_charges/exemples/
python -m mat_methode       # données dans ./donnees (ou MATMETHODE_DOSSIER=...)
ruff check .
```

```text
mat_methode/
  domain/      modèles (pydantic), règles §8 (étiquettes, bilan, communes, labos), journal, réglages
  report/      texte « Matériel et méthodes » (§10), Markdown, HTML imprimable
  exports/     JSON d'échange + import, PDF (reportlab), Word (python-docx + Pillow)
  extraction/  lecture d'un ancien rapport PDF (pdfplumber)
  storage/     fichiers JSON partagés, verrous, révisions, fusion des réglages, sauvegardes, temp
  ui/          interface PySide6 (pages, fenêtres, thème Windows 11)
tests/         pytest + pytest-qt
build/         MatMethode.spec, build.ps1, icône, fichier de version
```

## Choix faits (questions du §15)

| Question | Réponse retenue |
|---|---|
| Bibliothèque d'interface | **PySide6 seul** avec une feuille de style Fluent maison (§13) : pas de licence GPL/payante. |
| Corrections du texte (§14.1) | **Appliquées**. `rapport_attendu.md/.html` ont été régénérés ; les originaux du prototype sont gardés en `rapport_attendu_prototype.*`. Seules les phrases 2.2 et 2.3 changent (vérifié par un test). |
| Numéros Scirius / Aramis | **Texte libre** ; alerte sur les doublons (dans la manip et avec les autres manips). |
| Étiquettes S + n° d'étape | **Validées** (S2, S3a, S3b…). |
| Données | Partagées dans le dossier SharePoint (§9.1). |

Corrections du texte : « (1 : 1, v/v) » au lieu de « (1 : 1 (v/v)) » ; matériel en minuscule (« plaque chauffante
agitatrice », sigles conservés) ; liaisons variées (« il a ensuite été », « il a été », « il a enfin été ») ;
« filtré sous vide sur membrane de 5 µm pendant 10 min » ; « sous agitation à 300 tr/min ». Le sujet reste
« le produit » (masculin) : accorder avec la matière (« la graisse … chauffée ») demanderait de connaître son genre.

Autres points du §14 : contrôle « prélèvement après la fin de l'étape » (avertissement dans l'éditeur) ; confirmation avant
de supprimer un réactif qui a des informations mémorisées ; cartes du PDF plus hautes (et police réduite au-delà) quand une
étape a beaucoup de réactifs ; focus gardé dans les fenêtres modales. Le laboratoire par défaut **par manip** n'est pas fait
(feuille de route).

## À vérifier sur un vrai Windows 11

Ces critères du §17 ne peuvent pas être testés automatiquement hors de Windows :
12 (lancement < 5 s sur un PC neuf), 13 (thème, couleur d'accentuation, mise à l'échelle 100/150/200 %, contraste élevé),
15 et 18 (Segoe UI dans les PDF produits par l'exe), 24 (Process Monitor : aucune écriture dans `%APPDATA%`,
`%LOCALAPPDATA%`, `%TEMP%`), 17 (ouverture du .docx dans Word sans avertissement), et SmartScreen.
La boîte « Enregistrer sous » de Windows peut mettre à jour la liste des fichiers récents (créée par Windows lui-même).

## Feuille de route

- **V1.1** : laboratoire par défaut par manip ; validation des formats Scirius/Aramis quand ils seront connus ;
  import de l'inventaire des réactifs (Excel) ; réglage fin de l'extraction PDF sur de vrais rapports.
- **V2** : OCR des PDF scannés ; impression d'étiquettes ; synchronisation SharePoint/Excel ; signature de l'exe.
- Hors périmètre pour l'instant : version web ou mobile, comptes et droits, journal d'audit réglementaire, anglais.
