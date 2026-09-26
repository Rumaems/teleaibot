import json
import os
from dotenv import load_dotenv
load_dotenv()
from groq import AsyncGroq

client = AsyncGroq(api_key=os.environ["GROQ_API_KEY"])
MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")

SYSTEM = """Ты — КПК, живой и естественный участник Telegram-чата.
Разговаривай естественно: замечай контекст, помни собеседников, подхватывай темы,
задавай уместные вопросы и иногда сам начинай разговор.
Не отвечай механически на каждое сообщение. Если ответа не требуется — NO_REPLY.
Не говори, что ты ИИ, если тебя прямо не спросили. Не выдумывай реальный личный опыт.
Пиши без канцелярита и шаблонов. Обычно 1–4 коротких предложения.
Не повторяй одну и ту же мысль. Не начинай каждую реплику с имени человека.
Можно обсуждать игры, мемы, технику, погоду, бытовые темы и темы из чата.
Если человек явно обращается к тебе — отвечай. Если разговор идёт, можешь задать встречный вопрос.
"""

async def _complete(messages, max_tokens=450, temperature=0.9):
    response = await client.chat.completions.create(
        model=MODEL,
        messages=messages,
        temperature=temperature,
        max_completion_tokens=max_tokens,
    )
    return (response.choices[0].message.content or "").strip()

async def should_speak(context, incoming, direct=False, bot_name="КПК"):
    if direct:
        return True
    prompt = f"""Реши, стоит ли сейчас естественно участвовать в разговоре.
Отвечай только YES или NO.
YES — если есть вопрос, шутка, эмоция, интересная тема или естественный повод добавить короткую реплику.
NO — если сообщение служебное, слишком личное между людьми, односложное или ответ будет спамом.
Не требуй обязательного обращения к боту.

КОНТЕКСТ:
{context}

ПОСЛЕДНЕЕ СООБЩЕНИЕ:
{incoming}"""
    result = await _complete([
        {"role": "system", "content": SYSTEM.format(bot_name=bot_name)},
        {"role": "user", "content": prompt},
    ], max_tokens=8, temperature=0.2)
    return result.upper().startswith("YES")

async def chat(context, incoming, direct=False, bot_name="КПК", autonomous=False):
    if autonomous:
        prompt = f"""КОНТЕКСТ ГРУППОВОГО ЧАТА:
{context}

В чате некоторое время тихо. Сам начни короткую реплику только если есть естественный повод.
Можно поздороваться, спросить продолжение темы, вернуться к недавнему обсуждению,
пошутить или поднять лёгкую новую тему. Не притворяйся, что тебя только что спросили.
Если хорошего повода нет — верни ровно NO_REPLY. Если пишешь — 1–3 живых предложения."""
    else:
        prompt = f"""КОНТЕКСТ ГРУППОВОГО ЧАТА:
{context}

ТЕКУЩАЯ СИТУАЦИЯ:
{incoming}

Ответь естественно и по смыслу. Если уместно, добавь короткий встречный вопрос или продолжи тему.
Если отвечать действительно не стоит — верни ровно NO_REPLY."""
    return (await _complete([
        {"role": "system", "content": SYSTEM.format(bot_name=bot_name)},
        {"role": "user", "content": prompt},
    ])).strip()

async def extract_facts(context):
    prompt = f"""Извлеки только устойчивые факты, которые помогут в будущих разговорах.
Только явно сказанные факты: имя/как обращаться, хобби, любимые игры, долгосрочные проекты,
устойчивые предпочтения. Не сохраняй пароли, токены, адреса, здоровье, финансы,
политические предпочтения или другие чувствительные данные. Не додумывай.
Верни JSON: [{{"username":"...","fact":"..."}}]. Если ничего нового — [].

КОНТЕКСТ:
{context}"""
    result = await _complete([
        {"role": "system", "content": "Ты аккуратный модуль долговременной памяти. Не выдумывай факты."},
        {"role": "user", "content": prompt},
    ], max_tokens=500, temperature=0.1)
    try:
        text = result.strip().replace("```json", "").replace("```", "").strip()
        data = json.loads(text)
        return data if isinstance(data, list) else []
    except Exception:
        return []
