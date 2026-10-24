import { options } from "@/lib/mock/engine";

// Static data, so this GET is prerendered at build time.
export async function GET() {
  return Response.json(options());
}
