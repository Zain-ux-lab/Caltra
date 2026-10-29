# Private free cloud beta

Status: prepared locally; no cloud deployment has been created yet.

Use Render Free Docker web service plus Neon Free PostgreSQL. This is a private single-user beta; do not share the login or host multiple users on one diary.

Required private Render environment variables:
- CALTRA_PUBLIC_ORIGIN: exact HTTPS origin assigned by Render
- CALTRA_ACCESS_PASSWORD: random password at least 16 characters; username is caltra
- CALTRA_DATABASE_URL: Neon PostgreSQL connection URI, with sslmode=require
- GEMINI_API_KEY: existing private Gemini key, configured in the hosting dashboard

Use Dockerfile at repository root, free compute, health path /healthz, no persistent disk, one instance. Do not enable paid upgrades. No personal SQLite database or evaluation photos are copied into the image. Existing local diary is not automatically migrated; cloud starts with a separate diary.

Render Free sleeps when idle and may take about a minute to wake. Neon Free has usage quotas and suspends compute when idle. Review quotas periodically. AI provider quotas/billing remain separate.

Security checks: anonymous diary/settings requests must return 401, incorrect hosts 403, missing cloud password 503, foreign-origin writes 403. API credentials never belong in frontend code or Git. Service worker caches only the offline notice.

Pending verification: build container on Render; verify a real Neon transaction, diary save/read across restart, HTTPS authenticated phone access and PWA installation. SQL adapter unit tests do not replace live PostgreSQL integration checks.

Sources: https://render.com/docs/free and https://neon.com/pricing
