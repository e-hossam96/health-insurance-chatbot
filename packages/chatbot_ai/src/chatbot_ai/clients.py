from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from openai import AsyncOpenAI, AsyncStream, Omit, omit
from openai.types.chat import (
    ChatCompletion,
    ChatCompletionChunk,
    ChatCompletionMessageParam,
    ChatCompletionToolParam,
)
from openai.types.shared_params import ResponseFormatJSONSchema
from qdrant_client import AsyncQdrantClient

from chatbot_ai.settings import AISettings, ReasoningEffort, Role, RoleConfig
from chatbot_ai.tracing import TurnTracer, make_tracer


@dataclass(frozen=True)
class RoleClient:
    config: RoleConfig
    client: AsyncOpenAI

    @property
    def model(self) -> str:
        return self.config.model

    @property
    def _effort(self) -> ReasoningEffort | Omit:
        effort = self.config.reasoning_effort
        return omit if effort is None else effort

    async def complete(
        self,
        messages: Iterable[ChatCompletionMessageParam],
        max_tokens: int,
        response_format: ResponseFormatJSONSchema | Omit = omit,
        tools: Iterable[ChatCompletionToolParam] | Omit = omit,
    ) -> ChatCompletion:
        if self.config.output_token_param == "max_tokens":
            return await self.client.chat.completions.create(
                model=self.model, messages=messages, max_tokens=max_tokens, response_format=response_format, tools=tools,
                reasoning_effort=self._effort,
            )
        return await self.client.chat.completions.create(
            model=self.model, messages=messages, max_completion_tokens=max_tokens, response_format=response_format, tools=tools,
            reasoning_effort=self._effort,
        )

    async def stream(
        self,
        messages: Iterable[ChatCompletionMessageParam],
        max_tokens: int,
        tools: Iterable[ChatCompletionToolParam] | Omit = omit,
    ) -> AsyncStream[ChatCompletionChunk]:
        if self.config.output_token_param == "max_tokens":
            return await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=max_tokens,
                tools=tools,
                stream=True,
                stream_options={"include_usage": True},
                reasoning_effort=self._effort,
            )
        return await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_completion_tokens=max_tokens,
            tools=tools,
            stream=True,
            stream_options={"include_usage": True},
            reasoning_effort=self._effort,
        )


def make_role_client(config: RoleConfig) -> RoleClient:
    return RoleClient(
        config=config,
        client=AsyncOpenAI(
            api_key=config.api_key.get_secret_value(),
            base_url=config.base_url,
            timeout=config.timeout_s,
            max_retries=config.max_retries,
        ),
    )


@dataclass
class RoleClients:
    settings: AISettings
    _clients: dict[Role, RoleClient] = field(default_factory=dict)
    _qdrant: AsyncQdrantClient | None = None
    _tracer: TurnTracer | None = None

    def tracer(self) -> TurnTracer:
        if self._tracer is None:
            secret = self.settings.langfuse_secret_key
            self._tracer = make_tracer(
                self.settings.langfuse_public_key, secret.get_secret_value() if secret else None, self.settings.langfuse_host
            )
        return self._tracer

    def qdrant(self) -> AsyncQdrantClient:
        if self._qdrant is None:
            self._qdrant = AsyncQdrantClient(url=self.settings.qdrant_url, check_compatibility=False)
        return self._qdrant

    def get(self, role: Role) -> RoleClient:
        if role not in self._clients:
            self._clients[role] = make_role_client(self.settings.role(role))
        return self._clients[role]

    async def aclose(self) -> None:
        for role_client in self._clients.values():
            await role_client.client.close()
        self._clients.clear()
        if self._qdrant is not None:
            await self._qdrant.close()
            self._qdrant = None
        if self._tracer is not None:
            self._tracer.flush()
