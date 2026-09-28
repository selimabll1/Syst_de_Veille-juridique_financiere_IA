"""Offline smoke tests for LegalTech financial validation v4.

Run from the project root:
    python -m scripts.test_financial_validation_v4

The test does not call Ollama and does not modify project data.
"""

from __future__ import annotations

from modules.fact_validator import VALIDATION_VERSION, validate_and_correct_analysis
from modules.scoring_engine import SCORING_VERSION, score_analysis
from modules.tunisian_amount_parser import (
    AMOUNT_PARSER_VERSION,
    format_tnd,
    parse_tunisian_amount,
)


NEAPOLIS = """
Dénomination sociale de la société : Société Communautaire Régionale Neapolis
Forme juridique de la société : Société Régionale
Montant du capital social ouvert à la souscription : 15000,000 dinars
Nombre de parts sociales à souscrire : 15 parts
Valeur nominale de la part sociale : 1000,000 dinars
Période d'ouverture de la souscription : Du 11/05/2026 au 29/05/2026
Convocation à l'assemblée générale constitutive : Via la plateforme
"""

AL_KUNUZ = """
Nom de la société : Société Communautaire locale agricole AI-Kunuz
Classification de la société : Locale
Montant du capital social souscrit : 5000 dinars tunisiens (TND)
Nombre d'actions nominales à souscrire : 15
Valeur nominale des actions : 33,333 TND
Période de souscription : Du 8 mai 2026 au 13 mai 2026
Convocation à l'assemblée générale constitutive : via la plateforme
"""

EL_FATH = """
Dénomination de la société communautaire : Société communautaire régionale El Fath
Catégorie de la Société : Régionale
Montant du capital de la société souscrit : 23000.000Dt
Nombre de parts nominales qui seront souscrites : 15
Valeur nominale des parts : 1533.33DT
Délai ouvert de la souscription : Du 11/05/2026 au 21/05/2026
Convocation à l'assemblée constitutive : Via la plateforme
"""


def base_analysis() -> dict:
    return {
        "societe": "À vérifier",
        "categorie": "À classifier manuellement",
        "type_evenement": "À classifier manuellement",
        "type_evenement_code": "AUTRE",
        "resume": "Résumé provisoire incorrect avec 1 000 000 dinars.",
        "risques_detectes": [],
        "opportunites_detectees": [],
        "risques_avec_preuves": [],
        "opportunites_avec_preuves": [],
        "action_recommandee": "Examiner",
        "niveau_confiance_llm": 1.0,
        "ocr_quality": 0.95,
        "json_valid": True,
    }


def main() -> None:
    assert parse_tunisian_amount("15000,000 dinars") == parse_tunisian_amount("15000")
    assert format_tnd(parse_tunisian_amount("1 000,000 dinars")) == "1 000 TND"
    assert format_tnd(parse_tunisian_amount("23000.000 DT")) == "23 000 TND"

    neapolis = score_analysis(base_analysis(), NEAPOLIS)
    neapolis_finance = neapolis["faits_financiers_valides"]
    assert neapolis["type_evenement_code"] == "CONSTITUTION_SOCIETE"
    assert neapolis_finance["capital_tnd"] == 15000.0
    assert neapolis_finance["nominal_tnd"] == 1000.0
    assert neapolis_finance["share_count"] == 15
    assert neapolis_finance["arithmetic_status"] == "PASS"
    assert "1 000 TND" in neapolis["resume"]
    assert "1 000 000" not in neapolis["resume"]
    assert neapolis["confiance_interpretation"] <= 0.95

    al_kunuz = score_analysis(base_analysis(), AL_KUNUZ)
    al_kunuz_finance = al_kunuz["faits_financiers_valides"]
    assert al_kunuz["categorie"] == "Société communautaire locale"
    assert al_kunuz_finance["arithmetic_status"] == "MISMATCH"
    assert al_kunuz["validation_factuelle"]["status"] == "WARNING"
    assert al_kunuz["confiance_interpretation"] <= 0.70

    el_fath = score_analysis(base_analysis(), EL_FATH)
    el_fath_finance = el_fath["faits_financiers_valides"]
    assert el_fath_finance["capital_tnd"] == 23000.0
    assert el_fath_finance["arithmetic_status"] == "PASS"

    print("LEGALTECH FINANCIAL VALIDATION V4 OK")
    print(f"Parser: {AMOUNT_PARSER_VERSION}")
    print(f"Validator: {VALIDATION_VERSION}")
    print(f"Scoring: {SCORING_VERSION}")
    print("Neapolis: PASS | 15 × 1 000 TND = 15 000 TND")
    print("Al-Kunuz: WARNING | published amounts are arithmetically inconsistent")
    print("El Fath: PASS | rounding difference accepted")


if __name__ == "__main__":
    main()
