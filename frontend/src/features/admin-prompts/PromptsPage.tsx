import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bot, FileText, Save, ShieldCheck } from "lucide-react";
import { useEffect, useState } from "react";
import { useBeforeUnload, useBlocker } from "react-router-dom";
import { queryKeys } from "../../api/queryKeys";
import { settingsApi } from "../../api/settings";
import type { PromptType, SystemPromptDto } from "../../api/types";
import { Badge, Button, Card, ConfirmDialog, EmptyState, ErrorState, PageLoader, Tabs, Textarea, useToast } from "../../shared/ui";
import { formatDateTime } from "../../shared/utils";

export default function PromptsPage() {
  const queryClient = useQueryClient();
  const toast = useToast();
  const [type, setType] = useState<PromptType>("user_support");
  const [content, setContent] = useState("");
  const [pendingType, setPendingType] = useState<PromptType>();
  const prompts = useQuery({ queryKey: queryKeys.prompts(), queryFn: ({ signal }) => settingsApi.prompts(signal) });
  const prompt = prompts.data?.find((item) => item.type === type);
  const dirty = Boolean(prompt && content !== prompt.content);
  const blocker = useBlocker(({ currentLocation, nextLocation }) => dirty && currentLocation.pathname !== nextLocation.pathname);

  useEffect(() => {
    if (prompt) setContent(prompt.content);
  }, [prompt]);
  useBeforeUnload((event) => {
    if (!dirty) return;
    event.preventDefault();
    event.returnValue = "";
  });
  const save = useMutation({
    mutationFn: () => settingsApi.savePrompt(type, content),
    onSuccess: (updated) => {
      queryClient.setQueryData<SystemPromptDto[]>(queryKeys.prompts(), (current) => current?.map((item) => item.type === updated.type ? updated : item) ?? [updated]);
      setContent(updated.content);
      toast(`System Prompt v${updated.version} сохранён`, "success");
    },
    onError: (error) => toast(error.message, "error"),
  });
  const requestTab = (next: PromptType) => {
    if (next === type) return;
    if (dirty) setPendingType(next);
    else setType(next);
  };

  return (
    <div className="p-4 sm:p-6 lg:p-8">
      <div className="mx-auto max-w-6xl">
        <header className="flex flex-wrap items-end justify-between gap-4">
          <div><p className="text-xs font-extrabold uppercase tracking-[0.18em] text-molvest-600">Runtime instructions</p><h1 className="mt-1 text-3xl font-black tracking-[-0.025em] text-molvest-950">System Prompts</h1><p className="mt-2 text-sm text-stone-500">Три независимых промпта применяются к следующим вызовам GigaChat без перезапуска.</p></div>
          {dirty && <Badge tone="warning">Есть несохранённые изменения</Badge>}
        </header>
        <Card className="mt-6 overflow-hidden">
          <div className="border-b border-stone-100 p-4 sm:p-5"><Tabs value={type} onChange={requestTab} ariaLabel="Тип System Prompt" items={[{ value: "user_support", label: "User Support" }, { value: "operator_gigachat", label: "Operator Template" }, { value: "knowledge_card", label: "Knowledge Card" }]} /></div>
          {prompts.isPending && <PageLoader label="Загружаем System Prompts" />}
          {prompts.isError && <ErrorState description={prompts.error.message} onRetry={() => void prompts.refetch()} />}
          {prompts.isSuccess && !prompt && <EmptyState title="Prompt не найден" description="Backend не вернул активную версию для выбранного типа." />}
          {prompt && (
            <div className="grid lg:grid-cols-[minmax(0,1fr)_17rem]">
              <div className="p-4 sm:p-6">
                <label className="text-sm font-bold text-molvest-950" htmlFor="prompt-content">Инструкции модели</label>
                <Textarea id="prompt-content" rows={24} className="mt-2 min-h-[32rem] font-mono text-[13px] leading-6" value={content} onChange={(event) => setContent(event.target.value)} spellCheck={false} />
                <div className="mt-4 flex flex-wrap items-center justify-between gap-3"><span className="text-xs text-stone-400">{content.length.toLocaleString("ru-RU")} символов</span><Button pending={save.isPending} disabled={!dirty || !content.trim()} onClick={() => save.mutate()}><Save className="size-4" /> Сохранить новую версию</Button></div>
              </div>
              <aside className="border-t border-stone-100 bg-stone-50 p-5 lg:border-l lg:border-t-0">
                <div className="flex size-10 items-center justify-center rounded-2xl bg-indigo-100 text-indigo-700">{type === "user_support" ? <Bot className="size-5" /> : type === "operator_gigachat" ? <ShieldCheck className="size-5" /> : <FileText className="size-5" />}</div>
                <h2 className="mt-4 text-sm font-bold text-stone-900">Активная версия</h2>
                <strong className="mt-1 block text-3xl font-black text-molvest-900">v{prompt.version}</strong>
                <dl className="mt-5 grid gap-4 text-xs"><div><dt className="text-stone-400">Обновлён</dt><dd className="mt-1 font-bold text-stone-700">{formatDateTime(prompt.updatedAt)}</dd></div><div><dt className="text-stone-400">Автор</dt><dd className="mt-1 font-bold text-stone-700">{prompt.updatedBy.displayName}</dd></div><div><dt className="text-stone-400">Режим</dt><dd className="mt-1 font-bold text-stone-700">{type}</dd></div></dl>
                <p className="mt-6 rounded-xl bg-white p-3 text-[11px] leading-5 text-stone-500">Новая версия не меняет уже запущенный stream и начнёт действовать со следующего GigaChat-call.</p>
              </aside>
            </div>
          )}
        </Card>
      </div>
      <ConfirmDialog open={Boolean(pendingType)} title="Переключить вкладку без сохранения?" description="Изменения текущего System Prompt будут потеряны." confirmLabel="Не сохранять" danger onConfirm={() => { if (pendingType) setType(pendingType); setPendingType(undefined); }} onCancel={() => setPendingType(undefined)} />
      <ConfirmDialog open={blocker.state === "blocked"} title="Уйти со страницы без сохранения?" description="Несохранённые изменения System Prompt будут потеряны." confirmLabel="Уйти" danger onConfirm={() => blocker.proceed?.()} onCancel={() => blocker.reset?.()} />
    </div>
  );
}
