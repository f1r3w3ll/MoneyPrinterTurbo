"""
Script Generation Service with Multi-LLM Support

Supports: OpenAI, Claude (Anthropic), Gemini, DeepSeek, Kimi, Qwen
"""

import json
import os
import re
import ssl
import time
from typing import Dict, Optional, Tuple
import httpx
from loguru import logger

from app.models.schema import (
    ScriptGenerationRequest,
    StructuredScript,
    SceneInfo,
    LLMProvider,
)
from app.config import config
from app.services.script_parser import ScriptParser


def _anthropic_http_client():
    """Use Windows trusted certificates when an inspected network inserts a CA."""
    if os.name != 'nt':
        return None
    try:
        context = ssl.create_default_context()
        for certificate, encoding, _trust in ssl.enum_certificates('ROOT'):
            if encoding == 'x509_asn':
                context.load_verify_locations(cadata=ssl.DER_cert_to_PEM_cert(certificate))
        return httpx.Client(verify=context, timeout=240)
    except Exception as exc:
        logger.warning(f'Não foi possível carregar certificados do Windows para Claude: {exc}')
        return None


class ScriptGeneratorService:
    """Generate structured scripts for long-form videos using various LLM providers"""

    def __init__(self):
        self.llm_configs = self._load_llm_configs()

    def _load_llm_configs(self) -> Dict:
        """Load LLM configurations from config"""
        return {
            "openai": config.llm.get("openai", {}),
            "claude": config.llm.get("claude", {}),
            "gemini": config.llm.get("gemini", {}),
            "deepseek": config.llm.get("deepseek", {}),
            "kimi": config.llm.get("kimi", {}),
            "qwen": config.llm.get("qwen", {}),
        }

    def generate_script(
        self, request: ScriptGenerationRequest
    ) -> Tuple[StructuredScript, str, float, Optional[int]]:
        """
        Generate structured script using specified LLM provider

        Returns:
            (script, model_used, generation_time, token_count)
        """
        start_time = time.time()

        provider = request.llm_provider.value
        logger.info(f"Generating script with {provider} for topic: {request.topic}")

        # Get LLM configuration
        llm_config = self.llm_configs.get(provider, {})
        if not llm_config or not llm_config.get("api_key"):
            raise ValueError(f"LLM provider {provider} not configured or missing API key")
        if not llm_config.get('enabled', True):
            raise ValueError(f'O provedor {provider} está desabilitado nas configurações.')

        target_scenes = self._target_scene_count(request)
        if target_scenes > 12:
            script, model, tokens = self._generate_script_batches(request, llm_config, target_scenes)
        else:
            script_json, model, tokens = self._generate_provider(
                provider, self._build_prompt(request), llm_config
            )
            script = self._parse_script_json(script_json, request)

        generation_time = time.time() - start_time
        logger.info(
            f"Script generated successfully in {generation_time:.2f}s using {model}"
        )

        return script, model, generation_time, tokens

    @staticmethod
    def _target_scene_count(request: ScriptGenerationRequest) -> int:
        return request.num_scenes or max(5, int(request.duration_minutes * 60 / 25))

    def _generate_provider(self, provider: str, prompt: str, llm_config: Dict):
        generators = {
            'openai': self._generate_openai, 'claude': self._generate_claude,
            'gemini': self._generate_gemini, 'deepseek': self._generate_deepseek,
            'kimi': self._generate_kimi, 'qwen': self._generate_qwen,
        }
        generator = generators.get(provider)
        if not generator:
            raise ValueError(f"Unsupported LLM provider: {provider}")
        return generator(prompt, llm_config)

    def _generate_script_batches(self, request, llm_config, target_scenes):
        batch_sizes = []
        remaining = target_scenes
        while remaining:
            batch_size = min(12, remaining)
            if remaining - batch_size and remaining - batch_size < 5:
                batch_size = remaining
            batch_sizes.append(batch_size)
            remaining -= batch_size

        scripts, model, token_count = [], None, 0
        offset = 0
        for batch_index, batch_size in enumerate(batch_sizes, start=1):
            batch_request = request.model_copy(update={
                'num_scenes': batch_size,
                'duration_minutes': request.duration_minutes * batch_size / target_scenes,
                'custom_instructions': (request.custom_instructions or '') + (
                    f'\nThis is batch {batch_index} of {len(batch_sizes)}, covering scenes '
                    f'{offset + 1}-{offset + batch_size} of one continuous video. '
                    'Return exactly this batch of scenes. Only the first batch opens the video; '
                    'only the final batch concludes it.'
                ),
            })
            content, model, tokens = self._generate_provider(
                request.llm_provider.value, self._build_prompt(batch_request), llm_config
            )
            parsed = self._parse_script_json(content, batch_request)
            if len(parsed.scenes) < batch_size:
                retry_request = batch_request.model_copy(update={
                    'custom_instructions': (batch_request.custom_instructions or '') + (
                        f'\nYour previous response returned too few scenes. Return exactly {batch_size} '
                        'complete scenes for this batch; do not shorten or omit any scene.'
                    ),
                })
                content, model, retry_tokens = self._generate_provider(
                    request.llm_provider.value, self._build_prompt(retry_request), llm_config
                )
                parsed = self._parse_script_json(content, retry_request)
                tokens = (tokens or 0) + (retry_tokens or 0)
            if len(parsed.scenes) < batch_size:
                raise ValueError(
                    f'Batch {batch_index} returned {len(parsed.scenes)} scenes after one retry; '
                    f'expected {batch_size}.'
                )
            for scene in parsed.scenes[:batch_size]:
                scene.index = offset
                offset += 1
            scripts.append(parsed)
            token_count += tokens or 0

        first = scripts[0]
        metadata = dict(first.metadata or {})
        metadata.update({
            'target_duration_seconds': int(request.duration_minutes * 60),
            'target_scene_count': target_scenes,
            'script_language': request.language,
            'script_llm_provider': request.llm_provider.value,
            'generation_batches': len(batch_sizes),
        })
        return StructuredScript(
            title=first.title,
            description=first.description,
            total_duration_estimate=int(request.duration_minutes * 60),
            scenes=[scene for script in scripts for scene in script.scenes],
            metadata=metadata,
        ), model, token_count

    def generate_editorial_json(self, provider: str, prompt: str) -> str:
        """Generate a small JSON editorial artifact with the configured LLM."""
        provider = provider.value if isinstance(provider, LLMProvider) else str(provider)
        llm_config = self.llm_configs.get(provider, {})
        if not llm_config or not llm_config.get("api_key"):
            raise ValueError(f"LLM provider {provider} not configured or missing API key")
        if not llm_config.get('enabled', True):
            raise ValueError(f'O provedor {provider} está desabilitado nas configurações.')

        generators = {
            'openai': self._generate_openai,
            'claude': self._generate_claude,
            'gemini': self._generate_gemini,
            'deepseek': self._generate_deepseek,
            'kimi': self._generate_kimi,
            'qwen': self._generate_qwen,
        }
        generator = generators.get(provider)
        if not generator:
            raise ValueError(f"Unsupported LLM provider: {provider}")
        content, _, _ = generator(prompt, llm_config)
        return content

    def correct_script_duration(
        self, script: StructuredScript, provider: str
    ) -> StructuredScript:
        """Perform one bounded narration-only rewrite to meet the time target."""
        metadata = dict(script.metadata or {})
        attempts = int(metadata.get("duration_correction_attempts", 0))
        if attempts >= 1:
            raise ValueError("A correção automática de duração já foi usada neste roteiro.")

        target_seconds = int(metadata.get("target_duration_seconds") or script.total_duration_estimate)
        language = metadata.get("script_language", "pt-BR")
        chars_per_second = ScriptParser.chars_per_second_for(language)
        narration_budget = int(target_seconds * chars_per_second)
        current_duration = ScriptParser().estimate_total_duration(script, language=language)
        source_script = script.model_dump()
        prompt = f"""You are revising an existing structured YouTube script.

Rewrite only the narration so it reaches the requested duration while preserving the topic, facts, narrative flow, scene count, image prompts, transitions, title, description, and metadata.

**Duration target:** {target_seconds} seconds in {language}
**Narration budget:** about {narration_budget:,} characters total
**Current narration estimate:** {current_duration:.0f} seconds

The current script is below or above the target. Expand or condense every scene proportionally with concrete, useful narration. Do not add filler, duplicate points, new unsupported claims, or placeholder text. Keep every existing JSON field and return the complete corrected script as JSON only.

**Current script:**
{json.dumps(source_script, ensure_ascii=False)}
"""
        content = self.generate_editorial_json(provider, prompt)
        try:
            corrected_data = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ValueError(f"A IA retornou uma correção inválida: {exc}") from exc

        # This operation is narration-only. Providers occasionally rewrite a
        # scene duration or visual field despite the instruction, which can
        # make an otherwise valid correction fail the production parser.
        original_scenes = {scene["index"]: scene for scene in source_script["scenes"]}
        for scene in corrected_data.get("scenes", []):
            original_scene = original_scenes.get(scene.get("index"))
            if not original_scene:
                continue
            for field in (
                "image_prompt", "duration_seconds", "transition",
                "narrative_role", "visual_function", "open_loop", "source_note",
            ):
                scene[field] = original_scene.get(field)
        corrected_data["title"] = source_script["title"]
        corrected_data["description"] = source_script.get("description", "")
        corrected_data["total_duration_estimate"] = source_script["total_duration_estimate"]
        corrected_data["metadata"] = source_script.get("metadata", {})
        request = ScriptGenerationRequest(
            topic=script.title,
            duration_minutes=target_seconds / 60,
            language=language,
            llm_provider=provider,
        )
        corrected = self._parse_script_json(json.dumps(corrected_data), request)
        corrected.metadata = {
            **dict(corrected.metadata or {}),
            **metadata,
            "duration_correction_attempts": attempts + 1,
        }
        return corrected

    def _build_prompt(self, request: ScriptGenerationRequest) -> str:
        """Build LLM prompt for script generation"""
        # Calculate number of scenes if not provided
        num_scenes = self._target_scene_count(request)  # ~25s per scene
        target_seconds = int(request.duration_minutes * 60)
        chars_per_second = ScriptParser.chars_per_second_for(request.language)
        narration_budget = int(target_seconds * chars_per_second)
        narration_per_scene = int(narration_budget / num_scenes)
        narration_minimum = int(narration_per_scene * 0.8)
        narration_maximum = int(narration_per_scene * 1.2)

        prompt = f"""You are a professional video script writer. Generate a structured script for a long-form YouTube video.

**Requirements:**
- Topic: {request.topic}
- Duration: {request.duration_minutes} minutes ({target_seconds} seconds)
- Number of scenes: {num_scenes}
- Language: {request.language}
- Style: {request.style}
- Narration budget: about {narration_budget:,} characters in total. This is required so the generated audio reaches the requested duration.
- Per-scene narration: aim for {narration_per_scene:,} characters; keep every scene between {narration_minimum:,} and {narration_maximum:,} characters unless a short transition is essential.
"""

        if request.target_audience:
            prompt += f"- Target audience: {request.target_audience}\n"

        if request.keywords:
            prompt += f"- Keywords to include: {', '.join(request.keywords)}\n"

        if request.custom_instructions:
            prompt += f"\n**Additional instructions:**\n{request.custom_instructions}\n"

        if request.editorial_context:
            editorial = json.dumps(request.editorial_context, ensure_ascii=False, indent=2)
            prompt += f"""
**Editorial direction (follow it exactly):**
{editorial}

Keep the chosen packaging promise. Do not use a title that promises something the
script does not answer. Treat source notes as verification leads, never as proof
of a claim that you cannot support.
"""
            cta = request.editorial_context.get("cta") or {}
            cta_text = str(cta.get("text") or "").strip() if cta.get("enabled") else ""
            if cta_text:
                prompt += f"""
Use this exact call-to-action only in the scene whose narrative_role is CTA:
{cta_text}
Do not repeat it in any other scene.
"""

        prompt += f"""
**Output Format (JSON only, no markdown):**
{{
  "title": "Engaging video title",
  "description": "Brief video description (2-3 sentences)",
  "total_duration_estimate": {target_seconds},
  "scenes": [
    {{
      "index": 0,
      "narration": "Detailed narration text in {request.language} (about {narration_per_scene:,} characters, engaging and informative)",
      "image_prompt": "Detailed English prompt for AI image generation (describe visual scene, style, mood)",
      "duration_seconds": 25,
      "transition": "fade",
      "narrative_role": "hook, context, escalation, payoff, or CTA",
      "visual_function": "What the image proves, contrasts, or reveals",
      "open_loop": "Optional question answered in a later scene",
      "source_note": "Optional source or verification lead for a factual claim"
    }},
    ... ({num_scenes} scenes total)
  ],
  "metadata": {{
    "editorial": {{
      "promise": "The precise value delivered by the video",
      "hook": "The opening tension or question",
      "chapters": [{{"title": "Chapter title", "purpose": "Why the viewer keeps watching"}}],
      "payoff": "How the conclusion answers the opening promise"
    }}
  }}
}}

**Scene Guidelines:**
1. The combined narration must stay close to the narration budget. Each scene should use {narration_minimum:,}-{narration_maximum:,} characters; do not output short placeholder scenes.
2. Image prompts in English, detailed and visual (e.g., "cinematic landscape with mountains at sunset, dramatic lighting, 4k quality")
3. Narration in {request.language}, conversational and engaging
4. Duration per scene: 20-30 seconds
5. Create a clear narrative flow across all scenes
6. First scene should hook the viewer
7. Last scene should have a strong conclusion/call-to-action
8. Put a meaningful change of pace, question, reveal, contrast, or consequence at least every 45-90 seconds
9. Build chapters with a new question or escalation at each transition; answer open loops before the conclusion
10. Every scene must state its narrative_role and visual_function. Use source_note for factual claims that need checking.
11. Write every narration line, including the call-to-action, exclusively in {request.language}. Keep any channel name as a proper brand name, but translate the CTA phrase itself (for example, "Subscribe" in English).

Output ONLY the JSON, no explanations or markdown formatting.
"""

        return prompt

    def _generate_openai(
        self, prompt: str, config: Dict
    ) -> Tuple[str, str, Optional[int]]:
        """Generate script using OpenAI API"""
        from openai import OpenAI

        api_key = config.get("api_key")
        model = config.get("model", "gpt-4o")
        base_url = config.get("base_url")

        client = OpenAI(api_key=api_key, base_url=base_url if base_url else None)

        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": "You are a professional video script writer. Output only valid JSON.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.7,
            max_tokens=12000,
            response_format={"type": "json_object"},
        )

        content = response.choices[0].message.content
        tokens = response.usage.total_tokens if response.usage else None

        return content, model, tokens

    def _generate_claude(
        self, prompt: str, config: Dict
    ) -> Tuple[str, str, Optional[int]]:
        """Generate script using Anthropic Claude API"""
        import anthropic

        api_key = config.get("api_key")
        model = config.get("model", "claude-3-5-sonnet-20241022")
        base_url = config.get("base_url") or "https://api.anthropic.com"

        # Specify the official endpoint even when no custom endpoint was saved.
        # Otherwise the SDK inherits ANTHROPIC_BASE_URL, which may point at a
        # stopped local proxy left by another development tool.
        client_options = {'api_key': api_key, 'base_url': base_url}
        http_client = _anthropic_http_client()
        if http_client is not None:
            client_options['http_client'] = http_client
        client = anthropic.Anthropic(**client_options)

        message = client.messages.create(
            model=model,
            max_tokens=16000,
            temperature=0.7,
            system="You are a professional video script writer. Output only valid JSON without markdown code blocks.",
            messages=[{"role": "user", "content": prompt}],
        )

        content = message.content[0].text
        # Remove markdown code blocks if present
        content = content.strip()
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()

        tokens = message.usage.input_tokens + message.usage.output_tokens

        return content, model, tokens

    def _generate_gemini(
        self, prompt: str, config: Dict
    ) -> Tuple[str, str, Optional[int]]:
        """Generate script using Google Gemini API"""
        import google.generativeai as genai

        api_key = config.get("api_key")
        model_name = config.get("model", "gemini-2.0-flash-exp")

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(
            model_name=model_name,
            generation_config={
                "temperature": 0.7,
                "max_output_tokens": 16000,
                "response_mime_type": "application/json",
            },
        )

        response = model.generate_content(prompt)
        content = response.text

        # Gemini doesn't provide token count in the same way
        tokens = None

        return content, model_name, tokens

    def _generate_deepseek(
        self, prompt: str, config: Dict
    ) -> Tuple[str, str, Optional[int]]:
        """Generate script using DeepSeek API (OpenAI-compatible)"""
        from openai import OpenAI

        api_key = config.get("api_key")
        model = config.get("model", "deepseek-chat")
        base_url = config.get("base_url", "https://api.deepseek.com")

        client = OpenAI(api_key=api_key, base_url=base_url)

        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": "You are a professional video script writer. Output only valid JSON.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.7,
            max_tokens=12000,
            response_format={"type": "json_object"},
        )

        content = response.choices[0].message.content
        tokens = response.usage.total_tokens if response.usage else None

        return content, model, tokens

    def _generate_kimi(
        self, prompt: str, config: Dict
    ) -> Tuple[str, str, Optional[int]]:
        """Generate script using Moonshot Kimi API (OpenAI-compatible)"""
        from openai import OpenAI

        api_key = config.get("api_key")
        model = config.get("model", "moonshot-v1-128k")
        base_url = config.get("base_url", "https://api.moonshot.cn/v1")

        client = OpenAI(api_key=api_key, base_url=base_url)

        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": "You are a professional video script writer. Output only valid JSON.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.7,
            max_tokens=12000,
        )

        content = response.choices[0].message.content

        # Extract JSON if wrapped in markdown
        content = content.strip()
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()

        tokens = response.usage.total_tokens if response.usage else None

        return content, model, tokens

    def _generate_qwen(
        self, prompt: str, config: Dict
    ) -> Tuple[str, str, Optional[int]]:
        """Generate script using Alibaba Qwen API"""
        from openai import OpenAI

        api_key = config.get("api_key")
        model = config.get("model", "qwen-max")
        base_url = config.get(
            "base_url", "https://dashscope.aliyuncs.com/compatible-mode/v1"
        )

        client = OpenAI(api_key=api_key, base_url=base_url)

        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": "You are a professional video script writer. Output only valid JSON.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.7,
            max_tokens=12000,
        )

        content = response.choices[0].message.content

        # Extract JSON if wrapped in markdown
        content = content.strip()
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()

        tokens = response.usage.total_tokens if response.usage else None

        return content, model, tokens

    def _parse_script_json(
        self, json_str: str, request: ScriptGenerationRequest
    ) -> StructuredScript:
        """Parse JSON string into StructuredScript"""
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON: {e}")
            logger.error(f"JSON content: {json_str}")
            raise ValueError(f"Invalid JSON response from LLM: {e}")

        # Validate and construct StructuredScript
        scenes = []
        for scene_data in data.get("scenes", []):
            scene = SceneInfo(
                index=scene_data["index"],
                narration=scene_data["narration"],
                image_prompt=scene_data["image_prompt"],
                duration_seconds=scene_data.get("duration_seconds"),
                transition=scene_data.get("transition", "fade"),
                narrative_role=scene_data.get("narrative_role"),
                visual_function=scene_data.get("visual_function"),
                open_loop=scene_data.get("open_loop"),
                source_note=scene_data.get("source_note"),
            )
            scenes.append(scene)

        metadata = data.get("metadata", {}) or {}
        metadata.setdefault("script_language", request.language)
        metadata.setdefault("target_duration_seconds", int(request.duration_minutes * 60))
        metadata.setdefault("script_llm_provider", request.llm_provider.value)
        metadata.setdefault("target_scene_count", self._target_scene_count(request))
        if request.editorial_context:
            generated_editorial = metadata.get("editorial", {}) or {}
            metadata["editorial"] = {
                **request.editorial_context,
                **generated_editorial,
            }
            if "cta" in request.editorial_context:
                metadata["editorial"]["cta"] = request.editorial_context["cta"]

        script = StructuredScript(
            title=data.get("title", f"Video sobre {request.topic}"),
            description=data.get("description", ""),
            total_duration_estimate=data.get(
                "total_duration_estimate", request.duration_minutes * 60
            ),
            scenes=scenes,
            metadata=metadata,
        )
        cta = (request.editorial_context or {}).get("cta") or {}
        selected_cta = str(cta.get("text") or "").strip() if cta.get("enabled") else ""
        cta_scenes = [
            scene for scene in script.scenes
            if scene.narrative_role and scene.narrative_role.lower() == 'cta'
        ]
        if selected_cta:
            if cta_scenes:
                cta_scenes[-1].narration = selected_cta
            elif script.scenes:
                script.scenes[-1].narration = f"{script.scenes[-1].narration.rstrip()} {selected_cta}".strip()
        else:
            cta_replacements = {
                'en-US': [(r'\binscreva-?se\b', 'Subscribe')],
                'es-ES': [(r'\binscreva-?se\b', 'Suscríbete')],
            }
            for scene in cta_scenes:
                for pattern, replacement in cta_replacements.get(request.language, []):
                    scene.narration = re.sub(pattern, replacement, scene.narration, flags=re.IGNORECASE)

        return script
