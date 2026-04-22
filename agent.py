import logging
import os
import json
import httpx
import asyncio
from datetime import datetime
from livekit.agents import Agent, AgentServer, AgentSession, JobContext, JobProcess, cli
from livekit.agents.voice import AgentCallContext
from livekit.plugins import silero
from livekit.plugins import openai, deepgram

logger = logging.getLogger("julian-cloud-agent")
BACKEND_URL = os.environ.get("BACKEND_URL", "https://specker.ai")

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

def build_instructions(topic: str | None, native_lang_code: str | None) -> str:
    lang_name = LANGUAGE_NAMES.get(native_lang_code or "", None)

    topic_line = (
        f"Today's conversation topic is: **{topic}**. Start the conversation around this topic naturally."
        if topic else
        "You can talk about anything — ask what's on the user's mind."
    )

    if lang_name and lang_name != "English":
        lang_line = f"""
You MUST speak in a natural mix of {lang_name} and English (code-switching).
Rules:
- Use simple {lang_name} words and phrases naturally woven into English sentences.
- Greet in {lang_name} first, then switch to mixed speech.
- Use English for explanations, feedback, and corrections.
- Use {lang_name} for greetings, encouragement, filler phrases, and emotional warmth.
- Example style (Filipino): "Kamusta ka? So how was your day today? Okay lang ba?"
- Example style (Hindi): "Arre yaar, that was really good! Aur bolo, kya chal raha hai?"
- Keep it natural — don't translate every word, just mix freely like a bilingual friend.
- NEVER speak 100% in {lang_name} — always keep English as the base.
"""
    else:
        lang_line = "Speak naturally in English only."

    return f"""You are Julian, a warm and empathetic AI English coach on a phone call.
Keep responses short — 1 to 2 sentences. Be warm, friendly, and encouraging.
Ask follow-up questions to keep the conversation going.

{topic_line}

{lang_line}

Your goal is to help the user practice English confidently. Gently correct mistakes by
repeating what they said correctly in your response, without being preachy about it.

IMPORTANT: Always stay engaged. If the user goes silent, gently prompt them to continue."""


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
                f"Ask how they are doing today."
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

    # ── Read participant metadata at call start ────────────────────────────────
    participant_identity = None
    user_email           = None
    user_id              = None
    topic                = None
    native_lang          = None

    for p in ctx.room.remote_participants.values():
        participant_identity = p.identity
        try:
            meta        = json.loads(p.metadata or "{}")
            user_email  = meta.get("email")
            user_id     = meta.get("userId")
            topic       = meta.get("topic")
            native_lang = meta.get("nativeLang")
            logger.info(f"Participant: {participant_identity} | userId: {user_id} | topic: {topic} | lang: {native_lang}")
        except Exception as e:
            logger.error(f"Metadata parse error: {e}")
        break

    def on_participant_connected(participant):
        nonlocal participant_identity, user_email, user_id, topic, native_lang
        if participant_identity is None:
            participant_identity = participant.identity
            try:
                meta        = json.loads(participant.metadata or "{}")
                user_email  = meta.get("email")
                user_id     = meta.get("userId")
                topic       = meta.get("topic")
                native_lang = meta.get("nativeLang")
                logger.info(f"Joined: {participant_identity} | userId: {user_id} | topic: {topic} | lang: {native_lang}")
            except Exception as e:
                logger.error(f"Metadata parse error on join: {e}")

    ctx.room.on("participant_connected", on_participant_connected)

    # ── STT: keep_alive=True prevents Deepgram from closing after silence ──────
    # ── endpointing: how long silence before utterance ends (ms) ──────────────
    stt = deepgram.STT(
        model="nova-2",
        language="en",
        interim_results=True,       # send partial results — keeps connection alive
        smart_format=True,
        punctuate=True,
        filler_words=True,          # capture uh, um etc for fluency analysis
        endpointing=400,            # ms of silence before utterance ends (default 10 — too short)
        utterance_end_ms=2000,      # wait 2s of silence before finalizing utterance
        no_delay=True,
        keywords=[],
    )

    # ── VAD: increase sensitivity so it keeps listening longer ────────────────
    vad = ctx.proc.userdata["vad"]

    session = AgentSession(
        stt=stt,
        llm=openai.LLM(model="gpt-4o-mini"),
        tts=deepgram.TTS(model="aura-2-thalia-en"),
        vad=vad,
        # Keep the turn detection generous so user can take their time
        min_endpointing_delay=0.8,   # wait at least 800ms after speech stops
        max_endpointing_delay=6.0,   # but no more than 6s
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

    # ── Silence recovery: if user goes quiet for 30s, Julian prompts them ─────
    @session.on("user_speech_committed")
    def on_user_spoke(event):
        # Reset any pending silence prompt whenever the user speaks
        pass

    async def _silence_prompt_loop():
        """If user hasn't spoken in 35s after Julian's last reply, prompt them."""
        SILENCE_THRESHOLD = 35  # seconds
        last_check = datetime.utcnow()
        while True:
            await asyncio.sleep(10)
            try:
                elapsed = (datetime.utcnow() - last_check).total_seconds()
                # Check if last transcript entry was from Julian more than threshold ago
                if transcript and transcript[-1]["role"] == "assistant":
                    last_time = datetime.fromisoformat(transcript[-1]["time"])
                    silence   = (datetime.utcnow() - last_time).total_seconds()
                    if silence >= SILENCE_THRESHOLD:
                        logger.info(f"Silence detected ({silence:.0f}s) — prompting user")
                        await session.generate_reply(
                            instructions="The user has been quiet. Gently ask if they're still there, or prompt them to continue the conversation with a simple question.",
                            allow_interruptions=True,
                        )
                        last_check = datetime.utcnow()
            except Exception as e:
                logger.warning(f"Silence prompt error: {e}")

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

    # Start silence prompt loop as background task
    silence_task = asyncio.create_task(_silence_prompt_loop())

    disconnect_event = asyncio.Event()
    ctx.room.on("disconnected", lambda: disconnect_event.set())
    await disconnect_event.wait()

    # Cancel silence loop on disconnect
    silence_task.cancel()
    try:
        await silence_task
    except asyncio.CancelledError:
        pass


if __name__ == "__main__":
    cli.run_app(server)