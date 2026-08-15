export const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
export async function request<T>(path: string, employee: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API}/api${path}`, { ...init, headers: { "Content-Type": "application/json", "X-Employee-Id": employee, ...(init?.headers || {}) }, cache: "no-store" });
  if (!response.ok) { const data = await response.json().catch(() => ({})); throw new Error(data.detail || `Request failed (${response.status})`); }
  return response.json();
}

