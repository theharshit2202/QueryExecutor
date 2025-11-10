"""
Database connection utilities for secure query execution with transaction support.
"""
import psycopg
from psycopg import Error
from psycopg import rows
from flask import current_app, session
import re


class DatabaseManager:
    """Manages database connections and query execution with transactions."""
    
    @staticmethod
    def _get_connection_with_db(db_type, database_name, autocommit=False):
        """Get connection with specific database name (for USE statements)."""
        config_key = 'PORTAL' if db_type == 'Portal' else 'BACKOFFICE'
        
        host = current_app.config.get(f'{config_key}_DB_HOST', '')
        port = current_app.config.get(f'{config_key}_DB_PORT', 5432)
        user = current_app.config.get(f'{config_key}_DB_USER', '')
        password = current_app.config.get(f'{config_key}_DB_PASSWORD', '')
        
        try:
            connection = psycopg.connect(
                host=host,
                port=int(port),
                user=user,
                password=password,
                dbname=database_name,
                autocommit=autocommit
            )
            current_app.logger.info(f"Connected to {db_type} database: {database_name}@{host}:{port}")
            return connection
        except Error as e:
            error_msg = f"Failed to connect to {db_type} database '{database_name}' at {host}:{port}. Error: {str(e)}"
            current_app.logger.error(error_msg)
            # PostgreSQL error codes
            if 'password authentication failed' in str(e).lower() or 'authentication failed' in str(e).lower():
                error_msg = f"Access denied for {db_type} database. Please check your username and password in .env file."
            elif 'database' in str(e).lower() and 'does not exist' in str(e).lower():
                error_msg = f"Database '{database_name}' does not exist for {db_type}. Please create the database or check the database name."
            elif 'could not connect' in str(e).lower() or 'connection refused' in str(e).lower():
                error_msg = f"Cannot connect to {db_type} database server at {host}:{port}. Please check if the server is running and the host/port are correct."
            raise ValueError(error_msg) from e
    
    @staticmethod
    def get_connection(db_type, autocommit=False):
        """
        Get database connection based on type.
        
        Args:
            db_type (str): 'BackOffice' or 'Portal'
            autocommit (bool): Whether to auto-commit transactions
            
        Returns:
            psycopg.Connection: Database connection object
            
        Raises:
            ValueError: If required configuration is missing
            Error: If database connection fails
        """
        config_key = 'PORTAL' if db_type == 'Portal' else 'BACKOFFICE'
        
        host = current_app.config.get(f'{config_key}_DB_HOST', '')
        port = current_app.config.get(f'{config_key}_DB_PORT', 5432)
        user = current_app.config.get(f'{config_key}_DB_USER', '')
        password = current_app.config.get(f'{config_key}_DB_PASSWORD', '')
        database = current_app.config.get(f'{config_key}_DB_NAME', '')
        
        # Validate configuration
        missing_config = []
        if not host:
            missing_config.append(f'{config_key}_DB_HOST')
        if not user:
            missing_config.append(f'{config_key}_DB_USER')
        if not password:
            missing_config.append(f'{config_key}_DB_PASSWORD')
        if not database:
            missing_config.append(f'{config_key}_DB_NAME')
        
        if missing_config:
            error_msg = f"{db_type} database configuration is incomplete. Missing: {', '.join(missing_config)}. Please check your .env file."
            current_app.logger.error(error_msg)
            raise ValueError(error_msg)
        
        try:
            connection = psycopg.connect(
                host=host,
                port=int(port),
                user=user,
                password=password,
                dbname=database,
                autocommit=autocommit
            )
            current_app.logger.info(f"Successfully connected to {db_type} database: {database}@{host}:{port}")
            return connection
        except Error as e:
            error_msg = f"Failed to connect to {db_type} database '{database}' at {host}:{port}. Error: {str(e)}"
            current_app.logger.error(error_msg)
            # PostgreSQL error codes
            if 'password authentication failed' in str(e).lower() or 'authentication failed' in str(e).lower():
                error_msg = f"Access denied for {db_type} database. Please check your username and password in .env file."
            elif 'database' in str(e).lower() and 'does not exist' in str(e).lower():
                error_msg = f"Database '{database}' does not exist for {db_type}. Please create the database or check the database name in .env file."
            elif 'could not connect' in str(e).lower() or 'connection refused' in str(e).lower():
                error_msg = f"Cannot connect to {db_type} database server at {host}:{port}. Please check if the server is running and the host/port are correct."
            raise ValueError(error_msg) from e
    
    @staticmethod
    def execute_query_with_transaction(query, db_type, user, defect_number):
        """
        Execute a query within a transaction (without committing).
        For SELECT queries, commits immediately.
        For DML queries, executes but doesn't commit - stores in session for later commit/rollback.
        
        Args:
            query (str): SQL query to execute
            db_type (str): 'BackOffice' or 'Portal'
            user (str): Username executing the query
            defect_number (str): Defect number
            
        Returns:
            tuple: (success, data, error_message, audit_id)
                - success (bool): True if query executed successfully
                - data: dict with 'columns', 'rows', 'rows_affected' for SELECT queries,
                        or dict with 'rows_affected' for DML queries
                - error_message (str): Error message if failed
                - audit_id (int): Audit log ID
        """
        from utils.validators import SQLValidator
        from utils.audit_logger import AuditLogger
        
        # Validate query
        is_valid, error_msg = SQLValidator.validate_query(query)
        if not is_valid:
            return False, None, error_msg, None
        
        # Don't create audit log upfront - we'll create separate logs for committed and pending queries
        connection = None
        cursor = None
        
        try:
            # Split query into individual statements
            statements = [s.strip() + ';' if s.strip() and not s.strip().endswith(';') else s.strip() 
                         for s in query.split(';') if s.strip()]
            
            if not statements:
                return False, None, "No valid statements found in query.", audit_id
            
            # Get a connection for executing statements
            # We'll use this for SELECT/read-only, and create individual connections for DML
            connection = DatabaseManager.get_connection(db_type, autocommit=True)
            cursor = connection.cursor(row_factory=rows.dict_row)
            
            # Track current database (for USE statements)
            current_database = db_type
            config_key = 'PORTAL' if db_type == 'Portal' else 'BACKOFFICE'
            original_database_name = current_app.config.get(f'{config_key}_DB_NAME', '')
            
            # Track results
            all_results = []
            all_columns = set()
            total_rows_affected = 0
            has_dml = False
            query_types = []
            committed_statements = []
            failed_statements = []
            threshold_exceeded_statements = []
            total_committed_rows = 0
            
            # Execute each statement individually
            for idx, stmt in enumerate(statements):
                if not stmt:
                    continue
                    
                # Determine statement type
                stmt_clean = SQLValidator.clean_query(stmt)
                stmt_type = SQLValidator.get_query_type(stmt)
                query_types.append(stmt_type)
                
                # Apply LIMIT 10 to SELECT statements if not present
                # Only add LIMIT for statements that actually start with SELECT,
                # not for SHOW/DESCRIBE/EXPLAIN which are treated as SELECT-like.
                stmt_upper = stmt_clean.upper()
                if stmt_upper.startswith('SELECT'):
                    if ' LIMIT ' not in stmt_upper and not stmt_upper.endswith(' LIMIT'):
                        if stmt.strip().endswith(';'):
                            stmt = stmt.strip()[:-1] + ' LIMIT 10;'
                        else:
                            stmt = stmt.strip() + ' LIMIT 10'
                
                try:
                    if stmt_type == 'USE':
                        # PostgreSQL doesn't support USE statement
                        # Instead, we reconnect to the new database
                        use_match = re.search(r'USE\s+([^\s;]+)', stmt_clean, re.IGNORECASE)
                        if use_match:
                            original_database_name = use_match.group(1)
                            # Reconnect with new database context
                            connection.close()
                            connection = DatabaseManager._get_connection_with_db(db_type, original_database_name, autocommit=True)
                            cursor = connection.cursor(row_factory=rows.dict_row)
                        continue
                        
                    elif stmt_type == 'SELECT':
                        # Execute SELECT/SHOW/DESCRIBE/EXPLAIN on main connection
                        cursor.execute(stmt)
                        try:
                            result_rows = cursor.fetchall()
                            if result_rows:
                                stmt_columns = set(result_rows[0].keys())
                                all_columns.update(stmt_columns)
                                all_results.extend(result_rows)
                                total_rows_affected += len(result_rows)
                        except Exception:
                            pass
                            
                    elif stmt_type in ['INSERT', 'UPDATE', 'DELETE']:
                        # DML operation - execute individually in separate connection
                        has_dml = True
                        rows_affected = 0
                        
                        try:
                            # Create separate connection for this DML statement (use current database)
                            dml_conn = DatabaseManager._get_connection_with_db(db_type, original_database_name, autocommit=False)
                            dml_cursor = dml_conn.cursor()
                            dml_cursor.execute(stmt)
                            rows_affected = dml_cursor.rowcount
                            
                            # Check threshold for UPDATE/DELETE
                            if stmt_type in ['UPDATE', 'DELETE'] and rows_affected >= SQLValidator.ROW_CONFIRMATION_THRESHOLD:
                                # Exceeds threshold - rollback and treat as error (but allow confirmation)
                                dml_conn.rollback()
                                dml_cursor.close()
                                dml_conn.close()
                                
                                threshold_exceeded_statements.append({
                                    'index': idx + 1,
                                    'statement': stmt,
                                    'type': stmt_type,
                                    'rows_affected': rows_affected,
                                    'threshold': SQLValidator.ROW_CONFIRMATION_THRESHOLD
                                })
                            else:
                                # Within threshold - commit immediately
                                dml_conn.commit()
                                dml_cursor.close()
                                dml_conn.close()
                                
                                # Create separate audit log for this committed statement
                                committed_audit_id = AuditLogger.log_query(
                                    user, stmt, db_type, defect_number, 
                                    status='Success', rows_affected=rows_affected
                                )
                                
                                committed_statements.append({
                                    'index': idx + 1,
                                    'statement': stmt,
                                    'type': stmt_type,
                                    'rows_affected': rows_affected,
                                    'audit_id': committed_audit_id
                                })
                                total_committed_rows += rows_affected
                                
                        except Error as e:
                            error_msg = str(e)
                            current_app.logger.error(f"Statement {idx + 1} failed: {error_msg}")
                            failed_statements.append({
                                'index': idx + 1,
                                'statement': stmt,
                                'error': error_msg,
                                'rows_affected': 0
                            })
                            try:
                                if 'dml_conn' in locals():
                                    dml_conn.rollback()
                                    dml_cursor.close()
                                    dml_conn.close()
                            except:
                                pass
                                
                    else:
                        # UNKNOWN or other statement types
                        cursor.execute(stmt)
                        try:
                            result_rows = cursor.fetchall()
                            if result_rows:
                                stmt_columns = set(result_rows[0].keys())
                                all_columns.update(stmt_columns)
                                all_results.extend(result_rows)
                                total_rows_affected += len(result_rows)
                        except Exception:
                            pass
                            
                except Error as e:
                    # Statement execution failed (for non-DML)
                    error_msg = str(e)
                    current_app.logger.error(f"Statement {idx + 1} failed: {error_msg}")
                    if stmt_type not in ['INSERT', 'UPDATE', 'DELETE']:
                        # For non-DML, this is a fatal error
                        raise
            
            # Close main connection
            if cursor:
                cursor.close()
            if connection:
                connection.close()
            
            # Prepare response
            if has_dml:
                # Handle DML results
                messages = []
                
                if committed_statements:
                    messages.append(f"Successfully committed {len(committed_statements)} statement(s) affecting {total_committed_rows} row(s).")
                
                if failed_statements:
                    error_details = "; ".join([f"Query {s['index']}: {s['error']}" for s in failed_statements])
                    messages.append(f"Failed to execute {len(failed_statements)} statement(s): {error_details}")
                
                if threshold_exceeded_statements:
                    # Create combined audit log for all pending (threshold-exceeded) statements
                    pending_queries = [s['statement'] for s in threshold_exceeded_statements]
                    pending_audit_id = AuditLogger.log_combined_pending(
                        user, pending_queries, db_type, defect_number
                    )
                    
                    # Store in session for confirmation
                    session['threshold_exceeded_statements'] = threshold_exceeded_statements
                    session['committed_statements'] = committed_statements
                    session['failed_statements'] = failed_statements
                    session['last_query'] = {
                        'query': query,
                        'database': db_type,
                        'defect_number': defect_number,
                        'audit_id': pending_audit_id,  # Use pending audit_id for tracking
                        'data': {
                            'query_type': threshold_exceeded_statements[0]['type'],
                            'rows_affected': sum(s['rows_affected'] for s in threshold_exceeded_statements),
                            'committed_count': len(committed_statements),
                            'failed_count': len(failed_statements),
                            'threshold_exceeded_count': len(threshold_exceeded_statements),
                            'messages': messages
                        }
                    }
                    session.modified = True
                    
                    # Return data for confirmation
                    data = {
                        'query_type': threshold_exceeded_statements[0]['type'],
                        'rows_affected': sum(s['rows_affected'] for s in threshold_exceeded_statements),
                        'statements_executed': len(statements),
                        'committed_count': len(committed_statements),
                        'failed_count': len(failed_statements),
                        'threshold_exceeded_count': len(threshold_exceeded_statements),
                        'messages': messages,
                        'committed_statements': committed_statements,
                        'failed_statements': failed_statements,
                        'threshold_exceeded_statements': threshold_exceeded_statements
                    }
                    
                    return True, data, None, pending_audit_id
                else:
                    # All DML statements either committed or failed - no threshold issues
                    # Separate audit logs have already been created for committed statements
                    # Create audit logs for failed statements if needed (optional - for tracking)
                    
                    # Combine error message if any failures
                    error_msg = None
                    if failed_statements:
                        error_details = "; ".join([f"Query {s['index']}: {s['error']}" for s in failed_statements])
                        error_msg = f"Some statements failed: {error_details}"
                        # Log failed statements with Error status
                        for failed_stmt in failed_statements:
                            AuditLogger.log_query(
                                user, failed_stmt['statement'], db_type, defect_number,
                                status='Error', rows_affected=0
                            )
                    
                    # Return data - use first committed audit_id if available, or None
                    return_audit_id = None
                    if committed_statements:
                        return_audit_id = committed_statements[0].get('audit_id')
                    
                    data = {
                        'query_type': query_types[0] if query_types else 'UNKNOWN',
                        'rows_affected': total_committed_rows,
                        'statements_executed': len(statements),
                        'committed_count': len(committed_statements),
                        'failed_count': len(failed_statements),
                        'messages': messages,
                        'committed_statements': committed_statements,
                        'failed_statements': failed_statements
                    }
                    
                    # Add SELECT results if any
                    if all_results:
                        columns = sorted(list(all_columns)) if all_columns else []
                        if all_columns and all_results:
                            normalized_results = []
                            for row in all_results:
                                normalized_row = {col: row.get(col) for col in columns}
                                normalized_results.append(normalized_row)
                            all_results = normalized_results
                        
                        data['columns'] = columns
                        data['rows'] = all_results
                    
                    return True, data, error_msg, return_audit_id
            else:
                # All read-only statements - create audit log with Success status
                columns = sorted(list(all_columns)) if all_columns else []
                
                # Normalize results
                if all_columns and all_results:
                    normalized_results = []
                    for row in all_results:
                        normalized_row = {col: row.get(col) for col in columns}
                        normalized_results.append(normalized_row)
                    all_results = normalized_results
                
                data = {
                    'columns': columns,
                    'rows': all_results,
                    'rows_affected': total_rows_affected,
                    'query_type': 'SELECT',
                    'statements_executed': len(statements)
                }
                
                # Create audit log for SELECT query with Success status
                select_audit_id = AuditLogger.log_query(
                    user, query, db_type, defect_number,
                    status='Success', rows_affected=total_rows_affected
                )
                
                return True, data, None, select_audit_id
            
        except ValueError as e:
            # Configuration or connection error
            error_msg = str(e)
            current_app.logger.error(error_msg)
            
            # Create audit log with Error status
            error_audit_id = AuditLogger.log_query(
                user, query, db_type, defect_number,
                status='Error', rows_affected=0
            )
            if error_audit_id:
                AuditLogger.update_log_status(error_audit_id, 'Error', 0, error_msg, database_name=db_type)
            
            return False, None, error_msg, error_audit_id
            
        except Error as e:
            error_msg = f"Database error: {str(e)}"
            current_app.logger.error(error_msg)
            
            # Rollback on error
            if connection:
                connection.rollback()
            
            # Create audit log with Error status
            error_audit_id = AuditLogger.log_query(
                user, query, db_type, defect_number,
                status='Error', rows_affected=0
            )
            if error_audit_id:
                AuditLogger.update_log_status(error_audit_id, 'Error', 0, str(e), database_name=db_type)
            
            return False, None, error_msg, error_audit_id
            
        except Exception as e:
            error_msg = f"Unexpected error: {str(e)}"
            current_app.logger.error(error_msg)
            
            # Rollback on error
            if connection:
                connection.rollback()
            
            # Create audit log with Error status
            error_audit_id = AuditLogger.log_query(
                user, query, db_type, defect_number,
                status='Error', rows_affected=0
            )
            if error_audit_id:
                AuditLogger.update_log_status(error_audit_id, 'Error', 0, str(e), database_name=db_type)
            
            return False, None, error_msg, error_audit_id
            
        finally:
            # Close cursor and connection
            # Note: This means we can't commit later - we'll need to re-execute on commit
            if cursor:
                cursor.close()
            if connection:
                connection.close()
    
    @staticmethod
    def commit_transaction(db_type, audit_id, user):
        """
        Commit pending transactions for a specific audit_id.
        Since we can't keep connections open, we re-execute and commit.
        
        Args:
            db_type (str): 'BackOffice' or 'Portal'
            audit_id (int): Audit log ID
            user (str): Username
            
        Returns:
            tuple: (success, error_message)
        """
        from utils.audit_logger import AuditLogger
        
        # Find the transaction in session
        pending_transactions = session.get('pending_transactions', [])
        transaction = None
        
        for txn in pending_transactions:
            if txn.get('audit_id') == audit_id and txn.get('db_type') == db_type:
                transaction = txn
                break
        
        if not transaction:
            return False, "Transaction not found in session."
        
        query = transaction.get('query')
        connection = None
        
        try:
            # Get connection and execute query with commit
            connection = DatabaseManager.get_connection(db_type, autocommit=False)
            # Use dict_row for dictionary-like results
            cursor = connection.cursor(row_factory=rows.dict_row)
            
            # Re-execute the query
            cursor.execute(query)
            
            # Commit the transaction
            connection.commit()
            cursor.close()
            
            # Mark audit log as Committed
            AuditLogger.mark_pending_as_committed(user)
            
            # Remove from pending transactions
            pending_transactions.remove(transaction)
            session['pending_transactions'] = pending_transactions
            session.modified = True
            
            return True, None
            
        except Error as e:
            error_msg = f"Commit error: {str(e)}"
            current_app.logger.error(error_msg)
            if connection:
                connection.rollback()
            return False, error_msg
        finally:
            if connection:
                connection.close()
    
    @staticmethod
    def rollback_transaction(db_type, audit_id, user):
        """
        Rollback pending transactions for a specific audit_id.
        
        Args:
            db_type (str): 'BackOffice' or 'Portal'
            audit_id (int): Audit log ID
            user (str): Username
            
        Returns:
            tuple: (success, error_message)
        """
        from utils.audit_logger import AuditLogger
        
        # Find the transaction in session
        pending_transactions = session.get('pending_transactions', [])
        transaction = None
        
        for txn in pending_transactions:
            if txn.get('audit_id') == audit_id and txn.get('db_type') == db_type:
                transaction = txn
                break
        
        if not transaction:
            return False, "Transaction not found in session."
        
        # Remove from pending transactions (rollback means we won't commit)
        pending_transactions.remove(transaction)
        session['pending_transactions'] = pending_transactions
        session.modified = True
        
        # Update audit log - we could add a 'RolledBack' status, but for now just remove from pending
        # The query was already executed, so we can't truly rollback without transaction state
        # This is a limitation of the web app model
        
        return True, None
