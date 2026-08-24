#!/usr/bin/env python3
"""同步 geosite_direct（国内直连大盘）。

上游是 Loyalsoldier/v2ray-rules-dat 的 direct-list.txt —— 本仓库的
geosite_direct 最初就是从它一次性导入的（见初始提交），但此前没有同步
机制，导入后就再没跟进过。这个脚本把它接上。

会剔除【精细代理规则集】里已有的域名（geosite_openai / geosite_google /
geosite_tiktok 等），因为那些是精心维护的策略，直连大盘必须让路。
2026-07-01 的 21f3422 手工删掉 3 条 Apple 域名做的就是这件事，这里自动化了。

不剔除 geosite_proxy 大盘的域名：方向反过来 —— proxy 每天重新生成时
会自行排除 direct 已有条目（见 update_proxy_from_gfwlist.py），两边
互相剔除会打架。

用法:
  python3 scripts/update_direct_from_upstream.py [--dry-run] [--allow-large-change]
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rulesets as R

PRIMARY_URL = ("https://raw.githubusercontent.com/Loyalsoldier/"
               "v2ray-rules-dat/release/direct-list.txt")
FALLBACK_URL = ("https://fastly.jsdelivr.net/gh/Loyalsoldier/"
                "v2ray-rules-dat@release/direct-list.txt")


def parse_args():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source", default=PRIMARY_URL)
    p.add_argument("--fallback", default=FALLBACK_URL)
    p.add_argument("--output", type=Path, default=R.SRC / "geosite_direct.json")
    p.add_argument("--max-change-ratio", type=float, default=0.05,
                   help="(新增+移除)/旧规则数 的上限（默认 0.05）")
    p.add_argument("--minimum-rules", type=int, default=50_000,
                   help="生成结果小于此数即判定上游异常（默认 50000）")
    p.add_argument("--allow-large-change", action="store_true",
                   help="接受超过 --max-change-ratio 的变动")
    p.add_argument("--dry-run", action="store_true", help="只预览，不写文件")
    return p.parse_args()


def main():
    args = parse_args()
    rules = R.parse_domain_list(R.fetch([args.source, args.fallback]))

    # 精细代理规则集优先：直连大盘让路
    reserved = R.fine_proxy_terms()
    before = len(rules["domain"]) + len(rules["domain_suffix"])
    removed = set()
    for field in ("domain", "domain_suffix"):
        hit = {v for v in rules[field] if v.lower() in reserved}
        removed |= hit
        rules[field] -= hit
    after = len(rules["domain"]) + len(rules["domain_suffix"])
    print("[filter] 剔除 {} 条已归属精细代理规则集的域名: {}".format(
        before - after, ", ".join(sorted(removed)) or "(无)"))

    old = R.load_rules(args.output)
    first_time = not Path(args.output).exists()
    _, new_total, ratio = R.report_delta(old, rules)
    R.guard(new_total, ratio, args.minimum_rules,
            args.max_change_ratio, args.allow_large_change, first_time)
    R.write_if_changed(args.output, rules, args.dry_run)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print("[error] {}".format(exc), file=sys.stderr)
        sys.exit(1)
