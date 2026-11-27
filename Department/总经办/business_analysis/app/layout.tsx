import type { Metadata, Viewport } from "next";
import "./globals.css";

const title = "经营分析";
const description = "连接 SQL Server、支持实时公式追溯的本地经营分析平台。";

export function generateMetadata(): Metadata {
  return {
    title,
    description,
    openGraph: {
      type: "website",
      locale: "zh_CN",
      title,
      description,
    },
    twitter: { card: "summary", title, description },
  };
}

export const viewport: Viewport = {
  colorScheme: "light dark",
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f4f6fb" },
    { media: "(prefers-color-scheme: dark)", color: "#0c111b" },
  ],
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN" suppressHydrationWarning>
      <body>{children}</body>
    </html>
  );
}
