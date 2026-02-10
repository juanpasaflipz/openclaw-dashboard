import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  icons: {
    icon: "/logo.webp",
    apple: "/logo.webp",
  },
  title: "Green Monkey — AI Agent Management, Simplified",
  description:
    "Deploy AI agents across 12 platforms with 9 LLM providers. Bring your own API keys. One dashboard to manage them all.",
  keywords: [
    "AI agents",
    "chatbot deployment",
    "LLM",
    "multi-channel",
    "Telegram bot",
    "Discord bot",
    "WhatsApp bot",
    "AI management",
  ],
  openGraph: {
    title: "Green Monkey — AI Agent Management, Simplified",
    description:
      "Deploy AI agents across 12 platforms with 9 LLM providers. Bring your own API keys.",
    url: "https://greenmonkey.dev",
    siteName: "Green Monkey",
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title: "Green Monkey — AI Agent Management, Simplified",
    description:
      "Deploy AI agents across 12 platforms with 9 LLM providers. Bring your own API keys.",
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className={inter.className}>{children}</body>
    </html>
  );
}
