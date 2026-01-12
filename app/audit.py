from flask import request, current_app
from app.db import get_db

def log_audit(username, action, details=None):
    try:
        ip_addr = request.remote_addr if request else 'unknown'
        db = get_db()
        db.execute("INSERT INTO audit_logs (username, action, details, ip_address) VALUES (?, ?, ?, ?)",
                  (username, action, details, ip_addr))
        db.commit()
    except Exception as e:
        # Avoid circular dependency or logger issues if app is not fully set up
        print(f"Audit log failed: {e}")
