import csv
import hashlib
import hmac
import io
import os
import re
import secrets
import sqlite3
from datetime import datetime, timezone, timedelta
from functools import wraps
from pathlib import Path

import click
from flask import Flask, abort, flash, g, jsonify, redirect, render_template, request, session, url_for, Response
from werkzeug.security import check_password_hash, generate_password_hash

from . import service

ROOT = Path(__file__).resolve().parent.parent
MN = {
    'For sellers': 'Борлуулагчдад', 'Explore auctions': 'Дуудлага худалдаа', 'My bids': 'Миний үнийн санал',
    'Seller studio': 'Борлуулагчийн самбар', 'Operations': 'Удирдлага', 'Sign in': 'Нэвтрэх',
    'Sign out': 'Гарах', 'Create account': 'Бүртгүүлэх', 'Current bid': 'Одоогийн үнэ',
    'Starting price': 'Эхлэх үнэ', 'Place bid': 'Үнийн санал өгөх', 'Bid history': 'Үнийн саналын түүх',
    'Auction rules': 'Дуудлага худалдааны дүрэм', 'Closes': 'Хаагдах хугацаа', 'Minimum increment': 'Үнийн алхам',
    'Seller-provided evidence': 'Борлуулагчийн өгсөн баримт', 'Condition': 'Барааны төлөв',
    'Report a concern': 'Асуудал мэдээлэх', 'No bids yet': 'Үнийн санал ирээгүй',
    'Your next great find.': 'Таны дараагийн онцгой олдвор.', 'Objects with a story.': 'Түүх өгүүлэх эд зүйлс.',
    'A considered way to bid.': 'Тунгааж сонгон, үнэ санал болго.', 'View auction': 'Дэлгэрэнгүй',
    'Email': 'Цахим шуудан', 'Password': 'Нууц үг', 'Open': 'Нээлттэй', 'Closed': 'Хаагдсан',
    'Draft': 'Ноорог', 'Cancelled': 'Цуцалсан', 'Suspended': 'Түдгэлзүүлсэн',
    'Pickup & contact': 'Хүлээн авах ба холбоо барих', 'Seller policies': 'Борлуулагчийн нөхцөл',
    'Buyer account': 'Худалдан авагчийн бүртгэл', 'Bid amount (MNT)': 'Санал болгох үнэ (₮)',
    'Request a pilot': 'Туршилтын хүсэлт илгээх', 'Send inquiry': 'Хүсэлт илгээх',
    'Save draft': 'Ноорог хадгалах', 'Publish auction': 'Дуудлага худалдааг нээх', 'New listing': 'Шинэ зар',
    'Payment deadline': 'Төлбөрийн хугацаа', 'Seller instructions': 'Борлуулагчийн заавар',
    'Free bidding': 'Үнийн санал үнэгүй', 'Demo collection': 'Туршилтын цуглуулга',
}


def create_app(config=None):
    app = Flask(__name__, template_folder=str(ROOT / 'templates'), static_folder=str(ROOT / 'static'))
    instance = ROOT / 'instance'
    instance.mkdir(exist_ok=True)
    secret = os.getenv('APP_SECRET')
    if not secret:
        secret_file = instance / 'session-secret'
        if not secret_file.exists():
            try:
                with secret_file.open('x') as f:
                    f.write(secrets.token_hex(32))
            except FileExistsError:
                pass
        secret = secret_file.read_text()
    if len(secret) < 32:
        raise RuntimeError('APP_SECRET must contain at least 32 characters.')
    app.config.update(SECRET_KEY=secret, DATABASE=os.getenv('AUCTION_DB', str(instance / 'auction.sqlite3')),
                      DEMO_MODE=os.getenv('DEMO_MODE', '1') == '1', MAX_CONTENT_LENGTH=32_768,
                      SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax',
                      SESSION_COOKIE_SECURE=os.getenv('COOKIE_SECURE', '0') == '1',
                      PERMANENT_SESSION_LIFETIME=timedelta(hours=8))
    if config:
        app.config.update(config)

    def db():
        if 'db' not in g:
            g.db = service.connect(app.config['DATABASE'])
        return g.db

    @app.teardown_appcontext
    def teardown(_error):
        connection = g.pop('db', None)
        if connection:
            connection.close()

    def translate(text):
        return MN.get(text, text) if session.get('lang') == 'mn' else text

    @app.template_filter('mnt')
    def mnt(value):
        return f'{int(value):,} ₮'

    @app.template_filter('localtime')
    def localtime(value):
        if not value:
            return '—'
        return datetime.fromtimestamp(value, timezone(timedelta(hours=8))).strftime('%Y.%m.%d · %H:%M') + ' UBT'

    @app.context_processor
    def context():
        session.setdefault('csrf', secrets.token_urlsafe(32))
        return dict(t=translate, csrf=session['csrf'], user=g.get('user'), lang=session.get('lang', 'en'), demo=app.config['DEMO_MODE'])

    @app.before_request
    def protect():
        g.user = None
        if request.endpoint == 'static':
            return
        if 'uid' in session:
            g.user = db().execute('SELECT * FROM users WHERE id=?', (session['uid'],)).fetchone()
            if not g.user or g.user['suspended']:
                session.clear()
                g.user = None
        if request.method == 'POST':
            if request.files:
                raise service.RuleError('Uploads are disabled in this preview. Use bundled demo photographs only.', 400)
            token = request.headers.get('X-CSRF-Token') or request.form.get('csrf', '')
            if not session.get('csrf') or not hmac.compare_digest(session['csrf'], token):
                raise service.RuleError('Your form expired. Refresh the page and try again.', 400)
            ip = hashlib.sha256((app.secret_key + (request.remote_addr or 'unknown')).encode()).hexdigest()
            auth = request.endpoint in ('login', 'register')
            bucket = ('auth:' if auth else 'write:') + ip
            if not service.rate_limit(db(), bucket, 20 if auth else 100, 300 if auth else 60):
                raise service.RuleError('Too many requests. Please wait and try again.', 429)

    @app.after_request
    def headers(response):
        response.headers.update({'X-Content-Type-Options': 'nosniff', 'X-Frame-Options': 'DENY',
                                 'Referrer-Policy': 'same-origin', 'Cache-Control': 'no-store',
                                 'Content-Security-Policy': "default-src 'self'; img-src 'self'; style-src 'self'; script-src 'self'; form-action 'self'; frame-ancestors 'none'; base-uri 'self'"})
        return response

    def require(role=None):
        def decorate(fn):
            @wraps(fn)
            def wrapped(*args, **kwargs):
                if not g.user:
                    if request.path.startswith('/api/'):
                        raise service.RuleError('Sign in to continue.', 401)
                    return redirect(url_for('login'))
                if role and g.user['role'] != role:
                    abort(403)
                return fn(*args, **kwargs)
            return wrapped
        return decorate

    def text(name, low=1, high=2000):
        value = request.form.get(name, '').strip()
        if not low <= len(value) <= high:
            raise service.RuleError(f'{name.replace("_", " ").title()} must have {low}–{high} characters.', 400)
        return value

    def integer(name, low, high):
        value = request.form.get(name, '')
        if not re.fullmatch(r'[0-9]{1,13}', value) or not low <= int(value) <= high:
            raise service.RuleError(f'Invalid {name.replace("_", " ")}.', 400)
        return int(value)

    def email():
        value = text('email', 5, 254).lower()
        if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', value):
            raise service.RuleError('Enter a valid email address.', 400)
        return value

    def auctions_query(where='', args=()):
        return db().execute('''SELECT a.*, s.name shop_name,s.slug, (SELECT max(amount) FROM bids WHERE auction_id=a.id) price,
           (SELECT count(*) FROM bids WHERE auction_id=a.id) bid_count FROM auctions a JOIN shops s ON s.id=a.shop_id ''' + where + ' ORDER BY a.id DESC', args).fetchall()

    def auction_or_404(auction_id):
        rows = auctions_query('WHERE a.id=?', (auction_id,))
        if not rows:
            abort(404)
        a = rows[0]
        if a['state'] == 'draft' and (not g.user or (g.user['role'] != 'operator' and g.user['shop_id'] != a['shop_id'])):
            abort(404)
        return a

    @app.errorhandler(service.RuleError)
    def rule_error(error):
        if request.path.startswith('/api/'):
            return jsonify(error=error.message), error.status
        return render_template('error.html', message=error.message, status=error.status), error.status

    @app.errorhandler(403)
    @app.errorhandler(404)
    @app.errorhandler(413)
    def http_error(error):
        return render_template('error.html', message={403:'You do not have access to this page.',404:'This page could not be found.',413:'This request is too large.'}[error.code], status=error.code), error.code

    @app.errorhandler(sqlite3.OperationalError)
    def database_error(error):
        app.logger.exception('Database operation failed')
        message = 'The database is busy or unavailable. Retry the same bid request; do not create a new request until its result is known.'
        if request.path.startswith('/api/'):
            return jsonify(error=message), 503
        return render_template('error.html', message=message, status=503), 503

    @app.post('/language')
    def language():
        session['lang'] = 'mn' if request.form.get('lang') == 'mn' else 'en'
        target = request.form.get('next', '/')
        if not target.startswith('/') or target.startswith('//') or '\\' in target:
            target = '/'
        return redirect(target)

    @app.get('/')
    def home():
        return render_template('home.html')

    @app.post('/inquiry')
    def inquiry():
        contact, message = email(), text('message', 10, 2000)
        db().execute('INSERT INTO inquiries(email,message,created_at) VALUES(?,?,unixepoch())', (contact, message))
        flash('Inquiry saved for the pilot operator. No email has been sent.')
        return redirect(url_for('home') + '#pilot')

    @app.get('/explore')
    def explore():
        service.close_due(db())
        return render_template('explore.html', auctions=auctions_query("WHERE a.state!='draft'"))

    @app.get('/shops/<slug>')
    def shop(slug):
        service.close_due(db())
        seller = db().execute('SELECT * FROM shops WHERE slug=?', (slug,)).fetchone()
        if not seller:
            abort(404)
        return render_template('shop.html', shop=seller, auctions=auctions_query("WHERE a.shop_id=? AND a.state!='draft'", (seller['id'],)))

    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if request.method == 'POST':
            address, password = email(), text('password', 1, 256)
            user = db().execute('SELECT * FROM users WHERE email=?', (address,)).fetchone()
            valid = check_password_hash(user['password'] if user else app.config['DUMMY_HASH'], password)
            if not user or not valid or user['suspended']:
                raise service.RuleError('Email or password was not accepted.', 401)
            language = session.get('lang', 'en')
            session.clear()
            session.update(uid=user['id'], lang=language, csrf=secrets.token_urlsafe(32))
            session.permanent = True
            service.audit(db(), user['id'], 'login', 'user', user['id'], 'Password login')
            return redirect(url_for('seller_dashboard' if user['role'] == 'seller' else 'admin' if user['role'] == 'operator' else 'account'))
        return render_template('auth.html', registering=False)

    @app.route('/register', methods=['GET', 'POST'])
    def register():
        if request.method == 'POST':
            address, password = email(), text('password', 12, 256)
            if request.form.get('accept') != 'yes':
                raise service.RuleError('Accept the demo terms and privacy notice to continue.', 400)
            try:
                cursor = db().execute("INSERT INTO users(email,password,alias,role,created_at) VALUES(?,?,?,'buyer',unixepoch())",
                                      (address, generate_password_hash(password), 'Bidder-' + secrets.token_hex(4).upper()))
            except sqlite3.IntegrityError:
                raise service.RuleError('This email cannot be registered. Try signing in.', 400)
            session.clear()
            session.update(uid=cursor.lastrowid, csrf=secrets.token_urlsafe(32))
            session.permanent = True
            flash('Buyer account created. Use synthetic information in this preview.')
            return redirect(url_for('explore'))
        return render_template('auth.html', registering=True)

    @app.post('/logout')
    def logout():
        session.clear()
        return redirect(url_for('home'))

    @app.get('/auctions/<int:auction_id>')
    def detail(auction_id):
        service.close_due(db())
        a = auction_or_404(auction_id)
        seller = db().execute('SELECT * FROM shops WHERE id=?', (a['shop_id'],)).fetchone()
        bids = db().execute('SELECT b.amount,b.created_at,u.alias FROM bids b JOIN users u ON u.id=b.user_id WHERE auction_id=? ORDER BY b.id DESC', (auction_id,)).fetchall()
        return render_template('detail.html', a=a, shop=seller, bids=bids, request_key=secrets.token_urlsafe(24), timestamp=service.now(db()))

    @app.get('/api/auctions/<int:auction_id>')
    def auction_state(auction_id):
        service.close_due(db())
        a = auction_or_404(auction_id)
        history = db().execute('SELECT u.alias,b.amount,b.created_at FROM bids b JOIN users u ON u.id=b.user_id WHERE auction_id=? ORDER BY b.id DESC LIMIT 50', (auction_id,)).fetchall()
        return jsonify(id=a['id'], state=a['state'], price=a['price'] or a['start_price'],
                       minimum=a['price'] + a['increment'] if a['price'] else a['start_price'],
                       closes_at=a['closes_at'], server_time=service.now(db()), bids=[dict(b) for b in history])

    @app.post('/api/auctions/<int:auction_id>/bids')
    @require('buyer')
    def bid_api(auction_id):
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            raise service.RuleError('Send a JSON object with amount and request_key.', 400)
        bid, replay = service.place_bid(db(), g.user['id'], auction_id, data.get('amount'), data.get('request_key'))
        return jsonify(bid_id=bid['id'], amount=bid['amount'], replay=replay), 200 if replay else 201

    @app.post('/auctions/<int:auction_id>/bid')
    @require('buyer')
    def bid_form(auction_id):
        amount = integer('amount', 1, 1_000_000_000_000)
        _, replay = service.place_bid(db(), g.user['id'], auction_id, amount, request.form.get('request_key'))
        flash('This bid was already received.' if replay else 'Your bid was accepted and recorded.')
        return redirect(url_for('detail', auction_id=auction_id))

    @app.get('/account')
    @require('buyer')
    def account():
        service.close_due(db())
        rows = db().execute('''SELECT a.*,s.name shop_name,s.contact, max(b.amount) my_bid,
                  (SELECT max(amount) FROM bids WHERE auction_id=a.id) price
           FROM bids b JOIN auctions a ON a.id=b.auction_id JOIN shops s ON s.id=a.shop_id
           WHERE b.user_id=? GROUP BY a.id ORDER BY a.id DESC''', (g.user['id'],)).fetchall()
        return render_template('account.html', auctions=rows)

    @app.post('/auctions/<int:auction_id>/report')
    @require()
    def report(auction_id):
        auction_or_404(auction_id)
        reason = text('reason', 10, 2000)
        with service.transaction(db()):
            db().execute('INSERT INTO reports(user_id,auction_id,reason,created_at) VALUES(?,?,?,unixepoch())', (g.user['id'], auction_id, reason))
            service.audit(db(), g.user['id'], 'report_opened', 'auction', auction_id, 'Private concern submitted')
        flash('Report saved. The operator reviews reports manually; email and instant support are not enabled.')
        return redirect(url_for('detail', auction_id=auction_id))

    @app.get('/seller')
    @require('seller')
    def seller_dashboard():
        service.close_due(db())
        rows = auctions_query('WHERE a.shop_id=?', (g.user['shop_id'],))
        winners = {r['id']: db().execute('SELECT email,alias FROM users WHERE id=?', (r['winner_id'],)).fetchone() for r in rows if r['winner_id']}
        return render_template('seller.html', auctions=rows, winners=winners)

    def listing_values():
        image = text('image', 1, 20)
        if image not in ('pendant', 'watch', 'ring'):
            raise service.RuleError('Choose a bundled demo photograph.', 400)
        close_text = text('closes_at', 16, 16)
        try:
            close = int(datetime.strptime(close_text, '%Y-%m-%dT%H:%M').replace(tzinfo=timezone(timedelta(hours=8))).timestamp())
        except ValueError:
            raise service.RuleError('Enter a valid closing date in Ulaanbaatar time.', 400)
        if not service.now(db()) + 60 <= close <= service.now(db()) + 366 * 86400:
            raise service.RuleError('Closing time must be between one minute and one year ahead.', 400)
        return dict(title=text('title', 3, 120), description=text('description', 10, 4000), condition=text('condition', 3, 1000),
                    evidence=text('evidence', 3, 2000), image=image, start_price=integer('start_price',1,1_000_000_000_000),
                    increment=integer('increment',1,1_000_000_000), closes_at=close, soft_close=integer('soft_close',0,600),
                    payment_hours=integer('payment_hours',1,168), fees=text('fees',3,1000),
                    seller_terms=text('seller_terms',10,4000), payment_instructions=text('payment_instructions',10,2000))

    @app.route('/seller/new', methods=['GET', 'POST'])
    @require('seller')
    def new_listing():
        if request.method == 'POST':
            values = listing_values()
            with service.transaction(db()):
                service.active_user(db(), g.user['id'])
                shop = db().execute('SELECT * FROM shops WHERE id=? AND status=\'approved\'', (g.user['shop_id'],)).fetchone()
                if not shop:
                    abort(403)
                names = ','.join(values)
                cursor = db().execute(f'INSERT INTO auctions(shop_id,{names},created_at) VALUES(?,{",".join("?" for _ in values)},unixepoch())', (g.user['shop_id'], *values.values()))
                service.audit(db(), g.user['id'], 'draft_created', 'auction', cursor.lastrowid, 'Material terms saved')
            return redirect(url_for('edit_listing', auction_id=cursor.lastrowid))
        shop = db().execute('SELECT * FROM shops WHERE id=?', (g.user['shop_id'],)).fetchone()
        default = dict(image='pendant', start_price=100000,increment=10000,soft_close=120,payment_hours=48,
                       fees='No buyer platform fee. Free pickup; delivery by separate agreement.',seller_terms=shop['terms'],payment_instructions=shop['instructions'],
                       closes_at=service.now(db())+86400)
        return render_template('edit.html', a=default, is_new=True)

    @app.route('/seller/<int:auction_id>/edit', methods=['GET', 'POST'])
    @require('seller')
    def edit_listing(auction_id):
        a = service.seller_access(db(), g.user['id'], auction_id)
        if a['state'] != 'draft':
            raise service.RuleError('Material terms are frozen after publication. Cancel with a reason and relist for corrections.')
        if request.method == 'POST':
            values = listing_values()
            with service.transaction(db()):
                locked = service.seller_access(db(), g.user['id'], auction_id)
                if locked['state'] != 'draft':
                    raise service.RuleError('The listing is no longer a draft.')
                db().execute(f'UPDATE auctions SET {",".join(k+"=?" for k in values)} WHERE id=?', (*values.values(), auction_id))
                service.audit(db(), g.user['id'], 'draft_updated', 'auction', auction_id, 'Material terms updated before publication')
            flash('Draft saved.')
            return redirect(url_for('edit_listing', auction_id=auction_id))
        return render_template('edit.html', a=a, is_new=False)

    @app.post('/seller/<int:auction_id>/publish')
    @require('seller')
    def publish(auction_id):
        with service.transaction(db()):
            a = service.seller_access(db(), g.user['id'], auction_id)
            if a['state'] != 'draft' or a['closes_at'] <= service.now(db()):
                raise service.RuleError('Only a draft with a future closing time can be published.')
            db().execute("UPDATE auctions SET state='open' WHERE id=?", (auction_id,))
            service.audit(db(), g.user['id'], 'published_terms_frozen', 'auction', auction_id, 'All material terms locked')
        flash('Auction opened. Material terms are now frozen.')
        return redirect(url_for('detail', auction_id=auction_id))

    @app.post('/seller/<int:auction_id>/cancel')
    @require('seller')
    def cancel(auction_id):
        reason = text('reason',10,1000)
        with service.transaction(db()):
            a = service.seller_access(db(), g.user['id'], auction_id)
            if service.settle_locked(db(), a, service.now(db())) or a['state'] not in ('draft','open'):
                raise service.RuleError('Only a draft or an unclosed auction can be cancelled. Closed outcomes require operator review.')
            db().execute("UPDATE auctions SET state='cancelled' WHERE id=?", (auction_id,))
            service.audit(db(), g.user['id'], 'cancelled', 'auction', auction_id, reason)
        return redirect(url_for('seller_dashboard'))

    @app.post('/seller/<int:auction_id>/status')
    @require('seller')
    def update_status(auction_id):
        kind, value = request.form.get('kind'), request.form.get('value')
        if 'outcome' in request.form:
            parts = request.form['outcome'].split(':')
            if len(parts) != 2:
                raise service.RuleError('Invalid status.', 400)
            kind, value = parts
        allowed = {'payment': ('paid','unpaid_review'), 'fulfillment': ('collected','delivered')}
        if kind not in allowed or value not in allowed[kind]:
            raise service.RuleError('Invalid status.',400)
        reason = text('reason',10,1000)
        with service.transaction(db()):
            a = service.seller_access(db(), g.user['id'], auction_id)
            if a['state'] != 'closed' or not a['winner_id']:
                raise service.RuleError('Status can only be recorded for an awarded, closed auction.')
            if kind == 'fulfillment' and a['payment'] != 'paid':
                raise service.RuleError('Record seller-confirmed payment before fulfillment.')
            if kind == 'payment' and value == 'unpaid_review' and (a['payment'] == 'paid' or service.now(db()) < a['closes_at'] + a['payment_hours'] * 3600):
                raise service.RuleError('Unpaid review requires an unpaid award past its payment deadline.')
            if (kind == 'payment' and a['payment'] not in ('awaiting','unpaid_review')) or (kind == 'fulfillment' and a['fulfillment'] != 'pending'):
                raise service.RuleError('This status is already final. Ask the operator to review a correction.')
            db().execute(f'UPDATE auctions SET {kind}=? WHERE id=?', (value,auction_id))
            service.audit(db(),g.user['id'],f'seller_recorded_{kind}', 'auction', auction_id, value + ': ' + reason)
        flash('Seller record saved. This is a manual confirmation, not provider verification.')
        return redirect(url_for('seller_dashboard'))

    @app.post('/seller/<int:auction_id>/relist')
    @require('seller')
    def relist(auction_id):
        reason = text('reason',10,1000)
        with service.transaction(db()):
            a = service.seller_access(db(),g.user['id'],auction_id)
            if a['state'] != 'cancelled' and not (a['state']=='closed' and (not a['winner_id'] or a['payment']=='unpaid_review')):
                raise service.RuleError('Relist only cancelled, unsold, or documented unpaid-review auctions.')
            fields = ['shop_id','title','description','condition','evidence','image','start_price','increment','soft_close','payment_hours','fees','seller_terms','payment_instructions']
            cursor = db().execute(f'INSERT INTO auctions({",".join(fields)},closes_at,created_at) VALUES({",".join("?" for _ in fields)},?,unixepoch())', (*[a[k] for k in fields],service.now(db())+86400))
            service.audit(db(),g.user['id'],'relisted_as_draft','auction',auction_id,f'New listing {cursor.lastrowid}. Review: {reason}. Old bids and award retained; no underbidder charged.')
        return redirect(url_for('edit_listing',auction_id=cursor.lastrowid))

    @app.get('/seller/export.csv')
    @require('seller')
    def export():
        service.close_due(db())
        output = io.StringIO(newline='')
        writer = csv.writer(output)
        writer.writerow(['auction_id','title','state','bid_id','bidder_alias','amount_mnt','bid_time_utc','winner_alias','payment','fulfillment'])
        rows = db().execute('''SELECT a.id,a.title,a.state,b.id bid_id,u.alias,b.amount,b.created_at,w.alias winner,a.payment,a.fulfillment
           FROM auctions a LEFT JOIN bids b ON b.auction_id=a.id LEFT JOIN users u ON u.id=b.user_id
           LEFT JOIN users w ON w.id=a.winner_id WHERE a.shop_id=? ORDER BY a.id,b.id''',(g.user['shop_id'],)).fetchall()
        for row in rows:
            writer.writerow([("'"+v if isinstance(v,str) and v.startswith(('=','+','-','@','\t','\r','\n')) else v) for v in row])
        return Response(output.getvalue(),mimetype='text/csv',headers={'Content-Disposition':'attachment; filename=auction-records.csv'})

    @app.get('/operator')
    @require('operator')
    def admin():
        service.close_due(db())
        return render_template('operator.html', shops=db().execute('SELECT * FROM shops').fetchall(),
             users=db().execute('SELECT id,email,alias,role,suspended FROM users').fetchall(), auctions=auctions_query(),
             reports=db().execute('SELECT * FROM reports ORDER BY id DESC').fetchall(),
             inquiries=db().execute('SELECT * FROM inquiries ORDER BY id DESC').fetchall(),
             events=db().execute('SELECT * FROM audit ORDER BY id DESC LIMIT 200').fetchall())

    @app.post('/operator/onboard')
    @require('operator')
    def onboard():
        values = dict(name=text('name',3,120),slug=text('slug',3,60), address=text('address',5,500),contact=text('contact',5,500),
                      terms=text('terms',10,4000), instructions=text('instructions',10,2000),identity_note=text('identity_note',10,1000))
        address, password = email(), text('password',12,256)
        if not re.fullmatch('[a-z0-9]+(?:-[a-z0-9]+)*',values['slug']):
            raise service.RuleError('Shop slug must contain lowercase letters, digits and hyphens.',400)
        hashed = generate_password_hash(password)
        try:
            with service.transaction(db()):
                cursor = db().execute(f'INSERT INTO shops({",".join(values)}) VALUES({",".join("?" for _ in values)})',tuple(values.values()))
                db().execute("INSERT INTO users(email,password,alias,role,shop_id,created_at) VALUES(?,?,?,'seller',?,unixepoch())",(address,hashed,'Seller-'+secrets.token_hex(4),cursor.lastrowid))
                service.audit(db(),g.user['id'],'seller_onboarded','shop',cursor.lastrowid,values['identity_note'])
        except sqlite3.IntegrityError:
            raise service.RuleError('Shop slug or email is already in use.',400)
        flash('Seller approved and account created. Share credentials privately outside this application.')
        return redirect(url_for('admin'))

    @app.post('/operator/action')
    @require('operator')
    def admin_action():
        kind = request.form.get('kind')
        entity_id, reason = integer('entity_id',1,10**12), text('reason',10,2000)
        tables = {'user':'users','shop':'shops','auction':'auctions','report':'reports'}
        if kind not in tables:
            abort(400)
        with service.transaction(db()):
            if not db().execute(f'SELECT id FROM {tables[kind]} WHERE id=?',(entity_id,)).fetchone():
                abort(404)
            if kind == 'user':
                if entity_id == g.user['id']:
                    raise service.RuleError('You cannot suspend your current operator account.',400)
                db().execute('UPDATE users SET suspended=1 WHERE id=?',(entity_id,))
            elif kind == 'shop':
                db().execute("UPDATE shops SET status='suspended' WHERE id=?",(entity_id,))
                # Settle all due lots before suspension; never erase an already earned award.
                for a in db().execute("SELECT * FROM auctions WHERE shop_id=? AND state='open'",(entity_id,)).fetchall():
                    service.settle_locked(db(),a,service.now(db()))
                db().execute("UPDATE auctions SET state='suspended' WHERE shop_id=? AND state IN ('open','draft')",(entity_id,))
            elif kind == 'auction':
                a=db().execute('SELECT * FROM auctions WHERE id=?',(entity_id,)).fetchone()
                if service.settle_locked(db(),a,service.now(db())) or a['state'] not in ('draft','open'):
                    raise service.RuleError('Closed or stopped listings retain their outcome. Document concerns through reports.')
                db().execute("UPDATE auctions SET state='suspended' WHERE id=?",(entity_id,))
            else:
                db().execute("UPDATE reports SET status='reviewed',resolution=? WHERE id=?",(reason,entity_id))
            service.audit(db(),g.user['id'],'operator_review' if kind=='report' else 'suspended',kind,entity_id,reason)
        flash('Action recorded. Suspended listings cannot reopen; retain records and review outside the live auction.')
        return redirect(url_for('admin'))

    @app.get('/policies')
    def policies():
        return render_template('policies.html')

    @app.cli.command('init-db')
    def init_db():
        service.migrate(app.config['DATABASE'])
        click.echo('Migration 001 applied (safe to repeat).')

    @app.cli.command('seed-demo')
    def seed_demo():
        if not app.config['DEMO_MODE']:
            raise click.ClickException('Synthetic seed is available only with DEMO_MODE=1.')
        from .seed import seed
        service.migrate(app.config['DATABASE'])
        seed(db())
        click.echo('Synthetic demo seeded. Password for all five demo accounts: Pilot-demo-2026!')

    @app.cli.command('close-auctions')
    def close_auctions():
        service.close_due(db())
        click.echo('Due auctions closed atomically.')

    app.config['DUMMY_HASH'] = generate_password_hash(secrets.token_urlsafe(24))
    return app
