from pydantic import BaseModel
from typing import Optional


class UploadResponse(BaseModel):
    paper_id: str
    status: str


class StatusResponse(BaseModel):
    paper_id: str
    status: str
    progress_pct: int
    progress_text: str
    error: Optional[str] = None
    detected_domain: Optional[str] = None


class ChatRequest(BaseModel):
    question: str
    reader_params: dict = {}
    model: str = "groq/llama-3.3-70b-versatile"
    api_key: Optional[str] = None


class ChatResponse(BaseModel):
    answer: str
    messages: list[dict]
