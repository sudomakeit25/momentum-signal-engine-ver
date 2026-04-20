import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import {
  ActivityIndicator,
  Alert,
  Modal,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { api, JournalStats, JournalTrade } from "../src/lib/api";
import { colors, radius, spacing } from "../src/lib/theme";

export default function JournalScreen() {
  const [addOpen, setAddOpen] = useState(false);
  const trades = useQuery({
    queryKey: ["journal-trades"],
    queryFn: api.journalTrades,
  });
  const stats = useQuery({
    queryKey: ["journal-stats"],
    queryFn: api.journalStats,
  });

  return (
    <SafeAreaView style={styles.container} edges={["bottom"]}>
      <ScrollView
        contentContainerStyle={styles.scrollContent}
        showsVerticalScrollIndicator={false}
      >
        <StatsCard data={stats.data} loading={stats.isLoading} />

        <View style={styles.toolbar}>
          <Text style={styles.sectionTitle}>TRADES</Text>
          <Pressable
            onPress={() => setAddOpen(true)}
            style={styles.addBtn}
          >
            <Text style={styles.addBtnText}>+ Add</Text>
          </Pressable>
        </View>

        {trades.isLoading ? (
          <ActivityIndicator color={colors.primary} />
        ) : !trades.data || trades.data.length === 0 ? (
          <Text style={styles.muted}>
            No trades yet. Add one manually or import from Alpaca via the web
            app.
          </Text>
        ) : (
          trades.data.map((t, i) => (
            <TradeRow key={t.id ?? i} trade={t} />
          ))
        )}
      </ScrollView>

      <AddTradeSheet
        visible={addOpen}
        onClose={() => setAddOpen(false)}
      />
    </SafeAreaView>
  );
}

function StatsCard({
  data,
  loading,
}: {
  data: JournalStats | undefined;
  loading: boolean;
}) {
  if (loading) {
    return (
      <View style={styles.card}>
        <ActivityIndicator color={colors.primary} />
      </View>
    );
  }
  if (!data || !data.total_trades) {
    return (
      <View style={styles.card}>
        <Text style={styles.sectionTitle}>STATS</Text>
        <Text style={styles.muted}>No closed trades yet.</Text>
      </View>
    );
  }
  const winColor =
    (data.win_rate ?? 0) >= 55 ? colors.bullish : colors.amber;
  const pnlColor =
    (data.total_pnl ?? 0) >= 0 ? colors.bullish : colors.bearish;
  return (
    <View style={styles.card}>
      <Text style={styles.sectionTitle}>STATS</Text>
      <View style={styles.row}>
        <Text style={styles.muted}>Total trades</Text>
        <Text style={styles.mono}>{data.total_trades}</Text>
      </View>
      <View style={styles.row}>
        <Text style={styles.muted}>Open / Closed</Text>
        <Text style={styles.mono}>
          {data.open_trades ?? 0} / {data.closed_trades ?? 0}
        </Text>
      </View>
      <View style={styles.row}>
        <Text style={styles.muted}>Win rate</Text>
        <Text style={[styles.mono, { color: winColor }]}>
          {data.win_rate?.toFixed(1) ?? "--"}%
        </Text>
      </View>
      <View style={styles.row}>
        <Text style={styles.muted}>Avg R</Text>
        <Text style={styles.mono}>{data.avg_r?.toFixed(2) ?? "--"}</Text>
      </View>
      <View style={styles.row}>
        <Text style={styles.muted}>Total P&L</Text>
        <Text style={[styles.mono, { color: pnlColor, fontWeight: "700" }]}>
          {(data.total_pnl ?? 0) >= 0 ? "+" : ""}$
          {(data.total_pnl ?? 0).toFixed(2)}
        </Text>
      </View>
    </View>
  );
}

function TradeRow({ trade }: { trade: JournalTrade }) {
  const qc = useQueryClient();
  const [closeOpen, setCloseOpen] = useState(false);
  const [exitPrice, setExitPrice] = useState("");

  const closeTrade = useMutation({
    mutationFn: () =>
      api.closeTrade(String(trade.id), parseFloat(exitPrice)),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["journal-trades"] });
      qc.invalidateQueries({ queryKey: ["journal-stats"] });
      setCloseOpen(false);
    },
    onError: (e) => Alert.alert("Close failed", String(e)),
  });

  const isOpen = trade.status === "open";
  const pnlColor =
    trade.pnl === null || trade.pnl === undefined
      ? colors.textDim
      : trade.pnl >= 0
      ? colors.bullish
      : colors.bearish;

  return (
    <View style={styles.card}>
      <View style={styles.row}>
        <View style={{ flexDirection: "row", gap: spacing.sm }}>
          <Text style={styles.symbol}>{trade.symbol}</Text>
          <Text
            style={[
              styles.action,
              {
                color:
                  trade.side === "buy" || trade.side === "long"
                    ? colors.bullish
                    : colors.bearish,
              },
            ]}
          >
            {trade.side.toUpperCase()}
          </Text>
          {isOpen && (
            <Text style={styles.openBadge}>OPEN</Text>
          )}
        </View>
        {trade.pnl !== null && trade.pnl !== undefined && (
          <Text style={[styles.mono, { color: pnlColor, fontWeight: "700" }]}>
            {trade.pnl >= 0 ? "+" : ""}${trade.pnl.toFixed(2)}
            {trade.r_multiple !== null && trade.r_multiple !== undefined
              ? ` · ${trade.r_multiple.toFixed(2)}R`
              : ""}
          </Text>
        )}
      </View>
      <View style={styles.row}>
        <Text style={styles.muted}>Entry</Text>
        <Text style={styles.mono}>
          {trade.shares} sh @ ${trade.entry_price.toFixed(2)}
        </Text>
      </View>
      {trade.exit_price !== null && (
        <View style={styles.row}>
          <Text style={styles.muted}>Exit</Text>
          <Text style={styles.mono}>${trade.exit_price.toFixed(2)}</Text>
        </View>
      )}
      {trade.setup_type ? (
        <Text style={styles.muted}>
          {trade.setup_type.replace(/_/g, " ")}
        </Text>
      ) : null}
      {isOpen && (
        <Pressable
          onPress={() => setCloseOpen(true)}
          style={styles.closeBtn}
        >
          <Text style={styles.closeBtnText}>Close Trade</Text>
        </Pressable>
      )}

      <Modal
        visible={closeOpen}
        transparent
        animationType="fade"
        onRequestClose={() => setCloseOpen(false)}
      >
        <View style={styles.modalBackdrop}>
          <View style={styles.modalCard}>
            <Text style={styles.sectionTitle}>
              Close {trade.symbol}
            </Text>
            <Text style={styles.muted}>Exit price</Text>
            <TextInput
              value={exitPrice}
              onChangeText={setExitPrice}
              placeholder="0.00"
              placeholderTextColor={colors.textDim}
              keyboardType="decimal-pad"
              style={styles.input}
              autoFocus
            />
            <View style={{ flexDirection: "row", gap: spacing.sm }}>
              <Pressable
                onPress={() => setCloseOpen(false)}
                style={[styles.modalBtn, styles.modalBtnSecondary]}
              >
                <Text style={styles.modalBtnText}>Cancel</Text>
              </Pressable>
              <Pressable
                onPress={() => closeTrade.mutate()}
                style={[styles.modalBtn, styles.modalBtnPrimary]}
                disabled={!exitPrice || closeTrade.isPending}
              >
                <Text
                  style={[styles.modalBtnText, { color: "#000" }]}
                >
                  {closeTrade.isPending ? "Closing…" : "Close"}
                </Text>
              </Pressable>
            </View>
          </View>
        </View>
      </Modal>
    </View>
  );
}

function AddTradeSheet({
  visible,
  onClose,
}: {
  visible: boolean;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const [symbol, setSymbol] = useState("");
  const [shares, setShares] = useState("");
  const [entry, setEntry] = useState("");
  const [stop, setStop] = useState("");
  const [target, setTarget] = useState("");
  const [setup, setSetup] = useState("");

  const add = useMutation({
    mutationFn: () =>
      api.addTrade({
        symbol: symbol.trim().toUpperCase(),
        shares: parseFloat(shares),
        entry_price: parseFloat(entry),
        stop_loss: stop ? parseFloat(stop) : undefined,
        target: target ? parseFloat(target) : undefined,
        setup_type: setup,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["journal-trades"] });
      qc.invalidateQueries({ queryKey: ["journal-stats"] });
      setSymbol("");
      setShares("");
      setEntry("");
      setStop("");
      setTarget("");
      setSetup("");
      onClose();
    },
    onError: (e) => Alert.alert("Add failed", String(e)),
  });

  const canSubmit = symbol && shares && entry;

  return (
    <Modal
      visible={visible}
      transparent
      animationType="slide"
      onRequestClose={onClose}
    >
      <SafeAreaView style={styles.sheetBackdrop} edges={["top", "bottom"]}>
        <View style={styles.sheet}>
          <View style={styles.sheetHeader}>
            <Text style={styles.sheetTitle}>New Trade</Text>
            <Pressable onPress={onClose} hitSlop={10}>
              <Text style={{ color: colors.primary, fontSize: 16 }}>
                Cancel
              </Text>
            </Pressable>
          </View>
          <ScrollView contentContainerStyle={{ padding: spacing.lg, gap: spacing.md }}>
            <Field label="Symbol" value={symbol} onChange={setSymbol} autoCap />
            <Field label="Shares" value={shares} onChange={setShares} numeric />
            <Field label="Entry price" value={entry} onChange={setEntry} numeric />
            <Field label="Stop loss" value={stop} onChange={setStop} numeric />
            <Field label="Target" value={target} onChange={setTarget} numeric />
            <Field label="Setup (optional)" value={setup} onChange={setSetup} />
            <Pressable
              disabled={!canSubmit || add.isPending}
              onPress={() => add.mutate()}
              style={[
                styles.submitBtn,
                (!canSubmit || add.isPending) && { opacity: 0.5 },
              ]}
            >
              <Text style={styles.submitBtnText}>
                {add.isPending ? "Saving…" : "Save Trade"}
              </Text>
            </Pressable>
          </ScrollView>
        </View>
      </SafeAreaView>
    </Modal>
  );
}

function Field({
  label,
  value,
  onChange,
  numeric,
  autoCap,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  numeric?: boolean;
  autoCap?: boolean;
}) {
  return (
    <View>
      <Text style={styles.muted}>{label}</Text>
      <TextInput
        value={value}
        onChangeText={onChange}
        placeholderTextColor={colors.textDim}
        keyboardType={numeric ? "decimal-pad" : "default"}
        autoCapitalize={autoCap ? "characters" : "none"}
        style={styles.input}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg },
  scrollContent: {
    padding: spacing.lg,
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
  toolbar: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
  },
  sectionTitle: {
    color: colors.textDim,
    fontSize: 10,
    fontWeight: "700",
    letterSpacing: 0.5,
    marginBottom: spacing.sm,
  },
  addBtn: {
    backgroundColor: colors.primaryDark,
    paddingHorizontal: spacing.md,
    paddingVertical: 6,
    borderRadius: radius.sm,
  },
  addBtnText: { color: "#000", fontSize: 12, fontWeight: "700" },
  row: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    paddingVertical: 4,
  },
  symbol: {
    color: colors.text,
    fontSize: 14,
    fontWeight: "700",
    fontVariant: ["tabular-nums"],
  },
  action: { fontSize: 12, fontWeight: "700" },
  openBadge: {
    color: colors.amber,
    fontSize: 10,
    fontWeight: "700",
    borderWidth: 1,
    borderColor: colors.amber,
    paddingHorizontal: 4,
    borderRadius: 2,
  },
  muted: { color: colors.textMuted, fontSize: 12 },
  mono: {
    color: colors.text,
    fontSize: 13,
    fontVariant: ["tabular-nums"],
  },
  closeBtn: {
    marginTop: spacing.sm,
    backgroundColor: colors.bgCard,
    borderRadius: radius.sm,
    paddingVertical: 8,
    alignItems: "center",
    borderWidth: 1,
    borderColor: colors.border,
  },
  closeBtnText: { color: colors.text, fontSize: 12, fontWeight: "600" },

  modalBackdrop: {
    flex: 1,
    backgroundColor: "rgba(0,0,0,0.6)",
    justifyContent: "center",
    padding: spacing.xl,
  },
  modalCard: {
    backgroundColor: colors.bgElevated,
    borderRadius: radius.md,
    padding: spacing.lg,
    borderWidth: 1,
    borderColor: colors.border,
  },
  input: {
    backgroundColor: colors.bgCard,
    color: colors.text,
    borderRadius: radius.sm,
    paddingHorizontal: spacing.sm,
    paddingVertical: 8,
    marginTop: 4,
    marginBottom: spacing.sm,
    fontVariant: ["tabular-nums"],
  },
  modalBtn: {
    flex: 1,
    paddingVertical: 10,
    borderRadius: radius.sm,
    alignItems: "center",
  },
  modalBtnPrimary: { backgroundColor: colors.primaryDark },
  modalBtnSecondary: {
    backgroundColor: colors.bgCard,
    borderWidth: 1,
    borderColor: colors.border,
  },
  modalBtnText: { color: colors.text, fontSize: 13, fontWeight: "700" },

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
  sheetTitle: { color: colors.text, fontSize: 15, fontWeight: "700" },
  submitBtn: {
    backgroundColor: colors.primaryDark,
    paddingVertical: 12,
    borderRadius: radius.md,
    alignItems: "center",
    marginTop: spacing.md,
  },
  submitBtnText: { color: "#000", fontSize: 14, fontWeight: "700" },
});
