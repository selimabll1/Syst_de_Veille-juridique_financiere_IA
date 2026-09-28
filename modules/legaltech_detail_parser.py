from __future__ import annotations

import json
from pathlib import Path
import re
import sqlite3
from typing import Any

DETAIL_PARSER_VERSION = "legaltech_detail_parser_v29_1"
DEFAULT_DB = Path("data/legaltech_notifications_v5.sqlite3")

_WS = re.compile(r"\s+")

# Labels observed in LegalTech article/detail pages. Longest first avoids
# interpreting "Date" before "Date de modification".
KNOWN_LABELS = [
    "Dénomination réservée", "Dénomination latin", "Dénomination",
    "التسمية المحجوزة", "Enseigne", "الشارة", "1er responsable",
    "Date de début d’activité", "Date de début d'activité", "Date d’immatriculation",
    "Année comptable", "Type modification", "نوع التحيين", "Forme juridique",
    "Bulletin N°", "Date Publication", "Type publication", "Type de registre",
    "Durée", "Annonce N°", "Date d'immatriculation",
    "Matricule fiscal / Id unique (RNE)",
    "Matricule fiscal / ID unique (RNE)",
    "Date de modification",
    "Date de création",
    "Date de publication",
    "Titre d'alerte",
    "Titre de l'alerte",
    "Nom de l'entreprise",
    "Identifiant Unique",
    "Personnalité juridique",
    "Acheteur public",
    "Montant TTC",
    "Montant HT",
    "Raison sociale",
    "Type de publication",
    "Type de modification",
    "Numéro publication",
    "Numero publication",
    "Catégories",
    "Catégorie",
    "Sources",
    "Réference",
    "Référence",
    "Résumé",
    "Numero",
    "Numèro",
    "Attributaire",
    "Objet FR",
    "Objet AR",
    "Adresse",
    "Activité",
    "Capital",
    "Responsable",
    "Qualité",
    "ID",
    "Date",
]

KEY_MAP = {
    "dénomination réservée": "denomination_reservee", "dénomination latin": "denomination_latin",
    "dénomination": "denomination", "التسمية المحجوزة": "denomination_alternative",
    "enseigne": "enseigne", "الشارة": "enseigne_ar", "1er responsable": "responsable",
    "date de début d’activité": "date_debut_activite", "date de début d'activité": "date_debut_activite",
    "année comptable": "annee_comptable", "type modification": "type_modification",
    "titre d'alerte": "titre_alerte",
    "titre de l'alerte": "titre_alerte",
    "catégories": "categories",
    "catégorie": "categorie",
    "sources": "sources",
    "nom de l'entreprise": "nom_entreprise",
    "matricule fiscal / id unique (rne)": "identifiant_unique",
    "date de création": "date_creation",
    "date de modification": "date_modification",
    "date de publication": "date_publication",
    "réference": "reference",
    "référence": "reference",
    "résumé": "resume",
    "identifiant unique": "identifiant_unique",
    "personnalité juridique": "personnalite_juridique",
    "acheteur public": "acheteur_public",
    "montant ttc": "montant_ttc",
    "montant ht": "montant_ht",
    "raison sociale": "raison_sociale",
    "type de publication": "type_publication",
    "type de modification": "type_modification",
    "numéro publication": "numero_publication",
    "numero publication": "numero_publication",
    "numero": "numero",
    "numèro": "numero",
    "attributaire": "attributaire",
    "objet fr": "objet_fr",
    "objet ar": "objet_ar",
    "adresse": "adresse",
    "activité": "activite",
    "capital": "capital",
    "responsable": "responsable",
    "qualité": "qualite",
    "id": "id",
    "date": "date",
}


def _clean(value: Any) -> str:
    return _WS.sub(" ", str(value or "")).strip(" \t\r\n:：")


def _key(label: str) -> str:
    folded = _clean(label).casefold()
    return KEY_MAP.get(
        folded,
        re.sub(r"[^a-z0-9]+", "_", folded.replace("é", "e").replace("è", "e").replace("à", "a")).strip("_"),
    )


def parse_detail_text(text: str, existing: dict[str, Any] | None = None) -> dict[str, Any]:
    """Parse visible LegalTech detail text into deterministic fields.

    This is intentionally rule-based; it does not rely on the LLM.
    """
    fields: dict[str, Any] = dict(existing or {})
    # Flattened RNE cards separate fields with commas, while amounts may also
    # contain commas. Split only before an explicit label followed by a colon.
    labels = '|'.join(re.escape(label) for label in sorted(KNOWN_LABELS, key=len, reverse=True))
    text = re.sub(r'\s*,\s*(?=(?:'+labels+r')\s*[:：])', '\n', str(text or ''), flags=re.I)
    raw_lines = [line.strip() for line in text.splitlines()]
    lines = [line for line in raw_lines if line]

    if not lines:
        return fields

    label_lookup = {label.casefold(): label for label in KNOWN_LABELS}

    def is_label(line: str) -> str | None:
        clean = _clean(line).rstrip(":")
        folded = clean.casefold()
        if folded in label_lookup:
            return label_lookup[folded]
        # LegalTech sometimes renders "Label:value" on one line.
        for label in KNOWN_LABELS:
            if re.match(r"^" + re.escape(label.casefold()) + r"\s*:+", folded):
                return label
        return None

    i = 0
    while i < len(lines):
        line = lines[i]
        matched = is_label(line)
        if not matched:
            i += 1
            continue

        clean_line = _clean(line)
        inline_value = ""
        inline_match = re.match(
            r"^" + re.escape(matched) + r"\s*:+\s*(.*)$",
            clean_line,
            flags=re.I,
        )
        if inline_match:
            inline_value = _clean(inline_match.group(1))

        value_parts: list[str] = []
        if inline_value:
            value_parts.append(inline_value)

        j = i + 1
        while j < len(lines):
            if is_label(lines[j]):
                break
            value_parts.append(_clean(lines[j]))
            j += 1

        value = _clean(" ".join(x for x in value_parts if x))
        if value:
            key = _key(matched)
            old = _clean(fields.get(key))
            if not old or len(value) > len(old):
                fields[key] = value

        i = max(i + 1, j)

    # Common aliases consumed by the UI/filters.
    if fields.get("titre_alerte"):
        fields.setdefault("titre", fields["titre_alerte"])
    if fields.get("nom_entreprise"):
        fields.setdefault("denomination", fields["nom_entreprise"])
    if fields.get("categories"):
        fields.setdefault("categorie", fields["categories"])
    if fields.get("resume"):
        fields.setdefault("summary", fields["resume"])

    return fields


def backfill_database(db_path: str | Path = DEFAULT_DB) -> dict[str, int]:
    path = Path(db_path)
    if not path.exists():
        return {"rows": 0, "updated": 0}

    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    updated = 0
    try:
        rows = con.execute(
            """SELECT alert_key, detail_text, source_fields_json
               FROM notification_alerts
               WHERE detail_text IS NOT NULL AND TRIM(detail_text) <> ''"""
        ).fetchall()

        for row in rows:
            try:
                existing = json.loads(row["source_fields_json"] or "{}")
                if not isinstance(existing, dict):
                    existing = {}
            except Exception:
                existing = {}

            parsed = parse_detail_text(row["detail_text"], existing)
            new_json = json.dumps(parsed, ensure_ascii=False, sort_keys=True)
            if new_json != (row["source_fields_json"] or "{}"):
                con.execute(
                    "UPDATE notification_alerts SET source_fields_json=? WHERE alert_key=?",
                    (new_json, row["alert_key"]),
                )
                updated += 1
        con.commit()
        return {"rows": len(rows), "updated": updated}
    finally:
        con.close()
