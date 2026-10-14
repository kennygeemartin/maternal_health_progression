# Guidance and notification wording

Updated 2026-10-14 under the project owner's confirmation that the reviewer approved notification guidance.

Month guidance emails greet the recipient by name, introduce the selected month's guidance, include published content and source links, and end with:

> Continue your antenatal visits and discuss your progress, measurements and questions with your midwife or doctor. Contact your maternity care team promptly whenever you need advice.

The old general disclaimer footer and exact platform boilerplate about approximate month labels / low model estimates are omitted from email presentation. Stored approved content remains intact. Specific clinical instructions, including urgent movement-related instructions, are preserved.

Care updates thank the user for recording measurements and provide a clear next step: arrange a professional visit or contact the maternity team promptly when the recorded assessment needs attention. Emails avoid duplicated diagnostic disclaimers and end with the professional-review recommendation. Detailed model limitations remain with assessment/model information, rather than being repeated in guidance delivery messages.

The notification screen presents pregnancy guidance and care updates, actual email subjects, clear statuses such as Submitted for delivery, and a direct link to month guidance. It does not claim confirmed inbox delivery. Service error codes appear only to administrators; mothers see a readable explanation and retry action. Verification, opt-in, ownership checks and failed-delivery tracking remain functional.

Existing in-app care notifications use the new presentation based on their saved assessment without rewriting stored audit records. Unattempted queued monthly messages can refresh their wording without creating a duplicate. Already-attempted messages retain their original content for provider idempotency; accepted messages are not resent merely because the wording changed.

Validation: 15 local automated tests passed, with the disposable PostgreSQL test left to CI. Tests cover greeting and closing, preservation of urgent guidance, duplicate prevention and attempted-message identity. Frontend syntax and rendering checks passed for readable statuses, guidance navigation and hidden service error codes for mothers. Tests use synthetic records and mocked delivery; no new real emails were sent during this change.
