import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bot, Save, ShieldCheck, Sparkles } from "lucide-react";
import { useEffect, useState } from "react";
import { useBeforeUnload, useBlocker } from "react-router-dom";
import { queryKeys } from "../../api/queryKeys";
import { settingsApi } from "../../api/settings";
import type { PromptType, SystemPromptDto } from "../../api/types";
import { Badge, Button, Card, ConfirmDialog, EmptyState, ErrorState, PageLoader, Tabs, Textarea, useToast } from "../../shared/ui";

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
       toast("System Prompt сохранён", "success");
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
          <div className="border-b border-[#dbe3f0] p-4 sm:p-5"><Tabs value={type} onChange={requestTab} ariaLabel="Тип System Prompt" items={[{ value: "user_support", label: "User Support" }, { value: "operator_gigachat", label: "Operator Template" }, { value: "knowledge_card", label: "Помощник карточки решения" }]} /></div>
          {prompts.isPending && <PageLoader label="Загружаем System Prompts" />}
          {prompts.isError && <ErrorState description={prompts.error.message} onRetry={() => void prompts.refetch()} />}
           {prompts.isSuccess && !prompt && <EmptyState title="Prompt не найден" description="Backend не вернул текст для выбранного типа." />}
          {prompt && (
             <div className="p-4 sm:p-6">
                <div className="flex items-center gap-3"><div className="flex size-10 items-center justify-center rounded-xl bg-[#fbc4fb]/55 text-[#a13cc9]">{type === "user_support" ? <Bot className="size-5" /> : type === "operator_gigachat" ? <ShieldCheck className="size-5" /> : <Sparkles className="size-5" />}</div><div><p className="text-[10px] font-extrabold uppercase tracking-[0.15em] text-molvest-700">{type === "knowledge_card" ? "Помощник карточки решения" : type}</p><p className="text-sm font-bold text-black">Инструкции модели</p></div></div>
               <Textarea id="prompt-content" rows={24} className="mt-5 min-h-[32rem] font-mono text-[13px] leading-6" value={content} onChange={(event) => setContent(event.target.value)} spellCheck={false} />
               <div className="mt-4 flex flex-wrap items-center justify-between gap-3"><span className="text-xs text-stone-400">{content.length.toLocaleString("ru-RU")} символов · изменения применяются к следующим вызовам</span><Button pending={save.isPending} disabled={!dirty || !content.trim()} onClick={() => save.mutate()}><Save className="size-4" /> Сохранить</Button></div>
             </div>
          )}
        </Card>
      </div>
      <ConfirmDialog open={Boolean(pendingType)} title="Переключить вкладку без сохранения?" description="Изменения текущего System Prompt будут потеряны." confirmLabel="Не сохранять" danger onConfirm={() => { if (pendingType) setType(pendingType); setPendingType(undefined); }} onCancel={() => setPendingType(undefined)} />
      <ConfirmDialog open={blocker.state === "blocked"} title="Уйти со страницы без сохранения?" description="Несохранённые изменения System Prompt будут потеряны." confirmLabel="Уйти" danger onConfirm={() => blocker.proceed?.()} onCancel={() => blocker.reset?.()} />
    </div>
  );
}
