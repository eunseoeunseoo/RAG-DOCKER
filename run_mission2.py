"""
run_mission2.py - Mission 2: RAG Top-10 실패 케이스 발굴

실행 방법:
    python run_mission2.py

출력:
    - storage/         : VectorStoreIndex 영속화
    - mission2_log.md  : 실패 케이스별 Top-10 검색 결과 (score, 200자, metadata)
"""

import sys
# Windows 콘솔 UTF-8 출력
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import os
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
from llama_index.core import (
    Document,
    Settings,
    SimpleDirectoryReader,
    StorageContext,
    VectorStoreIndex,
    load_index_from_storage,
)
from llama_index.core.node_parser import SimpleNodeParser
from llama_index.core.readers.base import BaseReader
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.readers.file import DocxReader, FlatReader, HWPReader, PDFReader
from llama_index.readers.wikipedia import WikipediaReader


# ── 커스텀 Reader ─────────────────────────────────────────────────────────────

class XlsxReader(BaseReader):
    def load_data(self, file, extra_info=None):
        file_path = str(file)
        xls = pd.ExcelFile(file_path, engine="openpyxl")
        documents = []
        for sheet_name in xls.sheet_names:
            df = pd.read_excel(file_path, sheet_name=sheet_name, engine="openpyxl")
            try:
                text = df.to_markdown(index=False)
            except ImportError:
                text = df.to_string(index=False)
            metadata = {
                "file_name": Path(file_path).name,
                "file_path": file_path,
                "file_type": ".xlsx",
                "sheet_name": sheet_name,
            }
            if extra_info:
                metadata.update(extra_info)
            documents.append(Document(text=text, metadata=metadata))
        return documents


class OCRImageReader(BaseReader):
    def load_data(self, file, extra_info=None):
        try:
            import pytesseract
            from PIL import Image
            image = Image.open(str(file))
            text = pytesseract.image_to_string(image, lang="kor+eng")
        except Exception as exc:
            text = f"[OCR failed: {exc}]"
        metadata = {
            "file_name": Path(str(file)).name,
            "file_path": str(file),
            "file_type": ".png",
        }
        if extra_info:
            metadata.update(extra_info)
        return [Document(text=text, metadata=metadata)]


# ── VectorStoreIndex 구축 / 로드 ──────────────────────────────────────────────

STORAGE_DIR = "./storage"


def build_or_load_index() -> VectorStoreIndex:
    Settings.embed_model = HuggingFaceEmbedding(model_name="all-MiniLM-L6-v2")
    Settings.llm = None  # 검색 실패 분석이 목적 — LLM 불필요

    if Path(STORAGE_DIR).exists() and any(Path(STORAGE_DIR).iterdir()):
        print(f"[INFO] Loading index from {STORAGE_DIR} ...")
        storage_context = StorageContext.from_defaults(persist_dir=STORAGE_DIR)
        index = load_index_from_storage(storage_context)
        print("[INFO] Index loaded from storage.")
        return index

    print("[INFO] Building VectorStoreIndex from scratch ...")
    parser = SimpleNodeParser.from_defaults(chunk_size=256, chunk_overlap=50)

    # Wikipedia (User-Agent 설정 후 최대 3회 재시도)
    import wikipedia as _wp
    _wp.set_user_agent("run_mission2/1.0 (RAG study project)")
    wiki_docs = []
    for attempt in range(3):
        try:
            wiki_docs = WikipediaReader().load_data(pages=["Python (programming language)"])
            break
        except Exception as exc:
            print(f"  Wikipedia load attempt {attempt + 1} failed: {exc}")
            if attempt == 2:
                print("  Wikipedia load failed - using local files only")
    wiki_nodes = parser.get_nodes_from_documents(wiki_docs)
    print(f"  Wikipedia: {len(wiki_nodes)} nodes")

    # 로컬 파일
    file_extractor = {
        ".txt": FlatReader(),
        ".pdf": PDFReader(),
        ".docx": DocxReader(),
        ".xlsx": XlsxReader(),
        ".hwp": HWPReader(),
        ".png": OCRImageReader(),
    }
    local_reader = SimpleDirectoryReader(
        input_dir="data",
        file_extractor=file_extractor,
        required_exts=[".txt", ".pdf", ".docx", ".xlsx", ".hwp", ".png"],
    )
    local_docs = local_reader.load_data()
    local_nodes = parser.get_nodes_from_documents(local_docs)
    print(f"  Local data/: {len(local_nodes)} nodes")

    all_nodes = wiki_nodes + local_nodes
    print(f"  Total: {len(all_nodes)} nodes")

    index = VectorStoreIndex(all_nodes)
    index.storage_context.persist(STORAGE_DIR)
    print(f"[INFO] Index persisted to {STORAGE_DIR}/")
    return index


# ── 실패 케이스 정의 ──────────────────────────────────────────────────────────

@dataclass
class FailureCase:
    id: int
    category: str
    question: str
    expected_source: str   # 정답이 있어야 할 파일명
    expected_keyword: str  # 정답 노드에 있어야 할 핵심 키워드
    failure_reason: str    # 예상 실패 원인


CASES: list[FailureCase] = [
    FailureCase(
        id=1, category="구조적 위치 질의",
        question="Policy.pdf에서 5조 3항의 내용을 그대로 인용해줘.",
        expected_source="Policy.pdf",
        expected_keyword="5조",
        failure_reason="chunk_size=256 으로 인해 조항 번호와 본문이 서로 다른 청크로 분리되어 "
                       "'5조 3항'이라는 키워드가 포함된 청크가 top-10 안에 들어오지 않음.",
    ),
    FailureCase(
        id=2, category="표 셀 좌표 질의",
        question="CRA.xlsx에서 첫 번째 시트의 3행 2열 값은 무엇인가?",
        expected_source="CRA.xlsx",
        expected_keyword="3행",
        failure_reason="to_markdown() 변환으로 행 번호가 사라지고 헤더만 남아 "
                       "'3행 2열'이라는 좌표 기반 질문에 대응하는 청크가 검색되지 않음.",
    ),
    FailureCase(
        id=3, category="멀티홉 — 교차 문서",
        question="Policy.pdf의 연구비 지침과 SRS.docx의 비기능 요구사항이 공통으로 언급하는 원칙은?",
        expected_source="Policy.pdf",
        expected_keyword="원칙",
        failure_reason="두 문서의 청크가 동시에 top-10에 들어와야 답할 수 있는 멀티홉 질문. "
                       "단일 임베딩 유사도로는 두 문서를 동시에 연결하는 청크를 선택 불가.",
    ),
    FailureCase(
        id=4, category="이미지 OCR 품질 의존",
        question="Image.png 파일에서 OCR로 추출된 텍스트의 두 번째 문단 첫 문장은?",
        expected_source="Image.png",
        expected_keyword="",
        failure_reason="pytesseract OCR 품질이 낮으면 문단 구분 자체가 깨지거나 노이즈 문자가 섞여 "
                       "질문의 '두 번째 문단'에 해당하는 청크가 생성되지 않음.",
    ),
    FailureCase(
        id=5, category="HWP 그림 캡션",
        question="DESIGN.hwp에 포함된 그림 2의 캡션을 알려줘.",
        expected_source="DESIGN.hwp",
        expected_keyword="그림",
        failure_reason="HWPReader가 그림 캡션을 텍스트로 추출하지 못해 "
                       "해당 내용이 아예 인덱스에 없으므로 top-10에 등장 불가.",
    ),
    FailureCase(
        id=6, category="한영 언어 불일치",
        question="파이썬의 GIL(전역 인터프리터 잠금)이 멀티스레딩 성능에 미치는 영향은?",
        expected_source="Wikipedia",
        expected_keyword="GIL",
        failure_reason="한국어 질문을 영어 Wikipedia 청크와 매칭할 때 "
                       "all-MiniLM-L6-v2 임베딩의 다국어 정렬이 약해 "
                       "GIL 관련 영문 청크가 top-10 하위권에 위치.",
    ),
    FailureCase(
        id=7, category="수치 집계",
        question="SRS.docx에서 비기능 요구사항 항목은 총 몇 개인가?",
        expected_source="SRS.docx",
        expected_keyword="비기능",
        failure_reason="개수 집계를 위해서는 비기능 요구사항 목록 전체가 포함된 청크가 필요하나 "
                       "chunk_size=256 으로 목록이 여러 청크에 분산되어 단일 청크에서 전체 개수 파악 불가.",
    ),
    FailureCase(
        id=8, category="청크 경계 분리",
        question="Text.txt 문서의 마지막 문장을 정확히 인용해줘.",
        expected_source="Text.txt",
        expected_keyword="",
        failure_reason="마지막 문장이 마지막 청크에 있지만 '마지막 문장'이라는 의미론적 질문으로는 "
                       "해당 청크의 임베딩 유사도가 낮아 top-10 안에 들어오지 못함. "
                       "위치 기반 검색은 벡터 검색의 맹점.",
    ),
    FailureCase(
        id=9, category="범위 초과 — 인덱스 외 정보",
        question="이 RAG 시스템에서 사용하는 벡터 DB의 이름과 버전은?",
        expected_source="없음",
        expected_keyword="",
        failure_reason="시스템 내부 구현 정보는 어떤 문서에도 포함되지 않아 "
                       "top-10 내 모든 청크가 관련 없는 노드로 채워짐 (완전한 범위 초과).",
    ),
    FailureCase(
        id=10, category="환각 유발 — 존재하지 않는 수치",
        question="Policy.pdf에 명시된 연구비 총 예산 규모(숫자)는 정확히 얼마인가?",
        expected_source="Policy.pdf",
        expected_keyword="예산",
        failure_reason="문서에 구체적 예산 수치가 없으므로 관련 청크가 top-10에 오더라도 "
                       "숫자를 포함하지 않아 LLM이 환각을 일으키거나 '없음'으로 응답해야 함. "
                       "Retrieval 자체는 일부 성공하나 근거 노드에 정답이 없는 케이스.",
    ),
]


# ── 검색 실행 & 로그 생성 ─────────────────────────────────────────────────────

def run_and_log(index: VectorStoreIndex) -> None:
    retriever = index.as_retriever(similarity_top_k=10)
    lines: list[str] = []

    lines.append("# Mission 2 — RAG Top-10 실패 케이스 로그\n")
    lines.append(
        "VectorStoreIndex(`similarity_top_k=10`)로 검색했을 때 "
        "정답 근거 노드가 상위에 들어오지 않는 질문-데이터 페어를 기록합니다.\n"
    )
    lines.append(f"- **임베딩 모델**: `all-MiniLM-L6-v2`")
    lines.append(f"- **Chunk size / overlap**: 256 / 50")
    lines.append(f"- **similarity_top_k**: 10\n")
    lines.append("---\n")

    for case in CASES:
        print(f"\n[Case {case.id:02d}] {case.category}")
        print(f"  Q: {case.question}")

        try:
            nodes = retriever.retrieve(case.question)
        except Exception as exc:
            nodes = []
            print(f"  Retrieval error: {exc}")

        # 정답 노드가 top-10에 있는지 확인
        hit = any(
            case.expected_keyword.lower() in (n.text or "").lower()
            for n in nodes
        ) if case.expected_keyword else False

        status = "⚠️ PARTIAL HIT" if hit else "❌ MISS"
        print(f"  Expected source: {case.expected_source} | Status: {status}")

        lines.append(f"## Case {case.id:02d} — {case.category}")
        lines.append(f"\n**질문**: {case.question}\n")
        lines.append(f"**정답이 있어야 할 파일**: `{case.expected_source}`\n")
        lines.append(f"**Top-10 검색 결과 상태**: {status}\n")
        lines.append(f"**예상 실패 원인**: {case.failure_reason}\n")
        lines.append("\n### Top-10 검색 결과\n")
        lines.append("| # | score | source | text (앞 200자) |")
        lines.append("|---|-------|--------|----------------|")

        for rank, node in enumerate(nodes, 1):
            score = getattr(node, "score", None)
            score_str = f"{score:.4f}" if isinstance(score, float) else "-"
            meta = node.metadata or {}
            source = meta.get("file_name", meta.get("filename", "Wikipedia"))
            text_preview = node.text[:200].replace("\n", " ").replace("|", "\\|") if node.text else ""
            lines.append(f"| {rank} | {score_str} | `{source}` | {text_preview} |")

        lines.append("")  # 빈 줄
        lines.append(f"**metadata (1위 노드)**: `{nodes[0].metadata if nodes else {}}`\n")
        lines.append("---\n")

    log_path = Path("mission2_log.md")
    log_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n[DONE] mission2_log.md 생성 완료 ({log_path.stat().st_size} bytes)")


# ── 진입점 ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    index = build_or_load_index()
    run_and_log(index)
