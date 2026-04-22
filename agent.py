import logging
import os
import json
import httpx
import asyncio
from datetime import datetime
from livekit.agents import Agent, AgentServer, AgentSession, JobContext, JobProcess, cli
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

def build_instructions(topic, native_lang_code):
    lang_name = LANGUAGE_NAMES.get(native_lang_code or "", None)
    topic_line = (
        f"Today's conversation topic is: {topic}. Start the conversation around this topic naturally."
        if topic else "You can talk about anything — ask what's on the user's mind."
    )
    if lang_name and lang_name != "English":
        lang_line = f"""You MUST speak in a natural mix of {lang_name} and English (code-switching).
- Greet in {lang_name} first, then switch to mixed speech.
- Use English for explanations and corrections, {lang_name} for warmth and encouragement.
- Example (Filipino): "Kamusta ka? So how was your day today? Okay lang ba?"
- Example (Hindi): "Arre yaar, that was really good! Aur bolo, kya chal raha hai?"
- NEVER speak 100% in {lang_name} — always keep English as the base."""
    else:
        lang_line = "Speak naturally in English only."

    return f"""You are Julian, a warm, patient, encouraging AI English coach on a phone call.

STYLE: Keep each response to 1-2 sentences. Always end with a follow-up question.
Be genuinely curious. Respond directly to what the user just said.
If user makes a grammar mistake, use the correct form naturally in your reply without pointing it out.

{topic_line}

{lang_line}

LISTENING: Always wait for the user to fully finish before responding.
Never interrupt. If the user pauses briefly, wait — they may still be thinking.
Stay fully engaged. If user is quiet over 20 seconds, gently check in."""


class JulianAgent(Agent):
    def __init__(self, topic=None, native_lang=None):
        self._topic       = topic
        self._native_lang = native_lang
        super().__init__(instructions=build_instructions(topic, native_lang))

    async def on_enter(self):
        lang_name = LANGUAGE_NAMES.get(self._native_lang or "", None)
        if lang_name and lang_name != "English":
            greeting = (f"Greet warmly in {lang_name} (one short phrase), then switch to mixed {lang_name} and English. Ask how they are doing today.")
        else:
            greeting = "Greet the user warmly and ask how they are doing today."
        if self._topic:
            greeting += f" Then naturally bring up today's topic: {self._topic}."
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
    user_email = None
    user_id = None
    topic = None
    native_lang = None

    for p in ctx.room.remote_participants.values():
        participant_identity = p.identity
        try:
            meta = json.loads(p.metadata or "{}")
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
                meta = json.loads(participant.metadata or "{}")
                user_email  = meta.get("email")
                user_id     = meta.get("userId")
                topic       = meta.get("topic")
                native_lang = meta.get("nativeLang")
                logger.info(f"Joined: {participant_identity} | userId: {user_id}")
            except Exception as e:
                logger.error(f"Metadata parse error: {e}")

    ctx.room.on("participant_connected", on_participant_connected)

    # Use only guaranteed-valid STT params
    stt = deepgram.STT(
        model="nova-2",
        language="en",
        interim_results=True,
        smart_format=True,
        punctuate=True,
        filler_words=True,
    )

    session = AgentSession(
        stt=stt,
        llm=openai.LLM(model="gpt-4o-mini"),
        tts=deepgram.TTS(model="aura-2-thalia-en"),
        vad=ctx.proc.userdata["vad"],
    )

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
                await client.post(f"{BACKEND_URL}/api/live-transcript",
                    json={"userId": uid, "roomName": room_name, "entry": entry},
                    headers={"Content-Type": "application/json"})
        except Exception as e:
            logger.warning(f"Live transcript save failed: {e}")

    async def on_shutdown():
        logger.info(f"Shutdown | Lines: {len(transcript)}")
        if not transcript:
            return
        duration = int((datetime.utcnow() - start_time).total_seconds())
        payload = {
            "roomName": ctx.room.name, "participantIdentity": participant_identity,
            "userEmail": user_email, "userId": user_id, "duration": duration,
            "transcript": transcript, "topic": topic, "nativeLang": native_lang,
            "timestamp": datetime.utcnow().isoformat(),
        }
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                res = await client.post(f"{BACKEND_URL}/api/call-report",
                    json=payload, headers={"Content-Type": "application/json"})
                logger.info(f"✅ Sent: {res.status_code}")
        except Exception as e:
            logger.error(f"Failed to send: {e}")

    ctx.add_shutdown_callback(on_shutdown)

    await session.start(agent=JulianAgent(topic=topic, native_lang=native_lang), room=ctx.room)

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