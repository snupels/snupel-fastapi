# Mission review and feed management

- Set `MISSION_REVIEWER_EMAILS` to the comma-separated, existing account email
  addresses authorized to review mission photo submissions. These accounts do
  not receive unrelated administrator CRUD or reward-shipping permissions.
- Existing `ADMIN_EMAILS` accounts retain review access.
- Deployment reads the GitHub repository variable `MISSION_REVIEWER_EMAILS`
  into the server environment. A missing/empty deployment value preserves the
  existing server setting. To revoke everyone in this new role, set the variable
  to a single space and redeploy (the parsed allowlist becomes empty).
- Deploy the backend and Alembic migration `0046_feed_deletion` before the
  frontend. Sign in normally (including Google) and open `/mission-review/`;
  the account and passport pages show this link only after a permission check.

## Certification and feed are independent

- Only a pending certification may be approved/rejected; review locks and the
  existing stamp/badge award service prevent duplicate rewards.
- Public feeds require approved, shared, non-deleted submissions.
- Only the owner may view private approved posts on their own feed/profile or
  post detail, and change public/private visibility. Other users cannot retrieve
  private/deleted detail, comments, likes, or liked-feed entries.
- Visibility-only PATCH retains the caption. Explicit caption edits remain
  supported. Proof photos and engagement records are retained.
- DELETE `/api/stamp-submissions/{id}/feed` marks feed-only deletion, returning
  204 (also on repeated owner deletion). It never deletes certification rows,
  proofs, collected stamps or badges, and never changes approval status.
  Deleted posts cannot be republished using visibility PATCH.
- Previously issued signed photo URLs can remain valid for their existing
  10-minute lifetime. This change does not revoke already downloaded photos.
  Existing security middleware marks feed responses no-store to prevent caching.

Tests in `test_feed_management.py` exercise real repository queries against an
isolated SQLite database, including approval, privacy transitions, authorization,
deletion, and award preservation. No production submissions are used for tests.
