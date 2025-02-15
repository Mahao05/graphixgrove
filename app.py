from flask import Flask, render_template, flash, redirect, url_for, session, request, logging
from wtforms import Form, StringField, TextAreaField, PasswordField, validators
from passlib.hash import sha256_crypt
from functools import wraps
from flask_socketio import SocketIO
from app import routes
import requests
import threading
import time

app = Flask(__name__)
app.secret_key = "secret123"
socketio = SocketIO(app)

from app import app


# Index
@app.route('/')
def index():
    return render_template('home.html')

# Helper function to fetch live data
def fetch_crypto_data():
    url = "https://api.coingecko.com/api/v3/coins/markets"
    params = {
        "vs_currency": session.get("currency", "usd"),
        "order": "market_cap_desc",
        "per_page": 10,
        "page": 1,
        "sparkline": "false",
    }
    response = requests.get(url, params=params)
    return response.json()

@app.route("/dashboard")
def dashboard():
    session["currency"] = session.get("currency", "usd")
    data = fetch_crypto_data()
    return render_template("dashboard.html", data={"crypto_data": data, "currency": session["currency"]})

@app.route("/market")
def market_cap():
    session["currency"] = session.get("currency", "usd")
    data = fetch_crypto_data()
    return render_template("market_cap.html", data={"crypto_data": data, "currency": session["currency"]})

@socketio.on("fetch_data")
def handle_realtime_data():
    # Send updated data to the client in real-time
    data = fetch_crypto_data()
    socketio.emit("update_data", {"crypto_data": data})

@app.route("/market-cap")
def market_cap():
    currency = session["currency"]
    # Replace these with actual API data
    market_cap_data = {
        "marketCap": {"BTC": 600000000, "ETH": 400000000, "Others": 200000000},
        "volume": {"BTC": 1500, "ETH": 900, "Others": 600},
        "trend": [1.2, 1.3, 1.5, 1.4, 1.6, 1.8, 2.0],
        "dates": ["Day 1", "Day 2", "Day 3", "Day 4", "Day 5", "Day 6", "Day 7"],
    }
    return render_template(
        "market_cap.html", data={"marketData": market_cap_data, "currency": currency}
    )

# Define the custom filter for formatting currency
def format_currency(value, symbol="$"):
    """
    Format a number as currency.
    
    Args:
        value (float): The number to format.
        symbol (str): The currency symbol (default is "$").
    
    Returns:
        str: The formatted currency string.
    """
    try:
        return f"{symbol}{value:,.2f}"  # Format number with 2 decimal places and thousands separator
    except (ValueError, TypeError):
        return value  # Return the original value if formatting fails

# Register the filter with Jinja2
app.jinja_env.filters["currency"] = format_currency

@app.template_filter("format_currency")
def format_currency(value, currency):
    if currency == "USD":
        return f"${value:,}"
    elif currency == "EUR":
        return f"€{value:,}"
    elif currency == "GBP":
        return f"£{value:,}"
    elif currency == "JPY":
        return f"¥{value:,}"
    return f"{value:,} {currency}"

# Background data fetch
market_data = {}
news_data = []

def fetch_data():
    global market_data, news_data
    while True:
        try:
            # Fetch market cap data
            market_data_response = requests.get("https://api.coingecko.com/api/v3/global").json()
            market_data = market_data_response['data']['total_market_cap']

            # Fetch crypto news
            news_response = requests.get("https://cryptopanic.com/api/v1/posts/?auth_token=YOUR_API_KEY").json()
            news_data = news_response['results']

            # Send data to the frontend via SocketIO
            socketio.emit("updateData", {"marketCap": market_data, "news": news_data})

            time.sleep(10)
        except Exception as e:
            print("Error fetching data:", e)

# Start background thread
threading.Thread(target=fetch_data, daemon=True).start()


@app.route("/news")
def news():
    return render_template("news.html")

@app.route("/favorites")
def favorites():
    return render_template("favorites.html")

# Register Form Class
class RegisterForm(Form):
    name = StringField('Name', [validators.Length(min=1, max=50)])
    username = StringField('Username', [validators.Length(min=4, max=25)])
    email = StringField('Email', [validators.Length(min=6, max=50)])
    password = PasswordField('Password', [
        validators.DataRequired(),
        validators.EqualTo('confirm', message='Passwords do not match')
    ])
    confirm = PasswordField('Confirm Password')


# User Register
@app.route('/register', methods=['GET', 'POST'])
def register():
    form = RegisterForm(request.form)
    if request.method == 'POST' and form.validate():
        name = form.name.data
        email = form.email.data
        username = form.username.data
        password = sha256_crypt.encrypt(str(form.password.data))

        # Create cursor
        cur = mysql.connection.cursor()

        # Execute query
        cur.execute("INSERT INTO users(name, email, username, password) VALUES(%s, %s, %s, %s)", (name, email, username, password))

        # Commit to DB
        mysql.connection.commit()

        # Close connection
        cur.close()

        flash('You are now registered and can log in', 'success')

        return redirect(url_for('login'))
    return render_template('register.html', form=form)


# User login
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        # Get Form Fields
        username = request.form['username']
        password_candidate = request.form['password']

        # Create cursor
        cur = mysql.connection.cursor()

        # Get user by username
        result = cur.execute("SELECT * FROM users WHERE username = %s", [username])

        if result > 0:
            # Get stored hash
            data = cur.fetchone()
            password = data['password']

            # Compare Passwords
            if sha256_crypt.verify(password_candidate, password):
                # Passed
                session['logged_in'] = True
                session['username'] = username

                flash('You are now logged in', 'success')
                return redirect(url_for('dashboard'))
            else:
                error = 'Invalid login'
                return render_template('login.html', error=error)
            # Close connection
            cur.close()
        else:
            error = 'Username not found'
            return render_template('login.html', error=error)

    return render_template('login.html')

# Check if user logged in
def is_logged_in(f):
    @wraps(f)
    def wrap(*args, **kwargs):
        if 'logged_in' in session:
            return f(*args, **kwargs)
        else:
            flash('Unauthorized, Please login', 'danger')
            return redirect(url_for('login'))
    return wrap

# Logout
@app.route('/logout')
@is_logged_in
def logout():
    session.clear()
    flash('You are now logged out', 'success')
    return redirect(url_for('login'))


if __name__ == "__main__":
    app.run()
    socketio.run()

