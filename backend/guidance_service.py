"""Month-specific approved content, with explicitly identified trimester fallback."""
import hashlib
from datetime import date
from sqlalchemy import select, or_
from .database import Guidance, GuidanceMonth, PregnancyPreferences
from .notification_messages import guidance_body, VISIT_RECOMMENDATION

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

def email_content(month, entries, name=None):
    greeting = f"Hello {name}," if name else "Hello,"
    body = (f"{greeting}\n\nYour Bloom guidance for pregnancy month {month}\n\n"
            "One step at a time, you are building a record of your pregnancy journey. "
            "Here is your guidance for this month.\n\n")
    for entry in entries:
        scope = f"Month {month}" if entry["month"] else "Trimester guidance"
        body += f"{entry['title']} ({scope})\n{guidance_body(entry['body'])}\nSource: {entry['source_url']}\n\n"
    body += "You can manage your email preferences in Bloom.\n\n" + VISIT_RECOMMENDATION
    if len(body) > 30000:
        # Avoid truncating reviewed medical instructions part-way through a paragraph.
        body = (f"{greeting}\n\nYour guidance for pregnancy month {month} is ready. "
                "Open Bloom to read all of your guidance and manage your email preferences.\n\n" + VISIT_RECOMMENDATION)
    identity = hashlib.sha256((str(month) + str(entries)).encode()).hexdigest()
    return f"Bloom: support for pregnancy month {month}", body, identity
