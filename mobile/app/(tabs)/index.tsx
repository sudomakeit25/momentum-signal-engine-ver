import { useQuery } from "@tanstack/react-query";
import { Link } from "expo-router";
import {
  ActivityIndicator,
  FlatList,
  RefreshControl,
  StyleSheet,
  Text,
  View,
  Pressable,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { api, ScanRow } from "../../src/lib/api";
import { colors, radius, spacing } from "../../src/lib/theme";

export default function ScannerScreen() {
  const { data, isLoading, isRefetching, refetch, error } = useQuery({
    queryKey: ["scan", 30],
    queryFn: () => api.scan(30),
  });

  return (
    <SafeAreaView style={styles.container} edges={["top"]}>
      <View style={styles.header}>
        <Text style={styles.title}>Momentum Scanner</Text>
        <Text style={styles.subtitle}>Top 30 by composite score</Text>
      </View>

      {isLoading && !data ? (
        <View style={styles.center}>
          <ActivityIndicator color={colors.primary} />
        </View>
      ) : error ? (
        <View style={styles.center}>
          <Text style={styles.errorText}>
            {(error as Error).message}
          </Text>
        </View>
      ) : (
        <FlatList
          data={data ?? []}
          keyExtractor={(item) => item.symbol}
          renderItem={({ item }) => <ScanRowItem row={item} />}
          refreshControl={
            <RefreshControl
              refreshing={isRefetching}
              onRefresh={refetch}
              tintColor={colors.primary}
            />
          }
          contentContainerStyle={{ paddingBottom: spacing.xxl }}
        />
      )}
    </SafeAreaView>
  );
}

function ScanRowItem({ row }: { row: ScanRow }) {
  const up = row.change_pct >= 0;
  const volRatio =
    row.avg_volume > 0 ? row.volume / row.avg_volume : 0;
  const volSurge = volRatio >= 2;
  const topSignal = (row.signals ?? []).sort(
    (a, b) => (b.confidence ?? 0) - (a.confidence ?? 0),
  )[0];
  const setups = (row.setup_types ?? []).map((s) => String(s).replace(/_/g, " "));

  return (
    <Link href={`/instrument/${row.symbol}`} asChild>
      <Pressable style={({ pressed }) => [styles.row, pressed && { opacity: 0.7 }]}>
        <View style={styles.rowTop}>
          <View style={{ flex: 1 }}>
            <View style={styles.symbolLine}>
              <Text style={styles.symbol}>{row.symbol}</Text>
              {topSignal && (
                <View
                  style={[
                    styles.actionChip,
                    topSignal.action === "BUY"
                      ? { backgroundColor: colors.bullish }
                      : { backgroundColor: colors.bearish },
                  ]}
                >
                  <Text style={styles.actionChipText}>
                    {topSignal.action} @ ${topSignal.entry.toFixed(2)}
                  </Text>
                </View>
              )}
            </View>
            <Text style={styles.meta} numberOfLines={1}>
              RS {row.relative_strength.toFixed(2)}
              {volSurge && (
                <Text style={styles.volSurge}>  · Vol {volRatio.toFixed(1)}×</Text>
              )}
            </Text>
          </View>
          <View style={{ alignItems: "flex-end" }}>
            <Text style={styles.price}>${row.price.toFixed(2)}</Text>
            <Text
              style={[
                styles.change,
                { color: up ? colors.bullish : colors.bearish },
              ]}
            >
              {up ? "+" : ""}
              {row.change_pct.toFixed(2)}%
            </Text>
          </View>
          <View style={styles.scoreBadge}>
            <Text style={styles.score}>{row.score.toFixed(0)}</Text>
          </View>
        </View>
        {setups.length > 0 && (
          <View style={styles.setupsRow}>
            {setups.slice(0, 4).map((s, i) => (
              <View key={i} style={styles.setupPill}>
                <Text style={styles.setupPillText}>{s}</Text>
              </View>
            ))}
            {setups.length > 4 && (
              <Text style={styles.setups}>+{setups.length - 4}</Text>
            )}
          </View>
        )}
      </Pressable>
    </Link>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg },
  center: { flex: 1, justifyContent: "center", alignItems: "center" },
  header: {
    paddingHorizontal: spacing.lg,
    paddingBottom: spacing.md,
    paddingTop: spacing.sm,
  },
  title: { color: colors.text, fontSize: 22, fontWeight: "700" },
  subtitle: { color: colors.textDim, fontSize: 12, marginTop: 2 },
  row: {
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
    borderBottomColor: colors.borderSubtle,
    borderBottomWidth: 1,
  },
  rowTop: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.md,
  },
  symbolLine: {
    flexDirection: "row",
    alignItems: "center",
    gap: spacing.sm,
    flexWrap: "wrap",
  },
  symbol: { color: colors.text, fontSize: 16, fontWeight: "700" },
  actionChip: {
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: radius.sm,
  },
  actionChipText: {
    color: "#000",
    fontSize: 10,
    fontWeight: "700",
    fontVariant: ["tabular-nums"],
  },
  meta: { color: colors.textMuted, fontSize: 11, marginTop: 3 },
  volSurge: { color: colors.amber, fontWeight: "700" },
  setups: { color: colors.textDim, fontSize: 11 },
  setupsRow: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 4,
    marginTop: spacing.sm,
  },
  setupPill: {
    backgroundColor: colors.bgCard,
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: radius.sm,
  },
  setupPillText: {
    color: colors.textMuted,
    fontSize: 10,
    textTransform: "capitalize",
  },
  price: { color: colors.text, fontSize: 14, fontVariant: ["tabular-nums"] },
  change: { fontSize: 12, fontVariant: ["tabular-nums"], marginTop: 2 },
  scoreBadge: {
    backgroundColor: colors.bgCard,
    paddingHorizontal: spacing.sm,
    paddingVertical: 4,
    borderRadius: radius.sm,
    minWidth: 40,
    alignItems: "center",
  },
  score: {
    color: colors.amber,
    fontSize: 13,
    fontWeight: "700",
    fontVariant: ["tabular-nums"],
  },
  errorText: { color: colors.bearish, padding: spacing.lg },
});
