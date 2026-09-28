"""Source-neutral event vocabulary. Patterns are language rules, never entity rules."""
import re
import unicodedata
from services.financial_vocabulary import EVENTS

# Priority expresses specificity, not business severity or proof of completion.
TAXONOMY = {
 'CAPITAL_REDUCTION': ('Réduction de capital', 100, ['réduction du capital','réduction de capital','تخفيض رأس المال','تخفيض رأس مال']),
 'CAPITAL_INCREASE': ('Augmentation de capital', 100, ['augmentation de capital','augmentation du capital','ترفيع رأس المال','الترفيع في رأس المال','زيادة رأس المال']),
 'INCORPORATION': ('Constitution société', 85, ['constitution de société','constitution de sociétés','il a été constitué','تأسيس شركة']),
 'FINANCING': ('Financement', 70, ['accord de financement','levée de fonds','تمويل']),
 'ACQUISITION': ('Acquisition', 85, ['acquisition de','prise de participation','استحواذ']),
 'DISPOSAL': ('Cession', 85, ['cession de parts','cession des parts','cession d’actions','cession des actions','تفويت']),
 'MERGER': ('Fusion', 85, ['fusion absorption','projet de fusion','اندماج']),
 'RESTRUCTURING': ('Restructuration', 80, ['restructuration','إعادة هيكلة']),
 'LIQUIDATION': ('Liquidation', 95, ['liquidation','dissolution','تصفية','مصفية']),
 'GOVERNANCE': ('Gouvernance', 55, ['mise à jour des dirigeants','conseil d’administration','تحيين المسيرين','مجلس الإدارة']),
 'DIRECTOR_APPOINTMENT': ('Dirigeant nomination/départ', 75, ['nomination de','démission du directeur','départ du directeur','تعيين مدير','استقالة']),
 'SHAREHOLDING': ('Actionnariat', 65, ['modification de l’actionnariat','franchissement de seuil','تغيير المساهمين']),
 'MEETING': ('Assemblée', 40, ['assemblée générale','الجلسة العامة']),
 'FINANCIAL_STATEMENTS_FILING': ('Dépôt d’états financiers', 76, ['dépôt des états financiers','dépôt de comptes','dépôt des comptes annuels','إيداع القوائم المالية','ايداع الحسابات السنوية']),
 'FINANCIAL_STATEMENTS_APPROVAL': ('Approbation des états financiers', 74, ['approbation des états financiers','approbation des comptes annuels','المصادقة على القوائم المالية','المصادقة على الحسابات السنوية']),
 'FINANCIAL_REPORTING_PUBLICATION': ('Publication du reporting financier', 50, ['publication des états financiers','publie ses états financiers','mise à disposition des états financiers','publication du rapport financier','états financiers','comptes annuels','نشر القوائم المالية','نشر التقرير المالي','القوائم المالية']),
 'FINANCIAL_RESULTS': ('Résultats financiers', 45, ['résultats financiers','chiffre d’affaires','résultat net','bénéfice net','perte nette','EBITDA','EBIT','cash flow','flux de trésorerie','capitaux propres','total du bilan','رقم المعاملات','النتيجة الصافية','الربح الصافي','التدفقات النقدية']),
 'DIVIDEND': ('Dividende', 70, ['dividende','توزيع الأرباح']),
 'DEBT': ('Dette', 70, ['emprunt obligataire','restructuration de dette','قرض رقاعي','ديون']),
 'REGULATION': ('Réglementation', 65, ['nouvelle réglementation','règlement du conseil','نظام هيئة السوق','تنقيح القانون']),
 'REGULATORY_GUIDANCE': ('Guidance réglementaire', 62, ['guide réglementaire','orientation réglementaire','instruction générale','circulaire','précisions relatives aux informations','précisions sur l’obligation','توضيحات بشأن المعلومات','دليل تنظيمي','منشور توجيهي']),
 'SANCTION': ('Sanction', 85, ['sanction prononcée','sanction administrative','amende infligée','عقوبة','خطية']),
 'REPORTING_OBLIGATION': ('Obligation/reporting', 60, ['obligation d’information','obligation de déclaration','doivent publier','يجب التصريح']),
 'TENDER': ('Appel d’offres', 75, ['appel d’offres','appel d’offres','طلب عروض']),
 'CONTRACT': ('Contrat', 70, ['signature du contrat','contrat conclu','إبرام عقد']),
 'LITIGATION': ('Contentieux', 80, ['décision judiciaire','dépôt d’une plainte','litige','حكم أو قرار قضائي','نزاع']),
 'PUBLIC_WARNING': ('Mise en garde publique', 90, ['mise en garde','تحذير']),
 'OTHER': ('Autre explicitement classé', 0, []),
 'UNKNOWN': ('Non déterminé', 0, []),
}
TAXONOMY.update(EVENTS)
# A line-item called "dividendes" is not an event. An explicit distribution
# action is required; financial reporting also needs actual numeric content.
TAXONOMY['DIVIDEND'] = ('Dividende', 70, ['distribution de dividendes', 'distribution d’un dividende', 'versement d’un dividende', 'mise en paiement du dividende', 'توزيع الأرباح'])


def normalize(text):
    value = unicodedata.normalize('NFKD',str(text)).casefold().replace('’',"'").replace('ـ','')
    value = ''.join(c for c in value if not unicodedata.combining(c))
    return ' '.join(value.translate(str.maketrans('أإآى','اااي')).split())


def performance_evidence(evidence):
    """A metric with a numeric value, not a reporting label or accounting year."""
    metric = r"(?:chiffre d[' ]affaires|resultat net|benefice net|perte nette|ebitda|ebit|marge(?: nette| brute| operationnelle)?|cash[ -]flow|flux de tresorerie|dette(?: nette| financiere)?|endettement|capitaux propres|total (?:du )?bilan|reserves|رقم المعاملات|النتيجة الصافية|الربح الصافي|التدفقات النقدية|مجموع الاصول)"
    period = r"(?:\s+(?:exercice|annee|en|au titre de l.exercice|سنة|لسنة|عام|السنة المالية)\s+(?:H[12]\s+)?(?:19|20)\d{2})?"
    link = r"\s*(?::|：|=|s'eleve a|sont de|est de|de|atteint|بلغ|بمبلغ)?\s*"
    amount = r"([+-]?\d+(?:[ .,٬٫]\d+)*)(?:\s*(%|tnd|dt|mdt|dinars?|millions?|euros?|دينار|مليون))?"
    found = []
    for item in evidence:
        text = normalize(item['quote']).translate(str.maketrans('٠١٢٣٤٥٦٧٨٩', '0123456789'))
        for match in re.finditer(r'(?<!\w)' + metric + r'(?!\w)' + period + link + amount, text, re.I):
            if not match[2] and re.fullmatch(r'(?:19|20)\d{2}', match[1]):
                continue
            found.append(item)
            break
    return found


def classify(evidence, *, multi_document=False):
    candidates=[]
    normalized_evidence=[(e,normalize(e['quote'])) for e in evidence]
    for code,(label,priority,terms) in TAXONOMY.items():
        ids=[];confirmed=[]
        normalized_terms=[normalize(term) for term in terms]
        for index,(e,text) in enumerate(normalized_evidence):
            for term in normalized_terms:
                if term not in text:continue
                for match in re.finditer(r'(?<!\w)'+re.escape(term)+r'(?!\w)',text):
                    prefix=text[max(0,match.start()-35):match.start()]
                    if re.search(r"(?:aucune?|pas de|sans|absence de|لم|لا|دون)\s+(?:\w+\s+){0,2}$",prefix):continue
                    ids.append(e['id'])
                    # Vocabulary alone is only a candidate. Require surrounding
                    # source content and reject definitions/hypothetical examples.
                    hypothetical=re.search(r'(?:hypothese de|exemple de|definition de|en cas de|possibilite de|pourrait proceder a une)\s*$',prefix)
                    adjacent=normalized_evidence[index+1] if index+1<len(normalized_evidence) else None
                    local_context=len(text.split())>=len(term.split())+2
                    heading_context=bool(adjacent and len(text.split())<=len(term.split())+2 and len(adjacent[1].split())>=4)
                    if (local_context or heading_context) and not hypothetical:
                        confirmed.append(e['id'])
                        if not local_context:confirmed.append(adjacent[0]['id'])
                    break
        if ids:candidates.append({'code':code,'label':label,'priority':priority,'evidence_ids':list(dict.fromkeys(ids)),'confirmed_evidence_ids':list(dict.fromkeys(confirmed))})
    candidates.sort(key=lambda c:-c['priority'])
    supported=[c for c in candidates if c['confirmed_evidence_ids']]
    performance = performance_evidence(evidence)
    if not performance:
        for candidate in candidates:
            if candidate['code'] in {'FINANCIAL_RESULTS', 'FINANCIAL_REPORTING_PUBLICATION'}:
                candidate['confirmed_evidence_ids'] = []
        supported = [c for c in supported if c['code'] not in {'FINANCIAL_RESULTS', 'FINANCIAL_REPORTING_PUBLICATION'}]
    uncertain=not supported or multi_document or (len(supported)>1 and supported[0]['priority']==supported[1]['priority'])
    primary='UNKNOWN' if uncertain else supported[0]['code']
    return {'event_type':primary,'event_subtype':None,'candidates':candidates,'evidence_ids':[] if uncertain else supported[0]['confirmed_evidence_ids'],'confidence':0 if uncertain else 85,'reason':'Plusieurs événements/documents ou preuves insuffisantes' if uncertain else 'Action explicite avec contexte source ; entité/autorité vérifiée par le profil métier, réalisation et effets à vérifier'}
