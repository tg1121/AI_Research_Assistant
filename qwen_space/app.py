"""
DeepSeek-R1-Distill-Qwen-7B inference server.
Runs on GCP Cloud Run (L4 GPU).
Model is baked into the Docker image — no download on cold start.
"""
import json
import threading
import torch
import gradio as gr
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

MODEL_ID = "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B"

_model = None
_tokenizer = None
_lock = threading.Lock()


def _load():
    global _model, _tokenizer
    if _model is not None:
        return
    with _lock:
        if _model is not None:
            return
        print(f"Loading {MODEL_ID}...")
        bnb = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.bfloat16,
            bnb_4bit_use_double_quant=True,
        )
        _tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
        _model = AutoModelForCausalLM.from_pretrained(
            MODEL_ID,
            quantization_config=bnb,
            device_map="auto",
            attn_implementation="sdpa",
        )
        _model.eval()
        print("Model ready")


def generate(messages_json: str, max_tokens: int = 6000) -> str:
    _load()
    messages = json.loads(messages_json)
    text = _tokenizer.apply_chat_template(
        messages, tokenize=False, add_generation_prompt=True
    )
    inputs = _tokenizer([text], return_tensors="pt").to(_model.device)
    with torch.no_grad():
        output = _model.generate(
            **inputs,
            max_new_tokens=int(max_tokens),
            do_sample=False,
            pad_token_id=_tokenizer.eos_token_id,
        )
    new_tokens = output[0][inputs.input_ids.shape[1]:]
    return _tokenizer.decode(new_tokens, skip_special_tokens=True)


demo = gr.Interface(
    fn=generate,
    inputs=[
        gr.Textbox(label="messages_json"),
        gr.Number(label="max_tokens", value=6000, precision=0),
    ],
    outputs=gr.Textbox(label="response"),
    title="DeepSeek-R1-Distill-Qwen-7B — Research Pipeline",
    description="LLM inference endpoint. Set HF_SPACE_URL to this service URL.",
)

if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=7860, show_error=True)
