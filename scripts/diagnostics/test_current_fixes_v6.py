"""Tests hors ligne du correctif LegalTech v6.

Commande :
    python -m scripts.test_current_fixes_v6
"""

from modules.fact_validator import VALIDATION_VERSION
from modules.scoring_engine import SCORING_VERSION, score_analysis
from modules.tunisian_amount_parser import AMOUNT_PARSER_VERSION


def _base_analysis() -> dict:
    return {
        "societe": "À vérifier",
        "categorie": "À vérifier",
        "type_evenement_code": "AUTRE",
        "type_evenement": "À classifier manuellement",
        "resume": "Résumé provisoire.",
        "action_recommandee": "Examiner",
        "risques_detectes": [],
        "opportunites_detectees": [],
        "risques_avec_preuves": [],
        "opportunites_avec_preuves": [],
        "niveau_confiance_llm": 0.85,
        "ocr_quality": 0.95,
        "json_valid": True,
    }


def main() -> None:
    intissar = """
    Constitution d'une Société Communautaire Locale.
    Dénomination sociale de la société Civile: Société Communautaire Locale El lntissar
    Type de société : Locale
    Montant du capital social souscrit: 5 000 dinars
    Nombre d'actions à souscrire: 100 actions
    Valeur nominale des actions: 50 dinars
    Période de souscription : Du 28/04/2026 au 08/05/2026
    Convocation de l'assemblée générale constitutive : par la plateforme
    """
    result = score_analysis(_base_analysis(), intissar)
    financial = result["faits_financiers_valides"]
    assert result["societe"] == "Société Communautaire Locale El Intissar"
    assert financial["share_count"] == 100
    assert financial["capital_tnd"] == 5000.0
    assert financial["nominal_tnd"] == 50.0
    assert financial["arithmetic_status"] == "PASS"

    nokhba = """
    Avis au public.
    Dénomination sociale : Société communautaire locale Al-Nokhba
    Type de société : Locale
    Capital social souscrit : Cinq mille dinars tunisiens (5 000 TND)
    Nombre d'actions nominales à souscrire : 10
    Valeur nominale des actions : 500 dinars tunisiens
    Période de souscription : Du 01/05/2026 au 15/05/2026
    Convocation à l'assemblée générale constitutive : Via la plateforme
    """
    result = score_analysis(_base_analysis(), nokhba)
    financial = result["faits_financiers_valides"]
    assert financial["capital_tnd"] == 5000.0
    assert financial["share_count"] == 10
    assert financial["nominal_tnd"] == 500.0
    assert financial["arithmetic_status"] == "PASS"

    auditor = """
    GESTION DE SOCIETES. Homologation de résolutions. SOCIETES ANONYMES.
    Société Nationale de Cellulose et de Papier Alfa
    Le siège social : Avenue Habib Bourguiba, Kasserine
    Le capital : 19 806 230 dinars
    La forme juridique : Société Anonyme
    L'Assemblée Générale Ordinaire a décidé la désignation du cabinet PAC
    représenté par Monsieur Zouhair Merghli en tant que Commissaire aux comptes
    de la société pour les exercices 2025-2026-2027.
    """
    result = score_analysis(_base_analysis(), auditor)
    assert result["type_evenement_code"] == "NOMINATION_COMMISSAIRE"
    assert result["categorie"] == "Société anonyme — homologation de résolutions"
    assert result["faits_financiers_valides"]["arithmetic_status"] == "NOT_APPLICABLE"
    assert "cabinet PAC" in result["resume"]
    assert "exercices 2025–2026–2027" in result["action_recommandee"]
    assert result["raison_plafond_confiance"] != "Contrôle financier: UNVERIFIED"

    assert SCORING_VERSION == "legaltech_scoring_v6"
    assert VALIDATION_VERSION == "fact_validation_v4"
    assert AMOUNT_PARSER_VERSION == "tunisian_amount_parser_v2"

    print("LEGALTECH CURRENT FIXES V6 OK")
    print("SCORING:", SCORING_VERSION)
    print("VALIDATOR:", VALIDATION_VERSION)
    print("PARSER:", AMOUNT_PARSER_VERSION)
    print("El Intissar: PASS | 100 × 50 TND = 5 000 TND")
    print("Al-Nokhba: PASS | montant entre parenthèses correctement extrait")
    print("Commissaire aux comptes: contrôle financier NON APPLICABLE")


if __name__ == "__main__":
    main()
