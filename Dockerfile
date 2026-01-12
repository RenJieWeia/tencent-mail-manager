# 使用更现代的 Python 3.10-slim 镜像
FROM python:3.10-slim

# 设置环境变量
# 防止 Python 生成 .pyc 文件
ENV PYTHONDONTWRITEBYTECODE=1
# 确保控制台输出不被缓冲，实时打印日志
ENV PYTHONUNBUFFERED=1

# 设置工作目录
WORKDIR /app

# 优先复制依赖文件以利用 Docker 缓存
COPY requirements.txt .

# 安装依赖 (-i 指定镜像源可选，此处保留清华源以加快国内构建)
RUN pip install --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 复制项目所有文件
COPY . .

# 暴露端口
EXPOSE 5000

# 声明数据卷
VOLUME ["/app/data"]

# 启动命令 (更新为 run.py)
CMD ["python", "run.py"]
