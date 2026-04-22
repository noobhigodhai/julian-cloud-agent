import logging
import os
import json
import httpx
import asyncio
from datetime import datetime
from livekit.agents import Agent, AgentServer, AgentSession, JobContext, JobProcess, cli
from livekit.plugins import silero
from livekit.plugins import openai, google

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

def get_google_stt(native_lang: str | None):
    """
    Single language STT per user based on their native language.
    Single language avoids Google defaulting to English when multiple are passed.
    Native language STT handles English words fine due to code-switching support.
    """
    creds_json = os.environ.get("GOOGLE_CREDENTIALS_JSON", "")
    creds = json.loads(creds_json) if creds_json else None

    lang_map = {
        "hi": "hi-IN",     # Hindi
        "tl": "fil-PH",    # Filipino
        "ta": "ta-IN",     # Tamil
        "te": "te-IN",     # Telugu
        "bn": "bn-IN",     # Bengali
        "mr": "mr-IN",     # Marathi
        "gu": "gu-IN",     # Gujarati
        "kn": "kn-IN",     # Kannada
        "ml": "ml-IN",     # Malayalam
        "pa": "pa-IN",     # Punjabi
        "ur": "ur-IN",     # Urdu
        "id": "id-ID",     # Indonesian
        "ms": "ms-MY",     # Malay
        "ko": "ko-KR",     # Korean
        "ja": "ja-JP",     # Japanese
        "ar": "ar-XA",     # Arabic
        "es": "es-ES",     # Spanish
        "fr": "fr-FR",     # French
        "de": "de-DE",     # German
        "pt": "pt-BR",     # Portuguese
        "zh": "cmn-Hans-CN", # Mandarin
        "vi": "vi-VN",     # Vietnamese
        "en": "en-US",     # English
    }

    lang_code = lang_map.get(native_lang or "", "en-US")
    logger.info(f"🎤 STT: Google | language={lang_code}")

    return google.STT(
        languages=[lang_code],
        credentials_info=creds,
    )


def get_google_tts(native_lang: str | None):
    """
    Chirp3-HD voices with native language codes.
    Only Chirp3-HD supports streaming synthesis in LiveKit.
    """
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


def build_instructions(topic: str | None, native_lang_code: str | None) -> str:
    lang_name = LANGUAGE_NAMES.get(native_lang_code or "", None)

    topic_line = (
        f"Today's conversation topic is: **{topic}**. Keep the conversation around this topic."
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
- Step 4: Wait for them to try. When they do, praise them and continue.

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
    else:
        lang_line = """
Speak naturally in English only.
Gently correct any mistakes by naturally using the correct version in your reply.
Keep responses short — 1 to 2 sentences. Always ask a follow-up question.
"""

    return f"""You are Julian, a warm and empathetic AI English coach on a phone call.
Be friendly, encouraging, and fun — like a supportive bilingual friend.

{topic_line}

{lang_line}"""


class JulianAgent(Agent):
    def __init__(self, topic: str | None = None, native_lang: str | None = None):
        self._topic       = topic
        self._native_lang = native_lang
        super().__init__(instructions=build_instructions(topic, native_lang))

    async def on_enter(self):
        lang_name = LANGUAGE_NAMES.get(self._native_lang or "", None)

        if lang_name and lang_name != "English":
            greeting = (
                f"Greet the user with ONE short warm {lang_name} phrase only "
                f"(like Namaste / Kamusta / Hola), then immediately switch to English. "
                f"In English, tell them today you'll practice speaking English together"
                f"{f' about {self._topic}' if self._topic else ''}. "
                f"Ask them in English: how are you doing today? "
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

    await ctx.connect()

    for p in ctx.room.remote_participants.values():
        on_participant_connected(p)
        break

    if not participant_joined.is_set():
        try:
            await asyncio.wait_for(participant_joined.wait(), timeout=15.0)
        except asyncio.TimeoutError:
            logger.warning("⚠️ Timed out waiting for participant — using defaults")

    logger.info(f"🎯 Starting agent | topic: {topic} | lang: {native_lang}")

    session = AgentSession(
        stt=get_google_stt(native_lang),
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