# Project State

## Current Focus

The user AI turn uses one prepared `GenerationRequest` for two sequential calls:

```text
GenerationContext
    -> hidden structured confidence
    -> threshold decision
    -> streaming user answer or clarification/escalation
```

Screenshot parsing, attachment preparation and RAG retrieval happen before the
confidence call and remain inside the same re-entrant `GenerationGate` turn.

## Confidence Contract

- `ConfidenceAssessment` contains only `confidence` in the range `0..1`.
- The confidence prompt is hardcoded in `backend/app/providers/gigachat.py`.
- The editable `SystemPrompt(type=user_support)` is not passed to confidence.
- Confidence uses constrained sampling (`temperature=0`, `top_p=0.1`) and a documented
  schema.
- RAG status metadata is declarative, not an instruction that conflicts with the
  confidence prompt.
- The operator threshold is applied by `DialogService` after the confidence call.
- Explicit operator requests are routed locally with confidence `0`.
- Low-confidence clarification text is selected locally from the current message
  category and does not create a third GigaChat call.

## Runtime Checks

The local `backend/.venv` is used for backend verification. The confidence provider
smoke check covers:

- stable high confidence for an informational `1C` question;
- low confidence for an incomplete typo-only message;
- stable operator routing phrases such as `переведи на специалиста`;
- separate clarification wording for error, informational and generic messages;
- structured schema construction and confidence client temperature.

The local answer stream was also checked to emit multiple text chunks followed by
usage metadata.

## Constraints

- Do not modify `Problems` or `files/`.
- Do not expose credentials or technical confidence instructions to the frontend.
- Keep one user-turn metric with aggregated confidence and answer usage.
