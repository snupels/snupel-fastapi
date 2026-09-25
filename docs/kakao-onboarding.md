# Kakao login and initial consent

Kakao authorization uses the official REST flow with `prompt=login` so a normal
desktop/mobile browser reauthenticates instead of silently reusing an account.
Kakao does not support this prompt inside its own in-app browser; the login page
advises opening an external browser when another account is needed.
The site never collects a Kakao password or reproduces the PC KakaoTalk app.

New tokens issued by AuthService carry a signed `onboarding_required` flag based
on the saved nickname, phone number, terms consent and privacy consent.
Restricted tokens can access their own auth profile to complete setup, but cannot
use member routes (missions, likes, comments, follows, reviewer functions).
Public routes treat them as unauthenticated.

After profile/consent submission, POST `/api/auth/complete-onboarding` checks
the stored profile before issuing a normal token. Frontend checks the same account
and token are still active before storing the response. Failed or stale responses
cannot restore a logged-out/switched account. Marketing choices remain optional.
Existing consent dates are preserved and returning members do not re-consent.

Previously issued tokens without the flag retain their original validity for
backward compatibility (up to the configured token expiry); this does not perform
global session revocation. No existing social-account links are merged or deleted.

Deploy backend and frontend together, backend first. This change does not prove
the cause of the reported account mismatch; the displayed profile and intended
Kakao account still need to be compared with the user.

Reference: https://developers.kakao.com/docs/ko/kakaologin/rest-api#request-code
