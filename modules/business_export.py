"""Export grounded business results without inventing generic scores."""
from datetime import datetime
import json
from config import OUTPUT_EXCEL_DIR


def export_grounded(row, record):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font
    OUTPUT_EXCEL_DIR.mkdir(parents=True, exist_ok=True)
    path = OUTPUT_EXCEL_DIR / ("resultat_metier_" + datetime.now().strftime("%Y%m%d_%H%M%S_%f") + ".xlsx")
    book = Workbook()
    result = book.active
    result.title = "Résultat métier"
    result.append(["Champ", "Valeur"])
    from modules.service_model import service_label
    from services.result_presentation import BUSINESS_LABELS, output_view
    from services.financial_intelligence import note
    from services.event_taxonomy import TAXONOMY
    analysis = record["analysis"]
    grounding = analysis.get("grounding", {})
    facts = analysis.get("canonical_facts") or {}
    def readable(value):
        if value is None or value == "": return "Non déterminé"
        if isinstance(value, list): return "\n".join(readable(v) for v in value)
        if isinstance(value, dict):
            return "\n".join(f"{BUSINESS_LABELS.get(k, k.replace('_', ' ').capitalize())} : {readable(v)}" for k, v in value.items())
        return str(value)
    review = {"validated": "Validé", "draft": "À valider", "pending": "À valider", "correction": "À corriger"}
    metadata = {
        "Titre": row["title"], "Source": row["source"], "Date de publication": row.get("date"),
        "Service": service_label(record["service_id"]), "Validation humaine": review.get(record.get("review_status"), "À vérifier"),
        "Date de validation": record.get("validated_at") or "Non validé", "Version": record.get("revision"),
        "Lien source": row.get("source_url") or (row.get("raw") or {}).get("pdf_url"),
    }
    for key, value in metadata.items(): result.append([key, readable(value)])
    for key, value in output_view(analysis).items():
        if key == "evidence": continue
        if key == "event_type": value = TAXONOMY.get(value, (value,))[0]
        result.append([BUSINESS_LABELS.get(key, key.replace("_", " ").capitalize()), readable(value)])
    financial = note(facts, record["service_id"]) if facts and not grounding.get("human_changes") else {}
    if financial:
        numbers = book.create_sheet("Faits et calculs")
        numbers.append(["Nature", "Indicateur", "Valeur", "Preuves", "Méthode / contrôle"])
        for item in financial.get("key_facts", []):
            numbers.append(["Fait source", item["label"], item["text"], ", ".join(item["evidence_ids"]), "Extrait de la source"])
        for item in financial.get("metrics", []):
            numbers.append(["Calcul Python", item["name"], item["result"], ", ".join(item["evidence_ids"]), item["formula"] + " · " + item["validation_status"]])
        for item in financial.get("sections", []):
            numbers.append([{"FACT": "Fait source", "INTERPRETATION": "Interprétation — à valider", "RECOMMENDATION": "Recommandation UGFS"}.get(item["kind"], item["kind"]), item["label"], item["text"], ", ".join(item["evidence_ids"]), ""])
    proof = book.create_sheet("Preuves source")
    proof.append(["Identifiant", "Citation exacte", "Page début", "Page fin", "Publication enfant", "Origine", "Début texte", "Fin texte", "Identité source"])
    for item in grounding.get("evidence", []):
        proof.append([readable(item.get(k)) for k in ("id", "quote", "page_start", "page_end", "child_publication_id", "origin", "start", "end", "source_record_id")])
    reliability = book.create_sheet("Fiabilité et validation")
    reliability.append(["Champ", "Valeur"])
    rel = analysis.get("reliability") or {}
    for key, value in {
        "Fiabilité factuelle": rel.get("factual_score"), "Indice global": rel.get("score"),
        "Pertinence métier": rel.get("service_relevance"), "Limites": grounding.get("limitations"),
        "Validation humaine": metadata["Validation humaine"], "Date de validation": metadata["Date de validation"],
        "Corrections humaines": grounding.get("human_changes") or "Aucune correction enregistrée",
        "Précaution": "Analyse préliminaire soumise à validation humaine. L’indice de fiabilité n’est pas une probabilité statistique de vérité.",
    }.items(): reliability.append([key, readable(value)])
    trace = book.create_sheet("Traçabilité")
    trace.append(["Champ", "Valeur"])
    for key, value in {"Notification": row["uid"], "Modèle": record.get("model"), "Version du prompt": record.get("prompt_version"), "Version du pipeline": analysis.get("pipeline_version"), "Empreinte source": grounding.get("source_hash"), "Provenance documentaire": analysis.get("source_identity") or facts.get("source_identity")}.items():
        trace.append([key, readable(value)])
    technical = book.create_sheet("Détails techniques")
    technical.append(["Champ", "Valeur"])
    for key, value in analysis.items():
        serialized = json.dumps(value, ensure_ascii=False)
        for offset in range(0, len(serialized), 30000):
            technical.append([key + (f" — partie {offset // 30000 + 1}" if len(serialized) > 30000 else ""), serialized[offset:offset + 30000]])
    for sheet in book:
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = sheet.dimensions
        sheet.column_dimensions["A"].width = 30
        sheet.column_dimensions["B"].width = 80
        for column in ("C", "D", "E", "F", "G", "H"):
            sheet.column_dimensions[column].width = 28
        if sheet.title == "Faits et calculs": sheet.column_dimensions["C"].width = 80
        for row_cells in sheet:
            for cell in row_cells:
                cell.data_type = "s"
                cell.alignment = Alignment(wrap_text=True, vertical="top")
        for cell in sheet[1]:
            cell.font = Font(bold=True)
    book.save(path)
    book.close()
    return path
