# Vérification du nettoyage et de la portabilité — 28 septembre 2026

## Périmètre

Gel produit demandé par l'utilisateur. Aucun fichier du runtime actif n'a changé après le checkpoint de nettoyage. Les changements de sémantique financière/triage appartiennent à la phase précédente et sont inclus dans le checkpoint. Pas de nouveau métier, routage, scoring, IA, UI ou transport email pendant ce rangement.

## Rollback et rangement

Checkpoint local : `backups/PORTABILITY_BEFORE_20260928_150138/`. Archive ZIP vérifiée, 866 fichiers, aucune erreur de copie ; 13 sauvegardes SQLite via l'API backup. Environnements virtuels, caches, anciens backups, répétition isolée et métadonnées Git exclus de l'archive ; aucune mutation Git effectuée.

38 fichiers archivés localement (anciens lanceurs/installeurs, ZIP, diagnostic CMF obsolète et sortie Git temporaire `tatus`). 29 diagnostics déplacés vers `scripts/diagnostics/`. Aucun fichier supprimé définitivement. Liste exhaustive : `CLEANUP_MOVES.json`. Hash de chaque fichier archivé vérifié identique à sa source au checkpoint. Les diagnostics ajustent seulement leur parent de racine quand nécessaire.

Les anciens dossiers de sauvegarde restent localement exclus de Git : contenu potentiellement utile/confidentiel, aucune suppression sur simple nom. Les modules de compatibilité restent en place. UNKNOWN n'est pas synonyme de mort.

## Vérifications

| Vérification | Résultat |
|---|---|
| Chemin actif | app.py → ui.app_ui → services.ui_adapter → services/modules |
| Import map | 67 fichiers ACTIVE ; imports conditionnels/littéraux et appels dynamiques inventoriés |
| Chemins personnels dans les fichiers actifs | 0 occurrence C:\ / Users / Salima / Desktop |
| Runtime actif après checkpoint nettoyage | Hashes inchangés |
| Suite maintenue, environnement existant | 165 tests réussis |
| Suite maintenue, nouvelle .venv | 165 tests réussis |
| Compilation | app/config/UI/services/modules/scripts : réussie dans les deux environnements |
| Installation pip depuis requirements.txt | Réussie dans une nouvelle .venv Python 3.13.5 sans system-site-packages |
| pip check, environnement neuf | Aucun conflit |
| Application réelle | Accueil, Notifications, Résultats, Référentiel, Organisation & Paramétrage rendus dans le navigateur |
| Application sans données | Accueil avec compteurs 0, sources Non connecté, référentiel vide ; Notifications vide |
| Données | Fichiers protégés non transitoires inchangés, 13/13 SQLite integrity_check OK |

Les deux erreurs initiales étaient des timeouts AppTest de 3 secondes. Le délai de test est désormais 30 secondes ; le comportement de l'application n'a pas été modifié pour ce test. La suite a ensuite réussi.

## Clean room

`.cleanroom/` est une copie neuve des sources/templates nécessaires, pas un clone du commit actuel : les travaux précédents comportent encore beaucoup de fichiers non suivis. Sa `.venv` a été créée séparément avec `py -3.13 -m venv`, puis ses dépendances installées par pip (accès réseau autorisé). Aucun fichier de production, PDF, session, base ou `.venv` existante copié. Un `.env` d'exemple sans secret est fourni. Aucun SQLite créé par la consultation. Versions effectives : `CLEAN_ROOM_PACKAGES.txt` (Streamlit 1.64.0 dans le neuf ; 1.58.0 dans l'environnement courant).

Contrôle d'environnement neuf : aucune dépendance Python manquante ; avertissements attendus pour Chromium non installé, session absente et dossiers créés au premier usage. Ollama/Tesseract/Poppler restent les installations externes de ce même PC : leur réinstallation sur un autre Windows n'a pas été simulée. Le guide explique cette installation.

Environnement de démonstration actuel : `msal` et `pypdf` déclarés dans requirements manquent ; ils sont bien installés dans le neuf. Ne pas confondre le succès de la consultation actuelle avec toutes les dépendances installées. Aucune mise à niveau forcée de l'environnement de démonstration.

## Git et limites

État complet : `GIT_STATUS.txt`. Diff statistique : `GIT_DIFF_STAT.txt`. Ces sorties incluent les travaux antérieurs ; le diff Git ne reflète pas seulement cette passe et n'inclut pas le contenu non suivi. Les D correspondent à des déplacements, pas à des pertes locales. L'archive est volontairement exclue du futur dépôt de production.

Aucun commit ni push. Avant qu'un autre développeur clone la version finale, les nouveaux fichiers source/configuration/templates/docs doivent être revus et committés. Les exclusions de données/auth ont été ajoutées ; aucun secret/donnée réelle actuellement suivi dans ces emplacements, sauf les schémas/templates explicitement conservés. Vérifier le diff indexé avant livraison.

Voir KNOWN_LIMITATIONS.md : session LegalTech, collecte partielle possible, CMF à configurer, référentiel vide, SMTP non configuré, absence de validation sur un deuxième PC physique. Le nettoyage n'est pas une certification de toutes les intégrations externes.
