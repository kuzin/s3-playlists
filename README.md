# S3 Playlists

Foundry VTT module: playlist compendia that reference remote audio (for example HTTPS URLs on S3). No JavaScript; only `module.json` and compendium `.db` files.

## Install

**Manifest URL (Foundry or Forge Bazaar):**

`https://raw.githubusercontent.com/kuzin/s3-playlists/main/module.json`

In Foundry: **Add-on Modules → Install Module → Manifest URL**. On [The Forge](https://forgevtt.com/), use the same manifest in the module installer.

## Release a new version

1. Bump `"version"` in `module.json` and commit to `main`.
2. Create and push an annotated tag that **exactly** matches that version (example for `1.8.2`):

   ```bash
   git tag 1.8.2
   git push origin 1.8.2
   ```

3. The [Release](.github/workflows/release.yml) workflow builds `s3-playlists.zip` with `module.json` and `packs/` at the **zip root** (correct for Foundry) and attaches it to a GitHub Release.

The manifest’s `download` field points at `.../releases/latest/download/s3-playlists.zip`, so installs and updates track the latest GitHub release automatically once at least one release exists.

**First-time setup:** After merging these workflows, publish your current version once (for example tag `1.8.1`) so `latest/download` resolves.

## Repo layout

| Path | Purpose |
|------|--------|
| `module.json` | Package manifest |
| `packs/*.db` | Playlist compendia (JSON lines / NeDB-style exports) |

Pull requests run a [validation workflow](.github/workflows/validate.yml) that checks JSON and that every pack path exists.

## Sync pack DBs from S3

Playlists are driven by [`sync-packs.json`](sync-packs.json): each entry maps a Foundry playlist to an S3 key prefix (under your bucket). The script lists audio objects there and rewrites the corresponding `packs/*.db` lines, **preserving** playlist and sound `_id` values when the HTTPS path is unchanged so worlds stay stable.

### One-time: regenerate config from the current DBs

After you change folder layout in the bucket, edit `sync-packs.json` manually or regenerate from what is already in the repo:

```bash
python3 scripts/sync_packs.py discover -o sync-packs.json
```

### Local sync (needs AWS credentials)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export AWS_ACCESS_KEY_ID=... AWS_SECRET_ACCESS_KEY=...
python scripts/sync_packs.py sync --config sync-packs.json
```

### GitHub Actions

The [Sync packs from S3](.github/workflows/sync-s3-packs.yml) workflow runs on **workflow_dispatch** (optional **commit** checkbox) and on a **weekly schedule**. Add repository secrets:

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
