#!/usr/bin/env python3
"""规则集的共用定义与读写。

被 check_conflicts.py / update_direct_from_upstream.py /
update_upstream_lists.py 共用，避免三份重复实现。
"""
import json
import os
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "source"

FIELDS = ("domain", "domain_suffix", "domain_keyword", "domain_regex")
DIRECT = "geosite_direct"

# 非代理类规则集 —— 不参与 geosite_direct 的直连/代理冲突检查。
#
# 默认所有 geosite_* 都当作代理类来查（新增代理规则集时自动纳入检查，
# 忘了登记也不会漏检）；只有确实不是代理语义的才列在这里。
NON_PROXY = frozenset({
    DIRECT,               # 直连大盘本身
    "geosite_apple_cn",   # 直连：国内可直连的 Apple 域名
    "geosite_google_cn",  # 直连：国内可直连的 Google 域名
    "geosite_win_update",  # 直连：Windows 更新，走代理纯属浪费流量
    "geosite_win_spy",    # 拦截：Windows 遥测，命中即断，压过直连是期望行为
    "geosite_win_extra",  # 拦截：同上
})

# 直连语义的小列表：生成时要剔除代理类规则集已有的条目，
# 否则会把有意让其走代理的域名（如 ChatGPT 用的 Apple 登录）拉回直连。
DIRECT_LIKE = frozenset({
    "geosite_apple_cn",
    "geosite_google_cn",
    "geosite_win_update",
})


def load_rules(path):
    """读成 {field: set()}；文件不存在时返回空集合。"""
    out = {field: set() for field in FIELDS}
    if not Path(path).exists():
        return out
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    for rule in data.get("rules", []):
        for field in FIELDS:
            values = rule.get(field, [])
            if isinstance(values, str):
                values = [values]
            out[field].update(values)
    return out


def load_terms(path):
    """该规则集里的精确域名集合（domain + domain_suffix），小写。"""
    rules = load_rules(path)
    return {v.lower() for v in rules["domain"] | rules["domain_suffix"]}


def proxy_rulesets():
    """所有代理语义的规则集路径。"""
    return [p for p in sorted(SRC.glob("geosite_*.json")) if p.stem not in NON_PROXY]


def proxy_terms():
    """所有代理类规则集的精确域名并集。"""
    terms = set()
    for path in proxy_rulesets():
        terms |= load_terms(path)
    return terms


def fine_proxy_rulesets():
    """精细维护的代理规则集 —— 不含 geosite_proxy 大盘。

    大盘是 GFWList 每天自动转换出来的，粒度粗且会误收（windowsupdate.com
    就在里面）。只有人工维护的细分策略才有权压过直连列表；拿大盘去剔除
    直连条目，会把 Windows 更新这类该直连的域名一并剔掉。
    """
    return [p for p in proxy_rulesets() if p.stem != "geosite_proxy"]


def fine_proxy_terms():
    terms = set()
    for path in fine_proxy_rulesets():
        terms |= load_terms(path)
    return terms


def direct_like_terms():
    """所有直连语义规则集的精确域名并集 —— 供 proxy 大盘生成时让路。"""
    terms = set()
    for name in sorted({DIRECT} | DIRECT_LIKE):
        terms |= load_terms(SRC / "{}.json".format(name))
    return terms


def parse_domain_list(text):
    """解析 v2ray 风格的纯文本域名列表 → {field: set()}。

    裸域名 → domain_suffix（v2ray 的 domain: 语义就是后缀匹配）
    full:  → domain（精确）
    regexp:→ domain_regex
    keyword:→ domain_keyword
    """
    out = {field: set() for field in FIELDS}
    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        line = line.split()[0]          # 去掉 " @attr" 之类的尾随属性
        if line.startswith("full:"):
            out["domain"].add(_clean(line[5:], number))
        elif line.startswith("regexp:"):
            expression = line[7:]
            if not expression:
                raise ValueError("第 {} 行是空正则".format(number))
            out["domain_regex"].add(expression)
        elif line.startswith("keyword:"):
            out["domain_keyword"].add(line[8:])
        elif line.startswith("domain:"):
            out["domain_suffix"].add(_clean(line[7:], number))
        elif ":" in line:
            raise ValueError("第 {} 行有未知前缀: {!r}".format(number, line))
        else:
            out["domain_suffix"].add(_clean(line, number))
    return out


def _clean(value, number):
    value = value.strip().lower().rstrip(".")
    if not value or any(c.isspace() for c in value) or any(c in value for c in "/|^"):
        raise ValueError("第 {} 行不是合法域名: {!r}".format(number, value))
    return value


def fetch(urls):
    """按顺序尝试下载，全失败才报错。"""
    errors = []
    for url in urls:
        if not url:
            continue
        request = urllib.request.Request(url, headers={
            "Accept": "text/plain",
            "User-Agent": "sing-box-rules-sync/1.0",
        })
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                body = response.read()
            if len(body) < 100:
                raise ValueError("响应异常小: {} 字节".format(len(body)))
            print("[fetch] {} ({} 字节)".format(url, len(body)))
            return body.decode("utf-8")
        except (OSError, ValueError, urllib.error.URLError) as exc:
            errors.append("{}: {}".format(url, exc))
    raise RuntimeError("上游全部下载失败:\n  " + "\n  ".join(errors))


def report_delta(old, new):
    """打印逐字段与总量变化，返回 (旧总数, 新总数, 变动比例)。"""
    additions = removals = 0
    for field in FIELDS:
        added = len(new[field] - old[field])
        removed = len(old[field] - new[field])
        additions += added
        removals += removed
        if old[field] or new[field]:
            print("[delta] {:14s} old={:6d} new={:6d} add={:5d} remove={:5d}"
                  .format(field, len(old[field]), len(new[field]), added, removed))
    old_total = sum(len(old[f]) for f in FIELDS)
    new_total = sum(len(new[f]) for f in FIELDS)
    ratio = (additions + removals) / max(old_total, 1)
    print("[delta] total old={} new={} add={} remove={} ratio={:.2%}"
          .format(old_total, new_total, additions, removals, ratio))
    return old_total, new_total, ratio


def render(rules):
    rule = {f: sorted(rules[f]) for f in FIELDS if rules[f]}
    return json.dumps({"version": 1, "rules": [rule]},
                      ensure_ascii=False, indent=2) + "\n"


def atomic_write(path, content):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        prefix=path.name + ".", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
        os.replace(temporary, str(path))
    except Exception:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def write_if_changed(path, rules, dry_run):
    """内容无变化返回 False；dry-run 只报告不落盘。"""
    content = render(rules)
    path = Path(path)
    current = path.read_text(encoding="utf-8") if path.exists() else ""
    if content == current:
        print("[ok] {} 已是最新".format(path))
        return False
    if dry_run:
        print("[dry-run] {} 会被更新".format(path))
        return False
    atomic_write(path, content)
    print("[write] 已更新 {}".format(path))
    return True


def guard(new_total, ratio, minimum, max_ratio, allow_large, first_time):
    """安全阈值：规则数下限 + 变动比例上限。首次生成没有"变动"可言，跳过比例检查。"""
    if new_total < minimum:
        raise RuntimeError("生成的规则数 {} 低于安全下限 {}".format(new_total, minimum))
    if first_time:
        print("[init] 首次生成，跳过变动比例检查")
        return
    if ratio > max_ratio and not allow_large:
        raise RuntimeError(
            "变动比例 {:.2%} 超过安全上限 {:.2%}；人工核对后加 --allow-large-change 重跑"
            .format(ratio, max_ratio))
