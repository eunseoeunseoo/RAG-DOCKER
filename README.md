# Retrieval API Baseline Report

## 1. 실행 방식

- **RAG 서버 실행 방식**: Docker (`docker compose up -d`, port 8000, `0.0.0.0` bind)
- **Cloudflare Quick Tunnel URL**: `https://isle-composite-jobs-substance.trycloudflare.com`
- **사용한 데이터**: `data/` 로컬 파일 6종 (Policy.pdf, SRS.docx, CRA.xlsx, DESIGN.hwp, Image.png, Text.txt) + Wikipedia (Python)
- **사용한 index/retriever**: `VectorStoreIndex` + `HuggingFaceEmbedding` (`all-MiniLM-L6-v2`), `chunk_size=256, overlap=50`, `storage/` 영속화

> **개발 과정**: Mock 서버로 endpoint 스펙·응답 형식 검증 완료 후 실제 VectorStoreIndex 기반 RAG로 교체

## 2. Public URL self-check

- **/health 결과**: `{"status":"ok","ready":true}`
- **/retrieve 테스트 질문**: `연구비 지침의 목적은 무엇인가?`
- **/retrieve 반환 contexts 수**: 3개 (`top_k=3` 기준)

## 3. Baseline 검색 결과

| 질문 | 기대 정보 | 검색된 context에 포함 여부 | 실패 원인 |
|---|---|---|---|
| 연구비 지침의 목적은 무엇인가? | Policy.pdf 목적 조항 | △ 부분 포함 (3위, score 0.51) | DESIGN.hwp 청크가 1·2위 선점 — 한국어 임베딩 유사도 혼재 |
| Python is used for what? | Wikipedia Python 관련 청크 | ✅ 포함 (1·2·3위 모두 Wikipedia, score 0.70~0.66) | 없음 — 영어 질문·영어 문서 매칭 정확 |
| 비기능 요구사항은 무엇인가? | SRS.docx 비기능 요구사항 | △ 부분 포함 (2위, score 0.42) | DESIGN.hwp 청크가 1·3위 선점 — 유사 도메인 문서 간 혼재 |

## 4. 다음 개선 계획

- **chunking**: `chunk_size=256` → `512` 상향 검토 (한국어 조항 단위가 256자 초과로 분리되는 문제 완화)
- **metadata**: 파일명·조항 번호 메타데이터 보강 → 특정 파일 대상 질문 시 필터링 검색 지원
- **query rewrite**: 한국어 질문을 영어로 번역 후 검색 → `all-MiniLM-L6-v2` 다국어 정렬 성능 개선
- **reranker/top_k**: `similarity_top_k` 3→10 확대 후 cross-encoder reranker로 최종 압축하여 정밀도 향상
