// Server page. It reads API health, then hands the browser a client form.
// The browser posts to this app. This app calls FastAPI.

// The interactive page.
import { Designer } from "@/components/designer";

// Health reader. It uses API_URL on the server.
import { loadHealth } from "@/lib/health";

// Render on each request so a down API is not baked into a static page.
export const dynamic = "force-dynamic";

// Render the Phase 5 page.
export default async function HomePage() {
  // Read GET /health before sending HTML.
  const health = await loadHealth();
  // The client component prints the status and the forms.
  return <Designer initialHealth={health} />;
}
