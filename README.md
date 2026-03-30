# S3 Playlists

Foundry VTT module: playlist compendia that reference remote audio (for example HTTPS URLs on S3). No JavaScript; only `module.json` and compendium `.db` files.

**Automation & agent notes:** [AGENTS.md](AGENTS.md) (commit/push expectations, CI overview, release checklist). Cursor loads [.cursor/rules/s3-playlists.mdc](.cursor/rules/s3-playlists.mdc) for the same.

## Install

**Manifest URL (Foundry or Forge Bazaar):**

`https://raw.githubusercontent.com/kuzin/s3-playlists/main/module.json`

In Foundry: **Add-on Modules → Install Module → Manifest URL**. On [The Forge](https://forgevtt.com/), use the same manifest in the module installer.

## CI workflows

| Workflow | When | What |
|----------|------|------|
| **Validate** | Push / PR to `main` | `module.json` JSON + every pack path exists |
| **Release** | Push tag `*.*.*` | Builds `s3-playlists.zip`, GitHub Release (tag must match `module.json` version) |
| **Sync packs from S3** | Manual + weekly cron | Lists S3, updates `packs/*.db` (optional bot commit) |

Workflows set `FORCE_JAVASCRIPT_ACTIONS_TO_NODE24` so JavaScript actions use Node 24 (avoids deprecation warnings).

## Release a new version

1. Bump `"version"` in `module.json` and commit to `main`.
2. Create and push a tag that **exactly** matches that version (example for `1.8.2`):

   ```bash
   git tag 1.8.2
   git push origin 1.8.2
   ```

3. The [Release](.github/workflows/release.yml) workflow builds `s3-playlists.zip` with `module.json` and `packs/` at the **zip root** (correct for Foundry) and attaches it to a GitHub Release.

The manifest’s `download` field points at `https://github.com/kuzin/s3-playlists/releases/latest/download/s3-playlists.zip`, so installs and updates track the latest GitHub release once at least one release exists.

**First-time setup:** Publish your current version once (for example tag `1.8.1`) so `latest/download` resolves.

## Repo layout

| Path | Purpose |
|------|--------|
| `module.json` | Package manifest |
| `packs/*.db` | Playlist compendia (JSON lines / NeDB-style exports) |
| `sync-packs.json` | Maps each playlist to an S3 key prefix (for sync script) |
| `scripts/sync_packs.py` | `discover` / `sync` from S3 |

## Sync pack DBs from S3

Playlists are driven by [`sync-packs.json`](sync-packs.json): each entry maps a Foundry playlist to an S3 key prefix (under your bucket). The script lists audio objects there and rewrites the corresponding `packs/*.db` lines, **preserving** playlist and sound `_id` values when the HTTPS path is unchanged so worlds stay stable.

### Display names (filename rules, no ID3 / no extra IAM)

`defaults.display_name` controls how **track labels** are derived from each object key’s filename (stem): strip leading `01 - ` style index segments, replace `-` and `_` with spaces, collapse whitespace, and **`title_case`** (default **on**; set to `false` under `display_name` to disable). Per-playlist overrides go under that playlist’s `display_name` (merged over defaults).

- **`defaults.sound_description`**: `"empty"` (default) or `"same_as_name"` to copy the display string into each sound’s `description` field (Foundry’s subtitle-style field).
- **`defaults.playlist_description`**: how to populate Foundry **playlist** `description` strings via the `enrich` command. It’s a template rule using placeholders like `{name}` (playlist doc name) and `{prefix}` (S3 key prefix). Defaults to `"{name} playlist. Streamed from {prefix}"`.
- **`description`** on a playlist entry (optional): per-playlist override for `enrich`. If omitted, `enrich` uses `defaults.playlist_description` for empty descriptions (and you can use `--force` to overwrite).

Run **`discover`** after changing code so `sync-packs.json` includes the latest `defaults` block; then run **`sync`** so `packs/*.db` pick up new names.

### Regenerate config from the current DBs

After you change folder layout in the bucket, edit `sync-packs.json` manually or regenerate:

```bash
python3 scripts/sync_packs.py discover -o sync-packs.json
```

### Local sync (needs AWS credentials)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export AWS_ACCESS_KEY_ID=... AWS_SECRET_ACCESS_KEY=...
python scripts/sync_packs.py sync --config sync-packs.json

# Fill empty playlist blurbs (no AWS; only edits Playlist.description fields)
python scripts/sync_packs.py enrich --config sync-packs.json
```

### GitHub Actions

The [Sync packs from S3](.github/workflows/sync-s3-packs.yml) workflow runs on **workflow_dispatch** (optional **commit** checkbox) and on a **weekly schedule**.

**Trigger from the terminal** ([GitHub CLI](https://cli.github.com/) `gh`, after `gh auth login`):

```bash
gh workflow run sync-s3-packs.yml --ref main -f commit=true   # sync + commit packs to main
gh workflow run sync-s3-packs.yml --ref main -f commit=false  # sync only, no commit
```

Run from a clone of this repo or add `-R kuzin/s3-playlists`. Same as the Actions tab **Run workflow** button.

**Repository secrets** (required for the workflow to talk to S3):

- `AWS_ACCESS_KEY_ID`
- `AWS_SECRET_ACCESS_KEY`

IAM can be minimal: **`s3:ListBucket`** on the bucket (listing prefixes is enough; no `GetObject` required). Example:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ListAudioPrefixes",
      "Effect": "Allow",
      "Action": ["s3:ListBucket"],
      "Resource": "arn:aws:s3:::YOUR_BUCKET_NAME"
    }
  ]
}
```

If you use a prefix-only IAM condition, include every top-level prefix you use (for example `Music/*` and `MGS/*`).
