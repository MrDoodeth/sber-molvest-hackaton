import { useQuery } from "@tanstack/react-query";
import { MessageCircleMore, Plus } from "lucide-react";
import { NavLink, useNavigate } from "react-router-dom";
import { dialogsApi } from "../../api/dialogs";
import { queryKeys } from "../../api/queryKeys";
import { DialogStatusBadge } from "../../shared/chat/DialogStatusBadge";
import { useListReorderAnimation } from "../../shared/hooks/useListReorderAnimation";
import { useUserProcessing } from "../../shared/hooks/useUserProcessing";
import { Button, EmptyState, ErrorState, Skeleton } from "../../shared/ui";
import { cn, formatRelativeDate, truncateTitle } from "../../shared/utils";

export default function UserDialogsNav({ mobile = false }: { mobile?: boolean }) {
  const navigate = useNavigate();
  const processing = useUserProcessing();
  const dialogs = useQuery({
    queryKey: queryKeys.user.dialogs(),
    queryFn: ({ signal }) => dialogsApi.list(signal),
    refetchInterval: 2500,
    refetchOnMount: "always",
  });
  const listRef = useListReorderAnimation<HTMLElement>(dialogs.data?.map((dialog) => dialog.id) ?? []);
  const serverBusyDialogId = dialogs.data?.find((dialog) => dialog.isProcessing)?.id;
  const busyDialogId = processing.busyDialogId ?? serverBusyDialogId ?? null;
  const isBusy = processing.isBusy || serverBusyDialogId !== undefined;

  return (
    <aside className={cn("flex min-h-0 flex-col border-[#dbe3f0] bg-white", mobile ? "h-full" : "hidden border-r md:flex md:w-80 md:shrink-0")}>
      <div className="border-b border-[#dbe3f0] p-4">
        <Button className="w-full" disabled={isBusy} onClick={() => navigate("/user/new")}>
          <Plus className="size-4" /> Новый чат
        </Button>
      </div>
      <div className="flex items-center justify-between px-4 pb-2 pt-4">
        <h2 className="text-xs font-extrabold uppercase tracking-[0.16em] text-slate-500">Мои обращения</h2>
        {dialogs.data && <span className="rounded-full bg-[#fcc67f]/45 px-2 py-0.5 text-xs font-bold text-[#9a5600]">{dialogs.data.length}</span>}
      </div>
      <nav ref={listRef} aria-label="Мои обращения" className="min-h-0 flex-1 overflow-y-auto p-2">
        {dialogs.isPending && <div className="grid gap-2 p-2"><Skeleton className="h-24" /><Skeleton className="h-24" /><Skeleton className="h-24" /></div>}
        {dialogs.isError && dialogs.data === undefined && (
          <ErrorState description={dialogs.error.message} onRetry={() => void dialogs.refetch()} />
        )}
        {dialogs.isError && dialogs.data !== undefined && (
          <ErrorState
            compact
            title="Нет соединения"
            description="Показываем сохранённые обращения."
            onRetry={() => void dialogs.refetch()}
          />
        )}
        {dialogs.data?.length === 0 && (
          <EmptyState icon={<MessageCircleMore className="size-8" />} title="Обращений пока нет" description="Отправьте первое сообщение, чтобы начать диалог." />
        )}
        {dialogs.data?.map((dialog) => (
          <NavLink
            key={dialog.id}
            data-reorder-id={dialog.id}
            to={`/user/dialogs/${dialog.id}`}
            aria-disabled={isBusy && busyDialogId !== dialog.id}
            tabIndex={isBusy && busyDialogId !== dialog.id ? -1 : undefined}
            onClick={(event) => {
              if (isBusy && busyDialogId !== dialog.id) event.preventDefault();
            }}
            className={({ isActive }) => cn(
              "mb-1 block rounded-xl border p-3.5 transition",
              isBusy && busyDialogId !== dialog.id && "pointer-events-none opacity-55",
              isActive ? "border-molvest-200 bg-molvest-50 shadow-sm" : "border-transparent hover:border-[#dbe3f0] hover:bg-[#f1f4fb]",
            )}
          >
            <div className="flex items-start justify-between gap-2">
              <p className="text-sm font-bold leading-5 text-black">{truncateTitle(dialog.title || dialog.lastMessagePreview || "Новое обращение")}</p>
              <span className="shrink-0 text-[10px] text-slate-400">{formatRelativeDate(dialog.updatedAt)}</span>
            </div>
            <div className="mt-2 flex items-center justify-between gap-2">
              <DialogStatusBadge dialog={dialog} />
              {dialog.lastMessagePreview && dialog.title && (
                <span className="truncate text-[11px] text-slate-400">{truncateTitle(dialog.lastMessagePreview, 34)}</span>
              )}
            </div>
          </NavLink>
        ))}
      </nav>
    </aside>
  );
}
