// Load the shared stylesheet.
import "./globals.css";

// Metadata type for the document title and description.
import type { Metadata } from "next";

// Title and description shown for the Phase 0 page.
export const metadata: Metadata = {
  // Browser tab title.
  title: "PhotoSpace",
  // Short description of this skeleton page.
  description: "PhotoSpace API health status",
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
