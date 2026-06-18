# Activity Image Enrichment Fixes

## Scope

Fix the four validated issues in the current activity image-enrichment change without broadening authorization or refactoring unrelated activity flows.

## Authorization

- OCR preview is a system-level, resource-consuming operation and must require an active `profiles.role = admin` user.
- Runtime configuration create, update, and delete operations must require the same admin authorization because they change global behavior, including `ocr.enabled`.
- Configuration reads and ordinary activity reads remain authenticated-user operations.
- Frontend visibility is only a usability control; the backend admin dependency remains authoritative.

## Confirmation Write Binding

- Store and render the activity snapshot returned by the preview response.
- Confirmation always targets `preview.activity_id`, never the mutable drawer selection.
- If the current selection no longer matches the preview activity, dismiss or reject the stale response rather than opening a confirmation dialog.
- After a successful write, update drawer state only when it still displays the written activity, then invalidate activity and enrichment-context queries.

## OCR Cache Consistency

- Preserve completed OCR only when the existing and incoming image identity is unchanged.
- For the current schema, identity includes bucket, object path, public URL, and origin URL.
- When a same-path row changes source identity, reset OCR status to `pending` and clear text, confidence, provider, error, and completion time in the upsert.
- Existing unchanged mappings continue to retain OCR results.

## Error Mapping

- Keep successful OCR responses with no text as the existing domain conflict outcome.
- Track per-image operational failures separately from successful empty recognition.
- If every usable image fails operationally, raise a dedicated upstream OCR error and map it to HTTP 502.
- Partial failures remain warnings when at least one image succeeds.
- Missing provider configuration remains HTTP 503.

## Tests

- API tests: ordinary users receive 403 for OCR preview; admins can preview; config mutations require admin.
- Service tests: all OCR calls failing raises the upstream error; all successful empty responses retain the no-text domain outcome; partial failure still succeeds with warnings.
- Repository tests: same image identity preserves OCR; changed source identity resets OCR fields.
- Frontend logic is isolated into a small identity helper and verified through TypeScript/build checks; confirmation code must use preview identity directly.
- Final verification runs focused tests, full backend tests, frontend production build, Python compilation, and `validate.sh` with the project virtual environment on `PATH`.
