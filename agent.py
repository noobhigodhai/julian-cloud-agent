import logging
import os
import json
import httpx
import asyncio
from datetime import datetime
from openai import AsyncOpenAI
from livekit.agents import Agent, AgentServer, AgentSession, JobContext, JobProcess, cli
from livekit.plugins import silero
from livekit.plugins import openai, deepgram

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

def build_instructions(topic, native_lang_code):
    lang_name = LANGUAGE_NAMES.get(native_lang_code or "", None)
    logger.debug(f"build_instructions | lang_code={native_lang_code!r} → lang_name={lang_name!r} | topic={topic!r}")
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
        logger.info(f"Language mode: MIXED ({lang_name} + English)")
    else:
        lang_line = "Speak naturally in English only."
        logger.info("Language mode: English only")

    return f"""You are Julian, a warm, patient, encouraging AI English coach on a phone call.

STYLE: Keep each response to 1-2 sentences. Always end with a follow-up question.
Be genuinely curious. Respond directly to what the user just said.
If user makes a grammar mistake, use the correct form naturally in your reply without pointing it out.

{topic_line}

{lang_line}

LISTENING: Always wait for the user to fully finish before responding.
Never interrupt. If the user pauses briefly, wait — they may still be thinking.
Stay fully engaged. If user is quiet over 20 seconds, gently check in."""


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
    user_email = None
    user_id = None
    topic = None
    native_lang = None

    logger.info(f"[entrypoint] room={ctx.room.name} | remote_participants={len(ctx.room.remote_participants)}")

    for p in ctx.room.remote_participants.values():
        participant_identity = p.identity
        raw_meta = p.metadata or "{}"
        logger.debug(f"[entrypoint] raw metadata: {raw_meta}")
        try:
            meta = json.loads(raw_meta)
            user_email  = meta.get("email")
            user_id     = meta.get("userId")
            topic       = meta.get("topic")
            native_lang = meta.get("nativeLang")
            logger.info(f"[entrypoint] Participant: {participant_identity} | userId={user_id} | email={user_email} | topic={topic!r} | nativeLang={native_lang!r}")
        except Exception as e:
            logger.error(f"Metadata parse error: {e}")
        break

    if not participant_identity:
        logger.warning("[entrypoint] No remote participants yet — waiting for join event")

    def on_participant_connected(participant):
        nonlocal participant_identity, user_email, user_id, topic, native_lang
        if participant_identity is None:
            participant_identity = participant.identity
            raw_meta = participant.metadata or "{}"
            logger.debug(f"[on_participant_connected] raw metadata: {raw_meta}")
            try:
                meta = json.loads(raw_meta)
                user_email  = meta.get("email")
                user_id     = meta.get("userId")
                topic       = meta.get("topic")
                native_lang = meta.get("nativeLang")
                logger.info(f"[on_participant_connected] identity={participant_identity} | userId={user_id} | nativeLang={native_lang!r}")
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

    session.on("user_speech_started",   lambda _:  logger.debug("[session] user_speech_started"))
    session.on("agent_speech_started",  lambda _:  logger.debug("[session] agent_speech_started"))
    session.on("user_speech_committed", lambda ev: logger.debug(f"[session] user_speech_committed: {getattr(ev, 'user_transcript', '')!r}"))
    session.on("agent_speech_committed",lambda ev: logger.debug(f"[session] agent_speech_committed: {getattr(ev, 'agent_transcript', '')!r}"))

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

        logger.info("Running GPT grammar/sentence analysis...")
        gpt_result = await analyze_with_gpt(transcript, duration)
        if gpt_result:
            logger.info(f"GPT analysis done. Overall score: {gpt_result.get('overall_score')}")
        else:
            logger.warning("GPT analysis returned empty result")

        payload = {
            "roomName": ctx.room.name, "participantIdentity": participant_identity,
            "userEmail": user_email, "userId": user_id, "duration": duration,
            "transcript": transcript, "topic": topic, "nativeLang": native_lang,
            "analysis": gpt_result,
            "timestamp": datetime.utcnow().isoformat(),
        }
        try:
            async with httpx.AsyncClient(timeout=30) as client:
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