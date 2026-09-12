import { useQuery } from "@tanstack/react-query";
import { Clock3, Inbox, UserRound } from "lucide-react";
import { useState } from "react";
import { operatorApi } from "../../api/operator";
import { queryKeys } from "../../api/queryKeys";
import { useOperatorQueueEvents } from "../../shared/hooks/useOperatorQueueEvents";
import { useListReorderAnimation } from "../../shared/hooks/useListReorderAnimation";
import { Badge, EmptyState, ErrorState, Skeleton, Tabs } from "../../shared/ui";
import { cn, formatPercent, formatRelativeDate, truncateTitle } from "../../shared/utils";

export default function OperatorQueue({
  selectedId,
  onSelect,
  className,
}: {
  selectedId?: string;
  onSelect: (id: string) => void;
  className?: string;
}) {
  const [scope, setScope] = useState<"unassigned" | "mine">("unassigned");
  useOperatorQueueEvents();
  const queue = useQuery({
    queryKey: queryKeys.operator.queue(scope),
    queryFn: ({ signal }) => operatorApi.queue(scope, signal),
    refetchInterval: 2500,
    refetchOnMount: "always",
  });
  const listRef = useListReorderAnimation<HTMLDivElement>(queue.data?.map((dialog) => dialog.id) ?? []);
  return (
    <aside className={cn("min-h-0 flex-col border-r border-[#dbe3f0] bg-white", className)}>
      <div className="border-b border-[#dbe3f0] p-4">
        <div className="mb-3 flex items-center justify-between">
          <div>
            <p className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-slate-500">Live queue</p>
            <h2 className="mt-0.5 text-lg font-bold text-black">Обращения</h2>
          </div>
          {queue.data && <Badge tone={scope === "mine" ? "info" : "warning"}>{queue.data.length}</Badge>}
        </div>
        <Tabs
          value={scope}
          onChange={setScope}
          ariaLabel="Очередь оператора"
          items={[{ value: "unassigned", label: "Не назначены" }, { value: "mine", label: "Мои" }]}
        />
      </div>
      <div ref={listRef} className="min-h-0 flex-1 overflow-y-auto p-2">
        {queue.isPending && <div className="grid gap-2 p-2"><Skeleton className="h-32" /><Skeleton className="h-32" /><Skeleton className="h-32" /></div>}
        {queue.isError && queue.data === undefined && (
          <ErrorState description={queue.error.message} onRetry={() => void queue.refetch()} />
        )}
        {queue.isError && queue.data !== undefined && (
          <ErrorState
            compact
            title="Нет соединения"
            description="Показываем сохранённую очередь."
            onRetry={() => void queue.refetch()}
          />
        )}
        {queue.data?.length === 0 && (
          <EmptyState icon={<Inbox className="size-8" />} title={scope === "mine" ? "Нет тикетов в работе" : "Очередь пуста"} description={scope === "mine" ? "Возьмите свободное обращение во вкладке «Не назначены»." : "Новые эскалации появятся здесь автоматически."} />
        )}
        {queue.data?.map((dialog) => (
          <button
            key={dialog.id}
            data-reorder-id={dialog.id}
            type="button"
            onClick={() => onSelect(dialog.id)}
            className={cn(
              "mb-1 w-full rounded-xl border p-3.5 text-left transition",
              selectedId === dialog.id ? "border-[#fbc4fb] bg-[#fdf5fd] shadow-sm" : "border-transparent hover:border-[#dbe3f0] hover:bg-[#f1f4fb]",
            )}
            >
              <div className="flex items-start justify-between gap-2">
                <p className="min-w-0 text-sm font-bold leading-5 text-black">{truncateTitle(dialog.title || dialog.lastMessagePreview || "Обращение пользователя")}</p>
                {dialog.lastMessageAuthor === "user" && <Badge tone="info" className="shrink-0 text-[10px]">Новое</Badge>}
              </div>
              {dialog.lastMessagePreview && dialog.title && <p className="mt-2 truncate text-xs text-slate-500">{dialog.lastMessagePreview}</p>}
            <div className="mt-3 flex items-center gap-1.5 text-xs text-slate-500"><UserRound className="size-3.5" /> {dialog.user?.displayName || "Пользователь"}</div>
            <div className="mt-2 flex items-center justify-between gap-2">
              <span className="flex items-center gap-1 text-[11px] text-slate-400"><Clock3 className="size-3" /> {formatRelativeDate(dialog.escalatedAt || dialog.updatedAt)}</span>
              <Badge tone={dialog.confidence < 0.5 ? "danger" : "warning"}>Confidence {formatPercent(dialog.confidence)}</Badge>
            </div>
          </button>
        ))}
      </div>
    </aside>
  );
}
