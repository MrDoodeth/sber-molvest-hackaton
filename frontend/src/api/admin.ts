import { apiRequest, queryString } from "./client";
import type {
  AdminDialogDetailDto,
  AdminDialogListItem,
  CaseCardDto,
  FeedbackVerdict,
  KnowledgeCandidateDto,
  PageResponse,
} from "./types";

export interface AdminDialogFilters {
  feedback: FeedbackVerdict | "unrated";
  page: number;
  date?: string;
  resolvedBy?: "ai" | "operator" | "";
  hasAttachment?: boolean;
}

export const adminApi = {
  dialogs: (filters: AdminDialogFilters, signal?: AbortSignal) =>
    apiRequest<PageResponse<AdminDialogListItem>>(
      `/api/admin/dialogs${queryString({
        feedback: filters.feedback,
        page: filters.page,
        date: filters.date,
        resolved_by: filters.resolvedBy,
        has_attachment: filters.hasAttachment,
      })}`,
      { signal },
    ),
  dialog: (dialogId: string, signal?: AbortSignal) =>
    apiRequest<AdminDialogDetailDto>(`/api/admin/dialogs/${dialogId}`, { signal }),
  createCandidate: (dialogId: string, signal?: AbortSignal) =>
    apiRequest<KnowledgeCandidateDto>(`/api/admin/dialogs/${dialogId}/candidate`, {
      method: "POST",
      signal,
    }),
  candidate: (candidateId: string, signal?: AbortSignal) =>
    apiRequest<KnowledgeCandidateDto>(`/api/admin/candidates/${candidateId}`, { signal }),
  updateCandidate: (candidateId: string, generatedCard: CaseCardDto, signal?: AbortSignal) =>
    apiRequest<KnowledgeCandidateDto>(`/api/admin/candidates/${candidateId}`, {
      method: "PATCH",
      json: { generatedCard },
      signal,
    }),
  approveCandidate: (candidateId: string, sectionId: string, signal?: AbortSignal) =>
    apiRequest<KnowledgeCandidateDto>(`/api/admin/candidates/${candidateId}/approve`, {
      method: "POST",
      json: { sectionId },
      signal,
    }),
  rejectCandidate: (candidateId: string, signal?: AbortSignal) =>
    apiRequest<KnowledgeCandidateDto>(`/api/admin/candidates/${candidateId}/reject`, {
      method: "POST",
      signal,
    }),
  deleteDialog: (dialogId: string, signal?: AbortSignal) =>
    apiRequest<void>(`/api/admin/dialogs/${dialogId}`, { method: "DELETE", signal }),
};
