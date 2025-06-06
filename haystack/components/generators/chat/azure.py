# SPDX-FileCopyrightText: 2022-present deepset GmbH <info@deepset.ai>
#
# SPDX-License-Identifier: Apache-2.0

import os
from typing import Any, Dict, List, Optional, Union

from openai.lib.azure import AsyncAzureADTokenProvider, AsyncAzureOpenAI, AzureADTokenProvider, AzureOpenAI

from haystack import component, default_from_dict, default_to_dict
from haystack.components.generators.chat import OpenAIChatGenerator
from haystack.dataclasses.streaming_chunk import StreamingCallbackT
from haystack.tools import (
    Tool,
    Toolset,
    _check_duplicate_tool_names,
    deserialize_tools_or_toolset_inplace,
    serialize_tools_or_toolset,
)
from haystack.utils import Secret, deserialize_callable, deserialize_secrets_inplace, serialize_callable
from haystack.utils.http_client import init_http_client


@component
class AzureOpenAIChatGenerator(OpenAIChatGenerator):
    """
    Generates text using OpenAI's models on Azure.

    It works with the gpt-4 - type models and supports streaming responses
    from OpenAI API. It uses [ChatMessage](https://docs.haystack.deepset.ai/docs/chatmessage)
    format in input and output.

    You can customize how the text is generated by passing parameters to the
    OpenAI API. Use the `**generation_kwargs` argument when you initialize
    the component or when you run it. Any parameter that works with
    `openai.ChatCompletion.create` will work here too.

    For details on OpenAI API parameters, see
    [OpenAI documentation](https://platform.openai.com/docs/api-reference/chat).

    ### Usage example

    ```python
    from haystack.components.generators.chat import AzureOpenAIChatGenerator
    from haystack.dataclasses import ChatMessage
    from haystack.utils import Secret

    messages = [ChatMessage.from_user("What's Natural Language Processing?")]

    client = AzureOpenAIChatGenerator(
        azure_endpoint="<Your Azure endpoint e.g. `https://your-company.azure.openai.com/>",
        api_key=Secret.from_token("<your-api-key>"),
        azure_deployment="<this a model name, e.g. gpt-4o-mini>")
    response = client.run(messages)
    print(response)
    ```

    ```
    {'replies':
        [ChatMessage(content='Natural Language Processing (NLP) is a branch of artificial intelligence that focuses on
         enabling computers to understand, interpret, and generate human language in a way that is useful.',
         role=<ChatRole.ASSISTANT: 'assistant'>, name=None,
         meta={'model': 'gpt-4o-mini', 'index': 0, 'finish_reason': 'stop',
         'usage': {'prompt_tokens': 15, 'completion_tokens': 36, 'total_tokens': 51}})]
    }
    ```
    """

    # pylint: disable=super-init-not-called
    # ruff: noqa: PLR0913
    def __init__(  # pylint: disable=too-many-positional-arguments
        self,
        azure_endpoint: Optional[str] = None,
        api_version: Optional[str] = "2023-05-15",
        azure_deployment: Optional[str] = "gpt-4o-mini",
        api_key: Optional[Secret] = Secret.from_env_var("AZURE_OPENAI_API_KEY", strict=False),
        azure_ad_token: Optional[Secret] = Secret.from_env_var("AZURE_OPENAI_AD_TOKEN", strict=False),
        organization: Optional[str] = None,
        streaming_callback: Optional[StreamingCallbackT] = None,
        timeout: Optional[float] = None,
        max_retries: Optional[int] = None,
        generation_kwargs: Optional[Dict[str, Any]] = None,
        default_headers: Optional[Dict[str, str]] = None,
        tools: Optional[Union[List[Tool], Toolset]] = None,
        tools_strict: bool = False,
        *,
        azure_ad_token_provider: Optional[Union[AzureADTokenProvider, AsyncAzureADTokenProvider]] = None,
        http_client_kwargs: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize the Azure OpenAI Chat Generator component.

        :param azure_endpoint: The endpoint of the deployed model, for example `"https://example-resource.azure.openai.com/"`.
        :param api_version: The version of the API to use. Defaults to 2023-05-15.
        :param azure_deployment: The deployment of the model, usually the model name.
        :param api_key: The API key to use for authentication.
        :param azure_ad_token: [Azure Active Directory token](https://www.microsoft.com/en-us/security/business/identity-access/microsoft-entra-id).
        :param organization: Your organization ID, defaults to `None`. For help, see
        [Setting up your organization](https://platform.openai.com/docs/guides/production-best-practices/setting-up-your-organization).
        :param streaming_callback: A callback function called when a new token is received from the stream.
            It accepts [StreamingChunk](https://docs.haystack.deepset.ai/docs/data-classes#streamingchunk)
            as an argument.
        :param timeout: Timeout for OpenAI client calls. If not set, it defaults to either the
            `OPENAI_TIMEOUT` environment variable, or 30 seconds.
        :param max_retries: Maximum number of retries to contact OpenAI after an internal error.
            If not set, it defaults to either the `OPENAI_MAX_RETRIES` environment variable, or set to 5.
        :param generation_kwargs: Other parameters to use for the model. These parameters are sent directly to
            the OpenAI endpoint. For details, see [OpenAI documentation](https://platform.openai.com/docs/api-reference/chat).
            Some of the supported parameters:
            - `max_tokens`: The maximum number of tokens the output text can have.
            - `temperature`: The sampling temperature to use. Higher values mean the model takes more risks.
                Try 0.9 for more creative applications and 0 (argmax sampling) for ones with a well-defined answer.
            - `top_p`: Nucleus sampling is an alternative to sampling with temperature, where the model considers
                tokens with a top_p probability mass. For example, 0.1 means only the tokens comprising
                the top 10% probability mass are considered.
            - `n`: The number of completions to generate for each prompt. For example, with 3 prompts and n=2,
                the LLM will generate two completions per prompt, resulting in 6 completions total.
            - `stop`: One or more sequences after which the LLM should stop generating tokens.
            - `presence_penalty`: The penalty applied if a token is already present.
                Higher values make the model less likely to repeat the token.
            - `frequency_penalty`: Penalty applied if a token has already been generated.
                Higher values make the model less likely to repeat the token.
            - `logit_bias`: Adds a logit bias to specific tokens. The keys of the dictionary are tokens, and the
                values are the bias to add to that token.
        :param default_headers: Default headers to use for the AzureOpenAI client.
        :param tools:
            A list of tools or a Toolset for which the model can prepare calls. This parameter can accept either a
            list of `Tool` objects or a `Toolset` instance.
        :param tools_strict:
            Whether to enable strict schema adherence for tool calls. If set to `True`, the model will follow exactly
            the schema provided in the `parameters` field of the tool definition, but this may increase latency.
        :param azure_ad_token_provider: A function that returns an Azure Active Directory token, will be invoked on
            every request.
        :param http_client_kwargs:
            A dictionary of keyword arguments to configure a custom `httpx.Client`or `httpx.AsyncClient`.
            For more information, see the [HTTPX documentation](https://www.python-httpx.org/api/#client).
        """
        # We intentionally do not call super().__init__ here because we only need to instantiate the client to interact
        # with the API.

        # Why is this here?
        # AzureOpenAI init is forcing us to use an init method that takes either base_url or azure_endpoint as not
        # None init parameters. This way we accommodate the use case where env var AZURE_OPENAI_ENDPOINT is set instead
        # of passing it as a parameter.
        azure_endpoint = azure_endpoint or os.environ.get("AZURE_OPENAI_ENDPOINT")
        if not azure_endpoint:
            raise ValueError("Please provide an Azure endpoint or set the environment variable AZURE_OPENAI_ENDPOINT.")

        if api_key is None and azure_ad_token is None:
            raise ValueError("Please provide an API key or an Azure Active Directory token.")

        # The check above makes mypy incorrectly infer that api_key is never None,
        # which propagates the incorrect type.
        self.api_key = api_key  # type: ignore
        self.azure_ad_token = azure_ad_token
        self.generation_kwargs = generation_kwargs or {}
        self.streaming_callback = streaming_callback
        self.api_version = api_version
        self.azure_endpoint = azure_endpoint
        self.azure_deployment = azure_deployment
        self.organization = organization
        self.model = azure_deployment or "gpt-4o-mini"
        self.timeout = timeout if timeout is not None else float(os.environ.get("OPENAI_TIMEOUT", "30.0"))
        self.max_retries = max_retries if max_retries is not None else int(os.environ.get("OPENAI_MAX_RETRIES", "5"))
        self.default_headers = default_headers or {}
        self.azure_ad_token_provider = azure_ad_token_provider
        self.http_client_kwargs = http_client_kwargs
        _check_duplicate_tool_names(list(tools or []))
        self.tools = tools
        self.tools_strict = tools_strict

        client_args: Dict[str, Any] = {
            "api_version": api_version,
            "azure_endpoint": azure_endpoint,
            "azure_deployment": azure_deployment,
            "api_key": api_key.resolve_value() if api_key is not None else None,
            "azure_ad_token": azure_ad_token.resolve_value() if azure_ad_token is not None else None,
            "organization": organization,
            "timeout": self.timeout,
            "max_retries": self.max_retries,
            "default_headers": self.default_headers,
            "azure_ad_token_provider": azure_ad_token_provider,
        }

        self.client = AzureOpenAI(
            http_client=init_http_client(self.http_client_kwargs, async_client=False), **client_args
        )
        self.async_client = AsyncAzureOpenAI(
            http_client=init_http_client(self.http_client_kwargs, async_client=True), **client_args
        )

    def to_dict(self) -> Dict[str, Any]:
        """
        Serialize this component to a dictionary.

        :returns:
            The serialized component as a dictionary.
        """
        callback_name = serialize_callable(self.streaming_callback) if self.streaming_callback else None
        azure_ad_token_provider_name = None
        if self.azure_ad_token_provider:
            azure_ad_token_provider_name = serialize_callable(self.azure_ad_token_provider)
        return default_to_dict(
            self,
            azure_endpoint=self.azure_endpoint,
            azure_deployment=self.azure_deployment,
            organization=self.organization,
            api_version=self.api_version,
            streaming_callback=callback_name,
            generation_kwargs=self.generation_kwargs,
            timeout=self.timeout,
            max_retries=self.max_retries,
            api_key=self.api_key.to_dict() if self.api_key is not None else None,
            azure_ad_token=self.azure_ad_token.to_dict() if self.azure_ad_token is not None else None,
            default_headers=self.default_headers,
            tools=serialize_tools_or_toolset(self.tools),
            tools_strict=self.tools_strict,
            azure_ad_token_provider=azure_ad_token_provider_name,
            http_client_kwargs=self.http_client_kwargs,
        )

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AzureOpenAIChatGenerator":
        """
        Deserialize this component from a dictionary.

        :param data: The dictionary representation of this component.
        :returns:
            The deserialized component instance.
        """
        deserialize_secrets_inplace(data["init_parameters"], keys=["api_key", "azure_ad_token"])
        deserialize_tools_or_toolset_inplace(data["init_parameters"], key="tools")
        init_params = data.get("init_parameters", {})
        serialized_callback_handler = init_params.get("streaming_callback")
        if serialized_callback_handler:
            data["init_parameters"]["streaming_callback"] = deserialize_callable(serialized_callback_handler)
        serialized_azure_ad_token_provider = init_params.get("azure_ad_token_provider")
        if serialized_azure_ad_token_provider:
            data["init_parameters"]["azure_ad_token_provider"] = deserialize_callable(
                serialized_azure_ad_token_provider
            )
        return default_from_dict(cls, data)
