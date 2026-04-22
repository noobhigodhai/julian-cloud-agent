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
    Chirp3-HD voices with native language codes.
    Only Chirp3-HD supports streaming synthesis in LiveKit.
    Native language code (hi-IN, ta-IN etc.) gives the correct accent.
    """
    creds_json = os.environ.get("GOOGLE_CREDENTIALS_JSON", "")
    creds = json.loads(creds_json) if creds_json else None

    voice_map = {
        "hi": ("hi-IN-Chirp3-HD-Aoede",  "hi-IN"),   # Hindi ✅
        "tl": ("fil-PH-Chirp3-HD-Aoede", "fil-PH"),  # Filipino ✅
        "ta": ("ta-IN-Chirp3-HD-Aoede",  "ta-IN"),   # Tamil ✅
        "te": ("te-IN-Chirp3-HD-Aoede",  "te-IN"),   # Telugu ✅
        "bn": ("bn-IN-Chirp3-HD-Aoede",  "bn-IN"),   # Bengali ✅
        "mr": ("mr-IN-Chirp3-HD-Aoede",  "mr-IN"),   # Marathi ✅
        "gu": ("gu-IN-Chirp3-HD-Aoede",  "gu-IN"),   # Gujarati ✅
        "kn": ("kn-IN-Chirp3-HD-Aoede",  "kn-IN"),   # Kannada ✅
        "ml": ("ml-IN-Chirp3-HD-Aoede",  "ml-IN"),   # Malayalam ✅
        "pa": ("pa-IN-Chirp3-HD-Aoede",  "pa-IN"),   # Punjabi ✅
        "ur": ("ur-IN-Chirp3-HD-Aoede",  "ur-IN"),   # Urdu ✅
        "id": ("id-ID-Chirp3-HD-Aoede",  "id-ID"),   # Indonesian ✅
        "ms": ("ms-MY-Chirp3-HD-Aoede",  "ms-MY"),   # Malay ✅
        "ko": ("ko-KR-Chirp3-HD-Aoede",  "ko-KR"),   # Korean ✅
        "ja": ("ja-JP-Chirp3-HD-Aoede",  "ja-JP"),   # Japanese ✅
        "ar": ("ar-XA-Chirp3-HD-Aoede",  "ar-XA"),   # Arabic ✅
        "es": ("es-ES-Chirp3-HD-Aoede",  "es-ES"),   # Spanish ✅
        "fr": ("fr-FR-Chirp3-HD-Aoede",  "fr-FR"),   # French ✅
        "de": ("de-DE-Chirp3-HD-Aoede",  "de-DE"),   # German ✅
        "pt": ("pt-BR-Chirp3-HD-Aoede",  "pt-BR"),   # Portuguese ✅
        "zh": ("cmn-CN-Chirp3-HD-Aoede", "cmn-CN"),  # Mandarin ✅
        "vi": ("vi-VN-Chirp3-HD-Aoede",  "vi-VN"),   # Vietnamese ✅
        "en": ("en-US-Chirp3-HD-Aoede",  "en-US"),   # English only
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
- IMPORTANT: Write ONLY the words to be spoken. No stage directions, no brackets, no labels.
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

    # ── Register listener BEFORE connecting ───────────────────────────────────
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

    ctx.room.on("participant_connected", on_participant_connected)

    # ── Connect to room ───────────────────────────────────────────────────────
    await ctx.connect()

    # ── Check if participant already in room ──────────────────────────────────
    for p in ctx.room.remote_participants.values():
        on_participant_connected(p)
        break

    # ── Wait up to 15 seconds for participant ─────────────────────────────────
    if not participant_joined.is_set():
        try:
            await asyncio.wait_for(participant_joined.wait(), timeout=15.0)
        except asyncio.TimeoutError:
            logger.warning("⚠️ Timed out waiting for participant — using defaults")

    logger.info(f"🎯 Starting agent | topic: {topic} | lang: {native_lang}")

    # ── Session ───────────────────────────────────────────────────────────────
    session = AgentSession(
        stt=deepgram.STT(model="nova-2", language="en"),
        llm=openai.LLM(model="gpt-4o-mini"),
        tts=get_google_tts(native_lang),
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