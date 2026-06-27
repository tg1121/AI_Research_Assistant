"""
Qwen 2.5 14B inference server.
Runs on GCP Cloud Run (L4 GPU) or locally.
API: POST /api/predict  {"data": ["<messages_json>", max_tokens]}
     -> {"data": ["<response_text>"]}
"""
import json
import torch
import gradio as gr
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

MODEL_ID = "Qwen/Qwen2.5-14B-Instruct"

bnb = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_quant_type="nf4",
    bnb_4bit_compute_dtype=torch.bfloat16,
    bnb_4bit_use_double_quant=True,
)

print(f"Loading {MODEL_ID}...")
tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
model = AutoModelForCausalLM.from_pretrained(
    MODEL_ID,
    quantization_config=bnb,
    device_map="auto",
    attn_implementation="sdpa",
)
model.eval()
print("Model ready")


def generate(messages_json: str, max_tokens: int = 6000) -> str:
    messages = json.loads(messages_json)
    text = tokenizer.apply_chat_template(
        messages, tokenize=False, add_generation_prompt=True
    )
    inputs = tokenizer([text], return_tensors="pt").to(model.device)
    with torch.no_grad():
        output = model.generate(
            **inputs,
            max_new_tokens=int(max_tokens),
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
    title="Qwen 2.5 14B — Research Pipeline",
    description="LLM inference endpoint. Set HF_SPACE_URL to this service URL.",
)

if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=7860, show_error=True)
