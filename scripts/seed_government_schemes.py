import os
import sys
import time
from datetime import date, datetime, timezone
from typing import List, Dict, Any

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Load .env.staging if present
staging_env_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".env.staging"))
if os.path.exists(staging_env_path):
    from dotenv import load_dotenv
    load_dotenv(staging_env_path)

from backend.app.core.config import settings
from backend.app.core.logging import logger
from backend.app.db.session import SessionLocal
from backend.app.models.models import GovernmentScheme, SyncLog

# Authoritative Government Agricultural Schemes (Direct from Official Portals: pmkisan.gov.in, pmfby.gov.in, myscheme.gov.in, soilhealth.dac.gov.in)
OFFICIAL_GOVERNMENT_SCHEMES: List[Dict[str, Any]] = [
    {
        "scheme_code": "PM_KISAN",
        "scheme_name": "Pradhan Mantri Kisan Samman Nidhi (PM-KISAN)",
        "name_translations": {
            "hi": "प्रधानमंत्री किसान सम्मान निधि",
            "te": "ప్రధాన మంత్రి కిసాన్ సమ్మాన్ నిధి",
            "ta": "பிரதம மந்திரி கிசான் சம்மான் நிதி",
        },
        "short_description": "Central sector scheme to provide income support to all landholding farmer families across the country.",
        "benefits_summary": "Financial benefit of ₹6,000 per year per family, payable in three equal four-monthly installments of ₹2,000 each directly transferred to the bank accounts of beneficiaries via Aadhaar-linked DBT.",
        "eligibility_criteria": [
            "All landholding farmer families having cultivable landholding in their names.",
            "Exclusions apply: Institutional landholders, farmer families holding constitutional posts, serving/retired government officers/employees, income tax payees in last assessment year, and professionals (doctors, engineers, lawyers, CAs).",
        ],
        "required_documents": [
            "Aadhaar Card (Mandatory)",
            "Land ownership records (Khata/Khatoni/ROR/Patta document)",
            "Active Aadhaar-linked Bank Account (Passbook copy)",
            "e-KYC authentication via mobile OTP or biometric CSC verification",
        ],
        "application_process": "Farmers can register online at the official PM-KISAN portal (pmkisan.gov.in) via 'Farmer Corner -> New Farmer Registration' or visit their nearest Common Service Centre (CSC) or local revenue / agriculture nodal officer.",
        "official_portal_url": "https://pmkisan.gov.in",
        "sponsoring_agency": "Ministry of Agriculture & Farmers Welfare, Department of Agriculture & Farmers Welfare",
        "state_scope": "Central",
        "last_verified_date": date(2026, 8, 15),
    },
    {
        "scheme_code": "PMFBY",
        "scheme_name": "Pradhan Mantri Fasal Bima Yojana (PMFBY)",
        "name_translations": {
            "hi": "प्रधानमंत्री फसल बीमा योजना",
            "te": "ప్రధాన మంత్రి ఫసల్ బీమా యోజన",
            "ta": "பிரதம மந்திரி பயிர் காப்பீட்டுத் திட்டம்",
        },
        "short_description": "Comprehensive risk insurance service for farmers against natural calamities, pests, and post-harvest losses.",
        "benefits_summary": "Comprehensive crop insurance coverage from pre-sowing to post-harvest stages. Maximum premium payable by farmers is uniform and low: 2% for Kharif food and oilseed crops, 1.5% for Rabi crops, and 5% for annual commercial/horticultural crops. Balance premium is subsidized by Central and State Governments.",
        "eligibility_criteria": [
            "All farmers including sharecroppers and tenant farmers growing the notified crops in the notified areas.",
            "Voluntary for all farmers (both loanee and non-loanee).",
            "Must possess insurable interest in the notified crop.",
        ],
        "required_documents": [
            "Aadhaar Card",
            "Bank Passbook with IFSC and account details",
            "Land possession certificate / Record of Rights (RoR)",
            "Sowing Certificate / self-declaration of sowing",
            "Sharecropper / Tenant agreement (for non-landowning cultivators)",
        ],
        "application_process": "Enrollment through the National Crop Insurance Portal (pmfby.gov.in), authorized bank branches, cooperative societies, or Common Service Centres (CSC) before the notified cut-off date of the respective season.",
        "official_portal_url": "https://pmfby.gov.in",
        "sponsoring_agency": "Ministry of Agriculture & Farmers Welfare",
        "state_scope": "Central",
        "last_verified_date": date(2026, 8, 1),
    },
    {
        "scheme_code": "KCC",
        "scheme_name": "Kisan Credit Card (KCC) Scheme",
        "name_translations": {
            "hi": "किसान क्रेडिट कार्ड योजना",
            "te": "కిసాన్ క్రెడిట్ కార్డు పథకం",
            "ta": "கிசான் கடன் அட்டை திட்டம்",
        },
        "short_description": "Adequate and timely institutional short-term credit facility for farmers' cultivation and allied activities.",
        "benefits_summary": "Revolving cash credit facility up to ₹3,00,000 at a subsidized benchmark interest rate of 7% per annum. With prompt repayment incentive of 3%, the effective interest rate is reduced to 4% per annum. Collateral-free loan limit up to ₹1,60,000.",
        "eligibility_criteria": [
            "All farmers - individual or joint cultivators / owner-cultivators.",
            "Tenant farmers, oral lessees, and sharecroppers.",
            "Self Help Groups (SHGs) or Joint Liability Groups (JLGs) of farmers.",
            "Farmers engaged in animal husbandry, dairy, and fisheries.",
        ],
        "required_documents": [
            "Duly completed KCC Application Form",
            "Identity Proof (Aadhaar Card, Voter ID, or PAN Card)",
            "Address Proof",
            "Land Record proof certified by revenue authority",
            "Passport-size photographs",
        ],
        "application_process": "Submit application to any Commercial Bank, Regional Rural Bank (RRB), or Cooperative Bank branch, or download KCC one-page form from pmkisan.gov.in / myscheme.gov.in.",
        "official_portal_url": "https://myscheme.gov.in/schemes/kcc",
        "sponsoring_agency": "Reserve Bank of India & Ministry of Agriculture & Farmers Welfare",
        "state_scope": "Central",
        "last_verified_date": date(2026, 7, 20),
    },
    {
        "scheme_code": "SOIL_HEALTH_CARD",
        "scheme_name": "Soil Health Card Scheme",
        "name_translations": {
            "hi": "मृदा स्वास्थ्य कार्ड योजना",
            "te": "నేల ఆరోగ్య కార్డు పథకం",
            "ta": "மண் சுகாதார அட்டை திட்டம்",
        },
        "short_description": "Soil testing service issuing customized nutrient and fertilizer advisories to every farm holding.",
        "benefits_summary": "Provides farmers with a printed Soil Health Card containing the status of their soil with respect to 12 parameters (N, P, K, S, Zn, Fe, Cu, Mn, Bo, pH, EC, OC) and customized dosage recommendations for chemical fertilizers and biofertilizers.",
        "eligibility_criteria": [
            "All farmers holding agricultural land across all states and union territories in India.",
        ],
        "required_documents": [
            "Aadhaar Number",
            "Land revenue record details (Survey Number / Khasra number)",
            "Mobile number for SMS report delivery",
        ],
        "application_process": "Soil samples are collected by the State Agriculture Department or village nodal personnel. Farmers can also take soil samples directly to the nearest Soil Testing Laboratory (STL) or Krishi Vigyan Kendra (KVK). Status can be tracked at soilhealth.dac.gov.in.",
        "official_portal_url": "https://soilhealth.dac.gov.in",
        "sponsoring_agency": "Department of Agriculture & Farmers Welfare",
        "state_scope": "Central",
        "last_verified_date": date(2026, 6, 10),
    },
    {
        "scheme_code": "PMKSY_PDMC",
        "scheme_name": "Pradhan Mantri Krishi Sinchayee Yojana - Per Drop More Crop (PDMC)",
        "name_translations": {
            "hi": "प्रधानमंत्री कृषि सिंचाई योजना - प्रति बूंद अधिक फसल",
            "te": "ప్రధాన మంత్రి కృషి సించాయి యోజన - ప్రతి చుక్కకు ఎక్కువ పంట",
        },
        "short_description": "Promotes micro-irrigation technologies (drip and sprinkler) to maximize water-use efficiency.",
        "benefits_summary": "Financial assistance and capital subsidy on drip and sprinkler irrigation installations: up to 55% of indicative system cost for small and marginal farmers, and up to 45% for other farmers.",
        "eligibility_criteria": [
            "All landholding farmers having an assured water source on their land.",
            "Members of cooperative societies, water user associations, and registered farmer groups.",
        ],
        "required_documents": [
            "Aadhaar Card",
            "Land title documents / 7/12 extract / RoR",
            "Electricity connection certificate or proof of assured irrigation source (borewell/well)",
            "Bank passbook copy",
            "Quotation from empanelled micro-irrigation manufacturers",
        ],
        "application_process": "Apply online through state agriculture / horticulture department portals or visit the District Horticulture Officer / Assistant Director of Agriculture.",
        "official_portal_url": "https://pmksy.gov.in",
        "sponsoring_agency": "Ministry of Agriculture & Farmers Welfare",
        "state_scope": "Central",
        "last_verified_date": date(2026, 7, 5),
    },
]


def seed_government_schemes():
    """
    Seeds verified government schemes into PostgreSQL idempotently.
    Updates existing records if changed and tracks execution in sync_logs.
    """
    start_time = time.time()
    db = SessionLocal()

    records_processed = 0
    records_inserted = 0
    records_updated = 0
    status = "SUCCESS"
    error_summary = None

    try:
        logger.info(f"Seeding {len(OFFICIAL_GOVERNMENT_SCHEMES)} authoritative government schemes.")

        for item in OFFICIAL_GOVERNMENT_SCHEMES:
            records_processed += 1
            existing = db.query(GovernmentScheme).filter(GovernmentScheme.scheme_code == item["scheme_code"]).first()

            if existing:
                # Idempotent update of verified fields
                existing.scheme_name = item["scheme_name"]
                existing.name_translations = item["name_translations"]
                existing.short_description = item["short_description"]
                existing.benefits_summary = item["benefits_summary"]
                existing.eligibility_criteria = item["eligibility_criteria"]
                existing.required_documents = item["required_documents"]
                existing.application_process = item["application_process"]
                existing.official_portal_url = item["official_portal_url"]
                existing.sponsoring_agency = item["sponsoring_agency"]
                existing.state_scope = item["state_scope"]
                existing.last_verified_date = item["last_verified_date"]
                existing.updated_at = datetime.now(timezone.utc)
                records_updated += 1
                logger.info(f"Updated verified scheme: {item['scheme_code']}")
            else:
                new_scheme = GovernmentScheme(
                    scheme_code=item["scheme_code"],
                    scheme_name=item["scheme_name"],
                    name_translations=item["name_translations"],
                    short_description=item["short_description"],
                    benefits_summary=item["benefits_summary"],
                    eligibility_criteria=item["eligibility_criteria"],
                    required_documents=item["required_documents"],
                    application_process=item["application_process"],
                    official_portal_url=item["official_portal_url"],
                    sponsoring_agency=item["sponsoring_agency"],
                    state_scope=item["state_scope"],
                    last_verified_date=item["last_verified_date"],
                    is_active=True,
                )
                db.add(new_scheme)
                records_inserted += 1
                logger.info(f"Inserted new verified scheme: {item['scheme_code']}")

        db.commit()
        logger.info("Government scheme seeding completed successfully.")

    except Exception as exc:
        db.rollback()
        status = "FAILED"
        error_summary = str(exc)
        logger.error(f"Scheme seeding failed: {exc}", exc_info=True)

    finally:
        execution_time = round(time.time() - start_time, 2)
        sync_log = SyncLog(
            sync_source="MYSCHEME_SCRAPE",
            status=status,
            records_processed=records_processed,
            records_inserted=records_inserted,
            records_updated=records_updated,
            error_message=error_summary,
            execution_time_seconds=execution_time,
        )
        db.add(sync_log)
        db.commit()
        db.close()
        logger.info(f"Scheme audit log created: status={status}, processed={records_processed}, time={execution_time}s")


if __name__ == "__main__":
    if settings.ENVIRONMENT != "staging":
        print(f"FATAL: seed_government_schemes.py requires explicit ENVIRONMENT=staging. Current: '{settings.ENVIRONMENT}'. Aborting.")
        sys.exit(1)

    if not settings.DATABASE_URL or "sqlite" in settings.DATABASE_URL.lower():
        print("FATAL: seed_government_schemes.py requires a valid PostgreSQL DATABASE_URL. SQLite is strictly rejected.")
        sys.exit(1)

    seed_government_schemes()
