import { useQuery } from "@tanstack/react-query";
import { Bot, CheckCircle2, Clock3, MessageSquareMore, TrendingUp, UserRoundCheck } from "lucide-react";
import { useState } from "react";
import { monitoringApi } from "../../api/monitoring";
import { queryKeys } from "../../api/queryKeys";
import type { MonitoringPeriod } from "../../api/types";
import { Card, EmptyState, ErrorState, PageLoader, Tabs } from "../../shared/ui";
import { formatPercent } from "../../shared/utils";

function formatDuration(milliseconds: number): string {
  if (milliseconds < 1000) return `${Math.round(milliseconds)} мс`;
  return `${(milliseconds / 1000).toFixed(1)} сек`;
}

export default function MonitoringPage() {
  const [period, setPeriod] = useState<MonitoringPeriod>("7d");
  const monitoring = useQuery({ queryKey: queryKeys.monitoring(period), queryFn: ({ signal }) => monitoringApi.aggregate(period, signal) });
  const cards = monitoring.data ? [
    { label: "Всего запросов", value: monitoring.data.totalRequests.toLocaleString("ru-RU"), detail: "пользовательских turn", icon: MessageSquareMore, tone: "bg-stone-100 text-stone-700" },
    { label: "Решено AI", value: monitoring.data.aiResolved.toLocaleString("ru-RU"), detail: formatPercent(monitoring.data.aiResolvedRate), icon: Bot, tone: "bg-indigo-100 text-indigo-700" },
    { label: "Эскалации", value: monitoring.data.escalations.toLocaleString("ru-RU"), detail: formatPercent(monitoring.data.escalationRate), icon: UserRoundCheck, tone: "bg-sky-100 text-sky-700" },
    { label: "Среднее время ответа", value: formatDuration(monitoring.data.averageResponseTimeMs), detail: "backend aggregate", icon: Clock3, tone: "bg-amber-100 text-amber-800" },
    { label: "Полезные решения", value: monitoring.data.helpful.toLocaleString("ru-RU"), detail: formatPercent(monitoring.data.helpfulRate), icon: CheckCircle2, tone: "bg-emerald-100 text-emerald-700" },
  ] : [];

  return (
    <div className="p-4 sm:p-6 lg:p-8">
      <div className="mx-auto max-w-7xl">
        <header className="flex flex-wrap items-end justify-between gap-5"><div><p className="text-xs font-extrabold uppercase tracking-[0.18em] text-molvest-600">Aggregate health</p><h1 className="mt-1 text-3xl font-black tracking-[-0.025em] text-molvest-950">Monitoring</h1><p className="mt-2 text-sm text-stone-500">KPI уже агрегированы backend и не вычисляются из списка диалогов в браузере.</p></div><div className="w-full sm:w-auto sm:min-w-[27rem]"><Tabs value={period} onChange={setPeriod} ariaLabel="Период мониторинга" items={[{ value: "today", label: "Сегодня" }, { value: "7d", label: "7 дней" }, { value: "30d", label: "30 дней" }, { value: "all", label: "Всё время" }]} /></div></header>
        {monitoring.isPending && <PageLoader label="Собираем агрегаты" />}
        {monitoring.isError && <ErrorState description={monitoring.error.message} onRetry={() => void monitoring.refetch()} />}
        {monitoring.data && (
          <>
             <div className="mt-7 grid gap-4 sm:grid-cols-2 xl:grid-cols-6">
              {cards.map(({ label, value, detail, icon: Icon, tone }) => <Card key={label} className="p-5"><span className={`flex size-10 items-center justify-center rounded-2xl ${tone}`}><Icon className="size-5" /></span><p className="mt-5 text-xs font-bold text-stone-500">{label}</p><strong className="mt-1 block text-2xl font-black tracking-[-0.025em] text-molvest-950">{value}</strong><span className="mt-1 block text-xs font-semibold text-stone-400">{detail}</span></Card>)}
            </div>
            {monitoring.data.totalRequests === 0 ? <Card className="mt-5"><EmptyState icon={<TrendingUp className="size-8" />} title="За период данных нет" description="KPI появятся после обработки первых пользовательских запросов." /></Card> : <Card className="mt-5 overflow-hidden"><div className="border-b border-stone-100 px-5 py-4"><h2 className="font-bold text-molvest-950">Контур эффективности</h2><p className="mt-1 text-xs text-stone-500">Доли основаны на агрегатах выбранного периода.</p></div><div className="grid gap-6 p-5 sm:grid-cols-3"><Rate label="Автоматизация" value={monitoring.data.aiResolvedRate} color="bg-indigo-500" /><Rate label="Передано специалистам" value={monitoring.data.escalationRate} color="bg-sky-500" /><Rate label="Подтверждено полезным" value={monitoring.data.helpfulRate} color="bg-emerald-500" /></div></Card>}
          </>
        )}
      </div>
    </div>
  );
}

function Rate({ label, value, color }: { label: string; value: number; color: string }) {
  const normalized = Math.max(0, Math.min(value <= 1 ? value * 100 : value, 100));
  return <div><div className="flex justify-between gap-4 text-xs font-bold text-stone-600"><span>{label}</span><span>{Math.round(normalized)}%</span></div><div className="mt-2 h-2 overflow-hidden rounded-full bg-stone-100"><div className={`h-full rounded-full ${color}`} style={{ width: `${normalized}%` }} /></div></div>;
}
