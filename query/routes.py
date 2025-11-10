"""
Query execution routes.
"""
from flask import Blueprint, render_template, request, jsonify, flash, session, redirect, url_for
from flask_login import login_required, current_user
from query.forms import QueryForm
from utils.db import DatabaseManager
from utils.validators import SQLValidator
from utils.audit_logger import AuditLogger

query_bp = Blueprint('query', __name__, url_prefix='')


@query_bp.route('/query', methods=['GET', 'POST'])
@login_required
def query_page():
    """Query executor page."""
    form = QueryForm()
    
    if form.validate_on_submit():
        # Clear any previous result to avoid showing stale data
        session.pop('last_query', None)
        session.pop('pending_transactions', None)
        session.modified = True
        # Read directly from form payload to avoid stale WTForms data
        sql_query = (request.form.get('sql_query') or '').strip()
        defect_number = form.defect_number.data.strip()
        database = form.database.data
        
        # Block protected tables for non-admin users
        if SQLValidator.references_protected_tables(sql_query) and getattr(current_user, 'role', 'user') != 'admin':
            flash('Access to protected tables is restricted.', 'danger')
            return render_template('query.html', form=form)

        # Validate inputs
        if not sql_query:
            flash('SQL query is required.', 'danger')
            return render_template('query.html', form=form)
        
        if not defect_number:
            flash('Defect number is required.', 'danger')
            return render_template('query.html', form=form)
        
        # Execute query with transaction management
        success, data, error, audit_id = DatabaseManager.execute_query_with_transaction(
            sql_query, database, current_user.username, defect_number
        )
        
        if not success:
            flash(f'Query execution failed: {error}', 'danger')
            return render_template('query.html', form=form)
        
        # Store results in session
        session['last_query'] = {
            'query': sql_query,
            'database': database,
            'defect_number': defect_number,
            'audit_id': audit_id,
            'data': data,
            'query_type': data.get('query_type', 'SELECT')
        }
        session.modified = True
        
        # Handle per-statement results and errors
        if data.get('messages'):
            # Show messages about committed/failed statements
            for msg in data.get('messages', []):
                if 'Successfully committed' in msg:
                    flash(msg, 'success')
                elif 'Failed to execute' in msg:
                    flash(msg, 'danger')
                elif 'exceeded threshold' in msg:
                    flash(msg, 'warning')
        
        # Check if any statements exceeded threshold (need confirmation)
        if data.get('threshold_exceeded_count', 0) > 0:
            # Redirect to confirmation page for threshold-exceeded statements
            return redirect(url_for('query.confirm_dml', audit_id=audit_id))
        
        # Show error message if there were failures (but some succeeded)
        if error:
            flash(error, 'warning')
        
        # Redirect to results page
        return redirect(url_for('query.result_page'))
    
    return render_template('query.html', form=form)


@query_bp.route('/result')
@login_required
def result_page():
    """Display query results."""
    query_data = session.get('last_query')
    
    if not query_data:
        flash('No query results found.', 'warning')
        return redirect(url_for('query.query_page'))
    
    return render_template(
        'result.html',
        query_data=query_data
    )


@query_bp.route('/confirm-dml/<int:audit_id>')
@login_required
def confirm_dml(audit_id):
    """Confirmation page for large DML operations."""
    query_data = session.get('last_query')
    threshold_exceeded_statements = session.get('threshold_exceeded_statements', [])
    committed_statements = session.get('committed_statements', [])
    failed_statements = session.get('failed_statements', [])
    
    if not query_data or query_data.get('audit_id') != audit_id:
        flash('Invalid request.', 'danger')
        return redirect(url_for('query.query_page'))
    
    rows_affected = query_data.get('data', {}).get('rows_affected', 0)
    
    return render_template(
        'confirm_dml.html',
        query_data=query_data,
        rows_affected=rows_affected,
        threshold=SQLValidator.ROW_CONFIRMATION_THRESHOLD,
        threshold_exceeded_statements=threshold_exceeded_statements,
        committed_statements=committed_statements,
        failed_statements=failed_statements
    )


@query_bp.route('/reject', methods=['POST'])
@login_required
def reject_changes():
    """Reject pending DML changes."""
    from flask_wtf.csrf import validate_csrf
    from wtforms import ValidationError
    
    try:
        validate_csrf(request.form.get('csrf_token', ''))
    except ValidationError:
        flash('CSRF token validation failed.', 'danger')
        return redirect(url_for('query.query_page'))
    
    query_data = session.get('last_query')
    
    if not query_data:
        flash('No pending changes to reject.', 'warning')
        return redirect(url_for('query.query_page'))
    
    audit_id = query_data.get('audit_id')
    database = query_data.get('database')
    
    # Update audit log status to "Rejected by user"
    if audit_id:
        rows_affected = query_data.get('data', {}).get('rows_affected', 0)
        AuditLogger.update_log_status(audit_id, 'Rejected by user', rows_affected, database_name=database)
    
    # Rollback transaction (if any)
    DatabaseManager.rollback_transaction(database, audit_id, current_user.username)
    
    # Clear last query from session
    session.pop('last_query', None)
    session.modified = True
    
    flash('DML operation rejected. Changes have been rolled back.', 'info')
    return redirect(url_for('query.query_page'))


@query_bp.route('/commit', methods=['POST'])
@login_required
def commit_changes():
    """Commit pending changes (threshold-exceeded statements)."""
    from flask_wtf.csrf import validate_csrf
    from wtforms import ValidationError
    from flask import current_app
    from psycopg2 import Error as PostgreSQLError
    
    try:
        validate_csrf(request.form.get('csrf_token', ''))
    except ValidationError:
        flash('CSRF token validation failed.', 'danger')
        return redirect(url_for('query.query_page'))
    
    query_data = session.get('last_query')
    threshold_exceeded_statements = session.get('threshold_exceeded_statements', [])
    
    if not query_data or not threshold_exceeded_statements:
        flash('No pending changes to commit.', 'warning')
        return redirect(url_for('query.query_page'))
    
    database = query_data.get('database')
    audit_id = query_data.get('audit_id')
    config_key = 'PORTAL' if database == 'Portal' else 'BACKOFFICE'
    original_database_name = current_app.config.get(f'{config_key}_DB_NAME', '')
    
    # Get database connection details
    host = current_app.config.get(f'{config_key}_DB_HOST', '')
    port = current_app.config.get(f'{config_key}_DB_PORT', 5432)
    db_user = current_app.config.get(f'{config_key}_DB_USER', '')
    password = current_app.config.get(f'{config_key}_DB_PASSWORD', '')
    
    # Execute and commit each threshold-exceeded statement individually
    # Create separate audit logs for each committed statement
    committed_count = 0
    failed_count = 0
    total_rows = 0
    errors = []
    committed_audit_ids = []
    
    defect_number = query_data.get('defect_number', '')
    user = current_user.username
    
    for stmt_info in threshold_exceeded_statements:
        stmt = stmt_info['statement']
        stmt_idx = stmt_info['index']
        
        try:
            # Create connection for this statement
            import psycopg2
            dml_conn = psycopg2.connect(
                host=host,
                port=int(port),
                user=db_user,
                password=password,
                database=original_database_name
            )
            dml_conn.autocommit = False
            dml_cursor = dml_conn.cursor()
            dml_cursor.execute(stmt)
            rows_affected = dml_cursor.rowcount
            dml_conn.commit()
            dml_cursor.close()
            dml_conn.close()
            
            # Create separate audit log for this committed statement
            committed_audit_id = AuditLogger.log_query(
                user, stmt, database, defect_number,
                status='Success', rows_affected=rows_affected
            )
            if committed_audit_id:
                committed_audit_ids.append(committed_audit_id)
            
            committed_count += 1
            total_rows += rows_affected
            
        except PostgreSQLError as e:
            error_msg = str(e)
            current_app.logger.error(f"Failed to commit statement {stmt_idx}: {error_msg}")
            
            # Create separate audit log for this failed statement
            failed_audit_id = AuditLogger.log_query(
                user, stmt, database, defect_number,
                status='Error', rows_affected=0
            )
            if failed_audit_id:
                AuditLogger.update_log_status(failed_audit_id, 'Error', 0, error_msg, database)
            
            failed_count += 1
            errors.append(f"Query {stmt_idx}: {error_msg}")
        except Exception as e:
            error_msg = str(e)
            current_app.logger.error(f"Unexpected error committing statement {stmt_idx}: {error_msg}")
            
            # Create separate audit log for this failed statement
            failed_audit_id = AuditLogger.log_query(
                user, stmt, database, defect_number,
                status='Error', rows_affected=0
            )
            if failed_audit_id:
                AuditLogger.update_log_status(failed_audit_id, 'Error', 0, error_msg, database)
            
            failed_count += 1
            errors.append(f"Query {stmt_idx}: {error_msg}")
    
    # Note: The pending audit log (audit_id) remains with "Pending" status
    # as it represents the original combined pending query.
    # Separate audit logs have been created for each committed/failed statement.
    
    # Clear session data
    session.pop('last_query', None)
    session.pop('threshold_exceeded_statements', None)
    session.pop('committed_statements', None)
    session.pop('failed_statements', None)
    session.modified = True
    
    if committed_count > 0:
        flash(f'Successfully committed {committed_count} statement(s) affecting {total_rows} row(s).', 'success')
    if failed_count > 0:
        flash(f'Failed to commit {failed_count} statement(s): {"; ".join(errors)}', 'danger')
    
    return redirect(url_for('query.query_page'))


@query_bp.route('/rollback', methods=['POST'])
@login_required
def rollback_changes():
    """Rollback pending changes."""
    from flask_wtf.csrf import validate_csrf
    from wtforms import ValidationError
    
    try:
        validate_csrf(request.form.get('csrf_token', request.json.get('csrf_token', '')))
    except ValidationError:
        return jsonify({'success': False, 'message': 'CSRF token validation failed.'}), 403
    
    query_data = session.get('last_query')
    
    if not query_data:
        return jsonify({'success': False, 'message': 'No pending changes to rollback.'}), 400
    
    database = query_data.get('database')
    audit_id = query_data.get('audit_id')
    
    # Rollback transaction
    success, error = DatabaseManager.rollback_transaction(
        database, audit_id, current_user.username
    )
    
    if success:
        # Clear last query from session
        session.pop('last_query', None)
        session.modified = True
        
        flash('Changes rolled back successfully!', 'info')
        return jsonify({'success': True, 'message': 'Changes rolled back successfully.'})
    else:
        return jsonify({'success': False, 'message': f'Rollback failed: {error}'}), 500

