import os
import json
import logging 
import csv
import psutil
from io import StringIO, BytesIO
from datetime import datetime

from flask import Flask, render_template, request, session, redirect, url_for, flash, jsonify, send_file
from flask_session import Session
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_login import LoginManager, UserMixin, login_user, logout_user, current_user, login_required
from calcualtors import GoldCalculator, SilverCalculator

# Initialize the Flask app
app = Flask(__name__)

# Load configuration from environment variables or fallback to defaults
app.secret_key = os.getenv('SECRET_KEY', 'jhd87^&*^udhwduy792ejlndhy783uh')
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///test.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
Session(app)
db = SQLAlchemy(app)
bcrypt = Bcrypt(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# Load configuration from JSON file
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_DIR = os.path.join(ROOT_DIR, 'config')
CONFIG_FILE_PATH = os.path.join(CONFIG_DIR, 'config.json')

def load_config() -> dict:
    """Loads configuration from a JSON file."""
    try:
        with open(CONFIG_FILE_PATH) as config_file:
            return json.load(config_file)
    except FileNotFoundError:
        logging.error(f"Configuration file not found at {CONFIG_FILE_PATH}")
        return {}
    except json.JSONDecodeError as e:
        logging.error(f"Error decoding JSON config: {e}")
        return {}

app.config.update(load_config())

# Define the database models


class GoldTransaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    weight = db.Column(db.Float, nullable=False)
    price_per_gram = db.Column(db.Float, nullable=False)
    purity = db.Column(db.String(50), nullable=False)
    service_charge = db.Column(db.Float, nullable=False)
    tax = db.Column(db.Float, nullable=False)
    total = db.Column(db.Float, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)


class SilverTransaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    weight = db.Column(db.Float, nullable=False)
    price_per_gram = db.Column(db.Float, nullable=False)
    purity = db.Column(db.String(50), nullable=False)
    service_charge = db.Column(db.Float, nullable=False)
    tax = db.Column(db.Float, nullable=False)
    total = db.Column(db.Float, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)


class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    fname = db.Column(db.String(20), nullable=False)
    lname = db.Column(db.String(20), nullable=False)
    username = db.Column(db.String(20), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(60), nullable=False)
    user_level = db.Column(db.String(10), nullable=False, default='customer')

    def __repr__(self):
        return f"User('{self.username}', '{self.email}', '{self.user_level}')"


class Settings(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    currency = db.Column(db.String(10), nullable=False)
    theme = db.Column(db.String(10), nullable=False)


class AuditLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    username = db.Column(db.String(20), nullable=False)
    action = db.Column(db.String(255), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    details = db.Column(db.Text, nullable=True)

    def __repr__(self):
        return f"AuditLog('{self.user_id}', '{self.action}', '{self.timestamp}')"


# Create the database
with app.app_context():
    db.create_all()

@app.route('/health')
def health():
    health_info = {
        "status": "healthy",
        "message": "The server is up and running.",
        "version": "1.0.0",
        "timestamp": datetime.now().isoformat()
    }
    return render_template('health.html', **health_info)

@app.route('/permission-denied')
def permission_denied():
    return render_template('permission_denied.html')

@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

# Home route
@app.route('/')
def home() -> str:
    return render_template('homepage.html')

@app.context_processor
def inject_theme():
    return dict(current_theme=app.config.get('THEME', 'light'))

# Gold calculator route
@app.route('/gold-calculator', methods=['GET', 'POST'])
def gold_calculator():
    if request.method == 'POST':
        try:
            weight = float(request.form['weight'])
            gold_price_per_gram = float(request.form['price_per_gram'])
            gold_service_charge = float(request.form['service_charge'])
            gold_tax = float(request.form['tax'])
            purity = request.form['purity']

            # Save price per gram to session
            session['gold_price_per_gram'] = gold_price_per_gram
            session['gold_service_charge'] = gold_service_charge
            session['gold_tax'] = gold_tax

            # Calculate gold price
            gold_item = GoldCalculator(weight, gold_price_per_gram, gold_service_charge, gold_tax)
            bill_details = gold_item.calculate_price()

            # Save to database
            transaction = GoldTransaction(
                weight=weight,
                price_per_gram=gold_price_per_gram,
                purity=purity,
                service_charge=gold_service_charge,
                tax=gold_tax,
                total=bill_details['Final Price']
            )
            db.session.add(transaction)
            db.session.commit()

            return render_template('gold_bill.html',
                                   bill=bill_details,
                                   weight=weight,
                                   price_per_gram=gold_price_per_gram,
                                   purity=purity,
                                   config=app.config)
        except ValueError as e:
            logging.error(f"ValueError in gold calculator: {str(e)}")
            flash(f"Input error: {str(e)}", 'error')
            return redirect(url_for('gold_calculator'))

    # Use session-stored price per gram or a default value
    gold_price_per_gram = session.get('gold_price_per_gram', 0)
    gold_service_charge = session.get('gold_service_charge', 0)
    gold_tax = session.get('gold_tax', 0)

    return render_template('gold_calculator.html',
                           price_per_gram=gold_price_per_gram,
                           service_charge=gold_service_charge,
                           tax=gold_tax,
                           config=app.config)

# Silver calculator route
@app.route('/silver-calculator', methods=['GET', 'POST'])
def silver_calculator():
    if request.method == 'POST':
        try:
            weight = float(request.form['weight'])
            silver_price_per_gram = float(request.form['price_per_gram'])
            silver_purity = float(request.form['purity'])
            silver_service_charge = float(request.form['service_charge'])
            silver_tax = float(request.form['tax'])

            # Save price per gram to session
            session['silver_price_per_gram'] = silver_price_per_gram
            session['silver_service_charge'] = silver_service_charge
            session['silver_tax'] = silver_tax

            # Calculate silver price
            silver_item = SilverCalculator(
                weight=weight,
                price_per_gram=silver_price_per_gram,
                service_charge=silver_service_charge,
                tax=silver_tax,
                purity=silver_purity
            )
            bill_details = silver_item.calculate_price()

            # Save to database
            transaction = SilverTransaction(
                weight=weight,
                price_per_gram=silver_price_per_gram,
                service_charge=silver_service_charge,
                tax=silver_tax,
                total=bill_details['Final Price'],
                purity=silver_purity
            )
            db.session.add(transaction)
            db.session.commit()

            return render_template('silver_bill.html',
                                   bill=bill_details,
                                   weight=weight,
                                   price_per_gram=silver_price_per_gram,
                                   purity=silver_purity,
                                   config=app.config)
        except ValueError as e:
            logging.error(f"ValueError in silver calculator: {str(e)}")
            flash(f"Input error: {str(e)}", 'error')
            return redirect(url_for('silver_calculator'))

    # Use session-stored price per gram or a default value
    silver_price_per_gram = session.get('silver_price_per_gram', 0)
    silver_service_charge = session.get('silver_service_charge', 0)
    silver_tax = session.get('silver_tax', 0)

    return render_template('silver_calculator.html',
                           price_per_gram=silver_price_per_gram,
                           service_charge=silver_service_charge,
                           tax=silver_tax,
                           config=app.config)

@app.route('/history', methods=['GET'])
@login_required
def history():
    if current_user.user_level != 'admin':
        return redirect(url_for('permission_denied'))
    selected_type = request.args.get('type', 'all')

    if selected_type == 'gold':
        transactions = GoldTransaction.query.all()
        transactions = [{'id': t.id, 'type': 'Gold', 'weight': t.weight, 'price_per_gram': t.price_per_gram, 
                         "purity": t.purity, 'service_charge': t.service_charge, 'tax': t.tax, 'total': t.total, 'timestamp': t.timestamp} for t in transactions]
    elif selected_type == 'silver':
        transactions = SilverTransaction.query.all()
        transactions = [{'id': t.id, 'type': 'Silver', 'weight': t.weight, 'price_per_gram': t.price_per_gram,
                         'purity': t.purity, 'service_charge': t.service_charge, 'tax': t.tax, 'total': t.total, 'timestamp': t.timestamp} for t in transactions]
    else:
        gold_transactions = GoldTransaction.query.all()
        silver_transactions = SilverTransaction.query.all()

        transactions = [{'id': t.id, 'type': 'Gold', 'weight': t.weight, 'price_per_gram': t.price_per_gram,
                         'purity': t.purity, 'service_charge': t.service_charge, 'tax': t.tax, 'total': t.total, 'timestamp': t.timestamp} for t in gold_transactions]

        transactions += [{'id': t.id, 'type': 'Silver', 'weight': t.weight, 'price_per_gram': t.price_per_gram,
                          'purity': t.purity, 'service_charge': t.service_charge, 'tax': t.tax, 'total': t.total, 'timestamp': t.timestamp} for t in silver_transactions]

    return render_template('history.html', transactions=transactions, selected_type=selected_type)


@app.route('/download_csv', methods=['POST'])
def download_csv():
    selected_type = request.args.get('type', 'all')

    si = StringIO()
    writer = csv.writer(si)

    header = ['ID', 'Type', 'Weight (g)', 'Price per Gram', 'Purity', 'Service Charge', 'Tax', 'Total', 'Timestamp']
    writer.writerow(header)

    transactions = []

    if selected_type == 'gold':
        transactions = GoldTransaction.query.all()
        for t in transactions:
            writer.writerow([t.id, 'Gold', t.weight, t.price_per_gram, t.purity, t.service_charge, t.tax, t.total, t.timestamp])
    elif selected_type == 'silver':
        transactions = SilverTransaction.query.all()
        for t in transactions:
            writer.writerow([t.id, 'Silver', t.weight, t.price_per_gram, t.purity, t.service_charge, t.tax, t.total, t.timestamp])
    else:
        gold_transactions = GoldTransaction.query.all()
        for t in gold_transactions:
            writer.writerow([t.id, 'Gold', t.weight, t.price_per_gram, t.purity, t.service_charge, t.tax, t.total, t.timestamp])
        silver_transactions = SilverTransaction.query.all()
        for t in silver_transactions:
            writer.writerow([t.id, 'Silver', t.weight, t.price_per_gram, t.purity, t.service_charge, t.tax, t.total, t.timestamp])

    output = si.getvalue().encode('utf-8')
    return send_file(
        BytesIO(output),
        mimetype='text/csv',
        as_attachment=True,
        download_name='transactions.csv'
    )

# Additional routes
@app.route('/pricing')
def pricing() -> str:
    return render_template('pricing.html', config=app.config)

@app.route('/features')
def features() -> str:
    return render_template('features.html', config=app.config)

@app.route('/about')
def about() -> str:
    return render_template('about.html', config=app.config)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.route("/register", methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        fname = request.form.get('fname')
        lname = request.form.get('lname')
        username = request.form.get('username')
        email = request.form.get('email')
        password = bcrypt.generate_password_hash(request.form.get('password')).decode('utf-8')
        # Set user level to 'customer' by default
        user_level = 'customer'
        user = User(fname=fname, lname=lname, username=username, email=email, password=password, user_level=user_level)
        db.session.add(user)
        db.session.commit()
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route("/login", methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        user = User.query.filter_by(email=email).first()
        if user and bcrypt.check_password_hash(user.password, password):
            login_user(user)
            log_action(user.id, user.username, 'Login', f'User {user.username} logged in.')
            return redirect(url_for('dashboard'))
    return render_template('login.html')


from flask_login import current_user, login_required

@app.route("/dashboard")
@login_required
def dashboard():
    if current_user.user_level == 'admin':
        total_users = User.query.count()  # Count total users
        active_sessions = len(session)  # This is a basic approach. You may want to track sessions differently.
        
        # Example: If you store active users in the session, you might track like this:
        active_sessions = session.get('active_users', 0)
        
        system_health = "Good"  # This can be determined by your own logic
        cpu_core = psutil.cpu_count()
        cpu_utilization = psutil.cpu_percent(interval=1)

        if cpu_utilization > 80:
            system_health = "Warning"
        else:
            system_health = "Good"

        return render_template('admin_dashboard.html', 
                            total_users=total_users, 
                            active_sessions=active_sessions, 
                            system_health=system_health,
                            cpu_core=cpu_core,
                            cpu_util=cpu_utilization)
    elif current_user.user_level == 'manager':
        return render_template('manager_dashboard.html')
    else:
        return render_template('customer_dashboard.html')

@app.route("/logout")
def logout():
    logout_user()
    return redirect(url_for('login'))


@app.route('/admin/manage_users', methods=['GET', 'POST'])
@login_required
def manage_users():
    if current_user.user_level != 'admin':
        return redirect(url_for('permission_denied'))

    users = User.query.all()

    if request.method == 'POST':
        user_id = request.form.get('user_id')
        new_level = request.form.get('user_level')
        
        user = User.query.get(user_id)
        if user:
            user.user_level = new_level
            db.session.commit()
            flash(f"User {user.username}'s level updated to {new_level}.", 'success')
        else:
            flash("User not found.", 'error')

    return render_template('manage_users.html', users=users)

@app.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    if current_user.user_level != 'admin':
        return redirect(url_for('home'))

    if request.method == 'POST':
        currency = request.form.get('currency')
        theme = request.form.get('theme')

        # Save the settings (you might save them to a database or a config file)
        # Assuming you have a Settings model or similar logic to save settings
        settings = Settings.query.first()
        if not settings:
            settings = Settings(currency=currency, theme=theme)
        else:
            settings.currency = currency
            settings.theme = theme

        flash(f'Settings updated successfully. Currency set to {currency}. Theme set to {theme}.', 'success')
        
        db.session.add(settings)
        db.session.commit()
        flash('Settings updated successfully!', 'success')
        log_action(current_user.id, current_user.username, 'System Settings Change', details=f"Currency set to {currency}, Theme set to {theme}")
        return redirect(url_for('settings'))
    
    settings = Settings.query.first()
    return render_template('settings.html', settings=settings)


def log_action(user_id, username, action, details=None):
    log_entry = AuditLog(user_id=user_id, username=username, action=action, details=details)
    db.session.add(log_entry)
    db.session.commit()


@app.route('/admin/audit_log')
@login_required
def audit_log():
    if current_user.user_level != 'admin':
        return redirect(url_for('home'))

    logs = AuditLog.query.order_by(AuditLog.timestamp.desc()).all()
    return render_template('audit_log.html', logs=logs)


if __name__ == '__main__':
    app.run(debug=True)
