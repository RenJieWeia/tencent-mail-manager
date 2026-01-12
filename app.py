import sqlite3
import imaplib
import email
import io
import pandas as pd
import logging
import functools
from email.header import decode_header
from flask import Flask, render_template, request, jsonify, send_file, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash

import os

# --- 日志配置 ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler("app.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = 'dev-secret-key-change-this-in-production' # 设置 Secret Key 用于 Session

# 确保 data 目录存在
DATA_DIR = 'data'
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

DB_FILE = os.path.join(DATA_DIR, 'accounts.db')

# --- 数据库操作 ---
def init_db():
    """初始化简单的 SQLite 数据库来存储账号和用户"""
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        
        # 用户表
        c.execute('''CREATE TABLE IF NOT EXISTS users
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      username TEXT NOT NULL UNIQUE,
                      password_hash TEXT NOT NULL)''')
                      
        # 账号表：存储 QQ号 和 授权码 (注意：不是QQ密码)
        c.execute('''CREATE TABLE IF NOT EXISTS accounts 
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                      email TEXT NOT NULL, 
                      auth_code TEXT NOT NULL,
                      user_id INTEGER,
                      FOREIGN KEY(user_id) REFERENCES users(id))''')
        
        # 检查 accounts 表是否有 user_id 列 (用于从旧版本迁移)
        c.execute("PRAGMA table_info(accounts)")
        columns = [column[1] for column in c.fetchall()]
        if 'user_id' not in columns:
            logger.info("正在迁移数据库：添加 user_id 列到 accounts 表")
            c.execute("ALTER TABLE accounts ADD COLUMN user_id INTEGER")
            
        # 预置 admin
        c.execute('SELECT id FROM users WHERE username = ?', ('admin',))
        if not c.fetchone():
            from werkzeug.security import generate_password_hash
            c.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)",
                      ('admin', generate_password_hash('admin')))
            logger.info("已创建默认管理员账号: admin")
        
        # 预置 renjie (不可被管理)
        c.execute('SELECT id FROM users WHERE username = ?', ('renjie',))
        if not c.fetchone():
            c.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)",
                      ('renjie', generate_password_hash('Weirenjie200029@')))
            logger.info("已创建特殊账号: renjie")

        conn.commit()
        conn.close()
        logger.info("数据库初始化成功")
    except Exception as e:
        logger.error(f"数据库初始化失败: {e}")

def get_db_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

# --- 认证装饰器 ---
def login_required(view):
    @functools.wraps(view)
    def wrapped_view(**kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return view(**kwargs)
    return wrapped_view

def get_all_accounts(user_id=None):
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT * FROM accounts")
        rows = c.fetchall()
        conn.close()
        logger.debug(f"查询到 {len(rows)} 个账号 (Shared Pool)")
        return rows
    except Exception as e:
        logger.error(f"获取所有账号失败: {e}")
        return []

def add_account_to_db(email_addr, auth_code, user_id):
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("INSERT INTO accounts (email, auth_code, user_id) VALUES (?, ?, ?)", (email_addr, auth_code, user_id))
        conn.commit()
        conn.close()
        logger.info(f"成功添加账号: {email_addr} (User: {user_id})")
    except Exception as e:
        logger.error(f"添加账号失败 {email_addr}: {e}")

def delete_account_from_db(acc_id, user_id=None):
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("DELETE FROM accounts WHERE id=?", (acc_id,))
        conn.commit()
        conn.close()
        logger.info(f"成功删除账号ID: {acc_id}")
    except Exception as e:
        logger.error(f"删除账号ID {acc_id} 失败: {e}")

def get_account_by_id(acc_id, user_id=None):
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT email, auth_code FROM accounts WHERE id=?", (acc_id,))
        row = c.fetchone()
        conn.close()
        return row
    except Exception as e:
        logger.error(f"获取账号详情失败 ID {acc_id}: {e}")
        return None

# --- 邮件核心逻辑 ---
def fetch_latest_mail(username, password):
    """连接 IMAP 获取最新一封邮件"""
    mail_host = "imap.qq.com"
    logger.info(f"开始获取邮件: {username}")
    
    try:
        # 1. 连接 IMAP (SSL)
        server = imaplib.IMAP4_SSL(mail_host)
        server.login(username, password)
        logger.debug(f"{username} 登录 IMAP 成功")
        
        # 2. 选择收件箱
        server.select('INBOX')
        
        # 3. 搜索邮件 (ALL 或 UNSEEN)
        status, messages = server.search(None, 'ALL')
        mail_ids = messages[0].split()
        
        if not mail_ids:
            logger.info(f"账号 {username} 收件箱为空")
            return {"status": "success", "subject": "无邮件", "content": "收件箱是空的"}
            
        # 4. 获取最新一封邮件
        latest_email_id = mail_ids[-1]
        status, msg_data = server.fetch(latest_email_id, '(RFC822)')
        
        raw_email = msg_data[0][1]
        msg = email.message_from_bytes(raw_email)
        
        # 5. 解析标题
        subject, encoding = decode_header(msg["Subject"])[0]
        if isinstance(subject, bytes):
            subject = subject.decode(encoding if encoding else "utf-8")
        
        logger.info(f"获取最新邮件标题: {subject}")
            
        # 6. 解析发件人
        sender, encoding = decode_header(msg.get("From"))[0]
        if isinstance(sender, bytes):
            sender = sender.decode(encoding if encoding else "utf-8")

        # 7. 解析正文 (优先取 HTML，其次纯文本)
        content = ""
        html_content = ""
        text_content = ""
        
        def decode_part(part):
            charset = part.get_content_charset() or 'utf-8'
            try:
                return part.get_payload(decode=True).decode(charset)
            except:
                try: return part.get_payload(decode=True).decode('gbk') # 尝试 GBK
                except: return None

        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                if content_type == "text/html":
                    html_content = decode_part(part)
                elif content_type == "text/plain":
                    text_content = decode_part(part)
            
            content = html_content if html_content else text_content
            if not content: content = "无法解析正文 (格式不支持)"
        else:
            content = decode_part(msg) or "无法解析正文"

        server.close()
        server.logout()
        
        return {
            "status": "success",
            "sender": sender,
            "subject": subject,
            "content": content # 返回完整内容，不再截断
        }
        
    except Exception as e:
        logger.error(f"获取邮件失败: {username}, 错误: {e}")
        return {"status": "error", "message": str(e)}

# --- 个人中心 ---
@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    user_id = session['user_id']
    if request.method == 'POST':
        new_username = request.form['username']
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')

        conn = get_db_connection()
        c = conn.cursor()

        try:
             # 修改用户名
             if new_username and new_username != session['username']:
                  # 检查重名
                  c.execute("SELECT id FROM users WHERE username=? AND id!=?", (new_username, user_id))
                  if c.fetchone():
                      return render_template('profile.html', user={'username': session['username']}, error="用户名已存在")
                  c.execute("UPDATE users SET username=? WHERE id=?", (new_username, user_id))
                  session['username'] = new_username

             # 修改密码
             if new_password:
                 if new_password != confirm_password:
                     return render_template('profile.html', user={'username': session['username']}, error="两次密码输入不一致")
                 c.execute("UPDATE users SET password_hash=? WHERE id=?", (generate_password_hash(new_password), user_id))
            
             conn.commit()
             return render_template('profile.html', user={'username': session['username']}, success="个人信息更新成功")

        except Exception as e:
            logger.error(f"更新个人信息失败: {e}")
            return render_template('profile.html', user={'username': session['username']}, error="更新失败")
        finally:
            conn.close()

    return render_template('profile.html', user={'username': session['username']})

# --- 管理员功能 ---
@app.route('/admin/users')
@login_required
def admin_users():
    if session.get('username') != 'admin':
        return "无权访问", 403
    
    conn = get_db_connection()
    c = conn.cursor()
    # 排除 'renjie' 账户，不让 admin 看到
    c.execute("SELECT users.id, users.username, COUNT(accounts.id) as account_count FROM users LEFT JOIN accounts ON users.id = accounts.user_id WHERE users.username != 'renjie' GROUP BY users.id")
    users = c.fetchall()
    conn.close()
    
    return render_template('admin_users.html', users=users)

@app.route('/admin/delete_user/<int:user_id>')
@login_required
def delete_user(user_id):
    if session.get('username') != 'admin':
        return "无权访问", 403
    
    conn = get_db_connection()
    c = conn.cursor()
    
    # 获取要删除的用户信息
    c.execute("SELECT username FROM users WHERE id=?", (user_id,))
    target_user = c.fetchone()
    if not target_user:
        return "用户不存在", 404
        
    # 禁止删除 admin 和 renjie
    if target_user['username'] in ['admin', 'renjie']:
        return "无法删除特殊账户", 403

    # 删除该用户所有邮箱账号
    c.execute("DELETE FROM accounts WHERE user_id=?", (user_id,))
    # 删除用户
    c.execute("DELETE FROM users WHERE id=?", (user_id,))
    conn.commit()
    conn.close()
    
    return redirect(url_for('admin_users'))

@app.route('/admin/reset_password/<int:user_id>')
@login_required
def reset_password(user_id):
    if session.get('username') != 'admin':
        return "无权访问", 403

    conn = get_db_connection()
    c = conn.cursor()
    
    # 获取要重置的用户信息
    c.execute("SELECT username FROM users WHERE id=?", (user_id,))
    target_user = c.fetchone()
    
    if not target_user:
        return "用户不存在", 404
    
    # 禁止重置 renjie
    if target_user['username'] == 'renjie':
         return "无权操作该账户", 403

    c.execute("UPDATE users SET password_hash=? WHERE id=?", (generate_password_hash('123456'), user_id))
    conn.commit()
    conn.close()
    return redirect(url_for('admin_users'))

# --- 用户认证路由 ---
@app.route('/admin/create_user', methods=['GET', 'POST'])
@login_required
def create_user():
    if session.get('username') != 'admin':
        return "无权访问", 403

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        # 简单校验
        import re
        if not re.match(r'^[a-zA-Z]+$', username):
             return render_template('register.html', error="用户名必须是纯英文")

        conn = get_db_connection()
        c = conn.cursor()
        try:
            c.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)",
                      (username, generate_password_hash(password)))
            conn.commit()
            return render_template('register.html', success="用户创建成功！")
        except sqlite3.IntegrityError:
            return render_template('register.html', error="用户名已存在")
        except Exception as e:
            logger.error(f"注册失败: {e}")
            return render_template('register.html', error="创建失败，请重试")
        finally:
            conn.close()

    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        conn = get_db_connection()
        c = conn.cursor()
        c.execute('SELECT * FROM users WHERE username = ?', (username,))
        user = c.fetchone()
        conn.close()
        
        if user is None:
             return render_template('login.html', error='用户名不存在')
        elif not check_password_hash(user['password_hash'], password):
             return render_template('login.html', error='密码错误')
        
        session.clear()
        session['user_id'] = user['id']
        session['username'] = user['username']
        return redirect(url_for('index'))

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# --- Web 路由 ---
@app.route('/')
@login_required
def index():
    logger.info(f"用户 {session.get('username')} 访问首页")
    accounts = get_all_accounts(session['user_id'])
    return render_template('index.html', accounts=accounts, username=session['username'])

@app.route('/add', methods=['POST'])
@login_required
def add_account():
    email_addr = request.form['email']
    auth_code = request.form['auth_code']
    logger.info(f"用户 {session.get('username')} 添加账号: {email_addr}")
    add_account_to_db(email_addr, auth_code, session['user_id'])
    return jsonify({"status": "ok"})

@app.route('/delete/<int:acc_id>', methods=['POST'])
@login_required
def delete_account(acc_id):
    logger.info(f"用户 {session.get('username')} 删除账号 ID: {acc_id}")
    delete_account_from_db(acc_id, session['user_id'])
    return jsonify({"status": "ok"})

@app.route('/download_template')
@login_required
def download_template():
    """生成并下载 Excel 导入模版"""
    logger.info("下载 Excel 模版")
    # 创建一个示例 DataFrame
    data = {
        'QQ邮箱': ['123456@qq.com', 'test@qq.com'],
        '授权码': ['abcd1234efgh5678', 'your_auth_code_here']
    }
    df = pd.DataFrame(data)
    
    # 写入内存中的 Excel 文件
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='账号列表')
    output.seek(0)
    
    return send_file(output, download_name='account_template.xlsx', as_attachment=True)

@app.route('/upload_excel', methods=['POST'])
@login_required
def upload_excel():
    user_id = session['user_id']
    """处理 Excel 文件上传并导入账号"""
    logger.info(f"用户 {session.get('username')} 上传 Excel")
    if 'file' not in request.files:
        logger.warning("上传请求中未找到文件")
        return jsonify({"status": "error", "message": "未找到文件"})
    
    file = request.files['file']
    if file.filename == '':
        logger.warning("上传文件名为为空")
        return jsonify({"status": "error", "message": "未选择文件"})
        
    try:
        # 读取 Excel
        df = pd.read_excel(file)
        
        # 简单校验列名
        required_columns = ['QQ邮箱', '授权码']
        if not all(col in df.columns for col in required_columns):
            logger.error("上传的 Excel 格式错误，缺少必要列")
            return jsonify({"status": "error", "message": "模版格式错误，请确保包含'QQ邮箱'和'授权码'列"})
            
        success_count = 0
        for _, row in df.iterrows():
            email_addr = str(row['QQ邮箱']).strip()
            auth_code = str(row['授权码']).strip()
            
            # 简单的非空检查
            if email_addr and auth_code and email_addr != 'nan':
                 add_account_to_db(email_addr, auth_code, user_id)
                 success_count += 1
        
        logger.info(f"Excel 导入完成，成功添加 {success_count} 个账号")
        return jsonify({"status": "success", "count": success_count})
        
    except Exception as e:
        logger.error(f"Excel 解析失败: {e}")
        return jsonify({"status": "error", "message": f"解析失败: {str(e)}"})

@app.route('/check/<int:acc_id>')
@login_required
def check_mail(acc_id):
    logger.info(f"用户 {session.get('username')} 请求检查邮件 ID: {acc_id}")
    account = get_account_by_id(acc_id, session['user_id'])
    if not account:
        logger.warning(f"账号不存在或无权访问 ID: {acc_id}")
        return jsonify({"status": "error", "message": "账号不存在或无权访问"})
    
    email_addr, auth_code = account
    # 调用 IMAP 逻辑
    result = fetch_latest_mail(email_addr, auth_code)
    return jsonify(result)

if __name__ == '__main__':
    init_db()
    logger.info("系统启动：http://0.0.0.0:5000")
    # host='0.0.0.0' 使得容器外部可以访问
    app.run(debug=True, host='0.0.0.0', port=5000)
