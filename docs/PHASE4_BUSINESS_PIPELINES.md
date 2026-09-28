# Phase 4 — Investissement et Suivi portefeuille

Vérification du 19 septembre 2026. Architecture et présentation conservées : `app.py → ui.app_ui → services.ui_adapter → backend`. Aucun import d’interface historique ajouté, aucun fichier historique supprimé ou archivé.

## Résultat livré

Le routage Investissement exploite le texte collecté et six catégories d’événements configurables : réduction/augmentation de capital, transaction, gouvernance, liquidation et financement. Il ne nécessite pas de participation UGFS. Au contrôle, 31 notifications étaient candidates à Investissement parmi 312 notifications centrales affichées.

Suivi portefeuille exige un rapprochement avec une participation réelle, ou une personne reliée à une participation présente dans le référentiel. Une liste de surveillance, une affectation manuelle, un dossier DD ou une mention LegalTech ne prouvent pas une détention. Les homonymes ambigus ne confirment pas une participation. Le référentiel de production est vide : aucune affectation automatique Portefeuille et aucune analyse Portefeuille de production n’ont été créées.

Les deux services utilisent le transport Ollama commun, avec leurs prompts, contextes et résultats spécialisés. Modèle réellement vérifié : **qwen3:1.7b**. CMF reste exclusivement Conformité.

## Ancrage des résultats

Le modèle choisit des identifiants de citations exactes et d’actions autorisées sous un schéma JSON strict. Un identifiant inventé ou du texte libre supplémentaire provoque une erreur ; aucun résultat de secours fictif ne remplace l’échec. Les interprétations, signaux et priorités de revue proviennent de politiques configurables et sont explicitement présentés comme des appréciations, pas comme des faits financiers prouvés.

Chaque résultat conserve le hash de la source, les positions et textes des citations, les liens champ/preuve, le rapprochement et sa provenance, la version du prompt, le modèle et la politique appliquée. Les montants décimaux et les phrases longues restent complets. Les données absentes restent « Non déterminé » : secteur non confirmé, exposition UGFS, croissance, perte, valeur, rentabilité ou échéance. Les dates de publication ne deviennent pas des échéances contractuelles.

La sélection de preuves réduit les inventions factuelles ; elle ne certifie pas l’exactitude du document, la qualité OCR, la pertinence d’un événement ou une interprétation économique. La classification par termes peut nécessiter une correction humaine, notamment en présence de négations. Le contexte demeure limité par la configuration du moteur ; une troncature est signalée.

## Matrice métier

| Service | Source record | Routing reason | Referential match | AI result | Grounding quality | Validation | Remaining issue |
|---|---|---|---|---|---|---|---|
| Investissement | LegalTech / FERTIMED, `jrletemps-fr-2026-08-29-PT260477` | Réduction de capital détectée dans le texte collecté | Aucun ; explicitement affiché | Réel, Ollama qwen3:1.7b, persisté ; lancement backend puis relancement depuis le bouton UI | 3 citations vérifiées exactement ; incidence économique non supposée | Brouillon de production, aucune validation de test | Revue métier humaine requise |
| Suivi portefeuille — production | Aucun cas admissible sans référentiel réel | Routage automatique bloqué faute de preuve | Référentiel UGFS non renseigné | Aucune analyse fabriquée | Absence de correspondance affichée ; contrôle backend avant appel IA | Sans objet | Fournir des participations UGFS faisant autorité |
| Investissement + Suivi portefeuille — isolé | ALPHA TEST, source et participation explicitement fictives, base hors production | Affectation à deux services ; référence de fixture | Référence isolée avec provenance | Deux résultats réels du même Ollama, prompts distincts | Citations source et rattachement de fixture ; champs inconnus explicites | Correction Investissement puis validation séparée des deux résultats depuis le navigateur | Cette vérification ne constitue pas une preuve de participation réelle |

## Vérifications effectuées

| Test | UI | Backend | Persistence | Live/isolated | Result |
|---|---|---|---|---|---|
| Page Investissement, raison de routage, besoin sélectionné | Vérifiée dans le navigateur | Règles actives | Lecture seule avant action | Données réelles | 31 candidats ; détail sélectionne le besoin Investissement |
| Analyser avec l’IA — Investissement | Bouton et succès visibles | Ollama local réel | Brouillon, révisions et événements enregistrés | Réel | Succès, aucun changement du résultat Commerce existant |
| Citations du brouillon réel | Résultat spécialisé visible | Comparaison des positions avec le texte extrait | 3 citations persistées | Réel | Toutes correspondent exactement |
| Excel | Export déclenché ; téléchargement proposé | openpyxl réel | Fichier créé et rouvert | Réel | Feuilles Résultat métier, Preuves source, Traçabilité ; aucun score financier fictif |
| Portfolio sans référentiel | Message explicite sur la page | Analyse refusée sans correspondance | Aucune participation fictive | Page réelle + tests isolés négatifs | Conforme |
| Deux analyses pour une seule notification | Deux services et résultats visibles | Même moteur Ollama, deux prompts | Une notification, deux affectations, deux résultats | Navigateur et moteur réels, données isolées | Conforme |
| Correction indépendante | Formulaire utilisé | Motif et version contrôlés | Investment révisé, Portfolio inchangé | Navigateur, base isolée | Conforme |
| Validation indépendante | Boutons utilisés pour les deux services | Cycle de vie réel | Investment validé avant Portfolio | Navigateur, base isolée | Non traité tant que Portfolio reste brouillon |
| Traité indépendant de Lu | Affichage vérifié | Résultats tous validés | Lecture conservée Non lu | Navigateur, base isolée | « Traité » et « Non lu » coexistent correctement |
| Diffusion | Aperçu puis ajout à la file | Résultat validé requis | File et événement persistés | Navigateur, base isolée ; garde négative en tests | Aucun email envoyé |
| Affectation manuelle, homonymes, personne liée, GICS, CMF | Pages couvertes par AppTest | Cas déterministes | SQLite temporaires | Isolé | Régressions conformes |

Suite exécutée : **45 tests réussis**, incluant les suites final_adapter, final_ui, final_operations, phase3_pipeline, pdf_preview et phase4_grounding. Les tests unitaires de sélection IA utilisent des réponses contrôlées ; les vérifications Ollama indiquées ci-dessus utilisent réellement le modèle local. Ne pas confondre ces niveaux de preuve.

## Routages corrigés et limites conservées

- Des annonces pertinentes telles que FERTIMED étaient uniquement affectées à Commerce : la nouvelle règle ajoute Investissement sur preuve d’événement. Les affectations humaines gardent la priorité.
- Une liste de surveillance appartenant au service Portefeuille n’est plus interprétée comme preuve de détention.
- Les relations vers une société absente ou ambiguë ne déclenchent pas de fausse correspondance Portefeuille.
- La page d’un service ouvre désormais son résultat spécialisé plutôt que le premier résultat d’un autre service.
- Les résultats Commerce et Conformité précédemment collectés sont conservés intégralement. Le brouillon Commerce existant comporte une formulation de croissance non démontrée, déjà signalée en Phase 3 ; Phase 4 ne le réécrit pas rétroactivement.
- Certaines cartes historiques de collecte présentent des titres semblables sous des identifiants distincts. Cette phase ne fusionne ni ne supprime ces enregistrements. Le contrat vérifié ici garantit qu’ajouter des services ne duplique pas la notification centrale identifiée par son UID.
- La reconnexion LegalTech et les synchronisations de Phase 3 ne sont pas recertifiées par cette phase ; aucun nouveau cycle de collecte n’a été déclenché pendant ces vérifications Phase 4.

## Référentiel et configuration

Six modèles **à en-tête uniquement** dans `data/reference/import_templates/` : Participations, Pipeline DD, Fonds, Dirigeants, Actionnaires, GICS L4. Leur README précise les types et liens requis. L’ancien modèle contenant des exemples est conservé mais exclu des imports réels. Aucun fichier nommé `template` n’est traité comme un référentiel faisant autorité.

Les fichiers CSV/JSON/XLSX réels sont configurables dans Organisation & Paramétrage ; aucune modification de l’interface ou du pipeline ne sera nécessaire pour charger le vrai référentiel. Les règles, événements, interprétations, actions, prompts et schémas de sélection sont configurables. Les versions précédentes de configuration sont conservées.

## Fichiers et protection des données

Nouveaux composants principaux : `services/grounded_analysis.py`, `modules/business_export.py`, `tests/test_phase4_grounding.py` et les six modèles vides. Adaptations ciblées : routing, business_analysis, pipeline_config, operations, ui_adapter, business_pipeline_registry et les pages existantes. Aucun changement de thème ou d’architecture.

Point de reprise : `backups/phase4_20260914_135712` (224 fichiers de code/configuration, copies SQLite cohérentes et inventaire de protection). Comparaison en lecture seule : **13 bases intègres, aucun identifiant d’origine manquant, aucun fichier protégé manquant ou modifié hors bases, aucune interface historique modifiée**. Les résultats métier présents avant Phase 4 sont identiques ; un seul nouveau résultat de production a été ajouté, Investissement à l’état brouillon. Aucune fixture Phase 4 dans la base de production. Les données de test vivent exclusivement dans le répertoire d’artefacts local `phase4_isolated`.

Pour revenir au code précédent : arrêter uniquement le processus de vérification concerné, examiner les différences avec le point de reprise, puis restaurer sélectivement les composants Phase 4 après approbation. **Ne pas restaurer une ancienne base sur les données courantes** : conserver les sources, nouveaux résultats, corrections et historique. Les résultats versionnés restent lisibles. Aucun rollback n’a été exécuté.

Mesure de chargement du backend après mise en cache de la normalisation : 14,06 s à froid, 0,106 s au second chargement (312 notifications). Le premier affichage navigateur a également présenté de la latence ; cette phase ne constitue pas une certification de performance du démarrage.
