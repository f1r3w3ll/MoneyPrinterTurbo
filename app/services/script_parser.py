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
        if script.total_duration_estimate < 900:  # 15 minutes
            raise ValueError(
                f"Duration must be at least 15 minutes (900s), "
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
        # LLMs commonly use "cut" for a direct cut; internally this is "none".
        if scene.transition == "cut":
            scene.transition = "none"

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
        self, script: StructuredScript, chars_per_second: float = 15.0
    ) -> float:
        """
        Estimate total video duration based on narration length

        Args:
            script: StructuredScript object
            chars_per_second: Average TTS speed (characters per second)

        Returns:
            Estimated duration in seconds
        """
        total_chars = sum(len(scene.narration) for scene in script.scenes)
        estimated_duration = total_chars / chars_per_second

        # Add transition time (1 second per scene)
        estimated_duration += len(script.scenes)

        logger.debug(
            f"Estimated duration: {estimated_duration}s "
            f"({total_chars} chars @ {chars_per_second} chars/s)"
        )

        return estimated_duration
