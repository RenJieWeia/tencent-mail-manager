import imaplib
import email
from email.header import decode_header
import logging

logger = logging.getLogger(__name__)

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
