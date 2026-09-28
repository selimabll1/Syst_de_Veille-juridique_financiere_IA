"""Teste la validité de la session HTTP LegalTech capturée."""
from __future__ import annotations

import argparse
from pathlib import Path

from modules.legaltech_http_client import LegalTechHTTPClient, LEGALTECH_CLIENT_VERSION


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--endpoints", type=Path, default=Path("config/legaltech_endpoints.local.json"))
    parser.add_argument("--session", type=Path, default=Path("secrets/legaltech_session.local.json"))
    args = parser.parse_args()
    client = LegalTechHTTPClient.from_files(args.endpoints, args.session)
    result = client.check_session()
    print("SESSION LEGALTECH VALIDE")
    print("Client :", LEGALTECH_CLIENT_VERSION)
    print("HTTP :", result["status_code"])
    print("Type :", result["content_type"])
    print("URL finale :", result["final_url"])


if __name__ == "__main__":
    main()
