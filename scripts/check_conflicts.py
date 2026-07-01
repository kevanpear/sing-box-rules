#!/usr/bin/env python3
"""跨规则集冲突检查。

直连大盘 geosite_direct 与所有走代理的规则集之间，若出现同一个
domain / domain_suffix 同时被列入，路由结果会依赖规则顺序，容易出诡异
bug。默认只告警；CI 使用 --strict 将重叠视为失败。

用法: python3 scripts/check_conflicts.py [--strict]
"""
import argparse
import json
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "source"
DIRECT = "geosite_direct"


def load_terms(path: Path):
    """返回该规则集里的精确域名集合 (domain + domain_suffix)。"""
    data = json.loads(path.read_text(encoding="utf-8"))
    terms = set()
    for rule in data.get("rules", []):
        for key in ("domain", "domain_suffix"):
            v = rule.get(key)
            if isinstance(v, str):
                terms.add(v)
            elif isinstance(v, list):
                terms.update(v)
    return terms


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--strict",
        action="store_true",
        help="return a non-zero status when conflicts are found",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    files = sorted(SRC.glob("geosite_*.json"))
    direct_path = SRC / f"{DIRECT}.json"
    if not direct_path.exists():
        print(f"[skip] 找不到 {direct_path}")
        return 0

    direct_terms = load_terms(direct_path)
    total = 0
    for f in files:
        name = f.stem
        if name == DIRECT:
            continue
        overlap = direct_terms & load_terms(f)
        if overlap:
            total += len(overlap)
            print(f"::warning::{DIRECT} 与 {name} 重叠 {len(overlap)} 个域名: "
                  + ", ".join(sorted(overlap)[:20])
                  + (" ..." if len(overlap) > 20 else ""))

    if total == 0:
        print("[ok] 无跨表域名冲突")
    else:
        print(f"[warn] 共发现 {total} 处直连/代理重叠 —— 请确认路由顺序符合预期")
    return 1 if total and args.strict else 0


if __name__ == "__main__":
    sys.exit(main())
