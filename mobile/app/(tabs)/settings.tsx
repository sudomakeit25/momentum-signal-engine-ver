import { Linking, StyleSheet, Text, View, Pressable } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import Constants from "expo-constants";
import { API_BASE } from "../../src/lib/api";
import { colors, radius, spacing } from "../../src/lib/theme";

export default function SettingsScreen() {
  const version = Constants.expoConfig?.version ?? "dev";

  return (
    <SafeAreaView style={styles.container} edges={["top"]}>
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
        <Text style={styles.muted}>
          Push notifications wiring coming next. For now, SMS / Discord /
          Telegram alerts are configured from the web app.
        </Text>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg, padding: spacing.lg },
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
});
