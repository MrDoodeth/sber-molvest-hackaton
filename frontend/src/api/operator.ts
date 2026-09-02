import { apiRequest, queryString } from "./client";
import type { DialogSummary, OperatorDialogDetailDto, OperatorTemplateDto } from "./types";

export const operatorApi = {
  queue: (scope: "unassigned" | "mine", signal?: AbortSignal) =>
    apiRequest<DialogSummary[]>(`/api/operator/dialogs${queryString({ scope })}`, { signal }),
  detail: (dialogId: string, signal?: AbortSignal) =>
    apiRequest<OperatorDialogDetailDto>(`/api/dialogs/${dialogId}`, { signal }),
  claim: (dialogId: string, signal?: AbortSignal) =>
    apiRequest<OperatorDialogDetailDto>(`/api/operator/dialogs/${dialogId}/claim`, {
      method: "POST",
      signal,
    }),
  generateTemplate: (dialogId: string, signal?: AbortSignal) =>
    apiRequest<OperatorTemplateDto>(`/api/operator/dialogs/${dialogId}/template`, {
      method: "POST",
      signal,
    }),
  queueEventsUrl: "/api/operator/events",
  dialogEventsUrl: (dialogId: string) => `/api/operator/dialogs/${dialogId}/events`,
};
