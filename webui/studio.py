"""Local long-form studio. Workers and persistence belong to app.services.studio."""
import importlib
import importlib.util
import json
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


def _channel_profile_editor():
    profile = editorial.get_channel_profile()
    with st.expander('1 · Identidade editorial do canal', expanded=True):
        st.caption('Defina a linha editorial uma vez. Ela orienta pauta, embalagem e roteiro, sem substituir sua revisão final.')
        with st.form('channel_profile'):
            name = st.text_input('Nome do canal', value=profile['name'])
            niche, subniche = st.columns(2)
            with niche:
                channel_niche = st.text_input('Nicho', value=profile['niche'], placeholder='Ex.: História e tecnologia')
            with subniche:
                channel_subniche = st.text_input('Recorte', value=profile['subniche'], placeholder='Ex.: decisões que moldaram a internet')
            audience = st.text_input('Público principal', value=profile['audience'])
            promise = st.text_area('Promessa do canal', value=profile['promise'], placeholder='O que a pessoa aprende ou sente ao assistir?')
            tone = st.selectbox('Tom', ['documentary', 'educational', 'entertaining'], index=['documentary', 'educational', 'entertaining'].index(profile['tone'] if profile['tone'] in ('documentary', 'educational', 'entertaining') else 'documentary'), format_func=lambda value: {'documentary': 'Documentário', 'educational': 'Educacional', 'entertaining': 'Entretenimento'}[value])
            pillars = st.text_area('Pilares e séries', value=profile['pillars'], placeholder='Ex.: guerras da tecnologia; infraestruturas invisíveis')
            visual_style = st.text_input('Direção visual', value=profile['visual_style'], placeholder='Ex.: documental cinematográfica, arquivos e infográficos')
            source_policy = st.text_area('Política de fontes', value=profile['source_policy'], placeholder='Ex.: priorizar fontes primárias e indicar incertezas')
            restricted = st.text_input('Assuntos ou abordagens a evitar', value=profile['restricted_topics'])
            if st.form_submit_button('Salvar identidade editorial'):
                editorial.save_channel_profile({'name': name, 'niche': channel_niche, 'subniche': channel_subniche, 'audience': audience, 'promise': promise, 'tone': tone, 'pillars': pillars, 'visual_style': visual_style, 'source_policy': source_policy, 'restricted_topics': restricted})
                st.success('Identidade editorial salva.')
                profile = editorial.get_channel_profile()
    return profile


def _brief_and_packaging(profile):
    st.subheader('1 · Pauta e embalagem')
    st.caption('Comece pela pergunta e pela promessa. Depois escolha uma embalagem que o roteiro realmente entrega.')
    prior = st.session_state.get('studio_brief', {})
    with st.expander('Definir pauta', expanded=True):
        topic = st.text_input('Tema do vídeo', value=prior.get('topic', ''), key='brief_topic')
        question = st.text_input('Pergunta central', value=prior.get('central_question', ''), key='brief_question')
        thesis = st.text_area('Tese ou descoberta que o vídeo sustenta', value=prior.get('thesis', ''), key='brief_thesis')
        promise = st.text_area('Promessa específica deste vídeo', value=prior.get('promise', profile.get('promise', '')), key='brief_promise')
        goal = st.selectbox('Objetivo', ['Descoberta', 'Busca', 'Retorno ao canal'], key='brief_goal')
        sources = st.text_area('Fontes, links ou notas para checagem', value=prior.get('sources', ''), key='brief_sources', placeholder='Registre hipóteses e referências antes de tratá-las como fatos.')
        brief = {'topic': topic.strip(), 'central_question': question.strip(), 'thesis': thesis.strip(), 'promise': promise.strip(), 'goal': goal, 'sources': sources.strip()}
        st.session_state.studio_brief = brief

    if not brief['topic']:
        st.info('Defina o tema para criar títulos e thumbnail alinhados à pauta.')
        return brief, None

    options = editorial.packaging_options(brief)
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
                service.save_settings({'llm': {provider: config}, 'image_generation': {'openai_api_key': image_key, 'sd_api_key': sd_key}, 'premium_tts': {'elevenlabs_api_key': eleven_key, 'elevenlabs_voice_id': eleven_voice}})
                st.success('Configurações salvas.')
    return service.get_settings()


def _script_sources(backend, settings, profile=None, brief=None, selected_package=None):
    st.subheader('3 · Prepare o roteiro')
    st.caption('Gere com IA, importe um JSON ou comece com um rascunho. Revise todas as cenas antes da produção.')
    with st.expander('Gerar roteiro com IA'):
        with st.form('generate_script'):
            topic = st.text_input('Tema do vídeo', value=(brief or {}).get('topic', ''))
            minutes = st.slider('Duração estimada (minutos)', 15, 30, 20)
            provider = st.selectbox('IA para o roteiro', ['openai', 'claude', 'gemini', 'deepseek', 'kimi', 'qwen'])
            model_notice = model_status_message(provider, settings.get('llm', {}).get(provider, {}).get('model', ''))
            if model_notice:
                st.warning(model_notice)
            language = st.selectbox('Idioma da narração', ['pt-BR', 'en-US', 'es-ES'])
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
                                editorial_context = {'channel': profile or {}, 'brief': dict(brief, topic=topic.strip()), 'selected_package': selected_package}
                            result = ScriptGeneratorService().generate_script(ScriptGenerationRequest(topic=topic, duration_minutes=minutes, llm_provider=provider, custom_instructions=instructions, language=language, style=style, target_audience=audience, editorial_context=editorial_context))
                            script = result[0] if isinstance(result, tuple) else result
                            data = script.model_dump()
                            if selected_package:
                                data['title'] = selected_package['title'] or data['title']
                            _load(data)
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
            _load({'title': 'Novo documentário', 'description': '', 'total_duration_estimate': 900, 'scenes': [{'index': i, 'narration': 'Escreva a narração desta cena.', 'image_prompt': 'Descreva a imagem desta cena.', 'duration_seconds': None, 'transition': 'fade'} for i in range(scene_count)]})
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
        duration = st.number_input('Estimativa total em segundos', 900, 1800, int(script['total_duration_estimate']))
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
    voices = ['pt-BR-AntonioNeural', 'pt-BR-FranciscaNeural', 'en-US-GuyNeural', 'en-US-JennyNeural', 'es-ES-AlvaroNeural', 'es-ES-ElviraNeural']
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
            if record['status'] in ('failed', 'interrupted') and st.button('Retomar produção', key=f'resume_{task_id}'):
                try:
                    backend.resume(task_id)
                    st.success('Retomada solicitada.')
                except Exception as exc:
                    st.error(redact(exc))
            artifacts = record.get('artifacts') or {}
            if artifacts.get('duration_seconds'):
                st.caption(f"Duração real: {float(artifacts['duration_seconds']) / 60:.1f} minutos")
                if artifacts.get('video') and not 900 <= float(artifacts['duration_seconds']) <= 1800:
                    st.warning('O áudio gerado ficou fora de 15–30 minutos. Ajuste o roteiro e crie uma nova produção se precisar dessa duração.')
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


def render():
    st.markdown(STUDIO_STYLE, unsafe_allow_html=True)
    st.markdown('''
    <section class="studio-hero">
      <h1>Estúdio de vídeos</h1>
      <p>Crie vídeos de 15–30 minutos, do roteiro ao arquivo final.</p>
      <div class="studio-flow" aria-label="Etapas da produção">
        <span>1 · Pauta</span><span>2 · Embalagem</span><span>3 · Roteiro</span><span>4 · Revisão</span><span>5 · Produção</span>
      </div>
    </section>
    ''', unsafe_allow_html=True)
    backend = importlib.import_module('app.services.studio')
    settings_service = importlib.import_module('app.services.studio_settings')
    create_tab, productions_tab, settings_tab = st.tabs(['Criar vídeo', 'Produções', 'Configurações'])
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
    except Exception as exc:
        st.error(f'Não foi possível carregar o histórico: {redact(exc)}')
