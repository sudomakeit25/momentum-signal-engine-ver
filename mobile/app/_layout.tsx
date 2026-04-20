import { Stack, useRouter } from "expo-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StatusBar } from "expo-status-bar";
import { SafeAreaProvider } from "react-native-safe-area-context";
import { useEffect } from "react";
import * as Notifications from "expo-notifications";
import { usePushRegistration } from "../src/lib/push";
import { colors } from "../src/lib/theme";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 2 * 60 * 1000,
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

function NotificationRouter() {
  // Fire-and-forget: register for push on launch, expose state via Settings.
  usePushRegistration();
  const router = useRouter();

  // When the user taps a push notification, route them to the relevant
  // instrument page via the 'url' data field the backend attaches.
  useEffect(() => {
    const sub = Notifications.addNotificationResponseReceivedListener((resp) => {
      const data = resp.notification.request.content.data as
        | { url?: string; type?: string }
        | undefined;
      if (!data?.url) return;
      // URLs arrive like 'mse://instrument/NVDA' — strip the scheme for
      // expo-router's in-app navigation and keep it simple.
      const path = data.url.replace(/^mse:\/\//, "/");
      router.push(path as Parameters<typeof router.push>[0]);
    });
    return () => sub.remove();
  }, [router]);

  return null;
}

export default function RootLayout() {
  return (
    <QueryClientProvider client={queryClient}>
      <SafeAreaProvider>
        <StatusBar style="light" />
        <NotificationRouter />
        <Stack
          screenOptions={{
            contentStyle: { backgroundColor: colors.bg },
            headerStyle: { backgroundColor: colors.bg },
            headerTintColor: colors.text,
            headerTitleStyle: { color: colors.text, fontWeight: "700" },
          }}
        >
          <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
          <Stack.Screen
            name="instrument/[symbol]"
            options={{ title: "Instrument" }}
          />
        </Stack>
      </SafeAreaProvider>
    </QueryClientProvider>
  );
}
