import os
import sqlite3
import requests
import re 
import uuid
import time
import base64
from deep_translator import GoogleTranslator
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, g
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from google import genai
from google.genai import types

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

app = Flask(__name__)
app.secret_key = 'your_secret_key' 

app.config['UPLOAD_FOLDER'] = os.path.join('static', 'uploads')

if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

NAVER_CLIENT_ID = os.getenv("NAVER_CLIENT_ID");
NAVER_CLIENT_SECRET = os.getenv("NAVER_CLIENT_SECRET")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

gemini_client = None
if GOOGLE_API_KEY:
    try:
        gemini_client = genai.Client(api_key=GOOGLE_API_KEY)
        print(">>> Gemini Client Initialized.")
    except Exception as e:
        print(f">>> Gemini Client Init Error: {e}")
else:
    print(">>> Warning: Google API Key is missing.")

def classify_product(title):
    title = title.lower()
    if any(word in title for word in ['padding', 'coat', 'outer', 'jacket', 'vest', 'jumper', 'cardigan']):
        return 'Outer'
    elif any(word in title for word in ['top', 'shirt', 'tee', 'hoodie', 'sweatshirt', 'sleeveless']):
        return 'Top'
    elif any(word in title for word in ['dress', 'skirt', 'one-piece']):
        return 'Dress'
    elif any(word in title for word in ['all-in-one', 'bodysuit', 'romper', 'overall']):
        return 'All-in-one'
    elif any(word in title for word in ['hat', 'cap', 'scarf', 'ribbon', 'accessory', 'necklace', 'tie']):
        return 'Accessory'
    else:
        return 'Etc'

#Query changed to Korean ("강아지 옷") for Naver API accuracy
def fetch_naver_api_products(query="강아지 옷", display=20):
    if not NAVER_CLIENT_ID or not NAVER_CLIENT_SECRET or "Here" in NAVER_CLIENT_ID:
        return []
    url = "https://openapi.naver.com/v1/search/shop.json"
    headers = {"X-Naver-Client-Id": NAVER_CLIENT_ID, "X-Naver-Client-Secret": NAVER_CLIENT_SECRET}
    params = {"query": query, "display": display, "sort": "sim"}
    products = []
    translator = GoogleTranslator(source='ko', target='en')
    try:
        response = requests.get(url, headers=headers, params=params)
        if response.status_code == 200:
            items = response.json().get('items', [])
            sizes = ['S', 'M', 'L']
            for item in items:
                try:
                    raw_title = item['title']
                    clean_title = re.sub('<[^<]+?>', '', raw_title)
                    price = int(item['lprice'])
                    image_url = item['image']
                    brand = item.get('brand', '')
                    if not brand: brand = item.get('mallName', 'NaverStore')
                    
                    try:
                        eng_title = translator.translate(clean_title)
                        eng_brand = translator.translate(brand) if re.search('[a-zA-Z]', brand) is None else brand
                    except:
                        eng_title = clean_title
                        eng_brand = brand
                    
                    usd_price = round(price / 1300)
                    if usd_price < 1: usd_price = 1
                    
                    category = classify_product(eng_title)
                    size = sizes[len(clean_title) % 3]
                    description = "High-quality K-Pet fashion item sourced directly from Korea."
                    products.append((eng_title, usd_price, eng_brand, category, size, image_url, description))
                except: continue
    except: pass
    return products

def init_db():
    conn = sqlite3.connect('petshop.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, username TEXT, password TEXT, pet_name TEXT, pet_breed TEXT, pet_size TEXT, pet_image TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS pets (id INTEGER PRIMARY KEY, user_id INTEGER, name TEXT, breed TEXT, size TEXT, image TEXT, created_at INTEGER)''')
    c.execute('''CREATE TABLE IF NOT EXISTS products (id INTEGER PRIMARY KEY, name TEXT, price INTEGER, brand TEXT, category TEXT, image TEXT, description TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS cart_items (id INTEGER PRIMARY KEY, user_id INTEGER, product_id INTEGER, size TEXT, qty INTEGER, created_at INTEGER)''')
    c.execute('PRAGMA table_info(products)')
    product_columns = [row[1] for row in c.fetchall()]
    if 'size' not in product_columns:
        c.execute('ALTER TABLE products ADD COLUMN size TEXT')
    c.execute('PRAGMA table_info(users)')
    user_columns = [row[1] for row in c.fetchall()]
    if 'email' not in user_columns:
        c.execute('ALTER TABLE users ADD COLUMN email TEXT')
    c.execute('SELECT count(*) FROM products')
    if c.fetchone()[0] == 0:
        # [Modified] Using Korean query for initialization
        api_data = fetch_naver_api_products("강아지 옷", display=20)
        if api_data:
            c.executemany(
                'INSERT INTO products (name, price, brand, category, size, image, description) VALUES (?,?,?,?,?,?,?)',
                api_data
            )
            conn.commit()
    c.execute('UPDATE products SET size = ? WHERE size IS NULL OR size = ""', ('M',))

    # One-time migration: copy existing user pet profiles into pets table.
    c.execute('SELECT id, pet_name, pet_breed, pet_size, pet_image FROM users')
    users = c.fetchall()
    for user in users:
        user_id, pet_name, pet_breed, pet_size, pet_image = user
        if any([pet_name, pet_breed, pet_size, pet_image]):
            c.execute('SELECT count(*) FROM pets WHERE user_id = ?', (user_id,))
            if c.fetchone()[0] == 0:
                c.execute(
                    'INSERT INTO pets (user_id, name, breed, size, image, created_at) VALUES (?,?,?,?,?,?)',
                    (user_id, pet_name, pet_breed, pet_size, pet_image, int(time.time()))
                )
    conn.commit()
    conn.close()

init_db()

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect('petshop.db')
        db.row_factory = sqlite3.Row
    return db

def normalize_pet_size(size_text):
    if not size_text:
        return None
    match = re.search(r'(\d+(?:\.\d+)?)', size_text)
    if match:
        weight = float(match.group(1))
        if weight < 3:
            return 'S'
        if weight < 7:
            return 'M'
        return 'L'
    size_text = size_text.upper()
    if 'S' in size_text:
        return 'S'
    if 'M' in size_text:
        return 'M'
    if 'L' in size_text:
        return 'L'
    return None

def size_prompt_hint(size_bucket):
    if size_bucket == 'S':
        return "The clothing should look snug and compact."
    if size_bucket == 'M':
        return "The clothing should look balanced and true-to-size."
    if size_bucket == 'L':
        return "The clothing should look roomier with a relaxed fit."
    return ""

@app.context_processor
def inject_nav_pets():
    if 'user_id' not in session:
        return {'nav_pets': []}
    db = get_db()
    pets = db.execute(
        'SELECT * FROM pets WHERE user_id = ? ORDER BY created_at DESC, id DESC',
        (session['user_id'],)
    ).fetchall()
    return {'nav_pets': pets}

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

@app.route('/')
def index():
    category = request.args.get('category')
    db = get_db()
    if category and category != 'All':
        products = db.execute('SELECT * FROM products WHERE category = ?', (category,)).fetchall()
    else:
        products = db.execute('SELECT * FROM products').fetchall()
    return render_template('index.html', products=products, current_category=category)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = generate_password_hash(request.form['password'])
        pet_name = request.form.get('pet_name')
        pet_breed = request.form.get('pet_breed')
        pet_size = request.form.get('pet_size')
        
        pet_image_filename = None
        if 'pet_image' in request.files:
            file = request.files['pet_image']
            if file.filename != '':
                filename = secure_filename(file.filename)
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                pet_image_filename = filename

        db = get_db()
        cursor = db.execute(
            'INSERT INTO users (username, password, pet_name, pet_breed, pet_size, pet_image) VALUES (?, ?, ?, ?, ?, ?)',
            (username, password, pet_name, pet_breed, pet_size, pet_image_filename)
        )
        user_id = cursor.lastrowid
        if any([pet_name, pet_breed, pet_size, pet_image_filename]):
            db.execute(
                'INSERT INTO pets (user_id, name, breed, size, image, created_at) VALUES (?,?,?,?,?,?)',
                (user_id, pet_name, pet_breed, pet_size, pet_image_filename, int(time.time()))
            )
        db.commit()
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        db = get_db()
        user = db.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        
        if user and check_password_hash(user['password'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['pet_image'] = user['pet_image']
            return redirect(url_for('index'))
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/mypage')
def mypage():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    db = get_db()
    user = db.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],)).fetchone()
    if user is None:
        session.clear()
        return redirect(url_for('login'))

    pets = db.execute(
        'SELECT * FROM pets WHERE user_id = ? ORDER BY created_at DESC, id DESC',
        (session['user_id'],)
    ).fetchall()

    return render_template('mypage.html', user=user, pets=pets)

@app.route('/account/update', methods=['POST'])
def update_account():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    email = request.form.get('email')
    current_password = request.form.get('current_password')
    new_password = request.form.get('new_password')
    confirm_password = request.form.get('confirm_password')

    db = get_db()
    user = db.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],)).fetchone()
    if user is None:
        session.clear()
        return redirect(url_for('login'))

    if email is not None and email.strip() != '':
        db.execute('UPDATE users SET email = ? WHERE id = ?', (email.strip(), session['user_id']))

    if current_password and new_password and confirm_password:
        if new_password == confirm_password and check_password_hash(user['password'], current_password):
            new_hash = generate_password_hash(new_password)
            db.execute('UPDATE users SET password = ? WHERE id = ?', (new_hash, session['user_id']))

    db.commit()
    return redirect(url_for('mypage'))

@app.route('/pets/add', methods=['POST'])
def add_pet():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    pet_name = request.form.get('pet_name')
    pet_breed = request.form.get('pet_breed')
    pet_size = request.form.get('pet_size')
    pet_image_filename = None

    if 'pet_image' in request.files:
        file = request.files['pet_image']
        if file and file.filename != '':
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            pet_image_filename = filename

    if not pet_image_filename:
        return redirect(url_for('mypage'))

    if not any([pet_name, pet_breed, pet_size, pet_image_filename]):
        return redirect(url_for('mypage'))

    db = get_db()
    db.execute(
        'INSERT INTO pets (user_id, name, breed, size, image, created_at) VALUES (?,?,?,?,?,?)',
        (session['user_id'], pet_name, pet_breed, pet_size, pet_image_filename, int(time.time()))
    )
    db.commit()
    return redirect(url_for('mypage'))

@app.route('/pets/update/<int:pet_id>', methods=['POST'])
def update_pet(pet_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    pet_name = request.form.get('pet_name')
    pet_breed = request.form.get('pet_breed')
    pet_size = request.form.get('pet_size')
    pet_image_filename = None

    if 'pet_image' in request.files:
        file = request.files['pet_image']
        if file and file.filename != '':
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            pet_image_filename = filename

    db = get_db()
    pet = db.execute(
        'SELECT * FROM pets WHERE id = ? AND user_id = ?',
        (pet_id, session['user_id'])
    ).fetchone()
    if pet is None:
        return redirect(url_for('mypage'))

    update_fields = []
    update_params = []
    if pet_name is not None:
        update_fields.append('name = ?')
        update_params.append(pet_name)
    if pet_breed is not None:
        update_fields.append('breed = ?')
        update_params.append(pet_breed)
    if pet_size is not None:
        update_fields.append('size = ?')
        update_params.append(pet_size)
    if pet_image_filename:
        update_fields.append('image = ?')
        update_params.append(pet_image_filename)

    if update_fields:
        update_params.extend([pet_id, session['user_id']])
        db.execute(
            f'UPDATE pets SET {", ".join(update_fields)} WHERE id = ? AND user_id = ?',
            tuple(update_params)
        )
        db.commit()

    return redirect(url_for('mypage'))

@app.route('/pets/delete/<int:pet_id>', methods=['POST'])
def delete_pet(pet_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    db = get_db()
    db.execute(
        'DELETE FROM pets WHERE id = ? AND user_id = ?',
        (pet_id, session['user_id'])
    )
    db.commit()
    return redirect(url_for('mypage'))

@app.route('/product/<int:product_id>')
def product_detail(product_id):
    db = get_db()
    product = db.execute('SELECT * FROM products WHERE id = ?', (product_id,)).fetchone()
    return render_template('detail.html', product=product)

@app.route('/cart')
def cart():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    db = get_db()
    items = db.execute(
        '''
        SELECT c.id, c.size, c.qty, p.id AS product_id, p.name, p.price, p.image
        FROM cart_items c
        JOIN products p ON c.product_id = p.id
        WHERE c.user_id = ?
        ORDER BY c.created_at DESC, c.id DESC
        ''',
        (session['user_id'],)
    ).fetchall()

    total = sum(item['price'] * item['qty'] for item in items)
    return render_template('cart.html', items=items, total=total)

@app.route('/cart/add', methods=['POST'])
def cart_add():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    product_id = request.form.get('product_id')
    size = request.form.get('size', 'M').strip().upper()
    qty = request.form.get('qty', '1')

    try:
        qty = max(1, int(qty))
    except Exception:
        qty = 1

    if not product_id:
        return redirect(url_for('cart'))

    db = get_db()
    product = db.execute('SELECT id FROM products WHERE id = ?', (product_id,)).fetchone()
    if product is None:
        return redirect(url_for('cart'))

    existing = db.execute(
        'SELECT id, qty FROM cart_items WHERE user_id = ? AND product_id = ? AND size = ?',
        (session['user_id'], product_id, size)
    ).fetchone()

    if existing:
        db.execute(
            'UPDATE cart_items SET qty = ? WHERE id = ?',
            (existing['qty'] + qty, existing['id'])
        )
    else:
        db.execute(
            'INSERT INTO cart_items (user_id, product_id, size, qty, created_at) VALUES (?,?,?,?,?)',
            (session['user_id'], product_id, size, qty, int(time.time()))
        )
    db.commit()
    return redirect(url_for('cart'))

@app.route('/cart/update/<int:item_id>', methods=['POST'])
def cart_update(item_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    size = request.form.get('size', 'M').strip().upper()
    qty = request.form.get('qty', '1')

    try:
        qty = max(1, int(qty))
    except Exception:
        qty = 1

    db = get_db()
    db.execute(
        'UPDATE cart_items SET size = ?, qty = ? WHERE id = ? AND user_id = ?',
        (size, qty, item_id, session['user_id'])
    )
    db.commit()
    return redirect(url_for('cart'))

@app.route('/cart/remove/<int:item_id>', methods=['POST'])
def cart_remove(item_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))

    db = get_db()
    db.execute(
        'DELETE FROM cart_items WHERE id = ? AND user_id = ?',
        (item_id, session['user_id'])
    )
    db.commit()
    return redirect(url_for('cart'))

@app.route('/api/fit_clothing', methods=['POST'])
def fit_clothing():
    if 'user_id' not in session:
        return jsonify({'error': 'login_required', 'message': 'Please login first.'}), 401

    db = get_db()
    user_id = session['user_id']
    
    product_name = request.form.get('product_name', 'Stylish Dog Clothes')
    product_image_url = request.form.get('product_image_url') 
    product_size = request.form.get('product_size')
    
    selected_pet_id = request.form.get('pet_id')
    new_name = request.form.get('pet_name')
    new_breed = request.form.get('pet_breed')
    new_size = request.form.get('pet_size')
    new_image_file = request.files.get('user_image')

    new_image_filename = None
    if new_image_file and new_image_file.filename != '':
        filename = secure_filename(new_image_file.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        new_image_file.save(file_path)
        new_image_filename = filename

    pet = None
    if selected_pet_id:
        pet = db.execute(
            'SELECT * FROM pets WHERE id = ? AND user_id = ?',
            (selected_pet_id, user_id)
        ).fetchone()
    elif any([new_name, new_breed, new_size, new_image_filename]):
        db.execute(
            'INSERT INTO pets (user_id, name, breed, size, image, created_at) VALUES (?,?,?,?,?,?)',
            (user_id, new_name, new_breed, new_size, new_image_filename, int(time.time()))
        )
        db.commit()
        pet = db.execute(
            'SELECT * FROM pets WHERE user_id = ? ORDER BY created_at DESC, id DESC LIMIT 1',
            (user_id,)
        ).fetchone()
    else:
        pet = db.execute(
            'SELECT * FROM pets WHERE user_id = ? AND image IS NOT NULL AND image != "" ORDER BY created_at DESC, id DESC LIMIT 1',
            (user_id,)
        ).fetchone()
        if pet is None:
            pet = db.execute(
                'SELECT * FROM pets WHERE user_id = ? ORDER BY created_at DESC, id DESC LIMIT 1',
                (user_id,)
            ).fetchone()

    if pet is None or not pet['image']:
        return jsonify({'error': 'no_image', 'message': 'Pet profile or image missing.'}), 400

    pet_breed = pet['breed'] if pet['breed'] else 'Dog'
    pet_size = pet['size']
    pet_image_filename = pet['image']
    pet_size_bucket = normalize_pet_size(pet_size) if pet_size else None
    product_size_bucket = product_size.strip().upper() if product_size else None

    print(f">>> Multimodal Request: Breed={pet_breed}, Product={product_name}")
    generated_image_url = None
    
    if gemini_client and product_image_url:
        try:
            pet_image_path = os.path.join(app.config['UPLOAD_FOLDER'], pet_image_filename)
            with open(pet_image_path, "rb") as f:
                pet_image_data = f.read()
            
            product_response = requests.get(product_image_url)
            product_image_data = product_response.content

            size_context = []
            if pet_size_bucket:
                size_context.append(f"pet size {pet_size_bucket}")
            if product_size_bucket:
                size_context.append(f"clothing size {product_size_bucket}")
            size_line = f" The fitting should reflect {', '.join(size_context)}." if size_context else ""
            fit_hint = size_prompt_hint(product_size_bucket)
            fit_line = f" {fit_hint}" if fit_hint else ""

            prompt_text = (
                f"Based on the provided images, create a realistic photograph of the {pet_breed} dog "
                f"wearing the clothing item shown in the product image."
                f"{size_line}{fit_line} The dog should be in a natural pose. High quality, detailed texture."
            )

            contents = [
                prompt_text,
                types.Part.from_bytes(data=pet_image_data, mime_type="image/jpeg"),
                types.Part.from_bytes(data=product_image_data, mime_type="image/jpeg")
            ]

            response = gemini_client.models.generate_content(
                model='gemini-3-pro-image-preview', 
                contents=contents,
                config=types.GenerateContentConfig(
                    response_modalities=["TEXT", "IMAGE"]
                )
            )
            
            if response.candidates and response.candidates[0].content.parts:
                for part in response.candidates[0].content.parts:
                    if part.inline_data:
                        raw_data = part.inline_data.data
                        image_bytes = None

                        if isinstance(raw_data, bytes):
                            image_bytes = raw_data
                        elif isinstance(raw_data, str):
                            image_bytes = base64.b64decode(raw_data)
                        
                        if image_bytes:
                            mime_type = part.inline_data.mime_type
                            ext = ".png"
                            
                            if "jpeg" in mime_type or "jpg" in mime_type:
                                ext = ".jpg"
                            elif "webp" in mime_type:
                                ext = ".webp"
                            
                            unique_filename = f"gemini_multi_{uuid.uuid4().hex[:8]}{ext}"
                            
                            save_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
                            with open(save_path, "wb") as f:
                                f.write(image_bytes)
                                
                            generated_image_url = f"/static/uploads/{unique_filename}"
                            print(f">>> Generated & Saved ({ext}): {generated_image_url}")
                            break
        
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f">>> Gemini Multimodal Error: {e}")
            pass
            
    if generated_image_url:
        message = f"AI has synthesized the look based on your photos!"
    else:
        time.sleep(1)
        generated_image_url = "https://images.unsplash.com/photo-1583337130417-3346a1be7dee?w=600"
        message = "Demo Mode: AI processing failed or timed out."

    return jsonify({
        'success': True,
        'result_image': generated_image_url,
        'message': message
    })

if __name__ == '__main__':
    app.run(debug=True, port=5000)
