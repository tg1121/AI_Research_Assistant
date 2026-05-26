import os
import uuid
from supabase import create_client

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# How much expertise shifts on feedback
FEEDBACK_SHIFT = 0.15
# How many corrections before default shifts
THRESHOLD = 3

def create_session(paper_id: str) -> dict:
    """Create a new session with default parameters."""
    defaults = get_global_defaults()
    
    session = {
        "paper_id": paper_id,
        "reader_expertise": defaults["reader_expertise"],
        "scientific_knowledge": defaults["scientific_knowledge"],
        "language_complexity": defaults["language_complexity"]
    }
    
    result = supabase.table("sessions").insert(session).execute()
    return result.data[0]

def get_session(session_id: str) -> dict:
    """Get session by ID."""
    result = supabase.table("sessions").select("*").eq("id", session_id).execute()
    return result.data[0] if result.data else None

def update_session_parameters(session_id: str, reader_expertise: float,
                               scientific_knowledge: float = None,
                               language_complexity: float = None) -> dict:
    """Update session parameters. If scientific_knowledge and language_complexity
    are None they follow reader_expertise proportionally."""
    
    if scientific_knowledge is None:
        scientific_knowledge = reader_expertise
    if language_complexity is None:
        language_complexity = reader_expertise

    # clamp all values between 0 and 1
    reader_expertise = max(0.0, min(1.0, reader_expertise))
    scientific_knowledge = max(0.0, min(1.0, scientific_knowledge))
    language_complexity = max(0.0, min(1.0, language_complexity))

    result = supabase.table("sessions").update({
        "reader_expertise": reader_expertise,
        "scientific_knowledge": scientific_knowledge,
        "language_complexity": language_complexity,
        "updated_at": "now()"
    }).eq("id", session_id).execute()

    return result.data[0]

def record_feedback(session_id: str, paper_id: str, question: str,
                    direction: str, reason: str, expertise_before: float,
                    expertise_after: float):
    """Record a feedback event."""
    supabase.table("feedback").insert({
        "session_id": session_id,
        "paper_id": paper_id,
        "question": question,
        "direction": direction,
        "reason": reason,
        "expertise_before": expertise_before,
        "expertise_after": expertise_after
    }).execute()

    # check if global defaults should update
    _check_and_update_defaults(question, direction)

def apply_feedback(session: dict, direction: str) -> dict:
    """
    Apply feedback to session parameters.
    direction: 'too_technical' | 'too_simple' | 'language_too_hard' | 'more_math'
    Returns updated session.
    """
    expertise = session["reader_expertise"]
    sci = session["scientific_knowledge"]
    lang = session["language_complexity"]

    if direction == "too_technical":
        # both parameters down together
        expertise = expertise - FEEDBACK_SHIFT
        sci = expertise
        lang = expertise
    elif direction == "too_simple":
        # both parameters up together
        expertise = expertise + FEEDBACK_SHIFT
        sci = expertise
        lang = expertise
    elif direction == "language_too_hard":
        # decouple — only language down
        lang = lang - FEEDBACK_SHIFT
    elif direction == "more_math":
        # decouple — only scientific knowledge up
        sci = sci + FEEDBACK_SHIFT

    return update_session_parameters(session["id"], expertise, sci, lang)

def get_global_defaults() -> dict:
    """Get current global default parameters."""
    result = supabase.table("parameter_defaults").select("*").limit(1).execute()
    if result.data:
        return result.data[0]
    return {"reader_expertise": 0.0, "scientific_knowledge": 0.0, "language_complexity": 0.0}

def _check_and_update_defaults(question: str, direction: str):
    """Check if enough feedback exists to update global defaults."""
    result = supabase.table("feedback").select("id").eq(
        "direction", direction
    ).execute()

    count = len(result.data)

    if count >= THRESHOLD and count % THRESHOLD == 0:
        # enough signal — shift global defaults
        defaults = get_global_defaults()
        shift = FEEDBACK_SHIFT if "simple" in direction or "math" in direction else -FEEDBACK_SHIFT
        new_expertise = max(0.0, min(1.0, defaults["reader_expertise"] + shift))

        supabase.table("parameter_defaults").update({
            "reader_expertise": new_expertise,
            "scientific_knowledge": new_expertise,
            "language_complexity": new_expertise,
            "sample_count": count,
            "updated_at": "now()"
        }).eq("id", defaults["id"]).execute()

        print(f"Global defaults updated: reader_expertise → {new_expertise}")
        