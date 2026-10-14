"""Month-specific approved content, with explicitly identified trimester fallback."""
import hashlib
from datetime import date
from sqlalchemy import select, or_
from .database import Guidance, GuidanceMonth, PregnancyPreferences

def selected_month(db, pregnancy):
    preference = db.get(PregnancyPreferences, pregnancy.id)
    return preference.month if preference else min(9, max(1, (date.today() - pregnancy.lmp).days // 30 + 1))

def content(db, month, category="all"):
    stage = (month - 1) // 3 + 1
    rows = db.execute(select(Guidance, GuidanceMonth.month).outerjoin(GuidanceMonth,
        GuidanceMonth.guidance_id == Guidance.id).where(Guidance.reviewed == True,
        Guidance.stage == stage, Guidance.category.in_(["all", category]),
        or_(GuidanceMonth.month.is_(None), GuidanceMonth.month == month)).order_by(Guidance.id)).all()
    return [{"id": g.id, "title": g.title, "body": g.body, "source_url": g.source_url,
             "month": target, "scope": "month" if target else "trimester"} for g, target in rows]

def email_content(month, entries):
    body = f"Your Bloom guidance for pregnancy month {month}\n\n"
    for entry in entries:
        scope = f"Month {month}" if entry["month"] else "Trimester guidance"
        body += f"{entry['title']} ({scope})\n{entry['body']}\nSource: {entry['source_url']}\n\n"
    body += "This information supports your maternity care; it does not replace personalised advice from your care team.\nTo stop guidance emails, turn off email updates in Bloom."
    if len(body) > 30000:
        # Avoid truncating reviewed medical instructions part-way through a paragraph.
        body = f"Reviewed guidance for pregnancy month {month} is available in Bloom.\nSign in to read all of your published guidance.\nTo stop guidance emails, turn off email updates in Bloom."
    identity = hashlib.sha256((str(month) + str(entries)).encode()).hexdigest()
    return f"Bloom: your month {month} guidance", body, identity
