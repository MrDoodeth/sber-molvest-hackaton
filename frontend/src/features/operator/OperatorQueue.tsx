import { useQuery } from "@tanstack/react-query";
import { Clock3, Image as ImageIcon, Inbox, UserRound } from "lucide-react";
import { useState } from "react";
import { operatorApi } from "../../api/operator";
import { queryKeys } from "../../api/queryKeys";
import { useOperatorQueueEvents } from "../../shared/hooks/useOperatorQueueEvents";
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
  });
  return (
    <aside className={cn("min-h-0 flex-col border-r border-stone-200 bg-white", className)}>
      <div className="border-b border-stone-100 p-4">
        <div className="mb-3 flex items-center justify-between">
          <div>
            <p className="text-[10px] font-extrabold uppercase tracking-[0.18em] text-molvest-600">Live queue</p>
            <h2 className="mt-0.5 text-lg font-bold text-molvest-950">Обращения</h2>
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
      <div className="min-h-0 flex-1 overflow-y-auto p-2">
        {queue.isPending && <div className="grid gap-2 p-2"><Skeleton className="h-32" /><Skeleton className="h-32" /><Skeleton className="h-32" /></div>}
        {queue.isError && <ErrorState description={queue.error.message} onRetry={() => void queue.refetch()} />}
        {queue.isSuccess && queue.data.length === 0 && (
          <EmptyState icon={<Inbox className="size-8" />} title={scope === "mine" ? "Нет тикетов в работе" : "Очередь пуста"} description={scope === "mine" ? "Возьмите свободное обращение во вкладке «Не назначены»." : "Новые эскалации появятся здесь автоматически."} />
        )}
        {queue.data?.map((dialog) => (
          <button
            key={dialog.id}
            type="button"
            onClick={() => onSelect(dialog.id)}
            className={cn(
              "mb-1 w-full rounded-2xl border p-3.5 text-left transition",
              selectedId === dialog.id ? "border-sky-200 bg-sky-50 shadow-sm" : "border-transparent hover:border-stone-200 hover:bg-stone-50",
            )}
          >
            <div className="flex items-start justify-between gap-2">
              <p className="text-sm font-bold leading-5 text-stone-900">{truncateTitle(dialog.title || dialog.lastMessagePreview || "Обращение пользователя")}</p>
              {dialog.hasAttachment && <ImageIcon className="mt-0.5 size-4 shrink-0 text-indigo-500" aria-label="Есть вложение" />}
            </div>
            <div className="mt-3 flex items-center gap-1.5 text-xs text-stone-500"><UserRound className="size-3.5" /> {dialog.user?.displayName || "Пользователь"}</div>
            <div className="mt-2 flex items-center justify-between gap-2">
              <span className="flex items-center gap-1 text-[11px] text-stone-400"><Clock3 className="size-3" /> {formatRelativeDate(dialog.escalatedAt || dialog.updatedAt)}</span>
              <Badge tone={dialog.confidence < 0.5 ? "danger" : "warning"}>Confidence {formatPercent(dialog.confidence)}</Badge>
            </div>
          </button>
        ))}
      </div>
    </aside>
  );
}
