import { apiRequest } from "./client";
import type { AdminSettingsInput, AdminSettingsResponse, PromptType, SystemPromptDto } from "./types";

export const settingsApi = {
  prompts: (signal?: AbortSignal) =>
    apiRequest<SystemPromptDto[]>("/api/admin/prompts", { signal }),
  savePrompt: (type: PromptType, content: string, signal?: AbortSignal) =>
    apiRequest<SystemPromptDto>(`/api/admin/prompts/${type}`, {
      method: "PUT",
      json: { content },
      signal,
    }),
  settings: (signal?: AbortSignal) =>
    apiRequest<AdminSettingsResponse>("/api/admin/settings", { signal }),
  saveSettings: (settings: AdminSettingsInput, signal?: AbortSignal) =>
    apiRequest<AdminSettingsResponse>("/api/admin/settings", {
      method: "PUT",
      json: settings,
      signal,
    }),
};
