import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BookCheck, FileSearch, Sparkles, XCircle } from "lucide-react";
import { useEffect, useState } from "react";
import { adminApi } from "../../api/admin";
import { knowledgeApi } from "../../api/knowledge";
import { queryKeys } from "../../api/queryKeys";
import type { CaseCardDto } from "../../api/types";
import { Badge, Button, Card, ConfirmDialog, ErrorState, Field, PageLoader, Textarea, useToast } from "../../shared/ui";

const fields: Array<{ key: keyof CaseCardDto; label: string; rows: number }> = [
  { key: "title", label: "Название кейса", rows: 2 },
  { key: "problem", label: "Проблема", rows: 3 },
  { key: "result", label: "Результат", rows: 2 },
];

export default function CandidateModeration({ candidateId, dialogId }: { candidateId: string; dialogId: string }) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const [card, setCard] = useState<CaseCardDto>();
  const [rejectOpen, setRejectOpen] = useState(false);
  const candidate = useQuery({ queryKey: queryKeys.admin.candidate(candidateId), queryFn: ({ signal }) => adminApi.candidate(candidateId, signal) });
  const resultingDocument = useQuery({
    queryKey: queryKeys.kb.document(candidate.data?.resultingDocumentId ?? ""),
    queryFn: ({ signal }) => knowledgeApi.document(candidate.data!.resultingDocumentId!, signal),
    enabled: Boolean(candidate.data?.resultingDocumentId),
    refetchInterval: (query) => query.state.data?.indexStatus === "processing" ? 2500 : false,
  });

  useEffect(() => {
    if (!candidate.data) return;
    setCard(candidate.data.generatedCard);
  }, [candidate.data]);
  const generate = useMutation({
    mutationFn: () => adminApi.generateCandidateCard(candidateId),
    onSuccess: (updated) => {
      queryClient.setQueryData(queryKeys.admin.candidate(candidateId), updated);
      setCard(updated.generatedCard);
      toast("Карточка заполнена через GigaChat", "success");
    },
    onError: (error) => toast(error.message, "error"),
  });
  const approve = useMutation({
    mutationFn: () => adminApi.approveCandidate(candidateId, card!),
    onSuccess: (updated) => {
      queryClient.setQueryData(queryKeys.admin.candidate(candidateId), updated);
      void queryClient.invalidateQueries({ queryKey: queryKeys.admin.dialog(dialogId) });
      void queryClient.invalidateQueries({ queryKey: queryKeys.admin.allDialogs() });
      void queryClient.invalidateQueries({ queryKey: queryKeys.kb.allDocuments() });
      void queryClient.invalidateQueries({ queryKey: queryKeys.kb.sections() });
       toast("Карточка одобрена и передана на индексацию", "success");
    },
    onError: (error) => toast(error.message, "error"),
  });
  const reject = useMutation({
    mutationFn: () => adminApi.rejectCandidate(candidateId),
    onSuccess: (updated) => {
      queryClient.setQueryData(queryKeys.admin.candidate(candidateId), updated);
      void queryClient.invalidateQueries({ queryKey: queryKeys.admin.dialog(dialogId) });
      void queryClient.invalidateQueries({ queryKey: queryKeys.admin.allDialogs() });
      setRejectOpen(false);
      toast("Кандидат отклонён", "success");
    },
    onError: (error) => toast(error.message, "error"),
  });

  if (candidate.isPending) return <PageLoader label="Загружаем карточку кандидата" />;
  if (candidate.isError) return <ErrorState description={candidate.error.message} onRetry={() => void candidate.refetch()} />;
  if (!card) return null;
  const cardComplete = fields.every(({ key }) => card[key].trim().length > 0);

  return (
    <Card className="overflow-hidden" >
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-stone-100 bg-stone-50 px-5 py-4">
        <div><p className="text-[10px] font-extrabold uppercase tracking-[0.16em] text-molvest-600">Knowledge candidate</p><h2 className="mt-1 text-lg font-bold text-molvest-950">Карточка решения</h2></div>
        {candidate.data.status === "approved" && <Badge tone="success">Опубликовано</Badge>}
        {candidate.data.status === "rejected" && <Badge tone="danger">Отклонено</Badge>}
      </div>
      <div className="grid gap-4 p-5">
        {fields.map((field) => (
          <Field key={field.key} label={field.label}>
            <Textarea rows={field.rows} disabled={candidate.data.status !== "pending"} value={card[field.key]} onChange={(event) => setCard({ ...card, [field.key]: event.target.value })} />
            {candidate.data.status === "pending" && !card[field.key].trim() && <span className="text-xs font-normal text-red-700">Поле обязательно</span>}
          </Field>
        ))}
        {candidate.data.status === "pending" && (
          <div className="rounded-2xl border border-molvest-100 bg-molvest-50 p-4">
            <p className="text-sm leading-6 text-molvest-900">Заполните поля вручную или поручите это GigaChat. Перед публикацией карточка всегда сохраняется в системный раздел «Журнал обращений».</p>
            <div className="mt-4 flex flex-wrap gap-2">
              <Button variant="giga" pending={generate.isPending} disabled={approve.isPending} onClick={() => generate.mutate()}><Sparkles className="size-4" /> Заполнить через GigaChat</Button>
              <Button pending={approve.isPending} disabled={generate.isPending || !cardComplete} onClick={() => approve.mutate()}><BookCheck className="size-4" /> Approve</Button>
              <Button variant="ghost" disabled={approve.isPending || generate.isPending} onClick={() => setRejectOpen(true)}><XCircle className="size-4" /> Reject</Button>
            </div>
          </div>
        )}
        {candidate.data.status === "approved" && (
          <div className="rounded-2xl border border-emerald-100 bg-emerald-50 p-4">
            <div className="flex items-center gap-2 font-bold text-emerald-900"><FileSearch className="size-4" /> Индексация документа</div>
            {resultingDocument.isPending && <p className="mt-2 text-sm text-emerald-800">Проверяем статус…</p>}
            {resultingDocument.isError && <p className="mt-2 text-sm text-red-700">{resultingDocument.error.message}</p>}
            {resultingDocument.data && <div className="mt-2 flex flex-wrap items-center gap-2"><Badge tone={resultingDocument.data.indexStatus === "indexed" ? "success" : resultingDocument.data.indexStatus === "failed" ? "danger" : "warning"}>{resultingDocument.data.indexStatus}</Badge><span className="text-xs text-emerald-800">{resultingDocument.data.title}</span>{resultingDocument.data.indexError && <p className="w-full text-xs text-red-700">{resultingDocument.data.indexError}</p>}</div>}
          </div>
        )}
      </div>
      <ConfirmDialog open={rejectOpen} title="Отклонить кандидата?" description="Карточка останется в журнале, но не попадёт в production RAG." confirmLabel="Отклонить" danger pending={reject.isPending} onConfirm={() => reject.mutate()} onCancel={() => setRejectOpen(false)} />
    </Card>
  );
}
