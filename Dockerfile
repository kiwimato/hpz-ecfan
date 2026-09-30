# hpz-ecfan in a container, for hosts without Python (Unraid, appliances).
# Needs /dev/port and CAP_SYS_RAWIO; see docker-compose.yml.
FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY hpz_ecfan ./hpz_ecfan
RUN pip install --no-cache-dir . && rm -rf /root/.cache
ENV HPZ_EC_LOCK=/lock/ecmbox
ENTRYPOINT ["hpz-ecfan"]
CMD ["status"]
