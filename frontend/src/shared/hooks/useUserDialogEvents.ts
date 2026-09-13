import { useQueryClient } from "@tanstack/react-query";
import { startTransition, useEffect, useState } from "react";
import { dialogsApi } from "../../api/dialogs";
import { queryKeys } from "../../api/queryKeys";
import type { DialogDetailDto, UserDialogEvent } from "../../api/types";
import { appendPersistedMessage } from "./messageCache";
import { useEventSource } from "./useEventSource";

const eventNames = [
  "dialog_sync",
  "confidence",
  "operator_connected",
  "assistant_token",
  "assistant_done",
  "operator_message",
  "dialog_closed",
  "error",
] as const;

export type UserTurnPhase = "idle" | "vision" | "thinking" | "streaming" | "error";

export function useUserDialogEvents(dialogId: string, onTerminal?: () => void) {
  const queryClient = useQueryClient();
  const [assistantText, setAssistantText] = useState<string | null>(null);
  const [confidence, setConfidence] = useState<number>();
  const [phase, setPhase] = useState<UserTurnPhase>("idle");
  const [eventError, setEventError] = useState<string>();

  useEffect(() => {
    setAssistantText(null);
    setConfidence(undefined);
    setPhase("idle");
    setEventError(undefined);
  }, [dialogId]);

  useEventSource<UserDialogEvent>({
    url: dialogsApi.eventsUrl(dialogId),
    eventNames,
    onOpen: () => {
      void queryClient.refetchQueries({ queryKey: queryKeys.dialog.detail(dialogId), type: "active" });
      void queryClient.refetchQueries({ queryKey: queryKeys.dialog.messages(dialogId), type: "active" });
    },
    onEvent: (event) => {
      switch (event.type) {
        case "dialog_sync":
          setAssistantText(null);
          void queryClient.invalidateQueries({ queryKey: queryKeys.dialog.detail(dialogId) });
          void queryClient.invalidateQueries({ queryKey: queryKeys.dialog.messages(dialogId) });
          break;
        case "confidence":
          setConfidence(event.value);
          setPhase("thinking");
          queryClient.setQueryData<DialogDetailDto>(queryKeys.dialog.detail(dialogId), (current) =>
            current
              ? { ...current, confidence: event.value, isProcessing: true, processingError: undefined }
              : current,
          );
          break;
        case "assistant_token":
          setPhase("streaming");
          queryClient.setQueryData<DialogDetailDto>(queryKeys.dialog.detail(dialogId), (current) =>
            current ? { ...current, isProcessing: true, processingError: undefined } : current,
          );
          startTransition(() => setAssistantText((current) => `${current ?? ""}${event.token}`));
          break;
        case "assistant_done":
          appendPersistedMessage(queryClient, dialogId, event.message);
          setAssistantText(null);
          setPhase("idle");
          queryClient.setQueryData<DialogDetailDto>(queryKeys.dialog.detail(dialogId), (current) =>
            current ? { ...current, isProcessing: false, processingError: undefined } : current,
          );
          void queryClient.invalidateQueries({ queryKey: queryKeys.dialog.detail(dialogId) });
          void queryClient.invalidateQueries({ queryKey: queryKeys.user.dialogs() });
          onTerminal?.();
          break;
        case "operator_connected":
          appendPersistedMessage(queryClient, dialogId, event.message);
          setAssistantText(null);
          setPhase("idle");
          queryClient.setQueryData<DialogDetailDto>(queryKeys.dialog.detail(dialogId), (current) =>
            current
              ? {
                  ...current,
                  mode: "operator_support",
                  assignedOperator: event.operator,
                  isProcessing: false,
                  processingError: undefined,
                }
              : current,
          );
          void queryClient.invalidateQueries({ queryKey: queryKeys.user.dialogs() });
          onTerminal?.();
          break;
        case "operator_message":
          appendPersistedMessage(queryClient, dialogId, event.message);
          void queryClient.invalidateQueries({ queryKey: queryKeys.dialog.detail(dialogId) });
          void queryClient.invalidateQueries({ queryKey: queryKeys.user.dialogs() });
          break;
        case "dialog_closed":
          setAssistantText(null);
          setPhase("idle");
          queryClient.setQueryData<DialogDetailDto>(queryKeys.dialog.detail(dialogId), (current) =>
            current ? { ...current, isProcessing: false, processingError: undefined, status: "closed" } : current,
          );
          void queryClient.invalidateQueries({ queryKey: queryKeys.dialog.detail(dialogId) });
          void queryClient.invalidateQueries({ queryKey: queryKeys.dialog.messages(dialogId) });
          void queryClient.invalidateQueries({ queryKey: queryKeys.user.dialogs() });
          onTerminal?.();
          break;
        case "error":
          setEventError(event.message);
          setAssistantText(null);
          setPhase("error");
          queryClient.setQueryData<DialogDetailDto>(queryKeys.dialog.detail(dialogId), (current) =>
            current ? { ...current, isProcessing: false, processingError: event.message } : current,
          );
          void queryClient.invalidateQueries({ queryKey: queryKeys.user.dialogs() });
          onTerminal?.();
          break;
      }
    },
  });

  return {
    assistantText,
    confidence,
    phase,
    eventError,
    beginTurn: (hasScreenshot: boolean) => {
      setAssistantText("");
      setEventError(undefined);
      setConfidence(undefined);
      setPhase(hasScreenshot ? "vision" : "thinking");
      queryClient.setQueryData<DialogDetailDto>(queryKeys.dialog.detail(dialogId), (current) =>
        current ? { ...current, isProcessing: true, processingError: undefined } : current,
      );
    },
    cancelTurn: () => {
      setAssistantText(null);
      setPhase("idle");
    },
  };
}
