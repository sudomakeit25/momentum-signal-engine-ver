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
import { api } from "../../src/lib/api";
import { colors, radius, spacing } from "../../src/lib/theme";

export default function WatchlistScreen() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["watchlist"],
    queryFn: api.watchlist,
  });

  return (
    <SafeAreaView style={styles.container} edges={["top"]}>
      <View style={styles.header}>
        <Text style={styles.title}>Watchlist</Text>
        <Text style={styles.subtitle}>
          Synced from the web app via Redis.
        </Text>
      </View>

      {isLoading && !data ? (
        <View style={styles.center}>
          <ActivityIndicator color={colors.primary} />
        </View>
      ) : error ? (
        <View style={styles.center}>
          <Text style={styles.errorText}>{(error as Error).message}</Text>
        </View>
      ) : !data || data.length === 0 ? (
        <View style={styles.center}>
          <Text style={styles.muted}>
            No symbols watched yet. Add them from the web app or tap a symbol
            below to open its instrument page.
          </Text>
        </View>
      ) : (
        <FlatList
          data={data}
          keyExtractor={(s) => s}
          renderItem={({ item }) => (
            <Link href={`/instrument/${encodeURIComponent(item)}`} asChild>
              <Pressable style={({ pressed }) => [styles.row, pressed && { opacity: 0.6 }]}>
                <Text style={styles.symbol}>{item}</Text>
                <Text style={styles.chevron}>›</Text>
              </Pressable>
            </Link>
          )}
        />
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg },
  center: { flex: 1, justifyContent: "center", alignItems: "center", padding: spacing.lg },
  header: {
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.sm,
    paddingBottom: spacing.md,
  },
  title: { color: colors.text, fontSize: 22, fontWeight: "700" },
  subtitle: { color: colors.textDim, fontSize: 12, marginTop: 2 },
  row: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
    borderBottomColor: colors.borderSubtle,
    borderBottomWidth: 1,
  },
  symbol: {
    color: colors.text,
    fontSize: 16,
    fontWeight: "700",
    fontFamily: "Menlo",
  },
  chevron: { color: colors.textDim, fontSize: 20 },
  muted: { color: colors.textDim, textAlign: "center", fontSize: 13 },
  errorText: { color: colors.bearish },
});
