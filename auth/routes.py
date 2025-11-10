"""
Authentication routes.
"""
from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app
from flask_login import login_user, logout_user, current_user, login_required
from auth.forms import LoginForm, CreateUserForm, ResetPasswordForm, BulkUploadForm
from utils.db import DatabaseManager
from werkzeug.security import check_password_hash, generate_password_hash
import psycopg
from psycopg import Error
from psycopg import rows
import csv
import io

auth_bp = Blueprint('auth', __name__, url_prefix='')


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """Login page."""
    if current_user.is_authenticated:
        return redirect(url_for('query.query_page'))
    
    form = LoginForm()
    
    if form.validate_on_submit():
        username = form.username.data
        password = form.password.data
        
        # Try to get user from database
        try:
            # Use BackOffice DB for user storage (or create a separate auth DB)
            connection = DatabaseManager.get_connection('BackOffice')
            cursor = connection.cursor(row_factory=rows.dict_row)
            
            # Check if users table exists
            cursor.execute("""
                SELECT table_name 
                FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = 'users'
            """)
            
            if not cursor.fetchone():
                # Create users table if it doesn't exist
                cursor.execute("""
                    CREATE TABLE users (
                        id SERIAL PRIMARY KEY,
                        username VARCHAR(100) UNIQUE NOT NULL,
                        password_hash VARCHAR(255) NOT NULL,
                        role VARCHAR(20) NOT NULL DEFAULT 'user',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                cursor.execute("CREATE INDEX idx_username ON users(username);")
                connection.commit()
                
                # Create default admin user if no users exist
                default_password_hash = generate_password_hash('password')
                cursor.execute("""
                    INSERT INTO users (username, password_hash, role)
                    VALUES ('admin', %s, 'admin')
                    ON CONFLICT (username) DO NOTHING
                """, (default_password_hash,))
                connection.commit()
            
            # Ensure role column exists (migration safety)
            try:
                cursor.execute("""
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name = 'users' AND column_name = 'role'
                """)
                if not cursor.fetchone():
                    cursor.execute("ALTER TABLE users ADD COLUMN role VARCHAR(20) NOT NULL DEFAULT 'user'")
                    connection.commit()
            except Exception:
                pass

            # Get user from database
            cursor.execute("SELECT id, username, password_hash, role FROM users WHERE username = %s", (username,))
            user_data = cursor.fetchone()
            cursor.close()
            connection.close()
            
            if user_data and check_password_hash(user_data['password_hash'], password):
                # Create user object for Flask-Login
                from app import User
                user = User(
                    id=str(user_data['id']),
                    username=user_data['username'],
                    password_hash=user_data['password_hash'],
                    role=user_data.get('role', 'user')
                )
                
                login_user(user, remember=form.remember_me.data)
                flash('Login successful!', 'success')
                next_page = request.args.get('next')
                return redirect(next_page or url_for('query.query_page'))
            else:
                flash('Invalid username or password.', 'danger')
                
        except ValueError as e:
            # Configuration or connection error - show the error message
            flash(f'Database connection error: {str(e)}', 'danger')
            # Don't fallback to in-memory user for configuration errors
            # User needs to fix their .env file
        except Error as e:
            # Database error - fallback to in-memory user if DB fails
            current_app.logger.warning(f"Database error during login, falling back to in-memory user: {str(e)}")
            from app import users
            user = users.get(username)
            if user and user.check_password(password):
                login_user(user, remember=form.remember_me.data)
                flash('Login successful! (using fallback authentication)', 'info')
                next_page = request.args.get('next')
                return redirect(next_page or url_for('query.query_page'))
            else:
                flash('Invalid username or password.', 'danger')
        except Exception as e:
            # Unexpected error
            current_app.logger.error(f"Unexpected login error: {str(e)}")
            flash(f'Login error: {str(e)}', 'danger')
    
    return render_template('login.html', form=form)


# Admin: User management
admin_bp = Blueprint('admin', __name__, url_prefix='/admin')


def _require_admin():
    if not current_user.is_authenticated or getattr(current_user, 'role', 'user') != 'admin':
        return False
    return True


@admin_bp.route('/users', methods=['GET', 'POST'])
@login_required
def users_page():
    if not _require_admin():
        flash('Access denied. Admins only.', 'danger')
        return redirect(url_for('query.query_page'))
    
    create_form = CreateUserForm()
    reset_form = ResetPasswordForm()
    bulk_upload_form = BulkUploadForm()
    users_list = []

    # Load users
    try:
        connection = DatabaseManager.get_connection('BackOffice')
        cursor = connection.cursor(row_factory=rows.dict_row)
        cursor.execute("SELECT id, username, role, created_at FROM users ORDER BY created_at DESC")
        users_list = cursor.fetchall()
        cursor.close()
        connection.close()
    except Exception as e:
        flash(f'Error loading users: {str(e)}', 'danger')

    # Handle create user
    if create_form.validate_on_submit() and request.form.get('action') == 'create':
        try:
            connection = DatabaseManager.get_connection('BackOffice')
            cursor = connection.cursor()
            
            # Fix sequence if it's out of sync (e.g., after direct inserts)
            # This ensures the sequence is set to the correct value (max_id + 1)
            try:
                # Get the current max ID
                cursor.execute("SELECT COALESCE(MAX(id), 0) FROM users;")
                max_id = cursor.fetchone()[0]
                next_id = max_id + 1
                
                # Reset sequence to next_id (so nextval() will return next_id)
                # Method 1: Use pg_get_serial_sequence to find sequence name dynamically
                cursor.execute("""
                    SELECT setval(
                        pg_get_serial_sequence('users', 'id'), 
                        %s, 
                        false
                    );
                """, (next_id,))
                connection.commit()
                current_app.logger.info(f"Sequence reset to {next_id}")
            except Exception as seq_error:
                # If sequence fix fails, try alternative method with direct sequence name
                try:
                    cursor.execute("SELECT COALESCE(MAX(id), 0) FROM users;")
                    max_id = cursor.fetchone()[0]
                    next_id = max_id + 1
                    cursor.execute("SELECT setval('users_id_seq', %s, false);", (next_id,))
                    connection.commit()
                    current_app.logger.info(f"Sequence reset to {next_id} (using direct method)")
                except Exception as e2:
                    # If both methods fail, log error but try to continue
                    current_app.logger.error(f"Could not fix sequence: {str(seq_error)}, {str(e2)}")
                    # Try one more time with a simple query
                    try:
                        cursor.execute("SELECT setval('users_id_seq', (SELECT COALESCE(MAX(id), 0) + 1 FROM users), false);")
                        connection.commit()
                    except Exception:
                        pass
            
            pwd_hash = generate_password_hash(create_form.password.data)
            cursor.execute(
                "INSERT INTO users (username, password_hash, role) VALUES (%s, %s, %s)",
                (create_form.username.data, pwd_hash, create_form.role.data)
            )
            connection.commit()
            cursor.close()
            connection.close()
            flash('User created successfully.', 'success')
            return redirect(url_for('admin.users_page'))
        except Exception as e:
            flash(f'Error creating user: {str(e)}', 'danger')

    # Handle reset password
    if reset_form.validate_on_submit() and request.form.get('action') == 'reset':
        try:
            connection = DatabaseManager.get_connection('BackOffice')
            cursor = connection.cursor()
            pwd_hash = generate_password_hash(reset_form.new_password.data)
            cursor.execute(
                "UPDATE users SET password_hash = %s WHERE username = %s",
                (pwd_hash, reset_form.username.data)
            )
            connection.commit()
            cursor.close()
            connection.close()
            flash('Password reset successfully.', 'success')
            return redirect(url_for('admin.users_page'))
        except Exception as e:
            flash(f'Error resetting password: {str(e)}', 'danger')

    # Handle bulk upload
    if bulk_upload_form.validate_on_submit() and request.form.get('action') == 'bulk_upload':
        try:
            csv_file = bulk_upload_form.csv_file.data
            if not csv_file:
                flash('No file uploaded.', 'danger')
                return redirect(url_for('admin.users_page'))
            
            # Read CSV file
            stream = io.TextIOWrapper(csv_file.stream, encoding='utf-8')
            csv_reader = csv.DictReader(stream)
            
            # Expected columns: username, password, role
            users_to_create = []
            errors = []
            
            for row_num, row in enumerate(csv_reader, start=2):  # Start at 2 (row 1 is header)
                username = row.get('username', '').strip()
                password = row.get('password', '').strip()
                role = row.get('role', 'user').strip().lower()
                
                # Validate row
                if not username:
                    errors.append(f'Row {row_num}: Username is required')
                    continue
                
                if len(username) < 3 or len(username) > 50:
                    errors.append(f'Row {row_num}: Username must be between 3 and 50 characters')
                    continue
                
                if not password:
                    errors.append(f'Row {row_num}: Password is required')
                    continue
                
                if len(password) < 6:
                    errors.append(f'Row {row_num}: Password must be at least 6 characters')
                    continue
                
                if role not in ('user', 'admin'):
                    role = 'user'  # Default to user if invalid role
                
                users_to_create.append({
                    'username': username,
                    'password': password,
                    'role': role
                })
            
            if errors:
                for error in errors:
                    flash(error, 'warning')
            
            if not users_to_create:
                flash('No valid users to create from CSV file.', 'warning')
                return redirect(url_for('admin.users_page'))
            
            # Bulk insert users
            connection = DatabaseManager.get_connection('BackOffice')
            cursor = connection.cursor()
            
            # Fix sequence if it's out of sync (e.g., after direct inserts)
            # This ensures the sequence is set to the correct value (max_id + 1)
            try:
                # Get the current max ID
                cursor.execute("SELECT COALESCE(MAX(id), 0) FROM users;")
                max_id = cursor.fetchone()[0]
                next_id = max_id + 1
                
                # Reset sequence to next_id (so nextval() will return next_id)
                # Method 1: Use pg_get_serial_sequence to find sequence name dynamically
                cursor.execute("""
                    SELECT setval(
                        pg_get_serial_sequence('users', 'id'), 
                        %s, 
                        false
                    );
                """, (next_id,))
                connection.commit()
                current_app.logger.info(f"Sequence reset to {next_id}")
            except Exception as seq_error:
                # If sequence fix fails, try alternative method with direct sequence name
                try:
                    cursor.execute("SELECT COALESCE(MAX(id), 0) FROM users;")
                    max_id = cursor.fetchone()[0]
                    next_id = max_id + 1
                    cursor.execute("SELECT setval('users_id_seq', %s, false);", (next_id,))
                    connection.commit()
                    current_app.logger.info(f"Sequence reset to {next_id} (using direct method)")
                except Exception as e2:
                    # If both methods fail, log error but try to continue
                    current_app.logger.error(f"Could not fix sequence: {str(seq_error)}, {str(e2)}")
                    # Try one more time with a simple query
                    try:
                        cursor.execute("SELECT setval('users_id_seq', (SELECT COALESCE(MAX(id), 0) + 1 FROM users), false);")
                        connection.commit()
                    except Exception:
                        pass
            
            success_count = 0
            error_count = 0
            duplicate_count = 0
            
            for user_data in users_to_create:
                try:
                    pwd_hash = generate_password_hash(user_data['password'])
                    cursor.execute(
                        "INSERT INTO users (username, password_hash, role) VALUES (%s, %s, %s)",
                        (user_data['username'], pwd_hash, user_data['role'])
                    )
                    success_count += 1
                except Error as e:
                    # PostgreSQL error code for unique violation is 23505
                    if 'unique' in str(e).lower() or 'duplicate' in str(e).lower() or (hasattr(e, 'pgcode') and e.pgcode == '23505'):
                        duplicate_count += 1
                    else:
                        error_count += 1
                        flash(f'Error creating user {user_data["username"]}: {str(e)}', 'warning')
            
            connection.commit()
            cursor.close()
            connection.close()
            
            # Show summary
            if success_count > 0:
                flash(f'Successfully created {success_count} user(s).', 'success')
            if duplicate_count > 0:
                flash(f'{duplicate_count} user(s) already exist and were skipped.', 'info')
            if error_count > 0:
                flash(f'{error_count} user(s) failed to create.', 'warning')
            
            return redirect(url_for('admin.users_page'))
            
        except Exception as e:
            flash(f'Error processing bulk upload: {str(e)}', 'danger')
            return redirect(url_for('admin.users_page'))

    return render_template('admin/users.html', users=users_list, create_form=create_form, reset_form=reset_form, bulk_upload_form=bulk_upload_form)

