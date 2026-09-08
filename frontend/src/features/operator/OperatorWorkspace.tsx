import {
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import { ApiError } from "../../api/client";
import { authApi } from "../../api/auth";
import { dialogsApi } from "../../api/dialogs";
import { operatorApi } from "../../api/operator";
import { queryKeys } from "../../api/queryKeys";
import {
  Bot,
  CheckCircle2,
  Clipboard,
  Headphones,
  Inbox,
  MessagesSquare,
  PanelRight,
  RotateCcw,
  Sparkles,
  UserCheck,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  ChatComposer,
  DialogStatusBadge,
  MessageList,
} from "../../shared/chat";
import { appendPersistedMessage } from "../../shared/hooks/messageCache";
import { useOperatorDialogEvents } from "../../shared/hooks/useOperatorDialogEvents";
import {
  Badge,
  Button,
  ConfirmDialog,
  EmptyState,
  ErrorState,
  PageLoader,
  Tabs,
  Textarea,
  useToast,
} from "../../shared/ui";
import {
  formatDateTime,
  getErrorMessage,
  mergePersistedMessages,
  retryOrCreateSendAttempt,
  truncateTitle,
  type SendAttempt,
} from "../../shared/utils";
import { TemplateInsertAction } from "./TemplateInsertAction";
import OperatorQueue from "./OperatorQueue";

type MobilePane = "queue" | "chat" | "template";

interface TemplateState {
  status: "generating" | "ready" | "error";
  text: string;
  dialogUpdatedAt?: string;
  updatedAt?: string;
  error?: string;
}

export default function OperatorWorkspace() {
  const { dialogId } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const toast = useToast();
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const [mobilePane, setMobilePane] = useState<MobilePane>(
    dialogId ? "chat" : "queue",
  );
  const [text, setText] = useState("");
  const [attachments, setAttachments] = useState<File[]>([]);
  const [attachmentError, setAttachmentError] = useState<string>();
  const [failedAttempt, setFailedAttempt] = useState<SendAttempt>();
  const [closeOpen, setCloseOpen] = useState(false);
  const [templates, setTemplates] = useState<Record<string, TemplateState>>({});
  const me = useQuery({
    queryKey: queryKeys.me(),
    queryFn: ({ signal }) => authApi.me(signal),
  });
  const detail = useQuery({
    queryKey: queryKeys.dialog.detail(dialogId ?? ""),
    queryFn: ({ signal }) => operatorApi.detail(dialogId!, signal),
    enabled: Boolean(dialogId),
    refetchInterval: 2500,
    refetchOnMount: "always",
  });
  const messages = useInfiniteQuery({
    queryKey: queryKeys.dialog.messages(dialogId ?? ""),
    queryFn: ({ pageParam, signal }) =>
      dialogsApi.messages(dialogId!, pageParam, signal),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.nextCursor ?? undefined,
    enabled: Boolean(dialogId),
    refetchInterval: 2500,
    refetchOnMount: "always",
  });
  const events = useOperatorDialogEvents(dialogId, me.data?.id);
  const allMessages = messages.data
    ? mergePersistedMessages(...messages.data.pages.map((page) => page.items))
    : [];
  const processingError =
    events.eventError ?? detail.data?.processingError ?? undefined;
  const isAssignedToMe = Boolean(
    detail.data?.assignedOperator?.id &&
    detail.data.assignedOperator.id === me.data?.id,
  );
  const template = dialogId ? templates[dialogId] : undefined;
  const templateText = template?.text ?? "";
  const isGeneratingTemplate = template?.status === "generating";
  const templateStale = Boolean(
    template?.status === "ready" &&
    template.dialogUpdatedAt &&
    detail.data?.updatedAt &&
    template.dialogUpdatedAt !== detail.data.updatedAt,
  );
  const templateReady =
    template?.status === "ready" &&
    !templateStale &&
    Boolean(templateText.trim());
  const hasUserMessage = allMessages.some(
    (message) => message.authorType === "user",
  );

  useEffect(() => {
    setMobilePane(dialogId ? "chat" : "queue");
    setText("");
    setAttachments([]);
    setAttachmentError(undefined);
    setFailedAttempt(undefined);
    setCloseOpen(false);
  }, [dialogId]);

  const claim = useMutation({
    mutationFn: () => operatorApi.claim(dialogId!),
    onSuccess: (claimed) => {
      queryClient.setQueryData(queryKeys.dialog.detail(claimed.id), claimed);
      void queryClient.invalidateQueries({
        queryKey: queryKeys.operator.queues(),
      });
      requestAnimationFrame(() => textareaRef.current?.focus());
    },
    onError: (error) => {
      if (error instanceof ApiError && error.status === 409) {
        toast("Тикет уже взят другим оператором.", "error");
        void queryClient.refetchQueries({
          queryKey: queryKeys.operator.queues(),
        });
        if (dialogId)
          void queryClient.refetchQueries({
            queryKey: queryKeys.dialog.detail(dialogId),
          });
        return;
      }
      toast(getErrorMessage(error), "error");
    },
  });
  const generateTemplate = useMutation({
    mutationFn: (targetDialogId: string) =>
      operatorApi.generateTemplate(targetDialogId),
    onMutate: (targetDialogId) => {
      setTemplates((current) => ({
        ...current,
        [targetDialogId]: { status: "generating", text: "" },
      }));
    },
    onSuccess: (generated, targetDialogId) => {
      setTemplates((current) => ({
        ...current,
        [targetDialogId]: {
          status: "ready",
          text: generated.text,
          dialogUpdatedAt: generated.dialogUpdatedAt,
          updatedAt: generated.createdAt,
        },
      }));
    },
    onError: (error, targetDialogId) => {
      setTemplates((current) => ({
        ...current,
        [targetDialogId]: {
          status: "error",
          text: "",
          error: getErrorMessage(error),
        },
      }));
    },
  });
  const canGenerateTemplate = Boolean(
    dialogId &&
    detail.data?.status === "active" &&
    isAssignedToMe &&
    hasUserMessage &&
    !isGeneratingTemplate,
  );
  const canInsertTemplate =
    templateReady && isAssignedToMe && detail.data?.status === "active";
  const send = useMutation({
    mutationFn: (attempt: SendAttempt) =>
      dialogsApi.sendMessage(dialogId!, attempt),
    onSuccess: (message) => {
      appendPersistedMessage(queryClient, dialogId!, message);
      setText("");
      setAttachments([]);
      setAttachmentError(undefined);
      setFailedAttempt(undefined);
      void queryClient.invalidateQueries({
        queryKey: queryKeys.dialog.detail(dialogId!),
      });
      requestAnimationFrame(() => textareaRef.current?.focus());
    },
    onError: (error, attempt) => {
      setFailedAttempt(attempt);
      toast(getErrorMessage(error), "error");
    },
  });
  const close = useMutation({
    mutationFn: () => dialogsApi.close(dialogId!),
    onSuccess: (closed) => {
      queryClient.setQueryData(queryKeys.dialog.detail(closed.id), closed);
      void queryClient.invalidateQueries({
        queryKey: queryKeys.operator.queues(),
      });
      setCloseOpen(false);
    },
    onError: async (error) => {
      if (error instanceof ApiError && error.status === 409 && dialogId) {
        try {
          const current = await operatorApi.detail(dialogId);
          queryClient.setQueryData(queryKeys.dialog.detail(dialogId), current);
          void queryClient.invalidateQueries({
            queryKey: queryKeys.operator.queues(),
          });
          if (current.status === "closed") {
            setCloseOpen(false);
            return;
          }
        } catch {
          // Keep the original conflict message when the state refresh fails.
        }
      }
      toast(getErrorMessage(error), "error");
    },
  });
  const submitAttempt = (attempt: SendAttempt) => {
    if (!isAssignedToMe || send.isPending) return;
    send.mutate(attempt);
  };
  const submit = () => {
    const normalized = text.trim();
    if (!normalized && !attachments.length) return;
    const attempt = retryOrCreateSendAttempt(
      normalized,
      attachments,
      failedAttempt,
    );
    submitAttempt(attempt);
  };
  const updateAttachments = (files: File[]) => {
    setAttachments(files);
    setFailedAttempt(undefined);
  };
  const insertTemplate = (value: string) => {
    setText(value);
    setFailedAttempt(undefined);
    setMobilePane("chat");
    requestAnimationFrame(() => textareaRef.current?.focus());
  };
  const copyTemplate = async () => {
    try {
      await navigator.clipboard.writeText(templateText);
      toast("Шаблон скопирован", "success");
    } catch {
      toast("Не удалось скопировать текст", "error");
    }
  };
  const selectDialog = (id: string) => {
    navigate(`/operator/dialogs/${id}`);
    setMobilePane("chat");
  };

  return (
    <div className="flex h-[calc(100vh-65px)] min-h-[34rem] flex-col">
      <div className="border-b border-[#dbe3f0] bg-white p-2 lg:hidden">
        <Tabs
          value={mobilePane}
          onChange={setMobilePane}
          ariaLabel="Панели рабочего места"
          items={[
            { value: "queue", label: "Очередь" },
            { value: "chat", label: "Диалог" },
            { value: "template", label: "Шаблон" },
          ]}
        />
      </div>
      <div className="flex min-h-0 flex-1">
        <OperatorQueue
          selectedId={dialogId}
          onSelect={selectDialog}
          className={
            mobilePane === "queue"
              ? "flex w-full lg:w-[19rem]"
              : "hidden lg:flex lg:w-[19rem]"
          }
        />
        <section
          className={
            mobilePane === "chat"
              ? "flex min-w-0 flex-1 flex-col bg-cream"
              : "hidden min-w-0 flex-1 flex-col bg-cream lg:flex"
          }
        >
          {!dialogId && (
            <EmptyState
              icon={<Inbox className="size-9" />}
              title="Выберите обращение"
              description="Откройте тикет из очереди. До назначения доступен просмотр, но поле ответа останется заблокированным."
            />
          )}
          {dialogId && detail.isPending && (
            <PageLoader label="Открываем тикет" />
          )}
          {dialogId && detail.isError && (
            <ErrorState
              description={detail.error.message}
              onRetry={() => void detail.refetch()}
            />
          )}
          {dialogId && detail.data && (
            <>
              <header className="flex min-h-[4.75rem] items-center justify-between gap-4 border-b border-[#dbe3f0] bg-white px-4 py-3">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <h1 className="text-base font-bold text-black">
                      {truncateTitle(
                        detail.data.title ||
                          `Тикет ${detail.data.id.slice(0, 8)}`,
                      )}
                    </h1>
                    <DialogStatusBadge dialog={detail.data} />
                  </div>
                  <p className="mt-1 text-xs text-slate-500">
                    {detail.data.user?.displayName || "Пользователь"} ·
                    эскалация {formatDateTime(detail.data.escalatedAt)}
                  </p>
                </div>
                <div className="flex shrink-0 gap-2">
                  {detail.data.status === "active" &&
                    !detail.data.assignedOperator && (
                      <Button
                        size="sm"
                        pending={claim.isPending}
                        onClick={() => claim.mutate()}
                      >
                        <UserCheck className="size-4" /> Взять в работу
                      </Button>
                    )}
                  {detail.data.status === "active" && isAssignedToMe && (
                    <Button
                      size="sm"
                      variant="secondary"
                      onClick={() => setCloseOpen(true)}
                    >
                      <CheckCircle2 className="size-4" />
                      <span className="hidden sm:inline">Закрыть тикет</span>
                    </Button>
                  )}
                </div>
              </header>
              {detail.data.assignedOperator &&
                !isAssignedToMe &&
                detail.data.status === "active" && (
                  <div className="border-b border-amber-200 bg-amber-50 px-4 py-2.5 text-xs font-semibold text-amber-900">
                    Тикет ведёт {detail.data.assignedOperator.displayName}.
                    Редактирование ответа недоступно.
                  </div>
                )}
              <div className="min-h-0 flex-1 overflow-y-auto">
                {messages.isPending && <PageLoader label="Загружаем историю" />}
                {messages.isError && (
                  <ErrorState
                    description={messages.error.message}
                    onRetry={() => void messages.refetch()}
                  />
                )}
                {messages.data && (
                  <MessageList
                    messages={allMessages}
                    showConfidence
                    topAction={
                      messages.hasNextPage ? (
                        <Button
                          className="mx-auto"
                          size="sm"
                          variant="ghost"
                          pending={messages.isFetchingNextPage}
                          onClick={() => void messages.fetchNextPage()}
                        >
                          <RotateCcw className="size-3.5" /> Ранние сообщения
                        </Button>
                      ) : undefined
                    }
                    empty={
                      <EmptyState
                        title="История пуста"
                        description="Сообщения появятся после синхронизации с backend."
                      />
                    }
                  />
                )}
              </div>
              {processingError && (
                <div className="border-t border-red-100 bg-red-50 px-4 py-2 text-xs font-semibold text-red-800">
                  {processingError}
                </div>
              )}
              {failedAttempt && (
                <div className="flex items-center justify-between gap-3 border-t border-amber-200 bg-amber-50 px-4 py-2 text-xs text-amber-900">
                  <span>Ответ не подтверждён. Retry сохранит тот же UUID.</span>
                  <Button
                    size="sm"
                    variant="secondary"
                    pending={send.isPending}
                    onClick={() => submitAttempt(failedAttempt)}
                  >
                    Повторить
                  </Button>
                </div>
              )}
              {detail.data.status === "active" && isAssignedToMe && (
                <ChatComposer
                  ref={textareaRef}
                  value={text}
                  onChange={(value) => {
                    setText(value);
                    if (failedAttempt?.text !== value.trim())
                      setFailedAttempt(undefined);
                  }}
                  onSend={submit}
                  pending={send.isPending}
                  placeholder="Ответ пользователю…"
                  attachments={attachments}
                  attachmentError={attachmentError}
                  onAttachmentChange={updateAttachments}
                  onAttachmentError={setAttachmentError}
                  footer={
                    <button
                      type="button"
                      className="font-semibold text-indigo-600 lg:hidden"
                      onClick={() => setMobilePane("template")}
                    >
                      Открыть шаблон
                    </button>
                  }
                />
              )}
              {detail.data.status === "active" &&
                !isAssignedToMe &&
                !detail.data.assignedOperator && (
                  <div className="border-t border-stone-200 bg-white p-4 text-center text-sm text-stone-500">
                    <Headphones className="mr-2 inline size-4" />
                    Возьмите тикет в работу, чтобы ответить пользователю.
                  </div>
                )}
              {detail.data.status === "closed" && (
                <div className="border-t border-stone-200 bg-white p-4">
                  <p className="text-sm font-bold text-stone-900">
                    Тикет завершён
                  </p>
                  <p className="text-xs text-stone-500">
                    Тикет ожидает итоговой оценки пользователя. Полная история
                    доступна администратору для модерации.
                  </p>
                </div>
              )}
            </>
          )}
        </section>
        <aside
          className={
            mobilePane === "template"
              ? "flex min-h-0 w-full flex-col bg-[#fdfbff] lg:w-[22rem] lg:border-l lg:border-[#fbc4fb]"
              : "hidden min-h-0 w-[22rem] flex-col border-l border-[#fbc4fb] bg-[#fdfbff] lg:flex"
          }
        >
          <div className="border-b border-[#fbc4fb] bg-white/70 p-4">
            <p className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-[#a13cc9]">
              Operator copilot
            </p>
            <h2 className="mt-1 flex items-center gap-2 text-lg font-bold text-black">
              <Bot className="size-5 text-giga" /> Шаблон ответа
            </h2>
            <p className="mt-1.5 text-xs leading-5 text-slate-500">
              GigaChat соберёт ответ по актуальной истории тикета. Перед
              отправкой его можно изменить.
            </p>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto p-4">
            {!dialogId && (
              <EmptyState
                icon={<PanelRight className="size-8" />}
                title="Шаблон не выбран"
                description="Откройте тикет, чтобы сгенерировать ответ для клиента."
              />
            )}
            {dialogId && (
              <div className="space-y-4">
                {isGeneratingTemplate && (
                  <div
                    className="rounded-2xl border border-[#fbc4fb] bg-[#fbc4fb]/35 p-4"
                    role="status"
                    aria-live="polite"
                  >
                    <div className="flex items-center gap-2 text-sm font-bold text-[#a13cc9]">
                      <Sparkles className="size-4 animate-pulse" /> GigaChat
                      формирует шаблон
                    </div>
                    <p className="mt-2 text-xs leading-5 text-slate-500">
                      Берём последние сообщения и готовим новую версию ответа.
                    </p>
                  </div>
                )}
                {!isGeneratingTemplate && !templateText && !template?.error && (
                  <EmptyState
                    icon={<MessagesSquare className="size-8" />}
                    title="Шаблон ещё не создан"
                    description="Нажмите «Сгенерировать шаблон». Контекст будет собран из актуальной истории тикета."
                  />
                )}
                {(templateText || isGeneratingTemplate) && (
                  <div className="rounded-2xl border border-[#dbe3f0] bg-white p-4 shadow-sm">
                    <div className="flex items-center justify-between gap-3">
                      <div>
                        <label
                          htmlFor="operator-template"
                          className="text-sm font-bold text-black"
                        >
                          Редактируемый текст
                        </label>
                        <p className="mt-1 text-[11px] leading-5 text-slate-500">
                          Изменения применяются только к вашему ответу.
                        </p>
                      </div>
                      {templateReady && (
                        <Badge
                          tone="success"
                          className="justify-center text-center"
                        >
                          Готов к вставке
                        </Badge>
                      )}
                    </div>
                    <Textarea
                      id="operator-template"
                      rows={14}
                      className="mt-3 min-h-56 resize-y"
                      value={templateText}
                      disabled={isGeneratingTemplate}
                      onChange={(event) => {
                        if (!dialogId) return;
                        setTemplates((current) => ({
                          ...current,
                          [dialogId]: {
                            status: "ready",
                            text: event.target.value,
                            dialogUpdatedAt: template?.dialogUpdatedAt,
                            updatedAt: template?.updatedAt,
                          },
                        }));
                      }}
                      placeholder="Здесь появится шаблон ответа…"
                    />
                    {template?.updatedAt && !isGeneratingTemplate && (
                      <p className="mt-2 text-[11px] font-semibold text-emerald-700">
                        Шаблон обновлён {formatDateTime(template.updatedAt)}
                      </p>
                    )}
                    <div className="mt-3 flex justify-end">
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        disabled={!templateText.trim()}
                        onClick={() => void copyTemplate()}
                      >
                        <Clipboard className="size-4" /> Скопировать
                      </Button>
                    </div>
                  </div>
                )}
                {template?.error && (
                  <div
                    className="rounded-xl border border-red-200 bg-red-50 px-3 py-2.5 text-xs font-semibold leading-5 text-red-800"
                    role="alert"
                  >
                    Не удалось обновить шаблон: {template.error}
                  </div>
                )}
                {templateStale && (
                  <div className="rounded-xl border border-amber-200 bg-amber-50 px-3 py-2.5 text-xs font-semibold leading-5 text-amber-900">
                    В диалоге появились новые сообщения. Сгенерируйте шаблон
                    заново перед вставкой.
                  </div>
                )}
                {detail.data?.status === "active" && !isAssignedToMe && (
                  <div className="rounded-xl border border-amber-200 bg-amber-50 px-3 py-2.5 text-xs font-semibold leading-5 text-amber-900">
                    Сначала возьмите тикет в работу, чтобы генерировать и
                    вставлять шаблон.
                  </div>
                )}
                {detail.data?.status === "closed" && (
                  <div className="rounded-xl border border-stone-200 bg-stone-100 px-3 py-2.5 text-xs font-semibold leading-5 text-stone-600">
                    Закрытый тикет доступен только для просмотра.
                  </div>
                )}
              </div>
            )}
          </div>
          {dialogId && (
            <div className="border-t border-[#fbc4fb] bg-white/80 p-4">
              <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-1">
                <Button
                  type="button"
                  variant="giga"
                  className="w-full"
                  pending={isGeneratingTemplate}
                  disabled={!canGenerateTemplate}
                  onClick={() => {
                    if (dialogId) generateTemplate.mutate(dialogId);
                  }}
                >
                  <Sparkles className="size-4" />{" "}
                  {templateText
                    ? "Сгенерировать заново"
                    : "Сгенерировать шаблон"}
                </Button>
                <TemplateInsertAction
                  templateText={templateText}
                  currentText={text}
                  disabled={!canInsertTemplate}
                  onInsert={insertTemplate}
                  className="w-full"
                />
              </div>
              <p
                className="mt-3 text-center text-[11px] leading-5 text-stone-400"
                aria-live="polite"
              >
                {isGeneratingTemplate
                  ? "Шаблон загружается…"
                  : !hasUserMessage
                    ? "Ожидаем сообщение клиента для формирования шаблона."
                    : templateStale
                      ? "Шаблон устарел: обновите его по текущему диалогу."
                      : templateReady
                        ? "Шаблон обновлён. Проверьте текст и вставьте его в поле ответа."
                        : "Вставка станет доступна после готовности шаблона."}
              </p>
            </div>
          )}
        </aside>
      </div>
      <ConfirmDialog
        open={closeOpen}
        title="Закрыть тикет?"
        description="Пользователь больше не сможет писать в обращение и увидит финальную оценку решения."
        confirmLabel="Закрыть тикет"
        pending={close.isPending}
        onConfirm={() => close.mutate()}
        onCancel={() => setCloseOpen(false)}
      />
    </div>
  );
}
