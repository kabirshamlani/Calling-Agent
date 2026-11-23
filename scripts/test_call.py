"""Call the running agent without a phone.

Joins a LiveKit room as a caller, waits for the greeting, then speaks each
sentence you pass using the macOS `say` voice. It listens to the agent's audio
to time each reply and to see whether the agent ends the call.
The agent must be running: make serve

Usage: uv run python scripts/test_call.py "How do I cancel my transfer?"

A sentence can be a stage direction instead:
  "(silence)"            say nothing for 35 seconds
  "(interrupt) Why is it late? | Wait, how do I cancel?"
                         ask the first part, then talk over the answer with the second
"""

import asyncio
import os
import statistics
import subprocess
import sys
import tempfile
import time
import uuid
import wave
from pathlib import Path

from dotenv import load_dotenv
from livekit import api, rtc

RATE = 48000
FRAME = RATE // 100  # samples in 10 ms
SILENCE = b"\x00\x00" * FRAME
LOUD = 500  # 16-bit sample level above which audio counts as speech
QUIET_MEANS_DONE = 1.5  # seconds without agent audio before we call its reply finished
ROOT = Path(__file__).resolve().parents[1]


def spoken(sentence: str) -> bytes:
    """The sentence as 16-bit audio, with trailing silence cut so timing starts at the last word."""
    with tempfile.NamedTemporaryFile(suffix=".wav") as file:
        subprocess.run(["say", "-o", file.name, f"--data-format=LEI16@{RATE}", sentence], check=True)
        with wave.open(file.name) as audio:
            pcm = audio.readframes(audio.getnframes())
    samples = memoryview(pcm).cast("h")
    last_loud = max((i for i, sample in enumerate(samples) if abs(sample) > LOUD), default=0)
    return pcm[: (last_loud + 1) * 2]


class Caller:
    def __init__(self) -> None:
        self.room = rtc.Room()
        self.mic = rtc.AudioSource(RATE, 1)
        self.started = time.perf_counter()
        self.agent_last_heard = 0.0
        self.left = False
        self.reply_delays: list[float] = []

    def log(self, text: str) -> None:
        print(f"{time.perf_counter() - self.started:6.1f}s  {text}")

    async def join(self) -> None:
        name = f"test-{uuid.uuid4().hex[:8]}"
        token = (
            api.AccessToken()
            .with_identity("test-caller")
            .with_grants(api.VideoGrants(room_join=True, room=name))
            .with_room_config(api.RoomConfiguration(agents=[api.RoomAgentDispatch(agent_name="helpline")]))
            .to_jwt()
        )
        self.room.on("track_subscribed", self._on_track)
        self.room.on("disconnected", self._on_disconnected)
        await self.room.connect(os.environ["LIVEKIT_URL"], token)
        track = rtc.LocalAudioTrack.create_audio_track("mic", self.mic)
        await self.room.local_participant.publish_track(
            track, rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE)
        )
        self.log(f"joined {name}")

    def _on_track(self, track, *_) -> None:
        if track.kind == rtc.TrackKind.KIND_AUDIO:
            self._listener = asyncio.create_task(self._listen(track))

    async def _listen(self, track) -> None:
        async for event in rtc.AudioStream(track):
            if max(event.frame.data, default=0) > LOUD:
                self.agent_last_heard = time.perf_counter()

    def _on_disconnected(self, *_) -> None:
        if not self.left:
            self.log("call ended by the agent")
        self.left = True

    async def send(self, pcm: bytes) -> None:
        """Play audio into the call at real speed, so our clock matches what the agent hears."""
        due = time.perf_counter()
        for start in range(0, len(pcm), FRAME * 2):
            chunk = pcm[start : start + FRAME * 2].ljust(FRAME * 2, b"\x00")
            await self.mic.capture_frame(rtc.AudioFrame(chunk, RATE, 1, FRAME))
            due += 0.01
            await asyncio.sleep(max(0, due - time.perf_counter()))

    def agent_talking(self) -> bool:
        return time.perf_counter() - self.agent_last_heard < 0.3

    async def wait_for_reply(self, limit: float = 40) -> float | None:
        """Stay quiet until the agent has spoken and stopped. Return when it started."""
        asked, began = time.perf_counter(), None
        while not self.left and time.perf_counter() - asked < limit:
            await self.send(SILENCE * 10)
            if began is None and self.agent_last_heard > asked:
                began = self.agent_last_heard
            if began and time.perf_counter() - self.agent_last_heard > QUIET_MEANS_DONE:
                break
        return began

    async def say(self, sentence: str) -> None:
        self.log(f"caller says: {sentence}")
        await self.send(spoken(sentence))
        stopped = time.perf_counter()
        began = await self.wait_for_reply()
        if began:
            self.reply_delays.append(began - stopped)
            self.log(f"agent replied {began - stopped:.1f}s after the caller stopped")

    async def stay_silent(self, seconds: float = 35) -> None:
        self.log("caller says nothing")
        until = time.perf_counter() + seconds
        while not self.left and time.perf_counter() < until:
            await self.send(SILENCE * 10)

    async def interrupt(self, question: str, sentence: str) -> None:
        """Ask something, talk over the answer, and time how long the agent takes to go quiet."""
        interruption = spoken(sentence)  # made now: generating speech would stall our clock later
        self.log(f"caller says: {question}")
        await self.send(spoken(question))
        waited = time.perf_counter()
        while not self.agent_talking() and time.perf_counter() - waited < 15:
            await self.send(SILENCE * 10)
        await self.send(SILENCE * 200)  # let it get two seconds into the reply
        self.log(f"caller interrupts: {sentence}")
        began = time.perf_counter()
        talking = asyncio.create_task(self.send(interruption))
        while self.agent_talking() and time.perf_counter() - began < 8:
            await asyncio.sleep(0.02)
        self.log(f"agent went quiet {self.agent_last_heard - began:.1f}s after the caller started")
        await talking
        stopped = time.perf_counter()
        began = await self.wait_for_reply()
        if began:
            self.log(f"agent replied {began - stopped:.1f}s after the caller stopped")

    async def finish(self) -> None:
        for _ in range(50):  # a hang-up can land a few seconds after the last word
            if self.left:
                break
            await self.send(SILENCE * 10)
        if not self.left:
            self.log("call still open, hanging up from our side")
            self.left = True
            await self.room.disconnect()
        if len(self.reply_delays) > 1:
            d = self.reply_delays
            print(
                f"\nreply delay over {len(d)} turns: average {statistics.mean(d):.1f}s, "
                f"median {statistics.median(d):.1f}s, fastest {min(d):.1f}s, slowest {max(d):.1f}s"
            )


async def main(script: list[str]) -> None:
    load_dotenv(ROOT / ".env")
    caller = Caller()
    await caller.join()
    await caller.wait_for_reply()
    caller.log("greeting finished")
    for line in script:
        if caller.left:
            break
        if line == "(silence)":
            await caller.stay_silent()
        elif line.startswith("(interrupt)"):
            question, _, interruption = line.removeprefix("(interrupt)").partition("|")
            await caller.interrupt(question.strip(), interruption.strip())
        else:
            await caller.say(line)
    await caller.finish()


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1:] or ["How do I cancel my transfer?"]))
