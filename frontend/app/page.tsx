// Server page. It hands the browser a client form.
// The browser posts to this app. This app calls FastAPI.

// The interactive page.
import { Designer } from "@/components/designer";

// Render the Phase 5 page.
export default function HomePage() {
  // The client component prints the forms and the results.
  return <Designer />;
}
