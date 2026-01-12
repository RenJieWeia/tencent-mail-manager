# 使用官方 Python 轻量级镜像
FROM python:3.9-slim

# 设置工作目录
WORKDIR /app

# 复制依赖文件
COPY requirements.txt .

# 安装依赖
# 使用清华源加速安装 (可选，如果构建网络环境在国内)
RUN pip install --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 复制项目的所有文件到容器中
COPY . .

# 暴露端口
EXPOSE 5000

# 声明数据卷，方便持久化数据
VOLUME ["/app/data"]

# 启动命令
CMD ["python", "app.py"]
