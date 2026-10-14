# The Scribe of Nexus 4.0.0

Scribe combines cited source search, a notebook, and a chronological work catalog. This extension preserves the working v3 reconstruction and the classic Nexus palette. The supplied original Scribe ZIP could not be recovered; this remains an extension of that reconstruction.

The downloadable package contains the private knowledge archive. This repository contains application code and a GitHub Pages interface. Private source text, exported archives, token files, and refreshed data are excluded from the repository and the Pages artifact.

## Local use

Python 3.9+ and a modern browser are sufficient. No runtime packages, model downloads, or AI API keys are required.

```bash
python3 scribe.py serve --port 8787
```

Open `http://127.0.0.1:8787`. The server binds to loopback, checks the Host header, and exposes read-only archive endpoints. Stop with Ctrl+C. It does not change Termux boot, recovery settings, firewall rules, repository visibility, or Drive permissions.

When working from this code repository, supply the knowledge export explicitly:

```bash
python3 scribe.py --corpus /absolute/path/knowledge.json serve --port 8787
```

## Chronological Google Drive work

The package includes a dated catalog from the exhausted Nexus keyword search pages on the Nexus Generation and machackabook accounts, plus readable text from selected Scribe, Enclave, ADAM, Hamiltonian, OTASONAR, framework and related titles. The import receipt records exact coverage, failures, and empty text. Files outside those keyword searches and other connected accounts remain outside that snapshot. Metadata-only entries are labeled and are not treated as integrated document content.

Drive `createdTime`, `modifiedTime`, and Scribe collection time are separate fields. A Drive creation date can describe an upload or a copy; it does not establish the original work's creation. Unknown dates stay unknown. Variants remain distinct; changed content from the same Drive file retains revision ancestry.

```bash
python3 scribe.py timeline --axis created_at --csv > chronology.csv
python3 scribe.py search 'OTASONAR' --json
```

For a live refresh, obtain a Google OAuth access token with `https://www.googleapis.com/auth/drive.readonly`, store it in a regular file outside the served project, and restrict that file to the current user. The Scribe reads an explicitly selected project folder. It sends no writes to Drive and does not refresh or print tokens. Expired authorization requires a new token from your OAuth client. Connected ChatGPT credentials are not exported into the application.

```bash
python3 scribe.py drive-sync --token-file /absolute/private/path/drive-token.json --folder-id YOUR_PROJECT_FOLDER_ID --recursive
```

The token file can contain a JSON `access_token` or a raw access token. The CLI requires permission mode 600 on Unix. Native Docs and Slides export as text; native Sheets export as one CSV sheet. PDFs, Office files and other binary formats need a separately extracted text snapshot; their status is retained as blocked rather than inventing content. Imports are limited to 8 MiB per returned text file and 128 MiB per corpus; split larger collections by project.

Import a connector-produced snapshot with a list of `{metadata, text, status, collected_at}` records:

```bash
python3 scribe.py ingest /absolute/path/drive_documents.json --inventory /absolute/path/drive_inventory.json
```

Refreshes save into `.private/knowledge.json`, preserve the prior corpus, retain source revisions, and append a SHA-256 event to an integration ledger. Keep the resulting anchor separately. This gives integrity relative to that anchor; it is not immutable storage or hardware attestation. Original uploads are never executed or modified.

## GitHub project Pages

`pages.yml` publishes only a public browser interface. Publishing is manual, requires the main branch and the explicit `approve_public_shell` input, and uses the `github-pages` environment. There is no push-to-publish trigger. Configure repository Pages to use GitHub Actions before dispatching it; plan support is a separate GitHub prerequisite.

Pages generally remains public even when this personal repository is private. This interface therefore embeds no archive or Drive token. You select a local `knowledge.json` or encrypted vault after opening the page. Imported content remains in that browser tab. Hosted notes are held in memory; export a backup before closing. Localhost notes retain the v3 storage key so existing notes at the same origin remain available.

The Integrations pane can export a password-encrypted archive using PBKDF2-SHA256 (600,000 iterations), a random salt, and AES-256-GCM with a random nonce. A passphrase of at least 16 characters is required. Keep it separately; the application cannot recover it. This is protection for the exported file, not GitHub Pages access control. The Pages Content Security Policy blocks network connections.

```bash
python3 scribe.py build-pages --output site
python3 scripts/check_pages.py site
```

Only five explicitly permitted files can enter the Pages artifact. The guard checks the empty embedded corpus and rejects recognized credential patterns. Downloaded private knowledge and mutable state remain outside the published path. Relative asset paths support `/The-Scribe/` project URLs.

## Verification and limitations

```bash
python3 -m unittest discover -s tests -v
node tests/test-core.cjs
```

These are component checks, not proof of live Drive delivery, deployed Pages, TPM attestation, sensor verification or device readiness. Live connector reads are documented separately in the returned integration receipt. Browser audio records only a user-initiated microphone take; AI transcription is unconfigured. Scribe does not implement the proposed APFS Enclave mounting, SYNAPSE OAuth gateway, TPM trust root, RF geolocation or BERH zero-latency claims.

The included private archive has checksums. The self-contained installer verifies the payload and final installed bytes, reuses an identical release, backs up a modified recognized release, and starts the foreground server. `--no-start`, `--root PATH`, and `--port PORT` remain supported. Roll back by stopping the server and starting the preserved release from its own directory. Export notes before changing the localhost port or moving to a hosted origin.
