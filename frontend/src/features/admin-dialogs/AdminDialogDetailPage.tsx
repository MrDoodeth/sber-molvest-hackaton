import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Bot, BrainCircuit, Gauge, Paperclip, Sparkles, Trash2, UserRound } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { adminApi } from "../../api/admin";
import { queryKeys } from "../../api/queryKeys";
import { MessageList } from "../../shared/chat";
import { Badge, Button, Card, ConfirmDialog, ErrorState, PageLoader, useToast } from "../../shared/ui";
import { formatDateTime, formatPercent } from "../../shared/utils";
import CandidateModeration from "./CandidateModeration";

export default function AdminDialogDetailPage() {
  const { dialogId = "" } = useParams();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const toast = useToast();
  const [deleteOpen, setDeleteOpen] = useState(false);
  const journalPath = `/admin/dialogs?${searchParams.toString() || "feedback=helpful"}`;
  const detail = useQuery({
    queryKey: queryKeys.admin.dialog(dialogId),
    queryFn: ({ signal }) => adminApi.dialog(dialogId, signal),
    enabled: Boolean(dialogId),
    refetchInterval: 2500,
    refetchOnMount: "always",
  });
  const activeCandidateId = detail.data?.candidate?.id;
  const deleteDialog = useMutation({
    mutationFn: () => adminApi.deleteDialog(dialogId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.admin.allDialogs() });
      navigate(journalPath, { replace: true });
      toast("Чат удалён", "success");
    },
    onError: (error) => toast(error.message, "error"),
  });

  if (detail.isPending) return <PageLoader label="Загружаем полный аудит" />;
  if (detail.isError) return <ErrorState description={detail.error.message} onRetry={() => void detail.refetch()} />;
  if (!detail.data) return null;
  const { dialog, messages, feedback, audit } = detail.data;
  const canDeleteDialog = dialog.status === "closed" && detail.data.candidate?.status === "rejected";

  return (
    <div className="p-4 sm:p-6 lg:p-8">
      <div className="mx-auto max-w-7xl">
        <Link to={journalPath} className="inline-flex items-center gap-2 text-sm font-bold text-molvest-700 hover:text-molvest-950"><ArrowLeft className="size-4" /> К журналу</Link>
        <header className="mt-5 flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="text-2xl font-black tracking-[-0.02em] text-molvest-950">{dialog.title || `Обращение ${dialog.id.slice(0, 8)}`}</h1>
              <Badge tone={feedback?.verdict === "helpful" ? "success" : feedback?.verdict === "ai_error" ? "danger" : "neutral"}>{feedback?.verdict === "helpful" ? "Полезно" : feedback?.verdict === "ai_error" ? "AI ошибся" : "Ожидает оценки"}</Badge>
            </div>
            <p className="mt-2 text-sm text-stone-500">Закрыто {formatDateTime(dialog.closedAt)} · {audit.resolvedBy === "ai" ? "решено AI" : "решено оператором"}</p>
          </div>
          <div className="flex flex-wrap gap-2">
            {activeCandidateId && <a href="#candidate" className="inline-flex min-h-11 items-center rounded-xl border border-molvest-200 bg-white px-4 text-sm font-bold text-molvest-800 hover:bg-molvest-50"><Sparkles className="mr-2 size-4" /> Карточка решения</a>}
            {canDeleteDialog && <Button variant="danger" onClick={() => setDeleteOpen(true)}><Trash2 className="size-4" /> Удалить чат</Button>}
          </div>
        </header>
        <div className="mt-6 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
           <Card className="p-4"><span className="flex items-center gap-2 text-xs font-bold text-stone-400"><BrainCircuit className="size-4" /> GigaChat model</span><strong className="mt-2 block text-sm text-stone-900">{audit.gigachatModel || "—"}</strong></Card>
           <Card className="p-4"><span className="flex items-center gap-2 text-xs font-bold text-stone-400"><Gauge className="size-4" /> Last confidence</span><strong className="mt-2 block text-sm text-stone-900">{dialog.confidence === undefined ? "—" : formatPercent(dialog.confidence)}</strong></Card>
           <Card className="p-4"><span className="flex items-center gap-2 text-xs font-bold text-stone-400"><Bot className="size-4" /> Escalation threshold</span><strong className="mt-2 block text-sm text-stone-900">{audit.escalationThreshold === undefined ? "Не эскалирован" : formatPercent(audit.escalationThreshold)}</strong></Card>
            <Card className="p-4"><span className="flex items-center gap-2 text-xs font-bold text-stone-400"><Sparkles className="size-4" /> Системный промпт</span><pre className="mt-2 max-h-28 overflow-auto whitespace-pre-wrap break-words text-xs leading-5 text-stone-700">{audit.systemPrompt || "Снимок отсутствует"}</pre></Card>
          </div>
        <div className="mt-6 grid gap-6 xl:grid-cols-[minmax(0,1.35fr)_minmax(22rem,0.65fr)]">
          <Card className="flex h-full flex-col overflow-hidden">
            <div className="flex items-center justify-between border-b border-stone-100 px-5 py-4"><div><p className="text-[10px] font-extrabold uppercase tracking-[0.15em] text-molvest-600">Full conversation</p><h2 className="mt-1 text-lg font-bold text-molvest-950">История диалога</h2></div><div className="flex gap-2"><Badge tone="neutral"><UserRound className="mr-1 size-3" /> {messages.length} сообщений</Badge>{messages.some((message) => message.attachments.length) && <Badge tone="giga"><Paperclip className="mr-1 size-3" /> Вложения</Badge>}</div></div>
            <div className="flex-1 bg-stone-50"><MessageList messages={messages} showConfidence empty={<div className="p-6 text-center text-sm text-stone-500">В сохранённом аудите нет сообщений.</div>} /></div>
          </Card>
           <div id="candidate" className="min-w-0">{activeCandidateId ? <CandidateModeration candidateId={activeCandidateId} dialogId={dialogId} /> : <Card className="p-6"><h2 className="text-lg font-bold text-molvest-950">Карточка решения</h2><p className="mt-2 text-sm leading-6 text-stone-500">Для этого legacy-диалога карточка ещё не восстановлена.</p></Card>}</div>
        </div>
      </div>
      <ConfirmDialog
        open={deleteOpen}
        title="Удалить этот чат без возможности восстановления?"
         description="Отклонённый тикет, сообщения и вложения будут удалены без возможности восстановления."
        confirmLabel="Удалить"
        danger
        pending={deleteDialog.isPending}
        onConfirm={() => deleteDialog.mutate()}
        onCancel={() => setDeleteOpen(false)}
      />
    </div>
  );
}
