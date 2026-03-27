# import logging
# import os
# from livekit.agents import Agent, AgentServer, AgentSession, JobContext, JobProcess, cli
# from livekit.plugins import silero
# from livekit.plugins import openai, deepgram

# logger = logging.getLogger("julian-cloud-agent")

# # On LiveKit Cloud, env vars are injected as secrets — no .env file needed
# class JulianAgent(Agent):
#     def __init__(self) -> None:
#         super().__init__(
#             instructions="""You are Julian, a warm and empathetic AI friend on a phone call.
# Keep responses short — 1 to 2 sentences. Be warm and natural. English only.
# Ask follow-up questions to keep the conversation going.""",
#         )

#     async def on_enter(self):
#         await self.session.generate_reply(
#             instructions="Greet the user warmly and ask how they are doing today.",
#             allow_interruptions=True,
#         )

# server = AgentServer()

# def prewarm(proc: JobProcess):
#     proc.userdata["vad"] = silero.VAD.load()

# server.setup_fnc = prewarm

# @server.rtc_session(agent_name="julian-cloud")
# async def entrypoint(ctx: JobContext):
#     session = AgentSession(
#         stt=deepgram.STT(model="nova-2", language="en"),
#         llm=openai.LLM(model="gpt-4o-mini"),
#         tts=deepgram.TTS(model="aura-2-thalia-en"),
#         vad=ctx.proc.userdata["vad"],
#     )
#     await session.start(
#         agent=JulianAgent(),
#         room=ctx.room,
#     )

# if __name__ == "__main__":
#     cli.run_app(server)


# import logging
# import os
# import json
# import httpx
# import asyncio
# from datetime import datetime
# from livekit.agents import Agent, AgentServer, AgentSession, JobContext, JobProcess, cli
# from livekit.plugins import silero
# from livekit.plugins import openai, deepgram
# from livekit import api

# logger = logging.getLogger("julian-cloud-agent")

# BACKEND_URL    = os.environ.get("BACKEND_URL", "https://specker.ai")
# OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
# HUME_API_KEY   = os.environ.get("HUME_API_KEY")
# LIVEKIT_URL         = os.environ.get("LIVEKIT_URL")
# LIVEKIT_API_KEY     = os.environ.get("LIVEKIT_API_KEY")
# LIVEKIT_API_SECRET  = os.environ.get("LIVEKIT_API_SECRET")

# class JulianAgent(Agent):
#     def __init__(self) -> None:
#         super().__init__(
#             instructions="""You are Julian, a warm and empathetic AI friend on a phone call.
# Keep responses short — 1 to 2 sentences. Be warm and natural. English only.
# Ask follow-up questions to keep the conversation going.""",
#         )

#     async def on_enter(self):
#         await self.session.generate_reply(
#             instructions="Greet the user warmly and ask how they are doing today.",
#             allow_interruptions=True,
#         )

# server = AgentServer()

# def prewarm(proc: JobProcess):
#     proc.userdata["vad"] = silero.VAD.load()

# server.setup_fnc = prewarm

# @server.rtc_session(agent_name="julian-cloud")
# async def entrypoint(ctx: JobContext):
#     transcript = []
#     start_time = datetime.utcnow()

#     session = AgentSession(
#         stt=deepgram.STT(model="nova-2", language="en"),
#         llm=openai.LLM(model="gpt-4o-mini"),
#         tts=deepgram.TTS(model="aura-2-thalia-en"),
#         vad=ctx.proc.userdata["vad"],
#     )

#     # Collect transcript during call
#     @session.on("user_speech_committed")
#     def on_user(event):
#         transcript.append({
#             "role": "user",
#             "text": event.transcript,
#             "time": datetime.utcnow().isoformat(),
#         })
#         logger.info(f"User: {event.transcript}")

#     @session.on("agent_speech_committed")
#     def on_agent(event):
#         transcript.append({
#             "role": "assistant",
#             "text": event.transcript,
#             "time": datetime.utcnow().isoformat(),
#         })
#         logger.info(f"Julian: {event.transcript}")

#     await session.start(
#         agent=JulianAgent(),
#         room=ctx.room,
#     )

#     # Wait for call to end
#     disconnect_event = asyncio.Event()
#     ctx.room.on("disconnected", lambda: disconnect_event.set())
#     await disconnect_event.wait()

#     duration = int((datetime.utcnow() - start_time).total_seconds())
#     logger.info(f"Call ended. Duration: {duration}s | Lines: {len(transcript)}")

#     if len(transcript) == 0:
#         return

#     # Get user identity + email from participant metadata
#     participant_identity = None
#     user_email = None
#     for p in ctx.room.remote_participants.values():
#         participant_identity = p.identity
#         try:
#             meta = json.loads(p.metadata or "{}")
#             user_email = meta.get("email")
#         except Exception:
#             pass
#         break

#     # Get recording URL from S3 egress
#     recording_url = await get_recording_url(ctx)

#     # Run GPT + Hume in parallel
#     logger.info("Starting parallel analysis: GPT-4o + Hume AI")
#     gpt_task  = asyncio.create_task(analyze_with_gpt(transcript, duration))
#     hume_task = asyncio.create_task(analyze_with_hume(recording_url, transcript))

#     gpt_result, hume_result = await asyncio.gather(gpt_task, hume_task, return_exceptions=True)

#     if isinstance(gpt_result,  Exception):
#         logger.error(f"GPT failed: {gpt_result}")
#         gpt_result = {}
#     if isinstance(hume_result, Exception):
#         logger.error(f"Hume failed: {hume_result}")
#         hume_result = {}

#     # Send combined report to backend
#     payload = {
#         "roomName":            ctx.room.name,
#         "participantIdentity": participant_identity,
#         "userEmail":           user_email,
#         "duration":            duration,
#         "transcript":          transcript,
#         "analysis": {
#             **gpt_result,
#             "vocal_emotion": hume_result,
#         },
#         "timestamp": datetime.utcnow().isoformat(),
#     }

#     try:
#         async with httpx.AsyncClient(timeout=30) as client:
#             res = await client.post(
#                 f"{BACKEND_URL}/api/call-report",
#                 json=payload,
#                 headers={"Content-Type": "application/json"},
#             )
#             logger.info(f"Report sent: {res.status_code}")
#     except Exception as e:
#         logger.error(f"Failed to send report: {e}")


# async def get_recording_url(ctx) -> str | None:
#     """Wait for egress to finalize then return the S3 recording URL."""
#     try:
#         logger.info("Waiting 6s for egress to finalize...")
#         await asyncio.sleep(6)
#         lk = api.LiveKitAPI(
#             url=LIVEKIT_URL,
#             api_key=LIVEKIT_API_KEY,
#             api_secret=LIVEKIT_API_SECRET,
#         )
#         egresses = await lk.egress.list_egress(
#             api.ListEgressRequest(room_name=ctx.room.name)
#         )
#         for e in egresses.items:
#             if hasattr(e, "file") and e.file and e.file.location:
#                 logger.info(f"Recording URL: {e.file.location}")
#                 return e.file.location
#     except Exception as ex:
#         logger.warning(f"Could not get recording URL: {ex}")
#     return None


# async def analyze_with_gpt(transcript: list, duration: int) -> dict:
#     """GPT-4o analyzes transcript for grammar, vocabulary, fluency."""
#     try:
#         from openai import AsyncOpenAI
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
#         logger.error(f"GPT error: {e}")
#         return {}


# async def analyze_with_hume(audio_url: str | None, transcript: list) -> dict:
#     """
#     If audio URL available: use Hume prosody model (real vocal analysis).
#     Otherwise: fallback to Hume language model (text-based emotion scoring).
#     """
#     if not HUME_API_KEY:
#         logger.warning("Hume: no API key")
#         return {}

#     if audio_url:
#         return await _hume_audio(audio_url)
#     else:
#         logger.info("No audio URL — falling back to Hume language model")
#         return await _hume_text(transcript)


# async def _hume_audio(audio_url: str) -> dict:
#     """Hume prosody model — real pronunciation, fluency, confidence from voice."""
#     try:
#         async with httpx.AsyncClient(timeout=180) as client:
#             res = await client.post(
#                 "https://api.hume.ai/v0/batch/jobs",
#                 headers={"X-Hume-Api-Key": HUME_API_KEY},
#                 json={"urls": [audio_url], "models": {"prosody": {}}, "notify": False},
#             )
#             res.raise_for_status()
#             job_id = res.json()["job_id"]
#             logger.info(f"Hume audio job: {job_id}")

#             for _ in range(30):
#                 await asyncio.sleep(4)
#                 status = await client.get(
#                     f"https://api.hume.ai/v0/batch/jobs/{job_id}",
#                     headers={"X-Hume-Api-Key": HUME_API_KEY},
#                 )
#                 state = status.json().get("state", {}).get("status", "")
#                 logger.info(f"Hume status: {state}")
#                 if state == "COMPLETED":
#                     pred = await client.get(
#                         f"https://api.hume.ai/v0/batch/jobs/{job_id}/predictions",
#                         headers={"X-Hume-Api-Key": HUME_API_KEY},
#                     )
#                     return _parse_prosody(pred.json())
#                 if state == "FAILED":
#                     logger.error("Hume audio job failed")
#                     return {}
#     except Exception as e:
#         logger.error(f"Hume audio error: {e}")
#     return {}


# async def _hume_text(transcript: list) -> dict:
#     """Hume language model — emotion scoring from transcript text."""
#     try:
#         user_lines = [m["text"] for m in transcript if m["role"] == "user"]
#         if not user_lines:
#             return {}
#         text_input = " ".join(user_lines)

#         async with httpx.AsyncClient(timeout=60) as client:
#             res = await client.post(
#                 "https://api.hume.ai/v0/batch/jobs",
#                 headers={"X-Hume-Api-Key": HUME_API_KEY},
#                 json={"models": {"language": {}}, "text": [text_input], "notify": False},
#             )
#             res.raise_for_status()
#             job_id = res.json()["job_id"]
#             logger.info(f"Hume text job: {job_id}")

#             for _ in range(20):
#                 await asyncio.sleep(4)
#                 status = await client.get(
#                     f"https://api.hume.ai/v0/batch/jobs/{job_id}",
#                     headers={"X-Hume-Api-Key": HUME_API_KEY},
#                 )
#                 state = status.json().get("state", {}).get("status", "")
#                 if state == "COMPLETED":
#                     pred = await client.get(
#                         f"https://api.hume.ai/v0/batch/jobs/{job_id}/predictions",
#                         headers={"X-Hume-Api-Key": HUME_API_KEY},
#                     )
#                     return _parse_language(pred.json())
#                 if state == "FAILED":
#                     return {}
#     except Exception as e:
#         logger.error(f"Hume text error: {e}")
#     return {}


# def _parse_prosody(predictions: dict) -> dict:
#     try:
#         segs = (
#             predictions[0]["results"]["predictions"][0]
#             ["models"]["prosody"]["grouped_predictions"][0]["predictions"]
#         )
#         totals = {}
#         count  = len(segs) or 1
#         for seg in segs:
#             for e in seg["emotions"]:
#                 totals[e["name"]] = totals.get(e["name"], 0) + e["score"]
#         avg = {k: round(v / count, 3) for k, v in totals.items()}

#         confidence  = avg.get("Confidence",  0) + avg.get("Determination", 0)
#         nervousness = avg.get("Nervousness", 0) + avg.get("Anxiety", 0) + avg.get("Fear", 0)
#         excitement  = avg.get("Excitement",  0) + avg.get("Enthusiasm", 0) + avg.get("Joy", 0)

#         segments = []
#         for i, seg in enumerate(segs[:10]):
#             top3 = sorted(seg["emotions"], key=lambda x: x["score"], reverse=True)[:3]
#             segments.append({
#                 "segment": i + 1,
#                 "top_emotions": [{"name": e["name"], "score": round(e["score"] * 100)} for e in top3]
#             })

#         return {
#             "confidence_score":  min(round(confidence  * 120), 100),
#             "nervousness_score": min(round(nervousness * 120), 100),
#             "excitement_score":  min(round(excitement  * 120), 100),
#             "dominant_emotion":  max(avg, key=avg.get) if avg else "Neutral",
#             "segments":          segments,
#             "source":            "audio",
#         }
#     except Exception as e:
#         logger.error(f"Prosody parse error: {e}")
#         return {}


# def _parse_language(predictions: dict) -> dict:
#     try:
#         preds = (
#             predictions[0]["results"]["predictions"][0]
#             ["models"]["language"]["grouped_predictions"][0]["predictions"]
#         )
#         totals = {}
#         count  = len(preds) or 1
#         for pred in preds:
#             for e in pred.get("emotions", []):
#                 totals[e["name"]] = totals.get(e["name"], 0) + e["score"]
#         avg = {k: round(v / count, 3) for k, v in totals.items()}

#         confidence  = avg.get("Confidence",  0) + avg.get("Determination", 0)
#         nervousness = avg.get("Nervousness", 0) + avg.get("Anxiety", 0) + avg.get("Fear", 0)
#         excitement  = avg.get("Excitement",  0) + avg.get("Enthusiasm", 0) + avg.get("Joy", 0)

#         top5 = sorted(avg.items(), key=lambda x: x[1], reverse=True)[:5]

#         return {
#             "confidence_score":  min(round(confidence  * 120), 100),
#             "nervousness_score": min(round(nervousness * 120), 100),
#             "excitement_score":  min(round(excitement  * 120), 100),
#             "dominant_emotion":  max(avg, key=avg.get) if avg else "Neutral",
#             "top_emotions":      [{"name": k, "score": round(v * 100)} for k, v in top5],
#             "source":            "text",
#         }
#     except Exception as e:
#         logger.error(f"Language parse error: {e}")
#         return {}


# if __name__ == "__main__":
#     cli.run_app(server)
import logging
import os
import json
import httpx
import asyncio
from datetime import datetime
from livekit.agents import Agent, AgentServer, AgentSession, JobContext, JobProcess, RoomInputOptions, cli
from livekit.plugins import silero
from livekit.plugins import openai, deepgram
from livekit import api

logger = logging.getLogger("julian-cloud-agent")

BACKEND_URL         = os.environ.get("BACKEND_URL", "https://specker.ai")
OPENAI_API_KEY      = os.environ.get("OPENAI_API_KEY")
HUME_API_KEY        = os.environ.get("HUME_API_KEY")
LIVEKIT_URL         = os.environ.get("LIVEKIT_URL")
LIVEKIT_API_KEY     = os.environ.get("LIVEKIT_API_KEY")
LIVEKIT_API_SECRET  = os.environ.get("LIVEKIT_API_SECRET")

class JulianAgent(Agent):
    def __init__(self) -> None:
        super().__init__(
            instructions="""You are Julian, a warm and empathetic AI friend on a phone call.
Keep responses short — 1 to 2 sentences. Be warm and natural. English only.
Ask follow-up questions to keep the conversation going.""",
        )

    async def on_enter(self):
        await self.session.generate_reply(
            instructions="Greet the user warmly and ask how they are doing today.",
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

    session = AgentSession(
        stt=deepgram.STT(model="nova-2", language="en"),
        llm=openai.LLM(model="gpt-4o-mini"),
        tts=deepgram.TTS(model="aura-2-thalia-en"),
        vad=ctx.proc.userdata["vad"],
    )

    # conversation_item_added fires for both user and agent turns in livekit-agents 1.5.x
    @session.on("conversation_item_added")
    def on_item_added(event):
        try:
            item = event.item
            # item.role is "user" or "assistant"
            # item.text_content is the transcript text
            role = getattr(item, "role", None)
            text = getattr(item, "text_content", None) or getattr(item, "text", None)

            if role and text:
                transcript.append({
                    "role": role,
                    "text": text,
                    "time": datetime.utcnow().isoformat(),
                })
                label = "User" if role == "user" else "Julian"
                logger.info(f"{label}: {text}")
            else:
                logger.info(f"conversation_item_added — role={role} text={text} attrs={dir(item)}")
        except Exception as e:
            logger.error(f"Error in on_item_added: {e} | event={event} | dir={dir(event)}")

    await session.start(
        agent=JulianAgent(),
        room=ctx.room,
        room_input_options=RoomInputOptions(close_on_disconnect=False),
    )

    # Wait for room disconnect
    disconnect_event = asyncio.Event()
    ctx.room.on("disconnected", lambda: disconnect_event.set())
    await disconnect_event.wait()

    # Give speech events a moment to flush
    await asyncio.sleep(2)

    duration = int((datetime.utcnow() - start_time).total_seconds())
    logger.info(f"Call ended. Duration: {duration}s | Lines: {len(transcript)}")

    if len(transcript) == 0:
        logger.warning("No transcript captured — skipping analysis")
        return

    # Get user identity + email from participant metadata
    participant_identity = None
    user_email = None
    for p in ctx.room.remote_participants.values():
        participant_identity = p.identity
        try:
            meta = json.loads(p.metadata or "{}")
            user_email = meta.get("email")
        except Exception:
            pass
        break

    # Get recording URL from S3 egress
    recording_url = await get_recording_url(ctx)

    # Run GPT + Hume in parallel
    logger.info("Starting parallel analysis: GPT-4o + Hume AI")
    gpt_task  = asyncio.create_task(analyze_with_gpt(transcript, duration))
    hume_task = asyncio.create_task(analyze_with_hume(recording_url, transcript))

    gpt_result, hume_result = await asyncio.gather(gpt_task, hume_task, return_exceptions=True)

    if isinstance(gpt_result, Exception):
        logger.error(f"GPT failed: {gpt_result}")
        gpt_result = {}
    if isinstance(hume_result, Exception):
        logger.error(f"Hume failed: {hume_result}")
        hume_result = {}

    # Send combined report to backend
    payload = {
        "roomName":            ctx.room.name,
        "participantIdentity": participant_identity,
        "userEmail":           user_email,
        "duration":            duration,
        "transcript":          transcript,
        "analysis": {
            **gpt_result,
            "vocal_emotion": hume_result,
        },
        "timestamp": datetime.utcnow().isoformat(),
    }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            res = await client.post(
                f"{BACKEND_URL}/api/call-report",
                json=payload,
                headers={"Content-Type": "application/json"},
            )
            logger.info(f"Report sent: {res.status_code}")
    except Exception as e:
        logger.error(f"Failed to send report: {e}")


async def get_recording_url(ctx) -> str | None:
    try:
        logger.info("Waiting 6s for egress to finalize...")
        await asyncio.sleep(6)
        lk = api.LiveKitAPI(url=LIVEKIT_URL, api_key=LIVEKIT_API_KEY, api_secret=LIVEKIT_API_SECRET)
        egresses = await lk.egress.list_egress(api.ListEgressRequest(room_name=ctx.room.name))
        for e in egresses.items:
            if hasattr(e, "file") and e.file and e.file.location:
                logger.info(f"Recording URL: {e.file.location}")
                return e.file.location
    except Exception as ex:
        logger.warning(f"Could not get recording URL: {ex}")
    return None


async def analyze_with_gpt(transcript: list, duration: int) -> dict:
    try:
        from openai import AsyncOpenAI
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
        logger.error(f"GPT error: {e}")
        return {}


async def analyze_with_hume(audio_url: str | None, transcript: list) -> dict:
    if not HUME_API_KEY:
        logger.warning("Hume: no API key")
        return {}
    if audio_url:
        return await _hume_audio(audio_url)
    else:
        logger.info("No audio URL — falling back to Hume language model")
        return await _hume_text(transcript)


async def _hume_audio(audio_url: str) -> dict:
    try:
        async with httpx.AsyncClient(timeout=180) as client:
            res = await client.post(
                "https://api.hume.ai/v0/batch/jobs",
                headers={"X-Hume-Api-Key": HUME_API_KEY},
                json={"urls": [audio_url], "models": {"prosody": {}}, "notify": False},
            )
            res.raise_for_status()
            job_id = res.json()["job_id"]
            logger.info(f"Hume audio job: {job_id}")
            for _ in range(30):
                await asyncio.sleep(4)
                status = await client.get(f"https://api.hume.ai/v0/batch/jobs/{job_id}", headers={"X-Hume-Api-Key": HUME_API_KEY})
                state = status.json().get("state", {}).get("status", "")
                logger.info(f"Hume status: {state}")
                if state == "COMPLETED":
                    pred = await client.get(f"https://api.hume.ai/v0/batch/jobs/{job_id}/predictions", headers={"X-Hume-Api-Key": HUME_API_KEY})
                    return _parse_prosody(pred.json())
                if state == "FAILED":
                    logger.error("Hume audio job failed")
                    return {}
    except Exception as e:
        logger.error(f"Hume audio error: {e}")
    return {}


async def _hume_text(transcript: list) -> dict:
    try:
        user_lines = [m["text"] for m in transcript if m["role"] == "user"]
        if not user_lines:
            return {}
        text_input = " ".join(user_lines)
        async with httpx.AsyncClient(timeout=60) as client:
            res = await client.post(
                "https://api.hume.ai/v0/batch/jobs",
                headers={"X-Hume-Api-Key": HUME_API_KEY},
                json={"models": {"language": {}}, "text": [text_input], "notify": False},
            )
            res.raise_for_status()
            job_id = res.json()["job_id"]
            logger.info(f"Hume text job: {job_id}")
            for _ in range(20):
                await asyncio.sleep(4)
                status = await client.get(f"https://api.hume.ai/v0/batch/jobs/{job_id}", headers={"X-Hume-Api-Key": HUME_API_KEY})
                state = status.json().get("state", {}).get("status", "")
                if state == "COMPLETED":
                    pred = await client.get(f"https://api.hume.ai/v0/batch/jobs/{job_id}/predictions", headers={"X-Hume-Api-Key": HUME_API_KEY})
                    return _parse_language(pred.json())
                if state == "FAILED":
                    return {}
    except Exception as e:
        logger.error(f"Hume text error: {e}")
    return {}


def _parse_prosody(predictions: dict) -> dict:
    try:
        segs = predictions[0]["results"]["predictions"][0]["models"]["prosody"]["grouped_predictions"][0]["predictions"]
        totals = {}
        count = len(segs) or 1
        for seg in segs:
            for e in seg["emotions"]:
                totals[e["name"]] = totals.get(e["name"], 0) + e["score"]
        avg = {k: round(v / count, 3) for k, v in totals.items()}
        confidence  = avg.get("Confidence", 0)  + avg.get("Determination", 0)
        nervousness = avg.get("Nervousness", 0) + avg.get("Anxiety", 0) + avg.get("Fear", 0)
        excitement  = avg.get("Excitement", 0)  + avg.get("Enthusiasm", 0) + avg.get("Joy", 0)
        segments = []
        for i, seg in enumerate(segs[:10]):
            top3 = sorted(seg["emotions"], key=lambda x: x["score"], reverse=True)[:3]
            segments.append({"segment": i + 1, "top_emotions": [{"name": e["name"], "score": round(e["score"] * 100)} for e in top3]})
        return {
            "confidence_score":  min(round(confidence  * 120), 100),
            "nervousness_score": min(round(nervousness * 120), 100),
            "excitement_score":  min(round(excitement  * 120), 100),
            "dominant_emotion":  max(avg, key=avg.get) if avg else "Neutral",
            "segments":          segments,
            "source":            "audio",
        }
    except Exception as e:
        logger.error(f"Prosody parse error: {e}")
        return {}


def _parse_language(predictions: dict) -> dict:
    try:
        preds = predictions[0]["results"]["predictions"][0]["models"]["language"]["grouped_predictions"][0]["predictions"]
        totals = {}
        count = len(preds) or 1
        for pred in preds:
            for e in pred.get("emotions", []):
                totals[e["name"]] = totals.get(e["name"], 0) + e["score"]
        avg = {k: round(v / count, 3) for k, v in totals.items()}
        confidence  = avg.get("Confidence", 0)  + avg.get("Determination", 0)
        nervousness = avg.get("Nervousness", 0) + avg.get("Anxiety", 0) + avg.get("Fear", 0)
        excitement  = avg.get("Excitement", 0)  + avg.get("Enthusiasm", 0) + avg.get("Joy", 0)
        top5 = sorted(avg.items(), key=lambda x: x[1], reverse=True)[:5]
        return {
            "confidence_score":  min(round(confidence  * 120), 100),
            "nervousness_score": min(round(nervousness * 120), 100),
            "excitement_score":  min(round(excitement  * 120), 100),
            "dominant_emotion":  max(avg, key=avg.get) if avg else "Neutral",
            "top_emotions":      [{"name": k, "score": round(v * 100)} for k, v in top5],
            "source":            "text",
        }
    except Exception as e:
        logger.error(f"Language parse error: {e}")
        return {}


if __name__ == "__main__":
    cli.run_app(server)