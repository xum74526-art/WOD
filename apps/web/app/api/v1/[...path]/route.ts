import { type NextRequest } from "next/server";
import { handleMobileApi } from "@/lib/mobile-api-adapter";

type Context = { params: Promise<{ path: string[] }> };

async function handler(request: NextRequest, context: Context) {
  const { path } = await context.params;
  return handleMobileApi(request, path);
}

export const dynamic = "force-dynamic";
export const GET = handler;
export const POST = handler;
export const PUT = handler;
export const PATCH = handler;
export const DELETE = handler;
