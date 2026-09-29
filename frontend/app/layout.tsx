// Load the shared stylesheet.
import "./globals.css";

// Metadata type for the document title and description.
import type { Metadata } from "next";

// Title and description shown for the Phase 5 page.
export const metadata: Metadata = {
  // Browser tab title.
  title: "PhotoSpace",
  // Short description of the room form and the design views.
  description: "PhotoSpace room form, Pareto designs, plan, and box view",
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
    <html lang="en" className="h-full">
      {/* Page body. min-h-full keeps the background full height. */}
      <body className="min-h-full">{children}</body>
    </html>
  );
}
