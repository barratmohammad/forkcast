"""The /ask endpoint: grounded recipe Q&A."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from auth import get_current_user
from config import get_settings
from database import get_db
from ollama_client import get_llm
from rag_pipeline import RecipeIndex, answer_question, get_index
from schemas import AskRequest, AskResponse

router = APIRouter(tags=["ask"], dependencies=[Depends(get_current_user)])


@router.post("/ask", response_model=AskResponse)
def ask(
    body: AskRequest,
    db: Session = Depends(get_db),
    index: RecipeIndex = Depends(get_index),
    llm=Depends(get_llm),
) -> AskResponse:
    """Answer a cooking question using only recipes retrieved from the collection."""
    settings = get_settings()
    return answer_question(
        db, index, llm, body.question, body.tags, settings.rag_top_k, settings.rag_max_distance
    )
