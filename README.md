# Fibo_auto Global Scanner v2.0

> 基于 MQL4 Fibo_auto 精确还原的全资产斐波那契扫描器  
> PRD v2.0 完整实现 · Streamlit Cloud · 4H/日/周/月四周期共振

---

## 📦 文件结构

```
app.py                    # 主程序（全部功能集成在单文件中）
requirements.txt          # Python 依赖声明
.streamlit/
  config.toml             # Streamlit 主题配置（暗色金色风格）
```

---

## 🚀 快速部署（Streamlit Cloud）

### 第 1 步：上传到 GitHub

```bash
git init
git add .
git commit -m "Fibo_auto v2.0 initial"
git remote add origin https://github.com/你的用户名/fiboauto-scanner.git
git push -u origin main
```

### 第 2 步：Streamlit Cloud 部署

1. 访问 [share.streamlit.io](https://share.streamlit.io)
2. 点击 **New app** → 连接 GitHub 仓库
3. 选择 `main` 分支，入口文件 `app.py`
4. 点击 **Deploy!**（首次约 2-3 分钟）

### 第 3 步：配置 Secrets（可选，用于高级功能）

在 Streamlit Cloud 控制台 → Settings → Secrets 填入：

```toml
# Secrets.toml（仅 Streamlit Cloud 后台填写，不要提交到 GitHub）

# AlphaVantage（美股全量代码列表）
ALPHAVANTAGE_KEY = "your_key_here"

# Binance（加密货币实时 WebSocket）
BINANCE_API_KEY    = "your_binance_api_key"
BINANCE_API_SECRET = "your_binance_api_secret"

# Alpaca（美股实时报价）
ALPACA_KEY    = "your_alpaca_key"
ALPACA_SECRET = "your_alpaca_secret"

# Supabase（多用户数据库，标的池持久化）
SUPABASE_URL = "https://xxx.supabase.co"
SUPABASE_KEY = "your_supabase_anon_key"
```

> 不配置 Secrets 时，应用以演示模式运行：yfinance 轮询替代 WebSocket，标的池存于 session_state。

---

## 🖥️ 本地运行

```bash
# 克隆项目
git clone https://github.com/你的用户名/fiboauto-scanner.git
cd fiboauto-scanner

# 安装依赖
pip install -r requirements.txt

# 启动
streamlit run app.py
```

浏览器自动打开 `http://localhost:8501`

---

## 📖 功能模块说明

### F1 — 扫描器（Scanner）

| 功能 | 说明 |
|------|------|
| 标的池选择 | 活跃混合精选 / S&P500+NDX / ETF / 期货 / 外汇 / 加密 / 全球指数 |
| 时间框架 | **4H**（新增）/ 日线 / 周线 / 月线，共振分最高 **4** 分 |
| Fib 区间 | 4 个预设区间 + 自定义区间 |
| 并发扫描 | ThreadPoolExecutor，支持 1-20 线程 |
| 结果过滤 | 实时共振分滑块，无需重扫 |
| 导出 | 含 7 个 Fib 层级价格的完整 CSV |

### F2 — 实时监控（Real-time Monitor）

| 功能 | 说明 |
|------|------|
| 数据源优先级 | Binance WS → Alpaca WS → yfinance 轮询（降级） |
| 预警触发 | 进入黄金区/深度回调区/精准触位/共振标的 |
| 通知渠道 | 页面 toast + Telegram（需配置）+ Email（需配置） |
| 监控容量 | 最多 20 个标的同时监控 |

### F3 — 回测模块（Backtest）

| 功能 | 说明 |
|------|------|
| 算法 | 滚动窗口回测，步长 1 根 K 线 |
| 结果指标 | 胜率 / R:R / 期望值 / 最大连续亏损 |
| 可视化 | Plotly 饼图结果分布 |
| 导出 | 每笔信号明细 CSV |

### F4 — 标的池管理（Watchlist）

| 功能 | 说明 |
|------|------|
| 个人收藏夹 | 最多 2000 个标的，CSV 批量导入/导出 |
| 团队标的池 | 共享池（生产环境需 Supabase） |
| 扫描预设 | 参数组合保存与切换 |

---

## 🔬 核心算法（MQL4 精确还原）

### 方向判断

```python
# MQL4 原版：bar_high < bar_low → 高点 bar 序号更小 → Bearish
# Python 等价（idx=0为最新bar）：
if idx_hi < idx_lo:
    direction = "Bearish"   # 高点更近
else:
    direction = "Bullish"   # 低点更近（或同时）
```

### Fibonacci 层级（上涨结构）

| 层级 | 公式 |
|------|------|
| F[0] 100% | swing_low |
| F[1] 76.0% | swing_high − 0.760 × range |
| F[2] 61.8% | swing_high − 0.618 × range |
| F[3] 50.0% | swing_high − 0.500 × range |
| F[4] 38.2% | swing_high − 0.382 × range |
| F[5] 23.6% | swing_high − 0.236 × range |
| F[6] 0.0%  | swing_high |

### 4H 时间框架换算

```python
# 1H 数据 resample 为 4H
df_4h = df_1h.resample('4h').agg(
    Open=('Open','first'), High=('High','max'),
    Low=('Low','min'), Close=('Close','last'), Volume=('Volume','sum')
).dropna()

# 回看根数换算
bars_4h_crypto   = Days × 6      # 24h ÷ 4h
bars_4h_us_stock = Days × 1.625  # 6.5h ÷ 4h
bars_4h_a_stock  = Days × 1.0    # 降级处理
```

---

## ⚠️ 已知限制

| 限制 | 说明 |
|------|------|
| 4H 数据覆盖 | yfinance 1H 最多 60 天，4H 回测时间段受限 |
| A 股 4H | 仅 4h 交易时段，4H K 线聚合效果有限，建议关闭 |
| yfinance 限流 | 并发 >16 线程可能触发封禁，建议 8-12 线程 |
| 回测非真实 | 不含滑点/手续费，胜率仅供参考 |
| Streamlit Cloud | 免费版 1GB 内存，30 分钟无访问后休眠 |
| WebSocket | 演示模式下降级为 yfinance 轮询（30s 延迟） |

---

## 📅 版本 Roadmap

| 版本 | 状态 | 主要功能 |
|------|------|----------|
| v1.0 | ✅ 已发布 | Google Colab + MQL4 还原 + 全资产扫描 |
| v1.1 | ✅ 已发布 | 区间校验 + A 股优化 + Fib 分布图 |
| **v2.0** | **📄 本版** | 4H 框架 + Streamlit + WebSocket + 回测 + 多用户 |
| v2.1 | 🗓 规划中 | 移动端 App + 更多 WebSocket 数据源 |
| v2.2 | 🗓 规划中 | AI 标的推荐 + 智能区间权重调整 |
| v3.0 | 🔭 远期 | Docker 私有部署 + 机构级并发 |

---

*Fibo_auto Global Scanner · PRD v2.0 · 2025*
