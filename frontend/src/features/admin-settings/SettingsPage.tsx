import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BrainCircuit, Database, Gauge, Save, Sigma } from "lucide-react";
import { useEffect, useState } from "react";
import { queryKeys } from "../../api/queryKeys";
import { settingsApi } from "../../api/settings";
import type { AdminSettingsInput } from "../../api/types";
import { Badge, Button, Card, EmptyState, ErrorState, Field, Input, PageLoader, Select, useToast } from "../../shared/ui";
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

function validate(settings: AdminSettingsInput, gigachatContextLimit: number): string[] {
  const errors: string[] = [];
  if (settings.gigachatContextRatio < 0 || settings.gigachatContextRatio > 1) errors.push("Размер контекста GigaChat должен быть от 0% до 100%.");
  if (settings.embeddingContextRatio < 0 || settings.embeddingContextRatio > 1) errors.push("Контекст Embeddings должен быть от 0% до 100%.");
  if (settings.operatorEscalationThreshold < 0 || settings.operatorEscalationThreshold > 1) errors.push("Порог оператора должен быть от 0% до 100%.");
  const totalBudget = Math.floor(gigachatContextLimit * settings.gigachatContextRatio);
  if (!Number.isInteger(settings.gigachatMaxOutputTokens) || settings.gigachatMaxOutputTokens <= 0 || settings.gigachatMaxOutputTokens >= totalBudget) errors.push("Максимальный ответ должен быть целым положительным числом меньше общего budget GigaChat.");
  if (!Number.isInteger(settings.ragTopK) || settings.ragTopK < 1) errors.push("rag_top_k должен быть целым числом не меньше 1.");
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
      activeModel: settings.data.activeModel,
      gigachatContextRatio: settings.data.gigachatContextRatio,
      gigachatMaxOutputTokens: settings.data.gigachatMaxOutputTokens,
      embeddingContextRatio: settings.data.embeddingContextRatio,
      ragTopK: settings.data.ragTopK,
      operatorEscalationThreshold: settings.data.operatorEscalationThreshold,
    });
  }, [settings.data]);
  const selectedModel = settings.data?.availableModels?.find((model) => model.id === form?.activeModel);
  const gigachatLimit = selectedModel?.contextLimit ?? settings.data?.capabilities.gigachatContextLimit ?? 0;
  const embeddingLimit = settings.data?.capabilities.embeddingContextLimit ?? 0;
  const totalBudget = form ? Math.floor(gigachatLimit * form.gigachatContextRatio) : 0;
  const inputBudget = form ? totalBudget - form.gigachatMaxOutputTokens : 0;
  const embeddingBudget = form ? Math.floor(embeddingLimit * form.embeddingContextRatio) : 0;
  const errors = form ? validate(form, gigachatLimit) : [];
  const dirty = Boolean(form && settings.data && (
    form.activeModel !== settings.data.activeModel ||
    form.gigachatContextRatio !== settings.data.gigachatContextRatio ||
    form.gigachatMaxOutputTokens !== settings.data.gigachatMaxOutputTokens ||
    form.embeddingContextRatio !== settings.data.embeddingContextRatio ||
    form.ragTopK !== settings.data.ragTopK ||
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
        <header className="flex flex-wrap items-end justify-between gap-4"><div><p className="text-xs font-extrabold uppercase tracking-[0.18em] text-molvest-600">Runtime configuration</p><h1 className="mt-1 text-3xl font-black tracking-[-0.025em] text-molvest-950">AI Settings</h1><p className="mt-2 text-sm text-stone-500">Одна атомарная операция для модели, контекста, retrieval и эскалации.</p></div>{dirty && <Badge tone="warning">Настройки изменены</Badge>}</header>
        <div className="mt-6 grid gap-5 lg:grid-cols-2">
          <Card className="overflow-hidden">
            <div className="flex items-center gap-3 border-b border-stone-100 bg-stone-50 px-5 py-4"><span className="flex size-10 items-center justify-center rounded-2xl bg-indigo-100 text-indigo-700"><BrainCircuit className="size-5" /></span><div><h2 className="font-bold text-stone-950">GigaChat</h2><p className="text-xs text-stone-500">Generation, context и routing gate</p></div></div>
            <div className="grid gap-5 p-5">
              <Field label="Активная модель" hint="Context limits для каждой модели возвращает backend."><Select value={form.activeModel} onChange={(event) => setForm({ ...form, activeModel: event.target.value })}>{settings.data.availableModels?.map((model) => <option key={model.id} value={model.id}>{model.label} · {model.id}</option>)}</Select></Field>
              <RangeField label="Размер скользящего окна GigaChat" value={form.gigachatContextRatio} onChange={(value) => setForm({ ...form, gigachatContextRatio: value })} preview={`${formatPercent(form.gigachatContextRatio)} от ${gigachatLimit.toLocaleString("ru-RU")} = ${totalBudget.toLocaleString("ru-RU")} tokens`} />
              <Field label="Максимальный размер ответа" hint={`Под вход остаётся ${Math.max(inputBudget, 0).toLocaleString("ru-RU")} tokens.`}><Input type="number" min="1" step="1" value={form.gigachatMaxOutputTokens} onChange={(event) => setForm({ ...form, gigachatMaxOutputTokens: Number(event.target.value) })} /></Field>
              <RangeField label="Порог подключения оператора" value={form.operatorEscalationThreshold} onChange={(value) => setForm({ ...form, operatorEscalationThreshold: value })} preview={`${formatPercent(form.operatorEscalationThreshold)}: ниже этого confidence тикет эскалируется`} />
            </div>
          </Card>
          <Card className="overflow-hidden">
            <div className="flex items-center gap-3 border-b border-stone-100 bg-stone-50 px-5 py-4"><span className="flex size-10 items-center justify-center rounded-2xl bg-molvest-100 text-molvest-700"><Database className="size-5" /></span><div><h2 className="font-bold text-stone-950">Retrieval</h2><p className="text-xs text-stone-500">BGE-M3 и hybrid evidence</p></div></div>
            <div className="grid gap-5 p-5">
              <RangeField label="Контекст Embeddings" value={form.embeddingContextRatio} onChange={(value) => setForm({ ...form, embeddingContextRatio: value })} preview={`${formatPercent(form.embeddingContextRatio)} от ${embeddingLimit.toLocaleString("ru-RU")} = ${embeddingBudget.toLocaleString("ru-RU")} tokens`} />
              <Field label="rag_top_k" hint="Количество лучших chunks после RRF. Верхняя граница не задаётся frontend."><Input type="number" min="1" step="1" value={form.ragTopK} onChange={(event) => setForm({ ...form, ragTopK: Number(event.target.value) })} /></Field>
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
