import warnings
from enum import Enum
from typing import Any, Dict, List, Optional, Union

import pydantic
from pydantic import BaseModel, Field

from app.config import config

# 忽略 Pydantic 的特定警告
warnings.filterwarnings(
    "ignore",
    category=UserWarning,
    message="Field name.*shadows an attribute in parent.*",
)


class VideoConcatMode(str, Enum):
    random = "random"
    sequential = "sequential"


class VideoTransitionMode(str, Enum):
    none = None
    shuffle = "Shuffle"
    fade_in = "FadeIn"
    fade_out = "FadeOut"
    slide_in = "SlideIn"
    slide_out = "SlideOut"


class VideoAspect(str, Enum):
    landscape = "16:9"
    portrait = "9:16"
    square = "1:1"

    def to_resolution(self):
        if self == VideoAspect.landscape:
            return 1920, 1080
        elif self == VideoAspect.portrait:
            return 1080, 1920
        elif self == VideoAspect.square:
            return 1080, 1080
        raise ValueError(f"unsupported video aspect: {self}")


class _Config:
    arbitrary_types_allowed = True


@pydantic.dataclasses.dataclass(config=_Config)
class MaterialInfo:
    provider: str = "pexels"
    url: str = ""
    duration: int = 0


class VideoParams(BaseModel):
    """
    {
      "video_subject": "",
      "video_aspect": "横屏 16:9（西瓜视频）",
      "voice_name": "女生-晓晓",
      "bgm_name": "random",
      "font_name": "STHeitiMedium 黑体-中",
      "text_color": "#FFFFFF",
      "font_size": 60,
      "stroke_color": "#000000",
      "stroke_width": 1.5
    }
    """

    video_subject: str
    video_script: str = ""  # Script used to generate the video
    video_terms: Optional[str | list] = None  # Keywords used to generate the video
    video_aspect: Optional[VideoAspect] = VideoAspect.portrait.value
    video_concat_mode: Optional[VideoConcatMode] = VideoConcatMode.random.value
    video_transition_mode: Optional[VideoTransitionMode] = None
    video_clip_duration: Optional[int] = 5
    match_materials_to_script: bool = False
    video_count: Optional[int] = 1

    video_source: Optional[str] = "pexels"
    video_materials: Optional[List[MaterialInfo]] = (
        None  # Materials used to generate the video
    )
    
    custom_audio_file: Optional[str] = None  # Custom audio file path, will ignore video_script and disable subtitle
    video_language: Optional[str] = ""  # auto detect

    voice_name: Optional[str] = ""
    voice_volume: Optional[float] = 1.0
    voice_rate: Optional[float] = 1.0
    bgm_type: Optional[str] = "random"
    bgm_file: Optional[str] = ""
    bgm_volume: Optional[float] = 0.2

    subtitle_enabled: Optional[bool] = True
    subtitle_position: Optional[str] = config.ui.get("subtitle_position", "bottom")  # top, bottom, center, custom
    custom_position: float = config.ui.get("custom_position", 70.0)
    font_name: Optional[str] = "STHeitiMedium.ttc"
    text_fore_color: Optional[str] = "#FFFFFF"
    text_background_color: Union[bool, str] = True
    rounded_subtitle_background: bool = False

    font_size: int = 60
    stroke_color: Optional[str] = "#000000"
    stroke_width: float = 1.5
    n_threads: Optional[int] = 2
    paragraph_number: int = Field(default=1, ge=1, le=10)
    video_script_prompt: str = Field(default="", max_length=2000)
    custom_system_prompt: str = Field(default="", max_length=8000)


class SubtitleRequest(BaseModel):
    video_script: str
    video_language: Optional[str] = ""
    voice_name: Optional[str] = "zh-CN-XiaoxiaoNeural-Female"
    voice_volume: Optional[float] = 1.0
    voice_rate: Optional[float] = 1.2
    bgm_type: Optional[str] = "random"
    bgm_file: Optional[str] = ""
    bgm_volume: Optional[float] = 0.2
    subtitle_position: Optional[str] = config.ui.get("subtitle_position", "bottom")
    font_name: Optional[str] = "STHeitiMedium.ttc"
    text_fore_color: Optional[str] = "#FFFFFF"
    text_background_color: Union[bool, str] = True
    rounded_subtitle_background: bool = False
    font_size: int = 60
    stroke_color: Optional[str] = "#000000"
    stroke_width: float = 1.5
    video_source: Optional[str] = "local"
    subtitle_enabled: Optional[str] = "true"


class AudioRequest(BaseModel):
    video_script: str
    video_language: Optional[str] = ""
    voice_name: Optional[str] = "zh-CN-XiaoxiaoNeural-Female"
    voice_volume: Optional[float] = 1.0
    voice_rate: Optional[float] = 1.2
    bgm_type: Optional[str] = "random"
    bgm_file: Optional[str] = ""
    bgm_volume: Optional[float] = 0.2
    video_source: Optional[str] = "local"


class VideoScriptParams:
    """
    {
      "video_subject": "春天的花海",
      "video_language": "",
      "paragraph_number": 1,
      "video_script_prompt": "",
      "custom_system_prompt": ""
    }
    """

    video_subject: Optional[str] = "春天的花海"
    video_language: Optional[str] = ""
    paragraph_number: int = Field(default=1, ge=1, le=10)
    video_script_prompt: str = Field(default="", max_length=2000)
    custom_system_prompt: str = Field(default="", max_length=8000)


class VideoTermsParams:
    """
    {
      "video_subject": "",
      "video_script": "",
      "amount": 5,
      "match_materials_to_script": false
    }
    """

    video_subject: Optional[str] = "春天的花海"
    video_script: Optional[str] = (
        "春天的花海，如诗如画般展现在眼前。万物复苏的季节里，大地披上了一袭绚丽多彩的盛装。金黄的迎春、粉嫩的樱花、洁白的梨花、艳丽的郁金香……"
    )
    amount: Optional[int] = 5
    match_materials_to_script: bool = False


class VideoSocialMetadataParams:
    """
    {
      "video_subject": "A day in Shanghai",
      "video_script": "",
      "language": "auto",
      "platform": "tiktok"
    }
    """

    video_subject: Optional[str] = Field(default="A day in Shanghai", max_length=500)
    video_script: Optional[str] = Field(default="", max_length=8000)
    language: Optional[str] = Field(default="auto", max_length=64)
    platform: Optional[str] = Field(default="tiktok", max_length=64)


class BaseResponse(BaseModel):
    status: int = 200
    message: Optional[str] = "success"
    data: Any = None


class TaskVideoRequest(VideoParams, BaseModel):
    pass


class TaskQueryRequest(BaseModel):
    pass


class VideoScriptRequest(VideoScriptParams, BaseModel):
    pass


class VideoTermsRequest(VideoTermsParams, BaseModel):
    pass


class VideoSocialMetadataRequest(VideoSocialMetadataParams, BaseModel):
    pass


######################################################################################################
######################################################################################################
######################################################################################################
######################################################################################################
class TaskResponse(BaseResponse):
    class TaskResponseData(BaseModel):
        task_id: str

    data: TaskResponseData

    class Config:
        json_schema_extra = {
            "example": {
                "status": 200,
                "message": "success",
                "data": {"task_id": "6c85c8cc-a77a-42b9-bc30-947815aa0558"},
            },
        }


class TaskQueryResponse(BaseResponse):
    class Config:
        json_schema_extra = {
            "example": {
                "status": 200,
                "message": "success",
                "data": {
                    "state": 1,
                    "progress": 100,
                    "videos": [
                        "http://127.0.0.1:8080/tasks/6c85c8cc-a77a-42b9-bc30-947815aa0558/final-1.mp4"
                    ],
                    "combined_videos": [
                        "http://127.0.0.1:8080/tasks/6c85c8cc-a77a-42b9-bc30-947815aa0558/combined-1.mp4"
                    ],
                },
            },
        }


class TaskDeletionResponse(BaseResponse):
    class Config:
        json_schema_extra = {
            "example": {
                "status": 200,
                "message": "success",
                "data": {
                    "state": 1,
                    "progress": 100,
                    "videos": [
                        "http://127.0.0.1:8080/tasks/6c85c8cc-a77a-42b9-bc30-947815aa0558/final-1.mp4"
                    ],
                    "combined_videos": [
                        "http://127.0.0.1:8080/tasks/6c85c8cc-a77a-42b9-bc30-947815aa0558/combined-1.mp4"
                    ],
                },
            },
        }


class VideoScriptResponse(BaseResponse):
    class Config:
        json_schema_extra = {
            "example": {
                "status": 200,
                "message": "success",
                "data": {
                    "video_script": "春天的花海，是大自然的一幅美丽画卷。在这个季节里，大地复苏，万物生长，花朵争相绽放，形成了一片五彩斑斓的花海..."
                },
            },
        }


class VideoTermsResponse(BaseResponse):
    class Config:
        json_schema_extra = {
            "example": {
                "status": 200,
                "message": "success",
                "data": {"video_terms": ["sky", "tree"]},
            },
        }


class VideoSocialMetadataResponse(BaseResponse):
    class Config:
        json_schema_extra = {
            "example": {
                "status": 200,
                "message": "success",
                "data": {
                    "title": "A Day in Shanghai You Should Not Miss",
                    "caption": "Save this quick Shanghai inspiration and follow for more short travel ideas.",
                    "hashtags": ["#shorts", "#travel", "#shanghai", "#viral", "#fyp"],
                },
            },
        }


class BgmRetrieveResponse(BaseResponse):
    class Config:
        json_schema_extra = {
            "example": {
                "status": 200,
                "message": "success",
                "data": {
                    "files": [
                        {
                            "name": "output013.mp3",
                            "size": 1891269,
                            "file": "/MoneyPrinterTurbo/resource/songs/output013.mp3",
                        }
                    ]
                },
            },
        }


class BgmUploadResponse(BaseResponse):
    class Config:
        json_schema_extra = {
            "example": {
                "status": 200,
                "message": "success",
                "data": {"file": "/MoneyPrinterTurbo/resource/songs/example.mp3"},
            },
        }

class VideoMaterialRetrieveResponse(BaseResponse):
    class Config:
        json_schema_extra = {
            "example": {
                "status": 200,
                "message": "success",
                "data": {
                    "files": [
                        {
                            "name": "example.mp4",
                            "size": 12345678,
                            "file": "/MoneyPrinterTurbo/resource/videos/example.mp4",
                        }
                    ]
                },
            },
        }

class VideoMaterialUploadResponse(BaseResponse):
    class Config:
        json_schema_extra = {
            "example": {
                "status": 200,
                "message": "success",
                "data": {
                    "file": "/MoneyPrinterTurbo/resource/videos/example.mp4",
                },
            },
        }


######################################################################################################
# Long-Form Video Models
######################################################################################################


class SceneInfo(BaseModel):
    """Individual scene in structured script for long-form videos"""
    index: int
    narration: str  # Text for TTS narration
    image_prompt: str  # Prompt for AI image generation (DALL-E, SD, etc.)
    duration_seconds: Optional[float] = None  # Override auto-calculated duration
    transition: Optional[str] = "fade"  # fade, slide, zoom, none
    narrative_role: Optional[str] = None  # hook, context, escalation, payoff, CTA
    visual_function: Optional[str] = None  # Establish, evidence, contrast, reveal
    open_loop: Optional[str] = None  # Question deliberately answered in a later scene
    source_note: Optional[str] = None  # Source or verification note for claims


class StructuredScript(BaseModel):
    """Complete structured script for a five-to-thirty-minute video."""
    title: str
    description: str
    total_duration_estimate: float  # 300-1800 seconds (5-30 min)
    scenes: List[SceneInfo]
    metadata: Optional[dict] = {}


class LongFormVideoParams(VideoParams):
    """Extended parameters for long-form video generation"""
    model_config = pydantic.ConfigDict(validate_default=True)
    # Script handling
    structured_script: Optional[StructuredScript] = None
    use_structured_script: bool = False

    # Image generation
    image_provider: Optional[str] = "dalle"  # dalle, sd (midjourney reserved, not implemented)
    image_quality: Optional[str] = "standard"  # standard, hd
    image_size: Optional[str] = "1024x1024"

    # Premium TTS
    premium_tts_provider: Optional[str] = None  # elevenlabs implemented; playht/murf reserved, not implemented

    # Thumbnail
    thumbnail_style: Optional[str] = "hybrid"  # hybrid, ai-only, template
    thumbnail_text: Optional[str] = ""
    animated_intro: bool = False
    cta_mode: str = "text"  # text, image, video
    cta_text: str = ""
    cta_asset_path: str = ""
    channel_logo_path: str = ""

    # Processing optimization
    enable_checkpointing: bool = True
    chunk_size_minutes: Optional[float] = 5.0
    max_scene_duration: Optional[float] = 30.0


class CheckpointState(BaseModel):
    """State for resumable long-form video tasks"""
    task_id: str
    current_phase: str  # script, audio, images, composition
    completed_scenes: List[int]
    generated_files: dict
    timestamp: float
    error_count: int = 0


# LLM Configuration and Script Generation Models

class LLMProvider(str, Enum):
    """Supported LLM providers for script generation"""
    OPENAI = "openai"
    CLAUDE = "claude"
    GEMINI = "gemini"
    DEEPSEEK = "deepseek"
    KIMI = "kimi"
    QWEN = "qwen"


class LLMConfig(BaseModel):
    """Configuration for a single LLM provider"""
    provider: LLMProvider
    api_key: str
    base_url: Optional[str] = None
    model: Optional[str] = None
    enabled: bool = True


class LLMConfigUpdate(BaseModel):
    """Update LLM provider configurations"""
    configs: List[LLMConfig]


class ScriptGenerationRequest(BaseModel):
    """Request to generate a structured script using LLM"""
    topic: str  # Main topic/subject for the video
    duration_minutes: float = 20.0  # Target duration (5-30 min)
    num_scenes: Optional[int] = None  # Auto-calculate if not provided
    language: str = "pt-BR"  # Language for narration
    style: Optional[str] = "educational"  # educational, documentary, entertaining
    target_audience: Optional[str] = None  # e.g., "general public", "tech enthusiasts"

    # LLM selection
    llm_provider: LLMProvider = LLMProvider.OPENAI

    # Advanced options
    keywords: Optional[List[str]] = []
    reference_urls: Optional[List[str]] = []
    custom_instructions: Optional[str] = None
    editorial_context: Optional[dict] = None  # Channel profile, brief, and selected packaging


class ScriptGenerationResponse(BaseModel):
    """Response containing generated structured script"""
    script: StructuredScript
    llm_provider: str
    model_used: str
    generation_time_seconds: float
    token_count: Optional[int] = None


######################################################################################################
# YouTube Upload Models
######################################################################################################


class YouTubeExchangeCodeRequest(BaseModel):
    """Request to exchange an OAuth authorization code for a token"""
    code: str


class YouTubeUploadRequest(BaseModel):
    """Request to upload a finished task video to YouTube"""
    task_id: str
    title: str
    description: str = ""
    tags: List[str] = []
    privacy_status: str = "private"  # private, unlisted, public
    category_id: str = "27"  # 27 = Education
    thumbnail_path: Optional[str] = None  # opcional, ex.: thumbnail.jpg dentro da tarefa


class YouTubeUploadRecord(BaseModel):
    """Registro de um upload no histórico (storage/youtube/uploads.jsonl)"""
    upload_id: str
    task_id: Optional[str] = None
    video_id: Optional[str] = None
    title: str = ""
    url: Optional[str] = None
    status: str = "pending"  # pending, uploading, completed, failed
    error: Optional[str] = None
    timestamp: float = 0.0


######################################################################################################
# SEO Models
######################################################################################################


class SEOAnalyzeRequest(BaseModel):
    """Request to analyze SEO of video metadata"""
    title: str
    description: str = ""
    keywords: List[str] = []
    script_title: Optional[str] = None


class SEOAnalyzeResponse(BaseModel):
    """Resultado da análise SEO heurística"""
    score: int  # 0-100
    checks: Dict[str, Any] = {}
    suggestions: List[str] = []


class SEOGenerateRequest(BaseModel):
    """Request to generate SEO metadata using LLM"""
    topic: str
    script: Optional[str] = None
    llm_provider: Optional[LLMProvider] = None


class SEOGenerateResponse(BaseModel):
    """Metadata SEO gerada pelo LLM"""
    titles: List[str] = []
    description: str = ""
    tags: List[str] = []
    hashtags: List[str] = []
    analysis: Optional[SEOAnalyzeResponse] = None


######################################################################################################
# Script Translation Models
######################################################################################################


class TranslateScriptRequest(BaseModel):
    """Request to translate a structured script to another language"""
    script: StructuredScript
    target_language: str
    llm_provider: Optional[LLMProvider] = None


######################################################################################################
# Batch Processing Models
######################################################################################################


class BatchVideoItem(BaseModel):
    """Item de um lote de vídeos longform"""
    # Modo 1: informar topic para gerar o roteiro via LLM antes de enfileirar
    topic: Optional[str] = None
    duration_minutes: float = 20.0
    language: str = "pt-BR"
    style: Optional[str] = "educational"
    llm_provider: Optional[LLMProvider] = None
    # Modo 2: parâmetros completos (ex.: com structured_script pronto)
    params: Optional[LongFormVideoParams] = None


class BatchVideoRequest(BaseModel):
    """Request to create a batch of long-form video tasks"""
    batch_id: Optional[str] = None
    requests: List[BatchVideoItem]


class BatchTaskStatus(BaseModel):
    """Estado de uma tarefa dentro de um lote"""
    task_id: str
    state: Optional[int] = None
    progress: Optional[int] = None


class BatchStatusResponse(BaseModel):
    """Status agregado de um lote"""
    batch_id: str
    task_ids: List[str]
    tasks: List[BatchTaskStatus]
    status: str = "processing"  # processing, completed, failed
    created_at: float = 0.0


######################################################################################################
# Analytics Models
######################################################################################################


class AnalyticsResponse(BaseModel):
    """Métricas agregadas de uso do sistema"""
    total_tasks: int = 0
    successful_tasks: int = 0
    failed_tasks: int = 0
    success_rate: float = 0.0
    avg_duration_seconds: float = 0.0
    by_provider: Dict[str, int] = {}
    by_task_type: Dict[str, int] = {}
    estimated_costs_usd: Dict[str, float] = {}
    videos_per_day: Dict[str, int] = {}
