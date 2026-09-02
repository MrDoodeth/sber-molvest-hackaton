import {
  type ChangeEvent,
  type KeyboardEvent,
  type ReactNode,
  forwardRef,
  useEffect,
  useRef,
  useState,
} from "react";
import {
  Bot,
  ChevronDown,
  FileText,
  Image as ImageIcon,
  Paperclip,
  Send,
  ShieldCheck,
  Sparkles,
  UserRound,
  X,
} from "lucide-react";
import type { AttachmentDto, DialogSummary, MessageDto, SourceRef } from "../../api/types";
import { Badge, Button, IconButton } from "../ui";
import {
  cn,
  dialogStatusLabel,
  formatBytes,
  formatDateTime,
  formatPercent,
  safeAttachmentUrl,
} from "../utils";

const IMAGE_LIMIT = 15 * 1024 * 1024;
const DOCUMENT_LIMIT = 40 * 1024 * 1024;
const IMAGE_EXTENSIONS = [".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"];
const DOCUMENT_EXTENSIONS = [".txt", ".doc", ".docx", ".pdf", ".epub", ".ppt", ".pptx", ".xlsx"];
export const RUNTIME_ATTACHMENT_ACCEPT = [...IMAGE_EXTENSIONS, ...DOCUMENT_EXTENSIONS].join(",");

export function validateRuntimeAttachment(file: File): string | null {
  const extension = `.${file.name.split(".").pop()?.toLowerCase() ?? ""}`;
  const isImage = file.type.startsWith("image/") || IMAGE_EXTENSIONS.includes(extension);
  const isDocument = DOCUMENT_EXTENSIONS.includes(extension);
  if (!isImage && !isDocument) {
    return "Поддерживаются изображения PNG/JPEG/TIFF/BMP и документы TXT/DOC/DOCX/PDF/EPUB/PPT/PPTX/XLSX.";
  }
  const limit = isImage ? IMAGE_LIMIT : DOCUMENT_LIMIT;
  if (file.size > limit) {
    return isImage ? "Изображение должно быть не больше 15 МБ." : "Документ должен быть не больше 40 МБ.";
  }
  return null;
}

export function DialogStatusBadge({ dialog }: { dialog: Pick<DialogSummary, "status" | "mode"> }) {
  const label = dialogStatusLabel(dialog);
  const tone = dialog.status === "closed" ? "neutral" : dialog.mode === "operator_support" ? "info" : "success";
  return <Badge tone={tone}>{label}</Badge>;
}

export function MessageSources({ sources }: { sources: SourceRef[] }) {
  if (!sources.length) return null;
  return (
    <details className="group mt-3 border-t border-current/10 pt-2 text-xs">
      <summary className="flex cursor-pointer list-none items-center gap-1.5 font-bold opacity-75 hover:opacity-100">
        Источники ({sources.length})
        <ChevronDown className="size-3.5 transition group-open:rotate-180" aria-hidden="true" />
      </summary>
      <ul className="mt-2 grid gap-1.5">
        {sources.map((source) => (
          <li key={`${source.documentId}-${source.label}`} className="rounded-lg bg-black/5 px-2.5 py-2 leading-5">
            <span className="mr-1 font-extrabold">[{source.label}]</span>
            {source.title}
          </li>
        ))}
      </ul>
    </details>
  );
}

export function AttachmentCard({ attachment, showAnalysis = false }: { attachment: AttachmentDto; showAnalysis?: boolean }) {
  const url = safeAttachmentUrl(attachment);
  const isImage = attachment.mimeType.startsWith("image/");
  const body = (
    <div className="flex min-w-0 items-center gap-2.5">
      <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-black/5">
        {isImage ? <ImageIcon className="size-4" /> : <FileText className="size-4" />}
      </span>
      <span className="min-w-0">
        <span className="block truncate text-xs font-bold">{attachment.fileName}</span>
        {attachment.sizeBytes !== undefined && <span className="text-[11px] opacity-65">{formatBytes(attachment.sizeBytes)}</span>}
      </span>
    </div>
  );
  return (
    <div className="mt-3">
      {isImage && url && (
        <a href={url} target="_blank" rel="noreferrer" className="mb-2 block overflow-hidden rounded-xl border border-black/10">
          <img src={url} alt={`Вложение ${attachment.fileName}`} className="max-h-56 w-full object-cover" />
        </a>
      )}
      {url ? (
        <a href={url} target="_blank" rel="noreferrer" className="block rounded-xl border border-black/10 p-2.5 transition hover:bg-black/5">
          {body}
        </a>
      ) : (
        <div className="rounded-xl border border-black/10 p-2.5">{body}</div>
      )}
      {showAnalysis && (attachment.extractedText || attachment.visualSummary) && (
        <details className="mt-2 rounded-xl bg-black/5 px-3 py-2 text-xs">
          <summary className="cursor-pointer font-bold">Анализ изображения</summary>
          {attachment.extractedText && <p className="mt-2 whitespace-pre-wrap leading-5"><strong>Распознано:</strong> {attachment.extractedText}</p>}
          {attachment.visualSummary && <p className="mt-2 whitespace-pre-wrap leading-5"><strong>Контекст:</strong> {attachment.visualSummary}</p>}
        </details>
      )}
    </div>
  );
}

function authorMeta(message: MessageDto) {
  if (message.authorType === "user") return { label: "Вы", icon: UserRound, bubble: "bg-molvest-800 text-white", align: "justify-end" };
  if (message.authorType === "assistant") return { label: "GigaChat", icon: Sparkles, bubble: "border border-indigo-100 bg-white text-stone-800 shadow-sm", align: "justify-start" };
  return {
    label: `Оператор${message.author?.displayName ? ` · ${message.author.displayName}` : ""}`,
    icon: ShieldCheck,
    bubble: "border border-sky-100 bg-sky-50 text-slate-800",
    align: "justify-start",
  };
}

export function MessageBubble({ message, showConfidence = false, showAttachmentAnalysis = false }: { message: MessageDto; showConfidence?: boolean; showAttachmentAnalysis?: boolean }) {
  if (message.authorType === "system") {
    return (
      <div className="message-enter my-3 flex justify-center">
        <div className="max-w-xl rounded-full border border-dashed border-stone-300 bg-stone-50 px-4 py-2 text-center text-xs font-semibold text-stone-600">
          {message.text}
          {showConfidence && message.confidence !== undefined && <span className="ml-2 text-stone-400">Confidence {formatPercent(message.confidence)}</span>}
        </div>
      </div>
    );
  }
  const meta = authorMeta(message);
  const Icon = meta.icon;
  return (
    <article className={cn("message-enter flex", meta.align)} data-message-id={message.id}>
      <div className={cn("max-w-[88%] rounded-2xl px-4 py-3 sm:max-w-[74%]", meta.bubble, message.authorType === "user" ? "rounded-br-md" : "rounded-bl-md")}>
        <div className="mb-1.5 flex items-center gap-1.5 text-[11px] font-extrabold uppercase tracking-[0.08em] opacity-70">
          <Icon className="size-3.5" aria-hidden="true" />
          {meta.label}
          {showConfidence && message.confidence !== undefined && <span>· {formatPercent(message.confidence)}</span>}
        </div>
        <p className="whitespace-pre-wrap break-words text-sm leading-6">{message.text}</p>
        {message.attachments.map((attachment) => (
          <AttachmentCard key={attachment.id} attachment={attachment} showAnalysis={showAttachmentAnalysis} />
        ))}
        <MessageSources sources={message.sources} />
        <time className="mt-2 block text-right text-[10px] opacity-55" dateTime={message.createdAt}>{formatDateTime(message.createdAt)}</time>
      </div>
    </article>
  );
}

export function StreamingMessage({ text, label = "GigaChat формирует ответ" }: { text: string; label?: string }) {
  return (
    <div className="message-enter flex justify-start" aria-live="polite">
      <div className="max-w-[88%] rounded-2xl rounded-bl-md border border-indigo-100 bg-white px-4 py-3 text-stone-800 shadow-sm sm:max-w-[74%]">
        <div className="mb-1.5 flex items-center gap-1.5 text-[11px] font-extrabold uppercase tracking-[0.08em] text-indigo-600">
          <Bot className="size-3.5" /> {label}
        </div>
        {text ? <p className="whitespace-pre-wrap break-words text-sm leading-6">{text}<span className="ml-0.5 inline-block h-4 w-0.5 animate-pulse bg-indigo-500 align-middle" /></p> : <div className="flex gap-1 py-2"><i className="size-1.5 animate-bounce rounded-full bg-indigo-400" /><i className="size-1.5 animate-bounce rounded-full bg-indigo-400 [animation-delay:120ms]" /><i className="size-1.5 animate-bounce rounded-full bg-indigo-400 [animation-delay:240ms]" /></div>}
      </div>
    </div>
  );
}

export function MessageList({
  messages,
  streamingText,
  streamingLabel,
  topAction,
  showConfidence = false,
  showAttachmentAnalysis = false,
  empty,
}: {
  messages: MessageDto[];
  streamingText?: string | null;
  streamingLabel?: string;
  topAction?: ReactNode;
  showConfidence?: boolean;
  showAttachmentAnalysis?: boolean;
  empty?: ReactNode;
}) {
  const endRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "end" });
  }, [messages.length, streamingText]);
  if (!messages.length && !streamingText && empty) return <>{empty}</>;
  return (
    <div className="grid gap-3 px-4 py-5 sm:px-6">
      {topAction}
      {messages.map((message) => (
        <MessageBubble key={message.id} message={message} showConfidence={showConfidence} showAttachmentAnalysis={showAttachmentAnalysis} />
      ))}
      {streamingText !== undefined && streamingText !== null && <StreamingMessage text={streamingText} label={streamingLabel} />}
      <div ref={endRef} />
    </div>
  );
}

interface ChatComposerProps {
  value: string;
  onChange: (value: string) => void;
  onSend: () => void;
  disabled?: boolean;
  pending?: boolean;
  placeholder?: string;
  attachment?: File;
  onAttachmentChange?: (file?: File) => void;
  attachmentError?: string;
  onAttachmentError?: (message?: string) => void;
  footer?: ReactNode;
}

export const ChatComposer = forwardRef<HTMLTextAreaElement, ChatComposerProps>(function ChatComposer(
  {
    value,
    onChange,
    onSend,
    disabled = false,
    pending = false,
    placeholder = "Опишите проблему…",
    attachment,
    onAttachmentChange,
    attachmentError,
    onAttachmentError,
    footer,
  },
  ref,
) {
  const [preview, setPreview] = useState<string>();
  const inputRef = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (!attachment?.type.startsWith("image/")) {
      setPreview(undefined);
      return;
    }
    const url = URL.createObjectURL(attachment);
    setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [attachment]);
  const submit = () => {
    if (disabled || pending || (!value.trim() && !attachment)) return;
    onSend();
  };
  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      submit();
    }
  };
  const onFile = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    const error = validateRuntimeAttachment(file);
    onAttachmentError?.(error ?? undefined);
    if (!error) onAttachmentChange?.(file);
  };

  return (
    <div className="border-t border-stone-200 bg-white p-3 sm:p-4">
      {attachment && (
        <div className="mb-3 flex items-center gap-3 rounded-xl border border-molvest-100 bg-molvest-50 p-2.5">
          {preview ? <img src={preview} alt="Предпросмотр вложения" className="size-12 rounded-lg object-cover" /> : <FileText className="mx-2 size-5 text-molvest-600" />}
          <div className="min-w-0 flex-1">
            <p className="truncate text-xs font-bold text-molvest-900">{attachment.name}</p>
            <p className="text-[11px] text-stone-500">{formatBytes(attachment.size)}</p>
          </div>
          <IconButton type="button" aria-label="Удалить вложение" onClick={() => { onAttachmentChange?.(undefined); onAttachmentError?.(undefined); }}>
            <X className="size-4" />
          </IconButton>
        </div>
      )}
      {attachmentError && <p className="mb-2 text-xs font-medium text-red-700" role="alert">{attachmentError}</p>}
      <div className="flex items-end gap-2 rounded-2xl border border-stone-200 bg-stone-50 p-2 focus-within:border-molvest-400 focus-within:ring-3 focus-within:ring-molvest-100">
        {onAttachmentChange && (
          <>
            <input ref={inputRef} name="attachment" type="file" className="sr-only" accept={RUNTIME_ATTACHMENT_ACCEPT} onChange={onFile} disabled={disabled || pending || Boolean(attachment)} aria-label="Выбрать вложение" />
            <IconButton type="button" aria-label="Прикрепить файл" disabled={disabled || pending || Boolean(attachment)} onClick={() => inputRef.current?.click()}>
              <Paperclip className="size-5" />
            </IconButton>
          </>
        )}
        <textarea
          ref={ref}
          name="message"
          rows={1}
          value={value}
          disabled={disabled}
          placeholder={placeholder}
          onChange={(event) => onChange(event.target.value)}
          onKeyDown={onKeyDown}
          className="max-h-40 min-h-10 flex-1 resize-none bg-transparent px-1 py-2 text-sm leading-6 outline-none placeholder:text-stone-400 disabled:cursor-not-allowed"
        />
        <Button type="button" size="sm" className="size-10 shrink-0 px-0" aria-label="Отправить сообщение" disabled={disabled || (!value.trim() && !attachment)} pending={pending} onClick={submit}>
          <Send className="size-4" />
        </Button>
      </div>
      <div className="mt-2 flex items-center justify-between gap-3 text-[11px] text-stone-400">
        <span>Enter — отправить · Shift+Enter — новая строка</span>
        {footer}
      </div>
    </div>
  );
});
