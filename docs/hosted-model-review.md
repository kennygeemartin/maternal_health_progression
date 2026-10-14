# Hosted maternal research model review

Reviewed 2026-10-14. Selected service: [Silvio0/maternal-risk-gradio-direct](https://huggingface.co/spaces/Silvio0/maternal-risk-gradio-direct), revision `82ffc870e3bbfb5693b02a8a7804f1f1f7a21dc0`. The Space metadata declares MIT licensing. Its pinned public `function.py` loads an already trained pipeline and performs prediction and probability inference. Bloom calls that service, rather than downloading or executing its joblib/pickle artifacts. Clinical validation, calibration, local population applicability and the model's training evaluation have not been established by this review. No accuracy figure is presented as evidence of clinical effectiveness.

The provider uses the six-feature [UCI Maternal Health Risk dataset schema](https://archive.ics.uci.edu/dataset/863/maternal+health+risk): age, systolic/diastolic pressure, blood glucose, Fahrenheit temperature and heart rate. UCI describes glucose as mmol/L; Bloom converts its recorded mg/dL using division by 18.0182. UCI does not establish fasting status, so use of Bloom's fasting measurement is a further research limitation. This is a single-visit classifier, not pregnancy progression forecasting. BMI and HbA1c are optional local records and are not sent.

| Provider field | Accepted service range | Unit |
| --- | --- | --- |
| Age | 10-70 (Bloom entry limit 60) | years |
| SystolicBP | 70-160 | mmHg |
| DiastolicBP | 49-100 | mmHg |
| BS | 6-19 | mmol/L |
| BodyTemp | 98-103 | Fahrenheit |
| HeartRate | 60-90 | bpm |

These are service input bounds, not safe clinical ranges or referral thresholds. The glucose minimum excludes many normal fasting results. Values are never clipped, filled, or fabricated. Unsupported visits are retained without an estimate and with a clear explanation. Symptoms and clinically concerning readings need care independent of model availability or classification.

## API and traceability

POST `/gradio_api/call/process_maternal_health` with `data` containing all six values in the table order; GET the SSE result by returned event identifier. Bloom checks both repository and deployed revisions before submitting measurements. Any revision drift blocks assessment pending a reviewed integration change. A successful response must have exactly three finite probability scores, sum within 0.001 of one, and a matching category. The service rounds scores to four decimal places. Its HTML explanation is ignored and never rendered. Results retain the provider revision, source URL and local model registry version.

Users explicitly enable external assessment for each pregnancy. Only the six numbers are transmitted; names, addresses and pregnancy identifiers are excluded. The external provider may process or log inputs. Consent and provider identity are displayed in settings. An optional private `HF_TOKEN` can authenticate calls; do not put it in frontend code. `RISK_MODEL_PROVIDER=disabled` blocks external inference. A custom HTTPS REST service can be configured using the variables documented in `.env.example`; its version and feature schema must match exactly.

## Verification and availability

A real public API call with entirely fabricated `[25,120,80,7.5,98.6,75]` measurements returned a mid research category and scores 0.2657 low, 0.683 mid, 0.0513 high. A fabricated glucose of 4.88 mmol/L was explicitly rejected by the provider. Repeated synthetic testing then hit the provider's anonymous ZeroGPU quota. The completed adapter did not achieve a further successful live smoke test because of that limit and intermittent network latency. Automated tests mock transport to check the exact request, conversion, version rejection, malformed scores, consent and alert flow. This is an optional public demo integration with no uptime guarantee; authenticated quota or a dedicated hosted endpoint is needed for dependable use. Failed calls return 503 and do not create a prediction or risk email.

Other candidates investigated: [maitry30/maataraksha-maternal-risk](https://huggingface.co/maitry30/maataraksha-maternal-risk) expects additional synthetic features not collected by Bloom, so it was rejected. Other public Spaces did not provide a verified matching live contract. No required model features are silently invented.
