from flask import Flask, render_template, request, redirect, session
import sqlite3
import os
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = "flora_frame_secret_key"

# ================= DATABASE CONNECTION =================
def get_db_connection():
    conn = sqlite3.connect("flora.db")
    conn.row_factory = sqlite3.Row
    return conn


# ================= USER SIDE =================

@app.route('/')
def home():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT id, name, price, image FROM plants")
    plants = cursor.fetchall()

    conn.close()
    return render_template('index.html', plants=plants)


@app.route('/plants')
def plants():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, category, price FROM plants")
    data = cursor.fetchall()
    conn.close()
    return render_template('plants.html', plants=data)


@app.route('/plants/<category>')
def plants_by_category(category):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, name, price, image FROM plants WHERE LOWER(category)=LOWER(?)",
        (category,)
    )
    data = cursor.fetchall()
    conn.close()
    return render_template('plants.html', plants=data)


@app.route('/plant/<int:plant_id>')
def plant_detail(plant_id):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, name, category, price, image, description
        FROM plants
        WHERE id = ?
    """, (plant_id,))

    plant = cursor.fetchone()

    if not plant:
        return "Plant not found", 404

    cursor.execute("""
        SELECT user_name, rating, review_text
        FROM reviews
        WHERE plant_name = ?
    """, (plant["name"],))
    reviews = cursor.fetchall()

    cursor.execute("""
        SELECT AVG(rating), COUNT(*)
        FROM reviews
        WHERE plant_name = ?
    """, (plant["name"],))
    avg_data = cursor.fetchone()

    average_rating = round(avg_data[0], 1) if avg_data[0] else 0
    total_reviews = avg_data[1]

    conn.close()

    return render_template(
        'plant_detail.html',
        plant=plant,
        reviews=reviews,
        average_rating=average_rating,
        total_reviews=total_reviews
    )


@app.route('/add_review/<int:plant_id>', methods=['POST'])
def add_review(plant_id):
    if 'user_id' not in session:
        return redirect('/login')
    
    rating = request.form['rating']
    review_text = request.form['review_text']

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT name FROM plants WHERE id = ?", (plant_id,))
    plant = cursor.fetchone()

    if not plant:
        return "Plant not found", 404

    cursor.execute("""
        INSERT INTO reviews (plant_name, user_name, rating, review_text)
        VALUES (?, ?, ?, ?)
    """, (plant["name"], session.get('user_name'), rating, review_text))
    conn.commit()
    conn.close()
    return redirect(f'/plant/{plant_id}')


# ================= SEARCH =================

@app.route('/search')
def search():
    query = request.args.get('q', '').strip()

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, name, price, image
        FROM plants
        WHERE name LIKE ? OR category LIKE ? OR description LIKE ?
    """, (f"%{query}%", f"%{query}%", f"%{query}%"))

    results = cursor.fetchall()
    conn.close()

    return render_template('plants.html', plants=results, search_query=query)


@app.route('/search-suggestions')
def search_suggestions():
    q = request.args.get('q', '').strip()

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT DISTINCT name
        FROM plants
        WHERE name LIKE ? OR category LIKE ? OR description LIKE ?
        LIMIT 6
    """, (f"%{q}%", f"%{q}%", f"%{q}%"))

    suggestions = [row["name"] for row in cursor.fetchall()]
    conn.close()
    return {"suggestions": suggestions}


# ================= AUTH =================

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO users (name, email, password) VALUES (?, ?, ?)",
            (request.form['name'], request.form['email'], request.form['password'])
        )
        conn.commit()
        conn.close()
        return redirect('/login')
    
    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, name FROM users WHERE email=? AND password=?",
            (request.form['email'], request.form['password'])
        )
        user = cursor.fetchone()

        conn.close()

        if user:
            session['user_id'] = user["id"]
            session['user_name'] = user["name"]
            session.setdefault('cart', [])
            return redirect('/')
        return "Invalid Login Credentials"
    
    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')


# ================= CART =================

@app.route('/add_to_cart/<int:plant_id>')
def add_to_cart(plant_id):
    if 'user_id' not in session:
        return redirect('/login')
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, price FROM plants WHERE id=?", (plant_id,))
    plant = cursor.fetchone()
    conn.close()

    if plant:
        cart = session.setdefault('cart', [])
        for item in cart:
            if item['id'] == plant["id"]:
                item['quantity'] += 1
                session.modified = True
                return redirect('/cart')
            
        cart.append({
            'id': plant["id"],
            'name': plant["name"],
            'price': float(plant["price"]),
            'quantity': 1
        })
        session.modified = True

    return redirect('/cart')


@app.route('/increase_quantity/<int:index>')
def increase_quantity(index):
    if 'user_id' not in session:
        return redirect('/login')
    cart = session.get('cart', [])
    if 0 <= index < len(cart):
        cart[index]['quantity'] += 1
        session.modified = True
    return redirect('/cart')

@app.route('/decrease_quantity/<int:index>')
def decrease_quantity(index):
    if 'user_id' not in session:
        return redirect('/login')
    cart = session.get('cart', [])
    if 0 <= index < len(cart):
        cart[index]['quantity'] -= 1
        if cart[index]['quantity'] <= 0:
            cart.pop(index)
        session.modified = True
    return redirect('/cart')

@app.route('/remove_from_cart/<int:index>')
def remove_from_cart(index):
    if 'user_id' not in session:
        return redirect('/login')
    cart = session.get('cart', [])
    if 0 <= index < len(cart):
        cart.pop(index)
        session.modified = True
    return redirect('/cart')

@app.route('/cart')
def cart():
    if 'user_id' not in session:
        return redirect('/login')
    
    cart_items = session.get('cart', [])
    total = sum(item['price'] * item['quantity'] for item in cart_items)
    return render_template('cart.html', cart=cart_items, total=total)


# ================= CHECKOUT =================

@app.route('/checkout', methods=['GET', 'POST'])
def checkout():
    if 'user_id' not in session:
        return redirect('/login'
                        )
    cart = session.get('cart', [])
    if not cart:
        return redirect('/cart')
    
    total = sum(item['price'] * item['quantity'] for item in cart)

    if request.method == 'POST':
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO orders (user_id, customer_name, address, phone, total_amount)
            VALUES (?, ?, ?, ?, ?)
        """, (
            session['user_id'],
            request.form['name'],
            request.form['address'],
            request.form['phone'],
            total
        ))

        order_id = cursor.lastrowid

        for item in cart:
            cursor.execute("""
                INSERT INTO order_items (order_id, plant_id, quantity, price)
                VALUES (?, ?, ?, ?)
            """, (order_id, item['id'], item['quantity'], item['price']))
        conn.commit()
        conn.close()
        session['cart'] = []
        return redirect('/order_success')
    
    return render_template('checkout.html', total=total)


@app.route('/order_success')
def order_success():
    return render_template('order_success.html')


# ================= STATIC =================

@app.route('/about')
def about():
    return render_template('about.html')


@app.route('/tips')
def tips():
    return render_template('tips.html')

# ================= ADMIN SIDE =================
@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id FROM admin WHERE username=? AND password=?",
            (username, password)
        )
        admin = cursor.fetchone()
        conn.close()
        if admin:
            session['admin'] = True
            return redirect('/admin/dashboard')
        else:
            return "Invalid Admin Credentials"
    return render_template('admin/admin_login.html')

@app.route('/admin/dashboard')
def admin_dashboard():
    if 'admin' not in session:
        return redirect('/admin/login')
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, category, price FROM plants")
    plants = cursor.fetchall()
    conn.close()
    return render_template('admin/admin_dashboard.html', plants=plants)

@app.route('/admin/add-plant', methods=['GET', 'POST'])
def admin_add_plant():
    if 'admin' not in session:
        return redirect('/admin/login')
    if request.method == 'POST':
        name = request.form['name']
        category = request.form['category']
        price = request.form['price']
        description = request.form['description']
        image_file = request.files.get('image')
        image_filename = None
        if image_file and image_file.filename != '':
            image_filename = secure_filename(image_file.filename)
            upload_folder = 'static/uploads'
            os.makedirs(upload_folder, exist_ok=True)
            image_file.save(os.path.join(upload_folder, image_filename))
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO plants (name, category, price, image, description)
            VALUES (?, ?, ?, ?, ?)
        """, (name, category, price, image_filename, description))
        conn.commit()
        conn.close()
        return redirect('/admin/dashboard')
    return render_template('admin/add_plant.html')

@app.route('/admin/edit/<int:id>', methods=['GET', 'POST'])
def admin_edit(id):
    if 'admin' not in session:
        return redirect('/admin/login')
    conn = get_db_connection()
    cursor = conn.cursor()
    if request.method == 'POST':
        name = request.form['name']
        category = request.form['category']
        price = request.form['price']
        description = request.form['description']
        image_file = request.files.get('image')
        if image_file and image_file.filename != '':
            image_filename = secure_filename(image_file.filename)
            upload_folder = 'static/uploads'
            os.makedirs(upload_folder, exist_ok=True)
            image_file.save(os.path.join(upload_folder, image_filename))
            cursor.execute("""
                UPDATE plants
                SET name=?, category=?, price=?, image=?, description=?
                WHERE id=?
            """, (name, category, price, image_filename, description, id))
        else:
            cursor.execute("""
                UPDATE plants
                SET name=?, category=?, price=?, description=?
                WHERE id=?
            """, (name, category, price, description, id))
        conn.commit()
        conn.close()
        return redirect('/admin/dashboard')
    cursor.execute("SELECT name, category, price, image, description FROM plants WHERE id=?", (id,))
    plant = cursor.fetchone()
    conn.close()
    return render_template('admin/admin_edit.html', plant=plant)

@app.route('/admin/delete/<int:id>')
def admin_delete(id):
    if 'admin' not in session:
        return redirect('/admin/login')
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM plants WHERE id=?", (id,))
    conn.commit()
    conn.close()
    return redirect('/admin/dashboard')

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin', None)
    return redirect('/admin/login')

# ================= RUN =================

if __name__ == "__main__":
    
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
