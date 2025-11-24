# Python rasmiy image (kichik hajmli)
FROM python:3.12-slim

# Ishchi papka
WORKDIR /app

# Kerakli paketlar (Debian)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Python kutubxonalarni oʻrnatish
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Kodlarni koʻchirish
COPY main.py .

# Muhtit oʻzgaruvchilari (Railwayda oʻrniga .env yoki Variables qoʻshasiz)
ENV BOT_TOKEN=your_token_here
ENV ADMIN_ID=123456789

# Botni ishga tushirish
CMD ["python", "main.py"]
