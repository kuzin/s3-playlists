#!/usr/bin/env python3
"""
Discover S3 prefixes from existing pack DBs, or sync pack .db files from live S3 listings.

Usage:
  python scripts/sync_packs.py discover [--output sync-packs.json]
  python scripts/sync_packs.py sync [--config sync-packs.json] [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import string
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import unquote

REPO_ROOT = Path(__file__).resolve().parent.parent
_ID_CHARS = string.ascii_letters + string.digits
AUDIO_EXT = {".mp3", ".wav", ".ogg", ".flac", ".webm", ".m4a", ".opus", ".aac"}


def new_foundry_id() -> str:
    return "".join(secrets.choice(_ID_CHARS) for _ in range(16))


def url_to_key(url: str) -> str | None:
    m = re.search(r"amazonaws\.com/(.+)$", url)
    if not m:
        return None
    return unquote(m.group(1))


def key_to_prefix(key: str) -> str:
    d = os.path.dirname(key.replace("\\", "/"))
    return d + "/" if d else ""


def load_module_pack_order(repo: Path) -> list[str]:
    data = json.loads((repo / "module.json").read_text(encoding="utf-8"))
    return [p["path"] for p in data.get("packs", [])]


def load_playlists_from_db(db_path: Path) -> list[dict[str, Any]]:
    if not db_path.is_file():
        return []
    raw = db_path.read_text(encoding="utf-8")
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        doc = json.loads(line)
        pid = doc.get("_id")
        if pid in seen:
            continue
        seen.add(pid)
        out.append(doc)
    return out


def cmd_discover(repo: Path, output: Path) -> None:
    if not output.is_absolute():
        output = (repo / output).resolve()
    pack_paths = load_module_pack_order(repo)
    bucket = None
    region = None
    packs_out: list[dict[str, Any]] = []

    for rel in pack_paths:
        db_path = repo / rel
        playlists = load_playlists_from_db(db_path)
        pl_cfg: list[dict[str, Any]] = []
        for doc in playlists:
            sounds = doc.get("sounds") or []
            if not sounds:
                print(f"warn: {rel} playlist {doc.get('name')!r} has no sounds; skipping", file=sys.stderr)
                continue
            path0 = sounds[0].get("path", "")
            key = url_to_key(path0)
            if not key:
                print(f"warn: bad URL in {rel}: {path0[:80]}", file=sys.stderr)
                continue
            if bucket is None:
                m = re.match(r"https://([^.]+)\.s3\.([^.]+)\.amazonaws\.com/", path0)
                if m:
                    bucket, region = m.group(1), m.group(2)
            prefix = key_to_prefix(key)
            entry: dict[str, Any] = {
                "name": doc["name"],
                "prefix": prefix,
                "playlist_id": doc.get("_id"),
            }
            r0 = sounds[0].get("repeat")
            v0 = sounds[0].get("volume")
            if r0 is not None:
                entry["repeat"] = r0
            if v0 is not None:
                entry["volume"] = v0
            desc = (doc.get("description") or "").strip()
            if desc:
                entry["description"] = doc["description"]
            pl_cfg.append(entry)
        packs_out.append({"path": rel, "playlists": pl_cfg})

    if not bucket or not region:
        print("error: could not infer bucket/region from existing pack URLs", file=sys.stderr)
        sys.exit(1)

    root_cfg = {
        "bucket": bucket,
        "region": region,
        "defaults": {
            "repeat": True,
            "volume": 0.72,
            "sorting": "a",
            "sound_description": "empty",
            "display_name": {
                "strip_leading_index": True,
                "hyphen_to_space": True,
                "underscore_to_space": True,
                "collapse_whitespace": True,
                "title_case": True,
            },
        },
        "packs": packs_out,
    }
    output.write_text(
        json.dumps(root_cfg, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {output.relative_to(repo)}")


def load_config(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() in (".yaml", ".yml"):
        try:
            import yaml  # type: ignore
        except ImportError as e:
            print("error: PyYAML required for .yaml config. pip install PyYAML", file=sys.stderr)
            raise SystemExit(1) from e
        return yaml.safe_load(text)
    return json.loads(text)


def quote_s3_url(bucket: str, region: str, key: str) -> str:
    from urllib.parse import quote

    q = quote(key, safe="/")
    return f"https://{bucket}.s3.{region}.amazonaws.com/{q}"


def list_audio_keys(client: Any, bucket: str, prefix: str) -> list[str]:
    keys: list[str] = []
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            k = obj["Key"]
            if k.endswith("/"):
                continue
            suf = Path(k).suffix.lower()
            if suf in AUDIO_EXT:
                keys.append(k)
    return sorted(keys)


def merge_display_name_opts(defaults: dict[str, Any], pl: dict[str, Any]) -> dict[str, Any]:
    a = dict(defaults.get("display_name") or {})
    a.update(pl.get("display_name") or {})
    return a


def humanize_stem(stem: str, opts: dict[str, Any]) -> str:
    """Turn a filename stem into a nicer label (no IAM; filename rules only)."""
    s = stem.strip()
    if opts.get("strip_leading_index", True):
        for _ in range(8):
            prev = s
            s = re.sub(r"^\s*\d+\s*-\s*", "", s, count=1)
            if s == prev:
                break
    if opts.get("underscore_to_space", True):
        s = s.replace("_", " ")
    if opts.get("hyphen_to_space", True):
        s = s.replace("-", " ")
    if opts.get("collapse_whitespace", True):
        s = re.sub(r"\s+", " ", s).strip()
    if opts.get("title_case", True):
        s = s.title()
    return s or stem


def sound_display_name(key: str, opts: dict[str, Any]) -> str:
    stem = Path(key).stem
    base = stem or Path(key).name
    return humanize_stem(base, opts)


def sound_description_for(
    display_name: str, defaults: dict[str, Any], pl: dict[str, Any]
) -> str:
    mode = pl.get("sound_description")
    if mode is None:
        mode = defaults.get("sound_description", "empty")
    if mode == "same_as_name":
        return display_name
    return ""


def cmd_sync(repo: Path, config_path: Path, dry_run: bool) -> None:
    try:
        import boto3
    except ImportError:
        print("error: boto3 required. pip install -r requirements.txt", file=sys.stderr)
        raise SystemExit(1)

    if not config_path.is_absolute():
        config_path = (repo / config_path).resolve()
    cfg = load_config(config_path)
    bucket = cfg["bucket"]
    region = cfg["region"]
    defaults = cfg.get("defaults") or {}
    default_repeat = defaults.get("repeat", True)
    default_volume = float(defaults.get("volume", 0.72))
    default_sorting = defaults.get("sorting", "a")

    client = boto3.client("s3", region_name=region)

    for pack in cfg["packs"]:
        rel = pack["path"]
        out_path = repo / rel
        existing = load_playlists_from_db(out_path)
        by_id = {d["_id"]: d for d in existing}
        by_name_prefix: dict[tuple[str, str], dict[str, Any]] = {}
        for d in existing:
            sounds = d.get("sounds") or []
            if not sounds:
                continue
            k = url_to_key(sounds[0].get("path", ""))
            if not k:
                continue
            by_name_prefix[(d["name"], key_to_prefix(k))] = d

        lines_out: list[str] = []
        for pl in pack["playlists"]:
            name = pl["name"]
            prefix = pl["prefix"]
            playlist_id = pl.get("playlist_id")
            repeat = pl.get("repeat", default_repeat)
            volume = float(pl.get("volume", default_volume))
            sorting = pl.get("sorting", default_sorting)
            display_opts = merge_display_name_opts(defaults, pl)

            doc = None
            if playlist_id and playlist_id in by_id:
                doc = json.loads(json.dumps(by_id[playlist_id]))
            elif (name, prefix) in by_name_prefix:
                doc = json.loads(json.dumps(by_name_prefix[(name, prefix)]))
            else:
                doc = None

            if doc is None:
                doc = {
                    "name": name,
                    "flags": {"playlist_import": {"isPlaylistImported": True}},
                    "sounds": [],
                    "mode": 0,
                    "playing": False,
                    "description": "",
                    "fade": None,
                    "sorting": sorting,
                    "seed": None,
                    "_stats": {
                        "systemId": None,
                        "systemVersion": None,
                        "coreVersion": "12",
                        "createdTime": int(time.time() * 1000),
                        "modifiedTime": int(time.time() * 1000),
                        "lastModifiedBy": None,
                    },
                    "ownership": {"default": 0},
                    "folder": None,
                    "sort": 0,
                    "_id": playlist_id or new_foundry_id(),
                }
            else:
                doc["name"] = name
                doc["sorting"] = sorting

            if "description" in pl:
                doc["description"] = pl["description"] if pl["description"] is not None else ""

            old_by_path = {s["path"]: s for s in (doc.get("sounds") or []) if s.get("path")}
            keys = list_audio_keys(client, bucket, prefix)
            new_sounds: list[dict[str, Any]] = []
            for sort_idx, key in enumerate(keys):
                url = quote_s3_url(bucket, region, key)
                disp = sound_display_name(key, display_opts)
                sd = sound_description_for(disp, defaults, pl)
                if url in old_by_path:
                    s = json.loads(json.dumps(old_by_path[url]))
                    s["name"] = disp
                    s["description"] = sd
                    s["repeat"] = repeat
                    s["volume"] = volume
                    s["sort"] = sort_idx
                    new_sounds.append(s)
                else:
                    new_sounds.append(
                        {
                            "name": disp,
                            "path": url,
                            "repeat": repeat,
                            "volume": volume,
                            "_id": new_foundry_id(),
                            "description": sd,
                            "playing": False,
                            "pausedTime": None,
                            "fade": None,
                            "sort": sort_idx,
                            "flags": {},
                        }
                    )
            doc["sounds"] = new_sounds
            now = int(time.time() * 1000)
            st = doc.get("_stats") or {}
            st["modifiedTime"] = now
            doc["_stats"] = st

            lines_out.append(json.dumps(doc, ensure_ascii=False, separators=(",", ":")))

        text = "\n".join(lines_out) + ("\n" if lines_out else "")
        if dry_run:
            print(f"[dry-run] would write {rel} ({len(lines_out)} playlists)")
        else:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(text, encoding="utf-8")
            print(f"wrote {rel} ({len(lines_out)} playlists)")


def main() -> None:
    ap = argparse.ArgumentParser(description="Foundry pack sync from S3")
    sub = ap.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("discover", help="Build sync-packs.json from current packs/*.db")
    d.add_argument("--output", "-o", type=Path, default=REPO_ROOT / "sync-packs.json")

    s = sub.add_parser("sync", help="List S3 and rewrite pack DBs")
    s.add_argument("--config", "-c", type=Path, default=REPO_ROOT / "sync-packs.json")
    s.add_argument("--dry-run", action="store_true")

    args = ap.parse_args()
    if args.cmd == "discover":
        cmd_discover(REPO_ROOT, args.output)
    else:
        cmd_sync(REPO_ROOT, args.config, args.dry_run)


if __name__ == "__main__":
    main()
