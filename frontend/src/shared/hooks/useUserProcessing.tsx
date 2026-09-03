import { useQuery } from "@tanstack/react-query";
import { createContext, useContext, useState, type ReactNode } from "react";
import { dialogsApi } from "../../api/dialogs";
import { queryKeys } from "../../api/queryKeys";

interface UserProcessingContextValue {
  busyDialogId: string | null;
  isBusy: boolean;
  begin: (dialogId?: string) => void;
  attach: (dialogId: string) => void;
  end: (dialogId?: string) => void;
  isBlocked: (dialogId: string) => boolean;
}

const UserProcessingContext = createContext<UserProcessingContextValue | null>(null);

export function UserProcessingProvider({ children }: { children: ReactNode }) {
  const [optimisticDialogId, setOptimisticDialogId] = useState<string | null | undefined>();
  const dialogs = useQuery({
    queryKey: queryKeys.user.dialogs(),
    queryFn: ({ signal }) => dialogsApi.list(signal),
    refetchInterval: 2500,
    refetchOnMount: "always",
  });
  const serverDialogId = dialogs.data?.find((dialog) => dialog.isProcessing)?.id;
  const busyDialogId = optimisticDialogId !== undefined
    ? optimisticDialogId
    : serverDialogId ?? null;
  const isBusy = optimisticDialogId !== undefined || serverDialogId !== undefined;

  return (
    <UserProcessingContext.Provider
      value={{
        busyDialogId,
        isBusy,
        begin: (dialogId) => setOptimisticDialogId(dialogId ?? null),
        attach: (dialogId) => setOptimisticDialogId(dialogId),
        end: (dialogId) => {
          setOptimisticDialogId((current) => {
            if (dialogId === undefined || current === dialogId) return undefined;
            return current;
          });
        },
        isBlocked: (dialogId) => isBusy && busyDialogId !== dialogId,
      }}
    >
      {children}
    </UserProcessingContext.Provider>
  );
}

export function useUserProcessing(): UserProcessingContextValue {
  const context = useContext(UserProcessingContext);
  if (!context) {
    throw new Error("useUserProcessing must be used inside UserProcessingProvider");
  }
  return context;
}
