
from flask import Flask, render_template, request, redirect, url_for, session, flash
import mysql.connector
from decimal import Decimal

app = Flask(__name__)
app.secret_key = "replace-with-a-strong-secret"

DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': 'root',      # change to your MySQL password
    'database': 'food_order'
}


def get_db():
    return mysql.connector.connect(**DB_CONFIG)

# Home / role selection
@app.route('/')
def home():
    return render_template('index.html')

@app.route('/choose_role', methods=['POST'])
def choose_role():
    role = request.form.get('role')
    if role not in ('user', 'employee'):
        flash('Invalid role', 'danger')
        return redirect(url_for('home'))
    session['role'] = role
    if role == 'user':
        session.setdefault('cart', [])
        return redirect(url_for('user_home'))
    return redirect(url_for('employee_home'))

# USER
@app.route('/user')
def user_home():
    return render_template('user_home.html')

@app.route('/restaurants')
def show_restaurants():
    db = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute('SELECT * FROM restaurants ORDER BY created_at DESC')
    data = cur.fetchall()
    cur.close(); db.close()
    return render_template('restaurants_user.html', restaurants=data)

@app.route('/menu_items/<int:restaurant_id>')
def show_menu_items(restaurant_id):
    db = get_db(); cur = db.cursor(dictionary=True)
    cur.execute('SELECT * FROM menu_items WHERE restaurant_id=%s AND (available=1 OR available IS NULL)', (restaurant_id,))
    items = cur.fetchall(); cur.close(); db.close()
    return render_template('menu_items_user.html', items=items, restaurant_id=restaurant_id)

@app.route('/add_to_cart/<int:item_id>')
def add_to_cart(item_id):
    if session.get('role') != 'user':
        flash('Only users may add to cart', 'warning'); return redirect(url_for('home'))
    db = get_db(); cur = db.cursor(dictionary=True)
    cur.execute('SELECT item_id, name, price, restaurant_id FROM menu_items WHERE item_id=%s', (item_id,))
    item = cur.fetchone(); cur.close(); db.close()
    if not item: flash('Item not found','danger'); return redirect(url_for('show_restaurants'))
    cart = session.get('cart', [])
    for c in cart:
        if c['item_id'] == item['item_id']:
            c['quantity'] += 1; session.modified = True; break
    else:
        cart.append({'item_id': item['item_id'], 'name': item['name'], 'price': float(item['price']), 'quantity': 1, 'restaurant_id': item['restaurant_id']})
        session['cart'] = cart
    flash(f"Added {item['name']} to cart", 'success')
    return redirect(url_for('view_cart'))

@app.route('/cart')
def view_cart():
    if session.get('role') != 'user': return redirect(url_for('home'))
    cart = session.get('cart', [])
    total = sum(Decimal(str(it['price'])) * it['quantity'] for it in cart)
    return render_template('cart.html', cart=cart, total=total)

@app.route('/delete_from_cart/<int:item_id>')
def delete_from_cart(item_id):
    if session.get('role') != 'user': return redirect(url_for('home'))
    cart = session.get('cart', [])
    cart = [i for i in cart if i['item_id'] != item_id]
    session['cart'] = cart; session.modified = True
    flash('Item removed from cart','info')
    return redirect(url_for('view_cart'))

@app.route('/proceed', methods=['POST'])
def proceed_order():
    if session.get('role') != 'user': return redirect(url_for('home'))
    cart = session.get('cart', [])
    if not cart: flash('Cart empty','warning'); return redirect(url_for('view_cart'))

    user_id = request.form.get('user_id') or None
    delivery_address = request.form.get('delivery_address') or 'Not provided'
    payment_method = request.form.get('payment_method') or 'Cash'

    total = sum(Decimal(str(it['price'])) * it['quantity'] for it in cart)

    db = get_db(); cur = db.cursor()
    cur.execute('INSERT INTO payments (order_id, payment_status, payment_method, amount) VALUES (%s,%s,%s,%s)', (None, 'Completed', payment_method, float(total)))
    payment_id = cur.lastrowid

    # For orders table we keep a representative item_id & restaurant_id (first item) for compatibility
    first_restaurant = cart[0].get('restaurant_id') if cart else None
    first_item = cart[0]['item_id'] if cart else None

    cur.execute('INSERT INTO orders (user_id, restaurant_id, item_id, total_amount, delivery_address, order_status, payment_id) VALUES (%s,%s,%s,%s,%s,%s,%s)',
                (user_id, first_restaurant, first_item, float(total), delivery_address, 'Pending', payment_id))
    order_id = cur.lastrowid

    cur.execute('UPDATE payments SET order_id=%s WHERE payment_id=%s', (order_id, payment_id))

    for it in cart:
        cur.execute('INSERT INTO order_items (order_id, item_id, quantity, price) VALUES (%s,%s,%s,%s)', (order_id, it['item_id'], it['quantity'], float(it['price'])))

    db.commit(); cur.close(); db.close()

    session.pop('cart', None)
    flash('Order placed successfully!', 'success')
    return render_template('order_success.html', order_id=order_id, total=total)

# EMPLOYEE
@app.route('/employee')
def employee_home():
    if session.get('role') != 'employee': return render_template('employee_login.html')
    return render_template('employee_home.html')

@app.route('/manage_restaurants')
def manage_restaurants():
    if session.get('role') != 'employee': return redirect(url_for('home'))
    db = get_db(); cur = db.cursor(dictionary=True)
    cur.execute('SELECT * FROM restaurants ORDER BY created_at DESC')
    data = cur.fetchall(); cur.close(); db.close()
    return render_template('restaurants_employee.html', restaurants=data)

@app.route('/add_restaurant', methods=['GET','POST'])
def add_restaurant():
    if session.get('role') != 'employee': return redirect(url_for('home'))
    if request.method == 'POST':
        name = request.form['name']; owner = request.form.get('owner_name'); email = request.form.get('email')
        phone = request.form.get('phone_no'); address = request.form.get('address'); cuisine = request.form.get('cuisine_type')
        db = get_db(); cur = db.cursor();
        cur.execute('INSERT INTO restaurants (name, owner_name, email, phone_no, address, cuisine_type) VALUES (%s,%s,%s,%s,%s,%s)', (name, owner, email, phone, address, cuisine))
        db.commit(); cur.close(); db.close(); flash('Restaurant added','success'); return redirect(url_for('manage_restaurants'))
    return render_template('add_restaurant.html')

@app.route('/delete_restaurant/<int:rid>')
def delete_restaurant(rid):
    if session.get('role') != 'employee': return redirect(url_for('home'))
    db = get_db(); cur = db.cursor(); cur.execute('DELETE FROM restaurants WHERE restaurant_id=%s', (rid,)); db.commit(); cur.close(); db.close(); flash('Restaurant deleted','info')
    return redirect(url_for('manage_restaurants'))

@app.route('/delivery_staff')
def delivery_staff_list():
    if session.get('role') != 'employee': return redirect(url_for('home'))
    db = get_db(); cur = db.cursor(dictionary=True); cur.execute('SELECT * FROM delivery_staff ORDER BY created_at DESC'); data = cur.fetchall(); cur.close(); db.close()
    return render_template('delivery_staff_employee.html', staff=data)

@app.route('/add_delivery_staff', methods=['GET','POST'])
def add_delivery_staff():
    if session.get('role') != 'employee': return redirect(url_for('home'))
    if request.method == 'POST':
        name = request.form['name']; phone = request.form.get('phone_no'); vehicle = request.form.get('vehicle_type'); loc = request.form.get('current_loc')
        db = get_db(); cur = db.cursor(); cur.execute('INSERT INTO delivery_staff (name, phone_no, vehicle_type, current_loc) VALUES (%s,%s,%s,%s)', (name, phone, vehicle, loc)); db.commit(); cur.close(); db.close(); flash('Delivery staff added','success')
        return redirect(url_for('delivery_staff_list'))
    return render_template('add_delivery_staff.html')

@app.route('/delete_delivery_staff/<int:did>')
def delete_delivery_staff(did):
    if session.get('role') != 'employee': return redirect(url_for('home'))
    db = get_db(); cur = db.cursor(); cur.execute('DELETE FROM delivery_staff WHERE delivery_id=%s', (did,)); db.commit(); cur.close(); db.close(); flash('Delivery staff deleted','info')
    return redirect(url_for('delivery_staff_list'))

@app.route('/users_list')
def users_list():
    if session.get('role') != 'employee': return redirect(url_for('home'))
    db = get_db(); cur = db.cursor(dictionary=True); cur.execute('SELECT user_id, name, email, phone_no, address, created_at FROM users ORDER BY created_at DESC'); data = cur.fetchall(); cur.close(); db.close()
    return render_template('users_employee.html', users=data)

@app.route('/orders_list')
def orders_list():
    if session.get('role') != 'employee': return redirect(url_for('home'))
    db = get_db(); cur = db.cursor(dictionary=True)
    cur.execute("""
        SELECT o.order_id, o.user_id, o.total_amount, o.order_date, o.order_status, p.payment_status
        FROM orders o
        LEFT JOIN payments p ON o.payment_id = p.payment_id
        ORDER BY o.order_date DESC
    """)
    data = cur.fetchall(); cur.close(); db.close()
    return render_template('orders_employee.html', orders=data)

@app.route('/logout')
def logout():
    session.pop('role', None); session.pop('cart', None); flash('Logged out','info'); return redirect(url_for('home'))

if __name__ == '__main__':
    app.run(debug=True)
