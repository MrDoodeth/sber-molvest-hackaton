import { ThumbsDown, ThumbsUp } from "lucide-react";
import type { DialogDetailDto, FeedbackVerdict } from "../../api/types";
import { Badge, Button } from "../../shared/ui";
import { canShowFeedback } from "../../shared/utils";

export function FeedbackPanel({
  dialog,
  pending,
  onFeedback,
}: {
  dialog: DialogDetailDto;
  pending?: boolean;
  onFeedback: (verdict: FeedbackVerdict) => void;
}) {
  if (dialog.feedback) {
    return (
      <div className="border-t border-stone-200 bg-white px-5 py-5 text-center">
        <Badge tone={dialog.feedback.verdict === "helpful" ? "success" : "danger"}>
          {dialog.feedback.verdict === "helpful" ? "Отмечено: решение помогло" : "Отмечено: AI ошибся"}
        </Badge>
      </div>
    );
  }
  if (!canShowFeedback(dialog)) return null;
  return (
    <section className="border-t border-stone-200 bg-white px-5 py-5 text-center" aria-labelledby="feedback-title">
      <h2 id="feedback-title" className="text-base font-bold text-molvest-950">Решение помогло?</h2>
      <p className="mt-1 text-xs text-stone-500">Оценка относится ко всему завершённому обращению.</p>
      <div className="mt-4 flex flex-col justify-center gap-2 sm:flex-row">
        <Button disabled={pending} onClick={() => onFeedback("helpful")}><ThumbsUp className="size-4" /> Да, помогло</Button>
        <Button variant="secondary" disabled={pending} onClick={() => onFeedback("ai_error")}><ThumbsDown className="size-4" /> Нет, AI ошибся</Button>
      </div>
    </section>
  );
}
