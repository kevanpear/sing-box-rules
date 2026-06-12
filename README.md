# sing-box-rules

自维护的 sing-box 域名规则集(替代之前托管在 Seafile 网盘、会 302 跳转导致下载失败的方案）。

## 结构

| 目录 | 内容 | 说明 |
|------|------|------|
| `source/*.json` | 规则**源码**（域名列表） | **要改规则改这里** |
| `srs/*.srs` | 编译后的二进制 | sing-box 实际加载的；由 CI 自动生成，勿手改 |
| `.github/workflows/compile.yml` | GitHub Action | push `source/` 后自动把 json 编译成 srs 并提交 |

## 如何维护规则

1. 编辑 `source/<name>.json`，增删 `domain` / `domain_suffix` / `domain_keyword` 条目。
2. `git commit && git push`。
3. GitHub Action 自动重新编译 `srs/<name>.srs`，几十秒后生效。
4. 客户端下次刷新规则集（默认按 `update_interval`）即拉到新版本。

本地也可手动编译验证：
```bash
sing-box rule-set compile source/geosite_openai.json -o srs/geosite_openai.srs
```

## 本地更新（手动，按需）

域名很少变，不设定时器。改完规则 push 后（或想拉取最新时），在本机跑一次：
```bash
~/sing-box-rules/sync-local.sh
```
脚本会：经代理 `git fetch` → 若有更新则把 `srs/*.srs` 同步到 `/var/lib/sing-box/`
→ 仅当文件确有变化时 `systemctl restart sing-box`。无变化时是 no-op。

## 客户端引用方式（sing-box 配置 route.rule_set）

本仓库是**私有**的，而 sing-box 远程规则集只支持 `url/download_detour/update_interval`、**不支持认证头**，
所以无法让 sing-box 直接拉私有 raw。改为「本机 `sync-local.sh` 拉取 → sing-box 按 `local` 加载」：

```json
{
  "type": "local",
  "tag": "geosite_openai",
  "format": "binary",
  "path": "/var/lib/sing-box/geosite_openai.srs"
}
```

更新由 `sync-local.sh` 负责（见下）。这样规则全程私有、不受 GFW 对 GitHub raw 的干扰。

## 规则集清单

- `geosite_direct` — 直连域名
- `geosite_proxy` — 走代理域名
- `geosite_openai` — OpenAI / Gemini 及相关 CDN
- `geosite_youtube` `geosite_spotify` — 流媒体/音乐
- `geosite_netflix` `geosite_disney` `geosite_primevideo` `geosite_hbo` — 影视
