from __future__ import annotations
import argparse, json
from modules.legaltech_browser_collector import AuthenticationRequired, LegalTechBrowserCollector
from modules.legaltech_remote_watcher import check_remote


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--headless", action="store_true")
    p.add_argument("--max-pages", type=int, default=100)
    args = p.parse_args()
    try:
        with LegalTechBrowserCollector(headless=args.headless, slow_mo_ms=0 if args.headless else 80) as browser:
            result = check_remote(browser, max_pages=args.max_pages)
            print(json.dumps(result, indent=2, ensure_ascii=False))
    except AuthenticationRequired as exc:
        print("AUTH_REQUIRED")
        print(exc)
        raise SystemExit(2)


if __name__ == "__main__":
    main()
