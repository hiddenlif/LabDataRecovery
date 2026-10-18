FROM python:3.13-slim@sha256:70729b46c69b4f1e97c4822c1af3df53a1476cf5ddc6c087c0c10bc3a5678c2f
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --require-hashes -r /tmp/requirements.txt
WORKDIR /app
COPY src /app/src
COPY examples /app/examples
COPY docs /app/docs
COPY README.md NOTICE.md /app/
ENV PYTHONPATH=/app/src
RUN mkdir /data && chown 10001:10001 /data
USER 10001:10001
WORKDIR /data
ENTRYPOINT ["python", "-m", "truegate.cli"]
