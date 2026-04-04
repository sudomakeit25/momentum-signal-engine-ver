"use client";

import { BookOpen } from "lucide-react";

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="space-y-3">
      <h2 className="text-base font-bold text-zinc-100">{title}</h2>
      <div className="space-y-2 text-sm leading-relaxed text-zinc-400">
        {children}
      </div>
    </section>
  );
}

function Field({ name, children }: { name: string; children: React.ReactNode }) {
  return (
    <div className="flex gap-3 rounded-md border border-zinc-800 bg-zinc-900/50 px-4 py-3">
      <span className="shrink-0 font-mono text-sm font-bold text-cyan-400">
        {name}
      </span>
      <span className="text-sm text-zinc-400">{children}</span>
    </div>
  );
}

export default function GuidePage() {
  return (
    <div className="mx-auto max-w-3xl space-y-8 pb-16">
      <div className="flex items-center gap-3">
        <BookOpen className="h-5 w-5 text-cyan-400" />
        <h1 className="text-lg font-bold">How It Works</h1>
      </div>

      {/* Overview */}
      <Section title="Overview">
        <p>
          The Momentum Signal Engine scans a universe of 76 liquid US equities
          every 30 seconds, ranks them by momentum, and generates actionable
          buy/sell signals with entry, stop-loss, and target prices. It uses
          real market data from Alpaca Markets.
        </p>
        <p>
          The engine combines multiple technical indicators (EMAs, RSI, ATR,
          VWAP, volume) and pattern detection (breakouts, flags, flat bases) to
          score each stock from 0&ndash;100 and surface the strongest setups.
        </p>
      </Section>

      {/* Pages */}
      <Section title="Pages">
        <div className="space-y-4">
          <div>
            <h3 className="mb-1 font-semibold text-zinc-200">Scanner</h3>
            <p>
              The main dashboard. Shows the top momentum stocks ranked by
              composite score. Auto-refreshes every 30 seconds. Use filters to
              narrow by price range and volume. Click any symbol to open its
              chart.
            </p>
          </div>
          <div>
            <h3 className="mb-1 font-semibold text-zinc-200">Charts</h3>
            <p>
              Interactive candlestick chart powered by TradingView
              Lightweight Charts. Shows EMA overlays (9, 21, 50, 200), VWAP,
              RSI panel, and volume histogram. Toggle indicators on/off from
              the toolbar.
            </p>
          </div>
          <div>
            <h3 className="mb-1 font-semibold text-zinc-200">Position Sizer</h3>
            <p>
              Calculates how many shares to buy based on your account size,
              risk tolerance, entry price, and stop-loss. Ensures you never
              risk more than a fixed percentage per trade.
            </p>
          </div>
          <div>
            <h3 className="mb-1 font-semibold text-zinc-200">Backtest</h3>
            <p>
              Runs the momentum strategy on historical data. Shows total
              trades, win rate, average R:R, total return, max drawdown, an
              equity curve, and a detailed trade log.
            </p>
          </div>
        </div>
      </Section>

      {/* Scanner Fields */}
      <Section title="Scanner Table Fields">
        <div className="space-y-2">
          <Field name="Symbol">
            The stock ticker. Click it to open the chart page for that stock.
          </Field>
          <Field name="Price">
            The latest closing price of the stock.
          </Field>
          <Field name="Change %">
            Today&apos;s percentage change. Green = up, red = down.
          </Field>
          <Field name="Volume">
            The number of shares traded today. Higher volume means more
            interest and liquidity.
          </Field>
          <Field name="RS">
            Relative Strength vs SPY. A value above 1.0 means the stock is
            outperforming the S&P 500 over the lookback period. Higher is
            better for momentum stocks.
          </Field>
          <Field name="Score">
            Composite momentum score from 0&ndash;100, combining relative
            strength, volume surge, proximity to 52-week high, EMA alignment,
            and breakout detection. Green (&ge;70) = strong, yellow
            (&ge;40) = moderate, gray (&lt;40) = weak.
          </Field>
          <Field name="Setups">
            Chart patterns detected on the stock. These are structural setups
            that may lead to a move, not necessarily active signals yet.
          </Field>
          <Field name="Signals">
            Active buy or sell signals. Green = BUY, red = SELL. Each signal
            includes an entry, stop-loss, target, and R:R ratio.
          </Field>
          <Field name="Reason">
            A plain-English explanation of why the signal was generated,
            describing the specific technical condition that triggered it.
          </Field>
        </div>
      </Section>

      {/* Signal Types */}
      <Section title="Signal Types">
        <p className="mb-2">
          The engine checks for these conditions on every scan. When both buy
          and sell signals fire on the same stock, only the higher-confidence
          side is kept.
        </p>

        <h3 className="mt-4 mb-2 font-semibold text-emerald-400">Buy Signals</h3>
        <div className="space-y-2">
          <Field name="EMA Crossover">
            The 9-period EMA crosses above the 21-period EMA, indicating a
            new short-term uptrend. Also triggers if the crossover happened
            within the last 5 bars and the trend is still active.
          </Field>
          <Field name="Breakout">
            Price closes above the 20-day resistance level on above-average
            volume (1.5x or more). This is the highest-confidence buy signal
            (75%).
          </Field>
          <Field name="RSI Pullback">
            RSI has pulled back to the 40&ndash;50 zone in an uptrend (healthy
            dip), or to 50&ndash;60 with bullish EMA stack. Good entry on a
            temporary dip.
          </Field>
          <Field name="VWAP Reclaim">
            Price crosses above the Volume Weighted Average Price from below.
            This often signals institutional buyers stepping in.
          </Field>
          <Field name="Uptrend Momentum">
            EMAs are stacked bullishly (9 &gt; 21 &gt; 50) with RSI between
            55&ndash;80. This is a lower-confidence trend-continuation signal
            (50%) that fires when no other specific setup is detected.
          </Field>
        </div>

        <h3 className="mt-4 mb-2 font-semibold text-red-400">Sell Signals</h3>
        <div className="space-y-2">
          <Field name="ATR Trailing Stop">
            Price drops below the ATR-based trailing stop. This is a trend
            protection mechanism&mdash;when the stop is hit, the uptrend is
            likely over. Highest-confidence sell signal (70%).
          </Field>
          <Field name="EMA Crossunder">
            The 9-period EMA crosses below the 21-period EMA, indicating the
            short-term trend is turning bearish. Confidence: 65%.
          </Field>
          <Field name="RSI Divergence">
            Price is making higher highs but RSI is making lower highs. This
            bearish divergence suggests momentum is fading even as price rises.
            Confidence: 55%.
          </Field>
          <Field name="Volume Climax">
            Extreme volume spike on a down candle, suggesting panic selling or
            a possible exhaustion top. Confidence: 60%.
          </Field>
        </div>
      </Section>

      {/* Technical Indicators */}
      <Section title="Technical Indicators">
        <div className="space-y-2">
          <Field name="EMA (9, 21, 50, 200)">
            Exponential Moving Average. Gives more weight to recent prices.
            EMA 9 reacts fastest, EMA 200 slowest. When shorter EMAs are above
            longer ones (&quot;stacked&quot;), the trend is bullish.
          </Field>
          <Field name="RSI (14)">
            Relative Strength Index. Measures momentum on a 0&ndash;100 scale.
            Above 70 = overbought, below 30 = oversold. In strong uptrends,
            pullbacks to 40&ndash;50 are buying opportunities.
          </Field>
          <Field name="ATR (14)">
            Average True Range. Measures volatility in dollar terms. Used to
            set stop-losses and position sizes. Higher ATR = more volatile.
          </Field>
          <Field name="VWAP">
            Volume Weighted Average Price. The average price weighted by
            volume. Institutional traders use this as fair value&mdash;price
            above VWAP is bullish.
          </Field>
          <Field name="MACD">
            Moving Average Convergence Divergence. Shows the relationship
            between 12-period and 26-period EMAs. The histogram shows
            momentum acceleration.
          </Field>
          <Field name="Volume SMA (20)">
            20-day average volume. Used to detect volume surges (current
            volume significantly above average).
          </Field>
        </div>
      </Section>

      {/* Chart Patterns */}
      <Section title="Chart Patterns (Setups)">
        <div className="space-y-2">
          <Field name="EMA Crossover">
            Short-term EMA crossed above long-term EMA, signaling a potential
            trend change.
          </Field>
          <Field name="Breakout">
            Price broke above a consolidation range with volume confirmation.
          </Field>
          <Field name="Flag / Pennant">
            A brief consolidation after a strong move, forming a flag shape.
            Usually resolves in the direction of the prior move.
          </Field>
          <Field name="Flat Base">
            Price trading in a tight range (low volatility) after an advance.
            Often precedes the next leg up.
          </Field>
          <Field name="Tight Range">
            Very narrow price range over recent bars, indicating compression
            before a potential explosive move.
          </Field>
          <Field name="Gap Up">
            Price opened significantly above the prior close, typically on
            news or earnings.
          </Field>
        </div>
      </Section>

      {/* Position Sizer Fields */}
      <Section title="Position Sizer Fields">
        <div className="space-y-2">
          <Field name="Account Size">
            Your total trading account value in dollars.
          </Field>
          <Field name="Risk %">
            The maximum percentage of your account you are willing to lose on
            this trade. For example, 2% of a $10,000 account = $200 max risk.
          </Field>
          <Field name="Entry Price">
            The price you plan to buy at.
          </Field>
          <Field name="Stop Loss">
            The price where you will exit if the trade goes against you. The
            difference between entry and stop determines your per-share risk.
          </Field>
          <Field name="Target Price">
            The price where you plan to take profits.
          </Field>
          <Field name="Shares">
            Calculated as: (Account &times; Risk%) &divide; (Entry &minus;
            Stop). This is the number of shares to buy so that if the stop is
            hit, you lose exactly your risk amount.
          </Field>
          <Field name="R:R Ratio">
            Reward-to-risk ratio: (Target &minus; Entry) &divide; (Entry
            &minus; Stop). A 2:1 ratio means your potential profit is twice
            your potential loss. Ratings: Excellent (&ge;3), Good (&ge;2),
            Decent (&ge;1.5), Poor (&lt;1.5).
          </Field>
        </div>
      </Section>

      {/* Backtest Fields */}
      <Section title="Backtest Fields">
        <div className="space-y-2">
          <Field name="Total Trades">
            The number of round-trip trades (buy + sell) executed during the
            backtest period.
          </Field>
          <Field name="Win Rate">
            Percentage of trades that were profitable. Above 50% with a
            positive R:R is a solid strategy.
          </Field>
          <Field name="Avg R:R">
            Average reward-to-risk ratio across all trades. Higher is better.
          </Field>
          <Field name="Total Return %">
            The total portfolio return over the backtest period, including
            compounding.
          </Field>
          <Field name="Max Drawdown %">
            The largest peak-to-trough decline during the backtest. Measures
            the worst-case loss you would have experienced.
          </Field>
          <Field name="Equity Curve">
            Chart showing your portfolio value over time. Ideally a smooth
            upward line.
          </Field>
          <Field name="Drawdown Chart">
            Shows periods of decline from the portfolio&apos;s peak. Displayed as
            negative percentages in red.
          </Field>
        </div>
      </Section>

      {/* Confidence */}
      <Section title="Confidence Levels">
        <p>
          Each signal has a confidence score from 0&ndash;100% indicating how
          strong the setup is:
        </p>
        <div className="space-y-2">
          <Field name="75%">
            Breakout with volume confirmation &mdash; strongest buy signal.
          </Field>
          <Field name="70%">
            RSI pullback in uptrend (buy) or ATR trailing stop hit (sell).
          </Field>
          <Field name="65%">
            Exact EMA crossover/crossunder bar.
          </Field>
          <Field name="60%">
            VWAP reclaim (buy) or volume climax (sell).
          </Field>
          <Field name="55%">
            Recent EMA crossover within 5 bars, mild RSI pullback, or RSI
            divergence.
          </Field>
          <Field name="50%">
            Uptrend momentum (trend-continuation fallback).
          </Field>
        </div>
      </Section>

      {/* Data Source */}
      <Section title="Data Source">
        <p>
          All market data comes from Alpaca Markets API using your paper
          trading account. The data is real-time market data &mdash; the same
          prices and volumes you see on any brokerage. Only execution is
          simulated in paper trading mode.
        </p>
        <p>
          The scanner universe includes 76 liquid US stocks across tech,
          healthcare, energy, financials, industrials, and major ETFs (SPY,
          QQQ, IWM, DIA).
        </p>
      </Section>
    </div>
  );
}
