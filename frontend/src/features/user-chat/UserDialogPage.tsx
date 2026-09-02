import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, CheckCircle2, Image as ImageIcon, LockKeyhole, RotateCcw, XCircle } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import { dialogsApi } from "../../api/dialogs";
import { queryKeys } from "../../api/queryKeys";
import type { FeedbackVerdict } from "../../api/types";
import { ChatComposer, DialogStatusBadge, MessageList } from "../../shared/chat";
import { appendPersistedMessage } from "../../shared/hooks/messageCache";
import { useUserDialogEvents } from "../../shared/hooks/useUserDialogEvents";
import { Badge, Button, ConfirmDialog, EmptyState, ErrorState, PageLoader, useToast } from "../../shared/ui";
import { getErrorMessage, mergePersistedMessages, retryOrCreateSendAttempt, truncateTitle, type SendAttempt } from "../../shared/utils";
import { FeedbackPanel } from "./FeedbackPanel";
import UserDialogsNav from "./UserDialogsNav";

export default function UserDialogPage() {
  const { dialogId = "" } = useParams();
  const location = useLocation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const toast = useToast();
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const initialTurn = useRef(location.state as { pendingTurn?: boolean; hasScreenshot?: boolean } | null);
  const [text, setText] = useState("");
  const [attachment, setAttachment] = useState<File>();
  const [attachmentError, setAttachmentError] = useState<string>();
  const [failedAttempt, setFailedAttempt] = useState<SendAttempt>();
  const [awaitingTerminal, setAwaitingTerminal] = useState(Boolean(initialTurn.current?.pendingTurn));
  const [closeOpen, setCloseOpen] = useState(false);
  const detail = useQuery({
    queryKey: queryKeys.dialog.detail(dialogId),
    queryFn: ({ signal }) => dialogsApi.detail(dialogId, signal),
    enabled: Boolean(dialogId),
  });
  const messages = useInfiniteQuery({
    queryKey: queryKeys.dialog.messages(dialogId),
    queryFn: ({ pageParam, signal }) => dialogsApi.messages(dialogId, pageParam, signal),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.nextCursor ?? undefined,
    enabled: Boolean(dialogId),
  });
  const events = useUserDialogEvents(dialogId, () => setAwaitingTerminal(false));
  const allMessages = messages.data ? mergePersistedMessages(...messages.data.pages.map((page) => page.items)) : [];

  const send = useMutation({
    mutationFn: (attempt: SendAttempt) => dialogsApi.sendMessage(dialogId, attempt),
    onSuccess: (message) => {
      appendPersistedMessage(queryClient, dialogId, message);
      setFailedAttempt(undefined);
      setText("");
      setAttachment(undefined);
      setAttachmentError(undefined);
      if (detail.data?.mode === "operator_support") setAwaitingTerminal(false);
      void queryClient.invalidateQueries({ queryKey: queryKeys.user.dialogs() });
      void queryClient.invalidateQueries({ queryKey: queryKeys.dialog.detail(dialogId) });
      requestAnimationFrame(() => textareaRef.current?.focus());
    },
    onError: (error, attempt) => {
      setFailedAttempt(attempt);
      setAwaitingTerminal(false);
      events.cancelTurn();
      toast(getErrorMessage(error), "error");
      requestAnimationFrame(() => textareaRef.current?.focus());
    },
  });
  const closeDialog = useMutation({
    mutationFn: () => dialogsApi.close(dialogId),
    onSuccess: (closed) => {
      queryClient.setQueryData(queryKeys.dialog.detail(dialogId), closed);
      void queryClient.invalidateQueries({ queryKey: queryKeys.user.dialogs() });
      setCloseOpen(false);
      toast("Обращение завершено", "success");
    },
    onError: (error) => toast(error.message, "error"),
  });
  const feedback = useMutation({
    mutationFn: (verdict: FeedbackVerdict) => dialogsApi.feedback(dialogId, verdict),
    onSuccess: (result) => {
      queryClient.setQueryData(queryKeys.dialog.detail(dialogId), (current: typeof detail.data) => current ? { ...current, feedback: result } : current);
      void queryClient.invalidateQueries({ queryKey: queryKeys.user.dialogs() });
      toast("Спасибо, оценка сохранена", "success");
    },
    onError: (error) => toast(error.message, "error"),
  });

  useEffect(() => {
    if (events.eventError) toast(events.eventError, "error");
  }, [events.eventError, toast]);

  useEffect(() => {
    if (!initialTurn.current?.pendingTurn) return;
    navigate(location.pathname, { replace: true, state: null });
  }, [location.pathname, navigate]);

  const submitAttempt = (attempt: SendAttempt) => {
    if (!detail.data || send.isPending) return;
    if (detail.data.mode === "ai_support") {
      setAwaitingTerminal(true);
      events.beginTurn(Boolean(attempt.attachment?.type.startsWith("image/")));
    }
    send.mutate(attempt);
  };
  const submit = () => {
    submitAttempt(retryOrCreateSendAttempt(text, attachment, failedAttempt));
  };
  const updateText = (value: string) => {
    setText(value);
    if (failedAttempt && value.trim() !== failedAttempt.text) setFailedAttempt(undefined);
  };
  const updateAttachment = (file?: File) => {
    setAttachment(file);
    if (failedAttempt && file !== failedAttempt.attachment) setFailedAttempt(undefined);
  };

  if (!dialogId) return <ErrorState title="Диалог не найден" />;
  const visiblePhase = awaitingTerminal && events.phase === "idle"
    ? initialTurn.current?.hasScreenshot ? "vision" : "thinking"
    : events.phase;
  return (
    <div className="flex h-[calc(100vh-65px)] min-h-[32rem]">
      <UserDialogsNav />
      <section className="flex min-w-0 flex-1 flex-col bg-stone-50">
        {detail.isPending && <PageLoader label="Открываем обращение" />}
        {detail.isError && <ErrorState description={detail.error.message} onRetry={() => void detail.refetch()} />}
        {detail.data && (
          <>
            <header className="flex min-h-[4.75rem] items-center gap-3 border-b border-stone-200 bg-white px-3 py-3 sm:px-5">
              <Link to="/user" className="inline-flex size-10 shrink-0 items-center justify-center rounded-xl text-molvest-800 hover:bg-molvest-50 md:hidden" aria-label="К списку обращений"><ArrowLeft className="size-5" /></Link>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <h1 className="text-base font-bold text-molvest-950">{truncateTitle(detail.data.title || `Обращение ${detail.data.id.slice(0, 8)}`)}</h1>
                  <DialogStatusBadge dialog={detail.data} />
                </div>
                <p className="mt-1 truncate text-xs text-stone-500">{detail.data.mode === "operator_support" ? detail.data.assignedOperator ? `На связи ${detail.data.assignedOperator.displayName}` : "Ожидаем свободного специалиста" : "GigaChat использует проверенные материалы базы знаний"}</p>
              </div>
              {detail.data.status === "active" && detail.data.mode === "ai_support" && allMessages.some((message) => message.authorType === "assistant") && (
                <Button variant="secondary" size="sm" disabled={awaitingTerminal || send.isPending} onClick={() => setCloseOpen(true)}><CheckCircle2 className="size-4" /><span className="hidden sm:inline">Завершить обращение</span></Button>
              )}
            </header>
            <div className="min-h-0 flex-1 overflow-y-auto">
              {messages.isPending && <PageLoader label="Загружаем переписку" />}
              {messages.isError && <ErrorState description={messages.error.message} onRetry={() => void messages.refetch()} />}
              {messages.data && (
                <MessageList
                  messages={allMessages}
                  streamingText={events.phase === "streaming" || events.phase === "thinking" ? events.assistantText : null}
                  topAction={messages.hasNextPage ? <Button variant="ghost" size="sm" className="mx-auto" pending={messages.isFetchingNextPage} onClick={() => void messages.fetchNextPage()}><RotateCcw className="size-3.5" /> Загрузить ранние сообщения</Button> : undefined}
                  empty={<EmptyState title="Начните разговор" description="Опишите проблему с 1С. Можно приложить один скриншот или документ." />}
                />
              )}
            </div>
            {visiblePhase === "vision" && <div className="flex items-center gap-2 border-t border-indigo-100 bg-indigo-50 px-4 py-2 text-xs font-semibold text-indigo-800"><ImageIcon className="size-4 animate-pulse" /> Анализирую изображение…</div>}
            {visiblePhase === "thinking" && awaitingTerminal && <div className="flex items-center justify-between gap-3 border-t border-molvest-100 bg-molvest-50 px-4 py-2 text-xs font-semibold text-molvest-800"><span>Проверяю базу знаний и уверенность ответа…</span>{events.confidence !== undefined && <Badge tone="success">Контекст найден</Badge>}</div>}
            {events.phase === "error" && <div className="flex items-center gap-2 border-t border-red-100 bg-red-50 px-4 py-2 text-xs font-semibold text-red-800"><XCircle className="size-4" /> {events.eventError || "Не удалось завершить обработку сообщения. Можно повторить отправку."}</div>}
            {failedAttempt && (
              <div className="flex flex-wrap items-center justify-between gap-3 border-t border-amber-200 bg-amber-50 px-4 py-3 text-xs text-amber-900">
                <span><strong>Отправка не подтверждена.</strong> Повтор использует тот же идентификатор и не создаст дубль.</span>
                <Button size="sm" variant="secondary" pending={send.isPending} onClick={() => submitAttempt(failedAttempt)}><RotateCcw className="size-3.5" /> Повторить</Button>
              </div>
            )}
            {detail.data.status === "active" ? (
              <ChatComposer
                ref={textareaRef}
                value={text}
                onChange={updateText}
                onSend={submit}
                pending={send.isPending}
                disabled={detail.data.mode === "ai_support" && awaitingTerminal}
                attachment={attachment}
                attachmentError={attachmentError}
                onAttachmentChange={updateAttachment}
                onAttachmentError={setAttachmentError}
                placeholder={detail.data.mode === "operator_support" ? "Сообщение специалисту…" : "Опишите вопрос по 1С…"}
                footer={detail.data.mode === "ai_support" && awaitingTerminal ? <span className="flex items-center gap-1 font-semibold text-molvest-700"><LockKeyhole className="size-3" /> Дождитесь ответа</span> : undefined}
              />
            ) : (
              <FeedbackPanel dialog={detail.data} pending={feedback.isPending} onFeedback={(verdict) => feedback.mutate(verdict)} />
            )}
          </>
        )}
      </section>
      <ConfirmDialog
        open={closeOpen}
        title="Завершить обращение?"
        description="После закрытия отправить новые сообщения в этот чат будет нельзя. Вы сможете оценить итоговое решение."
        confirmLabel="Завершить"
        pending={closeDialog.isPending}
        onConfirm={() => closeDialog.mutate()}
        onCancel={() => setCloseOpen(false)}
      />
    </div>
  );
}
