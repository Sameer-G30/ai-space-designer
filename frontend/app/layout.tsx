// Load the shared stylesheet.
import "./globals.css";

// Metadata type for the document title and description.
import type { Metadata } from "next";

// Self-hosted Google fonts, exposed as CSS variables.
import { Fraunces, Inter } from "next/font/google";

// Body font.
const inter = Inter({ subsets: ["latin"], variable: "--font-inter", display: "swap" });
// Heading font.
const fraunces = Fraunces({ subsets: ["latin"], variable: "--font-fraunces", display: "swap" });

// Title and description shown for the Phase 5 page.
export const metadata: Metadata = {
  // Browser tab title.
  title: "PhotoSpace",
  // Short description of the room form and the design views.
  description: "PhotoSpace room form, Pareto designs, plan, 3D view, and generated image",
};

// Root layout that wraps every page.
export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  // Render the document shell.
  return (
    // English document. h-full lets the page fill the viewport.
    <html lang="en" className={`h-full ${inter.variable} ${fraunces.variable}`}>
      {/* Page body. min-h-full keeps the background full height. */}
      <body className="min-h-full">{children}</body>
    </html>
  );
}
