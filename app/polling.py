import threading
import time
import logging
import concurrent.futures
from app.db import get_db
from app.services.email_service import fetch_latest_mail

logger = logging.getLogger(__name__)

class PollingService:
    def __init__(self, app):
        self.app = app
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.last_run_time = 0

    def start(self):
        self.thread.start()

    def _run_loop(self):
        logger.info("Polling service started")
        while True:
            try:
                with self.app.app_context():
                    self._check_and_poll()
            except Exception as e:
                logger.error(f"Polling loop error: {e}")
            
            # Check configuration every 5 seconds
            time.sleep(5) 

    def _check_and_poll(self):
        db = get_db()
        
        # Get settings
        enabled_row = db.execute("SELECT value FROM system_settings WHERE key='polling_enabled'").fetchone()
        interval_row = db.execute("SELECT value FROM system_settings WHERE key='polling_interval'").fetchone()

        enabled = enabled_row and enabled_row['value'] == '1'
        interval = int(interval_row['value']) if interval_row else 300

        if not enabled:
            return

        now = time.time()
        if self.last_run_time > 0 and (now - self.last_run_time) < interval:
            return

        logger.info("Starting polling cycle...")
        self.last_run_time = now
        
        # Fetch accounts (exclude status='error')
        query = "SELECT id, email, auth_code, last_mail_identifier FROM accounts WHERE status != 'error' OR status IS NULL"
        accounts = db.execute(query).fetchall()
        
        # Prepare data for threads to avoid passing SQLite Row objects across threads
        account_data_list = [{'id': row['id'], 'email': row['email'], 'auth_code': row['auth_code'], 'last_identifier': row['last_mail_identifier']} for row in accounts]

        def poll_task(acc_info):
            try:
                # 这里的逻辑主要是网络 IO 操作
                result = fetch_latest_mail(acc_info['email'], acc_info['auth_code'])
                new_status = 'success' if result['status'] == 'success' else 'error'
                
                # Check for new mail
                has_new = False
                current_identifier = None
                if new_status == 'success':
                    # Create a simple identifier: "subject|sender" (or handle potential None values)
                    subject = result.get('subject', '')
                    sender = result.get('sender', '')
                    current_identifier = f"{subject}|{sender}"
                    
                    # If identifier changed and not empty, it's new mail
                    # Note: First time run (last_identifier is None) -> also counts as new if we want,
                    # or only if it changes. Let's assume initialized accounts have None.
                    # If we set has_new=True on first run, all accounts will light up.
                    # However, "Polling" implies looking for updates.
                    # If last_identifier is None, maybe we just save it but don't flag as new?
                    # Or we flag it as new so user sees it? Let's flag as new to be safe.
                    if current_identifier != acc_info['last_identifier']:
                        has_new = True
                
                return {
                    'id': acc_info['id'], 
                    'status': new_status, 
                    'has_new': has_new,
                    'identifier': current_identifier
                }
            except Exception as e_poll:
                logger.error(f"Thread error polling {acc_info['email']}: {e_poll}")
                return None

        # 使用线程池并发执行，例如最多 10 个并发
        results_to_update = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            # 提交任务
            future_to_acc = {executor.submit(poll_task, acc): acc for acc in account_data_list}
            
            for future in concurrent.futures.as_completed(future_to_acc):
                res = future.result()
                if res:
                    results_to_update.append(res)
        
        # 回到主循环线程统一更新数据库 (避免 SQLite 多线程写锁问题)
        if results_to_update:
            try:
                for res in results_to_update:
                    if res['status'] == 'success':
                         if res['has_new']:
                            db.execute("UPDATE accounts SET status = ?, has_new_mail = 1, last_mail_identifier = ? WHERE id = ?", 
                                       (res['status'], res['identifier'], res['id']))
                         else:
                            # Just update status (keep has_new_mail as is, usually)
                            # Or if it's the SAME email, has_new_mail should stay whatever it was (1 or 0).
                            # So we don't touch has_new_mail unless it's new.
                            db.execute("UPDATE accounts SET status = ? WHERE id = ?", (res['status'], res['id']))
                    else:
                         db.execute("UPDATE accounts SET status = ? WHERE id = ?", (res['status'], res['id']))
                         
                db.commit()
                logger.info(f"Updated {len(results_to_update)} accounts status.")
            except Exception as e:
                logger.error(f"Database update error: {e}")

        logger.info("Polling cycle completed")
