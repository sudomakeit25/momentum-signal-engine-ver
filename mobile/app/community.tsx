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
import { api, CommunityPost } from "../src/lib/api";
import { COMMUNITY_FEED_ENABLED } from "../src/lib/flags";
import { colors, radius, spacing } from "../src/lib/theme";

export default function CommunityScreen() {
  const q = useQuery({
    enabled: COMMUNITY_FEED_ENABLED,
    queryKey: ["community-feed"],
    queryFn: () => api.communityFeed(50),
  });

  if (!COMMUNITY_FEED_ENABLED) {
    return (
      <SafeAreaView style={styles.container} edges={["bottom"]}>
        <View style={styles.center}>
          <Text style={styles.muted}>
            Community is not available in this build.
          </Text>
        </View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.container} edges={["bottom"]}>
      {q.isLoading ? (
        <View style={styles.center}>
          <ActivityIndicator color={colors.primary} />
        </View>
      ) : !q.data || q.data.length === 0 ? (
        <View style={styles.center}>
          <Text style={styles.muted}>
            No posts yet. The community feed is read-only in the mobile app —
            post from the web dashboard.
          </Text>
        </View>
      ) : (
        <FlatList
          data={q.data}
          keyExtractor={(p) => p.id}
          renderItem={({ item }) => <PostCard post={item} />}
          contentContainerStyle={styles.list}
        />
      )}
    </SafeAreaView>
  );
}

function PostCard({ post }: { post: CommunityPost }) {
  const date = post.created_at ? post.created_at.slice(0, 16) : "";
  return (
    <View style={styles.card}>
      <View style={styles.header}>
        <Text style={styles.author}>{post.user_name || "Anonymous"}</Text>
        <Text style={styles.when}>{date}</Text>
      </View>
      {post.symbol ? (
        <Link href={`/instrument/${post.symbol}`} asChild>
          <Pressable>
            <Text style={styles.symbolTag}>${post.symbol}</Text>
          </Pressable>
        </Link>
      ) : null}
      <Text style={styles.body}>{post.content}</Text>
      <View style={styles.footer}>
        <Text style={styles.muted}>
          ♥ {post.likes} · 💬 {post.comments?.length ?? 0}
        </Text>
      </View>
      {post.comments && post.comments.length > 0 && (
        <View style={styles.commentsWrap}>
          {post.comments.slice(0, 3).map((c, i) => (
            <View key={i} style={styles.comment}>
              <Text style={styles.commentAuthor}>{c.user_name}</Text>
              <Text style={styles.commentBody}>{c.content}</Text>
            </View>
          ))}
        </View>
      )}
    </View>
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
  list: { padding: spacing.lg, gap: spacing.md, paddingBottom: spacing.xxl },
  card: {
    backgroundColor: colors.bgElevated,
    borderRadius: radius.md,
    padding: spacing.md,
    borderWidth: 1,
    borderColor: colors.borderSubtle,
    marginBottom: spacing.md,
  },
  header: {
    flexDirection: "row",
    justifyContent: "space-between",
    marginBottom: 4,
  },
  author: { color: colors.text, fontSize: 13, fontWeight: "700" },
  when: { color: colors.textDim, fontSize: 11 },
  symbolTag: {
    color: colors.primary,
    fontSize: 12,
    fontWeight: "700",
    marginBottom: 4,
  },
  body: { color: colors.text, fontSize: 14, lineHeight: 20 },
  footer: {
    marginTop: spacing.sm,
    flexDirection: "row",
    justifyContent: "space-between",
  },
  commentsWrap: {
    marginTop: spacing.sm,
    borderTopWidth: 1,
    borderTopColor: colors.borderSubtle,
    paddingTop: spacing.sm,
    gap: spacing.sm,
  },
  comment: {
    backgroundColor: colors.bgCard,
    padding: spacing.sm,
    borderRadius: radius.sm,
  },
  commentAuthor: {
    color: colors.textMuted,
    fontSize: 11,
    fontWeight: "700",
    marginBottom: 2,
  },
  commentBody: { color: colors.text, fontSize: 12, lineHeight: 17 },
});
