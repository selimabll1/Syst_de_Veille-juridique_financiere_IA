from __future__ import annotations

import html
import os
import smtplib
from email.message import EmailMessage
from typing import Any, Iterable


def smtp_status() -> dict[str, Any]:
    host = os.getenv("UGFS_SMTP_HOST", "").strip()
    user = os.getenv("UGFS_SMTP_USER", "").strip()
    password = os.getenv("UGFS_SMTP_PASSWORD", "").strip()
    sender = os.getenv("UGFS_SMTP_FROM", "").strip() or user
    port_raw = os.getenv("UGFS_SMTP_PORT", "587").strip()
    try:
        port = int(port_raw)
    except ValueError:
        port = 587
    return {
        "configured": bool(host and sender),
        "host": host,
        "port": port,
        "user": user,
        "password_present": bool(password),
        "sender": sender,
        "use_tls": os.getenv("UGFS_SMTP_TLS", "1").strip() not in {"0", "false", "False"},
    }


def build_digest(
    service_label: str,
    alerts: Iterable[dict[str, Any]],
) -> tuple[str, str, str]:
    rows = list(alerts)
    subject = f"Veille UGFS — {service_label} — {len(rows)} alerte(s)"

    text_parts = [
        f"Veille UGFS — {service_label}",
        "",
        f"{len(rows)} alerte(s) sélectionnée(s).",
        "",
    ]
    html_parts = [
        f"<h2>Veille UGFS — {html.escape(service_label)}</h2>",
        f"<p><strong>{len(rows)}</strong> alerte(s) sélectionnée(s).</p>",
    ]

    for alert in rows:
        company = str(alert.get("_digest_company") or "—")
        title = str(alert.get("_digest_title") or "—")
        source = str(alert.get("_digest_source") or "—")
        date = str(alert.get("_digest_date") or "—")
        priority = str(alert.get("_digest_priority") or "À classer")
        summary = str(alert.get("_digest_summary") or "")

        text_parts.extend([
            company,
            f"{title} — {source} — {date}",
            f"Priorité : {priority}",
            summary,
            "",
        ])
        html_parts.append(
            "<div style='margin:16px 0;padding:12px;border:1px solid #d8e1ef;"
            "border-radius:10px'>"
            f"<strong>{html.escape(company)}</strong><br>"
            f"{html.escape(title)} · {html.escape(source)} · {html.escape(date)}<br>"
            f"<b>Priorité :</b> {html.escape(priority)}<br>"
            f"<p>{html.escape(summary)}</p>"
            "</div>"
        )

    text_parts.append("Message généré par le système de veille UGFS.")
    html_parts.append("<p>Message généré par le système de veille UGFS.</p>")

    return subject, "\n".join(text_parts), "\n".join(html_parts)


def send_email(
    recipients: Iterable[str],
    subject: str,
    text_body: str,
    html_body: str = "",
    *,
    timeout_seconds: int = 20,
) -> tuple[bool, str]:
    cfg = smtp_status()
    recipients = [str(value).strip() for value in recipients if str(value).strip()]
    if not recipients:
        return False, "Aucun destinataire configuré."
    if not cfg["configured"]:
        return False, (
            "SMTP non configuré. Définissez UGFS_SMTP_HOST, UGFS_SMTP_FROM "
            "et, si nécessaire, UGFS_SMTP_USER / UGFS_SMTP_PASSWORD."
        )

    msg = EmailMessage()
    msg["From"] = cfg["sender"]
    msg["To"] = ", ".join(recipients)
    msg["Subject"] = subject
    msg.set_content(text_body)
    if html_body:
        msg.add_alternative(html_body, subtype="html")

    try:
        with smtplib.SMTP(
            cfg["host"],
            int(cfg["port"]),
            timeout=int(timeout_seconds),
        ) as smtp:
            if cfg["use_tls"]:
                smtp.starttls()
            user = str(cfg.get("user") or "")
            password = os.getenv("UGFS_SMTP_PASSWORD", "")
            if user and password:
                smtp.login(user, password)
            smtp.send_message(msg)
        return True, "Email envoyé."
    except Exception as exc:
        return False, f"Envoi impossible : {exc}"
