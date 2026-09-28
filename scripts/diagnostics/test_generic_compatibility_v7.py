"""Offline checks that production selection and validation are PDF-agnostic."""

from __future__ import annotations

from pathlib import Path

from modules.fact_validator import (
    VALIDATION_VERSION,
    extract_company_name,
    infer_primary_event,
    validate_and_correct_analysis,
)
from modules.sample_selector import SAMPLE_SELECTOR_VERSION, select_diverse_segments


def _base_analysis() -> dict:
    return {
        "societe": "À vérifier",
        "categorie": "À classifier manuellement",
        "type_evenement": "À classifier manuellement",
        "type_evenement_code": "AUTRE",
        "resume": "Résumé provisoire.",
        "risques_detectes": [],
        "opportunites_detectees": [],
        "risques_avec_preuves": [],
        "opportunites_avec_preuves": [],
        "action_recommandee": "Examiner",
        "niveau_confiance_llm": 0.8,
        "ocr_quality": 0.9,
        "json_valid": True,
    }


def main() -> None:
    synthetic_segments = [
        {
            "announcement_id": "REF-A",
            "text": (
                "Dénomination sociale : Société Exemple Horizon "
                "Capital social : 10 000,000 TND "
                "Nombre de parts sociales à souscrire : 10 "
                "Valeur nominale : 1 000,000 TND "
                "Assemblée générale constitutive."
            ),
        },
        {
            "announcement_id": "REF-B",
            "text": "La société Exemple Delta a décidé sa dissolution anticipée et sa mise en liquidation.",
        },
        {
            "announcement_id": "REF-C",
            "text": "Désignation d'un commissaire aux comptes pour trois exercices.",
        },
        {
            "announcement_id": "REF-D",
            "text": "Vente aux enchères publiques d'un immeuble saisi.",
        },
        {
            "announcement_id": "REF-E",
            "text": "Annonce juridique sans catégorie déterminable.",
        },
    ]

    selected, codes = select_diverse_segments(synthetic_segments, max_segments=5)
    assert len(selected) == 5
    assert "CONSTITUTION_SOCIETE" in codes
    assert "LIQUIDATION" in codes
    assert "NOMINATION_COMMISSAIRE" in codes
    assert "VENTE_ENCHERES_SAISIE" in codes

    name = extract_company_name(synthetic_segments[0]["text"])
    assert name == "Société Exemple Horizon", name

    result = validate_and_correct_analysis(_base_analysis(), synthetic_segments[0]["text"])
    assert result["type_evenement_code"] == "CONSTITUTION_SOCIETE"
    financial = result["faits_financiers_valides"]
    assert financial["arithmetic_status"] == "PASS"
    assert financial["capital_tnd"] == 10000.0

    production_paths = [
        Path("app.py"),
        Path("modules/fact_validator.py"),
        Path("modules/sample_selector.py"),
    ]
    forbidden_tokens = [
        "MIXED_BUSINESS_SAMPLE_REFERENCES",
        "Références ciblées non trouvées",
    ]
    for path in production_paths:
        content = path.read_text(encoding="utf-8")
        for token in forbidden_tokens:
            assert token not in content, f"Hard-coded selector found in {path}: {token}"

    print("LEGALTECH GENERIC COMPATIBILITY V7 OK")
    print("Validator:", VALIDATION_VERSION)
    print("Selector:", SAMPLE_SELECTOR_VERSION)
    print("Detected event codes:", ", ".join(codes))


if __name__ == "__main__":
    main()
