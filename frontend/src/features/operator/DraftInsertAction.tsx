import { WandSparkles } from "lucide-react";
import { useState } from "react";
import { Button, ConfirmDialog } from "../../shared/ui";

export function DraftInsertAction({
  draftText,
  currentText,
  disabled = false,
  onInsert,
}: {
  draftText: string;
  currentText: string;
  disabled?: boolean;
  onInsert: (text: string) => void;
}) {
  const [confirmOpen, setConfirmOpen] = useState(false);
  const requestInsert = () => {
    if (currentText.trim()) setConfirmOpen(true);
    else onInsert(draftText);
  };
  return (
    <>
      <Button type="button" variant="giga" size="sm" disabled={disabled || !draftText} onClick={requestInsert}>
        <WandSparkles className="size-4" /> Вставить в ответ
      </Button>
      <ConfirmDialog
        open={confirmOpen}
        title="Заменить текущий текст предложением GigaChat?"
        description="Введённый вручную текст будет заменён. Черновик не отправится пользователю автоматически."
        confirmLabel="Заменить"
        onConfirm={() => {
          onInsert(draftText);
          setConfirmOpen(false);
        }}
        onCancel={() => setConfirmOpen(false)}
      />
    </>
  );
}
