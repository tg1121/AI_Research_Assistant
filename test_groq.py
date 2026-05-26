from groq import Groq
import json

client = Groq()
response = client.chat.completions.create(
    model="llama-3.3-70b-versatile",
    temperature=0,
    max_tokens=100,
    messages=[
        {"role": "system", "content": "Return JSON only."},
        {"role": "user", "content": 'Return this exact JSON: {"status": "ok", "model": "working"}'}
    ]
)
raw = response.choices[0].message.content.strip()
raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
parsed = json.loads(raw)
print(f"GROQ LIVE CALL OK: {parsed}")