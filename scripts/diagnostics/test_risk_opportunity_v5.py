
from modules.fact_validator import VALIDATION_VERSION
from modules.llm_analyzer import ANALYZER_VERSION
from modules.scoring_engine import SCORING_VERSION, score_analysis


SOURCE = """
CONSTITUTION DE SOCIETES
La dénomination sociale de la société : Société Communautaire Régionale Neapolis
Classification de la société : Régionale
Montant du capital social ouvert à la souscription : 15000,000 dinars
Nombre de parts sociales à souscrire : 15
Valeur nominale de la part sociale : 1000,000 dinars
Période de souscription : Du 11/05/2026 au 29/05/2026
Assemblée générale constitutive.
"""

analysis = {
    "societe": "Neapolis",
    "categorie": "Société communautaire",
    "type_evenement": "Constitution",
    "type_evenement_code": "CONSTITUTION_SOCIETE",
    "resume": "Résumé provisoire.",
    "action_recommandee": "Examiner",
    "niveau_confiance_llm": 0.9,
    "ocr_quality": 0.95,
    "json_valid": True,
    "risques_detectes": [],
    "opportunites_detectees": [],
    "risques_avec_preuves": [],
    "opportunites_avec_preuves": [],
}

result = score_analysis(analysis, SOURCE)

assert ANALYZER_VERSION == "legaltech_analyzer_v5"
assert SCORING_VERSION == "legaltech_scoring_v5"
assert VALIDATION_VERSION == "fact_validation_v3"
assert result["scoring_method"] == "baseline_rules_v5"
assert result["score_risque"] == 20
assert result["score_opportunite"] == 45
assert result["faits_financiers_valides"]["arithmetic_status"] == "PASS"
assert "le capital social annoncé de 15 000 TND" in result["action_recommandee"]

risk = result.get("evaluation_risque_derivee", {})
opportunity = result.get("opportunite_potentielle_derivee", {})

assert risk.get("description")
assert risk.get("score") == 20
assert opportunity.get("description")
assert opportunity.get("score") == 45
assert "29/05/2026" in opportunity["description"]
assert "sous réserve" in opportunity["description"]

print("LEGALTECH RISK / OPPORTUNITY V5 OK")
print("Analyzer:", ANALYZER_VERSION)
print("Scoring:", SCORING_VERSION)
print("Validator:", VALIDATION_VERSION)
print("Risk assessment:", risk["description"])
print("Potential opportunity:", opportunity["description"])
