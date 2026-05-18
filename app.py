import os
from flask import Flask, render_template, request, redirect, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
from extensions import db
from models import User, Product, CartItem, Order, OrderItem
from utils import (login_required, admin_required, build_recommendations,
                   compute_association_rules, compute_top_bundles, setup_store)
from sqlalchemy import func
from collections import defaultdict

app = Flask(__name__)

# ── Security ──────────────────────────────────────────────────────────────────
app.secret_key = os.environ.get('SECRET_KEY', 'change-me-before-going-live')

# ── Database (Vercel Postgres — free, inside Vercel dashboard) ────────────────
# Vercel Postgres exposes two URLs:
#   POSTGRES_URL              → pooled via pgbouncer  (bad for SQLAlchemy)
#   POSTGRES_URL_NON_POOLING  → direct to Neon        (correct for SQLAlchemy)
# We prefer NON_POOLING; fall back to regular URL if only that is present.
_db_url = (
    os.environ.get('POSTGRES_URL_NON_POOLING') or
    os.environ.get('POSTGRES_URL') or
    ''
)

# Fix scheme: Vercel gives postgres:// but SQLAlchemy needs postgresql+psycopg2://
for _old, _new in [
    ('postgres://',    'postgresql+psycopg2://'),
    ('postgresql://',  'postgresql+psycopg2://'),
]:
    if _db_url.startswith(_old):
        _db_url = _db_url.replace(_old, _new, 1)
        break

# Neon (Vercel Postgres backend) requires SSL — add if not already present
if _db_url and 'sslmode' not in _db_url:
    _db_url += ('&' if '?' in _db_url else '?') + 'sslmode=require'

# Use a placeholder when env var is missing so the app at least boots;
# the /setup route will show a clear message instead of a cryptic 500.
app.config['SQLALCHEMY_DATABASE_URI'] = _db_url or 'postgresql+psycopg2://localhost/placeholder'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Serverless-safe pool — Vercel may spin a fresh process per request
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_size': 1,
    'max_overflow': 2,
    'pool_recycle': 300,
    'pool_pre_ping': True,
    'connect_args': {'connect_timeout': 10},
}

db.init_app(app)


# ── One-time DB init ──────────────────────────────────────────────────────────
# Vercel has no startup hook, so visit /setup?token=YOUR_SETUP_TOKEN once
# right after your first deploy to create tables + default admin account.
@app.route('/setup')
def setup():
    token = os.environ.get('SETUP_TOKEN', '')
    if not token or request.args.get('token') != token:
        return 'Forbidden — wrong or missing token.', 403
    db_url = os.environ.get('POSTGRES_URL_NON_POOLING') or os.environ.get('POSTGRES_URL')
    if not db_url:
        return ('❌ POSTGRES_URL not set. Go to Vercel dashboard → Storage → Create Database → Postgres, then redeploy.'), 500
    try:
        with app.app_context():
            db.create_all()
            setup_store()
        return '✅ Database ready! Login at /login  (admin / 123)', 200
    except Exception as e:
        return f'❌ DB error: {e}', 500


# ── Inject cart count into every template ─────────────────────────────────────
@app.context_processor
def inject_cart_count():
    count = (
        sum(i.quantity for i in CartItem.query.filter_by(user_id=session['user_id']).all())
        if session.get('role') == 'customer' else 0
    )
    return dict(cart_count=count)


# ── Auth ──────────────────────────────────────────────────────────────────────
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form['username']).first()
        if user and check_password_hash(user.password, request.form['password']):
            session.update({'user_id': user.id, 'username': user.username, 'role': user.role})
            return redirect('/admin' if user.role == 'admin' else '/')
        flash('Invalid credentials.')
    return render_template('login.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        try:
            db.session.add(User(
                username=request.form['username'],
                password=generate_password_hash(request.form['password'])
            ))
            db.session.commit()
            flash('Registration successful! Please login.')
            return redirect('/login')
        except Exception:
            flash('Username already exists.')
    return render_template('register.html')


@app.route('/logout')
def logout():
    session.clear()
    return redirect('/')


# ── Customer ──────────────────────────────────────────────────────────────────
@app.route('/')
def index():
    q, cat = request.args.get('q', ''), request.args.get('category', '')
    query = Product.query.filter(Product.name.ilike(f'%{q}%')) if q else Product.query
    if cat:
        query = query.filter_by(category=cat)
    recs = build_recommendations(session.get('user_id'))
    return render_template('index.html', products=query.all(),
                           search_query=q, category_filter=cat, recs=recs)


@app.route('/add_to_cart/<int:product_id>', methods=['POST'])
@login_required
def add_to_cart(product_id):
    product = Product.query.get_or_404(product_id)
    qty = max(1, int(request.form.get('quantity', 1)))
    item = CartItem.query.filter_by(user_id=session['user_id'], product_id=product_id).first()
    if item:
        if item.quantity + qty <= product.stock_quantity:
            item.quantity += qty
        else:
            flash(f'Adding exceeds stock for {product.name}.')
    elif qty <= product.stock_quantity:
        db.session.add(CartItem(user_id=session['user_id'],
                                product_id=product_id, quantity=qty))
        flash(f'{product.name} added!')
    db.session.commit()
    return redirect(request.referrer or '/')


@app.route('/add_bundle/<int:pid_a>/<int:pid_b>', methods=['POST'])
@login_required
def add_bundle(pid_a, pid_b):
    for pid in [pid_a, pid_b]:
        prod = Product.query.get(pid)
        if prod and prod.stock_quantity > 0:
            item = CartItem.query.filter_by(user_id=session['user_id'], product_id=pid).first()
            if item and item.quantity < prod.stock_quantity:
                item.quantity += 1
            elif not item:
                db.session.add(CartItem(user_id=session['user_id'], product_id=pid, quantity=1))
    db.session.commit()
    flash("Bundle added to cart! 🎁")
    return redirect('/')


@app.route('/cart')
@login_required
def view_cart():
    items = CartItem.query.filter_by(user_id=session['user_id']).all()
    total = sum(i.product.price * i.quantity for i in items)
    return render_template('cart.html', cart_items=items, total=total,
                           recs=build_recommendations(session['user_id']))


@app.route('/update_cart/<int:cart_id>', methods=['POST'])
@login_required
def update_cart(cart_id):
    item = CartItem.query.get_or_404(cart_id)
    qty = int(request.form.get('quantity', 1))
    if qty <= 0:
        db.session.delete(item)
    elif qty <= item.product.stock_quantity:
        item.quantity = qty
    db.session.commit()
    return redirect('/cart')


@app.route('/remove_from_cart/<int:cart_id>', methods=['POST'])
@login_required
def remove_from_cart(cart_id):
    db.session.delete(CartItem.query.get_or_404(cart_id))
    db.session.commit()
    return redirect('/cart')


@app.route('/checkout', methods=['POST'])
@login_required
def checkout():
    items = CartItem.query.filter_by(user_id=session['user_id']).all()
    if not items:
        return redirect('/cart')
    order = Order(
        user_id=session['user_id'],
        total_amount=sum(i.product.price * i.quantity for i in items)
    )
    db.session.add(order)
    db.session.flush()
    for i in items:
        i.product.stock_quantity -= i.quantity
        db.session.add(OrderItem(order_id=order.id, product_id=i.product_id,
                                 quantity=i.quantity, price=i.product.price))
        db.session.delete(i)
    db.session.commit()
    flash('Order placed successfully! 🎉')
    return redirect('/my_orders')


@app.route('/my_orders')
@login_required
def my_orders():
    return render_template(
        'my_orders.html',
        orders=Order.query.filter_by(user_id=session['user_id'])
                          .order_by(Order.date_ordered.desc()).all()
    )


# ── Admin ─────────────────────────────────────────────────────────────────────
@app.route('/admin')
@admin_required
def admin_dashboard():
    return render_template('admin_dash.html', products=Product.query.all())


@app.route('/add_product', methods=['POST'])
@admin_required
def add_product():
    db.session.add(Product(
        name=request.form['name'], category=request.form['category'],
        price=float(request.form['price']), stock_quantity=int(request.form['quantity']),
        image_url=request.form.get('image_url') or
                  'https://via.placeholder.com/300x200?text=No+Image'
    ))
    db.session.commit()
    flash('Product added.')
    return redirect('/admin')


@app.route('/edit_product/<int:product_id>', methods=['GET', 'POST'])
@admin_required
def edit_product(product_id):
    p = Product.query.get_or_404(product_id)
    if request.method == 'POST':
        p.name = request.form['name']
        p.category = request.form['category']
        p.price = float(request.form['price'])
        p.stock_quantity = int(request.form['quantity'])
        p.image_url = request.form.get('image_url') or p.image_url
        db.session.commit()
        flash('Product updated!')
        return redirect('/admin')
    return render_template('edit_product.html', product=p)


@app.route('/delete_product/<int:product_id>', methods=['POST'])
@admin_required
def delete_product(product_id):
    db.session.delete(Product.query.get_or_404(product_id))
    db.session.commit()
    return redirect('/admin')


@app.route('/admin/orders')
@admin_required
def admin_orders():
    q = request.args.get('q', '')
    query = (
        Order.query.join(User).filter(
            Order.id == int(q) if q.isdigit() else User.username.ilike(f'%{q}%')
        ) if q else Order.query
    )
    orders = query.order_by(Order.date_ordered.desc()).all()
    return render_template('admin_orders.html', orders=orders, search_query=q,
                           matched_users={o.user_id: o.user.username for o in orders})


@app.route('/admin/analytics')
@admin_required
def admin_analytics():
    total_rev = db.session.query(func.sum(Order.total_amount)).scalar() or 0
    orders_count = Order.query.count()
    items_sold = db.session.query(func.sum(OrderItem.quantity)).scalar() or 0

    all_selling = (
        db.session.query(
            Product.name,
            func.sum(OrderItem.quantity).label('total_sold'),
            func.sum(OrderItem.quantity * OrderItem.price).label('total_earned')
        )
        .join(OrderItem).group_by(Product.id)
        .order_by(func.sum(OrderItem.quantity).desc()).all()
    )

    rules = compute_association_rules()
    return render_template(
        'admin_analytics.html',
        total_revenue=total_rev, total_orders=orders_count,
        total_products=Product.query.count(),
        avg_basket_size=round(items_sold / orders_count, 1) if orders_count else 0,
        active_customers=db.session.query(
            func.count(func.distinct(Order.user_id))).scalar() or 0,
        low_stock_products=Product.query.filter(Product.stock_quantity < 5).all(),
        low_performers=all_selling[::-1][:5], top_selling=all_selling[:5],
        more_selling=all_selling[5:],
        graph_labels=[i.name for i in all_selling[:5]],
        graph_data=[i.total_sold for i in all_selling[:5]],
        rules_labels=[f"{r['antecedent']} → {r['consequent']}" for r in rules[:8]],
        rules_confidence=[r['confidence'] for r in rules[:8]],
        rules_lift=[r['lift'] for r in rules[:8]],
        top_bundles=compute_top_bundles()
    )


@app.route('/admin/customer/<int:user_id>')
@admin_required
def customer_analysis(user_id):
    user = User.query.get_or_404(user_id)
    orders = Order.query.filter_by(user_id=user_id).order_by(
        Order.date_ordered.desc()).all()
    prod_counts, cat_counts = defaultdict(int), defaultdict(int)
    for o in orders:
        for i in o.items:
            prod_counts[i.product.name] += i.quantity
            cat_counts[i.product.category] += i.quantity

    recs = [r for r in compute_association_rules()
            if r['antecedent'] in prod_counts
            and r['consequent'] not in prod_counts][:3]

    if len(orders) >= 5:
        lbl, clr, desc = "🏆 Loyal Regular", "success", "Core revenue driver."
    elif len(orders) >= 2:
        lbl, clr, desc = "🔄 Repeat Buyer", "primary", "Great upsell potential."
    elif len(orders) == 1:
        lbl, clr, desc = "🆕 First-Timer", "warning", "Follow-up needed."
    else:
        lbl, clr, desc = "👻 Inactive", "secondary", "Needs promo."

    return render_template(
        'customer_analysis.html', user=user, orders=orders,
        total_spent=sum(o.total_amount for o in orders),
        total_orders_count=len(orders),
        avg_order_value=round(
            sum(o.total_amount for o in orders) / len(orders), 2) if orders else 0,
        favourite_product=max(prod_counts, key=prod_counts.get) if prod_counts else 'N/A',
        favourite_category=max(cat_counts, key=cat_counts.get) if cat_counts else 'N/A',
        behaviour_label=lbl, behaviour_colour=clr, behaviour_desc=desc,
        recommendations=recs,
        order_dates=[o.date_ordered.strftime('%b %d') for o in orders[::-1]],
        order_amounts=[o.total_amount for o in orders[::-1]],
        top_user_products=sorted(prod_counts.items(), key=lambda x: x[1], reverse=True)
    )


# ── Local dev only (Vercel ignores this block) ────────────────────────────────
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        setup_store()
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
