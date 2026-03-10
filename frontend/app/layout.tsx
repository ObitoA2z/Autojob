import "./globals.css";
import Link from "next/link";
import type { ReactNode } from "react";

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="fr">
      <body>
        <main>
          <h1>AutoInfluence Dashboard</h1>
          <nav>
            <Link href="/dashboard" className="nav-link">Dashboard</Link>
            <Link href="/campaigns" className="nav-link">Campaigns</Link>
            <Link href="/applications" className="nav-link">Applications</Link>
          </nav>
          {children}
        </main>
      </body>
    </html>
  );
}
