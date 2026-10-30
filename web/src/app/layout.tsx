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
            <div className="mx-auto flex max-w-[1800px] flex-wrap items-center gap-x-8 gap-y-2 px-4 py-3 lg:px-8">
              <Link href="/" className="flex items-center gap-2.5 font-semibold tracking-tight">
                <span className="grid size-7 place-items-center rounded-lg bg-gradient-to-br from-brand-strong to-teal-500 text-white shadow-[0_2px_10px_rgba(74,116,214,0.25)]" aria-hidden>
                  <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round">
                    <path d="M2.5 11V5l5.5-3 5.5 3v6L8 14z" />
                    <path d="M8 2v12M2.5 5L8 8l5.5-3" />
                  </svg>
                </span>
                Procurement Intelligence
              </Link>
              <Nav />
            </div>
          </header>
          <main className="mx-auto w-full max-w-[1800px] flex-1 px-4 py-8 lg:px-8">{children}</main>
          <footer className="border-t border-line px-4 py-4 text-center text-xs text-ink-muted">
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
