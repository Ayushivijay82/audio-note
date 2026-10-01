import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "Audio Notes",
  description: "Upload audio, get a transcript (Gnani ASR) and a summary.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className="h-full antialiased">
      <body className="min-h-full bg-zinc-50 text-zinc-900">
        <header className="border-b border-zinc-200 bg-white">
          <nav className="mx-auto flex max-w-4xl items-center gap-6 px-4 py-3">
            <Link href="/" className="font-semibold text-violet-700">
              Audio Notes
            </Link>
            <Link href="/" className="text-sm text-zinc-600 hover:text-zinc-900">
              Upload &amp; history
            </Link>
            <Link href="/architecture" className="text-sm text-zinc-600 hover:text-zinc-900">
              Architecture
            </Link>
          </nav>
        </header>
        <main className="mx-auto max-w-4xl px-4 py-8">{children}</main>
      </body>
    </html>
  );
}
