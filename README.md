# Tencent Mail Manager (MailNest)

A Flask-based application for managing multiple QQ Mail accounts effectively.

## Features

- **Multi-Account Management**: Add, delete, and view emails from multiple QQ accounts.
- **Audit Logging**: Tracks critical actions (Login, Delete, Add).
- **Default Ownership Control**: Configure whether new accounts belong to the creator or the admin automatically.
- **Admin Roles**: 
    - `renjie`: Super Admin with full system access.
    - `admin`: Standard Admin (dashboard access configurable by Super Admin).
- **Data Isolation Mode**: 
    - Toggleable feature for strict data scoping.
    - When enabled, users only see accounts assigned to them.
    - Admins can assign accounts to users in bulk.
- **Scale Ready**: Optimized for managing up to 10k emails.

## Project Structure

```
├── app/
│   ├── routes/         # Blueprints for Main and Admin routes
│   ├── services/       # Business logic (Email fetching)
│   ├── templates/      # HTML Templates
│   ├── __init__.py     # App Factory
│   ├── auth.py         # Authentication logic
│   ├── db.py           # Database connection and schema
│   └── audit.py        # Audit logging helper
├── data/               # SQLite Database storage
├── run.py              # Application Entry Point
├── Dockerfile          # Container configuration
└── requirements.txt    # Python dependencies
```

## Setup & Run

1. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Run the Application**:
   ```bash
   python run.py
   ```
   The app will start at `http://0.0.0.0:5000`.

3. **Login Credentials**:
   - Admin: `admin` / `admin`
   - Super Admin: `renjie` / `Weirenjie200029@`

## Data Isolation Mode

1. Login as `admin` or `renjie`.
2. Navigate to **Admin Dashboard**.
3. Toggle "Isolation Mode" ON.
4. Use the API or Dashboard to assign accounts to specific users.
   - **Bulk Assignment API**: POST `/admin/bulk_assign`
     ```json
     {
       "account_ids": [1, 2, 3],
       "user_id": 5
     }
     ```

## Development

- **Database**: SQLite (`data/accounts.db`).
- **Templates**: Uses Jinja2 and Bootstrap 5.

---

# 腾讯邮箱管理器 (MailNest) - 中文说明

这是一个基于 Flask 的应用程序，用于高效管理多个 QQ 邮箱账号。

## 功能特性

- **多账号管理**: 添加、删除和查看来自多个 QQ 账号的邮件。
- **审计日志**: 追踪关键操作（登录、删除、添加）。
- **默认归属权控制**: 配置新添加的账号是归属于添加人还是自动归属于管理员。
- **管理员角色**: 
    - `renjie`: 超级管理员，拥有完整系统权限。
    - `admin`: 普通管理员 (后台访问权限可由超管配置)。
- **数据隔离模式**: 
    - 可切换的严格数据权限功能。
    - 启用后，普通用户只能看到分配给他们的账号。
    - 管理员可以批量分配账号给用户。
- **扩展性**: 针对管理多达 1万+ 邮箱进行了优化。

## 项目结构

```
├── app/
│   ├── routes/         # 主路由和管理员路由蓝图
│   ├── services/       # 业务逻辑 (邮件获取)
│   ├── templates/      # HTML 模版
│   ├── __init__.py     # 应用工厂函数
│   ├── auth.py         # 认证逻辑
│   ├── db.py           # 数据库连接和表结构
│   └── audit.py        # 审计日志助手
├── data/               # SQLite 数据库文件
├── run.py              # 程序入口
├── Dockerfile          # Docker 容器配置
└── requirements.txt    # Python 依赖项
```

## 安装与运行

1. **安装依赖**:
   ```bash
   pip install -r requirements.txt
   ```

2. **运行应用**:
   ```bash
   python run.py
   ```
   应用将在 `http://0.0.0.0:5000` 启动。

3. **默认登录凭据**:
   - 管理员: `admin` / `admin`
   - 超级管理员: `renjie` / `Weirenjie200029@`

## 数据隔离模式

1. 使用 `admin` 或 `renjie` 登录。
2. 进入 **管理后台 (Admin Dashboard)**。
3. 开启 "数据隔离模式 (Isolation Mode)"。
4. 使用 API 或后台将账号分配给特定用户。
   - **批量分配 API**: POST `/admin/bulk_assign`
     ```json
     {
       "account_ids": [1, 2, 3],
       "user_id": 5
     }
     ```

## 开发

- **数据库**: SQLite (`data/accounts.db`).
- **模版引擎**: 使用 Jinja2 和 Bootstrap 5.
