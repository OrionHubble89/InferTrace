FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md LICENSE constraints.txt ./
COPY infertrace ./infertrace
RUN python -m pip install --no-cache-dir -c constraints.txt .
COPY examples ./examples
COPY scripts ./scripts
RUN mkdir /data && chown 10001:10001 /data
USER 10001
EXPOSE 8080
CMD ["python", "-m", "infertrace.api", "--host", "0.0.0.0", "--db", "/data/infertrace.db"]
