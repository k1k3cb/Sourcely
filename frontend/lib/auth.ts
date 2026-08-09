import { cookies } from "next/headers";

import { apiFetch, type ApiError } from "@/lib/api";

const TOKEN_COOKIE = "token";

type CurrentUser = {
  id: string;
  email: string;
  is_active: boolean;
  created_at: string;
};

export async function setAuthCookieFromBackend(): Promise<void> {
  void cookies;
}

export async function getCurrentUserFromCookies(): Promise<CurrentUser | null> {
  const jar = await cookies();
  const token = jar.get(TOKEN_COOKIE)?.value;
  if (!token) return null;
  try {
    return await apiServerFetch<CurrentUser>("/api/v1/auth/me");
  } catch (err) {
    const e = err as ApiError;
    if (e.status === 401) return null;
    throw err;
  }
}

export async function apiServerFetch<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const jar = await cookies();
  const token = jar.get(TOKEN_COOKIE)?.value;
  const headers: Record<string, string> = {
    Accept: "application/json",
    ...(init.headers as Record<string, string> | undefined),
  };
  if (token) headers["Cookie"] = `${TOKEN_COOKIE}=${token}`;
  return apiFetch<T>(path, { ...init, headers });
}
