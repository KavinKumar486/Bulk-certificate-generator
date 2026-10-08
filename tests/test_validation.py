from types import SimpleNamespace
import pytest

from app.models import Job
from app.services.job_service import validate_recipient


# ----------------------------------------------------------------------
# Level 1 Validation Tests (API Structure -> 422, no DB side-effects)
# ----------------------------------------------------------------------


def test_level1_empty_recipients_fails(client, auth_headers, db_session):
    payload = {"event_name": "Test Event", "recipients": []}
    response = client.post("/v1/jobs", json=payload, headers=auth_headers)
    assert response.status_code == 422
    assert db_session.query(Job).count() == 0


def test_level1_missing_event_name_fails(client, auth_headers, db_session):
    payload = {"recipients": [{"name": "Asha"}]}
    response = client.post("/v1/jobs", json=payload, headers=auth_headers)
    assert response.status_code == 422
    assert db_session.query(Job).count() == 0


def test_level1_blank_event_name_fails(client, auth_headers, db_session):
    payload = {"event_name": "   ", "recipients": [{"name": "Asha"}]}
    response = client.post("/v1/jobs", json=payload, headers=auth_headers)
    assert response.status_code == 422
    assert db_session.query(Job).count() == 0


def test_level1_too_long_event_name_fails(client, auth_headers, db_session):
    payload = {"event_name": "E" * 201, "recipients": [{"name": "Asha"}]}
    response = client.post("/v1/jobs", json=payload, headers=auth_headers)
    assert response.status_code == 422
    assert db_session.query(Job).count() == 0


def test_level1_exceeding_max_recipients_fails(client, auth_headers, db_session, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "MAX_RECIPIENTS_PER_REQUEST", 3)

    payload = {
        "event_name": "Exceeded Event",
        "recipients": [{"name": f"User {i}"} for i in range(4)],
    }
    response = client.post("/v1/jobs", json=payload, headers=auth_headers)
    assert response.status_code == 422
    assert db_session.query(Job).count() == 0


@pytest.mark.parametrize(
    "bad_recipient",
    [
        {"name": 12345},  # name is number instead of string
        {"name": ["Asha"]},  # name is list instead of string
        {"email": 123},  # email is number instead of string
        {"course": ["Python"]},  # course is list instead of string
        {"date": 20261001},  # date is number instead of string
    ],
)
def test_level1_wrong_field_types_fails(client, auth_headers, db_session, bad_recipient):
    payload = {
        "event_name": "Test Event",
        "recipients": [bad_recipient],
    }
    response = client.post("/v1/jobs", json=payload, headers=auth_headers)
    assert response.status_code == 422
    assert db_session.query(Job).count() == 0


def test_level1_recipient_not_an_object_fails(client, auth_headers, db_session):
    payload = {
        "event_name": "Test Event",
        "recipients": ["just a string instead of object"],
    }
    response = client.post("/v1/jobs", json=payload, headers=auth_headers)
    assert response.status_code == 422
    assert db_session.query(Job).count() == 0


# ----------------------------------------------------------------------
# Level 2 Validation Unit Tests (Calling validate_recipient directly)
# ----------------------------------------------------------------------


def test_level2_valid_recipient_passes():
    cert = SimpleNamespace(
        recipient_name="Asha Rao",
        email="asha@example.com",
        course="FastAPI 101",
        issue_date="2026-10-01",
    )
    # Should not raise
    validate_recipient(cert)


def test_level2_minimal_valid_recipient_passes():
    cert = SimpleNamespace(
        recipient_name="Asha Rao",
        email=None,
        course=None,
        issue_date=None,
    )
    validate_recipient(cert)


def test_level2_blank_name_raises():
    for blank in ["", "   ", None]:
        cert = SimpleNamespace(recipient_name=blank, email=None, course=None, issue_date=None)
        with pytest.raises(ValueError, match="Recipient name is required"):
            validate_recipient(cert)


def test_level2_overlong_name_raises():
    cert = SimpleNamespace(recipient_name="A" * 101, email=None, course=None, issue_date=None)
    with pytest.raises(ValueError, match="Recipient name must not exceed 100 characters"):
        validate_recipient(cert)


def test_level2_overlong_course_raises():
    cert = SimpleNamespace(recipient_name="Asha", email=None, course="C" * 151, issue_date=None)
    with pytest.raises(ValueError, match="Course must not exceed 150 characters"):
        validate_recipient(cert)


def test_level2_bad_email_raises():
    for bad_email in ["notanemail", "user@", "@domain.com", "user@domain..com"]:
        cert = SimpleNamespace(recipient_name="Asha", email=bad_email, course=None, issue_date=None)
        with pytest.raises(ValueError, match="Invalid email format"):
            validate_recipient(cert)


def test_level2_bad_date_raises():
    for bad_date in ["not-a-date", "2026/10/01", "2026-13-01", "01-10-2026", "2026-02-30"]:
        cert = SimpleNamespace(recipient_name="Asha", email=None, course=None, issue_date=bad_date)
        with pytest.raises(ValueError, match="Date must be in ISO format YYYY-MM-DD"):
            validate_recipient(cert)


# ----------------------------------------------------------------------
# Mixed Row Acceptance Test (Level 2 flaws do not fail Level 1 HTTP request)
# ----------------------------------------------------------------------


def test_request_with_invalid_recipient_values_is_accepted(client, auth_headers, db_session):
    payload = {
        "event_name": "PyCon Workshop 2026",
        "recipients": [
            {"name": "Valid User", "email": "valid@example.com"},
            {"name": "", "email": "bad-email", "date": "invalid-date"},  # Has Level 2 errors
        ],
    }
    response = client.post("/v1/jobs", json=payload, headers=auth_headers)
    assert response.status_code == 202
    data = response.json()
    assert data["total"] == 2

    # Both rows were stored in database
    db_job = db_session.query(Job).filter_by(id=data["job_id"]).first()
    assert db_job is not None
    assert len(db_job.certificates) == 2
