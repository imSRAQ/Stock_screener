# 📈 Automated NSE Stock Screener & AI Notifier

Welcome! If you are not a programmer, don't worry. This guide explains exactly what this project does in plain English.

## 🤔 What is this?
This is a **fully automated robot** that acts as your personal stock market analyst. 

Every day, there are over 5,000 stocks trading on the Indian Stock Market (NSE). Finding the good ones takes hours of staring at charts and reading financial reports. This system automates all of that. 

It wakes up automatically every morning, scans all 5,000+ stocks, filters out the bad ones, reads the news, uses Artificial Intelligence (AI) to write a summary, and generates a beautiful Web Dashboard. 

It then sends a short summary and the dashboard link directly to your phone via Telegram.

Once set up, **it runs 100% on its own in the cloud** for free. You never even need to open your laptop.

---

## 🛡️ How does it pick stocks? (The 6-Layer Filter)
We don't buy random stocks. To make it to your phone, a stock must survive a brutal "6-Layer Filter". If it fails even one layer, it is thrown out.

1. **The Trend Check:** The stock must already be going up consistently over the last 200 days. We don't try to catch falling knives.
2. **The Volume Check:** The trading volume must be higher than usual today. This means big institutions (like mutual funds) are buying, not just retail traders.
3. **The Momentum Check (RSI):** The stock must be moving up with good energy, but it shouldn't be "overbought" yet. There must be room to grow.
4. **The Strength Check (ADX):** The uptrend must be powerful, not just a weak, temporary bounce.
5. **The Weekly Check:** It zooms out to look at the weekly chart to ensure we aren't getting tricked by a short-term daily fakeout.
6. **The Fundamental Gate:** The company must be a good business. It must be profitable (positive EPS), growing its revenue (at least 5%), and not drowning in debt.

Out of 5,000 stocks, usually only **10 to 20** survive this test.

---

## 💰 How does it protect your money? (Smart Stop-Loss)
The golden rule of trading is: *Cut your losses fast, and let your winners run.* 

1. **Initial Stop-Loss:** Before you even buy, the system calculates a safe "floor" price based on historical volatility and volume. If the stock falls below this floor, it tells you to exit immediately to prevent a big loss.
2. **Trailing Stop-Loss:** If the stock goes up by 5%, the system activates a "trailing stop." As the stock price climbs higher and higher, the stop-loss floor moves up right behind it. If the stock eventually drops, you get stopped out, but you **keep your profit**.

---

## 🧠 The AI Brain
Instead of sending you a boring, confusing spreadsheet of numbers, this system connects to advanced AI (like Google Gemini, Groq, OpenAI, or Claude). 

It feeds all the stock data and the latest news headlines into the AI, and the AI writes a simple, 2-sentence summary for you. 

**Example of what you get on Telegram:**
> *"Reliance shows a solid bullish entry setup, backed by a strong ADX indicating trend strength and high volume confirming institutional participation. The RSI leaves plenty of headroom for price appreciation. Consider entering at Rs 2500.0 with a strict stop-loss at Rs 2400.0."*

---

## 📱 How to set it up (For Beginners)

This system runs automatically in the cloud using a free **Render.com** Web Service. To set it up, you just need to give it your API keys (secure passwords) so it can access AI and message your Telegram.

### Step 1: Get a Telegram Bot Token
1. Open Telegram on your phone and search for `BotFather`.
2. Send the message `/newbot` and follow the steps to name your bot.
3. BotFather will give you a long password called an **API Token**. Save this.
4. Search for your new bot in Telegram and send it a message saying "Hello".

### Step 2: Get your Telegram Chat ID
1. Search for `@RawDataBot` or `@userinfobot` on Telegram.
2. Send it a message. It will reply with your `id` (a string of numbers). Save this.

### Step 3: Get a Free AI Key (Groq or Gemini)
1. Go to [console.groq.com/keys](https://console.groq.com/keys) (recommended) or Google AI Studio.
2. Sign in with Google and click **Create API Key**. Save this key.

### Step 4: Deploy to Render.com
1. Go to [Render.com](https://render.com) and sign up.
2. Create a new **Web Service** and connect it to your GitHub repository.
3. Set the Build Command to `pip install -r requirements.txt` and the Start Command to `python stocks_monitoring_and_notifying/bot_worker.py`.
4. In the Environment Variables section, add your secrets:
   - `TELEGRAM_BOT_TOKEN`: (paste your token from Step 1)
   - `TELEGRAM_CHAT_ID`: (paste your ID from Step 2)
   - `GEMINI_API_KEY`: (paste your AI key from Step 3)
   - `GITHUB_TOKEN`: (create a personal access token on GitHub and paste here so the bot can save its data)

### Step 5: You're Done!
The system will now automatically run every Monday-Friday at 8:00 AM IST and send you the best stocks for the day!

---

## 🎮 Telegram Commands
You can actually text your bot on Telegram to control the system!

- Send `/status` to see how the overall stock market is doing today.
- Send `/portfolio` to see your current open trades and profit/loss.
- Send `/entry RELIANCE 2500 10` to log that you bought 10 shares of Reliance at 2500. The system will start tracking your trailing stop-loss automatically!
- Send `/hourly off` to stop getting hourly updates, or `/hourly on` to resume them.
