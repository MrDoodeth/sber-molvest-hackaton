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
  Download,
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
const IMAGE_REQUEST_LIMIT = 80 * 1024 * 1024;
export const MAX_RUNTIME_ATTACHMENTS = 10;
const IMAGE_EXTENSIONS = [".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"];
const DOCUMENT_EXTENSIONS = [".txt", ".doc", ".docx", ".pdf", ".epub", ".ppt", ".pptx", ".xlsx"];
const EMPTY_ATTACHMENTS: File[] = [];
export const RUNTIME_ATTACHMENT_ACCEPT = [...IMAGE_EXTENSIONS, ...DOCUMENT_EXTENSIONS].join(",");

export function isRuntimeImage(file: File): boolean {
  const extension = `.${file.name.split(".").pop()?.toLowerCase() ?? ""}`;
  return file.type.startsWith("image/") || IMAGE_EXTENSIONS.includes(extension);
}

export function validateRuntimeAttachment(file: File): string | null {
  const extension = `.${file.name.split(".").pop()?.toLowerCase() ?? ""}`;
  const isImage = isRuntimeImage(file);
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

export function validateRuntimeAttachments(files: File[]): string | null {
  if (files.length > MAX_RUNTIME_ATTACHMENTS) {
    return `Можно прикрепить не более ${MAX_RUNTIME_ATTACHMENTS} файлов.`;
  }
  for (const file of files) {
    const error = validateRuntimeAttachment(file);
    if (error) return error;
  }
  const imageBytes = files.reduce((total, file) => total + (isRuntimeImage(file) ? file.size : 0), 0);
  if (imageBytes >= IMAGE_REQUEST_LIMIT) {
    return "Суммарный размер изображений не должен превышать 80 МБ.";
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
  return (
    <div className="flex w-24 flex-col gap-1">
      {url ? (
        <a
          href={url}
          download={attachment.fileName}
          className="group relative flex aspect-square w-24 items-center justify-center overflow-hidden rounded-xl border border-black/10 bg-black/5 transition hover:border-molvest-300 hover:bg-black/10"
          title={`Скачать ${attachment.fileName}`}
          aria-label={`Скачать ${attachment.fileName}`}
        >
          {isImage ? <img src={url} alt={`Вложение ${attachment.fileName}`} className="size-full object-cover" /> : <FileText className="size-7 text-molvest-700" />}
          <span className="absolute inset-x-0 bottom-0 truncate bg-black/65 px-1.5 py-1 text-[10px] font-bold text-white">{attachment.fileName}</span>
          <span className="absolute right-1 top-1 rounded-md bg-black/55 p-1 text-white opacity-0 transition group-hover:opacity-100 group-focus-visible:opacity-100">
            <Download className="size-3.5" aria-hidden="true" />
          </span>
        </a>
      ) : (
        <div className="relative flex aspect-square w-24 items-center justify-center overflow-hidden rounded-xl border border-black/10 bg-black/5" title={attachment.fileName}>
          {isImage ? <ImageIcon className="size-7 text-molvest-700" /> : <FileText className="size-7 text-molvest-700" />}
          <span className="absolute inset-x-0 bottom-0 truncate bg-black/65 px-1.5 py-1 text-[10px] font-bold text-white">{attachment.fileName}</span>
        </div>
      )}
      {typeof attachment.sizeBytes === "number" && <span className="truncate px-1 text-[10px] opacity-65">{formatBytes(attachment.sizeBytes)}</span>}
      {showAnalysis && (attachment.extractedText || attachment.visualSummary) && (
        <details className="mt-1 w-72 max-w-[calc(100vw-3rem)] rounded-xl bg-black/5 px-3 py-2 text-xs">
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
        {message.attachments.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-2.5">
            {message.attachments.map((attachment) => (
              <AttachmentCard key={attachment.id} attachment={attachment} showAnalysis={showAttachmentAnalysis} />
            ))}
          </div>
        )}
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
  attachments?: File[];
  onAttachmentChange?: (files: File[]) => void;
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
    attachments = EMPTY_ATTACHMENTS,
    onAttachmentChange,
    attachmentError,
    onAttachmentError,
    footer,
  },
  ref,
) {
  const [previews, setPreviews] = useState<Array<string | undefined>>([]);
  const inputRef = useRef<HTMLInputElement>(null);
  useEffect(() => {
    const urls = attachments.map((file) => isRuntimeImage(file) ? URL.createObjectURL(file) : undefined);
    setPreviews(urls);
    return () => urls.forEach((url) => { if (url) URL.revokeObjectURL(url); });
  }, [attachments]);
  const submit = () => {
    if (disabled || pending || (!value.trim() && !attachments.length)) return;
    onSend();
  };
  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      submit();
    }
  };
  const onFile = (event: ChangeEvent<HTMLInputElement>) => {
    const selected = Array.from(event.target.files ?? []);
    event.target.value = "";
    if (!selected.length) return;
    const available = MAX_RUNTIME_ATTACHMENTS - attachments.length;
    if (available <= 0) {
      onAttachmentError?.(`Можно прикрепить не более ${MAX_RUNTIME_ATTACHMENTS} файлов.`);
      return;
    }
    const filesToAdd = selected.slice(0, available);
    const error = validateRuntimeAttachments([...attachments, ...filesToAdd]);
    if (error) {
      onAttachmentError?.(error);
      return;
    }
    onAttachmentChange?.([...attachments, ...filesToAdd]);
    onAttachmentError?.(selected.length > filesToAdd.length ? `Можно прикрепить не более ${MAX_RUNTIME_ATTACHMENTS} файлов.` : undefined);
  };
  const removeAttachment = (index: number) => {
    onAttachmentChange?.(attachments.filter((_, attachmentIndex) => attachmentIndex !== index));
    onAttachmentError?.(undefined);
  };

  return (
    <div className="border-t border-stone-200 bg-white p-3 sm:p-4">
      {attachments.length > 0 && (
        <div className="mb-3 flex flex-wrap gap-2">
          {attachments.map((file, index) => (
            <div key={`${file.name}-${file.lastModified}-${index}`} className="group relative size-20 overflow-hidden rounded-xl border border-molvest-100 bg-molvest-50">
              {previews[index] ? <img src={previews[index]} alt={`Предпросмотр ${file.name}`} className="size-full object-cover" /> : <div className="flex size-full items-center justify-center"><FileText className="size-7 text-molvest-600" /></div>}
              <span className="absolute inset-x-0 bottom-0 truncate bg-black/65 px-1.5 py-1 text-[10px] font-bold text-white" title={file.name}>{file.name}</span>
              <button type="button" className="absolute right-1 top-1 inline-flex size-6 items-center justify-center rounded-md bg-black/55 text-white opacity-100 transition hover:bg-black/75 sm:opacity-0 sm:group-hover:opacity-100 sm:group-focus-within:opacity-100" aria-label={`Удалить ${file.name}`} onClick={() => removeAttachment(index)}>
                <X className="size-3.5" />
              </button>
            </div>
          ))}
        </div>
      )}
      {attachmentError && <p className="mb-2 text-xs font-medium text-red-700" role="alert">{attachmentError}</p>}
      <div className="flex items-end gap-2 rounded-2xl border border-stone-200 bg-stone-50 p-2 focus-within:border-molvest-400 focus-within:ring-3 focus-within:ring-molvest-100">
        {onAttachmentChange && (
          <>
            <input ref={inputRef} name="attachments" type="file" className="sr-only" accept={RUNTIME_ATTACHMENT_ACCEPT} multiple onChange={onFile} disabled={disabled || pending || attachments.length >= MAX_RUNTIME_ATTACHMENTS} aria-label="Выбрать файлы" />
            <IconButton type="button" aria-label="Прикрепить файлы" disabled={disabled || pending || attachments.length >= MAX_RUNTIME_ATTACHMENTS} onClick={() => inputRef.current?.click()}>
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
        <Button type="button" size="sm" className="size-10 shrink-0 px-0" aria-label="Отправить сообщение" disabled={disabled || (!value.trim() && !attachments.length)} pending={pending} onClick={submit}>
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
