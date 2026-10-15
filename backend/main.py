import hashlib
import hmac
import os
import secrets
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated, Literal
import time

from fastapi import FastAPI, Depends, HTTPException, Request, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ConfigDict, model_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .database import (initialize_database, SessionLocal, User, LoginSession, Pregnancy,
                       Observation, Prediction, Guidance, GuidanceDelivery, Notification, ModelRegistry, AuditEvent,
                       PregnancyPreferences, GuidanceMonth, EmailVerification, EmailJob, now)
from . import inference
from . import hosted_model, guidance_service, mail, monthly_catalog
from . import notification_messages

SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"
if os.getenv("APP_ENV") == "production" and not SECURE:
    raise RuntimeError("Production requires COOKIE_SECURE=true and HTTPS")

@asynccontextmanager
async def lifespan(app):
    initialize_database()
    with SessionLocal() as db:
        monthly_catalog.seed(db)
        meta = inference.metadata()
        entry = db.get(ModelRegistry, meta["version"])
        if not entry:
            db.add(ModelRegistry(version=meta["version"], metadata_json=meta))
        else:
            entry.metadata_json = meta
        try:
            db.commit()
        except IntegrityError:
            # Another cold start can register the same model after our existence check.
            db.rollback()
            entry = db.get(ModelRegistry, meta["version"])
            if entry is None:
                raise
            entry.metadata_json = meta
            db.commit()
    yield

app = FastAPI(title="Bloom Maternal Health", version="1.0.0", lifespan=lifespan)

@app.middleware("http")
async def headers(request, call_next):
    # Require a custom header on mutations, including login, to prevent cross-site form attacks.
    if request.method in {"POST", "PATCH", "DELETE", "PUT"} and request.headers.get("x-bloom-request") != "1":
        return Response("Missing request header", status_code=403)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Content-Security-Policy"] = "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; frame-ancestors 'none'"
    if request.url.path == "/docs":
        # FastAPI's standard documentation UI uses jsDelivr assets and an inline initializer.
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self' https://cdn.jsdelivr.net 'unsafe-inline'; style-src 'self' https://cdn.jsdelivr.net 'unsafe-inline'; img-src 'self' data: https://fastapi.tiangolo.com; object-src 'none'; frame-ancestors 'none'"
    if request.url.path.startswith("/api"):
        response.headers["Cache-Control"] = "no-store"
    return response

def get_db():
    with SessionLocal() as db:
        yield db

DB = Annotated[Session, Depends(get_db)]

def password_hash(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.scrypt(password.encode(), salt=salt.encode(), n=16384, r=8, p=1).hex()
    return salt + ":" + digest

def current_user(request: Request, db: DB):
    token = request.cookies.get("bloom_session", "")
    session = db.get(LoginSession, hashlib.sha256(token.encode()).hexdigest()) if token else None
    if not session or session.expires_at.replace(tzinfo=timezone.utc) < now():
        raise HTTPException(401, "Please sign in")
    return db.get(User, session.user_id)

AUTH = Annotated[User, Depends(current_user)]

def admin(user: AUTH):
    if user.role != "admin":
        raise HTTPException(403, "Administrator access required")
    return user

ADMIN = Annotated[User, Depends(admin)]

def audit(db, user, action, resource):
    db.add(AuditEvent(user_id=user.id, action=action, resource=str(resource)))

def owned(db, user, pregnancy_id):
    pregnancy = db.get(Pregnancy, pregnancy_id)
    if not pregnancy or pregnancy.user_id != user.id:
        raise HTTPException(404, "Pregnancy not found")
    return pregnancy

def pregnancy_json(p):
    days = (date.today() - p.lmp).days
    week = days // 7
    return {"id": p.id, "label": p.label, "lmp": p.lmp, "due_date": p.lmp + timedelta(days=280),
            "weeks": week, "days": days % 7, "stage": 1 if week < 14 else 2 if week < 28 else 3}

class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

class Credentials(Strict):
    email: str = Field(min_length=5, max_length=254, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
    password: str = Field(min_length=10, max_length=128)

class Registration(Credentials):
    name: str = Field(min_length=1, max_length=100)

def start_session(response, db, user):
    token = secrets.token_urlsafe(32)
    db.add(LoginSession(token_hash=hashlib.sha256(token.encode()).hexdigest(), user_id=user.id,
                        expires_at=now() + timedelta(days=7)))
    response.set_cookie("bloom_session", token, httponly=True, secure=SECURE, samesite="strict", max_age=604800)

@app.post("/api/auth/register", status_code=201)
def register(data: Registration, response: Response, db: DB):
    user = User(name=data.name.strip(), email=data.email.lower().strip(), password_hash=password_hash(data.password))
    if not user.name:
        raise HTTPException(422, "Name is required")
    db.add(user)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Unable to register with this email")
    start_session(response, db, user)
    audit(db, user, "register", user.id)
    db.commit()
    return {"id": user.id, "name": user.name, "role": user.role}

@app.post("/api/auth/login")
def login(data: Credentials, response: Response, db: DB):
    user = db.scalar(select(User).where(User.email == data.email.lower().strip()))
    stored = user.password_hash if user else password_hash("dummy-password-for-timing")
    if not hmac.compare_digest(password_hash(data.password, stored.split(":")[0]), stored) or not user:
        raise HTTPException(401, "Email or password is incorrect")
    start_session(response, db, user)
    audit(db, user, "login", user.id)
    db.commit()
    return {"id": user.id, "name": user.name, "role": user.role}

@app.post("/api/auth/logout")
def logout(request: Request, response: Response, db: DB, user: AUTH):
    session = db.get(LoginSession, hashlib.sha256(request.cookies["bloom_session"].encode()).hexdigest())
    db.delete(session)
    db.commit()
    response.delete_cookie("bloom_session")
    return {"ok": True}

@app.get("/api/me")
def me(user: AUTH):
    return {"id": user.id, "name": user.name, "role": user.role, "email": user.email}

class PregnancyInput(Strict):
    lmp: date
    label: str = Field(default="My pregnancy", min_length=1, max_length=100)
    month: int | None = Field(default=None, ge=1, le=9)

    @model_validator(mode="after")
    def dates(self):
        if not 0 <= (date.today() - self.lmp).days <= 308:
            raise ValueError("Last menstrual period must be within the last 44 weeks")
        return self

@app.get("/api/pregnancies")
def pregnancies(db: DB, user: AUTH):
    return [pregnancy_json(p) for p in db.scalars(select(Pregnancy).where(Pregnancy.user_id == user.id).order_by(Pregnancy.lmp.desc(), Pregnancy.id.desc()))]

@app.post("/api/pregnancies", status_code=201)
def create_pregnancy(data: PregnancyInput, db: DB, user: AUTH):
    p = Pregnancy(user_id=user.id, **data.model_dump(exclude={"month"}))
    db.add(p)
    db.flush()
    if data.month is not None:
        db.add(PregnancyPreferences(pregnancy_id=p.id, month=data.month))
    audit(db, user, "pregnancy.create", p.id)
    db.commit()
    return pregnancy_json(p)

class PreferenceInput(Strict):
    month: int = Field(ge=1, le=9)
    email_enabled: bool = False
    remote_assessment_enabled: bool = False

def queue_monthly(db, user, pregnancy):
    preference = db.get(PregnancyPreferences, pregnancy.id)
    if not preference or not preference.email_enabled:
        return None, "disabled"
    if not mail.verified(db, user.id):
        return None, "verification_required"
    latest = db.scalar(select(Observation).where(Observation.pregnancy_id == pregnancy.id).order_by(Observation.observed_at.desc(), Observation.id.desc()).limit(1))
    prediction = db.scalar(select(Prediction).where(Prediction.observation_id == latest.id)) if latest else None
    entries = guidance_service.content(db, preference.month, prediction.result["category"] if prediction else "all")
    if not entries:
        return None, "no_reviewed_guidance"
    subject, body, identity = guidance_service.email_content(preference.month, entries, user.name)
    return mail.queue(db, user, pregnancy.id, "monthly_guidance", subject, body, identity), "queued"

def verification_message(db, user, pregnancy):
    if not mail.configured() or not mail.public_url():
        return {"status": "not_configured", "message": "Email delivery needs a sender and public app URL to be configured."}
    verification = db.get(EmailVerification, user.id)
    if verification and verification.verified_at:
        return {"status": "verified"}
    if verification and verification.requested_at and verification.requested_at.replace(tzinfo=timezone.utc) > now() - timedelta(minutes=15):
        previous = db.scalar(select(EmailJob).where(EmailJob.user_id == user.id, EmailJob.kind == "verification").order_by(EmailJob.id.desc()).limit(1))
        if previous:
            return mail.dispatch(db, previous)
    token = secrets.token_urlsafe(32)
    if not verification:
        verification = EmailVerification(user_id=user.id)
        db.add(verification)
    verification.token_hash = hashlib.sha256(token.encode()).hexdigest()
    verification.expires_at, verification.requested_at = now() + timedelta(hours=24), now()
    link = mail.public_url() + "/?email_token=" + token
    job = mail.queue(db, user, pregnancy.id, "verification", "Verify your Bloom email address",
                    "Welcome to Bloom. Confirm your email address to receive pregnancy guidance and care updates.\n\n" + link +
                    "\n\nThis link expires in 24 hours. If you did not request it, you can ignore this email.", verification.token_hash)
    db.commit()
    return mail.dispatch(db, job)

@app.put("/api/pregnancies/{pid}/preferences")
def preferences(pid: int, data: PreferenceInput, db: DB, user: AUTH):
    pregnancy = owned(db, user, pid)
    preference = db.get(PregnancyPreferences, pid)
    if preference and (preference.month != data.month or not data.email_enabled):
        for queued in db.scalars(select(EmailJob).where(EmailJob.pregnancy_id == pid, EmailJob.kind == "monthly_guidance", EmailJob.status.in_(["pending", "failed"]))):
            queued.status = "cancelled"
    if not preference:
        preference = PregnancyPreferences(pregnancy_id=pid, **data.model_dump())
        db.add(preference)
    else:
        for key, value in data.model_dump().items():
            setattr(preference, key, value)
    audit(db, user, "pregnancy.preferences", pid)
    db.commit()
    if data.email_enabled:
        if not mail.verified(db, user.id):
            email = verification_message(db, user, pregnancy)
        else:
            job, status = queue_monthly(db, user, pregnancy)
            db.commit()
            email = mail.dispatch(db, job) if job else {"status": status}
    else:
        email = {"status": "disabled"}
    return {"saved": True, "email": email}

class VerificationInput(Strict):
    token: str = Field(min_length=32, max_length=100)

@app.post("/api/email/verify")
def verify_email(data: VerificationInput, db: DB):
    digest = hashlib.sha256(data.token.encode()).hexdigest()
    verification = db.scalar(select(EmailVerification).where(EmailVerification.token_hash == digest).with_for_update())
    if not verification or not verification.expires_at or verification.expires_at.replace(tzinfo=timezone.utc) < now():
        raise HTTPException(400, "The email verification link is invalid or expired. Request a new email from your pregnancy preferences.")
    verification.verified_at, verification.token_hash = now(), None
    user = db.get(User, verification.user_id)
    audit(db, user, "email.verified", user.id)
    jobs = []
    for pregnancy in db.scalars(select(Pregnancy).where(Pregnancy.user_id == user.id)):
        job, _ = queue_monthly(db, user, pregnancy)
        if job:
            jobs.append(job)
    db.commit()
    # Remaining jobs are picked up by the authenticated daily worker.
    for job in jobs[:2]:
        mail.dispatch(db, job)
    return {"verified": True, "message": "Your email is confirmed. Your pregnancy guidance is ready for delivery."}

@app.post("/api/pregnancies/{pid}/email-guidance")
def email_guidance(pid: int, db: DB, user: AUTH):
    pregnancy = owned(db, user, pid)
    preference = db.get(PregnancyPreferences, pid)
    if not preference or not preference.email_enabled:
        raise HTTPException(409, "Enable guidance emails in pregnancy preferences first.")
    if not mail.verified(db, user.id):
        return verification_message(db, user, pregnancy)
    job, status = queue_monthly(db, user, pregnancy)
    db.commit()
    return mail.dispatch(db, job) if job else {"status": status}

@app.post("/api/emails/{jid}/retry")
def retry_email(jid: int, db: DB, user: AUTH):
    job = db.get(EmailJob, jid)
    if not job or job.user_id != user.id:
        raise HTTPException(404, "Email not found")
    return mail.dispatch(db, job)

@app.get("/api/jobs/emails")
def email_worker(request: Request, db: DB):
    secret = os.getenv("CRON_SECRET", "")
    if not secret or not hmac.compare_digest(request.headers.get("authorization", ""), "Bearer " + secret):
        raise HTTPException(401, "Worker authorization required")
    if not mail.configured():
        return {"status": "email_not_configured", "processed": 0}
    started = time.monotonic()
    for preference in db.scalars(select(PregnancyPreferences).where(PregnancyPreferences.email_enabled == True).order_by(PregnancyPreferences.last_checked_at.asc().nullsfirst()).limit(25)):
        pregnancy = db.get(Pregnancy, preference.pregnancy_id)
        user = db.get(User, pregnancy.user_id)
        queue_monthly(db, user, pregnancy)
        preference.last_checked_at = now()
    db.commit()
    jobs = list(db.scalars(select(EmailJob).where(EmailJob.status.in_(["pending", "failed", "sending"]), EmailJob.attempts < 5).order_by(EmailJob.id).limit(2)))
    processed = []
    for job in jobs:
        if time.monotonic() - started > 30:
            break
        processed.append(mail.dispatch(db, job))
    return {"processed": len(processed), "statuses": [item["status"] for item in processed]}

class Measurements(Strict):
    Age: float = Field(ge=10, le=60)
    BodyTempC: float | None = Field(default=None, ge=32, le=44)
    BodyTempF: float | None = Field(default=None, ge=90, le=110)
    HeartRate: float = Field(ge=30, le=220)
    SystolicBP: float = Field(ge=60, le=260)
    DiastolicBP: float = Field(ge=30, le=160)
    BMI: float | None = Field(default=None, ge=10, le=70)
    HbA1c: float | None = Field(default=None, ge=2, le=20)
    FastingGlucose: float = Field(ge=20, le=600)

    @model_validator(mode="after")
    def pressure(self):
        if (self.BodyTempC is None) == (self.BodyTempF is None):
            raise ValueError("Record exactly one temperature: BodyTempC in Celsius or a legacy BodyTempF reading")
        if self.SystolicBP <= self.DiastolicBP:
            raise ValueError("Systolic pressure must exceed diastolic pressure")
        return self

UNITS = {"Age": "years", "BodyTempC": "degC", "BodyTempF": "degF", "HeartRate": "bpm", "SystolicBP": "mmHg", "DiastolicBP": "mmHg", "BMI": "kg/m2", "HbA1c": "%", "FastingGlucose": "mg/dL"}

class ObservationInput(Strict):
    observed_at: datetime
    values: Measurements
    units: dict[str, str]

    @model_validator(mode="after")
    def validate_record(self):
        if self.observed_at.tzinfo is None:
            raise ValueError("Observation timestamp must include a timezone")
        if self.observed_at > now() + timedelta(minutes=5):
            raise ValueError("Observation cannot be in the future")
        expected = {key: UNITS[key] for key in self.values.model_dump(exclude_none=True)}
        if self.units != expected:
            raise ValueError("Each recorded measurement requires its specified unit")
        return self

@app.post("/api/pregnancies/{pid}/observations", status_code=201)
def record(pid: int, data: ObservationInput, db: DB, user: AUTH):
    p = owned(db, user, pid)
    if data.observed_at.date() < p.lmp:
        raise HTTPException(422, "Observation predates this pregnancy")
    observation = Observation(pregnancy_id=pid, observed_at=data.observed_at.astimezone(timezone.utc),
                              values=data.values.model_dump(exclude_none=True), units=data.units)
    db.add(observation)
    db.flush()
    audit(db, user, "observation.create", observation.id)
    db.commit()
    return {"id": observation.id}

@app.post("/api/observations/{oid}/predict")
def predict(oid: int, db: DB, user: AUTH):
    observation = db.get(Observation, oid)
    if not observation:
        raise HTTPException(404, "Observation not found")
    pregnancy = owned(db, user, observation.pregnancy_id)
    existing = db.scalar(select(Prediction).where(Prediction.observation_id == oid))
    if existing:
        return notification_messages.display_result(existing.result)
    preference = db.get(PregnancyPreferences, observation.pregnancy_id)
    if hosted_model.configured() and (not preference or not preference.remote_assessment_enabled):
        raise HTTPException(409, "Enable external research assessments in your pregnancy preferences before sending measurements to the hosted model.")
    try:
        result = inference.predict(observation.values)
    except hosted_model.ModelUnavailable as error:
        raise HTTPException(503, str(error))
    except Exception:
        raise HTTPException(503, "Assessment unavailable. " + (inference.UNIT_ISSUE if hosted_model.provider() == "disabled" else "Your measurements remain saved."))
    month = guidance_service.selected_month(db, pregnancy)
    entries = guidance_service.content(db, month, result["category"])
    result = {**result, "care_summary": notification_messages.care_summary(
        result, observation.values, month, entries, observation.observed_at)}
    meta = inference.metadata()
    prediction = Prediction(pregnancy_id=observation.pregnancy_id, observation_id=oid,
                            model_version=meta["version"], result={**result, "model_version": meta["version"]})
    db.add(prediction)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        return db.scalar(select(Prediction).where(Prediction.observation_id == oid)).result
    needs_review = result["category"] in {"mid", "high"} or result.get("review_required", False)
    message = notification_messages.care_update(result)
    if needs_review:
        db.add(Notification(user_id=user.id, pregnancy_id=observation.pregnancy_id, prediction_id=prediction.id,
                            message=message))
    audit(db, user, "prediction.create", prediction.id)
    db.commit()
    if needs_review and preference and preference.email_enabled and mail.verified(db, user.id):
        subject, body = notification_messages.care_email(result, user.name)
        job = mail.queue(db, user, observation.pregnancy_id, "risk_alert", subject, body,
            f"prediction:{prediction.id}")
        db.commit()
        mail.dispatch(db, job)
    return notification_messages.display_result(prediction.result)

@app.get("/api/pregnancies/{pid}/dashboard")
def dashboard(pid: int, db: DB, user: AUTH):
    p = owned(db, user, pid)
    observations = list(db.scalars(select(Observation).where(Observation.pregnancy_id == pid).order_by(Observation.observed_at, Observation.id)))
    predictions = {x.observation_id: x for x in db.scalars(select(Prediction).where(Prediction.pregnancy_id == pid))}
    prediction_results = {x.id: x.result for x in predictions.values()}
    latest = predictions.get(observations[-1].id) if observations else None
    category = latest.result["category"] if latest else "all"
    month = guidance_service.selected_month(db, p)
    guidance = guidance_service.content(db, month, category)
    preference = db.get(PregnancyPreferences, pid)
    return {"pregnancy": pregnancy_json(p), "observations": [
        {"id": o.id, "observed_at": o.observed_at.replace(tzinfo=timezone.utc), "values": o.values,
         "prediction": notification_messages.display_result(predictions[o.id].result) if o.id in predictions else None} for o in observations],
        "guidance": guidance,
        "preferences": {"month": month, "email_enabled": bool(preference and preference.email_enabled),
                        "email_verified": mail.verified(db, user.id), "email_configured": mail.configured(),
                        "email_address": user.email, "remote_assessment_enabled": bool(preference and preference.remote_assessment_enabled),
                        "remote_model": hosted_model.metadata() if hosted_model.configured() else None,
                        "assessment_model": inference.metadata()},
        "emails": [mail.summary(job) for job in db.scalars(select(EmailJob).where(EmailJob.user_id == user.id, EmailJob.pregnancy_id == pid).order_by(EmailJob.id.desc()).limit(20))],
        "notifications": [{"id": n.id, "message": notification_messages.display_text((prediction_results[n.prediction_id].get("care_summary") or notification_messages.care_update(prediction_results[n.prediction_id])) if n.prediction_id in prediction_results else n.message), "read": n.read, "created_at": n.created_at}
                          for n in db.scalars(select(Notification).where(Notification.user_id == user.id, Notification.pregnancy_id == pid).order_by(Notification.created_at.desc()))]}

@app.patch("/api/notifications/{nid}/read")
def read_notification(nid: int, db: DB, user: AUTH):
    n = db.get(Notification, nid)
    if not n or n.user_id != user.id:
        raise HTTPException(404, "Notification not found")
    n.read = True
    audit(db, user, "notification.read", nid)
    db.commit()
    return {"ok": True}

@app.post("/api/pregnancies/{pid}/guidance/{gid}/delivered")
def guidance_delivery(pid: int, gid: int, db: DB, user: AUTH):
    p = owned(db, user, pid)
    g = db.get(Guidance, gid)
    available = {entry["id"] for entry in guidance_service.content(db, guidance_service.selected_month(db, p), g.category if g else "all")}
    if not g or gid not in available:
        raise HTTPException(404, "Reviewed guidance not found for this stage")
    delivery = db.scalar(select(GuidanceDelivery).where(GuidanceDelivery.pregnancy_id == pid, GuidanceDelivery.guidance_id == gid))
    if not delivery:
        db.add(GuidanceDelivery(pregnancy_id=pid, guidance_id=gid))
        audit(db, user, "guidance.delivered", gid)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
    return {"ok": True}

@app.get("/api/model")
def model(user: AUTH):
    return inference.metadata()

class GuidanceInput(Strict):
    title: str = Field(min_length=1, max_length=150)
    body: str = Field(min_length=1, max_length=4000)
    stage: int = Field(ge=1, le=3)
    category: Literal["all", "low", "mid", "high"]
    source_url: str = Field(max_length=500, pattern=r"^https://")
    month: int | None = Field(default=None, ge=1, le=9)

@app.post("/api/admin/guidance", status_code=201)
def add_guidance(data: GuidanceInput, db: DB, user: ADMIN):
    values = data.model_dump(exclude={"month"})
    if data.month:
        values["stage"] = (data.month - 1) // 3 + 1
    g = Guidance(**values)
    db.add(g)
    db.flush()
    if data.month:
        db.add(GuidanceMonth(guidance_id=g.id, month=data.month))
    audit(db, user, "guidance.draft", g.id)
    db.commit()
    return {"id": g.id}

@app.post("/api/admin/guidance/{gid}/review")
def review_guidance(gid: int, db: DB, user: ADMIN):
    g = db.get(Guidance, gid)
    if not g:
        raise HTTPException(404, "Guidance not found")
    g.reviewed, g.reviewer_id, g.reviewed_at = True, user.id, now()
    audit(db, user, "guidance.publish", gid)
    db.commit()
    return {"ok": True}

@app.get("/api/admin")
def administration(db: DB, user: ADMIN):
    return {"guidance": [{"id": g.id, "title": g.title, "stage": g.stage, "category": g.category,
                          "month": db.get(GuidanceMonth, g.id).month if db.get(GuidanceMonth, g.id) else None,
                          "reviewed": g.reviewed, "body": g.body, "source_url": g.source_url} for g in db.scalars(select(Guidance))],
            "models": [m.metadata_json for m in db.scalars(select(ModelRegistry))],
            "audit": [{"action": a.action, "resource": a.resource, "user_id": a.user_id, "created_at": a.created_at}
                      for a in db.scalars(select(AuditEvent).order_by(AuditEvent.id.desc()).limit(100))]}

@app.get("/api/health")
def health():
    return {"status": "ok"}

app.mount("/", StaticFiles(directory=Path(__file__).resolve().parents[1] / "frontend", html=True), name="web")
