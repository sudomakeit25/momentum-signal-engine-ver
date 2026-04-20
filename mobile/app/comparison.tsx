import { useQueries } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import {
  ActivityIndicator,
  Dimensions,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import Svg, { Line as SvgLine, Path, Text as SvgText } from "react-native-svg";
import { api, ChartBar } from "../src/lib/api";
import { colors, radius, spacing } from "../src/lib/theme";

const RANGE_OPTIONS: { label: string; days: number }[] = [
  { label: "1M", days: 30 },
  { label: "3M", days: 90 },
  { label: "6M", days: 180 },
  { label: "1Y", days: 365 },
];

export default function ComparisonScreen() {
  const [a, setA] = useState("SPY");
  const [b, setB] = useState("QQQ");
  const [days, setDays] = useState(90);
  const [inputA, setInputA] = useState(a);
  const [inputB, setInputB] = useState(b);

  const queries = useQueries({
    queries: [
      { queryKey: ["cmp", a, days], queryFn: () => api.chart(a, days) },
      { queryKey: ["cmp", b, days], queryFn: () => api.chart(b, days) },
    ],
  });

  const loading = queries.some((q) => q.isLoading);
  const barsA = queries[0].data?.bars ?? [];
  const barsB = queries[1].data?.bars ?? [];

  return (
    <SafeAreaView style={styles.container} edges={["bottom"]}>
      <ScrollView
        contentContainerStyle={styles.scroll}
        keyboardShouldPersistTaps="handled"
      >
        <View style={styles.inputRow}>
          <View style={{ flex: 1 }}>
            <Text style={styles.muted}>Symbol A</Text>
            <TextInput
              value={inputA}
              onChangeText={setInputA}
              onSubmitEditing={() =>
                setA(inputA.trim().toUpperCase() || "SPY")
              }
              placeholder="SPY"
              placeholderTextColor={colors.textDim}
              autoCapitalize="characters"
              autoCorrect={false}
              style={styles.input}
            />
          </View>
          <View style={{ flex: 1 }}>
            <Text style={styles.muted}>Symbol B</Text>
            <TextInput
              value={inputB}
              onChangeText={setInputB}
              onSubmitEditing={() =>
                setB(inputB.trim().toUpperCase() || "QQQ")
              }
              placeholder="QQQ"
              placeholderTextColor={colors.textDim}
              autoCapitalize="characters"
              autoCorrect={false}
              style={styles.input}
            />
          </View>
          <Pressable
            onPress={() => {
              setA(inputA.trim().toUpperCase() || "SPY");
              setB(inputB.trim().toUpperCase() || "QQQ");
            }}
            style={styles.goBtn}
          >
            <Text style={styles.goBtnText}>Compare</Text>
          </Pressable>
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

        {loading ? (
          <View style={{ alignItems: "center", padding: spacing.xl }}>
            <ActivityIndicator color={colors.primary} />
          </View>
        ) : (
          <CompareChart
            a={{ symbol: a, bars: barsA }}
            b={{ symbol: b, bars: barsB }}
          />
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

function CompareChart({
  a,
  b,
}: {
  a: { symbol: string; bars: ChartBar[] };
  b: { symbol: string; bars: ChartBar[] };
}) {
  const width = Dimensions.get("window").width - spacing.lg * 2;
  const height = 240;
  const padX = 40;
  const padY = 20;

  const { pathA, pathB, series, minPct, maxPct, lastA, lastB } = useMemo(() => {
    if (a.bars.length < 2 || b.bars.length < 2) {
      return {
        pathA: "",
        pathB: "",
        series: [] as { x: number; aPct: number; bPct: number }[],
        minPct: 0,
        maxPct: 0,
        lastA: 0,
        lastB: 0,
      };
    }
    const firstA = a.bars[0].close;
    const firstB = b.bars[0].close;
    const n = Math.min(a.bars.length, b.bars.length);
    const aPcts: number[] = [];
    const bPcts: number[] = [];
    for (let i = 0; i < n; i++) {
      aPcts.push(((a.bars[i].close - firstA) / firstA) * 100);
      bPcts.push(((b.bars[i].close - firstB) / firstB) * 100);
    }
    const allPcts = [...aPcts, ...bPcts];
    const min = Math.min(...allPcts);
    const max = Math.max(...allPcts);
    const span = max - min || 1;
    const innerW = width - padX - padY;
    const innerH = height - padY * 2;
    const xAt = (i: number) => padX + (i / (n - 1)) * innerW;
    const yAt = (v: number) => padY + (1 - (v - min) / span) * innerH;
    let dA = `M ${xAt(0)} ${yAt(aPcts[0])}`;
    let dB = `M ${xAt(0)} ${yAt(bPcts[0])}`;
    for (let i = 1; i < n; i++) {
      dA += ` L ${xAt(i)} ${yAt(aPcts[i])}`;
      dB += ` L ${xAt(i)} ${yAt(bPcts[i])}`;
    }
    return {
      pathA: dA,
      pathB: dB,
      series: aPcts.map((p, i) => ({ x: xAt(i), aPct: p, bPct: bPcts[i] })),
      minPct: min,
      maxPct: max,
      lastA: aPcts[aPcts.length - 1],
      lastB: bPcts[bPcts.length - 1],
    };
  }, [a.bars, b.bars, width]);

  if (!pathA || !pathB) {
    return (
      <View style={styles.card}>
        <Text style={styles.muted}>No chart data.</Text>
      </View>
    );
  }

  const colorA = colors.primary;
  const colorB = colors.amber;

  return (
    <View style={styles.card}>
      <View style={styles.legend}>
        <LegendDot color={colorA} label={a.symbol} value={lastA} />
        <LegendDot color={colorB} label={b.symbol} value={lastB} />
      </View>
      <Svg width={width} height={height}>
        {/* Zero line */}
        <SvgLine
          x1={padX}
          y1={padY + (1 - (0 - minPct) / (maxPct - minPct || 1)) * (height - padY * 2)}
          x2={width - padY}
          y2={padY + (1 - (0 - minPct) / (maxPct - minPct || 1)) * (height - padY * 2)}
          stroke={colors.borderSubtle}
          strokeDasharray="3 4"
          strokeWidth={0.5}
        />
        <Path d={pathA} stroke={colorA} strokeWidth={1.5} fill="none" />
        <Path d={pathB} stroke={colorB} strokeWidth={1.5} fill="none" />
        <SvgText
          x={padX - 6}
          y={padY + 4}
          fontSize="9"
          fill={colors.textDim}
          textAnchor="end"
        >
          {maxPct.toFixed(1)}%
        </SvgText>
        <SvgText
          x={padX - 6}
          y={height - padY + 4}
          fontSize="9"
          fill={colors.textDim}
          textAnchor="end"
        >
          {minPct.toFixed(1)}%
        </SvgText>
      </Svg>
    </View>
  );
}

function LegendDot({
  color,
  label,
  value,
}: {
  color: string;
  label: string;
  value: number;
}) {
  return (
    <View
      style={{
        flexDirection: "row",
        alignItems: "center",
        gap: 6,
        marginRight: spacing.md,
      }}
    >
      <View
        style={{
          width: 8,
          height: 8,
          borderRadius: 4,
          backgroundColor: color,
        }}
      />
      <Text style={styles.legendText}>
        {label}{" "}
        <Text
          style={{
            color: value >= 0 ? colors.bullish : colors.bearish,
            fontWeight: "700",
          }}
        >
          {value >= 0 ? "+" : ""}
          {value.toFixed(2)}%
        </Text>
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg },
  scroll: { padding: spacing.lg, gap: spacing.md, paddingBottom: spacing.xxl },
  inputRow: { flexDirection: "row", gap: spacing.sm, alignItems: "flex-end" },
  input: {
    backgroundColor: colors.bgCard,
    color: colors.text,
    borderRadius: radius.sm,
    paddingHorizontal: spacing.sm,
    paddingVertical: 8,
    marginTop: 4,
    fontVariant: ["tabular-nums"],
    fontWeight: "700",
  },
  goBtn: {
    backgroundColor: colors.primaryDark,
    borderRadius: radius.sm,
    paddingHorizontal: spacing.md,
    paddingVertical: 10,
    alignSelf: "flex-end",
  },
  goBtnText: { color: "#000", fontSize: 12, fontWeight: "700" },
  rangeBar: {
    flexDirection: "row",
    alignSelf: "flex-start",
    borderRadius: radius.sm,
    borderWidth: 1,
    borderColor: colors.border,
    overflow: "hidden",
  },
  rangeBtn: {
    paddingHorizontal: spacing.md,
    paddingVertical: 6,
    backgroundColor: colors.bgElevated,
  },
  rangeBtnActive: { backgroundColor: colors.primaryDark },
  rangeBtnText: { color: colors.textMuted, fontSize: 12 },
  rangeBtnTextActive: { color: "#000", fontWeight: "700" },
  card: {
    backgroundColor: colors.bgElevated,
    borderRadius: radius.md,
    padding: spacing.md,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
  },
  legend: {
    flexDirection: "row",
    marginBottom: spacing.sm,
    flexWrap: "wrap",
  },
  legendText: { color: colors.text, fontSize: 12 },
  muted: { color: colors.textMuted, fontSize: 12 },
});
