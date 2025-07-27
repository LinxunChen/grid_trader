# 使用一个轻量级的 Python 官方镜像作为基础
FROM python:3.9-slim

# 设置工作目录
WORKDIR /app

# 复制依赖文件和源代码到容器中
COPY requirements.txt .
COPY grid_trader.py .
COPY config.json .

# 安装依赖
RUN pip install --no-cache-dir -r requirements.txt

# 容器启动时执行的命令
CMD ["python", "-u", "grid_trader.py"]
