from pydantic import BaseModel
from typing import Optional


class LoginRequest(BaseModel):
    email: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    user_id: str
    email: str


class SignupResponse(BaseModel):
    access_token: Optional[str] = None
    user_id: Optional[str] = None
    email: str
    confirm_email: bool = False


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


class MarkerDecisionRequest(BaseModel):
    use_marker: bool
    datalab_key: Optional[str] = None


class ChatRequest(BaseModel):
    question: str
    reader_params: dict = {}
    model: str = "openrouter/openai/gpt-oss-120b:free"
    api_key: Optional[str] = None
    paper_ids: list[str] = []  # all open papers; enables multi-paper context
    prior_messages: list[dict] = []  # frontend-saved history; restores backend state after restart


class ChatResponse(BaseModel):
    answer: str
    messages: list[dict]
