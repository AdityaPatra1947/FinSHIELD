import type { ReactNode } from "react";
import { Inter, Krona_One } from "next/font/google";
import Shell from "@/components/Shell";
import { AuthProvider } from "@/lib/auth";
import "./globals.css";

const display = Krona_One({ subsets: ["latin"], weight: "400", variable: "--font-display" });
const body = Inter({ subsets: ["latin"], variable: "--font-body" });

export const metadata = {
  title: "FinShield — spend clearly, score fraud honestly",
  description: "Educational banking analytics: spending reports, three fraud classifiers and customer segments on synthetic data.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" className={`${display.variable} ${body.variable}`}>
      <body>
        <AuthProvider>
          <Shell>{children}</Shell>
        </AuthProvider>
      </body>
    </html>
  );
}
