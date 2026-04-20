import { Linking, ScrollView, StyleSheet, Text, View, Pressable, Alert } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import Constants from "expo-constants";
import { API_BASE } from "../../src/lib/api";
import { usePushRegistration } from "../../src/lib/push";
import { colors, radius, spacing } from "../../src/lib/theme";

export default function SettingsScreen() {
  const version = Constants.expoConfig?.version ?? "dev";
  const push = usePushRegistration();

  const pushLabel = labelForPush(push.status);
  const pushColor =
    push.status === "registered"
      ? colors.bullish
      : push.status === "denied" || push.status === "error"
      ? colors.bearish
      : colors.amber;

  async function sendTest() {
    try {
      const url = new URL("/mobile/test-push", API_BASE);
      const resp = await fetch(url.toString(), { method: "POST" });
      const json = await resp.json();
      Alert.alert("Test push", JSON.stringify(json, null, 2));
    } catch (e) {
      Alert.alert("Test push failed", String(e));
    }
  }

  return (
    <SafeAreaView style={styles.container} edges={["top"]}>
      <ScrollView
        contentContainerStyle={styles.scrollContent}
        showsVerticalScrollIndicator={false}
      >
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>ABOUT</Text>
        <View style={styles.row}>
          <Text style={styles.label}>Version</Text>
          <Text style={styles.value}>{version}</Text>
        </View>
        <View style={styles.row}>
          <Text style={styles.label}>Backend</Text>
          <Text style={styles.valueMono} numberOfLines={1}>
            {API_BASE.replace(/^https?:\/\//, "")}
          </Text>
        </View>
      </View>

      <View style={styles.section}>
        <Text style={styles.sectionTitle}>LINKS</Text>
        <Pressable
          onPress={() => Linking.openURL("https://momentum-signal-engine.vercel.app/")}
          style={styles.linkRow}
        >
          <Text style={styles.link}>Open web dashboard</Text>
          <Text style={styles.chevron}>›</Text>
        </Pressable>
      </View>

      <View style={styles.section}>
        <Text style={styles.sectionTitle}>NOTIFICATIONS</Text>
        <View style={styles.row}>
          <Text style={styles.label}>Push status</Text>
          <Text style={[styles.value, { color: pushColor }]}>{pushLabel}</Text>
        </View>
        {push.token && (
          <View style={styles.row}>
            <Text style={styles.label}>Token</Text>
            <Text style={styles.valueMono} numberOfLines={1}>
              {push.token.replace("ExponentPushToken[", "…[").slice(0, 28) + "…"}
            </Text>
          </View>
        )}
        {push.error && (
          <Text style={[styles.muted, { color: colors.bearish }]}>
            {push.error}
          </Text>
        )}
        <Pressable
          onPress={sendTest}
          disabled={push.status !== "registered"}
          style={[
            styles.btn,
            push.status !== "registered" && { opacity: 0.4 },
          ]}
        >
          <Text style={styles.btnText}>Send test push</Text>
        </Pressable>
        <Text style={styles.muted}>
          Uses Expo push (no Apple/Google keys needed). Works only on a
          physical device — the simulator is rejected by Apple.
        </Text>
      </View>
      </ScrollView>
    </SafeAreaView>
  );
}

function labelForPush(status: string): string {
  switch (status) {
    case "idle":
    case "requesting_permission":
      return "Requesting permission…";
    case "fetching_token":
      return "Fetching token…";
    case "registering":
      return "Registering with backend…";
    case "registered":
      return "Registered ✓";
    case "denied":
      return "Permission denied";
    case "unsupported":
      return "Simulator (physical device required)";
    case "error":
      return "Error";
    default:
      return status;
  }
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg },
  scrollContent: { padding: spacing.lg, paddingBottom: spacing.xxl },
  section: {
    backgroundColor: colors.bgElevated,
    borderRadius: radius.md,
    padding: spacing.md,
    marginBottom: spacing.md,
  },
  sectionTitle: {
    color: colors.textDim,
    fontSize: 10,
    fontWeight: "700",
    letterSpacing: 0.5,
    marginBottom: spacing.sm,
  },
  row: {
    flexDirection: "row",
    justifyContent: "space-between",
    paddingVertical: 6,
  },
  linkRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    paddingVertical: 6,
  },
  label: { color: colors.textMuted, fontSize: 13 },
  value: { color: colors.text, fontSize: 13 },
  valueMono: { color: colors.text, fontSize: 12, fontFamily: "Menlo", flexShrink: 1, marginLeft: spacing.md },
  link: { color: colors.primary, fontSize: 14 },
  chevron: { color: colors.textDim, fontSize: 18 },
  muted: { color: colors.textDim, fontSize: 12, lineHeight: 18 },
  btn: {
    backgroundColor: colors.primaryDark,
    paddingVertical: 10,
    borderRadius: radius.md,
    alignItems: "center",
    marginVertical: spacing.sm,
  },
  btnText: { color: "#000", fontWeight: "700", fontSize: 13 },
});
