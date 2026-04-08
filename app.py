import logging
from pathlib import Path

import pandas as pd
import gradio as gr

from llama_index.readers.wikipedia import WikipediaReader
from llama_index.core import SimpleDirectoryReader, VectorStoreIndex, Settings, Document
from llama_index.core.node_parser import SimpleNodeParser
from llama_index.llms.google_genai import GoogleGenAI
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.core.readers.base import BaseReader

from llama_index.readers.file import (
    PDFReader,
    DocxReader,
    HWPReader,
    FlatReader,
)

logging.basicConfig(level=logging.INFO)

# ── 설정 ─────────────────────────────────────────────────────────────────────
import os
Settings.embed_model = HuggingFaceEmbedding(model_name="all-MiniLM-L6-v2")
Settings.llm = GoogleGenAI(
    model="gemini-2.0-flash",
    api_key=os.environ.get("GEMINI_API_KEY", ""),
)

parser = SimpleNodeParser.from_defaults(chunk_size=256, chunk_overlap=50)


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
            img = Image.open(str(file))
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


file_extractor = {
    ".txt":  FlatReader(),
    ".pdf":  PDFReader(),
    ".docx": DocxReader(),
    ".xlsx": XlsxReader(),
    ".hwp":  HWPReader(),
    ".png":  OCRImageReader(),
}

# ── 인덱스 초기화 (앱 시작 시 1회) ──────────────────────────────────────────

print(">>> 인덱스 초기화 중... (최초 1회, 잠시 기다려주세요)")

# Wikipedia 인덱스
wiki_docs = WikipediaReader().load_data(pages=["Python (programming language)"])
wiki_nodes = parser.get_nodes_from_documents(wiki_docs)
wiki_index = VectorStoreIndex(wiki_nodes)
wiki_engine = wiki_index.as_query_engine(similarity_top_k=3)

# 로컬 파일 인덱스
local_reader = SimpleDirectoryReader(
    input_dir="data",
    file_extractor=file_extractor,
    required_exts=[".txt", ".pdf", ".docx", ".xlsx", ".hwp", ".png"],
)
local_docs = local_reader.load_data()
local_nodes = parser.get_nodes_from_documents(local_docs)
local_index = VectorStoreIndex(local_nodes)
local_engine = local_index.as_query_engine(similarity_top_k=3)

# 전체 통합 인덱스
all_nodes = wiki_nodes + local_nodes
all_index = VectorStoreIndex(all_nodes)
all_engine = all_index.as_query_engine(similarity_top_k=3)

print(f">>> 초기화 완료! (Wikipedia {len(wiki_nodes)}개 + 로컬 {len(local_nodes)}개 노드)")

# 파일 목록 텍스트
file_list = "\n".join(
    sorted(set(doc.metadata.get("file_name", "unknown") for doc in local_docs))
)

# ── Gradio UI ─────────────────────────────────────────────────────────────────

def query_rag(question: str, source: str) -> tuple[str, str]:
    if not question.strip():
        return "", "질문을 입력해주세요."

    if source == "로컬 파일 (data/)":
        engine = local_engine
    elif source == "Wikipedia (Python)":
        engine = wiki_engine
    else:
        engine = all_engine

    response = engine.query(question)

    # 검색된 소스 노드 정리
    sources = []
    if hasattr(response, "source_nodes"):
        for node in response.source_nodes:
            fname = node.metadata.get("file_name", node.metadata.get("filename", "Wikipedia"))
            score = f"{node.score:.3f}" if node.score is not None else "-"
            preview = node.text[:120].replace("\n", " ")
            sources.append(f"**[{fname}]** (유사도: {score})\n> {preview}…")
    sources_text = "\n\n".join(sources) if sources else "소스 정보 없음"

    return str(response), sources_text


with gr.Blocks(title="RAG 파이프라인", theme=gr.themes.Soft()) as demo:
    gr.Markdown(
        """
        # RAG 파이프라인 데모
        문서에 질문하면 관련 내용을 찾아 답변합니다.
        """
    )

    with gr.Row():
        with gr.Column(scale=1):
            gr.Markdown(f"### 로드된 파일\n```\n{file_list}\n```")
            gr.Markdown(f"**Wikipedia**: Python (programming language)")
            gr.Markdown(
                f"**노드 수**: Wikipedia {len(wiki_nodes)}개 / 로컬 {len(local_nodes)}개"
            )

        with gr.Column(scale=3):
            source_radio = gr.Radio(
                choices=["전체 통합", "로컬 파일 (data/)", "Wikipedia (Python)"],
                value="전체 통합",
                label="검색 대상",
            )
            question_box = gr.Textbox(
                placeholder="예: Policy.pdf에서 연구비 지침의 목적은 무엇인가요?",
                label="질문 입력",
                lines=2,
            )
            submit_btn = gr.Button("검색", variant="primary")

            gr.Markdown("### 답변")
            answer_box = gr.Textbox(label="", lines=6, interactive=False)

            gr.Markdown("### 참조 소스 (검색된 청크)")
            sources_box = gr.Markdown()

    # 예시 질문
    gr.Examples(
        examples=[
            ["Policy.pdf에서 연구비 지침의 목적은 무엇인가?", "로컬 파일 (data/)"],
            ["SRS.docx에서 소프트웨어 요구사항의 적용 범위는?", "로컬 파일 (data/)"],
            ["이미지에 포함된 텍스트는 무엇인가?", "로컬 파일 (data/)"],
            ["What is Python used for?", "Wikipedia (Python)"],
            ["Python의 주요 특징은 무엇인가?", "전체 통합"],
        ],
        inputs=[question_box, source_radio],
    )

    submit_btn.click(
        fn=query_rag,
        inputs=[question_box, source_radio],
        outputs=[answer_box, sources_box],
    )
    question_box.submit(
        fn=query_rag,
        inputs=[question_box, source_radio],
        outputs=[answer_box, sources_box],
    )

demo.launch(server_name="0.0.0.0", server_port=7860)
