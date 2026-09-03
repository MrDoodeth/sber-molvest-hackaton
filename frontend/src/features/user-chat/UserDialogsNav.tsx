import { useQuery } from "@tanstack/react-query";
import { MessageCircleMore, Plus } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { dialogsApi } from "../../api/dialogs";
import { queryKeys } from "../../api/queryKeys";
import { DialogStatusBadge } from "../../shared/chat/DialogStatusBadge";
import { Button, EmptyState, ErrorState, Skeleton } from "../../shared/ui";
import { cn, formatRelativeDate, truncateTitle } from "../../shared/utils";

function preloadNewDialog() {
  void import("./NewUserDialogPage");
}

export default function UserDialogsNav({ mobile = false }: { mobile?: boolean }) {
  const navigate = useNavigate();
  const dialogs = useQuery({
    queryKey: queryKeys.user.dialogs(),
    queryFn: ({ signal }) => dialogsApi.list(signal),
    refetchInterval: 2500,
    refetchOnMount: "always",
  });
  const order = dialogs.data?.map((dialog) => dialog.id).join(",") ?? "";
  const previousOrder = useRef(order);
  const [orderRevision, setOrderRevision] = useState(0);

  useEffect(() => {
    preloadNewDialog();
  }, []);

  useEffect(() => {
    if (previousOrder.current && previousOrder.current !== order) {
      setOrderRevision((current) => current + 1);
    }
    previousOrder.current = order;
  }, [order]);

  return (
    <aside className={cn("flex min-h-0 flex-col border-stone-200 bg-white", mobile ? "h-full" : "hidden border-r md:flex md:w-80 md:shrink-0")}>
      <div className="border-b border-stone-100 p-4">
          <Button
            className="w-full"
            onClick={() => navigate("/user/new")}
            onFocus={preloadNewDialog}
            onPointerEnter={preloadNewDialog}
            onTouchStart={preloadNewDialog}
          >
          <Plus className="size-4" /> Новый чат
        </Button>
      </div>
      <div className="flex items-center justify-between px-4 pb-2 pt-4">
        <h2 className="text-xs font-extrabold uppercase tracking-[0.16em] text-stone-500">Мои обращения</h2>
        {dialogs.data && <span className="text-xs font-bold text-stone-400">{dialogs.data.length}</span>}
      </div>
      <nav aria-label="Мои обращения" className="min-h-0 flex-1 overflow-y-auto p-2">
        {dialogs.isPending && <div className="grid gap-2 p-2"><Skeleton className="h-24" /><Skeleton className="h-24" /><Skeleton className="h-24" /></div>}
        {dialogs.isError && <ErrorState description={dialogs.error.message} onRetry={() => void dialogs.refetch()} />}
        {dialogs.isSuccess && dialogs.data.length === 0 && (
          <EmptyState icon={<MessageCircleMore className="size-8" />} title="Обращений пока нет" description="Создайте чат, чтобы задать первый вопрос." />
        )}
        {dialogs.data?.map((dialog) => (
          <NavLink
            key={`${dialog.id}-${orderRevision}`}
            to={`/user/dialogs/${dialog.id}`}
            className={({ isActive }) => cn(
              "dialog-reorder-item mb-1 block rounded-2xl border p-3.5 transition",
              isActive ? "border-molvest-200 bg-molvest-50 shadow-sm" : "border-transparent hover:border-stone-200 hover:bg-stone-50",
            )}
          >
            <div className="flex items-start justify-between gap-2">
              <p className="text-sm font-bold leading-5 text-molvest-950">{truncateTitle(dialog.title || dialog.lastMessagePreview || "Новое обращение")}</p>
              <span className="shrink-0 text-[10px] text-stone-400">{formatRelativeDate(dialog.updatedAt)}</span>
            </div>
            <div className="mt-2 flex items-center justify-between gap-2">
              <DialogStatusBadge dialog={dialog} />
              {dialog.lastMessagePreview && dialog.title && (
                <span className="truncate text-[11px] text-stone-400">{truncateTitle(dialog.lastMessagePreview, 34)}</span>
              )}
            </div>
          </NavLink>
        ))}
      </nav>
    </aside>
  );
}
