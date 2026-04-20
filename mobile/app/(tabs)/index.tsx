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
  return (
    <Link href={`/instrument/${row.symbol}`} asChild>
      <Pressable style={({ pressed }) => [styles.row, pressed && { opacity: 0.7 }]}>
        <View style={{ flex: 1 }}>
          <Text style={styles.symbol}>{row.symbol}</Text>
          <Text style={styles.setups}>
            {(row.setup_types ?? []).slice(0, 2).join(" · ") || "—"}
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
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
    borderBottomColor: colors.borderSubtle,
    borderBottomWidth: 1,
    gap: spacing.md,
  },
  symbol: { color: colors.text, fontSize: 16, fontWeight: "700" },
  setups: { color: colors.textDim, fontSize: 11, marginTop: 2 },
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
