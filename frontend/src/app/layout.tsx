import type { Metadata } from "next";
import localFont from "next/font/local";
import "./globals.css";
import { Sidebar } from "@/components/layout/sidebar";
import { Providers } from "@/components/layout/providers";
import { CommandPalette } from "@/components/layout/command-palette";
import { TickerBar } from "@/components/layout/ticker-bar";
import { FeedbackWidget } from "@/components/layout/feedback-widget";

const geistSans = localFont({
  src: "./fonts/GeistVF.woff",
  variable: "--font-geist-sans",
  weight: "100 900",
});
const geistMono = localFont({
  src: "./fonts/GeistMonoVF.woff",
  variable: "--font-geist-mono",
  weight: "100 900",
});

export const metadata: Metadata = {
  title: "Momentum Signal Engine",
  description: "Stock trading analysis platform for high-probability momentum setups",
  manifest: "/manifest.json",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased bg-background text-foreground`}
      >
        <Providers>
          <CommandPalette />
          <Sidebar />
          <main className="min-h-screen p-4 pt-18 md:ml-60 md:p-6 md:pt-6">
            <TickerBar />
            {children}
          </main>
          <FeedbackWidget />
        </Providers>
      </body>
    </html>
  );
}
