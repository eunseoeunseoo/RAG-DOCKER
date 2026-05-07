FROM python:3.10

WORKDIR /app

# tesseract-ocr: PNG OCR 지원 (한국어 언어팩 포함)
RUN apt-get update && \
    apt-get install -y tesseract-ocr tesseract-ocr-kor && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 7860
EXPOSE 8000

CMD ["uvicorn", "api_server:app", "--host", "0.0.0.0", "--port", "8000"]