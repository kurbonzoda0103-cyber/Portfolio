import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "NicheLab — YouTube Research Tool",
  description: "Find profitable YouTube niches, analyze competitors, and grow your channel",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="h-full">
      <body className="h-full antialiased">{children}</body>
    </html>
  );
}
