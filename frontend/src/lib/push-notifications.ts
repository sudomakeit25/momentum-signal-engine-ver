/**
 * Browser push notifications.
 * Feature #43.
 */

export function isPushSupported(): boolean {
  return typeof window !== "undefined" && "Notification" in window;
}

export async function requestPermission(): Promise<boolean> {
  if (!isPushSupported()) return false;
  const result = await Notification.requestPermission();
  return result === "granted";
}

export function sendNotification(title: string, body: string, url?: string): void {
  if (!isPushSupported() || Notification.permission !== "granted") return;

  const notification = new Notification(title, {
    body,
    icon: "/favicon.ico",
    badge: "/favicon.ico",
    tag: "mse-signal",
  });

  if (url) {
    notification.onclick = () => {
      window.focus();
      window.location.href = url;
    };
  }
}

export function getPermissionStatus(): string {
  if (!isPushSupported()) return "unsupported";
  return Notification.permission;
}
