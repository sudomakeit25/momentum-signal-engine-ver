import { useQuery } from "@tanstack/react-query";
import { Stack, useLocalSearchParams } from "expo-router";
import { useState } from "react";
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import {
  api,
  AnalyzerResponse,
  FundamentalsResponse,
  NewsResponse,
  SeasonalityResponse,
  TrendsResponse,
} from "../../src/lib/api";
import { colors, radius, spacing } from "../../src/lib/theme";

type Section = "Overview" | "Seasonality" | "Fundamentals" | "News";
const SECTIONS: Section[] = ["Overview", "Seasonality", "Fundamentals", "News"];

export default function InstrumentScreen() {
  const { symbol: rawSymbol } = useLocalSearchParams<{ symbol: string }>();
  const symbol = String(rawSymbol ?? "").toUpperCase();
  const [section, setSection] = useState<Section>("Overview");

  return (
    <SafeAreaView style={styles.container} edges={["bottom"]}>
      <Stack.Screen options={{ title: symbol }} />

      <View style={styles.tabBar}>
        {SECTIONS.map((s) => (
          <Pressable
            key={s}
            onPress={() => setSection(s)}
            style={[styles.tab, section === s && styles.tabActive]}
          >
            <Text style={[styles.tabText, section === s && styles.tabTextActive]}>
              {s}
            </Text>
          </Pressable>
        ))}
      </View>

      <ScrollView
        style={{ flex: 1 }}
        contentContainerStyle={{ padding: spacing.lg, paddingBottom: spacing.xxl }}
      >
        {section === "Overview" && <OverviewSection symbol={symbol} />}
        {section === "Seasonality" && <SeasonalitySection symbol={symbol} />}
        {section === "Fundamentals" && <FundamentalsSection symbol={symbol} />}
        {section === "News" && <NewsSection symbol={symbol} />}
      </ScrollView>
    </SafeAreaView>
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
      <View style={styles.card}>
        <View style={styles.row}>
          <View>
            <Text style={styles.muted}>Verdict</Text>
            <Text style={styles.big}>{a.grade}</Text>
            <Text style={styles.verdict}>
              {a.verdict.replace(/_/g, " ")}
            </Text>
          </View>
          <View style={{ alignItems: "flex-end" }}>
            <Text style={styles.muted}>Price</Text>
            <Text style={styles.bigMono}>${a.price.toFixed(2)}</Text>
            <Text
              style={[
                styles.change,
                { color: a.change_pct >= 0 ? colors.bullish : colors.bearish },
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

      {a.strengths && a.strengths.length > 0 && (
        <View style={[styles.card, { borderColor: colors.bullish, borderWidth: 1 }]}>
          <Text style={[styles.cardTitle, { color: colors.bullish }]}>Strengths</Text>
          {a.strengths.map((s, i) => (
            <Text key={i} style={styles.bullet}>
              • {s}
            </Text>
          ))}
        </View>
      )}
      {a.weaknesses && a.weaknesses.length > 0 && (
        <View style={[styles.card, { borderColor: colors.bearish, borderWidth: 1 }]}>
          <Text style={[styles.cardTitle, { color: colors.bearish }]}>Weaknesses</Text>
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
        <View style={[styles.barFill, { width: `${pct}%`, backgroundColor: color }]} />
      </View>
    </View>
  );
}

function RetRow({ label, value }: { label: string; value: number | null | undefined }) {
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

/* --- Seasonality --- */

function SeasonalitySection({ symbol }: { symbol: string }) {
  const q = useQuery({
    queryKey: ["seasonality", symbol],
    queryFn: () => api.seasonality(symbol),
  });
  if (q.isLoading) return <Loading />;
  const d = q.data;
  if (!d || d.error) return <ErrorCard message={d?.error ?? "no data"} />;
  const months = d.months ?? [];
  return (
    <View style={{ gap: spacing.md }}>
      <Text style={styles.muted}>
        Based on {d.years_covered ?? 0} years of history.
      </Text>
      <View style={styles.card}>
        <Text style={styles.cardTitle}>Average Return by Month</Text>
        {months.map((m) => {
          const v = m.avg_pct;
          const positive = (v ?? 0) >= 0;
          return (
            <View key={m.month} style={styles.retRow}>
              <Text style={styles.mono}>{m.label}</Text>
              <View style={{ flexDirection: "row", gap: spacing.md }}>
                <Text style={styles.muted}>
                  win {m.win_rate !== null ? m.win_rate.toFixed(0) : "-"}%
                </Text>
                <Text
                  style={[
                    styles.mono,
                    { color: v === null ? colors.textDim : positive ? colors.bullish : colors.bearish },
                  ]}
                >
                  {v === null
                    ? "--"
                    : `${positive ? "+" : ""}${v.toFixed(2)}%`}
                </Text>
              </View>
            </View>
          );
        })}
      </View>
      {d.best_month && (
        <Text style={styles.muted}>
          Best: {d.best_month.label} · Worst: {d.worst_month?.label ?? "-"}
        </Text>
      )}
    </View>
  );
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
    <View style={{ width: 8, height: "100%", backgroundColor: c, borderRadius: 2 }} />
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
  tabBar: {
    flexDirection: "row",
    borderBottomColor: colors.borderSubtle,
    borderBottomWidth: 1,
    paddingHorizontal: spacing.md,
  },
  tab: { paddingHorizontal: spacing.md, paddingVertical: spacing.sm },
  tabActive: { borderBottomColor: colors.primary, borderBottomWidth: 2 },
  tabText: { color: colors.textMuted, fontSize: 13 },
  tabTextActive: { color: colors.primary, fontWeight: "700" },
  row: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
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
});
