import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BookOpen, FilePlus2, FileText, FolderPlus, MoreHorizontal, Pencil, Trash2, Upload } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { knowledgeApi, type DocumentFilters } from "../../api/knowledge";
import { queryKeys } from "../../api/queryKeys";
import type { IndexStatus, KnowledgeSectionDto, SourceType } from "../../api/types";
import { Badge, Button, Card, ConfirmDialog, EmptyState, ErrorState, Field, IconButton, Input, Modal, PageLoader, Select, Switch, useToast } from "../../shared/ui";
import { cn, formatDateTime } from "../../shared/utils";

const indexTone: Record<IndexStatus, "neutral" | "warning" | "success" | "danger"> = { uploaded: "neutral", processing: "warning", indexed: "success", failed: "danger" };
const sourceLabels: Record<SourceType, string> = { official_1c_docs: "Документация 1С", internal_kb: "Внутренняя БЗ", resolved_case: "Решённый кейс" };
const KB_ACCEPT = ".pdf,.docx,.html,.htm,.md,.markdown";

function validateKbFile(file: File): string | undefined {
  const extension = file.name.toLowerCase().split(".").pop();
  if (!extension || !["pdf", "docx", "html", "htm", "md", "markdown"].includes(extension)) return "Поддерживаются PDF, DOCX, HTML и Markdown.";
  if (file.size > 40 * 1024 * 1024) return "Файл должен быть не больше 40 МБ.";
  return undefined;
}

export default function KnowledgePage() {
  const queryClient = useQueryClient();
  const toast = useToast();
  const [searchParams, setSearchParams] = useSearchParams();
  const [status, setStatus] = useState<IndexStatus | "">("");
  const [createOpen, setCreateOpen] = useState(false);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [renameSection, setRenameSection] = useState<KnowledgeSectionDto>();
  const [sectionAction, setSectionAction] = useState<{ section: KnowledgeSectionDto; kind: "disable" | "delete" }>();
  const [name, setName] = useState("");
  const [file, setFile] = useState<File>();
  const [fileError, setFileError] = useState<string>();
  const [sourceType, setSourceType] = useState<Exclude<SourceType, "resolved_case">>("official_1c_docs");
  const sections = useQuery({ queryKey: queryKeys.kb.sections(), queryFn: ({ signal }) => knowledgeApi.sections(signal) });
  const selectedSectionId = searchParams.get("section") ?? "";
  const filters: DocumentFilters = { sectionId: selectedSectionId || undefined, status };
  const documents = useQuery({
    queryKey: queryKeys.kb.documents(filters),
    queryFn: ({ signal }) => knowledgeApi.documents(filters, signal),
    enabled: Boolean(selectedSectionId),
    refetchInterval: (query) => query.state.data?.items.some((document) => document.indexStatus === "processing") ? 2500 : false,
  });

  useEffect(() => {
    if (!selectedSectionId && sections.data?.[0]) setSearchParams({ section: sections.data[0].id }, { replace: true });
  }, [sections.data, selectedSectionId, setSearchParams]);

  const create = useMutation({
    mutationFn: () => knowledgeApi.createSection(name.trim()),
    onSuccess: (section) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.kb.sections() });
      setSearchParams({ section: section.id });
      setCreateOpen(false);
      setName("");
      toast("Раздел создан", "success");
    },
    onError: (error) => toast(error.message, "error"),
  });
  const updateSection = useMutation({
    mutationFn: ({ id, patch }: { id: string; patch: { name?: string; isEnabled?: boolean } }) => knowledgeApi.updateSection(id, patch),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.kb.sections() });
      void queryClient.invalidateQueries({ queryKey: queryKeys.kb.allDocuments() });
      setRenameSection(undefined);
      setSectionAction(undefined);
      setName("");
      toast("Раздел обновлён", "success");
    },
    onError: (error) => toast(error.message, "error"),
  });
  const deleteSection = useMutation({
    mutationFn: (id: string) => knowledgeApi.deleteSection(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.kb.sections() });
      void queryClient.invalidateQueries({ queryKey: queryKeys.kb.allDocuments() });
      setSearchParams({});
      setSectionAction(undefined);
      toast("Раздел удалён", "success");
    },
    onError: (error) => toast(error.message, "error"),
  });
  const toggleDocument = useMutation({
    mutationFn: ({ id, isEnabled }: { id: string; isEnabled: boolean }) => knowledgeApi.updateDocument(id, { isEnabled }),
    onSuccess: (document) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.kb.documents(filters) });
      void queryClient.invalidateQueries({ queryKey: queryKeys.kb.document(document.id) });
      toast(document.isEnabled ? "Документ включён" : "Документ исключён из RAG", "success");
    },
    onError: (error) => toast(error.message, "error"),
  });
  const upload = useMutation({
    mutationFn: () => knowledgeApi.uploadDocument({ file: file!, sectionId: selectedSectionId, sourceType }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.kb.documents(filters) });
      void queryClient.invalidateQueries({ queryKey: queryKeys.kb.sections() });
      setUploadOpen(false);
      setFile(undefined);
      setFileError(undefined);
      toast("Документ загружен и передан на индексацию", "success");
    },
    onError: (error) => toast(error.message, "error"),
  });
  const selectedSection = sections.data?.find((section) => section.id === selectedSectionId);

  return (
    <div className="p-4 sm:p-6 lg:p-8">
      <div className="mx-auto max-w-7xl">
        <header>
          <p className="text-xs font-extrabold uppercase tracking-[0.18em] text-molvest-600">RAG library</p>
          <h1 className="mt-1 text-3xl font-black tracking-[-0.025em] text-molvest-950">База знаний</h1>
          <p className="mt-2 text-sm text-stone-500">Разделы управляют доступностью документов как master switch.</p>
        </header>
        <div className="mt-6 grid gap-5 lg:grid-cols-[18rem_minmax(0,1fr)]">
          <Card className="min-h-72 overflow-hidden">
            <div className="flex items-center justify-between border-b border-stone-100 px-4 py-3.5"><h2 className="text-sm font-bold text-molvest-950">Разделы</h2><IconButton type="button" aria-label="Создать раздел" onClick={() => { setName(""); setCreateOpen(true); }}><FolderPlus className="size-4" /></IconButton></div>
            {sections.isPending && <PageLoader label="Загружаем разделы" />}
            {sections.isError && <ErrorState description={sections.error.message} onRetry={() => void sections.refetch()} />}
            {sections.isSuccess && sections.data.length === 0 && <EmptyState icon={<BookOpen className="size-8" />} title="Разделов нет" description="Создайте первый раздел для загрузки документов." action={<Button size="sm" onClick={() => setCreateOpen(true)}>Создать</Button>} />}
            <div className="grid gap-1 p-2">
              {sections.data?.map((section) => (
                <div key={section.id} className={cn("group rounded-2xl border p-3 transition", selectedSectionId === section.id ? "border-molvest-200 bg-molvest-50" : "border-transparent hover:bg-stone-50")}>
                  <div className="flex items-start justify-between gap-2">
                    <button type="button" onClick={() => setSearchParams({ section: section.id })} className="min-w-0 flex-1 text-left focus-visible:outline-2 focus-visible:outline-molvest-500">
                      <p className="truncate text-sm font-bold text-stone-900">{section.name}</p>
                      <p className="mt-1 text-[11px] text-stone-400">{section.documentCount ?? 0} документов</p>
                    </button>
                    <Switch checked={section.isEnabled} label={`${section.isEnabled ? "Выключить" : "Включить"} раздел ${section.name}`} disabled={updateSection.isPending} onChange={(next) => next ? updateSection.mutate({ id: section.id, patch: { isEnabled: true } }) : setSectionAction({ section, kind: "disable" })} />
                  </div>
                  <div className="mt-2 flex items-center gap-1 opacity-100 lg:opacity-0 lg:transition lg:group-hover:opacity-100">
                    <IconButton type="button" className="size-8 text-stone-400 hover:bg-white hover:text-molvest-700" onClick={() => { setName(section.name); setRenameSection(section); }} aria-label={`Переименовать ${section.name}`}><Pencil className="size-3.5" /></IconButton>
                    <IconButton type="button" className="size-8 text-stone-400 hover:bg-red-50 hover:text-red-700" disabled={section.isSystem} onClick={() => setSectionAction({ section, kind: "delete" })} aria-label={`Удалить ${section.name}`}><Trash2 className="size-3.5" /></IconButton>
                    {section.isSystem && <Badge tone="neutral">Системный</Badge>}
                  </div>
                </div>
              ))}
            </div>
          </Card>
          <Card className="min-w-0 overflow-hidden">
            <div className="flex flex-wrap items-end justify-between gap-3 border-b border-stone-100 p-4 sm:p-5">
              <div><p className="text-[10px] font-extrabold uppercase tracking-[0.15em] text-molvest-600">Documents</p><h2 className="mt-1 text-xl font-bold text-molvest-950">{selectedSection?.name || "Выберите раздел"}</h2>{selectedSection && !selectedSection.isEnabled && <p className="mt-1 text-xs font-semibold text-amber-800">Master switch выключен: документы временно не участвуют в RAG.</p>}</div>
              <div className="flex gap-2"><Select aria-label="Статус индексации" className="w-auto" value={status} onChange={(event) => setStatus(event.target.value as IndexStatus | "")}><option value="">Все статусы</option><option value="uploaded">uploaded</option><option value="processing">processing</option><option value="indexed">indexed</option><option value="failed">failed</option></Select><Button disabled={!selectedSectionId} onClick={() => setUploadOpen(true)}><Upload className="size-4" /> Загрузить</Button></div>
            </div>
            {!selectedSectionId && <EmptyState icon={<MoreHorizontal className="size-8" />} title="Раздел не выбран" description="Выберите раздел слева, чтобы увидеть его документы." />}
            {selectedSectionId && documents.isPending && <PageLoader label="Загружаем документы" />}
            {documents.isError && <ErrorState description={documents.error.message} onRetry={() => void documents.refetch()} />}
            {documents.isSuccess && documents.data.items.length === 0 && <EmptyState icon={<FilePlus2 className="size-8" />} title="Документов нет" description="Загрузите PDF, DOCX, HTML или Markdown. Индексация запустится автоматически." action={<Button onClick={() => setUploadOpen(true)}>Загрузить документ</Button>} />}
            {documents.data && documents.data.items.length > 0 && (
              <div className="overflow-x-auto">
                <table className="w-full min-w-[48rem] text-left text-sm">
                  <thead className="bg-stone-50 text-[10px] font-extrabold uppercase tracking-[0.12em] text-stone-500"><tr><th className="px-5 py-3">Документ</th><th className="px-4 py-3">Источник</th><th className="px-4 py-3">Индекс</th><th className="px-4 py-3">Включён</th><th className="px-4 py-3">Обновлён</th><th className="px-5 py-3" /></tr></thead>
                  <tbody className="divide-y divide-stone-100">{documents.data.items.map((document) => <tr key={document.id} className="hover:bg-molvest-50/40"><td className="px-5 py-4"><div className="flex items-center gap-3"><span className="flex size-9 items-center justify-center rounded-xl bg-stone-100 text-stone-500"><FileText className="size-4" /></span><div><p className="font-bold text-stone-900">{document.title}</p><p className="mt-0.5 text-xs text-stone-400">{document.fileName || document.id.slice(0, 8)}</p></div></div></td><td className="px-4 py-4 text-xs text-stone-600">{sourceLabels[document.sourceType]}</td><td className="px-4 py-4"><Badge tone={indexTone[document.indexStatus]}>{document.indexStatus}</Badge></td><td className="px-4 py-4"><Switch checked={document.isEnabled} label={`${document.isEnabled ? "Выключить" : "Включить"} документ ${document.title}`} disabled={toggleDocument.isPending} onChange={(next) => toggleDocument.mutate({ id: document.id, isEnabled: next })} /></td><td className="px-4 py-4 text-xs text-stone-500">{formatDateTime(document.indexedAt || document.updatedAt)}</td><td className="px-5 py-4 text-right"><Link to={`/admin/knowledge/documents/${document.id}`} className="font-bold text-molvest-700 hover:text-molvest-950">Открыть</Link></td></tr>)}</tbody>
                </table>
              </div>
            )}
          </Card>
        </div>
      </div>
      <Modal open={createOpen} title="Новый раздел" description="Раздел станет отдельной логической областью базы знаний." onClose={() => setCreateOpen(false)}><form className="grid gap-4" onSubmit={(event) => { event.preventDefault(); if (name.trim()) create.mutate(); }}><Field label="Название"><Input autoFocus value={name} onChange={(event) => setName(event.target.value)} placeholder="Например, Документация 1С" /></Field><div className="flex justify-end gap-2"><Button type="button" variant="secondary" onClick={() => setCreateOpen(false)}>Отмена</Button><Button type="submit" pending={create.isPending} disabled={!name.trim()}>Создать</Button></div></form></Modal>
      <Modal open={Boolean(renameSection)} title="Переименовать раздел" onClose={() => setRenameSection(undefined)}><form className="grid gap-4" onSubmit={(event) => { event.preventDefault(); if (renameSection && name.trim()) updateSection.mutate({ id: renameSection.id, patch: { name: name.trim() } }); }}><Field label="Название"><Input autoFocus value={name} onChange={(event) => setName(event.target.value)} /></Field><div className="flex justify-end gap-2"><Button type="button" variant="secondary" onClick={() => setRenameSection(undefined)}>Отмена</Button><Button type="submit" pending={updateSection.isPending} disabled={!name.trim()}>Сохранить</Button></div></form></Modal>
      <Modal open={uploadOpen} title="Загрузить документ" description="Permanent KB: файл пройдёт Docling, chunking, BGE-M3 и индексацию в Qdrant." onClose={() => setUploadOpen(false)}>
        <form className="grid gap-4" onSubmit={(event) => { event.preventDefault(); if (file && selectedSectionId) upload.mutate(); }}>
          <Field label="Файл" hint="PDF, DOCX, HTML или Markdown · до 40 МБ" error={fileError}><Input type="file" accept={KB_ACCEPT} onChange={(event) => { const selected = event.target.files?.[0]; setFile(selected); setFileError(selected ? validateKbFile(selected) : undefined); }} /></Field>
          <Field label="Раздел"><Select value={selectedSectionId} onChange={(event) => setSearchParams({ section: event.target.value })}>{sections.data?.map((section) => <option key={section.id} value={section.id}>{section.name}</option>)}</Select></Field>
          <Field label="Тип источника"><Select value={sourceType} onChange={(event) => setSourceType(event.target.value as Exclude<SourceType, "resolved_case">)}><option value="official_1c_docs">Официальная документация 1С</option><option value="internal_kb">Внутренняя база знаний</option></Select></Field>
          <div className="flex justify-end gap-2"><Button type="button" variant="secondary" onClick={() => setUploadOpen(false)}>Отмена</Button><Button type="submit" pending={upload.isPending} disabled={!file || Boolean(fileError) || !selectedSectionId}><Upload className="size-4" /> Загрузить</Button></div>
        </form>
      </Modal>
      <ConfirmDialog open={sectionAction?.kind === "disable"} title="Выключить раздел целиком?" description="Все документы раздела временно перестанут участвовать в RAG. Их индивидуальные настройки сохранятся." confirmLabel="Выключить" pending={updateSection.isPending} onConfirm={() => sectionAction && updateSection.mutate({ id: sectionAction.section.id, patch: { isEnabled: false } })} onCancel={() => setSectionAction(undefined)} />
      <ConfirmDialog open={sectionAction?.kind === "delete"} title="Удалить раздел?" description="Раздел, документы и поисковый индекс будут удалены. Действие нельзя отменить." confirmLabel="Удалить" danger pending={deleteSection.isPending} onConfirm={() => sectionAction && deleteSection.mutate(sectionAction.section.id)} onCancel={() => setSectionAction(undefined)} />
    </div>
  );
}
