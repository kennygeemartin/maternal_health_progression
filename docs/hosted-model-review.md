# Pretrained maternal research model review

## Default: bundled, token-free model

Selected on 2026-10-14: [viochris/Maternal-Health-Risk-Model-Research](https://github.com/viochris/Maternal-Health-Risk-Model-Research), source revision `f260b91bf8144b64a666996fc1acca6b4b1613ac`, MIT license. Copyright notice is retained in `backend/models/LICENSE.maternal-model.txt`. The data attribution is Marzia Ahmed, [UCI Maternal Health Risk dataset](https://doi.org/10.24432/C5DP5D), CC BY 4.0, Bangladesh. The repository documentation contains inconsistent algorithm labels; inspecting its pinned artifact establishes that the actual saved classifier is **CatBoost**, with 500 numerical symmetric trees, class indices 0/1/2 mapped to low/mid/high by the training notebook. Bloom uses this pretrained classifier and its fitted StandardScaler; it does not train another model or invent clinical rules to impersonate one.

Source artifact `Maternal-Health-Risk-Model/best_hp_model.joblib` SHA-256: `8dae3ed278947571f4edf8df8c34df00fd582000b2c1ee9bf264f3f410dbff5b`.

Deployed numeric export SHA-256: `3aa8650ae2405c3b32e82a4afcf0ce7379f5e80d751944701fa239a0e4215837`. The runtime verifies this digest, feature schema and class mapping. Only numerical tree splits/leaves, fitted scaling and provenance are bundled. Source fitted sampling objects, embedded neighbour data, executable pickle and native CatBoost packages are excluded. The export is 446,971 bytes. `scripts/export_maternal_model.py` documents and reproduces the guarded export; unknown globals or a changed source digest fail closed.

Bloom runs inference with standard Python. It makes no model-service request, requires no token or model-service fee and is unaffected by public model API quotas. Hosting, email and database limits remain separate. [Vercel Hobby](https://vercel.com/docs/plans/hobby) is a limited free hosting plan for eligible personal/noncommercial use, not an unlimited free compute guarantee.

The numerical export matched native CatBoost 1.2.8 within 1e-13 on 1,219 synthetic vectors: ordinary examples, random plausible/extreme values and exact/adjacent float32 split boundaries. `tests/fixtures/bundled_model_parity.json` contains only fabricated vectors and native reference scores; tests do not need CatBoost. This establishes inference parity, not clinical effectiveness. The source's held-out evaluation reports modest performance and especially poor mid-risk recall; clinical validation, calibration and local population applicability are not established. Scores are displayed as research scores, not calibrated clinical probabilities.

## Inputs and derivations

Six measured inputs suffice. Celsius temperature is converted using F = C * 9/5 + 32. Glucose recorded in mg/dL is converted to mmol/L by division by 18.0182. No names, addresses or identifiers enter the classifier. The source glucose's fasting status is unspecified, limiting application to Bloom's fasting glucose. BMI and HbA1c are optional local observations and are unused by this model. Missing haemoglobin, parity, symptoms, laboratory results or medical history cannot be safely deduced from these six measurements; they are neither requested by this classifier nor fabricated.

The reference envelope is the cleaned source dataset's observed bounds, not exact per-fold training coverage or healthy ranges: Age 10-70, systolic pressure 70-160 mmHg, diastolic pressure 49-100 mmHg, glucose 6-19 mmol/L, temperature 98-103 F, heart rate 60-90 bpm. Valid app readings outside that envelope are preserved and numerically evaluated without clipping, but flagged as review_required. The primary UI shows Review needed even if the classifier's research category was low. The original category and scores remain traceable; an in-app review notice and opted-in verified email can request care-team review. Outside-envelope status does not itself diagnose illness. Symptoms need care irrespective of research scores.

## Earlier external service investigation (optional fallback)

The previous Hugging Face service is retained as an explicit optional mode, with its separate privacy consent and provider bounds. It is no longer the default. The following records describe that earlier investigation.

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
