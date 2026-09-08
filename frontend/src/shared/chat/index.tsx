import {
  type ChangeEvent,
  type KeyboardEvent,
  type ReactNode,
  forwardRef,
  memo,
  useEffect,
  useRef,
  useState,
} from "react";
import Markdown from "react-markdown";
import type { Components } from "react-markdown";
import { PrismLight as SyntaxHighlighter } from "react-syntax-highlighter";
import bash from "react-syntax-highlighter/dist/esm/languages/prism/bash";
import css from "react-syntax-highlighter/dist/esm/languages/prism/css";
import javascript from "react-syntax-highlighter/dist/esm/languages/prism/javascript";
import json from "react-syntax-highlighter/dist/esm/languages/prism/json";
import markdown from "react-syntax-highlighter/dist/esm/languages/prism/markdown";
import markup from "react-syntax-highlighter/dist/esm/languages/prism/markup";
import python from "react-syntax-highlighter/dist/esm/languages/prism/python";
import shellSession from "react-syntax-highlighter/dist/esm/languages/prism/shell-session";
import sql from "react-syntax-highlighter/dist/esm/languages/prism/sql";
import tsx from "react-syntax-highlighter/dist/esm/languages/prism/tsx";
import typescript from "react-syntax-highlighter/dist/esm/languages/prism/typescript";
import yaml from "react-syntax-highlighter/dist/esm/languages/prism/yaml";
import { oneDark } from "react-syntax-highlighter/dist/esm/styles/prism";
import remarkGfm from "remark-gfm";
import {
  Bot,
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
import type { AttachmentDto, MessageDto } from "../../api/types";
import { Button, IconButton } from "../ui";
import {
  cn,
  formatBytes,
  formatDateTime,
  formatPercent,
  safeAttachmentUrl,
} from "../utils";

const IMAGE_LIMIT = 15 * 1024 * 1024;
const DOCUMENT_LIMIT = 40 * 1024 * 1024;
const ATTACHMENT_REQUEST_LIMIT = 80 * 1024 * 1024;
export const MAX_RUNTIME_ATTACHMENTS = 10;
export const MAX_RUNTIME_IMAGES = 1;
const IMAGE_EXTENSIONS = [".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"];
const DOCUMENT_EXTENSIONS = [".txt", ".doc", ".docx", ".pdf", ".epub", ".ppt", ".pptx", ".xlsx"];
const MIME_TYPES_BY_EXTENSION: Record<string, string[]> = {
  ".png": ["image/png"],
  ".jpg": ["image/jpeg"],
  ".jpeg": ["image/jpeg"],
  ".tif": ["image/tiff"],
  ".tiff": ["image/tiff"],
  ".bmp": ["image/bmp"],
  ".txt": ["text/plain"],
  ".doc": ["application/msword"],
  ".docx": ["application/vnd.openxmlformats-officedocument.wordprocessingml.document"],
  ".pdf": ["application/pdf"],
  ".epub": ["application/epub", "application/epub+zip"],
  ".ppt": ["application/ppt", "application/vnd.ms-powerpoint"],
  ".pptx": ["application/pptx", "application/vnd.openxmlformats-officedocument.presentationml.presentation"],
  ".xlsx": ["application/vnd.ms-excel", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"],
};
const EMPTY_ATTACHMENTS: File[] = [];
export const RUNTIME_ATTACHMENT_ACCEPT = Object.entries(MIME_TYPES_BY_EXTENSION)
  .flatMap(([extension, mimeTypes]) => [extension, ...mimeTypes])
  .join(",");

SyntaxHighlighter.registerLanguage("bash", bash);
SyntaxHighlighter.registerLanguage("css", css);
SyntaxHighlighter.registerLanguage("javascript", javascript);
SyntaxHighlighter.registerLanguage("json", json);
SyntaxHighlighter.registerLanguage("markdown", markdown);
SyntaxHighlighter.registerLanguage("markup", markup);
SyntaxHighlighter.registerLanguage("python", python);
SyntaxHighlighter.registerLanguage("shell-session", shellSession);
SyntaxHighlighter.registerLanguage("sql", sql);
SyntaxHighlighter.registerLanguage("tsx", tsx);
SyntaxHighlighter.registerLanguage("typescript", typescript);
SyntaxHighlighter.registerLanguage("yaml", yaml);
SyntaxHighlighter.alias("bash", ["sh", "shell"]);
SyntaxHighlighter.alias("javascript", ["js"]);
SyntaxHighlighter.alias("json", ["jsonc"]);
SyntaxHighlighter.alias("markup", ["html", "xml"]);
SyntaxHighlighter.alias("markdown", ["md"]);
SyntaxHighlighter.alias("python", ["py"]);
SyntaxHighlighter.alias("typescript", ["ts"]);
SyntaxHighlighter.alias("yaml", ["yml"]);

const markdownPlugins = [remarkGfm];
const highlightLanguages = new Set([
  "bash",
  "css",
  "javascript",
  "json",
  "markdown",
  "markup",
  "python",
  "shell-session",
  "sql",
  "tsx",
  "typescript",
  "yaml",
]);
const languageAliases: Record<string, string> = {
  html: "markup",
  js: "javascript",
  jsonc: "json",
  md: "markdown",
  py: "python",
  sh: "bash",
  shell: "bash",
  ts: "typescript",
  xml: "markup",
  yml: "yaml",
};

function normalizeCodeLanguage(className?: string): string | undefined {
  const match = /(?:^|\s)language-([^\s]+)/.exec(className ?? "");
  if (!match) return undefined;
  const language = languageAliases[match[1].toLowerCase()] ?? match[1].toLowerCase();
  return highlightLanguages.has(language) ? language : undefined;
}

const markdownComponents: Components = {
  a({ children, node, ...props }) {
    void node;
    return <a {...props} target="_blank" rel="noreferrer" className="font-semibold text-molvest-700 underline decoration-molvest-200 underline-offset-2 hover:decoration-molvest-700">{children}</a>;
  },
  code({ children, className, node, ...props }) {
    void node;
    const language = normalizeCodeLanguage(className);
    if (!language) {
      return <code {...props} className={cn("rounded-md bg-[#eef2fa] px-1.5 py-0.5 font-mono text-[0.9em]", className)}>{children}</code>;
    }
    return (
      <SyntaxHighlighter
        language={language}
        style={oneDark}
        PreTag="div"
        customStyle={{ margin: 0, borderRadius: "0.75rem", padding: "0.875rem", fontSize: "0.78rem", lineHeight: 1.6 }}
        codeTagProps={{ className: "font-mono" }}
      >
        {String(children).replace(/\n$/, "")}
      </SyntaxHighlighter>
    );
  },
  input({ node, ...props }) {
    void node;
    return <input {...props} disabled className="mr-1.5 align-middle accent-molvest-400" />;
  },
};

export function MarkdownContent({ text, className }: { text: string; className?: string }) {
  return (
    <div className={cn("markdown-body", className)}>
      <Markdown remarkPlugins={markdownPlugins} skipHtml components={markdownComponents}>{text}</Markdown>
    </div>
  );
}

export function isRuntimeImage(file: File): boolean {
  const extension = `.${file.name.split(".").pop()?.toLowerCase() ?? ""}`;
  return IMAGE_EXTENSIONS.includes(extension);
}

export function validateRuntimeAttachment(file: File): string | null {
  const extension = `.${file.name.split(".").pop()?.toLowerCase() ?? ""}`;
  const isImage = isRuntimeImage(file);
  const isDocument = DOCUMENT_EXTENSIONS.includes(extension);
  if (!isImage && !isDocument) {
    return "Поддерживаются изображения PNG/JPEG/TIFF/BMP и документы TXT/DOC/DOCX/PDF/EPUB/PPT/PPTX/XLSX.";
  }
  const expectedMimeTypes = MIME_TYPES_BY_EXTENSION[extension] ?? [];
  if (file.type && !expectedMimeTypes.includes(file.type)) {
    return `Тип файла ${file.name} не соответствует его расширению.`;
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
  const imageCount = files.filter(isRuntimeImage).length;
  if (imageCount > MAX_RUNTIME_IMAGES) {
    return "Можно прикрепить только одно изображение за сообщение.";
  }
  const totalBytes = files.reduce((total, file) => total + file.size, 0);
  if (totalBytes >= ATTACHMENT_REQUEST_LIMIT) {
    return "Суммарный размер вложений должен быть менее 80 МБ.";
  }
  return null;
}

export { DialogStatusBadge } from "./DialogStatusBadge";

export function AttachmentCard({ attachment }: { attachment: AttachmentDto }) {
  const url = safeAttachmentUrl(attachment);
  const isImage = attachment.mimeType.startsWith("image/");
  return (
    <div className="flex w-24 flex-col gap-1">
      {url ? (
        <a
          href={url}
          download={attachment.fileName}
          className="group relative flex aspect-square w-24 items-center justify-center overflow-hidden rounded-xl border border-[#dbe3f0] bg-[#eef2fa] transition hover:border-molvest-400 hover:bg-molvest-50"
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
        <div className="relative flex aspect-square w-24 items-center justify-center overflow-hidden rounded-xl border border-[#dbe3f0] bg-[#eef2fa]" title={attachment.fileName}>
          {isImage ? <ImageIcon className="size-7 text-molvest-700" /> : <FileText className="size-7 text-molvest-700" />}
          <span className="absolute inset-x-0 bottom-0 truncate bg-black/65 px-1.5 py-1 text-[10px] font-bold text-white">{attachment.fileName}</span>
        </div>
      )}
      {typeof attachment.sizeBytes === "number" && <span className="truncate px-1 text-[10px] opacity-65">{formatBytes(attachment.sizeBytes)}</span>}
    </div>
  );
}

function authorMeta(message: MessageDto) {
  if (message.authorType === "assistant") return { label: "GigaChat", icon: Sparkles, bubble: "border border-[#dbe3f0] bg-white text-slate-800 shadow-sm", align: "justify-start" };
  if (message.authorType === "operator") return { label: "ОПЕРАТОР", icon: ShieldCheck, bubble: "border border-[#fbc4fb] bg-[#fdf5fd] text-slate-800", align: "justify-start" };
  return {
    label: "КЛИЕНТ",
    icon: UserRound,
    bubble: "bg-molvest-400 text-white",
    align: "justify-end",
  };
}

export const MessageBubble = memo(function MessageBubble({ message, showConfidence = false }: { message: MessageDto; showConfidence?: boolean }) {
  if (message.authorType === "system") {
    return (
      <div className="message-enter my-3 flex justify-center">
        <div className="max-w-xl rounded-full border border-dashed border-[#dbe3f0] bg-white px-4 py-2 text-center text-xs font-semibold text-slate-600">
          {message.text}
          {showConfidence && message.confidence !== undefined && <span className="ml-2 text-slate-400">Confidence {formatPercent(message.confidence)}</span>}
        </div>
      </div>
    );
  }
  const meta = authorMeta(message);
  const Icon = meta.icon;
  const isRightAligned = meta.align === "justify-end";
  return (
    <article className={cn("message-enter flex", meta.align)} data-message-id={message.id}>
      <div className={cn("max-w-[88%] rounded-2xl px-4 py-3 sm:max-w-[74%]", meta.bubble, isRightAligned ? "rounded-br-md" : "rounded-bl-md")}>
        <div className="mb-1.5 flex items-center gap-1.5 text-[11px] font-extrabold uppercase tracking-[0.08em] opacity-70">
          <Icon className="size-3.5" aria-hidden="true" />
          {meta.label}
          {showConfidence && message.authorType !== "operator" && message.confidence !== undefined && <span>· {formatPercent(message.confidence)}</span>}
        </div>
        {message.authorType === "assistant" || message.authorType === "operator" ? <MarkdownContent text={message.text} className={message.authorType === "operator" ? "!bg-transparent" : undefined} /> : <p className="whitespace-pre-wrap break-words text-sm leading-6">{message.text}</p>}
        {message.attachments.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-2.5">
            {message.attachments.map((attachment) => (
              <AttachmentCard key={attachment.id} attachment={attachment} />
            ))}
          </div>
        )}
        <time className="mt-2 block text-right text-[10px] opacity-55" dateTime={message.createdAt}>{formatDateTime(message.createdAt)}</time>
      </div>
    </article>
  );
});

export const StreamingMessage = memo(function StreamingMessage({ text, label = "GigaChat формирует ответ" }: { text: string; label?: string }) {
  return (
    <div className="message-enter flex justify-start" aria-live="polite">
      <div className="max-w-[88%] rounded-2xl rounded-bl-md border border-[#dbe3f0] bg-white px-4 py-3 text-slate-800 shadow-sm sm:max-w-[74%]">
        <div className="mb-1.5 flex items-center gap-1.5 text-[11px] font-extrabold uppercase tracking-[0.08em] text-molvest-700">
          <Bot className="size-3.5" /> {label}
        </div>
        {text ? <><MarkdownContent text={text} /><span className="ml-0.5 inline-block h-4 w-0.5 animate-pulse bg-molvest-400 align-middle" aria-hidden="true" /></> : <div className="flex gap-1 py-2"><i className="size-1.5 animate-bounce rounded-full bg-molvest-300" /><i className="size-1.5 animate-bounce rounded-full bg-molvest-300 [animation-delay:120ms]" /><i className="size-1.5 animate-bounce rounded-full bg-molvest-300 [animation-delay:240ms]" /></div>}
      </div>
    </div>
  );
});

export function MessageList({
  messages,
  streamingText,
  streamingLabel,
  topAction,
  showConfidence = false,
  empty,
}: {
  messages: MessageDto[];
  streamingText?: string | null;
  streamingLabel?: string;
  topAction?: ReactNode;
  showConfidence?: boolean;
  empty?: ReactNode;
}) {
  const endRef = useRef<HTMLDivElement>(null);
  const hasStreamingMessage = streamingText !== undefined && streamingText !== null;
  useEffect(() => {
    endRef.current?.scrollIntoView({ block: "end" });
  }, [messages.length, hasStreamingMessage, streamingText]);
  if (!messages.length && !streamingText && empty) return <>{empty}</>;
  return (
    <div className="grid gap-3 bg-cream px-4 py-5 sm:px-6">
      {topAction}
      {messages.map((message) => (
        <MessageBubble key={message.id} message={message} showConfidence={showConfidence} />
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
    <div className="border-t border-[#dbe3f0] bg-white p-3 sm:p-4">
      {attachments.length > 0 && (
        <div className="mb-3 flex flex-wrap gap-2">
          {attachments.map((file, index) => (
            <div key={`${file.name}-${file.lastModified}-${index}`} className="group relative size-20 overflow-hidden rounded-xl border border-[#dbe3f0] bg-molvest-50">
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
      <div className="flex items-end gap-2 rounded-2xl border border-[#dbe3f0] bg-white p-2 focus-within:border-molvest-400 focus-within:ring-3 focus-within:ring-molvest-100">
        {onAttachmentChange && (
          <>
            <input ref={inputRef} name="attachments" type="file" className="sr-only" accept={RUNTIME_ATTACHMENT_ACCEPT} multiple onChange={onFile} disabled={disabled || pending || attachments.length >= MAX_RUNTIME_ATTACHMENTS} aria-label="Выбрать файлы: одно изображение и документы" />
            <IconButton type="button" aria-label="Прикрепить файлы: одно изображение и документы" disabled={disabled || pending || attachments.length >= MAX_RUNTIME_ATTACHMENTS} onClick={() => inputRef.current?.click()}>
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
          className="max-h-40 min-h-10 flex-1 resize-none bg-transparent px-1 py-2 text-sm leading-6 outline-none placeholder:text-slate-400 disabled:cursor-not-allowed"
        />
        <Button type="button" size="sm" className="size-10 shrink-0 px-0" aria-label="Отправить сообщение" disabled={disabled || (!value.trim() && !attachments.length)} pending={pending} onClick={submit}>
          <Send className="size-4" />
        </Button>
      </div>
      <div className="mt-2 flex items-center justify-between gap-3 text-[11px] text-slate-400">
        <span>Enter — отправить · Shift+Enter — новая строка</span>
        {footer}
      </div>
    </div>
  );
});
