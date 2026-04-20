import { useState } from "react";
import { Link, useRouter } from "expo-router";
import {
  FlatList,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { colors, radius, spacing } from "../../src/lib/theme";

const POPULAR = [
  "AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA", "AMD",
  "RKLB", "MU", "WDC", "AVGO", "INTC", "SPY", "QQQ",
  "LLY", "UNH", "JPM", "V", "XOM",
];

const FOREX = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD"];
const COMMODITIES = ["GCUSD", "SIUSD", "CLUSD", "NGUSD"];
const INDICES = ["^GSPC", "^DJI", "^IXIC", "^VIX"];

export default function SearchScreen() {
  const router = useRouter();
  const [query, setQuery] = useState("");

  const submit = () => {
    const s = query.trim().toUpperCase();
    if (!s) return;
    setQuery("");
    router.push(`/instrument/${encodeURIComponent(s)}`);
  };

  const sections = [
    { title: "Popular", items: POPULAR },
    { title: "Forex", items: FOREX },
    { title: "Commodities", items: COMMODITIES },
    { title: "Indices", items: INDICES },
  ];

  return (
    <SafeAreaView style={styles.container} edges={["top"]}>
      <View style={styles.inputRow}>
        <TextInput
          value={query}
          onChangeText={(t) => setQuery(t.toUpperCase())}
          placeholder="Ticker (e.g. NVDA, EURUSD)"
          placeholderTextColor={colors.textDim}
          autoCapitalize="characters"
          autoCorrect={false}
          style={styles.input}
          onSubmitEditing={submit}
          returnKeyType="search"
        />
        <Pressable onPress={submit} style={styles.openBtn}>
          <Text style={styles.openBtnText}>Open</Text>
        </Pressable>
      </View>

      <FlatList
        data={sections}
        keyExtractor={(s) => s.title}
        renderItem={({ item }) => (
          <View style={{ marginTop: spacing.lg, paddingHorizontal: spacing.lg }}>
            <Text style={styles.sectionTitle}>{item.title.toUpperCase()}</Text>
            <View style={styles.chipWrap}>
              {item.items.map((sym) => (
                <Link
                  key={sym}
                  href={`/instrument/${encodeURIComponent(sym)}`}
                  asChild
                >
                  <Pressable style={({ pressed }) => [styles.chip, pressed && { opacity: 0.6 }]}>
                    <Text style={styles.chipText}>{sym}</Text>
                  </Pressable>
                </Link>
              ))}
            </View>
          </View>
        )}
      />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg },
  inputRow: {
    flexDirection: "row",
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.sm,
    paddingBottom: spacing.md,
    gap: spacing.sm,
  },
  input: {
    flex: 1,
    backgroundColor: colors.bgElevated,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.md,
    paddingHorizontal: spacing.md,
    paddingVertical: 10,
    color: colors.text,
    fontSize: 14,
  },
  openBtn: {
    backgroundColor: colors.primaryDark,
    paddingHorizontal: spacing.lg,
    justifyContent: "center",
    borderRadius: radius.md,
  },
  openBtnText: { color: "#000", fontWeight: "700" },
  sectionTitle: {
    color: colors.textDim,
    fontSize: 11,
    fontWeight: "700",
    marginBottom: spacing.sm,
    letterSpacing: 0.5,
  },
  chipWrap: { flexDirection: "row", flexWrap: "wrap", gap: 6 },
  chip: {
    borderWidth: 1,
    borderColor: colors.border,
    backgroundColor: colors.bgElevated,
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: radius.md,
  },
  chipText: {
    color: colors.text,
    fontSize: 12,
    fontFamily: "Menlo",
  },
});
