export class AuthError extends Error {
  constructor() {
    super("需要访问口令");
    this.name = "AuthError";
  }
}

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = localStorage.getItem("eewAuthToken") || "";
  const headers = new Headers(options.headers);
  headers.set("Content-Type", "application/json");
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const response = await fetch(path, { ...options, headers });
  if (response.status === 401) throw new AuthError();
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}
