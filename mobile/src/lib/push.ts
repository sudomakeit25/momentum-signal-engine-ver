// Push notification registration + permission + token upload.
//
// One public hook: `usePushRegistration()`. It:
// 1. Asks the OS for notification permission (first time only).
// 2. Fetches the Expo push token from the Expo service.
// 3. POSTs it to /mobile/register-token so the backend dispatcher can
//    deliver alerts to this device.
//
// State is surfaced as { status, token, error } so the Settings
// screen can display progress.

import { useEffect, useState } from "react";
import { Platform } from "react-native";
import Constants from "expo-constants";
import * as Device from "expo-device";
import * as Notifications from "expo-notifications";
import { API_BASE } from "./api";

Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowAlert: true,
    shouldShowBanner: true,
    shouldShowList: true,
    shouldPlaySound: true,
    shouldSetBadge: false,
  }),
});

type Status =
  | "idle"
  | "requesting_permission"
  | "fetching_token"
  | "registering"
  | "registered"
  | "denied"
  | "unsupported"
  | "error";

export type PushState = {
  status: Status;
  token: string | null;
  error: string | null;
};

async function registerForPushNotifications(): Promise<PushState> {
  if (!Device.isDevice) {
    return {
      status: "unsupported",
      token: null,
      error: "Push requires a physical device, not a simulator.",
    };
  }

  if (Platform.OS === "android") {
    try {
      await Notifications.setNotificationChannelAsync("default", {
        name: "default",
        importance: Notifications.AndroidImportance.DEFAULT,
        vibrationPattern: [0, 250, 250, 250],
      });
    } catch {
      /* channel creation best-effort */
    }
  }

  const existing = await Notifications.getPermissionsAsync();
  let status = existing.status;
  if (status !== "granted") {
    const req = await Notifications.requestPermissionsAsync();
    status = req.status;
  }
  if (status !== "granted") {
    return {
      status: "denied",
      token: null,
      error: "Notification permission was not granted.",
    };
  }

  const projectId =
    Constants.expoConfig?.extra?.eas?.projectId ||
    Constants.easConfig?.projectId ||
    undefined;

  let tokenData;
  try {
    tokenData = await Notifications.getExpoPushTokenAsync(
      projectId ? { projectId } : undefined,
    );
  } catch (e) {
    return {
      status: "error",
      token: null,
      error: `Failed to fetch Expo push token: ${String(e)}`,
    };
  }
  const token = tokenData.data;

  // Register with our backend.
  try {
    const url = new URL("/mobile/register-token", API_BASE);
    url.searchParams.set("token", token);
    url.searchParams.set("platform", Platform.OS);
    const resp = await fetch(url.toString(), { method: "POST" });
    if (!resp.ok) {
      return {
        status: "error",
        token,
        error: `Backend returned ${resp.status}`,
      };
    }
  } catch (e) {
    return {
      status: "error",
      token,
      error: `Backend request failed: ${String(e)}`,
    };
  }

  return { status: "registered", token, error: null };
}

// Module-level state — run the registration flow exactly once per process
// and let every hook subscriber observe the final result.
let _cached: PushState = { status: "idle", token: null, error: null };
let _promise: Promise<PushState> | null = null;
const _subscribers = new Set<(s: PushState) => void>();

function _publish(s: PushState) {
  _cached = s;
  for (const fn of _subscribers) fn(s);
}

function _ensureRegistration(): Promise<PushState> {
  if (_promise) return _promise;
  _publish({ ..._cached, status: "requesting_permission" });
  _promise = registerForPushNotifications().then((result) => {
    _publish(result);
    return result;
  });
  return _promise;
}

export function usePushRegistration(): PushState {
  const [state, setState] = useState<PushState>(_cached);

  useEffect(() => {
    _subscribers.add(setState);
    _ensureRegistration();
    return () => {
      _subscribers.delete(setState);
    };
  }, []);

  return state;
}
