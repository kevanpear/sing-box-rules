# sing-box-rules

自维护的 sing-box 域名规则集(替代之前托管在 Seafile 网盘、会 302 跳转导致下载失败的方案）。

## 结构

| 目录 | 内容 | 说明 |
|------|------|------|
| `source/*.json` | 规则**源码**（域名列表） | **要改规则改这里** |
| `srs/*.srs` | 编译后的二进制 | sing-box 实际加载的；由 CI 自动生成，勿手改 |
| `scripts/check_conflicts.py` | 冲突检查 | 检查 `geosite_direct` 与代理类规则集的同域名重叠 |
| `scripts/update_proxy_from_gfwlist.py` | GFWList 转换 | Base64 AutoProxy → sing-box JSON，并排除 direct 重叠 |
| `.github/workflows/compile.yml` | GitHub Action | push `source/` 自动编译 srs 并提交；PR 只校验（JSON 语法 + 编译 + 冲突）不提交 |
| `.github/workflows/sync-proxy.yml` | GitHub Action | 每日同步上游 GFWList，校验后提交 JSON 与 SRS |

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
- `geosite_google-gemini` — Google Gemini / NotebookLM / AI Studio 相关域名
- `geosite_claude` — Anthropic / Claude 及相关内容域名
- `geosite_youtube` `geosite_spotify` — 流媒体/音乐
- `geosite_netflix` `geosite_disney` `geosite_primevideo` `geosite_hbo` — 影视
- `geosite_playstation` — PlayStation / Sony 账号登录及风控域名
