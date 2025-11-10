"""
WTForms for query execution.
"""
from flask_wtf import FlaskForm
from wtforms import TextAreaField, StringField, SelectField
from wtforms.validators import DataRequired, Length, ValidationError
from utils.validators import SQLValidator


class QueryForm(FlaskForm):
    """SQL Query form."""
    sql_query = TextAreaField(
        'SQL Query',
        validators=[DataRequired(message='SQL query is required.')],
        render_kw={
            'placeholder': 'Enter your SQL query (SELECT, INSERT, UPDATE, DELETE)',
            'class': 'form-control',
            'rows': 10,
            'id': 'sql_query_editor'
        }
    )
    defect_number = StringField(
        'Defect Number',
        validators=[DataRequired(message='Defect number is required.'), Length(max=100)],
        render_kw={'placeholder': 'Enter defect number', 'class': 'form-control'}
    )
    database = SelectField(
        'Database',
        choices=[('BackOffice', 'BackOffice'), ('Portal', 'Portal')],
        validators=[DataRequired(message='Please select a database.')],
        render_kw={'class': 'form-select'}
    )
    
    def validate_sql_query(self, field):
        """Custom validation for SQL query."""
        query = field.data.strip()
        if not query:
            raise ValidationError('SQL query cannot be empty.')
        
        # Use SQLValidator for comprehensive validation
        is_valid, error_msg = SQLValidator.validate_query(query)
        if not is_valid:
            raise ValidationError(error_msg)

