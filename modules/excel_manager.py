"""Export Excel métier du Système de Veille LegalTech.

Objectif
--------
Produire un classeur lisible par les équipes Juridique, Finance et Direction,
tout en conservant une feuille technique complète pour l'audit.

Feuilles générées :
- ``Synthèse`` : vue décisionnelle et priorités de revue ;
- ``Vue_Juridique`` : risques, preuves, validation et actions juridiques ;
- ``Vue_Finance`` : montants, cohérence financière et potentiel ;
- ``Méthodologie_Scoring`` : explication transparente des scores ;
- ``Analyse_détaillée`` : données complètes et traçabilité technique ;
- ``Revue_humaine`` : champs jaunes à valider/corriger ;
- ``Légende`` : définitions métier et règles de lecture.

IMPORTANT
---------
Le fichier Excel NE calcule PAS lui-même les scores métier.
Il affiche les scores produits en amont par ``modules.scoring_engine`` et leur
``score_breakdown``. Le score d'opportunité est un potentiel générique de veille
et non une recommandation d'investissement UGFS.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from openpyxl.formatting.rule import CellIsRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

from config import OUTPUT_EXCEL_DIR

try:
    # Source de vérité pour les scores de base affichés dans la méthodologie.
    from modules.scoring_engine import EVENT_BASE_SCORES, SCORING_VERSION
except Exception:
    # L'export continue de fonctionner même si le module de scoring n'est pas
    # importable dans un contexte isolé. Cette table correspond à la version v5.
    SCORING_VERSION = "legaltech_scoring_v5"
    EVENT_BASE_SCORES: dict[str, tuple[int, int, str]] = {
        "CONSTITUTION_SOCIETE": (20, 35, "Création d'une nouvelle structure sans signal négatif explicite."),
        "SOUSCRIPTION_CAPITAL": (25, 55, "Fenêtre de souscription explicite, à confirmer selon la stratégie UGFS."),
        "AUGMENTATION_CAPITAL": (30, 65, "Événement de financement pouvant créer une opportunité à analyser."),
        "DISSOLUTION": (75, 20, "Fin anticipée de la société ou décision de dissolution."),
        "LIQUIDATION": (85, 25, "Liquidation en cours avec impact élevé sur la continuité."),
        "CLOTURE_LIQUIDATION": (55, 10, "Clôture d'une liquidation, événement important mais achevé."),
        "REDRESSEMENT_JUDICIAIRE": (90, 20, "Procédure judiciaire affectant fortement la continuité et les créanciers."),
        "FAILLITE": (95, 20, "Faillite ou procédure collective critique."),
        "CLOTURE_FAILLITE": (60, 10, "Clôture d'une faillite, avec risque historique élevé mais procédure terminée."),
        "VENTE_FONDS_COMMERCE": (35, 65, "Cession d'un actif commercial pouvant constituer une opportunité transactionnelle."),
        "LOCATION_GERANCE": (25, 45, "Mise en location-gérance d'un fonds de commerce."),
        "VENTE_ENCHERES_SAISIE": (80, 70, "Saisie ou adjudication : risque élevé et potentiel d'acquisition."),
        "AVIS_CREANCIERS": (70, 15, "Appel ou délai de déclaration des créances."),
        "NOMINATION_DIRIGEANT": (25, 15, "Changement de direction à surveiller."),
        "NOMINATION_COMMISSAIRE": (15, 10, "Nomination de contrôle/audit, généralement peu risquée seule."),
        "CHANGEMENT_GOUVERNANCE": (30, 15, "Modification de gouvernance nécessitant une revue."),
        "CONVOCATION_AGO": (10, 15, "Convocation ordinaire sans signal négatif explicite."),
        "CONVOCATION_AGE": (15, 25, "Assemblée extraordinaire pouvant porter sur une opération structurante."),
        "CONSTITUTION_ASSOCIATION": (10, 15, "Création associative, généralement faible en risque financier."),
        "RECTIFICATIF": (10, 5, "Rectification administrative ou éditoriale."),
        "AUTRE": (20, 15, "Événement non classé, à revoir manuellement."),
    }


EXCEL_EXPORT_VERSION = "excel_metier_v4"


# =============================================================================
# Schéma interne
# =============================================================================

BASE_COLUMNS = [
    "ID_Annonce", "Date_Email", "Nom_PDF", "Société", "Société_Source",
    "Catégorie", "Code_Événement_Principal", "Type_Événement_IA",
    "Événements_Secondaires", "Résumé_IA", "Montant_Capital_Original",
    "Capital_Normalisé_TND", "Nombre_Parts_Actions",
    "Valeur_Nominale_Originale", "Valeur_Nominale_TND",
    "Capital_Calculé_TND", "Écart_Capital_TND", "Statut_Contrôle_Capital",
    "Période_Souscription", "Version_Parseur_Montants",
    "Risques_Détectés_IA", "Preuves_Risques", "Évaluation_Risque_Dérivée",
    "Base_Évaluation_Risque", "Opportunités_Détectées_IA",
    "Preuves_Opportunités", "Opportunité_Potentielle_Dérivée",
    "Base_Opportunité_Dérivée", "Nature_Opportunité_Dérivée",
    "Score_Risque_IA", "Niveau_Risque_IA", "Détail_Score_Risque",
    "Score_Opportunité_IA", "Niveau_Opportunité_IA",
    "Détail_Score_Opportunité", "Portée_Score_Opportunité",
    "Action_Recommandée_IA", "Confiance_IA", "Confiance_Extraction",
    "Confiance_Interprétation", "Plafond_Confiance_Interprétation",
    "Raison_Plafond_Confiance", "Couverture_Preuves", "Scoring_Method",
    "Version_Scoring", "Version_Analyseur", "Version_Validation_Factuelle",
    "Statut_Validation_Factuelle", "Corrections_Automatiques",
    "Erreurs_Validation_Factuelle",
]

TRACEABILITY_COLUMNS = [
    "Index_Annonce", "Référence_Annonce", "Page_Début", "Page_Fin",
    "Nombre_Pages", "Caractères_Annonce", "Qualité_Extraction_Segment",
    "Méthode_Extraction", "Méthode_Segmentation", "Statut_Validation_PDF",
    "Statut_Validation_PDF_Global", "Statut_Validation_Annonce",
    "Avertissements_Validation", "JSON_Valide", "Erreur_LLM", "Modèle_LLM",
    "Extrait_Source",
]

CORRECTION_COLUMNS = [
    "Statut_Revue", "Société_Corrigée", "Type_Événement_Corrigé",
    "Résumé_Corrigé", "Risques_Corrigés", "Opportunités_Corrigées",
    "Score_Risque_Corrigé", "Score_Opportunité_Corrigé",
    "Action_Corrigée", "Commentaire_Humain", "Validateur",
    "Date_Validation",
]

EXPORT_COLUMNS = BASE_COLUMNS + TRACEABILITY_COLUMNS + CORRECTION_COLUMNS


FRENCH_HEADER_MAP = {
    "ID_Annonce": "Identifiant de l’annonce",
    "Date_Email": "Source d’import",
    "Nom_PDF": "Fichier PDF",
    "Société": "Nom de société proposé",
    "Société_Source": "Nom relevé dans le document",
    "Catégorie": "Catégorie métier",
    "Code_Événement_Principal": "Code de l’événement principal",
    "Type_Événement_IA": "Événement principal",
    "Événements_Secondaires": "Événements secondaires",
    "Résumé_IA": "Résumé factuel",
    "Montant_Capital_Original": "Capital publié (texte source)",
    "Capital_Normalisé_TND": "Capital normalisé (TND)",
    "Nombre_Parts_Actions": "Nombre de parts ou actions",
    "Valeur_Nominale_Originale": "Valeur nominale publiée",
    "Valeur_Nominale_TND": "Valeur nominale normalisée (TND)",
    "Capital_Calculé_TND": "Capital recalculé (TND)",
    "Écart_Capital_TND": "Écart de capital (TND)",
    "Statut_Contrôle_Capital": "Statut du contrôle du capital",
    "Période_Souscription": "Période de souscription",
    "Version_Parseur_Montants": "Version du parseur de montants",
    "Risques_Détectés_IA": "Risques explicitement mentionnés",
    "Preuves_Risques": "Preuves textuelles des risques",
    "Évaluation_Risque_Dérivée": "Évaluation de risque dérivée",
    "Base_Évaluation_Risque": "Base de l’évaluation du risque",
    "Opportunités_Détectées_IA": "Opportunités explicitement mentionnées",
    "Preuves_Opportunités": "Preuves textuelles des opportunités",
    "Opportunité_Potentielle_Dérivée": "Opportunité potentielle dérivée",
    "Base_Opportunité_Dérivée": "Base de l’opportunité dérivée",
    "Nature_Opportunité_Dérivée": "Nature de l’opportunité dérivée",
    "Score_Risque_IA": "Score de risque (0–100)",
    "Niveau_Risque_IA": "Niveau de risque",
    "Détail_Score_Risque": "Détail du calcul du risque",
    "Score_Opportunité_IA": "Potentiel d’opportunité (0–100)",
    "Niveau_Opportunité_IA": "Niveau de potentiel",
    "Détail_Score_Opportunité": "Détail du calcul du potentiel",
    "Portée_Score_Opportunité": "Portée du potentiel d’opportunité",
    "Action_Recommandée_IA": "Action recommandée",
    "Confiance_IA": "Fiabilité globale du pipeline",
    "Confiance_Extraction": "Fiabilité de l’extraction",
    "Confiance_Interprétation": "Fiabilité de l’interprétation",
    "Plafond_Confiance_Interprétation": "Plafond de fiabilité appliqué",
    "Raison_Plafond_Confiance": "Raison du plafond de fiabilité",
    "Couverture_Preuves": "Couverture des preuves",
    "Scoring_Method": "Méthode de calcul des scores",
    "Version_Scoring": "Version du moteur de scoring",
    "Version_Analyseur": "Version de l’analyseur",
    "Version_Validation_Factuelle": "Version de la validation factuelle",
    "Statut_Validation_Factuelle": "Statut de validation factuelle",
    "Corrections_Automatiques": "Corrections automatiques appliquées",
    "Erreurs_Validation_Factuelle": "Points à revoir manuellement",
    "Index_Annonce": "Numéro de l’annonce dans le PDF",
    "Référence_Annonce": "Référence officielle de l’annonce",
    "Page_Début": "Page de début",
    "Page_Fin": "Page de fin",
    "Nombre_Pages": "Nombre de pages",
    "Caractères_Annonce": "Nombre de caractères",
    "Qualité_Extraction_Segment": "Qualité d’extraction du segment",
    "Méthode_Extraction": "Méthode d’extraction",
    "Méthode_Segmentation": "Méthode de segmentation",
    "Statut_Validation_PDF": "Statut de validation du PDF",
    "Statut_Validation_PDF_Global": "Statut global du PDF",
    "Statut_Validation_Annonce": "Statut structurel de l’annonce",
    "Avertissements_Validation": "Avertissements structurels",
    "JSON_Valide": "Réponse JSON valide",
    "Erreur_LLM": "Erreur du modèle local",
    "Modèle_LLM": "Modèle local utilisé",
    "Extrait_Source": "Extrait du texte source",
    "Statut_Revue": "Statut de revue humaine",
    "Société_Corrigée": "Nom de société validé ou corrigé",
    "Type_Événement_Corrigé": "Événement corrigé",
    "Résumé_Corrigé": "Résumé corrigé",
    "Risques_Corrigés": "Risques corrigés",
    "Opportunités_Corrigées": "Opportunités corrigées",
    "Score_Risque_Corrigé": "Score de risque corrigé",
    "Score_Opportunité_Corrigé": "Potentiel d’opportunité corrigé",
    "Action_Corrigée": "Action recommandée corrigée",
    "Commentaire_Humain": "Commentaire du validateur",
    "Validateur": "Nom du validateur",
    "Date_Validation": "Date de validation",
}

REVERSE_HEADER_MAP = {value: key for key, value in FRENCH_HEADER_MAP.items()}


# =============================================================================
# Helpers de normalisation
# =============================================================================

def safe_text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (list, tuple, set)):
        return "; ".join(safe_text(item) for item in value if safe_text(item))
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value).strip()


def safe_number(value: Any, default: Any = 0) -> Any:
    try:
        return round(float(value), 3)
    except (TypeError, ValueError):
        return default


def get_first(analysis: dict, *keys: str, default: Any = "") -> Any:
    for key in keys:
        if key in analysis and analysis.get(key) not in (None, ""):
            return analysis.get(key)
    return default


def _evidence_text(items: Any) -> str:
    if not isinstance(items, list):
        return ""
    lines: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        description = safe_text(item.get("description"))
        proof = safe_text(item.get("preuve_textuelle"))
        if description and proof:
            lines.append(f"{description} — Preuve : « {proof} »")
    return "\n".join(lines)


def _breakdown_text(items: Any) -> str:
    if not isinstance(items, list):
        return ""
    lines: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        factor = safe_text(item.get("facteur"), "Facteur")
        points = item.get("points", 0)
        justification = safe_text(item.get("justification"))
        line = f"{points:+} — {factor}"
        if justification:
            line += f" — {justification}"
        lines.append(line)
    return "\n".join(lines)


def _validation_text(items: Any) -> str:
    if not isinstance(items, list):
        return ""
    lines: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        code = safe_text(item.get("code") or item.get("field"), "INFO")
        message = safe_text(
            item.get("message")
            or item.get("reason")
            or f"{item.get('before', '')} → {item.get('after', '')}"
        )
        lines.append(f"{code} : {message}")
    return "\n".join(lines)


# =============================================================================
# Traduction métier des scores
# =============================================================================

def _risk_reading(value: Any) -> str:
    score = safe_number(value, 0)
    if score < 30:
        return "Faible — surveillance normale"
    if score < 60:
        return "Modéré — revue recommandée"
    if score < 80:
        return "Élevé — traitement prioritaire"
    return "Critique — escalade immédiate"


def _opportunity_reading(value: Any) -> str:
    score = safe_number(value, 0)
    if score < 30:
        return "Faible — peu de potentiel identifié"
    if score < 60:
        return "À examiner — potentiel à qualifier"
    if score < 80:
        return "Intéressant — analyse métier prioritaire"
    return "Très élevé — à confirmer avec les critères UGFS"


def _confidence_reading(value: Any) -> str:
    score = safe_number(value, 0)
    if score < 0.50:
        return "Fragile — contrôle humain renforcé"
    if score < 0.70:
        return "Acceptable — vérification recommandée"
    if score < 0.85:
        return "Bonne — quelques contrôles restent nécessaires"
    return "Très bonne — sans constituer une certitude juridique"


def _financial_status_fr(value: Any) -> str:
    return {
        "NOT_APPLICABLE": "NON APPLICABLE",
        "NON_APPLICABLE": "NON APPLICABLE",
        "UNVERIFIED": "À VÉRIFIER",
        "MISMATCH": "INCOHÉRENCE",
        "PASS": "CONFORME",
    }.get(safe_text(value).upper(), safe_text(value, "À VÉRIFIER"))


def _factual_status_fr(value: Any) -> str:
    return {
        "PASS": "CONFORME",
        "WARNING": "AVERTISSEMENT",
        "FAIL": "ÉCHEC",
        "UNKNOWN": "À VÉRIFIER",
        "INCONNU": "À VÉRIFIER",
    }.get(safe_text(value).upper(), safe_text(value, "À VÉRIFIER"))


def _review_priority(row: pd.Series) -> str:
    """Priorité opérationnelle de REVUE, distincte du score du moteur."""
    risk = safe_number(row.get("Score_Risque_IA"), 0)
    opportunity = safe_number(row.get("Score_Opportunité_IA"), 0)
    financial = safe_text(row.get("Statut_Contrôle_Capital")).upper()
    factual = safe_text(row.get("Statut_Validation_Factuelle")).upper()

    if risk >= 80 or financial == "MISMATCH" or factual == "FAIL":
        return "P1 — Immédiate"
    if risk >= 60 or opportunity >= 60 or factual == "WARNING":
        return "P2 — Prioritaire"
    if risk >= 30 or opportunity >= 30:
        return "P3 — À examiner"
    return "P4 — Surveillance"


def _department_owner(row: pd.Series) -> str:
    risk = safe_number(row.get("Score_Risque_IA"), 0)
    opportunity = safe_number(row.get("Score_Opportunité_IA"), 0)
    financial = safe_text(row.get("Statut_Contrôle_Capital")).upper()
    event = safe_text(row.get("Code_Événement_Principal")).upper()

    finance_events = {
        "SOUSCRIPTION_CAPITAL",
        "AUGMENTATION_CAPITAL",
        "VENTE_FONDS_COMMERCE",
        "VENTE_ENCHERES_SAISIE",
        "LOCATION_GERANCE",
    }
    legal_events = {
        "DISSOLUTION",
        "LIQUIDATION",
        "CLOTURE_LIQUIDATION",
        "REDRESSEMENT_JUDICIAIRE",
        "FAILLITE",
        "CLOTURE_FAILLITE",
        "AVIS_CREANCIERS",
        "NOMINATION_DIRIGEANT",
        "NOMINATION_COMMISSAIRE",
        "CHANGEMENT_GOUVERNANCE",
        "CONVOCATION_AGO",
        "CONVOCATION_AGE",
    }

    needs_finance = financial in {"PASS", "MISMATCH", "UNVERIFIED"} or event in finance_events or opportunity >= 60
    needs_legal = event in legal_events or risk >= 60

    if needs_finance and needs_legal:
        return "Juridique + Finance"
    if needs_finance:
        return "Finance"
    return "Juridique"


# =============================================================================
# Conversion d'une analyse en ligne d'export
# =============================================================================

def analysis_to_row(analysis: dict, pdf_name: str, index: int) -> dict:
    risk_score = get_first(analysis, "Score_Risque_IA", "score_risque", default=0)
    opportunity_score = get_first(
        analysis, "Score_Opportunité_IA", "score_opportunite", default=0
    )
    risk_level = get_first(
        analysis, "Niveau_Risque_IA", "niveau_risque", default="-"
    )
    opportunity_level = get_first(
        analysis, "Niveau_Opportunité_IA", "niveau_opportunite", default="-"
    )
    confidence = get_first(
        analysis, "Confiance_IA", "niveau_confiance", default=0
    )

    breakdown = analysis.get("score_breakdown", {})
    factual = analysis.get("validation_factuelle", {})
    financial = analysis.get("faits_financiers_valides", {})

    if not isinstance(breakdown, dict):
        breakdown = {}
    if not isinstance(factual, dict):
        factual = {}
    if not isinstance(financial, dict):
        financial = {}

    risks = get_first(
        analysis, "Risques_Détectés_IA", "risques_detectes", default=[]
    )
    opportunities = get_first(
        analysis,
        "Opportunités_Détectées_IA",
        "opportunites_detectees",
        default=[],
    )

    derived_risk = analysis.get("evaluation_risque_derivee", {})
    derived_opportunity = analysis.get("opportunite_potentielle_derivee", {})
    if not isinstance(derived_risk, dict):
        derived_risk = {}
    if not isinstance(derived_opportunity, dict):
        derived_opportunity = {}

    row = {
        "ID_Annonce": f"ANN-{index:04d}",
        "Date_Email": "Import PDF manuel",
        "Nom_PDF": pdf_name,
        "Société": safe_text(
            get_first(analysis, "Société", "societe", default="À vérifier")
        ),
        "Société_Source": safe_text(analysis.get("societe_source")),
        "Catégorie": safe_text(
            get_first(analysis, "Catégorie", "categorie", default="À vérifier")
        ),
        "Code_Événement_Principal": safe_text(
            analysis.get("type_evenement_code"), "AUTRE"
        ),
        "Type_Événement_IA": safe_text(
            get_first(
                analysis,
                "Type_Événement_IA",
                "type_evenement",
                default="À classifier manuellement",
            )
        ),
        "Événements_Secondaires": safe_text(
            analysis.get("evenements_secondaires", [])
        ),
        "Résumé_IA": safe_text(
            get_first(analysis, "Résumé_IA", "resume", default="")
        ),
        "Montant_Capital_Original": safe_text(financial.get("capital_original")),
        "Capital_Normalisé_TND": safe_number(financial.get("capital_tnd"), ""),
        "Nombre_Parts_Actions": (
            financial.get("share_count", "")
            if financial.get("share_count") is not None
            else ""
        ),
        "Valeur_Nominale_Originale": safe_text(
            financial.get("nominal_original")
        ),
        "Valeur_Nominale_TND": safe_number(financial.get("nominal_tnd"), ""),
        "Capital_Calculé_TND": safe_number(
            financial.get("computed_capital_tnd"), ""
        ),
        "Écart_Capital_TND": safe_number(financial.get("difference_tnd"), ""),
        "Statut_Contrôle_Capital": safe_text(
            financial.get("arithmetic_status"), "NON_APPLICABLE"
        ),
        "Période_Souscription": safe_text(
            financial.get("subscription_period")
        ),
        "Version_Parseur_Montants": safe_text(
            financial.get("parser_version"), "-"
        ),
        "Risques_Détectés_IA": safe_text(risks),
        "Preuves_Risques": _evidence_text(
            analysis.get("risques_avec_preuves", [])
        ),
        "Évaluation_Risque_Dérivée": safe_text(derived_risk.get("description")),
        "Base_Évaluation_Risque": safe_text(derived_risk.get("base")),
        "Opportunités_Détectées_IA": safe_text(opportunities),
        "Preuves_Opportunités": _evidence_text(
            analysis.get("opportunites_avec_preuves", [])
        ),
        "Opportunité_Potentielle_Dérivée": safe_text(
            derived_opportunity.get("description")
        ),
        "Base_Opportunité_Dérivée": safe_text(
            derived_opportunity.get("base")
        ),
        "Nature_Opportunité_Dérivée": safe_text(
            derived_opportunity.get("nature")
        ),
        "Score_Risque_IA": safe_number(risk_score, 0),
        "Niveau_Risque_IA": safe_text(risk_level, "-"),
        "Détail_Score_Risque": _breakdown_text(
            breakdown.get("risk_breakdown", [])
        ),
        "Score_Opportunité_IA": safe_number(opportunity_score, 0),
        "Niveau_Opportunité_IA": safe_text(opportunity_level, "-"),
        "Détail_Score_Opportunité": _breakdown_text(
            breakdown.get("opportunity_breakdown", [])
        ),
        "Portée_Score_Opportunité": safe_text(
            breakdown.get("opportunity_scope")
        ),
        "Action_Recommandée_IA": safe_text(
            get_first(
                analysis,
                "Action_Recommandée_IA",
                "action_recommandee",
                default="Vérifier manuellement le document.",
            )
        ),
        "Confiance_IA": safe_number(confidence, 0),
        "Confiance_Extraction": safe_number(
            analysis.get("confiance_extraction"), 0
        ),
        "Confiance_Interprétation": safe_number(
            analysis.get("confiance_interpretation"), 0
        ),
        "Plafond_Confiance_Interprétation": safe_number(
            analysis.get("plafond_confiance_interpretation"), 0
        ),
        "Raison_Plafond_Confiance": safe_text(
            analysis.get("raison_plafond_confiance"), "-"
        ),
        "Couverture_Preuves": safe_text(
            analysis.get("statut_couverture_preuves")
            if analysis.get("couverture_preuves") is None
            else analysis.get("couverture_preuves")
        ),
        "Scoring_Method": safe_text(
            get_first(
                analysis, "Scoring_Method", "scoring_method", default="-"
            )
        ),
        "Version_Scoring": safe_text(
            analysis.get("scoring_version"), "-"
        ),
        "Version_Analyseur": safe_text(
            analysis.get("analyzer_version"), "-"
        ),
        "Version_Validation_Factuelle": safe_text(
            factual.get("version"), "-"
        ),
        "Statut_Validation_Factuelle": safe_text(
            factual.get("status"), "INCONNU"
        ),
        "Corrections_Automatiques": _validation_text(
            factual.get("corrections", [])
        ),
        "Erreurs_Validation_Factuelle": _validation_text(
            factual.get("issues", [])
        ),
    }

    for column in TRACEABILITY_COLUMNS + CORRECTION_COLUMNS:
        row[column] = ""
    return row


def _ensure_columns(dataframe: pd.DataFrame) -> pd.DataFrame:
    result = dataframe.copy()
    for column in EXPORT_COLUMNS:
        if column not in result.columns:
            result[column] = ""
    return result[EXPORT_COLUMNS]


# =============================================================================
# Vues métier
# =============================================================================

def _summary_dataframe(dataframe: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []

    for _, row in dataframe.iterrows():
        rows.append(
            {
                "Référence": row["Référence_Annonce"],
                "Société": row["Société"],
                "Événement": row["Type_Événement_IA"],
                "Département pilote": _department_owner(row),
                "Priorité de revue": _review_priority(row),
                "Résumé factuel": row["Résumé_IA"],
                "Risque /100": row["Score_Risque_IA"],
                "Lecture du risque": _risk_reading(row["Score_Risque_IA"]),
                "Pourquoi ce risque ?": row["Détail_Score_Risque"],
                "Potentiel /100": row["Score_Opportunité_IA"],
                "Lecture du potentiel": _opportunity_reading(
                    row["Score_Opportunité_IA"]
                ),
                "Pourquoi ce potentiel ?": row["Détail_Score_Opportunité"],
                "Contrôle factuel": _factual_status_fr(
                    row["Statut_Validation_Factuelle"]
                ),
                "Contrôle financier": _financial_status_fr(
                    row["Statut_Contrôle_Capital"]
                ),
                "Fiabilité pipeline": row["Confiance_IA"],
                "Lecture fiabilité": _confidence_reading(row["Confiance_IA"]),
                "Action recommandée": row["Action_Recommandée_IA"],
                "Statut de revue": (
                    row["Statut_Revue"] if safe_text(row["Statut_Revue"])
                    else "À valider"
                ),
            }
        )

    return pd.DataFrame(rows)


def _legal_dataframe(dataframe: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for _, row in dataframe.iterrows():
        rows.append(
            {
                "Référence": row["Référence_Annonce"],
                "Société": row["Société"],
                "Événement": row["Type_Événement_IA"],
                "Priorité": _review_priority(row),
                "Risque /100": row["Score_Risque_IA"],
                "Lecture du risque": _risk_reading(row["Score_Risque_IA"]),
                "Détail du calcul": row["Détail_Score_Risque"],
                "Risques explicitement mentionnés": row["Risques_Détectés_IA"],
                "Preuves dans le document": row["Preuves_Risques"],
                "Évaluation de risque dérivée": row["Évaluation_Risque_Dérivée"],
                "Base de l’évaluation": row["Base_Évaluation_Risque"],
                "Validation factuelle": _factual_status_fr(
                    row["Statut_Validation_Factuelle"]
                ),
                "Corrections automatiques": row["Corrections_Automatiques"],
                "Points à revoir": row["Erreurs_Validation_Factuelle"],
                "Extrait source": row["Extrait_Source"],
                "Action recommandée": row["Action_Recommandée_IA"],
                "Fiabilité de l’interprétation": row["Confiance_Interprétation"],
            }
        )
    return pd.DataFrame(rows)


def _finance_dataframe(dataframe: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for _, row in dataframe.iterrows():
        rows.append(
            {
                "Référence": row["Référence_Annonce"],
                "Société": row["Société"],
                "Événement": row["Type_Événement_IA"],
                "Priorité": _review_priority(row),
                "Capital publié": row["Montant_Capital_Original"],
                "Capital normalisé (TND)": row["Capital_Normalisé_TND"],
                "Nb. parts/actions": row["Nombre_Parts_Actions"],
                "Valeur nominale": row["Valeur_Nominale_Originale"],
                "Valeur nominale (TND)": row["Valeur_Nominale_TND"],
                "Capital recalculé (TND)": row["Capital_Calculé_TND"],
                "Écart (TND)": row["Écart_Capital_TND"],
                "Contrôle financier": _financial_status_fr(
                    row["Statut_Contrôle_Capital"]
                ),
                "Période de souscription": row["Période_Souscription"],
                "Potentiel /100": row["Score_Opportunité_IA"],
                "Lecture du potentiel": _opportunity_reading(
                    row["Score_Opportunité_IA"]
                ),
                "Détail du calcul": row["Détail_Score_Opportunité"],
                "Opportunité explicite": row["Opportunités_Détectées_IA"],
                "Preuve": row["Preuves_Opportunités"],
                "Opportunité potentielle dérivée": row[
                    "Opportunité_Potentielle_Dérivée"
                ],
                "Portée / limites": row["Portée_Score_Opportunité"],
                "Validation factuelle": _factual_status_fr(
                    row["Statut_Validation_Factuelle"]
                ),
                "Action recommandée": row["Action_Recommandée_IA"],
            }
        )
    return pd.DataFrame(rows)


def _review_dataframe(dataframe: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "ID_Annonce", "Nom_PDF", "Référence_Annonce", "Société_Source",
        "Société", "Catégorie", "Type_Événement_IA", "Résumé_IA",
        "Risques_Détectés_IA", "Preuves_Risques",
        "Opportunités_Détectées_IA", "Preuves_Opportunités",
        "Évaluation_Risque_Dérivée", "Opportunité_Potentielle_Dérivée",
        "Score_Risque_IA", "Détail_Score_Risque",
        "Score_Opportunité_IA", "Détail_Score_Opportunité",
        "Action_Recommandée_IA", "Extrait_Source",
    ] + CORRECTION_COLUMNS

    review = dataframe[columns].copy()
    review["Statut_Revue"] = review["Statut_Revue"].replace("", "À valider")
    return review.rename(columns=FRENCH_HEADER_MAP)


def _legend_dataframe() -> pd.DataFrame:
    rows = [
        (
            "Score de risque 0–29",
            "Faible : surveillance normale. Le score mesure la criticité de l’événement détecté et de signaux explicites.",
        ),
        (
            "Score de risque 30–59",
            "Moyen / modéré : revue recommandée.",
        ),
        (
            "Score de risque 60–79",
            "Élevé : traitement prioritaire par l’équipe concernée.",
        ),
        (
            "Score de risque 80–100",
            "Critique : escalade / revue immédiate.",
        ),
        (
            "Potentiel d’opportunité 0–29",
            "Faible potentiel générique identifié.",
        ),
        (
            "Potentiel d’opportunité 30–59",
            "À examiner : potentiel à qualifier avec les critères UGFS.",
        ),
        (
            "Potentiel d’opportunité 60–79",
            "Intéressant : analyse métier prioritaire, sans constituer une recommandation d’investissement.",
        ),
        (
            "Potentiel d’opportunité ≥80",
            "Très élevé si un futur moteur UGFS le permet. Dans le baseline v5, le potentiel générique est plafonné à 75.",
        ),
        (
            "Fiabilité du pipeline",
            "Qualité technique de l’extraction + interprétation. Ce n’est PAS une probabilité de vérité juridique et elle ne modifie pas les scores métier.",
        ),
        (
            "CONFORME / PASS",
            "Le contrôle déterministe concerné a réussi.",
        ),
        (
            "INCOHÉRENCE / MISMATCH",
            "Les données financières publiées ne sont pas arithmétiquement cohérentes ; revue humaine obligatoire.",
        ),
        (
            "À VÉRIFIER / UNVERIFIED",
            "Une donnée nécessaire au contrôle manque.",
        ),
        (
            "NON APPLICABLE",
            "Le contrôle du capital n’est pas pertinent pour ce type d’événement.",
        ),
        (
            "Risque explicite",
            "Risque extrait seulement lorsqu’une preuve textuelle correspond au document source.",
        ),
        (
            "Risque dérivé",
            "Évaluation prudente issue du moteur de règles/validation ; elle n’est pas nécessairement écrite telle quelle dans le document.",
        ),
        (
            "Opportunité potentielle",
            "Déduction prudente de veille. Elle reste soumise à l’éligibilité, la stratégie, le secteur et les critères d’investissement UGFS.",
        ),
        (
            "Priorité P1/P2/P3/P4",
            "Couche de lecture ajoutée dans l’Excel pour organiser la revue. Elle n’est PAS un troisième score du modèle.",
        ),
        (
            "Revue humaine",
            "Compléter uniquement les cellules jaunes de Revue_humaine puis réimporter le fichier dans l’application.",
        ),
    ]
    return pd.DataFrame(rows, columns=["Terme", "Définition"])


def _methodology_event_dataframe() -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for event_code, (risk, opportunity, reason) in EVENT_BASE_SCORES.items():
        rows.append(
            {
                "Code événement": event_code,
                "Risque de base": risk,
                "Potentiel de base": opportunity,
                "Raison métier": reason,
            }
        )
    return pd.DataFrame(rows)


def _methodology_rules_dataframe() -> pd.DataFrame:
    rows = [
        (
            "Principe général",
            "Le LLM extrait/classifie les faits ; le moteur de scoring calcule ensuite le score numérique.",
            "Le score n’est donc pas une note librement inventée par Qwen.",
        ),
        (
            "Souscription secondaire",
            "+10 potentiel",
            "Si l’événement principal est CONSTITUTION_SOCIETE et qu’une SOUSCRIPTION_CAPITAL est détectée.",
        ),
        (
            "Délai explicite",
            "+5 risque",
            "Présence d’un délai légal/opérationnel explicite : « dans un délai », « au plus tard », « date limite », etc.",
        ),
        (
            "Intervention judiciaire",
            "+5 risque",
            "Tribunal, jugement, ordonnance, juge-commissaire ou administrateur judiciaire, hors événements déjà judiciaires.",
        ),
        (
            "Créanciers concernés",
            "+8 risque",
            "Mention explicite de créanciers/déclaration de créances, hors événements déjà classés AVIS_CREANCIERS ou REDRESSEMENT_JUDICIAIRE.",
        ),
        (
            "Risque avec preuve source",
            "+2 par élément ; max +6",
            "Uniquement pour les risques dont la citation a été retrouvée dans le texte source.",
        ),
        (
            "Opportunité avec preuve source",
            "+2 par élément ; max +6",
            "Uniquement pour les opportunités dont la citation a été retrouvée dans le texte source.",
        ),
        (
            "Plafond risque",
            "100",
            "Le score final déterministe ne dépasse jamais 100.",
        ),
        (
            "Plafond potentiel baseline",
            "75",
            "Le potentiel générique est volontairement plafonné tant que les critères d’investissement UGFS ne sont pas configurés.",
        ),
        (
            "OCR",
            "0 point métier",
            "La qualité OCR influence la fiabilité du pipeline, jamais directement le score de risque/opportunité.",
        ),
        (
            "Mode ML optionnel",
            "ml_regression_v5",
            "Utilisé uniquement si les modèles .joblib existent ET sont certifiés pour la même version de scoring. Sinon baseline_rules_v5.",
        ),
    ]
    return pd.DataFrame(rows, columns=["Règle", "Impact", "Explication"])


def _confidence_methodology_dataframe() -> pd.DataFrame:
    rows = [
        (
            "Complétude",
            "30 %",
            "Société, événement, catégorie et résumé présents/identifiés.",
        ),
        (
            "JSON valide",
            "20 %",
            "La réponse structurée du modèle respecte le format attendu.",
        ),
        (
            "Confiance LLM",
            "20 %",
            "Auto-évaluation du modèle sur extraction/classification, plafonnée.",
        ),
        (
            "Couverture des preuves",
            "15 %",
            "Part des affirmations risque/opportunité appuyées par une citation source.",
        ),
        (
            "Validation factuelle",
            "15 %",
            "Pénalise les anomalies et corrections importantes détectées par le validateur.",
        ),
        (
            "Confiance globale",
            "50 % extraction + 50 % interprétation",
            "Indicateur de qualité technique ; maximum global 95 %.",
        ),
        (
            "Plafond WARNING",
            "Interprétation ≤ 75 %",
            "Validation factuelle en avertissement.",
        ),
        (
            "Plafond FAIL",
            "Interprétation ≤ 50 %",
            "Échec de validation factuelle.",
        ),
        (
            "Contrôle financier UNVERIFIED",
            "Interprétation ≤ 80 %",
            "Données financières insuffisantes pour terminer le contrôle.",
        ),
        (
            "Contrôle financier MISMATCH",
            "Interprétation ≤ 70 %",
            "Incohérence arithmétique détectée.",
        ),
    ]
    return pd.DataFrame(rows, columns=["Composante", "Poids / plafond", "Sens"])


# =============================================================================
# Styles Excel
# =============================================================================

NAVY = "13294B"
BLUE = "0B5D86"
CYAN = "DDF3FC"
LIGHT_BLUE = "EAF3F8"
LIGHT_GREY = "F4F8FB"
LIGHT_YELLOW = "FFF2CC"
LIGHT_GREEN = "E2F0D9"
MEDIUM_GREEN = "C6E0B4"
LIGHT_ORANGE = "FCE4D6"
LIGHT_RED = "F4CCCC"
LIGHT_AMBER = "FFE699"
WHITE = "FFFFFF"
TEXT = "18314F"
MUTED = "71839A"
BORDER = Side(style="thin", color="D6E2EE")


def _apply_score_formatting(
    worksheet,
    header_row: int,
    header_names: dict[int, str],
) -> None:
    first_data_row = header_row + 1
    last_data_row = worksheet.max_row
    if last_data_row < first_data_row:
        return

    for col_idx, header in header_names.items():
        letter = get_column_letter(col_idx)
        target = f"{letter}{first_data_row}:{letter}{last_data_row}"

        is_risk = "Risque /100" in header or "Score de risque" in header
        is_opportunity = (
            "Potentiel /100" in header
            or "Potentiel d’opportunité" in header
            or "Score d’opportunité" in header
        )
        is_confidence = (
            "Fiabilité" in header
            or "Confiance" in header
        )

        if is_risk:
            worksheet.conditional_formatting.add(
                target,
                CellIsRule(
                    operator="lessThan",
                    formula=["30"],
                    fill=PatternFill("solid", fgColor=LIGHT_GREEN),
                ),
            )
            worksheet.conditional_formatting.add(
                target,
                CellIsRule(
                    operator="between",
                    formula=["30", "59.999"],
                    fill=PatternFill("solid", fgColor=LIGHT_AMBER),
                ),
            )
            worksheet.conditional_formatting.add(
                target,
                CellIsRule(
                    operator="between",
                    formula=["60", "79.999"],
                    fill=PatternFill("solid", fgColor=LIGHT_ORANGE),
                ),
            )
            worksheet.conditional_formatting.add(
                target,
                CellIsRule(
                    operator="greaterThanOrEqual",
                    formula=["80"],
                    fill=PatternFill("solid", fgColor=LIGHT_RED),
                ),
            )

        if is_opportunity:
            worksheet.conditional_formatting.add(
                target,
                CellIsRule(
                    operator="lessThan",
                    formula=["30"],
                    fill=PatternFill("solid", fgColor=LIGHT_GREY),
                ),
            )
            worksheet.conditional_formatting.add(
                target,
                CellIsRule(
                    operator="between",
                    formula=["30", "59.999"],
                    fill=PatternFill("solid", fgColor=LIGHT_AMBER),
                ),
            )
            worksheet.conditional_formatting.add(
                target,
                CellIsRule(
                    operator="greaterThanOrEqual",
                    formula=["60"],
                    fill=PatternFill("solid", fgColor=MEDIUM_GREEN),
                ),
            )

        if is_confidence:
            for cell in worksheet[letter][header_row:]:
                cell.number_format = "0.0%"


def _style_table_sheet(
    worksheet,
    title: str,
    header_row: int = 3,
    editable_headers: set[str] | None = None,
    subtitle_text: str | None = None,
) -> None:
    editable_headers = editable_headers or set()
    max_column = max(1, worksheet.max_column)
    last_letter = get_column_letter(max_column)

    worksheet.merge_cells(
        start_row=1, start_column=1, end_row=1, end_column=max_column
    )
    title_cell = worksheet.cell(1, 1)
    title_cell.value = title
    title_cell.fill = PatternFill("solid", fgColor=NAVY)
    title_cell.font = Font(color=WHITE, bold=True, size=15)
    title_cell.alignment = Alignment(horizontal="left", vertical="center")
    worksheet.row_dimensions[1].height = 30

    worksheet.merge_cells(
        start_row=2, start_column=1, end_row=2, end_column=max_column
    )
    subtitle = worksheet.cell(2, 1)
    subtitle.value = subtitle_text or (
        f"Généré le {datetime.now().strftime('%d/%m/%Y à %H:%M')} — "
        "Les scores sont des indicateurs de priorisation et nécessitent une revue humaine."
    )
    subtitle.fill = PatternFill("solid", fgColor=LIGHT_BLUE)
    subtitle.font = Font(color=NAVY, italic=True, size=10)
    subtitle.alignment = Alignment(
        horizontal="left", vertical="center", wrap_text=True
    )
    worksheet.row_dimensions[2].height = 30

    worksheet.freeze_panes = f"A{header_row + 1}"
    if worksheet.max_row >= header_row:
        worksheet.auto_filter.ref = (
            f"A{header_row}:{last_letter}{worksheet.max_row}"
        )
    worksheet.sheet_view.showGridLines = False

    header_names: dict[int, str] = {}
    for cell in worksheet[header_row]:
        header_names[cell.column] = str(cell.value or "")
        cell.fill = PatternFill("solid", fgColor=BLUE)
        cell.font = Font(color=WHITE, bold=True)
        cell.alignment = Alignment(
            horizontal="center", vertical="center", wrap_text=True
        )
        cell.border = Border(bottom=BORDER)
    worksheet.row_dimensions[header_row].height = 44

    text_keywords = (
        "Résumé", "Risque", "Opportunité", "Potentiel", "Action", "Preuve",
        "Base", "Détail", "Pourquoi", "Commentaire", "Extrait", "Correction",
        "Définition", "Explication", "Raison", "Portée", "Lecture",
    )
    narrow_keywords = (
        "Score", "/100", "Page", "Fiabilité", "Confiance",
        "Statut", "Nombre", "Nb.", "Écart", "Priorité",
    )

    for col_idx in range(1, max_column + 1):
        header = header_names.get(col_idx, "")
        letter = get_column_letter(col_idx)

        if any(keyword in header for keyword in text_keywords):
            width = 38
        elif any(keyword in header for keyword in narrow_keywords):
            width = 18
        elif header in {
            "Société", "Nom de société proposé",
            "Nom relevé dans le document",
            "Nom de société validé ou corrigé",
            "Catégorie métier", "Événement principal",
            "Événement", "Fichier PDF", "Département pilote",
        }:
            width = 28
        else:
            width = min(max(len(header) + 3, 13), 26)

        worksheet.column_dimensions[letter].width = width

    for row_idx in range(header_row + 1, worksheet.max_row + 1):
        worksheet.row_dimensions[row_idx].height = 62
        alternate = PatternFill(
            "solid", fgColor=LIGHT_GREY if row_idx % 2 == 0 else WHITE
        )

        for col_idx in range(1, max_column + 1):
            cell = worksheet.cell(row_idx, col_idx)
            header = header_names.get(col_idx, "")
            cell.alignment = Alignment(vertical="top", wrap_text=True)
            cell.border = Border(bottom=BORDER)
            cell.fill = (
                PatternFill("solid", fgColor=LIGHT_YELLOW)
                if header in editable_headers
                else alternate
            )

    _apply_score_formatting(worksheet, header_row, header_names)


def _write_kpis(worksheet, dataframe: pd.DataFrame) -> None:
    """Ajoute une bande KPI au-dessus du tableau de synthèse."""
    total = len(dataframe)

    risk_values = pd.to_numeric(
        dataframe.get("Risque /100", pd.Series(dtype=float)),
        errors="coerce",
    )
    opp_values = pd.to_numeric(
        dataframe.get("Potentiel /100", pd.Series(dtype=float)),
        errors="coerce",
    )

    avg_risk = round(float(risk_values.mean()), 1) if risk_values.notna().any() else 0
    avg_opp = round(float(opp_values.mean()), 1) if opp_values.notna().any() else 0

    priorities = dataframe.get(
        "Priorité de revue", pd.Series(dtype=str)
    ).astype(str)
    urgent = int(priorities.str.startswith(("P1", "P2")).sum())

    cards = [
        ("Documents analysés", total),
        ("Risque moyen", f"{avg_risk}/100"),
        ("Potentiel moyen", f"{avg_opp}/100"),
        ("Cas P1/P2", urgent),
    ]

    starts = [1, 5, 9, 13]
    for (label, value), start_col in zip(cards, starts):
        end_col = start_col + 2
        worksheet.merge_cells(
            start_row=3,
            start_column=start_col,
            end_row=3,
            end_column=end_col,
        )
        worksheet.merge_cells(
            start_row=4,
            start_column=start_col,
            end_row=4,
            end_column=end_col,
        )
        label_cell = worksheet.cell(3, start_col)
        value_cell = worksheet.cell(4, start_col)

        label_cell.value = label
        label_cell.fill = PatternFill("solid", fgColor=LIGHT_BLUE)
        label_cell.font = Font(color=NAVY, bold=True, size=10)
        label_cell.alignment = Alignment(horizontal="center", vertical="center")

        value_cell.value = value
        value_cell.fill = PatternFill("solid", fgColor=WHITE)
        value_cell.font = Font(color=NAVY, bold=True, size=16)
        value_cell.alignment = Alignment(horizontal="center", vertical="center")

        for row in (3, 4):
            for col in range(start_col, end_col + 1):
                worksheet.cell(row, col).border = Border(
                    left=BORDER, right=BORDER, top=BORDER, bottom=BORDER
                )

    worksheet.row_dimensions[3].height = 22
    worksheet.row_dimensions[4].height = 34


def _style_summary(worksheet, summary: pd.DataFrame) -> None:
    _style_table_sheet(
        worksheet,
        "Synthèse décisionnelle LegalTech",
        header_row=6,
        subtitle_text=(
            f"Généré le {datetime.now().strftime('%d/%m/%Y à %H:%M')} — "
            "Vue commune Direction / Juridique / Finance. "
            "Le potentiel d’opportunité n’est pas une recommandation d’investissement."
        ),
    )
    _write_kpis(worksheet, summary)

    # Priorités P1/P2/P3/P4.
    headers = {
        str(cell.value): cell.column
        for cell in worksheet[6]
        if cell.value is not None
    }
    priority_col = headers.get("Priorité de revue")
    if priority_col:
        letter = get_column_letter(priority_col)
        start = 7
        end = worksheet.max_row
        if end >= start:
            worksheet.conditional_formatting.add(
                f"{letter}{start}:{letter}{end}",
                CellIsRule(
                    operator="equal",
                    formula=['"P1 — Immédiate"'],
                    fill=PatternFill("solid", fgColor=LIGHT_RED),
                ),
            )


def _style_review(worksheet) -> None:
    editable = {FRENCH_HEADER_MAP[column] for column in CORRECTION_COLUMNS}
    _style_table_sheet(
        worksheet,
        "Revue humaine — compléter uniquement les cellules jaunes",
        editable_headers=editable,
        subtitle_text=(
            "Les colonnes jaunes sont réservées aux corrections humaines. "
            "Ne modifiez pas les colonnes générées automatiquement."
        ),
    )

    headers = {
        str(cell.value): cell.column
        for cell in worksheet[3]
        if cell.value is not None
    }

    if worksheet.max_row >= 4:
        status_col = headers.get("Statut de revue humaine")
        if status_col:
            dv_status = DataValidation(
                type="list",
                formula1='"À valider,Validé,Corrigé,Rejeté"',
                allow_blank=False,
            )
            worksheet.add_data_validation(dv_status)
            dv_status.add(
                f"{get_column_letter(status_col)}4:"
                f"{get_column_letter(status_col)}{worksheet.max_row}"
            )

        for score_header in (
            "Score de risque corrigé",
            "Potentiel d’opportunité corrigé",
        ):
            col = headers.get(score_header)
            if not col:
                continue
            dv_score = DataValidation(
                type="decimal",
                operator="between",
                formula1="0",
                formula2="100",
                allow_blank=True,
            )
            worksheet.add_data_validation(dv_score)
            dv_score.add(
                f"{get_column_letter(col)}4:"
                f"{get_column_letter(col)}{worksheet.max_row}"
            )


def _style_legend(worksheet) -> None:
    _style_table_sheet(
        worksheet,
        "Légende et règles de lecture",
        header_row=3,
        subtitle_text=(
            "Référentiel métier de lecture des scores, contrôles et priorités."
        ),
    )
    worksheet.column_dimensions["A"].width = 34
    worksheet.column_dimensions["B"].width = 105
    for row in worksheet.iter_rows(min_row=4):
        row[0].font = Font(bold=True, color=NAVY)
        row[1].alignment = Alignment(wrap_text=True, vertical="top")


def _style_methodology_sheet(
    worksheet,
    event_count: int,
    rules_header_row: int,
    confidence_header_row: int,
) -> None:
    worksheet.sheet_view.showGridLines = False

    worksheet.merge_cells("A1:D1")
    worksheet["A1"] = "Méthodologie du scoring LegalTech"
    worksheet["A1"].fill = PatternFill("solid", fgColor=NAVY)
    worksheet["A1"].font = Font(color=WHITE, bold=True, size=15)
    worksheet["A1"].alignment = Alignment(horizontal="left")
    worksheet.row_dimensions[1].height = 30

    worksheet.merge_cells("A2:D2")
    worksheet["A2"] = (
        f"Version moteur : {SCORING_VERSION} — "
        "Le LLM extrait les faits ; le moteur de scoring attribue les points. "
        "OCR = confiance uniquement."
    )
    worksheet["A2"].fill = PatternFill("solid", fgColor=LIGHT_BLUE)
    worksheet["A2"].font = Font(color=NAVY, italic=True)
    worksheet["A2"].alignment = Alignment(wrap_text=True)

    section_rows = [
        (4, "1. Scores de base par type d’événement"),
        (rules_header_row - 1, "2. Ajustements déterministes"),
        (confidence_header_row - 1, "3. Calcul de la fiabilité du pipeline"),
    ]

    for row_number, text in section_rows:
        worksheet.merge_cells(
            start_row=row_number,
            start_column=1,
            end_row=row_number,
            end_column=4,
        )
        cell = worksheet.cell(row_number, 1)
        cell.value = text
        cell.fill = PatternFill("solid", fgColor=CYAN)
        cell.font = Font(color=NAVY, bold=True, size=12)
        cell.alignment = Alignment(vertical="center")
        worksheet.row_dimensions[row_number].height = 24

    header_rows = [5, rules_header_row, confidence_header_row]
    for header_row in header_rows:
        for cell in worksheet[header_row]:
            if cell.value is None:
                continue
            cell.fill = PatternFill("solid", fgColor=BLUE)
            cell.font = Font(color=WHITE, bold=True)
            cell.alignment = Alignment(
                horizontal="center", vertical="center", wrap_text=True
            )

    for row in worksheet.iter_rows(min_row=6, max_row=worksheet.max_row):
        for cell in row:
            cell.alignment = Alignment(vertical="top", wrap_text=True)
            cell.border = Border(bottom=BORDER)

    worksheet.column_dimensions["A"].width = 30
    worksheet.column_dimensions["B"].width = 24
    worksheet.column_dimensions["C"].width = 24
    worksheet.column_dimensions["D"].width = 85

    # Risk / opportunity colors on event table.
    event_first = 6
    event_last = 5 + event_count
    if event_last >= event_first:
        worksheet.conditional_formatting.add(
            f"B{event_first}:B{event_last}",
            CellIsRule(
                operator="greaterThanOrEqual",
                formula=["80"],
                fill=PatternFill("solid", fgColor=LIGHT_RED),
            ),
        )
        worksheet.conditional_formatting.add(
            f"C{event_first}:C{event_last}",
            CellIsRule(
                operator="greaterThanOrEqual",
                formula=["60"],
                fill=PatternFill("solid", fgColor=MEDIUM_GREEN),
            ),
        )


# =============================================================================
# Export principal
# =============================================================================

def export_results(results: list[dict]) -> Path:
    OUTPUT_EXCEL_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    output_path = OUTPUT_EXCEL_DIR / (
        f"analyse_legaltech_metier_{timestamp}.xlsx"
    )

    detailed = _ensure_columns(pd.DataFrame(results))
    summary = _summary_dataframe(detailed)
    legal = _legal_dataframe(detailed)
    finance = _finance_dataframe(detailed)
    review = _review_dataframe(detailed)
    detailed_fr = detailed.rename(columns=FRENCH_HEADER_MAP)
    legend = _legend_dataframe()

    methodology_events = _methodology_event_dataframe()
    methodology_rules = _methodology_rules_dataframe()
    methodology_confidence = _confidence_methodology_dataframe()

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        # Synthèse : 2 lignes titre + KPI lignes 3-4 + ligne 5 espace +
        # en-têtes ligne 6.
        summary.to_excel(
            writer,
            index=False,
            sheet_name="Synthèse",
            startrow=5,
        )
        legal.to_excel(
            writer,
            index=False,
            sheet_name="Vue_Juridique",
            startrow=2,
        )
        finance.to_excel(
            writer,
            index=False,
            sheet_name="Vue_Finance",
            startrow=2,
        )
        detailed_fr.to_excel(
            writer,
            index=False,
            sheet_name="Analyse_détaillée",
            startrow=2,
        )
        review.to_excel(
            writer,
            index=False,
            sheet_name="Revue_humaine",
            startrow=2,
        )
        legend.to_excel(
            writer,
            index=False,
            sheet_name="Légende",
            startrow=2,
        )

        # Méthodologie : trois blocs successifs.
        methodology_events.to_excel(
            writer,
            index=False,
            sheet_name="Méthodologie_Scoring",
            startrow=4,
        )
        event_last_row = 5 + len(methodology_events)
        rules_section_row = event_last_row + 2
        rules_header_row = rules_section_row + 1
        methodology_rules.to_excel(
            writer,
            index=False,
            sheet_name="Méthodologie_Scoring",
            startrow=rules_header_row - 1,
        )

        rules_last_row = rules_header_row + len(methodology_rules)
        confidence_section_row = rules_last_row + 2
        confidence_header_row = confidence_section_row + 1
        methodology_confidence.to_excel(
            writer,
            index=False,
            sheet_name="Méthodologie_Scoring",
            startrow=confidence_header_row - 1,
        )

        # Styles.
        _style_summary(writer.sheets["Synthèse"], summary)

        _style_table_sheet(
            writer.sheets["Vue_Juridique"],
            "Vue Juridique — risques, preuves et contrôles",
            subtitle_text=(
                "Vue destinée à la revue juridique : criticité, preuves source, "
                "validation factuelle et actions à engager."
            ),
        )
        _style_table_sheet(
            writer.sheets["Vue_Finance"],
            "Vue Finance — cohérence des montants et potentiel",
            subtitle_text=(
                "Vue destinée à la Finance : montants normalisés, contrôle "
                "arithmétique, potentiel et limites d’interprétation."
            ),
        )
        _style_table_sheet(
            writer.sheets["Analyse_détaillée"],
            "Analyse détaillée et traçabilité technique",
            subtitle_text=(
                "Feuille d’audit : champs complets, versions, preuves, "
                "contrôles et informations techniques."
            ),
        )
        _style_review(writer.sheets["Revue_humaine"])
        _style_legend(writer.sheets["Légende"])
        _style_methodology_sheet(
            writer.sheets["Méthodologie_Scoring"],
            event_count=len(methodology_events),
            rules_header_row=rules_header_row,
            confidence_header_row=confidence_header_row,
        )

        # Couleurs des onglets.
        writer.sheets["Synthèse"].sheet_properties.tabColor = BLUE
        writer.sheets["Vue_Juridique"].sheet_properties.tabColor = "5B9BD5"
        writer.sheets["Vue_Finance"].sheet_properties.tabColor = "70AD47"
        writer.sheets["Méthodologie_Scoring"].sheet_properties.tabColor = "4472C4"
        writer.sheets["Analyse_détaillée"].sheet_properties.tabColor = NAVY
        writer.sheets["Revue_humaine"].sheet_properties.tabColor = "E6B800"
        writer.sheets["Légende"].sheet_properties.tabColor = "71839A"

    return output_path


# =============================================================================
# Réimport de la revue humaine
# =============================================================================

def read_corrected_excel(uploaded_file) -> pd.DataFrame:
    """Lire la feuille de revue et restaurer les noms internes attendus."""
    workbook = pd.ExcelFile(uploaded_file)

    if "Revue_humaine" in workbook.sheet_names:
        dataframe = pd.read_excel(
            workbook,
            sheet_name="Revue_humaine",
            header=2,
        )
    elif "Analyse_détaillée" in workbook.sheet_names:
        dataframe = pd.read_excel(
            workbook,
            sheet_name="Analyse_détaillée",
            header=2,
        )
    else:
        dataframe = pd.read_excel(uploaded_file)

    dataframe = dataframe.rename(columns=REVERSE_HEADER_MAP)
    return dataframe
