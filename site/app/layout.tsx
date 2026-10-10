import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";
import "./globals.css";

export const metadata: Metadata = {
  title: "Ghost — Local code review and tested repairs",
  description:
    "Ghost is a local development agent for Python and JavaScript/TypeScript security reviews, failure investigation, and tested repairs you approve. Open source. macOS and Linux.",
  icons: { icon: "/assets/ghost-icon.svg" },
  openGraph: {
    title: "Ghost — Local code review and tested repairs",
    description:
      "Review code, investigate failures, and test a proposed repair in your terminal. Your approval before source changes.",
    type: "website",
  },
};

export const viewport: Viewport = { themeColor: "#101720" };

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
