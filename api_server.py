"""
api_server.py - Mock RAG Retrieval API (테스트용)

GET  /health   → {"status": "ok", "ready": true}
POST /retrieve → 하드코딩된 contexts 반환 (실제 검색 없음)
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="Mock RAG Retrieval API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

MOCK_CONTEXTS = [
    {
        "text": "제 2 조(적용범위) 연구비 지원기관의 별도 기준이나 지침이 있는 경우를 제외하고는 연구비 관리 업무처리에 관한 사항은 이 지침을 따른다.",
        "source": "Policy.pdf",
        "score": 0.85,
    },
    {
        "text": "제 3 조(역할 및 절차) 산학협력단은 연구과제 안내에서부터 협약, 연구비 청구 및 사후관리 등 연구자가 원활하게 연구를 수행할 수 있도록 지원한다.",
        "source": "Policy.pdf",
        "score": 0.78,
    },
    {
        "text": "비기능 요구사항: 시스템은 99.9% 이상의 가용성을 보장해야 하며, 응답 시간은 2초 이내여야 한다.",
        "source": "SRS.docx",
        "score": 0.71,
    },
    {
        "text": "Python is a high-level, general-purpose programming language. Its design philosophy emphasizes code readability with the use of significant indentation.",
        "source": "Wikipedia",
        "score": 0.65,
    },
    {
        "text": "연구책임자는 연구과제의 각종 보고와 연구비 집행 및 정산에 관한 사항에 대해 주관하여 수행한다.",
        "source": "Policy.pdf",
        "score": 0.61,
    },
]


@app.get("/health")
def health():
    return {"status": "ok", "ready": True}


class RetrieveRequest(BaseModel):
    question: str
    top_k: int = 5


@app.post("/retrieve")
def retrieve(req: RetrieveRequest):
    return {"contexts": MOCK_CONTEXTS[: req.top_k]}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api_server:app", host="0.0.0.0", port=8000, reload=False)
