# RAG Pipeline — 신입 사원 온보딩 미션 3주차

LlamaIndex를 활용한 RAG(Retrieval-Augmented Generation) 파이프라인 구현 보고서입니다.

## 구현 내용

| 빌딩 블록 | 구현 방법 |
|----------|---------|
| Block 1 — Document | `WikipediaReader` + `SimpleDirectoryReader` (6종 포맷) |
| Block 2 — Node | `SimpleNodeParser(chunk_size=256, chunk_overlap=50)` |
| Block 3 — Index | `VectorStoreIndex` (임베딩 유사도 검색) |
| Block 4 — QueryEngine | `index.as_query_engine(similarity_top_k=3)` |

- **LLM**: `GoogleGenAI` (`gemini-2.0-flash-lite`) — Gemini 무료 API 연동
- **임베딩**: `HuggingFaceEmbedding` (`all-MiniLM-L6-v2`)
- **UI**: Gradio Blocks — 질문 입력, 답변 출력, 참조 소스 표시
- **배포**: Docker 컨테이너 (`python:3.10` + `tesseract-ocr-kor`)

## 실행 방법

```bash
docker build -t rag-docker .
docker run -d -p 7860:7860 -e GEMINI_API_KEY="your_api_key" rag-docker
```

브라우저에서 http://localhost:7860 접속

---

# 포맷별 호환성 보고서

## 1. 파싱 품질 테스트

| 파일 | 확장자 | 로드 성공 | 파싱 품질 (상/중/하) | 판단 근거 |
|------|--------|:--------:|:------------------:|----------|
| Text.txt | `.txt` | ✅ | 상 | `FlatReader`가 원본 텍스트를 그대로 읽어 손실 없음. 줄바꿈·공백 완전 보존 |
| Policy.pdf | `.pdf` | ✅ | 중 | `PDFReader`(pypdf)가 본문 텍스트는 정상 추출하나, 다단 레이아웃·표 셀 병합 정보 손실. 폰트 특수문자 일부 깨짐 |
| SRS.docx | `.docx` | ✅ | 중 | `DocxReader`(python-docx)가 단락 텍스트는 정상 추출하나, 표 행·열 구조 flat text로 풀려 맥락 파악 어려움 |
| CRA.xlsx | `.xlsx` | ✅ | 중 | 커스텀 `XlsxReader`(`df.to_markdown()`)로 헤더-행 관계 보존. 병합 셀·수식 결과는 미반영 |
| DESIGN.hwp | `.hwp` | ✅ | 하 | `HWPReader`가 기본 텍스트 추출하나 표·그림 캡션 누락 다수. 일부 특수 기호 깨짐 |
| Image.png | `.png` | ✅ | 중 | `OCRImageReader`(pytesseract) 적용으로 이미지 내 텍스트 추출 가능. 손글씨·저해상도 이미지는 인식률 저하 |

- **파싱 품질 기준**: 원본 대비 텍스트 추출 정확도 (상: 거의 완벽 / 중: 핵심 추출 가능 / 하: 누락·깨짐 심각)
- **판단 근거**: 원본과 비교하여 구체적으로 기술 (예: "표 구조 유지되었으나 셀 병합 정보 손실", "한글 깨짐 발생")

## 2. 검색 품질 테스트

파일별로 직접 설계한 질문을 QueryEngine에 질의하고 결과를 기록하세요. **RAG가 가장 실패하기 쉬운 챌린징한 질문**을 찾아 보고하는 것이 핵심입니다.

| 파일 | 질문 | 기대 답변 (원본 기준) | 실제 응답 | 검색 품질 (상/중/하) | 판단 근거 |
|------|------|-------------------|----------|:------------------:|----------|
| Text.txt | "문서에서 언급된 핵심 키워드 3가지는?" | 파일 내 주요 키워드 열거 | 관련 단어 포함한 응답 | 중 | VectorStoreIndex 전환 후 의미론적 검색으로 관련 청크 정확히 선택 |
| Text.txt | "문서의 마지막 문장을 그대로 인용해줘" | 마지막 문장 정확 인용 | 유사 내용 응답 | 중 | chunk_overlap=50 적용으로 경계 문장 포함 확률 향상. 단, 정확한 인용보다 요약 경향 |
| Policy.pdf | "5조 3항의 내용은 무엇인가?" | 해당 조항 원문 | 해당 조항 근방 내용 응답 | 중 | chunk_size=256 축소로 조항 단위 청크 분리. VectorStoreIndex가 유사 조항 청크 검색 |
| Policy.pdf | "이 정책의 유효 기간은?" | 특정 날짜/기간 | 날짜 포함 응답 | 상 | 날짜 텍스트가 소규모 청크에 집중되어 임베딩 유사도 검색으로 정확히 히트 |
| SRS.docx | "요구사항 ID REQ-003의 설명은?" | REQ-003 항목 원문 | REQ-003 포함 청크 응답 | 중 | 작은 chunk_size로 ID 단위 분리. 단, 표 flat text 변환으로 완전한 행 매핑은 어려움 |
| SRS.docx | "비기능 요구사항 중 성능 관련 항목은 몇 개인가?" | 정확한 개수 | 관련 항목 열거하나 개수 부정확 | 중 | 의미론적 검색으로 성능 관련 청크 검색 성공. 개수 집계는 LLM 추론 의존 |
| CRA.xlsx | "A열 3행의 값은 무엇인가?" | 정확한 셀 값 | Markdown 테이블 기반 응답 | 중 | to_markdown() 전환으로 헤더-행 관계 보존. 열 이름 기반 조회 가능 |
| CRA.xlsx | "합계가 가장 큰 항목은?" | 특정 항목명 | 관련 행 나열 후 추론 | 중 | Markdown 테이블에서 수치 컬럼 추출 가능. 수식 결과 미반영은 한계 |
| DESIGN.hwp | "설계 문서의 전체 구조(목차)를 설명해줘" | 장·절 목차 구조 | 일부 제목 나열 | 중 | 제목 텍스트 청크가 VectorStoreIndex에서 의미론적으로 검색됨 |
| DESIGN.hwp | "그림 2의 캡션은 무엇인가?" | 캡션 원문 | 무응답 또는 관련 없는 텍스트 | 하 | HWPReader가 그림 캡션을 추출하지 못함. 파서 한계로 개선 어려움 |
| Image.png | "이미지에 포함된 텍스트를 읽어줘" | 이미지 내 텍스트 | OCR 추출 텍스트 응답 | 중 | pytesseract OCR 적용으로 텍스트 추출 성공. 인식률은 이미지 품질에 의존 |
| Image.png | "이미지의 주요 내용은 무엇인가?" | 이미지 내용 설명 | OCR 텍스트 기반 요약 응답 | 중 | OCR로 추출된 텍스트를 기반으로 내용 파악 가능. 비텍스트 시각 요소는 여전히 미인식 |

- **검색 품질 기준**: 기대 답변 대비 실제 응답의 정확도 (상: 정확히 답변 / 중: 부분 정답 / 하: 오답·무응답)
- **판단 근거**: 실패 원인 분석 (예: "표가 flat text로 풀려 행·열 매핑 불가", "chunk 경계에서 문맥 단절")

## 3. 미지원 포맷 해결 방안

| 확장자 | 실패 원인 | 시도한 해결 방법 | 해결 후 파싱 품질 | 해결 후 검색 품질 |
|--------|----------|----------------|:------------------:|:------------------:|
| `.xlsx` | llama-index 기본 Reader 없음, `to_string()`으로 행·열 구조 손실 | `pandas` + `openpyxl`로 커스텀 `XlsxReader` 구현, `df.to_markdown()`으로 헤더-행 관계 보존 | 중 | 중 |
| `.png` | `ImageReader`가 OCR 미지원 (메타데이터만 추출) | `pytesseract` + Tesseract OCR 엔진(kor+eng)을 활용한 커스텀 `OCRImageReader` 구현, Dockerfile에 `tesseract-ocr-kor` 설치 추가 | 중 | 중 |
| `.hwp` | HWP 독점 포맷으로 그림 캡션·표 구조 파싱 불안정 | `HWPReader` 적용 (부분 성공). 완전 해결을 위해서는 LibreOffice로 docx 변환 후 처리 권장 | 하 | 중 |

## 4. 검색 품질 개선 실험

| 개선 방법 | 적용 대상 | 테스트 질문 | 개선 전 응답 | 개선 후 응답 | 효과 (상/중/하) |
|----------|----------|-----------|------------|------------|:--------------:|
| `SummaryIndex` → `VectorStoreIndex` | 전체 문서 | "성능 요구사항 관련 내용은?" | 전체 노드 순차 전달로 LLM 부담 큼, 관련 없는 내용 혼입 | 임베딩 유사도 상위 3개 노드만 전달, 정확도·속도 개선 | 상 |
| `chunk_size` 1024→256, `chunk_overlap` 0→50 | SRS.docx | "요구사항 ID REQ-003의 설명은?" | ID-설명 혼입 오답 | REQ-003 해당 청크가 별도 노드로 분리되어 정확도 향상 | 상 |
| `df.to_markdown()` 전처리 | CRA.xlsx | "A열 3행의 값은 무엇인가?" | 위치 정보 손실로 무응답 | 헤더·행 관계 보존으로 열 이름 기반 조회 가능 | 중 |
| `pytesseract` OCR (`OCRImageReader`) | Image.png | "이미지에 포함된 텍스트를 읽어줘" | 메타데이터(크기 등)만 응답 | 이미지 내 텍스트 추출 성공 | 상 |
| `similarity_top_k` 5→3 설정 | 전체 문서 | "Policy.pdf에서 5조 내용은?" | 관련 없는 문서 내용 혼입 | 유사도 상위 3청크로 검색 범위 제한, 노이즈 감소 및 토큰 사용량 절감 | 중 |

- 예시 접근법: chunk_size/overlap 조정, metadata 추가, 문서 전처리(표→텍스트 변환 등)
