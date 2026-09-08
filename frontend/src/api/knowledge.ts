import { apiRequest, queryString } from "./client";
import type {
  KnowledgeDocumentDto,
  KnowledgeDocumentsResponse,
  KnowledgeSectionDto,
} from "./types";

export interface DocumentFilters {
  sectionId?: string;
}

export interface UploadDocumentInput {
  file: File;
  sectionId: string;
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
      })}`,
      { signal },
    ),
  uploadDocument: (input: UploadDocumentInput, signal?: AbortSignal) => {
    const form = new FormData();
    form.set("file", input.file);
    return apiRequest<KnowledgeDocumentDto>(`/api/admin/knowledge/sections/${input.sectionId}/documents`, {
      method: "POST",
      body: form,
      signal,
    });
  },
  document: (id: string, signal?: AbortSignal) =>
    apiRequest<KnowledgeDocumentDto>(`/api/admin/knowledge/documents/${id}`, { signal }),
  documentDownloadUrl: (id: string) => `/api/admin/knowledge/documents/${id}/download`,
  updateDocument: (
    id: string,
    patch: Pick<KnowledgeDocumentDto, "isEnabled">,
    signal?: AbortSignal,
  ) =>
    apiRequest<KnowledgeDocumentDto>(`/api/admin/knowledge/documents/${id}`, {
      method: "PATCH",
      json: patch,
      signal,
    }),
  deleteDocument: (id: string, signal?: AbortSignal) =>
    apiRequest<void>(`/api/admin/knowledge/documents/${id}`, {
      method: "DELETE",
      signal,
    }),
  reindex: (id: string, signal?: AbortSignal) =>
    apiRequest<KnowledgeDocumentDto>(`/api/admin/knowledge/documents/${id}/reindex`, {
      method: "POST",
      signal,
    }),
};
