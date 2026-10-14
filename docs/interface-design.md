# Shared header and interface design

Updated 2026-10-14 following the project owner's request to use a picture banner on login, registration and every application page.

The shared `site-header` is outside the authentication and application-view containers, so navigation and sign-out do not remove it. A white brand strip sits above a full-width photographic masthead. The app sidebar begins below that header. Small screens display the photo above a solid blue caption panel; desktop uses a dark blue transition behind the text. The former overview-only banner is removed from active page markup.

Design references: [UNICEF](https://www.unicef.org/) and [WHO](https://www.who.int/), reviewed for editorial imagery, brand identity and content hierarchy. Bloom uses its own generated image and branding, not the institutions' photographs or logos.

## Palette and typography

| Use | Colour |
| --- | --- |
| Healthcare blue / primary actions | `#174c70` |
| Main text | `#152e40` |
| Secondary and help text | `#465b6b` |
| Warm rose accents | `#9f4960` |
| Rose surface | `#fbeef2` |
| Pale blue surface | `#eaf3fa` |
| Page background | `#f5f8fb` |

Manrope provides clear rounded headings; Source Sans 3 provides readable body text. Both are hosted locally as variable WOFF2 fonts, with Latin and extended-Latin coverage and fallback system fonts. Font licenses are retained in `frontend/assets/fonts/`. Main body text is 16px; helpers are 14px, with comfortable line spacing and visible focus outlines. The PWA icon, browser theme, charts, forms, navigation, cards, risk notices and dialogs follow the new palette. Font and image assets join the static application-shell cache; health data is not cached.

## Verification

Actual local FastAPI browser checks used only fabricated accounts and a disposable database. Login, registration, Overview, Measurements, Guidance, Notifications, Pregnancy Profile and Administration each retain one visible full-width header. Desktop, 390px phones, 320px phones and 768px tablets were checked for horizontal overflow. The real registration flow, pregnancy setup and measurement dialog rendered without uncaught frontend exceptions. Source Sans 3 and Manrope loaded from the application, and JavaScript syntax checks passed.

Selected solid foreground/background pairs were checked against the [W3C contrast-minimum guidance](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html). This verifies the listed palette pairs, not a comprehensive accessibility certification. Header text stays on the dark blue section/overlay, or on a solid blue mobile panel.

| Checked pair | Contrast ratio |
| --- | --- |
| body on white | 14.03:1 |
| secondary on white | 7.07:1 |
| secondary on page | 6.64:1 |
| white on primary | 9.11:1 |
| rose on white | 5.84:1 |
| link on blue surface | 8.12:1 |
| text on rose surface | 6.27:1 |
| warning | 6.69:1 |
| alert | 6.31:1 |
| header accent | 6.93:1 |
| input outline | 3.26:1 |

## Current picture asset and final prompt

Asset: `frontend/assets/maternal-header-v2.jpg`, 2172 x 724px, about 147KB. Generated with the built-in image-generation tool; both portrayed adults are fictional. The original PNG remains in the generator output directory. This is a separate new image; the first banner is retained for provenance.

Final generation prompt:

Use case: photorealistic-natural. Create a new ultra-wide editorial photograph for the shared masthead banner of Bloom, a maternal health support application. Panoramic approximately 5:1 composition. A fictional adult Black Nigerian expectant mother wearing a muted dusty-rose maternity dress and an adult Black female healthcare professional in soft healthcare-blue scrubs have a relaxed, supportive conversation in a modern, welcoming antenatal clinic. Warm natural expressions and dignified body language, the pregnant mother's hand resting on her clothed bump, realistic faces and hands. Keep the two women together in the right third of the frame and fit their faces and pregnant abdomen in the middle horizontal band so a shallow wide header crop preserves the maternal-care scene. The left half is an airy, softly blurred light neutral clinic interior with pale blue details and very subtle warm rose accents, suitable for a dark-blue text overlay added later in HTML. Soft daylight, natural editorial photography, warm skin tones, professional healthcare setting without a cold hospital feeling, balanced colours rather than a green tint. No embedded text, no logos, no watermarks, no instruments or procedures, no UI mockup. One cohesive photograph, not a collage.
