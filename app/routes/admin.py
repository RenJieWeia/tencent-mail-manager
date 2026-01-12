from flask import (
    Blueprint, render_template, request, redirect, url_for, flash, g, jsonify
)
import sqlite3
import re
from werkzeug.security import generate_password_hash
from app.auth import login_required
from app.db import get_db
from app.audit import log_audit

bp = Blueprint('admin', __name__, url_prefix='/admin')

@bp.before_request
@login_required
def admin_required():
    if g.user['username'] not in ['admin', 'renjie']:
        return "Access Denied", 403

@bp.route('/dashboard')
def dashboard():
    # Permission Check
    if not g.can_access_dashboard:
        return render_template('base.html', error="Access Denied: You are not authorized to view the dashboard."), 403

    db = get_db()
    users = db.execute("SELECT * FROM users WHERE username != 'renjie'").fetchall()
    
    # Isolation Status
    setting = db.execute("SELECT value FROM system_settings WHERE key='isolation_mode'").fetchone()
    isolation_mode = setting['value'] == '1' if setting else False
    
    # Admin Permission Status
    perm_setting = db.execute("SELECT value FROM system_settings WHERE key='allow_admin_dashboard'").fetchone()
    allow_admin_dashboard = perm_setting['value'] == '1' if perm_setting else False

    # Default Ownership Mode (CHECK THIS: '1' = Self, '0' = Admin)
    # Default is '1' (Self) if not set, to match previous behavior? 
    # User request: "当开启后...默认归属权是添加人 (Self), 关闭后...默认归属权为admin"
    # So '1' = Self (Creator), '0' = Admin.
    own_setting = db.execute("SELECT value FROM system_settings WHERE key='default_ownership_self'").fetchone()
    default_ownership_self = own_setting['value'] == '1' if own_setting else True # Default to True (old behavior)

    return render_template('admin_dashboard.html', 
                            users=users, 
                            isolation_mode=isolation_mode,
                            allow_admin_dashboard=allow_admin_dashboard,
                            default_ownership_self=default_ownership_self)

@bp.route('/toggle_ownership_mode', methods=['POST'])
def toggle_ownership_mode():
    mode = request.form.get('mode') # 'on' (Self) or 'off' (Admin)
    val = '1' if mode == 'on' else '0'
    
    db = get_db()
    db.execute("INSERT OR REPLACE INTO system_settings (key, value) VALUES ('default_ownership_self', ?)", (val,))
    db.commit()
    
    log_audit(g.user['username'], 'TOGGLE_OWNERSHIP', f"Set default ownership to {'Creator' if val=='1' else 'Admin'}")
    flash(f"已设置新账号默认归属为: {'添加人' if val=='1' else 'Admin 账户'}", "success")
    return redirect(url_for('admin.dashboard'))

@bp.route('/toggle_admin_access', methods=['POST'])
def toggle_admin_access():
    if not g.is_super_admin:
        return "Access Denied", 403
        
    mode = request.form.get('mode') # 'on' or 'off'
    val = '1' if mode == 'on' else '0'
    
    db = get_db()
    db.execute("INSERT OR REPLACE INTO system_settings (key, value) VALUES ('allow_admin_dashboard', ?)", (val,))
    db.commit()
    
    log_audit(g.user['username'], 'TOGGLE_ADMIN_ACCESS', f"Set admin dashboard access to {val}")
    flash(f"已{'授权' if val=='1' else '禁止'} Admin 账号访问控制台", "success")
    return redirect(url_for('admin.dashboard'))

@bp.route('/toggle_isolation', methods=['POST'])
def toggle_isolation():
    mode = request.form.get('mode') # 'on' or 'off'
    val = '1' if mode == 'on' else '0'
    
    db = get_db()
    db.execute("INSERT OR REPLACE INTO system_settings (key, value) VALUES ('isolation_mode', ?)", (val,))
    db.commit()
    
    log_audit(g.user['username'], 'TOGGLE_ISOLATION', f"Set isolation to {val}")
    flash(f"Data Isolation Mode turned {'ON' if val=='1' else 'OFF'}")
    return redirect(url_for('admin.dashboard'))

@bp.route('/users')
def users_list():
    db = get_db()
    # Exclude renjie from list if logged in as admin? 
    # Original logic: "users.username != 'renjie'"
    query = "SELECT users.id, users.username, COUNT(accounts.id) as account_count FROM users LEFT JOIN accounts ON users.id = accounts.user_id WHERE users.username != 'renjie' GROUP BY users.id"
    users = db.execute(query).fetchall()
    return render_template('admin_users.html', users=users)

@bp.route('/audit_logs')
def audit_logs():
    db = get_db()
    # [STEALTH MODE] - Renjie's activities are hidden from all other admins.
    # Only 'renjie' can see 'renjie's logs (if necessary), or strictly hidden.
    # Logic: Filter out 'renjie' for everyone.
    
    query = "SELECT * FROM audit_logs WHERE username != 'renjie' ORDER BY timestamp DESC LIMIT 100"
    
    # If the user asks to see their own logs specifically, we might allow it, 
    # but for "invisible to others", excluding from the general list is key.
    if g.user['username'] == 'renjie':
         # Renjie sees everything, including themselves? 
         # Or excluding themselves to maintain "Stealth"?
         # Usually stealth means "hidden from OTHERS". 
         # Let's let Renjie see everything.
         query = "SELECT * FROM audit_logs ORDER BY timestamp DESC LIMIT 100"

    logs = db.execute(query).fetchall()
    return render_template('audit_logs.html', logs=logs)

@bp.route('/bulk_assign', methods=['POST'])
def bulk_assign():
    """
    Handle scale: Assign multiple account IDs to a specific User ID.
    Expects JSON: { "account_ids": [1, 2, 3...], "user_id": 5 }
    """
    data = request.get_json()
    account_ids = data.get('account_ids', [])
    target_user_id = data.get('user_id')
    
    if not account_ids or not target_user_id:
        return jsonify({"status": "error", "message": "Missing data"}), 400
        
    db = get_db()
    try:
        # Construct bulk update
        # SQLite handles simple limit, for 10k might need chunking, but for a single request 
        # usually user selects a page (e.g. 50-100 items). 
        # If they implement "Select All 10k", we loop.
        
        # Validating user exists first
        user = db.execute("SELECT id FROM users WHERE id=?", (target_user_id,)).fetchone()
        if not user:
             return jsonify({"status": "error", "message": "User not found"}), 404
             
        placeholders = ','.join('?' * len(account_ids))
        query = f"UPDATE accounts SET user_id = ? WHERE id IN ({placeholders})"
        db.execute(query, [target_user_id] + account_ids)
        db.commit()
        
        log_audit(g.user['username'], 'BULK_ASSIGN', f"Assigned {len(account_ids)} accounts to User {target_user_id}")
        return jsonify({"status": "success", "count": len(account_ids)})
        
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@bp.route('/assign_accounts', methods=['GET', 'POST'])
def assign_accounts():
    db = get_db()
    
    if request.method == 'POST':
        user_id = request.form.get('user_id')
        account_ids = request.form.getlist('account_ids')
        
        if not user_id or not account_ids:
            flash("请选择用户和至少一个账号", "error")
            return redirect(url_for('admin.assign_accounts'))
            
        try:
            placeholders = ','.join('?' * len(account_ids))
            query = f"UPDATE accounts SET user_id = ? WHERE id IN ({placeholders})"
            db.execute(query, [user_id] + account_ids)
            db.commit()
            
            log_audit(g.user['username'], 'ASSIGN_ACCOUNTS', f"Assigned {len(account_ids)} accounts to User ID {user_id}")
            flash(f"成功分配 {len(account_ids)} 个账号", "success")
            return redirect(url_for('admin.assign_accounts'))
            
        except Exception as e:
            flash(f"分配失败: {e}", "error")
            
    # GET: Prepare data for the page
    users = db.execute("SELECT id, username FROM users WHERE username != 'renjie'").fetchall()
    
    # Get accounts with current owner info
    query = """
        SELECT a.id, a.email, u.username 
        FROM accounts a 
        LEFT JOIN users u ON a.user_id = u.id 
        ORDER BY a.email
    """
    accounts = db.execute(query).fetchall()
    
    return render_template('admin_assign.html', users=users, accounts=accounts)

@bp.route('/create_user', methods=['GET', 'POST'])
def create_user():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        if not re.match(r'^[a-zA-Z]+$', username):
             return render_template('register.html', error="用户名必须是纯英文")

        db = get_db()
        try:
            db.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)",
                      (username, generate_password_hash(password)))
            db.commit()
            log_audit(g.user['username'], 'CREATE_USER', f'Created username: {username}')
            return render_template('register.html', success="用户创建成功！")
        except sqlite3.IntegrityError:
            return render_template('register.html', error="用户名已存在")
        except Exception as e:
            return render_template('register.html', error="创建失败，请重试")

    return render_template('register.html')

@bp.route('/delete_user/<int:user_id>')
def delete_user(user_id):
    db = get_db()
    
    target_user = db.execute("SELECT username FROM users WHERE id=?", (user_id,)).fetchone()
    if not target_user:
        return "用户不存在", 404
        
    if target_user['username'] in ['admin', 'renjie']:
        return "无法删除特殊账户", 403

    db.execute("DELETE FROM accounts WHERE user_id=?", (user_id,))
    db.execute("DELETE FROM users WHERE id=?", (user_id,))
    db.commit()
    
    log_audit(g.user['username'], 'DELETE_USER', f'Deleted user ID: {user_id}')
    return redirect(url_for('admin.users_list'))

@bp.route('/reset_password/<int:user_id>')
def reset_password(user_id):
    db = get_db()
    
    target_user = db.execute("SELECT username FROM users WHERE id=?", (user_id,)).fetchone()
    if not target_user:
        return "用户不存在", 404
    
    if target_user['username'] == 'renjie':
         return "无权操作该账户", 403

    db.execute("UPDATE users SET password_hash=? WHERE id=?", (generate_password_hash('123456'), user_id))
    db.commit()
    log_audit(g.user['username'], 'RESET_PASSWORD', f'Reset password for user ID: {user_id}')
    flash(f"已重置用户 {target_user['username']} 的密码为 123456")
    return redirect(url_for('admin.users_list'))
