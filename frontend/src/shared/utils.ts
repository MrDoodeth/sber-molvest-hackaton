import type { AttachmentDto, DialogDetailDto, DialogSummary, MessageDto } from "../api/types";

export function cn(...classes: Array<string | false | null | undefined>): string {
  return classes.filter(Boolean).join(" ");
}

const dateTimeFormatter = new Intl.DateTimeFormat("ru-RU", {
  day: "2-digit",
  month: "short",
  hour: "2-digit",
  minute: "2-digit",
});

export function formatDateTime(value?: string): string {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "—" : dateTimeFormatter.format(date);
}

export function formatRelativeDate(value?: string): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  const delta = Date.now() - date.getTime();
  const minutes = Math.floor(delta / 60_000);
  if (minutes < 1) return "только что";
  if (minutes < 60) return `${minutes} мин назад`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} ч назад`;
  return dateTimeFormatter.format(date);
}

export function formatPercent(value: number): string {
  const normalized = value <= 1 ? value * 100 : value;
  return `${Math.round(normalized)}%`;
}

export function formatBytes(bytes?: number): string {
  if (bytes === undefined) return "";
  if (bytes < 1024) return `${bytes} Б`;
  if (bytes < 1024 ** 2) return `${Math.round(bytes / 1024)} КБ`;
  return `${(bytes / 1024 ** 2).toFixed(1)} МБ`;
}

export function truncateTitle(value: string, maxLength = 50): string {
  const characters = Array.from(value);
  if (characters.length <= maxLength) return value;
  return `${characters.slice(0, maxLength - 1).join("").trimEnd()}…`;
}

export function dialogStatusLabel(dialog: Pick<DialogSummary, "status" | "mode">): string {
  if (dialog.status === "closed") return "Закрыт";
  return dialog.mode === "operator_support" ? "Специалист подключён" : "AI отвечает";
}

export function mergePersistedMessages(...groups: MessageDto[][]): MessageDto[] {
  const byId = new Map<string, MessageDto>();
  groups.flat().forEach((message) => {
    const current = byId.get(message.id);
    if (!current || Date.parse(message.createdAt) >= Date.parse(current.createdAt)) {
      byId.set(message.id, message);
    }
  });
  return [...byId.values()].sort((left, right) => {
    const delta = Date.parse(left.createdAt) - Date.parse(right.createdAt);
    return delta || left.id.localeCompare(right.id);
  });
}

export interface SendAttempt {
  clientMessageId: string;
  text: string;
  attachments: File[];
}

export function createSendAttempt(text: string, attachments: File[] = []): SendAttempt {
  return {
    clientMessageId: crypto.randomUUID(),
    text,
    attachments,
  };
}

export function retryOrCreateSendAttempt(
  text: string,
  attachments: File[] = [],
  failedAttempt?: SendAttempt,
): SendAttempt {
  const normalized = text.trim();
  if (
    failedAttempt?.text === normalized
    && failedAttempt.attachments.length === attachments.length
    && failedAttempt.attachments.every((file, index) => file === attachments[index])
  ) {
    return failedAttempt;
  }
  return createSendAttempt(normalized, attachments);
}

export function canShowFeedback(dialog: Pick<DialogDetailDto, "status" | "feedback">): boolean {
  return dialog.status === "closed" && !dialog.feedback;
}

export function safeAttachmentUrl(attachment: Pick<AttachmentDto, "url">): string | undefined {
  if (!attachment.url) return undefined;
  try {
    const url = new URL(attachment.url, window.location.origin);
    if (url.origin !== window.location.origin || !url.pathname.startsWith("/api/")) return undefined;
    return `${url.pathname}${url.search}`;
  } catch {
    return undefined;
  }
}

export function getErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "Произошла непредвиденная ошибка";
}
