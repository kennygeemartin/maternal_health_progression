FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend backend
COPY frontend frontend
COPY Results/proposed_lstm.pt Results/proposed_lstm.pt
COPY Results/maternal_model_scaler.pkl Results/maternal_model_scaler.pkl
COPY Results/maternal_model_results.json Results/maternal_model_results.json
RUN useradd --create-home bloom && chown -R bloom:bloom /app
USER bloom
EXPOSE 8000
CMD ["python", "-m", "backend.serve"]
