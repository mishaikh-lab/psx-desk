#!/usr/bin/env python3
"""
psx_fetch.py - pulls the public tables from the PSX Data Portal into data.json.

For personal research use. Please keep it low-frequency (a few runs per day at most).

Setup (one time):   pip install requests beautifulsoup4
Run:                python psx_fetch.py
With holdings:      python psx_fetch.py --symbols FFC,OGDC,HBL
Extra page:         python psx_fetch.py --add indices=/indices

Every <table> on each page is saved as-is (headers + rows + links), so the dashboard
keeps working even if PSX adds or reorders columns. If a page comes back with no
tables it is probably rendered by JavaScript - the log will say so.
"""
import argparse
import datetime
import json
import os
import sys
import time
from urllib.parse import urljoin

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    sys.exit("Missing packages. Run:  pip install requests beautifulsoup4")

BASE = "https://dps.psx.com.pk"

# Edit freely: name -> path on the data portal. If a path is wrong the log shows it.
PAGES = {
    "market-watch": "/market-watch",
    "payouts": "/payouts",
    "announcements": "/announcements",
}

HEADERS = {"User-Agent": "PSX-Desk personal research script (low frequency, single user)"}
DELAY_SECONDS = 2.0


def clean(text):
    return " ".join(text.split())


def parse_tables(html, page_url):
    soup = BeautifulSoup(html, "html.parser")
    tables = []
    for t in soup.find_all("table"):
        headers = [clean(th.get_text(" ")) for th in t.select("thead th")]
        trs = t.select("tbody tr") or t.find_all("tr")
        rows, row_links = [], []
        for tr in trs:
            tds = tr.find_all("td")
            if not tds:
                if not headers:
                    headers = [clean(th.get_text(" ")) for th in tr.find_all("th")]
                continue
            rows.append([clean(td.get_text(" ")) for td in tds])
            row_links.append([urljoin(page_url, a["href"]) for a in tr.find_all("a", href=True)])
        if not rows:
            continue
        width = max(len(r) for r in rows)
        if len(headers) < width:
            headers += [f"Column {i + 1}" for i in range(len(headers), width)]
        tables.append({"headers": headers[:width], "rows": rows, "row_links": row_links})
    return tables, soup


def fetch_page(path):
    url = urljoin(BASE, path)
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    tables, soup = parse_tables(resp.text, url)
    entry = {"url": url, "tables": tables}
    if not tables:
        entry["text_preview"] = clean(soup.get_text(" "))[:3000]
    return entry


def main():
    ap = argparse.ArgumentParser(description="Fetch public PSX Data Portal tables.")
    ap.add_argument("--out", default="data.json", help="output file (default data.json)")
    ap.add_argument("--symbols", default="", help="comma-separated symbols to fetch company pages for")
    ap.add_argument("--add", action="append", default=[], metavar="NAME=/path", help="extra page to fetch")
    args = ap.parse_args()

    pages = dict(PAGES)
    for item in args.add:
        if "=" not in item:
            sys.exit(f"--add needs NAME=/path, got: {item}")
        name, path = item.split("=", 1)
        pages[name.strip()] = path.strip()
    for sym in [s.strip().upper() for s in args.symbols.split(",") if s.strip()]:
        pages[f"company:{sym}"] = f"/company/{sym}"

    previous = {}
    if os.path.exists(args.out):
        try:
            with open(args.out, encoding="utf-8") as f:
                previous = json.load(f).get("pages", {})
        except (OSError, ValueError):
            previous = {}

    result = {}
    log = {}
    for i, (name, path) in enumerate(pages.items()):
        if i:
            time.sleep(DELAY_SECONDS)
        try:
            entry = fetch_page(path)
            result[name] = entry
            n = sum(len(t["rows"]) for t in entry["tables"])
            log[name] = f"ok - {len(entry['tables'])} table(s), {n} row(s)"
            if not entry["tables"]:
                log[name] = "ok but NO TABLES found (page may be JavaScript-rendered)"
        except Exception as exc:  # keep going; keep the last good copy if we have one
            log[name] = f"FAILED - {exc}"
            if name in previous:
                result[name] = dict(previous[name], stale=True)
                log[name] += " (kept previous copy)"

    out = {
        "fetched_at": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "source": BASE,
        "pages": result,
    }
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)

    print(f"\nWrote {args.out}")
    for name, msg in log.items():
        print(f"  {name:<22} {msg}")


if __name__ == "__main__":
    main()
