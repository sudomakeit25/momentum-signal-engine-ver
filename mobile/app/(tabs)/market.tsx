import { useQuery } from "@tanstack/react-query";
import { Link } from "expo-router";
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
  BreadthResponse,
  DarkPoolScanRow,
  IntradayPattern,
  OptionsFlowScanRow,
  RegimeResponse,
  SectorFlow,
  SignalSummary,
} from "../../src/lib/api";
import { colors, radius, spacing } from "../../src/lib/theme";

export default function MarketScreen() {
  const breadth = useQuery({
    queryKey: ["breadth"],
    queryFn: api.breadth,
  });
  const regime = useQuery({
    queryKey: ["regime"],
    queryFn: api.regime,
  });
  const sectors = useQuery({
    queryKey: ["sector-flow"],
    queryFn: api.sectorFlow,
  });
  const signals = useQuery({
    queryKey: ["top-signals"],
    queryFn: () => api.topSignals(15),
  });
  const darkPool = useQuery({
    queryKey: ["dark-pool"],
    queryFn: () => api.darkPoolScan(8),
  });
  const optionsFlow = useQuery({
    queryKey: ["options-flow"],
    queryFn: () => api.optionsFlowScan(8),
  });
  const ipos = useQuery({
    queryKey: ["ipos"],
    queryFn: api.ipoCalendar,
  });
  const intraday = useQuery({
    queryKey: ["intraday-patterns"],
    queryFn: api.intradayPatterns,
    refetchInterval: 60_000,
  });

  return (
    <SafeAreaView style={styles.container} edges={["top"]}>
      <View style={styles.header}>
        <Text style={styles.title}>Market</Text>
        <Text style={styles.subtitle}>Breadth, regime, sectors, flow.</Text>
      </View>
      <ScrollView
        contentContainerStyle={styles.scrollContent}
        showsVerticalScrollIndicator={false}
      >
        <IntradayCard
          data={intraday.data?.patterns ?? []}
          loading={intraday.isLoading}
        />
        <RegimeCard data={regime.data} loading={regime.isLoading} />
        <BreadthCard data={breadth.data} loading={breadth.isLoading} />
        <SectorCard data={sectors.data} loading={sectors.isLoading} />
        <SignalsCard data={signals.data} loading={signals.isLoading} />
        <DarkPoolCard data={darkPool.data} loading={darkPool.isLoading} />
        <OptionsFlowCard
          data={optionsFlow.data}
          loading={optionsFlow.isLoading}
        />
        <IpoCard
          upcoming={ipos.data?.upcoming ?? []}
          recent={ipos.data?.recent ?? []}
          loading={ipos.isLoading}
        />
      </ScrollView>
    </SafeAreaView>
  );
}

function IntradayCard({
  data,
  loading,
}: {
  data: IntradayPattern[];
  loading: boolean;
}) {
  if (loading) return <CardSkeleton title="INTRADAY REVERSALS" />;
  if (!data || data.length === 0) {
    // Hide entirely outside market hours / before any patterns are
    // detected. Avoids a stale empty card sitting at the top of the tab.
    return null;
  }
  return (
    <View style={styles.card}>
      <Text style={styles.cardTitle}>INTRADAY REVERSALS</Text>
      {data.slice(0, 10).map((p, i) => {
        const glyph = patternGlyph(p.pattern_type);
        const actionColor =
          p.action === "BUY" ? colors.bullish : colors.bearish;
        return (
          <Link
            key={`${p.symbol}-${p.pattern_type}-${i}`}
            href={`/instrument/${p.symbol}`}
            asChild
          >
            <Pressable
              style={({ pressed }) => [
                {
                  paddingVertical: 6,
                  borderBottomWidth: 1,
                  borderBottomColor: colors.borderSubtle,
                },
                pressed && { opacity: 0.6 },
              ]}
            >
              <View style={styles.row}>
                <View style={{ flexDirection: "row", gap: spacing.sm }}>
                  <Text style={[styles.mono, { color: actionColor, fontWeight: "700" }]}>
                    {glyph}
                  </Text>
                  <Text style={styles.mono}>{p.symbol}</Text>
                </View>
                <Text style={styles.mono}>${p.trigger_price.toFixed(2)}</Text>
              </View>
              <Text style={[styles.muted, { fontSize: 11, marginTop: 2 }]}>
                {patternLabel(p.pattern_type)} · move {p.move_pct >= 0 ? "+" : ""}
                {p.move_pct.toFixed(1)}% · now {p.recovery_pct >= 0 ? "+" : ""}
                {p.recovery_pct.toFixed(1)}% off extreme
              </Text>
            </Pressable>
          </Link>
        );
      })}
    </View>
  );
}

function patternGlyph(t: string): string {
  switch (t) {
    case "v_reversal":
      return "V↑";
    case "inverted_v":
      return "Λ↓";
    case "breakdown":
      return "↓↓";
    case "breakout":
      return "↑↑";
    default:
      return "";
  }
}

function patternLabel(t: string): string {
  switch (t) {
    case "v_reversal":
      return "V-reversal";
    case "inverted_v":
      return "Inverted V";
    case "breakdown":
      return "Breakdown";
    case "breakout":
      return "Breakout";
    default:
      return t;
  }
}

function RegimeCard({
  data,
  loading,
}: {
  data: RegimeResponse | undefined;
  loading: boolean;
}) {
  if (loading) return <CardSkeleton title="REGIME" />;
  if (!data) return null;
  const biasColor =
    data.recommendation?.bias === "long"
      ? colors.bullish
      : data.recommendation?.bias === "short"
      ? colors.bearish
      : colors.amber;
  return (
    <View style={styles.card}>
      <Text style={styles.cardTitle}>REGIME</Text>
      <Text style={styles.big}>{data.regime?.replace(/_/g, " ")}</Text>
      {data.description && (
        <Text style={styles.muted}>{data.description}</Text>
      )}
      <View style={styles.row}>
        <Text style={styles.muted}>SPY</Text>
        <Text style={styles.mono}>
          ${data.spy_price?.toFixed(2) ?? "--"}{" "}
          {data.spy_change_20d !== undefined && (
            <Text
              style={{
                color:
                  (data.spy_change_20d ?? 0) >= 0
                    ? colors.bullish
                    : colors.bearish,
              }}
            >
              ({data.spy_change_20d >= 0 ? "+" : ""}
              {data.spy_change_20d?.toFixed(2)}% · 20d)
            </Text>
          )}
        </Text>
      </View>
      {data.recommendation && (
        <View style={styles.row}>
          <Text style={styles.muted}>Recommendation</Text>
          <Text style={[styles.mono, { color: biasColor }]}>
            {data.recommendation.bias} · {data.recommendation.position_size}
          </Text>
        </View>
      )}
    </View>
  );
}

function BreadthCard({
  data,
  loading,
}: {
  data: BreadthResponse | undefined;
  loading: boolean;
}) {
  if (loading) return <CardSkeleton title="BREADTH" />;
  if (!data || !data.total) return null;
  const bullPct = data.bullish_pct;
  const color =
    bullPct >= 60 ? colors.bullish : bullPct <= 40 ? colors.bearish : colors.amber;
  return (
    <View style={styles.card}>
      <Text style={styles.cardTitle}>BREADTH</Text>
      <View style={styles.row}>
        <Text style={styles.muted}>Bullish</Text>
        <Text style={[styles.mono, { color }]}>
          {data.bullish}/{data.total} ({bullPct.toFixed(1)}%)
        </Text>
      </View>
      <View style={styles.barTrack}>
        <View
          style={[
            styles.barFill,
            { width: `${bullPct}%`, backgroundColor: color },
          ]}
        />
      </View>
      <View style={[styles.row, { marginTop: 4 }]}>
        <Text style={styles.muted}>Above EMA21</Text>
        <Text style={styles.mono}>
          {data.above_ema21}/{data.total} ({data.above_ema21_pct.toFixed(1)}%)
        </Text>
      </View>
    </View>
  );
}

function SectorCard({
  data,
  loading,
}: {
  data: SectorFlow[] | undefined;
  loading: boolean;
}) {
  if (loading) return <CardSkeleton title="SECTOR FLOW" />;
  if (!data || !data.length) return null;
  return (
    <View style={styles.card}>
      <Text style={styles.cardTitle}>SECTOR FLOW</Text>
      {data.slice(0, 8).map((s) => {
        const c =
          s.flow_direction === "inflow"
            ? colors.bullish
            : s.flow_direction === "outflow"
            ? colors.bearish
            : colors.textMuted;
        return (
          <View key={s.sector} style={styles.row}>
            <Text style={styles.mono} numberOfLines={1}>
              {s.sector}
            </Text>
            <View style={{ flexDirection: "row", gap: spacing.md }}>
              <Text style={styles.muted}>mom {s.momentum_count}</Text>
              <Text style={[styles.mono, { color: c }]}>
                {s.flow_direction} {(s.flow_strength * 100).toFixed(0)}%
              </Text>
            </View>
          </View>
        );
      })}
    </View>
  );
}

function SignalsCard({
  data,
  loading,
}: {
  data: SignalSummary[] | undefined;
  loading: boolean;
}) {
  if (loading) return <CardSkeleton title="TOP SIGNALS" />;
  if (!data || !data.length) return null;
  return (
    <View style={styles.card}>
      <Text style={styles.cardTitle}>TOP SIGNALS</Text>
      {data.slice(0, 10).map((s, i) => (
        <Link
          key={`${s.symbol}-${i}`}
          href={`/instrument/${s.symbol}`}
          asChild
        >
          <Pressable
            style={({ pressed }) => [
              {
                paddingVertical: 6,
                borderBottomWidth: 1,
                borderBottomColor: colors.borderSubtle,
              },
              pressed && { opacity: 0.6 },
            ]}
          >
            <View style={styles.row}>
              <View style={{ flexDirection: "row", gap: spacing.sm }}>
                <Text
                  style={[
                    styles.mono,
                    {
                      color:
                        s.action === "BUY" ? colors.bullish : colors.bearish,
                      fontWeight: "700",
                    },
                  ]}
                >
                  {s.action}
                </Text>
                <Text style={styles.mono}>{s.symbol}</Text>
              </View>
              <Text style={styles.muted}>
                {(s.confidence * 100).toFixed(0)}% · ${s.entry.toFixed(2)}
              </Text>
            </View>
            <Text style={[styles.muted, { fontSize: 11, marginTop: 2 }]}>
              {s.setup_type.replace(/_/g, " ")}
            </Text>
          </Pressable>
        </Link>
      ))}
    </View>
  );
}

function DarkPoolCard({
  data,
  loading,
}: {
  data: DarkPoolScanRow[] | undefined;
  loading: boolean;
}) {
  if (loading) return null;
  if (!data || !data.length) return null;
  return (
    <View style={styles.card}>
      <Text style={styles.cardTitle}>DARK POOL</Text>
      {data.slice(0, 8).map((r, i) => {
        const c =
          r.trend === "accumulating"
            ? colors.bullish
            : r.trend === "distributing"
            ? colors.bearish
            : colors.textMuted;
        return (
          <Link
            key={`${r.symbol}-${i}`}
            href={`/instrument/${r.symbol}`}
            asChild
          >
            <Pressable style={styles.row}>
              <Text style={styles.mono}>{r.symbol}</Text>
              <Text style={[styles.mono, { color: c }]}>
                {r.trend} · {r.recent_short_pct.toFixed(1)}% short
              </Text>
            </Pressable>
          </Link>
        );
      })}
    </View>
  );
}

function OptionsFlowCard({
  data,
  loading,
}: {
  data: OptionsFlowScanRow[] | undefined;
  loading: boolean;
}) {
  if (loading) return null;
  if (!data || !data.length) return null;
  return (
    <View style={styles.card}>
      <Text style={styles.cardTitle}>OPTIONS FLOW</Text>
      {data.slice(0, 8).map((r, i) => {
        const c =
          r.flow_sentiment === "bullish"
            ? colors.bullish
            : r.flow_sentiment === "bearish"
            ? colors.bearish
            : colors.textMuted;
        return (
          <Link
            key={`${r.symbol}-${i}`}
            href={`/instrument/${r.symbol}`}
            asChild
          >
            <Pressable style={styles.row}>
              <Text style={styles.mono}>{r.symbol}</Text>
              <Text style={[styles.mono, { color: c }]}>
                {r.flow_sentiment} · p/c {r.put_call_ratio.toFixed(2)}
              </Text>
            </Pressable>
          </Link>
        );
      })}
    </View>
  );
}

function IpoCard({
  upcoming,
  recent,
  loading,
}: {
  upcoming: { symbol: string; company: string; date: string }[];
  recent: { symbol: string; company: string; date: string }[];
  loading: boolean;
}) {
  if (loading) return null;
  if (!upcoming.length && !recent.length) return null;
  return (
    <View style={styles.card}>
      <Text style={styles.cardTitle}>IPO CALENDAR</Text>
      {upcoming.length > 0 && (
        <>
          <Text
            style={[styles.muted, { marginTop: 4, fontWeight: "700" }]}
          >
            Upcoming
          </Text>
          {upcoming.slice(0, 4).map((i) => (
            <View key={`u-${i.symbol}`} style={styles.row}>
              <Text style={styles.mono}>{i.symbol}</Text>
              <Text style={styles.muted} numberOfLines={1}>
                {i.date} · {i.company}
              </Text>
            </View>
          ))}
        </>
      )}
      {recent.length > 0 && (
        <>
          <Text
            style={[styles.muted, { marginTop: 8, fontWeight: "700" }]}
          >
            Recent
          </Text>
          {recent.slice(0, 4).map((i) => (
            <View key={`r-${i.symbol}`} style={styles.row}>
              <Text style={styles.mono}>{i.symbol}</Text>
              <Text style={styles.muted} numberOfLines={1}>
                {i.date} · {i.company}
              </Text>
            </View>
          ))}
        </>
      )}
    </View>
  );
}

function CardSkeleton({ title }: { title: string }) {
  return (
    <View style={styles.card}>
      <Text style={styles.cardTitle}>{title}</Text>
      <ActivityIndicator color={colors.primary} />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg },
  header: {
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.sm,
    paddingBottom: spacing.md,
  },
  title: { color: colors.text, fontSize: 22, fontWeight: "700" },
  subtitle: { color: colors.textDim, fontSize: 12, marginTop: 2 },
  scrollContent: {
    paddingHorizontal: spacing.lg,
    paddingBottom: spacing.xxl,
    gap: spacing.md,
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
    fontSize: 10,
    fontWeight: "700",
    letterSpacing: 0.5,
    marginBottom: spacing.sm,
  },
  big: {
    color: colors.primary,
    fontSize: 22,
    fontWeight: "800",
    textTransform: "capitalize",
  },
  row: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    paddingVertical: 4,
  },
  muted: { color: colors.textMuted, fontSize: 12 },
  mono: {
    color: colors.text,
    fontSize: 13,
    fontVariant: ["tabular-nums"],
  },
  barTrack: {
    height: 5,
    backgroundColor: colors.bgCard,
    borderRadius: 3,
    marginTop: 4,
  },
  barFill: { height: 5, borderRadius: 3 },
});
