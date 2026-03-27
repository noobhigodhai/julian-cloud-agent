import logging
import os
from livekit.agents import Agent, AgentServer, AgentSession, JobContext, JobProcess, cli
from livekit.plugins import silero
from livekit.plugins import openai, deepgram

logger = logging.getLogger("julian-cloud-agent")

# On LiveKit Cloud, env vars are injected as secrets — no .env file needed
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
    session = AgentSession(
        stt=deepgram.STT(model="nova-2", language="en"),
        llm=openai.LLM(model="gpt-4o-mini"),
        tts=deepgram.TTS(model="aura-2-thalia-en"),
        vad=ctx.proc.userdata["vad"],
    )
    await session.start(
        agent=JulianAgent(),
        room=ctx.room,
    )

if __name__ == "__main__":
    cli.run_app(server)
