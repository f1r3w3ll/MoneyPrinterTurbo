"""
Image Generation Service for Long-Form Videos

Supports multiple AI image generation providers:
- DALL-E 3 (OpenAI)
- Stable Diffusion (via Replicate or local)
- Midjourney (reserved, not implemented in this build)
"""

import os
import time
import base64
import ssl
import httpx
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Tuple

import requests
from loguru import logger

from app.config import config


DEFAULT_REPLICATE_SD_MODEL = 'stability-ai/stable-diffusion-3.5-large'


def is_output_safety_block(error: Exception) -> bool:
    """Identify an image that OpenAI rejected after generating its output."""
    detail = str(error).lower()
    return 'moderation_blocked' in detail and 'moderation_stage' in detail and 'output' in detail


def neutral_documentary_prompt() -> str:
    """Safe visual fallback used only after an output moderation rejection."""
    return ('A neutral documentary visual: an abstract, non-graphic editorial composition with '
            'architecture, landscape, maps, documents, and symbolic objects as appropriate; '
            'no people, no violence, no injury, no weapons, no logos, no readable text.')


def stable_diffusion_input(model: str, prompt: str, width: int = 1024, height: int = 1024) -> dict:
    """Adapt the image request to the input schema of the configured model."""
    normalized = str(model or '').split(':', 1)[0]
    if normalized == DEFAULT_REPLICATE_SD_MODEL:
        ratio = width / height if height else 1
        aspect_ratio = min(
            {'1:1': 1, '16:9': 16 / 9, '9:16': 9 / 16},
            key=lambda label: abs({'1:1': 1, '16:9': 16 / 9, '9:16': 9 / 16}[label] - ratio),
        )
        return {'prompt': prompt, 'aspect_ratio': aspect_ratio, 'output_format': 'png'}
    return {
        'prompt': prompt,
        'width': width,
        'height': height,
        'num_outputs': 1,
    }


def _image_http_client():
    """Trust the OS certificate store without disabling HTTPS verification."""
    context = ssl.create_default_context()
    if os.name == 'nt':
        for certificate, encoding, trust in ssl.enum_certificates('ROOT'):
            if encoding == 'x509_asn' and (trust is True or ssl.Purpose.SERVER_AUTH.oid in trust):
                context.load_verify_locations(cadata=ssl.DER_cert_to_PEM_cert(certificate))
    return httpx.Client(verify=context, timeout=600)


class ImageGenerationService:
    """AI Image generation service with multi-provider support"""

    def __init__(self, provider: str = None):
        """
        Initialize image generation service

        Args:
            provider: Provider name (dalle, sd). Midjourney is reserved and
                     not implemented in this build.
                     If None, uses config default.
        """
        self.provider = provider or config.image_generation.get(
            "default_provider", "sd"
        )
        if self.provider == "midjourney":
            raise ValueError(
                "Midjourney is not implemented in this build. Use 'dalle' or 'sd'."
            )
        if self.provider == "dalle":
            raise ValueError("DALL-E está desativado no Estúdio. Use Pexels ou Stable Diffusion.")
        if self.provider != "sd":
            raise ValueError(f"Unsupported image provider: {self.provider}")
        logger.info(f"Initialized ImageGenerationService with provider: {self.provider}")

    def generate_image(
        self,
        prompt: str,
        scene_id: str,
        output_dir: str,
        **kwargs,
    ) -> str:
        """
        Generate a single image using the configured provider

        Args:
            prompt: Image description prompt
            scene_id: Scene identifier (e.g., "scene-0")
            output_dir: Directory to save the generated image
            **kwargs: Provider-specific parameters

        Returns:
            Path to generated image file

        Raises:
            ValueError: If provider is unsupported
            Exception: If image generation fails
        """
        os.makedirs(output_dir, exist_ok=True)

        logger.info(f"Generating image for {scene_id} with {self.provider}")
        logger.debug(f"Prompt: {prompt}")

        if self.provider == "dalle":
            return self._generate_dalle(prompt, scene_id, output_dir, **kwargs)
        return self._generate_stable_diffusion(
            prompt, scene_id, output_dir, **kwargs
        )

    def batch_generate(
        self,
        prompts: List[Tuple[str, str]],  # [(scene_id, prompt)]
        output_dir: str,
        max_concurrent: int = 3,
        max_retries: int = 3,
    ) -> Dict[str, str]:
        """
        Generate multiple images with rate limiting and retry logic

        Args:
            prompts: List of (scene_id, prompt) tuples
            output_dir: Directory to save generated images
            max_concurrent: Maximum concurrent requests (for rate limiting)
            max_retries: Maximum retry attempts per image

        Returns:
            Dictionary mapping scene_id to image_path
        """
        logger.info(
            f"Batch generating {len(prompts)} images with "
            f"max {max_concurrent} concurrent requests"
        )

        results = {}
        failed = []

        with ThreadPoolExecutor(max_workers=max_concurrent) as executor:
            # Submit all tasks
            future_to_scene = {}
            for scene_id, prompt in prompts:
                future = executor.submit(
                    self._generate_with_retry,
                    prompt,
                    scene_id,
                    output_dir,
                    max_retries,
                )
                future_to_scene[future] = scene_id

            # Collect results as they complete
            for future in as_completed(future_to_scene):
                scene_id = future_to_scene[future]
                try:
                    image_path = future.result()
                    results[scene_id] = image_path
                    logger.info(
                        f"Successfully generated image for {scene_id} "
                        f"({len(results)}/{len(prompts)})"
                    )
                except Exception as e:
                    logger.error(f"Failed to generate image for {scene_id}: {e}")
                    failed.append(scene_id)

        if failed:
            logger.warning(f"Failed to generate {len(failed)} images: {failed}")

        return results

    def _generate_with_retry(
        self,
        prompt: str,
        scene_id: str,
        output_dir: str,
        max_retries: int = 3,
    ) -> str:
        """
        Generate image with exponential backoff retry

        Args:
            prompt: Image prompt
            scene_id: Scene identifier
            output_dir: Output directory
            max_retries: Maximum retry attempts

        Returns:
            Path to generated image

        Raises:
            Exception: If all retries fail
        """
        for attempt in range(max_retries):
            try:
                return self.generate_image(prompt, scene_id, output_dir)
            except Exception as e:
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt  # Exponential backoff: 1s, 2s, 4s
                    logger.warning(
                        f"Attempt {attempt + 1}/{max_retries} failed for {scene_id}, "
                        f"retrying in {wait_time}s: {e}"
                    )
                    time.sleep(wait_time)
                else:
                    logger.error(
                        f"All {max_retries} attempts failed for {scene_id}: {e}"
                    )
                    raise

    def _generate_dalle(
        self, prompt: str, scene_id: str, output_dir: str, **kwargs
    ) -> str:
        """
        Generate image using DALL-E 3

        Args:
            prompt: Image description
            scene_id: Scene identifier
            output_dir: Output directory

        Returns:
            Path to generated image
        """
        try:
            from openai import OpenAI
        except ImportError:
            raise ImportError(
                "OpenAI package not installed. Install with: pip install openai"
            )

        api_key = (config.image_generation.get("openai_api_key") or
                   config.app.get("openai_api_key") or config.llm.get("openai", {}).get("api_key"))
        if not api_key:
            raise ValueError("OpenAI API key not configured")

        model = config.image_generation.get("dalle_model", "dall-e-3")
        quality = kwargs.get("quality") or config.image_generation.get("dalle_quality", "standard")
        size = kwargs.get("size") or config.image_generation.get("dalle_size", "1024x1024")
        if model.startswith('gpt-image-'):
            quality = {'standard': 'medium', 'hd': 'high'}.get(quality, quality)
            size = {'1024x1792': '1024x1536', '1792x1024': '1536x1024'}.get(size, size)

        # Enhance prompt for better quality
        enhanced_prompt = f"{prompt}, high quality, detailed, cinematic lighting"

        logger.debug(f"DALL-E request: model={model}, quality={quality}, size={size}")

        # Generate image
        with _image_http_client() as http_client:
            client = OpenAI(api_key=api_key, http_client=http_client)
            try:
                response = client.images.generate(
                    model=model, prompt=enhanced_prompt, size=size, quality=quality, n=1
                )
            except Exception as exc:
                if is_output_safety_block(exc):
                    logger.warning(f'OpenAI safety system blocked generated output for {scene_id}; retrying once with neutral documentary direction.')
                    try:
                        response = client.images.generate(
                            model=model, prompt=neutral_documentary_prompt(), size=size, quality=quality, n=1
                        )
                    except Exception as retry_error:
                        if is_output_safety_block(retry_error):
                            raise ValueError(
                                f'A OpenAI bloqueou a imagem da cena {scene_id} por segurança, inclusive após uma alternativa neutra. '
                                'Revise o prompt visual da cena ou escolha clipes gratuitos/Stable Diffusion e retome a produção.'
                            ) from retry_error
                        raise
                else:
                    from openai import APIConnectionError
                    if not isinstance(exc, APIConnectionError):
                        raise
                    cause = exc.__cause__
                    certificate_error = False
                    for _ in range(8):
                        if cause is None:
                            break
                        certificate_error |= 'CERTIFICATE_VERIFY_FAILED' in str(cause)
                        cause = cause.__cause__
                    detail = ('O certificado HTTPS da rede não foi reconhecido. Confira os certificados do Windows e a VPN.'
                              if certificate_error else 'Confira a conexão com a internet, VPN ou proxy e tente retomar.')
                    raise RuntimeError(f'Falha de conexão ao gerar a imagem {scene_id}. {detail} Os arquivos já gerados foram preservados.') from exc

        # Download image
        image_path = os.path.join(output_dir, f"{scene_id}.png")
        image_data = response.data[0]
        if getattr(image_data, 'b64_json', None):
            img_data = base64.b64decode(image_data.b64_json)
        else:
            image_url = image_data.url
            logger.debug(f"Downloading image from {image_url}")
            download = requests.get(image_url, timeout=60)
            download.raise_for_status()
            img_data = download.content

        with open(image_path, "wb") as f:
            f.write(img_data)

        # Verify file size
        file_size = os.path.getsize(image_path)
        if file_size < 1024:  # Less than 1KB is suspicious
            raise ValueError(f"Generated image file is too small: {file_size} bytes")

        logger.info(
            f"DALL-E image generated successfully: {image_path} ({file_size} bytes)"
        )

        return image_path

    def _generate_stable_diffusion(
        self, prompt: str, scene_id: str, output_dir: str, **kwargs
    ) -> str:
        """
        Generate image using Stable Diffusion (via Replicate)

        Args:
            prompt: Image description
            scene_id: Scene identifier
            output_dir: Output directory

        Returns:
            Path to generated image
        """
        try:
            import replicate
        except ImportError:
            raise ImportError(
                "Replicate package not installed. Install with: pip install replicate"
            )

        api_key = config.image_generation.get("sd_api_key")
        if not api_key:
            raise ValueError("Stable Diffusion API key not configured")

        model = config.image_generation.get(
            "sd_model", DEFAULT_REPLICATE_SD_MODEL
        )

        logger.debug(f"Stable Diffusion request: model={model}")

        # Generate image
        output = replicate.Client(api_token=api_key).run(
            model,
            input=stable_diffusion_input(model, prompt),
        )

        # Download image (output is a list of URLs)
        image_url = output[0] if isinstance(output, list) else output
        image_path = os.path.join(output_dir, f"{scene_id}.png")

        logger.debug(f"Downloading image from {image_url}")
        download = requests.get(str(image_url), timeout=60)
        download.raise_for_status()
        img_data = download.content

        with open(image_path, "wb") as f:
            f.write(img_data)

        logger.info(f"Stable Diffusion image generated successfully: {image_path}")

        return image_path
