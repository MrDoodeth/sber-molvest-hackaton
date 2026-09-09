export type Role = "user" | "operator" | "admin";
export type DialogStatus = "active" | "closed";
export type DialogMode = "ai_support" | "operator_support";
export type MessageAuthor = "user" | "assistant" | "operator" | "system";
export type FeedbackVerdict = "helpful" | "ai_error";
export type CandidateStatus = "pending" | "approved" | "rejected";
export type ModerationStatus = "unmoderated" | "approved" | "rejected";
export type CandidateSource = "user_feedback" | "operator" | "admin";
export type IndexStatus = "uploaded" | "processing" | "indexed" | "failed";
export type PromptType = "user_support" | "operator_gigachat" | "knowledge_card";
export type MonitoringPeriod = "today" | "7d" | "30d" | "all";

export interface UserRef {
  id: string;
  displayName: string;
}

export interface AttachmentDto {
  id: string;
  messageId: string;
  fileName: string;
  mimeType: string;
  sizeBytes?: number | null;
  url?: string;
}

export interface MessageDto {
  id: string;
  dialogId: string;
  authorType: MessageAuthor;
  author?: UserRef;
  text: string;
  confidence?: number;
  attachments: AttachmentDto[];
  createdAt: string;
}

export interface DialogFeedbackDto {
  id: string;
  dialogId: string;
  verdict: FeedbackVerdict;
  createdAt: string;
}

export interface CandidateRef {
  id: string;
  status: CandidateStatus;
  source: CandidateSource;
}

export interface DialogSummary {
  id: string;
  status: DialogStatus;
  mode: DialogMode;
  confidence: number;
  isProcessing: boolean;
  processingError?: string | null;
  assignedOperator?: UserRef;
  lastMessagePreview?: string;
  lastMessageAuthor?: MessageAuthor;
  title?: string;
  user?: UserRef;
  hasAttachment?: boolean;
  escalatedAt?: string;
  closedAt?: string;
  createdAt?: string;
  updatedAt: string;
  feedback?: DialogFeedbackDto;
  candidate?: CandidateRef;
}

export interface OperatorTemplateDto {
  dialogId: string;
  dialogUpdatedAt: string;
  text: string;
  createdAt: string;
}

export interface DialogDetailDto extends DialogSummary {
  channel: "web" | "bitrix24" | "redmine";
}

export type OperatorDialogDetailDto = DialogDetailDto;

export interface CursorPage<T> {
  items: T[];
  nextCursor?: string | null;
}

export type MessagePageDto = CursorPage<MessageDto>;

export interface KnowledgeSectionDto {
  id: string;
  name: string;
  isEnabled: boolean;
  isSystem?: boolean;
  documentCount?: number;
  createdAt: string;
}

export interface KnowledgeDocumentDto {
  id: string;
  sectionId: string;
  title: string;
  isEnabled: boolean;
  indexStatus: IndexStatus;
  indexError?: string;
  indexedAt?: string;
  createdAt?: string;
  updatedAt?: string;
  downloadUrl: string;
}

export interface KnowledgeDocumentsResponse {
  items: KnowledgeDocumentDto[];
}

export interface CaseCardDto {
  title: string;
  problem: string;
  result: string;
}

export interface KnowledgeCandidateDto extends CandidateRef {
  dialogId: string;
  generatedCard: CaseCardDto;
  resultingDocumentId?: string;
  resultingDocument?: Pick<KnowledgeDocumentDto, "id" | "title" | "indexStatus" | "indexError">;
  reviewedBy?: UserRef;
  reviewedAt?: string;
  createdAt: string;
}

export interface SystemPromptDto {
  id: string;
  type: PromptType;
  content: string;
  updatedAt: string;
  updatedBy?: UserRef;
}

export interface ModelOptionDto {
  id: string;
  label: string;
  contextLimit: number;
}

export interface AdminSettingsResponse {
  activeModel: string;
  gigachatContextRatio: number;
  gigachatMaxOutputTokens: number;
  embeddingContextRatio: number;
  ragTopK: number;
  operatorEscalationThreshold: number;
  capabilities: {
    gigachatContextLimit: number;
    embeddingContextLimit: number;
  };
  availableModels: ModelOptionDto[];
}

export type AdminSettingsInput = Omit<AdminSettingsResponse, "capabilities" | "availableModels">;

export interface AdminDialogListItem extends DialogSummary {
  resolvedBy: "ai" | "operator";
  lastConfidence?: number | null;
  moderationStatus: ModerationStatus;
}

export interface PageResponse<T> {
  items: T[];
  page: number;
  pageSize: number;
  total: number;
  totalPages: number;
}

export interface AdminDialogAuditDto {
  resolvedBy: "ai" | "operator";
  gigachatModel?: string;
  systemPrompt?: string;
  escalationThreshold?: number;
}

export interface AdminDialogDetailDto {
  dialog: DialogDetailDto;
  messages: MessageDto[];
  feedback?: DialogFeedbackDto;
  candidate?: CandidateRef;
  audit: AdminDialogAuditDto;
}

export interface MonitoringResponse {
  totalRequests: number;
  aiResolved: number;
  aiResolvedRate: number;
  escalations: number;
  escalationRate: number;
  failedRequests: number;
  averageResponseTimeMs: number;
  helpful: number;
  helpfulRate: number;
}

export type UserDialogEvent =
  | { type: "confidence"; value: number }
  | { type: "operator_connected"; operator?: UserRef; message: MessageDto }
  | { type: "assistant_token"; token: string }
  | { type: "assistant_done"; message: MessageDto }
  | { type: "operator_message"; message: MessageDto }
  | { type: "dialog_closed" }
  | { type: "error"; message: string };

export type OperatorQueueEvent =
  | { type: "ticket_available"; dialog: DialogSummary }
  | { type: "ticket_updated"; dialog: DialogSummary }
  | { type: "ticket_claimed"; dialogId: string; operator: UserRef }
  | { type: "ticket_closed"; dialogId: string };

export type OperatorDialogEvent =
  | { type: "user_message"; message: MessageDto }
  | { type: "operator_access_revoked"; operator: UserRef }
  | { type: "dialog_closed" }
  | { type: "error"; message: string };
