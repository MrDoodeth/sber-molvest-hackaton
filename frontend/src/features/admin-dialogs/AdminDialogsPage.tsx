import { useQuery } from "@tanstack/react-query";
import { Bot, CalendarDays, ChevronLeft, ChevronRight, Image as ImageIcon, MessagesSquare, UserRound } from "lucide-react";
import { Link, useSearchParams } from "react-router-dom";
import { adminApi, type AdminDialogFilters } from "../../api/admin";
import { queryKeys } from "../../api/queryKeys";
import type { FeedbackVerdict } from "../../api/types";
import { Badge, Button, Card, EmptyState, ErrorState, Field, Input, PageLoader, Select, Tabs } from "../../shared/ui";
import { formatDateTime, formatPercent } from "../../shared/utils";

type JournalTab = FeedbackVerdict | "unrated";

function parseTab(value: string | null): JournalTab {
  return value === "ai_error" || value === "unrated" ? value : "helpful";
}

export default function AdminDialogsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const feedback = parseTab(searchParams.get("feedback"));
  const rawPage = Number(searchParams.get("page") ?? 1);
  const page = Number.isInteger(rawPage) && rawPage > 0 ? rawPage : 1;
  const resolvedBy = searchParams.get("resolved_by");
  const filters: AdminDialogFilters = {
    feedback,
    page,
    date: searchParams.get("date") || undefined,
    resolvedBy: resolvedBy === "ai" || resolvedBy === "operator" ? resolvedBy : undefined,
    hasAttachment: searchParams.get("has_attachment") === "true" ? true : undefined,
  };
  const dialogs = useQuery({
    queryKey: queryKeys.admin.dialogs(filters),
    queryFn: ({ signal }) => adminApi.dialogs(filters, signal),
    refetchInterval: 2500,
    refetchOnMount: "always",
  });
  const patchFilters = (patch: Record<string, string | undefined>) => {
    const next = new URLSearchParams(searchParams);
    Object.entries(patch).forEach(([key, value]) => value ? next.set(key, value) : next.delete(key));
    if (!("page" in patch)) next.set("page", "1");
    setSearchParams(next);
  };

  return (
    <div className="p-4 sm:p-6 lg:p-8">
      <div className="mx-auto max-w-7xl">
        <header className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="text-xs font-extrabold uppercase tracking-[0.18em] text-molvest-600">Quality workbench</p>
            <h1 className="mt-1 text-3xl font-black tracking-[-0.025em] text-molvest-950">Журнал обращений</h1>
            <p className="mt-2 text-sm text-stone-500">Завершённые кейсы, оценка решений и очередь модерации знаний.</p>
          </div>
          {dialogs.data && <div className="rounded-2xl border border-stone-200 bg-white px-4 py-3 text-right"><span className="block text-2xl font-black text-molvest-900">{dialogs.data.total}</span><span className="text-[10px] font-bold uppercase tracking-wider text-stone-400">в этой группе</span></div>}
        </header>
        <Card className="mt-6 overflow-hidden">
          <div className="border-b border-stone-100 p-4 sm:p-5">
            <Tabs<JournalTab>
              value={feedback}
              onChange={(value) => patchFilters({ feedback: value })}
              ariaLabel="Группы журнала"
              items={[{ value: "helpful", label: "Полезные" }, { value: "ai_error", label: "AI ошибся" }, { value: "unrated", label: "Ожидают оценки" }]}
            />
            <div className="mt-4 grid gap-3 sm:grid-cols-[1fr_1fr_auto]">
              <Field label="Дата закрытия">
                <Input type="date" value={filters.date ?? ""} onChange={(event) => patchFilters({ date: event.target.value || undefined })} />
              </Field>
              <Field label="Кем решено">
                <Select value={filters.resolvedBy ?? ""} onChange={(event) => patchFilters({ resolved_by: event.target.value || undefined })}>
                  <option value="">Все</option><option value="ai">AI</option><option value="operator">Оператор</option>
                </Select>
              </Field>
              <label className="flex min-h-11 items-center gap-2 self-end rounded-xl border border-stone-200 bg-stone-50 px-3.5 text-sm font-semibold text-stone-700">
                <input type="checkbox" className="size-4 accent-molvest-700" checked={filters.hasAttachment === true} onChange={(event) => patchFilters({ has_attachment: event.target.checked ? "true" : undefined })} />
                Есть вложение
              </label>
            </div>
          </div>
          {dialogs.isPending && <PageLoader label="Загружаем журнал" />}
          {dialogs.isError && <ErrorState description={dialogs.error.message} onRetry={() => void dialogs.refetch()} />}
          {dialogs.isSuccess && dialogs.data.items.length === 0 && <EmptyState icon={<MessagesSquare className="size-9" />} title="Обращений не найдено" description="Для выбранной группы и фильтров пока нет завершённых диалогов." />}
          {dialogs.data && dialogs.data.items.length > 0 && (
            <>
              <div className="hidden overflow-x-auto md:block">
                <table className="w-full border-collapse text-left text-sm">
                  <thead className="bg-stone-50 text-[10px] font-extrabold uppercase tracking-[0.13em] text-stone-500">
                    <tr><th className="px-5 py-3">Обращение</th><th className="px-4 py-3">Закрыто</th><th className="px-4 py-3">Решено</th><th className="px-4 py-3">Confidence</th><th className="px-4 py-3">Модерация</th><th className="px-5 py-3" /></tr>
                  </thead>
                  <tbody className="divide-y divide-stone-100">
                    {dialogs.data.items.map((dialog) => (
                      <tr key={dialog.id} className="transition hover:bg-molvest-50/50">
                        <td className="max-w-md px-5 py-4"><div className="flex items-start gap-3">{dialog.hasAttachment ? <ImageIcon className="mt-0.5 size-4 shrink-0 text-indigo-500" /> : <MessagesSquare className="mt-0.5 size-4 shrink-0 text-stone-300" />}<div><p className="line-clamp-2 font-bold text-stone-900">{dialog.title || dialog.lastMessagePreview || "Завершённое обращение"}</p><p className="mt-1 text-xs text-stone-400">{dialog.user?.displayName || `ID ${dialog.id.slice(0, 8)}`}</p></div></div></td>
                        <td className="whitespace-nowrap px-4 py-4 text-xs text-stone-500">{formatDateTime(dialog.closedAt)}</td>
                        <td className="px-4 py-4"><Badge tone={dialog.resolvedBy === "ai" ? "giga" : "info"}>{dialog.resolvedBy === "ai" ? <><Bot className="mr-1 size-3" /> AI</> : <><UserRound className="mr-1 size-3" /> Оператор</>}</Badge></td>
                        <td className="px-4 py-4 font-bold text-stone-700">{dialog.lastConfidence === undefined ? "—" : formatPercent(dialog.lastConfidence)}</td>
                        <td className="px-4 py-4">{dialog.candidate ? <Badge tone={dialog.candidate.status === "approved" ? "success" : dialog.candidate.status === "rejected" ? "danger" : "warning"}>{dialog.candidate.status}</Badge> : <span className="text-xs text-stone-400">Нет кандидата</span>}</td>
                        <td className="px-5 py-4 text-right"><Link to={`/admin/dialogs/${dialog.id}`} className="text-sm font-bold text-molvest-700 hover:text-molvest-900">Открыть</Link></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="grid divide-y divide-stone-100 md:hidden">
                {dialogs.data.items.map((dialog) => (
                  <Link key={dialog.id} to={`/admin/dialogs/${dialog.id}`} className="p-4 transition hover:bg-molvest-50">
                    <div className="flex items-start justify-between gap-3"><p className="line-clamp-2 text-sm font-bold text-stone-900">{dialog.title || dialog.lastMessagePreview || "Завершённое обращение"}</p>{dialog.hasAttachment && <ImageIcon className="size-4 shrink-0 text-indigo-500" />}</div>
                    <div className="mt-3 flex flex-wrap items-center gap-2"><Badge tone={dialog.resolvedBy === "ai" ? "giga" : "info"}>{dialog.resolvedBy === "ai" ? "AI" : "Оператор"}</Badge>{dialog.candidate && <Badge tone="warning">{dialog.candidate.status}</Badge>}<span className="ml-auto text-xs text-stone-400">{formatDateTime(dialog.closedAt)}</span></div>
                  </Link>
                ))}
              </div>
              <div className="flex flex-wrap items-center justify-between gap-3 border-t border-stone-100 px-4 py-3">
                <span className="text-xs text-stone-500">Страница {dialogs.data.page} из {Math.max(dialogs.data.totalPages, 1)}</span>
                <div className="flex gap-2">
                  <Button variant="secondary" size="sm" disabled={dialogs.data.page <= 1} onClick={() => patchFilters({ page: String(dialogs.data.page - 1) })}><ChevronLeft className="size-4" /> Назад</Button>
                  <Button variant="secondary" size="sm" disabled={dialogs.data.page >= dialogs.data.totalPages} onClick={() => patchFilters({ page: String(dialogs.data.page + 1) })}>Далее <ChevronRight className="size-4" /></Button>
                </div>
              </div>
            </>
          )}
        </Card>
        <p className="mt-4 flex items-center gap-2 text-xs text-stone-400"><CalendarDays className="size-3.5" /> Пагинация и фильтрация выполняются на backend.</p>
      </div>
    </div>
  );
}
