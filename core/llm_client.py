from typing import Protocol, Optional


class LLMClient(Protocol):
    """Abstract interface for LLM API calls."""

    def chat_completion(
        self,
        messages: list[dict],
        model: str,
        temperature: float = 0.3,
        max_tokens: int = 65536,
        timeout: tuple = (30, 600),
    ) -> dict:
        """Returns {'content', 'finish_reason', 'usage', 'raw_response'}."""
        ...


class HttpLLMClient:
    """Production implementation using requests.Session."""

    def __init__(self, api_key: str, api_base_url: str, session: Optional[object] = None):
        self.api_key = api_key
        self.api_base_url = api_base_url.rstrip('/')
        self._session = session or self._create_session()

    def _create_session(self):
        import requests
        s = requests.Session()
        s.headers.update({
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        })
        return s

    def chat_completion(
        self,
        messages: list,
        model: str,
        temperature: float = 0.3,
        max_tokens: int = 65536,
        timeout: tuple = (30, 600),
    ) -> dict:
        endpoint = f"{self.api_base_url}/chat/completions"
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        response = self._session.post(endpoint, json=payload, timeout=timeout)
        response.raise_for_status()
        result = response.json()

        choices = result.get('choices', [])
        choice = choices[0] if choices else {}
        message = choice.get('message', {})

        return {
            'content': message.get('content', ''),
            'finish_reason': choice.get('finish_reason', ''),
            'usage': result.get('usage', {}),
            'raw_response': result,
        }
