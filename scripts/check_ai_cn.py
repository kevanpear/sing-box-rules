#!/usr/bin/env python3.11
"""Validate the China AI direct list and export/check its Clash source mirror."""
import argparse
import ipaddress
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "source/geosite_ai_cn.json"
PROTECTED = (
    "anthropic.com", "claude.ai", "claude.com", "claude.app", "clau.de",
    "claudeusercontent.com", "openai.com", "chatgpt.com", "oaistatic.com",
    "oaiusercontent.com", "google.com", "googleapis.com", "gstatic.com",
    "github.com", "githubusercontent.com",
)
SHARED = {
    "com", "cn", "ai", "net", "org", "com.cn", "co", "io", "app",
    "aliyuncs.com", "volces.com", "volcengine.com", "byteimg.com",
    "bytedance.com", "mi.com", "xiaomi.com", "mi-img.com",
}


def matches(host, domain, suffix=False):
    return host == domain or (suffix and host.endswith("." + domain))


def load_ruleset(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict) or set(data) != {"version", "rules"} or type(data["version"]) is not int or data["version"] not in (1, 3):
        raise ValueError("expected a version 1 or 3 native source rule-set")
    if not isinstance(data["rules"], list) or not data["rules"]:
        raise ValueError("rules must be a nonempty list")
    entries, rules = [], []
    for index, source in enumerate(data["rules"]):
        if not isinstance(source, dict) or not source or set(source) - {"domain", "domain_suffix"}:
            raise ValueError(f"rule {index}: only exact domains and suffixes are allowed")
        rule = {}
        for kind in ("domain", "domain_suffix"):
            if kind not in source:
                continue
            values = source[kind]
            if not isinstance(values, list) or not values:
                raise ValueError(f"rule {index}: {kind} must be a nonempty list")
            for host in values:
                if not isinstance(host, str) or len(host) > 253 or not re.fullmatch(
                    r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
                    r"(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+", host
                ):
                    raise ValueError(f"rule {index}: expected lowercase DNS name, no wildcard/URL")
                try:
                    ipaddress.ip_address(host)
                except ValueError:
                    pass
                else:
                    raise ValueError(f"rule {index}: IP literals are forbidden")
                if host in SHARED or any(
                    matches(host, protected, True) or matches(protected, host, kind == "domain_suffix")
                    for protected in PROTECTED
                ):
                    raise ValueError(f"unsafe broad or protected domain: {host}")
                entries.append((host, kind == "domain_suffix"))
            rule[kind] = sorted(values)
        rules.append(rule)
    for i, (host, suffix) in enumerate(entries):
        for other, other_suffix in entries[:i]:
            if matches(host, other, other_suffix) or matches(other, host, suffix):
                raise ValueError(f"duplicate/overlapping domains: {host}, {other}")
    return {"version": data["version"], "rules": rules}


def clash_source(data):
    lines = [
        "# 中国 AI 服务直连分组；出站与 DNS 策略由客户端配置决定。",
        "# 从 sing-box-rules/source/geosite_ai_cn.json 生成，请在该文件维护域名。",
        "# 生成：python3.11 scripts/check_ai_cn.py --write-clash <本文件路径>",
        "payload:",
    ]
    for field, kind in (("domain", "DOMAIN"), ("domain_suffix", "DOMAIN-SUFFIX")):
        terms = sorted(host for rule in data["rules"] for host in rule.get(field, []))
        lines.extend(f"  - '{kind},{host}'" for host in terms)
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=SOURCE)
    mirrors = parser.add_mutually_exclusive_group()
    mirrors.add_argument("--write-clash", type=Path)
    mirrors.add_argument("--check-clash", type=Path)
    args = parser.parse_args()
    try:
        data = load_ruleset(args.source)
        if args.write_clash:
            args.write_clash.write_text(clash_source(data), encoding="utf-8")
        if args.check_clash and args.check_clash.read_text(encoding="utf-8") != clash_source(data):
            raise ValueError("Clash source mirror is stale; regenerate it with --write-clash")
    except (OSError, ValueError, TypeError) as exc:
        parser.exit(1, f"china-ai: {exc}\n")
    count = sum(len(values) for rule in data["rules"] for values in rule.values())
    print(f"[ok] geosite_ai_cn: {count} exact/suffix entries")


if __name__ == "__main__":
    main()
