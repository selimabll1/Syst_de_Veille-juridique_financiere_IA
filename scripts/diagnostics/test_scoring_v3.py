"""Quick verification for the LegalTech v3 analysis/scoring patch."""

from modules.fact_validator import VALIDATION_VERSION, validate_and_correct_analysis
from modules.llm_analyzer import ANALYZER_VERSION
from modules.scoring_engine import SCORING_VERSION, baseline_scores


def main() -> None:
    source = """
    AVIS AU PUBLIC
    Dénomination sociale de la société : Société Test Régionale
    Forme juridique de la société : Société Régionale
    Montant du capital social ouvert à la souscription : 15000,000 dinars
    Date de dépôt du projet de statuts : 20/04/2026
    Période de souscription du 11/05/2026 au 29/05/2026.
    Convocation à l'assemblée générale constitutive.
    """
    raw = {
        "societe": "Société Test",
        "categorie": "CONSTITUTION_SOCIETE",
        "type_evenement": "AGO",
        "type_evenement_code": "CONVOCATION_AGO",
        "resume": "Constitution de Société Test avec des fondateurs.",
        "action_recommandee": "Souscription de la société",
        "risques_detectes": [],
        "opportunites_detectees": [],
        "risques_avec_preuves": [],
        "opportunites_avec_preuves": [],
    }

    corrected = validate_and_correct_analysis(raw, source)
    risk, opportunity, explanation = baseline_scores(corrected, source)

    assert ANALYZER_VERSION == "legaltech_analyzer_v3"
    assert SCORING_VERSION == "legaltech_scoring_v3"
    assert VALIDATION_VERSION == "fact_validation_v1"
    assert corrected["type_evenement_code"] == "CONSTITUTION_SOCIETE"
    assert "CONVOCATION_ASSEMBLEE_CONSTITUTIVE" in corrected["evenements_secondaires"]
    assert corrected["categorie"] == "Société régionale"
    assert risk == 20
    assert opportunity == 45
    assert explanation["ocr_used_in_business_scores"] is False

    print("LEGALTECH V3 PATCH OK")
    print(f"Analyzer: {ANALYZER_VERSION}")
    print(f"Scoring: {SCORING_VERSION}")
    print(f"Factual validation: {VALIDATION_VERSION}")
    print(f"Primary event: {corrected['type_evenement_code']}")
    print(f"Risk / opportunity: {risk} / {opportunity}")


if __name__ == "__main__":
    main()
