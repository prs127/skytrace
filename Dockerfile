# Skytrace live server for Google Cloud Run (also works locally: docker run -p 8080:8080 skytrace)
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend ./backend
COPY frontend ./frontend
# Fetch the official SPHEREx solid-angle pixel maps (6 x 16 MB) and per-pixel channel map from the public IRSA S3 bucket
# into backend/sapm/ at build time, so live requests never wait for them.
RUN cd backend && python -c "import pipeline as P; [P.sapm(d) for d in range(1, 7)]; assert P.channel_map('dr1') is not None; print('calibration maps ok')"
ENV SKYTRACE_MAX_JOBS=2 SKYTRACE_MAX_EXPOSURES=700 PORT=8080
WORKDIR /app/backend
EXPOSE 8080
# Cloud Run sets $PORT; default 8080.
CMD ["sh", "-c", "exec uvicorn server:app --host 0.0.0.0 --port ${PORT:-8080}"]
