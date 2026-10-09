import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";
import "./globals.css";

export const metadata: Metadata = {
  title: "Ghost — Find what you missed before you ship.",
  description:
    "Find what you missed before you ship. Ghost is an open-source security CLI for local Python and JavaScript/TypeScript reviews, with evidence and supported repairs.",
  icons: { icon: "/assets/ghost-icon.svg" },
  openGraph: {
    title: "Ghost — Find what you missed before you ship.",
    description:
      "Local security reviews. Clear findings. Repairs you approve. Meet your new pre-ship ritual.",
    type: "website",
  },
};

export const viewport: Viewport = { themeColor: "#101512" };

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
