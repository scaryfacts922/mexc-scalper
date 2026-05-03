# MEXC Scalper — Live Signal Engine
### 1–5 Minute Crypto Scalping System | EMA + RSI + VWAP + Volume

---

## 🚀 DEPLOY TO NETLIFY (5 minutes)

### Step 1: Push to GitHub
```bash
git init
git add .
git commit -m "MEXC Scalper init"
gh repo create mexc-scalper --public --push
# OR: create repo on github.com, then git remote add origin <url> && git push
```

### Step 2: Connect to Netlify
1. Go to [netlify.com](https://netlify.com) → **Add new site** → **Import from Git**
2. Select your GitHub repo
3. Build settings auto-detected from `netlify.toml`:
   - **Publish directory**: `public`
   - **Functions directory**: `netlify/functions`
4. Click **Deploy**

### Step 3: Add Environment Variable
1. Netlify Dashboard → **Site settings** → **Environment variables**
2. Add: `ANTHROPIC_API_KEY` = `sk-ant-...your key...`
3. Re-deploy (Deploys → Trigger deploy)

**Your app is live at `https://your-site.netlify.app`**

---

## 🐍 PYTHON LOCAL ENGINE

### Install
```bash
pip install requests pandas numpy colorama
```

### Run
```bash
cd python/
python scalper_engine.py
```

Change the symbol or timeframe at top of file:
```python
WATCHLIST = ["SOLUSDT", ...]  # first symbol runs
TIMEFRAME = "1m"              # or "5m"
```

---

## 📊 STRATEGY RULES

### ✅ LONG Entry (all required)
| Condition | Rule |
|-----------|------|
| Trend | Price > VWAP |
| EMA | EMA9 > EMA21 |
| Momentum | RSI between 45–65 |
| Volume | Volume > 1.5× 20-candle average |
| Trigger | Price crosses above EMA9 |

### ✅ SHORT Entry
| Condition | Rule |
|-----------|------|
| Trend | Price < VWAP |
| EMA | EMA9 < EMA21 |
| Momentum | RSI between 35–55 |
| Volume | Volume > 1.5× average |
| Trigger | Price crosses below EMA9 |

### ⛔ DO NOT TRADE WHEN
- RSI > 75 (overbought) or RSI < 25 (oversold)
- Volume ratio < 0.8× average (low conviction)
- EMA9 and EMA21 within 0.05% of each other (consolidation)
- ATR < 0.08% of price (no range to scalp)
- Major news event within 15 minutes
- Weekend / low-liquidity session

### 📐 Risk Management
| Level | Calculation |
|-------|-------------|
| Stop Loss | Entry ∓ 1.0 × ATR |
| Take Profit 1 | Entry ± 1.5 × ATR (R:R = 1:1.5) |
| Take Profit 2 | Entry ± 2.5 × ATR (R:R = 1:2.5) |
| Position Size | (Account × 0.5%) ÷ ATR |
| Max risk/trade | 0.5% of account |

### 🚪 Exit Rules
1. **Hard exit**: Price hits SL or TP
2. **Time exit**: After 5 candles with no TP hit
3. **Momentum exit**: RSI crosses 70 (for longs) or 30 (for shorts)
4. **Reversal exit**: EMA9 crosses back through EMA21

---

## 📁 Project Structure
```
mexc-scalper/
├── public/
│   └── index.html          ← Frontend dashboard (Netlify serves this)
├── netlify/
│   └── functions/
│       └── ai-advisor.js   ← Claude AI analysis function
├── python/
│   └── scalper_engine.py   ← Local Python engine
└── netlify.toml            ← Netlify config
```

---

## 🔑 API Keys
- **MEXC Market Data**: No API key needed (public endpoints)
- **Anthropic (Claude)**: Required for AI advisor button
  - Get yours at [console.anthropic.com](https://console.anthropic.com)
  - Add as `ANTHROPIC_API_KEY` in Netlify env vars

---

## ⚠️ Disclaimer
This tool is for **educational and informational purposes only**.
Crypto scalping is high risk. Never risk money you cannot afford to lose.
Always paper-trade first. Past signals do not guarantee future results.
