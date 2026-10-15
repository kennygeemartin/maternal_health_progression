"""Versioned measurement action rules, independent of research model classification.
Sources and implementation choices are documented in docs/care-assessment.md.
"""
VERSION = "maternal-actions-2026-10-15-v1"
BP = "https://www.nhs.uk/pregnancy/existing-health-conditions/high-blood-pressure/"
HOME_BP = "https://www.whittington.nhs.uk/mini-apps/leaflet/Default.asp?id=482&print=1"
GLUCOSE = "https://www.nice.org.uk/guidance/ng3/chapter/Recommendations"
HYPO = "https://www.nhs.uk/conditions/low-blood-sugar-hypoglycaemia/"
WARNING = "https://www.cdc.gov/hearher/maternal-warning-signs/index.html"
PULSE = "https://www.cpdconnect.nhs.scot/media/2438/sepsis-appendices-20.pdf"
SYMPTOMS = {
    "chest_breathing": "Chest pain or difficulty breathing",
    "headache_vision": "Severe or persistent headache, or changes in vision",
    "bleeding_fluid": "Bleeding more than spotting, or leaking fluid",
    "severe_pain": "Severe or persistent abdominal pain",
    "faint_confused": "Fainting, confusion or a seizure",
    "cannot_drink": "Vomiting and unable to keep fluids down",
    "reduced_movement": "Baby moving less, stopping, or changing from the usual pattern",
    "severe_swelling": "Sudden severe swelling of the face or hands",
}

def assess(values, month, weeks=None):
    findings = []
    def add(level, title, action, source):
        findings.append(dict(level=level, title=title, action=action, source_url=source))
    symptoms = values.get("_symptoms", [])
    for symptom in symptoms:
        if symptom in SYMPTOMS:
            add("urgent", SYMPTOMS[symptom], "Get medical help now. Call your maternity unit immediately; for chest pain, severe breathing difficulty, collapse, seizure or heavy bleeding, call your local emergency service. Do not wait for another reading or an email.", WARNING)
    systolic, diastolic = values.get("SystolicBP"), values.get("DiastolicBP")
    if systolic is not None and diastolic is not None:
        reading = f"Blood pressure {systolic:g}/{diastolic:g} mmHg"
        if systolic >= 160 or diastolic >= 110:
            add("urgent", reading + " is severely raised", "Contact maternity triage now for immediate assessment. Do not wait for a routine appointment or delay seeking help to take more readings.", BP)
        elif systolic >= 150 or diastolic >= 100:
            add("today", reading + " is high", "Rest seated for 5 minutes and recheck. If still raised, contact your maternity unit today, within 4 hours. Seek help now if you feel unwell.", HOME_BP)
        elif systolic >= 140 or diastolic >= 90:
            add("today", reading + " is raised", "Rest seated for 5 minutes and recheck. If still raised, contact your maternity unit within 24 hours. Seek help now for severe headache, vision changes or severe abdominal pain.", HOME_BP)
        elif systolic < 90 or diastolic < 60:
            add("today", reading + " is low", "Sit or lie down if dizzy and rise slowly. Recheck the reading and contact your maternity team today if it persists, you feel unwell or take blood-pressure medicine. Fainting or confusion needs immediate help.", "https://www.nhs.uk/conditions/low-blood-pressure-hypotension/")
        elif systolic >= 135 or diastolic >= 85:
            add("monitor", reading + " is approaching the raised threshold", "Rest for 5 minutes and recheck. If similar, monitor daily. A repeat of 140 systolic or 90 diastolic or higher needs maternity advice within 24 hours.", HOME_BP)
        else:
            add("routine", reading + " is below the raised threshold", "If you feel well, continue your usual monitoring and antenatal plan.", BP)
    temp = values.get("BodyTempC")
    if temp is None and values.get("BodyTempF") is not None:
        temp = round((values["BodyTempF"] - 32) * 5 / 9, 6)
    if temp is not None:
        if temp >= 38:
            add("urgent", f"Temperature {temp:.1f} °C indicates fever", "Seek medical care now during pregnancy, especially if you feel unwell. Do not wait for your next appointment.", WARNING)
        elif temp < 35:
            add("urgent", f"Temperature {temp:.1f} °C is very low", "Seek emergency medical help now. Keep warm while arranging help.", "https://www.nhs.uk/conditions/hypothermia/")
        elif temp >= 37.5 or temp < 36:
            add("monitor", f"Temperature {temp:.1f} °C needs another check", "Recheck with a reliable thermometer. Contact maternity care today if it persists or you feel unwell; 38 °C or higher needs help now.", PULSE)
        else:
            add("routine", f"Temperature {temp:.1f} °C does not indicate fever", "Continue monitoring if you feel well.", WARNING)
    glucose = values.get("FastingGlucose")
    if glucose is not None:
        mmol = glucose / 18.0182
        if mmol < 4:
            add("urgent", f"Fasting glucose {glucose:g} mg/dL is low", "Act now. If fully awake and able to swallow safely, have a small glass of fruit juice or glucose tablets and recheck in 10-15 minutes. Repeat if still below 4 mmol/L (about 72 mg/dL). Seek urgent advice; if confused, unconscious or unable to swallow, give nothing by mouth and call emergency services.", HYPO)
        elif mmol >= 5.3:
            add("today", f"Fasting glucose {glucose:g} mg/dL is above a common pregnancy diabetes target", "Contact your maternity or diabetes team today to agree follow-up. The usual fasting target for diabetes in pregnancy is below 5.3 mmol/L (about 95 mg/dL); a home reading alone does not diagnose diabetes. Follow your own prescribed target and do not change medicines yourself. Vomiting, abdominal pain, rapid breathing, drowsiness or confusion with high glucose needs emergency help now.", GLUCOSE)
        else:
            add("routine", f"Fasting glucose {glucose:g} mg/dL does not trigger a glucose alert", "This is above the low-glucose threshold and below the common pregnancy diabetes fasting target. Continue your agreed monitoring and regular meals.", GLUCOSE)
    pulse = values.get("HeartRate")
    if pulse is not None:
        if pulse > 120 or pulse < 40:
            add("urgent", f"Heart rate {pulse:g} beats/min needs urgent assessment", "Contact maternity triage now. Chest pain, breathlessness, fainting or confusion needs emergency help.", PULSE)
        elif pulse >= 100 or pulse <= 50:
            add("monitor", f"Heart rate {pulse:g} beats/min needs a resting recheck", "Rest quietly and recheck. Contact maternity care today if it remains unusual for you. Seek urgent help for chest pain, breathlessness or fainting.", PULSE)
        else:
            add("routine", f"Heart rate {pulse:g} beats/min does not trigger a pulse alert", "Continue your usual monitoring if you feel well. A racing or irregular heartbeat with chest pain, breathlessness or fainting needs urgent help.", PULSE)
    rank = {"routine": 0, "monitor": 1, "today": 2, "urgent": 3}
    findings.sort(key=lambda f: rank[f["level"]], reverse=True)
    level = findings[0]["level"] if findings else "monitor"
    labels = {"routine": "No urgent threshold detected", "monitor": "Recheck and monitor", "today": "Contact maternity care today", "urgent": "Get medical help now"}
    stage = ("After 20 weeks, raised blood pressure needs particular attention because pre-eclampsia can develop. "
             if weeks is not None and weeks >= 20 and systolic is not None and diastolic is not None and (systolic >= 140 or diastolic >= 90) else "")
    stage += ("Once you know your baby's usual movement pattern, a reduction or change needs immediate maternity advice."
              if month >= 4 else "Mild nausea and tiredness can occur early on; severe pain, bleeding or inability to keep fluids down needs prompt help.")
    return dict(version=VERSION, level=level, label=labels[level], findings=findings, stage_advice=stage,
                symptoms_reported=bool(symptoms), safety_note="These checks cover the readings entered. New or worsening symptoms need care even when the numbers look reassuring.")


def text(assessment):
    blocks = [assessment["label"]]
    for finding in assessment["findings"]:
        blocks.append(f"{finding['title']}\n{finding['action']}\nSource: {finding['source_url']}")
    blocks.extend([assessment["stage_advice"], assessment["safety_note"]])
    return "\n\n".join(blocks)
