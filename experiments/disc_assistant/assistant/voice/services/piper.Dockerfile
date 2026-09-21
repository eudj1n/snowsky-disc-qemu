FROM python:3.11-slim-bookworm
RUN pip install --no-cache-dir piper-tts==1.4.2
WORKDIR /app
COPY piper_server.py /app/piper_server.py
USER 65534:65534
ENTRYPOINT ["python", "/app/piper_server.py"]
CMD ["--host", "0.0.0.0", "--port", "18121", "--voices", "/models/voices.json"]
