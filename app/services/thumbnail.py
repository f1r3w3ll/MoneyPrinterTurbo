"""
Thumbnail Generation Service for YouTube Videos

Generates eye-catching thumbnails using hybrid approach:
1. AI-generated base image
2. Text overlay with professional styling
3. Optimized for YouTube (<2MB, 1280x720)
"""

import os
from typing import Optional

from loguru import logger
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

from app.services.image_generation import ImageGenerationService


class ThumbnailService:
    """YouTube thumbnail generation service"""

    # YouTube recommended thumbnail size
    YOUTUBE_THUMBNAIL_SIZE = (1280, 720)
    MAX_FILE_SIZE_BYTES = 2 * 1024 * 1024  # 2MB

    def __init__(self):
        """Initialize thumbnail service"""
        self.image_service = ImageGenerationService()

    def generate_hybrid_thumbnail(
        self,
        video_title: str,
        ai_image_prompt: str,
        output_path: str,
        style: str = "dramatic",
        provider: Optional[str] = None,
    ) -> str:
        """
        Generate hybrid thumbnail with AI image + text overlay

        Process:
        1. Generate AI image (1280x720)
        2. Apply color grading
        3. Add text overlay with effects
        4. Optimize for YouTube

        Args:
            video_title: Title text to overlay on thumbnail
            ai_image_prompt: Prompt for AI image generation
            output_path: Path to save thumbnail
            style: Visual style (dramatic, clean, colorful)
            provider: Image generation provider (optional)

        Returns:
            Path to generated thumbnail
        """
        logger.info(f"Generating hybrid thumbnail: {output_path}")

        # Ensure output directory exists
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        # Set provider if specified
        if provider:
            self.image_service.provider = provider

        # 1. Generate AI image
        temp_image_path = self._generate_base_image(ai_image_prompt, output_path)

        # 2. Load and process image
        img = Image.open(temp_image_path)
        img = img.convert("RGB")  # Ensure RGB mode

        # 3. Resize to YouTube thumbnail size
        img = img.resize(self.YOUTUBE_THUMBNAIL_SIZE, Image.Resampling.LANCZOS)

        # 4. Apply color grading
        img = self._apply_color_grading(img, style)

        # 5. Add text overlay
        img = self._add_text_overlay(img, video_title, style)

        # 6. Save optimized
        self._save_optimized(img, output_path)

        # Clean up temp file if different from output
        if temp_image_path != output_path and os.path.exists(temp_image_path):
            os.remove(temp_image_path)

        logger.info(f"Thumbnail generated successfully: {output_path}")
        return output_path

    def _generate_base_image(
        self, prompt: str, output_path: str
    ) -> str:
        """
        Generate AI base image for thumbnail

        Args:
            prompt: Image generation prompt
            output_path: Final output path

        Returns:
            Path to generated image
        """
        # Enhance prompt for thumbnail style
        enhanced_prompt = (
            f"{prompt}, youtube thumbnail style, eye-catching, "
            f"high contrast, vibrant colors, professional quality"
        )

        output_dir = os.path.dirname(output_path)
        scene_id = "thumbnail"

        return self.image_service.generate_image(
            prompt=enhanced_prompt, scene_id=scene_id, output_dir=output_dir
        )

    def _apply_color_grading(self, img: Image.Image, style: str) -> Image.Image:
        """
        Apply color grading to enhance visual appeal

        Args:
            img: PIL Image
            style: Visual style

        Returns:
            Enhanced image
        """
        if style == "dramatic":
            # Increase contrast and saturation
            enhancer = ImageEnhance.Contrast(img)
            img = enhancer.enhance(1.3)
            enhancer = ImageEnhance.Color(img)
            img = enhancer.enhance(1.2)

        elif style == "colorful":
            # Vibrant colors
            enhancer = ImageEnhance.Color(img)
            img = enhancer.enhance(1.5)
            enhancer = ImageEnhance.Brightness(img)
            img = enhancer.enhance(1.1)

        elif style == "clean":
            # Slight enhancement only
            enhancer = ImageEnhance.Sharpness(img)
            img = enhancer.enhance(1.1)

        return img

    def _add_text_overlay(
        self, img: Image.Image, title: str, style: str
    ) -> Image.Image:
        """
        Add title text with professional styling

        Effects:
        - Drop shadow
        - Stroke outline
        - Semi-transparent background bar (optional)
        - Bold font

        Args:
            img: PIL Image
            title: Title text
            style: Visual style

        Returns:
            Image with text overlay
        """
        draw = ImageDraw.Draw(img, "RGBA")

        # Load font
        font = self._get_font(size=80)

        # Word wrap for long titles
        wrapped_title = self._wrap_text(title, font, max_width=1200)

        # Calculate text position (centered, middle-bottom)
        bbox = draw.multiline_textbbox((0, 0), wrapped_title, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]

        x = (1280 - text_width) // 2
        y = 720 - text_height - 100  # 100px from bottom

        # Optional: Add semi-transparent background bar
        if style != "clean":
            self._add_background_bar(img, y - 20, text_height + 40)

        # Draw drop shadow
        shadow_offset = 4
        draw.multiline_text(
            (x + shadow_offset, y + shadow_offset),
            wrapped_title,
            font=font,
            fill=(0, 0, 0, 180),
            align="center",
        )

        # Draw main text with stroke
        draw.multiline_text(
            (x, y),
            wrapped_title,
            font=font,
            fill=(255, 255, 255),
            stroke_width=3,
            stroke_fill=(0, 0, 0),
            align="center",
        )

        return img

    def _add_background_bar(self, img: Image.Image, y: int, height: int):
        """
        Add semi-transparent background bar for text

        Args:
            img: PIL Image
            y: Y position
            height: Bar height
        """
        overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        # Draw semi-transparent black bar
        draw.rectangle([(0, y), (1280, y + height)], fill=(0, 0, 0, 120))

        # Composite with original image
        img.paste(Image.alpha_composite(img.convert("RGBA"), overlay))

    def _get_font(self, size: int = 80) -> ImageFont.FreeTypeFont:
        """
        Load font for text overlay

        Args:
            size: Font size

        Returns:
            ImageFont object
        """
        # Try to load Impact font (ideal for YouTube thumbnails)
        font_names = [
            "impact.ttf",
            "Impact.ttf",
            "arial.ttf",
            "Arial.ttf",
            "DejaVuSans-Bold.ttf",
        ]

        for font_name in font_names:
            try:
                return ImageFont.truetype(font_name, size)
            except OSError:
                continue

        # Fallback to default font
        logger.warning("Could not load preferred font, using default")
        return ImageFont.load_default()

    def _wrap_text(
        self, text: str, font: ImageFont.FreeTypeFont, max_width: int
    ) -> str:
        """
        Wrap text to fit within max width

        Args:
            text: Text to wrap
            font: Font to use
            max_width: Maximum width in pixels

        Returns:
            Wrapped text with newlines
        """
        words = text.split()
        lines = []
        current_line = []

        for word in words:
            test_line = " ".join(current_line + [word])
            bbox = font.getbbox(test_line)
            width = bbox[2] - bbox[0]

            if width <= max_width:
                current_line.append(word)
            else:
                if current_line:
                    lines.append(" ".join(current_line))
                current_line = [word]

        if current_line:
            lines.append(" ".join(current_line))

        return "\n".join(lines)

    def _save_optimized(self, img: Image.Image, output_path: str):
        """
        Save image optimized for YouTube

        Requirements:
        - Format: JPEG
        - Max size: 2MB
        - Resolution: 1280x720

        Args:
            img: PIL Image
            output_path: Output file path
        """
        # Try quality 90 first
        img.save(output_path, "JPEG", quality=90, optimize=True)

        # If file too large, reduce quality
        file_size = os.path.getsize(output_path)
        if file_size > self.MAX_FILE_SIZE_BYTES:
            logger.warning(
                f"Thumbnail too large ({file_size} bytes), reducing quality"
            )
            img.save(output_path, "JPEG", quality=85, optimize=True)

            # If still too large, try quality 80
            file_size = os.path.getsize(output_path)
            if file_size > self.MAX_FILE_SIZE_BYTES:
                img.save(output_path, "JPEG", quality=80, optimize=True)

        final_size = os.path.getsize(output_path)
        logger.debug(
            f"Thumbnail saved: {output_path} ({final_size} bytes, "
            f"{final_size / (1024 * 1024):.2f} MB)"
        )
