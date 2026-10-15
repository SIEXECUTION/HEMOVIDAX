export type Role = { id: number; codigo: string; nombre: string };
export type Account = {
  idUsuario: number;
  username: string;
  email: string;
  estado: string;
  roles: Role[];
  persona: {
    idPersona: number;
    ci: string;
    nombres: string;
    apellidos: string;
    nombreCompleto: string;
  } | null;
};
export type Session = {
  account: Account;
  access: string;
  refresh: string;
  role: string;
};
const key = "hemovida_cloud_session";
export function readSession(): Session | null {
  try {
    return JSON.parse(sessionStorage.getItem(key) || "null");
  } catch {
    return null;
  }
}
export function saveSession(session: Session | null) {
  if (session) sessionStorage.setItem(key, JSON.stringify(session));
  else sessionStorage.removeItem(key);
}
const configured = String(import.meta.env.VITE_API_URL || "")
  .trim()
  .replace(/\/+$/, "");
export const API_URL = configured
  ? configured.endsWith("/api")
    ? configured
    : `${configured}/api`
  : "/api";
export async function request<T = any>(
  path: string,
  body?: unknown,
  method?: string,
  anonymous = false,
): Promise<T> {
  const session = anonymous ? null : readSession();
  const response = await fetch(`${API_URL}/${path}`, {
    method: method || (body === undefined ? "GET" : "POST"),
    headers: {
      Accept: "application/json",
      ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
      ...(session
        ? {
            Authorization: `Bearer ${session.access}`,
            ...(session.role ? { "X-Active-Role": session.role } : {}),
          }
        : {}),
    },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    if (response.status === 401 && session)
      window.dispatchEvent(new Event("hemovida:expired"));
    const message =
      data?.detail ||
      (data &&
        Object.entries(data)
          .map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join(", ") : v}`)
          .join("; "));
    throw new Error(
      message || `No se pudo completar la operación (${response.status}).`,
    );
  }
  return data as T;
}
