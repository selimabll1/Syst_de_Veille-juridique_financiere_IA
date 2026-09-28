"""Deterministic factual validation and correction for LegalTech analyses.

This module corrects high-impact facts after the local LLM response. It is the
source of truth for event classification, company/category normalization,
Tunisian currency parsing and capital arithmetic checks.
"""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Any

from modules.tunisian_amount_parser import (
    AMOUNT_PARSER_VERSION,
    compare_capital_arithmetic,
    extract_labeled_amount,
    format_tnd,
)


VALIDATION_VERSION = "fact_validation_v5_generic"

PRIMARY_EVENT_LABELS: dict[str, str] = {
    "CONSTITUTION_SOCIETE": "Constitution d'une société",
    "SOUSCRIPTION_CAPITAL": "Souscription au capital",
    "AUGMENTATION_CAPITAL": "Augmentation de capital",
    "DISSOLUTION": "Dissolution",
    "LIQUIDATION": "Liquidation",
    "CLOTURE_LIQUIDATION": "Clôture de liquidation",
    "REDRESSEMENT_JUDICIAIRE": "Redressement judiciaire",
    "FAILLITE": "Faillite",
    "CLOTURE_FAILLITE": "Clôture de faillite",
    "VENTE_FONDS_COMMERCE": "Vente d'un fonds de commerce",
    "LOCATION_GERANCE": "Location-gérance",
    "VENTE_ENCHERES_SAISIE": "Vente aux enchères / saisie",
    "AVIS_CREANCIERS": "Avis aux créanciers",
    "NOMINATION_DIRIGEANT": "Nomination d'un dirigeant",
    "NOMINATION_COMMISSAIRE": "Nomination d'un commissaire aux comptes",
    "CHANGEMENT_GOUVERNANCE": "Changement de gouvernance",
    "CONVOCATION_AGO": "Convocation à une assemblée générale ordinaire",
    "CONVOCATION_AGE": "Convocation à une assemblée générale extraordinaire",
    "CONSTITUTION_ASSOCIATION": "Constitution d'une association",
    "RECTIFICATIF": "Rectificatif",
    "AUTRE": "À classifier manuellement",
}

ALLOWED_ACTION_VERBS = (
    "vérifier",
    "analyser",
    "surveiller",
    "contacter",
    "escalader",
    "archiver",
    "examiner",
    "confirmer",
    "contrôler",
)

DATE_TOKEN = (
    r"(?:\d{1,2}/\d{1,2}/\d{4}|"
    r"\d{1,2}\s+(?:janvier|février|fevrier|mars|avril|mai|juin|juillet|"
    r"août|aout|septembre|octobre|novembre|décembre|decembre)\s+\d{4})"
)

CAPITAL_CONTROL_EVENTS = {
    "CONSTITUTION_SOCIETE",
    "SOUSCRIPTION_CAPITAL",
    "AUGMENTATION_CAPITAL",
}


def _flat(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _norm(text: str) -> str:
    value = _flat(text).casefold().replace("’", "'")
    return value


def _clean_entity(value: str) -> str:
    """Clean spacing and punctuation without changing a proper name."""
    cleaned = _flat(value).strip(" :;,.")
    cleaned = re.sub(r"\s+-\s+", "-", cleaned)
    cleaned = re.sub(r"\s*:\s*", " : ", cleaned)
    return re.sub(r"\s{2,}", " ", cleaned).strip()


def normalize_company_display_name(value: str) -> str:
    """Normalize a company name conservatively and generically.

    No company name, publication reference or OCR correction is hard-coded.
    The source spelling is preserved separately by ``validate_and_correct_analysis``.
    """
    cleaned = _clean_entity(value)
    cleaned = re.split(
        r"\s+(?=(?:Forme juridique|Classification(?: de la société| des entreprises)?|"
        r"Catégorie de la Société|Type de Société|Montant du capital|Capital Social|"
        r"Adresse du siège|Objet social|Date de dépôt|Nombre de parts|Valeur nominale))",
        cleaned,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]

    # Collapse an accidentally duplicated legal-form prefix while preserving
    # the actual company name and every non-generic token.
    legal_form = (
        r"Société(?:\s+Civile)?(?:\s+Communautaire)?"
        r"(?:\s+(?:Locale|Régionale))?"
    )
    cleaned = re.sub(
        rf"^({legal_form})\s+\1\s+",
        r"\1 ",
        cleaned,
        flags=re.IGNORECASE,
    )
    return re.sub(r"\s{2,}", " ", cleaned).strip()

def _first_match(text: str, patterns: list[str]) -> str:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return _clean_entity(match.group(1))
    return ""


def extract_company_name(source_text: str) -> str:
    """Extract a company/entity name from common legal-publication labels.

    The rules are label-based and do not depend on a known company or PDF.
    """
    text = _flat(source_text)
    stop = (
        r"(?=\s+(?:Forme juridique|Classification(?: de la société| des entreprises)?|"
        r"Catégorie de la Société|Type de Société|Montant du capital|"
        r"Le montant du capital|Capital Social|Capital social|Le capital|"
        r"Adresse du siège|Siège Social|Le siège social|"
        r"Objet social|Objet de l'activité|Sujet d'activité|Durée de la société|"
        r"La période désignée|Date de dépôt|Nombre (?:de|d')|Valeur nominale))"
    )

    direct_patterns = [
        rf"Dénomination sociale de la société\s*(?:Civile\s*)?:\s*(.+?){stop}",
        rf"Dénomination sociale\s*:\s*(.+?){stop}",
        rf"Dénomination de la société communautaire\s*:\s*(.+?){stop}",
        rf"Nom\s+de\s+la\s+société\s*:\s*(.+?){stop}",
        rf"Dénomination de la société\s*:\s*(.+?){stop}",
        rf"Dénomination Sociale\s*:\s*(.+?){stop}",
        rf"Raison sociale\s*:\s*(.+?){stop}",
        rf"Nom commercial\s*:\s*(.+?){stop}",
    ]
    direct = _first_match(text, direct_patterns)
    if direct:
        return direct

    # Headings used for sociétés anonymes and similar legal forms.
    heading_match = re.search(
        r"SOCI[ÉE]T[ÉE]S?\s+(?:ANONYMES?|À RESPONSABILITÉ LIMITÉE|"
        r"UNIPERSONNELLES?)\s+(.+?)\s+(?:Le siège social|Siège social)\s*:",
        text,
        flags=re.IGNORECASE,
    )
    if heading_match:
        return _clean_entity(heading_match.group(1))

    # Generic form: « La dénomination sociale de la société X : Y ».
    qualified = re.search(
        rf"La dénomination sociale de la société\s+(.+?)\s*:\s*(.+?){stop}",
        text,
        flags=re.IGNORECASE,
    )
    if qualified:
        qualifier = _clean_entity(qualified.group(1))
        name = _clean_entity(qualified.group(2))
        generic_qualifiers = {
            "civile", "communautaire", "locale", "régionale", "regionale",
            "anonyme", "commerciale",
        }
        if qualifier.casefold() in generic_qualifiers:
            return name
        return f"{qualifier} : {name}" if qualifier and name else name or qualifier

    return ""

def _extract_explicit_category(source_text: str) -> str:
    text = _flat(source_text)
    patterns = [
        r"Classification de la société\s*:\s*(Locale|Régionale|Regionale)",
        r"Classification des entreprises\s*:\s*(Locale|Régionale|Regionale)",
        r"Catégorie de la Société\s*:\s*(Locale|Régionale|Regionale)",
        r"Type de Société\s*:\s*(Locale|Régionale|Regionale)",
        r"Type de société\s*:\s*(Locale|Régionale|Regionale)",
        r"Forme juridique de la société\s*:\s*Société\s+(Locale|Régionale|Regionale)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            value = match.group(1).casefold()
            return "Régionale" if value.startswith("r") else "Locale"
    return ""


def infer_category(
    source_text: str,
    company_name: str,
    current: str = "",
    event_code: str = "",
) -> str:
    explicit = _extract_explicit_category(source_text)
    company = _norm(company_name)
    source = _norm(source_text)

    is_community = "société communautaire" in company or "société communautaire" in source
    is_civil_local = "société civile locale" in company or "société civile locale" in source

    if event_code == "NOMINATION_COMMISSAIRE" and (
        "société anonyme" in source or "sociétés anonymes" in source
    ):
        if "homologation de résolutions" in source:
            return "Société anonyme — homologation de résolutions"
        return "Société anonyme — contrôle légal des comptes"

    if event_code == "NOMINATION_DIRIGEANT" and (
        "société anonyme" in source or "s.a" in source
    ):
        return "Société anonyme — gouvernance"

    if explicit == "Régionale":
        return "Société communautaire régionale" if is_community else "Société régionale"
    if explicit == "Locale":
        if is_civil_local:
            return "Société civile locale"
        return "Société communautaire locale" if is_community else "Société locale"

    if "société communautaire régionale" in company:
        return "Société communautaire régionale"
    if "société communautaire locale" in company:
        return "Société communautaire locale"
    if is_civil_local:
        return "Société civile locale"
    if is_community:
        return "Société communautaire"

    current_clean = _clean_entity(current)
    if current_clean and "_" not in current_clean:
        return current_clean
    return "À classifier manuellement"


def _constitution_signal_count(text: str) -> int:
    patterns = [
        r"constitution de\s+soci[ée]t[ée]s?",
        r"avis au public",
        r"avis public",
        r"d[ée]nomination .*soci[ée]t[ée]",
        r"nom .*soci[ée]t[ée]",
        r"date de d[ée]p[oô]t .*statut",
        r"projet de (?:statuts?|contrat constitutif)",
        r"capital social .*souscription",
        r"nombre .*parts? nominales?",
        r"nombre .*actions? nominales?",
        r"assembl[ée]e g[ée]n[ée]rale constitutive",
        r"liste des fondateurs",
        r"dur[ée]e de la soci[ée]t[ée]",
    ]
    return sum(bool(re.search(pattern, text)) for pattern in patterns)


def infer_primary_event(source_text: str, llm_code: str = "") -> tuple[str, str]:
    """Infer the primary legal event using ordered high-precision rules."""
    text = _norm(source_text)
    ordered: list[tuple[str, list[str]]] = [
        ("CLOTURE_FAILLITE", [r"cl[oô]ture de (?:la )?faillite"]),
        ("CLOTURE_LIQUIDATION", [r"cl[oô]ture .*liquidation", r"fin .*travaux de liquidation"]),
        ("REDRESSEMENT_JUDICIAIRE", [r"redressement judiciaire", r"p[ée]riode d'observation"]),
        ("VENTE_ENCHERES_SAISIE", [r"vente aux ench[eè]res", r"saisie immobili[eè]re", r"adjudication"]),
        ("VENTE_FONDS_COMMERCE", [r"vente d'un fonds de commerce", r"cession d'un fonds de commerce", r"donation d'un fonds de commerce"]),
        ("LOCATION_GERANCE", [r"location.?g[ée]rance", r"g[ée]rance libre"]),
        ("AUGMENTATION_CAPITAL", [r"augmentation du capital"]),
        ("LIQUIDATION", [r"mise en liquidation", r"liquidation anticip[ée]e", r"nomm[ée].*liquidateur"]),
        ("DISSOLUTION", [r"dissolution anticip[ée]e", r"d[ée]cision de dissolution"]),
        ("FAILLITE", [r"d[ée]clar[ée].*faillite", r"jugement de faillite", r"proc[ée]dure de faillite"]),
        ("AVIS_CREANCIERS", [r"avis aux cr[ée]anciers", r"d[ée]clarer leurs cr[ée]ances", r"produire leurs titres de cr[ée]ances"]),
        ("NOMINATION_COMMISSAIRE", [r"nomination .*commissaire aux comptes", r"d[ée]signation .*commissaire aux comptes"]),
        ("NOMINATION_DIRIGEANT", [r"nomination .*directeur", r"nomination .*g[ée]rant", r"administrateur d[ée]l[ée]gu[ée]"]),
        ("CONSTITUTION_ASSOCIATION", [r"constitution d'une association", r"d[ée]claration de constitution d'une association"]),
        ("RECTIFICATIF", [r"rectificatif"]),
    ]

    for code, patterns in ordered:
        if any(re.search(pattern, text) for pattern in patterns):
            return code, f"Règle textuelle forte: {code}"

    if re.search(r"assembl[ée]e g[ée]n[ée]rale constitutive|assembl[ée]e constitutive|assembl[ée]e g[ée]n[ée]rale fondatrice", text):
        return "CONSTITUTION_SOCIETE", "Assemblée constitutive détectée"
    if _constitution_signal_count(text) >= 3:
        return "CONSTITUTION_SOCIETE", "Plusieurs indices concordants de constitution"
    if re.search(r"assembl[ée]e g[ée]n[ée]rale extraordinaire|\bage\b", text):
        return "CONVOCATION_AGE", "Convocation AGE explicite"
    if re.search(r"assembl[ée]e g[ée]n[ée]rale ordinaire|\bago\b", text):
        return "CONVOCATION_AGO", "Convocation AGO explicite"
    if re.search(r"p[ée]riode .*souscription|ouverture .*souscription", text):
        return "SOUSCRIPTION_CAPITAL", "Souscription explicite sans indices suffisants de constitution"
    if llm_code in PRIMARY_EVENT_LABELS:
        return llm_code, "Code LLM conservé faute de règle plus forte"
    return "AUTRE", "Aucune règle déterministe concluante"


def infer_secondary_events(source_text: str, primary_event: str) -> list[str]:
    text = _norm(source_text)
    secondary: list[str] = []
    if re.search(r"souscription|souscrire", text) and primary_event != "SOUSCRIPTION_CAPITAL":
        secondary.append("SOUSCRIPTION_CAPITAL")
    if re.search(r"assembl[ée]e (?:g[ée]n[ée]rale )?(?:constitutive|fondatrice)", text):
        secondary.append("CONVOCATION_ASSEMBLEE_CONSTITUTIVE")
    if re.search(r"avis aux cr[ée]anciers|d[ée]clarer leurs cr[ée]ances", text) and primary_event != "AVIS_CREANCIERS":
        secondary.append("AVIS_CREANCIERS")
    if re.search(r"nomm[ée].*liquidateur", text) and primary_event != "LIQUIDATION":
        secondary.append("NOMINATION_LIQUIDATEUR")
    return secondary


def _extract_share_count(source_text: str) -> int | None:
    text = _flat(source_text)
    patterns = [
        r"Nombre\s+de\s+parts\s+sociales\s+à\s+souscrire\s*:\s*(\d[\d\s]*)",
        r"Nombre\s+de\s+parts\s+nominales(?:\s+qui\s+seront)?\s+souscrites?\s*:\s*(\d[\d\s]*)",
        r"Nombre\s+d['’]actions\s+(?:nominales\s+)?à\s+souscrire\s*:\s*(\d[\d\s]*)",
        r"Nombre\s+d['’]actions\s+(?:nominales\s+)?souscrites?\s*:\s*(\d[\d\s]*)",
        r"Nombre\s+de\s+Parts\s+Sociales\s*:\s*(\d[\d\s]*)",
        r"Nombre\s+de\s+parts\s+ou\s+actions\s*:\s*(\d[\d\s]*)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            digits = re.sub(r"\D", "", match.group(1))
            return int(digits) if digits else None
    return None

def _extract_subscription_period(source_text: str) -> dict[str, str]:
    text = _flat(source_text)
    labels = (
        r"(?:Période(?: d'ouverture)? de la souscription|Période de souscription ouverte|"
        r"Période de souscription|Délai ouvert de la souscription|Période d'ouverture de la souscription)"
    )
    match = re.search(
        rf"{labels}\s*:\s*(?:Du|Depuis)?\s*(?P<start>{DATE_TOKEN})\s*(?:au|à)\s*(?P<end>{DATE_TOKEN})",
        text,
        flags=re.IGNORECASE,
    )
    if not match:
        return {"start": "", "end": "", "original": ""}
    start = _flat(match.group("start"))
    end = _flat(match.group("end"))
    return {"start": start, "end": end, "original": f"Du {start} au {end}"}


def extract_financial_facts(
    source_text: str,
    event_code: str = "",
) -> dict[str, Any]:
    capital = extract_labeled_amount(
        source_text,
        [
            r"Montant du capital social(?: ouvert à la souscription| souscrit)?",
            r"Montant du capital de la société souscrit",
            r"Le montant du capital social de la société(?: disponible pour la souscription)?",
            r"Capital Social Souscriptible",
            r"Capital social souscrit",
            r"Capital social",
            r"Le capital",
        ],
    )
    nominal = extract_labeled_amount(
        source_text,
        [
            r"Valeur nominale de la part sociale",
            r"Valeur nominale des parts",
            r"Valeur nominale des actions",
            r"Valeur Nominale de la Part",
            r"Valeur nominale",
        ],
    )
    share_count = _extract_share_count(source_text)
    subscription = _extract_subscription_period(source_text)

    capital_decimal = capital.get("value_decimal") if capital else None
    nominal_decimal = nominal.get("value_decimal") if nominal else None

    control_applicable = event_code in CAPITAL_CONTROL_EVENTS
    if control_applicable:
        arithmetic = compare_capital_arithmetic(
            capital_decimal if isinstance(capital_decimal, Decimal) else None,
            share_count,
            nominal_decimal if isinstance(nominal_decimal, Decimal) else None,
        )
    else:
        arithmetic = {
            "status": "NOT_APPLICABLE",
            "computed_capital_tnd": None,
            "difference_tnd": None,
            "relative_difference": None,
            "tolerance_tnd": None,
            "message": (
                "Le contrôle nombre de parts × valeur nominale n'est pas applicable "
                "à ce type d'événement."
            ),
        }

    return {
        "parser_version": AMOUNT_PARSER_VERSION,
        "control_applicable": control_applicable,
        "capital_original": capital.get("original", "") if capital else "",
        "capital_tnd": capital.get("value_tnd") if capital else None,
        "capital_formatted": capital.get("formatted_tnd", "") if capital else "",
        "share_count": share_count,
        "nominal_original": nominal.get("original", "") if nominal else "",
        "nominal_tnd": nominal.get("value_tnd") if nominal else None,
        "nominal_formatted": nominal.get("formatted_tnd", "") if nominal else "",
        "computed_capital_tnd": arithmetic.get("computed_capital_tnd"),
        "difference_tnd": arithmetic.get("difference_tnd"),
        "relative_difference": arithmetic.get("relative_difference"),
        "arithmetic_status": arithmetic.get("status"),
        "arithmetic_message": arithmetic.get("message"),
        "subscription_start": subscription.get("start", ""),
        "subscription_end": subscription.get("end", ""),
        "subscription_period": subscription.get("original", ""),
    }

def _source_explicitly_states_count(source_text: str, count_token: str) -> bool:
    text = _norm(source_text)
    token = re.escape(count_token.casefold())
    return bool(re.search(rf"\b{token}\s+fondateurs?\b", text))


def sanitize_summary(summary: str, source_text: str) -> tuple[str, list[dict[str, str]]]:
    """Neutralize unsupported founder counts in non-deterministic summaries."""
    issues: list[dict[str, str]] = []
    result = _flat(summary)
    number_words = (
        "un|une|deux|trois|quatre|cinq|six|sept|huit|neuf|dix|onze|"
        "douze|treize|quatorze|quinze|seize|dix-sept|dix-huit|dix-neuf|vingt"
    )
    pattern = re.compile(rf"\b(\d+|{number_words})\s+fondateurs?\b", re.IGNORECASE)
    for match in list(pattern.finditer(result)):
        token = match.group(1)
        if not _source_explicitly_states_count(source_text, token):
            result = result.replace(match.group(0), "des fondateurs", 1)
            issues.append(
                {
                    "code": "UNSUPPORTED_FOUNDER_COUNT",
                    "severity": "warning",
                    "message": (
                        "Le nombre de fondateurs n'est pas explicitement indiqué; "
                        "il a été neutralisé dans le résumé."
                    ),
                }
            )
    result = re.sub(r"(?:[.;]\s*)?des fondateurs\.?$", ".", result, flags=re.IGNORECASE)
    return result.strip(), issues


def _build_constitution_summary(
    company_name: str,
    financial: dict[str, Any],
) -> str:
    sentences = [f"Constitution de {company_name or 'la société à vérifier'}." ]

    if financial.get("capital_formatted"):
        sentences.append(f"Capital social annoncé : {financial['capital_formatted']}.")

    share_count = financial.get("share_count")
    nominal = financial.get("nominal_formatted")
    if share_count and nominal:
        sentences.append(
            f"Souscription de {share_count} parts ou actions d'une valeur nominale de {nominal}."
        )
    elif share_count:
        sentences.append(f"Nombre de parts ou actions à souscrire : {share_count}.")
    elif nominal:
        sentences.append(f"Valeur nominale publiée : {nominal}.")

    if financial.get("subscription_period"):
        sentences.append(f"Période de souscription : {financial['subscription_period']}.")

    return " ".join(sentences)


def _extract_auditor_facts(source_text: str) -> dict[str, str]:
    text = _flat(source_text)
    cabinet_match = re.search(
        r"d[ée]signation du\s+(cabinet\s+[A-Za-z0-9À-ÿ&'’.\- ]+?)\s+représenté",
        text,
        flags=re.IGNORECASE,
    )
    representative_match = re.search(
        r"représenté par\s+(?:Monsieur|M\.?)\s+([A-Za-zÀ-ÿ'’.\- ]+?)\s+en tant que",
        text,
        flags=re.IGNORECASE,
    )
    exercises_match = re.search(
        r"pour les exercices\s+([0-9\s/–—\-]+)",
        text,
        flags=re.IGNORECASE,
    )
    cabinet = _clean_entity(cabinet_match.group(1)) if cabinet_match else ""
    representative = _clean_entity(representative_match.group(1)) if representative_match else ""
    exercises = _flat(exercises_match.group(1)).strip(" .;,-") if exercises_match else ""
    exercises = re.sub(r"\s*[-–—/]\s*", "–", exercises)
    return {
        "cabinet": cabinet,
        "representative": representative,
        "exercises": exercises,
    }


def _build_auditor_summary(company_name: str, source_text: str) -> str:
    facts = _extract_auditor_facts(source_text)
    company = company_name or "la société"
    cabinet = facts.get("cabinet") or "un commissaire aux comptes"
    representative = facts.get("representative")
    exercises = facts.get("exercises")

    sentence = f"{company} a désigné {cabinet if cabinet.casefold().startswith('un ') else 'le ' + cabinet}"
    if representative:
        sentence += f", représenté par {representative}"
    sentence += ", en qualité de commissaire aux comptes"
    if exercises:
        sentence += f" pour les exercices {exercises}"
    return sentence + "."


def _build_action(
    event_code: str,
    financial: dict[str, Any],
    source_text: str = "",
) -> str:
    if event_code == "CONSTITUTION_SOCIETE":
        arithmetic_status = financial.get("arithmetic_status")
        if arithmetic_status == "MISMATCH":
            return (
                "Contrôler l'incohérence entre le capital annoncé, le nombre de parts "
                "et la valeur nominale dans le document source avant toute décision."
            )

        capital = financial.get("capital_formatted")
        deadline = financial.get("subscription_end")
        capital_phrase = (
            f"le capital social annoncé de {capital}"
            if capital
            else "le capital social annoncé"
        )
        action = (
            f"Vérifier les statuts, {capital_phrase}, les conditions d'éligibilité à la "
            "souscription et la cohérence des données financières avant toute prise de contact."
        )
        if deadline:
            action += f" Date limite de souscription : {deadline}."
        return action

    if event_code == "NOMINATION_COMMISSAIRE":
        facts = _extract_auditor_facts(source_text)
        cabinet = facts.get("cabinet") or "le commissaire aux comptes"
        exercises = facts.get("exercises")
        if cabinet.casefold().startswith("cabinet "):
            cabinet_phrase = "du " + cabinet
        elif cabinet.casefold().startswith(("le ", "la ", "l'")):
            cabinet_phrase = "de " + cabinet
        else:
            cabinet_phrase = "du commissaire aux comptes " + cabinet
        action = (
            f"Vérifier l'enregistrement de la nomination {cabinet_phrase}, "
            "l'étendue du mandat et les obligations de suivi associées"
        )
        if exercises:
            action += f" pour les exercices {exercises}"
        return action + ", puis archiver la résolution et les pièces justificatives."

    actions = {
        "SOUSCRIPTION_CAPITAL": "Vérifier la date limite, les conditions de souscription et l'adéquation avec la stratégie UGFS.",
        "AUGMENTATION_CAPITAL": "Analyser les modalités de l'augmentation de capital et l'intérêt potentiel pour UGFS.",
        "DISSOLUTION": "Vérifier la décision de dissolution, ses effets et les délais applicables.",
        "LIQUIDATION": "Escalader pour une revue juridique et financière de la liquidation et des délais créanciers.",
        "REDRESSEMENT_JUDICIAIRE": "Escalader pour une revue prioritaire de la procédure, des créances et des échéances.",
        "FAILLITE": "Escalader immédiatement pour une revue juridique et financière.",
        "VENTE_FONDS_COMMERCE": "Analyser l'actif cédé, le prix, les oppositions possibles et l'intérêt transactionnel.",
        "VENTE_ENCHERES_SAISIE": "Analyser le bien, la mise à prix, la date d'adjudication et les conditions de participation.",
        "NOMINATION_DIRIGEANT": "Vérifier la décision de nomination, la durée du mandat, les pouvoirs accordés et son enregistrement.",
        "CONVOCATION_AGO": "Examiner l'ordre du jour et les décisions soumises à l'assemblée.",
        "CONVOCATION_AGE": "Examiner l'ordre du jour et les opérations structurantes proposées.",
    }
    return actions.get(
        event_code,
        "Vérifier manuellement les faits, le type d'événement et les conséquences opérationnelles.",
    )



def build_derived_risk_assessment(
    event_code: str,
    company_name: str,
    financial: dict[str, Any],
) -> dict[str, Any]:
    """Build one cautious deterministic risk assessment.

    This is not an explicit statement from the document. It explains the
    prioritisation implied by the legal event and validated facts.
    """
    company = company_name or "la société"
    financial_status = str(financial.get("arithmetic_status", "UNVERIFIED"))

    if financial_status == "MISMATCH":
        return {
            "nature": "Dérivé déterministe",
            "description": (
                f"Risque de fiabilité des données financières pour {company}: "
                "le capital publié n'est pas cohérent avec le nombre de parts et "
                "la valeur nominale."
            ),
            "base": financial.get("arithmetic_message", "Incohérence arithmétique détectée."),
        }

    descriptions = {
        "CONSTITUTION_SOCIETE": (
            "Risque faible de mise en œuvre et de vérification documentaire lié à "
            "la création d'une nouvelle structure; aucun signal juridique négatif "
            "explicite n'a été détecté."
        ),
        "SOUSCRIPTION_CAPITAL": (
            "Risque modéré lié à l'éligibilité, aux modalités de souscription et au "
            "respect de la fenêtre temporelle annoncée."
        ),
        "AUGMENTATION_CAPITAL": (
            "Risque modéré de dilution, de valorisation et d'exécution de l'opération "
            "de capital, à analyser avant toute décision."
        ),
        "DISSOLUTION": "Risque élevé de cessation d'activité et d'impact sur les parties prenantes.",
        "LIQUIDATION": (
            "Risque critique pour la continuité de l'entreprise, les créanciers et "
            "la récupération des actifs."
        ),
        "CLOTURE_LIQUIDATION": (
            "Risque résiduel lié à la clôture des opérations et aux droits restant à vérifier."
        ),
        "REDRESSEMENT_JUDICIAIRE": (
            "Risque critique lié à la continuité, aux créances et aux décisions judiciaires."
        ),
        "FAILLITE": "Risque critique de perte financière et de non-recouvrement.",
        "CLOTURE_FAILLITE": (
            "Risque résiduel élevé lié aux droits, créances ou actifs non encore régularisés."
        ),
        "VENTE_FONDS_COMMERCE": (
            "Risque modéré lié à la propriété de l'actif, au prix, aux oppositions et "
            "aux conditions de transfert."
        ),
        "LOCATION_GERANCE": (
            "Risque modéré lié aux responsabilités contractuelles et à l'exploitation du fonds."
        ),
        "VENTE_ENCHERES_SAISIE": (
            "Risque élevé lié à la procédure de saisie, aux charges du bien et aux "
            "conditions d'adjudication."
        ),
        "AVIS_CREANCIERS": (
            "Risque élevé de perte de droits en cas de non-respect des délais de déclaration."
        ),
        "NOMINATION_DIRIGEANT": (
            "Risque faible à modéré de transition de gouvernance et de continuité décisionnelle."
        ),
        "NOMINATION_COMMISSAIRE": (
            "Risque faible; l'événement concerne principalement le contrôle et l'audit."
        ),
        "CHANGEMENT_GOUVERNANCE": (
            "Risque modéré de transition de gouvernance nécessitant une revue des pouvoirs."
        ),
        "CONVOCATION_AGO": (
            "Risque faible en l'absence de décision négative explicite; l'ordre du jour doit être examiné."
        ),
        "CONVOCATION_AGE": (
            "Risque modéré car une assemblée extraordinaire peut porter sur une opération structurante."
        ),
        "CONSTITUTION_ASSOCIATION": "Risque faible de mise en œuvre administrative et de conformité.",
        "RECTIFICATIF": (
            "Risque faible mais nécessité de vérifier que la correction est intégrée dans les données."
        ),
        "AUTRE": "Risque non déterminé avec précision; une classification humaine reste nécessaire.",
    }

    basis_parts = [f"Événement principal: {event_code}"]
    if financial.get("capital_formatted"):
        basis_parts.append(f"capital publié: {financial['capital_formatted']}")
    if financial.get("subscription_period"):
        basis_parts.append(f"période: {financial['subscription_period']}")

    return {
        "nature": "Dérivé déterministe",
        "description": descriptions.get(event_code, descriptions["AUTRE"]),
        "base": "; ".join(basis_parts),
    }


def build_derived_opportunity(
    event_code: str,
    company_name: str,
    secondary_events: list[str],
    financial: dict[str, Any],
    source_text: str,
) -> dict[str, Any]:
    """Return at most one cautious, fact-based potential opportunity."""
    company = company_name or "la société"
    secondary = set(secondary_events or [])
    deadline = financial.get("subscription_end")
    capital = financial.get("capital_formatted")

    if event_code == "CONSTITUTION_SOCIETE" and (
        "SOUSCRIPTION_CAPITAL" in secondary
        or financial.get("subscription_period")
    ):
        deadline_part = f" avant le {deadline}" if deadline else ""
        capital_part = f" portant sur un capital annoncé de {capital}" if capital else ""
        return {
            "nature": "Opportunité potentielle dérivée",
            "categorie": "Souscription / financement",
            "description": (
                f"Étudier une éventuelle participation à la souscription de {company}"
                f"{deadline_part}{capital_part}, sous réserve d'éligibilité et "
                "d'alignement avec la stratégie UGFS."
            ),
            "base": (
                "Souscription au capital explicitement annoncée"
                + (f"; période {financial['subscription_period']}" if financial.get("subscription_period") else "")
                + (f"; capital {capital}" if capital else "")
            ),
        }

    if event_code in {"SOUSCRIPTION_CAPITAL", "AUGMENTATION_CAPITAL"}:
        deadline_part = f" avant le {deadline}" if deadline else ""
        return {
            "nature": "Opportunité potentielle dérivée",
            "categorie": "Financement",
            "description": (
                f"Évaluer la possibilité de participer à l'opération de capital de {company}"
                f"{deadline_part}, sous réserve d'éligibilité, de valorisation et "
                "d'intérêt stratégique UGFS."
            ),
            "base": "Opération de souscription ou d'augmentation de capital explicitement détectée.",
        }

    if event_code == "VENTE_FONDS_COMMERCE":
        return {
            "nature": "Opportunité potentielle dérivée",
            "categorie": "Acquisition / financement",
            "description": (
                "Évaluer l'intérêt d'une acquisition ou d'un financement du fonds de "
                "commerce, après vérification du prix, des charges, des oppositions et "
                "de l'adéquation stratégique."
            ),
            "base": "Vente ou cession d'un fonds de commerce explicitement détectée.",
        }

    if event_code == "VENTE_ENCHERES_SAISIE":
        return {
            "nature": "Opportunité potentielle dérivée",
            "categorie": "Acquisition d'actif",
            "description": (
                "Évaluer l'intérêt d'une acquisition lors de l'adjudication, après "
                "vérification du bien, des charges, de la mise à prix et des conditions "
                "de participation."
            ),
            "base": "Vente aux enchères ou saisie explicitement détectée.",
        }

    if event_code == "LOCATION_GERANCE":
        return {
            "nature": "Opportunité potentielle dérivée",
            "categorie": "Exploitation / partenariat",
            "description": (
                "Évaluer une opportunité d'exploitation ou de partenariat liée à la "
                "location-gérance, sous réserve d'une revue contractuelle et financière."
            ),
            "base": "Location-gérance explicitement détectée.",
        }

    normalized_source = _norm(source_text)
    if event_code in {"LIQUIDATION", "REDRESSEMENT_JUDICIAIRE", "FAILLITE"} and re.search(
        r"vente|cession|actifs?|ench[eè]res|adjudication",
        normalized_source,
    ):
        return {
            "nature": "Opportunité potentielle dérivée",
            "categorie": "Actifs en difficulté",
            "description": (
                "Évaluer uniquement les actifs ou opérations de cession explicitement "
                "mentionnés, après revue juridique, financière et des charges associées."
            ),
            "base": (
                "Procédure de difficulté accompagnée d'une mention explicite de vente, "
                "cession ou actifs."
            ),
        }

    return {}

def validate_and_correct_analysis(analysis: dict[str, Any], source_text: str) -> dict[str, Any]:
    """Correct the analysis and attach a factual/financial audit trail."""
    corrected = dict(analysis)
    corrections: list[dict[str, str]] = []
    issues: list[dict[str, str]] = []

    llm_code = str(corrected.get("type_evenement_code", "AUTRE") or "AUTRE")
    event_code, event_reason = infer_primary_event(source_text, llm_code)
    if event_code != llm_code:
        corrections.append(
            {
                "field": "type_evenement_code",
                "before": llm_code,
                "after": event_code,
                "reason": event_reason,
            }
        )
    corrected["type_evenement_code"] = event_code
    corrected["type_evenement"] = PRIMARY_EVENT_LABELS[event_code]
    corrected["evenements_secondaires"] = infer_secondary_events(source_text, event_code)

    extracted_company = extract_company_name(source_text)
    current_company = _clean_entity(str(corrected.get("societe", "")))
    source_company = extracted_company or current_company or "À vérifier"
    display_company = normalize_company_display_name(source_company)

    corrected["societe_source"] = source_company

    if _norm(display_company) != _norm(current_company):
        corrections.append(
            {
                "field": "societe",
                "before": current_company or "À vérifier",
                "after": display_company,
                "reason": (
                    "Nom extrait du document puis normalisé pour l'affichage; "
                    "la forme source est conservée séparément."
                ),
            }
        )
    corrected["societe"] = display_company or "À vérifier"

    category = infer_category(
        source_text,
        str(corrected.get("societe", "")),
        str(corrected.get("categorie", "")),
        event_code,
    )
    if category != str(corrected.get("categorie", "")):
        corrections.append(
            {
                "field": "categorie",
                "before": str(corrected.get("categorie", "")),
                "after": category,
                "reason": "Catégorie normalisée à partir d'un libellé explicite du texte source",
            }
        )
    corrected["categorie"] = category

    financial = extract_financial_facts(source_text, event_code)
    corrected["faits_financiers_valides"] = financial

    arithmetic_status = financial.get("arithmetic_status")
    if event_code in {"CONSTITUTION_SOCIETE", "SOUSCRIPTION_CAPITAL", "AUGMENTATION_CAPITAL"}:
        if arithmetic_status == "MISMATCH":
            issues.append(
                {
                    "code": "CAPITAL_ARITHMETIC_MISMATCH",
                    "severity": "warning",
                    "message": (
                        f"Capital annoncé {financial.get('capital_formatted') or 'inconnu'}; "
                        f"capital calculé {format_tnd(financial.get('computed_capital_tnd'))}; "
                        "les données publiées doivent être revues."
                    ),
                }
            )
        elif arithmetic_status == "UNVERIFIED":
            issues.append(
                {
                    "code": "CAPITAL_ARITHMETIC_UNVERIFIED",
                    "severity": "warning",
                    "message": financial.get("arithmetic_message", "Contrôle financier impossible."),
                }
            )

    original_summary = str(corrected.get("resume", ""))
    if event_code == "CONSTITUTION_SOCIETE":
        deterministic_summary = _build_constitution_summary(
            str(corrected.get("societe", "")),
            financial,
        )
        if _norm(deterministic_summary) != _norm(original_summary):
            corrections.append(
                {
                    "field": "resume",
                    "before": original_summary,
                    "after": deterministic_summary,
                    "reason": "Résumé reconstruit à partir de faits financiers déterministes",
                }
            )
        corrected["resume"] = deterministic_summary
    elif event_code == "NOMINATION_COMMISSAIRE":
        deterministic_summary = _build_auditor_summary(
            str(corrected.get("societe", "")),
            source_text,
        )
        if _norm(deterministic_summary) != _norm(original_summary):
            corrections.append(
                {
                    "field": "resume",
                    "before": original_summary,
                    "after": deterministic_summary,
                    "reason": "Résumé reconstruit à partir de la résolution et du mandat du commissaire",
                }
            )
        corrected["resume"] = deterministic_summary
    else:
        summary, summary_issues = sanitize_summary(original_summary, source_text)
        corrected["resume"] = summary
        issues.extend(summary_issues)

    recommended_action = _build_action(event_code, financial, source_text)
    current_action = _flat(str(corrected.get("action_recommandee", "")))
    action_is_weak = (
        len(current_action) < 45
        or not current_action.casefold().startswith(ALLOWED_ACTION_VERBS)
        or event_code == "CONSTITUTION_SOCIETE"
    )
    if action_is_weak and _norm(recommended_action) != _norm(current_action):
        corrections.append(
            {
                "field": "action_recommandee",
                "before": current_action,
                "after": recommended_action,
                "reason": "Action rendue opérationnelle à partir des faits validés",
            }
        )
        corrected["action_recommandee"] = recommended_action

    corrected["evaluation_risque_derivee"] = build_derived_risk_assessment(
        event_code,
        str(corrected.get("societe", "")),
        financial,
    )
    corrected["opportunite_potentielle_derivee"] = build_derived_opportunity(
        event_code,
        str(corrected.get("societe", "")),
        corrected.get("evenements_secondaires", []),
        financial,
        source_text,
    )

    status = "WARNING" if issues else "PASS"
    corrected["validation_factuelle"] = {
        "version": VALIDATION_VERSION,
        "status": status,
        "corrections": corrections,
        "issues": issues,
        "event_reason": event_reason,
        "financial_status": arithmetic_status,
    }
    return corrected
