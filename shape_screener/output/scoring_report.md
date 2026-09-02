# Fundamental & Technical Scoring Methodology

This report outlines the specific parameters extracted for each stock and how the algorithms calculate the composite **Fund Score (0-100)** and **Tech Score (0-100)**. 

Both scores are designed to normalize disparate metrics into a single, easy-to-read "strength" rating where **100 is excellent** and **0 is weak**. Missing data defaults to a neutral score (usually 50) so companies aren't heavily penalized for missing API data.

---

## 1. Fundamental Score (Fund Score)

The fundamental score evaluates a company's financial health, valuation, and profitability based on 7 key metrics fetched from Yahoo Finance.

| Parameter | Weight | What it measures | Scoring Logic |
| :--- | :--- | :--- | :--- |
| **P/E Ratio** | 15% | Valuation (Price to Earnings) | **Best (< 15):** 100 pts<br>**Good (15-25):** Scales down to 60 pts<br>**Poor (> 40):** 0 pts |
| **ROE** | 15% | Efficiency (Return on Equity) | **Best (> 20%):** 100 pts<br>**Positive:** Scales linearly<br>**Negative:** 0 pts |
| **Debt to Equity** | 15% | Leverage & Debt Risk | **Best (< 0.5):** 100 pts<br>**Good (0.5-1.0):** Scales down to 60 pts<br>**Poor (> 2.0):** 0 pts |
| **Profit Margin** | 15% | Profitability (Net Margin) | **Best (> 25%):** 100 pts<br>**Positive:** Scales linearly<br>**Negative:** 0 pts |
| **Revenue Growth** | 15% | Top-line Growth (YoY) | **Best (> 20%):** 100 pts<br>**Positive:** Scales linearly<br>**Negative:** 0 pts |
| **Free Cash Flow** | 15% | Cash generation | **Positive FCF:** 100 pts<br>**Negative FCF:** 0 pts |
| **EPS** | 10% | Earnings per share | **Positive EPS:** 100 pts<br>**Negative EPS:** 0 pts |

> [!NOTE]
> The final **Fund Score** is the weighted sum of the points achieved in all 7 categories.

---

## 2. Technical Score (Tech Score)

The technical score evaluates the immediate price momentum and trend strength of the stock based purely on its historical closing prices.

| Parameter | Weight | What it measures | Scoring Logic |
| :--- | :--- | :--- | :--- |
| **RSI (14)** | 25% | Momentum (Overbought/Oversold) | **Goldilocks (50-65):** 100 pts<br>**Healthy (40-70):** 50 pts<br>**Extreme (<30 or >80):** 0 pts |
| **SMA Crossovers** | 25% | Medium & Long-term Trend | **Above 50-day & 200-day:** 100 pts<br>**Above 200-day only:** 50 pts<br>**Below both:** 0 pts |
| **MACD** | 25% | Trend Reversals / Momentum | **Bullish (MACD Line > Signal Line):** 100 pts<br>**Bearish (MACD Line < Signal Line):** 0 pts |
| **ADX (14)** | 25% | Trend Strength (Regardless of direction) | **Strong Trend (> 25):** 100 pts<br>**Moderate (20-25):** 50 pts<br>**Weak/Ranging (< 20):** 0 pts |

> [!NOTE]
> The final **Tech Score** is simply the average of these four indicator scores. Because the screener is explicitly filtering for **Uptrends**, a high ADX coupled with Bullish MACD and price above the SMA-200 guarantees that the stock is experiencing strong upward momentum.

---

## 3. Justification & References for Weightings

The weights and thresholds were not chosen arbitrarily. They are derived from classical value investing principles and standard quantitative momentum strategies used by institutional traders.

### Fundamental Weightings Justification

The fundamental score uses an evenly distributed weighting (15% across major metrics, 10% for EPS) to prevent any single metric from dominating the score. This creates a balanced "Quality" factor model.

- **P/E Ratio (15%)**: Serves as the primary valuation anchor. **Reference:** *Benjamin Graham ("The Intelligent Investor")* established the concept of the "Margin of Safety," heavily emphasizing buying companies with low P/E ratios (specifically recommending a P/E under 15 for defensive investors).
- **Return on Equity / ROE (15%)**: Measures management's efficiency at compounding capital. **Reference:** *Warren Buffett* famously targets companies with a consistent ROE of 15% or higher, as it indicates a strong economic moat and the ability to grow internally without taking on excessive debt.
- **Debt to Equity (15%)**: A strict risk-management filter. **Reference:** *Peter Lynch ("One Up On Wall Street")* suggests a D/E ratio of less than 0.5 to ensure a company has the balance sheet strength to survive economic downturns. 
- **Profit Margin & Revenue Growth (15% each)**: Top-line and bottom-line health. **Reference:** *Philip Fisher ("Common Stocks and Uncommon Profits")* identified consistent sales growth and high profit margins as the most critical factors for long-term capital appreciation, demonstrating pricing power.
- **Free Cash Flow (FCF) (15%)**: Cash is the ultimate truth teller. **Reference:** Modern Discounted Cash Flow (DCF) models rely entirely on FCF because, unlike EPS, cash flow is extremely difficult for accountants to manipulate.
- **EPS (10%)**: Given slightly less weight than FCF because Earnings Per Share can be artificially inflated through share buybacks or accounting accruals, but remains a necessary baseline for profitability.

### Technical Weightings Justification

The technical score distributes weight evenly (25% each) across four distinct classes of indicators (Momentum, Trend, Acceleration, and Strength) to build a robust profile of the stock's price action.

- **SMA 50 & 200 (25%)**: The institutional standard for trend direction. **Reference:** Legendary trader *Paul Tudor Jones* famously stated his number one rule for trading is "never play macho with the 200-day moving average." A stock above its 200-day SMA is in a confirmed long-term bull market.
- **RSI (25%)**: Created by *J. Welles Wilder*. Rather than just buying "oversold" (<30), the algorithm rewards the 50-65 "Goldilocks" zone. **Reference:** In swing trading, an RSI hovering between 50 and 65 during an uptrend indicates healthy, sustained buying pressure that is not yet exhausted (overbought).
- **MACD (25%)**: Created by *Gerald Appel*. MACD measures the *acceleration* of a trend. A bullish crossover confirms that immediate short-term momentum is aligned with the longer-term trend.
- **ADX (25%)**: Also created by *J. Welles Wilder*. While SMA tells you the *direction* of the trend, ADX tells you the *strength* of it. **Reference:** Wilder established that an ADX reading above 25 signifies a strong trend, which helps quantitative models filter out choppy, sideways markets where trend-following strategies fail.
