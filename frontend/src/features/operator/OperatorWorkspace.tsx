import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError } from "../../api/client";
import { authApi } from "../../api/auth";
import { dialogsApi } from "../../api/dialogs";
import { operatorApi } from "../../api/operator";
import { queryKeys } from "../../api/queryKeys";
import type { CandidateRef } from "../../api/types";
import { Bot, CheckCircle2, Clipboard, Headphones, Inbox, MessagesSquare, PanelRight, RotateCcw, Sparkles, UserCheck } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { ChatComposer, DialogStatusBadge, MessageList, MessageSources, StreamingMessage } from "../../shared/chat";
import { appendPersistedMessage } from "../../shared/hooks/messageCache";
import { useOperatorDialogEvents } from "../../shared/hooks/useOperatorDialogEvents";
import { Badge, Button, ConfirmDialog, EmptyState, ErrorState, PageLoader, Tabs, useToast } from "../../shared/ui";
import { formatDateTime, formatPercent, getErrorMessage, mergePersistedMessages, retryOrCreateSendAttempt, truncateTitle, type SendAttempt } from "../../shared/utils";
import { DraftInsertAction } from "./DraftInsertAction";
import OperatorQueue from "./OperatorQueue";

type MobilePane = "queue" | "chat" | "draft";

export default function OperatorWorkspace() {
  const { dialogId } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const toast = useToast();
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const [mobilePane, setMobilePane] = useState<MobilePane>(dialogId ? "chat" : "queue");
  const [text, setText] = useState("");
  const [failedAttempt, setFailedAttempt] = useState<SendAttempt>();
  const [closeOpen, setCloseOpen] = useState(false);
  const me = useQuery({ queryKey: queryKeys.me(), queryFn: ({ signal }) => authApi.me(signal) });
  const detail = useQuery({
    queryKey: queryKeys.dialog.detail(dialogId ?? ""),
    queryFn: ({ signal }) => operatorApi.detail(dialogId!, signal),
    enabled: Boolean(dialogId),
  });
  const messages = useInfiniteQuery({
    queryKey: queryKeys.dialog.messages(dialogId ?? ""),
    queryFn: ({ pageParam, signal }) => dialogsApi.messages(dialogId!, pageParam, signal),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.nextCursor ?? undefined,
    enabled: Boolean(dialogId),
  });
  const events = useOperatorDialogEvents(dialogId);
  const allMessages = messages.data ? mergePersistedMessages(...messages.data.pages.map((page) => page.items)) : [];
  const currentDraft = events.draft ?? detail.data?.latestDraft;
  const draftText = events.draftText ?? currentDraft?.text ?? "";
  const draftConfidence = events.confidence ?? currentDraft?.confidence;
  const triggerMessageId = events.triggerMessageId ?? currentDraft?.triggerMessageId;
  const triggerMessage = allMessages.find((message) => message.id === triggerMessageId);
  const isAssignedToMe = Boolean(detail.data?.assignedOperator?.id && detail.data.assignedOperator.id === me.data?.id);

  useEffect(() => setMobilePane(dialogId ? "chat" : "queue"), [dialogId]);

  const claim = useMutation({
    mutationFn: () => operatorApi.claim(dialogId!),
    onSuccess: (claimed) => {
      queryClient.setQueryData(queryKeys.dialog.detail(claimed.id), claimed);
      void queryClient.invalidateQueries({ queryKey: queryKeys.operator.queues() });
      toast("Тикет назначен вам", "success");
      requestAnimationFrame(() => textareaRef.current?.focus());
    },
    onError: (error) => {
      if (error instanceof ApiError && error.status === 409) {
        toast("Тикет уже взят другим оператором.", "error");
        void queryClient.refetchQueries({ queryKey: queryKeys.operator.queues() });
        if (dialogId) void queryClient.refetchQueries({ queryKey: queryKeys.dialog.detail(dialogId) });
        return;
      }
      toast(getErrorMessage(error), "error");
    },
  });
  const send = useMutation({
    mutationFn: (attempt: SendAttempt) => dialogsApi.sendMessage(dialogId!, attempt),
    onSuccess: (message) => {
      appendPersistedMessage(queryClient, dialogId!, message);
      setText("");
      setFailedAttempt(undefined);
      void queryClient.invalidateQueries({ queryKey: queryKeys.dialog.detail(dialogId!) });
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
      void queryClient.invalidateQueries({ queryKey: queryKeys.operator.queues() });
      setCloseOpen(false);
      toast("Тикет закрыт", "success");
    },
    onError: (error) => toast(error.message, "error"),
  });
  const propose = useMutation({
    mutationFn: () => dialogsApi.proposeCandidate(dialogId!),
    onSuccess: (candidate) => {
      queryClient.setQueryData(queryKeys.dialog.detail(dialogId!), (current: typeof detail.data) =>
        current ? { ...current, candidate: { id: candidate.id, status: candidate.status, source: candidate.source } satisfies CandidateRef } : current,
      );
      toast("Кандидат в базу знаний создан", "success");
    },
    onError: (error) => toast(error.message, "error"),
  });

  const submitAttempt = (attempt: SendAttempt) => {
    if (!isAssignedToMe || send.isPending) return;
    send.mutate(attempt);
  };
  const submit = () => {
    const normalized = text.trim();
    if (!normalized) return;
    const attempt = retryOrCreateSendAttempt(normalized, undefined, failedAttempt);
    submitAttempt(attempt);
  };
  const insertDraft = (value: string) => {
    setText(value);
    setFailedAttempt(undefined);
    setMobilePane("chat");
    requestAnimationFrame(() => textareaRef.current?.focus());
  };
  const copyDraft = async () => {
    try {
      await navigator.clipboard.writeText(draftText);
      toast("Черновик скопирован", "success");
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
      <div className="border-b border-stone-200 bg-white p-2 lg:hidden">
        <Tabs value={mobilePane} onChange={setMobilePane} ariaLabel="Панели рабочего места" items={[{ value: "queue", label: "Очередь" }, { value: "chat", label: "Диалог" }, { value: "draft", label: "AI черновик" }]} />
      </div>
      <div className="flex min-h-0 flex-1">
        <OperatorQueue selectedId={dialogId} onSelect={selectDialog} className={mobilePane === "queue" ? "flex w-full lg:w-[19rem]" : "hidden lg:flex lg:w-[19rem]"} />
        <section className={mobilePane === "chat" ? "flex min-w-0 flex-1 flex-col bg-stone-50" : "hidden min-w-0 flex-1 flex-col bg-stone-50 lg:flex"}>
          {!dialogId && <EmptyState icon={<Inbox className="size-9" />} title="Выберите обращение" description="Откройте тикет из очереди. До назначения доступен просмотр, но поле ответа останется заблокированным." />}
          {dialogId && detail.isPending && <PageLoader label="Открываем тикет" />}
          {dialogId && detail.isError && <ErrorState description={detail.error.message} onRetry={() => void detail.refetch()} />}
          {dialogId && detail.data && (
            <>
              <header className="flex min-h-[4.75rem] items-center justify-between gap-4 border-b border-stone-200 bg-white px-4 py-3">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <h1 className="text-base font-bold text-stone-950">{truncateTitle(detail.data.title || `Тикет ${detail.data.id.slice(0, 8)}`)}</h1>
                    <DialogStatusBadge dialog={detail.data} />
                  </div>
                  <p className="mt-1 text-xs text-stone-500">{detail.data.user?.displayName || "Пользователь"} · эскалация {formatDateTime(detail.data.escalatedAt)}</p>
                </div>
                <div className="flex shrink-0 gap-2">
                  {detail.data.status === "active" && !detail.data.assignedOperator && <Button size="sm" pending={claim.isPending} onClick={() => claim.mutate()}><UserCheck className="size-4" /> Взять в работу</Button>}
                  {detail.data.status === "active" && isAssignedToMe && <Button size="sm" variant="secondary" onClick={() => setCloseOpen(true)}><CheckCircle2 className="size-4" /><span className="hidden sm:inline">Закрыть тикет</span></Button>}
                </div>
              </header>
              {detail.data.assignedOperator && !isAssignedToMe && detail.data.status === "active" && (
                <div className="border-b border-amber-200 bg-amber-50 px-4 py-2.5 text-xs font-semibold text-amber-900">Тикет ведёт {detail.data.assignedOperator.displayName}. Редактирование ответа недоступно.</div>
              )}
              <div className="min-h-0 flex-1 overflow-y-auto">
                {messages.isPending && <PageLoader label="Загружаем историю" />}
                {messages.isError && <ErrorState description={messages.error.message} onRetry={() => void messages.refetch()} />}
                {messages.data && <MessageList messages={allMessages} showConfidence showAttachmentAnalysis topAction={messages.hasNextPage ? <Button className="mx-auto" size="sm" variant="ghost" pending={messages.isFetchingNextPage} onClick={() => void messages.fetchNextPage()}><RotateCcw className="size-3.5" /> Ранние сообщения</Button> : undefined} empty={<EmptyState title="История пуста" description="Сообщения появятся после синхронизации с backend." />} />}
              </div>
              {events.eventError && <div className="border-t border-red-100 bg-red-50 px-4 py-2 text-xs font-semibold text-red-800">{events.eventError}</div>}
              {failedAttempt && <div className="flex items-center justify-between gap-3 border-t border-amber-200 bg-amber-50 px-4 py-2 text-xs text-amber-900"><span>Ответ не подтверждён. Retry сохранит тот же UUID.</span><Button size="sm" variant="secondary" pending={send.isPending} onClick={() => submitAttempt(failedAttempt)}>Повторить</Button></div>}
              {detail.data.status === "active" && isAssignedToMe && (
                <ChatComposer ref={textareaRef} value={text} onChange={(value) => { setText(value); if (failedAttempt?.text !== value.trim()) setFailedAttempt(undefined); }} onSend={submit} pending={send.isPending} placeholder="Ответ пользователю…" footer={<button type="button" className="font-semibold text-indigo-600 lg:hidden" onClick={() => setMobilePane("draft")}>Открыть AI черновик</button>} />
              )}
              {detail.data.status === "active" && !isAssignedToMe && !detail.data.assignedOperator && <div className="border-t border-stone-200 bg-white p-4 text-center text-sm text-stone-500"><Headphones className="mr-2 inline size-4" />Возьмите тикет в работу, чтобы ответить пользователю.</div>}
              {detail.data.status === "closed" && (
                <div className="flex flex-wrap items-center justify-between gap-3 border-t border-stone-200 bg-white p-4">
                  <div><p className="text-sm font-bold text-stone-900">Тикет завершён</p><p className="text-xs text-stone-500">Полная история доступна администратору для модерации.</p></div>
                  {detail.data.candidate ? <Badge tone={detail.data.candidate.status === "approved" ? "success" : detail.data.candidate.status === "rejected" ? "danger" : "warning"}>Кандидат уже создан · {detail.data.candidate.status}</Badge> : <Button pending={propose.isPending} onClick={() => propose.mutate()}><Sparkles className="size-4" /> Предложить в БЗ</Button>}
                </div>
              )}
            </>
          )}
        </section>
        <aside className={mobilePane === "draft" ? "flex min-h-0 w-full flex-col bg-[#f7f6ff] lg:w-[22rem] lg:border-l" : "hidden min-h-0 w-[22rem] flex-col border-l border-indigo-100 bg-[#f7f6ff] lg:flex"}>
          <div className="border-b border-indigo-100 bg-white/70 p-4">
            <p className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-indigo-600">Operator copilot</p>
            <h2 className="mt-1 flex items-center gap-2 text-lg font-bold text-stone-950"><Bot className="size-5 text-giga" /> AI GigaChat</h2>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto p-4">
            {!dialogId && <EmptyState icon={<PanelRight className="size-8" />} title="Черновик не выбран" description="Откройте тикет, чтобы увидеть предложение GigaChat." />}
            {dialogId && !draftText && events.draftText === null && <EmptyState icon={<MessagesSquare className="size-8" />} title="Черновика пока нет" description="Он появится после нового сообщения пользователя и сохранится на backend." />}
            {dialogId && events.draftText !== null && <StreamingMessage text={events.draftText} label="GigaChat готовит черновик" />}
            {dialogId && draftText && events.draftText === null && (
              <div className="rounded-2xl border border-indigo-100 bg-white p-4 shadow-sm">
                {triggerMessage && <div className="mb-4 rounded-xl bg-stone-50 p-3 text-xs leading-5 text-stone-600"><strong className="block text-[10px] uppercase tracking-wider text-stone-400">К сообщению пользователя</strong><span className="mt-1 line-clamp-3 block">{triggerMessage.text || "Сообщение с вложением"}</span></div>}
                <p className="whitespace-pre-wrap text-sm leading-6 text-stone-800">{draftText}</p>
                {draftConfidence !== undefined && <div className="mt-4"><Badge tone={draftConfidence < 0.5 ? "danger" : "giga"}>Confidence {formatPercent(draftConfidence)}</Badge></div>}
                <MessageSources sources={currentDraft?.sources ?? []} />
                <div className="mt-5 flex flex-wrap gap-2">
                  <DraftInsertAction draftText={draftText} currentText={text} disabled={!isAssignedToMe || detail.data?.status !== "active"} onInsert={insertDraft} />
                  <Button type="button" variant="secondary" size="sm" onClick={() => void copyDraft()}><Clipboard className="size-4" /> Скопировать</Button>
                </div>
                <p className="mt-4 text-[11px] leading-5 text-stone-400">GigaChat ничего не отправляет сам. Проверьте и при необходимости отредактируйте предложение.</p>
              </div>
            )}
          </div>
        </aside>
      </div>
      <ConfirmDialog open={closeOpen} title="Закрыть тикет?" description="Пользователь больше не сможет писать в обращение и увидит финальную оценку решения." confirmLabel="Закрыть тикет" pending={close.isPending} onConfirm={() => close.mutate()} onCancel={() => setCloseOpen(false)} />
    </div>
  );
}
