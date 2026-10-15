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
  const url = `${API_URL}/${path}`;
  let response: Response;
  try {
    response = await fetch(url, {
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
      signal: AbortSignal.timeout(60000),
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "TimeoutError") {
      throw new Error(
        `La API no respondió a tiempo (${API_URL}). Render puede estar iniciando; intenta nuevamente.`,
      );
    }
    throw new Error(
      `No se pudo conectar con la API (${API_URL}). Comprueba VITE_API_URL en el build de Cloudflare y CORS_ALLOWED_ORIGINS en Render.`,
    );
  }
  const isJson = response.headers
    .get("content-type")
    ?.includes("application/json");
  if (!isJson) {
    throw new Error(
      `La API devolvió una respuesta que no es JSON (HTTP ${response.status}, ${url}). Comprueba que VITE_API_URL apunte al backend de Render y vuelve a compilar el frontend.`,
    );
  }
  const data = await response.json().catch(() => null);
  if (response.ok && data === null) {
    throw new Error(`La API devolvió JSON inválido (${url}).`);
  }
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
