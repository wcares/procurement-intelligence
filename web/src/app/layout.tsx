import type { Metadata } from "next";
import { Open_Sans, Roboto_Mono } from "next/font/google";
import Link from "next/link";
import { AuthProvider } from "@/components/auth";
import { HeaderBar } from "@/components/nav";
import "./globals.css";

// The World Bank's web type: Open Sans for text, Roboto Mono for figures and code.
const openSans = Open_Sans({ variable: "--font-open-sans", subsets: ["latin"] });
const robotoMono = Roboto_Mono({ variable: "--font-roboto-mono", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Procurement Intelligence",
  description: "Evidence-backed procurement planning from World Bank project history",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${openSans.variable} ${robotoMono.variable} h-full antialiased`}>
      <body className="min-h-full flex flex-col">
        <AuthProvider>
          <header className="sticky top-0 z-40 border-t-[3px] border-b border-t-brand-2 border-b-line bg-surface print:hidden">
            <HeaderBar />
          </header>
          <main className="mx-auto w-full max-w-[1400px] flex-1 px-4 py-8 lg:px-8">{children}</main>
          <footer className="border-t border-line bg-subtle print:hidden">
            <div className="mx-auto flex max-w-[1400px] flex-wrap items-center justify-between gap-2 px-4 py-4 text-xs text-ink-muted lg:px-8">
              <span>
                A prototype built on World Bank open data: Projects, Procurement Notices, Documents &amp; Reports, Finances One and
                the World Development Indicators. Not a World Bank product.
              </span>
              <Link href="/data-handling" className="underline underline-offset-2 hover:text-foreground">How your data is handled</Link>
            </div>
          </footer>
        </AuthProvider>
      </body>
    </html>
  );
}
