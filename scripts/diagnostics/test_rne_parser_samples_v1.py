from modules.legaltech_browser_collector import parse_rne_visible_fields

VILAVI = """RNE - Publication N° 2026121638 Annonce N°: 2026121638 Type publication Modification Bulletin N° 183 Date 24-07-2026 Identifiant Unique 1131931X Capital 34525000 Durée 99 Type de registre Société 1er responsable غسان سلامة Qualité رئيس مجلس إدارة Nom commercial VILAVI Type modification Dépôt des états financiers نوع التحيين إيداع القوائم المالية Dénomination latin VILAVI Dénomination Ar فـي لا فـي Adresse عدد 79 نهج 9007 سيدي فتح الله 1046 جبل الجلود تونس Activite صنع المثلجات (قشدة مثلجة، غرانيت) و الصوربي Consultez l'Etat du Registre RNE Créer une alerte Registre National des Entreprises"""

NEXT_GEN = """RNE - Publication N° ARD000150493 Annonce N°: ARD000150493 Type publication Réservation dénomination Bulletin N° 186 Date 27-07-2026 Type demande de réservation CREATION N° certificat 2026144893297 Date réservation 2026-07-27 Délai de réservation 2027-01-27 Type réservation Dénomination Dénomination latin Next gen Enterprise Technology & Optimization Dénomination Ar تكنولوجيا و تحسين إدارة المؤسسات من الجيل الجديد Registre National des Entreprises"""

def main():
    v = parse_rne_visible_fields(VILAVI)
    assert v["numero_publication"] == "2026121638", v
    assert v["type_publication"] == "Modification", v
    assert v["identifiant_unique"] == "1131931X", v
    assert v["capital"] == "34525000", v
    assert v["categorie_registre"] == "Société", v
    assert v["responsable"] == "غسان سلامة", v
    assert v["qualite_responsable"] == "رئيس مجلس إدارة", v
    assert v["type_modification"] == "Dépôt des états financiers", v
    assert v["denomination"] == "VILAVI", v
    assert v["denomination_latin"] == "VILAVI", v
    assert v["adresse"].startswith("عدد 79"), v
    assert "المثلجات" in v["activite"], v

    n = parse_rne_visible_fields(NEXT_GEN)
    assert n["numero_publication"] == "ARD000150493", n
    assert n["type_publication"] == "Réservation dénomination", n
    assert n["type_demande_reservation"] == "CREATION", n
    assert n["numero_certificat"] == "2026144893297", n
    assert n["date_reservation"] == "2026-07-27", n
    assert n["delai_reservation"] == "2027-01-27", n
    assert n["type_reservation"] == "Dénomination", n
    assert n["denomination"] == "Next gen Enterprise Technology & Optimization", n

    print("RNE PARSER TEST OK")
    print("VILAVI:", v)
    print("NEXT GEN:", n)

if __name__ == "__main__":
    main()
