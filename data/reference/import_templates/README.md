# Import du référentiel UGFS

Ces six CSV sont des **schémas vides**, sans société fictive. L’ancien `portfolio_companies_template.csv` est conservé pour historique et ne doit pas être chargé comme données réelles.

Copier le modèle approprié vers un nouveau fichier de données, puis renseigner uniquement les enregistrements faisant autorité. Déclarer son chemin dans **Organisation & Paramétrage → Règles de routage & fichiers du référentiel**. CSV UTF-8, liste JSON d’objets ou première feuille XLSX sont acceptés. Aucun fichier dont le nom contient `template` n’est importé.

| Modèle | Valeur `type` | Fonction |
|---|---|---|
| participations_template.csv | portfolio | Participation/société effectivement en portefeuille |
| pipeline_dd_template.csv | pipeline_dd | Société en due diligence ; ne prouve pas une participation |
| fonds_template.csv | fund | Fonds ; ne prouve pas automatiquement une détention UGFS |
| dirigeants_template.csv | director | Personne et société liée via `portfolio_company` |
| actionnaires_template.csv | shareholder | Personne/entité actionnaire et société liée via `portfolio_company` |
| gics_l4_template.csv | sector | Correspondance sectorielle ; ne prouve pas une participation |

`name` et `type` sont nécessaires. `identifier` désambiguïse les homonymes. `portfolio_company` doit désigner une société présente dans un enregistrement `type=portfolio` pour confirmer une relation au portefeuille. `fund`, `gics_l4`, `sector`, `reference_id`, `source_reference`, `as_of` portent le contexte et la provenance disponibles. Ne pas remplir une relation ou un secteur par supposition. Un rapprochement nominal signale une mention, pas à lui seul la qualité de partie affectée.

Les raisons de rapprochement conservent le fichier, le numéro de ligne ou identifiant, et son empreinte SHA-256. Les homonymes associés à des identifiants différents restent ambigus sans identifiant correspondant. Les listes de surveillance ne sont pas assimilées à des participations. Une affectation manuelle au Suivi portefeuille reste possible, mais l’analyse ne s’exécute pas sans preuve de référence.
