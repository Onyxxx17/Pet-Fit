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

app = Flask(__name__)
app.secret_key = 'your_secret_key' 

app.config['UPLOAD_FOLDER'] = os.path.join('static', 'uploads')

if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

NAVER_CLIENT_ID = "Js36ALdCTg6fZ8v8T78g"
NAVER_CLIENT_SECRET = "vsvGv1iGyZ"
GOOGLE_API_KEY = "google api"

gemini_client = None
if "AIza" in GOOGLE_API_KEY:
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
    if "Here" in NAVER_CLIENT_ID:
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
                    description = "High-quality K-Pet fashion item sourced directly from Korea."
                    products.append((eng_title, usd_price, eng_brand, category, image_url, description))
                except: continue
    except: pass
    return products

def init_db():
    conn = sqlite3.connect('petshop.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, username TEXT, password TEXT, pet_name TEXT, pet_breed TEXT, pet_size TEXT, pet_image TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS products (id INTEGER PRIMARY KEY, name TEXT, price INTEGER, brand TEXT, category TEXT, image TEXT, description TEXT)''')
    c.execute('SELECT count(*) FROM products')
    if c.fetchone()[0] == 0:
        # [Modified] Using Korean query for initialization
        api_data = fetch_naver_api_products("강아지 옷", display=20)
        if api_data:
            c.executemany('INSERT INTO products (name, price, brand, category, image, description) VALUES (?,?,?,?,?,?)', api_data)
            conn.commit()
    conn.close()

init_db()

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect('petshop.db')
        db.row_factory = sqlite3.Row
    return db

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
        db.execute('INSERT INTO users (username, password, pet_name, pet_breed, pet_size, pet_image) VALUES (?, ?, ?, ?, ?, ?)',
                   (username, password, pet_name, pet_breed, pet_size, pet_image_filename))
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

@app.route('/product/<int:product_id>')
def product_detail(product_id):
    db = get_db()
    product = db.execute('SELECT * FROM products WHERE id = ?', (product_id,)).fetchone()
    return render_template('detail.html', product=product)

@app.route('/api/fit_clothing', methods=['POST'])
def fit_clothing():
    if 'user_id' not in session:
        return jsonify({'error': 'login_required', 'message': 'Please login first.'}), 401

    db = get_db()
    user_id = session['user_id']
    
    product_name = request.form.get('product_name', 'Stylish Dog Clothes')
    product_image_url = request.form.get('product_image_url') 
    
    new_breed = request.form.get('pet_breed')
    new_size = request.form.get('pet_size')
    new_image_file = request.files.get('user_image')

    update_query = "UPDATE users SET "
    update_params = []
    
    if new_breed:
        update_query += "pet_breed = ?, "
        update_params.append(new_breed)
    if new_size:
        update_query += "pet_size = ?, "
        update_params.append(new_size)
    if new_image_file and new_image_file.filename != '':
        filename = secure_filename(new_image_file.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        new_image_file.save(file_path)
        update_query += "pet_image = ?, "
        update_params.append(filename)
        session['pet_image'] = filename 
        
    if update_params:
        update_query = update_query.rstrip(', ') + " WHERE id = ?"
        update_params.append(user_id)
        try:
            db.execute(update_query, tuple(update_params))
            db.commit()
        except Exception as e:
            print(f">>> DB Update Error: {e}")

    user = db.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
    if user is None or not user['pet_image']:
        return jsonify({'error': 'no_image', 'message': 'Pet profile or image missing.'}), 400

    pet_breed = user['pet_breed'] if user['pet_breed'] else 'Dog'
    pet_image_filename = user['pet_image']

    print(f">>> Multimodal Request: Breed={pet_breed}, Product={product_name}")
    generated_image_url = None
    
    if gemini_client and product_image_url:
        try:
            pet_image_path = os.path.join(app.config['UPLOAD_FOLDER'], pet_image_filename)
            with open(pet_image_path, "rb") as f:
                pet_image_data = f.read()
            
            product_response = requests.get(product_image_url)
            product_image_data = product_response.content

            prompt_text = (
                f"Based on the provided images, create a realistic photograph of the {pet_breed} dog "
                f"wearing the clothing item shown in the product image. "
                "The dog should be in a natural pose. High quality, detailed texture."
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