import logging
import os
import json
import httpx
import asyncio
from datetime import datetime
from livekit.agents import Agent, AgentServer, AgentSession, JobContext, JobProcess, RoomOptions, cli
from livekit.plugins import silero
from livekit.plugins import openai, deepgram

logger = logging.getLogger("julian-cloud-agent")
BACKEND_URL = os.environ.get("BACKEND_URL", "https://specker.ai")

class JulianAgent(Agent):
    def __init__(self):
        super().__init__(instructions="""You are Julian, a warm and empathetic AI friend on a phone call.
Keep responses short — 1 to 2 sentences. Be warm and natural. English only.
Ask follow-up questions to keep the conversation going.""")

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
    participant_identity = None
    user_email = None
    user_id = None

    for p in ctx.room.remote_participants.values():
        participant_identity = p.identity
        try:
            meta = json.loads(p.metadata or "{}")
            user_email = meta.get("email")
            user_id = meta.get("userId")
            logger.info(f"Participant: {participant_identity} | userId: {user_id}")
        except Exception as e:
            logger.error(f"Metadata parse error: {e}")
        break

    def on_participant_connected(participant):
        nonlocal participant_identity, user_email, user_id
        if participant_identity is None:
            participant_identity = participant.identity
            try:
                meta = json.loads(participant.metadata or "{}")
                user_email = meta.get("email")
                user_id = meta.get("userId")
                logger.info(f"Participant joined: {participant_identity} | userId: {user_id}")
            except Exception as e:
                logger.error(f"Metadata parse error on join: {e}")

    ctx.room.on("participant_connected", on_participant_connected)

    session = AgentSession(
        stt=deepgram.STT(model="nova-2", language="en"),
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
                transcript.append({
                    "role": role,
                    "text": text,
                    "time": datetime.utcnow().isoformat(),
                })
                logger.info(f"{'User' if role == 'user' else 'Julian'}: {text}")
        except Exception as e:
            logger.error(f"Error in on_item_added: {e}")

    async def on_shutdown():
        logger.info(f"Shutdown callback | Lines: {len(transcript)}")
        if not transcript:
            logger.warning("No transcript — skipping")
            return

        duration = int((datetime.utcnow() - start_time).total_seconds())
        logger.info(f"Sending transcript | duration: {duration}s | lines: {len(transcript)}")

        # Step 1: Send transcript to app via LiveKit data channel (instant)
        try:
            data = json.dumps({
                "type":       "transcript",
                "transcript": transcript,
                "duration":   duration,
            }).encode()
            await ctx.room.local_participant.publish_data(data, reliable=True)
            logger.info("✅ Transcript sent via data channel to app")
            await asyncio.sleep(1)  # give time to deliver
        except Exception as e:
            logger.error(f"Data channel error: {e}")

        # Step 2: Send to server for MongoDB storage + Hume analysis (background)
        payload = {
            "roomName":            ctx.room.name,
            "participantIdentity": participant_identity,
            "userEmail":           user_email,
            "userId":              user_id,
            "duration":            duration,
            "transcript":          transcript,
            "timestamp":           datetime.utcnow().isoformat(),
        }
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                res = await client.post(
                    f"{BACKEND_URL}/api/call-report",
                    json=payload,
                    headers={"Content-Type": "application/json"},
                )
                logger.info(f"✅ Transcript sent to server: {res.status_code}")
        except Exception as e:
            logger.error(f"Failed to send to server: {e}")

    ctx.add_shutdown_callback(on_shutdown)

    await session.start(
        agent=JulianAgent(),
        room=ctx.room,
        room_options=RoomOptions(close_on_disconnect=False),
    )

    disconnect_event = asyncio.Event()
    ctx.room.on("disconnected", lambda: disconnect_event.set())
    await disconnect_event.wait()


if __name__ == "__main__":
    cli.run_app(server)