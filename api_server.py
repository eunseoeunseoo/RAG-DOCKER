"""
api_server.py - RAG Retrieval API (Mission 1)

GET  /health   → {"status": "ok", "ready": true}
POST /retrieve → {"contexts": [{"text": "...", "source": "...", "score": 0.82}]}
"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
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
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

STORAGE_DIR = "./storage"
INDEX: VectorStoreIndex | None = None


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


def build_or_load_index() -> VectorStoreIndex:
    Settings.embed_model = HuggingFaceEmbedding(model_name="all-MiniLM-L6-v2")
    Settings.llm = None

    if Path(STORAGE_DIR).exists() and any(Path(STORAGE_DIR).iterdir()):
        logger.info("Loading index from %s ...", STORAGE_DIR)
        storage_context = StorageContext.from_defaults(persist_dir=STORAGE_DIR)
        index = load_index_from_storage(storage_context)
        logger.info("Index loaded from storage.")
        return index

    logger.info("Building VectorStoreIndex from scratch ...")
    parser = SimpleNodeParser.from_defaults(chunk_size=256, chunk_overlap=50)

    import wikipedia as _wp
    _wp.set_user_agent("api_server/1.0 (RAG study project)")
    wiki_docs = []
    for attempt in range(3):
        try:
            wiki_docs = WikipediaReader().load_data(pages=["Python (programming language)"])
            break
        except Exception as exc:
            logger.warning("Wikipedia load attempt %d failed: %s", attempt + 1, exc)
    wiki_nodes = parser.get_nodes_from_documents(wiki_docs)
    logger.info("Wikipedia: %d nodes", len(wiki_nodes))

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
    logger.info("Local data/: %d nodes", len(local_nodes))

    all_nodes = wiki_nodes + local_nodes
    index = VectorStoreIndex(all_nodes)
    index.storage_context.persist(STORAGE_DIR)
    logger.info("Index persisted to %s/ (%d nodes total)", STORAGE_DIR, len(all_nodes))
    return index


@asynccontextmanager
async def lifespan(app: FastAPI):
    global INDEX
    logger.info("Initializing RAG index ...")
    INDEX = build_or_load_index()
    logger.info("RAG index ready.")
    yield


app = FastAPI(title="RAG Retrieval API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok", "ready": INDEX is not None}


class RetrieveRequest(BaseModel):
    question: str
    top_k: int = 5


@app.post("/retrieve")
def retrieve(req: RetrieveRequest):
    if INDEX is None:
        raise HTTPException(status_code=503, detail="Index not ready")

    retriever = INDEX.as_retriever(similarity_top_k=req.top_k)
    nodes = retriever.retrieve(req.question)

    contexts = []
    for node in nodes:
        meta = node.metadata or {}
        source = meta.get("file_name", meta.get("filename", "Wikipedia"))
        score = getattr(node, "score", None)
        text = (node.text or "")[:2000]
        entry = {"text": text, "source": source}
        if isinstance(score, (int, float)):
            entry["score"] = round(score, 4)
        contexts.append(entry)

    return {"contexts": contexts}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api_server:app", host="0.0.0.0", port=8000, reload=False)
