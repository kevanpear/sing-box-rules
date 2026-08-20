#!/usr/bin/env python3
"""生成 geoip_cn 规则集（中国大陆 IPv4 + IPv6 段）。

为什么需要它：本仓库其余规则集全是 geosite（域名匹配），而**不带域名、
直接以 IP 发起的连接**（游戏、P2P、部分 App 的直连 API）匹配不到任何
geosite 规则，会落到路由表的 final 上。若 final 是代理，国内 IP 的流量
就会绕道境外。geoip_cn 用于在 final 之前兜底放行国内 IP。

命名用 geoip_ 而非 geosite_ 前缀：scripts/check_conflicts.py 只扫描
geosite_*.json（域名重叠检查），IP 规则集不适用该检查，改名即可天然跳过。

用法:
  python3 scripts/update_geoip_cn.py [--dry-run] [--proxy http://127.0.0.1:7890]
"""
import argparse
import ipaddress
import json
import sys
import urllib.request
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent / "source"
OUT = SRC / "geoip_cn.json"

SOURCES = [
    ("IPv4", "https://raw.githubusercontent.com/17mon/china_ip_list/master/china_ip_list.txt"),
    ("IPv6", "https://raw.githubusercontent.com/gaoyifan/china-operator-ip/ip-lists/china6.txt"),
]

# 单次变动超过旧规则数的这个比例即视为异常（与 update_proxy_from_gfwlist.py 同思路）
SAFE_RATIO = 0.05


def fetch(url, proxy):
    if proxy:
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
    else:
        opener = urllib.request.build_opener()
    with opener.open(url, timeout=60) as r:
        return r.read().decode("utf-8", "replace")


def parse_cidrs(text):
    """逐行解析并用 ipaddress 严格校验，丢弃非法条目。"""
    out = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            out.append(str(ipaddress.ip_network(line, strict=False)))
        except ValueError:
            print("  [skip] 非法 CIDR: %s" % line[:60], file=sys.stderr)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", help="只预览，不写文件")
    ap.add_argument("--proxy", default=None, help="下载用的 HTTP 代理")
    ap.add_argument("--allow-large-change", action="store_true",
                    help="允许超过安全阈值的变动")
    args = ap.parse_args()

    cidrs = []
    for name, url in SOURCES:
        print("下载 %s ..." % name)
        got = parse_cidrs(fetch(url, args.proxy))
        print("  %s: %d 条" % (name, len(got)))
        cidrs.extend(got)

    # 去重 + 排序（IPv4 在前、IPv6 在后，各自按网络地址序）
    uniq = sorted(set(cidrs),
                  key=lambda c: (ipaddress.ip_network(c).version,
                                 ipaddress.ip_network(c)))
    print("合计去重后: %d 条" % len(uniq))

    if not uniq:
        print("::error::解析结果为空，中止", file=sys.stderr)
        return 1

    old = 0
    if OUT.exists():
        try:
            prev = json.loads(OUT.read_text(encoding="utf-8"))
            old = sum(len(r.get("ip_cidr", [])) for r in prev.get("rules", []))
        except Exception:
            old = 0

    if old:
        delta = abs(len(uniq) - old)
        if delta > old * SAFE_RATIO and not args.allow_large_change:
            print("::error::变动 %d 条，超过旧规则数 %d 的 %.0f%% —— "
                  "请人工核对后用 --allow-large-change 发布"
                  % (delta, old, SAFE_RATIO * 100), file=sys.stderr)
            return 1
        print("与上一版相比变动 %d 条（旧 %d）" % (delta, old))

    data = {"version": 1, "rules": [{"ip_cidr": uniq}]}
    if args.dry_run:
        print("[dry-run] 不写入。前 3 条: %s" % uniq[:3])
        return 0

    OUT.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                   encoding="utf-8")
    print("已写入 %s（%d 条）" % (OUT, len(uniq)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
