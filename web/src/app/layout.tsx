import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import Link from "next/link";
import { AuthProvider } from "@/components/auth";
import { Nav } from "@/components/nav";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Procurement Intelligence",
  description: "Evidence-backed procurement planning from World Bank project history",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}>
      <body className="min-h-full flex flex-col">
        <AuthProvider>
          <header className="border-b border-line bg-surface">
            <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-8 gap-y-2 px-4 py-3">
              <Link href="/" className="font-semibold tracking-tight">
                Procurement Intelligence
              </Link>
              <Nav />
            </div>
          </header>
          <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-8">{children}</main>
          <footer className="border-t border-line px-4 py-4 text-center text-xs text-muted">
            Data: World Bank Projects, Procurement Notices, Documents &amp; Reports and CPIA APIs. ·{" "}
            <Link href="/data-handling" className="underline">
              How your data is handled
            </Link>
          </footer>
        </AuthProvider>
      </body>
    </html>
  );
}
