#!/usr/bin/env python3
"""
reset_lastmod_from_git.py — one-off rebuild of config/page_hashes.json.

Sets each page's sitemap <lastmod> to the date of the last commit that changed the page's
CONTENT (template-insensitive digest from content_hash.py), not the last commit that touched
the file. After the 19 Sep 2026 header rewrite every page carried the same lastmod; this
restores real dates so Bing/Google can trust the sitemap again.

  python3 scripts/reset_lastmod_from_git.py          # rewrite config/page_hashes.json
  python3 scripts/reset_lastmod_from_git.py --dry    # print distribution only
"""
import os, sys, json, glob, subprocess, datetime, collections

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from content_hash import content_digest  # noqa: E402

BASE = "https://www.consulting24.co"
TODAY = datetime.date.today().isoformat()
STORE = os.path.join(ROOT, "config", "page_hashes.json")


def git(*args, inp=None):
    return subprocess.run(["git", *args], cwd=ROOT, input=inp, capture_output=True).stdout


def pages():
    out = []
    for path in glob.glob(os.path.join(ROOT, "**", "index.html"), recursive=True):
        head = open(path, encoding="utf-8", errors="ignore").read(1200)
        if "generated-redirect-stub" in head or 'name="robots" content="noindex' in head:
            continue
        rel = os.path.relpath(path, ROOT)
        url_path = "" if rel == "index.html" else "/" + os.path.dirname(rel) + "/"
        out.append((BASE + (url_path or "/"), rel))
    return sorted(out)


def versions(rel):
    """[(sha, date)] newest first for commits touching rel."""
    log = git("log", "--format=%H%x09%cs", "--", rel).decode()
    return [tuple(l.split("\t")) for l in log.splitlines() if "\t" in l]


def blobs(rel, shas):
    """digest per version via one `git cat-file --batch` call."""
    req = "".join(f"{s}:{rel}\n" for s in shas).encode()
    out = git("cat-file", "--batch", inp=req)
    digests, i = [], 0
    for _ in shas:
        nl = out.index(b"\n", i)
        hdr = out[i:nl].decode().split()
        if len(hdr) < 3:                       # "<sha> missing"
            digests.append(None); i = nl + 1; continue
        size = int(hdr[2])
        body = out[nl + 1:nl + 1 + size]
        digests.append(content_digest(body.decode("utf-8", "ignore")))
        i = nl + 1 + size + 1
    return digests


def main():
    dry = "--dry" in sys.argv
    store, dist = {}, collections.Counter()
    for url, rel in pages():
        cur = content_digest(open(os.path.join(ROOT, rel), encoding="utf-8", errors="ignore").read())
        vs = versions(rel)
        if not vs:
            lastmod = TODAY                                    # untracked / new file
        else:
            ds = blobs(rel, [s for s, _ in vs])
            if ds[0] != cur:
                lastmod = TODAY                                # uncommitted content change
            else:
                lastmod = vs[-1][1]                            # default: first commit (never changed since)
                for k in range(len(ds) - 1):
                    if ds[k] != ds[k + 1]:
                        lastmod = vs[k][1]; break
        store[url] = {"hash": cur, "lastmod": lastmod}
        dist[lastmod[:7]] += 1
    print("lastmod by month:", sorted(dist.items()))
    print("today:", dist[TODAY[:7]] if False else sum(1 for v in store.values() if v["lastmod"] == TODAY))
    if not dry:
        json.dump(store, open(STORE, "w"), indent=0)
        print(f"wrote {STORE}: {len(store)} URLs")


if __name__ == "__main__":
    main()
