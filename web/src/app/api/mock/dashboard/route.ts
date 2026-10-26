import { dashboard } from "@/lib/mock/dashboard";

export async function GET() {
  return Response.json(dashboard());
}
