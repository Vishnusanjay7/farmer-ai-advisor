from backend.app.db.session import SessionLocal
from backend.app.models.models import GovernmentScheme
from scripts.seed_government_schemes import seed_government_schemes


def test_scheme_seeding_and_idempotency():
    db = SessionLocal()
    initial_count = db.query(GovernmentScheme).count()

    # Run seed script
    seed_government_schemes()
    count_after_first = db.query(GovernmentScheme).count()
    assert count_after_first >= 5

    # Run seed script again to verify idempotency
    seed_government_schemes()
    count_after_second = db.query(GovernmentScheme).count()
    assert count_after_second == count_after_first

    # Verify PM-KISAN fields
    pm_kisan = db.query(GovernmentScheme).filter(GovernmentScheme.scheme_code == "PM_KISAN").first()
    assert pm_kisan is not None
    assert pm_kisan.official_portal_url == "https://pmkisan.gov.in"
    assert len(pm_kisan.eligibility_criteria) > 0
    assert len(pm_kisan.required_documents) > 0
    assert pm_kisan.last_verified_date is not None
    db.close()
