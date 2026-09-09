"""
Checkpoint Manager for Long-Form Video Generation

Enables resumable tasks by saving/loading checkpoint state.
Critical for long-running tasks that may fail due to:
- Network issues
- API rate limits
- System crashes
- User interruption
"""

import json
import os
from typing import Optional

from loguru import logger

from app.models.schema import CheckpointState


class CheckpointManager:
    """Manages checkpoint state for resumable tasks"""

    def __init__(self, task_id: str, checkpoint_dir: str):
        """
        Initialize checkpoint manager

        Args:
            task_id: Unique task identifier
            checkpoint_dir: Directory to store checkpoint files
        """
        self.task_id = task_id
        self.checkpoint_dir = checkpoint_dir
        self.checkpoint_path = os.path.join(
            checkpoint_dir, f"{task_id}.checkpoint.json"
        )

        # Create checkpoint directory if it doesn't exist
        os.makedirs(checkpoint_dir, exist_ok=True)

        logger.debug(f"CheckpointManager initialized for task {task_id}")

    def save_checkpoint(self, state: CheckpointState):
        """
        Save checkpoint state atomically

        Uses temp file + rename for atomic write to prevent corruption.

        Args:
            state: CheckpointState to save
        """
        temp_path = self.checkpoint_path + ".tmp"

        try:
            # Write to temp file
            with open(temp_path, "w", encoding="utf-8") as f:
                f.write(state.model_dump_json(indent=2))

                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_path, self.checkpoint_path)

            logger.info(
                f"Checkpoint saved for task {self.task_id}: "
                f"phase={state.current_phase}, "
                f"scenes_completed={len(state.completed_scenes)}"
            )

        except Exception as e:
            logger.error(f"Failed to save checkpoint: {e}")
            # Clean up temp file
            if os.path.exists(temp_path):
                os.remove(temp_path)
            raise

    def load_checkpoint(self) -> Optional[CheckpointState]:
        """
        Load checkpoint state if it exists

        Returns:
            CheckpointState if checkpoint exists, None otherwise
        """
        if not os.path.exists(self.checkpoint_path):
            logger.debug(f"No checkpoint found for task {self.task_id}")
            return None

        try:
            with open(self.checkpoint_path, "r", encoding="utf-8") as f:
                data = f.read()

            state = CheckpointState.model_validate_json(data)

            logger.info(
                f"Checkpoint loaded for task {self.task_id}: "
                f"phase={state.current_phase}, "
                f"scenes_completed={len(state.completed_scenes)}, "
                f"errors={state.error_count}"
            )

            return state

        except Exception as e:
            logger.error(f"Failed to load checkpoint: {e}")
            logger.warning("Checkpoint file may be corrupted, starting fresh")
            return None

    def clear_checkpoint(self):
        """
        Delete checkpoint file after successful completion

        Should be called when task completes successfully.
        """
        if os.path.exists(self.checkpoint_path):
            try:
                os.remove(self.checkpoint_path)
                logger.info(f"Checkpoint cleared for task {self.task_id}")
            except Exception as e:
                logger.warning(f"Failed to clear checkpoint: {e}")

    def checkpoint_exists(self) -> bool:
        """
        Check if checkpoint exists for this task

        Returns:
            True if checkpoint file exists
        """
        return os.path.exists(self.checkpoint_path)

    def get_progress_info(self) -> Optional[dict]:
        """
        Get progress information from checkpoint

        Returns:
            Dictionary with progress info, or None if no checkpoint
        """
        state = self.load_checkpoint()
        if not state:
            return None

        return {
            "task_id": state.task_id,
            "current_phase": state.current_phase,
            "completed_scenes": state.completed_scenes,
            "num_completed_scenes": len(state.completed_scenes),
            "error_count": state.error_count,
            "timestamp": state.timestamp,
            "has_generated_files": len(state.generated_files) > 0,
        }

    def update_phase(self, state: CheckpointState, new_phase: str):
        """
        Update checkpoint phase

        Helper method to update phase and save in one call.

        Args:
            state: Current CheckpointState
            new_phase: New phase name
        """
        state.current_phase = new_phase
        self.save_checkpoint(state)
        logger.info(f"Task {self.task_id} advanced to phase: {new_phase}")

    def mark_scene_completed(self, state: CheckpointState, scene_index: int):
        """
        Mark a scene as completed

        Helper method to track scene-level progress.

        Args:
            state: Current CheckpointState
            scene_index: Index of completed scene
        """
        if scene_index not in state.completed_scenes:
            state.completed_scenes.append(scene_index)
            state.completed_scenes.sort()
            self.save_checkpoint(state)
            logger.debug(
                f"Scene {scene_index} marked as completed "
                f"({len(state.completed_scenes)} scenes done)"
            )

    def record_error(self, state: CheckpointState, error_message: str):
        """
        Record error in checkpoint

        Increments error count and saves checkpoint.

        Args:
            state: Current CheckpointState
            error_message: Error description
        """
        state.error_count += 1
        self.save_checkpoint(state)
        logger.warning(
            f"Error recorded for task {self.task_id} "
            f"(total errors: {state.error_count}): {error_message}"
        )

    @staticmethod
    def get_all_checkpoints(checkpoint_dir: str) -> list[dict]:
        """
        List all checkpoints in directory

        Args:
            checkpoint_dir: Checkpoint directory

        Returns:
            List of checkpoint info dictionaries
        """
        if not os.path.exists(checkpoint_dir):
            return []

        checkpoints = []

        for filename in os.listdir(checkpoint_dir):
            if filename.endswith(".checkpoint.json"):
                task_id = filename.replace(".checkpoint.json", "")
                checkpoint_path = os.path.join(checkpoint_dir, filename)

                try:
                    with open(checkpoint_path, "r", encoding="utf-8") as f:
                        state = CheckpointState.model_validate_json(f.read())

                    checkpoints.append(
                        {
                            "task_id": task_id,
                            "current_phase": state.current_phase,
                            "completed_scenes": len(state.completed_scenes),
                            "error_count": state.error_count,
                            "timestamp": state.timestamp,
                        }
                    )
                except Exception as e:
                    logger.warning(
                        f"Failed to read checkpoint {filename}: {e}"
                    )

        return checkpoints
