# Security policy

## Reporting a problem in InfraSentinel itself
Please don't open a public issue. Use GitHub's **Report a vulnerability** button (Security tab → Advisories) or email the maintainers. We aim to reply within 3 working days.

## How InfraSentinel protects itself
| Area | Protection |
|---|---|
| Passwords | PBKDF2-SHA256, 200,000 rounds, random salt per account |
| Sign-in | Optional 2-step sign-in (TOTP codes); 5 wrong attempts per account or 20 per network address in 15 minutes → wait; same response time for unknown emails |
| Sessions | Random 192-bit token in an HttpOnly, SameSite cookie (Secure over HTTPS); 12-hour expiry; changing the password signs out other devices |
| Data at rest | One SQLite database, file mode 600; optional encryption (`IS_ENCRYPT=1`, Fernet/AES-128 + HMAC) |
| Checker | Read-only; outbound connection only; can't run commands sent by the dashboard; install commands verify its SHA-256 fingerprint before running it |
| Checker access codes | One per organization, resettable at any time (old commands stop working), age shown with a 90-day reminder |
| AI | Runs on the InfraSentinel server; answers only from scan data; risky commands in answers are flagged; reviewed "checked steps" are shown first |
| Web | `X-Frame-Options: DENY`, `nosniff`, `Referrer-Policy`, HSTS behind HTTPS; web search fetches public addresses only (no internal network access) |
| Public mode | Demo password randomised; "Scan this laptop" and model changes only from the host itself; AI rate limit |

## Known limits
- No independent security audit or penetration test has been done yet.
- The checker is not code-signed yet; integrity is checked with SHA-256 fingerprints, and the Windows program is built by GitHub Actions from this repository.
- Password reset needs the server operator (`python3 server.py --reset-password EMAIL`); there is no email reset yet.
