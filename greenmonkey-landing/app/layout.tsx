import type { Metadata } from "next";
import { Inter, Nunito_Sans } from "next/font/google";
import "./globals.css";

const inter = Inter({ subsets: ["latin"] });
const nunitoSans = Nunito_Sans({
  subsets: ["latin"],
  weight: ["400", "500", "600", "700", "800"],
  variable: "--font-nunito-sans",
});

export const metadata: Metadata = {
  icons: {
    icon: "/logo.webp",
    apple: "/logo.webp",
  },
  title: "Green Monkey — Autonomous AI Agents That Actually Do Work",
  description:
    "Deploy AI agents that plan, execute approved actions, and report back transparently. No black boxes. No runaway automation.",
  keywords: [
    "AI agents",
    "autonomous agents",
    "human-in-the-loop",
    "AI safety",
    "GitHub agent",
    "LLM agents",
    "AI automation",
    "agent framework",
  ],
  openGraph: {
    title: "Green Monkey — Autonomous AI Agents That Actually Do Work",
    description:
      "AI agents that plan, execute approved actions, and report back transparently. No black boxes.",
    url: "https://greenmonkey.dev",
    siteName: "Green Monkey",
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title: "Green Monkey — Autonomous AI Agents That Actually Do Work",
    description:
      "AI agents that plan, execute approved actions, and report back transparently. No black boxes.",
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className={`${inter.className} ${nunitoSans.variable}`}>{children}</body>
    </html>
  );
}
