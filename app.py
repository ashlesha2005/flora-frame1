from flask import Flask, render_template, request, redirect, session
import mysql.connector

import os
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = "flora_frame_secret_key"

# ================= DATABASE CONNECTION =================
def get_db_connection():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="root11",
        database="flora_frame"
    )

# ================= USER SIDE =================

@app.route('/')
def home():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Fetch plants dynamically for home page
    cursor.execute("SELECT id, name, price, image FROM plants")
    plants = cursor.fetchall()

    cursor.close()
    conn.close()

    return render_template('index.html', plants=plants)


@app.route('/plants')
def plants():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, category, price FROM plants")
    data = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('plants.html', plants=data)


@app.route('/plants/<category>')
def plants_by_category(category):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, name, price, image FROM plants WHERE LOWER(category)=LOWER(%s)",
        (category,)
    )
    data = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('plants.html', plants=data)

@app.route('/plant/<int:plant_id>')
def plant_detail(plant_id):
    conn = get_db_connection()
    cursor = conn.cursor()

    # Fetch plant details
    cursor.execute("""
        SELECT id, name, category, price, image, description
        FROM plants
        WHERE id = %s
    """, (plant_id,))
    plant = cursor.fetchone()

    if not plant:
        return "Plant not found", 404

    # Fetch reviews for this plant
    cursor.execute("""
        SELECT user_name, rating, review_text
        FROM reviews
        WHERE plant_name = %s
    """, (plant[1],))
    reviews = cursor.fetchall()

    # ⭐ Calculate average rating and total reviews
    cursor.execute("""
        SELECT AVG(rating), COUNT(*)
        FROM reviews
        WHERE plant_name = %s
    """, (plant[1],))
    avg_data = cursor.fetchone()

    average_rating = round(avg_data[0], 1) if avg_data[0] else 0
    total_reviews = avg_data[1]

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

    # Get plant name
    cursor.execute("SELECT name FROM plants WHERE id = %s", (plant_id,))
    plant = cursor.fetchone()

    if not plant:
        return "Plant not found", 404

    plant_name = plant[0]
    user_name = session.get('username')  # must exist in session

    cursor.execute("""
        INSERT INTO reviews (plant_name, user_name, rating, review_text)
        VALUES (%s, %s, %s, %s)
    """, (plant_name, user_name, rating, review_text))

    conn.commit()

    return redirect(f'/plant/{plant_id}')



@app.route('/search')
def search():
    query = request.args.get('q', '').strip()

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, name, price, image
        FROM plants
        WHERE 
            name LIKE %s
            OR category LIKE %s
            OR description LIKE %s
            OR SOUNDEX(name) = SOUNDEX(%s)
    """, (
        f"%{query}%",
        f"%{query}%",
        f"%{query}%",
        query
    ))

    results = cursor.fetchall()
    cursor.close()
    conn.close()

    return render_template(
        'plants.html',
        plants=results,
        search_query=query
    )

@app.route('/search-suggestions')
def search_suggestions():
    q = request.args.get('q', '').strip()

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT DISTINCT name
        FROM plants
        WHERE 
            name LIKE %s
            OR category LIKE %s
            OR description LIKE %s
            OR SOUNDEX(name) = SOUNDEX(%s)
        LIMIT 6
    """, (f"%{q}%", f"%{q}%", f"%{q}%", q))

    suggestions = [row[0] for row in cursor.fetchall()]

    cursor.close()
    conn.close()

    return {"suggestions": suggestions}



# ================= AUTH =================

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO users (name, email, password) VALUES (%s, %s, %s)",
            (name, email, password)
        )
        conn.commit()
        cursor.close()
        conn.close()

        return redirect('/login')

    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id, name FROM users WHERE email=%s AND password=%s",
            (email, password)
        )
        user = cursor.fetchone()
        cursor.close()
        conn.close()

        if user:
            session['user_id'] = user[0]
            session['user_name'] = user[1]
            session.setdefault('cart', [])
            return redirect('/')
        else:
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
    cursor.execute("SELECT id, name, price FROM plants WHERE id=%s", (plant_id,))
    plant = cursor.fetchone()
    cursor.close()
    conn.close()

    if plant:
        cart = session.setdefault('cart', [])

        # If already in cart → increase quantity
        for item in cart:
            if item['id'] == plant[0]:
                item['quantity'] += 1
                session.modified = True
                return redirect('/cart')

        # If not present → add new
        cart.append({
            'id': plant[0],
            'name': plant[1],
            'price': float(plant[2]),
            'quantity': 1
        })
        session.modified = True

    return redirect('/cart')


# ➕ Increase quantity
@app.route('/increase_quantity/<int:index>')
def increase_quantity(index):
    if 'user_id' not in session:
        return redirect('/login')

    cart = session.get('cart', [])
    if 0 <= index < len(cart):
        cart[index]['quantity'] += 1
        session.modified = True

    return redirect('/cart')


# ➖ Decrease quantity
@app.route('/decrease_quantity/<int:index>')
def decrease_quantity(index):
    if 'user_id' not in session:
        return redirect('/login')

    cart = session.get('cart', [])
    if 0 <= index < len(cart):
        cart[index]['quantity'] -= 1

        # Remove if quantity becomes 0
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
        return redirect('/login')

    cart = session.get('cart', [])

    # If cart is empty → go back
    if not cart:
        return redirect('/cart')

    total = sum(item['price'] * item['quantity'] for item in cart)

    if request.method == 'POST':
        name = request.form['name']
        address = request.form['address']
        phone = request.form['phone']

        # ================= SAVE ORDER TO DATABASE =================
        conn = get_db_connection()
        cursor = conn.cursor()

        user_id = session['user_id']

        # Insert order
        cursor.execute("""
            INSERT INTO orders (user_id, customer_name, address, phone, total_amount)
            VALUES (%s, %s, %s, %s, %s)
        """, (user_id, name, address, phone, total))

        order_id = cursor.lastrowid

        # Insert order items
        for item in cart:
            cursor.execute("""
                INSERT INTO order_items (order_id, plant_id, quantity, price)
                VALUES (%s, %s, %s, %s)
            """, (
                order_id,
                item['id'],
                item['quantity'],
                item['price']
            ))

        conn.commit()
        cursor.close()
        conn.close()

        # Clear cart after order
        session['cart'] = []

        return redirect('/order_success')

    return render_template('checkout.html', total=total)


@app.route('/order_success')
def order_success():
    return render_template('order_success.html')



# ================= ABOUT PAGE =================
@app.route('/about')
def about():
    return render_template('about.html')


# ================= PLANT CARE TIPS =================
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
            "SELECT id FROM admin WHERE username=%s AND password=%s",
            (username, password)
        )
        admin = cursor.fetchone()
        cursor.close()
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
    cursor.close()
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

        image_file = request.files.get('image')  # ✅ correct way

        image_filename = None
        if image_file and image_file.filename != '':
            from werkzeug.utils import secure_filename
            import os

            image_filename = secure_filename(image_file.filename)
            upload_folder = 'static/uploads'
            os.makedirs(upload_folder, exist_ok=True)

            image_path = os.path.join(upload_folder, image_filename)
            image_file.save(image_path)

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO plants (name, category, price, image, description)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (name, category, price, image_filename, description)
        )
        conn.commit()
        cursor.close()
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
            from werkzeug.utils import secure_filename
            import os

            image_filename = secure_filename(image_file.filename)
            upload_folder = 'static/uploads'
            os.makedirs(upload_folder, exist_ok=True)
            image_file.save(os.path.join(upload_folder, image_filename))

            cursor.execute(
                """
                UPDATE plants
                SET name=%s, category=%s, price=%s, image=%s, description=%s
                WHERE id=%s
                """,
                (name, category, price, image_filename, description, id)
            )
        else:
            cursor.execute(
                """
                UPDATE plants
                SET name=%s, category=%s, price=%s, description=%s
                WHERE id=%s
                """,
                (name, category, price, description, id)
            )

        conn.commit()
        cursor.close()
        conn.close()
        return redirect('/admin/dashboard')

    cursor.execute(
        "SELECT name, category, price, image, description FROM plants WHERE id=%s",
        (id,)
    )
    plant = cursor.fetchone()
    cursor.close()
    conn.close()

    return render_template('admin/admin_edit.html', plant=plant)



@app.route('/admin/delete/<int:id>')
def admin_delete(id):
    if 'admin' not in session:
        return redirect('/admin/login')

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM plants WHERE id=%s", (id,))
    conn.commit()
    cursor.close()
    conn.close()

    return redirect('/admin/dashboard')


@app.route('/admin/logout')
def admin_logout():
    session.pop('admin', None)
    return redirect('/admin/login')


# ================= RUN =================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
