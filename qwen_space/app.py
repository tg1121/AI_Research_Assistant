"""
ZeroGPU Gradio Space — Qwen 2.5 14B Instruct inference endpoint.

Called by the research pipeline at paper ingestion time.
API: POST /api/predict  {"data": ["<messages_json>", max_tokens]}
     → {"data": ["<response_text>"]}
"""
import json
import torch
import spaces
import gradio as gr
from transformers import AutoModelForCausalLM, AutoTokenizer

MODEL_ID = "Qwen/Qwen2.5-14B-Instruct"

tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
_model = None


def _load():
    global _model
    if _model is None:
        _model = AutoModelForCausalLM.from_pretrained(
            MODEL_ID,
            torch_dtype=torch.bfloat16,
            device_map="auto",
        )


@spaces.GPU(duration=300)
def generate(messages_json: str, max_tokens: int = 6000) -> str:
    _load()
    messages = json.loads(messages_json)
    text = tokenizer.apply_chat_template(
        messages, tokenize=False, add_generation_prompt=True
    )
    inputs = tokenizer([text], return_tensors="pt").to(_model.device)
    with torch.no_grad():
        output = _model.generate(
            **inputs,
            max_new_tokens=max_tokens,
            do_sample=False,
            pad_token_id=tokenizer.eos_token_id,
        )
    new_tokens = output[0][inputs.input_ids.shape[1]:]
    return tokenizer.decode(new_tokens, skip_special_tokens=True)


demo = gr.Interface(
    fn=generate,
    inputs=[
        gr.Textbox(label="messages_json"),
        gr.Number(label="max_tokens", value=6000, precision=0),
    ],
    outputs=gr.Textbox(label="response"),
    title="Qwen 2.5 14B — Research Pipeline Inference",
    description="Internal LLM endpoint for knowledge graph extraction. Set HF_SPACE_URL in your .env to point here.",
)

if __name__ == "__main__":
    demo.launch()
