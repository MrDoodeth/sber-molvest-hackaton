import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, MessageCircleMore } from "lucide-react";
import { useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ApiError } from "../../api/client";
import type { DialogDetailDto, DialogSummary, MessageDto } from "../../api/types";
import { dialogsApi } from "../../api/dialogs";
import { queryKeys } from "../../api/queryKeys";
import { ChatComposer, MessageList, isRuntimeImage } from "../../shared/chat";
import type { MessageInfiniteData } from "../../shared/hooks/messageCache";
import { useUserProcessing } from "../../shared/hooks/useUserProcessing";
import { EmptyState, useToast } from "../../shared/ui";
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
  const processing = useUserProcessing();
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const createdDialogRef = useRef<DialogDetailDto>();
  const [text, setText] = useState("");
  const [attachments, setAttachments] = useState<File[]>([]);
  const [attachmentError, setAttachmentError] = useState<string>();
  const [optimisticMessage, setOptimisticMessage] = useState<MessageDto>();
  const [failedAttempt, setFailedAttempt] = useState<SendAttempt>();

  const startDialog = useMutation({
    mutationFn: async (attempt: SendAttempt) => {
      const dialog = createdDialogRef.current ?? await dialogsApi.create();
      createdDialogRef.current = dialog;
      const message = await dialogsApi.sendMessage(dialog.id, attempt);
      return { dialog, message, hasScreenshot: attempt.attachments.some(isRuntimeImage) };
    },
    onSuccess: ({ dialog, message, hasScreenshot }) => {
      processing.attach(dialog.id);
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
      const attachmentRejected =
        attempt.attachments.length > 0 &&
        error instanceof ApiError &&
        error.code === "unprocessable";
      processing.end();
      setOptimisticMessage(undefined);
      setText(attempt.text);
      setAttachments(attachmentRejected ? [] : attempt.attachments);
      setFailedAttempt(attachmentRejected ? undefined : attempt);
      setAttachmentError(attachmentRejected ? error.message : undefined);
      toast(getErrorMessage(error), "error");
      requestAnimationFrame(() => textareaRef.current?.focus());
    },
  });

  const submitAttempt = (attempt: SendAttempt) => {
    if (startDialog.isPending || processing.isBusy) return;
    processing.begin();
    setOptimisticMessage({
      id: attempt.clientMessageId,
      dialogId: "new",
      authorType: "user",
      text: attempt.text,
      attachments: attempt.attachments.map((file, index) => ({
        id: `local-${attempt.clientMessageId}-${index}`,
        messageId: attempt.clientMessageId,
        fileName: file.name,
        mimeType: file.type,
        sizeBytes: file.size,
      })),
       createdAt: new Date().toISOString(),
    });
    setText("");
    setAttachments([]);
    setFailedAttempt(undefined);
    setAttachmentError(undefined);
    startDialog.mutate(attempt);
  };
  const submit = () => {
    submitAttempt(retryOrCreateSendAttempt(text.trim(), attachments, failedAttempt));
  };
  const updateText = (value: string) => {
    setText(value);
    if (failedAttempt?.text !== value.trim()) setFailedAttempt(undefined);
  };
  const updateAttachments = (files: File[]) => {
    setAttachments(files);
    setFailedAttempt(undefined);
  };

  return (
    <div className="flex h-[calc(100vh-65px)] min-h-[32rem]">
      <UserDialogsNav />
      <section className="flex min-w-0 flex-1 flex-col bg-cream">
        <header className="flex min-h-[4.75rem] items-center gap-3 border-b border-[#dbe3f0] bg-white px-3 py-3 sm:px-5">
          <Link to="/user" className="inline-flex size-10 shrink-0 items-center justify-center rounded-xl text-molvest-700 hover:bg-molvest-50 md:hidden" aria-label="К списку обращений"><ArrowLeft className="size-5" /></Link>
          <div className="min-w-0">
            <h1 className="text-base font-bold text-black">Новое обращение</h1>
            <p className="mt-1 text-xs text-slate-500">Диалог появится в списке после отправки первого сообщения.</p>
          </div>
        </header>
        <div className="min-h-0 flex-1 overflow-y-auto">
          <MessageList
            messages={optimisticMessage ? [optimisticMessage] : []}
            streamingText={optimisticMessage ? "" : null}
             empty={<EmptyState icon={<MessageCircleMore className="size-8" />} title="Начните разговор" description="Опишите проблему с 1С. Можно приложить до 10 файлов и одно изображение." />}
          />
        </div>
        <ChatComposer
          ref={textareaRef}
          value={text}
           onChange={updateText}
           onSend={submit}
           pending={startDialog.isPending}
           disabled={processing.isBusy}
          attachments={attachments}
          attachmentError={attachmentError}
           onAttachmentChange={updateAttachments}
           onAttachmentError={setAttachmentError}
           placeholder="Опишите вопрос по 1С…"
        />
      </section>
    </div>
  );
}
