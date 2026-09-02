import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, FileCog, RefreshCw, Save, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { knowledgeApi } from "../../api/knowledge";
import { queryKeys } from "../../api/queryKeys";
import type { IndexStatus, SourceType } from "../../api/types";
import { Badge, Button, Card, ConfirmDialog, ErrorState, Field, Input, PageLoader, Switch, useToast } from "../../shared/ui";
import { formatDateTime } from "../../shared/utils";

const sourceLabels: Record<SourceType, string> = { official_1c_docs: "Официальная документация 1С", internal_kb: "Внутренняя база знаний", resolved_case: "Решённый кейс" };
const statusTone: Record<IndexStatus, "neutral" | "warning" | "success" | "danger"> = { uploaded: "neutral", processing: "warning", indexed: "success", failed: "danger" };

export default function DocumentDetailPage() {
  const { documentId = "" } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const toast = useToast();
  const [title, setTitle] = useState("");
  const [oneCVersion, setOneCVersion] = useState("");
  const [tags, setTags] = useState("");
  const [confirm, setConfirm] = useState<"disable" | "reindex" | "delete">();
  const document = useQuery({
    queryKey: queryKeys.kb.document(documentId),
    queryFn: ({ signal }) => knowledgeApi.document(documentId, signal),
    enabled: Boolean(documentId),
    refetchInterval: (query) => query.state.data?.indexStatus === "processing" ? 2500 : false,
  });
  const sections = useQuery({ queryKey: queryKeys.kb.sections(), queryFn: ({ signal }) => knowledgeApi.sections(signal) });
  useEffect(() => {
    if (!document.data) return;
    setTitle(document.data.title);
    setOneCVersion(document.data.oneCVersion ?? "");
    setTags(document.data.tags.join(", "));
  }, [document.data]);
  const dirty = Boolean(document.data && (title !== document.data.title || oneCVersion !== (document.data.oneCVersion ?? "") || tags !== document.data.tags.join(", ")));
  const update = useMutation({
    mutationFn: (patch: Parameters<typeof knowledgeApi.updateDocument>[1]) => knowledgeApi.updateDocument(documentId, patch),
    onSuccess: (updated) => {
      queryClient.setQueryData(queryKeys.kb.document(documentId), updated);
      void queryClient.invalidateQueries({ queryKey: queryKeys.kb.allDocuments() });
      setConfirm(undefined);
      toast("Документ обновлён", "success");
    },
    onError: (error) => toast(error.message, "error"),
  });
  const reindex = useMutation({
    mutationFn: () => knowledgeApi.reindex(documentId),
    onSuccess: (updated) => {
      queryClient.setQueryData(queryKeys.kb.document(documentId), updated);
      void queryClient.invalidateQueries({ queryKey: queryKeys.kb.allDocuments() });
      setConfirm(undefined);
      toast("Переиндексация запущена", "success");
    },
    onError: (error) => toast(error.message, "error"),
  });
  const remove = useMutation({
    mutationFn: () => knowledgeApi.deleteDocument(documentId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.kb.allDocuments() });
      void queryClient.invalidateQueries({ queryKey: queryKeys.kb.sections() });
      navigate(`/admin/knowledge?section=${document.data?.sectionId ?? ""}`, { replace: true });
      toast("Документ и индекс удалены", "success");
    },
    onError: (error) => toast(error.message, "error"),
  });

  if (document.isPending) return <PageLoader label="Загружаем документ" />;
  if (document.isError) return <ErrorState description={document.error.message} onRetry={() => void document.refetch()} />;
  if (!document.data) return null;
  const section = sections.data?.find((item) => item.id === document.data.sectionId);

  return (
    <div className="p-4 sm:p-6 lg:p-8">
      <div className="mx-auto max-w-5xl">
        <Link to={`/admin/knowledge?section=${document.data.sectionId}`} className="inline-flex items-center gap-2 text-sm font-bold text-molvest-700 hover:text-molvest-950"><ArrowLeft className="size-4" /> К базе знаний</Link>
        <header className="mt-5 flex flex-wrap items-start justify-between gap-4">
          <div><p className="text-xs font-extrabold uppercase tracking-[0.17em] text-molvest-600">Document detail</p><h1 className="mt-1 text-3xl font-black tracking-[-0.02em] text-molvest-950">{document.data.title}</h1><p className="mt-2 text-sm text-stone-500">{section?.name || document.data.sectionId} · {sourceLabels[document.data.sourceType]}</p></div>
          <div className="flex flex-wrap items-center gap-3"><Badge tone={statusTone[document.data.indexStatus]}>{document.data.indexStatus}</Badge><div className="flex items-center gap-2 rounded-xl border border-stone-200 bg-white px-3 py-2"><span className="text-xs font-bold text-stone-600">В RAG</span><Switch checked={document.data.isEnabled} label="Участие документа в RAG" disabled={update.isPending} onChange={(next) => next ? update.mutate({ isEnabled: true }) : setConfirm("disable")} /></div></div>
        </header>
        <div className="mt-6 grid gap-5 lg:grid-cols-[minmax(0,1fr)_19rem]">
          <Card className="p-5 sm:p-6">
            <h2 className="text-lg font-bold text-molvest-950">Метаданные</h2>
            <div className="mt-5 grid gap-4">
              <Field label="Название"><Input value={title} onChange={(event) => setTitle(event.target.value)} /></Field>
              <Field label="Версия конфигурации 1С" hint="Это business metadata, а не версия файла."><Input value={oneCVersion} onChange={(event) => setOneCVersion(event.target.value)} placeholder="Например, 3.0" /></Field>
              <Field label="Теги" hint="Через запятую"><Input value={tags} onChange={(event) => setTags(event.target.value)} /></Field>
              <div><Button pending={update.isPending} disabled={!dirty || !title.trim()} onClick={() => update.mutate({ title: title.trim(), oneCVersion: oneCVersion.trim() || undefined, tags: tags.split(",").map((tag) => tag.trim()).filter(Boolean) })}><Save className="size-4" /> Сохранить</Button></div>
            </div>
          </Card>
          <div className="grid content-start gap-5">
            <Card className="p-5"><div className="flex items-center gap-2 text-sm font-bold text-molvest-950"><FileCog className="size-4 text-molvest-600" /> Индексация</div><dl className="mt-4 grid gap-3 text-xs"><div><dt className="text-stone-400">Статус</dt><dd className="mt-1 font-bold text-stone-800">{document.data.indexStatus}</dd></div><div><dt className="text-stone-400">Проиндексирован</dt><dd className="mt-1 font-bold text-stone-800">{formatDateTime(document.data.indexedAt)}</dd></div><div><dt className="text-stone-400">Версия записи</dt><dd className="mt-1 font-bold text-stone-800">{document.data.version ?? "—"}</dd></div></dl>{document.data.indexError && <div className="mt-4 rounded-xl bg-red-50 p-3 text-xs leading-5 text-red-800"><strong>Ошибка:</strong> {document.data.indexError}</div>}</Card>
            <Card className="grid gap-2 p-4"><Button variant="secondary" disabled={document.data.indexStatus === "processing"} onClick={() => setConfirm("reindex")}><RefreshCw className="size-4" /> Переиндексировать</Button><Button variant="ghost" className="text-red-700 hover:bg-red-50" onClick={() => setConfirm("delete")}><Trash2 className="size-4" /> Удалить документ</Button></Card>
          </div>
        </div>
      </div>
      <ConfirmDialog open={confirm === "disable"} title="Выключить документ?" description="Документ останется в разделе и индексе, но временно не будет участвовать в retrieval." confirmLabel="Выключить" pending={update.isPending} onConfirm={() => update.mutate({ isEnabled: false })} onCancel={() => setConfirm(undefined)} />
      <ConfirmDialog open={confirm === "reindex"} title="Запустить переиндексацию?" description="Документ повторно пройдёт parsing, chunking и обновление векторного индекса." confirmLabel="Запустить" pending={reindex.isPending} onConfirm={() => reindex.mutate()} onCancel={() => setConfirm(undefined)} />
      <ConfirmDialog open={confirm === "delete"} title="Удалить документ?" description="Исходный файл, metadata и все связанные chunks будут удалены без восстановления." confirmLabel="Удалить" danger pending={remove.isPending} onConfirm={() => remove.mutate()} onCancel={() => setConfirm(undefined)} />
    </div>
  );
}
