import { useQueryClient } from "@tanstack/react-query";
import { operatorApi } from "../../api/operator";
import { queryKeys } from "../../api/queryKeys";
import type { OperatorQueueEvent } from "../../api/types";
import { useEventSource } from "./useEventSource";

const eventNames = ["ticket_available", "ticket_updated", "ticket_claimed", "ticket_closed"] as const;

export function useOperatorQueueEvents() {
  const queryClient = useQueryClient();
  useEventSource<OperatorQueueEvent>({
    url: operatorApi.queueEventsUrl,
    eventNames,
    onOpen: () => {
      void queryClient.refetchQueries({ queryKey: queryKeys.operator.queues(), type: "active" });
    },
    onEvent: (event) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.operator.queues() });
      if (event.type === "ticket_claimed" || event.type === "ticket_closed") {
        void queryClient.invalidateQueries({ queryKey: queryKeys.dialog.detail(event.dialogId) });
      }
    },
  });
}
