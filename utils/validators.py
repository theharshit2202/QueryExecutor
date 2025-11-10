"""
SQL query validation utilities.
"""
import re


class SQLValidator:
    """Validates SQL queries for security and correctness."""
    
    # DDL keywords to block
    DDL_KEYWORDS = ['CREATE', 'DROP', 'ALTER', 'TRUNCATE', 'RENAME']
    
    # DML keywords that require WHERE clause
    DML_KEYWORDS_REQUIRING_WHERE = ['UPDATE', 'DELETE']
    
    ROW_CONFIRMATION_THRESHOLD = 10
    PROTECTED_TABLES = {'USERS', 'AUDIT_LOG'}
    
    @staticmethod
    def clean_query(query):
        """Remove comments and normalize whitespace."""
        # Remove single-line comments
        query_clean = re.sub(r'--.*$', '', query, flags=re.MULTILINE)
        # Remove multi-line comments
        query_clean = re.sub(r'/\*.*?\*/', '', query_clean, flags=re.DOTALL)
        # Normalize whitespace
        query_clean = ' '.join(query_clean.split())
        return query_clean.strip()
    
    @staticmethod
    def is_ddl_statement(query):
        """Check if query contains DDL statements."""
        query_clean = SQLValidator.clean_query(query)
        # Split by semicolon and check each statement
        statements = [s.strip() for s in query_clean.split(';') if s.strip()]
        
        for statement in statements:
            statement_upper = statement.upper()
            for keyword in SQLValidator.DDL_KEYWORDS:
                # Check if keyword appears at start of statement
                if statement_upper.startswith(keyword):
                    return True
        return False
    
    @staticmethod
    def has_multiple_statements(query):
        """Check if query contains multiple statements (semicolons not at end)."""
        # Remove comments first
        query_clean = SQLValidator.clean_query(query)
        # Count semicolons that aren't at the end
        semicolons = [m.start() for m in re.finditer(r';', query_clean)]
        if len(semicolons) > 1:
            return True
        if len(semicolons) == 1 and semicolons[0] != len(query_clean) - 1:
            return True
        return False
    
    @staticmethod
    def validate_update_has_where(query):
        """Validate that UPDATE/DELETE statements have a WHERE clause."""
        query_upper = SQLValidator.clean_query(query).upper()
        
        # Check for UPDATE or DELETE
        for keyword in SQLValidator.DML_KEYWORDS_REQUIRING_WHERE:
            if query_upper.startswith(keyword):
                # Check if WHERE clause exists
                if 'WHERE' not in query_upper:
                    return False, f"{keyword} statements must include a WHERE clause for safety."
                # Ensure WHERE is not empty
                where_match = re.search(r'WHERE\s+(.+?)(?:\s+ORDER|\s+LIMIT|$)', query_upper, re.IGNORECASE | re.DOTALL)
                if not where_match or not where_match.group(1).strip():
                    return False, f"{keyword} statements must have a valid WHERE clause."
        
        return True, None
    
    @staticmethod
    def validate_query(query):
        """
        Comprehensive query validation.
        Returns: (is_valid, error_message)
        """
        if not query or not query.strip():
            return False, "Query cannot be empty."
        
        query_clean = SQLValidator.clean_query(query)
        
        # Check for DDL (allow SHOW/DESCRIBE/EXPLAIN which are read-only)
        if SQLValidator.is_ddl_statement(query_clean):
            return False, "DDL operations (CREATE, DROP, ALTER, TRUNCATE) are not allowed."
        
        # Validate each statement individually for UPDATE/DELETE WHERE clauses
        # Split by semicolon and validate each statement
        statements = [s.strip() for s in query_clean.split(';') if s.strip()]
        for statement in statements:
            is_valid, error_msg = SQLValidator.validate_update_has_where(statement)
            if not is_valid:
                return False, error_msg
        
        return True, None

    @staticmethod
    def references_protected_tables(query):
        """Detect access to protected tables (users, audit_log)."""
        q = SQLValidator.clean_query(query).upper()
        for t in SQLValidator.PROTECTED_TABLES:
            # simple contains check with word boundary
            if re.search(rf"\b{t}\b", q):
                return True
        return False
    
    @staticmethod
    def get_query_type(query):
        """Determine query type (SELECT, INSERT, UPDATE, DELETE, USE, SHOW, etc.)."""
        query_upper = SQLValidator.clean_query(query).upper()

        if query_upper.startswith('SELECT'):
            return 'SELECT'
        # Treat SHOW / DESCRIBE / EXPLAIN as SELECT-like (read-only, returns results)
        elif query_upper.startswith('SHOW') or query_upper.startswith('DESCRIBE') or query_upper.startswith('DESC ') or query_upper.startswith('EXPLAIN'):
            return 'SELECT'
        # USE statement changes database context
        elif query_upper.startswith('USE'):
            return 'USE'
        elif query_upper.startswith('INSERT'):
            return 'INSERT'
        elif query_upper.startswith('UPDATE'):
            return 'UPDATE'
        elif query_upper.startswith('DELETE'):
            return 'DELETE'
        else:
            return 'UNKNOWN'

