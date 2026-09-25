# Kakao account email

The provider must grant `account_email`, and the user must consent. The returned
email is accepted only when both `is_email_valid` and `is_email_verified` are true.
Never infer an address from the Kakao nickname or phone number.

In Kakao Developers, enable Kakao Login > Consent Items > Kakao account (email).
If unavailable, obtain the app's required permission through Kakao first. After
confirming this permission, set the GitHub repository variable
`KAKAO_REQUEST_EMAIL=true` and deploy. This explicitly requests email consent on
login, including for previously connected users. Without this flag, the existing
console-configured consent flow is preserved. Requesting an unapproved scope can
break login, so the flag is deliberately not enabled by the code change.

Existing Kakao users with the exact generated `kakao_<provider id>@oauth...`
placeholder can receive their verified email on their next login. The same user
ID, passport, consent history, submissions and rewards remain intact. Real account
emails are not overwritten. If another account already owns that email, keep the
original user and address; never silently merge accounts or transfer rewards.
Concurrent email-uniqueness conflicts roll back only the email update.

Deployment alone cannot obtain an email Kakao has not supplied. Console permission
and user consent must be verified separately; no user login is performed by tests.

Reference: https://developers.kakao.com/docs/ko/kakaologin/rest-api#req-user-info
