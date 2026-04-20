import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
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
  const qc = useQueryClient();
  const { data, isLoading, error } = useQuery({
    queryKey: ["watchlist"],
    queryFn: api.watchlist,
  });

  const remove = useMutation({
    mutationFn: async (symbol: string) => {
      const current = Array.isArray(data) ? data : [];
      const next = current.filter((s) => s !== symbol);
      await api.saveWatchlist(next);
      return next;
    },
    onMutate: async (symbol) => {
      await qc.cancelQueries({ queryKey: ["watchlist"] });
      const prev = qc.getQueryData<string[]>(["watchlist"]);
      const prevSafe = Array.isArray(prev) ? prev : [];
      qc.setQueryData<string[]>(
        ["watchlist"],
        prevSafe.filter((s) => s !== symbol),
      );
      return { prev: prevSafe };
    },
    onError: (_err, _sym, ctx) => {
      if (ctx?.prev) qc.setQueryData(["watchlist"], ctx.prev);
    },
    onSettled: () => {
      qc.invalidateQueries({ queryKey: ["watchlist"] });
    },
  });

  return (
    <SafeAreaView style={styles.container} edges={["top"]}>
      <View style={styles.header}>
        <Text style={styles.title}>Watchlist</Text>
        <Text style={styles.subtitle}>
          Tap a symbol to open · tap ✕ to remove.
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
            No symbols watched yet. Open any symbol and tap ★ in the top-right
            to add it.
          </Text>
        </View>
      ) : (
        <FlatList
          data={data}
          keyExtractor={(s) => s}
          renderItem={({ item }) => (
            <View style={styles.row}>
              <Link
                href={`/instrument/${encodeURIComponent(item)}`}
                asChild
              >
                <Pressable
                  style={({ pressed }) => [
                    styles.symbolPress,
                    pressed && { opacity: 0.6 },
                  ]}
                >
                  <Text style={styles.symbol}>{item}</Text>
                  <Text style={styles.chevron}>›</Text>
                </Pressable>
              </Link>
              <Pressable
                onPress={() => remove.mutate(item)}
                hitSlop={10}
                style={styles.removeBtn}
              >
                <Text style={styles.removeText}>✕</Text>
              </Pressable>
            </View>
          )}
        />
      )}
    </SafeAreaView>
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
    borderBottomColor: colors.borderSubtle,
    borderBottomWidth: 1,
  },
  symbolPress: {
    flex: 1,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
  },
  symbol: {
    color: colors.text,
    fontSize: 16,
    fontWeight: "700",
    fontFamily: "Menlo",
  },
  chevron: { color: colors.textDim, fontSize: 20 },
  removeBtn: {
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
    borderLeftColor: colors.borderSubtle,
    borderLeftWidth: 1,
  },
  removeText: {
    color: colors.bearish,
    fontSize: 16,
    fontWeight: "700",
  },
  muted: { color: colors.textDim, textAlign: "center", fontSize: 13 },
  errorText: { color: colors.bearish },
});
