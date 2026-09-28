# Limites connues

- Application interne locale : pas de système d'authentification multi-utilisateur durci. Ne pas exposer directement sur Internet.
- Référentiel UGFS vide : modèles uniquement, aucun portefeuille inventé. Le triage n'établit pas une pertinence métier confirmée.
- Ollama, modèle, Tesseract/langues et navigateur sont des dépendances externes. Le clone n'emporte aucune session ni donnée.
- La session LegalTech expire et certaines réponses du serveur peuvent échouer. La dernière répétition a conservé un résultat distant non synchronisé ; aucune promesse de collecte exhaustive à partir de ce seul test.
- La politique de pertinence CMF doit être configurée pour autoriser une collecte utile ; CMF reste Conformité uniquement.
- SMTP/diffusion email non configuré : aucun envoi réel testé ni implémenté pendant cette passe. Seuls des résultats validés peuvent être candidats à diffusion.
- Les résultats historiques ne sont pas réécrits. Le replay HEXABYTE a été réalisé sur une copie : FINANCIAL_RESULTS avant, FINANCIAL_STATEMENTS_FILING après, performance/impact non déterminés. L'ancien résultat réel reste traçable ; une réanalyse explicite crée une nouvelle version.
- Plusieurs scripts/anciens modules restent pour compatibilité. UNKNOWN signifie non prouvé actif, pas autorisation de suppression. Le vieux test CMF utilisait des API obsolètes et n'est pas dans la suite maintenue.
- Les exigences pip ne verrouillent pas toutes les dépendances transitives ; refaire le contrôle d'environnement et la suite après mise à jour.
- Les vérifications de nettoyage/fresh install sont consignées dans `CLEANUP_VERIFICATION.md` ; aucune validation sur un second PC physique n'est prétendue.
