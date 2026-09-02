import { apiRequest, queryString } from "./client";
import type {
  IndexStatus,
  KnowledgeDocumentDto,
  KnowledgeDocumentsResponse,
  KnowledgeSectionDto,
  SourceType,
} from "./types";

export interface DocumentFilters {
  sectionId?: string;
  status?: IndexStatus | "";
}

export interface UploadDocumentInput {
  file: File;
  sectionId: string;
  sourceType: Exclude<SourceType, "resolved_case">;
}

export const knowledgeApi = {
  sections: (signal?: AbortSignal) =>
    apiRequest<KnowledgeSectionDto[]>("/api/admin/knowledge/sections", { signal }),
  createSection: (name: string, signal?: AbortSignal) =>
    apiRequest<KnowledgeSectionDto>("/api/admin/knowledge/sections", {
      method: "POST",
      json: { name },
      signal,
    }),
  updateSection: (
    id: string,
    patch: Partial<Pick<KnowledgeSectionDto, "name" | "isEnabled">>,
    signal?: AbortSignal,
  ) =>
    apiRequest<KnowledgeSectionDto>(`/api/admin/knowledge/sections/${id}`, {
      method: "PATCH",
      json: patch,
      signal,
    }),
  deleteSection: (id: string, signal?: AbortSignal) =>
    apiRequest<void>(`/api/admin/knowledge/sections/${id}`, {
      method: "DELETE",
      signal,
    }),
  documents: (filters: DocumentFilters, signal?: AbortSignal) =>
    apiRequest<KnowledgeDocumentsResponse>(
      `/api/admin/knowledge/documents${queryString({
        section_id: filters.sectionId,
        status: filters.status,
      })}`,
      { signal },
    ),
  uploadDocument: (input: UploadDocumentInput, signal?: AbortSignal) => {
    const form = new FormData();
    form.set("file", input.file);
    form.set("section_id", input.sectionId);
    form.set("source_type", input.sourceType);
    return apiRequest<KnowledgeDocumentDto>("/api/admin/knowledge/documents", {
      method: "POST",
      body: form,
      signal,
    });
  },
  document: (id: string, signal?: AbortSignal) =>
    apiRequest<KnowledgeDocumentDto>(`/api/admin/knowledge/documents/${id}`, { signal }),
  updateDocument: (
    id: string,
    patch: Partial<Pick<KnowledgeDocumentDto, "title" | "isEnabled" | "oneCVersion" | "tags">>,
    signal?: AbortSignal,
  ) =>
    apiRequest<KnowledgeDocumentDto>(`/api/admin/knowledge/documents/${id}`, {
      method: "PATCH",
      json: patch,
      signal,
    }),
  reindex: (id: string, signal?: AbortSignal) =>
    apiRequest<KnowledgeDocumentDto>(`/api/admin/knowledge/documents/${id}/reindex`, {
      method: "POST",
      signal,
    }),
  deleteDocument: (id: string, signal?: AbortSignal) =>
    apiRequest<void>(`/api/admin/knowledge/documents/${id}`, {
      method: "DELETE",
      signal,
    }),
};
