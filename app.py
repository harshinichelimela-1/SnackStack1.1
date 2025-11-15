# app.py
from flask import Flask, render_template, request, redirect, url_for, session, flash
import mysql.connector
from decimal import Decimal
import random, string

app = Flask(__name__)
app.secret_key = "snackstack_secret_key_v1"

DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "root",
    "database": "food_order"
}

def get_db():
    return mysql.connector.connect(**DB_CONFIG)

# helpers
def random_str(n=8):
    return ''.join(random.choices(string.ascii_letters + string.digits, k=n))

# HOME
@app.route('/')
def home():
    return render_template('home.html')
# USER LOGIN
@app.route('/login_user', methods=['GET','POST'])
def login_user():
    if request.method == 'POST':
        email = request.form.get('email').strip()      # remove extra spaces
        password = request.form.get('password').strip()
        
        db = get_db()
        cur = db.cursor(dictionary=True)
        
        # Check plain-text match in users table
        cur.execute("SELECT user_id, name FROM users WHERE email=%s AND password=%s", (email, password))
        user = cur.fetchone()
        
        cur.close()
        db.close()
        
        if user:
            session.clear()
            session['user_id'] = user['user_id']
            session['user_name'] = user['name']
            session.setdefault('cart', [])   # list of dicts {item_id, name, price, qty}
            return redirect(url_for('user_home'))
        
        flash('Invalid email or password','danger')
    
    return render_template('login_user.html')


# EMPLOYEE LOGIN
# EMPLOYEE LOGIN
@app.route('/login_employee', methods=['GET','POST'])
def login_employee():
    if request.method == 'POST':
        username = request.form.get('username').strip()
        password = request.form.get('password').strip()
        
        db = get_db()
        cur = db.cursor(dictionary=True)
        
        # Make sure your employees table has 'username' column
        cur.execute("SELECT emp_id FROM employees WHERE username=%s AND password=%s", (username, password))
        emp = cur.fetchone()
        
        cur.close()
        db.close()
        
        if emp:
            session.clear()
            session['emp'] = emp['emp_id']
            return redirect(url_for('employee_home'))
        
        flash('Invalid employee credentials','danger')
    
    return render_template('login_employee.html')


# LOGOUT
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('home'))

# USER HOME
@app.route('/user')
def user_home():
    if 'user_id' not in session:
        return redirect(url_for('login_user'))
    return render_template('user_home.html', name=session.get('user_name'))

# SHOW RESTAURANTS (public)
@app.route('/restaurants')
def show_restaurants():
    db = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute("SELECT * FROM restaurants ORDER BY created_at DESC")
    rs = cur.fetchall()
    cur.close(); db.close()
    return render_template('restaurants_public.html', restaurants=rs)

# SHOW MENU for a restaurant
@app.route('/menu/<int:rid>')
def show_menu(rid):
    if 'user_id' not in session:
        return redirect(url_for('login_user'))
    db = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute("SELECT * FROM menu_items WHERE restaurant_id=%s AND (available=1)", (rid,))
    items = cur.fetchall()
    cur.execute("SELECT name FROM restaurants WHERE restaurant_id=%s", (rid,))
    r = cur.fetchone()
    cur.close(); db.close()
    return render_template('menu_user.html', items=items, restaurant=r)

# CART (session-based simple)
@app.route('/cart/add/<int:item_id>')
def cart_add(item_id):
    if 'user_id' not in session:
        return redirect(url_for('login_user'))
    db = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute("SELECT item_id, name, price FROM menu_items WHERE item_id=%s AND (available=1)", (item_id,))
    it = cur.fetchone()
    cur.close(); db.close()
    if not it:
        flash('Item not available','warning')
        return redirect(url_for('show_restaurants'))
    cart = session.get('cart', [])
    for c in cart:
        if c['item_id'] == it['item_id']:
            c['qty'] += 1
            session.modified = True
            break
    else:
        cart.append({'item_id': it['item_id'], 'name': it['name'], 'price': float(it['price']), 'qty': 1})
        session['cart'] = cart
    flash(f"Added {it['name']} to cart",'success')
    return redirect(url_for('view_cart'))

@app.route('/cart')
def view_cart():
    if 'user_id' not in session:
        return redirect(url_for('login_user'))
    cart = session.get('cart', [])
    total = sum(Decimal(str(x['price'])) * x['qty'] for x in cart)
    return render_template('cart.html', cart=cart, total=total)

@app.route('/cart/delete/<int:item_id>')
def cart_delete(item_id):
    if 'user_id' not in session:
        return redirect(url_for('login_user'))
    cart = session.get('cart', [])
    cart = [c for c in cart if c['item_id'] != item_id]
    session['cart'] = cart
    session.modified = True
    flash('Item removed from cart','info')
    return redirect(url_for('view_cart'))

# PROCEED: create order, order_items, payment, assign staff
@app.route('/cart/proceed', methods=['POST'])
def cart_proceed():
    if 'user_id' not in session:
        return redirect(url_for('login_user'))
    cart = session.get('cart', [])
    if not cart:
        flash('Cart is empty','warning')
        return redirect(url_for('view_cart'))
    user_id = session['user_id']
    total = sum(Decimal(str(x['price'])) * x['qty'] for x in cart)
    db = get_db()
    cur = db.cursor()
    try:
        cur.execute("INSERT INTO orders (user_id, total_amount, status) VALUES (%s, %s, %s)",
                    (user_id, float(total), 'Placed'))
        order_id = cur.lastrowid
        for it in cart:
            cur.execute("INSERT INTO order_items (order_id, item_id, quantity, price) VALUES (%s,%s,%s,%s)",
                        (order_id, it['item_id'], it['qty'], float(it['price'])))
        cur.execute("INSERT INTO payments (order_id, amount, method, status) VALUES (%s,%s,%s,%s)",
                    (order_id, float(total), request.form.get('payment_method','Cash'), 'Completed'))
        cur.execute("SELECT staff_id FROM delivery_staff WHERE status='available' LIMIT 1")
        staff = cur.fetchone()
        if staff:
            staff_id = staff[0]
            cur.execute("UPDATE orders SET staff_id=%s WHERE order_id=%s", (staff_id, order_id))
            cur.execute("UPDATE delivery_staff SET status='busy' WHERE staff_id=%s", (staff_id,))
        db.commit()
    except Exception as e:
        db.rollback()
        cur.close(); db.close()
        flash(f'Failed to place order: {e}','danger')
        return redirect(url_for('view_cart'))
    cur.close(); db.close()
    session.pop('cart', None)
    flash('Order placed successfully!','success')
    return render_template('order_success.html', order_id=order_id, total=total)

# EMPLOYEE PAGES (protected)
@app.route('/employee')
def employee_home():
    if 'emp' not in session:
        return redirect(url_for('login_employee'))
    return render_template('employee_home.html', emp=session.get('emp'))

# DELIVERY STAFF CRUD
@app.route('/employee/delivery_staff')
def employee_delivery_staff():
    if 'emp' not in session:
        return redirect(url_for('login_employee'))
    db = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute("SELECT * FROM delivery_staff ORDER BY created_at DESC")
    staff = cur.fetchall()
    cur.close(); db.close()
    return render_template('delivery_staff_emp.html', staff=staff)

@app.route('/employee/delivery_staff/add', methods=['GET','POST'])
def employee_delivery_staff_add():
    if 'emp' not in session:
        return redirect(url_for('login_employee'))
    if request.method == 'POST':
        name = request.form['name']
        phone = request.form.get('phone_no')
        vehicle = request.form.get('vehicle_type')
        loc = request.form.get('current_loc')
        db = get_db(); cur = db.cursor()
        cur.execute("INSERT INTO delivery_staff (name, phone_no, vehicle_type, current_loc, status) VALUES (%s,%s,%s,%s,%s)",
                    (name, phone, vehicle, loc, 'available'))
        db.commit(); cur.close(); db.close()
        flash('Delivery staff added','success')
        return redirect(url_for('employee_delivery_staff'))
    return render_template('add_delivery_staff.html')

@app.route('/employee/delivery_staff/edit/<int:staff_id>', methods=['GET','POST'])
def employee_delivery_staff_edit(staff_id):
    if 'emp' not in session:
        return redirect(url_for('login_employee'))
    db = get_db(); cur = db.cursor(dictionary=True)
    if request.method == 'POST':
        name = request.form['name']; phone = request.form.get('phone_no')
        vehicle = request.form.get('vehicle_type'); loc = request.form.get('current_loc'); status = request.form.get('status')
        upd = db.cursor()
        upd.execute("UPDATE delivery_staff SET name=%s, phone_no=%s, vehicle_type=%s, current_loc=%s, status=%s WHERE staff_id=%s",
                    (name, phone, vehicle, loc, status, staff_id))
        db.commit(); upd.close(); cur.close(); db.close()
        flash('Delivery staff updated','success')
        return redirect(url_for('employee_delivery_staff'))
    cur.execute("SELECT * FROM delivery_staff WHERE staff_id=%s", (staff_id,))
    st = cur.fetchone()
    cur.close(); db.close()
    if not st:
        flash('Staff not found','danger')
        return redirect(url_for('employee_delivery_staff'))
    return render_template('edit_delivery_staff.html', staff=st)

@app.route('/employee/delivery_staff/delete/<int:staff_id>')
def employee_delivery_staff_delete(staff_id):
    if 'emp' not in session:
        return redirect(url_for('login_employee'))
    db = get_db(); cur = db.cursor()
    cur.execute("DELETE FROM delivery_staff WHERE staff_id=%s", (staff_id,))
    db.commit(); cur.close(); db.close()
    flash('Delivery staff deleted','info')
    return redirect(url_for('employee_delivery_staff'))

# RESTAURANTS CRUD
@app.route('/employee/restaurants')
def employee_restaurants():
    if 'emp' not in session:
        return redirect(url_for('login_employee'))
    db = get_db(); cur = db.cursor(dictionary=True)
    cur.execute("SELECT * FROM restaurants ORDER BY created_at DESC")
    rows = cur.fetchall(); cur.close(); db.close()
    return render_template('restaurants_emp.html', restaurants=rows)

@app.route('/employee/restaurants/add', methods=['GET','POST'])
def employee_restaurants_add():
    if 'emp' not in session:
        return redirect(url_for('login_employee'))
    if request.method == 'POST':
        name = request.form['name']; owner = request.form.get('owner_name')
        email = request.form.get('email'); phone = request.form.get('phone_no')
        address = request.form.get('address'); cuisine = request.form.get('cuisine_type')
        db = get_db(); cur = db.cursor()
        cur.execute("INSERT INTO restaurants (name, owner_name, email, phone_no, address, cuisine_type) VALUES (%s,%s,%s,%s,%s,%s)",
                    (name, owner, email, phone, address, cuisine))
        db.commit(); cur.close(); db.close()
        flash('Restaurant added','success')
        return redirect(url_for('employee_restaurants'))
    return render_template('add_restaurant.html')

@app.route('/employee/restaurants/edit/<int:rid>', methods=['GET','POST'])
def employee_restaurants_edit(rid):
    if 'emp' not in session:
        return redirect(url_for('login_employee'))
    db = get_db(); cur = db.cursor(dictionary=True)
    if request.method == 'POST':
        name = request.form['name']; owner = request.form.get('owner_name'); email = request.form.get('email')
        phone = request.form.get('phone_no'); address = request.form.get('address'); cuisine = request.form.get('cuisine_type')
        upd = db.cursor(); upd.execute("UPDATE restaurants SET name=%s, owner_name=%s, email=%s, phone_no=%s, address=%s, cuisine_type=%s WHERE restaurant_id=%s",
                                      (name, owner, email, phone, address, cuisine, rid))
        db.commit(); upd.close(); cur.close(); db.close()
        flash('Restaurant updated','success')
        return redirect(url_for('employee_restaurants'))
    cur.execute("SELECT * FROM restaurants WHERE restaurant_id=%s", (rid,))
    r = cur.fetchone(); cur.close(); db.close()
    if not r:
        flash('Restaurant not found','danger')
        return redirect(url_for('employee_restaurants'))
    return render_template('edit_restaurant.html', r=r)

@app.route('/employee/restaurants/delete/<int:rid>')
def employee_restaurants_delete(rid):
    if 'emp' not in session:
        return redirect(url_for('login_employee'))
    db = get_db(); cur = db.cursor()
    cur.execute("DELETE FROM restaurants WHERE restaurant_id=%s", (rid,))
    db.commit(); cur.close(); db.close()
    flash('Restaurant deleted','info')
    return redirect(url_for('employee_restaurants'))

# USERS LIST + DELETE
@app.route('/employee/users')
def employee_users():
    if 'emp' not in session:
        return redirect(url_for('login_employee'))
    db = get_db(); cur = db.cursor(dictionary=True)
    cur.execute("SELECT * FROM users ORDER BY created_at DESC")
    users = cur.fetchall(); cur.close(); db.close()
    return render_template('users_emp.html', users=users)

@app.route('/employee/users/delete/<int:uid>')
def employee_users_delete(uid):
    if 'emp' not in session:
        return redirect(url_for('login_employee'))
    db = get_db(); cur = db.cursor()
    cur.execute("DELETE FROM users WHERE user_id=%s", (uid,))
    db.commit(); cur.close(); db.close()
    flash('User deleted','info')
    return redirect(url_for('employee_users'))

# ORDERS (employee view)
@app.route('/employee/orders')
def employee_orders():
    if 'emp' not in session:
        return redirect(url_for('login_employee'))
    db = get_db(); cur = db.cursor(dictionary=True)
    cur.execute("""
        SELECT o.order_id, o.user_id, o.total_amount, o.status, o.created_at, o.staff_id, p.amount AS payment_amount
        FROM orders o
        LEFT JOIN payments p ON o.order_id = p.order_id
        ORDER BY o.created_at DESC
    """)
    orders = cur.fetchall(); cur.close(); db.close()
    return render_template('orders_emp.html', orders=orders)

if __name__ == '__main__':
    app.run(debug=True)

