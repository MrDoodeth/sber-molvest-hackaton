from __future__ import annotations

import unittest

from pydantic import SecretStr

from app.core.config import Settings
from app.providers.gigachat import (
    _CONFIDENCE_SYSTEM_PROMPT,
    GigaChatProvider,
)
from app.providers.interfaces import ConfidenceAssessment, GenerationRequest
from app.services.dialogs import DialogService


class ConfidencePolicyTests(unittest.TestCase):
    def test_confidence_schema_has_description_and_only_one_field(self) -> None:
        schema = ConfidenceAssessment.model_json_schema()

        self.assertEqual(set(schema["properties"]), {"confidence"})
        self.assertTrue(schema["description"])
        self.assertTrue(schema["properties"]["confidence"]["description"])

    def test_confidence_context_does_not_contain_answer_instructions(self) -> None:
        provider = GigaChatProvider(Settings())
        request = GenerationRequest(
            system_prompt="editable user support prompt",
            current_text="Что такое 1C",
            threshold=0.76,
            rag_status="empty",
        )

        messages = provider._messages(
            request,
            system_prompt=_CONFIDENCE_SYSTEM_PROMPT,
        )
        system_message = messages[0].content

        self.assertIn("Не пытайся дать пользователю ответ", system_message)
        self.assertNotIn("editable user support prompt", system_message)
        self.assertNotIn("Попробуй решить вопрос", system_message)

    def test_confidence_client_uses_constrained_sampling(self) -> None:
        settings = Settings(gigachat_credentials=SecretStr("test"))
        provider = GigaChatProvider(settings)

        client = provider._client("GigaChat-2-Max", 64, temperature=0.0, top_p=0.1)

        self.assertEqual(client.temperature, 0.0)
        self.assertEqual(client.top_p, 0.1)
        self.assertIs(
            client,
            provider._client("GigaChat-2-Max", 64, temperature=0.0, top_p=0.1),
        )

    def test_operator_shortcuts_cover_imperative_phrases(self) -> None:
        self.assertTrue(
            DialogService._explicit_operator_request("Привет, переведи на специалиста")
        )
        self.assertTrue(
            DialogService._explicit_operator_request("Просто переведи на специалиста")
        )
        self.assertFalse(DialogService._explicit_operator_request("Оператор не нужен"))

    def test_low_confidence_streak_requires_three_consecutive_turns(self) -> None:
        self.assertEqual(DialogService._count_low_confidence_streak([0.2, 0.3], 0.8), 2)
        self.assertEqual(
            DialogService._count_low_confidence_streak([0.2, 0.3, 0.4], 0.8), 3
        )

    def test_low_confidence_streak_resets_after_high_or_unknown_turn(self) -> None:
        self.assertEqual(
            DialogService._count_low_confidence_streak([0.2, 0.9, 0.3, 0.4], 0.8),
            2,
        )
        self.assertEqual(
            DialogService._count_low_confidence_streak([0.2, None, 0.4], 0.8),
            1,
        )
        self.assertEqual(DialogService._count_low_confidence_streak([0.8], 0.8), 0)


if __name__ == "__main__":
    unittest.main()
