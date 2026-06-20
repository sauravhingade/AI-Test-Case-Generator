import io
import fitz  # PyMuPDF — PDF parsing
import docx  # python-docx — DOCX parsing

from contextlib import asynccontextmanager
from dotenv import load_dotenv

from fastapi import FastAPI, UploadFile, File, HTTPException, Query
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware

from backend.schemas.models import (
    GenerateRequest,
    GenerateResponse,
    TestType,
    BDDFormat,
)
from backend.chains.extractor_chain import extract_user_stories
from backend.chains.generator_chain import generate_all_test_suites
from backend.chains.rag_chain import build_rag_context_map
from backend.rag.vectorstore import (
    index_all_suites,
    get_indexed_count,
    clear_vectorstore,
)
from backend.utils.exporter import export_as_json, export_as_csv, export_as_excel

load_dotenv()


# ── Lifespan ────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🚀 AI Test Generator starting up...")
    yield
    print("🛑 AI Test Generator shutting down...")


# ── App ─────────────────────────────────────────────────────

app = FastAPI(
    title="AI Test Case Generator",
    description="Generate BDD test cases from requirements using GPT-4o + RAG",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── In-memory store for last generated suites ───────────────

_last_suites = []


# ── Helpers ─────────────────────────────────────────────────


def _extract_text_from_pdf(file_bytes: bytes) -> str:
    """Extract text from PDF bytes using PyMuPDF."""
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    return "\n".join(page.get_text() for page in doc)


def _extract_text_from_docx(file_bytes: bytes) -> str:
    """Extract text from DOCX bytes using python-docx."""
    doc = docx.Document(io.BytesIO(file_bytes))
    return "\n".join(para.text for para in doc.paragraphs if para.text.strip())


def _run_pipeline(req: GenerateRequest) -> GenerateResponse:
    """
    Core pipeline:
    1. Extract user stories from requirements text
    2. Retrieve similar past test cases per story (RAG)
    3. Generate test suites with RAG context
    4. Index generated test cases back into RAG
    5. Return GenerateResponse
    """
    global _last_suites

    # Step 1 — Extract user stories
    user_story_list = extract_user_stories(req.requirements_text)

    # Step 2 — Build RAG context map per story
    # 1st request: RAG empty → no context, just generate
    # 2nd request onwards: similar past TCs injected as few-shot
    rag_map = build_rag_context_map(user_story_list.user_stories, k=3)

    # Step 3 — Generate test suites
    suites = generate_all_test_suites(
        user_stories=user_story_list.user_stories,
        request=req,
        similar_test_cases_map=rag_map,
    )

    # Step 4 — Index back into RAG for future requests
    index_all_suites(suites)

    # Step 5 — Store for export
    _last_suites = suites

    response = GenerateResponse(
        user_stories=user_story_list.user_stories,
        test_suites=suites,
        total_test_cases=sum(s.total_count for s in suites),
        total_user_stories=user_story_list.total_count,
        requirements_summary=user_story_list.summary,
    )

    # Save to SQLite

    return response


# ── Routes ──────────────────────────────────────────────────


@app.get("/health")
def health():
    """Health check — used by Docker and deployment platforms."""
    return {"status": "ok", "rag_indexed": get_indexed_count(), "version": "1.0.0"}


@app.post("/generate", response_model=GenerateResponse)
def generate_from_text(req: GenerateRequest):
    """
    Generate test cases from raw requirements text.

    Body:
        requirements_text        : str
        test_types               : list[TestType]  (optional)
        bdd_format               : BDDFormat        (optional)
        max_test_cases_per_story : int              (optional, 1-20)
    """
    if not req.requirements_text.strip():
        raise HTTPException(status_code=400, detail="requirements_text cannot be empty")

    try:
        return _run_pipeline(req)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/generate/file", response_model=GenerateResponse)
async def generate_from_file(
    file: UploadFile = File(...),
    test_types: list[TestType] = Query(
        default=[TestType.FUNCTIONAL, TestType.NEGATIVE, TestType.EDGE_CASE]
    ),
    bdd_format: BDDFormat = Query(default=BDDFormat.GHERKIN),
    max_test_cases_per_story: int = Query(default=5, ge=1, le=20),
):
    """
    Generate test cases from uploaded file (PDF, DOCX, or TXT).
    """
    file_bytes = await file.read()
    filename = file.filename.lower() if file.filename else ""

    if filename.endswith(".pdf"):
        text = _extract_text_from_pdf(file_bytes)
    elif filename.endswith(".docx"):
        text = _extract_text_from_docx(file_bytes)
    elif filename.endswith(".txt"):
        text = file_bytes.decode("utf-8")
    else:
        raise HTTPException(
            status_code=400, detail="Unsupported file type. Use PDF, DOCX, or TXT."
        )

    if not text.strip():
        raise HTTPException(status_code=400, detail="Could not extract text from file.")

    req = GenerateRequest(
        requirements_text=text,
        test_types=test_types,
        bdd_format=bdd_format,
        max_test_cases_per_story=max_test_cases_per_story,
    )

    try:
        return _run_pipeline(req)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/export/{format}")
def export_test_cases(format: str):
    """
    Export last generated test cases.
    format: json | csv | excel
    """
    if not _last_suites:
        raise HTTPException(
            status_code=404, detail="No test cases generated yet. Call /generate first."
        )

    if format == "json":
        return StreamingResponse(
            io.BytesIO(export_as_json(_last_suites)),
            media_type="application/json",
            headers={"Content-Disposition": "attachment; filename=test_cases.json"},
        )
    elif format == "csv":
        return StreamingResponse(
            io.BytesIO(export_as_csv(_last_suites)),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=test_cases.csv"},
        )
    elif format == "excel":
        return StreamingResponse(
            io.BytesIO(export_as_excel(_last_suites)),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": "attachment; filename=test_cases.xlsx"},
        )
    else:
        raise HTTPException(
            status_code=400, detail="Invalid format. Use: json | csv | excel"
        )


@app.delete("/rag/clear")
def clear_rag():
    """Clear all indexed test cases from RAG."""
    success = clear_vectorstore()
    return {"success": success, "message": "RAG vectorstore cleared."}


@app.get("/rag/stats")
def rag_stats():
    """Returns count of indexed test cases in RAG."""
    return {"indexed_test_cases": get_indexed_count()}
