"""
Shubham Kotkar 2.0 - Secure SQL Query Executor
A Flask web application for authenticated users to execute SQL queries safely with transaction management.
"""
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_wtf.csrf import CSRFProtect
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
import os
from datetime import timedelta
from functools import wraps

# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__)

# Configuration
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(
    minutes=int(os.getenv('SESSION_TIMEOUT_MINUTES', 30))
)

# Database Configuration
app.config['BACKOFFICE_DB_HOST'] = os.getenv('BACKOFFICE_DB_HOST', 'localhost')
app.config['BACKOFFICE_DB_PORT'] = int(os.getenv('BACKOFFICE_DB_PORT', 3306))
app.config['BACKOFFICE_DB_USER'] = os.getenv('BACKOFFICE_DB_USER', '')
app.config['BACKOFFICE_DB_PASSWORD'] = os.getenv('BACKOFFICE_DB_PASSWORD', '')
app.config['BACKOFFICE_DB_NAME'] = os.getenv('BACKOFFICE_DB_NAME', '')

app.config['PORTAL_DB_HOST'] = os.getenv('PORTAL_DB_HOST', 'localhost')
app.config['PORTAL_DB_PORT'] = int(os.getenv('PORTAL_DB_PORT', 3306))
app.config['PORTAL_DB_USER'] = os.getenv('PORTAL_DB_USER', '')
app.config['PORTAL_DB_PASSWORD'] = os.getenv('PORTAL_DB_PASSWORD', '')
app.config['PORTAL_DB_NAME'] = os.getenv('PORTAL_DB_NAME', '')

# Initialize extensions
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'auth.login'
login_manager.login_message = 'Please log in to access this page.'
login_manager.login_message_category = 'info'

csrf = CSRFProtect(app)
# Ensure AJAX endpoints get JSON on unauthorized instead of HTML redirect
@login_manager.unauthorized_handler
def unauthorized():
    return jsonify({'success': False, 'message': 'Unauthorized'}), 401


# Security headers
@app.after_request
def set_security_headers(response):
    """Set security headers for all responses."""
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Content-Security-Policy'] = "default-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com;"
    response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    # Prevent caching to avoid stale results being shown
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response


# User class for Flask-Login
class User(UserMixin):
    """User class for authentication."""
    
    def __init__(self, id, username, password_hash, role='user'):
        self.id = id
        self.username = username
        self.password_hash = password_hash
        self.role = role
    
    def check_password(self, password):
        """Check if provided password matches the hash."""
        return check_password_hash(self.password_hash, password)


# In-memory user store (fallback if DB fails)
users = {
    'admin': User(
        id='1',
        username='admin',
        password_hash=generate_password_hash('password'),
        role='admin'
    )
}


@login_manager.user_loader
def load_user(user_id):
    """Load user by ID."""
    # Try database lookup first
    try:
        from utils.db import DatabaseManager
        from psycopg import Error
        from psycopg import rows
        connection = DatabaseManager.get_connection('BackOffice')
        cursor = connection.cursor(row_factory=rows.dict_row)
        cursor.execute("SELECT id, username, password_hash, role FROM users WHERE id = %s", (user_id,))
        row = cursor.fetchone()
        cursor.close()
        connection.close()
        if row:
            return User(id=str(row['id']), username=row['username'], password_hash=row['password_hash'], role=row.get('role', 'user'))
    except ValueError as e:
        # Configuration error - log but don't fail silently
        app.logger.error(f"Database configuration error in load_user: {str(e)}")
        # Fall through to in-memory user fallback
    except Error as e:
        # Database error - log but fallback to in-memory user
        app.logger.warning(f"Database error in load_user: {str(e)}")
    except Exception as e:
        # Other errors - log and fallback
        app.logger.error(f"Unexpected error in load_user: {str(e)}")
    
    # Fallback to in-memory user store
    for _, user in users.items():
        if user.id == user_id:
            return user
    return None


# Session timeout decorator
def check_session_timeout(f):
    """Decorator to check session timeout."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if current_user.is_authenticated:
            session.permanent = True
        return f(*args, **kwargs)
    return decorated_function


# Routes
@app.route('/')
def index():
    """Redirect to login if not authenticated, otherwise to query page."""
    if current_user.is_authenticated:
        return redirect(url_for('query.query_page'))
    return redirect(url_for('auth.login'))


@app.route('/logout')
@login_required
def logout():
    """Logout user."""
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('auth.login'))


# Error handlers
@app.errorhandler(403)
def forbidden(error):
    """403 Forbidden error handler."""
    return render_template('error.html', error_code=403, error_message='Access Forbidden'), 403


@app.errorhandler(404)
def not_found(error):
    """404 Not Found error handler."""
    return render_template('error.html', error_code=404, error_message='Page Not Found'), 404


@app.errorhandler(500)
def internal_error(error):
    """500 Internal Server Error handler."""
    return render_template('error.html', error_code=500, error_message='Internal Server Error'), 500


# Register blueprints
from auth.routes import auth_bp, admin_bp
from query.routes import query_bp

app.register_blueprint(auth_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(query_bp)


if __name__ == '__main__':
    # Initialize audit table
    from utils.audit_logger import AuditLogger
    with app.app_context():
        AuditLogger.ensure_audit_table_exists()
    
    app.run(debug=True, host='0.0.0.0', port=5000)
