from __future__ import annotations

import unittest

from app.core.config import Settings
from app.providers.gigachat import (
    _CONFIDENCE_SYSTEM_PROMPT,
    GigaChatProvider,
)
from app.providers.interfaces import ConfidenceAssessment, GenerationRequest
from app.services.dialogs import DialogService
from pydantic import SecretStr


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

    def test_clarification_matches_the_user_message(self) -> None:
        self.assertIn(
            "точный текст ошибки",
            DialogService._clarification_message("У меня ошибка при запуске 1С", 0),
        )
        self.assertIn(
            "что именно хотите узнать о 1С",
            DialogService._clarification_message("Что такое 1C", 0),
        )
        self.assertIn(
            "сделать в 1С",
            DialogService._clarification_message("Привте", 0),
        )


if __name__ == "__main__":
    unittest.main()
