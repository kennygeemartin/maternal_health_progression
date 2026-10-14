"""Resend delivery with persisted idempotency and mailbox verification."""
import hashlib
import json
import os
from datetime import timedelta
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from .database import EmailJob, EmailVerification, User, PregnancyPreferences, now

def configured():
    return bool(os.getenv("RESEND_API_KEY") and os.getenv("EMAIL_FROM"))

def public_url():
    url = os.getenv("APP_PUBLIC_URL", "").rstrip("/")
    if not url and os.getenv("VERCEL_PROJECT_PRODUCTION_URL"):
        url = "https://" + os.environ["VERCEL_PROJECT_PRODUCTION_URL"]
    if not url.startswith("https://"):
        return None
    return url

class MailFailure(Exception):
    pass

def send_provider(recipient, subject, body, key):
    if not configured():
        raise MailFailure("email_not_configured")
    payload = json.dumps({"from": os.environ["EMAIL_FROM"], "to": [recipient],
                          "subject": subject, "text": body}).encode()
    request = Request("https://api.resend.com/emails", data=payload, method="POST",
                      headers={"Authorization": "Bearer " + os.environ["RESEND_API_KEY"],
                               "Content-Type": "application/json", "Idempotency-Key": key,
                               "User-Agent": "Bloom/1.0"})
    try:
        with urlopen(request, timeout=15) as response:
            result = json.load(response)
        identifier = result.get("id")
        if not isinstance(identifier, str) or not identifier:
            raise MailFailure("invalid_provider_response")
        return identifier
    except HTTPError as error:
        raise MailFailure("email_provider_http_" + str(error.code)) from None
    except (URLError, TimeoutError, OSError, ValueError, AttributeError, TypeError):
        raise MailFailure("email_provider_unavailable") from None

def verified(db, user_id):
    verification = db.get(EmailVerification, user_id)
    return bool(verification and verification.verified_at)

def queue(db, user, pid, kind, subject, body, identity):
    key = hashlib.sha256(f"{user.id}:{pid}:{kind}:{identity}".encode()).hexdigest()
    existing = db.scalar(select(EmailJob).where(EmailJob.dedupe_key == key))
    if existing:
        if kind == "monthly_guidance" and existing.status in {"pending", "failed", "cancelled"} and not existing.attempts:
            existing.subject, existing.body = subject, body
        if existing.status == "cancelled" and kind == "monthly_guidance" and not existing.provider_id:
            existing.status = "pending"
        return existing
    job = EmailJob(user_id=user.id, pregnancy_id=pid, dedupe_key=key, kind=kind, subject=subject, body=body)
    try:
        with db.begin_nested():
            db.add(job)
            db.flush()
    except IntegrityError:
        return db.scalar(select(EmailJob).where(EmailJob.dedupe_key == key))
    return job

def summary(job):
    return {"id": job.id, "kind": job.kind, "status": job.status,
            "subject": job.subject,
            "error_code": job.error_code, "created_at": job.created_at}

def dispatch(db, job):
    # Retrying after 24h may duplicate an email whose provider acknowledgement was lost.
    # Such jobs require operator review rather than automatic replay.
    if job.status in {"accepted", "cancelled", "review_required"}:
        return summary(job)
    if not configured():
        job.status, job.error_code = "failed", "email_not_configured"
        db.commit()
        return summary(job)
    if job.attempts and job.created_at.replace(tzinfo=now().tzinfo) < now() - timedelta(hours=23):
        job.status, job.error_code = "review_required", "idempotency_window_expired"
        db.commit()
        return summary(job)
    preference = db.get(PregnancyPreferences, job.pregnancy_id)
    if job.kind != "verification" and (not preference or not preference.email_enabled or not verified(db, job.user_id)):
        job.status = "cancelled"
        db.commit()
        return summary(job)
    # A crashed worker can be reclaimed within the provider's idempotency window.
    stale = now() - timedelta(minutes=2)
    claim = db.execute(update(EmailJob).where(EmailJob.id == job.id,
        ((EmailJob.status.in_(["pending", "failed"])) | ((EmailJob.status == "sending") & (EmailJob.updated_at < stale))),
        EmailJob.attempts < 5).values(status="sending", attempts=EmailJob.attempts + 1, updated_at=now()))
    db.commit()
    db.refresh(job)
    if not claim.rowcount:
        return summary(job)
    user = db.get(User, job.user_id)
    try:
        job.provider_id = send_provider(user.email, job.subject, job.body, "bloom-" + job.dedupe_key)
        job.status, job.error_code = "accepted", None
        if job.kind == "verification":
            # Remove the bearer verification URL once it has been accepted by the provider.
            job.body = "Mailbox verification message accepted by provider."
    except MailFailure as error:
        job.status, job.error_code = "failed", str(error)
    job.updated_at = now()
    db.commit()
    return summary(job)
