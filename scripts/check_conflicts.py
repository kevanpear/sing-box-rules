#!/usr/bin/env python3
"""跨规则集冲突检查。

直连大盘 geosite_direct 与走代理的规则集之间，若同一个 domain /
domain_suffix 两边都有，路由结果就取决于规则顺序，容易出诡异 bug。
默认只告警；CI 用 --strict 把重叠视为失败。

只检查【代理语义】的规则集。直连语义的小列表（geosite_win_update 等）
geosite_win_update 等）与 direct 重叠是天经地义的 —— 它们本来就是
direct 的子集，拆出来只为能单独调度；拦截语义的 geosite_win_spy /
geosite_win_spy 命中即断，压过直连也是期望行为。这份名单见
rulesets.NON_PROXY。

IP 规则集（geoip_*）不做域名重叠检查，前缀不同天然跳过。

用法: python3 scripts/check_conflicts.py [--strict]
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rulesets as R


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strict", action="store_true",
                        help="发现重叠时返回非零状态")
    return parser.parse_args()


def main():
    args = parse_args()
    direct_path = R.SRC / "{}.json".format(R.DIRECT)
    if not direct_path.exists():
        print("[skip] 找不到 {}".format(direct_path))
        return 0

    direct_terms = R.load_terms(direct_path)
    total = 0
    for path in R.proxy_rulesets():
        overlap = direct_terms & R.load_terms(path)
        if overlap:
            total += len(overlap)
            print("::warning::{} 与 {} 重叠 {} 个域名: ".format(
                R.DIRECT, path.stem, len(overlap))
                + ", ".join(sorted(overlap)[:20])
                + (" ..." if len(overlap) > 20 else ""))

    skipped = sorted(R.NON_PROXY - {R.DIRECT})
    print("[info] 已跳过 {} 个非代理语义规则集: {}".format(len(skipped), ", ".join(skipped)))
    if total == 0:
        print("[ok] 无跨表域名冲突")
    else:
        print("[warn] 共发现 {} 处直连/代理重叠 —— 请确认路由顺序符合预期".format(total))
    return 1 if total and args.strict else 0


if __name__ == "__main__":
    sys.exit(main())
