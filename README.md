# API Status Monitor

一个轻量级的 API 可用性监测站，支持统一配置多个站点和多个模型，并自动生成静态监控页。

## 功能特性

- 统一配置多个站点和模型
- 每 10 分钟自动探测一次
- 记录 HTTP 状态、响应延迟、错误信息
- 展示全部目标的当前状态、最近 24 小时格子图、最近检测记录
- 纯静态页面，可部署到 GitHub Pages
- 兼容旧版单站点环境变量配置

## 项目结构

```text
api_status_monitor/
├── .github/workflows/status-check.yml
├── docs/
│   ├── index.html
│   ├── style.css
│   ├── app.js
│   └── data/
│       ├── status.json
│       └── history.json
├── scripts/check_api.py
├── monitor_daemon.py
├── .env.example
└── README.md
```

## 配置方式

### 推荐：统一配置多个站点和模型

在本地 `.env` 或 GitHub Actions Secret `MONITOR_TARGETS` 中配置一个 JSON 数组：

```json
[
  {
    "name": "OpenAI GPT-4o mini",
    "base_url": "https://api.openai.com/v1",
    "api_key": "sk-xxxxx",
    "model": "gpt-4o-mini"
  },
  {
    "name": "GLM 主站",
    "base_url": "https://example.com/v1",
    "api_key": "your_key",
    "model": "GLM-5.1"
  }
]
```

字段说明：

- `name`: 页面展示名称
- `base_url`: 接口基础地址
- `api_key`: 该目标自己的密钥
- `model`: 要探测的模型名
- `target_id`: 可选，自定义唯一标识；不填会自动生成

### 兼容：旧版单站点配置

如果没有配置 `MONITOR_TARGETS`，脚本会回退到以下变量：

```bash
API_BASE_URL=https://api.example.com/v1
API_KEY=your_api_key
API_MODEL=gpt-4o-mini
```

## GitHub Actions 配置

进入仓库 `Settings -> Secrets and variables -> Actions`，推荐添加：

- `MONITOR_TARGETS`

如果你暂时还在用旧版单目标方式，也可以继续保留：

- `API_BASE_URL`
- `API_KEY`
- `API_MODEL`

配置完成后，工作流会每 10 分钟运行一次，并更新 `docs/data/status.json` 与 `docs/data/history.json`。

## 本地使用

```bash
# 1. 复制配置模板
cp .env.example .env

# 2. 编辑 .env，填入 MONITOR_TARGETS 或旧版单目标变量

# 3. 手动执行一次检测
python3 scripts/check_api.py

# 4. 启动本地静态页面
cd docs
python3 -m http.server 8080
```

浏览器访问 `http://localhost:8080`。

## 本地守护进程

如果你想在本机持续检测，可以运行：

```bash
python3 monitor_daemon.py
```

可选环境变量：

- `CHECK_INTERVAL_SECONDS`: 检测间隔秒数，默认 `600`

## 页面说明

- `全局概览`: 汇总全部目标数量、当前在线数、历史检测次数、平均延迟
- `监控目标`: 每个站点和模型组合对应一张卡片
- `最近24小时`: 每个目标一行小时格子图
- `最近检测记录`: 混合展示所有目标的最新结果

## 隐私安全

- API Key 只用于探测请求，不会写入公开页面
- 页面只展示域名、模型、状态、延迟和错误信息
- 建议使用权限受限的专用 Key
