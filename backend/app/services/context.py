from __future__ import annotations

import math

from app.providers.interfaces import ChatTurn, Evidence, GenerationRequest
from app.services.settings import RuntimeSettings


def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    # A conservative local estimate avoids an extra network token-count request.
    return max(1, math.ceil(len(text) / 3))


class ContextBuilder:
    def build_embedding_context(
        self,
        *,
        current_text: str,
        history: list[ChatTurn],
        screenshot_extracted_text: str | None,
        screenshot_visual_summary: str | None,
        settings: RuntimeSettings,
    ) -> str:
        current_parts = [current_text]
        if screenshot_extracted_text:
            current_parts.append(screenshot_extracted_text)
        if screenshot_visual_summary:
            current_parts.append(screenshot_visual_summary)
        current = "\n".join(part for part in current_parts if part).strip()
        current = current or "Вопрос содержится во вложении."
        remaining = settings.embedding_input_budget - estimate_tokens(current)
        selected: list[ChatTurn] = []
        for turn in reversed(history):
            cost = estimate_tokens(turn.text) + 2
            if cost > remaining:
                break
            selected.append(turn)
            remaining -= cost
        selected.reverse()
        history_text = "\n".join(f"{turn.role}: {turn.text}" for turn in selected)
        if history_text:
            return f"{current}\n\nСвежий контекст диалога:\n{history_text}"
        return current

    def build_generation_request(
        self,
        *,
        system_prompt: str,
        current_text: str,
        history: list[ChatTurn],
        evidence: list[Evidence],
        attachment_file_id: str | None,
        attachment_mime_type: str | None,
        screenshot_extracted_text: str | None,
        screenshot_visual_summary: str | None,
        settings: RuntimeSettings,
    ) -> GenerationRequest:
        mandatory_cost = (
            estimate_tokens(system_prompt)
            + estimate_tokens(current_text)
            + estimate_tokens(screenshot_extracted_text or "")
            + estimate_tokens(screenshot_visual_summary or "")
        )
        remaining = max(0, settings.gigachat_input_budget - mandatory_cost)
        selected_evidence: list[Evidence] = []
        for item in evidence:
            cost = estimate_tokens(item.text) + estimate_tokens(item.source.title) + 4
            if cost > remaining:
                break
            selected_evidence.append(item)
            remaining -= cost
        selected: list[ChatTurn] = []
        for turn in reversed(history):
            cost = estimate_tokens(turn.text) + 4
            if cost > remaining:
                break
            selected.append(turn)
            remaining -= cost
        selected.reverse()
        return GenerationRequest(
            system_prompt=system_prompt,
            current_text=current_text,
            history=tuple(selected),
            evidence=tuple(selected_evidence),
            threshold=settings.operator_escalation_threshold,
            attachment_file_id=attachment_file_id,
            attachment_mime_type=attachment_mime_type,
            screenshot_extracted_text=screenshot_extracted_text,
            screenshot_visual_summary=screenshot_visual_summary,
        )
