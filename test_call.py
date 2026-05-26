from groq import Groq
import json

client = Groq()

test_section = """
## Introduction
We propose a new method for image classification using neural networks.
The core idea is to minimize the loss function $L(\\theta) = \\sum_i (y_i - f(x_i; \\theta))^2$
where $\\theta$ are the model parameters, $x_i$ are inputs, and $y_i$ are labels.
Prior methods failed because they could not handle high-dimensional data efficiently.
Our approach achieves 95% accuracy on the benchmark dataset.
"""

response = client.chat.completions.create(
    model="llama-3.3-70b-versatile",
    temperature=0,
    max_tokens=1000,
    messages=[
        {
            "role": "system",
            "content": "You are explaining a research paper to someone with no scientific background. Use plain language only. No jargon without immediate explanation. No symbols. Return JSON only. No preamble."
        },
        {
            "role": "user",
            "content": f"""Read this section and answer these questions in plain English a curious 16-year-old would understand.
Return ONLY this JSON, nothing else:

{{
  "Q1_problem": "What was broken or impossible before?",
  "Q2_insight": "What was the clever idea?",
  "Q3_mechanism": "How does it work, described as a story with no symbols?"
}}

SECTION:
{test_section}"""
        }
    ]
)

raw = response.choices[0].message.content
print("RAW RESPONSE:")
print(raw)
print("\nPARSED:")
parsed = json.loads(raw)
for q, a in parsed.items():
    print(f"\n{q}:\n{a}")