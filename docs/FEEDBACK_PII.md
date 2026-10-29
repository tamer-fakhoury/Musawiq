# Customer Feedback PII and Consent Handling

Feedback is free text and may contain names, phone numbers, addresses, order
details, or other personal data. `feedback_items.text` and uploaded feedback
files are classified as `sensitive_pii` with `access-restricted` handling in
`docs/PII.md`.

## Consent

- Feedback may only be submitted by an authorized store owner or manager.
- The uploader attests that the store has a lawful basis and any required
  customer consent to use the feedback for recommendations.
- The MVP does not store a separate consent flag. Consent evidence must be
  retained by the store outside the platform until a consent-capture workflow
  is added.
- Feedback must not be submitted if consent has been withdrawn.

## Access and rejection messages

- Feedback rows and files are tenant-scoped and are not available to the
  reporting role.
- Validation responses identify only the file and row number. They never echo
  the submitted text or filename content.
- Uploaded feedback files are stored with purpose `feedback_file`; the storage
  key and checksum are internal and are not exposed by the API.

## Retention

- Feedback text and uploaded files follow the store's retention policy.
- Delete or anonymize feedback when its purpose is complete or consent is
  withdrawn.
- Archived files remain access-restricted until the retention job removes them.
- Audit and recommendation snapshots must not contain raw feedback text beyond
  what is necessary for the recorded recommendation.
