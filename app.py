import logging
from pathlib import Path

import pandas as pd

from llama_index.readers.wikipedia import WikipediaReader
from llama_index.core import SimpleDirectoryReader, SummaryIndex, VectorStoreIndex, Settings, Document
from llama_index.core.node_parser import SimpleNodeParser
from llama_index.core.llms.mock import MockLLM
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.core.readers.base import BaseReader

from llama_index.readers.file import (
    PDFReader,
    DocxReader,
    HWPReader,
    FlatReader,
)

# Logging 활성화
logging.basicConfig(level=logging.DEBUG)

# 0. 설정: 로컬 임베딩 + Mock LLM
Settings.embed_model = HuggingFaceEmbedding(model_name="all-MiniLM-L6-v2")
Settings.llm = MockLLM()

print("=== Block 1: Document 로드 ===")
loader = WikipediaReader()

documents = loader.load_data(pages=["Python (programming language)"])

print(f"len(documents) = {len(documents)}")
print("documents[0].metadata =")
print(documents[0].metadata)
print("documents[0].text[:300] =")
print(documents[0].text[:300])

print("\n=== Block 2: Node 분할 ===")
# chunk_size 축소 + overlap 추가로 경계 문맥 보존
parser = SimpleNodeParser.from_defaults(chunk_size=256, chunk_overlap=50)
nodes = parser.get_nodes_from_documents(documents)

print(f"len(nodes) = {len(nodes)}")
print("nodes[0].text[:200] =")
print(nodes[0].text[:200])
print("nodes[0].metadata =")
print(nodes[0].metadata)

print("\n=== Block 3: VectorStoreIndex 구축 ===")
# SummaryIndex → VectorStoreIndex: 임베딩 유사도 기반 검색으로 정확도 향상
index = VectorStoreIndex(nodes)
print("VectorStoreIndex 생성 완료")

print("\n=== Block 4: QueryEngine 실행 ===")
query_engine = index.as_query_engine()
response = query_engine.query("What is Python used for?")

print("질문: What is Python used for?")
print("응답:")
print(response)


# ── 커스텀 Reader 정의 ────────────────────────────────────────────────────────

class XlsxReader(BaseReader):
    """pandas로 xlsx를 읽어 Markdown 테이블로 변환 (행·열 구조 보존)."""

    def load_data(self, file, extra_info=None):
        file_path = str(file)
        xls = pd.ExcelFile(file_path, engine="openpyxl")
        documents = []

        for sheet_name in xls.sheet_names:
            df = pd.read_excel(file_path, sheet_name=sheet_name, engine="openpyxl")
            # Markdown 테이블로 변환 — 헤더·행 관계를 텍스트에 보존
            try:
                text = df.to_markdown(index=False)
            except ImportError:
                # tabulate 없을 경우 fallback
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
    """pytesseract OCR로 PNG 이미지 내 텍스트를 추출."""

    def load_data(self, file, extra_info=None):
        try:
            import pytesseract
            from PIL import Image

            img = Image.open(str(file))
            # 한국어(kor) + 영어(eng) 동시 인식
            text = pytesseract.image_to_string(img, lang="kor+eng")
        except Exception as e:
            text = f"[OCR 실패: {e}]"

        metadata = {
            "file_name": Path(str(file)).name,
            "file_path": str(file),
            "file_type": ".png",
        }
        if extra_info:
            metadata.update(extra_info)

        return [Document(text=text, metadata=metadata)]


# ── 확장자별 Reader 매핑 ──────────────────────────────────────────────────────
file_extractor = {
    ".txt":  FlatReader(),
    ".pdf":  PDFReader(),
    ".docx": DocxReader(),
    ".xlsx": XlsxReader(),
    ".hwp":  HWPReader(),
    ".png":  OCRImageReader(),   # OCR 기반으로 교체
}

# ── Block 7: 다양한 문서 포맷 로드 ───────────────────────────────────────────
print("\n=== Block 7: 다양한 문서 포맷 로드 ===")

reader = SimpleDirectoryReader(
    input_dir="data",
    file_extractor=file_extractor,
    required_exts=[".txt", ".pdf", ".docx", ".xlsx", ".hwp", ".png"],
)

documents = reader.load_data()

print(f"\n총 Document 개수: {len(documents)}")

print("\n=== Document별 metadata & 내용 일부 ===")
for i, doc in enumerate(documents):
    print(f"\n[Document {i}]")
    print("metadata =", doc.metadata)
    print("text[:200] =", doc.text[:200])

# ── Node 분할 (chunk_size·overlap 적용) ──────────────────────────────────────
print("\n=== Node 분할 ===")

parser = SimpleNodeParser.from_defaults(chunk_size=256, chunk_overlap=50)
nodes = parser.get_nodes_from_documents(documents)

print(f"총 Node 개수: {len(nodes)}")
if nodes:
    print("nodes[0].metadata =", nodes[0].metadata)
    print("nodes[0].text[:200] =", nodes[0].text[:200])

# ── VectorStoreIndex 생성 ─────────────────────────────────────────────────────
print("\n=== VectorStoreIndex 생성 ===")

index = VectorStoreIndex(nodes)
print("VectorStoreIndex 생성 완료")

# ── QueryEngine 실행 ──────────────────────────────────────────────────────────
print("\n=== QueryEngine 실행 ===")

query_engine = index.as_query_engine(similarity_top_k=5)

test_queries = [
    "각 파일의 내용을 간단히 요약해줘",
    "Policy.pdf에서 언급된 주요 정책 내용은?",
    "SRS.docx의 요구사항 목록을 알려줘",
    "이미지에 포함된 텍스트는 무엇인가?",
]

for q in test_queries:
    print(f"\n질문: {q}")
    response = query_engine.query(q)
    print("응답:")
    print(response)
