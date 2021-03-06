import os
import logging
from flask.ext.mysql import MySQL
from flask import Flask, render_template, json, jsonify, request
from flask import session, redirect
from werkzeug import generate_password_hash, check_password_hash

import pickle
import requests

app = Flask(__name__)

template_dir = os.path.join(os.path.dirname(__file__), 'templates')

app.secret_key = 'why would I tell you my secret key?'

mysql = MySQL()
app.config['MYSQL_DATABASE_USER'] = 'root'
app.config['MYSQL_DATABASE_PASSWORD'] = 'derp123'
app.config['MYSQL_DATABASE_DB'] = 'shit'
app.config['MYSQL_DATABASE_HOST'] = '127.0.0.1'
mysql.init_app(app)

conn = mysql.connect()
cursor = conn.cursor()

def get_user_id():
    email = pickle.loads(session['u2']).email
    query = "SELECT id FROM User where email = '%s'" % email
    cursor.execute(query)
    return cursor.fetchone()[0]

def format_currency(value):
    return "${:,.2f}".format(value)

class User(object):
    email = ""
    first_name = ""
    last_name = ""

    def __init__(self,email,first_name,last_name):
        self.email = email
        self.first_name = first_name
        self.last_name = last_name

    def get_email(self):
        """Return the email address"""
        return self.email

    def get_first_name(self):
        """Return the first name"""
        return self.first_name

    def get_last_name(self):
        """Return the last name"""
        return self.last_name

class Ticker(object):
    def __init__(self,name,quantityShares):
        self.name = name
        self.quantityShares = quantityShares 

portfolio = {}

def addUser(firstname,lastname,email,password):
    _hashed_password = generate_password_hash(password)
    cursor.callproc('sp_createUser',(firstname,lastname,email,_hashed_password))

    data = cursor.fetchall()
 
    if len(data) is 0:
        conn.commit()
        return jsonify({'message':'User created successfully !'})
    else:
        return jsonify({'error':str(data[0])})

def signInUser(logInEmail,logInPassword):    
    s = cursor.User.query.filter_by(logInEmail = email).first()
    if check_password_hash(s.password,logInPassword):
        return jsonify({'html':'<span>Log In Successful!</span>'})
    else:
        return jsonify({'html':'<span>Log In Failed...</span>'})


@app.route('/submitShares', methods=['POST'])
def submitShares():
    ticker = request.form['ticker']
    quantity = request.form['quantity']
    email = pickle.loads(session['u2']).email

    query = "SELECT id FROM User where email = '%s'" % email
    cursor.execute(query)
    user = cursor.fetchone()[0]

    cursor.execute("SELECT portfolio_id FROM Portfolio WHERE user_id = %i" % user)
    userPortfolio = cursor.fetchone()[0]    
    portfolio[ticker] = Ticker(ticker,quantity)

    cursor.execute("select tickers from Portfolio where user_id = %i" % get_user_id())
    port=pickle.loads(cursor.fetchone()[0])
    portfolio.update(port)
    query = 'UPDATE Portfolio SET tickers="%s" WHERE portfolio_id = %i' % (pickle.dumps(portfolio), userPortfolio) 
    cursor.execute(query)
    conn.commit()

    return redirect('/dashboard')


@app.route('/')
def home():
    if session.get('user'):
        return redirect('/userHome')
    else:
        return render_template('%s.html' % 'index')   

@app.route('/dashboard')
def dashboard():
    if session.get('user'):
        cursor.execute("select tickers from Portfolio where user_id = %i" % get_user_id())
        port=pickle.loads(cursor.fetchone()[0]).values()
        total_price = sum([int(stock.quantityShares) * float(requests.get('http://finance.yahoo.com/d/quotes.csv', params={'s':stock.name, 'f':'a'}).content[:-1]) for stock in port])
        percents = {stock.name: float(int(stock.quantityShares) * float(requests.get('http://finance.yahoo.com/d/quotes.csv', params={'s':stock.name, 'f':'a'}).content[:-1])) / total_price for stock in port}

        positions = '|'.join(['%s~%f' % (k,v) for k,v in percents.iteritems()])

        positionsArray = []
        for k, v in percents.iteritems():
            positionsArray.append([str(k), str(v)])

        data = requests.get("https://test3.blackrock.com/tools/hackathon/portfolio-analysis", params={'positions': positions, 'calculateRisk': True, 'calculateExposures':True, 'startDate':'20160715'})
        total_risk = data.json()['resultMap'][u'PORTFOLIOS'][0][u'portfolios'][0]['riskData']['totalRisk']

        return render_template('dashboard/production/index2.html', portfolios=port, total_risk=round(total_risk, 2), total_price=format_currency(total_price),
                                total_return=format_currency(total_price*1.11), positions= positions, percents=positionsArray, username=pickle.loads(session['u2']).first_name)
    else:
        return redirect('/login')

@app.route('/stocklookup', methods=('GET',))
def stockLookUp():
    if session.get('user'):
        return render_template('%s.html' % 'dashboard/production/stockLookup')
    else:
        return render_template('error.html',error = 'Unauthorized Access')        

@app.route('/about')
def about():
    return render_template('%s.html' % 'about')

@app.route('/viewSignUp')
def viewSignUp():
    return render_template('%s.html' % 'signup')  

@app.route('/signUp', methods=['GET','POST'])
def signUp():
    _firstname = request.form['firstname']
    _lastname = request.form['lastname']
    _email = request.form['email']
    _password = request.form['password']
    _confirmpassword = request.form['password_confirm']
    if _password != _confirmpassword:
        return jsonify({'html':'<span>Password Confirmation Does Not Match!!</span>'})
    elif _firstname and _lastname and _email and _password:
        addUser(_firstname,_lastname, _email, _password)
        return jsonify({'html':'<span>All fields good !!</span>'})
    else:
        return jsonify({'html':'<span>Enter the required fields</span>'})

@app.route('/login')
def login():
    return render_template('%s.html' % 'login') 

@app.route('/userHome')
def userHome():
    userinfo = pickle.loads(session['u2'])

    if session.get('user'):
        logging.info(userinfo.get_first_name())
        return render_template('userHome.html', data= userinfo.get_first_name())
    else:
        return render_template('error.html',error = 'Unauthorized Access')

@app.route('/validateLogin',methods=['POST'])
def validateLogin():
    try:
        _username = request.form['inputEmail']
        _password = request.form['inputPassword']
 
        # connect to mysql 
        cursor.callproc('sp_validateLogin',(_username,))
        data = cursor.fetchall()

        if len(data) > 0:
            if check_password_hash(str(data[0][4]),_password):
                userinfo = User(data[0][3], data[0][1], data[0][2])
                session['u2'] = pickle.dumps(userinfo)
                logging.info(userinfo.get_first_name())
                session['user'] = data[0][0]
                return redirect('/userHome')
            else:
                return render_template('error.html',error = 'Wrong Email address or Password.')
        else:
            return render_template('error.html',error = 'Wrong Email address or Password.')
 
    except Exception as e:
        return render_template('error.html',error = str(e))

@app.route('/delete/<name>')
def delete(name):
    name = name.upper()
    email = pickle.loads(session['u2']).email

    query = "SELECT id FROM User where email = '%s'" % email
    cursor.execute(query)
    user = cursor.fetchone()[0]

    cursor.execute("SELECT portfolio_id FROM Portfolio WHERE user_id = %i" % user)
    userPortfolio = cursor.fetchone()[0]    

    cursor.execute("select tickers from Portfolio where user_id = %i" % get_user_id())
    port=pickle.loads(cursor.fetchone()[0])
    portfolio.update(port)
    del portfolio[name]

    query = 'UPDATE Portfolio SET tickers="%s" WHERE portfolio_id = %i' % (pickle.dumps(portfolio), userPortfolio) 
    cursor.execute(query)
    conn.commit()

    return redirect('/dashboard')

@app.route('/logout')
def logout():
    session.pop('user',None)
    return redirect('/')

if __name__ == '__main__':
    app.run(debug=True)
