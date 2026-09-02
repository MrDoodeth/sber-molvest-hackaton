import { apiRequest, queryString } from "./client";
import type {
  DialogDetailDto,
  DialogFeedbackDto,
  DialogSummary,
  FeedbackVerdict,
  KnowledgeCandidateDto,
  MessageDto,
  MessagePageDto,
} from "./types";

export interface SendMessageInput {
  clientMessageId: string;
  text: string;
  attachments?: File[];
}

export const dialogsApi = {
  list: (signal?: AbortSignal) => apiRequest<DialogSummary[]>("/api/dialogs", { signal }),
  create: (signal?: AbortSignal) =>
    apiRequest<DialogDetailDto>("/api/dialogs", { method: "POST", signal }),
  detail: (dialogId: string, signal?: AbortSignal) =>
    apiRequest<DialogDetailDto>(`/api/dialogs/${dialogId}`, { signal }),
  messages: (dialogId: string, cursor?: string, signal?: AbortSignal) =>
    apiRequest<MessagePageDto>(
      `/api/dialogs/${dialogId}/messages${queryString({ cursor, limit: 50 })}`,
      { signal },
    ),
  sendMessage: (dialogId: string, input: SendMessageInput, signal?: AbortSignal) => {
    const form = new FormData();
    form.set("client_message_id", input.clientMessageId);
    form.set("text", input.text);
    input.attachments?.forEach((attachment) => form.append("attachments", attachment));
    return apiRequest<MessageDto>(`/api/dialogs/${dialogId}/messages`, {
      method: "POST",
      body: form,
      signal,
    });
  },
  close: (dialogId: string, signal?: AbortSignal) =>
    apiRequest<DialogDetailDto>(`/api/dialogs/${dialogId}/close`, {
      method: "POST",
      signal,
    }),
  feedback: (dialogId: string, verdict: FeedbackVerdict, signal?: AbortSignal) =>
    apiRequest<DialogFeedbackDto>(`/api/dialogs/${dialogId}/feedback`, {
      method: "POST",
      json: { verdict },
      signal,
    }),
  proposeCandidate: (dialogId: string, signal?: AbortSignal) =>
    apiRequest<KnowledgeCandidateDto>(`/api/dialogs/${dialogId}/knowledge-candidate`, {
      method: "POST",
      signal,
    }),
  eventsUrl: (dialogId: string) => `/api/dialogs/${dialogId}/events`,
};
