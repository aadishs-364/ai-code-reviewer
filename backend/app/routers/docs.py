from fastapi import APIRouter

from app.review.engine import run_docs
from app.schemas import DocRequest, DocResponse

router = APIRouter(prefix="/docs", tags=["documentation"])


@router.post("/generate", response_model=DocResponse)
def generate(req: DocRequest) -> DocResponse:
    result = run_docs(
        code=req.code,
        filename=req.filename,
        language=req.language,
        style=req.style,
    )
    return DocResponse(**result)
