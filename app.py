import logging
logging.basicConfig(level=logging.DEBUG)

from llama_index.readers.wikipedia import WikipediaReader
from llama_index.core import SummaryIndex, Settings
from llama_index.core.node_parser import SimpleNodeParser
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.core.llms.mock import MockLLM

# 0. 설정: 로컬 임베딩 + Mock LLM
Settings.embed_model = HuggingFaceEmbedding(model_name="all-MiniLM-L6-v2")
Settings.llm = MockLLM()

print("=== Block 1: Document 로드 ===")
loader = WikipediaReader()

# 위키 제목은 안정적인 것으로 먼저 테스트
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