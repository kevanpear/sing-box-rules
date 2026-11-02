# sing-box-rules

自维护的 sing-box 域名规则集(替代之前托管在 Seafile 网盘、会 302 跳转导致下载失败的方案）。

## 结构

| 目录 | 内容 | 说明 |
|------|------|------|
| `source/*.json` | 规则**源码**（域名列表） | **要改规则改这里** |
| `srs/*.srs` | 编译后的二进制 | sing-box 实际加载的；由 CI 自动生成，勿手改 |
| `scripts/rulesets.py` | 共用模块 | 规则集分类（代理 / 直连 / 拦截）、上游列表解析、原子写入、安全阈值 |
| `scripts/check_conflicts.py` | 冲突检查 | 只查 `geosite_direct` 与**代理语义**规则集的重叠；直连/拦截语义的按 `rulesets.NON_PROXY` 跳过 |
| `scripts/check_ai_cn.py` | 中国 AI 清单检查与镜像 | 验证独立直连组边界，生成／检查 Clash classical 镜像 |
| `scripts/update_direct_from_upstream.py` | 直连大盘同步 | Loyalsoldier `direct-list.txt` → `geosite_direct`，剔除精细代理规则集已有域名 |
| `scripts/update_upstream_lists.py` | 小列表同步 | apple-cn / google-cn / win-update / win-spy / win-extra 五个规则集 |
| `scripts/update_geoip_cn.py` | 中国大陆 IP 段同步 | 拉取 IPv4/IPv6 CIDR 生成 `source/geoip_cn.json`，内置 5% 变动阈值 |
| `scripts/update_proxy_from_gfwlist.py` | GFWList 转换 | Base64 AutoProxy → sing-box JSON，并排除所有直连语义规则集已有域名 |
| `.github/workflows/compile.yml` | GitHub Action | push `source/` 自动编译 srs 并提交；PR 只校验（JSON 语法 + 编译 + 冲突）不提交 |
| `.github/workflows/sync-upstream.yml` | GitHub Action | **上游同步的唯一定时入口**，每日按序跑 direct → 小列表 → proxy |
| `.github/workflows/sync-proxy.yml` | GitHub Action | 仅手动，单独重跑 GFWList 同步 |
| `.github/workflows/sync-geoip.yml` | GitHub Action | 仅手动，刷新 `geoip_cn` |

## 如何维护规则

1. 编辑 `source/<name>.json`，增删 `domain` / `domain_suffix` / `domain_keyword` 条目。
2. `git commit && git push`。
3. GitHub Action 自动重新编译 `srs/<name>.srs`，几十秒后生效。
4. 客户端下次刷新规则集（默认按 `update_interval`）即拉到新版本。

本地也可手动编译验证：
```bash
sing-box rule-set compile source/geosite_openai.json -o srs/geosite_openai.srs
```

## geosite_proxy 自动同步

`geosite_proxy` 由
`YW5vbnltb3Vz/domain-list-community` 的 release 分支 `gfwlist.txt`
自动转换。GitHub Actions 每天 02:20 UTC 检查一次：

1. 下载并严格解码 Base64 AutoProxy 列表；
2. 转换 `domain` / `full` / `keyword` / `regexp` 规则；
3. 去重、排序，并排除 `geosite_direct` 已存在的精确条目；
4. 执行 JSON、跨表冲突和 sing-box 编译校验；
5. 仅在规则变化时提交 `source/geosite_proxy.json` 与对应 SRS。

默认安全阈值为 5%。若单次增删总量超过旧规则数的 5%，工作流会失败，
必须人工审核后通过 `workflow_dispatch` 勾选 `allow_large_change` 才能发布。

本地预览：

```bash
python3 scripts/update_proxy_from_gfwlist.py --dry-run
```

## 更新流程（公开+远程方案）

改完 `source/*.json` → push → GitHub Action 自动编译出新 `srs/*.srs` →
客户端按 `update_interval`（默认 1d）自动拉取。整个过程无需在本机手动操作。

## 客户端引用方式（sing-box 配置 route.rule_set）

本仓库为 **public**，sing-box 可直接远程拉取 raw（免鉴权）：

```json
{
  "type": "remote",
  "tag": "geosite_openai",
  "format": "binary",
  "url": "https://raw.githubusercontent.com/kevanpear/sing-box-rules/master/srs/geosite_openai.srs",
  "download_detour": "proxy",
  "update_interval": "1d"
}
```

- `download_detour: proxy` — 经代理出口下载，绕开 GFW 对 `raw.githubusercontent.com` 的干扰。
- 建议同时启用 `experimental.cache_file`，规则集会持久化，某次下载失败也不会导致启动失败。

push 新规则后，客户端按 `update_interval` 自动更新，**无需手动操作**。

## 规则集清单

- `geosite_direct` — 直连域名
- `geosite_proxy` — 走代理域名
- `geosite_openai` — OpenAI 及相关 CDN
- `geosite_google` — v2fly `domain-list-community/data/google` 转换的完整 Google 域名集（排除 `@cn`）
- `geosite_google-gemini` — Google Gemini 所需域名
- `geosite_claude` — Anthropic / Claude 全量兼容规则集
- `geosite_claude_dns` — 当前由解锁 DNS 覆盖的 Anthropic / Claude 域名
- `geosite_claude_warp` — 当前未被解锁 DNS 覆盖、用于 WARP 兜底的 Claude 域名
- `geosite_youtube` `geosite_spotify` `geosite_tiktok` — 流媒体/音乐/短视频
- `geosite_netflix` `geosite_disney` `geosite_primevideo` `geosite_hbo` — 影视
- `geosite_playstation` — PlayStation / Sony 账号登录及风控域名
- `geoip_cn` — **中国大陆 IP 段（IPv4 + IPv6）**，唯一的非域名规则集

直连语义（可与`geosite_direct`重叠，独立列出以便单独调度）：

- `geosite_win_update` — Windows 更新域名（538 条），动辄几 GB，不该吃代理流量
- `geosite_ai_cn` — 中国 AI 服务域名，适合在全局代理兜底前单独直连；不改直连大盘或国外 AI 分组

拦截语义（命中即断，需要客户端配一条 `action: reject`）：

- `geosite_win_spy` — Windows 遥测域名（347 条）

### geoip_cn 为什么必要

其余规则集全是 geosite（域名匹配）。但**不带域名、直接以 IP 发起的连接**
（游戏、P2P、部分 App 的直连 API）匹配不到任何 geosite 规则，会一路落到
路由表的 `final`。若 `final` 是代理，国内 IP 的流量就会绕道境外——
在只服务本机的场景不明显，一旦用作**全网透明代理（旁路由）**就会被放大。

用法：放在所有域名规则之后、`final` 之前，命中即 `direct`。

```json
{ "rule_set": ["geoip_cn"], "outbound": "direct" }
```

命名用 `geoip_` 而非 `geosite_` 前缀是有意的：`check_conflicts.py` 只扫描
`geosite_*.json` 做域名重叠检查，IP 规则集不适用该检查，换前缀即天然跳过。

更新：`python3 scripts/update_geoip_cn.py`
（数据源 17mon/china_ip_list 与 gaoyifan/china-operator-ip；网络能直连
`raw.githubusercontent.com` 时不需要 `--proxy`）

## 上游同步（Loyalsoldier/v2ray-rules-dat）

`geosite_direct` 最初就是从该仓库的 `direct-list.txt` 一次性导入的，但此前
没有同步机制。现在由 `sync-upstream.yml` 每日跑，三步**必须按序**：

1. `update_direct_from_upstream.py` — 直连大盘，是后两步的剔除基准
2. `update_upstream_lists.py` — 五个小列表，剔除**精细代理规则集**已有域名
3. `update_proxy_from_gfwlist.py` — 反过来剔除所有**直连语义**规则集已有域名

顺序颠倒会留下 direct/proxy 重叠，末尾 `check_conflicts.py --strict` 会失败。

### 谁压过谁

- **精细代理规则集**（`geosite_openai` 等人工维护的）压过直连列表。
  例：`itunes.apple.com` 有意留在 `geosite_openai` 里走代理（ChatGPT 的
  Apple 登录），所以它会被从 `geosite_direct` 里剔除。
  2026-07-01 的 21f3422 手工做的就是这件事，现在自动化了。
- **`geosite_proxy` 大盘不压过任何直连列表**。GFWList 粒度粗且会误收
  —— `windowsupdate.com` 就在里面。拿大盘去剔除直连条目，会把该直连的
  Windows 更新一并剔掉。

### 安全阈值

`geosite_direct` 5%、小列表 15%，超限即失败，需人工核对后
`workflow_dispatch` 勾 `allow_large_change`。首次生成（文件还不存在）
没有"变动"可言，自动跳过比例检查。

## 路由顺序建议

规则按顺序匹配，先命中先生效。上面这些规则集的推荐排法：

```json
"rules": [
  { "rule_set": ["geosite_reject"], "action": "reject" },
  { "rule_set": ["geosite_ai_cn"], "outbound": "direct" },
  { "rule_set": ["geosite_win_update"], "outbound": "direct" },
  { "rule_set": ["geosite_openai", "geosite_claude", "geosite_google"], "outbound": "proxy" },
  { "rule_set": ["geosite_direct"], "outbound": "direct" },
  { "rule_set": ["geosite_proxy"], "outbound": "proxy" },
  { "rule_set": ["geoip_cn"], "outbound": "direct" }
]
```

拦截类放最前（命中即断），直连小列表次之（它们是 `geosite_direct` 的子集，
放前面才有单独调度的意义），精细代理规则集再次之，两个大盘垫底，
`geoip_cn` 在 `final` 之前兜底。

## 中国 AI 服务分组

唯一域名编辑点：`source/geosite_ai_cn.json`。使用原生规则集格式，不另建第二份厂商目录。四个规则块依次对应下表；当前共14条精确／后缀条目：

| 厂商 | 覆盖范围 | 资料 |
|---|---|---|
| DeepSeek | deepseek.com、deepseeksvc.com，含API、聊天网页和文件服务 | [官方API文档](https://api-docs.deepseek.com/)、[官方聊天网页](https://chat.deepseek.com/)加载的[前端脚本](https://fe-static.deepseek.com/chat/static/main.d1d163b7e4.js)明确使用 files.deepseeksvc.com |
| 火山方舟 | 精确ark.cn-beijing.volces.com；通过方舟调用的GLM、DeepSeek、Kimi、豆包、MiniMax共用该主机 | [官方Coding Plan文档](https://console.volcengine.com/ark/region%3Acn-beijing/docs/coding-plan-personal-get-started) |
| Kimi／Moonshot | kimi.com、kimi.ai、moonshot.cn、moonshot.ai，含API、OAuth、更新、CDN和远程控制 | [官方文档](https://www.kimi.com/code/docs/en/)、[地区端点源码](https://github.com/MoonshotAI/kimi-code/blob/main/packages/oauth/src/region.ts)、[开放平台源码](https://github.com/MoonshotAI/kimi-code/blob/main/packages/oauth/src/open-platform.ts) |
| 小米MiMo | xiaomimimo.com、mimo.mi.com、mimo.xiaomi.com；账号、隐私与已核实资源只列精确主机 | [官方API文档](https://mimo.mi.com/docs/zh-CN/quick-start/summary/first-api-call)、[官网](https://mimo.xiaomi.com/) |

直连表示使用客户端配置的本地出口，不保证服务端地理位置。规则只提供匹配范围，DNS、出站、来源条件及广告拒绝顺序由设备配置决定；需要直连时，DNS和数据规则均引用本组，并放在全局兜底前。Kimi国内／国际主机都覆盖，但不修改客户端的区域或Base URL。模型访问的任意网页、MCP、GitHub不会因此一起直连。

该组登记为`NON_PROXY`和`DIRECT_LIKE`，不会被误当代理类从直连大盘剔除；GFWList同步也会排除其精确条目。与`geosite_direct`重叠是正常现象，无需把这些域名搬出大盘。新增时核实域名归属，不加入IP、关键词、正则或宽泛共享云父域。

```sh
python3.11 scripts/check_ai_cn.py
python3.11 -m unittest discover -s tests -p 'test_ai_cn.py'
# 在本项目运行，机械生成姊妹仓库镜像；只改本项目的source源文件。
python3.11 scripts/check_ai_cn.py --write-clash ../clash-rules/source/geosite_ai_cn.yaml
python3.11 scripts/check_ai_cn.py --check-clash ../clash-rules/source/geosite_ai_cn.yaml
```

检查器拦截重复／重叠、部分常见共享父域和受保护的国外AI域名；不代替新增厂商的归属审查。push后由CI生成SRS，Clash按自己的CI生成YAML／MRS，本地编译验证放临时目录、不提交产物。设备若使用受保护的本地副本，须按其投放流程同步，发布共享仓库不会自动改写它。
