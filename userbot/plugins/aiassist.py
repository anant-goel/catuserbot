# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~# CatUserBot Plugin #~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~#
# aiassist.py — Modern, provider-agnostic AI assistant for catuserbot
#
# This COMPLEMENTS the existing plugins; it does not replace them:
#   - openai.py already gives you `.gpt` (OpenAI-only, older gpt-3.5 models)
#   - aitools.py already gives you `.genimg` (AI image generation)
# This plugin adds three REACTIVE commands that work with ANY OpenAI-compatible
# backend (OpenAI, Groq, OpenRouter, Together, or a local Ollama / LM Studio),
# so you can use newer/free models without touching the existing setup:
#     .ask <question>        -> ask an AI model anything (or reply to a message)
#     .summarize [count]     -> AI summary of the last N *messages* in this chat
#                               (the built-in chatfs only counts files/sizes)
#     .rewrite [instruction] -> rewrite the replied-to message (clearer/formal/translate)
#
# Every command is REACTIVE — it only runs when *you* type it — which is the
# design that keeps the account from looking like a spammer.
#
# SETUP — add these to your .env file (already documented in .env.sample):
#     AI_API_KEY   = your key                       (required)
#     AI_BASE_URL  = https://api.openai.com/v1      (default; change per provider)
#     AI_MODEL     = gpt-4o-mini                    (default; change per provider)
#
#   Groq      -> AI_BASE_URL=https://api.groq.com/openai/v1   AI_MODEL=llama-3.3-70b-versatile
#   OpenRouter-> AI_BASE_URL=https://openrouter.ai/api/v1     AI_MODEL=anthropic/claude-3.5-sonnet
#   Ollama    -> AI_BASE_URL=http://localhost:11434/v1        AI_MODEL=llama3.1  (AI_API_KEY=ollama)
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~#

import os

import aiohttp
from telethon.errors import FloodWaitError
from telethon.utils import get_display_name

from userbot import catub

from ..core.managers import edit_delete, edit_or_reply

plugin_category = "tools"

# --- Config (read from environment; .env is loaded by Config/config.py) -------------------
AI_API_KEY = os.environ.get("AI_API_KEY")
AI_BASE_URL = os.environ.get("AI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
AI_MODEL = os.environ.get("AI_MODEL", "gpt-4o-mini")

TG_LIMIT = 4096  # Telegram single-message character cap
MAX_SUMMARY_MESSAGES = 500  # hard cap so summarize never hammers the API / trips FloodWait


async def _call_ai(prompt, system=None):
    """Send one prompt to an OpenAI-compatible chat endpoint and return the text reply."""
    if not AI_API_KEY:
        return (
            "❌ `AI_API_KEY` is not set.\n\n"
            "Add it to your `.env` file, e.g.:\n"
            "`AI_API_KEY = \"sk-your-key\"`"
        )

    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    headers = {
        "Authorization": f"Bearer {AI_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": AI_MODEL,
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": 1500,
    }

    timeout = aiohttp.ClientTimeout(total=90)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                f"{AI_BASE_URL}/chat/completions", headers=headers, json=payload
            ) as resp:
                data = await resp.json()
                if resp.status != 200:
                    err = data.get("error", {})
                    msg = err.get("message") if isinstance(err, dict) else data
                    return f"❌ API error ({resp.status}): `{msg}`"
                return data["choices"][0]["message"]["content"].strip()
    except aiohttp.ClientError as e:
        return f"❌ Network error: `{e}`"
    except Exception as e:  # noqa: BLE001
        return f"❌ Unexpected error: `{e}`"


async def _send_long(cat, text: str):
    """Edit the status message with the reply; chunk into follow-ups if it's too long."""
    if len(text) <= TG_LIMIT:
        return await edit_or_reply(cat, text)
    chunks = [text[i : i + TG_LIMIT] for i in range(0, len(text), TG_LIMIT)]
    await edit_or_reply(cat, chunks[0])
    for chunk in chunks[1:]:
        try:
            await cat.respond(chunk)
        except FloodWaitError as e:
            return await cat.respond(
                f"⚠️ Hit a Telegram rate limit, stopping. Wait {e.seconds}s."
            )


@catub.cat_cmd(
    pattern=r"ask(?:\s|$)([\s\S]*)",
    command=("ask", plugin_category),
    info={
        "header": "Ask an AI model anything (provider-agnostic).",
        "description": "Sends your question to the configured AI backend and replies inline. "
        "Reply to a message with .ask to use that message as the question. "
        "Unlike .gpt this works with Groq/OpenRouter/Ollama and newer models.",
        "usage": [
            "{tr}ask <your question>",
            "{tr}ask  (as a reply to a message)",
        ],
    },
)
async def ask_handler(event):
    query = (event.pattern_match.group(1) or "").strip()
    if not query and event.reply_to_msg_id:
        replied = await event.get_reply_message()
        query = (replied.text or "").strip()
    if not query:
        return await edit_delete(event, "`Give me a question, or reply to a message.`", 8)

    cat = await edit_or_reply(event, "🤔 `Thinking...`")
    answer = await _call_ai(query)
    await _send_long(cat, answer)


@catub.cat_cmd(
    pattern=r"summarize(?:\s|$)(\d*)",
    command=("summarize", plugin_category),
    info={
        "header": "AI summary of the recent conversation in this chat.",
        "description": "Reads the last N text messages (default 100, max 500) and returns a "
        "concise AI summary. The built-in chatfs only counts media/files; this summarizes "
        "what people actually said. Great for catching up on busy groups.",
        "usage": [
            "{tr}summarize",
            "{tr}summarize 250",
        ],
    },
)
async def summarize_handler(event):
    raw = event.pattern_match.group(1)
    count = int(raw) if raw else 100
    count = max(1, min(count, MAX_SUMMARY_MESSAGES))

    cat = await edit_or_reply(event, f"📖 `Reading the last {count} messages...`")

    lines = []
    try:
        async for msg in event.client.iter_messages(event.chat_id, limit=count):
            if not msg.text:
                continue
            name = get_display_name(msg.sender) or "Unknown"
            lines.append(f"{name}: {msg.text}")
    except FloodWaitError as e:
        return await edit_delete(
            cat, f"⚠️ `Telegram asked to slow down. Try again in {e.seconds}s.`", 10
        )

    if not lines:
        return await edit_delete(cat, "`No text messages found to summarize.`", 8)

    lines.reverse()  # chronological order
    transcript = "\n".join(lines)

    system = (
        "You are summarizing a Telegram chat. Give a concise summary: the main topics, "
        "any decisions or action items, and who said what only when it matters. "
        "Use short bullet points. Do not invent anything not in the transcript."
    )
    summary = await _call_ai(transcript, system=system)
    await _send_long(cat, f"📝 **Summary of the last {count} messages:**\n\n{summary}")


@catub.cat_cmd(
    pattern=r"rewrite(?:\s|$)([\s\S]*)",
    command=("rewrite", plugin_category),
    info={
        "header": "Rewrite the replied-to message with AI.",
        "description": "Reply to any message with .rewrite to get a cleaner version. "
        "Add an instruction to control the style (formal, shorter, translate, etc.).",
        "usage": [
            "{tr}rewrite  (as a reply — defaults to clearer + fixed grammar)",
            "{tr}rewrite make it formal  (as a reply)",
            "{tr}rewrite translate to Spanish  (as a reply)",
        ],
    },
)
async def rewrite_handler(event):
    if not event.reply_to_msg_id:
        return await edit_delete(event, "`Reply to a message you want rewritten.`", 8)

    replied = await event.get_reply_message()
    source = (replied.text or "").strip()
    if not source:
        return await edit_delete(event, "`That message has no text to rewrite.`", 8)

    instruction = (event.pattern_match.group(1) or "").strip()
    if not instruction:
        instruction = "Rewrite this more clearly and fix any grammar/spelling, keeping the meaning."

    cat = await edit_or_reply(event, "✍️ `Rewriting...`")
    system = (
        "You rewrite text. Return ONLY the rewritten text with no preamble, no quotes, "
        "and no explanation."
    )
    prompt = f"Instruction: {instruction}\n\nText:\n{source}"
    result = await _call_ai(prompt, system=system)
    await _send_long(cat, result)
