"""The phone agent. LiveKit carries the audio; this file decides every word.

Run:  uv run python -m helpline.agent dev      take calls
      uv run python -m helpline.agent console  talk to it from this terminal

The session is given no language model on purpose. When the caller finishes a
sentence we ask the model ourselves, pass the reply through the gate, and
speak only what the gate returns.
"""

import asyncio
import json
import logging
import re
import time
from collections.abc import Coroutine
from pathlib import Path

from dotenv import load_dotenv
from livekit import rtc
from livekit.agents import Agent, AgentServer, AgentSession, ErrorEvent, JobContext, cli
from livekit.agents.job import get_job_context
from livekit.agents.llm import ChatContext, ChatMessage
from livekit.agents.voice import SpeechHandle, UserInputTranscribedEvent, UserStateChangedEvent
from livekit.plugins import deepgram, silero

from helpline import lines
from helpline.brain import BACKUP_MODEL, MODEL, draft, judge, make_llm, same_words
from helpline.gate import Gate, Turn
from helpline.prompt import build_system_prompt, load_articles, prompt_version

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")
logger = logging.getLogger("helpline")

CALL_LOG = ROOT / "logs" / "calls.jsonl"
HEARING_MODEL = "flux-general-en"  # Deepgram Flux: speech to text that also detects end of turn
VOICE_MODEL = "aura-2-andromeda-en"  # Deepgram Aura-2: text to speech
# Deepgram's region nearest to where this runs. From India the EU one is half the distance
# of the US one (api.deepgram.com), and a turn crosses it twice.
SPEECH_HOST = "api.eu.deepgram.com"
SILENCE_SECONDS = 10
SAY_ONE_MOMENT_AFTER_SECONDS = 1.5  # past this, silence feels like a dropped line
PAD_AFTER_LAST_WORD_SECONDS = 0.5  # the phone network lags a little behind our audio
PHONE_SETTLE_SECONDS = 1.0  # a phone line drops the first moment of audio after pickup
PHONE_PICKUP_LIMIT_SECONDS = 10


def without_phone_number(room_name: str) -> str:
    """LiveKit names a phone call's room after the caller's number. Keep the last two digits."""
    return re.sub(r"\+(\d+)(\d\d)", lambda m: "+" + "x" * len(m[1]) + m[2], room_name)


class Helpline(Agent):
    def __init__(self, room_name: str, caller: rtc.RemoteParticipant) -> None:
        super().__init__(instructions="")
        articles = load_articles()
        self.call_id = without_phone_number(room_name)
        self.caller = caller
        self.on_phone = caller.kind == rtc.ParticipantKind.PARTICIPANT_KIND_SIP
        self.gate = Gate(articles)
        self.system_prompt = build_system_prompt(articles)
        self.prompt_version = prompt_version(self.system_prompt)
        self.models = [make_llm(MODEL), make_llm(BACKUP_MODEL)]
        self.closing = False  # a handoff or goodbye has begun
        self.checking_in = False  # we asked "are you still there?" and are waiting
        self.heard_caller = False
        self.early: tuple[str, asyncio.Task] | None = None  # (the words it was started on, the draft)
        self.tasks: set[asyncio.Task] = set()

    async def on_enter(self) -> None:
        self.session.on("user_state_changed", self._on_user_state)
        self.session.on("user_input_transcribed", self._on_words)
        self.record(note="caller joined", on_phone=self.on_phone)
        if self.on_phone:
            await self._wait_for_pickup()
        self._log("", "", Turn("chat", "greeting", lines.GREETING))
        self.session.say(lines.GREETING)

    async def on_user_turn_completed(self, turn_ctx: ChatContext, new_message: ChatMessage) -> None:
        heard = new_message.text_content or ""
        if self.closing or not heard.strip():
            return
        self.checking_in = False

        started = time.perf_counter()
        thinking = self._draft_for(heard)
        done, _ = await asyncio.wait({thinking}, timeout=SAY_ONE_MOMENT_AFTER_SECONDS)
        if not done:
            self.session.say(lines.ONE_MOMENT)
        reply, turn = judge(self.gate, heard, await thinking)
        if self.closing:  # a goodbye began while we were waiting for the model
            return
        # How long LiveKit took to decide the caller had finished speaking.
        end_of_turn = (new_message.metrics or {}).get("end_of_turn_delay", 0)
        self._log(
            heard,
            reply,
            turn,
            end_of_turn_ms=round(end_of_turn * 1000),
            model_ms=round((time.perf_counter() - started) * 1000),
        )
        self._speak(turn)

    def _on_words(self, event: UserInputTranscribedEvent) -> None:
        """Start on the model as soon as a sentence looks finished, before the turn is final.

        Waiting for the end-of-turn check costs about half a second. If the caller
        keeps talking, the early draft is for the wrong words and is thrown away.
        """
        heard = event.transcript.strip()
        if self.closing or not heard.endswith((".", "?", "!")):
            return
        if self.early and same_words(self.early[0], heard):
            return
        self._drop_early()
        self.early = (
            heard,
            asyncio.create_task(draft(self.models, self.system_prompt, self.gate.transcript, heard)),
        )

    def _draft_for(self, heard: str) -> asyncio.Task:
        """The early draft if it was for these exact words, else a fresh one."""
        early, self.early = self.early, None
        if early and same_words(early[0], heard):
            return early[1]
        if early:
            early[1].cancel()
        return asyncio.create_task(draft(self.models, self.system_prompt, self.gate.transcript, heard))

    def _drop_early(self) -> None:
        if self.early:
            self.early[1].cancel()
            self.early = None

    async def _wait_for_pickup(self) -> None:
        """A phone caller joins the room while the line is still ringing. Anything
        said before it turns active is never heard, so wait for that first."""
        give_up_at = time.perf_counter() + PHONE_PICKUP_LIMIT_SECONDS
        while self._line_status() != "active" and time.perf_counter() < give_up_at:
            await asyncio.sleep(0.1)
        self.record(note="line active", status=self._line_status())
        await asyncio.sleep(PHONE_SETTLE_SECONDS)

    def _line_status(self) -> str | None:
        return self.caller.attributes.get("sip.callStatus")

    def _speak(self, turn: Turn) -> None:
        if not turn.hang_up:
            self.session.say(turn.say)
            return
        self.closing = True  # a handoff is final: nothing the caller says now reopens the call
        last_line = self.session.say(turn.say, allow_interruptions=False)
        self._start(self._hang_up_after(last_line))

    async def _hang_up_after(self, last_line: SpeechHandle) -> None:
        await last_line.wait_for_playout()
        await asyncio.sleep(PAD_AFTER_LAST_WORD_SECONDS)
        job = get_job_context()
        try:
            await job.delete_room()  # deleting the room drops the phone call
        except Exception:
            logger.exception("could not delete the room; shutting the job down instead")
            job.shutdown()

    def _on_user_state(self, event: UserStateChangedEvent) -> None:
        if event.new_state == "speaking":
            self.checking_in = False
            if not self.heard_caller:
                self.heard_caller = True
                self.record(note="caller audio detected")  # proof that their sound reaches us
        elif event.new_state == "away" and not self.closing and not self.checking_in:
            self.checking_in = True
            self._start(self._check_in_then_end())

    async def _check_in_then_end(self) -> None:
        """Ask once. If the caller still says nothing, say goodbye and end the call."""
        self._log("", "", Turn("chat", "still_there", lines.STILL_THERE))
        await self.session.say(lines.STILL_THERE).wait_for_playout()
        await asyncio.sleep(SILENCE_SECONDS)
        if self.checking_in and not self.closing:
            turn = Turn("end", "silence", lines.GOODBYE, hang_up=True)
            self._log("", "", turn)
            self._speak(turn)

    def _start(self, work: Coroutine) -> None:
        """Run in the background. The loop only holds a weak reference, so we keep a strong one."""
        task = asyncio.create_task(work)
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    def _log(self, heard: str, reply: str, turn: Turn, end_of_turn_ms: int = 0, model_ms: int = 0) -> None:
        self.record(
            turn=len(self.gate.transcript),
            heard=heard,
            model_reply=reply,
            action=turn.action,
            detail=turn.detail,
            said=turn.say,
            end_of_turn_ms=end_of_turn_ms,  # caller stopped talking -> we were handed their words
            model_ms=model_ms,  # we had their words -> the gate had decided
            model=MODEL,
            prompt_version=self.prompt_version,
        )

    def record(self, **fields) -> None:
        """Append one line to the call log."""
        CALL_LOG.parent.mkdir(exist_ok=True)
        entry = {"time": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "call_id": self.call_id, **fields}
        with CALL_LOG.open("a") as log:
            log.write(json.dumps(entry) + "\n")


server = AgentServer(num_idle_processes=1)  # one process kept warm, so pickup is not delayed


@server.rtc_session(agent_name="helpline")
async def entrypoint(ctx: JobContext) -> None:
    await ctx.connect()
    caller = await ctx.wait_for_participant()  # greet only once someone is there to hear it
    session = AgentSession(
        stt=deepgram.STTv2(
            model=HEARING_MODEL, base_url=f"wss://{SPEECH_HOST}/v2/listen"
        ),  # needs DEEPGRAM_API_KEY
        tts=deepgram.TTS(model=VOICE_MODEL, base_url=f"https://{SPEECH_HOST}/v1/speak"),
        vad=silero.VAD.load(),
        user_away_timeout=SILENCE_SECONDS,
        turn_handling={
            # Flux hears where a sentence ends, so let it decide when the caller has finished.
            "turn_detection": "stt",
            "endpointing": {"min_delay": 0.1, "max_delay": 1.2},
            # Any voice over the agent stops it. The smarter detector missed real interruptions.
            "interruption": {"mode": "vad", "min_duration": 0.3},
        },
    )
    agent = Helpline(ctx.room.name, caller)

    def drop_call_if_speech_failed(event: ErrorEvent) -> None:
        # Hearing or speaking has stopped working, so we cannot even say goodbye.
        # A dropped call is kinder than a silent one.
        if not event.error.recoverable and not agent.closing:
            agent.closing = True
            agent.record(note="speech service failed, call dropped", error=type(event.error).__name__)
            agent.dropping = ctx.delete_room()

    session.on("error", drop_call_if_speech_failed)
    await session.start(agent=agent, room=ctx.room)


if __name__ == "__main__":
    cli.run_app(server)
