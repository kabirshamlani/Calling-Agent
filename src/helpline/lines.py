"""Every fixed line the agent can say.

The model never writes these. It picks which one applies and the code speaks it,
so the wording is the same on every call and no caller can change it.
"""

GREETING = (
    "Hi, you've reached Wise transfer support. I'm an automated assistant. "
    "I can help with questions about where your money is. What would you like to know?"
)
HANDOFF = (
    "That's something a member of our team needs to help you with. "
    "I'm passing you to a human agent now. Thanks for calling."
)
GOODBYE = "Thanks for calling. Goodbye."
UNCLEAR = "Sorry, I didn't catch that. Could you say it again?"
STILL_THERE = "Are you still there?"
ONE_MOMENT = "One moment."

CHAT = {
    "greeting": "Hi. What would you like to know about your transfer?",
    "identity": "Yes, I'm an automated assistant. What would you like to know about your transfer?",
    "wait": "No problem, take your time.",
    "other": "I can help with questions about where your money is. What would you like to know?",
}
