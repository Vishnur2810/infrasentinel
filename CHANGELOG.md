# Changelog

## 0.5 (October 2026)
- Storage moved from JSON files to one SQLite database with a write lock; optional encryption at rest (`IS_ENCRYPT=1`); automatic migration of old data.
- 2-step sign-in (TOTP), sign-in rate limiting, password change, operator password reset, data export and account deletion.
- Automatic fix verification: each scan is compared with the previous one ("Verified fixes", "1 fixed · 1 new").
- Checker 0.5: macOS checks, network devices and router Telnet/FTP check, names of packages with waiting security fixes, `--every` and `--no-network`; can run as a packaged Windows .exe.
- Install commands verify the checker's SHA-256 fingerprint; Windows falls back to the .exe when Python is missing.
- Reviewed fix steps (`playbook.json`) shown before every AI explanation; risky AI commands flagged; AI answer queue; web search cache and SearXNG option.
- "Who to call" contact on serious problems; configurable risk weights (`IS_WEIGHTS`); security headers.
- Privacy notice, terms, SECURITY.md, MIT license; Docker, systemd and named Cloudflare tunnel deployment; tests and GitHub Actions.

## 0.4
- First public version: accounts, Linux and Windows checker, Scan now, AI assistant with web search, Liquid Glass UI, public link.
