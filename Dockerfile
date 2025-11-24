# Python 3.10 asosidagi yengil versiyani olamiz
FROM python:3.10-slim

# Ishchi papkani belgilaymiz
WORKDIR /app

# Kerakli fayllarni nusxalaymiz
COPY requirements.txt .

# Kutubxonalarni o'rnatamiz
RUN pip install --no-cache-dir -r requirements.txt

# Qolgan barcha kodlarni nusxalaymiz
COPY . .

# Botni ishga tushiramiz
CMD ["python", "main.py"]
