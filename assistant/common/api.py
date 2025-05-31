import asyncio
import google.auth
import google.auth.transport.requests
import inspect
import json
import logging
import math
from typing import List, Optional

import aiohttp
import discord
import tiktoken
from openai.types.chat.chat_completion import ChatCompletion
from openai.types.chat.chat_completion_message import ChatCompletionMessage
# Used to help adapt Gemini response to be somewhat OpenAI-like for easier integration
from openai.types.chat.chat_completion import Choice as OpenAIChoice, ChatCompletion as OpenAIChatCompletion
from openai.types.chat.chat_completion_message_tool_call import ChatCompletionMessageToolCall
from openai.types.chat.chat_completion_chunk import ChoiceDeltaToolCall, ChoiceDeltaToolCallFunction
from openai.types.chat.completion_create_params import Function as OpenAIFunction
from openai.types.create_embedding_response import CreateEmbeddingResponse, Usage as OpenAIEmbeddingUsage
from openai.types.embedding import Embedding as OpenAIEmbedding
from redbot.core import commands
from redbot.core.i18n import Translator, cog_i18n
from redbot.core.utils.chat_formatting import box, humanize_number

from ..abc import MixinMeta
from .calls import request_chat_completion_raw, request_embedding_raw
from .constants import MODELS
from .models import GuildSettings

log = logging.getLogger("red.vrt.assistant.api")
_ = Translator("Assistant", __file__)


@cog_i18n(_)
class API(MixinMeta):
    async def openai_status(self) -> str:
        try:
            timeout = aiohttp.ClientTimeout(total=5)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url="https://status.openai.com/api/v2/status.json") as res:
                    data = await res.json()
                    status = data["status"]["description"]
                    # ind = data["status"]["indicator"]
        except Exception as e:
            log.error("Failed to fetch OpenAI API status", exc_info=e)
            status = _("Failed to fetch: {}").format(str(e))
        return status

    async def request_response(
        self,
        messages: List[dict],
        conf: GuildSettings,
        functions: Optional[List[dict]] = None,
        member: Optional[discord.Member] = None,
        response_token_override: int = None,
        model_override: Optional[str] = None,
        temperature_override: Optional[float] = None,
    ) -> ChatCompletionMessage:
        model_name = model_override or conf.get_user_model(member)
        
        # Determine if we are using Gemini
        is_gemini = model_name.startswith("gemini-")

        # API key and base URL determination
        api_key_to_use = None
        project_id_to_use = None
        base_url_to_use = self.db.endpoint_override # Default, can be overridden for Gemini
        using_aistudio_key = False

        if is_gemini:
            if self.db.gemini_api_key:
                api_key_to_use = self.db.gemini_api_key
                base_url_to_use = "https://generativelanguage.googleapis.com/v1beta"
                project_id_to_use = None # Not used for AI Studio keys
                using_aistudio_key = True
                log.debug("Using Gemini AI Studio API Key for chat")
            else:
                using_aistudio_key = False
                try:
                    credentials, detected_project_id = await asyncio.to_thread(
                        google.auth.default, scopes=["https://www.googleapis.com/auth/cloud-platform"]
                    )
                    if not credentials:
                        raise google.auth.exceptions.DefaultCredentialsError(_("Google Cloud credentials not found."))

                    # Refresh credentials if they are stale
                    if credentials.expired and credentials.refresh_token:
                         await asyncio.to_thread(credentials.refresh, google.auth.transport.requests.Request())

                    api_key_to_use = credentials.token # This is the Google Access Token
                except Exception as e:
                    log.error("Failed to get Google Cloud credentials for Gemini", exc_info=e)
                    raise commands.UserFeedbackCheckFailure(
                        _("Gemini Auth Error: Could not obtain Google Cloud credentials. Ensure Application Default Credentials are set up correctly or provide an AI Studio API key. Error: {}").format(e)
                    ) from e

                project_id_to_use = self.db.google_project_id or detected_project_id
                if not project_id_to_use:
                    raise commands.UserFeedbackCheckFailure(
                        _("Google Cloud Project ID not set or detected. Configure it using the bot's admin commands or ensure ADC is providing it.")
                    )
                # For Gemini with ADC, base_url is regional.
                base_url_to_use = self.db.endpoint_override or "https://us-central1-aiplatform.googleapis.com/v1"
                log.debug(f"Using Google Cloud ADC for Gemini chat. Project: {project_id_to_use}, Endpoint: {base_url_to_use}")
        else:
            api_key_to_use = conf.api_key
            base_url_to_use = self.db.endpoint_override


        max_convo_tokens = self.get_max_tokens(conf, member) # Max tokens for the *conversation*
        max_response_tokens_user_setting = conf.get_user_max_response_tokens(member) # User's desired max for the *response*

        current_convo_tokens = await self.count_payload_tokens(messages, model_name)
        if functions:
            current_convo_tokens += await self.count_function_tokens(functions, model_name)

        # Dynamically adjust OpenAI model_name to lower cost if applicable
        if not is_gemini:
            if "-16k" in model_name and current_convo_tokens < 3000:
                model_name = model_name.replace("-16k", "")
            if "-32k" in model_name and current_convo_tokens < 4000:
                model_name = model_name.replace("-32k", "")

        max_model_tokens = MODELS.get(model_name, 1000000 if is_gemini else 4096) # Default based on type

        # Calculate actual max_tokens for the API call (max_output_tokens for Gemini)
        # This needs to be the capacity for the response itself.
        if response_token_override:
            max_api_response_tokens = response_token_override
        elif max_response_tokens_user_setting:
             # User has a specific limit for the response size
            max_api_response_tokens = max_response_tokens_user_setting
        else:
            # Dynamic: calculate available space, ensuring it's positive
            available_for_response = max_model_tokens - current_convo_tokens
            max_api_response_tokens = max(0, available_for_response) if not is_gemini else None # Gemini often doesn't need this if not strictly limiting output

        if model_name not in MODELS: # Check against our known models list
            log.warning(f"Model {model_name} is not in internal MODELS list. Attempting to use, but may fail.")
            # Potentially switch to a default if truly unknown, but for now, let it try

        if is_gemini:
            # `model_name` for Gemini is just the model ID, e.g., "gemini-1.5-pro-latest"
            # `project_id_to_use` is determined above
            # `base_url_to_use` is the regional Vertex AI endpoint
            
            # Extract system message if present (OpenAI format uses first message if role is system)
            system_message_str = None
            processed_messages = messages
            if messages and messages[0]["role"] == "system":
                system_message_str = messages[0]["content"]
                processed_messages = messages[1:] # Pass messages without system prompt if extracted

            gemini_raw_response = await self.request_gemini_chat_completion_raw(
                model=model_name, # Just the model ID, e.g., "gemini-1.5-pro-latest"
                project_id=project_id_to_use,
                messages=processed_messages, 
                temperature=temperature_override if temperature_override is not None else conf.temperature,
                api_key=api_key_to_use, # Google Cloud Access Token
                max_tokens=max_api_response_tokens, 
                functions=functions,
                base_url=base_url_to_use,
                system_message=system_message_str,
                using_aistudio_key=using_aistudio_key,
                # seed=conf.seed, # TODO: Add seed if supported
            )
            
            # Adapt Gemini response to OpenAI's ChatCompletionMessage structure
            # This is a simplified adaptation
            final_content = ""
            tool_calls_adapted = []

            if gemini_raw_response.get("candidates"):
                candidate = gemini_raw_response["candidates"][0]
                if candidate.get("content") and candidate["content"].get("parts"):
                    for part in candidate["content"]["parts"]:
                        if "text" in part:
                            final_content += part["text"]
                        elif "functionCall" in part:
                            fc = part["functionCall"]
                            tool_calls_adapted.append(
                                ChatCompletionMessageToolCall(
                                    id=f"call_{fc['name']}_{abs(hash(json.dumps(fc['args'])))}", # Create a unique enough ID
                                    function=OpenAIFunction(name=fc["name"], arguments=json.dumps(fc["args"])),
                                    type="function",
                                )
                            )
            
            message_role = "assistant" # Gemini uses "model" for assistant responses
            
            prompt_tokens = gemini_raw_response.get("usageMetadata", {}).get("promptTokenCount", 0)
            completion_tokens = gemini_raw_response.get("usageMetadata", {}).get("candidatesTokenCount", 0)
            total_tokens = gemini_raw_response.get("usageMetadata", {}).get("totalTokenCount", 0)

            adapted_choice = OpenAIChoice(
                finish_reason="stop", # Gemini has finishReason, map it if needed
                index=0,
                message=ChatCompletionMessage(
                    content=final_content if final_content else None, 
                    role=message_role, 
                    tool_calls=tool_calls_adapted if tool_calls_adapted else None,
                    function_call=None
                ),
                logprobs=None,
            )
            
            simulated_openai_response = OpenAIChatCompletion(
                id="chatcmpl-gemini-" + str(abs(hash(final_content))), 
                choices=[adapted_choice],
                created=int(discord.utils.utcnow().timestamp()), 
                model=model_name, 
                object="chat.completion", 
                usage={
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": total_tokens,
                }
            )
            message_to_return = simulated_openai_response.choices[0].message
            
            conf.update_usage(
                model_name, 
                total_tokens,
                prompt_tokens,
                completion_tokens,
            )

        else: # OpenAI or compatible API call
            if model_name not in MODELS: 
                log.error(f"OpenAI model {model_name} is not in internal MODELS list. Switching to gpt-4o-mini.")
                model_name = "gpt-4o-mini"

            response: OpenAIChatCompletion = await request_chat_completion_raw(
                model=model_name,
                messages=messages,
                temperature=temperature_override if temperature_override is not None else conf.temperature,
                api_key=api_key_to_use,
                max_tokens=max_api_response_tokens,
                functions=functions,
                frequency_penalty=conf.frequency_penalty,
                presence_penalty=conf.presence_penalty,
                seed=conf.seed,
                base_url=base_url_to_use,
            )
            message_to_return: ChatCompletionMessage = response.choices[0].message
            conf.update_usage(
                response.model,
                response.usage.total_tokens,
                response.usage.prompt_tokens,
                response.usage.completion_tokens,
            )

        log.debug(f"MESSAGE TYPE: {type(message_to_return)}")
        return message_to_return

    async def request_embedding(self, text: str, conf: GuildSettings) -> List[float]:
        model_name = conf.embed_model
        is_gemini_provider = model_name.startswith("gemini-")
        
        api_key_to_use = None
        project_id_to_use = None
        base_url_to_use = self.db.endpoint_override
        using_aistudio_key = False

        if is_gemini_provider:
            if self.db.gemini_api_key:
                api_key_to_use = self.db.gemini_api_key
                base_url_to_use = "https://generativelanguage.googleapis.com/v1beta"
                project_id_to_use = None # Not used for AI Studio keys
                using_aistudio_key = True
                log.debug("Using Gemini AI Studio API Key for embeddings")
            else:
                using_aistudio_key = False
                try:
                    credentials, detected_project_id = await asyncio.to_thread(
                        google.auth.default, scopes=["https://www.googleapis.com/auth/cloud-platform"]
                    )
                    if not credentials:
                        raise google.auth.exceptions.DefaultCredentialsError(_("Google Cloud credentials not found for Gemini embeddings."))
                    if credentials.expired and credentials.refresh_token:
                        await asyncio.to_thread(credentials.refresh, google.auth.transport.requests.Request())
                    api_key_to_use = credentials.token
                except Exception as e:
                    log.error("Failed to get Google Cloud credentials for Gemini embedding", exc_info=e)
                    raise commands.UserFeedbackCheckFailure(
                         _("Gemini Auth Error (Embeddings): Could not obtain Google Cloud credentials or use AI Studio Key. Error: {}").format(e)
                    ) from e

                project_id_to_use = self.db.google_project_id or detected_project_id
                if not project_id_to_use:
                    raise commands.UserFeedbackCheckFailure(
                        _("Google Cloud Project ID not set or detected for Gemini embeddings. Configure it or ensure ADC provides it.")
                    )
                base_url_to_use = self.db.endpoint_override or f"https://us-central1-aiplatform.googleapis.com/v1"
                log.debug(f"Using Google Cloud ADC for Gemini embeddings. Project: {project_id_to_use}, Endpoint: {base_url_to_use}")

            gemini_response = await self.request_gemini_embedding_raw(
                text=text,
                api_key=api_key_to_use, 
                model=model_name,
                project_id=project_id_to_use, # May be None if using AI Studio Key
                base_url=base_url_to_use,
                using_aistudio_key=using_aistudio_key
            )
            # Handle different response structures for AI Studio vs Vertex AI
            if using_aistudio_key:
                # AI Studio direct embedding response
                if "embedding" not in gemini_response or "value" not in gemini_response["embedding"]:
                    log.error(f"Invalid Gemini AI Studio Embedding API response format: {gemini_response}")
                    raise commands.UserFeedbackCheckFailure(_("Invalid response format from Gemini AI Studio Embedding API."))
                embedding_values = gemini_response["embedding"]["value"]
                # AI Studio does not provide token counts in the embedding response directly
                token_count = await self.count_tokens(text, model_name)
            else:
                # Vertex AI embedding response
                if not gemini_response.get("predictions") or not gemini_response["predictions"][0].get("embeddings"):
                    log.error(f"Invalid Vertex AI Embedding API response format: {gemini_response}")
                    raise commands.UserFeedbackCheckFailure(_("Invalid response format from Vertex AI Embedding API."))
                embedding_values = gemini_response["predictions"][0]["embeddings"]["values"]
                token_count = gemini_response["predictions"][0]["embeddings"]["statistics"]["token_count"]
            
            conf.update_usage(
                model_name, 
                token_count,
                token_count, 
                0, 
            )
            return embedding_values
        else: # OpenAI or compatible
            api_key_to_use = conf.api_key # Standard OpenAI key
            response: CreateEmbeddingResponse = await self.request_openai_embedding_raw(
                text=text,
                api_key=api_key_to_use,
                model=model_name,
                base_url=base_url_to_use,
            )
            conf.update_usage(
                response.model,
                response.usage.total_tokens,
                response.usage.prompt_tokens,
                0,
            )
            return response.data[0].embedding

    async def request_gemini_embedding_raw(
        self,
        text: str,
        api_key: str,
        model: str,
        project_id: Optional[str], # Google Cloud Project ID, optional if using AI Studio key
        base_url: str,
        task_type: str = "RETRIEVAL_DOCUMENT", 
        using_aistudio_key: bool = False,
    ) -> dict: 
        """
        Makes a raw request to a Google Gemini Embedding model (Vertex AI or AI Studio).
        """
        # Construct the full model path for the endpoint
        # Example: projects/PROJECT_ID/locations/us-central1/publishers/google/models/text-embedding-004
        # Assuming 'model' is just the ID like 'text-embedding-004' or 'gemini-1.5-flash' for embeddings
        # For embeddings, the model path often includes "publishers/google/models/"
        # We'll assume a default location `us-central1` if not part of base_url or model string
        location = "us-central1" # Or extract from base_url if more complex logic is needed
        
        if using_aistudio_key:
            # AI Studio uses a different endpoint structure and payload
            # Model is usually just "embedding-001" or similar.
            # Base URL: "https://generativelanguage.googleapis.com/v1beta"
            # Key is passed in the URL for REST embedContent.
            predict_endpoint = f"{base_url}/models/{model}:embedContent?key={api_key}"
            payload = {"content": {"parts": [{"text": text}]}} # Model is in the URL, not payload
            headers = {
                "Content-Type": "application/json; charset=utf-8",
            }
        else:
            # Vertex AI
            if not project_id: # Should be ensured by caller if not using AI studio key
                raise ValueError("Project ID is required for Vertex AI Gemini embeddings.")

            if model.startswith("projects/"):
                model_path_for_endpoint = model
            else:
                model_path_for_endpoint = f"projects/{project_id}/locations/{location}/publishers/google/models/{model}"

            predict_endpoint = f"{base_url}/{model_path_for_endpoint}:predict"
            payload = {
                "instances": [{"content": text, "task_type": task_type}],
            }
            headers = { # Vertex AI uses Bearer token
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json; charset=utf-8",
            }

        timeout = aiohttp.ClientTimeout(total=120)
        async with self.bot.session.post(predict_endpoint, json=payload, headers=headers, timeout=timeout) as resp:
            if resp.status != 200:
                err_text = await resp.text()
                log.error(f"Gemini Embedding API Error ({resp.status}) hitting {predict_endpoint}: {err_text}")
                raise commands.UserFeedbackCheckFailure(
                    _("Gemini Embedding API request failed with status {status}: {error}").format(status=resp.status, error=err_text)
                )

            response_json = await resp.json()

            # Validation is now handled by the caller (request_embedding) due to different response structures
            return response_json

    async def request_openai_embedding_raw(self, text: str, api_key: str, model: str, base_url: Optional[str] = None ) -> CreateEmbeddingResponse:
        return await request_embedding_raw( 
            text=text,
            api_key=api_key,
            model=model,
            base_url=base_url,
        )

    async def request_gemini_chat_completion_raw(
        self,
        model: str,
        project_id: Optional[str], # Google Cloud Project ID, optional if using AI Studio key
        messages: List[dict],
        temperature: float,
        api_key: str,
        max_tokens: Optional[int], 
        functions: Optional[List[dict]], 
        base_url: str,
        system_message: Optional[str] = None,
        using_aistudio_key: bool = False,
    ) -> dict: 
        """
        Makes a raw request to a Google Gemini Chat Completion model (Vertex AI or AI Studio).
        """
        # Construct the full model path for the endpoint
        # Example: projects/PROJECT_ID/locations/us-central1/publishers/google/models/gemini-1.5-pro-latest
        location = "us-central1" # Or extract from base_url
        
        action = "generateContent" # Could be streamGenerateContent for streaming

        if using_aistudio_key:
            # AI Studio uses a different endpoint structure. Key is in the URL.
            model_id_for_url = model if model.startswith("models/") else f"models/{model}"
            generate_endpoint = f"{base_url}/{model_id_for_url}:{action}?key={api_key}"
            headers = {
                "Content-Type": "application/json; charset=utf-8",
            }
        else:
            # Vertex AI
            if not project_id:
                raise ValueError("Project ID is required for Vertex AI Gemini chat.")

            if model.startswith("projects/"):
                model_path_for_endpoint = model
            else:
                model_path_for_endpoint = f"projects/{project_id}/locations/{location}/publishers/google/models/{model}"
            generate_endpoint = f"{base_url}/{model_path_for_endpoint}:{action}"
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json; charset=utf-8",
            }

        gemini_contents = []
        for msg in messages:
            role = "user" if msg["role"] == "user" else "model" 
            
            if msg["role"] == "tool" or msg["role"] == "function": 
                gemini_contents.append({
                    "role": "function", 
                    "parts": [{
                        "functionResponse": {
                            "name": msg.get("name") or msg.get("tool_call_id", "unknown_function"), 
                            "response": {"content": msg["content"]}, 
                        }
                    }]
                })
                continue

            if isinstance(msg.get("content"), list): 
                parts = []
                for item in msg["content"]:
                    if item["type"] == "text":
                        parts.append({"text": item["text"]})
                    elif item["type"] == "image_url":
                        image_url_data = item["image_url"]["url"]
                        if image_url_data.startswith("data:image/"): 
                            mime_type, base64_data = image_url_data.split(";", 1)[0].split(":")[1], image_url_data.split(",", 1)[1]
                            parts.append({"inlineData": {"mimeType": mime_type, "data": base64_data}})
                        else: 
                            log.warning(f"Direct image URL {image_url_data} might not be supported by Gemini API. Consider inlineData or fileData.")
                            parts.append({"text": f"[Image available at: {image_url_data}]"}) 
                gemini_contents.append({"role": role, "parts": parts})
            elif isinstance(msg.get("content"), str): 
                 gemini_contents.append({"role": role, "parts": [{"text": msg["content"]}]})

        payload = {"contents": gemini_contents}
        
        generation_config = {}
        if temperature is not None:
            generation_config["temperature"] = temperature
        if max_tokens is not None: 
            generation_config["maxOutputTokens"] = max_tokens

        if generation_config:
            payload["generationConfig"] = generation_config

        if system_message:
            payload["systemInstruction"] = {"parts": [{"text": system_message}]} # AI Studio format for system prompt

        if functions: 
            gemini_tools = []
            function_declarations = []
            for func_schema in functions:
                # Ensure parameters is a dict, even if empty, for Gemini schema
                params = func_schema.get("parameters")
                if params is None or not isinstance(params, dict) or not params.get("properties"):
                     # Gemini needs parameters to be a valid OpenAPI schema object.
                     # If it's missing or not structured correctly, provide a default empty one.
                    params = {"type": "object", "properties": {}}

                function_declarations.append({
                    "name": func_schema["name"],
                    "description": func_schema.get("description", ""),
                    "parameters": params,
                })

            if function_declarations:
                 gemini_tools.append({"functionDeclarations": function_declarations})
            if gemini_tools:
                payload["tools"] = gemini_tools
        
        # Headers are defined above based on using_aistudio_key

        timeout = aiohttp.ClientTimeout(total=300) 
        async with self.bot.session.post(generate_endpoint, json=payload, headers=headers, timeout=timeout) as resp:
            if resp.status != 200:
                err_text = await resp.text()
                log.error(f"Gemini API Error ({resp.status}) hitting {generate_endpoint}: {err_text}\nPayload: {json.dumps(payload, indent=2)}")
                raise commands.UserFeedbackCheckFailure(
                     _("Gemini API request failed with status {status}: {error}").format(status=resp.status, error=err_text)
                )
            try:
                response_json = await resp.json()
            except aiohttp.ContentTypeError:
                err_text = await resp.text()
                log.error(f"Gemini API Error: Non-JSON response from {generate_endpoint}. Response: {err_text}")
                raise commands.UserFeedbackCheckFailure(
                    _("Gemini API returned a non-JSON response.")
                )

            if not response_json.get("candidates") and not response_json.get("error"):
                if response_json.get("promptFeedback", {}).get("blockReason"):
                    block_reason = response_json["promptFeedback"]["blockReason"]
                    log.warning(f"Gemini request blocked. Reason: {block_reason}. Details: {response_json['promptFeedback']}")
                    raise commands.UserFeedbackCheckFailure(
                        _("Content blocked by Gemini due to: {reason}").format(reason=block_reason)
                    )
                log.error(f"Invalid Gemini API response format (no candidates or error): {response_json} from {generate_endpoint}")
                raise commands.UserFeedbackCheckFailure(_("Invalid response format from Gemini API (no candidates or error field)."))
            elif response_json.get("error"):
                error_details = response_json["error"]
                log.error(f"Gemini API returned an error: {error_details} from {generate_endpoint}")
                raise commands.UserFeedbackCheckFailure(
                    _("Gemini API error: {message} (Code: {code})").format(message=error_details.get("message","Unknown"), code=error_details.get("code", "N/A"))
                )

            return response_json

    # -------------------------------------------------------
    # -------------------------------------------------------
    # ----------------------- HELPERS -----------------------
    # -------------------------------------------------------
    # -------------------------------------------------------

    async def count_payload_tokens(self, messages: List[dict], model_name: str = "gpt-4o-mini") -> int:
        if model_name.startswith("gemini-"):
            num_tokens = 0
            for message in messages:
                content = message.get("content")
                if isinstance(content, str):
                    num_tokens += len(content) 
                elif isinstance(content, list): 
                    for item in content:
                        if item["type"] == "text":
                             num_tokens += len(item["text"]) 
            log.debug(f"Rough token estimate for Gemini model '{model_name}': {num_tokens} (character count based)")
            return num_tokens 

        if not messages:
            return 0

        def _count_payload_openai():
            try:
                encoding = tiktoken.encoding_for_model(model_name)
            except KeyError:
                log.warning(f"Tiktoken encoding not found for model {model_name}. Using o200k_base.")
                encoding = tiktoken.get_encoding("o200k_base")

            tokens_per_message = 3
            tokens_per_name = 1
            num_tokens = 0
            for message in messages:
                num_tokens += tokens_per_message
                for key, value in message.items():
                    if key == "content" and value is None: 
                        continue
                    if isinstance(value, list) and key == "content": 
                        for item in value:
                            if item.get("type") == "text" and item.get("text"):
                                num_tokens += len(encoding.encode(str(item["text"])))
                    elif isinstance(value, str):
                         num_tokens += len(encoding.encode(value))
                    else: 
                        num_tokens += len(encoding.encode(json.dumps(value)))

                    if key == "name":
                        num_tokens += tokens_per_name
            num_tokens += 3  
            return num_tokens

        return await asyncio.to_thread(_count_payload_openai)

    async def count_function_tokens(self, functions: List[dict], model_name: str = "gpt-4o-mini") -> int:
        if model_name.startswith("gemini-"):
            if not functions:
                return 0
            try:
                json_str = json.dumps(functions)
                log.debug(f"Rough function token estimate for Gemini model '{model_name}': {len(json_str)} (character count of JSON)")
                return len(json_str) 
            except Exception as e:
                log.error(f"Error estimating function tokens for Gemini: {e}")
                return 0 

        if not functions:
            return 0
            
        func_init = 0
        prop_init = 0
        prop_key = 0
        enum_init = 0
        enum_item = 0
        func_end = 0

        if model_name in [
            "gpt-4o",
            "gpt-4o-2024-05-13",
            "gpt-4o-2024-08-06",
            "gpt-4o-2024-11-20",
            "gpt-4o-mini",
            "gpt-4o-mini-2024-07-18",
            "gpt-4.1",
            "gpt-4.1-mini",
            "gpt-4.1-nano",
            "o1-preview",
            "o1-preview-2024-09-12",
            "o1",
            "o1-2024-12-17",
            "o1-mini",
            "o1-mini-2024-09-12",
            "o3-mini",
            "o3-mini-2025-01-31",
        ]:
            func_init = 7
            prop_init = 3
            prop_key = 3
            enum_init = -3
            enum_item = 3
            func_end = 12
        elif model_name in [
            "gpt-3.5-turbo-1106",
            "gpt-3.5-turbo-0125",
            "gpt-4",
            "gpt-4-turbo",
            "gpt-4-turbo-preview",
            "gpt-4-0125-preview",
            "gpt-4-1106-preview",
        ] or model_name.startswith("gpt-4o") or model_name.startswith("gpt-4.1"): 
            func_init = 10
            prop_init = 3
            prop_key = 3
            enum_init = -3
            enum_item = 3
            func_end = 12
        else:
            log.warning(f"Incompatible model for function token counting: {model_name}")

        def _count_tokens():
            try:
                encoding = tiktoken.encoding_for_model(model_name)
            except KeyError:
                encoding = tiktoken.get_encoding("o200k_base")

            func_token_count = 0
            if len(functions) > 0:
                for f in functions:
                    if "function" not in f.keys():
                        f = {"function": f, "name": f["name"], "description": f["description"]}
                    func_token_count += func_init  
                    function = f["function"]
                    f_name = function["name"]
                    f_desc = function["description"]
                    if f_desc.endswith("."):
                        f_desc = f_desc[:-1]
                    line = f_name + ":" + f_desc
                    func_token_count += len(encoding.encode(line))  
                    if len(function["parameters"]["properties"]) > 0:
                        func_token_count += prop_init  
                        for key in list(function["parameters"]["properties"].keys()):
                            func_token_count += prop_key  
                            p_name = key
                            p_type = function["parameters"]["properties"][key].get("type", "")
                            p_desc = function["parameters"]["properties"][key].get("description", "")
                            if "enum" in function["parameters"]["properties"][key].keys():
                                func_token_count += enum_init  
                                for item in function["parameters"]["properties"][key]["enum"]:
                                    func_token_count += enum_item
                                    func_token_count += len(encoding.encode(item))
                            if p_desc.endswith("."):
                                p_desc = p_desc[:-1]
                            line = f"{p_name}:{p_type}:{p_desc}"
                            func_token_count += len(encoding.encode(line))
                func_token_count += func_end
            return func_token_count
        return await asyncio.to_thread(_count_tokens)

    async def get_tokens(self, text: str, model_name: str = "gpt-4o-mini") -> list[int]:
        if not text:
            log.debug("No text to get tokens from!")
            return []
        if isinstance(text, bytes):
            text = text.decode(encoding="utf-8", errors="ignore") 

        if model_name.startswith("gemini-"):
            log.warning(f"get_tokens called for Gemini model '{model_name}'. Returning character codes as placeholder.")
            return [ord(c) for c in text]

        def _get_encoding_openai():
            try:
                enc = tiktoken.encoding_for_model(model_name)
            except KeyError:
                log.warning(f"Tiktoken encoding not found for model {model_name}. Using o200k_base.")
                enc = tiktoken.get_encoding("o200k_base")
            return enc

        encoding = await asyncio.to_thread(_get_encoding_openai)
        return await asyncio.to_thread(encoding.encode, text)

    async def count_tokens(self, text: str, model_name: str) -> int:
        if not text:
            log.debug("No text to get token count from!")
            return 0
        
        if model_name.startswith("gemini-"):
            char_count = len(text)
            log.debug(f"Rough token estimate for Gemini model '{model_name}' (text): {char_count} (character count)")
            return char_count 

        try:
            tokens = await self.get_tokens(text, model_name) 
            return len(tokens)
        except TypeError as e:
            log.error(f"Failed to count tokens for '{model_name}': {text}", exc_info=e)
            return 0

    async def can_call_llm(self, conf: GuildSettings, ctx: Optional[commands.Context] = None) -> bool:
        model_name = conf.get_user_model(ctx.author if ctx else None)
        is_gemini = model_name.startswith("gemini-")

        if is_gemini:
            # If gemini_api_key is set, we can call the LLM.
            if self.db.gemini_api_key:
                return True

            # If no AI Studio key, check ADC for Vertex AI, which requires a project ID.
            if not self.db.google_project_id:
                if ctx:
                    await ctx.send(_("Google Cloud Project ID is not set and no Gemini API Key is available. This is required for Gemini models. Please use the admin command to set one of these."))
                return False
            try:
                # Try to get credentials to check if ADC is set up
                credentials, _ = await asyncio.to_thread(google.auth.default)
                if not credentials:
                    if ctx:
                        await ctx.send(_("Google Cloud credentials not found (and no AI Studio key set). Ensure Application Default Credentials (ADC) are configured in the bot's environment."))
                    return False
            except Exception as e:
                if ctx:
                    await ctx.send(_("Failed to acquire Google Cloud credentials (and no AI Studio key set): {}. Ensure ADC is configured.").format(e))
                log.error("ADC check failed for Gemini (no AI Studio key set)", exc_info=e)
                return False
            return True
        else: # OpenAI or other non-Gemini
            if not conf.api_key and not self.db.endpoint_override:
                if ctx:
                    txt = _("There are no API keys set for LLM interaction!\n")
                    if ctx.author.id == ctx.guild.owner_id: 
                        txt += _("- Set your OpenAI API key with `{cmd}assist openaikey`\n").format(cmd=ctx.clean_prefix)
                    await ctx.send(txt)
                return False
            return True


    async def resync_embeddings(self, conf: GuildSettings) -> int:
        """Update embeds to match current dimensions or model type."""
        if not conf.embeddings:
            return 0
        
        sample_key = list(conf.embeddings.keys())[0] if conf.embeddings else None
        if not sample_key:
            return 0 # No embeddings to sample or resync

        sample_text_for_probing = conf.embeddings[sample_key].text
        try:
            sample_embed_vector = await self.request_embedding(sample_text_for_probing, conf)
        except Exception as e:
            log.error(f"Failed to get sample embedding during resync: {e}. Aborting resync.")
            return 0

        target_dimension = len(sample_embed_vector)
        target_model_name = conf.embed_model 

        synced_count = 0
        tasks = []

        for name, em_data in conf.embeddings.items():
            if em_data.model != target_model_name or len(em_data.embedding) != target_dimension:
                log.info(f"Resyncing embedding for '{name}': model mismatch ('{em_data.model}' vs '{target_model_name}') or dim mismatch ({len(em_data.embedding)} vs {target_dimension}).")
                
                async def update_task(n, text_to_embed, current_conf):
                    try:
                        new_embedding_vector = await self.request_embedding(text_to_embed, current_conf)
                        current_conf.embeddings[n].embedding = new_embedding_vector
                        current_conf.embeddings[n].model = current_conf.embed_model 
                        current_conf.embeddings[n].update() 
                        log.debug(f"Successfully updated embedding for '{n}' to model '{current_conf.embed_model}'.")
                        return 1
                    except Exception as e_update:
                        log.error(f"Failed to update embedding for '{n}' during resync: {e_update}")
                        return 0

                tasks.append(update_task(name, em_data.text, conf))

        if tasks:
            results = await asyncio.gather(*tasks)
            synced_count = sum(results)
            if synced_count > 0:
                log.info(f"Resynced {synced_count} embeddings successfully.")
        
        return synced_count


    def get_max_tokens(self, conf: GuildSettings, user: Optional[discord.Member]) -> int:
        user_max_convo_tokens = conf.get_user_max_tokens(user) 
        model_name = conf.get_user_model(user)
        
        default_for_gemini = 1000000 if "1.5" in model_name or "2." in model_name else 32000
        max_model_total_tokens = MODELS.get(model_name, default_for_gemini if model_name.startswith("gemini-") else 4096)

        if not user_max_convo_tokens or user_max_convo_tokens > max_model_total_tokens:
            return max_model_total_tokens 
        return user_max_convo_tokens 

    async def cut_text_by_tokens(self, text: str, conf: GuildSettings, user: Optional[discord.Member] = None) -> str:
        if not text:
            log.debug("No text to cut by tokens!")
            return text
        
        model_name = conf.get_user_model(user)
        max_tokens_for_context = self.get_max_tokens(conf, user)
        tokens = await self.get_tokens(text, model_name) 
        cut_tokens = tokens[:max_tokens_for_context]
        return await self.get_text(cut_tokens, model_name) 

    async def get_text(self, tokens: list, model_name: str = "gpt-4o-mini") -> str:
        if model_name.startswith("gemini-"):
            try:
                return "".join([chr(t) for t in tokens])
            except TypeError: 
                log.error(f"Cannot decode Gemini tokens for model {model_name} as char codes. Tokens: {tokens[:10]}")
                return "" 

        def _get_encoding_openai():
            try:
                enc = tiktoken.encoding_for_model(model_name)
            except KeyError:
                log.warning(f"Tiktoken encoding not found for model {model_name}. Using o200k_base.")
                enc = tiktoken.get_encoding("o200k_base")
            return enc

        encoding = await asyncio.to_thread(_get_encoding_openai)
        return await asyncio.to_thread(encoding.decode, tokens, errors="ignore") 

    # -------------------------------------------------------
    # -------------------------------------------------------
    # -------------------- FORMATTING -----------------------
    # -------------------------------------------------------
    # -------------------------------------------------------
    async def degrade_conversation(
        self,
        messages: List[dict],
        function_list: List[dict],
        conf: GuildSettings,
        user: Optional[discord.Member],
    ) -> bool:
        """
        Iteratively degrade a conversation payload in-place to fit within the max token limit, prioritizing more recent messages and critical context.

        Order of importance:
        - System messages
        - Function calls available to model
        - Most recent user message
        - Most recent assistant message
        - Most recent function/tool message

        System messages are always ignored.

        Args:
            messages (List[dict]): message entries sent to the api
            function_list (List[dict]): list of json function schemas for the model
            conf: (GuildSettings): current settings

        Returns:
            bool: whether the conversation was degraded
        """
        # Fetch the current model the user is using
        model = conf.get_user_model(user)
        # Fetch the max token limit for the current user
        max_tokens = self.get_max_tokens(conf, user)
        # Token count of current conversation
        convo_tokens = await self.count_payload_tokens(messages, model)
        # Token count of function calls available to model
        function_tokens = await self.count_function_tokens(function_list, model)

        total_tokens = convo_tokens + function_tokens

        # Check if the total token count is already under the max token limit
        if total_tokens <= max_tokens:
            return False

        log.debug(f"Degrading messages for {user} (total: {total_tokens}/max: {max_tokens})")

        def count(role: str):
            return sum(1 for msg in messages if msg["role"] == role)

        async def pop(role: str) -> int:
            for idx, msg in enumerate(messages):
                if msg["role"] != role:
                    continue
                removed = messages.pop(idx)
                reduction = 4
                if "name" in removed:
                    reduction += 1
                if content := removed.get("content"):
                    if isinstance(content, list):
                        for i in content:
                            if i["type"] == "text":
                                reduction += await self.count_tokens(i["text"], model)
                            else:
                                reduction += 2
                    else:
                        reduction += await self.count_tokens(str(content), model)
                elif tool_calls := removed.get("tool_calls"):
                    reduction += await self.count_tokens(str(tool_calls), model)
                elif function_call := removed.get("function_call"):
                    reduction += await self.count_tokens(str(function_call), model)
                return reduction
            return 0

        # We will NOT remove the most recent user message or assistant message
        # We will also not touch system messages
        # We will also not touch function calls available to model (yet)
        iters = 0
        while True:
            iters += 1
            break_conditions = [
                count("user") <= 1,
                count("assistant") <= 1,
                iters > 100,
            ]
            if any(break_conditions):
                break
            # First we will iterate through the messages and remove in the following sweep order:
            # 1. Remove oldest tool call or response
            reduced = await pop("tool")
            if reduced:
                total_tokens -= reduced
                if total_tokens <= max_tokens:
                    break
            reduced = await pop("function")
            if reduced:
                total_tokens -= reduced
                if total_tokens <= max_tokens:
                    break
            # 2. Remove oldest assistant message
            reduced = await pop("assistant")
            if reduced:
                total_tokens -= reduced
                if total_tokens <= max_tokens:
                    break
            # 3. Remove oldest user message
            reduced = await pop("user")
            if reduced:
                total_tokens -= reduced
                if total_tokens <= max_tokens:
                    break
            # Then we will repeat the process until we are under the max token limit

        log.debug(f"Convo degradation finished for {user} (total: {total_tokens}/max: {max_tokens})")
        return True

    async def token_pagify(self, text: str, conf: GuildSettings) -> List[str]:
        """Pagify a long string by tokens rather than characters"""
        if not text:
            log.debug("No text to pagify!")
            return []
        token_chunks = []
        tokens = await self.get_tokens(text)
        current_chunk = []

        max_tokens = min(conf.max_tokens - 100, MODELS[conf.model])
        for token in tokens:
            current_chunk.append(token)
            if len(current_chunk) == max_tokens:
                token_chunks.append(current_chunk)
                current_chunk = []

        if current_chunk:
            token_chunks.append(current_chunk)

        text_chunks = []
        for chunk in token_chunks:
            text = await self.get_text(chunk)
            text_chunks.append(text)

        return text_chunks

    # -------------------------------------------------------
    # -------------------------------------------------------
    # ----------------------- EMBEDS ------------------------
    # -------------------------------------------------------
    # -------------------------------------------------------
    async def get_function_menu_embeds(self, user: discord.Member) -> List[discord.Embed]:
        func_dump = {k: v.model_dump(exclude_defaults=False) for k, v in self.db.functions.items()}
        registry = {"Assistant-Custom": func_dump}
        for cog_name, function_schemas in self.registry.items():
            cog = self.bot.get_cog(cog_name)
            if not cog:
                continue
            for function_name, data in function_schemas.items():
                function_schema = data["schema"]
                function_obj = getattr(cog, function_name, None)
                if function_obj is None:
                    continue
                if cog_name not in registry:
                    registry[cog_name] = {}
                registry[cog_name][function_name] = {
                    "code": inspect.getsource(function_obj),
                    "jsonschema": function_schema,
                    "permission_level": data["permission_level"],
                }

        conf = self.db.get_conf(user.guild)
        model = conf.get_user_model(user)

        pages = sum(len(v) for v in registry.values())
        page = 1
        embeds = []
        for cog_name, functions in registry.items():
            for function_name, data in functions.items():
                embed = discord.Embed(
                    title=_("Custom Functions"),
                    description=function_name,
                    color=discord.Color.blue(),
                )
                if cog_name != "Assistant-Custom":
                    embed.add_field(
                        name=_("3rd Party"),
                        value=_("This function is managed by the `{}` cog").format(cog_name),
                        inline=False,
                    )
                elif cog_name == "Assistant":
                    embed.add_field(
                        name=_("Internal Function"),
                        value=_("This is an internal command that can only be used when interacting with a tutor"),
                        inline=False,
                    )
                schema = json.dumps(data["jsonschema"], indent=2)
                tokens = await self.count_tokens(schema, model)

                schema_text = _("This function consumes `{}` input tokens each call\n").format(humanize_number(tokens))

                if user.id in self.bot.owner_ids:
                    if len(schema) > 900:
                        schema_text += box(schema[:900] + "...", "py")
                    else:
                        schema_text += box(schema, "py")

                    if len(data["code"]) > 900:
                        code_text = box(data["code"][:900] + "...", "py")
                    else:
                        code_text = box(data["code"], "py")

                else:
                    schema_text += box(data["jsonschema"]["description"], "json")
                    code_text = box(_("Hidden..."))

                embed.add_field(name=_("Permission Level"), value=data["permission_level"].capitalize(), inline=False)
                embed.add_field(name=_("Schema"), value=schema_text, inline=False)
                embed.add_field(name=_("Code"), value=code_text, inline=False)

                embed.set_footer(text=_("Page {}/{}").format(page, pages))
                embeds.append(embed)
                page += 1

        if not embeds:
            embeds.append(
                discord.Embed(
                    description=_("No custom code has been added yet!"),
                    color=discord.Color.purple(),
                )
            )
        return embeds

    async def get_embbedding_menu_embeds(self, conf: GuildSettings, place: int) -> List[discord.Embed]:
        embeddings = sorted(conf.embeddings.items(), key=lambda x: x[0])
        embeds = []
        pages = math.ceil(len(embeddings) / 5)
        model = conf.get_user_model()
        start = 0
        stop = 5
        for page in range(pages):
            stop = min(stop, len(embeddings))
            embed = discord.Embed(title=_("Embeddings"), color=discord.Color.blue())
            embed.set_footer(text=_("Page {}/{}").format(page + 1, pages))
            num = 0
            for i in range(start, stop):
                name, embedding = embeddings[i]
                tokens = await self.count_tokens(embedding.text, model)
                text = (
                    box(f"{embedding.text[:30].strip()}...")
                    if len(embedding.text) > 33
                    else box(embedding.text.strip())
                )
                val = _(
                    "`Created:    `{}\n"
                    "`Modified:   `{}\n"
                    "`Tokens:     `{}\n"
                    "`Dimensions: `{}\n"
                    "`AI Created: `{}\n"
                    "`Model:      `{}\n"
                ).format(
                    embedding.created_at(),
                    embedding.modified_at(relative=True),
                    tokens,
                    len(embedding.embedding),
                    embedding.ai_created,
                    conf.embed_model,
                )
                val += text
                fieldname = f"➣ {name}" if place == num else name
                embed.add_field(
                    name=fieldname[:250],
                    value=val,
                    inline=False,
                )
                num += 1
            embeds.append(embed)
            start += 5
            stop += 5
        if not embeds:
            embeds.append(discord.Embed(description=_("No embeddings have been added!"), color=discord.Color.purple()))
        return embeds
