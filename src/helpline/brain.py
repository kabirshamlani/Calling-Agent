"""Decide how to reply to one caller turn: by rule where a rule is enough, by model otherwise."""

import asyncio
import logging
import re

from livekit.agents import APIConnectOptions
from livekit.agents.llm import LLM, ChatContext
from livekit.plugins import google

from helpline.gate import Gate, Turn, handoff

MODEL = "gemini-3.5-flash-lite"  # no wrong answers on either test set
BACKUP_MODEL = "gemini-3.1-flash-lite"  # a little faster, a little looser on scope
MODEL_TIMEOUT_SECONDS = 5  # per model. Longer than this and we stop waiting for it.
# No retries: one costs seconds the caller hears. Google refuses a deadline under ten
# seconds, so the five-second limit is ours, in draft().
ONE_TRY = APIConnectOptions(max_retry=0, timeout=10)

logger = logging.getLogger("helpline")

# Things callers say that need no model. A shortcut applies only when the whole
# sentence, with the politeness taken out, is one of these and nothing more.
POLITENESS = re.compile(
    r"\b(?:please|sorry|okay|ok|alright|great|right|well|um|uh|no|thanks|thank you|for now)\b"
)
PERSON = r"(?:a |an |the )?(?:real |actual |live )?(?:person|human|agent|representative|operator|someone)"
I_WANT = (
    r"(?:can i|could i|may i|i want to|i need to|i would like to|i'd like to"
    r"|let me|get me|give me|put me through to)"
)
SHORTCUTS = {
    "[chat:repeat]": re.compile(
        r"(?:(?:can|could) you )?(?:say|repeat) (?:that|it)(?: again| once more)?"
        r"|pardon|come again|what was that|what did you say|say again"
    ),
    "[handoff:asked_for_human]": re.compile(rf"{PERSON}|{I_WANT} (?:(?:talk|speak) (?:to|with) )?{PERSON}"),
    "[chat:greeting]": re.compile(r"(?:hello|hi|hey)(?: there)?|good (?:morning|afternoon|evening)"),
    "[end]": re.compile(r"(?:that's|that is) (?:all|it|everything)|nothing else|(?:bye )?(?:bye|goodbye)"),
}


def shortcut(heard: str) -> str | None:
    """The label for a sentence that needs no model, or None."""
    words = re.sub(r"[^a-z' ]", " ", heard.lower())
    words = " ".join(POLITENESS.sub(" ", words).split())
    for label, pattern in SHORTCUTS.items():
        if pattern.fullmatch(words):
            return label
    return None


def same_words(a: str, b: str) -> bool:
    """True when two transcripts differ only in case, spacing or punctuation."""
    letters = [re.sub(r"[^a-z0-9]", "", text.lower()) for text in (a, b)]
    return letters[0] == letters[1]


def make_llm(model: str = MODEL) -> LLM:
    """Needs GOOGLE_API_KEY in the environment."""
    if model == MODEL:  # it thinks before replying unless told not to, and that takes seconds
        return google.LLM(model=model, thinking_config={"thinking_level": "minimal"})
    return google.LLM(model=model)


async def ask(llm: LLM, system_prompt: str, transcript: list[tuple[str, str]], heard: str) -> str:
    """Send the rules, the articles and the call so far. Return the model's raw reply.

    The model sees its own earlier replies with their labels, not the words
    that were spoken, so the label habit does not fade over a long call.
    """
    context = ChatContext()
    context.add_message(role="system", content=system_prompt)
    for earlier_heard, earlier_reply in transcript:
        context.add_message(role="user", content=earlier_heard)
        context.add_message(role="assistant", content=earlier_reply)
    context.add_message(role="user", content=heard)

    reply = ""
    async with llm.chat(chat_ctx=context, conn_options=ONE_TRY) as stream:
        async for chunk in stream:
            if chunk.delta and chunk.delta.content:
                reply += chunk.delta.content
    return reply


async def draft(
    llms: list[LLM], system_prompt: str, transcript: list[tuple[str, str]], heard: str
) -> str | None:
    """The label and reply for one caller sentence, before the gate has seen it.

    The models are tried in order. One that errors or is too slow goes to the
    back of the list, so the rest of the call starts with one that works.
    None means no model answered.
    """
    reply = shortcut(heard)
    for _ in range(len(llms)):
        if reply is not None:
            break
        try:
            reply = await asyncio.wait_for(
                ask(llms[0], system_prompt, transcript, heard), MODEL_TIMEOUT_SECONDS
            )
        except Exception as error:
            logger.warning("%s did not answer: %s", llms[0].model, type(error).__name__)
            llms.append(llms.pop(0))
    return reply


def judge(gate: Gate, heard: str, reply: str | None) -> tuple[str, Turn]:
    """Put a draft through the gate. No draft at all means the caller gets a person."""
    if reply is None:
        return "(no model answered)", handoff("model_error")
    return reply, gate.decide(heard, reply)


async def respond(llms: list[LLM], system_prompt: str, gate: Gate, heard: str) -> tuple[str, Turn]:
    """One caller turn. Returns (the label and reply, the turn to speak).

    The live call and the evals both come through draft() and judge(), so they
    treat a failure the same way.
    """
    return judge(gate, heard, await draft(llms, system_prompt, gate.transcript, heard))
