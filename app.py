import sqlite3
import imaplib
import email
import io
import pandas as pd
import logging
from email.header import decode_header
from flask import Flask, render_template, request, jsonify, send_file

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

# 确保 data 目录存在
DATA_DIR = 'data'
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

DB_FILE = os.path.join(DATA_DIR, 'accounts.db')

# --- 数据库操作 ---
def init_db():
    """初始化简单的 SQLite 数据库来存储账号"""
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        # 创建表：存储 QQ号 和 授权码 (注意：不是QQ密码)
        c.execute('''CREATE TABLE IF NOT EXISTS accounts 
                     (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                      email TEXT NOT NULL, 
                      auth_code TEXT NOT NULL)''')
        conn.commit()
        conn.close()
        logger.info("数据库初始化成功")
    except Exception as e:
        logger.error(f"数据库初始化失败: {e}")

def get_all_accounts():
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT * FROM accounts")
        rows = c.fetchall()
        conn.close()
        logger.debug(f"查询到 {len(rows)} 个账号")
        return rows
    except Exception as e:
        logger.error(f"获取所有账号失败: {e}")
        return []

def add_account_to_db(email_addr, auth_code):
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("INSERT INTO accounts (email, auth_code) VALUES (?, ?)", (email_addr, auth_code))
        conn.commit()
        conn.close()
        logger.info(f"成功添加账号: {email_addr}")
    except Exception as e:
        logger.error(f"添加账号失败 {email_addr}: {e}")

def delete_account_from_db(acc_id):
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("DELETE FROM accounts WHERE id=?", (acc_id,))
        conn.commit()
        conn.close()
        logger.info(f"成功删除账号ID: {acc_id}")
    except Exception as e:
        logger.error(f"删除账号ID {acc_id} 失败: {e}")

def get_account_by_id(acc_id):
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

# --- Web 路由 ---
@app.route('/')
def index():
    logger.info("访问首页")
    accounts = get_all_accounts()
    return render_template('index.html', accounts=accounts)

@app.route('/add', methods=['POST'])
def add_account():
    email_addr = request.form['email']
    auth_code = request.form['auth_code']
    logger.info(f"收到添加账号请求: {email_addr}")
    add_account_to_db(email_addr, auth_code)
    return jsonify({"status": "ok"})

@app.route('/delete/<int:acc_id>', methods=['POST'])
def delete_account(acc_id):
    logger.info(f"收到删除账号请求 ID: {acc_id}")
    delete_account_from_db(acc_id)
    return jsonify({"status": "ok"})

@app.route('/download_template')
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
def upload_excel():
    """处理 Excel 文件上传并导入账号"""
    logger.info("收到 Excel 上传请求")
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
                 add_account_to_db(email_addr, auth_code)
                 success_count += 1
        
        logger.info(f"Excel 导入完成，成功添加 {success_count} 个账号")
        return jsonify({"status": "success", "count": success_count})
        
    except Exception as e:
        logger.error(f"Excel 解析失败: {e}")
        return jsonify({"status": "error", "message": f"解析失败: {str(e)}"})

@app.route('/check/<int:acc_id>')
def check_mail(acc_id):
    logger.info(f"请求检查邮件，账号ID: {acc_id}")
    account = get_account_by_id(acc_id)
    if not account:
        logger.warning(f"账号不存在 ID: {acc_id}")
        return jsonify({"status": "error", "message": "账号不存在"})
    
    email_addr, auth_code = account
    # 调用 IMAP 逻辑
    result = fetch_latest_mail(email_addr, auth_code)
    return jsonify(result)

if __name__ == '__main__':
    init_db()
    logger.info("系统启动：http://0.0.0.0:5000")
    # host='0.0.0.0' 使得容器外部可以访问
    app.run(debug=True, host='0.0.0.0', port=5000)
