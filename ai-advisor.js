// netlify/functions/ai-advisor.js
// Netlify serverless function — calls Claude API to give live trading advice
// Deploy: push to GitHub → Netlify auto-deploys
// Set env var: ANTHROPIC_API_KEY in Netlify dashboard

exports.handler = async (event, context) => {
  // CORS headers
  const headers = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Content-Type',
    'Content-Type': 'application/json',
  };

  if (event.httpMethod === 'OPTIONS') {
    return { statusCode: 200, headers, body: '' };
  }

  if (event.httpMethod !== 'POST') {
    return { statusCode: 405, headers, body: JSON.stringify({ error: 'Method not allowed' }) };
  }

  try {
    const { context: tradingContext } = JSON.parse(event.body);
    const ctx = tradingContext;

    const prompt = `You are a professional crypto scalping advisor. Analyze this LIVE market data and give a precise, actionable verdict.

LIVE MARKET DATA:
- Symbol: ${ctx.symbol} | Timeframe: ${ctx.timeframe}
- Current Price: ${ctx.currentPrice}
- Strategy Signal: ${ctx.signal} (Strength: ${ctx.signalStrength}%)

INDICATORS:
- EMA9: ${ctx.ema9?.toFixed(6)} | EMA21: ${ctx.ema21?.toFixed(6)}
- RSI(14): ${ctx.rsi?.toFixed(2)}
- VWAP: ${ctx.vwap?.toFixed(6)}
- ATR: ${ctx.atr?.toFixed(6)}
- Volume Ratio vs 20-candle avg: ${ctx.volRatio?.toFixed(2)}x

SETUP LEVELS:
- Entry: ${ctx.entry?.toFixed(6)}
- Stop Loss: ${ctx.stopLoss?.toFixed(6)}
- Target 1: ${ctx.tp1?.toFixed(6)}
- Target 2: ${ctx.tp2?.toFixed(6)}

RECENT 5 CANDLES (OHLCV):
${ctx.recentCandles?.map((c,i)=>`  [${i+1}] O:${c.o} H:${c.h} L:${c.l} C:${c.c} V:${c.v}`).join('\n')}

${ctx.noTradeReasons?.length ? 'NO-TRADE FILTERS TRIGGERED: '+ctx.noTradeReasons.join(', ') : ''}

Based on the strategy rules (EMA crossover, VWAP position, RSI momentum, volume confirmation):
1. Should I ENTER, WAIT, EXIT, or HOLD?
2. What is the key risk right now?
3. At what price should I exit if already in?

Respond ONLY as JSON (no markdown, no backticks):
{
  "verdict": "ENTER LONG" | "ENTER SHORT" | "WAIT" | "HOLD" | "EXIT NOW" | "STAND ASIDE" | "CAUTION",
  "action": "ENTER" | "WAIT" | "EXIT" | "HOLD",
  "reasoning": "2-3 sentences max, specific to the numbers above",
  "exitPrice": number or null,
  "riskNote": "one sentence about the main risk"
}`;

    const response = await fetch('https://api.anthropic.com/v1/messages', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'x-api-key': process.env.ANTHROPIC_API_KEY,
        'anthropic-version': '2023-06-01',
      },
      body: JSON.stringify({
        model: 'claude-sonnet-4-20250514',
        max_tokens: 400,
        messages: [{ role: 'user', content: prompt }],
      }),
    });

    if (!response.ok) {
      const err = await response.text();
      throw new Error('Anthropic API error: ' + err);
    }

    const data = await response.json();
    const rawText = data.content[0].text.trim();

    // Parse JSON response
    let parsed;
    try {
      parsed = JSON.parse(rawText);
    } catch (e) {
      // Try to extract JSON from response
      const match = rawText.match(/\{[\s\S]*\}/);
      if (match) {
        parsed = JSON.parse(match[0]);
      } else {
        throw new Error('Could not parse AI response as JSON');
      }
    }

    return {
      statusCode: 200,
      headers,
      body: JSON.stringify({
        verdict: parsed.verdict || 'WAIT',
        action: parsed.action || 'WAIT',
        reasoning: parsed.reasoning || 'Analysis unavailable.',
        exitPrice: parsed.exitPrice || null,
        riskNote: parsed.riskNote || '',
        timestamp: new Date().toISOString(),
      }),
    };

  } catch (error) {
    console.error('AI advisor error:', error);
    return {
      statusCode: 500,
      headers,
      body: JSON.stringify({
        error: error.message,
        verdict: 'WAIT',
        reasoning: 'AI analysis temporarily unavailable. Using local rule-based analysis.',
      }),
    };
  }
};
