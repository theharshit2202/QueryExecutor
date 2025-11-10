"""
Audit logging utilities for tracking query executions.
"""
from flask import current_app, session
from psycopg import Error
import psycopg
from datetime import datetime


class AuditLogger:
    """Handles audit logging for query executions."""
    
    @staticmethod
    def get_audit_db_connection(preferred_db_type: str | None = None):
        """Get connection to database for audit log.
        If preferred_db_type provided ('BackOffice' or 'Portal'), use that DB.
        Otherwise attempt BackOffice then Portal.
        """
        try:
            def _connect(prefix: str):
                conn = psycopg.connect(
                    host=current_app.config.get(f'{prefix}_DB_HOST'),
                    port=current_app.config.get(f'{prefix}_DB_PORT', 5432),
                    user=current_app.config.get(f'{prefix}_DB_USER'),
                    password=current_app.config.get(f'{prefix}_DB_PASSWORD'),
                    dbname=current_app.config.get(f'{prefix}_DB_NAME'),
                    autocommit=True
                )
                return conn

            if preferred_db_type in ('BackOffice', 'Portal'):
                return _connect('PORTAL' if preferred_db_type == 'Portal' else 'BACKOFFICE')

            # Fallback order: BackOffice then Portal
            return _connect('BACKOFFICE')
        except Error as e:
            current_app.logger.error(f"Audit DB connection error: {str(e)}")
            # Try Portal DB as fallback
            try:
                return _connect('PORTAL')
            except Error:
                return None
    
    @staticmethod
    def ensure_audit_table_exists(target_db_type: str | None = None):
        """Ensure audit_log table exists."""
        connection = AuditLogger.get_audit_db_connection(target_db_type)
        if not connection:
            return False
        
        try:
            cursor = connection.cursor()
            # Check if table exists
            cursor.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name = 'audit_log'
                );
            """)
            table_exists = cursor.fetchone()[0]
            
            if not table_exists:
                # Create status type if it doesn't exist
                cursor.execute("""
                    DO $$ BEGIN
                        CREATE TYPE audit_status AS ENUM ('Pending','Success','Error','Rejected by user');
                    EXCEPTION
                        WHEN duplicate_object THEN null;
                    END $$;
                """)
                
                create_table_sql = """
                CREATE TABLE audit_log (
                    audit_id SERIAL PRIMARY KEY,
                    audit_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    executed_by_user VARCHAR(100),
                    query_text TEXT,
                    database_name VARCHAR(50),
                    status audit_status DEFAULT 'Pending',
                    defect_number VARCHAR(50),
                    rows_affected INTEGER DEFAULT 0,
                    error_message TEXT
                );
                """
                cursor.execute(create_table_sql)
                
                # Create indexes
                cursor.execute("CREATE INDEX idx_user ON audit_log(executed_by_user);")
                cursor.execute("CREATE INDEX idx_timestamp ON audit_log(audit_timestamp);")
                cursor.execute("CREATE INDEX idx_status ON audit_log(status);")
                connection.commit()
            else:
                # Check if status column needs to be updated (migration)
                try:
                    cursor.execute("""
                        SELECT EXISTS (
                            SELECT 1 FROM information_schema.columns 
                            WHERE table_name = 'audit_log' 
                            AND column_name = 'status'
                            AND data_type = 'USER-DEFINED'
                        );
                    """)
                    has_enum = cursor.fetchone()[0]
                    
                    if not has_enum:
                        # Migrate from VARCHAR to ENUM if needed
                        cursor.execute("""
                            DO $$ BEGIN
                                CREATE TYPE audit_status AS ENUM ('Pending','Success','Error','Rejected by user');
                            EXCEPTION
                                WHEN duplicate_object THEN null;
                            END $$;
                        """)
                        cursor.execute("""
                            ALTER TABLE audit_log 
                            ALTER COLUMN status TYPE audit_status 
                            USING status::audit_status;
                        """)
                        connection.commit()
                except Error:
                    # Migration might not be needed, ignore error
                    pass
            
            cursor.close()
            return True
        except Error as e:
            current_app.logger.error(f"Error creating audit table: {str(e)}")
            return False
        finally:
            if connection:
                connection.close()
    
    @staticmethod
    def log_query(user, query_text, database_name, defect_number, status='Pending', rows_affected=0):
        """Log one or multiple query executions with specified status.
        
        Accepts a single query string, or a list/tuple of query strings.
        Returns a single audit_id for a single query, or a list of audit_ids for multiple queries.
        Returns None on failure.
        
        Args:
            user: Username executing the query
            query_text: Single query string or list/tuple of query strings
            database_name: Database name
            defect_number: Defect number
            status: Status to set ('Pending', 'Success', 'Error', etc.)
            rows_affected: Number of rows affected (for committed queries)
        """
        AuditLogger.ensure_audit_table_exists(database_name)

        connection = AuditLogger.get_audit_db_connection(database_name)
        if not connection:
            return None

        is_multiple = isinstance(query_text, (list, tuple))
        queries = list(query_text) if is_multiple else [query_text]

        try:
            cursor = connection.cursor()
            insert_sql = """
            INSERT INTO audit_log 
            (executed_by_user, query_text, database_name, defect_number, status, rows_affected)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING audit_id
            """

            audit_ids = []
            for q in queries:
                cursor.execute(insert_sql, (user, q, database_name, defect_number, status, rows_affected))
                result = cursor.fetchone()
                if result:
                    audit_ids.append(result[0])

            connection.commit()
            cursor.close()

            # Store audit_ids in session for transaction tracking (only for Pending status)
            if status == 'Pending':
                if 'pending_audit_ids' not in session:
                    session['pending_audit_ids'] = []
                session['pending_audit_ids'].extend(audit_ids)
                session.modified = True

            return audit_ids if is_multiple else (audit_ids[0] if audit_ids else None)
        except Error as e:
            current_app.logger.error(f"Error logging query: {str(e)}")
            return None
        finally:
            if connection:
                connection.close()
    
    @staticmethod
    def log_combined_pending(user, queries, database_name, defect_number):
        """Log multiple queries combined into a single audit log with Pending status.
        
        This is used for threshold-exceeded statements that need confirmation.
        Combines all queries into one audit log entry.
        
        Args:
            user: Username executing the query
            queries: List of query strings to combine
            database_name: Database name
            defect_number: Defect number
            
        Returns:
            audit_id: Single audit log ID for the combined queries, or None on failure
        """
        if not queries:
            return None
            
        AuditLogger.ensure_audit_table_exists(database_name)
        connection = AuditLogger.get_audit_db_connection(database_name)
        if not connection:
            return None

        try:
            cursor = connection.cursor()
            # Combine all queries into a single query text
            combined_query = '; '.join(queries)
            
            insert_sql = """
            INSERT INTO audit_log 
            (executed_by_user, query_text, database_name, defect_number, status)
            VALUES (%s, %s, %s, %s, 'Pending')
            RETURNING audit_id
            """
            cursor.execute(insert_sql, (user, combined_query, database_name, defect_number))
            result = cursor.fetchone()
            audit_id = result[0] if result else None
            
            connection.commit()
            cursor.close()

            # Store audit_id in session for transaction tracking
            if 'pending_audit_ids' not in session:
                session['pending_audit_ids'] = []
            session['pending_audit_ids'].append(audit_id)
            session.modified = True

            return audit_id
        except Error as e:
            current_app.logger.error(f"Error logging combined pending query: {str(e)}")
            return None
        finally:
            if connection:
                connection.close()
    
    @staticmethod
    def update_log_status(audit_id, status, rows_affected=0, error_message=None, database_name=None):
        """Update audit log status."""
        connection = AuditLogger.get_audit_db_connection(database_name)
        if not connection:
            return False
        
        try:
            cursor = connection.cursor()
            if error_message:
                update_sql = """
                UPDATE audit_log 
                SET status = %s, rows_affected = %s, error_message = %s
                WHERE audit_id = %s
                """
                cursor.execute(update_sql, (status, rows_affected, str(error_message)[:500], audit_id))
            else:
                update_sql = """
                UPDATE audit_log 
                SET status = %s, rows_affected = %s
                WHERE audit_id = %s
                """
                cursor.execute(update_sql, (status, rows_affected, audit_id))
            connection.commit()
            cursor.close()
            return True
        except Error as e:
            current_app.logger.error(f"Error updating audit log: {str(e)}")
            return False
        finally:
            if connection:
                connection.close()
    
    @staticmethod
    def mark_pending_as_committed(user):
        """Mark all pending audit logs for the current session as Success.
        
        Note: This method is kept for backward compatibility but is no longer used
        in the main flow. Status is now updated directly in the commit route.
        """
        if 'pending_audit_ids' not in session:
            return True
        
        audit_ids = session.get('pending_audit_ids', [])
        if not audit_ids:
            return True
        
        connection = AuditLogger.get_audit_db_connection()
        if not connection:
            return False
        
        try:
            cursor = connection.cursor()
            placeholders = ','.join(['%s'] * len(audit_ids))
            update_sql = f"""
            UPDATE audit_log 
            SET status = 'Success'
            WHERE audit_id IN ({placeholders}) AND executed_by_user = %s AND status = 'Pending'
            """
            params = audit_ids + [user]
            cursor.execute(update_sql, params)
            connection.commit()
            cursor.close()
            
            # Clear pending audit IDs from session
            session.pop('pending_audit_ids', None)
            session.modified = True
            
            return True
        except Error as e:
            current_app.logger.error(f"Error marking logs as committed: {str(e)}")
            return False
        finally:
            if connection:
                connection.close()

