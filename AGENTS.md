# Agent instructions (Cursor / automation)

This file is for **humans and AI assistants** working on `s3-playlists`. Keep it accurate when workflows, scripts, or conventions change—**update this file and [README.md](README.md) together** when behavior or setup changes.

## Project

- **What it is:** Foundry VTT module: no JS; [`module.json`](module.json) + [`packs/*.db`](packs/) (JSONL, one playlist document per line).
- **Audio:** HTTPS URLs to objects in S3 (virtual-hosted style URLs in the DBs).
- **Config:** [`sync-packs.json`](sync-packs.json) maps each playlist to an S3 key prefix. [`scripts/sync_packs.py`](scripts/sync_packs.py): `discover` regenerates config from DBs; `sync` lists S3 and rewrites `.db` files (preserves sound `_id` when URL unchanged). **`defaults.display_name`** humanizes filename stems (strip index, hyphens to spaces, **`title_case`** on by default); optional **`sound_description`**: `same_as_name`; **`defaults.playlist_description`** template + offline `enrich` command to fill empty `Playlist.description` fields.

## Git: commit and push to `main`

Unless the user explicitly asks otherwise (e.g. “don’t push”, draft PR only):

1. After **any substantive change** (code, workflows, docs, `sync-packs.json`, pack DBs when intentionally edited in-repo), **`git add`**, **`git commit`** with a short imperative message, then **`git push origin main`**.
2. If **`git pull` is needed** (non–fast-forward), prefer **`git pull --rebase origin main`** then push.
3. Do **not** commit secrets, `.env`, or AWS keys. `.venv/` and `__pycache__/` are ignored.

## GitHub Actions (this repo)

| Workflow | File | Purpose |
|----------|------|--------|
| Validate | [`.github/workflows/validate.yml`](.github/workflows/validate.yml) | On push/PR to `main`: valid `module.json`, pack paths exist. |
| Release | [`.github/workflows/release.yml`](.github/workflows/release.yml) | On tag `*.*.*`: tag must match `module.json` `version`; uploads `s3-playlists.zip` to Releases. |
| Sync S3 | [`.github/workflows/sync-s3-packs.yml`](.github/workflows/sync-s3-packs.yml) | Lists S3, runs `sync`; when it commits `packs/*.db` it auto-bumps `module.json` patch version + tags (triggering Release). Needs `AWS_*` secrets. |

Workflow-level **`FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: true`** avoids Node 20 deprecation warnings for JS actions.

### Trigger **Sync packs from S3** via GitHub CLI (`gh`)

From the repo root (or pass `-R kuzin/s3-playlists`), after **`gh auth login`** with a token that includes **`workflow`** (the default `repo` scope usually includes it):

```bash
# Sync from S3 and commit/push updated packs/*.db to main (same as UI checkbox on)
gh workflow run sync-s3-packs.yml --ref main -f commit=true

# Sync only; do not commit (inspect logs / confirm no unwanted diffs, no version bump)
gh workflow run sync-s3-packs.yml --ref main -f commit=false
```

Watch the latest run: `gh run list --workflow=sync-s3-packs.yml -L 1` then `gh run watch <RUN_ID>`.

Agents in Cursor can run these commands when the user asks, if `gh auth status` works in that environment.

## Secrets (repository)

- **`AWS_ACCESS_KEY_ID`**, **`AWS_SECRET_ACCESS_KEY`** — for Sync workflow; IAM needs at least **`s3:ListBucket`** on the bucket.

## Release checklist (new Foundry version)

1. Bump **`"version"`** in `module.json`; commit and push to `main`.
2. Tag and push: `git tag X.Y.Z && git push origin X.Y.Z` (tag **must** equal `version`).
3. Confirm Release workflow attached **`s3-playlists.zip`**; manifest `download` uses `releases/latest/download/...`.

## Local commands

```bash
# Regenerate sync-packs.json from current DBs (after S3 folder layout changes)
python3 scripts/sync_packs.py discover -o sync-packs.json

# Sync from S3 (needs venv + boto3 + AWS env vars)
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python scripts/sync_packs.py sync --config sync-packs.json

# Fill empty playlist blurbs (no AWS; only edits Playlist.description fields)
python scripts/sync_packs.py enrich --config sync-packs.json
```

## Documentation maintenance

- **README.md** — User-facing: install, release, sync, IAM snippet, `gh workflow run` for Sync, links.
- **AGENTS.md** (this file) — Agent/operator: conventions, CI table, commit/push expectation, `gh` dispatch for Sync, release steps.

When adding or changing workflows, scripts, or required secrets, **update both** README and AGENTS.
