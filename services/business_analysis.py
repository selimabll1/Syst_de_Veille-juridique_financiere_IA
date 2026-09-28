"""Shared source extraction and one AI engine with four business configurations."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import tempfile
from services import pipeline_config
from services.jobs import report, stage


def extract_source(row):
    if row.get('child_id'):
        from services.composite_documents import verified_child
        from modules.ocr_engine import calculate_quality
        child=verified_child(row)
        return child['extracted_text'], calculate_quality(child['extracted_text']), 'child_pages'
    raw = row["raw"]
    source_pdf = raw.get("pdf_url") or ""
    if row["kind"] == "cmf":
        text = str(raw.get("raw_excerpt") or "").strip()
        bulletin = "bulletin" in str(raw.get("section", "")).lower()
        if bulletin and not row.get("pdf_path") and not raw.get("pdf_url"):
            raise ValueError("Ce bulletin CMF ne possède pas de document collecté. Synchronisez CMF ou ouvrez la source pour retrouver le PDF ; la page de liste ne peut pas servir d’analyse du bulletin.")
        if len(text) < 80 and raw.get("detail_url") and not bulletin:
            report("Lecture du texte officiel CMF…")
            from modules.cmf_collector_v1 import fetch_detail_content
            content = fetch_detail_content(raw["detail_url"])
            text = content["text"]
            source_pdf = content["pdf_url"] or source_pdf
        text = row["title"] + "\n\n" + text
    else:
        from services.normalization import _analysis_text
        text = _analysis_text(raw)
    quality, method = 1.0, "collected_text"
    if len(text.strip()) < 100 or (row["kind"] == "cmf" and (source_pdf or "bulletin" in str(raw.get("section")))):
        pdf = Path(row["pdf_path"]) if row.get("pdf_path") else None
        temporary = None
        if pdf is None and row["kind"] == "cmf" and source_pdf:
            import requests
            from modules.cmf_collector_v1 import _safe_cmf_url
            report("Lecture du PDF officiel CMF…")
            response = requests.get(_safe_cmf_url(source_pdf), timeout=(10, 60))
            response.raise_for_status()
            if not response.content.startswith(b"%PDF"):
                raise ValueError("La source CMF n’a pas retourné un PDF exploitable.")
            temporary = tempfile.TemporaryDirectory(prefix="ugfs_cmf_extract_")
            pdf = Path(temporary.name) / "source.pdf"
            pdf.write_bytes(response.content)
        if pdf and pdf.is_file():
            report("Extraction du document ; OCR Tesseract si nécessaire…")
            from modules.ocr_engine import extract_pdf_text
            try:
                extracted = extract_pdf_text(pdf, persist=False)
                if extracted["text"].strip():
                    text = row["title"] + "\n\n" + extracted["text"]
                    quality = extracted["ocr_quality"]
                    method = extracted["method"] + ("_partial" if extracted.get("errors") else "")
                else:
                    raise ValueError("Le document ne contient pas de texte exploitable ; vérifiez Tesseract et les langues OCR.")
            finally:
                if temporary:
                    temporary.cleanup()
    if len(text.strip()) < 80:
        raise ValueError("Texte source insuffisant pour une analyse fiable. Ouvrez la source ou collectez le document/extrait.")
    return text, quality, method


def analyze(row, services=None, *, force=False):
    """Explicit command; cache hits preserve the current result and human review."""
    import time
    from modules import business_pipeline_registry as registry, llm_analyzer as engine
    from services import intelligence, correctness_gates
    from services import composite_documents
    config = pipeline_config.load()
    selected = list(row["services"] if services is None else services)
    if not selected:
        raise ValueError("Aucun service affecté. Corrigez les services concernés avant l’analyse.")
    if set(selected) - set(row["services"]) or set(selected) - set(pipeline_config.eligible(row["kind"], config)):
        raise ValueError("L’analyse est réservée aux services affectés et éligibles pour cette source.")
    if composite_documents.is_parent(row):
        return composite_documents.preprocess(row)
    if row.get('child_id'):
        row=deepcopy(row)
        row['child_publication']=composite_documents.verified_child(row)
    attempts = {s: registry.start_attempt(row, s) for s in selected}
    started = time.perf_counter()
    try:
        t = time.perf_counter()
        stage("extraction")
        text, quality, method = extract_source(row)
        extraction_time = time.perf_counter() - t
        stage("facts")
        prepared = intelligence.prepare(row, text, quality, method)
        prepared["timings"]["document_extraction"] = extraction_time
    except Exception as exc:
        for token in attempts.values(): registry.fail_attempt(token, str(exc))
        raise
    successful, failures, cached = [], [], []
    preflight = correctness_gates.source_identity(row, text, prepared["facts"])
    if preflight.outcome == "SUCCESS":
        preflight = correctness_gates.document_scope(row, prepared["facts"])
    if preflight.outcome == "SUCCESS":
        preflight = correctness_gates.event_and_facts(prepared["facts"])
    if preflight.outcome != "SUCCESS":
        message = preflight.error_message()
        for token in attempts.values():
            registry.fail_attempt(token, message)
        report(message)
        return {"ok": False, "message": message, "services": [], "cached": [], "errors": [message], "outcome": preflight.outcome}
    for service in selected:
        try:
            relevance = correctness_gates.service_relevance(row, service, prepared["facts"])
            if relevance.outcome != "SUCCESS":
                raise ValueError(relevance.error_message())
            model_version = engine.model_identity()
            key = intelligence.cache_key(prepared, service, config, model_version)
            if model_version and not force and registry.reuse_current(row, service, key, attempts[service]):
                successful.append(service); cached.append(service)
                report(f"{service} : résultat inchangé réutilisé, validation humaine conservée.")
                continue
            report(f"Analyse {service} : faits canoniques et preuves bornées, modèle {engine.OLLAMA_MODEL}…")
            result = intelligence.analyze_prepared(row, service, prepared, config)
            result.update(cache_key=key, model_version=model_version, routing_snapshot={"assigned":row["services"],"manual":row.get("manual_routing",False),"reasons":row.get("routing_reasons",[])})
            gate = correctness_gates.evaluate(row, service, text, prepared["facts"], result)
            if not gate.allowed:
                raise ValueError(gate.error_message())
            result["correctness"] = {"outcome": gate.outcome, "reasons": list(gate.reasons), "details": gate.details}
            result["timings"]["total_analysis"] = time.perf_counter() - started
            stage("persistence",service)
            registry.save_result(row, service, result, model=engine.OLLAMA_MODEL, prompt_version=config["services"][service]["prompt_version"], source_hash=prepared["facts"]["source_hash"], attempt=attempts[service])
            successful.append(service)
            report(f"{service} : brouillon sourcé enregistré ; validation humaine requise.")
        except Exception as exc:
            registry.fail_attempt(attempts[service], str(exc))
            failures.append(f"{service} : {exc}")
            report(failures[-1])
    return {"ok":not failures,"message":f"{len(successful)-len(cached)} résultat(s) enregistré(s), {len(cached)} réutilisé(s)."+(" Échec : "+" ; ".join(failures) if failures else ""),"services":successful,"cached":cached,"errors":failures,"outcome":"SUCCESS_REVIEW_REQUIRED" if successful else ("ANALYSIS_ERROR" if failures else "SUCCESS")}
