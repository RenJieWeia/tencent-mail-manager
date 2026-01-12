# MailNest

这是一个基于 Python Flask 开发的轻量级 Web 应用，旨在帮助用户集中管理多个 QQ 邮箱账号。支持账号的批量导入、实时查看最新邮件、以及 Docker 容器化部署。

## ✨ 主要功能

*   **集中管理**：在左侧列表统一查看所有保存的邮箱账号。
*   **邮件预览**：点击账号即可通过 IMAP 协议直连腾讯服务器，实时获取并渲染最新一封邮件（支持 HTML 内容和图片显示）。
*   **批量导入**：支持通过 Excel 模版批量导入多个账号（自动下载模版）。
*   **快捷搜索**：内置实时搜索栏，快速定位目标邮箱。
*   **账号管理**：支持单条账号的添加（通过导入）和删除操作。
*   **美观界面**：采用 Bootstrap 5 和 Inter 字体打造的现代化清爽 UI。
*   **日志系统**：详细的后台操作日志 (`app.log`)，方便维护排查。

## 🛠️ 技术栈

*   **后端**：Python 3.9+, Flask, SQLite
*   **前端**：HTML5, Bootstrap 5, JavaScript
*   **邮件协议**：IMAP (SSL)
*   **数据处理**：Pandas, OpenPyXL
*   **部署**：Docker, GitHub Actions

## 🚀 快速开始

### 方式一：本地直接运行

1.  **克隆项目**
    ```bash
    git clone <your-repo-url>
    cd tencent-mail-manager
    ```

2.  **安装依赖**
    ```bash
    pip install -r requirements.txt
    ```

3.  **运行应用**
    ```bash
    python app.py
    ```

4.  **访问**
    打开浏览器访问 [http://127.0.0.1:5000](http://127.0.0.1:5000)

### 方式二：Docker 部署

1.  **构建镜像**
    ```bash
    docker build -t tencent-mail-manager .
    ```

2.  **运行容器**
    ```bash
    # 运行并挂载数据目录，确保数据持久化
    docker run -d -p 5000:5000 -v $(pwd)/data:/app/data --name mail-manager tencent-mail-manager
    ```

3.  **访问**
    浏览器访问 [http://localhost:5000](http://localhost:5000)

## 📁 项目结构

```
tencent-mail-manager/
├── app.py              # Flask 后端核心逻辑
├── accounts.db         # SQLite 数据库 (自动生成)
├── app.log             # 运行日志 (自动生成)
├── requirements.txt    # Python 依赖列表
├── Dockerfile          # Docker 构建文件
└── templates/
    └── index.html      # 前端界面模板
```

## 📝 注意事项

1.  **授权码**：添加账号时输入的密码必须是 **QQ 邮箱开启 IMAP/SMTP 服务后生成的授权码**，而不是你的 QQ 登录密码。
2.  **网络连接**：由于需要连接 `imap.qq.com`，请确保运行环境能够访问外网。

## 🤝 贡献

欢迎提交 Issue 或 Pull Request 来改进这个项目！

## 📄 许可证

MIT License
