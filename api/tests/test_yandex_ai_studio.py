from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from api.config import settings
from api.llm.factory import get_llm_provider
from api.llm.yandex_ai_studio import YandexAIStudioProvider


@patch("api.llm.yandex_ai_studio.get_cache")
@patch("api.llm.yandex_ai_studio.openai.OpenAI")
def test_yandex_provider_uses_responses_api(mock_openai, mock_get_cache):
    """Provider sends the documented Yandex AI Studio Responses request."""
    client = mock_openai.return_value
    client.responses.create.return_value = SimpleNamespace(output_text="Готовый ответ")
    cache = mock_get_cache.return_value
    cache.get.return_value = None

    provider = YandexAIStudioProvider(
        api_key="test-api-key",
        folder="test-folder",
        model="deepseek-v4-flash/latest",
    )

    assert provider.complete("Вопрос", "Инструкция", max_tokens=321) == "Готовый ответ"
    mock_openai.assert_called_once_with(
        api_key="test-api-key",
        base_url="https://ai.api.cloud.yandex.net/v1",
        project="test-folder",
    )
    client.responses.create.assert_called_once_with(
        model="gpt://test-folder/deepseek-v4-flash/latest",
        temperature=0.3,
        instructions="Инструкция",
        input="Вопрос",
        max_output_tokens=321,
        store=True,
        truncation="disabled",
    )
    cache.set.assert_called_once_with(
        "Вопрос",
        "Инструкция",
        "gpt://test-folder/deepseek-v4-flash/latest",
        "Готовый ответ",
    )


def test_yandex_provider_requires_credentials():
    with patch.object(settings, "yandex_cloud_api_key", ""):
        provider = YandexAIStudioProvider(api_key="", folder="test-folder")

        try:
            provider.complete("Вопрос")
        except ValueError as error:
            assert "YANDEX_CLOUD_API_KEY" in str(error)
        else:
            raise AssertionError("Provider must reject a missing API key")


def test_factory_returns_yandex_provider():
    assert isinstance(get_llm_provider(), YandexAIStudioProvider)
