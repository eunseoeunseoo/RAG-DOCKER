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

---

# Mission 3 — RAG Retrieval API 공개 + 리더보드 Baseline

## 1. 구현 목표

외부 평가 서버가 직접 호출할 수 있는 RAG Retrieval HTTP API를 구현하고, Cloudflare Quick Tunnel을 통해 public HTTPS URL로 공개했습니다. 평가 기준은 LLM 생성 답변이 아니라 **retrieval 결과(contexts)** 입니다.

## 2. 시스템 구성

```
Docker container (RAG API)
  api_server.py — FastAPI, port 8000 (0.0.0.0 bind)
        |
        | docker compose ports: 8000:8000
        v
Host PC — http://127.0.0.1:8000
        |
        | cloudflared.exe tunnel
        v
https://isle-composite-jobs-substance.trycloudflare.com  ← 평가 서버가 호출
```

| 항목 | 내용 |
|------|------|
| API 서버 파일 | `api_server.py` (FastAPI + uvicorn) |
| 인덱스 소스 | `storage/` 디렉터리 (없으면 Wikipedia + `data/` 로 자동 빌딩) |
| 임베딩 모델 | `HuggingFaceEmbedding` (`all-MiniLM-L6-v2`) |
| chunk_size / overlap | 256 / 50 |
| 배포 방법 | `docker compose up -d` |
| 외부 공개 | Cloudflare Quick Tunnel |
| 제출 파일 | `rag_endpoint.json` |

## 3. API 엔드포인트 명세

### GET /health

서버와 인덱스가 평가 가능한 상태인지 확인합니다.

응답:
```json
{"status": "ok", "ready": true}
```

### POST /retrieve

질문을 받아 관련 context를 반환합니다.

요청:
```json
{"question": "출장비 초과 시 어떤 승인이 필요한가?", "top_k": 5}
```

응답:
```json
{
  "contexts": [
    {
      "text": "제 2 조(적용범위)  연구비  지원기관...",
      "source": "Policy.pdf",
      "score": 0.5372
    }
  ]
}
```

- `contexts`: JSON 배열, 각 항목은 `text`(필수), `source`, `score`(권장) 포함
- `text` 길이: 최대 2,000자로 제한
- `score`: 코사인 유사도 기반 retrieval 점수 (소수점 4자리)

## 4. 구현 세부사항

### 4-1. 인덱스 초기화 (lifespan)

FastAPI `lifespan` 이벤트로 서버 시작 시 인덱스를 로드합니다.

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    global INDEX
    INDEX = build_or_load_index()   # storage/ 로드 → 없으면 빌딩
    yield
```

`storage/` 폴더가 존재하면 `load_index_from_storage()`로 빠르게 로드하고, 없으면 Wikipedia + `data/` 6종 포맷을 파싱해 `VectorStoreIndex`를 새로 구축합니다.

### 4-2. /retrieve 처리 흐름

```
요청 JSON → RetrieveRequest 파싱 → INDEX.as_retriever(top_k) → node 목록
  → 각 node에서 text(최대 2000자), source(file_name), score 추출
  → {"contexts": [...]} 반환
```

### 4-3. Docker Compose 설정

```yaml
services:
  rag:
    build: .
    ports:
      - "8000:8000"
    volumes:
      - ./storage:/app/storage   # 인덱스 영속화
      - ./data:/app/data
    command: uvicorn api_server:app --host 0.0.0.0 --port 8000
```

`storage/`를 볼륨 마운트하여 컨테이너 재시작 시에도 인덱스를 재빌딩하지 않습니다.

## 5. 실제 테스트 결과

### /health 확인

```
GET https://isle-composite-jobs-substance.trycloudflare.com/health
→ {"status":"ok","ready":true}
```

### /retrieve 확인 (질문: "Policy.pdf 내용은?", top_k=2)

```json
{
  "contexts": [
    {
      "text": "제 2 조(적용범위)  연구비  지원기관 ...",
      "source": "Policy.pdf",
      "score": 0.5372
    },
    {
      "text": "연구자의 연구수행 자율성 보장 및 지원 ...",
      "source": "Policy.pdf",
      "score": 0.5027
    }
  ]
}
```

## 6. 실행 방법

```bash
# 1. Docker Compose로 RAG API 서버 시작 (포트 8000)
docker compose up -d

# 2. Windows PowerShell에서 Cloudflare Quick Tunnel 시작
.\cloudflared.exe tunnel --url http://127.0.0.1:8000
# → 터미널에 출력된 https://*.trycloudflare.com URL을 rag_endpoint.json에 기록

# 3. public URL로 동작 확인
curl.exe https://<tunnel-url>/health
curl.exe -X POST https://<tunnel-url>/retrieve \
  -H "Content-Type: application/json" \
  -d "{\"question\":\"연구비 지침의 목적은?\",\"top_k\":3}"
```

## 7. URL 유지 규칙

| 상황 | URL 변경 여부 |
|------|:----------:|
| Docker 컨테이너 재시작 | 유지 |
| RAG 서버 코드 수정 후 재배포 | 유지 |
| `cloudflared` 프로세스 종료 후 재실행 | **변경** |
| PC 재부팅 후 재실행 | **변경** |

평가 시간(11:20, 12:20)에는 `cloudflared` 프로세스를 종료하지 마세요. URL이 바뀌면 `rag_endpoint.json`을 수정하고 다시 commit/push 하세요.

---

# Mission 2 — RAG Top-10 실패 케이스 분석

## 실행 방법

```bash
python run_mission2.py
```

`storage/` 폴더에서 인덱스를 로드(없으면 새로 구축)하고, 10개 실패 케이스의 Top-10 검색 결과를 `mission2_log.md`에 저장합니다.

## 실패 원인 분석

**첫 번째 실패 패턴은 청킹(Chunking)으로 인한 구조 파괴다.** `chunk_size=256`으로 문서를 자르면 조항 번호(`5조 3항`)와 본문이 서로 다른 청크에 분리되거나, 표의 헤더-행 관계가 무너진다. 특히 PDF의 조항 구조나 XLSX의 셀 좌표 질문처럼 위치 정보를 포함한 질문은 임베딩 유사도 검색으로 정답 노드를 top-10 안에 올리는 것 자체가 불가능하다. 벡터 검색은 의미적 유사도를 측정하지만, "3행 2열"과 같은 좌표 기반 질의는 의미가 아닌 위치 정보를 요구하기 때문이다.

**두 번째 실패 패턴은 단일 임베딩 모델의 언어·도메인 한계다.** `all-MiniLM-L6-v2`는 영어 중심 모델로, 한국어 질문(`파이썬의 GIL이 멀티스레딩 성능에 미치는 영향은?`)을 영어 Wikipedia 청크와 매핑할 때 다국어 정렬이 약해 관련 청크가 top-10 하위권으로 밀린다. 또한 멀티홉 질문처럼 두 문서를 동시에 참조해야 하는 경우, 단일 쿼리 벡터가 두 문서의 청크를 동시에 높은 순위로 끌어올리지 못해 조합적 추론이 근본적으로 불가능하다.

**세 번째 실패 패턴은 파서 한계로 인한 정보 누락이다.** HWPReader는 그림 캡션을 추출하지 못하고, OCR 기반 이미지 처리는 저해상도나 손글씨에서 문단 구분이 무너진다. 이렇게 파서 단계에서 이미 정보가 사라지면 어떤 검색 전략을 써도 해당 내용을 찾을 수 없다. 범위 초과 질문(인덱스에 없는 정보)이나 환각 유발 질문(문서에 수치가 없는데 숫자를 요구) 역시 Retrieval 이전에 데이터 설계 문제로 귀결된다.

| # | 실패 유형 | 핵심 원인 |
|---|----------|----------|
| 1 | 구조적 위치 질의 | chunk_size=256으로 조항 번호·본문 분리 |
| 2 | 표 셀 좌표 질의 | to_markdown() 변환으로 행 번호 소실 |
| 3 | 멀티홉 교차 문서 | 단일 쿼리 벡터로 2개 문서 동시 매핑 불가 |
| 4 | 이미지 OCR 품질 | 저품질 OCR로 문단 구분 붕괴 |
| 5 | HWP 그림 캡션 | HWPReader가 캡션 미추출 → 인덱스 부재 |
| 6 | 한영 언어 불일치 | 한국어 쿼리 ↔ 영어 청크 임베딩 불일치 |
| 7 | 수치 집계 | 목록이 여러 청크에 분산 → 전체 개수 파악 불가 |
| 8 | 청크 경계 분리 | 위치 기반 질의에 벡터 유사도 검색 부적합 |
| 9 | 범위 초과 | 인덱스에 없는 정보는 어떤 방법으로도 검색 불가 |
| 10 | 환각 유발 수치 | 근거 노드에 정답 수치 자체가 없음 |

---

## 실제 발굴 사례 — UI 매뉴얼 문서에서의 시각 위치 질의 실패

### 질문
> "로그인 버튼은 화면 어디에 있나요?"

### 실제 응답
```
[Source: Local data/] LLM error (ClientError). Retriever-only results:
[manual.pdf] Ⅱ. 학자금대출 실행 [ 일반 / 취업후 ] • 사후관리확약 전자서명수단으로 동의 ...
[manual.pdf] Ⅱ. 학자금대출 실행 ( 분할납부 연계대출 - 등록금 ) • 대출 거래 약정에 "예, 내용에 동의합니다" ...
[manual.pdf] 학자금대출 실행 ( 분할납부 연계대출 - 등록금 ) Step 2. 대출조건입력 ...
```

### 실패 원인 분석

`manual.pdf`는 학자금 대출 서비스의 사용자 매뉴얼로, 각 단계별 UI 화면 캡처 이미지와 텍스트 설명이 함께 구성된 문서다. "로그인 버튼은 화면 어디에 있나요?"라는 질문은 버튼의 **시각적 위치(좌측 상단, 중앙 등)**를 묻는 것이지만, RAG 파이프라인은 이 질문에 전혀 관련 없는 대출 실행 절차 텍스트 청크를 반환했다.

이 실패는 두 가지 구조적 한계가 겹쳐서 발생한다. 첫째, PDF에 포함된 UI 스크린샷 이미지는 `PDFReader`가 텍스트로 추출하지 못한다. 버튼의 위치·색상·레이아웃 같은 시각 정보는 이미지 안에만 존재하므로 아예 인덱스에 포함되지 않는다. 둘째, 설령 "로그인" 키워드가 텍스트에 등장하더라도 그 텍스트는 버튼의 위치가 아닌 절차 설명이므로, 유사도 검색이 "로그인 버튼 위치"라는 의도와 맞지 않는 청크를 끌어온다.

결국 이 유형의 질문은 **텍스트 기반 RAG의 근본적 맹점**을 드러낸다. UI 매뉴얼처럼 이미지와 텍스트가 혼합된 문서에서 시각적 위치를 묻는 질의는, 멀티모달 모델(이미지 이해 가능)이나 UI 좌표 메타데이터를 별도로 구조화하지 않는 한 텍스트 벡터 검색으로는 해결이 불가능하다.

| 항목 | 내용 |
|------|------|
| 문서 | manual.pdf (학자금 대출 UI 매뉴얼) |
| 질문 유형 | 시각적 UI 위치 질의 |
| 실패 원인 | PDF 내 이미지는 텍스트 추출 불가 → 인덱스 부재 |
| 검색 결과 | 무관한 대출 절차 텍스트 청크 반환 |
| 개선 방안 | 멀티모달 모델 도입 또는 UI 요소 좌표를 메타데이터로 구조화 |

---

# Retrieval API Baseline Report

## 1. 실행 방식

- **RAG 서버 실행 방식**: Docker (`docker compose up -d`, port 8000)
- **Cloudflare Quick Tunnel URL**: `https://isle-composite-jobs-substance.trycloudflare.com`
- **사용한 데이터**: Mock (하드코딩된 고정 contexts — Policy.pdf·SRS.docx·Wikipedia 내용 기반)
- **사용한 index/retriever**: Mock 서버 (실제 RAG 교체 전 endpoint 스펙 및 응답 형식 검증용)

## 2. Public URL self-check

- **/health 결과**: `{"status":"ok","ready":true}`
- **/retrieve 테스트 질문**: `출장비 초과 시 어떤 승인이 필요한가?`
- **/retrieve 반환 contexts 수**: 5개 (`top_k=5` 기준)

## 3. Baseline 검색 결과

| 질문 | 기대 정보 | 검색된 context에 포함 여부 | 실패 원인 |
|---|---|---|---|
| 출장비 초과 시 어떤 승인이 필요한가? | 출장비 한도·승인 절차 | ❌ 미포함 | Mock 서버 — 질문과 무관하게 고정 contexts 반환 |
| 연구비 지침의 목적은 무엇인가? | 연구비 지침 목적 조항 | △ 부분 포함 | 고정 contexts에 Policy.pdf 조항 일부 포함되나 목적 조항과 일치하지 않음 |
| 비기능 요구사항 항목은 몇 개인가? | SRS.docx 비기능 요구사항 목록 | △ 부분 포함 | 고정 contexts에 SRS.docx 비기능 요구사항 문장 1건 포함되나 전체 목록 아님 |

> **비고**: 현재 Mock RAG로 동작 중. 질문이 달라도 동일한 contexts가 반환되는 구조이므로 검색 품질 평가 의미 없음. 실제 VectorStoreIndex 기반 RAG 교체 후 재평가 예정.

## 4. 다음 개선 계획

- **chunking**: `chunk_size=256, overlap=50` → 한국어 문서에 맞게 `chunk_size=512` 상향 검토
- **metadata**: 파일명·조항 번호·페이지 번호 메타데이터 보강으로 필터링 검색 지원
- **query rewrite**: 한국어 질문을 영어로 번역 후 검색하여 `all-MiniLM-L6-v2` 다국어 성능 개선
- **reranker/top_k**: `similarity_top_k` 5→10으로 확대 후 reranker 적용해 최종 top_k 압축
