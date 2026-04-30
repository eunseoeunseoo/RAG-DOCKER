"""
Mission 1 — Streamable HTTP MCP Server
VectorStoreIndex 기반 RAG QueryEngine 을 FastMCP Streamable HTTP 로 노출합니다.
"""

import logging
import os
from collections import Counter
from pathlib import Path

import pandas as pd
from fastmcp import FastMCP
from llama_index.core import Document, Settings, SimpleDirectoryReader, VectorStoreIndex
from llama_index.core.node_parser import SimpleNodeParser
from llama_index.core.readers.base import BaseReader
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.llms.google_genai import GoogleGenAI
from llama_index.readers.file import DocxReader, FlatReader, HWPReader, PDFReader
from llama_index.readers.wikipedia import WikipediaReader

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


# ── readers ──────────────────────────────────────────────────────────────────

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


# ── pipeline ──────────────────────────────────────────────────────────────────

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
        logger.warning("GEMINI_API_KEY not set — retriever-only mode.")


def build_pipeline():
    configure_models()
    parser = SimpleNodeParser.from_defaults(chunk_size=256, chunk_overlap=50)

    logger.info("Loading Wikipedia documents...")
    import wikipedia as _wp
    _wp.set_user_agent("mcp-rag-server/1.0 (RAG study project)")
    wiki_docs = []
    for attempt in range(3):
        try:
            wiki_docs = WikipediaReader().load_data(pages=["Python (programming language)"])
            break
        except Exception as exc:
            logger.warning(f"Wikipedia load attempt {attempt + 1} failed: {exc}")
            if attempt == 2:
                logger.warning("Wikipedia load failed — using local files only")
    wiki_nodes = parser.get_nodes_from_documents(wiki_docs)

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

    all_nodes = wiki_nodes + local_nodes
    all_index = VectorStoreIndex(all_nodes)

    wiki_index = VectorStoreIndex(wiki_nodes)
    local_index = VectorStoreIndex(local_nodes)

    logger.info(
        f"Pipeline ready: Wikipedia {len(wiki_nodes)} nodes + "
        f"local {len(local_nodes)} nodes = {len(all_nodes)} total"
    )

    return {
        "wiki_engine": wiki_index.as_query_engine(similarity_top_k=3) if Settings.llm else None,
        "wiki_retriever": wiki_index.as_retriever(similarity_top_k=3),
        "local_engine": local_index.as_query_engine(similarity_top_k=3) if Settings.llm else None,
        "local_retriever": local_index.as_retriever(similarity_top_k=3),
        "all_engine": all_index.as_query_engine(similarity_top_k=3) if Settings.llm else None,
        "all_retriever": all_index.as_retriever(similarity_top_k=3),
    }


logger.info("Initialising RAG pipeline …")
PIPELINE = build_pipeline()
logger.info("RAG pipeline ready.")


# ── FastMCP server ────────────────────────────────────────────────────────────

mcp = FastMCP("RAG MCP Server")


@mcp.tool()
def rag_query(question: str, source: str = "all") -> str:
    """RAG 기반 질의응답 도구.

    Args:
        question: 질문 텍스트
        source: 검색 대상 — "all"(전체 통합), "local"(로컬 파일), "wiki"(Wikipedia)
    """
    if not question.strip():
        return "질문을 입력해 주세요."

    source = source.lower().strip()
    if source in ("local", "로컬", "data"):
        engine = PIPELINE["local_engine"]
        retriever = PIPELINE["local_retriever"]
        label = "Local data/"
    elif source in ("wiki", "wikipedia"):
        engine = PIPELINE["wiki_engine"]
        retriever = PIPELINE["wiki_retriever"]
        label = "Wikipedia"
    else:
        engine = PIPELINE["all_engine"]
        retriever = PIPELINE["all_retriever"]
        label = "All (combined)"

    if engine is not None:
        try:
            response = engine.query(question)
            source_nodes = getattr(response, "source_nodes", [])
            sources = []
            for node in source_nodes:
                meta = node.metadata or {}
                fname = meta.get("file_name", meta.get("filename", "Wikipedia"))
                score = getattr(node, "score", None)
                score_text = f"{score:.3f}" if isinstance(score, (int, float)) else "-"
                preview = node.text[:120].replace("\n", " ")
                sources.append(f"[{fname}](score:{score_text}) {preview}")
            source_text = "\n".join(sources) if sources else "No source nodes."
            return f"[Source: {label}]\n\n{response}\n\n---\nRetrieved nodes:\n{source_text}"
        except Exception as exc:
            logger.exception("QueryEngine failed, falling back to retriever.")
            retrieved = retriever.retrieve(question)
            snippets = [
                f"[{(n.metadata or {}).get('file_name', 'Wikipedia')}] "
                f"{n.text[:120].replace(chr(10), ' ')}"
                for n in retrieved
            ]
            return (
                f"[Source: {label}] LLM error ({type(exc).__name__}). "
                "Retriever-only results:\n" + "\n".join(snippets)
            )

    retrieved = retriever.retrieve(question)
    snippets = [
        f"[{(n.metadata or {}).get('file_name', 'Wikipedia')}] "
        f"{n.text[:120].replace(chr(10), ' ')}"
        for n in retrieved
    ]
    return (
        f"[Source: {label}] LLM not configured. Top retrieved nodes:\n"
        + "\n".join(snippets)
    )


if __name__ == "__main__":
    port = int(os.environ.get("MCP_PORT", "8000"))
    logger.info(f"Starting Streamable HTTP MCP server on 0.0.0.0:{port} …")
    mcp.run(transport="http", host="0.0.0.0", port=port)
