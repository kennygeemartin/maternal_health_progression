"""Warm notification copy around published guidance and care-team referrals."""

VISIT_RECOMMENDATION = (
    "Continue your antenatal visits and discuss your progress, measurements and questions "
    "with your midwife or doctor. Contact your maternity care team promptly whenever you need advice."
)

def guidance_body(body):
    # Remove only Bloom's old platform boilerplate, preserving clinical instructions.
    return body.replace("\n\nMonth labels are approximate. Follow your care team's personalised advice.", "").replace(
        " A low model estimate does not rule out a problem.", "")

def care_update(result):
    if result.get("review_required") or result.get("outside_training_range"):
        return ("Thank you for keeping track of your health. Your readings are ready for a closer review. "
                "Please arrange a visit with your midwife or doctor to discuss these measurements and your next steps.")
    if result.get("category") == "high":
        return ("Thank you for checking in on your health. Your latest readings need attention from your care team. "
                "Please contact your midwife or doctor promptly to arrange a professional review and discuss your next steps.")
    return ("Thank you for keeping up with your pregnancy check-ins. Your latest readings would benefit from a care-team review. "
            "Please arrange a visit with your midwife or doctor to discuss your measurements and plan your next steps together.")

def care_email(result, name):
    return ("Bloom: a check-in with your care team",
            f"Hello {name},\n\nYour pregnancy care update\n\n"
            "You can open Bloom to see your measurements and manage your email preferences.\n\n" + care_update(result))
