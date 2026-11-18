from functools import wraps
from flask import session, redirect, flash
from models import Order, Product, CartItem, User
from extensions import db
from itertools import combinations
from collections import defaultdict
from werkzeug.security import generate_password_hash

# --- Authentication Decorators ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or session.get('role') != 'customer':
            flash('Please login to continue.')
            return redirect('/login')
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get('role') != 'admin':
            return redirect('/')
        return f(*args, **kwargs)
    return decorated_function

# --- Market Basket Analytics ---
def compute_association_rules(min_support=1, min_lift=0.5):
    orders = Order.query.all()
    transactions, item_freq, pair_freq = [], defaultdict(int), defaultdict(int)
    if not orders: return []
    
    for order in orders:
        pids = list({item.product_id for item in order.items})
        transactions.append(set(pids))
        for pid in pids: item_freq[pid] += 1
            
    for t in transactions:
        for a, b in combinations(sorted(t), 2): pair_freq[(a, b)] += 1
            
    rules, product_names = [], {p.id: p.name for p in Product.query.all()}
    for (a, b), freq in pair_freq.items():
        if freq < min_support: continue
        for ant, con in [(a, b), (b, a)]:
            support, confidence = freq / len(orders), freq / item_freq[ant]
            lift = confidence / (item_freq[con] / len(orders))
            if lift >= min_lift:
                rules.append({'antecedent': product_names.get(ant), 'consequent': product_names.get(con),
                              'support': round(support, 3), 'confidence': round(confidence, 3), 'lift': round(lift, 3)})
    return sorted(rules, key=lambda x: x['lift'], reverse=True)

def compute_top_bundles(top_n=5):
    pair_freq, product_map = defaultdict(int), {p.id: p for p in Product.query.all()}
    for order in Order.query.all():
        pids = list({item.product_id for item in order.items})
        for a, b in combinations(sorted(pids), 2): pair_freq[(a, b)] += 1
            
    sorted_pairs = sorted(pair_freq.items(), key=lambda x: x[1], reverse=True)
    bundles, seen = [], set()
    for (a, b), freq in sorted_pairs:
        pair_key = (min(a, b), max(a, b))
        if pair_key not in seen and product_map.get(a) and product_map.get(b):
            bundles.append({'prod_a': product_map[a], 'prod_b': product_map[b], 'freq': freq})
            seen.add(pair_key)
            if len(bundles) >= top_n: break
    return bundles

# --- Unified Recommendation Engine ---
def build_recommendations(user_id=None):
    all_prods = {p.id: p for p in Product.query.filter(Product.stock_quantity > 0).all()}
    bought_ids, cart_ids, already_seen, fav_cat = set(), set(), set(), None
    product_buyers, user_purchases, product_sold = defaultdict(set), defaultdict(set), defaultdict(int)

    for order in Order.query.all():
        for item in order.items:
            product_buyers[item.product_id].add(order.user_id)
            user_purchases[order.user_id].add(item.product_id)
            product_sold[item.product_id] += item.quantity

    if user_id:
        user_orders = Order.query.filter_by(user_id=user_id).all()
        bought_ids = {item.product_id for o in user_orders for item in o.items}
        cart_ids = {ci.product_id for ci in CartItem.query.filter_by(user_id=user_id).all()}
        already_seen = bought_ids | cart_ids
        
        cat_counts = defaultdict(int)
        for o in user_orders:
            for item in o.items:
                if item.product_id in all_prods: cat_counts[all_prods[item.product_id].category] += item.quantity
        fav_cat = max(cat_counts, key=cat_counts.get) if cat_counts else None

    rule_scores, collab_scores, trend_scores = {}, {}, {p: s * 0.8 for p, s in product_sold.items() if p in all_prods and p not in already_seen}
    cat_pids = {p.id for p in all_prods.values() if p.category == fav_cat and p.id not in already_seen} if fav_cat else set()

    if bought_ids:
        rules = compute_association_rules(min_support=1, min_lift=0.1)
        name_to_pid = {p.name: p.id for p in all_prods.values()}
        bought_names = {all_prods[pid].name for pid in bought_ids if pid in all_prods}
        
        for rule in rules:
            if rule['antecedent'] in bought_names:
                pid = name_to_pid.get(rule['consequent'])
                if pid and pid not in already_seen and pid in all_prods:
                    rule_scores[pid] = {'score': rule['confidence'] * rule['lift'] * 40, 'reason': f"Because you bought {rule['antecedent']}"}

        similar_users = {uid for pid in bought_ids for uid in product_buyers.get(pid, [])} - {user_id}
        for uid in similar_users:
            for pid in user_purchases.get(uid, []):
                if pid not in already_seen and pid in all_prods:
                    collab_scores.setdefault(pid, {'score': 0, 'reason': "Shoppers like you bought this"})['score'] += 15

    scored = []
    for pid in set(rule_scores) | set(collab_scores) | cat_pids | set(trend_scores):
        if pid not in all_prods: continue
        prod, combo, signals, reasons = all_prods[pid], 0.0, [], []
        
        if pid in rule_scores: combo += rule_scores[pid]['score']; signals.append('personalised'); reasons.append(rule_scores[pid]['reason'])
        if pid in collab_scores: combo += collab_scores[pid]['score']; signals.append('people_also'); reasons.append(collab_scores[pid]['reason'])
        if pid in cat_pids: combo += 20; signals.append('category')
        if pid in trend_scores: combo += trend_scores[pid]; signals.append('trending')

        display_reason = f"{reasons[0]} + {' · '.join(s.replace('_', ' ').title() for s in signals[1:])}" if len(signals) > 1 and reasons else (reasons[0] if reasons else 'Popular in the store')
        scored.append({'product': prod, 'combo_score': combo, 'signals': signals, 'reason': display_reason})

    scored.sort(key=lambda x: x['combo_score'], reverse=True)
    
    res, shown = {'personalised': [], 'people_also': [], 'trending': [], 'category': []}, set()
    for item in scored:
        if item['product'].id in shown: continue
        tag, lst = ('✨ Picked For You', 'personalised') if 'personalised' in item['signals'] else \
                   ('🛒 People Also Bought', 'people_also') if 'people_also' in item['signals'] else \
                   ('🔥 Trending', 'trending') if 'trending' in item['signals'] else \
                   (f"🏷️ More {fav_cat or 'Items'}", 'category')
        item['tag'] = tag
        res[lst].append(item)
        shown.add(item['product'].id)

    if not res['trending']: res['trending'] = [{'product': p, 'combo_score': 0, 'signals': ['trending'], 'reason': 'New arrival', 'tag': '🔥 Popular'} for p in all_prods.values() if p.id not in shown]
    if not res['personalised']: res['personalised'] = [dict(i, tag='🔥 Trending Now', reason='Popular with shoppers') for i in res['trending'][:6]]; res['trending'] = res['trending'][6:]
    if not res['people_also']: res['people_also'] = [dict(i, tag='🛍️ You May Also Like', reason='Shoppers also enjoy this') for i in res['trending'][:6]]; res['trending'] = res['trending'][6:]
    if not res['category']: res['category'] = [{'product': p, 'combo_score': 0, 'signals': ['category'], 'reason': 'Explore our collection', 'tag': '🏷️ Browse More'} for p in all_prods.values() if p.id not in shown][:6]

    res.update({'bundles': compute_top_bundles(4), 'fav_cat': fav_cat})
    return {k: v[:6] if isinstance(v, list) else v for k, v in res.items()}

def setup_store():
    if User.query.first(): return
    db.session.add(User(username='admin', password=generate_password_hash('123'), role='admin'))
    db.session.add(User(username='alice', password=generate_password_hash('alice123'), role='customer'))
    db.session.commit()
    print("✅ Store initialized.")