import logging
import os
from collections import Counter
from pathlib import Path

import gradio as gr
import pandas as pd
from llama_index.core import Document, Settings, SimpleDirectoryReader, VectorStoreIndex
from llama_index.core.node_parser import SimpleNodeParser
from llama_index.core.readers.base import BaseReader
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.llms.google_genai import GoogleGenAI
from llama_index.readers.file import DocxReader, FlatReader, HWPReader, PDFReader
from llama_index.readers.wikipedia import WikipediaReader

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


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


def print_document_checks(title: str, documents: list[Document]) -> None:
    print(f"\n=== {title}: Document Check ===")
    print(f"len(documents) = {len(documents)}")
    if documents:
        print(f"documents[0].metadata = {documents[0].metadata}")
        preview = documents[0].text[:200].replace("\n", " ")
        print(f"documents[0].text[:200] = {preview}")


def print_node_checks(title: str, nodes) -> None:
    print(f"\n=== {title}: Node Check ===")
    print(f"len(nodes) = {len(nodes)}")
    if nodes:
        preview = nodes[0].text[:200].replace("\n", " ")
        print(f"nodes[0].text[:200] = {preview}")
        print(f"nodes[0].metadata = {nodes[0].metadata}")


def print_local_document_summary(documents: list[Document]) -> None:
    print("\n=== Local Documents by Format ===")
    counts = Counter(doc.metadata.get("file_type", "unknown") for doc in documents)
    for file_type, count in sorted(counts.items()):
        print(f"{file_type}: {count}")

    print("\n=== Local Document Metadata Preview ===")
    for doc in documents:
        print(doc.metadata)


def configure_models() -> None:
    Settings.embed_model = HuggingFaceEmbedding(model_name="all-MiniLM-L6-v2")

    gemini_api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if gemini_api_key:
        Settings.llm = GoogleGenAI(
            model="gemini-2.0-flash-lite",
            api_key=gemini_api_key,
        )
        logger.info("Google Gemini LLM configured.")
    else:
        Settings.llm = None
        logger.warning(
            "GEMINI_API_KEY is not set. QueryEngine-based natural language answers may not work."
        )


def build_pipeline():
    configure_models()
    parser = SimpleNodeParser.from_defaults(chunk_size=256, chunk_overlap=50)

    logger.info("Loading Wikipedia documents...")
    wiki_docs = WikipediaReader().load_data(pages=["Python (programming language)"])
    print_document_checks("Wikipedia", wiki_docs)

    wiki_nodes = parser.get_nodes_from_documents(wiki_docs)
    print_node_checks("Wikipedia", wiki_nodes)

    wiki_index = VectorStoreIndex(wiki_nodes)
    wiki_retriever = wiki_index.as_retriever(similarity_top_k=3)
    wiki_engine = wiki_index.as_query_engine(similarity_top_k=3) if Settings.llm else None

    logger.info("Loading local files from data/ ...")
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
    print_document_checks("Local data/", local_docs)
    print_local_document_summary(local_docs)

    local_nodes = parser.get_nodes_from_documents(local_docs)
    print_node_checks("Local data/", local_nodes)

    local_index = VectorStoreIndex(local_nodes)
    local_retriever = local_index.as_retriever(similarity_top_k=3)
    local_engine = local_index.as_query_engine(similarity_top_k=3) if Settings.llm else None

    all_nodes = wiki_nodes + local_nodes
    print_node_checks("Combined", all_nodes)

    all_index = VectorStoreIndex(all_nodes)
    all_retriever = all_index.as_retriever(similarity_top_k=3)
    all_engine = all_index.as_query_engine(similarity_top_k=3) if Settings.llm else None

    print("\n=== Retriever Smoke Test ===")
    smoke_query = "What is Python used for?"
    retrieved_nodes = wiki_retriever.retrieve(smoke_query)
    print(f"query = {smoke_query}")
    print(f"retrieved node count = {len(retrieved_nodes)}")
    if retrieved_nodes:
        print(f"top retrieved metadata = {retrieved_nodes[0].metadata}")

    print(
        f"\nInitialization complete: Wikipedia {len(wiki_nodes)} nodes + "
        f"local {len(local_nodes)} nodes = total {len(all_nodes)} nodes"
    )

    return {
        "local_docs": local_docs,
        "wiki_nodes": wiki_nodes,
        "local_nodes": local_nodes,
        "wiki_retriever": wiki_retriever,
        "local_retriever": local_retriever,
        "all_retriever": all_retriever,
        "wiki_engine": wiki_engine,
        "local_engine": local_engine,
        "all_engine": all_engine,
    }


PIPELINE = build_pipeline()


def format_retrieved_nodes(nodes) -> str:
    if not nodes:
        return "No source nodes found."

    lines = []
    for node in nodes:
        metadata = node.metadata or {}
        file_name = metadata.get("file_name", metadata.get("filename", "Wikipedia"))
        score = getattr(node, "score", None)
        score_text = f"{score:.3f}" if isinstance(score, (int, float)) else "-"
        preview = node.text[:160].replace("\n", " ")
        lines.append(f"**[{file_name}]** (score: {score_text})\n> {preview}")

    return "\n\n".join(lines)


def query_rag(question: str, source: str) -> tuple[str, str]:
    if not question.strip():
        return "", "질문을 입력해 주세요."

    if source == "로컬 파일 (data/)":
        engine = PIPELINE["local_engine"]
        retriever = PIPELINE["local_retriever"]
    elif source == "Wikipedia (Python)":
        engine = PIPELINE["wiki_engine"]
        retriever = PIPELINE["wiki_retriever"]
    else:
        engine = PIPELINE["all_engine"]
        retriever = PIPELINE["all_retriever"]

    if engine is not None:
        try:
            response = engine.query(question)
            sources_text = format_retrieved_nodes(getattr(response, "source_nodes", []))
            return str(response), sources_text
        except Exception as exc:
            logger.exception("QueryEngine failed. Falling back to retriever-only mode.")
            retrieved_nodes = retriever.retrieve(question)
            sources_text = format_retrieved_nodes(retrieved_nodes)
            fallback_answer = (
                "LLM 응답 생성 중 오류가 발생해 검색 결과만 표시합니다.\n\n"
                f"오류 요약: {type(exc).__name__}\n"
                "가능한 원인: Gemini API 할당량 초과, 일시적 네트워크 문제, API 설정 문제"
            )
            return fallback_answer, sources_text

    retrieved_nodes = retriever.retrieve(question)
    sources_text = format_retrieved_nodes(retrieved_nodes)
    fallback_answer = (
        "LLM is not configured, so this app is showing retrieved source nodes only.\n\n"
        "Set GEMINI_API_KEY to enable natural language answers from QueryEngine."
    )
    return fallback_answer, sources_text


file_list = "\n".join(
    sorted(set(doc.metadata.get("file_name", "unknown") for doc in PIPELINE["local_docs"]))
)


with gr.Blocks(title="RAG Pipeline Demo", theme=gr.themes.Soft()) as demo:
    gr.Markdown(
        """
        # RAG Pipeline Demo
        Documents are indexed and searched through a simple LlamaIndex-based RAG pipeline.
        """
    )

    with gr.Row():
        with gr.Column(scale=1):
            gr.Markdown(f"### Loaded Files\n```\n{file_list}\n```")
            gr.Markdown("**Wikipedia**: Python (programming language)")
            gr.Markdown(
                f"**Node Count**: Wikipedia {len(PIPELINE['wiki_nodes'])} / "
                f"Local {len(PIPELINE['local_nodes'])}"
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
            submit_btn = gr.Button("질문하기", variant="primary")

            gr.Markdown("### 답변")
            answer_box = gr.Textbox(label="", lines=6, interactive=False)

            gr.Markdown("### 참고한 소스 노드")
            sources_box = gr.Markdown()

    gr.Examples(
        examples=[
            ["Policy.pdf에서 연구비 지침의 목적은 무엇인가요?", "로컬 파일 (data/)"],
            ["SRS.docx에서 소프트웨어 요구사항의 적용 범위는 무엇인가요?", "로컬 파일 (data/)"],
            ["이미지에 포함된 텍스트는 무엇인가요?", "로컬 파일 (data/)"],
            ["What is Python used for?", "Wikipedia (Python)"],
            ["Python의 주요 특징은 무엇인가요?", "전체 통합"],
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


if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=7860)
