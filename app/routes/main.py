from flask import (
    Blueprint, render_template, request, jsonify, redirect, url_for, session, current_app, flash, g, send_file
)
import pandas as pd
import io
from app.auth import login_required
from app.db import get_db
from app.services.email_service import fetch_latest_mail
from app.audit import log_audit
from werkzeug.security import generate_password_hash 

bp = Blueprint('main', __name__)

@bp.route('/')
@login_required
def index():
    db = get_db()
    
    # Check Isolation Mode
    isolation_setting = db.execute("SELECT value FROM system_settings WHERE key='isolation_mode'").fetchone()
    is_isolated = isolation_setting and isolation_setting['value'] == '1'
    
    # Get Polling Settings
    polling_enabled_row = db.execute("SELECT value FROM system_settings WHERE key='polling_enabled'").fetchone()
    polling_interval_row = db.execute("SELECT value FROM system_settings WHERE key='polling_interval'").fetchone()
    polling_config = {
        'enabled': polling_enabled_row and polling_enabled_row['value'] == '1',
        'interval': polling_interval_row['value'] if polling_interval_row else '300'
    }

    query = "SELECT * FROM accounts"
    params = []
    
    # Data Isolation Logic
    if is_isolated:
        if g.user['username'] not in ['admin', 'renjie']:
            query += " WHERE user_id = ?"
            params.append(g.user['id'])
    
    # Search logic
    search_query = request.args.get('search', '')
    if search_query:
        if 'WHERE' in query:
            query += " AND email LIKE ?"
        else:
            query += " WHERE email LIKE ?"
        params.append(f'%{search_query}%')

    # Sorting: New Mail first, then ID desc
    query += " ORDER BY has_new_mail DESC, id DESC"
        
    accounts = db.execute(query, params).fetchall()
    
    # Return JSON for AJAX requests (Auto-refresh)
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.args.get('format') == 'json':
         return jsonify([dict(row) for row in accounts])

    return render_template('index.html', accounts=accounts, search_query=search_query, polling_config=polling_config)

@bp.route('/polling/config', methods=['POST'])
@login_required
def polling_config():
    if g.user['username'] != 'renjie':
         return jsonify({"status": "error", "message": "Access denied"}), 403
    
    enabled = request.form.get('enabled') == 'true'
    interval = request.form.get('interval')
    
    try:
        interval_val = int(interval)
        if interval_val < 10: # Minimum interval safety
             return jsonify({"status": "error", "message": "Interval too small (min 10s)"}), 400
    except:
        return jsonify({"status": "error", "message": "Invalid interval"}), 400

    db = get_db()
    db.execute("INSERT OR REPLACE INTO system_settings (key, value) VALUES ('polling_enabled', ?)", ('1' if enabled else '0',))
    db.execute("INSERT OR REPLACE INTO system_settings (key, value) VALUES ('polling_interval', ?)", (str(interval_val),))
    db.commit()
    
    log_audit(g.user['username'], 'UPDATE_POLLING', f"Enabled: {enabled}, Interval: {interval_val}")
    return jsonify({"status": "ok"})

@bp.route('/add', methods=['POST'])
@login_required
def add_account():
    email_addr = request.form['email']
    auth_code = request.form['auth_code']
    
    db = get_db()
    
    # Ownership Logic
    own_setting = db.execute("SELECT value FROM system_settings WHERE key='default_ownership_self'").fetchone()
    default_ownership_self = own_setting['value'] == '1' if own_setting else True
    
    if default_ownership_self:
        user_id = g.user['id']
    else:
        admin_user = db.execute("SELECT id FROM users WHERE username='admin'").fetchone()
        user_id = admin_user['id'] if admin_user else g.user['id'] # Fallback to current if admin not found
    
    try:
        db.execute("INSERT INTO accounts (email, auth_code, user_id) VALUES (?, ?, ?)", 
                   (email_addr, auth_code, user_id))
        db.commit()
        log_audit(g.user['username'], 'ADD_ACCOUNT', f"Added {email_addr}")
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@bp.route('/delete/<int:acc_id>', methods=['POST'])
@login_required
def delete_account(acc_id):
    db = get_db()
    
    # Check permissions if isolated
    isolation_setting = db.execute("SELECT value FROM system_settings WHERE key='isolation_mode'").fetchone()
    is_isolated = isolation_setting and isolation_setting['value'] == '1'
    
    if is_isolated and g.user['username'] not in ['admin', 'renjie']:
        acc = db.execute("SELECT user_id FROM accounts WHERE id = ?", (acc_id,)).fetchone()
        if not acc or acc['user_id'] != g.user['id']:
             return jsonify({"status": "error", "message": "Permission denied"}), 403

    db.execute("DELETE FROM accounts WHERE id = ?", (acc_id,))
    db.commit()
    log_audit(g.user['username'], 'DELETE_ACCOUNT', f"Deleted account ID {acc_id}")
    return jsonify({"status": "ok"})

@bp.route('/check/<int:acc_id>')
@login_required
def view_mail(acc_id):
    db = get_db()
    account = db.execute("SELECT email, auth_code FROM accounts WHERE id = ?", (acc_id,)).fetchone()
    
    if account:
        result = fetch_latest_mail(account['email'], account['auth_code'])
        
        new_status = 'success' if result['status'] == 'success' else 'error'
        
        # When user checks mail, clear "new mail" flag and update identifier
        if new_status == 'success':
             subject = result.get('subject', '')
             sender = result.get('sender', '')
             current_identifier = f"{subject}|{sender}"
             
             db.execute("UPDATE accounts SET status = ?, has_new_mail = 0, last_mail_identifier = ? WHERE id = ?", 
                        (new_status, current_identifier, acc_id))
        else:
             db.execute("UPDATE accounts SET status = ? WHERE id = ?", (new_status, acc_id))

        db.commit()
        
        return jsonify(result)
    return jsonify({"status": "error", "message": "Account not found"})

@bp.route('/download_template')
@login_required
def download_template():
    data = {
        'QQ邮箱': ['123456@qq.com', 'test@qq.com'],
        '授权码': ['abcd1234efgh5678', 'your_auth_code_here']
    }
    df = pd.DataFrame(data)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='账号列表')
    output.seek(0)
    return send_file(output, download_name='account_template.xlsx', as_attachment=True)

@bp.route('/upload_excel', methods=['POST'])
@login_required
def upload_excel():
    db = get_db()
    
    # Ownership Logic
    own_setting = db.execute("SELECT value FROM system_settings WHERE key='default_ownership_self'").fetchone()
    default_ownership_self = own_setting['value'] == '1' if own_setting else True
    
    if default_ownership_self:
        user_id = g.user['id']
    else:
        admin_user = db.execute("SELECT id FROM users WHERE username='admin'").fetchone()
        user_id = admin_user['id'] if admin_user else g.user['id']

    if 'file' not in request.files:
        return jsonify({"status": "error", "message": "No file part"})
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({"status": "error", "message": "No selected file"})
        
    try:
        df = pd.read_excel(file)
        required_columns = ['QQ邮箱', '授权码']
        if not all(col in df.columns for col in required_columns):
            return jsonify({"status": "error", "message": "Columns must include: QQ邮箱, 授权码"})
            
        success_count = 0
        for _, row in df.iterrows():
            email_addr = str(row['QQ邮箱']).strip()
            auth_code = str(row['授权码']).strip()
            
            if email_addr and auth_code and email_addr != 'nan':
                 try:
                    db.execute("INSERT INTO accounts (email, auth_code, user_id) VALUES (?, ?, ?)", 
                            (email_addr, auth_code, user_id))
                    success_count += 1
                 except Exception:
                    pass 
        
        db.commit()
        log_audit(g.user['username'], 'UPLOAD_EXCEL', f"Imported {success_count} accounts")
        return jsonify({"status": "success", "count": success_count})
        
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    user_id = g.user['id']
    if request.method == 'POST':
        new_username = request.form['username']
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')

        db = get_db()
        try:
             if new_username and new_username != g.user['username']:
                  check = db.execute("SELECT id FROM users WHERE username=? AND id!=?", (new_username, user_id)).fetchone()
                  if check:
                      return render_template('profile.html', user=g.user, error="用户名已存在")
                  db.execute("UPDATE users SET username=? WHERE id=?", (new_username, user_id))
                  session['username'] = new_username

             if new_password:
                 if new_password != confirm_password:
                     return render_template('profile.html', user=g.user, error="两次密码输入不一致")
                 db.execute("UPDATE users SET password_hash=? WHERE id=?", (generate_password_hash(new_password), user_id))
            
             db.commit()
             g.user = db.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
             return render_template('profile.html', user=g.user, success="个人信息更新成功")

        except Exception as e:
            return render_template('profile.html', user=g.user, error="更新失败")

    return render_template('profile.html', user=g.user)
