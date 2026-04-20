# API Status Monitor

一个轻量级的API可用性监测站，支持自动定时检测和可视化展示。

## 功能特性

- 自动定时探测API可用性（每10分钟）
- 记录HTTP状态、响应延迟、错误信息
- 7天历史数据统计和可用率计算
- 24小时可用性热力图展示
- 纯静态页面，可部署到GitHub Pages

## 项目结构

```
api_status_monitor/
├── .github/
│   └── workflows/
│       └── status-check.yml   # GitHub Actions定时任务
├── docs/
│   ├── index.html             # 状态展示页面
│   ├── style.css              # 样式文件
│   ├── app.js                 # 前端交互脚本
│   └── data/
│       ├── status.json        # 当前状态
│       └── history.json       # 历史记录
├── scripts/
│   └── check_api.py           # 探测脚本
├── .env.example               # 环境变量示例
├── .gitignore
├── requirements.txt
└── README.md
```

## 快速开始

### 1. Fork本项目到你的GitHub账号

### 2. 配置Secrets

进入仓库 Settings → Secrets and variables → Actions，添加：

| Secret名称 | 说明 |
|-----------|------|
| `API_BASE_URL` | API地址，如 `https://api.example.com/v1` |
| `API_KEY` | 你的API密钥 |
| `API_MODEL` | 探测模型，如 `gpt-3.5-turbo` |

### 3. 启用GitHub Pages

进入 Settings → Pages：
- Source选择 `Deploy from a branch`
- Branch选择 `main`，目录选择 `/docs`
- 点击Save

### 4. 手动触发首次运行

进入 Actions → API Status Check → Run workflow

之后每10分钟会自动运行一次。

## 本地测试

```bash
# 1. 克隆项目
git clone https://github.com/你的用户名/api_status_monitor.git
cd api_status_monitor

# 2. 创建配置文件
cp .env.example .env
# 编辑.env填写你的API配置

# 3. 运行探测脚本（Python 3.8+）
python scripts/check_api.py

# 4. 本地查看页面
cd docs
python -m http.server 8080
# 浏览器打开 http://localhost:8080
```

## 隐私安全

- API Key仅存储在GitHub Secrets中，不会出现在代码中
- 状态页面只显示域名，不显示完整URL和Key
- 建议使用只读权限的API Key进行监测

## 自定义

### 修改检测频率

编辑 `.github/workflows/status-check.yml`：

```yaml
schedule:
  - cron: '0/10 * * * *'  # 改为你需要的时间
```

### 修改探测模型

在Secrets中修改 `API_MODEL` 的值。

### 修改历史保留天数

编辑 `scripts/check_api.py`，修改 `HISTORY_DAYS` 常量。

## 致谢

参考项目: [anyrouter-status-page](https://github.com/KMnO4-zx/anyrouter-status-page)
