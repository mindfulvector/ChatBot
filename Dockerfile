FROM python:3.10

WORKDIR /app

# Copy and install requirements.txt file separately so it is in it's own filesystem layer
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application's code into the container in a separate layer
COPY . .

CMD ["python3","chat.py"]
