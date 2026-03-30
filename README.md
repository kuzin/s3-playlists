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
