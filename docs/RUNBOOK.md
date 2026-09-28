# Exploitation Windows

Exécuter toutes les commandes depuis la racine ; utiliser `.venv/Scripts/python.exe`. Installation et connexion : README.

1. `python scripts/check_environment.py` : contrôle en lecture seule, aucun secret imprimé. WARN signifie service facultatif manquant ; FAIL signifie dépendance/ressource requise ou base inaccessible. Une session présente n'est pas nécessairement encore valide.
2. `python -m streamlit run app.py --server.address 127.0.0.1` : interface locale. Arrêt Ctrl+C. Pour un port occupé, utiliser `--server.port 8502` ; ne pas arrêter un processus inconnu.
3. Synchroniser via l'interface. Une session expirée nécessite une reconnexion manuelle. Une erreur de collecte ne doit jamais être traitée comme succès.
4. Analyser uniquement des services affectés ; corriger/valider un brouillon ; télécharger l'Excel. Pas d'envoi SMTP automatique.
5. Contrôler la supervision et l'historique. Ne pas relancer en masse une analyse ou un routage pour réparer un seul résultat.

## Sauvegarde et restauration

PROTÉGÉS : `data/` (SQLite, PDF, texte, exports, références et corrections), `secrets/`, `.env`, configuration/prompts et historique. Arrêter les processus qui écrivent avant une restauration. Pour une sauvegarde à chaud SQLite, utiliser l'API backup SQLite ; ne pas copier seulement le fichier principal en oubliant le WAL. Copier les autres fichiers en conservant leurs chemins et restreindre l'accès à la sauvegarde.

Le checkpoint de cette passe est `backups/PORTABILITY_BEFORE_20260928_150138/` : archive vérifiée, manifeste SHA-256, statut Git et sauvegardes SQLite cohérentes. Ce dossier est local et exclu de Git. Restaurer d'abord dans un dossier séparé, vérifier l'intégrité, puis choisir les fichiers à rétablir. Ne jamais remplacer des résultats humains plus récents par une sauvegarde ancienne.

`docs/CLEANUP_MOVES.json` indique chaque déplacement. Pour annuler le rangement, déplacer chaque destination vers son origine uniquement après vérification de l'absence de collision. Aucun fichier de production n'a été déplacé par ce rangement.

## Transfert vers un autre PC

Un clone fournit code/configuration/templates, pas les données privées. Installer les dépendances externes séparément. Laisser l'application vide pour une première validation. Le transfert éventuel de données est une opération UGFS distincte et sécurisée. Reconnecter LegalTech sur le nouveau PC ; ne pas committer/copier des cookies dans le dépôt.
