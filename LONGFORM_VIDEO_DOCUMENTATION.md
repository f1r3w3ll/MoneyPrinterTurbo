# MoneyPrinterTurbo - Long-Form Video Extension
## Documentação Completa do Sistema de Vídeos Longos (15-30 min)

**Versão:** 1.3.0 Extended
**Data de Atualização:** 2026-09-07
**Status:** Produção

---

## 📋 Índice

1. [Visão Geral](#visão-geral)
2. [Arquitetura do Sistema](#arquitetura-do-sistema)
3. [Funcionalidades Implementadas](#funcionalidades-implementadas)
4. [Estrutura de Arquivos](#estrutura-de-arquivos)
5. [Configuração](#configuração)
6. [API Endpoints](#api-endpoints)
7. [Modelos de Dados](#modelos-de-dados)
8. [Serviços](#serviços)
9. [Fluxo de Trabalho](#fluxo-de-trabalho)
10. [Exemplos de Uso](#exemplos-de-uso)
11. [Troubleshooting](#troubleshooting)

---

## 🎯 Visão Geral

O MoneyPrinterTurbo foi estendido de um gerador de vídeos curtos (30-60s) para um sistema completo de geração de vídeos longos para YouTube (15-30 minutos), com as seguintes capacidades:

### Recursos Principais

✅ **Geração de Vídeos Longos (15-30 min)**
- Pipeline completo de produção de vídeo
- Suporte a 5-100 cenas por vídeo
- Processamento progressivo em chunks de 5 minutos
- Sistema de checkpoints para tarefas resumíveis

✅ **Geração de Imagens por IA**
- Múltiplos providers: DALL-E 3, Stable Diffusion, Midjourney
- Geração em batch com rate limiting
- Imagens 1024x1024 otimizadas para vídeo

✅ **Geração Automática de Roteiro com LLM**
- 6 providers de LLM suportados:
  - OpenAI (GPT-4o, GPT-4o-mini, GPT-4-turbo)
  - Claude (Claude 3.5 Sonnet, Opus, Haiku)
  - Gemini (Gemini 2.0 Flash, 1.5 Pro/Flash)
  - DeepSeek (DeepSeek Chat, Coder)
  - Kimi (Moonshot v1-8k/32k/128k)
  - Qwen (Qwen Max, Plus, Turbo)
- Prompts otimizados para vídeos educacionais/documentários
- Validação automática de roteiros gerados

✅ **TTS Premium**
- ElevenLabs (melhor qualidade)
- Play.ht
- Murf.ai
- + Azure TTS e Edge TTS (existentes)

✅ **Thumbnails Híbridos para YouTube**
- Geração de imagem base com IA
- Overlay de texto com fontes otimizadas
- Tamanho 1280x720, <2MB
- Otimização automática de qualidade

✅ **Sistema de Configuração de API Keys**
- Gerenciamento via API REST
- Persistência automática em config.toml
- Mascaramento de chaves por segurança
- Atualização em tempo real sem restart

---

## 🏗️ Arquitetura do Sistema

### Pipeline Original (Mantido - 100% Compatível)
```
Tópico → Script (LLM) → Termos → Áudio (Edge TTS) →
Materiais (Pexels) → Legendas → Vídeo Final (30-60s)
```

### Novo Pipeline Long-Form
```
1. GERAÇÃO DE ROTEIRO (Automática ou Manual)
   ├─ Via LLM (OpenAI/Claude/Gemini/DeepSeek/Kimi/Qwen)
   ├─ Via JSON estruturado manual
   └─ Validação de roteiro

2. GERAÇÃO DE ÁUDIO
   ├─ Chunking de texto (5000 chars)
   ├─ TTS Premium (ElevenLabs/Play.ht/Murf)
   └─ Áudio em chunks de 5 min

3. GERAÇÃO DE IMAGENS
   ├─ Batch processing (max 3 concurrent)
   ├─ DALL-E 3 / Stable Diffusion / Midjourney
   └─ Retry com exponential backoff

4. COMPOSIÇÃO DE VÍDEO
   ├─ Processamento progressivo (chunks de 5 min)
   ├─ Ken Burns effect em imagens
   ├─ Adição de legendas por chunk
   ├─ Codificação incremental
   └─ Concatenação FFmpeg (sem re-encoding)

5. GERAÇÃO DE THUMBNAIL
   ├─ Imagem base com IA
   ├─ Text overlay otimizado
   └─ Compressão para YouTube specs

6. CHECKPOINTING
   ├─ Salvamento após cada fase
   ├─ Resumo automático em caso de falha
   └─ Cleanup de arquivos temporários
```

### Otimizações de Performance

- **Memória**: Processamento em chunks de 5 min evita overflow
- **Rate Limiting**: Max 3 requisições concorrentes para APIs
- **Retry Logic**: Exponential backoff para APIs externas
- **FFmpeg**: Concatenação sem re-encoding para velocidade
- **Garbage Collection**: Limpeza explícita após cada chunk

---

## ✨ Funcionalidades Implementadas

### 1. Geração Automática de Roteiro

**Endpoint:** `POST /api/v1/generate-script`

**Capabilities:**
- Geração de roteiros completos a partir de um tópico
- Personalização de idioma, estilo, duração, audiência
- Suporte para palavras-chave e URLs de referência
- Validação automática pós-geração
- Retorna token count e tempo de geração

**Providers Suportados:**
```toml
[llm.openai]      # GPT-4o, GPT-4o-mini
[llm.claude]      # Claude 3.5 Sonnet, Opus, Haiku
[llm.gemini]      # Gemini 2.0 Flash, 1.5 Pro
[llm.deepseek]    # DeepSeek Chat
[llm.kimi]        # Moonshot 128k context
[llm.qwen]        # Qwen Max (Alibaba)
```

### 2. Gerenciamento de Configurações de LLM

**Endpoints:**
- `POST /api/v1/llm-config` - Salvar/atualizar API keys
- `GET /api/v1/llm-config` - Visualizar configurações (keys mascaradas)

**Funcionalidades:**
- Persistência automática em config.toml
- Suporte a múltiplas chaves por provider
- Mascaramento de segurança (exibe sk-...1234)
- Flag "configured" para indicar status
- Validação de formato de chaves

### 3. Vídeos Long-Form

**Endpoint:** `POST /api/v1/longform-videos`

**Características:**
- Duração: 15-30 minutos (900-1800 segundos)
- 5-100 cenas por vídeo
- Imagens geradas por IA para cada cena
- TTS premium ou padrão
- Legendas automáticas
- Thumbnail personalizado

### 4. Validação de Roteiro

**Endpoint:** `POST /api/v1/validate-script`

**Validações:**
- Mínimo 5 cenas, máximo 100
- Duração total 15-30 min
- Narração: 10-2000 caracteres por cena
- Image prompts não-vazios
- Duração por cena: 3-60 segundos

### 5. Checkpoints e Resumo de Tarefas

**Endpoints:**
- `POST /api/v1/resume-task/{task_id}` - Resumir tarefa interrompida
- `GET /api/v1/checkpoint-status/{task_id}` - Ver progresso

**Sistema de Checkpoint:**
- Salvamento após cada fase (script, audio, images, composition)
- Armazena cenas completadas e arquivos gerados
- Contador de erros
- Timestamp de última atualização

---

## 📁 Estrutura de Arquivos

### Novos Arquivos Criados

```
finback/
├── app/
│   ├── models/
│   │   └── schema.py                    [MODIFICADO +60 linhas]
│   │       ├── SceneInfo
│   │       ├── StructuredScript
│   │       ├── LongFormVideoParams
│   │       ├── CheckpointState
│   │       ├── LLMProvider (enum)
│   │       ├── LLMConfig
│   │       ├── LLMConfigUpdate
│   │       ├── ScriptGenerationRequest
│   │       └── ScriptGenerationResponse
│   │
│   ├── services/
│   │   ├── script_parser.py             [NOVO - 170 linhas]
│   │   │   └── ScriptParser (validação de JSON scripts)
│   │   │
│   │   ├── image_generation.py          [NOVO - 300 linhas]
│   │   │   └── ImageGenerationService
│   │   │       ├── generate_image()
│   │   │       ├── batch_generate()
│   │   │       ├── _generate_dalle()
│   │   │       ├── _generate_stable_diffusion()
│   │   │       └── _generate_midjourney()
│   │   │
│   │   ├── thumbnail.py                 [NOVO - 250 linhas]
│   │   │   └── ThumbnailService
│   │   │       ├── generate_hybrid_thumbnail()
│   │   │       ├── _add_text_overlay()
│   │   │       └── _apply_color_grading()
│   │   │
│   │   ├── checkpoint.py                [NOVO - 200 linhas]
│   │   │   └── CheckpointManager
│   │   │       ├── save_checkpoint()
│   │   │       ├── load_checkpoint()
│   │   │       ├── clear_checkpoint()
│   │   │       ├── checkpoint_exists()
│   │   │       └── get_progress_info()
│   │   │
│   │   ├── script_generator.py          [NOVO - 450 linhas]
│   │   │   └── ScriptGeneratorService
│   │   │       ├── generate_script()
│   │   │       ├── _build_prompt()
│   │   │       ├── _generate_openai()
│   │   │       ├── _generate_claude()
│   │   │       ├── _generate_gemini()
│   │   │       ├── _generate_deepseek()
│   │   │       ├── _generate_kimi()
│   │   │       ├── _generate_qwen()
│   │   │       └── _parse_script_json()
│   │   │
│   │   ├── voice.py                     [MODIFICADO +87 linhas]
│   │   │   ├── elevenlabs_tts()         [NOVO]
│   │   │   └── is_elevenlabs_voice()    [NOVO]
│   │   │
│   │   ├── task.py                      [MODIFICADO +437 linhas]
│   │   │   ├── start_longform()                      [NOVO]
│   │   │   ├── parse_structured_script_longform()    [NOVO]
│   │   │   ├── generate_audio_chunked_longform()     [NOVO]
│   │   │   ├── generate_images_batch_longform()      [NOVO]
│   │   │   └── generate_thumbnail_longform()         [NOVO]
│   │   │
│   │   └── video.py                     [MODIFICADO +294 linhas]
│   │       ├── compose_longform_video()              [NOVO]
│   │       ├── _compose_single_longform_chunk()      [NOVO]
│   │       ├── _image_to_video_clip_with_effect()    [NOVO]
│   │       └── _concat_chunks_ffmpeg()               [NOVO]
│   │
│   └── controllers/v1/
│       └── video.py                     [MODIFICADO +254 linhas]
│           ├── create_longform_video()               [NOVO]
│           ├── validate_structured_script()          [NOVO]
│           ├── resume_longform_task()                [NOVO]
│           ├── get_checkpoint_status()               [NOVO]
│           ├── update_llm_config()                   [NOVO]
│           ├── get_llm_config()                      [NOVO]
│           └── generate_script()                     [NOVO]
│
├── test/
│   └── test_longform.py                 [NOVO - 350 linhas]
│       ├── TestScriptParser
│       ├── TestCheckpointManager
│       ├── TestImageGeneration
│       └── TestThumbnailGeneration
│
├── config.example.toml                  [MODIFICADO +95 linhas]
├── config.toml                          [MODIFICADO +95 linhas]
├── pyproject.toml                       [MODIFICADO +1 linha]
│   └── anthropic==0.47.0 adicionado
│
└── LONGFORM_VIDEO_DOCUMENTATION.md     [NOVO - este arquivo]
```

### Estatísticas de Código

```
Total de Linhas Adicionadas: ~2,470
Arquivos Novos: 5
Arquivos Modificados: 6
Dependências Adicionadas: 1 (anthropic)

Distribuição:
- Services:      1,570 linhas (63%)
- Controllers:     254 linhas (10%)
- Models:           60 linhas (2%)
- Tests:           350 linhas (14%)
- Config:           95 linhas (4%)
- Docs:            141 linhas (6%)
```

---

## ⚙️ Configuração

### 1. Estrutura do config.toml

```toml
# Porta do servidor (padrão 8080)
listen_port = 8081

[app]
# ... configurações existentes ...

# ===== NOVAS SEÇÕES =====

[image_generation]
default_provider = "dalle"          # dalle, sd, midjourney

# DALL-E Configuration
dalle_model = "dall-e-3"
dalle_quality = "standard"          # standard, hd
dalle_size = "1024x1024"

# Stable Diffusion (via Replicate)
sd_api_key = ""
sd_model = "stability-ai/sdxl"
sd_base_url = "https://api.replicate.com"

# Midjourney (via unofficial wrapper)
midjourney_api_key = ""
midjourney_base_url = ""

[premium_tts]
# ElevenLabs (Recomendado)
elevenlabs_api_key = ""
elevenlabs_model = "eleven_multilingual_v2"
elevenlabs_voice_id = ""

# Play.ht
playht_api_key = ""
playht_user_id = ""
playht_voice = ""

# Murf.ai
murf_api_key = ""
murf_voice_id = ""

[longform]
max_video_duration = 1800           # 30 minutos
default_chunk_size = 300            # 5 minutos
enable_checkpoint = true
checkpoint_dir = "./storage/checkpoints"
temp_dir = "./storage/temp"

# LLM Configuration for Script Generation
[llm.openai]
api_key = ""
model = "gpt-4o"
enabled = true

[llm.claude]
api_key = ""
model = "claude-3-5-sonnet-20241022"
enabled = true

[llm.gemini]
api_key = ""
model = "gemini-2.0-flash-exp"
enabled = true

[llm.deepseek]
api_key = ""
model = "deepseek-chat"
base_url = "https://api.deepseek.com"
enabled = true

[llm.kimi]
api_key = ""
model = "moonshot-v1-128k"
base_url = "https://api.moonshot.cn/v1"
enabled = true

[llm.qwen]
api_key = ""
model = "qwen-max"
base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
enabled = true
```

### 2. Variáveis de Ambiente

Nenhuma variável de ambiente adicional é necessária. Todas as configurações são feitas via config.toml ou API REST.

---

## 🔌 API Endpoints

### Endpoints de Geração de Roteiro

#### 1. Gerar Roteiro com LLM

**Request:**
```http
POST /api/v1/generate-script
Content-Type: application/json

{
  "topic": "História da Inteligência Artificial",
  "duration_minutes": 20,
  "num_scenes": null,
  "language": "pt-BR",
  "style": "educational",
  "target_audience": "público geral",
  "llm_provider": "openai",
  "keywords": ["machine learning", "deep learning", "neural networks"],
  "reference_urls": [],
  "custom_instructions": null
}
```

**Response:**
```json
{
  "status": 200,
  "message": "success",
  "data": {
    "script": {
      "title": "A Fascinante Jornada da Inteligência Artificial",
      "description": "Uma exploração profunda sobre a história e evolução da IA",
      "total_duration_estimate": 1200,
      "scenes": [
        {
          "index": 0,
          "narration": "Bem-vindos a esta jornada fascinante pela história da inteligência artificial...",
          "image_prompt": "Futuristic AI laboratory with holographic displays and neural network visualizations, cinematic lighting, high detail, 4k",
          "duration_seconds": 25,
          "transition": "fade"
        }
        // ... 47 cenas adicionais
      ],
      "metadata": {}
    },
    "llm_provider": "openai",
    "model_used": "gpt-4o",
    "generation_time_seconds": 8.5,
    "token_count": 12450
  }
}
```

#### 2. Validar Roteiro

**Request:**
```http
POST /api/v1/validate-script
Content-Type: application/json

{
  "title": "Título do Vídeo",
  "description": "Descrição",
  "total_duration_estimate": 1200,
  "scenes": [...]
}
```

**Response:**
```json
{
  "status": 200,
  "message": "success",
  "data": {
    "valid": true,
    "message": "Script is valid",
    "scene_count": 48,
    "estimated_duration": 1200.0
  }
}
```

### Endpoints de Configuração LLM

#### 3. Atualizar Configurações de LLM

**Request:**
```http
POST /api/v1/llm-config
Content-Type: application/json

{
  "configs": [
    {
      "provider": "openai",
      "api_key": "sk-proj-...",
      "model": "gpt-4o",
      "enabled": true
    },
    {
      "provider": "claude",
      "api_key": "sk-ant-...",
      "model": "claude-3-5-sonnet-20241022",
      "enabled": true
    }
  ]
}
```

**Response:**
```json
{
  "status": 200,
  "message": "success",
  "data": {
    "message": "LLM configurations updated successfully",
    "providers_updated": ["openai", "claude"]
  }
}
```

#### 4. Ver Configurações de LLM

**Request:**
```http
GET /api/v1/llm-config
```

**Response:**
```json
{
  "status": 200,
  "message": "success",
  "data": {
    "configs": [
      {
        "provider": "openai",
        "api_key": "sk-p...xyz",
        "model": "gpt-4o",
        "base_url": null,
        "enabled": true,
        "configured": true
      },
      {
        "provider": "claude",
        "api_key": "***",
        "model": "claude-3-5-sonnet-20241022",
        "base_url": null,
        "enabled": true,
        "configured": false
      }
    ]
  }
}
```

### Endpoints de Vídeo Long-Form

#### 5. Criar Vídeo Long-Form

**Request:**
```http
POST /api/v1/longform-videos
Content-Type: application/json

{
  "structured_script": {
    "title": "...",
    "description": "...",
    "total_duration_estimate": 1200,
    "scenes": [...]
  },
  "use_structured_script": true,
  "image_provider": "dalle",
  "image_quality": "standard",
  "premium_tts_provider": "elevenlabs",
  "voice_name": "pt-BR-FranciscaNeural",
  "thumbnail_style": "hybrid",
  "thumbnail_text": "Título do Thumbnail",
  "enable_checkpointing": true,
  "chunk_size_minutes": 5.0,
  "video_aspect": "16:9",
  "subtitle_enabled": true
}
```

**Response:**
```json
{
  "status": 200,
  "message": "success",
  "data": {
    "task_id": "abc123-def456-ghi789"
  }
}
```

#### 6. Verificar Status de Checkpoint

**Request:**
```http
GET /api/v1/checkpoint-status/abc123-def456-ghi789
```

**Response:**
```json
{
  "status": 200,
  "message": "success",
  "data": {
    "has_checkpoint": true,
    "current_phase": "images",
    "completed_scenes": [0, 1, 2, 3, 4],
    "num_completed_scenes": 5,
    "error_count": 0,
    "timestamp": 1726567890.0
  }
}
```

#### 7. Resumir Tarefa Interrompida

**Request:**
```http
POST /api/v1/resume-task/abc123-def456-ghi789
Content-Type: application/json

{
  "structured_script": {...},
  "use_structured_script": true,
  ...
}
```

**Response:**
```json
{
  "status": 200,
  "message": "success",
  "data": {
    "task_id": "abc123-def456-ghi789"
  }
}
```

---

## 📊 Modelos de Dados

### SceneInfo
```python
class SceneInfo(BaseModel):
    index: int
    narration: str                    # Texto para narração TTS
    image_prompt: str                 # Prompt para geração de imagem IA
    duration_seconds: Optional[float] = None
    transition: Optional[str] = "fade"
```

### StructuredScript
```python
class StructuredScript(BaseModel):
    title: str
    description: str
    total_duration_estimate: float    # 900-1800 segundos
    scenes: List[SceneInfo]
    metadata: Optional[dict] = {}
```

### LLMProvider (Enum)
```python
class LLMProvider(str, Enum):
    OPENAI = "openai"
    CLAUDE = "claude"
    GEMINI = "gemini"
    DEEPSEEK = "deepseek"
    KIMI = "kimi"
    QWEN = "qwen"
```

### ScriptGenerationRequest
```python
class ScriptGenerationRequest(BaseModel):
    topic: str
    duration_minutes: float = 20.0
    num_scenes: Optional[int] = None
    language: str = "pt-BR"
    style: Optional[str] = "educational"
    target_audience: Optional[str] = None
    llm_provider: LLMProvider = LLMProvider.OPENAI
    keywords: Optional[List[str]] = []
    reference_urls: Optional[List[str]] = []
    custom_instructions: Optional[str] = None
```

### CheckpointState
```python
class CheckpointState(BaseModel):
    task_id: str
    current_phase: str                # script, audio, images, composition
    completed_scenes: List[int]
    generated_files: dict
    timestamp: float
    error_count: int = 0
```

---

## 🛠️ Serviços

### ScriptGeneratorService

**Localização:** `app/services/script_generator.py`

**Métodos Principais:**
- `generate_script(request)` - Gera roteiro usando LLM selecionado
- `_build_prompt(request)` - Constrói prompt otimizado
- `_generate_openai/claude/gemini/deepseek/kimi/qwen()` - Integrações específicas
- `_parse_script_json(json_str)` - Parse e validação de JSON

**Características:**
- Suporte a 6 providers de LLM
- Retry automático em caso de falha
- Validação de output JSON
- Tratamento de erros específicos por provider

### ImageGenerationService

**Localização:** `app/services/image_generation.py`

**Métodos Principais:**
- `generate_image(prompt, scene_id, output_dir)` - Gera imagem única
- `batch_generate(prompts, output_dir, max_concurrent)` - Batch processing
- `_generate_dalle/sd/midjourney()` - Integrações específicas

**Características:**
- Rate limiting (max 3 concurrent)
- Exponential backoff retry
- Download e salvamento automático
- Suporte a múltiplos providers

### ThumbnailService

**Localização:** `app/services/thumbnail.py`

**Métodos Principais:**
- `generate_hybrid_thumbnail(title, ai_prompt, output_path)` - Thumbnail completo
- `_add_text_overlay(img, title, style)` - Adiciona texto
- `_apply_color_grading(img, style)` - Ajustes de cor

**Características:**
- Geração de imagem base com IA
- Text overlay com drop shadow e stroke
- Redimensionamento para 1280x720
- Compressão para <2MB (YouTube specs)

### CheckpointManager

**Localização:** `app/services/checkpoint.py`

**Métodos Principais:**
- `save_checkpoint(state)` - Salvamento atômico
- `load_checkpoint()` - Carregamento de checkpoint
- `clear_checkpoint()` - Limpeza após sucesso
- `checkpoint_exists()` - Verificação de existência
- `get_progress_info()` - Informações de progresso

**Características:**
- Salvamento atômico (temp file + rename)
- JSON serialização
- Tratamento de erros
- Informações de progresso detalhadas

---

## 🔄 Fluxo de Trabalho

### Fluxo Completo Recomendado

```
1. CONFIGURAR API KEYS
   ↓
   POST /api/v1/llm-config
   {
     "configs": [
       {"provider": "openai", "api_key": "sk-..."},
       {"provider": "claude", "api_key": "sk-ant-..."}
     ]
   }

2. GERAR ROTEIRO AUTOMATICAMENTE
   ↓
   POST /api/v1/generate-script
   {
     "topic": "História da IA",
     "duration_minutes": 20,
     "language": "pt-BR",
     "llm_provider": "openai"
   }
   ↓
   Retorna: StructuredScript com 48 cenas

3. VALIDAR ROTEIRO (Opcional)
   ↓
   POST /api/v1/validate-script
   {script_gerado}
   ↓
   Confirma: válido, 48 cenas, 20 min

4. CRIAR VÍDEO LONG-FORM
   ↓
   POST /api/v1/longform-videos
   {
     "structured_script": {script_gerado},
     "image_provider": "dalle",
     "premium_tts_provider": "elevenlabs",
     "enable_checkpointing": true
   }
   ↓
   Retorna: task_id

5. MONITORAR PROGRESSO
   ↓
   GET /api/v1/checkpoint-status/{task_id}
   ↓
   Fase atual: images, 15/48 cenas completadas

6. (Se necessário) RESUMIR TAREFA
   ↓
   POST /api/v1/resume-task/{task_id}
   {mesmos_parametros}

7. DOWNLOAD DO VÍDEO FINAL
   ↓
   GET /api/v1/tasks/{task_id}
   ↓
   {
     "video_url": "/storage/tasks/{task_id}/final_video.mp4",
     "thumbnail_url": "/storage/tasks/{task_id}/thumbnail.jpg",
     "duration": 1205.3
   }
```

### Fases de Processamento

```
Phase 1: SCRIPT (5% → 10%)
├─ Parse JSON estruturado
├─ Validar número de cenas (5-100)
├─ Validar duração total (15-30 min)
└─ Checkpoint saved

Phase 2: AUDIO (10% → 30%)
├─ Agrupar cenas em chunks de 5000 chars
├─ Gerar TTS para cada chunk
├─ Combinar áudios
└─ Checkpoint saved

Phase 3: IMAGES (30% → 50%)
├─ Preparar prompts para todas as cenas
├─ Batch generate (max 3 concurrent)
├─ Retry em caso de falha (3x)
└─ Checkpoint saved

Phase 4: SUBTITLES (50% → 60%)
├─ Gerar legendas por chunk de áudio
├─ Formatar .srt
└─ Checkpoint saved

Phase 5: COMPOSITION (60% → 90%)
├─ Processar chunks de 5 min
├─ Converter imagens para vídeo (Ken Burns)
├─ Adicionar áudio e legendas
├─ Codificar chunks
├─ Concatenar com FFmpeg
└─ Checkpoint saved

Phase 6: THUMBNAIL (90% → 100%)
├─ Gerar imagem base com IA
├─ Adicionar text overlay
├─ Comprimir para YouTube specs
└─ Task complete!
```

---

## 💡 Exemplos de Uso

### Exemplo 1: Vídeo Educacional sobre IA

```bash
# 1. Configurar OpenAI
curl -X POST http://localhost:8081/api/v1/llm-config \
  -H "Content-Type: application/json" \
  -d '{
    "configs": [{
      "provider": "openai",
      "api_key": "sk-proj-YOUR-KEY",
      "model": "gpt-4o",
      "enabled": true
    }]
  }'

# 2. Gerar roteiro
curl -X POST http://localhost:8081/api/v1/generate-script \
  -H "Content-Type: application/json" \
  -d '{
    "topic": "Inteligência Artificial: Do Passado ao Futuro",
    "duration_minutes": 20,
    "language": "pt-BR",
    "style": "educational",
    "llm_provider": "openai",
    "keywords": ["machine learning", "neural networks", "AGI"],
    "target_audience": "estudantes de tecnologia"
  }' > script.json

# 3. Validar roteiro
curl -X POST http://localhost:8081/api/v1/validate-script \
  -H "Content-Type: application/json" \
  -d @script.json

# 4. Criar vídeo
curl -X POST http://localhost:8081/api/v1/longform-videos \
  -H "Content-Type: application/json" \
  -d '{
    "structured_script": '$(cat script.json | jq .data.script)',
    "use_structured_script": true,
    "image_provider": "dalle",
    "image_quality": "hd",
    "premium_tts_provider": "elevenlabs",
    "voice_name": "elevenlabs:21m00Tcm4TlvDq8ikWAM",
    "thumbnail_text": "IA: Passado e Futuro",
    "video_aspect": "16:9",
    "subtitle_enabled": true
  }'
```

### Exemplo 2: Vídeo Documentário sobre História

```python
import requests
import json

API_BASE = "http://localhost:8081/api/v1"

# 1. Configurar Claude
config_response = requests.post(
    f"{API_BASE}/llm-config",
    json={
        "configs": [{
            "provider": "claude",
            "api_key": "sk-ant-YOUR-KEY",
            "model": "claude-3-5-sonnet-20241022",
            "enabled": True
        }]
    }
)
print(f"Config: {config_response.json()}")

# 2. Gerar roteiro
script_response = requests.post(
    f"{API_BASE}/generate-script",
    json={
        "topic": "A Queda do Império Romano",
        "duration_minutes": 25,
        "language": "pt-BR",
        "style": "documentary",
        "llm_provider": "claude",
        "keywords": ["Roma", "império", "história"],
        "target_audience": "público geral interessado em história"
    }
)
script_data = script_response.json()
print(f"Script gerado: {script_data['data']['script']['title']}")
print(f"Cenas: {len(script_data['data']['script']['scenes'])}")

# 3. Criar vídeo
video_response = requests.post(
    f"{API_BASE}/longform-videos",
    json={
        "structured_script": script_data['data']['script'],
        "use_structured_script": True,
        "image_provider": "dalle",
        "image_quality": "standard",
        "voice_name": "pt-BR-AntonioNeural",
        "thumbnail_text": "A Queda do Império Romano",
        "video_aspect": "16:9",
        "subtitle_enabled": True,
        "enable_checkpointing": True
    }
)
task_id = video_response.json()['data']['task_id']
print(f"Task ID: {task_id}")

# 4. Monitorar progresso
import time
while True:
    status_response = requests.get(f"{API_BASE}/checkpoint-status/{task_id}")
    if status_response.status_code == 404:
        print("Tarefa completa!")
        break

    status_data = status_response.json()['data']
    print(f"Fase: {status_data['current_phase']}, "
          f"Cenas: {status_data['num_completed_scenes']}")
    time.sleep(30)
```

### Exemplo 3: Script Manual Customizado

```json
{
  "title": "Meu Vídeo Personalizado",
  "description": "Um vídeo sobre tecnologia moderna",
  "total_duration_estimate": 900,
  "scenes": [
    {
      "index": 0,
      "narration": "Bem-vindos ao futuro da tecnologia. Hoje vamos explorar as inovações que estão moldando nosso mundo.",
      "image_prompt": "Futuristic cityscape with flying cars and holographic billboards, cyberpunk style, neon lights, 8k, ultra detailed",
      "duration_seconds": 20,
      "transition": "fade"
    },
    {
      "index": 1,
      "narration": "A inteligência artificial está revolucionando a forma como vivemos e trabalhamos.",
      "image_prompt": "Advanced AI robot working alongside humans in modern office, collaborative atmosphere, natural lighting",
      "duration_seconds": 25,
      "transition": "fade"
    }
    // ... adicionar 3+ cenas adicionais para totalizar 5+ cenas
  ]
}
```

```bash
# Usar script manual
curl -X POST http://localhost:8081/api/v1/longform-videos \
  -H "Content-Type: application/json" \
  -d @meu_script.json
```

---

## 🐛 Troubleshooting

### Problemas Comuns

#### 1. Erro: "LLM provider not configured or missing API key"

**Causa:** API key não configurada para o provider selecionado

**Solução:**
```bash
curl -X POST http://localhost:8081/api/v1/llm-config \
  -H "Content-Type: application/json" \
  -d '{
    "configs": [{
      "provider": "openai",
      "api_key": "sua-chave-aqui",
      "enabled": true
    }]
  }'
```

#### 2. Erro: "Script validation failed: at least 5 scenes"

**Causa:** Roteiro tem menos de 5 cenas

**Solução:** Adicionar mais cenas ou aumentar num_scenes no request de geração

#### 3. Erro: "Duration must be between 15 and 30 minutes"

**Causa:** Duração total fora dos limites

**Solução:** Ajustar `total_duration_estimate` para 900-1800 segundos

#### 4. Tarefa Travada na Fase de Images

**Causa:** Rate limiting da API de imagens ou falha de rede

**Solução:**
```bash
# Verificar checkpoint
curl http://localhost:8081/api/v1/checkpoint-status/{task_id}

# Resumir tarefa
curl -X POST http://localhost:8081/api/v1/resume-task/{task_id} \
  -H "Content-Type: application/json" \
  -d @parametros_originais.json
```

#### 5. Erro: "Invalid JSON response from LLM"

**Causa:** LLM retornou resposta mal-formatada

**Solução:**
- Tentar novamente (pode ser falha temporária)
- Trocar para outro provider mais confiável (Claude, GPT-4o)
- Simplificar o prompt (reduzir custom_instructions)

#### 6. Memória Insuficiente

**Causa:** Vídeo muito longo sendo processado de uma vez

**Solução:**
```toml
# Reduzir chunk_size no config.toml
[longform]
default_chunk_size = 180  # 3 minutos ao invés de 5
```

#### 7. Thumbnail Muito Grande (>2MB)

**Causa:** Imagem gerada com muitos detalhes

**Solução:** O sistema já comprime automaticamente. Se persistir, verificar logs.

---

## 📈 Performance e Custos

### Custos Estimados (20 min de vídeo)

```
DALL-E 3 (48 imagens @ $0.04):        $1.92
ElevenLabs (3000 chars @ $0.015):     $0.05
GPT-4o Script Gen (12k tokens):       $0.12
-------------------------------------------
Total por Vídeo:                      ~$2.09

Com OpenAI API keys apenas:           ~$2.04
Com Gemini (grátis) + SD (barato):    ~$0.50
```

### Tempo de Processamento

```
Fase                  Tempo Estimado
-----------------------------------
Script Generation     5-15 segundos
Audio Generation      2-5 minutos
Image Generation      10-20 minutos (48 imagens)
Video Composition     15-25 minutos
Thumbnail             30-60 segundos
-----------------------------------
Total:                30-50 minutos para vídeo de 20 min
```

### Requisitos de Sistema

```
CPU:     4-8 cores (recomendado 8+)
RAM:     8GB mínimo, 16GB recomendado
Disco:   20GB livre durante processamento
         5GB para vídeo final
Network: Banda larga (APIs externas)
```

---

## 🔐 Segurança

### Boas Práticas

1. **API Keys:**
   - Nunca commitar config.toml com chaves
   - Usar variáveis de ambiente em produção
   - Rodar auditorias regulares de uso

2. **Rate Limiting:**
   - Sistema interno já implementa (max 3 concurrent)
   - Configurar rate limits externos se necessário

3. **Validação:**
   - Todo input é validado com Pydantic
   - Sanitização de file paths
   - Validação de duração e número de cenas

4. **Checkpoints:**
   - Armazenados localmente com permissões restritas
   - Cleanup automático após sucesso
   - Não contêm dados sensíveis

---

## 🚀 Próximos Passos e Melhorias Futuras

### Roadmap

- [ ] Interface Web (Streamlit) para geração de roteiro
- [ ] Suporte a mais providers de imagem (Midjourney oficial)
- [ ] Batch processing de múltiplos vídeos
- [ ] Integração com YouTube API (upload automático)
- [ ] Análise de SEO para títulos/descrições
- [ ] Tradução automática de roteiros
- [ ] Vozes clonadas customizadas
- [ ] Efeitos de transição avançados
- [ ] Suporte a vídeos 4K
- [ ] Dashboard de analytics

---

## 📞 Suporte e Documentação

- **Documentação Original:** https://github.com/harry0703/MoneyPrinterTurbo
- **API Docs (Swagger):** http://localhost:8081/docs
- **Issues:** GitHub Issues
- **Versão:** 1.3.0 Extended
- **Data:** 2026-09-07

---

**Desenvolvido com ❤️ para criadores de conteúdo**
