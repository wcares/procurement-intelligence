// The in-app mock has no accounts: everyone is the demo admin (like PROCINTEL_AUTH=off in the backend).
export async function GET() {
  return Response.json({ username: "demo", role: "admin", mode: "off" });
}
