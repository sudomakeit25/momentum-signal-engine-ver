import { useQuery } from "@tanstack/react-query";
import { Link } from "expo-router";
import {
  ActivityIndicator,
  FlatList,
  Pressable,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { api, AlertHistoryItem } from "../src/lib/api";
import { colors, radius, spacing } from "../src/lib/theme";

export default function AlertsScreen() {
  const q = useQuery({
    queryKey: ["alerts-history"],
    queryFn: () => api.alertsHistory(100, true),
  });

  return (
    <SafeAreaView style={styles.container} edges={["bottom"]}>
      {q.isLoading ? (
        <View style={styles.center}>
          <ActivityIndicator color={colors.primary} />
        </View>
      ) : !q.data || q.data.length === 0 ? (
        <View style={styles.center}>
          <Text style={styles.muted}>
            No alerts have been dispatched yet. New signals will show up here
            once the scanner starts firing.
          </Text>
        </View>
      ) : (
        <FlatList
          data={q.data}
          keyExtractor={(item, i) =>
            `${item.symbol}-${item.dispatched_at ?? i}`
          }
          renderItem={({ item }) => <AlertRow item={item} />}
          contentContainerStyle={{ paddingBottom: spacing.xxl }}
        />
      )}
    </SafeAreaView>
  );
}

function AlertRow({ item }: { item: AlertHistoryItem }) {
  const isBuy = item.action === "BUY";
  const actionColor = isBuy ? colors.bullish : colors.bearish;
  const pnl = item.pnl_pct;
  const pnlColor =
    pnl === null || pnl === undefined
      ? colors.textDim
      : pnl > 0
      ? colors.bullish
      : pnl < 0
      ? colors.bearish
      : colors.textMuted;
  return (
    <Link href={`/instrument/${item.symbol}`} asChild>
      <Pressable
        style={({ pressed }) => [styles.row, pressed && { opacity: 0.6 }]}
      >
        <View style={styles.rowTop}>
          <View style={{ flex: 1 }}>
            <View style={{ flexDirection: "row", gap: spacing.sm }}>
              <Text style={[styles.action, { color: actionColor }]}>
                {item.action}
              </Text>
              <Text style={styles.symbol}>{item.symbol}</Text>
            </View>
            <Text style={styles.setup}>
              {item.setup_type.replace(/_/g, " ")}
            </Text>
            {item.dispatched_at && (
              <Text style={styles.when}>
                {item.dispatched_at.slice(0, 16)}
                {item.channel ? ` · ${item.channel}` : ""}
              </Text>
            )}
          </View>
          <View style={{ alignItems: "flex-end" }}>
            <Text style={styles.entry}>${item.entry.toFixed(2)}</Text>
            {pnl !== null && pnl !== undefined && (
              <Text style={[styles.pnl, { color: pnlColor }]}>
                {pnl >= 0 ? "+" : ""}
                {pnl.toFixed(2)}%
              </Text>
            )}
          </View>
        </View>
      </Pressable>
    </Link>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg },
  center: {
    flex: 1,
    justifyContent: "center",
    alignItems: "center",
    padding: spacing.lg,
  },
  muted: {
    color: colors.textDim,
    textAlign: "center",
    fontSize: 13,
    lineHeight: 20,
  },
  row: {
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
    borderBottomColor: colors.borderSubtle,
    borderBottomWidth: 1,
  },
  rowTop: { flexDirection: "row", alignItems: "flex-start" },
  action: { fontSize: 13, fontWeight: "700" },
  symbol: {
    color: colors.text,
    fontSize: 13,
    fontWeight: "700",
    fontVariant: ["tabular-nums"],
  },
  setup: {
    color: colors.textMuted,
    fontSize: 11,
    marginTop: 2,
    textTransform: "capitalize",
  },
  when: { color: colors.textDim, fontSize: 10, marginTop: 2 },
  entry: {
    color: colors.text,
    fontSize: 13,
    fontVariant: ["tabular-nums"],
  },
  pnl: {
    fontSize: 12,
    fontVariant: ["tabular-nums"],
    marginTop: 2,
    fontWeight: "600",
  },
});
