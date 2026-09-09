"""
Script Generation Service with Multi-LLM Support

Supports: OpenAI, Claude (Anthropic), Gemini, DeepSeek, Kimi, Qwen
"""

import json
import time
from typing import Dict, Optional, Tuple
from loguru import logger

from app.models.schema import (
    ScriptGenerationRequest,
    StructuredScript,
    SceneInfo,
    LLMProvider,
)
from app.config import config


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

        # Build prompt
        prompt = self._build_prompt(request)

        # Generate with selected provider
        if provider == "openai":
            script_json, model, tokens = self._generate_openai(prompt, llm_config)
        elif provider == "claude":
            script_json, model, tokens = self._generate_claude(prompt, llm_config)
        elif provider == "gemini":
            script_json, model, tokens = self._generate_gemini(prompt, llm_config)
        elif provider == "deepseek":
            script_json, model, tokens = self._generate_deepseek(prompt, llm_config)
        elif provider == "kimi":
            script_json, model, tokens = self._generate_kimi(prompt, llm_config)
        elif provider == "qwen":
            script_json, model, tokens = self._generate_qwen(prompt, llm_config)
        else:
            raise ValueError(f"Unsupported LLM provider: {provider}")

        # Parse JSON response
        script = self._parse_script_json(script_json, request)

        generation_time = time.time() - start_time
        logger.info(
            f"Script generated successfully in {generation_time:.2f}s using {model}"
        )

        return script, model, generation_time, tokens

    def _build_prompt(self, request: ScriptGenerationRequest) -> str:
        """Build LLM prompt for script generation"""
        # Calculate number of scenes if not provided
        num_scenes = request.num_scenes or max(
            5, int(request.duration_minutes * 60 / 25)
        )  # ~25s per scene

        prompt = f"""You are a professional video script writer. Generate a structured script for a long-form YouTube video.

**Requirements:**
- Topic: {request.topic}
- Duration: {request.duration_minutes} minutes ({int(request.duration_minutes * 60)} seconds)
- Number of scenes: {num_scenes}
- Language: {request.language}
- Style: {request.style}
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

        prompt += f"""
**Output Format (JSON only, no markdown):**
{{
  "title": "Engaging video title",
  "description": "Brief video description (2-3 sentences)",
  "total_duration_estimate": {int(request.duration_minutes * 60)},
  "scenes": [
    {{
      "index": 0,
      "narration": "Detailed narration text in {request.language} (minimum 50 characters, engaging and informative)",
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
1. Each narration should be 50-300 characters for natural speech
2. Image prompts in English, detailed and visual (e.g., "cinematic landscape with mountains at sunset, dramatic lighting, 4k quality")
3. Narration in {request.language}, conversational and engaging
4. Duration per scene: 20-30 seconds
5. Create a clear narrative flow across all scenes
6. First scene should hook the viewer
7. Last scene should have a strong conclusion/call-to-action
8. Put a meaningful change of pace, question, reveal, contrast, or consequence at least every 45-90 seconds
9. Build chapters with a new question or escalation at each transition; answer open loops before the conclusion
10. Every scene must state its narrative_role and visual_function. Use source_note for factual claims that need checking.

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
        base_url = config.get("base_url")

        client_options = {'api_key': api_key}
        if base_url:
            client_options['base_url'] = base_url
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
        if request.editorial_context:
            generated_editorial = metadata.get("editorial", {}) or {}
            metadata["editorial"] = {
                **request.editorial_context,
                **generated_editorial,
            }

        script = StructuredScript(
            title=data.get("title", f"Video sobre {request.topic}"),
            description=data.get("description", ""),
            total_duration_estimate=data.get(
                "total_duration_estimate", request.duration_minutes * 60
            ),
            scenes=scenes,
            metadata=metadata,
        )

        return script
