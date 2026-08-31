#!/usr/bin/env python3
"""同步 Loyalsoldier/v2ray-rules-dat 的几个小规则集。

这些列表都很小（几百条），但各自解决一个具体问题：

  geosite_apple_cn    国内可直连的 Apple 域名 —— 走代理纯属绕远
  geosite_google_cn   国内可直连的 Google 域名（google.cn 等）
  geosite_win_update  Windows 更新域名 —— 动辄几个 GB，不该吃代理流量
  geosite_win_spy     Windows 遥测域名 —— 用于拦截
  geosite_win_extra   Windows 附加遥测域名 —— 用于拦截
  geosite_reject      广告/追踪域名（上游 reject-list）—— 用于拦截

直连语义的三个（见 rulesets.DIRECT_LIKE）会剔除【精细代理规则集】已有的域名，
否则会把有意让其走代理的域名拉回直连 —— 典型例子是 geosite_openai 里的
Apple 登录域名，apple-cn 若不剔除就会盖掉它。

拦截语义的两个（win_spy / win_extra）不做剔除：命中即断，压过直连是期望行为。

用法:
  python3 scripts/update_upstream_lists.py [--only geosite_apple_cn] [--dry-run]
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rulesets as R

BASE_RAW = "https://raw.githubusercontent.com/Loyalsoldier/v2ray-rules-dat/release"
BASE_CDN = "https://fastly.jsdelivr.net/gh/Loyalsoldier/v2ray-rules-dat@release"

# 规则集名 -> (上游文件名, 生成结果的规则数下限)
LISTS = {
    "geosite_apple_cn":   ("apple-cn", 100),
    "geosite_google_cn":  ("google-cn", 50),
    "geosite_win_update": ("win-update", 300),
    "geosite_win_spy":    ("win-spy", 200),
    "geosite_win_extra":  ("win-extra", 200),
    # 去广告：上游 reject-list 约 18.8 万条，下限取 10 万——低于此值几乎肯定是
    # 上游异常（文件截断/为空），宁可同步失败也不要发布一个残缺的拦截清单。
    "geosite_reject":     ("reject-list", 100000),
}


def parse_args():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--only", action="append", choices=sorted(LISTS),
                   help="只同步指定规则集（可重复）")
    p.add_argument("--max-change-ratio", type=float, default=0.15,
                   help="(新增+移除)/旧规则数 的上限（默认 0.15，小列表波动天然偏大）")
    p.add_argument("--allow-large-change", action="store_true")
    p.add_argument("--dry-run", action="store_true", help="只预览，不写文件")
    return p.parse_args()


def sync(name, upstream, minimum, args):
    print("\n=== {} <- {}.txt ===".format(name, upstream))
    text = R.fetch(["{}/{}.txt".format(BASE_RAW, upstream),
                    "{}/{}.txt".format(BASE_CDN, upstream)])
    rules = R.parse_domain_list(text)

    if name in R.DIRECT_LIKE:
        reserved = R.fine_proxy_terms()
        removed = set()
        for field in ("domain", "domain_suffix"):
            hit = {v for v in rules[field] if v.lower() in reserved}
            removed |= hit
            rules[field] -= hit
        print("[filter] 剔除 {} 条已归属精细代理规则集的域名: {}".format(
            len(removed), ", ".join(sorted(removed)) or "(无)"))

    output = R.SRC / "{}.json".format(name)
    first_time = not output.exists()
    old = R.load_rules(output)
    _, new_total, ratio = R.report_delta(old, rules)
    R.guard(new_total, ratio, minimum,
            args.max_change_ratio, args.allow_large_change, first_time)
    return R.write_if_changed(output, rules, args.dry_run)


def main():
    args = parse_args()
    targets = args.only or sorted(LISTS)
    changed = []
    for name in targets:
        upstream, minimum = LISTS[name]
        if sync(name, upstream, minimum, args):
            changed.append(name)
    print("\n[done] 有变化的规则集: {}".format(", ".join(changed) or "(无)"))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print("[error] {}".format(exc), file=sys.stderr)
        sys.exit(1)
