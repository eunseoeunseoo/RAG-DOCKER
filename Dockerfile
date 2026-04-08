FROM python:3.10

WORKDIR /app

# tesseract-ocr: PNG OCR 지원 (한국어 언어팩 포함)
RUN apt-get update && \
    apt-get install -y tesseract-ocr tesseract-ocr-kor && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "app.py"]