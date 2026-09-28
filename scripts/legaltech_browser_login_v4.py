
from modules.legaltech_browser_collector import (
    DEFAULT_BASE_URL,
    DEFAULT_STORAGE_STATE,
    DEFAULT_SESSION_STORAGE,
    LegalTechBrowserCollector,
)

def main():
    print("Cookies/localStorage :", DEFAULT_STORAGE_STATE)
    print("sessionStorage :", DEFAULT_SESSION_STORAGE)
    print("Une fenêtre Chromium va s'ouvrir.")
    print("Connectez-vous normalement à LegalTech.")
    print("Après connexion, ouvrez /page-notifications une fois si possible.")

    with LegalTechBrowserCollector(headless=False) as browser:
        browser.goto(DEFAULT_BASE_URL)
        input(
            "\nQuand vous êtes connecté(e) et que LegalTech fonctionne, "
            "revenez ici et appuyez sur Entrée..."
        )
        browser.save_full_state()
        if browser.is_authenticated():
            print("SESSION LEGALTECH COMPLÈTE SAUVEGARDÉE")
        else:
            print("CONNEXION NON DÉTECTÉE")

if __name__ == "__main__":
    main()
