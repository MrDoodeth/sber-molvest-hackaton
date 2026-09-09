import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  BookOpen,
  FilePlus2,
  FileText,
  FolderPlus,
  MoreHorizontal,
  Pencil,
  RefreshCw,
  Trash2,
  Upload,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { knowledgeApi, type DocumentFilters } from "../../api/knowledge";
import { queryKeys } from "../../api/queryKeys";
import type {
  IndexStatus,
  KnowledgeDocumentDto,
  KnowledgeSectionDto,
} from "../../api/types";
import {
  Badge,
  Button,
  Card,
  ConfirmDialog,
  EmptyState,
  ErrorState,
  Field,
  IconButton,
  Input,
  Modal,
  PageLoader,
  Switch,
  useToast,
} from "../../shared/ui";
import { cn, formatRelativeDate, truncateTitle, withDemoRole } from "../../shared/utils";

const indexTone: Record<
  IndexStatus,
  "neutral" | "warning" | "success" | "danger"
> = {
  uploaded: "neutral",
  processing: "warning",
  indexed: "success",
  failed: "danger",
};
const KB_ACCEPT = ".pdf,.docx,.html,.htm,.md,.markdown";

function validateKbFile(file: File): string | undefined {
  const extension = file.name.toLowerCase().split(".").pop();
  if (
    !extension ||
    !["pdf", "docx", "html", "htm", "md", "markdown"].includes(extension)
  )
    return "Поддерживаются PDF, DOCX, HTML и Markdown.";
  if (file.size > 40 * 1024 * 1024) return "Файл должен быть не больше 40 МБ.";
  return undefined;
}

export default function KnowledgePage() {
  const queryClient = useQueryClient();
  const toast = useToast();
  const [searchParams, setSearchParams] = useSearchParams();
  const [createOpen, setCreateOpen] = useState(false);
  const [renameSection, setRenameSection] = useState<KnowledgeSectionDto>();
  const [sectionAction, setSectionAction] = useState<{
    section: KnowledgeSectionDto;
    kind: "disable" | "delete";
  }>();
  const [documentToDelete, setDocumentToDelete] =
    useState<KnowledgeDocumentDto>();
  const [name, setName] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);
  const sections = useQuery({
    queryKey: queryKeys.kb.sections(),
    queryFn: ({ signal }) => knowledgeApi.sections(signal),
  });
  const selectedSectionId = searchParams.get("section") ?? "";
  const filters: DocumentFilters = {
    sectionId: selectedSectionId || undefined,
  };
  const documents = useQuery({
    queryKey: queryKeys.kb.documents(filters),
    queryFn: ({ signal }) => knowledgeApi.documents(filters, signal),
    enabled: Boolean(selectedSectionId),
    refetchInterval: (query) =>
      query.state.data?.items.some(
        (document) => document.indexStatus === "processing",
      )
        ? 2500
        : false,
  });

  useEffect(() => {
    if (!selectedSectionId && sections.data?.[0])
      setSearchParams({ section: sections.data[0].id }, { replace: true });
  }, [sections.data, selectedSectionId, setSearchParams]);
  const selectedSection = sections.data?.find(
    (section) => section.id === selectedSectionId,
  );
  const isCaseJournal =
    selectedSection?.isSystem && selectedSection.name === "Журнал обращений";
  const canUpload = Boolean(selectedSectionId) && !isCaseJournal;

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
    mutationFn: ({
      id,
      patch,
    }: {
      id: string;
      patch: { name?: string; isEnabled?: boolean };
    }) => knowledgeApi.updateSection(id, patch),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.kb.sections() });
      void queryClient.invalidateQueries({
        queryKey: queryKeys.kb.allDocuments(),
      });
      setRenameSection(undefined);
      setSectionAction(undefined);
      setName("");
    },
    onError: (error) => toast(error.message, "error"),
  });
  const deleteSection = useMutation({
    mutationFn: (id: string) => knowledgeApi.deleteSection(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.kb.sections() });
      void queryClient.invalidateQueries({
        queryKey: queryKeys.kb.allDocuments(),
      });
      setSearchParams({});
      setSectionAction(undefined);
      toast("Раздел удалён", "success");
    },
    onError: (error) => toast(error.message, "error"),
  });
  const toggleDocument = useMutation({
    mutationFn: ({ id, isEnabled }: { id: string; isEnabled: boolean }) =>
      knowledgeApi.updateDocument(id, { isEnabled }),
    onSuccess: (document) => {
      void queryClient.invalidateQueries({
        queryKey: queryKeys.kb.documents(filters),
      });
      void queryClient.invalidateQueries({
        queryKey: queryKeys.kb.document(document.id),
      });
      toast(
        document.isEnabled ? "Документ включён" : "Документ исключён из RAG",
        "success",
      );
    },
    onError: (error) => toast(error.message, "error"),
  });
  const upload = useMutation({
    mutationFn: (input: { file: File; sectionId: string }) =>
      knowledgeApi.uploadDocument(input),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: queryKeys.kb.documents(filters),
      });
      void queryClient.invalidateQueries({ queryKey: queryKeys.kb.sections() });
      if (fileInputRef.current) fileInputRef.current.value = "";
      toast("Документ загружен и передан на индексацию", "success");
    },
    onError: (error) => {
      if (fileInputRef.current) fileInputRef.current.value = "";
      toast(error.message, "error");
    },
  });
  const reindex = useMutation({
    mutationFn: (id: string) => knowledgeApi.reindex(id),
    onSuccess: (document) => {
      void queryClient.invalidateQueries({
        queryKey: queryKeys.kb.documents(filters),
      });
      queryClient.setQueryData(queryKeys.kb.document(document.id), document);
      toast("Переиндексация запущена", "success");
    },
    onError: (error) => toast(error.message, "error"),
  });
  const deleteDocument = useMutation({
    mutationFn: (id: string) => knowledgeApi.deleteDocument(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: queryKeys.kb.documents(filters),
      });
      void queryClient.invalidateQueries({
        queryKey: queryKeys.kb.allDocuments(),
      });
      void queryClient.invalidateQueries({ queryKey: queryKeys.kb.sections() });
      setDocumentToDelete(undefined);
      toast("Документ удалён из базы знаний", "success");
    },
    onError: (error) => toast(error.message, "error"),
  });
  const chooseFile = () => {
    if (canUpload) fileInputRef.current?.click();
  };
  const handleFileChange = (selectedFile: File | undefined) => {
    if (!selectedFile || !selectedSectionId) return;
    const error = validateKbFile(selectedFile);
    if (error) {
      toast(error, "error");
      if (fileInputRef.current) fileInputRef.current.value = "";
      return;
    }
    upload.mutate({ file: selectedFile, sectionId: selectedSectionId });
  };

  return (
    <div className="p-4 sm:p-6 lg:p-8">
      <div className="mx-auto max-w-7xl">
        <header>
          <p className="text-xs font-extrabold uppercase tracking-[0.18em] text-molvest-600">
            RAG library
          </p>
          <h1 className="mt-1 text-3xl font-black tracking-[-0.025em] text-molvest-950">
            База знаний
          </h1>
          <p className="mt-2 text-sm text-stone-500">
            Разделы управляют доступностью документов.
          </p>
        </header>
        <div className="mt-6 grid gap-5 lg:grid-cols-[18rem_minmax(0,1fr)]">
          <Card className="min-h-72 overflow-hidden">
            <div className="flex items-center justify-between border-b border-stone-100 px-4 py-3.5">
              <h2 className="text-sm font-bold text-molvest-950">Разделы</h2>
              <IconButton
                type="button"
                aria-label="Создать раздел"
                onClick={() => {
                  setName("");
                  setCreateOpen(true);
                }}
              >
                <FolderPlus className="size-4" />
              </IconButton>
            </div>
            {sections.isPending && <PageLoader label="Загружаем разделы" />}
            {sections.isError && (
              <ErrorState
                description={sections.error.message}
                onRetry={() => void sections.refetch()}
              />
            )}
            {sections.isSuccess && sections.data.length === 0 && (
              <EmptyState
                icon={<BookOpen className="size-8" />}
                title="Разделов нет"
                description="Создайте первый раздел для загрузки документов."
                action={
                  <Button size="sm" onClick={() => setCreateOpen(true)}>
                    Создать
                  </Button>
                }
              />
            )}
            <div className="grid gap-1 p-2">
              {sections.data?.map((section) => (
                <div
                  key={section.id}
                  role="button"
                  tabIndex={0}
                  aria-pressed={selectedSectionId === section.id}
                  className={cn(
                    "group rounded-xl border p-3 transition",
                    selectedSectionId === section.id
                      ? "border-molvest-400 bg-molvest-50"
                      : "border-transparent hover:bg-[#f1f4fb]",
                  )}
                  onClick={() => setSearchParams({ section: section.id })}
                  onKeyDown={(event) => {
                    if (event.target !== event.currentTarget) return;
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      setSearchParams({ section: section.id });
                    }
                  }}
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0 flex-1 text-left">
                      <p className="truncate text-sm font-bold text-black">
                        {section.name}
                      </p>
                      <p className="mt-1 text-[11px] text-slate-400">
                        {section.documentCount ?? 0} документов
                      </p>
                    </div>
                    <span onClick={(event) => event.stopPropagation()}>
                      <Switch
                        checked={section.isEnabled}
                        label={`${section.isEnabled ? "Выключить" : "Включить"} раздел ${section.name}`}
                        disabled={updateSection.isPending}
                        onChange={(next) =>
                          next
                            ? updateSection.mutate({
                                id: section.id,
                                patch: { isEnabled: true },
                              })
                            : setSectionAction({ section, kind: "disable" })
                        }
                      />
                    </span>
                  </div>
                  <div className="mt-2 flex items-center gap-1 opacity-100 lg:opacity-0 lg:transition lg:group-hover:opacity-100">
                    {!section.isSystem && (
                      <>
                        <IconButton
                          type="button"
                          className="size-8 text-stone-400 hover:bg-white hover:text-molvest-700"
                          onClick={(event) => {
                            event.stopPropagation();
                            setName(section.name);
                            setRenameSection(section);
                          }}
                          aria-label={`Переименовать ${section.name}`}
                        >
                          <Pencil className="size-3.5" />
                        </IconButton>
                        <IconButton
                          type="button"
                          className="size-8 text-stone-400 hover:bg-red-50 hover:text-red-700"
                          onClick={(event) => {
                            event.stopPropagation();
                            setSectionAction({ section, kind: "delete" });
                          }}
                          aria-label={`Удалить ${section.name}`}
                        >
                          <Trash2 className="size-3.5" />
                        </IconButton>
                      </>
                    )}
                    {section.isSystem && (
                      <Badge tone="neutral">Системный</Badge>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </Card>
          <Card className="min-w-0 overflow-hidden">
            <div className="flex flex-wrap items-end justify-between gap-3 border-b border-[#dbe3f0] p-4 sm:p-5">
              <div>
                <p className="text-[10px] font-extrabold uppercase tracking-[0.15em] text-molvest-600">
                  Documents
                </p>
                <h2 className="mt-1 text-xl font-bold text-molvest-950">
                  {selectedSection?.name || "Выберите раздел"}
                </h2>
                {selectedSection && !selectedSection.isEnabled && (
                  <p className="mt-1 text-xs font-semibold text-amber-800">
                    Master switch выключен: документы временно не участвуют в
                    RAG.
                  </p>
                )}
              </div>
              <div className="flex items-center gap-2">
                <input
                  ref={fileInputRef}
                  className="sr-only"
                  type="file"
                  accept={KB_ACCEPT}
                  onChange={(event) =>
                    handleFileChange(event.target.files?.[0])
                  }
                />
                <Button
                  pending={upload.isPending}
                  disabled={!canUpload}
                  onClick={chooseFile}
                >
                  <Upload className="size-4" /> Загрузить
                </Button>
              </div>
            </div>
            {!selectedSectionId && (
              <EmptyState
                icon={<MoreHorizontal className="size-8" />}
                title="Раздел не выбран"
                description="Выберите раздел слева, чтобы увидеть его документы."
              />
            )}
            {selectedSectionId && documents.isPending && (
              <PageLoader label="Загружаем документы" />
            )}
            {documents.isError && (
              <ErrorState
                description={documents.error.message}
                onRetry={() => void documents.refetch()}
              />
            )}
            {documents.isSuccess && documents.data.items.length === 0 && (
              <EmptyState
                icon={<FilePlus2 className="size-8" />}
                title={
                  isCaseJournal
                    ? "Одобренных кейсов пока нет"
                    : "Документов нет"
                }
                description={
                  isCaseJournal
                    ? "Одобренные карточки решений появятся здесь после модерации."
                    : "Нажмите «Загрузить», чтобы выбрать файл и запустить индексацию."
                }
              />
            )}
            {documents.data && documents.data.items.length > 0 && (
              <div className="w-full">
                <table className="w-full table-fixed text-left text-sm">
                  <thead className="bg-[#f7f9fd] text-[10px] font-extrabold uppercase tracking-[0.12em] text-slate-500">
                    <tr>
                      <th className="w-[38%] px-2 py-3 sm:px-5">Документ</th>
                      <th className="w-[16%] px-2 py-3 sm:px-4">Включён</th>
                      <th className="w-[20%] px-2 py-3 sm:px-4">Обновлён</th>
                      <th className="w-[18%] px-2 py-3 sm:px-4">Индекс</th>
                      <th
                        className="w-[8%] px-2 py-3 sm:px-5"
                        aria-label="Действия"
                      />
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[#edf1f9]">
                    {documents.data.items.map((document) => (
                      <tr key={document.id} className="hover:bg-[#fafcff]">
                        <td className="min-w-0 px-2 py-4 sm:px-5">
                          <div className="flex min-w-0 items-center gap-2 sm:gap-3">
                            <a
                              href={withDemoRole(
                                document.downloadUrl ||
                                knowledgeApi.documentDownloadUrl(document.id),
                              )}
                              download
                              className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-[#eef2fa] text-slate-500 transition hover:bg-molvest-100 hover:text-molvest-700 focus-visible:outline-2 focus-visible:outline-molvest-400"
                              title={`Скачать ${document.title}`}
                              aria-label={`Скачать ${document.title}`}
                            >
                              <FileText className="size-4" />
                            </a>
                            <p
                              className="min-w-0 truncate font-bold text-black"
                              title={document.title}
                            >
                              {truncateTitle(document.title, 20)}
                            </p>
                          </div>
                        </td>
                        <td className="px-2 py-4 sm:px-4">
                          <Switch
                            checked={document.isEnabled}
                            label={`${document.isEnabled ? "Выключить" : "Включить"} документ ${document.title}`}
                            disabled={toggleDocument.isPending}
                            onChange={(next) =>
                              toggleDocument.mutate({
                                id: document.id,
                                isEnabled: next,
                              })
                            }
                          />
                        </td>
                        <td className="px-2 py-4 text-xs text-slate-500 sm:px-4">
                          {formatRelativeDate(document.updatedAt)}
                        </td>
                        <td className="px-2 py-4 sm:px-5">
                          <div className="flex max-w-full flex-wrap items-center gap-1">
                            <Badge
                              className="max-w-full break-all text-[10px]"
                              tone={indexTone[document.indexStatus]}
                            >
                              {document.indexStatus}
                            </Badge>
                            {document.indexStatus === "failed" && (
                              <IconButton
                                type="button"
                                className="size-8 text-red-700 hover:bg-red-50"
                                aria-label={`Повторить индексацию ${document.title}`}
                                disabled={reindex.isPending}
                                onClick={() => reindex.mutate(document.id)}
                              >
                                <RefreshCw className="size-3.5" />
                              </IconButton>
                            )}
                          </div>
                        </td>
                        <td className="px-2 py-4 text-right sm:px-5">
                          <IconButton
                            type="button"
                            className="size-8 text-slate-400 hover:bg-red-50 hover:text-red-700"
                            aria-label={`Удалить ${document.title}`}
                            disabled={deleteDocument.isPending}
                            onClick={() => setDocumentToDelete(document)}
                          >
                            <Trash2 className="size-3.5" />
                          </IconButton>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        </div>
      </div>
      <Modal
        open={createOpen}
        title="Новый раздел"
        description="Раздел станет отдельной логической областью базы знаний."
        onClose={() => setCreateOpen(false)}
      >
        <form
          className="grid gap-4"
          onSubmit={(event) => {
            event.preventDefault();
            if (name.trim()) create.mutate();
          }}
        >
          <Field label="Название">
            <Input
              autoFocus
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="Например, Документация 1С"
            />
          </Field>
          <div className="flex justify-end gap-2">
            <Button
              type="button"
              variant="secondary"
              onClick={() => setCreateOpen(false)}
            >
              Отмена
            </Button>
            <Button
              type="submit"
              pending={create.isPending}
              disabled={!name.trim()}
            >
              Создать
            </Button>
          </div>
        </form>
      </Modal>
      <Modal
        open={Boolean(renameSection)}
        title="Переименовать раздел"
        onClose={() => setRenameSection(undefined)}
      >
        <form
          className="grid gap-4"
          onSubmit={(event) => {
            event.preventDefault();
            if (renameSection && name.trim())
              updateSection.mutate({
                id: renameSection.id,
                patch: { name: name.trim() },
              });
          }}
        >
          <Field label="Название">
            <Input
              autoFocus
              value={name}
              onChange={(event) => setName(event.target.value)}
            />
          </Field>
          <div className="flex justify-end gap-2">
            <Button
              type="button"
              variant="secondary"
              onClick={() => setRenameSection(undefined)}
            >
              Отмена
            </Button>
            <Button
              type="submit"
              pending={updateSection.isPending}
              disabled={!name.trim()}
            >
              Сохранить
            </Button>
          </div>
        </form>
      </Modal>
      <ConfirmDialog
        open={sectionAction?.kind === "disable"}
        title="Выключить раздел целиком?"
        description="Все документы раздела временно перестанут участвовать в RAG. Их индивидуальные настройки сохранятся."
        confirmLabel="Выключить"
        pending={updateSection.isPending}
        onConfirm={() =>
          sectionAction &&
          updateSection.mutate({
            id: sectionAction.section.id,
            patch: { isEnabled: false },
          })
        }
        onCancel={() => setSectionAction(undefined)}
      />
      <ConfirmDialog
        open={sectionAction?.kind === "delete"}
        title="Удалить раздел?"
        description="Раздел, документы и поисковый индекс будут удалены. Действие нельзя отменить."
        confirmLabel="Удалить"
        danger
        pending={deleteSection.isPending}
        onConfirm={() =>
          sectionAction && deleteSection.mutate(sectionAction.section.id)
        }
        onCancel={() => setSectionAction(undefined)}
      />
      <ConfirmDialog
        open={Boolean(documentToDelete)}
        title="Удалить документ из базы знаний?"
        description={`Документ будет удалён из поискового индекса и object storage. Действие нельзя отменить.`}
        confirmLabel="Удалить"
        danger
        pending={deleteDocument.isPending}
        onConfirm={() => {
          if (documentToDelete) deleteDocument.mutate(documentToDelete.id);
        }}
        onCancel={() => setDocumentToDelete(undefined)}
      />
    </div>
  );
}
