import { apiRequest } from "./client";
import type { CurrentUser, Role } from "./types";

export const authApi = {
  me: (signal?: AbortSignal) => apiRequest<CurrentUser>("/api/me", { signal }),
  demoLogin: (role: Role, signal?: AbortSignal) =>
    apiRequest<void>("/api/auth/demo-login", {
      method: "POST",
      json: { role },
      signal,
    }),
  logout: (signal?: AbortSignal) =>
    apiRequest<void>("/api/auth/logout", {
      method: "POST",
      signal,
    }),
};
