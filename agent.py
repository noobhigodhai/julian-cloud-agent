import logging
import os
import json
import httpx
import asyncio
from datetime import datetime
from openai import AsyncOpenAI
from livekit.agents import Agent, AgentServer, AgentSession, JobContext, JobProcess, cli
from livekit.plugins import silero
from livekit.plugins import openai, google

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("julian-cloud-agent")
logger.setLevel(logging.DEBUG)

BACKEND_URL    = os.environ.get("BACKEND_URL", "https://specker.ai")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

logger.info("=== Julian Cloud Agent starting ===")
logger.info(f"BACKEND_URL     : {BACKEND_URL}")
logger.info(f"OPENAI_API_KEY  : {'set' if OPENAI_API_KEY else 'MISSING'}")

LANGUAGE_NAMES = {
    "tl": "Filipino/Tagalog", "hi": "Hindi",     "bn": "Bengali",
    "ta": "Tamil",            "te": "Telugu",     "mr": "Marathi",
    "gu": "Gujarati",         "kn": "Kannada",    "ml": "Malayalam",
    "pa": "Punjabi",          "ur": "Urdu",       "id": "Indonesian/Bahasa",
    "ms": "Malay",            "vi": "Vietnamese", "th": "Thai",
    "ar": "Arabic",           "es": "Spanish",    "pt": "Portuguese",
    "fr": "French",           "de": "German",     "zh": "Mandarin Chinese",
    "ja": "Japanese",         "ko": "Korean",     "sw": "Swahili",
    "en": "English",
}

def get_google_stt(native_lang: str | None):
    creds_json = os.environ.get("GOOGLE_CREDENTIALS_JSON", "")
    creds = json.loads(creds_json) if creds_json else None

    lang_map = {
        "hi": "hi-IN",
        "tl": "fil-PH",
        "ta": "ta-IN",
        "te": "te-IN",
        "bn": "bn-IN",
        "mr": "mr-IN",
        "gu": "gu-IN",
        "kn": "kn-IN",
        "ml": "ml-IN",
        "pa": "pa-IN",
        "ur": "ur-IN",
        "id": "id-ID",
        "ms": "ms-MY",
        "ko": "ko-KR",
        "ja": "ja-JP",
        "ar": "ar-XA",
        "es": "es-ES",
        "fr": "fr-FR",
        "de": "de-DE",
        "pt": "pt-BR",
        "zh": "cmn-Hans-CN",
        "vi": "vi-VN",
        "en": "en-US",
    }

    lang_code = lang_map.get(native_lang or "", "en-US")
    logger.info(f"🎤 STT: Google | language={lang_code}")

    return google.STT(
        languages=[lang_code],
        credentials_info=creds,
    )


def get_google_tts(native_lang: str | None):
    creds_json = os.environ.get("GOOGLE_CREDENTIALS_JSON", "")
    creds = json.loads(creds_json) if creds_json else None

    voice_map = {
        "hi": ("hi-IN-Chirp3-HD-Aoede",  "hi-IN"),
        "tl": ("fil-PH-Chirp3-HD-Aoede", "fil-PH"),
        "ta": ("ta-IN-Chirp3-HD-Aoede",  "ta-IN"),
        "te": ("te-IN-Chirp3-HD-Aoede",  "te-IN"),
        "bn": ("bn-IN-Chirp3-HD-Aoede",  "bn-IN"),
        "mr": ("mr-IN-Chirp3-HD-Aoede",  "mr-IN"),
        "gu": ("gu-IN-Chirp3-HD-Aoede",  "gu-IN"),
        "kn": ("kn-IN-Chirp3-HD-Aoede",  "kn-IN"),
        "ml": ("ml-IN-Chirp3-HD-Aoede",  "ml-IN"),
        "pa": ("pa-IN-Chirp3-HD-Aoede",  "pa-IN"),
        "ur": ("ur-IN-Chirp3-HD-Aoede",  "ur-IN"),
        "id": ("id-ID-Chirp3-HD-Aoede",  "id-ID"),
        "ms": ("ms-MY-Chirp3-HD-Aoede",  "ms-MY"),
        "ko": ("ko-KR-Chirp3-HD-Aoede",  "ko-KR"),
        "ja": ("ja-JP-Chirp3-HD-Aoede",  "ja-JP"),
        "ar": ("ar-XA-Chirp3-HD-Aoede",  "ar-XA"),
        "es": ("es-ES-Chirp3-HD-Aoede",  "es-ES"),
        "fr": ("fr-FR-Chirp3-HD-Aoede",  "fr-FR"),
        "de": ("de-DE-Chirp3-HD-Aoede",  "de-DE"),
        "pt": ("pt-BR-Chirp3-HD-Aoede",  "pt-BR"),
        "zh": ("cmn-CN-Chirp3-HD-Aoede", "cmn-CN"),
        "vi": ("vi-VN-Chirp3-HD-Aoede",  "vi-VN"),
        "en": ("en-US-Chirp3-HD-Aoede",  "en-US"),
    }

    voice_name, language = voice_map.get(native_lang or "", ("en-US-Chirp3-HD-Aoede", "en-US"))
    logger.info(f"🎙️ TTS voice: {voice_name} | language: {language}")

    try:
        return google.TTS(
            voice_name=voice_name,
            language=language,
            gender="female",
            credentials_info=creds,
        )
    except Exception as e:
        logger.warning(f"⚠️ Voice {voice_name} failed ({e}) — fallback to en-US")
        return google.TTS(
            voice_name="en-US-Chirp3-HD-Aoede",
            language="en-US",
            gender="female",
            credentials_info=creds,
        )


async def analyze_with_gpt(transcript: list, duration: int) -> dict:
    try:
        client = AsyncOpenAI(api_key=OPENAI_API_KEY)
        transcript_text = "\n".join([
            f"{'User' if m['role'] == 'user' else 'Julian'}: {m['text']}"
            for m in transcript
        ])
        prompt = f"""Analyze this English language learning conversation and return a detailed JSON report.

TRANSCRIPT:
{transcript_text}

DURATION: {duration // 60} minutes {duration % 60} seconds

Return ONLY valid JSON with no markdown or explanation:
{{
  "overall_score": <0-100>,
  "summary": "<2-3 sentence summary>",
  "grammar": {{
    "score": <0-100>,
    "mistakes": [{{"original": "", "corrected": "", "explanation": ""}}],
    "feedback": "<1-2 sentences>"
  }},
  "vocabulary": {{
    "score": <0-100>,
    "advanced_words_used": [],
    "suggestions": [],
    "feedback": "<1-2 sentences>"
  }},
  "fluency": {{
    "score": <0-100>,
    "filler_words_detected": [],
    "pace": "<too fast | good | too slow>",
    "feedback": "<1-2 sentences>"
  }},
  "confidence": {{
    "score": <0-100>,
    "feedback": "<1-2 sentences>"
  }},
  "pronunciation_tips": [{{"word": "", "tip": ""}}],
  "strengths": [],
  "areas_to_improve": [],
  "next_steps": []
}}"""
        response = await client.chat.completions.create(
            model="gpt-4o",
            temperature=0.3,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.choices[0].message.content.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        return json.loads(raw.strip())
    except Exception as e:
        logger.error(f"GPT analysis error: {e}")
        return {}


def build_instructions(topic, native_lang_code):
    lang_name = LANGUAGE_NAMES.get(native_lang_code or "", None)
    logger.debug(f"build_instructions | lang_code={native_lang_code!r} → lang_name={lang_name!r} | topic={topic!r}")

    topic_line = (
        f"Today's conversation topic is: {topic}. Keep the conversation around this topic."
        if topic else
        "You can talk about anything — ask what's on the user's mind."
    )

    if lang_name and lang_name != "English":
        lang_line = f"""
You are an English coach. The user speaks {lang_name} and is learning English.

YOUR ROLE:
- You are a fun, warm, encouraging English coach on a phone call.
- Your job is to help the user PRACTICE speaking English.
- You speak in English always. Use {lang_name} only for tiny warm filler words like
  "yaar", "arre", "acha", "sahi hai", "Kamusta" — never full {lang_name} sentences.

WHEN USER SPEAKS IN {lang_name}:
- Step 1: Acknowledge warmly what they said in English.
- Step 2: Teach them how to say it in English naturally.
- Step 3: Ask them to retry and say it in English.
- Step 4: When they try, praise them and continue the conversation.

EXAMPLES:
User: "main theek hoon"
You: "Oh nice, so you're doing well! In English you'd say: I am doing fine. Now you try saying that!"

User: "mujhe travel bahut pasand hai"
You: "Acha! You love travelling! In English say: I love to travel. Go ahead, give it a try!"

User: "I love to travel"
You: "Yes! Perfect yaar! So where would you love to travel to?"

User: "kamusta ka"
You: "Oh you asked how I am! In English that's: How are you? Now you try saying it!"

WHEN USER SPEAKS IN ENGLISH:
- Celebrate their effort warmly.
- Gently correct any mistakes by naturally using the correct version in your reply.
- Ask a follow-up question to keep them talking in English.

RULES:
- Keep each response to 2 to 3 sentences max.
- Always end with either a retry request OR a follow-up question in English.
- Never lecture. Keep it fun and encouraging like a friend.
- ONLY speak the words. No stage directions, no brackets, no labels.
"""
        logger.info(f"Language mode: COACH ({lang_name} → English practice)")
    else:
        lang_line = """
Speak naturally in English only.
Gently correct any mistakes by naturally using the correct version in your reply.
Keep responses short — 1 to 2 sentences. Always ask a follow-up question.
"""
        logger.info("Language mode: English only")

    return f"""You are Julian, a warm, patient, encouraging AI English coach on a phone call.
Be friendly and fun — like a supportive bilingual friend.

{topic_line}

{lang_line}

LISTENING: Always wait for the user to fully finish before responding.
Never interrupt. If the user pauses briefly, wait — they may still be thinking.
If user is quiet for over 20 seconds, gently check in."""


class JulianAgent(Agent):
    def __init__(self, topic=None, native_lang=None):
        self._topic       = topic
        self._native_lang = native_lang
        super().__init__(instructions=build_instructions(topic, native_lang))

    async def on_enter(self):
        lang_name = LANGUAGE_NAMES.get(self._native_lang or "", None)

        if lang_name and lang_name != "English":
            greeting = (
                f"Greet the user with ONE short warm {lang_name} phrase only "
                f"(like Namaste / Kamusta / Hola), then immediately switch to English. "
                f"In English tell them today you'll practice speaking English together"
                f"{f' about {self._topic}' if self._topic else ''}. "
                f"Ask how they are doing in English. "
                f"Keep it to 2 sentences max. "
                f"Speak ONLY the words — no labels, no brackets."
            )
        else:
            greeting = (
                f"Greet the user warmly in English. "
                f"Tell them today you'll practice English together"
                f"{f' about {self._topic}' if self._topic else ''}. "
                f"Ask how they are doing today."
            )

        logger.info(f"[on_enter] greeting instruction: {greeting}")
        await self.session.generate_reply(instructions=greeting, allow_interruptions=True)


server = AgentServer()

def prewarm(proc: JobProcess):
    proc.userdata["vad"] = silero.VAD.load()

server.setup_fnc = prewarm

@server.rtc_session(agent_name="julian-cloud")
async def entrypoint(ctx: JobContext):
    transcript = []
    start_time = datetime.utcnow()
    participant_identity = None
    user_email  = None
    user_id     = None
    topic       = None
    native_lang = None

    # ── Step 1: Read from job dispatch metadata FIRST (available immediately) ──
    try:
        job_meta = json.loads(ctx.job.metadata or "{}")
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
            meta = json.loads(raw_meta)
            # Only override if values are still missing
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

    # ── Step 3: Connect to room ───────────────────────────────────────────────
    await ctx.connect()

    # ── Step 4: Check if participant already in room ──────────────────────────
    for p in ctx.room.remote_participants.values():
        _parse_meta(p)
        meta_ready.set()
        break

    # ── Step 5: Wait up to 15s for participant if not already joined ──────────
    if not meta_ready.is_set():
        logger.info("[entrypoint] Waiting for participant to join...")
        try:
            await asyncio.wait_for(meta_ready.wait(), timeout=15.0)
            logger.info(f"[entrypoint] Participant arrived | nativeLang={native_lang!r}")
        except asyncio.TimeoutError:
            logger.warning("[entrypoint] Participant join timed out — using job metadata")

    ctx.room.off("participant_connected", on_participant_connected)
    logger.info(f"[entrypoint] Starting session | lang={native_lang!r} | topic={topic!r}")

    # ── Session — fully Google STT + TTS ──────────────────────────────────────
    session = AgentSession(
        stt=get_google_stt(native_lang),
        llm=openai.LLM(model="gpt-4o-mini"),
        tts=get_google_tts(native_lang),
        vad=ctx.proc.userdata["vad"],
    )

    session.on("user_speech_started",    lambda _:  logger.debug("[session] user_speech_started"))
    session.on("agent_speech_started",   lambda _:  logger.debug("[session] agent_speech_started"))
    session.on("user_speech_committed",  lambda ev: logger.debug(f"[session] user_speech_committed: {getattr(ev, 'user_transcript', '')!r}"))
    session.on("agent_speech_committed", lambda ev: logger.debug(f"[session] agent_speech_committed: {getattr(ev, 'agent_transcript', '')!r}"))

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
                if not transcript or transcript[-1]["role"] != "assistant":
                    continue
                last_time = datetime.fromisoformat(transcript[-1]["time"])
                silence = (datetime.utcnow() - last_time).total_seconds()
                if silence >= 25:
                    logger.info(f"Silence {silence:.0f}s — prompting")
                    await session.generate_reply(
                        instructions="User has been quiet. Warmly ask if they're still there with a simple friendly question.",
                        allow_interruptions=True,
                    )
            except Exception as e:
                logger.warning(f"Silence loop: {e}")

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
            return
        duration = int((datetime.utcnow() - start_time).total_seconds())

        logger.info("Running GPT analysis...")
        gpt_result = await analyze_with_gpt(transcript, duration)
        if gpt_result:
            logger.info(f"GPT done. Score: {gpt_result.get('overall_score')}")
        else:
            logger.warning("GPT analysis returned empty")

        payload = {
            "roomName":            ctx.room.name,
            "participantIdentity": participant_identity,
            "userEmail":           user_email,
            "userId":              user_id,
            "duration":            duration,
            "transcript":          transcript,
            "topic":               topic,
            "nativeLang":          native_lang,
            "analysis":            gpt_result,
            "timestamp":           datetime.utcnow().isoformat(),
        }
        try:
            async with httpx.AsyncClient(timeout=30) as client:
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