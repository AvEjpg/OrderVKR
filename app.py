import os
import jwt
import requests
import qrcode
import io
from flask import Flask, render_template, request, redirect, url_for, flash, session, send_file
from functools import wraps
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'your-secret-key-here')

FASTAPI_URL = os.getenv('FASTAPI_URL', 'http://127.0.0.1:8000')
BOT_USERNAME = os.getenv('TELEGRAM_BOT_USERNAME', 'orderKuz_bot')
JWT_SECRET = os.getenv('JWT_SECRET', 'super_secret_vkr_key_2026_flows')
JWT_ALGORITHM = os.getenv('JWT_ALGORITHM', 'HS256')

PRODUCTS = [
    {"id": 1, "name": "Ноутбук Lenovo", "price": 45000},
    {"id": 2, "name": "Мышь Logitech", "price": 1200},
    {"id": 3, "name": "Клавиатура механическая", "price": 3500},
    {"id": 4, "name": "Монитор 24\"", "price": 15000},
    {"id": 5, "name": "Наушники Sony", "price": 5000},
]

STATUS_NAMES = {1: "Создан", 2: "В обработке", 3: "Доставляется", 4: "Завершён", 5: "Отменён"}

# ---------- Вспомогательные функции ----------
def api_request(method, endpoint, data=None, params=None):
    url = f"{FASTAPI_URL}{endpoint}"
    headers = {"Content-Type": "application/json"}
    token = session.get('access_token')
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        if method.upper() == "GET":
            resp = requests.get(url, headers=headers, params=params)
        elif method.upper() == "POST":
            resp = requests.post(url, headers=headers, json=data)
        elif method.upper() == "PATCH":
            resp = requests.patch(url, headers=headers, json=data)
        else:
            return None, "Unsupported method"
        return resp.json(), resp.status_code
    except Exception as e:
        return {"error": str(e)}, 500

def decode_token(token):
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload.get("sub"), payload.get("role")
    except:
        return None, None

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'access_token' not in session:
            flash("Пожалуйста, войдите в систему", "warning")
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

def role_required(allowed_roles):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            role = session.get('role')
            if not role or role not in allowed_roles:
                flash("Доступ запрещён", "danger")
                return redirect(url_for('index'))
            return f(*args, **kwargs)
        return decorated
    return decorator

def get_cart():
    cart = session.get('cart', {})
    return {int(k): v for k, v in cart.items()}

def save_cart(cart):
    session['cart'] = {str(k): v for k, v in cart.items()}

def add_to_cart(product_id, quantity=1):
    cart = get_cart()
    if product_id in cart:
        cart[product_id]['quantity'] += quantity
    else:
        product = next((p for p in PRODUCTS if p['id'] == product_id), None)
        if product:
            cart[product_id] = {'name': product['name'], 'price': product['price'], 'quantity': quantity}
    save_cart(cart)

def remove_from_cart(product_id):
    cart = get_cart()
    if product_id in cart:
        del cart[product_id]
        save_cart(cart)

def update_quantity(product_id, quantity):
    if quantity <= 0:
        remove_from_cart(product_id)
    else:
        cart = get_cart()
        if product_id in cart:
            cart[product_id]['quantity'] = quantity
            save_cart(cart)

def get_cart_items():
    cart = get_cart()
    items = []
    total = 0
    for pid, item in cart.items():
        subtotal = item['price'] * item['quantity']
        total += subtotal
        items.append({'id': pid, 'name': item['name'], 'price': item['price'], 'quantity': item['quantity'], 'subtotal': subtotal})
    return items, total

# ---------- Маршруты ----------
@app.route('/')
@login_required
def index():
    return render_template('index.html', products=PRODUCTS, status_names=STATUS_NAMES)

@app.route('/add-to-cart/<int:product_id>', methods=['POST'])
@login_required
def add_to_cart_route(product_id):
    quantity = int(request.form.get('quantity', 1))
    add_to_cart(product_id, quantity)
    flash("Товар добавлен в корзину", "success")
    return redirect(url_for('index'))

@app.route('/cart')
@login_required
def cart():
    items, total = get_cart_items()
    return render_template('cart.html', cart_items=items, total=total)

@app.route('/update-cart', methods=['POST'])
@login_required
def update_cart():
    product_id = int(request.form.get('product_id'))
    quantity = int(request.form.get('quantity'))
    update_quantity(product_id, quantity)
    return redirect(url_for('cart'))

@app.route('/remove-from-cart/<int:product_id>', methods=['POST'])
@login_required
def remove_from_cart_route(product_id):
    remove_from_cart(product_id)
    flash("Товар удалён из корзины", "info")
    return redirect(url_for('cart'))

@app.route('/checkout', methods=['POST'])
@login_required
def checkout():
    items, total = get_cart_items()
    if not items:
        flash("Корзина пуста", "warning")
        return redirect(url_for('cart'))
    order_items = [{"product_name": i['name'], "quantity": i['quantity'], "price": i['price']} for i in items]
    data = {"items": order_items}
    resp_json, status = api_request("POST", "/api/orders", data=data)
    if status == 201:
        session.pop('cart', None)
        flash("Заказ успешно оформлен!", "success")
        return redirect(url_for('profile'))
    else:
        error = resp_json.get('detail', 'Ошибка при оформлении заказа')
        flash(error, "danger")
        return redirect(url_for('cart'))

@app.route('/profile')
@login_required
def profile():
    resp_json, status = api_request("GET", "/api/orders")
    if status != 200:
        flash("Не удалось загрузить заказы", "danger")
        orders = []
    else:
        user_id = session.get('user_id')
        orders = [o for o in resp_json if o['user_id'] == user_id]
        for o in orders:
            o['status_name'] = STATUS_NAMES.get(o['status_id'], "Неизвестно")
    bot_link = f"https://t.me/{BOT_USERNAME}"
    user_email = session.get('email')
    return render_template('profile.html', orders=orders, bot_link=bot_link, user_email=user_email)

@app.route('/manager/orders')
@login_required
@role_required(['manager', 'admin'])
def manager_orders():
    # Получаем все заказы
    resp_json, status = api_request("GET", "/api/orders")
    if status != 200:
        flash("Ошибка загрузки заказов", "danger")
        orders = []
    else:
        orders = resp_json
        for o in orders:
            o['status_name'] = STATUS_NAMES.get(o['status_id'], "Неизвестно")
    # Фильтр по статусу (из query string)
    filter_status = request.args.get('status', type=int)
    if filter_status:
        orders = [o for o in orders if o['status_id'] == filter_status]
    return render_template('manager_orders.html', orders=orders, status_names=STATUS_NAMES, filter_status=filter_status)

@app.route('/manager/orders/update_status', methods=['POST'])
@login_required
@role_required(['manager', 'admin'])
def update_order_status():
    order_id = request.form.get('order_id')
    new_status = request.form.get('status_id')
    if not order_id or not new_status:
        flash("Неверные параметры", "danger")
        return redirect(url_for('manager_orders'))
    data = {"status_id": int(new_status)}
    resp_json, status = api_request("PATCH", f"/api/orders/{order_id}/status", data=data)
    if status == 200:
        flash("Статус заказа обновлён", "success")
    else:
        error = resp_json.get('detail', 'Ошибка обновления статуса')
        flash(error, "danger")
    return redirect(url_for('manager_orders'))

@app.route('/custom-order', methods=['GET', 'POST'])
@login_required
def custom_order():
    if request.method == 'POST':
        # Собираем товары из формы (можно несколько строк)
        items = []
        product_names = request.form.getlist('product_name')
        prices = request.form.getlist('price')
        quantities = request.form.getlist('quantity')
        
        for name, price, qty in zip(product_names, prices, quantities):
            if name and price and qty:
                items.append({
                    "product_name": name,
                    "price": float(price),
                    "quantity": int(qty)
                })
        if not items:
            flash("Добавьте хотя бы один товар", "danger")
            return redirect(url_for('custom_order'))
        
        data = {"items": items}
        resp_json, status = api_request("POST", "/api/orders", data=data)  # тот же эндпоинт
        if status == 201:
            session.pop('cart', None)  # очищаем корзину, если была
            flash("Заказ успешно оформлен!", "success")
            return redirect(url_for('profile'))
        else:
            error = resp_json.get('detail', 'Ошибка')
            flash(error, "danger")
    
    return render_template('custom_order.html')

# ----- Управление пользователями (только менеджер) -----
@app.route('/manager/users')
@login_required
@role_required(['manager'])
def manager_users():
    resp_json, status = api_request("GET", "/api/auth/users")
    if status != 200:
        flash("Не удалось загрузить пользователей", "danger")
        users = []
    else:
        users = resp_json
    return render_template('manager_users.html', users=users)

@app.route('/manager/users/update_role', methods=['POST'])
@login_required
@role_required(['manager'])
def manager_update_role():
    user_id = request.form.get('user_id')
    new_role = request.form.get('role')
    if not user_id or not new_role:
        flash("Неверные параметры", "danger")
        return redirect(url_for('manager_users'))
    url = f"/api/auth/users/{user_id}/role?new_role={new_role}"
    resp_json, status = api_request("PATCH", url)
    if status == 200:
        flash("Роль пользователя обновлена", "success")
    else:
        error = resp_json.get('detail', 'Ошибка')
        flash(f"Ошибка: {error}", "danger")
    return redirect(url_for('manager_users'))

# ----- Статистика -----
@app.route('/statistics')
@login_required
@role_required(['manager', 'admin'])
def statistics():
    resp_json, status = api_request("GET", "/api/orders")
    if status != 200:
        flash("Ошибка загрузки данных", "danger")
        orders = []
    else:
        orders = resp_json
    total_orders = len(orders)
    completed = sum(1 for o in orders if o['status_id'] == 4)
    total_sum = sum(o['total_price'] for o in orders)
    status_stats = {id: 0 for id in STATUS_NAMES}
    for o in orders:
        status_stats[o['status_id']] += 1
    return render_template('statistics.html', total=total_orders, completed=completed,
                         total_sum=total_sum, status_stats=status_stats, status_names=STATUS_NAMES)

# ----- QR обратной связи -----
@app.route('/qr/feedback')
@login_required
def qr_feedback():
    # Ссылка на форму обратной связи (можно заменить на свою)
    FEEDBACK_URL = "https://docs.google.com/forms/d/e/1FAIpQLSdhZcExx6LSIXxk0ub55mSu-WIh23WYdGG9HY5EZhLDo7P8eA/viewform"
    try:
        img = qrcode.make(FEEDBACK_URL)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        return send_file(buf, mimetype="image/png")
    except ImportError:
        flash("Для генерации QR-кода установите библиотеку qrcode", "warning")
        return redirect(url_for('index'))

@app.route('/qr-page')
@login_required
def qr_page():
    return render_template('qr_feedback.html')

# ----- Аутентификация -----
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        data = {"email": email, "password": password}
        resp_json, status = api_request("POST", "/api/auth/register", data=data)
        if status == 201:
            flash("Регистрация успешна! Теперь войдите", "success")
            return redirect(url_for('login'))
        else:
            error = resp_json.get('detail', 'Ошибка регистрации')
            flash(error, "danger")
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        data = {"email": email, "password": password}
        resp_json, status = api_request("POST", "/api/auth/login", data=data)
        if status == 200 and 'access_token' in resp_json:
            token = resp_json['access_token']
            session['access_token'] = token
            user_id, role = decode_token(token)
            session['user_id'] = user_id
            session['role'] = role
            session['email'] = email
            flash("Добро пожаловать!", "success")
            return redirect(url_for('index'))
        else:
            error = resp_json.get('detail', 'Неверный email или пароль')
            flash(error, "danger")
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash("Вы вышли из системы", "info")
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True, port=5000)