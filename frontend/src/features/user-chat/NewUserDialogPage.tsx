import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, MessageCircleMore, RotateCcw } from "lucide-react";
import { useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import type { DialogDetailDto, DialogSummary, MessageDto } from "../../api/types";
import { dialogsApi } from "../../api/dialogs";
import { queryKeys } from "../../api/queryKeys";
import { ChatComposer, MessageList } from "../../shared/chat";
import type { MessageInfiniteData } from "../../shared/hooks/messageCache";
import { Button, EmptyState, useToast } from "../../shared/ui";
import {
  getErrorMessage,
  retryOrCreateSendAttempt,
  type SendAttempt,
} from "../../shared/utils";
import UserDialogsNav from "./UserDialogsNav";

export default function NewUserDialogPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const toast = useToast();
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const createdDialogRef = useRef<DialogDetailDto>();
  const [text, setText] = useState("");
  const [attachment, setAttachment] = useState<File>();
  const [attachmentError, setAttachmentError] = useState<string>();
  const [failedAttempt, setFailedAttempt] = useState<SendAttempt>();
  const [optimisticMessage, setOptimisticMessage] = useState<MessageDto>();

  const startDialog = useMutation({
    mutationFn: async (attempt: SendAttempt) => {
      const dialog = createdDialogRef.current ?? await dialogsApi.create();
      createdDialogRef.current = dialog;
      const message = await dialogsApi.sendMessage(dialog.id, attempt);
      return { dialog, message, hasScreenshot: Boolean(attempt.attachment?.type.startsWith("image/")) };
    },
    onSuccess: ({ dialog, message, hasScreenshot }) => {
      const hydratedDialog: DialogDetailDto = {
        ...dialog,
        title: message.text || undefined,
        lastMessagePreview: message.text || undefined,
        hasAttachment: message.attachments.length > 0,
        updatedAt: message.createdAt,
      };
      queryClient.setQueryData(queryKeys.dialog.detail(dialog.id), hydratedDialog);
      queryClient.setQueryData<MessageInfiniteData>(queryKeys.dialog.messages(dialog.id), {
        pages: [{ items: [message], nextCursor: null }],
        pageParams: [undefined],
      });
      queryClient.setQueryData<DialogSummary[]>(queryKeys.user.dialogs(), (current) =>
        current ? [hydratedDialog, ...current.filter((item) => item.id !== dialog.id)] : current,
      );
      void queryClient.invalidateQueries({ queryKey: queryKeys.user.dialogs() });
      navigate(`/user/dialogs/${dialog.id}`, {
        replace: true,
        state: { pendingTurn: true, hasScreenshot },
      });
    },
    onError: (error, attempt) => {
      setOptimisticMessage(undefined);
      setText(attempt.text);
      setAttachment(attempt.attachment);
      setFailedAttempt(attempt);
      toast(getErrorMessage(error), "error");
      requestAnimationFrame(() => textareaRef.current?.focus());
    },
  });

  const submitAttempt = (attempt: SendAttempt) => {
    if (startDialog.isPending) return;
    setOptimisticMessage({
      id: attempt.clientMessageId,
      dialogId: "new",
      authorType: "user",
      text: attempt.text,
      attachments: attempt.attachment ? [{
        id: `local-${attempt.clientMessageId}`,
        messageId: attempt.clientMessageId,
        fileName: attempt.attachment.name,
        mimeType: attempt.attachment.type,
        sizeBytes: attempt.attachment.size,
      }] : [],
      sources: [],
      createdAt: new Date().toISOString(),
    });
    setText("");
    setAttachment(undefined);
    setAttachmentError(undefined);
    setFailedAttempt(undefined);
    startDialog.mutate(attempt);
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

  return (
    <div className="flex h-[calc(100vh-65px)] min-h-[32rem]">
      <UserDialogsNav />
      <section className="flex min-w-0 flex-1 flex-col bg-stone-50">
        <header className="flex min-h-[4.75rem] items-center gap-3 border-b border-stone-200 bg-white px-3 py-3 sm:px-5">
          <Link to="/user" className="inline-flex size-10 shrink-0 items-center justify-center rounded-xl text-molvest-800 hover:bg-molvest-50 md:hidden" aria-label="К списку обращений"><ArrowLeft className="size-5" /></Link>
          <div className="min-w-0">
            <h1 className="text-base font-bold text-molvest-950">Новое обращение</h1>
            <p className="mt-1 text-xs text-stone-500">Диалог появится в списке после отправки первого сообщения.</p>
          </div>
        </header>
        <div className="min-h-0 flex-1 overflow-y-auto">
          <MessageList
            messages={optimisticMessage ? [optimisticMessage] : []}
            streamingText={optimisticMessage ? "" : null}
            empty={<EmptyState icon={<MessageCircleMore className="size-8" />} title="Начните разговор" description="Опишите проблему с 1С. Можно приложить один скриншот или документ." />}
          />
        </div>
        {failedAttempt && (
          <div className="flex flex-wrap items-center justify-between gap-3 border-t border-amber-200 bg-amber-50 px-4 py-3 text-xs text-amber-900">
            <span><strong>Отправка не подтверждена.</strong> Повтор использует тот же идентификатор и не создаст дубль сообщения.</span>
            <Button size="sm" variant="secondary" pending={startDialog.isPending} onClick={() => submitAttempt(failedAttempt)}><RotateCcw className="size-3.5" /> Повторить</Button>
          </div>
        )}
        <ChatComposer
          ref={textareaRef}
          value={text}
          onChange={updateText}
          onSend={submit}
          pending={startDialog.isPending}
          attachment={attachment}
          attachmentError={attachmentError}
          onAttachmentChange={updateAttachment}
          onAttachmentError={setAttachmentError}
          placeholder="Опишите вопрос по 1С…"
        />
      </section>
    </div>
  );
}
