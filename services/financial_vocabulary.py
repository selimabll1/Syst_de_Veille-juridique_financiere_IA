"""Financial event candidates and explicit action phrases, independent of source IDs."""

EVENTS = {
    'SHARE_ISSUANCE': ('Émission d’actions', 88, ['émission d’actions nouvelles', 'émission de nouvelles actions', 'إصدار أسهم جديدة']),
    'SHARE_CANCELLATION': ('Annulation d’actions', 88, ['annulation d’actions', 'annulation des actions', 'إلغاء الأسهم']),
    'RIGHTS_ISSUE': ('Souscription préférentielle', 89, ['émission avec droit préférentiel', 'exercice du droit préférentiel de souscription']),
    'CONVERSION': ('Conversion de titres', 88, ['conversion des obligations en actions', 'conversion de créances en capital']),
    'CAPITAL_RESTRUCTURING': ('Restructuration du capital', 89, ['restructuration du capital', 'إعادة هيكلة رأس المال']),
    'ABSORPTION': ('Fusion par absorption', 86, ['fusion par absorption', 'fusion-absorption']),
    'CONTRIBUTION': ('Apport d’actifs', 86, ['apport partiel d’actif', 'apport en nature']),
    'OWNERSHIP_CHANGE': ('Changement de propriété', 86, ['transfert de propriété des actions']),
    'CONTROL_CHANGE': ('Changement de contrôle', 87, ['prise de contrôle', 'changement de contrôle', 'انتقال السيطرة']),
    'SHAREHOLDING_CHANGE': ('Modification de l’actionnariat', 86, ['modification de l’actionnariat', 'franchissement de seuil']),
    'DEBT_ISSUANCE': ('Émission de dette', 81, ['émission de titres de dette']),
    'BOND_ISSUANCE': ('Émission obligataire', 82, ['émission d’un emprunt obligataire', 'émission obligataire', 'إصدار قرض رقاعي']),
    'BANK_FINANCING': ('Financement bancaire', 81, ['obtention d’un crédit bancaire', 'accord de crédit bancaire']),
    'REFINANCING': ('Refinancement', 83, ['refinancement de la dette', 'accord de refinancement']),
    'DEBT_REPAYMENT': ('Remboursement de dette', 81, ['remboursement anticipé de l’emprunt', 'remboursement du principal']),
    'GUARANTEE': ('Garantie financière', 81, ['octroi d’une garantie', 'constitution d’une sûreté']),
    'REVENUE_CHANGE': ('Évolution du chiffre d’affaires', 47, ['hausse du chiffre d’affaires', 'baisse du chiffre d’affaires']),
    'PROFIT_CHANGE': ('Évolution du résultat', 47, ['hausse du résultat net', 'baisse du résultat net']),
    'MARGIN_CHANGE': ('Évolution de marge', 47, ['amélioration de la marge', 'dégradation de la marge']),
    'CASHFLOW_CHANGE': ('Évolution des flux de trésorerie', 47, ['hausse des flux de trésorerie', 'baisse des flux de trésorerie']),
    'DISTRIBUTION': ('Distribution aux associés', 71, ['distribution de réserves', 'distribution aux associés']),
    'INSOLVENCY': ('Cessation de paiement', 96, ['cessation de paiement', 'cessation des paiements', 'التوقف عن الدفع']),
    'GOING_CONCERN': ('Continuité d’exploitation', 92, ['incertitude sur la continuité d’exploitation', 'incertitude significative liée à la continuité']),
    'LOSS_OF_CAPITAL': ('Perte de capital', 92, ['capitaux propres inférieurs à la moitié du capital', 'perte de la moitié du capital']),
    'DEFAULT': ('Défaut de paiement', 96, ['défaut de paiement', 'incident de remboursement']),
    'DIRECTOR_DEPARTURE': ('Départ de dirigeant', 76, ['démission du directeur', 'départ du directeur', 'استقالة المدير']),
    'BOARD_CHANGE': ('Changement du conseil', 76, ['renouvellement du conseil d’administration', 'modification du conseil d’administration']),
    'AUDITOR_EVENT': ('Commissariat aux comptes', 76, ['nomination du commissaire aux comptes', 'démission du commissaire aux comptes']),
    'GENERAL_MEETING': ('Assemblée générale', 41, ['convocation de l’assemblée générale', 'assemblée générale convoquée']),
    'PROSPECTUS': ('Prospectus', 61, ['visa du prospectus', 'publication du prospectus']),
    'DISCLOSURE': ('Information du marché', 59, ['publication d’une information privilégiée', 'déclaration au marché']),
}

# Group sub-events without erasing their actual code or confusing specificity
# with priority. These groups also feed the existing métier relevance sets.
FINANCIAL_EVENTS = set(EVENTS) - {
    'DIRECTOR_DEPARTURE', 'BOARD_CHANGE', 'AUDITOR_EVENT', 'GENERAL_MEETING',
    'PROSPECTUS', 'DISCLOSURE',
}
GOVERNANCE_EVENTS = {'GOVERNANCE', 'DIRECTOR_APPOINTMENT', 'DIRECTOR_DEPARTURE',
                     'BOARD_CHANGE', 'AUDITOR_EVENT', 'GENERAL_MEETING', 'MEETING'}
