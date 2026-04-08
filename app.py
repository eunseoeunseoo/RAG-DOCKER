import logging
from pathlib import Path

import pandas as pd

from llama_index.readers.wikipedia import WikipediaReader
from llama_index.core import SimpleDirectoryReader, SummaryIndex, Settings, Document
from llama_index.core.node_parser import SimpleNodeParser
from llama_index.core.llms.mock import MockLLM
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.core.readers.base import BaseReader

from llama_index.readers.file import (
    PDFReader,
    DocxReader,
    HWPReader,
    ImageReader,
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
parser = SimpleNodeParser.from_defaults()
nodes = parser.get_nodes_from_documents(documents)

print(f"len(nodes) = {len(nodes)}")
print("nodes[0].text[:200] =")
print(nodes[0].text[:200])
print("nodes[0].metadata =")
print(nodes[0].metadata)

print("\n=== Block 3: SummaryIndex 구축 ===")
index = SummaryIndex(nodes)
print("SummaryIndex 생성 완료")

print("\n=== Block 4: QueryEngine 실행 ===")
query_engine = index.as_query_engine()
response = query_engine.query("What is Python used for?")

print("질문: What is Python used for?")
print("응답:")
print(response)

# 커스텀 XLSX Reader
class XlsxReader(BaseReader):
    def load_data(self, file, extra_info=None):
        file_path = str(file)
        xls = pd.ExcelFile(file_path, engine="openpyxl")

        documents = []

        for sheet_name in xls.sheet_names:
            df = pd.read_excel(file_path, sheet_name=sheet_name, engine="openpyxl")
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

# 확장자별 Reader 매핑
file_extractor = {
    ".txt": FlatReader(),
    ".pdf": PDFReader(),
    ".docx": DocxReader(),
    ".xlsx": XlsxReader(),   # 👉 커스텀
    ".hwp": HWPReader(),
    ".png": ImageReader(),
}

# Block 7: 다양한 파일 로드

print("=== Block 7: 다양한 문서 포맷 로드 ===")

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

# Node 분할
print("\n=== Node 분할 ===")

parser = SimpleNodeParser.from_defaults()
nodes = parser.get_nodes_from_documents(documents)

print(f"총 Node 개수: {len(nodes)}")
if nodes:
    print("nodes[0].metadata =", nodes[0].metadata)
    print("nodes[0].text[:200] =", nodes[0].text[:200])

# Index 생성
print("\n=== Index 생성 ===")

index = SummaryIndex(nodes)
print("SummaryIndex 생성 완료")

# QueryEngine 실행
print("\n=== QueryEngine 실행 ===")

# 질의응답 동작
query_engine = index.as_query_engine()
response = query_engine.query("각 파일의 내용을 간단히 요약해줘")

print("\n질문: 각 파일의 내용을 간단히 요약해줘")
print("응답:")
print(response)
