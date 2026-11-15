from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class ProviderResponse:
    text: str
    tokens_in: int | None = None
    tokens_out: int | None = None
    retry_after: float | None = None
    http_status: int | None = 200


class ProviderException(Exception):
    def __init__(self, message: str, status_code: int | None = None, retry_after: float | None = None, timed_out: bool = False):
        super().__init__(message)
        self.status_code = status_code
        self.retry_after = retry_after
        self.timed_out = timed_out


class Provider(Protocol):
    def complete(self, *, model: str, messages: list[dict[str, str]], response_format: dict[str, Any] | None, temperature: float, timeout_seconds: float) -> ProviderResponse: ...


class OpenAICompatibleProvider:
    def __init__(self, api_key: str, base_url: str):
        from openai import OpenAI

        self.client = OpenAI(api_key=api_key, base_url=base_url)

    def complete(self, *, model: str, messages: list[dict[str, str]], response_format: dict[str, Any] | None, temperature: float, timeout_seconds: float) -> ProviderResponse:
        try:
            client = self.client.with_options(timeout=timeout_seconds)
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                response_format=response_format,
            )
        except Exception as exc:
            status = getattr(exc, "status_code", None)
            timed_out = type(exc).__name__ in {"APITimeoutError", "ConnectTimeout", "ReadTimeout", "WriteTimeout"}
            retry_after = None
            response = getattr(exc, "response", None)
            headers = getattr(response, "headers", {}) or {}
            if headers.get("retry-after"):
                try:
                    retry_after = float(headers["retry-after"])
                except ValueError:
                    pass
            body = getattr(exc, "body", None)
            if isinstance(body, dict):
                error = body.get("error", body)
                detail = error.get("message") if isinstance(error, dict) else None
            else:
                detail = None
            detail = str(detail or getattr(exc, "message", None) or type(exc).__name__).replace("\n", " ")[:300]
            raise ProviderException(detail, status, retry_after, timed_out=timed_out) from exc
        usage = getattr(response, "usage", None)
        return ProviderResponse(
            text=response.choices[0].message.content or "",
            tokens_in=getattr(usage, "prompt_tokens", None),
            tokens_out=getattr(usage, "completion_tokens", None),
        )
