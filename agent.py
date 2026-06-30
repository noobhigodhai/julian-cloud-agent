# import logging
# import os
# import json
# import httpx
# import asyncio
# from datetime import datetime, timezone

# def _now() -> datetime:
#     return datetime.now(timezone.utc)

# from livekit.agents import Agent, AgentServer, AgentSession, JobContext, JobProcess, cli
# from livekit.plugins import silero
# from livekit.plugins import openai, deepgram, azure

# logging.basicConfig(
#     level=logging.INFO,
#     format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
#     datefmt="%H:%M:%S",
# )
# logger = logging.getLogger("julian-cloud-agent")
# BACKEND_URL = os.environ.get("BACKEND_URL", "https://specker.ai")

# LANGUAGE_NAMES = {
#     "hi": "Hindi", "ta": "Tamil", "te": "Telugu", "mr": "Marathi",
#     "kn": "Kannada", "tl": "Filipino/Tagalog", "bn": "Bengali",
#     "es": "Spanish", "fr": "French", "de": "German", "pt": "Portuguese",
#     "ja": "Japanese", "ko": "Korean", "ar": "Arabic",
#     "id": "Indonesian/Bahasa", "ms": "Malay", "vi": "Vietnamese",
#     "zh": "Mandarin Chinese", "tr": "Turkish", "ru": "Russian",
#     "it": "Italian", "nl": "Dutch", "en": "English",
# }

# DEEPGRAM_LANG_MAP = {
#     "hi": "hi", "ta": "ta", "te": "te", "mr": "mr", "kn": "kn",
#     "tl": "tl", "bn": "bn", "es": "es", "fr": "fr", "de": "de",
#     "pt": "pt", "ja": "ja", "ko": "ko", "ar": "ar", "id": "id",
#     "ms": "ms", "vi": "vi", "zh": "zh", "tr": "tr", "ru": "ru",
#     "it": "it", "nl": "nl", "en": "en",
# }

# GOOGLE_VOICE_MAP = {
#     "hi": ("hi-IN-Chirp3-HD-Aoede", "hi-IN"),
#     "ta": ("ta-IN-Chirp3-HD-Aoede", "ta-IN"),
#     "te": ("te-IN-Chirp3-HD-Aoede", "te-IN"),
#     "mr": ("mr-IN-Chirp3-HD-Aoede", "mr-IN"),
#     "kn": ("kn-IN-Chirp3-HD-Aoede", "kn-IN"),
#     "tl": ("fil-PH-Chirp3-HD-Aoede", "fil-PH"),
#     "bn": ("bn-IN-Chirp3-HD-Aoede", "bn-IN"),
#     "es": ("es-ES-Chirp3-HD-Aoede", "es-ES"),
#     "fr": ("fr-FR-Chirp3-HD-Aoede", "fr-FR"),
#     "de": ("de-DE-Chirp3-HD-Aoede", "de-DE"),
#     "pt": ("pt-BR-Chirp3-HD-Aoede", "pt-BR"),
#     "ja": ("ja-JP-Chirp3-HD-Aoede", "ja-JP"),
#     "ko": ("ko-KR-Chirp3-HD-Aoede", "ko-KR"),
#     "ar": ("ar-XA-Chirp3-HD-Aoede", "ar-XA"),
#     "id": ("id-ID-Chirp3-HD-Aoede", "id-ID"),
#     "ms": ("ms-MY-Chirp3-HD-Aoede", "ms-MY"),
#     "vi": ("vi-VN-Chirp3-HD-Aoede", "vi-VN"),
#     "zh": ("cmn-CN-Chirp3-HD-Aoede", "cmn-CN"),
#     "tr": ("tr-TR-Chirp3-HD-Aoede", "tr-TR"),
#     "ru": ("ru-RU-Chirp3-HD-Aoede", "ru-RU"),
#     "it": ("it-IT-Chirp3-HD-Aoede", "it-IT"),
#     "nl": ("nl-NL-Chirp3-HD-Aoede", "nl-NL"),
#     "en": ("en-US-Chirp3-HD-Aoede", "en-US"),
# }


# def get_deepgram_stt(native_lang: str | None):
#     lang_code = DEEPGRAM_LANG_MAP.get(native_lang or "", "en")
#     logger.info(f"🎤 STT: Deepgram Nova-3 | language={lang_code}")
#     return deepgram.STT(model="nova-3", language=lang_code)


# def get_google_tts(native_lang: str | None):
#     creds_json = os.environ.get("GOOGLE_CREDENTIALS_JSON", "")
#     creds = json.loads(creds_json) if creds_json else None
#     voice_name, language = GOOGLE_VOICE_MAP.get(
#         native_lang or "", ("en-US-Chirp3-HD-Aoede", "en-US")
#     )
#     logger.info(f"🎙️ TTS: Google Chirp3-HD | voice={voice_name} | lang={language}")
#     try:
#         return google.TTS(voice_name=voice_name, language=language, gender="female", credentials_info=creds)
#     except Exception as e:
#         logger.warning(f"Google TTS failed ({e}) — fallback to en-US")
#         return google.TTS(voice_name="en-US-Chirp3-HD-Aoede", language="en-US", gender="female", credentials_info=creds)


# def build_instructions(topic, native_lang_code):
#     lang_name = LANGUAGE_NAMES.get(native_lang_code or "", None)

#     topic_line = (
#         f"Today's conversation topic is: {topic}. Keep the conversation around this topic."
#         if topic else
#         "You can talk about anything — ask what's on the user's mind."
#     )

#     if lang_name and lang_name != "English":
#         lang_line = f"""
# You are an English coach. The user speaks {lang_name} and is learning English.

# YOUR SPEAKING STYLE:
# - Speak in a natural mix of {lang_name} and English — this is called code-switching.
# - Use {lang_name} for greetings, encouragement, filler words, and emotional warmth.
# - Use English for explanations, corrections, and the main conversation.
# - Example (Hindi): "Namaste! So aaj hum travel ke baare mein baat karenge. How are you doing today?"
# - Example (Hindi): "Arre yaar, that was really good! Aur bolo, what do you love about travelling?"
# - Example (Filipino): "Kamusta ka! So today we will practice English together. Okay lang ba?"
# - Example (Tamil): "Vanakkam! Today we practice English. Neenga eppadi irukkeenga?"
# - Keep it warm, fun and natural — like a bilingual friend.
# - NEVER speak 100% in {lang_name} — always keep English as the main language.
# - ONLY speak the actual words. No stage directions, no labels, no brackets.

# WHEN USER SPEAKS IN {lang_name}:
# - Understand what they said and respond naturally in the mixed style.
# - Gently teach them the English version: "Oh nice! In English you can say: I am doing well."
# - Ask them to try saying it in English.
# - When they do, praise them and continue the conversation.

# WHEN USER SPEAKS IN ENGLISH:
# - Respond in mixed style naturally.
# - Gently correct any grammar mistakes by using the correct form in your reply.
# - Ask a follow-up question to keep them talking.
# """
#         logger.info(f"Language mode: MIXED ({lang_name} + English)")
#     else:
#         lang_line = """
# Speak naturally in English only.
# Gently correct any mistakes by naturally using the correct version in your reply.
# Keep responses short — 1 to 2 sentences. Always ask a follow-up question.
# """
#         logger.info("Language mode: English only")

#     return f"""You are Julian, a warm, fun, encouraging AI English coach on a phone call.
# Keep responses SHORT — 1 to 2 sentences max. Be friendly and natural.
# Always ask a follow-up question to keep the conversation going.

# {topic_line}

# {lang_line}

# LISTENING RULES:
# - Always wait for the user to fully finish speaking before responding.
# - Never interrupt. After you finish speaking, go straight into listening mode."""


# class JulianAgent(Agent):
#     def __init__(self, topic=None, native_lang=None):
#         self._topic = topic
#         self._native_lang = native_lang
#         super().__init__(instructions=build_instructions(topic, native_lang))

#     async def on_enter(self):
#         lang_name = LANGUAGE_NAMES.get(self._native_lang or "", None)

#         if lang_name and lang_name != "English":
#             greeting = (
#                 f"Greet the user with ONE short warm {lang_name} phrase "
#                 f"(like Namaste / Kamusta / Vanakkam / Hola), "
#                 f"then immediately switch to a mix of {lang_name} and English. "
#                 f"Tell them today you'll practice English together"
#                 f"{f' about {self._topic}' if self._topic else ''}. "
#                 f"Ask how they are doing. "
#                 f"Keep it warm, 2 sentences max. "
#                 f"Speak ONLY the words — no labels, no brackets."
#             )
#         else:
#             greeting = (
#                 f"Greet the user warmly in English. "
#                 f"Tell them today you will practice English together"
#                 f"{f' about {self._topic}' if self._topic else ''}. "
#                 f"Ask how they are doing today."
#             )

#         logger.info(f"[on_enter] greeting: {greeting}")
#         await self.session.generate_reply(instructions=greeting, allow_interruptions=True)


# server = AgentServer()

# def prewarm(proc: JobProcess):
#     proc.userdata["vad"] = silero.VAD.load()

# server.setup_fnc = prewarm

# @server.rtc_session(agent_name="julian-cloud")
# async def entrypoint(ctx: JobContext):
#     transcript = []
#     start_time = None
#     participant_identity = None
#     user_email = None
#     user_id = None
#     topic = None
#     native_lang = None

#     try:
#         job_meta = json.loads(ctx.job.metadata or "{}")
#         user_email = job_meta.get("email")
#         user_id = job_meta.get("userId")
#         topic = job_meta.get("topic")
#         native_lang = job_meta.get("nativeLang")
#         logger.info(f"[job_meta] userId={user_id} | topic={topic!r} | nativeLang={native_lang!r}")
#     except Exception as e:
#         logger.warning(f"[job_meta] parse error: {e}")

#     logger.info(f"[entrypoint] room={ctx.room.name}")

#     def _parse_meta(participant):
#         nonlocal participant_identity, user_email, user_id, topic, native_lang
#         participant_identity = participant.identity
#         raw_meta = participant.metadata or "{}"
#         try:
#             meta = json.loads(raw_meta)
#             user_email = meta.get("email") or user_email
#             user_id = meta.get("userId") or user_id
#             topic = meta.get("topic") or topic
#             native_lang = meta.get("nativeLang") or native_lang
#             logger.info(f"[participant_meta] identity={participant_identity} | topic={topic!r} | nativeLang={native_lang!r}")
#         except Exception as e:
#             logger.error(f"Participant metadata parse error: {e}")

#     meta_ready = asyncio.Event()

#     def on_participant_connected(participant):
#         _parse_meta(participant)
#         meta_ready.set()

#     ctx.room.on("participant_connected", on_participant_connected)
#     await ctx.connect()

#     for p in ctx.room.remote_participants.values():
#         _parse_meta(p)
#         meta_ready.set()
#         break

#     if not meta_ready.is_set():
#         logger.info("[entrypoint] Waiting for participant...")
#         try:
#             await asyncio.wait_for(meta_ready.wait(), timeout=15.0)
#         except asyncio.TimeoutError:
#             logger.warning("[entrypoint] Timed out — using job metadata")

#     ctx.room.off("participant_connected", on_participant_connected)
#     logger.info(f"[entrypoint] Starting session | lang={native_lang!r} | topic={topic!r}")

#     session = AgentSession(
#         stt=get_deepgram_stt(native_lang),
#         llm=openai.LLM(model="gpt-4o-mini"),
#         tts=get_azure_tts(native_lang),
#         vad=ctx.proc.userdata["vad"],
#         allow_interruptions=True,
#         min_endpointing_delay=0.3,
#         max_endpointing_delay=0.8,
#     )

#     session.on("user_speech_started", lambda _: logger.info("[session] 🎤 user_speech_started"))
#     session.on("agent_speech_started", lambda _: logger.info("[session] 🔊 agent_speech_started"))
#     session.on("user_speech_committed", lambda ev: logger.info(f"[session] user said: {getattr(ev, 'user_transcript', '')!r}"))
#     session.on("agent_speech_committed", lambda ev: logger.info("[session] agent spoke"))

#     # ─── Save BOTH user and assistant utterances to DB ───────────────────────
#     @session.on("conversation_item_added")
#     def on_item_added(event):
#         try:
#             item = event.item
#             role = getattr(item, "role", None)
#             text = getattr(item, "text_content", None) or getattr(item, "text", None)
#             if role and text:
#                 entry = {"role": role, "text": text, "time": _now().isoformat()}
#                 transcript.append(entry)
#                 logger.info(f"{'User' if role == 'user' else 'Julian'}: {text}")

#                 # Save both user AND assistant to DB for client polling
#                 if user_id:
#                     asyncio.create_task(_save_utterance(user_id, ctx.room.name, entry))
#         except Exception as e:
#             logger.error(f"Error in on_item_added: {e}")

#     async def _silence_prompt_loop():
#         while True:
#             await asyncio.sleep(8)
#             try:
#                 if not transcript:
#                     continue
#                 last = transcript[-1]
#                 if last["role"] != "assistant":
#                     continue
#                 last_time = datetime.fromisoformat(last["time"]).replace(tzinfo=timezone.utc)
#                 silence = (_now() - last_time).total_seconds()
#                 if silence >= 20:
#                     logger.info(f"Silence {silence:.0f}s — prompting")
#                     await session.generate_reply(
#                         instructions="The user has been quiet. Warmly encourage them in their native language to continue. Keep it to 1 short friendly sentence.",
#                         allow_interruptions=True,
#                     )
#             except Exception as e:
#                 logger.warning(f"Silence loop error: {e}")

#     async def _save_utterance(uid, room_name, entry):
#         try:
#             async with httpx.AsyncClient(timeout=5) as client:
#                 await client.post(
#                     f"{BACKEND_URL}/api/live-transcript",
#                     json={"userId": uid, "roomName": room_name, "entry": entry},
#                     headers={"Content-Type": "application/json"},
#                 )
#         except Exception as e:
#             logger.warning(f"Live transcript save failed: {e}")

#     async def on_shutdown():
#         logger.info(f"Shutdown | Lines: {len(transcript)}")
#         duration = int((_now() - (start_time or _now())).total_seconds())
#         logger.info(f"[shutdown] duration={duration}s | userId={user_id}")

#         if user_id:
#             url = f"{BACKEND_URL}/api/deduct-minutes"
#             logger.info(f"[minutes] POST {url} | userId={user_id} secondsUsed={duration}")
#             try:
#                 async with httpx.AsyncClient(timeout=10) as client:
#                     res = await client.post(url, json={"userId": user_id, "secondsUsed": duration}, headers={"Content-Type": "application/json"})
#                     logger.info(f"[minutes] HTTP {res.status_code} | body: {res.text[:200]}")
#             except Exception as e:
#                 logger.error(f"[minutes] request failed: {e}")
#         else:
#             logger.warning(f"[minutes] SKIPPED — userId={user_id!r} duration={duration}s")

#         if not transcript:
#             logger.warning("No transcript — skipping call report")
#             return

#         payload = {
#             "roomName": ctx.room.name, "participantIdentity": participant_identity,
#             "userEmail": user_email, "userId": user_id, "duration": duration,
#             "transcript": transcript, "topic": topic, "nativeLang": native_lang,
#             "timestamp": _now().isoformat(),
#         }
#         try:
#             async with httpx.AsyncClient(timeout=15) as client:
#                 res = await client.post(f"{BACKEND_URL}/api/call-report", json=payload, headers={"Content-Type": "application/json"})
#                 logger.info(f"✅ Call report sent: {res.status_code}")
#         except Exception as e:
#             logger.error(f"Failed to send call report: {e}")

#     start_time = _now()
#     logger.info(f"[session] call started at {start_time.isoformat()}")
#     await session.start(agent=JulianAgent(topic=topic, native_lang=native_lang), room=ctx.room)

#     silence_task = asyncio.create_task(_silence_prompt_loop())
#     disconnect_event = asyncio.Event()
#     ctx.room.on("disconnected", lambda *args: disconnect_event.set())
#     await disconnect_event.wait()

#     silence_task.cancel()
#     try:
#         await silence_task
#     except asyncio.CancelledError:
#         pass

#     logger.info("[entrypoint] Room disconnected — running shutdown")
#     await on_shutdown()


# if __name__ == "__main__":
#     cli.run_app(server)

import logging
import os
import json
import httpx
import asyncio
from datetime import datetime, timezone

def _now() -> datetime:
    return datetime.now(timezone.utc)

from livekit.agents import Agent, AgentServer, AgentSession, JobContext, JobProcess, cli
from livekit.plugins import silero
from livekit.plugins import openai, deepgram, azure
from livekit.plugins.azure import ProsodyConfig

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("julian-cloud-agent")
BACKEND_URL = os.environ.get("BACKEND_URL", "https://specker.ai")

LANGUAGE_NAMES = {
    "hi": "Hindi", "ta": "Tamil", "te": "Telugu", "mr": "Marathi",
    "kn": "Kannada", "tl": "Filipino/Tagalog", "bn": "Bengali",
    "es": "Spanish", "fr": "French", "de": "German", "pt": "Portuguese",
    "ja": "Japanese", "ko": "Korean", "ar": "Arabic",
    "id": "Indonesian/Bahasa", "ms": "Malay", "vi": "Vietnamese",
    "zh": "Mandarin Chinese", "tr": "Turkish", "ru": "Russian",
    "it": "Italian", "nl": "Dutch", "en": "English",
}

DEEPGRAM_LANG_MAP = {
    "hi": "hi", "ta": "ta", "te": "te", "mr": "mr", "kn": "kn",
    "tl": "tl", "bn": "bn", "es": "es", "fr": "fr", "de": "de",
    "pt": "pt", "ja": "ja", "ko": "ko", "ar": "ar", "id": "id",
    "ms": "ms", "vi": "vi", "zh": "zh", "tr": "tr", "ru": "ru",
    "it": "it", "nl": "nl", "en": "en",
}

# Indic languages use the bilingual en-IN-NeerjaIndicNeural voice, not a native
# single-language voice — Julian's replies are mostly-English with occasional
# native words, and native-language voices read those English words robotically.
INDIC_VOICE = "en-IN-NeerjaIndicNeural"

AZURE_VOICE_MAP = {
    "hi": INDIC_VOICE,
    "ta": INDIC_VOICE,
    "te": INDIC_VOICE,
    "mr": INDIC_VOICE,
    "kn": INDIC_VOICE,
    "bn": INDIC_VOICE,
    "tl": "fil-PH-BlessicaNeural",
    "es": "es-ES-ElviraNeural",
    "fr": "fr-FR-DeniseNeural",
    "de": "de-DE-KatjaNeural",
    "pt": "pt-BR-FranciscaNeural",
    "ja": "ja-JP-NanamiNeural",
    "ko": "ko-KR-SunHiNeural",
    "ar": "ar-SA-ZariyahNeural",
    "id": "id-ID-GadisNeural",
    "ms": "ms-MY-YasminNeural",
    "vi": "vi-VN-HoaiMyNeural",
    "zh": "zh-CN-XiaoxiaoNeural",
    "tr": "tr-TR-EmelNeural",
    "ru": "ru-RU-SvetlanaNeural",
    "it": "it-IT-ElsaNeural",
    "nl": "nl-NL-FennaNeural",
    "en": "en-US-AvaMultilingualNeural",
}


def get_deepgram_stt(native_lang: str | None):
    lang_code = DEEPGRAM_LANG_MAP.get(native_lang or "", "en")
    logger.info(f"🎤 STT: Deepgram Nova-3 | language={lang_code}")
    return deepgram.STT(model="nova-3", language=lang_code)


def get_azure_tts(native_lang: str | None):
    voice = AZURE_VOICE_MAP.get(native_lang or "", "en-US-AvaMultilingualNeural")
    logger.info(f"🎙️ TTS: Azure Neural | voice={voice}")
    return azure.TTS(
        voice=voice,
        prosody=ProsodyConfig(rate=1.1),
        speech_key=os.environ.get("AZURE_SPEECH_KEY"),
        speech_region=os.environ.get("AZURE_SPEECH_REGION"),
    )


def build_instructions(topic, native_lang_code):
    lang_name = LANGUAGE_NAMES.get(native_lang_code or "", None)

    topic_line = (
        f"Today's conversation topic is: {topic}. Keep the conversation around this topic."
        if topic else
        "You can talk about anything — ask what's on the user's mind."
    )

    if lang_name and lang_name != "English":
        lang_line = f"""
You are an English coach. The user's native language is {lang_name}.

ADAPTIVE SPEAKING STYLE:
- If the user is speaking comfortably in English, respond ONLY in English — no {lang_name} at all.
- If the user is struggling, hesitant, or speaks to you in {lang_name}, you may use a few brief {lang_name} words (a greeting, a word of encouragement, or to clarify one tricky word) — but at least 80% of your response must still be English.
- NEVER give a full sentence-by-sentence translation. {lang_name} is only a light seasoning to help them follow along, not a parallel conversation.
- Be warm, encouraging, and natural. Keep responses short — 1 to 2 sentences. Always ask a follow-up question.
- ONLY speak the actual words. No stage directions, no labels, no brackets.

WHEN USER SPEAKS IN {lang_name}:
- Understand what they said.
- Respond mostly in English; you may add one short {lang_name} phrase of encouragement.
- Encourage them to try saying it in English next.

WHEN USER SPEAKS IN ENGLISH:
- Respond purely in English.
- Gently correct any grammar mistakes by using the correct form in your reply.
- Ask a follow-up question to keep them talking.
"""
        logger.info(f"Language mode: adaptive (mostly English, native={lang_name})")
    else:
        lang_line = """
Speak naturally in English only.
Gently correct any mistakes by naturally using the correct version in your reply.
Keep responses short — 1 to 2 sentences. Always ask a follow-up question.
"""
        logger.info("Language mode: English only")

    return f"""You are Julian, a warm, fun, encouraging AI English coach on a phone call.
Keep responses SHORT — 1 to 2 sentences max. Be friendly and natural.
Always ask a follow-up question to keep the conversation going.

{topic_line}

{lang_line}

LISTENING RULES:
- Always wait for the user to fully finish speaking before responding.
- Never interrupt. After you finish speaking, go straight into listening mode."""


class JulianAgent(Agent):
    def __init__(self, topic=None, native_lang=None, on_tts_text=None):
        self._topic       = topic
        self._native_lang = native_lang
        self._on_tts_text = on_tts_text   # async fn(text: str)
        super().__init__(instructions=build_instructions(topic, native_lang))

    # ─── Intercept text RIGHT BEFORE it goes to TTS ───────────────────────────
    # tts_node gets an async iterator of text chunks from the LLM.
    # Strategy:
    #   1. Collect all text chunks from the iterator into a buffer
    #   2. Fire DB save AND TTS synthesis in true parallel (asyncio.gather)
    #   3. Yield TTS audio chunks as they arrive — no extra latency added
    async def tts_node(self, text, model_settings):
        # Responses are short (1-2 sentences), so synthesize the whole reply
        # in a single Azure TTS call. Splitting into multiple calls (per word
        # or per sentence) creates an audible seam/gap at every boundary —
        # one call per turn gives one continuous, fluent audio stream.
        full_text_parts = []
        async for chunk in text:
            full_text_parts.append(chunk)

        full_text = "".join(
            t.text if hasattr(t, "text") else str(t)
            for t in full_text_parts
        ).strip()

        logger.info(f"📝 [TTS] Intercepted: {full_text[:80]}...")
        if self._on_tts_text and full_text:
            asyncio.create_task(self._on_tts_text(full_text))

        async def _single_chunk():
            if full_text:
                yield full_text

        async for audio_chunk in Agent.tts_node(self, _single_chunk(), model_settings):
            yield audio_chunk

    async def on_enter(self):
        greeting = (
            f"Greet the user warmly in English only. "
            f"Tell them today you will practice English together"
            f"{f' about {self._topic}' if self._topic else ''}. "
            f"Ask how they are doing today. "
            f"Keep it to 2 sentences max. Speak ONLY the words — no labels, no brackets."
        )

        logger.info(f"[on_enter] greeting: {greeting}")
        await self.session.generate_reply(instructions=greeting, allow_interruptions=True)


server = AgentServer()

def prewarm(proc: JobProcess):
    proc.userdata["vad"] = silero.VAD.load()

server.setup_fnc = prewarm

@server.rtc_session(agent_name="julian-cloud")
async def entrypoint(ctx: JobContext):
    transcript           = []
    start_time           = None
    participant_identity = None
    user_email           = None
    user_id              = None
    topic                = None
    native_lang          = None

    try:
        job_meta    = json.loads(ctx.job.metadata or "{}")
        user_email  = job_meta.get("email")
        user_id     = job_meta.get("userId")
        topic       = job_meta.get("topic")
        native_lang = job_meta.get("nativeLang")
        logger.info(f"[job_meta] userId={user_id} | topic={topic!r} | nativeLang={native_lang!r}")
    except Exception as e:
        logger.warning(f"[job_meta] parse error: {e}")

    logger.info(f"[entrypoint] room={ctx.room.name}")

    def _parse_meta(participant):
        nonlocal participant_identity, user_email, user_id, topic, native_lang
        participant_identity = participant.identity
        raw_meta = participant.metadata or "{}"
        try:
            meta        = json.loads(raw_meta)
            user_email  = meta.get("email")      or user_email
            user_id     = meta.get("userId")     or user_id
            topic       = meta.get("topic")      or topic
            native_lang = meta.get("nativeLang") or native_lang
            logger.info(f"[participant_meta] identity={participant_identity} | topic={topic!r} | nativeLang={native_lang!r}")
        except Exception as e:
            logger.error(f"Participant metadata parse error: {e}")

    meta_ready = asyncio.Event()

    def on_participant_connected(participant):
        _parse_meta(participant)
        meta_ready.set()

    ctx.room.on("participant_connected", on_participant_connected)
    await ctx.connect()

    for p in ctx.room.remote_participants.values():
        _parse_meta(p)
        meta_ready.set()
        break

    if not meta_ready.is_set():
        logger.info("[entrypoint] Waiting for participant...")
        try:
            await asyncio.wait_for(meta_ready.wait(), timeout=15.0)
        except asyncio.TimeoutError:
            logger.warning("[entrypoint] Timed out — using job metadata")

    ctx.room.off("participant_connected", on_participant_connected)
    logger.info(f"[entrypoint] Starting session | lang={native_lang!r} | topic={topic!r}")

    http_client = httpx.AsyncClient(timeout=5)

    # ─── Called from tts_node — saves text to DB before TTS speaks it ────────
    async def _save_before_tts(text):
        # text may be a string or a SynthesisInput object — extract the string
        if hasattr(text, "text"):
            text = text.text
        elif not isinstance(text, str):
            text = str(text)

        text = text.strip()
        if not text:
            return

        entry = {"role": "assistant", "text": text, "time": _now().isoformat()}
        transcript.append(entry)

        if user_id:
            try:
                await http_client.post(
                    f"{BACKEND_URL}/api/live-transcript",
                    json={"userId": user_id, "roomName": ctx.room.name, "entry": entry},
                    headers={"Content-Type": "application/json"},
                )
                logger.info(f"✅ [TTS→DB] Saved: {text[:60]}...")
            except Exception as e:
                logger.warning(f"_save_before_tts HTTP error: {e}")

    session = AgentSession(
        stt=get_deepgram_stt(native_lang),
        llm=openai.LLM(model="gpt-4o-mini"),
        tts=get_azure_tts(native_lang),
        vad=ctx.proc.userdata["vad"],
        allow_interruptions=True,
        min_endpointing_delay=0.3,
        max_endpointing_delay=0.8,
    )

    session.on("user_speech_started",    lambda _: logger.info("[session] 🎤 user_speech_started"))
    session.on("agent_speech_started",   lambda _: logger.info("[session] 🔊 agent_speech_started"))
    session.on("user_speech_committed",  lambda ev: logger.info(f"[session] user said: {getattr(ev, 'user_transcript', '')!r}"))
    session.on("agent_speech_committed", lambda ev: logger.info("[session] agent spoke"))

    # ─── Save user utterances ─────────────────────────────────────────────────
    @session.on("conversation_item_added")
    def on_item_added(event):
        try:
            item = event.item
            role = getattr(item, "role", None)
            text = getattr(item, "text_content", None) or getattr(item, "text", None)
            if role == "user" and text:
                entry = {"role": "user", "text": text, "time": _now().isoformat()}
                transcript.append(entry)
                logger.info(f"User: {text}")
                if user_id:
                    asyncio.create_task(_save_utterance(user_id, ctx.room.name, entry))
        except Exception as e:
            logger.error(f"Error in on_item_added: {e}")

    async def _save_utterance(uid, room_name, entry):
        try:
            await http_client.post(
                f"{BACKEND_URL}/api/live-transcript",
                json={"userId": uid, "roomName": room_name, "entry": entry},
                headers={"Content-Type": "application/json"},
            )
        except Exception as e:
            logger.warning(f"User utterance save failed: {e}")

    async def _silence_prompt_loop():
        while True:
            await asyncio.sleep(8)
            try:
                if not transcript:
                    continue
                last = transcript[-1]
                if last["role"] != "assistant":
                    continue
                last_time = datetime.fromisoformat(last["time"]).replace(tzinfo=timezone.utc)
                silence   = (_now() - last_time).total_seconds()
                if silence >= 20:
                    logger.info(f"Silence {silence:.0f}s — prompting")
                    await session.generate_reply(
                        instructions="The user has been quiet. Warmly encourage them in their native language to continue. Keep it to 1 short friendly sentence.",
                        allow_interruptions=True,
                    )
            except Exception as e:
                logger.warning(f"Silence loop error: {e}")

    async def on_shutdown():
        logger.info(f"Shutdown | Lines: {len(transcript)}")
        duration = int((_now() - (start_time or _now())).total_seconds())
        logger.info(f"[shutdown] duration={duration}s | userId={user_id}")

        if user_id:
            url = f"{BACKEND_URL}/api/deduct-minutes"
            logger.info(f"[minutes] POST {url} | userId={user_id} secondsUsed={duration}")
            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    res = await client.post(
                        url,
                        json={"userId": user_id, "secondsUsed": duration},
                        headers={"Content-Type": "application/json"},
                    )
                    logger.info(f"[minutes] HTTP {res.status_code} | body: {res.text[:200]}")
            except Exception as e:
                logger.error(f"[minutes] request failed: {e}")
        else:
            logger.warning(f"[minutes] SKIPPED — userId={user_id!r} duration={duration}s")

        await http_client.aclose()

        if not transcript:
            logger.warning("No transcript — skipping call report")
            return

        payload = {
            "roomName":            ctx.room.name,
            "participantIdentity": participant_identity,
            "userEmail":           user_email,
            "userId":              user_id,
            "duration":            duration,
            "transcript":          transcript,
            "topic":               topic,
            "nativeLang":          native_lang,
            "timestamp":           _now().isoformat(),
        }
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                res = await client.post(
                    f"{BACKEND_URL}/api/call-report",
                    json=payload,
                    headers={"Content-Type": "application/json"},
                )
                logger.info(f"✅ Call report sent: {res.status_code}")
        except Exception as e:
            logger.error(f"Failed to send call report: {e}")

    start_time = _now()
    logger.info(f"[session] call started at {start_time.isoformat()}")

    await session.start(
        agent=JulianAgent(
            topic=topic,
            native_lang=native_lang,
            on_tts_text=_save_before_tts,
        ),
        room=ctx.room,
    )

    silence_task = asyncio.create_task(_silence_prompt_loop())
    disconnect_event = asyncio.Event()
    ctx.room.on("disconnected", lambda *args: disconnect_event.set())
    await disconnect_event.wait()

    silence_task.cancel()
    try:
        await silence_task
    except asyncio.CancelledError:
        pass

    logger.info("[entrypoint] Room disconnected — running shutdown")
    await on_shutdown()


if __name__ == "__main__":
    cli.run_app(server)