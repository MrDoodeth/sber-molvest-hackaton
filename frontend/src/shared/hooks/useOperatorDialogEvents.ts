import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { operatorApi } from "../../api/operator";
import { queryKeys } from "../../api/queryKeys";
import type { OperatorDialogDetailDto, OperatorDialogEvent } from "../../api/types";
import { appendPersistedMessage } from "./messageCache";
import { useEventSource } from "./useEventSource";

const eventNames = ["user_message", "dialog_closed", "error"] as const;

export function useOperatorDialogEvents(dialogId?: string) {
  const queryClient = useQueryClient();
  const [eventError, setEventError] = useState<string>();

  useEffect(() => {
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
          setEventError(undefined);
          void queryClient.invalidateQueries({ queryKey: queryKeys.dialog.detail(dialogId) });
          void queryClient.invalidateQueries({ queryKey: queryKeys.operator.queues() });
          break;
        case "dialog_closed":
          queryClient.setQueryData<OperatorDialogDetailDto>(queryKeys.dialog.detail(dialogId), (current) =>
            current ? { ...current, isProcessing: false, processingError: undefined, status: "closed" } : current,
          );
          void queryClient.invalidateQueries({ queryKey: queryKeys.dialog.detail(dialogId) });
          void queryClient.invalidateQueries({ queryKey: queryKeys.dialog.messages(dialogId) });
          void queryClient.invalidateQueries({ queryKey: queryKeys.operator.queues() });
          break;
        case "error":
          setEventError(event.message);
          queryClient.setQueryData<OperatorDialogDetailDto>(queryKeys.dialog.detail(dialogId), (current) =>
            current ? { ...current, isProcessing: false, processingError: event.message } : current,
          );
          void queryClient.invalidateQueries({ queryKey: queryKeys.operator.queues() });
          break;
      }
    },
  });

  return { eventError };
}
