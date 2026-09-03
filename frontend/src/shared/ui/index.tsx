import {
  type ButtonHTMLAttributes,
  type InputHTMLAttributes,
  type ReactNode,
  createContext,
  forwardRef,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
} from "react";
import { AlertCircle, CheckCircle2, LoaderCircle, X } from "lucide-react";
import { cn } from "../utils";

type ButtonVariant = "primary" | "secondary" | "ghost" | "danger" | "giga";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: "sm" | "md" | "lg";
  pending?: boolean;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button({
  className,
  variant = "primary",
  size = "md",
  pending = false,
  disabled,
  children,
  ...props
}, ref) {
  const variants: Record<ButtonVariant, string> = {
    primary: "bg-molvest-700 text-white hover:bg-molvest-800 shadow-sm",
    secondary: "border border-molvest-200 bg-white text-molvest-800 hover:bg-molvest-50",
    ghost: "text-molvest-800 hover:bg-molvest-100/70",
    danger: "bg-red-700 text-white hover:bg-red-800 shadow-sm",
    giga: "bg-giga text-white hover:bg-indigo-700 shadow-sm",
  };
  const sizes = {
    sm: "min-h-9 px-3 text-sm",
    md: "min-h-11 px-4 text-sm",
    lg: "min-h-12 px-5 text-base",
  };

  return (
    <button
      ref={ref}
      className={cn(
        "inline-flex items-center justify-center gap-2 rounded-xl font-semibold transition focus-visible:outline-2 focus-visible:outline-molvest-500 disabled:cursor-not-allowed disabled:opacity-55",
        variants[variant],
        sizes[size],
        className,
      )}
      disabled={disabled || pending}
      {...props}
    >
      {pending && <LoaderCircle aria-hidden="true" className="size-4 animate-spin" />}
      {children}
    </button>
  );
});

export const IconButton = forwardRef<HTMLButtonElement, ButtonHTMLAttributes<HTMLButtonElement>>(function IconButton({ className, children, ...props }, ref) {
  return (
    <button
      ref={ref}
      className={cn(
        "inline-flex size-10 items-center justify-center rounded-xl text-molvest-700 transition hover:bg-molvest-100 focus-visible:outline-2 focus-visible:outline-molvest-500 disabled:opacity-50",
        className,
      )}
      {...props}
    >
      {children}
    </button>
  );
});

export function Card({ className, children }: { className?: string; children: ReactNode }) {
  return (
    <section className={cn("rounded-2xl border border-molvest-100 bg-white shadow-[0_12px_36px_rgb(20_48_35/6%)]", className)}>
      {children}
    </section>
  );
}

export function Badge({
  children,
  tone = "neutral",
  className,
}: {
  children: ReactNode;
  tone?: "neutral" | "success" | "warning" | "danger" | "info" | "giga";
  className?: string;
}) {
  const tones = {
    neutral: "bg-stone-100 text-stone-700",
    success: "bg-emerald-100 text-emerald-800",
    warning: "bg-amber-100 text-amber-900",
    danger: "bg-red-100 text-red-800",
    info: "bg-sky-100 text-sky-800",
    giga: "bg-indigo-100 text-indigo-800",
  };
  return (
    <span className={cn("inline-flex items-center rounded-full px-2.5 py-1 text-xs font-bold", tones[tone], className)}>
      {children}
    </span>
  );
}

export function Field({
  label,
  hint,
  error,
  children,
  className,
}: {
  label: string;
  hint?: string;
  error?: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <label className={cn("grid gap-1.5 text-sm font-semibold text-molvest-900", className)}>
      <span>{label}</span>
      {children}
      {hint && !error && <span className="text-xs font-normal text-stone-500">{hint}</span>}
      {error && <span className="text-xs font-normal text-red-700">{error}</span>}
    </label>
  );
}

export function Input({ className, ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={cn(
        "min-h-11 w-full rounded-xl border border-stone-200 bg-white px-3.5 text-sm text-ink transition placeholder:text-stone-400 focus:border-molvest-500 focus:outline-none focus:ring-3 focus:ring-molvest-100 disabled:bg-stone-100",
        className,
      )}
      {...props}
    />
  );
}

export function Select({ className, children, ...props }: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      className={cn(
        "min-h-11 w-full rounded-xl border border-stone-200 bg-white px-3.5 text-sm text-ink transition focus:border-molvest-500 focus:outline-none focus:ring-3 focus:ring-molvest-100 disabled:bg-stone-100",
        className,
      )}
      {...props}
    >
      {children}
    </select>
  );
}

export function Textarea({ className, ...props }: React.TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      className={cn(
        "w-full resize-y rounded-xl border border-stone-200 bg-white px-3.5 py-3 text-sm leading-6 text-ink transition placeholder:text-stone-400 focus:border-molvest-500 focus:outline-none focus:ring-3 focus:ring-molvest-100 disabled:bg-stone-100",
        className,
      )}
      {...props}
    />
  );
}

export function Switch({
  checked,
  onChange,
  label,
  disabled,
}: {
  checked: boolean;
  onChange: (checked: boolean) => void;
  label: string;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={cn(
        "relative h-7 w-12 shrink-0 rounded-full transition focus-visible:outline-2 focus-visible:outline-molvest-500 disabled:opacity-50",
        checked ? "bg-molvest-600" : "bg-stone-300",
      )}
    >
      <span
        className={cn(
          "absolute top-1 size-5 rounded-full bg-white shadow-sm transition-transform",
          checked ? "left-1 translate-x-5" : "left-1 translate-x-0",
        )}
      />
    </button>
  );
}

export function Tabs<T extends string>({
  value,
  onChange,
  items,
  ariaLabel,
}: {
  value: T;
  onChange: (value: T) => void;
  items: Array<{ value: T; label: string; count?: number }>;
  ariaLabel: string;
}) {
  return (
    <div role="tablist" aria-label={ariaLabel} className="flex gap-1 rounded-xl bg-stone-100 p-1">
      {items.map((item) => (
        <button
          key={item.value}
          type="button"
          role="tab"
          aria-selected={value === item.value}
          onClick={() => onChange(item.value)}
          className={cn(
            "min-h-9 flex-1 rounded-lg px-3 text-sm font-semibold transition",
            value === item.value ? "bg-white text-molvest-900 shadow-sm" : "text-stone-500 hover:text-molvest-800",
          )}
        >
          {item.label}
          {item.count !== undefined && <span className="ml-1.5 text-xs opacity-70">{item.count}</span>}
        </button>
      ))}
    </div>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div aria-hidden="true" className={cn("animate-pulse rounded-xl bg-stone-200/80", className)} />;
}

export function PageLoader({ label = "Загружаем данные" }: { label?: string }) {
  return (
    <div className="flex min-h-52 flex-col items-center justify-center gap-3 text-stone-500" role="status">
      <LoaderCircle className="size-7 animate-spin text-molvest-600" aria-hidden="true" />
      <span className="text-sm font-medium">{label}</span>
    </div>
  );
}

export function EmptyState({
  title,
  description,
  action,
  icon,
}: {
  title: string;
  description: string;
  action?: ReactNode;
  icon?: ReactNode;
}) {
  return (
    <div className="flex min-h-56 flex-col items-center justify-center px-6 py-10 text-center">
      {icon && <div className="mb-4 text-molvest-500">{icon}</div>}
      <h2 className="text-lg font-bold text-molvest-950">{title}</h2>
      <p className="mt-2 max-w-md text-sm leading-6 text-stone-500">{description}</p>
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}

export function ErrorState({
  title = "Не удалось загрузить данные",
  description,
  onRetry,
}: {
  title?: string;
  description?: string;
  onRetry?: () => void;
}) {
  return (
    <div className="flex min-h-52 flex-col items-center justify-center px-6 py-10 text-center" role="alert">
      <AlertCircle className="size-8 text-red-600" aria-hidden="true" />
      <h2 className="mt-3 text-lg font-bold text-stone-900">{title}</h2>
      {description && <p className="mt-2 max-w-lg text-sm leading-6 text-stone-500">{description}</p>}
      {onRetry && (
        <Button variant="secondary" className="mt-5" onClick={onRetry}>
          Повторить
        </Button>
      )}
    </div>
  );
}

export function Modal({
  open,
  title,
  description,
  onClose,
  children,
  className,
}: {
  open: boolean;
  title: string;
  description?: string;
  onClose: () => void;
  children: ReactNode;
  className?: string;
}) {
  const closeRef = useRef<HTMLButtonElement>(null);
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;
  useEffect(() => {
    if (!open) return;
    closeRef.current?.focus();
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") onCloseRef.current();
    };
    document.addEventListener("keydown", closeOnEscape);
    return () => document.removeEventListener("keydown", closeOnEscape);
  }, [open]);
  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-ink/55 p-0 backdrop-blur-[2px] sm:items-center sm:p-5" onMouseDown={onClose}>
      <section
        role="dialog"
        aria-modal="true"
        aria-labelledby="modal-title"
        className={cn("max-h-[92vh] w-full overflow-auto rounded-t-3xl bg-white p-5 shadow-2xl sm:max-w-lg sm:rounded-3xl sm:p-6", className)}
        onMouseDown={(event) => event.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 id="modal-title" className="text-xl font-bold text-molvest-950">{title}</h2>
            {description && <p className="mt-1.5 text-sm leading-6 text-stone-500">{description}</p>}
          </div>
          <IconButton ref={closeRef} type="button" aria-label="Закрыть" onClick={onClose}>
            <X className="size-5" />
          </IconButton>
        </div>
        <div className="mt-5">{children}</div>
      </section>
    </div>
  );
}

export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel,
  cancelLabel = "Отмена",
  danger = false,
  pending = false,
  onConfirm,
  onCancel,
}: {
  open: boolean;
  title: string;
  description?: string;
  confirmLabel: string;
  cancelLabel?: string;
  danger?: boolean;
  pending?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const cancelRef = useRef<HTMLButtonElement>(null);
  const onCancelRef = useRef(onCancel);
  onCancelRef.current = onCancel;
  useEffect(() => {
    if (!open) return;
    cancelRef.current?.focus();
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !pending) onCancelRef.current();
    };
    document.addEventListener("keydown", closeOnEscape);
    return () => document.removeEventListener("keydown", closeOnEscape);
  }, [open, pending]);
  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center bg-ink/60 p-4 backdrop-blur-[2px]">
      <section
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="confirm-title"
        aria-describedby={description ? "confirm-description" : undefined}
        className="w-full max-w-md rounded-3xl bg-white p-6 shadow-2xl"
      >
        <div className={cn("mb-4 flex size-11 items-center justify-center rounded-2xl", danger ? "bg-red-100 text-red-700" : "bg-amber-100 text-amber-800")}>
          <AlertCircle className="size-5" aria-hidden="true" />
        </div>
        <h2 id="confirm-title" className="text-xl font-bold text-stone-950">{title}</h2>
        {description && <p id="confirm-description" className="mt-2 text-sm leading-6 text-stone-600">{description}</p>}
        <div className="mt-6 flex justify-end gap-3">
          <Button ref={cancelRef} type="button" variant="secondary" disabled={pending} onClick={onCancel}>
            {cancelLabel}
          </Button>
          <Button type="button" variant={danger ? "danger" : "primary"} pending={pending} onClick={onConfirm}>
            {confirmLabel}
          </Button>
        </div>
      </section>
    </div>
  );
}

type ToastTone = "success" | "error" | "info";
interface ToastItem {
  id: string;
  message: string;
  tone: ToastTone;
}
interface ToastContextValue {
  toast: (message: string, tone?: ToastTone) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const toast = useCallback((message: string, tone: ToastTone = "info") => {
    const id = crypto.randomUUID();
    setItems((current) => [...current, { id, message, tone }]);
    window.setTimeout(() => setItems((current) => current.filter((item) => item.id !== id)), 4200);
  }, []);
  return (
    <ToastContext.Provider value={{ toast }}>
      {children}
      <div className="fixed bottom-4 right-4 z-[80] grid w-[min(24rem,calc(100vw-2rem))] gap-2" aria-live="polite" aria-atomic="true">
        {items.map((item) => (
          <div
            key={item.id}
            className={cn(
              "flex items-start gap-3 rounded-2xl border bg-white p-4 text-sm font-semibold shadow-xl",
              item.tone === "error" ? "border-red-200 text-red-800" : item.tone === "success" ? "border-emerald-200 text-emerald-800" : "border-sky-200 text-sky-800",
            )}
          >
            {item.tone === "success" ? <CheckCircle2 className="mt-0.5 size-4 shrink-0" /> : <AlertCircle className="mt-0.5 size-4 shrink-0" />}
            <span className="flex-1 leading-5">{item.message}</span>
            <button type="button" aria-label="Закрыть уведомление" onClick={() => setItems((current) => current.filter((entry) => entry.id !== item.id))}>
              <X className="size-4" />
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastContextValue["toast"] {
  const context = useContext(ToastContext);
  if (!context) throw new Error("useToast must be used within ToastProvider");
  return context.toast;
}
