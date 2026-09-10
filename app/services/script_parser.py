"""
Script Parser Service for Long-Form Videos

Parses and validates JSON-formatted scripts with scene-by-scene descriptions.
"""

import json
from typing import Union

from loguru import logger

from app.models.schema import SceneInfo, StructuredScript


class ScriptParser:
    """Parser and validator for structured video scripts"""

    # These are planning estimates, not a replacement for measuring the final
    # audio. They keep the writing brief close to the pace of the selected
    # narration language before image and TTS costs are incurred.
    NARRATION_CHARS_PER_SECOND = {
        "pt-BR": 14.0,
        "en-US": 13.0,
        "de-DE": 13.5,
        "es-ES": 13.5,
    }

    @classmethod
    def chars_per_second_for(cls, language: str | None) -> float:
        """Return the planning narration rate for a supported language."""
        return cls.NARRATION_CHARS_PER_SECOND.get(language or "", 14.0)

    def parse_json_script(
        self, json_data: Union[str, dict]
    ) -> StructuredScript:
        """
        Parse JSON input and validate structured script

        Expected format:
        {
          "title": "Video Title",
          "description": "Video Description",
          "total_duration_estimate": 1200,
          "scenes": [
            {
              "index": 0,
              "narration": "Narration text...",
              "image_prompt": "Prompt for DALL-E...",
              "duration_seconds": 20,
              "transition": "fade"
            },
            ...
          ]
        }

        Args:
            json_data: JSON string or dict

        Returns:
            StructuredScript object

        Raises:
            ValueError: If validation fails
        """
        logger.info("Parsing structured script")

        # Parse JSON if string
        if isinstance(json_data, str):
            try:
                data = json.loads(json_data)
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSON: {e}")
        else:
            data = json_data

        # Create StructuredScript object (Pydantic will validate types)
        try:
            script = StructuredScript(**data)
        except Exception as e:
            raise ValueError(f"Script validation failed: {e}")

        # Additional business logic validations
        self._validate_script(script)

        logger.info(
            f"Script parsed successfully: {len(script.scenes)} scenes, "
            f"estimated duration: {script.total_duration_estimate}s"
        )

        return script

    def _validate_script(self, script: StructuredScript):
        """
        Validate script business rules

        Args:
            script: StructuredScript object

        Raises:
            ValueError: If validation fails
        """
        # Check scene count
        if len(script.scenes) < 5:
            raise ValueError(
                f"Script must have at least 5 scenes (has {len(script.scenes)})"
            )

        if len(script.scenes) > 100:
            raise ValueError(
                f"Script cannot have more than 100 scenes (has {len(script.scenes)})"
            )

        # Check duration
        if script.total_duration_estimate < 300:  # 5 minutes
            raise ValueError(
                f"Duration must be at least 5 minutes (300s), "
                f"got {script.total_duration_estimate}s"
            )

        if script.total_duration_estimate > 1800:  # 30 minutes
            raise ValueError(
                f"Duration cannot exceed 30 minutes (1800s), "
                f"got {script.total_duration_estimate}s"
            )

        indices = [scene.index for scene in script.scenes]
        if len(set(indices)) != len(indices) or any(index < 0 for index in indices):
            raise ValueError("Scene indices must be unique and non-negative")

        # Validate each scene
        for scene in script.scenes:
            self.validate_scene(scene)

    def validate_scene(self, scene: SceneInfo) -> bool:
        """
        Validate individual scene

        Args:
            scene: SceneInfo object

        Returns:
            True if valid

        Raises:
            ValueError: If validation fails
        """
        # Models often use an editor's vocabulary rather than the renderer's
        # small transition enum. Normalize equivalent names before validation.
        if isinstance(scene.transition, str):
            transition = scene.transition.strip().lower()
            transition_aliases = {
                "cut": "none", "hard cut": "none", "jump cut": "none",
                "wipe": "slide", "swipe": "slide",
                "dissolve": "fade", "crossfade": "fade", "cross-fade": "fade",
                "fade in": "fade", "fade-out": "fade",
            }
            scene.transition = transition_aliases.get(transition, transition)

        # Check narration length
        if not scene.narration or len(scene.narration.strip()) < 10:
            raise ValueError(
                f"Scene {scene.index}: narration too short "
                f"(minimum 10 characters)"
            )

        if len(scene.narration) > 2000:
            raise ValueError(
                f"Scene {scene.index}: narration too long "
                f"(maximum 2000 characters, has {len(scene.narration)})"
            )

        # Check image prompt
        if not scene.image_prompt or len(scene.image_prompt.strip()) < 3:
            raise ValueError(
                f"Scene {scene.index}: image_prompt is empty or too short"
            )

        if len(scene.image_prompt) > 1000:
            raise ValueError(
                f"Scene {scene.index}: image_prompt too long "
                f"(maximum 1000 characters)"
            )

        # Check duration if specified
        if scene.duration_seconds is not None:
            if scene.duration_seconds < 3:
                raise ValueError(
                    f"Scene {scene.index}: duration too short "
                    f"(minimum 3 seconds)"
                )

            if scene.duration_seconds > 60:
                raise ValueError(
                    f"Scene {scene.index}: duration too long "
                    f"(maximum 60 seconds)"
                )

        # Check transition
        valid_transitions = ["fade", "slide", "zoom", "none", None]
        if scene.transition not in valid_transitions:
            raise ValueError(
                f"Scene {scene.index}: invalid transition '{scene.transition}'. "
                f"Valid options: {valid_transitions}"
            )

        return True

    def estimate_total_duration(
        self,
        script: StructuredScript,
        chars_per_second: float | None = None,
        language: str | None = None,
    ) -> float:
        """
        Estimate total video duration based on narration length

        Args:
            script: StructuredScript object
            chars_per_second: Average TTS speed (characters per second).
                When omitted, it is selected from ``language``.
            language: Narration language used for the planning estimate.

        Returns:
            Estimated duration in seconds
        """
        chars_per_second = chars_per_second or self.chars_per_second_for(language)
        total_chars = sum(len(scene.narration) for scene in script.scenes)
        estimated_duration = total_chars / chars_per_second

        # Add transition time (1 second per scene)
        estimated_duration += len(script.scenes)

        logger.debug(
            f"Estimated duration: {estimated_duration}s "
            f"({total_chars} chars @ {chars_per_second} chars/s)"
        )

        return estimated_duration
