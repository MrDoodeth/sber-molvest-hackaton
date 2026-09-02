import type { InfiniteData, QueryClient } from "@tanstack/react-query";
import { queryKeys } from "../../api/queryKeys";
import type { MessageDto, MessagePageDto } from "../../api/types";
import { mergePersistedMessages } from "../utils";

export type MessageInfiniteData = InfiniteData<MessagePageDto, string | undefined>;

export function appendPersistedMessage(queryClient: QueryClient, dialogId: string, message: MessageDto) {
  queryClient.setQueryData<MessageInfiniteData>(queryKeys.dialog.messages(dialogId), (current) => {
    if (!current?.pages.length) return current;
    const [first, ...rest] = current.pages;
    return {
      ...current,
      pages: [{ ...first, items: mergePersistedMessages(first.items, [message]) }, ...rest],
    };
  });
}
