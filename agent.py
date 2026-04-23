# import logging
# import os
# import json
# import httpx
# import asyncio
# from datetime import datetime
# from openai import AsyncOpenAI
# from livekit.agents import Agent, AgentServer, AgentSession, JobContext, JobProcess, cli
# from livekit.plugins import silero
# from livekit.plugins import openai, deepgram, elevenlabs

# logging.basicConfig(
#     level=logging.INFO,
#     format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
#     datefmt="%H:%M:%S",
# )
# logger = logging.getLogger("julian-cloud-agent")
# logger.setLevel(logging.DEBUG)

# BACKEND_URL    = os.environ.get("BACKEND_URL", "https://specker.ai")
# OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
# ELEVEN_API_KEY = os.environ.get("ELEVEN_API_KEY")

# logger.info("=== Julian Cloud Agent starting ===")
# logger.info(f"BACKEND_URL    : {BACKEND_URL}")
# logger.info(f"OPENAI_API_KEY : {'set' if OPENAI_API_KEY else 'MISSING'}")
# logger.info(f"ELEVEN_API_KEY : {'set' if ELEVEN_API_KEY else 'MISSING'}")

# VOICE_ID = "21m00Tcm4TlvDq8ikWAM"  # Rachel — default ElevenLabs voice

# LANGUAGE_NAMES = {
#     "hi": "Hindi",
#     "es": "Spanish",
#     "fr": "French",
#     "de": "German",
#     "pt": "Portuguese",
#     "ja": "Japanese",
#     "ko": "Korean",
#     "ar": "Arabic",
#     "id": "Indonesian/Bahasa",
#     "vi": "Vietnamese",
#     "zh": "Mandarin Chinese",
#     "en": "English",
# }

# DEEPGRAM_LANG_MAP = {
#     "hi": "hi",
#     "es": "es",
#     "fr": "fr",
#     "de": "de",
#     "pt": "pt",
#     "ja": "ja",
#     "ko": "ko",
#     "ar": "ar",
#     "id": "id",
#     "vi": "vi",
#     "zh": "zh",
#     "en": "en",
# }


# def get_deepgram_stt(native_lang: str | None):
#     """
#     Deepgram Nova-2 STT — stable long sessions, no dropout.
#     """
#     lang_code = DEEPGRAM_LANG_MAP.get(native_lang or "", "en")
#     logger.info(f"🎤 STT: Deepgram Nova-2 | language={lang_code}")
#     return deepgram.STT(
#         model="nova-2",
#         language=lang_code,
#         interim_results=True,
#         smart_format=True,
#         punctuate=True,
#         filler_words=True,
#         endpointing_ms=300,
#     )


# def get_elevenlabs_tts(native_lang: str | None):
#     """
#     ElevenLabs Flash v2.5 TTS — 75ms latency, natural voice.
#     Auto-detects language from text — no language param needed.
#     """
#     logger.info(f"🎙️ TTS: ElevenLabs Flash v2.5 | voice={VOICE_ID}")
#     return elevenlabs.TTS(
#         model="eleven_flash_v2_5",
#         voice_id=VOICE_ID,
#         api_key=ELEVEN_API_KEY,
#     )


# async def analyze_with_gpt(transcript: list, duration: int) -> dict:
#     try:
#         client = AsyncOpenAI(api_key=OPENAI_API_KEY)
#         transcript_text = "\n".join([
#             f"{'User' if m['role'] == 'user' else 'Julian'}: {m['text']}"
#             for m in transcript
#         ])
#         prompt = f"""Analyze this English language learning conversation and return a detailed JSON report.

# TRANSCRIPT:
# {transcript_text}

# DURATION: {duration // 60} minutes {duration % 60} seconds

# Return ONLY valid JSON with no markdown or explanation:
# {{
#   "overall_score": <0-100>,
#   "summary": "<2-3 sentence summary>",
#   "grammar": {{
#     "score": <0-100>,
#     "mistakes": [{{"original": "", "corrected": "", "explanation": ""}}],
#     "feedback": "<1-2 sentences>"
#   }},
#   "vocabulary": {{
#     "score": <0-100>,
#     "advanced_words_used": [],
#     "suggestions": [],
#     "feedback": "<1-2 sentences>"
#   }},
#   "fluency": {{
#     "score": <0-100>,
#     "filler_words_detected": [],
#     "pace": "<too fast | good | too slow>",
#     "feedback": "<1-2 sentences>"
#   }},
#   "confidence": {{
#     "score": <0-100>,
#     "feedback": "<1-2 sentences>"
#   }},
#   "pronunciation_tips": [{{"word": "", "tip": ""}}],
#   "strengths": [],
#   "areas_to_improve": [],
#   "next_steps": []
# }}"""
#         response = await client.chat.completions.create(
#             model="gpt-4o",
#             temperature=0.3,
#             messages=[{"role": "user", "content": prompt}],
#         )
#         raw = response.choices[0].message.content.strip()
#         if raw.startswith("```"):
#             raw = raw.split("```")[1]
#             if raw.startswith("json"):
#                 raw = raw[4:]
#         return json.loads(raw.strip())
#     except Exception as e:
#         logger.error(f"GPT analysis error: {e}")
#         return {}


# def build_instructions(topic, native_lang_code):
#     lang_name = LANGUAGE_NAMES.get(native_lang_code or "", None)
#     logger.debug(f"build_instructions | lang_code={native_lang_code!r} → lang_name={lang_name!r} | topic={topic!r}")

#     topic_line = (
#         f"Today's conversation topic is: {topic}. Keep the conversation around this topic."
#         if topic else
#         "You can talk about anything — ask what's on the user's mind."
#     )

#     if lang_name and lang_name != "English":
#         lang_line = f"""
# You are an English tutor. The user speaks {lang_name} and wants to learn English.

# YOUR PERSONA:
# - You are Julian — a warm, fun, patient English tutor fluent in both English and {lang_name}.
# - You speak PRIMARILY in English.
# - You use {lang_name} ONLY when giving explanations, corrections, or encouragement.
# - Think of yourself as a friendly bilingual tutor who switches to {lang_name} to make things clear, then brings the student back to English.

# CONVERSATION FLOW:

# WHEN USER SPEAKS IN {lang_name}:
# - Step 1: Respond warmly in English acknowledging what they said.
# - Step 2: Switch to {lang_name} to explain how to say it in English.
# - Step 3: Ask them to repeat it in English. Stay encouraging.
# - Step 4: When they repeat, praise them with a small {lang_name} warmth word, then continue in English.

# WHEN USER SPEAKS IN ENGLISH:
# - Respond in English naturally.
# - If they make a grammar mistake, gently use the correct form in your reply without pointing it out directly.
# - Give a small {lang_name} encouragement like "Bilkul sahi!", "Shabash!", "Bagus!", "Hao!" to celebrate.
# - Ask a follow-up question to keep them speaking English.

# WHEN EXPLAINING GRAMMAR OR VOCABULARY:
# - Always explain in {lang_name} first so they understand clearly.
# - Then give the English version.
# - Then ask them to try.

# EXAMPLES (Hindi):
# User: "main theek hoon"
# Julian: "Oh great! Suniye — Hindi mein aapne kaha 'main theek hoon', English mein isko bolte hain: 'I am doing fine'. Ab aap try karein!"

# User: "I am doing fine"
# Julian: "Shabash yaar! Perfect! So tell me, have you travelled anywhere recently?"

# User: "I goes to market yesterday"
# Julian: "Nice try! Thoda correction — 'I went to market yesterday' bolte hain. Ab dobara bolein!"

# EXAMPLES (Indonesian):
# User: "saya baik baik saja"
# Julian: "Oh nice! In Indonesian 'saya baik baik saja' — in English: 'I am doing well'. Now you try!"

# User: "I am doing well"
# Julian: "Bagus! Perfect! So what have you been up to today? Tell me in English!"

# RULES:
# - Keep each response SHORT — 2 to 3 sentences max.
# - Always end with either a retry request OR a follow-up question in English.
# - Use {lang_name} for explanations and encouragement ONLY.
# - ONLY speak the actual words. No stage directions, no labels, no brackets.
# - Never be preachy. Keep it fun like a friendly tutor session.
# """
#         logger.info(f"Language mode: TUTOR ({lang_name} explanations → English practice)")
#     else:
#         lang_line = """
# Speak naturally in English only.
# Gently correct any mistakes by naturally using the correct version in your reply.
# Keep responses short — 1 to 2 sentences. Always ask a follow-up question.
# """
#         logger.info("Language mode: English only")

#     return f"""You are Julian, a warm, fun, patient AI English tutor on a phone call.
# You genuinely care about helping the user improve their English.
# Be encouraging, friendly, and natural — like a real tutor who knows the student's language.

# {topic_line}

# {lang_line}

# LISTENING RULES:
# - ALWAYS wait for the user to fully finish speaking before responding.
# - Never interrupt. After you finish speaking, go straight into listening mode.
# - Be fully present — respond to exactly what they just said."""


# class JulianAgent(Agent):
#     def __init__(self, topic=None, native_lang=None):
#         self._topic       = topic
#         self._native_lang = native_lang
#         super().__init__(instructions=build_instructions(topic, native_lang))

#     async def on_enter(self):
#         lang_name = LANGUAGE_NAMES.get(self._native_lang or "", None)

#         if lang_name and lang_name != "English":
#             greeting = (
#                 f"Greet the user warmly — start with ONE short greeting in {lang_name} "
#                 f"(e.g. Namaste / Hola / Bonjour), then switch to English immediately. "
#                 f"In English, tell them today you'll practice English together"
#                 f"{f' about {self._topic}' if self._topic else ''}. "
#                 f"Ask how they are doing in English. "
#                 f"Keep it natural, warm, 2 sentences max. "
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
#         await self.session.generate_reply(
#             instructions=greeting,
#             allow_interruptions=True,
#         )


# server = AgentServer()

# def prewarm(proc: JobProcess):
#     proc.userdata["vad"] = silero.VAD.load()

# server.setup_fnc = prewarm

# @server.rtc_session(agent_name="julian-cloud")
# async def entrypoint(ctx: JobContext):
#     transcript  = []
#     start_time  = datetime.utcnow()
#     participant_identity = None
#     user_email  = None
#     user_id     = None
#     topic       = None
#     native_lang = None

#     # ── Step 1: Read from job dispatch metadata FIRST ─────────────────────────
#     try:
#         job_meta    = json.loads(ctx.job.metadata or "{}")
#         user_email  = job_meta.get("email")
#         user_id     = job_meta.get("userId")
#         topic       = job_meta.get("topic")
#         native_lang = job_meta.get("nativeLang")
#         logger.info(f"[job_meta] userId={user_id} | topic={topic!r} | nativeLang={native_lang!r}")
#     except Exception as e:
#         logger.warning(f"[job_meta] parse error: {e}")

#     logger.info(f"[entrypoint] room={ctx.room.name}")

#     def _parse_meta(participant):
#         nonlocal participant_identity, user_email, user_id, topic, native_lang
#         participant_identity = participant.identity
#         raw_meta = participant.metadata or "{}"
#         logger.debug(f"[participant_meta] raw: {raw_meta}")
#         try:
#             meta        = json.loads(raw_meta)
#             user_email  = meta.get("email")      or user_email
#             user_id     = meta.get("userId")     or user_id
#             topic       = meta.get("topic")      or topic
#             native_lang = meta.get("nativeLang") or native_lang
#             logger.info(f"[participant_meta] identity={participant_identity} | topic={topic!r} | nativeLang={native_lang!r}")
#         except Exception as e:
#             logger.error(f"Participant metadata parse error: {e}")

#     # ── Step 2: Register listener BEFORE connecting ───────────────────────────
#     meta_ready = asyncio.Event()

#     def on_participant_connected(participant):
#         _parse_meta(participant)
#         meta_ready.set()

#     ctx.room.on("participant_connected", on_participant_connected)

#     # ── Step 3: Connect ───────────────────────────────────────────────────────
#     await ctx.connect()

#     # ── Step 4: Check if participant already in room ──────────────────────────
#     for p in ctx.room.remote_participants.values():
#         _parse_meta(p)
#         meta_ready.set()
#         break

#     # ── Step 5: Wait up to 15s ────────────────────────────────────────────────
#     if not meta_ready.is_set():
#         logger.info("[entrypoint] Waiting for participant...")
#         try:
#             await asyncio.wait_for(meta_ready.wait(), timeout=15.0)
#             logger.info(f"[entrypoint] Participant arrived | nativeLang={native_lang!r}")
#         except asyncio.TimeoutError:
#             logger.warning("[entrypoint] Timed out — using job metadata")

#     ctx.room.off("participant_connected", on_participant_connected)
#     logger.info(f"[entrypoint] Starting session | lang={native_lang!r} | topic={topic!r}")

#     # ── Session — Deepgram STT + ElevenLabs TTS ───────────────────────────────
#     session = AgentSession(
#         stt=get_deepgram_stt(native_lang),
#         llm=openai.LLM(model="gpt-4o-mini"),
#         tts=get_elevenlabs_tts(native_lang),
#         vad=ctx.proc.userdata["vad"],
#         allow_interruptions=True,
#         min_endpointing_delay=0.3,
#         max_endpointing_delay=0.8,
#     )

#     session.on("user_speech_started",    lambda _:  logger.info("[session] 🎤 user_speech_started"))
#     session.on("agent_speech_started",   lambda _:  logger.info("[session] 🔊 agent_speech_started"))
#     session.on("user_speech_committed",  lambda ev: logger.info(f"[session] ✅ user said: {getattr(ev, 'user_transcript', '')!r}"))
#     session.on("agent_speech_committed", lambda ev: logger.info(f"[session] ✅ agent spoke"))

#     @session.on("conversation_item_added")
#     def on_item_added(event):
#         try:
#             item = event.item
#             role = getattr(item, "role", None)
#             text = getattr(item, "text_content", None) or getattr(item, "text", None)
#             if role and text:
#                 entry = {"role": role, "text": text, "time": datetime.utcnow().isoformat()}
#                 transcript.append(entry)
#                 logger.info(f"{'User' if role == 'user' else 'Julian'}: {text}")
#                 if role == "user" and user_id:
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
#                 last_time = datetime.fromisoformat(last["time"])
#                 silence   = (datetime.utcnow() - last_time).total_seconds()
#                 if silence >= 20:
#                     logger.info(f"Silence {silence:.0f}s — prompting")
#                     await session.generate_reply(
#                         instructions=(
#                             "The user has been quiet. "
#                             "Warmly encourage them in their native language to try saying the English phrase. "
#                             "Keep it to 1 short friendly sentence only."
#                         ),
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
#         if not transcript:
#             return
#         duration = int((datetime.utcnow() - start_time).total_seconds())

#         logger.info("Running GPT analysis...")
#         gpt_result = await analyze_with_gpt(transcript, duration)
#         if gpt_result:
#             logger.info(f"GPT done. Score: {gpt_result.get('overall_score')}")
#         else:
#             logger.warning("GPT analysis returned empty")

#         payload = {
#             "roomName":            ctx.room.name,
#             "participantIdentity": participant_identity,
#             "userEmail":           user_email,
#             "userId":              user_id,
#             "duration":            duration,
#             "transcript":          transcript,
#             "topic":               topic,
#             "nativeLang":          native_lang,
#             "analysis":            gpt_result,
#             "timestamp":           datetime.utcnow().isoformat(),
#         }
#         try:
#             async with httpx.AsyncClient(timeout=30) as client:
#                 res = await client.post(
#                     f"{BACKEND_URL}/api/call-report",
#                     json=payload,
#                     headers={"Content-Type": "application/json"},
#                 )
#                 logger.info(f"✅ Sent: {res.status_code}")
#         except Exception as e:
#             logger.error(f"Failed to send: {e}")

#     ctx.add_shutdown_callback(on_shutdown)

#     await session.start(
#         agent=JulianAgent(topic=topic, native_lang=native_lang),
#         room=ctx.room,
#     )

#     silence_task = asyncio.create_task(_silence_prompt_loop())
#     disconnect_event = asyncio.Event()
#     ctx.room.on("disconnected", lambda: disconnect_event.set())
#     await disconnect_event.wait()

#     silence_task.cancel()
#     try:
#         await silence_task
#     except asyncio.CancelledError:
#         pass


# if __name__ == "__main__":
#     cli.run_app(server)


import logging
import os
import json
import httpx
import asyncio
from datetime import datetime
from livekit.agents import Agent, AgentServer, AgentSession, JobContext, JobProcess, cli
from livekit.plugins import silero
from livekit.plugins import openai, deepgram, google

logger = logging.getLogger("julian-cloud-agent")
BACKEND_URL = os.environ.get("BACKEND_URL", "https://specker.ai")

LANGUAGE_NAMES = {
    "tl":  "Filipino/Tagalog",
    "hi":  "Hindi",
    "bn":  "Bengali",
    "ta":  "Tamil",
    "te":  "Telugu",
    "mr":  "Marathi",
    "gu":  "Gujarati",
    "kn":  "Kannada",
    "ml":  "Malayalam",
    "pa":  "Punjabi",
    "ur":  "Urdu",
    "id":  "Indonesian/Bahasa",
    "ms":  "Malay",
    "vi":  "Vietnamese",
    "th":  "Thai",
    "ar":  "Arabic",
    "es":  "Spanish",
    "pt":  "Portuguese",
    "fr":  "French",
    "de":  "German",
    "zh":  "Mandarin Chinese",
    "ja":  "Japanese",
    "ko":  "Korean",
    "sw":  "Swahili",
    "en":  "English",
}

def get_google_tts(native_lang: str | None):
    """
    Always use an English voice for code-switching quality.
    Neural2 voices handle mixed-language text much better than native voices.
    """
    return google.TTS(
        voice_name="en-US-Neural2-F",
        language="en-US",
        gender="female",
    )

def build_instructions(topic: str | None, native_lang_code: str | None) -> str:
    lang_name = LANGUAGE_NAMES.get(native_lang_code or "", None)

    topic_line = (
        f"Today's conversation topic is: **{topic}**. "
        f"Start the conversation around this topic naturally."
        if topic else
        "You can talk about anything — ask what's on the user's mind."
    )

    if lang_name and lang_name != "English":
        lang_line = f"""
You MUST speak in a natural mix of {lang_name} and English — this is called code-switching.
Rules:
- Use simple {lang_name} words and phrases naturally woven into English sentences.
- Greet in {lang_name} first, then switch to mixed speech.
- Use English for explanations, feedback, and corrections.
- Use {lang_name} for greetings, encouragement, filler phrases, and emotional warmth.
- Example style (Filipino): "Kamusta ka? So how was your day today? Okay lang ba?"
- Example style (Hindi): "Arre yaar, that was really good! Aur bolo, kya chal raha hai?"
- Keep it natural — don't translate every word, just mix freely like a bilingual friend.
- NEVER speak 100% in {lang_name} — always keep English as the base.
- IMPORTANT: Write ONLY the words to be spoken. No stage directions, no brackets, no labels like 'Julian:'.
"""
    else:
        lang_line = "Speak naturally in English only."

    return f"""You are Julian, a warm and empathetic AI English coach on a phone call.
Keep responses short — 1 to 2 sentences. Be warm, friendly, and encouraging.
Ask follow-up questions to keep the conversation going.

{topic_line}

{lang_line}

Your goal is to help the user practice English confidently. Gently correct mistakes by 
repeating what they said correctly in your response, without being preachy about it."""


class JulianAgent(Agent):
    def __init__(self, topic: str | None = None, native_lang: str | None = None):
        self._topic       = topic
        self._native_lang = native_lang
        super().__init__(instructions=build_instructions(topic, native_lang))

    async def on_enter(self):
        lang_name = LANGUAGE_NAMES.get(self._native_lang or "", None)

        if lang_name and lang_name != "English":
            greeting = (
                f"Greet the user warmly in {lang_name} first (one short phrase), "
                f"then switch to a mix of {lang_name} and English. "
                f"Ask how they are doing today. "
                f"Speak ONLY the words — no labels, no brackets, no stage directions."
            )
        else:
            greeting = "Greet the user warmly in English and ask how they are doing today."

        if self._topic:
            greeting += f" Then naturally bring up today's topic: {self._topic}."

        await self.session.generate_reply(
            instructions=greeting,
            allow_interruptions=True,
        )


server = AgentServer()

def prewarm(proc: JobProcess):
    proc.userdata["vad"] = silero.VAD.load()

server.setup_fnc = prewarm

@server.rtc_session(agent_name="julian-cloud")
async def entrypoint(ctx: JobContext):
    transcript = []
    start_time = datetime.utcnow()

    participant_identity = None
    user_email           = None
    user_id              = None
    topic                = None
    native_lang          = None

    # ── Wait for participant so we have metadata before starting agent ────────
    participant_joined = asyncio.Event()

    def on_participant_connected(participant):
        nonlocal participant_identity, user_email, user_id, topic, native_lang
        participant_identity = participant.identity
        try:
            meta        = json.loads(participant.metadata or "{}")
            user_email  = meta.get("email")
            user_id     = meta.get("userId")
            topic       = meta.get("topic")
            native_lang = meta.get("nativeLang")
            logger.info(f"✅ Participant joined: {participant_identity} | topic: {topic} | lang: {native_lang}")
        except Exception as e:
            logger.error(f"Metadata parse error: {e}")
        participant_joined.set()

    # Check if participant already in room
    for p in ctx.room.remote_participants.values():
        on_participant_connected(p)
        break

    # If not yet joined, wait up to 15 seconds
    if not participant_joined.is_set():
        ctx.room.on("participant_connected", on_participant_connected)
        try:
            await asyncio.wait_for(participant_joined.wait(), timeout=15.0)
        except asyncio.TimeoutError:
            logger.warning("⚠️ Timed out waiting for participant — using defaults")

    logger.info(f"🎯 Starting agent | topic: {topic} | lang: {native_lang}")

    # ── Session with Google TTS ───────────────────────────────────────────────
    session = AgentSession(
        stt=deepgram.STT(model="nova-2", language="en"),
        llm=openai.LLM(model="gpt-4o-mini"),
        tts=get_google_tts(native_lang),   # ← Google TTS
        vad=ctx.proc.userdata["vad"],
    )

    @session.on("conversation_item_added")
    def on_item_added(event):
        try:
            item = event.item
            role = getattr(item, "role", None)
            text = getattr(item, "text_content", None) or getattr(item, "text", None)
            if role and text:
                entry = {
                    "role": role,
                    "text": text,
                    "time": datetime.utcnow().isoformat(),
                }
                transcript.append(entry)
                logger.info(f"{'User' if role == 'user' else 'Julian'}: {text}")

                if role == "user" and user_id:
                    asyncio.create_task(_save_utterance(user_id, ctx.room.name, entry))
        except Exception as e:
            logger.error(f"Error in on_item_added: {e}")

    async def _save_utterance(uid, room_name, entry):
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                await client.post(
                    f"{BACKEND_URL}/api/live-transcript",
                    json={"userId": uid, "roomName": room_name, "entry": entry},
                    headers={"Content-Type": "application/json"},
                )
        except Exception as e:
            logger.warning(f"Live transcript save failed: {e}")

    async def on_shutdown():
        logger.info(f"Shutdown | Lines: {len(transcript)}")
        if not transcript:
            logger.warning("No transcript — skipping")
            return

        duration = int((datetime.utcnow() - start_time).total_seconds())
        logger.info(f"Sending | duration: {duration}s | lines: {len(transcript)} | topic: {topic} | lang: {native_lang}")

        payload = {
            "roomName":            ctx.room.name,
            "participantIdentity": participant_identity,
            "userEmail":           user_email,
            "userId":              user_id,
            "duration":            duration,
            "transcript":          transcript,
            "topic":               topic,
            "nativeLang":          native_lang,
            "timestamp":           datetime.utcnow().isoformat(),
        }
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                res = await client.post(
                    f"{BACKEND_URL}/api/call-report",
                    json=payload,
                    headers={"Content-Type": "application/json"},
                )
                logger.info(f"✅ Sent to server: {res.status_code}")
        except Exception as e:
            logger.error(f"Failed to send: {e}")

    ctx.add_shutdown_callback(on_shutdown)

    await session.start(
        agent=JulianAgent(topic=topic, native_lang=native_lang),
        room=ctx.room,
    )

    disconnect_event = asyncio.Event()
    ctx.room.on("disconnected", lambda: disconnect_event.set())
    await disconnect_event.wait()


if __name__ == "__main__":
    cli.run_app(server)