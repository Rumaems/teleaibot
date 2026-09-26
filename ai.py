import os
from dotenv import load_dotenv

load_dotenv()
from groq import AsyncGroq

client = AsyncGroq(api_key=os.environ["GROQ_API_KEY"])
MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

SYSTEM = """Ты — живой участник Telegram-чата по имени {bot_name}.
Твоя задача — разговаривать естественно, коротко и по-человечески.
Ты не должен постоянно отвечать и не должен превращать каждый разговор в консультацию.
Можно обсуждать игры, мемы, технику, погоду, обычные бытовые темы и всё, что обсуждают люди.
Не говори, что ты 'ИИ', если тебя об этом прямо не спросили.
Не выдумывай личный опыт, которого у тебя нет.
Пиши в основном 1–3 коротких предложения, если ситуация не требует большего.
Не начинай каждую реплику с имени собеседника.
Не используй канцелярит и пафос.
Если неуместно отвечать — используй NO_REPLY.
"""

async def _complete(messages):
    response = await client.chat.completions.create(
        model=MODEL,
        messages=messages,
        temperature=0.85,
        max_completion_tokens=350,
    )
    return (response.choices[0].message.content or "").strip()


async def should_speak(context, incoming, direct=False, bot_name="КПК"):
    if direct:
        return True

    prompt = """Реши, стоит ли тебе сейчас отвечать на сообщение в групповом чате.
Отвечай только одним словом: YES или NO.
Отвечай YES, если реплика явно приглашает к разговору, содержит вопрос/интересную тему,
естественно связана с тобой или тебе есть что коротко добавить.
NO — если лучше промолчать, сообщение служебное, односложное или ответ будет лишним.

КОНТЕКСТ:
{context}

ПОСЛЕДНЕЕ СООБЩЕНИЕ:
{incoming}
""".format(context=context, incoming=incoming)

    result = await _complete([
        {"role": "system", "content": SYSTEM.format(bot_name=bot_name)},
        {"role": "user", "content": prompt},
    ])
    return result.upper().startswith("YES")


async def chat(context, incoming, direct=False, bot_name="КПК", autonomous=False):
    extra = ""
    if autonomous:
        extra = "\nЭто самостоятельная реплика. Не притворяйся, что тебя кто-то спросил."
    prompt = f"""КОНТЕКСТ ГРУППОВОГО ЧАТА:
{context}

ТЕКУЩАЯ СИТУАЦИЯ:
{incoming}

Сформулируй естественный ответ.{extra}
Если отвечать действительно не стоит, верни ровно NO_REPLY.
"""
    result = await _complete([
        {"role": "system", "content": SYSTEM.format(bot_name=bot_name)},
        {"role": "user", "content": prompt},
    ])
    return result.strip()
