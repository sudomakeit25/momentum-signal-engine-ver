"use client";

import { useState, useEffect } from "react";
import { Bell, Send, Check, AlertCircle, MessageSquare, Smartphone, Zap, Mail } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { cn } from "@/lib/utils";

interface NotificationConfig {
  webhook_url: string;
  webhook_platform: "discord" | "telegram" | "slack";
  sms_to: string;
  sms_method: "twilio" | "email_gateway";
  sms_carrier: string;
  sms_consent: boolean;
  sms_consent_timestamp: string;
  auto_alerts_enabled: boolean;
  min_confidence: number;
}

const DEFAULT_CONFIG: NotificationConfig = {
  webhook_url: "",
  webhook_platform: "discord",
  sms_to: "",
  sms_method: "email_gateway",
  sms_carrier: "",
  sms_consent: false,
  sms_consent_timestamp: "",
  auto_alerts_enabled: false,
  min_confidence: 0.6,
};

const CARRIERS: { key: string; label: string }[] = [
  { key: "att", label: "AT&T" },
  { key: "tmobile", label: "T-Mobile" },
  { key: "verizon", label: "Verizon" },
  { key: "sprint", label: "Sprint" },
  { key: "boost", label: "Boost Mobile" },
  { key: "cricket", label: "Cricket" },
  { key: "metro", label: "Metro by T-Mobile" },
  { key: "uscellular", label: "US Cellular" },
  { key: "virgin", label: "Virgin Mobile" },
  { key: "google_fi", label: "Google Fi" },
  { key: "mint", label: "Mint Mobile" },
  { key: "visible", label: "Visible" },
  { key: "xfinity", label: "Xfinity Mobile" },
];

export default function NotificationsPage() {
  const [config, setConfig] = useState<NotificationConfig>(DEFAULT_CONFIG);
  const [testStatus, setTestStatus] = useState<"idle" | "sending" | "sent" | "error">("idle");
  const [smsTestStatus, setSmsTestStatus] = useState<"idle" | "sending" | "sent" | "error">("idle");
  const [notifyStatus, setNotifyStatus] = useState<"idle" | "sending" | "sent" | "error">("idle");
  const [saveStatus, setSaveStatus] = useState<"idle" | "saving" | "saved" | "error">("idle");
  const [message, setMessage] = useState("");
  const [loaded, setLoaded] = useState(false);

  const apiBase = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

  // Load config from backend on mount
  useEffect(() => {
    fetch(`${apiBase}/notifications/config`)
      .then((r) => r.json())
      .then((data) => {
        setConfig({
          webhook_url: data.webhook_url || "",
          webhook_platform: data.webhook_platform || "discord",
          sms_to: data.sms_to || "",
          sms_method: data.sms_method || "email_gateway",
          sms_carrier: data.sms_carrier || "",
          sms_consent: data.sms_consent || false,
          sms_consent_timestamp: data.sms_consent_timestamp || "",
          auto_alerts_enabled: data.auto_alerts_enabled || false,
          min_confidence: data.min_confidence ?? 0.6,
        });
        setLoaded(true);
      })
      .catch(() => setLoaded(true));
  }, [apiBase]);

  const saveConfig = async () => {
    setSaveStatus("saving");
    try {
      const params = new URLSearchParams({
        webhook_url: config.webhook_url,
        webhook_platform: config.webhook_platform,
        sms_to: config.sms_to,
        sms_method: config.sms_method,
        sms_carrier: config.sms_carrier,
        sms_consent: String(config.sms_consent),
        auto_alerts_enabled: String(config.auto_alerts_enabled),
        min_confidence: String(config.min_confidence),
      });
      const res = await fetch(`${apiBase}/notifications/config?${params}`, { method: "POST" });
      const data = await res.json();
      if (data.status === "saved") {
        setSaveStatus("saved");
        setMessage("Configuration saved!");
        setTimeout(() => setSaveStatus("idle"), 2000);
      } else {
        setSaveStatus("error");
        setMessage("Failed to save");
      }
    } catch {
      setSaveStatus("error");
      setMessage("Network error");
    }
  };

  const testWebhook = async () => {
    if (!config.webhook_url) return;
    setTestStatus("sending");
    try {
      const res = await fetch(
        `${apiBase}/webhook/test?url=${encodeURIComponent(config.webhook_url)}&platform=${config.webhook_platform}`,
        { method: "POST" }
      );
      const data = await res.json();
      if (data.status === "sent") {
        setTestStatus("sent");
        setMessage("Test message sent!");
      } else {
        setTestStatus("error");
        setMessage(data.message || "Failed");
      }
    } catch {
      setTestStatus("error");
      setMessage("Network error");
    }
  };

  const testSms = async () => {
    if (!config.sms_to) return;
    setSmsTestStatus("sending");
    try {
      const res = await fetch(
        `${apiBase}/notifications/test-sms?to=${encodeURIComponent(config.sms_to)}`,
        { method: "POST" }
      );
      const data = await res.json();
      if (data.status === "sent") {
        setSmsTestStatus("sent");
        setMessage("Test SMS sent!");
      } else {
        setSmsTestStatus("error");
        setMessage("SMS failed — check Twilio config on server");
      }
    } catch {
      setSmsTestStatus("error");
      setMessage("Network error");
    }
  };

  const sendSignals = async () => {
    if (!config.webhook_url) return;
    setNotifyStatus("sending");
    try {
      const res = await fetch(
        `${apiBase}/webhook/notify?url=${encodeURIComponent(config.webhook_url)}&platform=${config.webhook_platform}&top=5`,
        { method: "POST" }
      );
      const data = await res.json();
      if (data.status === "sent") {
        setNotifyStatus("sent");
        setMessage(`Sent ${data.signals_count} signals!`);
      } else if (data.status === "no_signals") {
        setNotifyStatus("sent");
        setMessage("No signals right now");
      } else {
        setNotifyStatus("error");
        setMessage(data.message || "Failed");
      }
    } catch {
      setNotifyStatus("error");
      setMessage("Network error");
    }
  };

  if (!loaded) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="h-6 w-6 animate-spin rounded-full border-2 border-cyan-400 border-t-transparent" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Bell className="h-5 w-5 text-cyan-400" />
        <h1 className="text-lg font-bold">Notifications</h1>
      </div>

      {/* Auto-Alerts Toggle */}
      <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4 space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Zap className="h-4 w-4 text-amber-400" />
            <h2 className="text-sm font-semibold text-zinc-300">Auto-Alerts</h2>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-xs text-zinc-500">
              {config.auto_alerts_enabled ? "Enabled" : "Disabled"}
            </span>
            <Switch
              checked={config.auto_alerts_enabled}
              onCheckedChange={(checked) => setConfig({ ...config, auto_alerts_enabled: checked })}
            />
          </div>
        </div>
        <p className="text-xs text-zinc-500">
          When enabled, the server automatically sends alerts through your configured channels every
          time new buy/sell signals are detected (checked every ~2 minutes).
        </p>

        {/* Min confidence slider */}
        <div>
          <label className="mb-1 flex items-center justify-between text-xs text-zinc-500">
            <span>Minimum Confidence</span>
            <span className="font-mono text-zinc-300">{Math.round(config.min_confidence * 100)}%</span>
          </label>
          <input
            type="range"
            min={0.5}
            max={1.0}
            step={0.05}
            value={config.min_confidence}
            onChange={(e) => setConfig({ ...config, min_confidence: parseFloat(e.target.value) })}
            className="w-full accent-cyan-500"
          />
          <div className="flex justify-between text-[10px] text-zinc-600">
            <span>50%</span>
            <span>100%</span>
          </div>
        </div>
      </div>

      {/* Webhook config */}
      <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4 space-y-4">
        <div className="flex items-center gap-2">
          <MessageSquare className="h-4 w-4 text-cyan-400" />
          <h2 className="text-sm font-semibold text-zinc-300">Webhook (Discord / Telegram / Slack)</h2>
        </div>

        <div>
          <label className="mb-1 block text-xs text-zinc-500">Platform</label>
          <div className="flex gap-2">
            {(["discord", "telegram", "slack"] as const).map((p) => (
              <button
                key={p}
                onClick={() => setConfig({ ...config, webhook_platform: p })}
                className={cn(
                  "rounded-md px-3 py-1.5 text-xs font-medium capitalize transition-colors",
                  config.webhook_platform === p
                    ? "bg-cyan-600 text-white"
                    : "bg-zinc-800 text-zinc-400 hover:bg-zinc-700"
                )}
              >
                {p}
              </button>
            ))}
          </div>
        </div>

        <div>
          <label className="mb-1 block text-xs text-zinc-500">
            {config.webhook_platform === "discord"
              ? "Discord Webhook URL"
              : config.webhook_platform === "telegram"
              ? "Telegram Bot API URL"
              : "Slack Webhook URL"}
          </label>
          <input
            value={config.webhook_url}
            onChange={(e) => setConfig({ ...config, webhook_url: e.target.value })}
            placeholder={
              config.webhook_platform === "discord"
                ? "https://discord.com/api/webhooks/..."
                : config.webhook_platform === "telegram"
                ? "https://api.telegram.org/bot.../sendMessage?chat_id=..."
                : "https://hooks.slack.com/services/..."
            }
            className="w-full rounded border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-200 placeholder-zinc-600 focus:border-cyan-500 focus:outline-none"
          />
        </div>

        <div className="flex gap-3">
          <Button
            size="sm"
            variant="outline"
            onClick={testWebhook}
            disabled={!config.webhook_url || testStatus === "sending"}
          >
            {testStatus === "sending" ? "Sending..." : "Test Webhook"}
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={sendSignals}
            disabled={!config.webhook_url || notifyStatus === "sending"}
          >
            <Send className="mr-1 h-3 w-3" />
            {notifyStatus === "sending" ? "Sending..." : "Send Signals Now"}
          </Button>
        </div>
      </div>

      {/* SMS Config */}
      <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4 space-y-4">
        <div className="flex items-center gap-2">
          <Smartphone className="h-4 w-4 text-emerald-400" />
          <h2 className="text-sm font-semibold text-zinc-300">SMS Alerts</h2>
        </div>

        {/* SMS Method Selector */}
        <div>
          <label className="mb-1 block text-xs text-zinc-500">Delivery Method</label>
          <div className="flex gap-2">
            <button
              onClick={() => setConfig({ ...config, sms_method: "email_gateway" })}
              className={cn(
                "flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-colors",
                config.sms_method === "email_gateway"
                  ? "bg-emerald-600 text-white"
                  : "bg-zinc-800 text-zinc-400 hover:bg-zinc-700"
              )}
            >
              <Mail className="h-3 w-3" />
              Email Gateway (Free)
            </button>
            <button
              onClick={() => setConfig({ ...config, sms_method: "twilio" })}
              className={cn(
                "flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-colors",
                config.sms_method === "twilio"
                  ? "bg-emerald-600 text-white"
                  : "bg-zinc-800 text-zinc-400 hover:bg-zinc-700"
              )}
            >
              <Smartphone className="h-3 w-3" />
              Twilio
            </button>
          </div>
        </div>

        {/* Email Gateway: carrier selector */}
        {config.sms_method === "email_gateway" && (
          <div>
            <label className="mb-1 block text-xs text-zinc-500">Your Carrier</label>
            <select
              value={config.sms_carrier}
              onChange={(e) => setConfig({ ...config, sms_carrier: e.target.value })}
              className="w-full rounded border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-200 focus:border-cyan-500 focus:outline-none"
            >
              <option value="">Select your carrier...</option>
              {CARRIERS.map((c) => (
                <option key={c.key} value={c.key}>{c.label}</option>
              ))}
            </select>
          </div>
        )}

        {/* Method description */}
        <p className="text-xs text-zinc-500">
          {config.sms_method === "email_gateway"
            ? "Sends text messages via your carrier\u2019s email-to-SMS gateway. Free \u2014 just needs a Gmail account with an app password set on the server (SMTP_EMAIL, SMTP_PASSWORD)."
            : "Sends text messages via Twilio API. Requires TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM_NUMBER on the server."}
        </p>

        <div>
          <label className="mb-1 block text-xs text-zinc-500">
            Your Phone Number {config.sms_method === "email_gateway" ? "(10-digit US number)" : "(with country code)"}
          </label>
          <input
            value={config.sms_to}
            onChange={(e) => setConfig({ ...config, sms_to: e.target.value })}
            placeholder={config.sms_method === "email_gateway" ? "5559876543" : "+15559876543"}
            className="w-full rounded border border-zinc-700 bg-zinc-800 px-3 py-2 text-sm text-zinc-200 placeholder-zinc-600 focus:border-cyan-500 focus:outline-none"
          />
        </div>

        {/* SMS Consent Opt-In */}
        <div className="rounded-md border border-zinc-700 bg-zinc-800/50 p-3 space-y-2">
          <label className="flex items-start gap-3 cursor-pointer">
            <input
              type="checkbox"
              checked={config.sms_consent}
              onChange={(e) => setConfig({ ...config, sms_consent: e.target.checked })}
              className="mt-0.5 h-4 w-4 rounded border-zinc-600 accent-emerald-500"
            />
            <span className="text-xs text-zinc-300">
              I agree to receive automated SMS alerts from Momentum Signal Engine at the phone number
              provided above. Message frequency varies based on market activity. Message and data rates
              may apply. Reply STOP to unsubscribe at any time.
            </span>
          </label>
          {config.sms_consent && config.sms_consent_timestamp && (
            <p className="ml-7 text-[10px] text-zinc-600">
              Consent recorded: {new Date(config.sms_consent_timestamp).toLocaleString()}
            </p>
          )}
        </div>

        <Button
          size="sm"
          variant="outline"
          onClick={testSms}
          disabled={
            !config.sms_to ||
            !config.sms_consent ||
            (config.sms_method === "email_gateway" && !config.sms_carrier) ||
            smsTestStatus === "sending"
          }
        >
          <Smartphone className="mr-1 h-3 w-3" />
          {smsTestStatus === "sending" ? "Sending..." : "Send Test SMS"}
        </Button>
        {!config.sms_consent && config.sms_to && (
          <p className="text-[10px] text-amber-400">
            Please check the consent box above before sending SMS.
          </p>
        )}
        {config.sms_method === "email_gateway" && !config.sms_carrier && config.sms_to && config.sms_consent && (
          <p className="text-[10px] text-amber-400">
            Please select your carrier above.
          </p>
        )}
      </div>

      {/* Status message */}
      {message && (
        <div
          className={cn(
            "flex items-center gap-2 rounded-md p-3 text-sm",
            testStatus === "sent" || notifyStatus === "sent" || smsTestStatus === "sent" || saveStatus === "saved"
              ? "bg-emerald-950/30 text-emerald-400"
              : "bg-red-950/30 text-red-400"
          )}
        >
          {testStatus === "sent" || notifyStatus === "sent" || smsTestStatus === "sent" || saveStatus === "saved" ? (
            <Check className="h-4 w-4" />
          ) : (
            <AlertCircle className="h-4 w-4" />
          )}
          {message}
        </div>
      )}

      {/* Save button */}
      <Button
        onClick={saveConfig}
        disabled={saveStatus === "saving"}
        className="w-full bg-cyan-600 hover:bg-cyan-700"
      >
        {saveStatus === "saving" ? "Saving..." : saveStatus === "saved" ? "Saved!" : "Save Configuration"}
      </Button>

      {/* Instructions */}
      <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-4 space-y-3">
        <h2 className="text-sm font-semibold text-zinc-300">Setup Instructions</h2>

        <div className="space-y-2 text-xs text-zinc-400">
          <div>
            <h3 className="font-semibold text-zinc-300">Discord</h3>
            <ol className="ml-4 list-decimal space-y-1">
              <li>Go to your Discord server settings</li>
              <li>Navigate to Integrations &rarr; Webhooks</li>
              <li>Click &quot;New Webhook&quot; and copy the URL</li>
              <li>Paste the URL above and test</li>
            </ol>
          </div>

          <div>
            <h3 className="font-semibold text-zinc-300">Telegram</h3>
            <ol className="ml-4 list-decimal space-y-1">
              <li>Message @BotFather on Telegram to create a bot</li>
              <li>Get your bot token and your chat ID</li>
              <li>Use format: https://api.telegram.org/bot&lt;TOKEN&gt;/sendMessage?chat_id=&lt;CHAT_ID&gt;</li>
            </ol>
          </div>

          <div>
            <h3 className="font-semibold text-zinc-300">Slack</h3>
            <ol className="ml-4 list-decimal space-y-1">
              <li>Create an incoming webhook in your Slack workspace</li>
              <li>Copy the webhook URL and paste above</li>
            </ol>
          </div>

          <div>
            <h3 className="font-semibold text-emerald-300">SMS via Email Gateway (Free)</h3>
            <ol className="ml-4 list-decimal space-y-1">
              <li>Create a Gmail App Password (Google Account &rarr; Security &rarr; App Passwords)</li>
              <li>Set these environment variables on your server:</li>
            </ol>
            <pre className="mt-1 rounded bg-zinc-800 p-2 text-[10px] text-zinc-400">
{`SMTP_EMAIL=yourname@gmail.com
SMTP_PASSWORD=xxxx xxxx xxxx xxxx`}
            </pre>
            <p className="mt-1">Select your carrier, enter your 10-digit phone number, and test.</p>
          </div>

          <div>
            <h3 className="font-semibold text-emerald-300">SMS via Twilio (Paid)</h3>
            <ol className="ml-4 list-decimal space-y-1">
              <li>Sign up at twilio.com (free trial gives ~$15 credit)</li>
              <li>Get your Account SID, Auth Token, and a phone number</li>
              <li>Set these as environment variables on your server:</li>
            </ol>
            <pre className="mt-1 rounded bg-zinc-800 p-2 text-[10px] text-zinc-400">
{`TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_FROM_NUMBER=+15551234567`}
            </pre>
          </div>
        </div>
      </div>
    </div>
  );
}
