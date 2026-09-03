import type { DialogSummary } from "../../api/types";
import { Badge } from "../ui";
import { dialogStatusLabel } from "../utils";

export function DialogStatusBadge({
  dialog,
}: {
  dialog: Pick<DialogSummary, "status" | "mode" | "feedback">;
}) {
  const label = dialogStatusLabel(dialog);
  const tone =
    dialog.status === "closed"
      ? dialog.feedback?.verdict === "helpful"
        ? "success"
        : dialog.feedback?.verdict === "ai_error"
          ? "danger"
          : "neutral"
      : dialog.mode === "operator_support"
        ? "info"
        : "success";
  return <Badge tone={tone} className="justify-center text-center">{label}</Badge>;
}
