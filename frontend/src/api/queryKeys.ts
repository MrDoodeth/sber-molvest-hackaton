import type { AdminDialogFilters } from "./admin";
import type { DocumentFilters } from "./knowledge";
import type { MonitoringPeriod } from "./types";

function demoRole(): "user" | "operator" | "admin" {
  if (typeof window === "undefined") return "user";
  const role = window.location.pathname.split("/")[1];
  return role === "operator" || role === "admin" ? role : "user";
}

export const queryKeys = {
  user: {
    dialogs: () => ["user", "dialogs"] as const,
  },
  dialog: {
    detail: (dialogId: string) => [demoRole(), "dialog", dialogId, "detail"] as const,
    messages: (dialogId: string) => [demoRole(), "dialog", dialogId, "messages"] as const,
  },
  operator: {
    queues: () => ["operator", "queue"] as const,
    queue: (scope: "unassigned" | "mine") => ["operator", "queue", scope] as const,
  },
  kb: {
    sections: () => ["kb", "sections"] as const,
    allDocuments: () => ["kb", "documents"] as const,
    documents: (filters: DocumentFilters) => ["kb", "documents", filters] as const,
    document: (documentId: string) => ["kb", "document", documentId] as const,
  },
  admin: {
    allDialogs: () => ["admin", "dialogs"] as const,
    dialogs: (filters: AdminDialogFilters) => ["admin", "dialogs", filters] as const,
    dialog: (dialogId: string) => ["admin", "dialog", dialogId] as const,
    candidate: (candidateId: string) => ["admin", "candidate", candidateId] as const,
  },
  prompts: () => ["admin", "prompts"] as const,
  settings: () => ["admin", "settings"] as const,
  monitoring: (period: MonitoringPeriod) => ["admin", "monitoring", period] as const,
};
