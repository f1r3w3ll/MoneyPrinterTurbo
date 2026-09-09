"""
Analytics simples baseado em append de JSONL.

Cada tarefa concluída (com sucesso ou falha) grava um registro em
``storage/analytics/tasks.jsonl``. ``get_analytics`` agrega esses registros
em métricas gerais: total, taxa de sucesso, tempo médio, distribuição por
provider/fase e custos estimados com base em uma tabela de preços embutida.
"""

import json
import os
import time
from collections import defaultdict
from typing import Any, Dict, List, Optional

from loguru import logger

from app.config import config
from app.utils import utils

# Tabela simplificada de custos estimados por unidade (USD).
# Valores aproximados, usados apenas para estimativa agregada.
COST_TABLE = {
    "image": {
        "dalle": {"standard": 0.04, "hd": 0.08},
        "sd": {"standard": 0.02, "hd": 0.02},
        "midjourney": {"standard": 0.08, "hd": 0.08},
    },
    # Custo por 1M de tokens de saída (aproximado, usado quando há token_count)
    "llm_output_per_1m_tokens": {
        "openai": 10.0,
        "claude": 15.0,
        "gemini": 3.0,
        "deepseek": 2.0,
        "kimi": 3.0,
        "qwen": 3.0,
    },
    # Custo fixo estimado por tarefa quando não há contagem de tokens
    "llm_per_task": 0.03,
    # TTS: custo estimado por minuto de áudio gerado
    "tts_per_minute": 0.05,
}


def _analytics_file() -> str:
    """Resolve o arquivo de dados a partir da config, com fallback padrão."""
    cfg = getattr(config, "analytics", {}) or {}
    data_file = cfg.get("data_file", "./storage/analytics/tasks.jsonl")
    if not os.path.isabs(data_file):
        data_file = os.path.join(utils.root_dir(), data_file)
    return os.path.normpath(data_file)


def _is_enabled() -> bool:
    cfg = getattr(config, "analytics", {}) or {}
    return bool(cfg.get("enabled", True))


def record_task(
    task_id: str,
    params_summary: Optional[Dict[str, Any]],
    result: Optional[Dict[str, Any]],
    duration_seconds: float,
    success: bool,
    error: Optional[str] = None,
):
    """Grava um registro de tarefa no arquivo JSONL (append).

    Falhas de gravação são apenas logadas, nunca propagadas, para não
    quebrar a tarefa que acabou de executar.
    """
    if not _is_enabled():
        return

    record = {
        "task_id": task_id,
        "params_summary": params_summary or {},
        "result_summary": result or {},
        "duration_seconds": round(float(duration_seconds), 3),
        "success": bool(success),
        "error": error,
        "timestamp": time.time(),
    }

    try:
        data_file = _analytics_file()
        os.makedirs(os.path.dirname(data_file), exist_ok=True)
        with open(data_file, "a", encoding="utf-8") as fp:
            fp.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as exc:
        logger.warning(f"analytics: falha ao gravar registro da tarefa {task_id}: {exc}")


def _read_records() -> List[Dict[str, Any]]:
    data_file = _analytics_file()
    records = []
    if not os.path.isfile(data_file):
        return records
    try:
        with open(data_file, "r", encoding="utf-8") as fp:
            for line in fp:
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except Exception as exc:
        logger.warning(f"analytics: falha ao ler {data_file}: {exc}")
    return records


def _estimate_cost(record: Dict[str, Any]) -> Dict[str, float]:
    """Estima o custo de um registro com base na tabela embutida."""
    summary = record.get("params_summary") or {}
    result = record.get("result_summary") or {}
    cost = {"image": 0.0, "llm": 0.0, "tts": 0.0, "total": 0.0}

    if not record.get("success", False):
        return cost

    # Imagens geradas (longform)
    image_provider = (summary.get("image_provider") or "").lower()
    images = result.get("images") or {}
    num_images = len(images) if isinstance(images, (dict, list)) else 0
    if image_provider and num_images:
        quality = (summary.get("image_quality") or "standard").lower()
        price = (
            COST_TABLE["image"]
            .get(image_provider, COST_TABLE["image"]["dalle"])
            .get(quality, 0.04)
        )
        cost["image"] = round(num_images * price, 4)

    # LLM (script / metadados)
    llm_provider = (summary.get("llm_provider") or "").lower()
    token_count = result.get("token_count") or summary.get("token_count")
    if llm_provider and token_count:
        per_1m = COST_TABLE["llm_output_per_1m_tokens"].get(llm_provider, 10.0)
        cost["llm"] = round((token_count / 1_000_000) * per_1m, 4)
    elif llm_provider or summary.get("script_generated"):
        cost["llm"] = COST_TABLE["llm_per_task"]

    # TTS: estima pelo número de áudios/arquivos de áudio gerados
    audio_files = result.get("audio_files") or []
    audio_duration = result.get("audio_duration") or 0
    minutes = 0.0
    if audio_duration:
        minutes = float(audio_duration) / 60
    elif audio_files:
        minutes = len(audio_files) * 2.0  # estimativa conservadora
    if minutes:
        cost["tts"] = round(minutes * COST_TABLE["tts_per_minute"], 4)

    cost["total"] = round(cost["image"] + cost["llm"] + cost["tts"], 4)
    return cost


def get_analytics() -> Dict[str, Any]:
    """Agrega os registros JSONL em métricas resumidas."""
    records = _read_records()

    total = len(records)
    succeeded = [r for r in records if r.get("success")]
    durations = [r.get("duration_seconds", 0) for r in records]

    by_provider: Dict[str, int] = defaultdict(int)
    by_task_type: Dict[str, int] = defaultdict(int)
    cost_totals = {"image": 0.0, "llm": 0.0, "tts": 0.0, "total": 0.0}
    videos_per_day: Dict[str, int] = defaultdict(int)

    now = time.time()
    thirty_days_ago = now - 30 * 86400

    for record in records:
        summary = record.get("params_summary") or {}
        provider = summary.get("llm_provider") or summary.get("image_provider")
        if provider:
            by_provider[str(provider)] += 1
        task_type = summary.get("task_type") or "short"
        by_task_type[str(task_type)] += 1

        cost = _estimate_cost(record)
        for key in cost_totals:
            cost_totals[key] = round(cost_totals[key] + cost.get(key, 0.0), 4)

        if record.get("success") and record.get("timestamp", 0) >= thirty_days_ago:
            day = time.strftime("%Y-%m-%d", time.localtime(record["timestamp"]))
            videos_per_day[day] += 1

    return {
        "total_tasks": total,
        "successful_tasks": len(succeeded),
        "failed_tasks": total - len(succeeded),
        "success_rate": round(len(succeeded) / total, 4) if total else 0.0,
        "avg_duration_seconds": round(sum(durations) / total, 2) if total else 0.0,
        "by_provider": dict(by_provider),
        "by_task_type": dict(by_task_type),
        "estimated_costs_usd": cost_totals,
        "videos_per_day": dict(sorted(videos_per_day.items())),
    }
