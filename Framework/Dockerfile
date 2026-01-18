FROM python:3.9-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Set environment variables
ENV PORT=8080

# Run with Gunicorn
CMD exec gunicorn --bind :$PORT --workers 2 --threads 8 combined_server:app 