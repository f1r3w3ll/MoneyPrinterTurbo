"""Local long-form studio. Workers and persistence belong to app.services.studio."""
import importlib
import importlib.util
import json
from datetime import datetime
from pathlib import Path

import streamlit as st

from app.models.schema import LongFormVideoParams, ScriptGenerationRequest
from app.services import editorial
from app.services.script_parser import ScriptParser
from app.services.studio_settings import redact
from app.services.provider_errors import explain_generation_error, model_status_message

ROOT = Path(__file__).resolve().parents[1]
STATUS = {'queued': 'Na fila', 'running': 'Produzindo', 'failed': 'Falhou', 'interrupted': 'Interrompido', 'complete': 'Concluído'}
PHASES = {'queue': 'Aguardando na fila', 'script': 'Preparando roteiro', 'audio': 'Gerando narração',
          'images': 'Gerando imagens', 'subtitles': 'Preparando legendas',
          'composition': 'Compondo vídeo', 'thumbnail': 'Criando thumbnail', 'complete': 'Concluído'}
PREMIUM_VOICE_OPTIONS = (
    ('Homem · português', 'elevenlabs:UP5aPvvfM4UCXZrr3fdX'),
    ('Mulher · português', 'elevenlabs:lWq4KDY8znfkV0DrK8Vb'),
    ('Mulher · inglês', 'elevenlabs:lWq4KDY8znfkV0DrK8Vb'),
    ('Homem · inglês', 'elevenlabs:wBXNqKUATyqu0RtYt25i'),
)
VIDEO_LANGUAGE_LABELS = {
    'pt-BR': 'Português (Brasil)', 'en-US': 'Inglês (EUA)',
    'de-DE': 'Alemão', 'es-ES': 'Espanhol',
}
STUDIO_STYLE = """
<style>
.studio-hero {
    background: linear-gradient(120deg, #0b2545, #173f6d);
    border-radius: 14px;
    color: #ffffff;
    margin: 0 0 1.25rem;
    padding: 1.35rem 1.5rem;
}
.studio-hero h1 { color: #ffffff; font-size: 2rem; margin: 0; }
.studio-hero p { color: #e5f0ff; margin: .3rem 0 0; }
.studio-flow {
    display: flex;
    flex-wrap: wrap;
    gap: .55rem;
    margin-top: 1rem;
}
.studio-flow span {
    background: rgba(255, 255, 255, .16);
    border-radius: 999px;
    color: #ffffff;
    font-size: .88rem;
    padding: .35rem .7rem;
}
@media (max-width: 640px) {
    .studio-hero { padding: 1.1rem; }
    .studio-hero h1 { font-size: 1.65rem; }
}
</style>
"""


def _load(script, draft_id=None):
    st.session_state.studio_script = script
    st.session_state.studio_draft_id = draft_id
    st.session_state.studio_revision = st.session_state.get('studio_revision', 0) + 1
    package = (script.get('metadata') or {}).get('editorial', {}).get('selected_package', {})
    st.session_state.output_thumbnail_text = package.get('thumbnail_text') or script.get('title', '')


def _narration_duration_estimate(script):
    """Estimate narration time before costly media generation begins."""
    parsed = ScriptParser().parse_json_script(script)
    metadata = parsed.metadata or {}
    language = metadata.get('script_language')
    estimated_seconds = ScriptParser().estimate_total_duration(parsed, language=language)
    target_seconds = metadata.get('target_duration_seconds')
    return estimated_seconds, target_seconds


def _duration_is_on_target(estimated_seconds, target_seconds):
    """Allow a small planning margin; final audio is still measured later."""
    if not target_seconds:
        return True
    return target_seconds * 0.75 <= estimated_seconds <= target_seconds * 1.2


def _channel_profile_editor():
    channels = editorial.list_channels()
    active_id = editorial.active_channel_id()
    with st.expander('Canais e linha editorial', expanded=True):
        selected_id = st.selectbox(
            'Canal ativo',
            [channel['id'] for channel in channels],
            index=[channel['id'] for channel in channels].index(active_id),
            format_func=lambda channel_id: next(channel['name'] for channel in channels if channel['id'] == channel_id),
            key='active_editorial_channel',
        )
        if selected_id != active_id:
            editorial.set_active_channel(selected_id)
            for key in ('studio_brief', 'generated_studio_brief', 'brief_language', 'brief_topic', 'brief_question', 'brief_thesis', 'brief_promise', 'brief_goal', 'brief_sources'):
                st.session_state.pop(key, None)
            st.rerun()
        with st.form('new_editorial_channel'):
            new_name, new_niche = st.columns(2)
            with new_name:
                channel_name = st.text_input('Nome do novo canal')
            with new_niche:
                channel_niche = st.text_input('Nicho do novo canal')
            if st.form_submit_button('Criar canal'):
                try:
                    editorial.create_channel({'name': channel_name, 'niche': channel_niche})
                    for key in ('studio_brief', 'generated_studio_brief', 'brief_topic', 'brief_question', 'brief_thesis', 'brief_promise', 'brief_goal', 'brief_sources'):
                        st.session_state.pop(key, None)
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))
    profile = editorial.get_channel_profile()
    with st.expander('1 · Identidade editorial do canal', expanded=True):
        st.caption('Edite a linha editorial do canal ativo. Ela orienta pauta, embalagem e roteiro, sem substituir sua revisão final.')
        with st.form('channel_profile'):
            name = st.text_input('Nome do canal', value=profile['name'])
            niche, subniche = st.columns(2)
            with niche:
                channel_niche = st.text_input('Nicho', value=profile['niche'], placeholder='Ex.: História e tecnologia')
            with subniche:
                channel_subniche = st.text_input('Recorte', value=profile['subniche'], placeholder='Ex.: decisões que moldaram a internet')
            audience = st.text_input('Público principal', value=profile['audience'])
            promise = st.text_area('Promessa do canal', value=profile['promise'], placeholder='O que a pessoa aprende ou sente ao assistir?')
            language_options = list(VIDEO_LANGUAGE_LABELS)
            channel_language = st.selectbox('Idioma padrão do canal', language_options,
                index=language_options.index(profile['language']) if profile['language'] in language_options else 0,
                format_func=VIDEO_LANGUAGE_LABELS.get)
            tone = st.selectbox('Tom', ['documentary', 'educational', 'entertaining'], index=['documentary', 'educational', 'entertaining'].index(profile['tone'] if profile['tone'] in ('documentary', 'educational', 'entertaining') else 'documentary'), format_func=lambda value: {'documentary': 'Documentário', 'educational': 'Educacional', 'entertaining': 'Entretenimento'}[value])
            pillars = st.text_area('Pilares e séries', value=profile['pillars'], placeholder='Ex.: guerras da tecnologia; infraestruturas invisíveis')
            visual_style = st.text_input('Direção visual', value=profile['visual_style'], placeholder='Ex.: documental cinematográfica, arquivos e infográficos')
            source_policy = st.text_area('Política de fontes', value=profile['source_policy'], placeholder='Ex.: priorizar fontes primárias e indicar incertezas')
            restricted = st.text_input('Assuntos ou abordagens a evitar', value=profile['restricted_topics'])
            if st.form_submit_button('Salvar identidade editorial'):
                editorial.save_channel_profile({'name': name, 'niche': channel_niche, 'subniche': channel_subniche, 'audience': audience, 'promise': promise, 'language': channel_language, 'tone': tone, 'pillars': pillars, 'visual_style': visual_style, 'source_policy': source_policy, 'restricted_topics': restricted})
                st.success('Identidade editorial salva.')
                profile = editorial.get_channel_profile()
    return profile


def _brief_and_packaging(profile):
    st.subheader('1 · Pauta e embalagem')
    st.caption('Comece pela pergunta e pela promessa. Depois escolha uma embalagem que o roteiro realmente entrega.')
    profile_language = profile.get('language', 'pt-BR')
    if generated := st.session_state.pop('generated_studio_brief', None):
        st.session_state.studio_brief = generated
        st.session_state.brief_topic = generated['topic']
        st.session_state.brief_question = generated['central_question']
        st.session_state.brief_thesis = generated['thesis']
        st.session_state.brief_promise = generated['promise']
        st.session_state.brief_goal = generated['goal']
        st.session_state.brief_sources = generated['sources']
        st.session_state.brief_language = generated.get('language', profile_language)
    prior = st.session_state.get('studio_brief', {})
    with st.expander('Definir pauta', expanded=True):
        topic_column, provider_column, action_column = st.columns([3, 1.25, 1.45])
        with topic_column:
            topic = st.text_input('Tema do vídeo', value=prior.get('topic', ''), key='brief_topic')
        with provider_column:
            provider = st.selectbox('IA para pauta', ['openai', 'claude', 'gemini', 'deepseek', 'kimi', 'qwen'], key='brief_provider')
        with action_column:
            st.caption(' ')
            generate_brief = st.button('Gerar pauta com IA', key='generate_brief', type='secondary', use_container_width=True)
        language_options = list(VIDEO_LANGUAGE_LABELS)
        default_language = prior.get('language') or profile_language
        video_language = st.radio('Idioma do vídeo', language_options,
            index=language_options.index(default_language) if default_language in language_options else 0,
            format_func=VIDEO_LANGUAGE_LABELS.get, horizontal=True, key='brief_language')
        if st.session_state.get('packaging_language') != video_language:
            for key in list(st.session_state):
                if key.startswith('packaging_'):
                    st.session_state.pop(key, None)
            st.session_state.packaging_language = video_language
        if generate_brief:
            if not topic.strip():
                st.error('Informe o tema do vídeo antes de gerar a pauta.')
            else:
                with st.spinner('Estruturando a pauta…'):
                    try:
                        generated = editorial.generate_brief(topic, {**profile, 'language': video_language}, provider)
                        generated['language'] = video_language
                        st.session_state.generated_studio_brief = generated
                        st.rerun()
                    except Exception as exc:
                        st.error(redact(explain_generation_error(provider, exc)))
        question = st.text_input('Pergunta central', value=prior.get('central_question', ''), key='brief_question')
        thesis = st.text_area('Tese ou descoberta que o vídeo sustenta', value=prior.get('thesis', ''), key='brief_thesis')
        promise = st.text_area('Promessa específica deste vídeo', value=prior.get('promise', profile.get('promise', '')), key='brief_promise')
        goal = st.selectbox('Objetivo', ['Descoberta', 'Busca', 'Retorno ao canal'], key='brief_goal')
        sources = st.text_area('Fontes, links ou notas para checagem', value=prior.get('sources', ''), key='brief_sources', placeholder='Registre hipóteses e referências antes de tratá-las como fatos.')
        st.caption('A IA propõe uma pauta inicial com base no tema e na identidade editorial. Revise os fatos, fontes e a promessa antes de gerar o roteiro.')
        brief = {'topic': topic.strip(), 'central_question': question.strip(), 'thesis': thesis.strip(), 'promise': promise.strip(), 'goal': goal, 'sources': sources.strip(), 'language': video_language}
        st.session_state.studio_brief = brief

    if not brief['topic']:
        st.info('Defina o tema para criar títulos e thumbnail alinhados à pauta.')
        return brief, None

    options = editorial.packaging_options(brief, language=brief['language'])
    with st.expander('2 · Escolher embalagem', expanded=True):
        selected_index = st.radio('Ângulo de título e thumbnail', range(len(options)), format_func=lambda index: f"{options[index]['angle']} · {options[index]['title']}", horizontal=False, key='packaging_choice')
        selected = dict(options[selected_index])
        title = st.text_input('Título escolhido', value=selected['title'], key=f'packaging_title_{selected_index}')
        thumbnail_text = st.text_input('Texto da thumbnail', value=selected['thumbnail_text'], key=f'packaging_thumbnail_{selected_index}')
        visual_concept = st.text_area('Conceito visual da thumbnail', value=selected['visual_concept'], key=f'packaging_visual_{selected_index}')
        selected.update(title=title.strip(), thumbnail_text=thumbnail_text.strip(), visual_concept=visual_concept.strip())
        st.caption(f"Promessa a cumprir: {selected['promise']}")
    return brief, selected


def _settings(service):
    values = service.get_settings()
    with st.expander('Configurar serviços e chaves de API'):
        st.caption('As chaves ficam na configuração local. Campos vazios preservam as chaves já salvas.')
        configured = [name for name, item in values.get('llm', {}).items() if item.get('configured')]
        st.caption('Roteiros configurados: ' + (', '.join(configured) or 'nenhum'))
        images = values.get('image_generation', {})
        st.caption(f"Imagens: DALL-E {'configurado' if images.get('openai_configured') else 'pendente'} · Replicate {'configurado' if images.get('sd_configured') else 'pendente'}")
        provider = st.selectbox('Provedor de roteiro', ['openai', 'claude', 'gemini', 'deepseek', 'kimi', 'qwen'])
        current = values.get('llm', {}).get(provider, {})
        model_notice = model_status_message(provider, current.get('model', ''))
        if model_notice:
            st.warning(model_notice)
        with st.form('studio_settings'):
            st.caption('Selecione o provedor e informe os campos que deseja atualizar.')
            key = st.text_input('Chave do provedor de roteiro', type='password', key=f'api_{provider}')
            model = st.text_input('Modelo (opcional)', value=current.get('model') or '', key=f'model_{provider}')
            base_url = st.text_input('URL base (opcional)', value=current.get('base_url') or '', key=f'base_{provider}')
            enabled = st.checkbox('Habilitar provedor', value=current.get('enabled', True), key=f'enabled_{provider}')
            image_key = st.text_input('Chave OpenAI para imagens DALL-E', type='password')
            sd_key = st.text_input('Chave Replicate para Stable Diffusion', type='password')
            eleven_key = st.text_input('Chave ElevenLabs', type='password')
            woop_key = st.text_input('Chave WoopSocial para publicação', type='password')
            saved_voice = values.get('premium_tts', {}).get('elevenlabs_voice_id', '')
            preset_values = [voice for _, voice in PREMIUM_VOICE_OPTIONS]
            default_voice_index = preset_values.index('elevenlabs:' + saved_voice) if 'elevenlabs:' + saved_voice in preset_values else 0
            eleven_voice = st.selectbox(
                'Voz padrão ElevenLabs',
                PREMIUM_VOICE_OPTIONS,
                index=default_voice_index,
                format_func=lambda option: option[0],
            )[1].removeprefix('elevenlabs:')
            if st.form_submit_button('Salvar configurações'):
                config = {'api_key': key, 'enabled': enabled}
                if model.strip():
                    config['model'] = model.strip()
                if base_url.strip():
                    config['base_url'] = base_url.strip()
                service.save_settings({'llm': {provider: config}, 'image_generation': {'openai_api_key': image_key, 'sd_api_key': sd_key}, 'premium_tts': {'elevenlabs_api_key': eleven_key, 'elevenlabs_voice_id': eleven_voice}, 'woopsocial': {'woopsocial_api_key': woop_key}})
                st.success('Configurações salvas.')
    return service.get_settings()


def _script_sources(backend, settings, profile=None, brief=None, selected_package=None):
    st.subheader('3 · Prepare o roteiro')
    st.caption('Gere com IA, importe um JSON ou comece com um rascunho. Revise todas as cenas antes da produção.')
    with st.expander('Gerar roteiro com IA'):
        with st.form('generate_script'):
            topic = st.text_input('Tema do vídeo', value=(brief or {}).get('topic', ''))
            minutes = st.slider('Duração estimada (minutos)', 5, 30, 20)
            provider = st.selectbox('IA para o roteiro', ['openai', 'claude', 'gemini', 'deepseek', 'kimi', 'qwen'])
            model_notice = model_status_message(provider, settings.get('llm', {}).get(provider, {}).get('model', ''))
            if model_notice:
                st.warning(model_notice)
            language_options = list(VIDEO_LANGUAGE_LABELS)
            brief_language = (brief or {}).get('language')
            default_language = brief_language or (profile or {}).get('language', 'pt-BR')
            language = st.selectbox('Idioma da narração', language_options,
                index=language_options.index(default_language) if default_language in language_options else 0,
                format_func=VIDEO_LANGUAGE_LABELS.get, disabled=bool(brief_language),
                help='Definido na pauta para manter pauta, embalagem e roteiro no mesmo idioma.' if brief_language else None)
            style = st.selectbox('Estilo do roteiro', ['educational', 'documentary', 'entertaining'], format_func=lambda x: {'educational': 'Educacional', 'documentary': 'Documentário', 'entertaining': 'Entretenimento'}[x])
            audience = st.text_input('Público-alvo')
            instructions = st.text_area('Orientações adicionais')
            st.caption('A geração usa a API configurada e pode gerar custos.')
            if st.form_submit_button('Gerar roteiro'):
                if not topic.strip():
                    st.error('Informe um tema.')
                else:
                    from app.services.script_generator import ScriptGeneratorService
                    with st.spinner('Escrevendo roteiro…'):
                        try:
                            editorial_context = None
                            if brief and selected_package:
                                editorial_context = {'channel': {**(profile or {}), 'language': language}, 'brief': dict(brief, topic=topic.strip()), 'selected_package': selected_package}
                            result = ScriptGeneratorService().generate_script(ScriptGenerationRequest(topic=topic, duration_minutes=minutes, llm_provider=provider, custom_instructions=instructions, language=language, style=style, target_audience=audience, editorial_context=editorial_context))
                            script = result[0] if isinstance(result, tuple) else result
                            data = script.model_dump()
                            if selected_package:
                                data['title'] = selected_package['title'] or data['title']
                            estimated_seconds, target_seconds = _narration_duration_estimate(data)
                            _load(data)
                            if not _duration_is_on_target(estimated_seconds, target_seconds):
                                st.warning(
                                    f'A narração entregue pela IA estima {estimated_seconds / 60:.1f} minutos, '
                                    f'mas a meta é {target_seconds / 60:.0f} minutos. Revise ou gere novamente '
                                    'antes de iniciar a produção.'
                                )
                        except Exception as exc:
                            st.error(redact(explain_generation_error(provider, exc)))
    left, right = st.columns(2)
    with left:
        uploaded = st.file_uploader('Importar roteiro JSON', type=['json'])
        if st.button('Importar arquivo', disabled=uploaded is None):
            if uploaded.size > 2_000_000:
                st.error('O roteiro deve ter até 2 MB.')
            else:
                _load(ScriptParser().parse_json_script(uploaded.getvalue().decode('utf-8-sig')).model_dump())
        scene_count = st.number_input('Cenas do novo roteiro', 5, 100, 30)
        if st.button('Novo roteiro manual', key='new_script'):
            _load({'title': 'Novo documentário', 'description': '', 'total_duration_estimate': 300, 'scenes': [{'index': i, 'narration': 'Escreva a narração desta cena.', 'image_prompt': 'Descreva a imagem desta cena.', 'duration_seconds': None, 'transition': 'fade'} for i in range(scene_count)]})
    with right:
        drafts = backend.list_drafts()
        if drafts:
            selected = st.selectbox('Rascunhos salvos', range(len(drafts)), format_func=lambda i: drafts[i].get('script', {}).get('title', drafts[i]['id']))
            if st.button('Abrir rascunho'):
                draft = drafts[selected]
                _load(draft['script'], draft['id'])


def _editor(backend):
    script = st.session_state.get('studio_script')
    if not script:
        st.info('Seu roteiro aparecerá aqui para revisão.')
        return None
    revision = st.session_state.studio_revision
    st.subheader('4 · Revise as cenas')
    st.caption('Salve o roteiro para aplicar as alterações antes de exportar ou gerar o vídeo. A duração final depende da narração.')
    estimated_seconds, target_seconds = _narration_duration_estimate(script)
    duration_label = f'Narração estimada: {estimated_seconds / 60:.1f} minutos'
    if target_seconds:
        duration_label += f' · Meta da geração: {target_seconds / 60:.0f} minutos'
    if _duration_is_on_target(estimated_seconds, target_seconds):
        st.info(duration_label)
    else:
        st.warning(duration_label + '. Ajuste a narração antes de produzir o vídeo.')
        metadata = script.get('metadata') or {}
        attempts = int(metadata.get('duration_correction_attempts', 0))
        provider = metadata.get('script_llm_provider', 'openai')
        if attempts < 1:
            if st.button('Ajustar duração com IA', key=f'correct_duration_{revision}'):
                from app.services.script_generator import ScriptGeneratorService
                with st.spinner('Ajustando a narração para a duração escolhida…'):
                    try:
                        corrected = ScriptGeneratorService().correct_script_duration(
                            ScriptParser().parse_json_script(script), provider
                        )
                        _load(corrected.model_dump(), st.session_state.get('studio_draft_id'))
                        st.rerun()
                    except Exception as exc:
                        st.error(redact(explain_generation_error(provider, exc)))
        elif attempts >= 1:
            st.caption('A correção automática de duração já foi usada uma vez. Faça os ajustes restantes no roteiro para evitar tentativas em cadeia.')
    editorial_data = (script.get('metadata') or {}).get('editorial', {})
    if editorial_data:
        roles = [scene.get('narrative_role') for scene in script.get('scenes', []) if scene.get('narrative_role')]
        with st.expander('Checagem de retenção e promessa', expanded=True):
            if promise := editorial_data.get('promise') or editorial_data.get('brief', {}).get('promise'):
                st.write(f'**Promessa:** {promise}')
            if hook := editorial_data.get('hook'):
                st.write(f'**Gancho de abertura:** {hook}')
            if payoff := editorial_data.get('payoff'):
                st.write(f'**Entrega no final:** {payoff}')
            st.caption(f"Papéis narrativos identificados em {len(roles)} de {len(script['scenes'])} cenas. Revise as cenas sem papel ou sem uma função visual clara.")
    with st.form(f'editor_{revision}'):
        title = st.text_input('Título', value=script['title'], key=f'script_title_{revision}')
        description = st.text_area('Descrição', value=script.get('description', ''))
        duration = st.number_input('Estimativa total em segundos', 300, 1800, int(script['total_duration_estimate']))
        scenes = []
        for i, scene in enumerate(script['scenes']):
            with st.expander(f"Cena {i + 1} · {scene['narration'][:65]}", expanded=i == 0):
                narration = st.text_area('Narração', value=scene['narration'], key=f'narration_{revision}_{i}')
                prompt = st.text_area('Descrição da imagem', value=scene['image_prompt'], key=f'image_{revision}_{i}')
                st.caption('Imagem estática. A duração será medida a partir da narração gerada.')
                scenes.append(dict(scene, index=i, narration=narration, image_prompt=prompt))
        save = st.form_submit_button('Salvar roteiro')
        add = st.form_submit_button('Salvar e adicionar cena', disabled=len(scenes) >= 100)
        remove = st.form_submit_button('Salvar e remover última cena', disabled=len(scenes) <= 5)
        if save or add or remove:
            if add:
                scenes.append(dict(index=len(scenes), narration='Escreva a narração desta cena.', image_prompt='Descreva a imagem desta cena.', duration_seconds=None, transition='none'))
            if remove:
                scenes.pop()
            updated = dict(script, title=title, description=description, total_duration_estimate=duration, scenes=scenes)
            parsed = ScriptParser().parse_json_script(updated)
            saved = backend.save_draft(parsed.model_dump(), st.session_state.get('studio_draft_id'))
            st.session_state.studio_script = parsed.model_dump()
            st.session_state.studio_draft_id = saved['id']
            if add or remove:
                _load(parsed.model_dump(), saved['id'])
                st.rerun()
            st.success('Roteiro validado e salvo.')
    script = st.session_state.studio_script
    st.download_button('Exportar roteiro salvo', json.dumps(script, ensure_ascii=False, indent=2), file_name='roteiro.json', mime='application/json')
    return script


def _produce(backend, settings, script):
    st.subheader('5 · Produza o vídeo')
    image_provider = st.selectbox('Imagens', ['dalle', 'sd'], format_func=lambda p: {'dalle': 'DALL-E · OpenAI', 'sd': 'Stable Diffusion · Replicate'}[p])
    aspect_options = {'Retrato · 9:16': '9:16', 'Paisagem · 16:9': '16:9'}
    aspect_label = st.selectbox('Proporção do vídeo', list(aspect_options), key='output_aspect')
    aspect = aspect_options[aspect_label]
    image_quality = st.selectbox('Qualidade DALL-E', ['standard', 'hd'], key='output_quality', disabled=image_provider != 'dalle')
    image_size = st.selectbox('Tamanho DALL-E', ['1024x1024', '1792x1024', '1024x1792'], key='output_size', disabled=image_provider != 'dalle')
    st.session_state.setdefault('output_thumbnail_text', script['title'] if script else '')
    thumbnail_text = st.text_input('Texto da thumbnail', key='output_thumbnail_text')
    thumbnail_style = st.selectbox('Estilo da thumbnail', ['hybrid', 'ai-only', 'template'], key='output_thumbnail_style')
    voices = ['pt-BR-AntonioNeural', 'pt-BR-FranciscaNeural', 'en-US-GuyNeural', 'en-US-JennyNeural', 'de-DE-ConradNeural', 'de-DE-KatjaNeural', 'es-ES-AlvaroNeural', 'es-ES-ElviraNeural']
    premium = settings.get('premium_tts', {})
    premium_voices = [voice for _, voice in PREMIUM_VOICE_OPTIONS]
    if not (importlib.util.find_spec('elevenlabs') and premium.get('elevenlabs_configured')):
        premium_voices = []
    voice_labels = {voice: label + ' · ElevenLabs' for label, voice in PREMIUM_VOICE_OPTIONS}
    voice = st.selectbox('Voz da narração', voices + premium_voices, format_func=lambda option: voice_labels.get(option, option))
    fonts = sorted(p.name for p in (ROOT / 'resource' / 'fonts').glob('*') if p.suffix.lower() in ('.ttf', '.otf', '.ttc'))
    with st.expander('Configurações das legendas', expanded=True):
        subtitles = st.checkbox('Incluir legendas', value=True, key='output_subtitles')
        font = st.selectbox('Fonte', fonts, key='subtitle_font') if fonts else ''
        subtitle_positions = {'Topo': 'top', 'Centro': 'center', 'Base': 'bottom'}
        subtitle_position = subtitle_positions[st.selectbox('Posição', list(subtitle_positions), index=2, key='subtitle_position')]
        color_column, size_column = st.columns(2)
        with color_column:
            text_fore_color = st.color_picker('Cor do texto', '#FFFFFF', key='subtitle_foreground')
        with size_column:
            font_size = st.slider('Tamanho da fonte', 30, 100, 60, key='subtitle_font_size')
        outline_column, outline_width_column = st.columns(2)
        with outline_column:
            stroke_color = st.color_picker('Cor do contorno', '#000000', key='subtitle_stroke_color')
        with outline_width_column:
            stroke_width = st.slider('Espessura do contorno', 0.0, 10.0, 1.5, step=0.5, key='subtitle_stroke_width')
        background_column, background_color_column = st.columns(2)
        with background_column:
            subtitle_background = st.checkbox('Fundo da legenda', value=True, key='subtitle_background')
        with background_color_column:
            text_background_color = st.color_picker('Cor do fundo', '#000000', key='subtitle_background_color', disabled=not subtitle_background) if subtitle_background else False
    st.caption('A produção inclui narração, imagens, legendas, vídeo e thumbnail. Imagens e vozes premium podem gerar custos nas APIs.')
    if st.button('Gerar vídeo completo', key='produce', type='primary', disabled=script is None):
        parsed = ScriptParser().parse_json_script(script)
        estimated_seconds, target_seconds = _narration_duration_estimate(script)
        if not _duration_is_on_target(estimated_seconds, target_seconds):
            st.error(
                f'A narração atual estima {estimated_seconds / 60:.1f} minutos, fora da meta de '
                f'{target_seconds / 60:.0f} minutos. A produção não foi iniciada para evitar custos com um vídeo na duração errada.'
            )
            return
        params = LongFormVideoParams(video_subject=parsed.title, structured_script=parsed, use_structured_script=True, video_aspect=aspect, image_provider=image_provider, image_quality=image_quality, image_size=image_size, voice_name=voice, premium_tts_provider='elevenlabs' if voice.startswith('elevenlabs:') else None, font_name=font, font_size=font_size, subtitle_position=subtitle_position, text_fore_color=text_fore_color, stroke_color=stroke_color, stroke_width=stroke_width, text_background_color=text_background_color, bgm_type='', subtitle_enabled=subtitles, thumbnail_text=thumbnail_text, thumbnail_style=thumbnail_style)
        errors = backend.validate_settings(params)
        if errors:
            for error in errors:
                st.error(redact(error))
        else:
            st.session_state.studio_active = backend.submit(params)
            st.success('Produção iniciada. Acompanhe abaixo; você pode continuar trabalhando.')


@st.fragment(run_every='2s')
def _active_production_monitor(task_id):
    backend = importlib.import_module('app.services.studio')
    try:
        record = backend.get_production(task_id)
    except (FileNotFoundError, ValueError):
        st.warning('Não foi possível encontrar a produção iniciada. Consulte o histórico.')
        return
    progress = float(record.get('progress') or 0)
    phase = PHASES.get(record.get('phase'), record.get('phase') or 'Processando')
    st.subheader('Acompanhamento da produção')
    st.progress(max(0.0, min(1.0, progress / 100)), text=f'{phase} · {progress:.0f}%')
    if record.get('status') == 'complete':
        st.success('Vídeo concluído. Abra Produções para assistir ou baixar os arquivos.')
    elif record.get('status') in ('failed', 'interrupted'):
        st.error(redact(record.get('error') or 'A produção foi interrompida.'))


@st.fragment(run_every='2s')
def _monitor():
    backend = importlib.import_module('app.services.studio')
    active = [r for r in backend.list_productions() if r['status'] in ('queued', 'running')]
    for record in active:
        progress = float(record.get('progress') or 0)
        st.progress(max(0.0, min(1.0, progress / 100)), text=f"{record.get('title', record['id'])} · {record.get('phase') or 'aguardando'}")
    if not active:
        st.caption('Nenhuma produção em andamento. Atualize o histórico para ver os arquivos concluídos.')


def _history():
    backend = importlib.import_module('app.services.studio')
    st.subheader('4 · Produções e histórico')
    _monitor()
    st.button('Atualizar histórico', key='refresh_history')
    records = backend.list_productions()
    if not records:
        st.caption('Nenhuma produção ainda.')
    for record in records:
        task_id = record['id']
        with st.expander(f"{record.get('title', task_id)} · {STATUS.get(record['status'], record['status'])}", expanded=task_id == st.session_state.get('studio_active')):
            st.caption(f"{task_id} · {record.get('created_at', '')}")
            progress = float(record.get('progress') or 0)
            st.progress(max(0.0, min(1.0, progress / 100)), text=f"Etapa: {record.get('phase') or 'aguardando'}")
            if record.get('error'):
                st.error(redact(record['error']))
            if st.button('Abrir projeto', key=f'open_project_{task_id}'):
                project = backend.get_project(task_id)
                st.session_state.studio_brief = project['brief']
                _load(project['script'])
                st.success('Projeto restaurado em Criar vídeo.')
            if record['status'] not in ('queued', 'running') and st.button('Excluir projeto', key=f'delete_project_{task_id}'):
                try:
                    backend.delete_production(task_id)
                    st.success('Projeto excluído, incluindo todos os arquivos gerados.')
                    st.rerun()
                except Exception as exc:
                    st.error(redact(exc))
            if record['status'] in ('failed', 'interrupted') and st.button('Retomar produção', key=f'resume_{task_id}'):
                try:
                    backend.resume(task_id)
                    st.success('Retomada solicitada.')
                except Exception as exc:
                    st.error(redact(exc))
            artifacts = record.get('artifacts') or {}
            if artifacts.get('duration_seconds'):
                st.caption(f"Duração real: {float(artifacts['duration_seconds']) / 60:.1f} minutos")
                if artifacts.get('video') and not 300 <= float(artifacts['duration_seconds']) <= 1800:
                    st.warning('O áudio gerado ficou fora de 5–30 minutos. Ajuste o roteiro e crie uma nova produção se precisar dessa duração.')
            if artifacts.get('video'):
                video = Path(artifacts['video'])
                if video.is_file():
                    if st.button('Abrir player', key=f'play_{task_id}'):
                        st.video(str(video))
                    st.caption('Preparar o download carrega o arquivo na memória do servidor local.')
                    if st.button('Preparar download do vídeo', key=f'prepare_{task_id}'):
                        st.download_button('Baixar vídeo', video.read_bytes(), file_name=video.name, mime='video/mp4', key=f'download_{task_id}', on_click='ignore')
            for name, label in [('thumbnail', 'Thumbnail'), ('script', 'Roteiro'), ('subtitles', 'Legendas')]:
                path = Path(artifacts[name]) if artifacts.get(name) else None
                if path and path.is_file():
                    if name == 'thumbnail':
                        st.image(str(path), width=240)
                    st.download_button(f'Baixar {label.lower()}', path.read_bytes(), file_name=path.name, key=f'{name}_{task_id}')


def _publication_title(record):
    """Prefer the editorial YouTube title over the short thumbnail overlay."""
    params = record.get('params') or {}
    script = params.get('structured_script') or {}
    editorial = (script.get('metadata') or {}).get('editorial') or {}
    package = editorial.get('selected_package') or {}
    return package.get('title') or script.get('title') or record.get('title', '')


def _youtube_title(value):
    """Keep the auto-filled YouTube title within its 100-character limit."""
    title = ' '.join(str(value or '').split())
    if len(title) <= 100:
        return title
    shortened = title[:101].rsplit(' ', 1)[0].rstrip(' ,:;-')
    return shortened or title[:100]


def _publication_payload(raw):
    """Parse the JSON-mode LLM response used by publication generation."""
    if isinstance(raw, dict):
        return raw
    content = str(raw or '').strip()
    if content.startswith('```'):
        content = content.split('\n', 1)[-1].rsplit('```', 1)[0].strip()
    try:
        return json.loads(content)
    except ValueError:
        return content


def _publication_description(raw):
    """Extract displayable description text from a JSON-mode LLM response."""
    payload = _publication_payload(raw)
    if isinstance(payload, str):
        return payload
    if not isinstance(payload, dict):
        raise ValueError('A IA não retornou uma descrição válida. Tente gerar novamente.')
    description = payload.get('description') or payload.get('content')
    if isinstance(description, list):
        description = '\n'.join(str(item) for item in description)
    if not isinstance(description, str) or not description.strip():
        raise ValueError('A IA não retornou o campo de descrição. Tente gerar novamente.')
    return description.strip()


def _publication_content(raw):
    """Render a stable description and return its separate YouTube search tags."""
    payload = _publication_payload(raw)
    if not isinstance(payload, dict) or 'summary' not in payload:
        return _publication_description(payload), []

    def strings(value):
        return [str(item).strip() for item in (value or []) if str(item).strip()]

    summary = str(payload.get('summary') or '').strip()
    if not summary:
        raise ValueError('A IA não retornou o resumo da descrição. Tente gerar novamente.')
    chapters = []
    for item in payload.get('chapters') or []:
        if isinstance(item, dict) and item.get('time') and item.get('title'):
            chapters.append(f"{str(item['time']).strip()} — {str(item['title']).strip()}")
    takeaways = strings(payload.get('takeaways'))
    sources = strings(payload.get('sources'))
    cta = str(payload.get('cta') or '').strip()
    hashtags = [tag if tag.startswith('#') else f'#{tag.replace(" ", "")}' for tag in strings(payload.get('hashtags'))]
    tags = strings(payload.get('tags'))[:15]
    sections = [
        f"━━ VIDEO SUMMARY ━━\n{summary}",
        "━━ CHAPTERS ━━\n" + ('\n'.join(chapters) if chapters else 'Chapters are not available for this video.'),
        "━━ KEY TAKEAWAYS ━━\n" + ('\n'.join(f'• {item}' for item in takeaways) if takeaways else 'Key ideas are covered throughout the video.'),
        "━━ SOURCES & NOTES ━━\n" + ('\n'.join(f'• {item}' for item in sources) if sources else 'No external sources were supplied with this production.'),
    ]
    if cta:
        sections.append(cta)
    if hashtags:
        sections.append(' '.join(hashtags))
    return '\n\n'.join(sections), tags


def _publication_language(script):
    metadata = script.get('metadata') or {}
    editorial = metadata.get('editorial') or {}
    channel = editorial.get('channel') or {}
    return metadata.get('script_language') or channel.get('language') or 'pt-BR'


def _publication_duration_error(record):
    """Reject a completed artifact whose measured duration misses its video brief."""
    duration = (record.get('artifacts') or {}).get('duration_seconds')
    try:
        duration = float(duration)
    except (TypeError, ValueError):
        return 'Não foi possível confirmar a duração real deste vídeo. Abra Produções e gere-o novamente antes de publicar.'
    script = (record.get('params') or {}).get('structured_script') or {}
    target = (script.get('metadata') or {}).get('target_duration_seconds')
    try:
        target = float(target) if target else None
    except (TypeError, ValueError):
        target = None
    if target and not _duration_is_on_target(duration, target):
        return (f'Este arquivo tem {duration / 60:.1f} minutos, mas a meta desta produção é '
                f'{target / 60:.0f} minutos. Corrija o roteiro e gere uma nova produção antes de publicar.')
    if not 300 <= duration <= 1800:
        return (f'Este arquivo tem {duration / 60:.1f} minutos. O Estúdio publica vídeos entre 5 e 30 minutos; '
                'gere uma nova produção antes de publicar.')
    return None


def _publication_label(record):
    artifacts = record.get('artifacts') or {}
    parts = [record['title']]
    try:
        parts.append(f"{float(artifacts.get('duration_seconds')) / 60:.1f} min")
    except (TypeError, ValueError):
        pass
    video = Path(artifacts.get('video') or '')
    if video.is_file():
        size_mb = video.stat().st_size / (1024 * 1024)
        parts.append(f'{size_mb:.1f} MB')
    try:
        parts.append(datetime.fromtimestamp(float(record['created_at'])).strftime('%d/%m/%Y %H:%M'))
    except (KeyError, TypeError, ValueError, OSError):
        pass
    return ' · '.join(parts)


def _publication(settings):
    st.subheader('Publicação no YouTube')
    backend = importlib.import_module('app.services.studio')
    records = [item for item in backend.list_productions() if item.get('status') == 'complete' and (item.get('artifacts') or {}).get('video')]
    if not records:
        st.info('Conclua uma produção para publicá-la.')
        return
    selected = st.selectbox('Vídeo concluído', records, format_func=_publication_label, key='publication_video')
    duration_error = _publication_duration_error(selected)
    if duration_error:
        st.error(duration_error)
        return
    title = st.text_input('Título de publicação', value=_youtube_title(_publication_title(selected)), max_chars=100, key=f'publication_title_{selected["id"]}')
    st.caption(f'{len(title)}/100 caracteres')
    if st.button('Gerar descrição com IA', key=f'publication_ai_{selected["id"]}'):
        try:
            from app.services.script_generator import ScriptGeneratorService
            project = backend.get_project(selected['id'])
            language = _publication_language(project['script'])
            language_name = {'en-US': 'English', 'pt-BR': 'Brazilian Portuguese', 'de-DE': 'German', 'es-ES': 'Spanish'}.get(language, language)
            prompt = f"""Generate YouTube publication metadata exclusively in {language_name}. Return exactly one JSON object with these fields and no others:
{{
  \"summary\": \"two concise paragraphs explaining the video promise and value\",
  \"chapters\": [{{\"time\": \"00:00\", \"title\": \"chapter title\"}}],
  \"takeaways\": [\"3 to 5 specific viewer takeaways\"],
  \"sources\": [\"only sources or research notes present in the script; never invent URLs or citations\"],
  \"cta\": \"one natural channel-appropriate call to action\",
  \"hashtags\": [\"3 relevant hashtags\"],
  \"tags\": [\"8 to 15 YouTube search tags without #\"]
}}
Do not place headings inside any field. Use the supplied scene timing for chapters. Title: {title}. Script: {json.dumps(project['script'], ensure_ascii=False)}"""
            generated = ScriptGeneratorService().generate_editorial_json('openai', prompt)
            description_value, generated_tags = _publication_content(generated)
            st.session_state[f'publication_description_{selected["id"]}'] = description_value
            st.session_state[f'publication_tags_{selected["id"]}'] = ', '.join(generated_tags)
        except Exception as exc:
            st.error(redact(exc))
    description = st.text_area('Descrição', value=st.session_state.get(f'publication_description_{selected["id"]}', ''), key=f'publication_description_{selected["id"]}', height=220)
    tags_value = st.text_input('Tags do YouTube', value=st.session_state.get(f'publication_tags_{selected["id"]}', ''), key=f'publication_tags_{selected["id"]}', help='Separadas por vírgula; enviadas ao campo de tags do YouTube.')
    tags = [tag.strip() for tag in tags_value.split(',') if tag.strip()][:15]
    privacy = st.selectbox('Visibilidade', ['private', 'unlisted', 'public', 'scheduled'], format_func=lambda x: {'private': 'Privado', 'unlisted': 'Não listado', 'public': 'Público', 'scheduled': 'Agendado'}[x])
    scheduled_at = None
    if privacy == 'scheduled':
        day = st.date_input('Data de lançamento')
        hour = st.time_input('Hora de lançamento')
        scheduled_at = datetime.combine(day, hour).astimezone().isoformat()
    if not settings.get('woopsocial', {}).get('configured'):
        st.warning('Configure a chave WoopSocial em Configurações para carregar canais e publicar.')
        return
    try:
        from app.services import woopsocial
        available_projects = woopsocial.projects()
        accounts = woopsocial.youtube_accounts()
    except Exception as exc:
        st.error(redact(exc)); return
    if not available_projects:
        st.error('Nenhum projeto WoopSocial disponível para a chave configurada.')
        return
    project = st.selectbox('Projeto WoopSocial', available_projects, format_func=lambda item: item.get('name') or item['id'])
    account = st.selectbox('Canal do YouTube', accounts, format_func=woopsocial.account_label)
    if st.button('Publicar no YouTube', type='primary', key=f'publish_{selected["id"]}'):
        try:
            upload_progress = st.progress(0, text='Preparando publicação…')

            def report_upload(sent, total, phase):
                fraction = sent / total if total else 0
                upload_progress.progress(max(0.0, min(1.0, fraction)),
                    text=f'{phase} · {sent / (1024 * 1024):.1f} MB de {total / (1024 * 1024):.1f} MB')

            woopsocial.publish(selected['artifacts']['video'], project['id'], account['id'], title, description,
                               privacy, scheduled_at, tags=tags, progress=report_upload)
            upload_progress.progress(1.0, text='Publicação enviada à WoopSocial.')
            st.success('Publicação enviada à WoopSocial.')
        except Exception as exc:
            st.error(redact(exc))


def render():
    st.markdown(STUDIO_STYLE, unsafe_allow_html=True)
    st.markdown('''
    <section class="studio-hero">
      <h1>Estúdio de vídeos</h1>
      <p>Crie vídeos de 5–30 minutos, do roteiro ao arquivo final.</p>
      <div class="studio-flow" aria-label="Etapas da produção">
        <span>1 · Pauta</span><span>2 · Embalagem</span><span>3 · Roteiro</span><span>4 · Revisão</span><span>5 · Produção</span>
      </div>
    </section>
    ''', unsafe_allow_html=True)
    backend = importlib.import_module('app.services.studio')
    settings_service = importlib.import_module('app.services.studio_settings')
    status = settings_service.get_settings()
    status_columns = st.columns(4)
    status_items = [
        ('Roteiro IA', any(item.get('configured') for item in status.get('llm', {}).values())),
        ('Imagens', status.get('image_generation', {}).get('openai_configured') or status.get('image_generation', {}).get('sd_configured')),
        ('ElevenLabs', status.get('premium_tts', {}).get('elevenlabs_configured')),
        ('WoopSocial', status.get('woopsocial', {}).get('configured')),
    ]
    for column, (label, configured) in zip(status_columns, status_items):
        column.metric(label, 'Configurada' if configured else 'Pendente', '●' if configured else '○')
    create_tab, productions_tab, publication_tab, settings_tab = st.tabs(['Criar vídeo', 'Produções', 'Publicação', 'Configurações'])
    try:
        with settings_tab:
            settings = _settings(settings_service)
            profile = _channel_profile_editor()
        with create_tab:
            brief, selected_package = _brief_and_packaging(profile)
            _script_sources(backend, settings, profile, brief, selected_package)
            script = _editor(backend)
            if script:
                _produce(backend, settings, script)
                if active_id := st.session_state.get('studio_active'):
                    _active_production_monitor(active_id)
            else:
                st.info('Salve um roteiro para liberar as configurações de produção e a geração do vídeo.')
    except Exception as exc:
        st.error(f'Não foi possível concluir esta ação: {redact(exc)}')
    try:
        with productions_tab:
            _history()
        with publication_tab:
            _publication(settings)
    except Exception as exc:
        st.error(f'Não foi possível carregar o histórico: {redact(exc)}')
