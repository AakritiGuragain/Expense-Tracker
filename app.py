import sqlite3
from flask import Flask, render_template, request, g, redirect, url_for, send_file
import logging
from datetime import datetime
import csv
from io import StringIO, BytesIO # Import BytesIO

app = Flask(__name__)
DATABASE = 'expenses.db'

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def get_db():
    """
    Gets the database connection for the current request.
    If a connection is not already established, it creates one.
    """
    if 'db' not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close_db(e=None):
    """Closes the database connection at the end of the request."""
    db = g.pop('db', None)
    if db is not None:
        db.close()
        logging.info("Database connection closed.")

def init_db():
    """Initializes the database."""
    with app.app_context():
        db = get_db()
        with app.open_resource('schema.sql', mode='r') as f:
            db.cursor().executescript(f.read())
        db.commit()
        logging.info("Database initialized.")

@app.cli.command('initdb')
def initdb_command():
    """Initializes the database."""
    init_db()
    print('Initialized the database.')

def calculate_balance(transactions):
    """Calculates the income, expenses, and net balance from a list of transactions."""
    income = 0
    expenses = 0
    for transaction in transactions:
        if transaction['type'] == 'income':
            income += transaction['amount']
        elif transaction['type'] == 'expense':
            expenses += transaction['amount']
    net = income - expenses
    return {'income': income, 'expenses': expenses, 'net': net}

@app.route('/')
def index():
    """Displays the transaction history and balance."""
    db = get_db()
    try:
        cursor = db.cursor()
        cursor.execute("SELECT * FROM transactions ORDER BY date DESC")
        transactions = cursor.fetchall()
        balance = calculate_balance(transactions)
        return render_template('index.html', transactions=transactions, balance=balance)
    except Exception as e:
        logging.error(f"Error fetching transactions: {e}")
        return f"An error occurred: {e}", 500

@app.route('/add_transaction', methods=['POST'])
def add_transaction():
    """Adds a new transaction (income or expense) to the database."""
    db = get_db()
    date_str = request.form['date']
    try:
        date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        logging.error(f"Invalid date format: {date_str}")
        return "Invalid date format. Please use-MM-DD", 400

    description = request.form['description']
    category = request.form['category']
    amount = float(request.form['amount'])
    type = request.form['type']

    if type not in ('income', 'expense'):
        logging.error(f"Invalid transaction type: {type}")
        return "Invalid transaction type", 400

    try:
        cursor = db.cursor()
        cursor.execute(
            "INSERT INTO transactions (date, description, category, amount, type) VALUES (?, ?, ?, ?, ?)",
            (date, description, category, amount, type),
        )
        db.commit()
        logging.info(f"Transaction added: {date}, {description}, {category}, {amount}, {type}")
    except Exception as e:
        logging.error(f"Error adding transaction: {e}")
        db.rollback()
        return "Error adding transaction", 500
    finally:
        db.close()
    return redirect(url_for('index'))

@app.route('/delete_transaction/<int:transaction_id>', methods=['POST'])
def delete_transaction(transaction_id):
    """Deletes a transaction from the database."""
    db = get_db()
    try:
        db.execute('DELETE FROM transactions WHERE id = ?', (transaction_id,))
        db.commit()
        logging.info(f"Transaction {transaction_id} deleted successfully.")
    except Exception as e:
        logging.error(f"Error deleting transaction {transaction_id}: {e}")
        db.rollback()
        return "Error deleting transaction", 500
    finally:
        db.close()
    return redirect(url_for('index'))

@app.route('/export_csv')
def export_csv():
    """Exports transaction data to a CSV file."""
    db = get_db()
    try:
        cursor = db.cursor()
        cursor.execute("SELECT * FROM transactions ORDER BY date DESC")
        transactions = cursor.fetchall()

        output = StringIO()
        writer = csv.writer(output)

        # Write header
        writer.writerow(['Date', 'Description', 'Category', 'Amount', 'Type'])

        # Write transaction data
        for transaction in transactions:
            writer.writerow([
                transaction['date'],
                transaction['description'],
                transaction['category'],
                transaction['amount'],
                transaction['type']
            ])

        #  Use BytesIO instead of StringIO for binary data
        mem = BytesIO()
        mem.write(output.getvalue().encode('utf-8')) # Encode the string
        mem.seek(0)

        return send_file(mem, download_name='transactions.csv', mimetype='text/csv', as_attachment=True)
    except Exception as e:
        logging.error(f"Error exporting to CSV: {e}")
        return f"An error occurred: {e}", 500

def get_category_breakdown(transactions):
    """Calculates the total income and expenses for each category."""
    category_data = {}
    for transaction in transactions:
        category = transaction['category']
        amount = transaction['amount']
        type = transaction['type']

        if category not in category_data:
            category_data[category] = {'income': 0, 'expenses': 0}

        if type == 'income':
            category_data[category]['income'] += amount
        elif type == 'expense':
            category_data[category]['expenses'] += amount
    return category_data

@app.route('/category_breakdown')
def category_breakdown():
    """Displays a breakdown of income and expenses by category."""
    db = get_db()
    try:
        cursor = db.cursor()
        cursor.execute("SELECT * FROM transactions ORDER BY date DESC")
        transactions = cursor.fetchall()
        category_data = get_category_breakdown(transactions)
        return render_template('category_breakdown.html', category_data=category_data)
    except Exception as e:
        logging.error(f"Error fetching category breakdown: {e}")
        return f"An error occurred: {e}", 500

if __name__ == '__main__':
    app.run(debug=True)
