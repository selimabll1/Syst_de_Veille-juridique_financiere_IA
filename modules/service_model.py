"""Canonical service identifiers shared by registries, adapters and presentation.

Adding an identifier does not initialize or migrate any database.
"""
SERVICES = {
    "investment": {"label": "Investissement", "description": "Due diligence, screening et veille d’investissement", "sources": ["legaltech"]},
    "compliance": {"label": "Conformité", "description": "Veille juridique, gouvernance et réglementation", "sources": ["legaltech", "cmf", "finance_ministry"]},
    "portfolio": {"label": "Suivi portefeuille", "description": "Suivi des participations et événements", "sources": ["legaltech"]},
    "commercial": {"label": "Commerce", "description": "Signaux commerciaux et opportunités", "sources": ["legaltech", "social"]},
}

ALIASES = {
    "investment": "investment", "investissement": "investment", "inv": "investment",
    "compliance": "compliance", "conformite": "compliance", "conformité": "compliance", "conf": "compliance",
    "portfolio": "portfolio", "portefeuille": "portfolio", "suivi portefeuille": "portfolio", "port": "portfolio",
    "commercial": "commercial", "commerce": "commercial", "com": "commercial",
}


def service_key(value):
    return ALIASES.get(" ".join(str(value or "").strip().casefold().replace("_", " ").replace("-", " ").split()))


def service_label(key):
    return SERVICES.get(key, {}).get("label", str(key))
