import { useQueryClient } from "@tanstack/react-query";
import { startTransition, useEffect, useState } from "react";
import { operatorApi } from "../../api/operator";
import { queryKeys } from "../../api/queryKeys";
import type { OperatorDialogDetailDto, OperatorDialogEvent, OperatorDraftDto } from "../../api/types";
import { appendPersistedMessage } from "./messageCache";
import { useEventSource } from "./useEventSource";

const eventNames = ["user_message", "confidence", "draft_token", "draft_done", "dialog_closed", "error"] as const;

export function useOperatorDialogEvents(dialogId?: string) {
  const queryClient = useQueryClient();
  const [draftText, setDraftText] = useState<string | null>(null);
  const [draft, setDraft] = useState<OperatorDraftDto>();
  const [triggerMessageId, setTriggerMessageId] = useState<string>();
  const [confidence, setConfidence] = useState<number>();
  const [eventError, setEventError] = useState<string>();

  useEffect(() => {
    setDraftText(null);
    setDraft(undefined);
    setTriggerMessageId(undefined);
    setConfidence(undefined);
    setEventError(undefined);
  }, [dialogId]);

  useEventSource<OperatorDialogEvent>({
    url: dialogId ? operatorApi.dialogEventsUrl(dialogId) : "",
    eventNames,
    enabled: Boolean(dialogId),
    onOpen: () => {
      if (!dialogId) return;
      void queryClient.refetchQueries({ queryKey: queryKeys.dialog.detail(dialogId), type: "active" });
      void queryClient.refetchQueries({ queryKey: queryKeys.dialog.messages(dialogId), type: "active" });
    },
    onEvent: (event) => {
      if (!dialogId) return;
      switch (event.type) {
        case "user_message":
          appendPersistedMessage(queryClient, dialogId, event.message);
          setDraftText("");
          setDraft(undefined);
          setTriggerMessageId(event.message.id);
          setConfidence(undefined);
          setEventError(undefined);
          queryClient.setQueryData<OperatorDialogDetailDto>(queryKeys.dialog.detail(dialogId), (current) =>
            current ? { ...current, isProcessing: true, processingError: undefined } : current,
          );
          void queryClient.invalidateQueries({ queryKey: queryKeys.dialog.detail(dialogId) });
          void queryClient.invalidateQueries({ queryKey: queryKeys.operator.queues() });
          break;
        case "confidence":
          setEventError(undefined);
          setConfidence(event.value);
          setTriggerMessageId(event.triggerMessageId);
          queryClient.setQueryData<OperatorDialogDetailDto>(queryKeys.dialog.detail(dialogId), (current) =>
            current ? { ...current, isProcessing: true, processingError: undefined } : current,
          );
          break;
        case "draft_token":
          setEventError(undefined);
          if (triggerMessageId !== event.triggerMessageId) setDraftText("");
          setTriggerMessageId(event.triggerMessageId);
          queryClient.setQueryData<OperatorDialogDetailDto>(queryKeys.dialog.detail(dialogId), (current) =>
            current ? { ...current, isProcessing: true, processingError: undefined } : current,
          );
          startTransition(() => setDraftText((current) => `${current ?? ""}${event.token}`));
          break;
        case "draft_done":
          setDraft(event.draft);
          setDraftText(null);
          setConfidence(event.draft.confidence);
          setTriggerMessageId(event.draft.triggerMessageId);
          queryClient.setQueryData<OperatorDialogDetailDto>(queryKeys.dialog.detail(dialogId), (current) =>
            current
              ? {
                  ...current,
                  latestDraft: event.draft,
                  isProcessing: false,
                  processingError: undefined,
                }
              : current,
          );
          queryClient.setQueryData(queryKeys.operator.draft(dialogId), event.draft);
          break;
        case "dialog_closed":
          setDraftText(null);
          queryClient.setQueryData<OperatorDialogDetailDto>(queryKeys.dialog.detail(dialogId), (current) =>
            current ? { ...current, isProcessing: false, processingError: undefined, status: "closed" } : current,
          );
          void queryClient.invalidateQueries({ queryKey: queryKeys.dialog.detail(dialogId) });
          void queryClient.invalidateQueries({ queryKey: queryKeys.dialog.messages(dialogId) });
          void queryClient.invalidateQueries({ queryKey: queryKeys.operator.queues() });
          break;
        case "error":
          setEventError(event.message);
          setDraftText(null);
          queryClient.setQueryData<OperatorDialogDetailDto>(queryKeys.dialog.detail(dialogId), (current) =>
            current ? { ...current, isProcessing: false, processingError: event.message } : current,
          );
          void queryClient.invalidateQueries({ queryKey: queryKeys.operator.queues() });
          break;
      }
    },
  });

  return { draftText, draft, triggerMessageId, confidence, eventError };
}
