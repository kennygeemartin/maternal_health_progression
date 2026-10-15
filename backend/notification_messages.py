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
    if result.get("category") == "high":
        return ("Your latest assessment suggests you should contact your midwife or doctor promptly. "
                "Share your readings and how you are feeling so your care team can advise on your next steps.")
    if result.get("review_required") or result.get("outside_training_range"):
        return ("Your measurements are saved. Some readings fall outside the model's reference data, "
                "so its score cannot reliably explain them. This alone does not mean those readings are unhealthy. "
                "Share your record with your midwife or doctor for advice tailored to you.")
    return ("Thank you for checking in on your health. Your latest readings need attention from your care team. "
                "Please contact your midwife or doctor promptly to arrange a professional review and discuss your next steps.")
    return ("Thank you for keeping up with your pregnancy check-ins. Your latest readings would benefit from a care-team review. "
            "Please arrange a visit with your midwife or doctor to discuss your measurements and plan your next steps together.")

def care_summary(result, values, month, entries, observed_at):
    """Assemble approved education and actual readings; no generated clinical claims."""
    temperature = values.get("BodyTempC")
    if temperature is None and values.get("BodyTempF") is not None:
        temperature = (values["BodyTempF"] - 32) * 5 / 9
    readings = []
    if "SystolicBP" in values and "DiastolicBP" in values:
        readings.append(f"Blood pressure: {values['SystolicBP']:g}/{values['DiastolicBP']:g} mmHg")
    for key, label, unit in [("FastingGlucose", "Fasting glucose", "mg/dL"),
                              ("HeartRate", "Heart rate", "beats/min"),
                              ("HbA1c", "HbA1c", "%"), ("BMI", "BMI", "kg/m²")]:
        if values.get(key) is not None:
            readings.append(f"{label}: {values[key]:g} {unit}")
    if temperature is not None:
        readings.append(f"Temperature: {temperature:.1f} °C")
    sections = [f"Your check-in for pregnancy month {month}",
                f"Recorded visit: {observed_at.isoformat()}",
                "Your recorded measurements\n" + "\n".join(readings), care_update(result),
                "Support for this stage of pregnancy"]
    for entry in entries:
        sections.append(f"{entry['title']}\n{guidance_body(entry['body'])}\nSource: {entry['source_url']}")
    if not entries:
        sections.append("Bring your questions about symptoms, daily activities and upcoming appointments to your care team.")
    sections.extend(["For your next conversation\nShare when these readings were taken, any symptoms or changes you have noticed, "
                     "and medicines or supplements you take. Ask what follow-up measurements or appointments are appropriate for you.",
                     VISIT_RECOMMENDATION])
    return "\n\n".join(sections)

def care_email(result, name):
    return ("Bloom: a check-in with your care team",
            f"Hello {name},\n\nYour pregnancy care update\n\n"
            "You can open Bloom to see your measurements and manage your email preferences.\n\n" +
            result.get("care_summary", care_update(result)))
