"""Analyse déterministe des montants en dinars tunisiens.

Le parseur conserve la valeur publiée et normalise correctement les millimes.
Il sait également lire les montants écrits en lettres lorsqu'une valeur numérique
est fournie entre parenthèses, par exemple :

``Cinq mille dinars tunisiens (5 000 TND)`` -> ``5 000 TND``.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any


AMOUNT_PARSER_VERSION = "tunisian_amount_parser_v2"

CURRENCY_PATTERN = r"(?:TND|DT|dinars?\s+tunisiens?|dinars?)"
NUMBER_PATTERN = r"\d(?:[\d\s\u00A0\u202F]*\d)?(?:[.,]\d{1,3})?"


def _compact_number_text(value: str) -> str:
    cleaned = str(value or "").strip()
    cleaned = cleaned.replace("\u00a0", " ").replace("\u202f", " ")
    cleaned = re.sub(r"[^0-9,\.\s]", "", cleaned)
    cleaned = re.sub(r"\s+", "", cleaned)
    return cleaned


def parse_tunisian_amount(value: Any) -> Decimal | None:
    """Convertir un montant tunisien en ``Decimal``.

    Le dernier point ou la dernière virgule est interprété comme séparateur
    décimal lorsqu'il est suivi de un à trois chiffres. Trois chiffres finaux
    représentent les millimes, pas un groupe de milliers.
    """
    compact = _compact_number_text(str(value or ""))
    if not compact or not re.search(r"\d", compact):
        return None

    separator_positions = [
        index for index, char in enumerate(compact) if char in ",."
    ]

    if not separator_positions:
        normalized = compact
    else:
        last_position = separator_positions[-1]
        digits_after = len(compact) - last_position - 1

        if 1 <= digits_after <= 3:
            integer_part = re.sub(r"[,.]", "", compact[:last_position])
            decimal_part = re.sub(r"[,.]", "", compact[last_position + 1 :])
            normalized = f"{integer_part}.{decimal_part}"
        else:
            normalized = re.sub(r"[,.]", "", compact)

    try:
        return Decimal(normalized)
    except InvalidOperation:
        return None


def decimal_to_float(value: Decimal | None) -> float | None:
    return None if value is None else float(value)


def format_tnd(value: Decimal | float | int | None) -> str:
    """Formater une valeur normalisée en montant lisible."""
    if value is None:
        return "À vérifier"

    try:
        amount = value if isinstance(value, Decimal) else Decimal(str(value))
    except InvalidOperation:
        return "À vérifier"

    amount = amount.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
    sign = "-" if amount < 0 else ""
    amount = abs(amount)
    integer_part = int(amount)
    fractional = int((amount - Decimal(integer_part)) * 1000)

    integer_text = f"{integer_part:,}".replace(",", " ")
    if fractional == 0:
        return f"{sign}{integer_text} TND"

    fractional_text = f"{fractional:03d}".rstrip("0")
    return f"{sign}{integer_text},{fractional_text} TND"


def _amount_result(amount_original: str, currency: str) -> dict[str, Any]:
    original = " ".join(part for part in [amount_original.strip(), currency.strip()] if part)
    normalized = parse_tunisian_amount(amount_original)
    return {
        "original": original,
        "number_original": amount_original.strip(),
        "currency_original": currency.strip(),
        "value_decimal": normalized,
        "value_tnd": decimal_to_float(normalized),
        "formatted_tnd": format_tnd(normalized),
        "parser_version": AMOUNT_PARSER_VERSION,
    }


def _find_amount_in_window(window: str) -> dict[str, Any] | None:
    """Trouver prioritairement une valeur numérique entre parenthèses."""
    parenthetical = re.search(
        rf"\(\s*(?P<amount>{NUMBER_PATTERN})\s*(?P<currency>{CURRENCY_PATTERN})\s*\)",
        window,
        flags=re.IGNORECASE,
    )
    if parenthetical:
        return _amount_result(
            parenthetical.group("amount"),
            parenthetical.group("currency"),
        )

    direct = re.search(
        rf"(?P<amount>{NUMBER_PATTERN})\s*(?P<currency>{CURRENCY_PATTERN})",
        window,
        flags=re.IGNORECASE,
    )
    if direct:
        return _amount_result(direct.group("amount"), direct.group("currency"))

    # Certains avis omettent l'unité immédiatement après le montant, par
    # exemple « Capital Social Souscriptible : 5000 ». Le libellé explicite
    # permet d'accepter prudemment le premier nombre avant le prochain champ.
    bare = re.search(rf"(?P<amount>{NUMBER_PATTERN})", window)
    if bare:
        return _amount_result(bare.group("amount"), "")

    return None


def extract_labeled_amount(
    text: str,
    labels: list[str],
) -> dict[str, Any] | None:
    """Extraire le premier montant situé après un libellé donné.

    Une fenêtre courte est utilisée afin de ne pas confondre le capital avec une
    date, un numéro d'immatriculation ou un montant appartenant au champ suivant.
    """
    flat_text = re.sub(r"\s+", " ", text or "").strip()

    for label in labels:
        label_match = re.search(rf"(?:{label})\s*:?\s*", flat_text, flags=re.IGNORECASE)
        if not label_match:
            continue

        window = flat_text[label_match.end() : label_match.end() + 150]
        # Arrêter la recherche au prochain libellé métier courant.
        window = re.split(
            r"\s+(?=(?:Siège|Adresse|Activité|Objet|Durée|Date de dépôt|"
            r"Nombre de|Nombre d['’]|Valeur nominale|Établissement|Etablissement|"
            r"Période de souscription|Période d'ouverture|Banque)\b)",
            window,
            maxsplit=1,
            flags=re.IGNORECASE,
        )[0]

        result = _find_amount_in_window(window)
        if result is not None:
            return result

    return None


def compare_capital_arithmetic(
    announced_capital: Decimal | None,
    share_count: int | None,
    nominal_value: Decimal | None,
) -> dict[str, Any]:
    """Comparer le capital publié à ``nombre de parts × valeur nominale``."""
    if announced_capital is None or share_count is None or nominal_value is None:
        return {
            "status": "UNVERIFIED",
            "computed_capital_tnd": None,
            "difference_tnd": None,
            "relative_difference": None,
            "tolerance_tnd": None,
            "message": (
                "Le capital, le nombre de parts ou la valeur nominale manque; "
                "le contrôle arithmétique n'a pas pu être effectué."
            ),
        }

    computed = Decimal(share_count) * nominal_value
    difference = abs(announced_capital - computed)
    tolerance = max(Decimal("1.000"), abs(announced_capital) * Decimal("0.001"))
    relative = difference / abs(announced_capital) if announced_capital != 0 else Decimal("0")

    if difference <= tolerance:
        status = "PASS"
        message = "Le capital annoncé est cohérent avec le nombre de parts et la valeur nominale."
    else:
        status = "MISMATCH"
        message = (
            "Le capital annoncé ne correspond pas au produit nombre de parts × "
            "valeur nominale; une revue du document source est nécessaire."
        )

    return {
        "status": status,
        "computed_capital_tnd": float(computed),
        "difference_tnd": float(difference),
        "relative_difference": float(relative),
        "tolerance_tnd": float(tolerance),
        "message": message,
    }
