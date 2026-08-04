import { cookies } from "next/headers";

import { api, type CurrentUser, type ApiError } from "@/lib/api";

const TOKEN_COOKIE = "token";

export async function setAuthCookieFromBackend(): Promise<void> {
  // No-op on the server when the backend already sets the cookie via Set-Cookie.
  // Kept for symmetry with potential future server-action login.
  void cookies;
}

export async function getCurrentUserFromCookies(): Promise<CurrentUser | null> {
  const jar = await cookies();
  const token = jar.get(TOKEN_COOKIE)?.value;
  if (!token) return null;
  try {
    return await api.get<CurrentUser>("/api/v1/auth/me");
  } catch (err) {
    const e = err as ApiError;
    if (e.status === 401) return null;
    throw err;
  }
}
