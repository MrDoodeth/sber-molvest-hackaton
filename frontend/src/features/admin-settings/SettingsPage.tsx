import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BrainCircuit, Database, Gauge, Save, Sigma } from "lucide-react";
import { useEffect, useState } from "react";
import { queryKeys } from "../../api/queryKeys";
import { settingsApi } from "../../api/settings";
import type { AdminSettingsInput } from "../../api/types";
import { Badge, Button, Card, EmptyState, ErrorState, Field, PageLoader, useToast } from "../../shared/ui";
import { formatPercent } from "../../shared/utils";

function RangeField({ label, value, onChange, preview }: { label: string; value: number; onChange: (value: number) => void; preview: string }) {
  return (
    <Field label={label} hint={preview}>
      <div className="flex items-center gap-4 rounded-xl border border-stone-200 bg-white px-3 py-3">
        <input type="range" min="0" max="1" step="0.01" value={value} onChange={(event) => onChange(Number(event.target.value))} className="h-2 min-w-0 flex-1 cursor-pointer accent-molvest-700" />
        <span className="w-12 text-right text-sm font-black text-molvest-900">{formatPercent(value)}</span>
      </div>
    </Field>
  );
}

function validate(settings: AdminSettingsInput): string[] {
  const errors: string[] = [];
  if (settings.operatorEscalationThreshold < 0 || settings.operatorEscalationThreshold > 1) errors.push("Порог оператора должен быть от 0% до 100%.");
  return errors;
}

export default function SettingsPage() {
  const queryClient = useQueryClient();
  const toast = useToast();
  const [form, setForm] = useState<AdminSettingsInput>();
  const settings = useQuery({ queryKey: queryKeys.settings(), queryFn: ({ signal }) => settingsApi.settings(signal) });
  useEffect(() => {
    if (!settings.data) return;
    setForm({
      operatorEscalationThreshold: settings.data.operatorEscalationThreshold,
    });
  }, [settings.data]);
  const selectedModel = settings.data?.availableModels?.find((model) => model.id === settings.data.activeModel);
  const gigachatLimit = selectedModel?.contextLimit ?? settings.data?.capabilities.gigachatContextLimit ?? 0;
  const embeddingLimit = settings.data?.capabilities.embeddingContextLimit ?? 0;
  const totalBudget = settings.data ? Math.floor(gigachatLimit * settings.data.gigachatContextRatio) : 0;
  const inputBudget = settings.data ? totalBudget - settings.data.gigachatMaxOutputTokens : 0;
  const embeddingBudget = settings.data ? Math.floor(embeddingLimit * settings.data.embeddingContextRatio) : 0;
  const errors = form ? validate(form) : [];
  const dirty = Boolean(form && settings.data && (
     form.operatorEscalationThreshold !== settings.data.operatorEscalationThreshold
  ));
  const save = useMutation({
    mutationFn: () => settingsApi.saveSettings(form!),
    onSuccess: (updated) => {
      queryClient.setQueryData(queryKeys.settings(), updated);
      toast("AI/RAG настройки применены атомарно", "success");
    },
    onError: (error) => toast(error.message, "error"),
  });

  if (settings.isPending) return <PageLoader label="Загружаем настройки и limits" />;
  if (settings.isError) return <ErrorState description={settings.error.message} onRetry={() => void settings.refetch()} />;
  if (!form || !settings.data) return <EmptyState title="Настройки недоступны" description="Backend не вернул typed settings response." />;

  return (
    <div className="p-4 sm:p-6 lg:p-8">
      <div className="mx-auto max-w-6xl">
         <header className="flex flex-wrap items-end justify-between gap-4"><div><p className="text-xs font-extrabold uppercase tracking-[0.18em] text-molvest-600">Runtime configuration</p><h1 className="mt-1 text-3xl font-black tracking-[-0.025em] text-molvest-950">AI Settings</h1><p className="mt-2 text-sm text-stone-500">Изменяется только порог подключения оператора. Остальные параметры зафиксированы backend-политикой.</p></div>{dirty && <Badge tone="warning">Настройки изменены</Badge>}</header>
        <div className="mt-6 grid gap-5 lg:grid-cols-2">
          <Card className="overflow-hidden">
            <div className="flex items-center gap-3 border-b border-stone-100 bg-stone-50 px-5 py-4"><span className="flex size-10 items-center justify-center rounded-2xl bg-indigo-100 text-indigo-700"><BrainCircuit className="size-5" /></span><div><h2 className="font-bold text-stone-950">GigaChat</h2><p className="text-xs text-stone-500">Generation, context и routing gate</p></div></div>
             <div className="grid gap-5 p-5">
               <Field label="Активная модель" hint="Зафиксирована backend-политикой."><output className="flex min-h-11 items-center rounded-xl border border-stone-200 bg-stone-50 px-3.5 text-sm text-ink">{settings.data.activeModel}</output></Field>
               <Field label="Размер скользящего окна GigaChat" hint={`${formatPercent(settings.data.gigachatContextRatio)} от ${gigachatLimit.toLocaleString("ru-RU")} = ${totalBudget.toLocaleString("ru-RU")} tokens. Параметр фиксирован.`}><output className="flex min-h-11 items-center rounded-xl border border-stone-200 bg-stone-50 px-3.5 text-sm text-ink">{formatPercent(settings.data.gigachatContextRatio)}</output></Field>
               <Field label="Максимальный размер ответа" hint={`Под вход остаётся ${Math.max(inputBudget, 0).toLocaleString("ru-RU")} tokens. Параметр фиксирован.`}><output className="flex min-h-11 items-center rounded-xl border border-stone-200 bg-stone-50 px-3.5 text-sm text-ink">{settings.data.gigachatMaxOutputTokens.toLocaleString("ru-RU")} tokens</output></Field>
               <RangeField label="Порог подключения оператора" value={form.operatorEscalationThreshold} onChange={(value) => setForm({ ...form, operatorEscalationThreshold: value })} preview={`${formatPercent(form.operatorEscalationThreshold)}: ниже этого confidence тикет эскалируется`} />
             </div>
          </Card>
          <Card className="overflow-hidden">
            <div className="flex items-center gap-3 border-b border-stone-100 bg-stone-50 px-5 py-4"><span className="flex size-10 items-center justify-center rounded-2xl bg-molvest-100 text-molvest-700"><Database className="size-5" /></span><div><h2 className="font-bold text-stone-950">Retrieval</h2><p className="text-xs text-stone-500">BGE-M3 и hybrid evidence</p></div></div>
             <div className="grid gap-5 p-5">
               <Field label="Контекст Embeddings" hint={`${formatPercent(settings.data.embeddingContextRatio)} от ${embeddingLimit.toLocaleString("ru-RU")} = ${embeddingBudget.toLocaleString("ru-RU")} tokens. Параметр фиксирован.`}><output className="flex min-h-11 items-center rounded-xl border border-stone-200 bg-stone-50 px-3.5 text-sm text-ink">{formatPercent(settings.data.embeddingContextRatio)}</output></Field>
               <Field label="rag_top_k" hint="Количество лучших chunks после RRF. Параметр фиксирован backend-политикой."><output className="flex min-h-11 items-center rounded-xl border border-stone-200 bg-stone-50 px-3.5 text-sm text-ink">{settings.data.ragTopK}</output></Field>
               <div className="rounded-2xl border border-molvest-100 bg-molvest-50 p-4"><div className="flex items-center gap-2 text-sm font-bold text-molvest-900"><Sigma className="size-4" /> Расчёт budget</div><dl className="mt-4 grid gap-3 text-xs"><div className="flex justify-between gap-4"><dt className="text-stone-500">Общий GigaChat</dt><dd className="font-black text-molvest-900">{totalBudget.toLocaleString("ru-RU")}</dd></div><div className="flex justify-between gap-4"><dt className="text-stone-500">Вход GigaChat</dt><dd className="font-black text-molvest-900">{Math.max(inputBudget, 0).toLocaleString("ru-RU")}</dd></div><div className="flex justify-between gap-4"><dt className="text-stone-500">Вход BGE-M3</dt><dd className="font-black text-molvest-900">{embeddingBudget.toLocaleString("ru-RU")}</dd></div></dl></div>
            </div>
          </Card>
        </div>
        {errors.length > 0 && <div className="mt-5 rounded-2xl border border-red-200 bg-red-50 p-4" role="alert"><div className="flex items-center gap-2 text-sm font-bold text-red-900"><Gauge className="size-4" /> Проверьте значения</div><ul className="mt-2 grid gap-1 text-xs leading-5 text-red-800">{errors.map((error) => <li key={error}>· {error}</li>)}</ul></div>}
        <div className="mt-5 flex justify-end"><Button size="lg" pending={save.isPending} disabled={!dirty || errors.length > 0} onClick={() => save.mutate()}><Save className="size-4" /> Сохранить все настройки</Button></div>
      </div>
    </div>
  );
}
