import { useAuthStore } from "@/lib/auth-store";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  status: number;
  code: string;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = useAuthStore.getState().token;
  const headers = new Headers(options.headers);
  if (!(options.body instanceof URLSearchParams)) {
    headers.set("Content-Type", "application/json");
  }
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const res = await fetch(`${API_URL}${path}`, { ...options, headers });
  const body = await res.json().catch(() => null);

  if (!res.ok || !body?.success) {
    if (res.status === 401) {
      useAuthStore.getState().logout();
    }
    throw new ApiError(
      res.status,
      body?.error?.code ?? "ERROR",
      body?.error?.message ?? res.statusText ?? "Request failed",
    );
  }
  return body.data as T;
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, data?: unknown) =>
    request<T>(path, { method: "POST", body: data !== undefined ? JSON.stringify(data) : undefined }),
  put: <T>(path: string, data?: unknown) =>
    request<T>(path, { method: "PUT", body: JSON.stringify(data) }),
};

export async function login(username: string, password: string) {
  const res = await fetch(`${API_URL}/api/v1/auth/token`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({ username, password }),
  });
  const body = await res.json().catch(() => null);
  if (!res.ok || !body?.success) {
    throw new ApiError(res.status, body?.error?.code ?? "UNAUTHORIZED", body?.error?.message ?? "Login failed");
  }
  return body.data as { access_token: string; token_type: string };
}

export { API_URL };
