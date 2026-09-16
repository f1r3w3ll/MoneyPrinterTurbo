"""Safe, actionable messages for external script-provider failures."""

PROVIDER_NAMES = {
    'openai': 'OpenAI', 'claude': 'Claude', 'gemini': 'Gemini',
    'deepseek': 'DeepSeek', 'kimi': 'Kimi', 'qwen': 'Qwen',
}

RETIRED_MODELS = {
    ('claude', 'claude-3-5-sonnet-20241022'): 'claude-sonnet-4-6',
    ('gemini', 'gemini-2.0-flash-exp'): 'gemini-3.5-flash',
}


def is_credit_exhausted(error) -> bool:
    """Return true only for permanent credit/quota exhaustion, never a transient 429."""
    detail = str(error).lower()
    markers = ('credit_balance_exhausted', 'insufficient_quota', 'quota_exceeded',
               'no credits remaining', 'insufficient credits')
    return any(marker in detail for marker in markers)


def model_status_message(provider, model):
    replacement = RETIRED_MODELS.get((provider, model))
    if replacement:
        return (f'O modelo {model} está descontinuado. Em Configurações, escolha '
                f'{replacement} antes de gerar o roteiro.')
    return ''


def explain_generation_error(provider, error):
    name = PROVIDER_NAMES.get(provider, str(provider))
    detail = str(error).strip()
    lowered = detail.lower()
    if 'connection' in lowered or 'connect' in lowered or 'timeout' in lowered:
        return (f'{name} não respondeu à solicitação. Verifique sua conexão, VPN/proxy e a '
                f'disponibilidade da API; depois tente novamente. Confira também o modelo em Configurações.')
    if any(term in lowered for term in ('authentication', 'unauthorized', 'api key', 'invalid key')):
        return f'A chave configurada para {name} foi recusada. Atualize-a em Configurações e tente novamente.'
    if any(term in lowered for term in ('model', 'not found', 'deprecated', 'retired')):
        return f'O modelo configurado para {name} não está disponível. Escolha um modelo atual em Configurações.'
    return f'Não foi possível gerar o roteiro com {name}: {detail or "erro desconhecido"}'
