import { WandSparkles } from "lucide-react";
import { useState } from "react";
import { Button, ConfirmDialog } from "../../shared/ui";

export function TemplateInsertAction({
  templateText,
  currentText,
  disabled = false,
  onInsert,
  className,
}: {
  templateText: string;
  currentText: string;
  disabled?: boolean;
  onInsert: (text: string) => void;
  className?: string;
}) {
  const [confirmOpen, setConfirmOpen] = useState(false);
  const requestInsert = () => {
    if (currentText.trim()) setConfirmOpen(true);
    else onInsert(templateText);
  };
  return (
    <>
      <Button type="button" variant="secondary" size="sm" className={className} disabled={disabled || !templateText} onClick={requestInsert}>
        <WandSparkles className="size-4" /> Вставить шаблон
      </Button>
      <ConfirmDialog
        open={confirmOpen}
        title="Заменить текущий текст шаблоном?"
        description="Введённый вручную текст будет заменён. Шаблон не отправится пользователю автоматически."
        confirmLabel="Заменить"
        onConfirm={() => {
          onInsert(templateText);
          setConfirmOpen(false);
        }}
        onCancel={() => setConfirmOpen(false)}
      />
    </>
  );
}
