"""Offline checks for the French interface and readable Excel export."""

from pathlib import Path

import modules.excel_manager as excel_manager


def main() -> None:
    project_root = Path(__file__).resolve().parents[2]
    app_text = (project_root / "app.py").read_text(encoding="utf-8")

    forbidden_visible_labels = [
        "View score details",
        "Detected facts, risks and opportunities",
        "Download Excel file",
        "No analysis results yet",
        "Select analyzed announcement",
    ]
    for label in forbidden_visible_labels:
        assert label not in app_text, f"Libellé anglais restant : {label}"

    assert getattr(excel_manager, "EXCEL_EXPORT_VERSION", "") == "excel_francais_v3"
    assert "Société_Corrigée" in excel_manager.CORRECTION_COLUMNS
    assert (
        excel_manager.FRENCH_HEADER_MAP["Société_Corrigée"]
        == "Nom de société validé ou corrigé"
    )
    assert (
        excel_manager.FRENCH_HEADER_MAP["Société_Source"]
        == "Nom relevé dans le document"
    )

    print("LEGALTECH INTERFACE / EXCEL V8 OK")
    print("Interface : legaltech_app_v8_fr")
    print("Excel :", excel_manager.EXCEL_EXPORT_VERSION)
    print("Revue des noms de société : activée")


if __name__ == "__main__":
    main()
