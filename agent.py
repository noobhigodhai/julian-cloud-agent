import logging
import os
import json
import httpx
import asyncio
from datetime import datetime
from livekit.agents import Agent, AgentServer, AgentSession, JobContext, JobProcess, cli
from livekit.plugins import silero
from livekit.plugins import openai, deepgram

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("julian-cloud-agent")
BACKEND_URL = os.environ.get("BACKEND_URL", "https://specker.ai")

LANGUAGE_NAMES = {
    "hi": "Hindi",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
    "pt": "Portuguese",
    "ja": "Japanese",
    "ko": "Korean",
    "ar": "Arabic",
    "id": "Indonesian/Bahasa",
    "vi": "Vietnamese",
    "zh": "Mandarin Chinese",
    "ta": "Tamil",
    "te": "Telugu",
    "mr": "Marathi",
    "tl": "Filipino/Tagalog",
    "bn": "Bengali",
    "tr": "Turkish",
    "ru": "Russian",
    "it": "Italian",
    "nl": "Dutch",
    "en": "English",
}

# Deepgram Nova-3 language codes
DEEPGRAM_LANG_MAP = {
    "hi": "hi",
    "es": "es",
    "fr": "fr",
    "de": "de",
    "pt": "pt",
    "ja": "ja",
    "ko": "ko",
    "ar": "ar",
    "id": "id",
    "vi": "vi",
    "zh": "zh",
    "ta": "ta",
    "te": "te",
    "mr": "mr",
    "tl": "tl",
    "bn": "bn",
    "tr": "tr",
    "ru": "ru",
    "it": "it",
    "nl": "nl",
    "en": "en",
}


def get_deepgram_stt(native_lang: str | None):
    """
    Deepgram Nova-3 STT — supports Tamil, Telugu, Marathi, Filipino + more.
    Mumbai colocation for Hindi gives lower latency for Indian users.
    """
    lang_code = DEEPGRAM_LANG_MAP.get(native_lang or "", "en")
    logger.info(f"🎤 STT: Deepgram Nova-3 | language={lang_code}")
    return deepgram.STT(
        model="nova-3",
        language=lang_code,
    )


def get_deepgram_tts(native_lang: str | None):
    """
    Deepgram Aura TTS — fast, natural voice.
    English voice works best for code-switching.
    """
    logger.info(f"🎙️ TTS: Deepgram Aura-2 Thalia")
    return deepgram.TTS(model="aura-2-thalia-en")


def build_instructions(topic, native_lang_code):
    lang_name = LANGUAGE_NAMES.get(native_lang_code or "", None)
    logger.debug(f"build_instructions | lang_code={native_lang_code!r} -> lang_name={lang_name!r} | topic={topic!r}")

    topic_line = (
        f"Today's conversation topic is: {topic}. Keep the conversation around this topic."
        if topic else
        "You can talk about anything — ask what's on the user's mind."
    )

    if lang_name and lang_name != "English":
        lang_line = f"""
You are an English coach. The user speaks {lang_name} and is learning English.

YOUR SPEAKING STYLE:
- Speak in a natural mix of {lang_name} and English — this is called code-switching.
- Use {lang_name} for greetings, encouragement, filler words, and emotional warmth.
- Use English for explanations, corrections, and the main conversation.
- Example (Hindi): "Namaste! So aaj hum travel ke baare mein baat karenge. How are you doing today?"
- Example (Hindi): "Arre yaar, that was really good! Aur bolo, what do you love about travelling?"
- Example (Filipino): "Kamusta ka! So today we will practice English together. Okay lang ba?"
- Example (Tamil): "Vanakkam! Today we practice English. Neenga eppadi irukkeenga?"
- Keep it warm, fun and natural — like a bilingual friend.
- NEVER speak 100% in {lang_name} — always keep English as the main language.
- ONLY speak the actual words. No stage directions, no labels, no brackets.

WHEN USER SPEAKS IN {lang_name}:
- Understand what they said and respond naturally in the mixed style.
- Gently teach them the English version: "Oh nice! In English you can say: I am doing well."
- Ask them to try saying it in English.
- When they do, praise them and continue the conversation.

WHEN USER SPEAKS IN ENGLISH:
- Respond in mixed style naturally.
- Gently correct any grammar mistakes by using the correct form in your reply.
- Ask a follow-up question to keep them talking.
"""
        logger.info(f"Language mode: MIXED ({lang_name} + English)")
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
    def __init__(self, topic=None, native_lang=None):
        self._topic       = topic
        self._native_lang = native_lang
        super().__init__(instructions=build_instructions(topic, native_lang))

    async def on_enter(self):
        lang_name = LANGUAGE_NAMES.get(self._native_lang or "", None)

        if lang_name and lang_name != "English":
            greeting = (
                f"Greet the user with ONE short warm {lang_name} phrase "
                f"(like Namaste / Kamusta / Vanakkam / Hola), "
                f"then immediately switch to a mix of {lang_name} and English. "
                f"Tell them today you'll practice English together"
                f"{f' about {self._topic}' if self._topic else ''}. "
                f"Ask how they are doing. "
                f"Keep it warm, 2 sentences max. "
                f"Speak ONLY the words — no labels, no brackets."
            )
        else:
            greeting = (
                f"Greet the user warmly in English. "
                f"Tell them today you will practice English together"
                f"{f' about {self._topic}' if self._topic else ''}. "
                f"Ask how they are doing today."
            )

        logger.info(f"[on_enter] greeting: {greeting}")
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
    transcript  = []
    start_time  = datetime.utcnow()
    participant_identity = None
    user_email  = None
    user_id     = None
    topic       = None
    native_lang = None

    # ── Step 1: Read from job dispatch metadata FIRST ─────────────────────────
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
        logger.debug(f"[participant_meta] raw: {raw_meta}")
        try:
            meta        = json.loads(raw_meta)
            user_email  = meta.get("email")      or user_email
            user_id     = meta.get("userId")     or user_id
            topic       = meta.get("topic")      or topic
            native_lang = meta.get("nativeLang") or native_lang
            logger.info(f"[participant_meta] identity={participant_identity} | topic={topic!r} | nativeLang={native_lang!r}")
        except Exception as e:
            logger.error(f"Participant metadata parse error: {e}")

    # ── Step 2: Register listener BEFORE connecting ───────────────────────────
    meta_ready = asyncio.Event()

    def on_participant_connected(participant):
        _parse_meta(participant)
        meta_ready.set()

    ctx.room.on("participant_connected", on_participant_connected)

    # ── Step 3: Connect ───────────────────────────────────────────────────────
    await ctx.connect()

    # ── Step 4: Check if participant already in room ──────────────────────────
    for p in ctx.room.remote_participants.values():
        _parse_meta(p)
        meta_ready.set()
        break

    # ── Step 5: Wait up to 15s ────────────────────────────────────────────────
    if not meta_ready.is_set():
        logger.info("[entrypoint] Waiting for participant...")
        try:
            await asyncio.wait_for(meta_ready.wait(), timeout=15.0)
            logger.info(f"[entrypoint] Participant arrived | nativeLang={native_lang!r}")
        except asyncio.TimeoutError:
            logger.warning("[entrypoint] Timed out — using job metadata")

    ctx.room.off("participant_connected", on_participant_connected)
    logger.info(f"[entrypoint] Starting session | lang={native_lang!r} | topic={topic!r}")

    # ── Session — Deepgram Nova-3 STT + Deepgram TTS ──────────────────────────
    session = AgentSession(
        stt=get_deepgram_stt(native_lang),
        llm=openai.LLM(model="gpt-4o-mini"),
        tts=get_deepgram_tts(native_lang),
        vad=ctx.proc.userdata["vad"],
        allow_interruptions=True,
        min_endpointing_delay=0.3,
        max_endpointing_delay=0.8,
    )

    session.on("user_speech_started",    lambda _:  logger.info("[session] 🎤 user_speech_started"))
    session.on("agent_speech_started",   lambda _:  logger.info("[session] 🔊 agent_speech_started"))
    session.on("user_speech_committed",  lambda ev: logger.info(f"[session] user said: {getattr(ev, 'user_transcript', '')!r}"))
    session.on("agent_speech_committed", lambda ev: logger.info(f"[session] agent spoke"))

    @session.on("conversation_item_added")
    def on_item_added(event):
        try:
            item = event.item
            role = getattr(item, "role", None)
            text = getattr(item, "text_content", None) or getattr(item, "text", None)
            if role and text:
                entry = {"role": role, "text": text, "time": datetime.utcnow().isoformat()}
                transcript.append(entry)
                logger.info(f"{'User' if role == 'user' else 'Julian'}: {text}")
                if role == "user" and user_id:
                    asyncio.create_task(_save_utterance(user_id, ctx.room.name, entry))
        except Exception as e:
            logger.error(f"Error in on_item_added: {e}")

    async def _silence_prompt_loop():
        while True:
            await asyncio.sleep(8)
            try:
                if not transcript:
                    continue
                last = transcript[-1]
                if last["role"] != "assistant":
                    continue
                last_time = datetime.fromisoformat(last["time"])
                silence   = (datetime.utcnow() - last_time).total_seconds()
                if silence >= 20:
                    logger.info(f"Silence {silence:.0f}s — prompting")
                    await session.generate_reply(
                        instructions="The user has been quiet. Warmly encourage them in their native language to continue. Keep it to 1 short friendly sentence.",
                        allow_interruptions=True,
                    )
            except Exception as e:
                logger.warning(f"Silence loop error: {e}")

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
        logger.info(f"Sending | duration: {duration}s | lines: {len(transcript)}")

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
                logger.info(f"✅ Sent: {res.status_code}")
        except Exception as e:
            logger.error(f"Failed to send: {e}")

    ctx.add_shutdown_callback(on_shutdown)

    await session.start(
        agent=JulianAgent(topic=topic, native_lang=native_lang),
        room=ctx.room,
    )

    silence_task = asyncio.create_task(_silence_prompt_loop())
    disconnect_event = asyncio.Event()
    ctx.room.on("disconnected", lambda: disconnect_event.set())
    await disconnect_event.wait()

    silence_task.cancel()
    try:
        await silence_task
    except asyncio.CancelledError:
        pass


if __name__ == "__main__":
    cli.run_app(server)