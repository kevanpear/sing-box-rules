#!/usr/bin/env python3
"""Convert the upstream AutoProxy GFWList into a sing-box rule-set source.

The upstream file is Base64-encoded.  Domain anchors become domain_suffix
rules, URL anchors become exact domain rules, plain entries become
domain_keyword rules, and regular expressions are preserved.

Exact terms already present in geosite_direct are removed so the generated
proxy list cannot reintroduce direct/proxy conflicts.
"""

import argparse
import base64
import binascii
import json
import os
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit


PRIMARY_URL = (
    "https://raw.githubusercontent.com/YW5vbnltb3Vz/"
    "domain-list-community/release/gfwlist.txt"
)
FALLBACK_URL = (
    "https://fastly.jsdelivr.net/gh/YW5vbnltb3Vz/"
    "domain-list-community@release/gfwlist.txt"
)
FIELDS = ("domain", "domain_suffix", "domain_keyword", "domain_regex")


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default=PRIMARY_URL)
    parser.add_argument("--fallback", default=FALLBACK_URL)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("source/geosite_proxy.json"),
    )
    parser.add_argument(
        "--direct",
        type=Path,
        default=Path("source/geosite_direct.json"),
    )
    parser.add_argument(
        "--max-change-ratio",
        type=float,
        default=0.05,
        help="maximum (additions + removals) / old rule count (default: 0.05)",
    )
    parser.add_argument(
        "--minimum-rules",
        type=int,
        default=10_000,
        help="reject generated lists smaller than this (default: 10000)",
    )
    parser.add_argument(
        "--allow-large-change",
        action="store_true",
        help="accept a change larger than --max-change-ratio",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="validate and report without writing the output file",
    )
    return parser.parse_args()


def fetch(urls):
    errors = []
    for url in urls:
        if not url:
            continue
        request = urllib.request.Request(
            url,
            headers={
                "Accept": "text/plain",
                "User-Agent": "sing-box-rules-sync/1.0",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                body = response.read()
            if len(body) < 1_000:
                raise ValueError("response is unexpectedly small: {} bytes".format(len(body)))
            print("[fetch] {} ({} bytes)".format(url, len(body)))
            return body
        except (OSError, ValueError, urllib.error.URLError) as exc:
            errors.append("{}: {}".format(url, exc))
    raise RuntimeError("all upstream downloads failed:\n  " + "\n  ".join(errors))


def decode_autoproxy(raw):
    compact = b"".join(raw.split())
    try:
        decoded = base64.b64decode(compact, validate=True).decode("ascii")
    except (binascii.Error, UnicodeDecodeError) as exc:
        raise ValueError("upstream is not valid Base64-encoded ASCII") from exc
    lines = decoded.splitlines()
    if not lines or lines[0].strip() != "[AutoProxy 0.2.9]":
        raise ValueError("missing expected AutoProxy 0.2.9 header")
    return lines


def clean_domain(value, line_number):
    value = value.strip().lower().rstrip(".")
    if (
        not value
        or any(char.isspace() for char in value)
        or any(char in value for char in "/|^")
    ):
        raise ValueError("invalid domain at decoded line {}: {!r}".format(line_number, value))
    return value


def parse_rules(lines):
    rules = {field: set() for field in FIELDS}
    metadata = []
    for line_number, raw_line in enumerate(lines, 1):
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("!") or line.startswith("["):
            metadata.append(line)
            continue
        if line.startswith("@@"):
            raise ValueError(
                "unsupported AutoProxy exception at decoded line {}: {}"
                .format(line_number, line)
            )
        if line.startswith("||"):
            value = line[2:]
            if value.endswith("^"):
                value = value[:-1]
            rules["domain_suffix"].add(clean_domain(value, line_number))
            continue
        if line.startswith("|http://") or line.startswith("|https://"):
            parsed = urlsplit(line[1:])
            if not parsed.hostname:
                raise ValueError(
                    "URL anchor has no hostname at decoded line {}: {}"
                    .format(line_number, line)
                )
            rules["domain"].add(clean_domain(parsed.hostname, line_number))
            continue
        if len(line) >= 2 and line.startswith("/") and line.endswith("/"):
            expression = line[1:-1]
            if not expression:
                raise ValueError("empty regex at decoded line {}".format(line_number))
            rules["domain_regex"].add(expression)
            continue
        if line.startswith("|") or any(char.isspace() for char in line):
            raise ValueError(
                "unsupported AutoProxy syntax at decoded line {}: {}"
                .format(line_number, line)
            )
        rules["domain_keyword"].add(line)
    return rules, metadata


def load_rule_terms(path):
    data = json.loads(path.read_text(encoding="utf-8"))
    terms = set()
    for rule in data.get("rules", []):
        for field in ("domain", "domain_suffix"):
            values = rule.get(field, [])
            if isinstance(values, str):
                values = [values]
            terms.update(value.lower() for value in values)
    return terms


def load_existing(path):
    empty = {field: set() for field in FIELDS}
    if not path.exists():
        return empty
    data = json.loads(path.read_text(encoding="utf-8"))
    for rule in data.get("rules", []):
        for field in FIELDS:
            values = rule.get(field, [])
            if isinstance(values, str):
                values = [values]
            empty[field].update(values)
    return empty


def report_delta(old, new):
    additions = 0
    removals = 0
    for field in FIELDS:
        added = len(new[field] - old[field])
        removed = len(old[field] - new[field])
        additions += added
        removals += removed
        print(
            "[delta] {:13s} old={:6d} new={:6d} add={:5d} remove={:5d}"
            .format(field, len(old[field]), len(new[field]), added, removed)
        )
    old_total = sum(len(old[field]) for field in FIELDS)
    new_total = sum(len(new[field]) for field in FIELDS)
    ratio = (additions + removals) / max(old_total, 1)
    print(
        "[delta] total old={} new={} add={} remove={} ratio={:.2%}"
        .format(old_total, new_total, additions, removals, ratio)
    )
    return old_total, new_total, ratio


def render(rules):
    rule = {}
    for field in FIELDS:
        if rules[field]:
            rule[field] = sorted(rules[field])
    return (
        json.dumps(
            {"version": 1, "rules": [rule]},
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    )


def atomic_write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=path.name + ".",
        suffix=".tmp",
        dir=str(path.parent),
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
        os.replace(temporary_name, str(path))
    except Exception:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def main():
    args = parse_args()
    if not 0 <= args.max_change_ratio <= 1:
        raise ValueError("--max-change-ratio must be between 0 and 1")

    raw = fetch(dict.fromkeys((args.source, args.fallback)))
    rules, metadata = parse_rules(decode_autoproxy(raw))
    direct_terms = load_rule_terms(args.direct)
    before_filter = len(rules["domain"]) + len(rules["domain_suffix"])
    rules["domain"] -= direct_terms
    rules["domain_suffix"] -= direct_terms
    filtered = before_filter - len(rules["domain"]) - len(rules["domain_suffix"])
    print("[filter] removed {} exact terms already present in direct".format(filtered))
    for line in metadata:
        if line.startswith("! Last Modified:"):
            print("[source]{}".format(line[1:]))

    old = load_existing(args.output)
    _, new_total, ratio = report_delta(old, rules)
    if new_total < args.minimum_rules:
        raise RuntimeError(
            "generated rule count {} is below safety minimum {}"
            .format(new_total, args.minimum_rules)
        )
    if ratio > args.max_change_ratio and not args.allow_large_change:
        raise RuntimeError(
            "change ratio {:.2%} exceeds safety limit {:.2%}; "
            "review and rerun with --allow-large-change"
            .format(ratio, args.max_change_ratio)
        )

    content = render(rules)
    current = args.output.read_text(encoding="utf-8") if args.output.exists() else ""
    if content == current:
        print("[ok] {} is already up to date".format(args.output))
        return 0
    if args.dry_run:
        print("[dry-run] {} would be updated".format(args.output))
        return 0
    atomic_write(args.output, content)
    print("[write] updated {}".format(args.output))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print("[error] {}".format(exc), file=sys.stderr)
        sys.exit(1)
