"""
Qwen 2.5 7B Instruct — OpenAI-compatible inference server.
POST /v1/chat/completions — same interface as any OpenAI provider.
Model is baked into the Docker image; lazy-loaded on first request.
"""
import threading
import time
import uuid
from typing import Any, Dict, List, Optional

import torch
import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

MODEL_ID = "Qwen/Qwen2.5-7B-Instruct"

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


app = FastAPI(title="Qwen 2.5 7B — Research Pipeline")


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    model: str = MODEL_ID
    messages: List[ChatMessage]
    max_tokens: Optional[int] = 6000
    temperature: Optional[float] = 0.0
    tools: Optional[List[Dict[str, Any]]] = None


@app.get("/health")
def health():
    return {"status": "ok", "model_loaded": _model is not None}


@app.post("/v1/chat/completions")
def chat_completions(req: ChatCompletionRequest):
    _load()
    messages = [{"role": m.role, "content": m.content} for m in req.messages]

    kwargs = {}
    if req.tools:
        kwargs["tools"] = req.tools

    text = _tokenizer.apply_chat_template(
        messages, tokenize=False, add_generation_prompt=True, **kwargs
    )
    inputs = _tokenizer([text], return_tensors="pt").to(_model.device)

    with torch.no_grad():
        output = _model.generate(
            **inputs,
            max_new_tokens=int(req.max_tokens),
            do_sample=req.temperature > 0,
            temperature=req.temperature if req.temperature > 0 else None,
            pad_token_id=_tokenizer.eos_token_id,
        )

    new_tokens = output[0][inputs.input_ids.shape[1]:]
    content = _tokenizer.decode(new_tokens, skip_special_tokens=True)

    return {
        "id": f"chatcmpl-{uuid.uuid4().hex}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": MODEL_ID,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": inputs.input_ids.shape[1],
            "completion_tokens": len(new_tokens),
            "total_tokens": inputs.input_ids.shape[1] + len(new_tokens),
        },
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=7860)
