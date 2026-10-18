FROM python:3.13-slim@sha256:70729b46c69b4f1e97c4822c1af3df53a1476cf5ddc6c087c0c10bc3a5678c2f
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir --require-hashes -r /tmp/requirements.txt
COPY checks /checks
COPY entry.py /entry.py
COPY runner.py /runner.py
RUN chmod 700 /checks /runner.py && chmod 644 /entry.py
WORKDIR /checks
ENV TG_SOURCE=/candidate TG_ENTRY=/entry.py
ENTRYPOINT ["python", "-I", "/runner.py"]
