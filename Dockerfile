FROM python:3.12-slim

WORKDIR /app

# 安装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制源码
COPY server.py .

# 默认以 streamable-http 模式运行
EXPOSE 8000
CMD ["python3", "server.py", "--transport", "streamable-http", "--host", "0.0.0.0", "--port", "8000"]
