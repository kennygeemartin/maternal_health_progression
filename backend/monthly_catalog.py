"""Educational monthly summaries; publication authorized by the project owner, 2026-10-14.

Month groupings are approximate. Personal dating and care plans remain with the care team.
These summaries do not claim independent clinical review of the Bloom application.
"""
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from .database import Guidance, GuidanceMonth, GuidanceSeed, now

CATALOG = [
    (1, "Early pregnancy: arrange your first care visit",
     "You may have a missed period, tender breasts or tiredness, or very few symptoms. Arrange antenatal care and discuss your health history and medicines. Ask your care team about pregnancy supplements. Avoid alcohol and seek support to stop smoking. Do not stop prescribed medicines without speaking to your clinician.",
     "https://www.nhs.uk/best-start-in-life/pregnancy/week-by-week-guide-to-pregnancy/1st-trimester/week-4/"),
    (2, "Nausea, rest and support",
     "Nausea, fatigue, breast changes and mood changes can occur. Allow time for rest, try smaller balanced meals if easier to tolerate, and keep drinking fluids. Attend your first antenatal appointments. Discuss persistent sickness, worries or low mood with your care team, especially if sickness makes eating or drinking difficult.",
     "https://www.nhs.uk/best-start-in-life/pregnancy/week-by-week-guide-to-pregnancy/1st-trimester/week-8/"),
    (3, "First-trimester checks and everyday wellbeing",
     "Your body and symptoms may be changing; every pregnancy is different. Discuss pregnancy dating and available screening with your care team. Keep a varied diet, stay hydrated, and follow advice on suitable physical activity. Bring questions about symptoms, medicines or emotional wellbeing to your appointment.",
     "https://www.nhs.uk/best-start-in-life/pregnancy/week-by-week-guide-to-pregnancy/1st-trimester/week-12/"),
    (4, "Keeping comfortable as pregnancy progresses",
     "You may notice a growing bump and changes in appetite or energy. Continue antenatal follow-up and balanced meals. Gentle activity may help wellbeing when suitable for your pregnancy; follow any restrictions from your care team. Ask for advice about persistent discomfort rather than assuming every new symptom is expected.",
     "https://www.nhs.uk/best-start-in-life/pregnancy/week-by-week-guide-to-pregnancy/2nd-trimester/week-16/"),
    (5, "Mid-pregnancy checks and changing sensations",
     "Your care team may discuss a scan to check your baby's development. Sleep changes, indigestion or leg cramps may occur. Attend scheduled checks and discuss any recommended vaccinations with your clinician. If you are unsure about changes in your body, seek advice rather than relying on an app assessment.",
     "https://www.nhs.uk/best-start-in-life/pregnancy/week-by-week-guide-to-pregnancy/2nd-trimester/week-20/"),
    (6, "Comfort, follow-up and preparation",
     "Your bump is growing and you may notice back discomfort or digestive symptoms. Keep attending checks and discuss tests recommended for your own circumstances. Choose comfortable activities and rest when needed. Begin talking with your care team about birth preparation and the support you would like.",
     "https://www.nhs.uk/best-start-in-life/pregnancy/week-by-week-guide-to-pregnancy/2nd-trimester/week-24/"),
    (7, "Third-trimester care and your birth plan",
     "Later pregnancy can bring tiredness, sleep difficulties and greater physical discomfort. Keep your antenatal appointments and discuss a birth plan, feeding preferences and any recommended vaccinations. Ask your care team how to get help promptly if you have concerns. A low model estimate does not rule out a problem.",
     "https://www.nhs.uk/best-start-in-life/pregnancy/week-by-week-guide-to-pregnancy/3rd-trimester/week-28/"),
    (8, "Prepare your support and transport",
     "Your growing bump may make movement less comfortable. Discuss where you plan to give birth, transport arrangements and support at home. Your baby's movements should continue; do not assume they should reduce because there is less space. Contact your maternity team promptly if the usual movement pattern changes.",
     "https://www.nhs.uk/best-start-in-life/pregnancy/week-by-week-guide-to-pregnancy/3rd-trimester/week-32/"),
    (9, "Getting ready for birth and early recovery",
     "Prepare the things you need for birth and confirm how to contact your maternity team. Discuss labour signs, when to seek assessment, feeding and support after delivery. Keep attending follow-up appointments. Your care team can explain the plan if pregnancy continues beyond your expected due date.",
     "https://www.nhs.uk/best-start-in-life/pregnancy/week-by-week-guide-to-pregnancy/3rd-trimester/week-36/"),
]

MOVEMENT_GUIDANCE = ("When you have begun noticing your baby's movements, contact your maternity team immediately if they slow, stop or change from the usual pattern. Do not wait for an email or an app prediction.")
MOVEMENT_SOURCE = "https://www.nhs.uk/pregnancy/keeping-well/your-babys-movements/"

def seed(db):
    for month, title, body, source in CATALOG:
        key = f"nhs-month-{month}-owner-approved-2026-10-14"
        if db.get(GuidanceSeed, key):
            continue
        try:
            with db.begin_nested():
                guidance = Guidance(title=title, body=body + "\n\nMonth labels are approximate. Follow your care team's personalised advice.",
                    stage=(month - 1)//3 + 1, category="all", source_url=source, reviewed=True, reviewed_at=now())
                db.add(guidance)
                db.flush()
                db.add(GuidanceMonth(guidance_id=guidance.id, month=month))
                db.add(GuidanceSeed(key=key, guidance_id=guidance.id))
                db.flush()
        except IntegrityError:
            # Another cold start seeded the same source version first.
            pass
    key = "nhs-movement-owner-approved-2026-10-14"
    if not db.get(GuidanceSeed, key):
        try:
            with db.begin_nested():
                # Attach the warning to each later trimester through distinct records.
                for stage in [2, 3]:
                    guidance = Guidance(title="Changes in your baby's movements", body=MOVEMENT_GUIDANCE,
                        stage=stage, category="all", source_url=MOVEMENT_SOURCE, reviewed=True, reviewed_at=now())
                    db.add(guidance)
                    db.flush()
                db.add(GuidanceSeed(key=key, guidance_id=guidance.id))
                db.flush()
        except IntegrityError:
            pass
    db.commit()
