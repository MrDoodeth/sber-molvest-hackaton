export class ApiError extends Error {
  readonly code: string;
  readonly details?: unknown;
  readonly status: number;

  constructor(code: string, message: string, status: number, details?: unknown) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
    this.details = details;
  }
}

interface ErrorShape {
  code?: unknown;
  message?: unknown;
  details?: unknown;
  detail?: unknown;
}

const PAYLOAD_TOO_LARGE_MESSAGE = "Файл слишком большой. Изображение — до 15 МБ, документ — до 40 МБ.";

function isHtmlError(value: string): boolean {
  return /<\/?(?:html|head|body|title|h1)\b/i.test(value);
}

export function normalizeApiError(payload: unknown, status: number, statusText = ""): ApiError {
  const root = isRecord(payload) ? (payload as ErrorShape) : undefined;
  const detail = root && isRecord(root.detail) ? (root.detail as ErrorShape) : undefined;
  const source = detail ?? root;
  const stringDetail = root && typeof root.detail === "string" ? root.detail : undefined;
  const code = typeof source?.code === "string" ? source.code : `HTTP_${status}`;
  const rawMessage =
    typeof source?.message === "string"
      ? source.message
      : stringDetail ?? (typeof payload === "string" ? payload : undefined) ?? statusText ?? "Не удалось выполнить запрос";
  const message = status === 413
    ? PAYLOAD_TOO_LARGE_MESSAGE
    : isHtmlError(rawMessage)
      ? "Не удалось выполнить запрос"
      : rawMessage;
  const details = source?.details ?? (root && Array.isArray(root.detail) ? root.detail : undefined);

  return new ApiError(code, message || "Не удалось выполнить запрос", status, details);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function mapJsonKeys(value: unknown, mapKey: (key: string) => string): unknown {
  if (Array.isArray(value)) return value.map((item) => mapJsonKeys(item, mapKey));
  if (!isRecord(value)) return value;
  return Object.fromEntries(
    Object.entries(value).map(([key, item]) => [mapKey(key), mapJsonKeys(item, mapKey)]),
  );
}

function toCamelCase(key: string): string {
  return key.replace(/_([a-z0-9])/g, (_, character: string) => character.toUpperCase());
}

function toSnakeCase(key: string): string {
  return key.replace(/[A-Z]/g, (character) => `_${character.toLowerCase()}`);
}

interface ApiRequestOptions extends Omit<RequestInit, "body"> {
  body?: BodyInit | null;
  json?: unknown;
}

export async function apiRequest<T>(path: string, options: ApiRequestOptions = {}): Promise<T> {
  const headers = new Headers(options.headers);
  if (typeof window !== "undefined") {
    const role = window.location.pathname.split("/")[1];
    if (role === "user" || role === "operator" || role === "admin") {
      headers.set("X-Molvest-Role", role);
    }
  }
  let body = options.body;

  if (options.json !== undefined) {
    headers.set("Content-Type", "application/json");
    body = JSON.stringify(mapJsonKeys(options.json, toSnakeCase));
  }

  const response = await fetch(path, {
    ...options,
    headers,
    body,
  });

  const text = response.status === 204 ? "" : await response.text();
  let payload: unknown;
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      payload = text;
    }
  }

  if (!response.ok) {
    throw normalizeApiError(payload, response.status, response.statusText);
  }

  return mapJsonKeys(payload, toCamelCase) as T;
}

export function queryString(values: Record<string, string | number | boolean | null | undefined>): string {
  const params = new URLSearchParams();
  Object.entries(values).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") {
      params.set(key, String(value));
    }
  });
  const result = params.toString();
  return result ? `?${result}` : "";
}
