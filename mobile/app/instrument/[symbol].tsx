import { useQuery, useQueryClient, useMutation } from "@tanstack/react-query";
import { Stack, useLocalSearchParams } from "expo-router";
import { useMemo, useState } from "react";
import {
  ActivityIndicator,
  Dimensions,
  Linking,
  Modal,
  Pressable,
  ScrollView,
  Share,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import Svg, {
  Circle,
  Line as SvgLine,
  Path,
  Rect,
  Text as SvgText,
} from "react-native-svg";
import {
  api,
  API_BASE,
  AgentTopic,
  ChartBar,
  EventsResponse,
  FibonacciResponse,
  IchimokuResponse,
  IndicatorsResponse,
  InsiderTrade,
  MultiTFResponse,
  SeasonalityHeatmapRow,
  TranscriptQuarter,
  VolumeProfileResponse,
} from "../../src/lib/api";
import { colors, radius, spacing } from "../../src/lib/theme";

type Section =
  | "Overview"
  | "Indicators"
  | "Pattern"
  | "Seasonality"
  | "Earnings"
  | "Insider"
  | "Fundamentals"
  | "News";
const SECTIONS: Section[] = [
  "Overview",
  "Indicators",
  "Pattern",
  "Seasonality",
  "Earnings",
  "Insider",
  "Fundamentals",
  "News",
];

export default function InstrumentScreen() {
  const { symbol: rawSymbol } = useLocalSearchParams<{ symbol: string }>();
  const symbol = String(rawSymbol ?? "").toUpperCase();
  const [section, setSection] = useState<Section>("Overview");

  return (
    <SafeAreaView style={styles.container} edges={["bottom"]}>
      <Stack.Screen
        options={{
          title: symbol,
          headerRight: () => (
            <View style={{ flexDirection: "row" }}>
              <ShareButton symbol={symbol} />
              <WatchlistStar symbol={symbol} />
            </View>
          ),
        }}
      />

      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        style={styles.tabBarWrap}
        contentContainerStyle={styles.tabBar}
      >
        {SECTIONS.map((s) => (
          <Pressable
            key={s}
            onPress={() => setSection(s)}
            style={[styles.tab, section === s && styles.tabActive]}
          >
            <Text
              style={[styles.tabText, section === s && styles.tabTextActive]}
            >
              {s}
            </Text>
          </Pressable>
        ))}
      </ScrollView>

      <ScrollView
        style={{ flex: 1 }}
        contentContainerStyle={{
          padding: spacing.lg,
          paddingBottom: spacing.xxl,
        }}
      >
        {section === "Overview" && <OverviewSection symbol={symbol} />}
        {section === "Indicators" && <IndicatorsSection symbol={symbol} />}
        {section === "Pattern" && <PatternSection symbol={symbol} />}
        {section === "Seasonality" && <SeasonalitySection symbol={symbol} />}
        {section === "Earnings" && <EarningsSection symbol={symbol} />}
        {section === "Insider" && <InsiderSection symbol={symbol} />}
        {section === "Fundamentals" && <FundamentalsSection symbol={symbol} />}
        {section === "News" && <NewsSection symbol={symbol} />}
      </ScrollView>
    </SafeAreaView>
  );
}

/* --- Watchlist star (header) --- */

function WatchlistStar({ symbol }: { symbol: string }) {
  const qc = useQueryClient();
  const { data: list } = useQuery({
    queryKey: ["watchlist"],
    queryFn: api.watchlist,
  });
  const safeList = Array.isArray(list) ? list : [];
  const inList = safeList.includes(symbol);

  const toggle = useMutation({
    mutationFn: async () => {
      const next = inList
        ? safeList.filter((s) => s !== symbol)
        : [...safeList, symbol];
      await api.saveWatchlist(next);
      return next;
    },
    onMutate: async () => {
      await qc.cancelQueries({ queryKey: ["watchlist"] });
      const prev = qc.getQueryData<string[]>(["watchlist"]);
      const prevSafe = Array.isArray(prev) ? prev : [];
      qc.setQueryData<string[]>(
        ["watchlist"],
        inList
          ? prevSafe.filter((s) => s !== symbol)
          : [...prevSafe, symbol],
      );
      return { prev: prevSafe };
    },
    onError: (_err, _vars, ctx) => {
      if (ctx?.prev) qc.setQueryData(["watchlist"], ctx.prev);
    },
    onSettled: () => {
      qc.invalidateQueries({ queryKey: ["watchlist"] });
    },
  });

  return (
    <Pressable
      onPress={() => toggle.mutate()}
      style={{ paddingHorizontal: spacing.md, paddingVertical: spacing.sm }}
      hitSlop={10}
    >
      <Text
        style={{
          fontSize: 22,
          color: inList ? colors.amber : colors.textDim,
        }}
      >
        {inList ? "★" : "☆"}
      </Text>
    </Pressable>
  );
}

/* --- Overview --- */

function OverviewSection({ symbol }: { symbol: string }) {
  const analyzer = useQuery({
    queryKey: ["analyzer", symbol],
    queryFn: () => api.analyzer(symbol),
  });
  const trends = useQuery({
    queryKey: ["trends", symbol],
    queryFn: () => api.trends(symbol),
  });

  if (analyzer.isLoading) return <Loading />;
  const a = analyzer.data;
  const t = trends.data;

  if (!a || a.error) {
    return <ErrorCard message={a?.error ?? "no data"} />;
  }

  return (
    <View style={{ gap: spacing.md }}>
      <PriceChart symbol={symbol} />

      <View style={styles.card}>
        <View style={styles.row}>
          <View>
            <Text style={styles.muted}>Verdict</Text>
            <Text style={styles.big}>{a.grade}</Text>
            <Text style={styles.verdict}>{a.verdict.replace(/_/g, " ")}</Text>
          </View>
          <View style={{ alignItems: "flex-end" }}>
            <Text style={styles.muted}>Price</Text>
            <Text style={styles.bigMono}>${a.price.toFixed(2)}</Text>
            <Text
              style={[
                styles.change,
                {
                  color:
                    a.change_pct >= 0 ? colors.bullish : colors.bearish,
                },
              ]}
            >
              {a.change_pct >= 0 ? "+" : ""}
              {a.change_pct.toFixed(2)}%
            </Text>
          </View>
        </View>
      </View>

      <View style={styles.card}>
        <Text style={styles.cardTitle}>Component Scores</Text>
        <ScoreBar label="Trend" value={a.scores.trend} />
        <ScoreBar label="Momentum" value={a.scores.momentum} />
        <ScoreBar label="Quality" value={a.scores.quality} />
        <ScoreBar label="Risk" value={a.scores.risk} />
      </View>

      <View style={styles.card}>
        <Text style={styles.cardTitle}>Returns (weekly)</Text>
        <RetRow label="1Y" value={t?.returns?.["1y_pct"]} />
        <RetRow label="3Y" value={t?.returns?.["3y_pct"]} />
        <RetRow label="5Y" value={t?.returns?.["5y_pct"]} />
        {t?.regime && (
          <Text style={styles.muted}>
            Regime: {t.regime.replace(/_/g, " ")}
          </Text>
        )}
      </View>

      <AgentButtons symbol={symbol} />

      {a.strengths && a.strengths.length > 0 && (
        <View
          style={[styles.card, { borderColor: colors.bullish, borderWidth: 1 }]}
        >
          <Text style={[styles.cardTitle, { color: colors.bullish }]}>
            Strengths
          </Text>
          {a.strengths.map((s, i) => (
            <Text key={i} style={styles.bullet}>
              • {s}
            </Text>
          ))}
        </View>
      )}
      {a.weaknesses && a.weaknesses.length > 0 && (
        <View
          style={[styles.card, { borderColor: colors.bearish, borderWidth: 1 }]}
        >
          <Text style={[styles.cardTitle, { color: colors.bearish }]}>
            Weaknesses
          </Text>
          {a.weaknesses.map((w, i) => (
            <Text key={i} style={styles.bullet}>
              • {w}
            </Text>
          ))}
        </View>
      )}
    </View>
  );
}

function ScoreBar({ label, value }: { label: string; value: number }) {
  const pct = Math.max(0, Math.min(100, value));
  const color =
    pct >= 70 ? colors.bullish : pct >= 50 ? colors.amber : colors.bearish;
  return (
    <View style={{ marginVertical: 4 }}>
      <View style={{ flexDirection: "row", justifyContent: "space-between" }}>
        <Text style={styles.muted}>{label}</Text>
        <Text style={styles.mono}>{value.toFixed(0)}</Text>
      </View>
      <View style={styles.barTrack}>
        <View
          style={[styles.barFill, { width: `${pct}%`, backgroundColor: color }]}
        />
      </View>
    </View>
  );
}

function RetRow({
  label,
  value,
}: {
  label: string;
  value: number | null | undefined;
}) {
  if (value === null || value === undefined) {
    return (
      <View style={styles.retRow}>
        <Text style={styles.muted}>{label}</Text>
        <Text style={styles.muted}>--</Text>
      </View>
    );
  }
  return (
    <View style={styles.retRow}>
      <Text style={styles.muted}>{label}</Text>
      <Text
        style={[
          styles.mono,
          { color: value >= 0 ? colors.bullish : colors.bearish },
        ]}
      >
        {value >= 0 ? "+" : ""}
        {value.toFixed(1)}%
      </Text>
    </View>
  );
}

/* --- Price chart --- */

const RANGE_OPTIONS: { label: string; days: number }[] = [
  { label: "1M", days: 30 },
  { label: "3M", days: 90 },
  { label: "6M", days: 180 },
  { label: "1Y", days: 365 },
];

function PriceChart({ symbol }: { symbol: string }) {
  const [days, setDays] = useState(90);
  const q = useQuery({
    queryKey: ["chart", symbol, days],
    queryFn: () => api.chart(symbol, days),
  });

  const width = Math.min(Dimensions.get("window").width - spacing.lg * 2, 520);
  const height = 180;
  const padX = 8;
  const padY = 12;

  const bars = q.data?.bars ?? [];

  const { pathD, minClose, maxClose, firstClose, lastClose, xAt, yAt } =
    useMemo(() => {
      if (bars.length < 2) {
        return {
          pathD: "",
          minClose: 0,
          maxClose: 0,
          firstClose: 0,
          lastClose: 0,
          xAt: () => 0,
          yAt: () => 0,
        };
      }
      const closes = bars.map((b) => b.close);
      const min = Math.min(...closes);
      const max = Math.max(...closes);
      const range = max - min || 1;
      const innerW = width - padX * 2;
      const innerH = height - padY * 2;
      const n = bars.length;
      const xAt = (i: number) => padX + (i / (n - 1)) * innerW;
      const yAt = (v: number) => padY + (1 - (v - min) / range) * innerH;
      let d = `M ${xAt(0)} ${yAt(closes[0])}`;
      for (let i = 1; i < n; i++) d += ` L ${xAt(i)} ${yAt(closes[i])}`;
      return {
        pathD: d,
        minClose: min,
        maxClose: max,
        firstClose: closes[0],
        lastClose: closes[closes.length - 1],
        xAt,
        yAt,
      };
    }, [bars, width]);

  const up = lastClose >= firstClose;
  const lineColor = up ? colors.bullish : colors.bearish;
  const fillRect = `${colors.primary}15`;
  const lastIdx = bars.length - 1;
  const changePct =
    firstClose > 0 ? ((lastClose - firstClose) / firstClose) * 100 : 0;

  return (
    <View style={styles.card}>
      <View
        style={{
          flexDirection: "row",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: spacing.sm,
        }}
      >
        <Text style={styles.cardTitle}>Price</Text>
        {bars.length >= 2 && (
          <Text
            style={[
              styles.mono,
              { color: up ? colors.bullish : colors.bearish },
            ]}
          >
            {up ? "+" : ""}
            {changePct.toFixed(2)}% · {RANGE_OPTIONS.find((r) => r.days === days)?.label}
          </Text>
        )}
      </View>

      <View style={styles.rangeBar}>
        {RANGE_OPTIONS.map((r) => {
          const active = days === r.days;
          return (
            <Pressable
              key={r.days}
              onPress={() => setDays(r.days)}
              style={[styles.rangeBtn, active && styles.rangeBtnActive]}
            >
              <Text
                style={[
                  styles.rangeBtnText,
                  active && styles.rangeBtnTextActive,
                ]}
              >
                {r.label}
              </Text>
            </Pressable>
          );
        })}
      </View>

      {q.isLoading ? (
        <View style={{ height, justifyContent: "center", alignItems: "center" }}>
          <ActivityIndicator color={colors.primary} />
        </View>
      ) : bars.length < 2 ? (
        <View style={{ height, justifyContent: "center", alignItems: "center" }}>
          <Text style={styles.muted}>No chart data.</Text>
        </View>
      ) : (
        <Svg width={width} height={height}>
          <SvgLine
            x1={padX}
            y1={yAt(minClose)}
            x2={width - padX}
            y2={yAt(minClose)}
            stroke={colors.borderSubtle}
            strokeWidth={0.5}
          />
          <SvgLine
            x1={padX}
            y1={yAt(maxClose)}
            x2={width - padX}
            y2={yAt(maxClose)}
            stroke={colors.borderSubtle}
            strokeWidth={0.5}
          />
          <Path
            d={`${pathD} L ${xAt(lastIdx)} ${height - padY} L ${xAt(0)} ${
              height - padY
            } Z`}
            fill={fillRect}
            stroke="none"
          />
          <Path d={pathD} stroke={lineColor} strokeWidth={1.5} fill="none" />
          <Circle
            cx={xAt(lastIdx)}
            cy={yAt(lastClose)}
            r={3}
            fill={lineColor}
          />
          <SvgText
            x={width - padX}
            y={yAt(maxClose) - 2}
            fontSize="9"
            fill={colors.textDim}
            textAnchor="end"
          >
            {maxClose.toFixed(2)}
          </SvgText>
          <SvgText
            x={width - padX}
            y={yAt(minClose) + 9}
            fontSize="9"
            fill={colors.textDim}
            textAnchor="end"
          >
            {minClose.toFixed(2)}
          </SvgText>
        </Svg>
      )}
    </View>
  );
}

/* --- Indicators --- */

function IndicatorsSection({ symbol }: { symbol: string }) {
  const q = useQuery({
    queryKey: ["indicators", symbol],
    queryFn: () => api.indicators(symbol),
  });
  if (q.isLoading) return <Loading />;
  const d: IndicatorsResponse | undefined = q.data;
  if (!d || d.error) return <ErrorCard message={d?.error ?? "no data"} />;
  const s = d.snapshot;
  if (!s) return <ErrorCard message="no indicator snapshot" />;

  return (
    <View style={{ gap: spacing.md }}>
      {d.mood && d.mood.score !== null && (
        <View style={styles.card}>
          <Text style={styles.cardTitle}>Market Mood Meter</Text>
          <View style={styles.row}>
            <Text style={styles.big}>{d.mood.score?.toFixed(0)}</Text>
            <Text
              style={[
                styles.verdict,
                { color: moodColor(d.mood.score), fontWeight: "700" },
              ]}
            >
              {d.mood.label.replace(/_/g, " ")}
            </Text>
          </View>
          <View style={styles.moodTrack}>
            <View
              style={[
                styles.moodFill,
                {
                  width: `${Math.max(0, Math.min(100, d.mood.score ?? 0))}%`,
                  backgroundColor: moodColor(d.mood.score),
                },
              ]}
            />
          </View>
          {d.verdict && (
            <Text style={styles.muted}>
              RSI verdict: {d.verdict.replace(/_/g, " ")}
            </Text>
          )}
        </View>
      )}

      <View style={styles.card}>
        <Text style={styles.cardTitle}>Momentum</Text>
        <IndRow
          label="RSI (14)"
          value={s.rsi}
          format={(v) => v.toFixed(1)}
          colorFn={(v) =>
            v >= 70
              ? colors.bearish
              : v <= 30
              ? colors.bullish
              : colors.textMuted
          }
          hint={(v) =>
            v >= 70 ? "overbought" : v <= 30 ? "oversold" : "neutral"
          }
        />
        <IndRow
          label="Stoch %K"
          value={s.stoch_k}
          format={(v) => v.toFixed(1)}
          colorFn={(v) =>
            v >= 80
              ? colors.bearish
              : v <= 20
              ? colors.bullish
              : colors.textMuted
          }
          hint={(v) =>
            v >= 80 ? "overbought" : v <= 20 ? "oversold" : "neutral"
          }
        />
        <IndRow
          label="Williams %R"
          value={s.williams_r}
          format={(v) => v.toFixed(1)}
          colorFn={(v) =>
            v >= -20
              ? colors.bearish
              : v <= -80
              ? colors.bullish
              : colors.textMuted
          }
          hint={(v) =>
            v >= -20 ? "overbought" : v <= -80 ? "oversold" : "neutral"
          }
        />
      </View>

      <View style={styles.card}>
        <Text style={styles.cardTitle}>Trend / Volatility</Text>
        <IndRow
          label="MACD line"
          value={s.macd_line}
          format={(v) => v.toFixed(3)}
          colorFn={(v) => (v >= 0 ? colors.bullish : colors.bearish)}
        />
        <IndRow
          label="MACD hist"
          value={s.macd_hist}
          format={(v) => v.toFixed(3)}
          colorFn={(v) => (v >= 0 ? colors.bullish : colors.bearish)}
          hint={(v) => (v >= 0 ? "above signal" : "below signal")}
        />
        <IndRow
          label="Bollinger %B"
          value={s.bb_pct}
          format={(v) => (v * 100).toFixed(0) + "%"}
          colorFn={(v) =>
            v >= 1
              ? colors.bearish
              : v <= 0
              ? colors.bullish
              : colors.textMuted
          }
          hint={(v) =>
            v >= 1
              ? "above upper band"
              : v <= 0
              ? "below lower band"
              : "in band"
          }
        />
      </View>

      <View style={styles.card}>
        <Text style={styles.cardTitle}>Rate of Change</Text>
        <IndRow
          label="10-day"
          value={s.roc_10}
          format={(v) => `${v >= 0 ? "+" : ""}${v.toFixed(2)}%`}
          colorFn={(v) => (v >= 0 ? colors.bullish : colors.bearish)}
        />
        <IndRow
          label="21-day"
          value={s.roc_21}
          format={(v) => `${v >= 0 ? "+" : ""}${v.toFixed(2)}%`}
          colorFn={(v) => (v >= 0 ? colors.bullish : colors.bearish)}
        />
        <IndRow
          label="63-day"
          value={s.roc_63}
          format={(v) => `${v >= 0 ? "+" : ""}${v.toFixed(2)}%`}
          colorFn={(v) => (v >= 0 ? colors.bullish : colors.bearish)}
        />
      </View>

      <MultiTimeframeCard symbol={symbol} />
    </View>
  );
}

function MultiTimeframeCard({ symbol }: { symbol: string }) {
  const q = useQuery({
    queryKey: ["multi-tf", symbol],
    queryFn: () => api.multiTf(symbol),
  });
  if (q.isLoading) return null;
  const d: MultiTFResponse | undefined = q.data;
  if (!d || !d.timeframes) return null;
  const tfKeys = Object.keys(d.timeframes);
  if (!tfKeys.length) return null;

  const alignColor =
    d.alignment === "bullish"
      ? colors.bullish
      : d.alignment === "bearish"
      ? colors.bearish
      : colors.amber;

  return (
    <View style={styles.card}>
      <Text style={styles.cardTitle}>Multi-Timeframe Alignment</Text>
      {d.alignment && (
        <Text
          style={[styles.mono, { color: alignColor, marginBottom: spacing.sm }]}
        >
          {d.alignment.toUpperCase()} · strength{" "}
          {((d.alignment_strength ?? 0) * 100).toFixed(0)}%
        </Text>
      )}
      {tfKeys.map((key) => {
        const tf = d.timeframes[key];
        const color =
          tf.trend === "bullish"
            ? colors.bullish
            : tf.trend === "bearish"
            ? colors.bearish
            : tf.trend.startsWith("turning")
            ? colors.amber
            : colors.textMuted;
        return (
          <View
            key={key}
            style={{
              paddingVertical: 6,
              borderBottomColor: colors.borderSubtle,
              borderBottomWidth: 1,
            }}
          >
            <View style={styles.row}>
              <Text style={styles.mono}>{tf.label}</Text>
              <Text style={[styles.mono, { color }]}>
                {tf.trend.replace(/_/g, " ")}
              </Text>
            </View>
            <Text style={[styles.muted, { fontSize: 11, marginTop: 2 }]}>
              {tf.summary}
            </Text>
          </View>
        );
      })}
    </View>
  );
}

function IndRow({
  label,
  value,
  format,
  colorFn,
  hint,
}: {
  label: string;
  value: number | null;
  format: (v: number) => string;
  colorFn: (v: number) => string;
  hint?: (v: number) => string;
}) {
  if (value === null || value === undefined) {
    return (
      <View style={styles.retRow}>
        <Text style={styles.muted}>{label}</Text>
        <Text style={styles.muted}>--</Text>
      </View>
    );
  }
  return (
    <View style={styles.retRow}>
      <Text style={styles.muted}>{label}</Text>
      <View style={{ flexDirection: "row", gap: spacing.md, alignItems: "center" }}>
        {hint && (
          <Text style={[styles.muted, { fontSize: 11 }]}>{hint(value)}</Text>
        )}
        <Text style={[styles.mono, { color: colorFn(value) }]}>
          {format(value)}
        </Text>
      </View>
    </View>
  );
}

function moodColor(score: number | null | undefined): string {
  if (score === null || score === undefined) return colors.textDim;
  if (score >= 65) return colors.bullish;
  if (score >= 45) return colors.amber;
  return colors.bearish;
}

/* --- AI Agent buttons + modal --- */

function AgentButtons({ symbol }: { symbol: string }) {
  const [activeTopic, setActiveTopic] = useState<AgentTopic | null>(null);
  const topicsQ = useQuery({
    queryKey: ["agent-topics"],
    queryFn: api.agentTopics,
  });
  const topics = Array.isArray(topicsQ.data) ? topicsQ.data : [];
  if (!topics.length) return null;

  return (
    <View style={styles.card}>
      <Text style={styles.cardTitle}>AI Analyst</Text>
      <View style={styles.agentGrid}>
        {topics.map((t) => (
          <Pressable
            key={t.key}
            onPress={() => setActiveTopic(t)}
            style={({ pressed }) => [
              styles.agentBtn,
              pressed && { opacity: 0.6 },
            ]}
          >
            <Text style={styles.agentBtnText}>{t.label}</Text>
          </Pressable>
        ))}
      </View>
      <AgentSheet
        symbol={symbol}
        topic={activeTopic}
        onClose={() => setActiveTopic(null)}
      />
    </View>
  );
}

function AgentSheet({
  symbol,
  topic,
  onClose,
}: {
  symbol: string;
  topic: AgentTopic | null;
  onClose: () => void;
}) {
  const q = useQuery({
    enabled: topic !== null,
    queryKey: ["agent", symbol, topic?.key],
    queryFn: () => api.agent(symbol, topic!.key),
  });

  return (
    <Modal
      visible={topic !== null}
      animationType="slide"
      transparent
      onRequestClose={onClose}
    >
      <SafeAreaView style={styles.sheetBackdrop} edges={["top", "bottom"]}>
        <View style={styles.sheet}>
          <View style={styles.sheetHeader}>
            <Text style={styles.sheetTitle} numberOfLines={1}>
              {topic?.label} · {symbol}
            </Text>
            <Pressable onPress={onClose} hitSlop={10}>
              <Text style={{ color: colors.primary, fontSize: 16 }}>Done</Text>
            </Pressable>
          </View>
          <ScrollView contentContainerStyle={{ padding: spacing.lg }}>
            {q.isLoading && <Loading />}
            {q.data?.error && (
              <Text style={{ color: colors.amber }}>{q.data.error}</Text>
            )}
            {q.data?.markdown && (
              <Text style={styles.agentBody}>{q.data.markdown}</Text>
            )}
            {q.data?.model && (
              <Text style={[styles.muted, { marginTop: spacing.lg }]}>
                Model: {q.data.model}
              </Text>
            )}
          </ScrollView>
        </View>
      </SafeAreaView>
    </Modal>
  );
}

/* --- Seasonality --- */

const MONTH_LABELS = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];

const SAMPLE_OPTIONS: (number | "all")[] = [5, 10, 15, 20, 25, "all"];

type Aggregate = {
  label: string;
  avg_pct: number | null;
  win_rate: number | null;
};

function SeasonalitySection({ symbol }: { symbol: string }) {
  const q = useQuery({
    queryKey: ["seasonality", symbol],
    queryFn: () => api.seasonality(symbol),
  });
  const [sampleSize, setSampleSize] = useState<number | "all">(10);

  if (q.isLoading) return <Loading />;
  const d = q.data;
  if (!d || d.error) return <ErrorCard message={d?.error ?? "no data"} />;

  const fullHeatmap = (d.heatmap ?? [])
    .slice()
    .sort((a, b) => b.year - a.year);
  const rows =
    sampleSize === "all" ? fullHeatmap : fullHeatmap.slice(0, sampleSize as number);

  const aggregates: Aggregate[] = MONTH_LABELS.map((label) => {
    const values: number[] = [];
    for (const row of rows) {
      const v = row[label];
      if (typeof v === "number") values.push(v);
    }
    if (!values.length) return { label, avg_pct: null, win_rate: null };
    const avg = values.reduce((a, b) => a + b, 0) / values.length;
    const wins = values.filter((v) => v > 0).length;
    return { label, avg_pct: avg, win_rate: (wins / values.length) * 100 };
  });

  return (
    <View style={{ gap: spacing.md }}>
      <Text style={styles.muted}>
        {fullHeatmap.length} years of history · showing {rows.length}
      </Text>

      <View style={styles.sampleBar}>
        {SAMPLE_OPTIONS.map((opt) => {
          const active = sampleSize === opt;
          return (
            <Pressable
              key={String(opt)}
              onPress={() => setSampleSize(opt)}
              style={[styles.sampleBtn, active && styles.sampleBtnActive]}
            >
              <Text
                style={[
                  styles.sampleBtnText,
                  active && styles.sampleBtnTextActive,
                ]}
              >
                {opt === "all" ? "All" : opt}
              </Text>
            </Pressable>
          );
        })}
      </View>

      <ScrollView
        horizontal
        showsHorizontalScrollIndicator
        style={styles.seasonTableWrap}
      >
        <View>
          <View style={[styles.sRow, styles.sHeaderRow]}>
            <View style={[styles.sCellYear, styles.sHeaderCell]}>
              <Text style={styles.sHeaderText}>Year</Text>
            </View>
            {MONTH_LABELS.map((m) => (
              <View key={m} style={[styles.sCell, styles.sHeaderCell]}>
                <Text style={styles.sHeaderText}>{m}</Text>
              </View>
            ))}
          </View>

          <View style={[styles.sRow, styles.sAggRow]}>
            <View style={styles.sCellYear}>
              <Text style={styles.sAggLabel}>Probability %</Text>
            </View>
            {aggregates.map((m) => (
              <View
                key={m.label}
                style={[
                  styles.sCell,
                  { backgroundColor: probabilityCellBg(m.win_rate) },
                ]}
              >
                {m.win_rate !== null ? (
                  <Text
                    style={[
                      styles.sCellText,
                      {
                        color:
                          m.win_rate >= 50 ? colors.bullish : colors.bearish,
                      },
                    ]}
                  >
                    {m.win_rate >= 50 ? "▲" : "▼"} {m.win_rate.toFixed(0)}%
                  </Text>
                ) : (
                  <Text style={styles.sCellDim}>--</Text>
                )}
              </View>
            ))}
          </View>

          <View style={[styles.sRow, styles.sAggRow, styles.sAggRowBorder]}>
            <View style={styles.sCellYear}>
              <Text style={styles.sAggLabel}>Avg return %</Text>
            </View>
            {aggregates.map((m) => (
              <View
                key={m.label}
                style={[
                  styles.sCell,
                  { backgroundColor: heatCellBg(m.avg_pct) },
                ]}
              >
                {m.avg_pct !== null ? (
                  <Text
                    style={[
                      styles.sCellText,
                      {
                        color:
                          m.avg_pct >= 0 ? colors.bullish : colors.bearish,
                      },
                    ]}
                  >
                    {m.avg_pct > 0 ? "+" : ""}
                    {m.avg_pct.toFixed(2)}%
                  </Text>
                ) : (
                  <Text style={styles.sCellDim}>--</Text>
                )}
              </View>
            ))}
          </View>

          {rows.map((row: SeasonalityHeatmapRow) => (
            <View key={row.year} style={styles.sRow}>
              <View style={styles.sCellYear}>
                <Text style={styles.sYearText}>{row.year}</Text>
              </View>
              {MONTH_LABELS.map((m) => {
                const v = row[m];
                return (
                  <View
                    key={m}
                    style={[styles.sCell, { backgroundColor: heatCellBg(v) }]}
                  >
                    {typeof v === "number" ? (
                      <Text
                        style={[
                          styles.sCellText,
                          {
                            color: v >= 0 ? colors.bullish : colors.bearish,
                          },
                        ]}
                      >
                        {v > 0 ? "+" : ""}
                        {v.toFixed(2)}%
                      </Text>
                    ) : (
                      <Text style={styles.sCellDim}>--</Text>
                    )}
                  </View>
                );
              })}
            </View>
          ))}
        </View>
      </ScrollView>

      {d.best_month && (
        <Text style={styles.muted}>
          Best: {d.best_month.label} · Worst: {d.worst_month?.label ?? "-"}
        </Text>
      )}
    </View>
  );
}

function probabilityCellBg(v: number | null): string {
  if (v === null) return "transparent";
  if (v >= 50) {
    const strength = Math.min(1, (v - 50) / 50);
    return `rgba(52, 211, 153, ${0.12 + strength * 0.4})`;
  }
  const strength = Math.min(1, (50 - v) / 50);
  return `rgba(248, 113, 113, ${0.12 + strength * 0.4})`;
}

function heatCellBg(v: number | null | undefined): string {
  if (v === null || v === undefined) return "transparent";
  const clamped = Math.max(-10, Math.min(10, v)) / 10;
  if (clamped > 0) return `rgba(52, 211, 153, ${0.15 + clamped * 0.5})`;
  return `rgba(248, 113, 113, ${0.15 - clamped * 0.5})`;
}

/* --- Fundamentals --- */

function FundamentalsSection({ symbol }: { symbol: string }) {
  const q = useQuery({
    queryKey: ["fundamentals", symbol],
    queryFn: () => api.fundamentals(symbol),
  });
  if (q.isLoading) return <Loading />;
  const d = q.data;
  if (!d || d.error) return <ErrorCard message={d?.error ?? "no data"} />;
  const h = d.header;
  if (!h) return <ErrorCard message="no header" />;
  if (!d.has_fundamentals) {
    return (
      <View style={[styles.card, { borderColor: colors.amber, borderWidth: 1 }]}>
        <Text style={[styles.cardTitle, { color: colors.amber }]}>
          FMP Starter plan required
        </Text>
        <Text style={styles.muted}>
          Fundamentals (income statement, balance sheet, enterprise value)
          need an FMP Starter key. Panels populate automatically once the
          key is configured on the backend.
        </Text>
      </View>
    );
  }
  return (
    <View style={{ gap: spacing.md }}>
      <View style={styles.card}>
        <Text style={styles.cardTitle}>{h.name || symbol}</Text>
        <Text style={styles.muted}>
          {[h.sector, h.industry].filter(Boolean).join(" · ") || "—"}
        </Text>
        <View style={styles.retRow}>
          <Text style={styles.muted}>Market Cap</Text>
          <Text style={styles.mono}>{fmtMoney(h.market_cap)}</Text>
        </View>
        <View style={styles.retRow}>
          <Text style={styles.muted}>Price</Text>
          <Text style={styles.mono}>${h.price?.toFixed(2) ?? "--"}</Text>
        </View>
        <View style={styles.retRow}>
          <Text style={styles.muted}>EPS (TTM)</Text>
          <Text style={styles.mono}>{h.eps_ttm?.toFixed(2) ?? "--"}</Text>
        </View>
        <View style={styles.retRow}>
          <Text style={styles.muted}>P/E (TTM)</Text>
          <Text style={styles.mono}>{h.pe_ttm?.toFixed(2) ?? "--"}</Text>
        </View>
      </View>
    </View>
  );
}

function fmtMoney(n: number | undefined | null) {
  if (!n) return "--";
  if (n >= 1e12) return `$${(n / 1e12).toFixed(2)}T`;
  if (n >= 1e9) return `$${(n / 1e9).toFixed(1)}B`;
  if (n >= 1e6) return `$${(n / 1e6).toFixed(1)}M`;
  return `$${n.toFixed(2)}`;
}

/* --- News --- */

function NewsSection({ symbol }: { symbol: string }) {
  const q = useQuery({
    queryKey: ["news", symbol],
    queryFn: () => api.news(symbol),
  });
  if (q.isLoading) return <Loading />;
  const items = q.data?.articles ?? [];
  if (items.length === 0) {
    return <ErrorCard message={`No news mentioning ${symbol}.`} />;
  }
  return (
    <View style={{ gap: spacing.sm }}>
      {items.map((a, i) => (
        <View key={i} style={styles.card}>
          <View style={{ flexDirection: "row", gap: spacing.sm }}>
            <SentimentBadge s={a.sentiment} />
            <View style={{ flex: 1 }}>
              <Text style={styles.newsTitle}>{a.title}</Text>
              <Text style={styles.newsMeta}>
                {a.source} · {a.pub_date?.slice(0, 16)}
              </Text>
            </View>
          </View>
        </View>
      ))}
    </View>
  );
}

function SentimentBadge({ s }: { s: string }) {
  const c =
    s === "positive"
      ? colors.bullish
      : s === "negative"
      ? colors.bearish
      : colors.textMuted;
  return (
    <View
      style={{ width: 8, height: "100%", backgroundColor: c, borderRadius: 2 }}
    />
  );
}

/* --- Share button --- */

function ShareButton({ symbol }: { symbol: string }) {
  const onPress = async () => {
    try {
      const webHost =
        API_BASE.replace("api", "app")
          .replace("onrender.com", "vercel.app") ||
        "https://momentum-signal-engine.vercel.app";
      const url = `${webHost.replace(/\/$/, "")}/instrument/${symbol}`;
      await Share.share({
        message: `${symbol} on Momentum Signal Engine — ${url}`,
        url,
        title: symbol,
      });
    } catch {
      // user cancelled
    }
  };
  return (
    <Pressable
      onPress={onPress}
      hitSlop={10}
      style={{ paddingHorizontal: spacing.sm, paddingVertical: spacing.sm }}
    >
      <Text style={{ color: colors.primary, fontSize: 18 }}>↗</Text>
    </Pressable>
  );
}

/* --- Pattern tab --- */

function PatternSection({ symbol }: { symbol: string }) {
  const chartQ = useQuery({
    queryKey: ["chart-pattern", symbol],
    queryFn: () => api.chart(symbol, 200),
  });
  const fibQ = useQuery({
    queryKey: ["fib", symbol],
    queryFn: () => api.fibonacci(symbol),
  });
  const ichiQ = useQuery({
    queryKey: ["ichi", symbol],
    queryFn: () => api.ichimoku(symbol),
  });
  const vpQ = useQuery({
    queryKey: ["vp", symbol],
    queryFn: () => api.volumeProfile(symbol),
  });

  if (chartQ.isLoading) return <Loading />;
  const ta = (chartQ.data as { technical_analysis?: any })?.technical_analysis;

  return (
    <View style={{ gap: spacing.md }}>
      {ta?.trend_summary && (
        <View style={styles.card}>
          <Text style={styles.cardTitle}>Trend Summary</Text>
          <Text style={styles.bullet}>{ta.trend_summary}</Text>
        </View>
      )}

      {ta && (
        <View style={styles.card}>
          <Text style={styles.cardTitle}>Support / Resistance</Text>
          {(ta.resistance_levels ?? []).slice(0, 5).map((r: any, i: number) => (
            <LevelRow key={`r${i}`} label="R" level={r} color={colors.bearish} />
          ))}
          {(ta.support_levels ?? []).slice(0, 5).map((s: any, i: number) => (
            <LevelRow key={`s${i}`} label="S" level={s} color={colors.bullish} />
          ))}
          {(ta.resistance_levels?.length ?? 0) +
            (ta.support_levels?.length ?? 0) ===
            0 && <Text style={styles.muted}>No clear levels detected.</Text>}
        </View>
      )}

      {ta && ta.patterns && ta.patterns.length > 0 && (
        <View style={styles.card}>
          <Text style={styles.cardTitle}>Chart Patterns</Text>
          {ta.patterns.slice(0, 4).map((p: any, i: number) => (
            <View
              key={i}
              style={[styles.retRow, { flexDirection: "column", gap: 2 }]}
            >
              <View
                style={{
                  flexDirection: "row",
                  justifyContent: "space-between",
                  width: "100%",
                }}
              >
                <Text style={[styles.mono, { color: biasColor(p.bias) }]}>
                  {String(p.pattern_type).replace(/_/g, " ")}
                </Text>
                <Text style={styles.muted}>
                  {(p.confidence * 100).toFixed(0)}%
                  {p.target_price ? ` · tgt $${p.target_price.toFixed(2)}` : ""}
                </Text>
              </View>
              {p.description && (
                <Text style={[styles.muted, { fontSize: 11 }]}>
                  {p.description}
                </Text>
              )}
            </View>
          ))}
        </View>
      )}

      {ta && ta.trendlines && ta.trendlines.length > 0 && (
        <View style={styles.card}>
          <Text style={styles.cardTitle}>Trendlines</Text>
          {ta.trendlines.slice(0, 5).map((t: any, i: number) => (
            <View key={i} style={styles.retRow}>
              <Text
                style={[
                  styles.mono,
                  {
                    color:
                      t.trend_type === "uptrend"
                        ? colors.bullish
                        : colors.bearish,
                  },
                ]}
              >
                {t.trend_type} · {t.touches} touches
              </Text>
              <Text style={styles.muted}>
                ${t.start_price?.toFixed(2)} → ${t.end_price?.toFixed(2)}
              </Text>
            </View>
          ))}
        </View>
      )}

      <FibonacciCard data={fibQ.data} loading={fibQ.isLoading} />
      <IchimokuCard data={ichiQ.data} loading={ichiQ.isLoading} />
      <VolumeProfileCard data={vpQ.data} loading={vpQ.isLoading} />
    </View>
  );
}

function LevelRow({
  label,
  level,
  color,
}: {
  label: string;
  level: { price: number; strength: number; touches: number };
  color: string;
}) {
  return (
    <View style={styles.retRow}>
      <Text style={[styles.mono, { color }]}>
        {label} ${level.price.toFixed(2)}
      </Text>
      <Text style={styles.muted}>
        {level.touches} touches · str {(level.strength * 100).toFixed(0)}%
      </Text>
    </View>
  );
}

function biasColor(b: string): string {
  if (b === "bullish") return colors.bullish;
  if (b === "bearish") return colors.bearish;
  return colors.textMuted;
}

function FibonacciCard({
  data,
  loading,
}: {
  data: FibonacciResponse | undefined;
  loading: boolean;
}) {
  if (loading) return null;
  if (!data || data.error || !data.levels) return null;
  const levelEntries = Object.entries(data.levels);
  return (
    <View style={styles.card}>
      <Text style={styles.cardTitle}>Fibonacci · {data.trend ?? ""}</Text>
      <Text style={styles.muted}>
        Swing high ${data.high?.toFixed(2)} → low ${data.low?.toFixed(2)}
      </Text>
      {levelEntries.map(([k, v]) => {
        const isNearest = k === data.nearest_level;
        return (
          <View key={k} style={styles.retRow}>
            <Text
              style={[
                styles.mono,
                isNearest && { color: colors.amber, fontWeight: "700" },
              ]}
            >
              {k}
            </Text>
            <Text
              style={[
                styles.mono,
                isNearest && { color: colors.amber, fontWeight: "700" },
              ]}
            >
              ${v.toFixed(2)}
              {isNearest ? "  ← nearest" : ""}
            </Text>
          </View>
        );
      })}
    </View>
  );
}

function IchimokuCard({
  data,
  loading,
}: {
  data: IchimokuResponse | undefined;
  loading: boolean;
}) {
  if (loading) return null;
  if (!data || data.error) return null;
  const signalColor =
    data.signal === "bullish"
      ? colors.bullish
      : data.signal === "bearish"
      ? colors.bearish
      : colors.amber;
  return (
    <View style={styles.card}>
      <Text style={styles.cardTitle}>Ichimoku</Text>
      <View style={styles.retRow}>
        <Text style={styles.muted}>Signal</Text>
        <Text style={[styles.mono, { color: signalColor }]}>
          {data.signal?.replace(/_/g, " ")}
        </Text>
      </View>
      <View style={styles.retRow}>
        <Text style={styles.muted}>TK cross</Text>
        <Text
          style={[
            styles.mono,
            {
              color:
                data.tk_cross === "bullish" ? colors.bullish : colors.bearish,
            },
          ]}
        >
          {data.tk_cross}
        </Text>
      </View>
      <View style={styles.retRow}>
        <Text style={styles.muted}>Tenkan / Kijun</Text>
        <Text style={styles.mono}>
          ${data.tenkan?.toFixed(2)} / ${data.kijun?.toFixed(2)}
        </Text>
      </View>
      <View style={styles.retRow}>
        <Text style={styles.muted}>Cloud</Text>
        <Text style={styles.mono}>
          ${data.cloud_bottom?.toFixed(2)} – ${data.cloud_top?.toFixed(2)}
        </Text>
      </View>
    </View>
  );
}

function VolumeProfileCard({
  data,
  loading,
}: {
  data: VolumeProfileResponse | undefined;
  loading: boolean;
}) {
  if (loading) return null;
  if (!data || data.error || !data.profile) return null;
  const maxVol = Math.max(...data.profile.map((b) => b.volume), 1);
  const current = data.current ?? 0;
  const poc = data.poc ?? 0;
  return (
    <View style={styles.card}>
      <Text style={styles.cardTitle}>Volume Profile · POC ${poc.toFixed(2)}</Text>
      <Text style={styles.muted}>
        Value area ${data.value_area_low?.toFixed(2)} – $
        {data.value_area_high?.toFixed(2)}
      </Text>
      <View style={{ marginTop: spacing.sm, gap: 2 }}>
        {[...data.profile]
          .slice()
          .reverse()
          .map((b, i) => {
            const pct = b.volume / maxVol;
            const isCurrent =
              current >= b.price_low && current < b.price_high;
            const isPoc = poc >= b.price_low && poc < b.price_high;
            return (
              <View
                key={i}
                style={{
                  flexDirection: "row",
                  alignItems: "center",
                  gap: spacing.sm,
                }}
              >
                <Text
                  style={[
                    styles.muted,
                    { width: 60, fontSize: 10, fontVariant: ["tabular-nums"] },
                  ]}
                >
                  ${b.price_mid.toFixed(1)}
                </Text>
                <View style={{ flex: 1 }}>
                  <View
                    style={{
                      width: `${pct * 100}%`,
                      height: 8,
                      backgroundColor: isPoc
                        ? colors.amber
                        : isCurrent
                        ? colors.primary
                        : colors.bgCard,
                      borderRadius: 2,
                    }}
                  />
                </View>
              </View>
            );
          })}
      </View>
    </View>
  );
}

/* --- Earnings tab (events + transcripts) --- */

function EarningsSection({ symbol }: { symbol: string }) {
  const eventsQ = useQuery({
    queryKey: ["events", symbol],
    queryFn: () => api.events(symbol),
  });
  const transcriptsQ = useQuery({
    queryKey: ["transcripts", symbol],
    queryFn: () => api.transcripts(symbol),
  });
  const [openQuarter, setOpenQuarter] = useState<TranscriptQuarter | null>(
    null,
  );

  if (eventsQ.isLoading) return <Loading />;
  const e: EventsResponse | undefined = eventsQ.data;
  if (!e) return <ErrorCard message="no events" />;

  const quarters = transcriptsQ.data?.quarters ?? [];

  return (
    <View style={{ gap: spacing.md }}>
      {e.next_earnings && (
        <View
          style={[styles.card, { borderColor: colors.primary, borderWidth: 1 }]}
        >
          <Text style={[styles.cardTitle, { color: colors.primary }]}>
            Next Earnings
          </Text>
          <Text style={styles.bigMono}>{e.next_earnings.date}</Text>
          <Text style={styles.muted}>
            {e.next_earnings.eps_estimated
              ? `EPS est $${e.next_earnings.eps_estimated.toFixed(2)}`
              : "EPS est --"}
            {e.next_earnings.revenue_estimated
              ? ` · Rev est ${fmtMoney(e.next_earnings.revenue_estimated)}`
              : ""}
          </Text>
        </View>
      )}

      {e.recent_earnings.length > 0 && (
        <View style={styles.card}>
          <Text style={styles.cardTitle}>Recent Earnings</Text>
          {e.recent_earnings.map((r, i) => (
            <View key={i} style={styles.retRow}>
              <Text style={styles.mono}>{r.date}</Text>
              <View style={{ flexDirection: "row", gap: spacing.md }}>
                <Text style={styles.muted}>
                  EPS {r.eps?.toFixed(2) ?? "--"}
                </Text>
                {r.surprise_pct !== null && (
                  <Text
                    style={[
                      styles.mono,
                      {
                        color:
                          (r.surprise_pct ?? 0) >= 0
                            ? colors.bullish
                            : colors.bearish,
                      },
                    ]}
                  >
                    {r.surprise_pct >= 0 ? "+" : ""}
                    {r.surprise_pct.toFixed(1)}%
                  </Text>
                )}
              </View>
            </View>
          ))}
        </View>
      )}

      {e.recent_dividends.length > 0 && (
        <View style={styles.card}>
          <Text style={styles.cardTitle}>Dividends</Text>
          {e.recent_dividends.map((d, i) => (
            <View key={i} style={styles.retRow}>
              <Text style={styles.mono}>{d.date}</Text>
              <Text style={styles.mono}>
                ${d.dividend?.toFixed(2) ?? "--"}
              </Text>
            </View>
          ))}
        </View>
      )}

      {e.recent_splits.length > 0 && (
        <View style={styles.card}>
          <Text style={styles.cardTitle}>Stock Splits</Text>
          {e.recent_splits.map((s, i) => (
            <View key={i} style={styles.retRow}>
              <Text style={styles.mono}>{s.date}</Text>
              <Text style={styles.mono}>{s.ratio ?? "--"}</Text>
            </View>
          ))}
        </View>
      )}

      <View style={styles.card}>
        <Text style={styles.cardTitle}>Earnings Call Summaries</Text>
        {transcriptsQ.isLoading ? (
          <ActivityIndicator color={colors.primary} />
        ) : quarters.length === 0 ? (
          <Text style={styles.muted}>
            No transcripts available (needs FMP Starter).
          </Text>
        ) : (
          <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 6 }}>
            {quarters.slice(0, 12).map((q) => (
              <Pressable
                key={`${q.year}-${q.quarter}`}
                onPress={() => setOpenQuarter(q)}
                style={styles.quarterBtn}
              >
                <Text style={styles.quarterBtnText}>
                  Q{q.quarter} {q.year}
                </Text>
              </Pressable>
            ))}
          </View>
        )}
      </View>

      <TranscriptSheet
        symbol={symbol}
        quarter={openQuarter}
        onClose={() => setOpenQuarter(null)}
      />
    </View>
  );
}

function TranscriptSheet({
  symbol,
  quarter,
  onClose,
}: {
  symbol: string;
  quarter: TranscriptQuarter | null;
  onClose: () => void;
}) {
  const q = useQuery({
    enabled: quarter !== null,
    queryKey: [
      "transcript",
      symbol,
      quarter?.year,
      quarter?.quarter,
    ],
    queryFn: () => api.transcript(symbol, quarter!.year, quarter!.quarter),
  });
  return (
    <Modal
      visible={quarter !== null}
      animationType="slide"
      transparent
      onRequestClose={onClose}
    >
      <SafeAreaView style={styles.sheetBackdrop} edges={["top", "bottom"]}>
        <View style={styles.sheet}>
          <View style={styles.sheetHeader}>
            <Text style={styles.sheetTitle} numberOfLines={1}>
              {symbol} · Q{quarter?.quarter} {quarter?.year}
            </Text>
            <Pressable onPress={onClose} hitSlop={10}>
              <Text style={{ color: colors.primary, fontSize: 16 }}>Done</Text>
            </Pressable>
          </View>
          <ScrollView contentContainerStyle={{ padding: spacing.lg }}>
            {q.isLoading && <Loading />}
            {q.data?.error && (
              <Text style={{ color: colors.amber }}>{q.data.error}</Text>
            )}
            {q.data?.markdown && (
              <Text style={styles.agentBody}>{q.data.markdown}</Text>
            )}
            {q.data?.transcript_truncated && (
              <Text style={[styles.muted, { marginTop: spacing.md }]}>
                Transcript was truncated to fit token limits.
              </Text>
            )}
          </ScrollView>
        </View>
      </SafeAreaView>
    </Modal>
  );
}

/* --- Insider tab --- */

function InsiderSection({ symbol }: { symbol: string }) {
  const q = useQuery({
    queryKey: ["insider", symbol],
    queryFn: () => api.insiderTrades(symbol),
  });
  if (q.isLoading) return <Loading />;
  const trades = q.data?.trades ?? [];
  if (trades.length === 0) {
    return (
      <ErrorCard message="No insider trades reported for this symbol." />
    );
  }

  // Aggregate: buys vs sells in last 90 days
  const now = new Date();
  const ninetyDaysAgo = new Date(now.getTime() - 90 * 24 * 60 * 60 * 1000);
  let buyValue = 0;
  let sellValue = 0;
  for (const t of trades) {
    const d = new Date(t.filing_date);
    if (d < ninetyDaysAgo) continue;
    const isBuy = /purchase|buy|acquisition/i.test(
      `${t.transaction_type} ${t.acquired_disposed}`,
    );
    if (isBuy) buyValue += t.value;
    else sellValue += t.value;
  }
  const net = buyValue - sellValue;
  const netColor =
    net > 0 ? colors.bullish : net < 0 ? colors.bearish : colors.textMuted;

  return (
    <View style={{ gap: spacing.md }}>
      <View style={styles.card}>
        <Text style={styles.cardTitle}>Last 90 Days</Text>
        <View style={styles.retRow}>
          <Text style={styles.muted}>Buys</Text>
          <Text style={[styles.mono, { color: colors.bullish }]}>
            {fmtMoney(buyValue)}
          </Text>
        </View>
        <View style={styles.retRow}>
          <Text style={styles.muted}>Sells</Text>
          <Text style={[styles.mono, { color: colors.bearish }]}>
            {fmtMoney(sellValue)}
          </Text>
        </View>
        <View style={styles.retRow}>
          <Text style={styles.muted}>Net</Text>
          <Text style={[styles.mono, { color: netColor, fontWeight: "700" }]}>
            {net >= 0 ? "+" : ""}
            {fmtMoney(Math.abs(net))}
          </Text>
        </View>
      </View>

      <View style={styles.card}>
        <Text style={styles.cardTitle}>Recent Filings</Text>
        {trades.slice(0, 20).map((t, i) => (
          <InsiderRow key={i} trade={t} />
        ))}
      </View>
    </View>
  );
}

function InsiderRow({ trade }: { trade: InsiderTrade }) {
  const isBuy = /purchase|buy|acquisition/i.test(
    `${trade.transaction_type} ${trade.acquired_disposed}`,
  );
  const color = isBuy ? colors.bullish : colors.bearish;
  const openLink = () => {
    if (trade.link) Linking.openURL(trade.link).catch(() => {});
  };
  return (
    <Pressable
      onPress={openLink}
      style={{
        paddingVertical: 6,
        borderBottomWidth: 1,
        borderBottomColor: colors.borderSubtle,
      }}
    >
      <View style={styles.row}>
        <Text style={[styles.mono, { color }]}>
          {isBuy ? "BUY" : "SELL"}
        </Text>
        <Text style={styles.muted}>{trade.filing_date}</Text>
      </View>
      <Text style={[styles.muted, { fontSize: 11, marginTop: 2 }]}>
        {trade.reporter_name || trade.reporter_title || "Insider"}
      </Text>
      <View style={[styles.row, { marginTop: 2 }]}>
        <Text style={styles.muted}>
          {trade.shares.toLocaleString()} sh @ ${trade.price?.toFixed(2)}
        </Text>
        <Text style={[styles.mono, { color }]}>{fmtMoney(trade.value)}</Text>
      </View>
    </Pressable>
  );
}

/* --- Shared small UI --- */

function Loading() {
  return (
    <View style={{ padding: spacing.xl, alignItems: "center" }}>
      <ActivityIndicator color={colors.primary} />
    </View>
  );
}

function ErrorCard({ message }: { message: string }) {
  return (
    <View style={[styles.card, { borderColor: colors.amber, borderWidth: 1 }]}>
      <Text style={{ color: colors.amber }}>{message}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg },
  tabBarWrap: {
    borderBottomColor: colors.borderSubtle,
    borderBottomWidth: 1,
    maxHeight: 44,
    flexGrow: 0,
  },
  tabBar: {
    paddingHorizontal: spacing.md,
  },
  tab: { paddingHorizontal: spacing.md, paddingVertical: spacing.sm },
  tabActive: { borderBottomColor: colors.primary, borderBottomWidth: 2 },
  tabText: { color: colors.textMuted, fontSize: 13 },
  tabTextActive: { color: colors.primary, fontWeight: "700" },
  row: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
  },
  card: {
    backgroundColor: colors.bgElevated,
    borderRadius: radius.md,
    padding: spacing.md,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
  },
  cardTitle: {
    color: colors.textDim,
    fontSize: 11,
    fontWeight: "700",
    letterSpacing: 0.5,
    marginBottom: spacing.sm,
  },
  big: {
    color: colors.primary,
    fontSize: 40,
    fontWeight: "800",
    lineHeight: 44,
  },
  bigMono: {
    color: colors.text,
    fontSize: 24,
    fontWeight: "700",
    fontVariant: ["tabular-nums"],
  },
  verdict: {
    color: colors.textMuted,
    fontSize: 12,
    marginTop: 2,
    textTransform: "uppercase",
  },
  change: {
    fontSize: 13,
    fontVariant: ["tabular-nums"],
    marginTop: 2,
  },
  muted: { color: colors.textMuted, fontSize: 12 },
  mono: {
    color: colors.text,
    fontSize: 13,
    fontVariant: ["tabular-nums"],
  },
  barTrack: {
    height: 4,
    backgroundColor: colors.bgCard,
    borderRadius: 2,
    marginTop: 4,
  },
  barFill: { height: 4, borderRadius: 2 },
  retRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    paddingVertical: 4,
  },
  bullet: {
    color: colors.text,
    fontSize: 13,
    marginVertical: 2,
  },
  newsTitle: { color: colors.text, fontSize: 14, fontWeight: "600" },
  newsMeta: { color: colors.textDim, fontSize: 11, marginTop: 2 },

  rangeBar: {
    flexDirection: "row",
    alignSelf: "flex-start",
    borderRadius: radius.sm,
    borderWidth: 1,
    borderColor: colors.border,
    overflow: "hidden",
    marginBottom: spacing.sm,
  },
  rangeBtn: {
    paddingHorizontal: spacing.sm,
    paddingVertical: 4,
    backgroundColor: colors.bgElevated,
  },
  rangeBtnActive: { backgroundColor: colors.primaryDark },
  rangeBtnText: { color: colors.textMuted, fontSize: 11 },
  rangeBtnTextActive: { color: "#000", fontWeight: "700" },

  moodTrack: {
    height: 6,
    backgroundColor: colors.bgCard,
    borderRadius: 3,
    marginTop: spacing.sm,
    marginBottom: spacing.sm,
  },
  moodFill: { height: 6, borderRadius: 3 },

  agentGrid: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: spacing.sm,
  },
  agentBtn: {
    backgroundColor: colors.bgCard,
    borderRadius: radius.md,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderWidth: 1,
    borderColor: colors.border,
  },
  agentBtnText: { color: colors.text, fontSize: 12, fontWeight: "600" },

  quarterBtn: {
    backgroundColor: colors.bgCard,
    borderRadius: radius.sm,
    paddingHorizontal: spacing.md,
    paddingVertical: 6,
    borderWidth: 1,
    borderColor: colors.border,
  },
  quarterBtnText: {
    color: colors.text,
    fontSize: 12,
    fontWeight: "600",
    fontVariant: ["tabular-nums"],
  },

  sheetBackdrop: { flex: 1, backgroundColor: "rgba(0,0,0,0.6)" },
  sheet: {
    flex: 1,
    marginTop: 60,
    backgroundColor: colors.bg,
    borderTopLeftRadius: radius.lg,
    borderTopRightRadius: radius.lg,
    borderTopWidth: 1,
    borderLeftWidth: 1,
    borderRightWidth: 1,
    borderColor: colors.border,
  },
  sheetHeader: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
    borderBottomColor: colors.borderSubtle,
    borderBottomWidth: 1,
  },
  sheetTitle: {
    color: colors.text,
    fontSize: 15,
    fontWeight: "700",
    flex: 1,
    marginRight: spacing.md,
  },
  agentBody: {
    color: colors.text,
    fontSize: 14,
    lineHeight: 21,
  },

  sampleBar: {
    flexDirection: "row",
    alignSelf: "flex-start",
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: colors.border,
    overflow: "hidden",
  },
  sampleBtn: {
    paddingHorizontal: spacing.md,
    paddingVertical: 6,
    backgroundColor: colors.bgElevated,
  },
  sampleBtnActive: { backgroundColor: colors.primaryDark },
  sampleBtnText: { color: colors.textMuted, fontSize: 12 },
  sampleBtnTextActive: { color: "#000", fontWeight: "700" },

  seasonTableWrap: {
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    borderRadius: radius.md,
    backgroundColor: colors.bgElevated,
  },
  sRow: {
    flexDirection: "row",
    borderBottomWidth: 1,
    borderBottomColor: colors.borderSubtle,
  },
  sHeaderRow: { backgroundColor: colors.bgCard },
  sHeaderCell: { paddingVertical: 6 },
  sHeaderText: {
    color: colors.textMuted,
    fontSize: 10,
    fontWeight: "700",
    letterSpacing: 0.5,
    textAlign: "center",
  },
  sAggRow: { backgroundColor: "rgba(39,39,42,0.6)" },
  sAggRowBorder: { borderBottomColor: colors.border, borderBottomWidth: 1 },
  sAggLabel: {
    color: colors.text,
    fontSize: 11,
    fontWeight: "700",
  },
  sCellYear: {
    width: 74,
    paddingHorizontal: spacing.sm,
    paddingVertical: 6,
    justifyContent: "center",
  },
  sCell: {
    width: 64,
    paddingVertical: 6,
    justifyContent: "center",
    alignItems: "center",
  },
  sCellText: {
    fontSize: 10,
    fontVariant: ["tabular-nums"],
    fontWeight: "600",
  },
  sCellDim: { color: colors.textDim, fontSize: 10 },
  sYearText: { color: colors.textMuted, fontSize: 11, fontWeight: "600" },
});
