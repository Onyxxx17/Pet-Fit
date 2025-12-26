import os
import re
import uuid
import base64
import time
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
import psycopg2
from psycopg2.extras import RealDictCursor
from google import genai
from google.genai import types
from deep_translator import GoogleTranslator
import requests

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'your_secret_key_change_in_production')
app.config['UPLOAD_FOLDER'] = os.path.join('static', 'uploads')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max

if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

# Database connection
DATABASE_URL = os.environ.get('DATABASE_URL')
if not DATABASE_URL:
    print("WARNING: DATABASE_URL not set. Please set it to your Neon PostgreSQL connection string.")
    DATABASE_URL = "postgresql://user:pass@host/db"  # Placeholder

# API Keys
NAVER_CLIENT_ID = os.environ.get('NAVER_CLIENT_ID', 'Js36ALdCTg6fZ8v8T78g')
NAVER_CLIENT_SECRET = os.environ.get('NAVER_CLIENT_SECRET', 'vsvGv1iGyZ')
GOOGLE_API_KEY = os.environ.get('GOOGLE_API_KEY', '')
GEMINI_IMAGE_MODEL = os.environ.get('GEMINI_IMAGE_MODEL', 'gemini-2.5-flash-image')

gemini_client = None
if GOOGLE_API_KEY and "AIza" in GOOGLE_API_KEY:
    try:
        gemini_client = genai.Client(api_key=GOOGLE_API_KEY)
        print(">>> Gemini Client Initialized.")
    except Exception as e:
        print(f">>> Gemini Client Init Error: {e}")
else:
    print(">>> Warning: Google API Key is missing or invalid.")


# =======================
# Database helper functions
# =======================
def get_db():
    """Get database connection"""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    except Exception as e:
        print(f"Database connection error: {e}")
        raise


def init_db():
    """Initialize database with schema"""
    try:
        conn = get_db()
        with conn.cursor() as cur:
            with open('db/schema_postgres.sql', 'r') as f:
                cur.execute(f.read())
        conn.commit()
        conn.close()
        print(">>> Database initialized successfully")
    except Exception as e:
        print(f">>> Database initialization error: {e}")
        raise


# =======================
# Product Classification
# =======================
def classify_product(title):
    """Classify product based on title"""
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


def assign_weather_tag(category, title):
    """Assign weather tag based on product category and title"""
    title_lower = title.lower()
    if category == 'Outer' or 'winter' in title_lower or 'warm' in title_lower:
        return 'cold'
    elif 'rain' in title_lower or 'waterproof' in title_lower:
        return 'rain'
    else:
        return 'all-season'


def assign_style_tag(title):
    """Assign style tag based on title"""
    title_lower = title.lower()
    if any(word in title_lower for word in ['sport', 'athletic', 'active']):
        return 'sport'
    elif any(word in title_lower for word in ['street', 'urban', 'cool']):
        return 'street'
    else:
        return 'classic'


# =======================
# Naver API Integration
# =======================
def fetch_naver_api_products(query="강아지 옷", display=20):
    """Fetch products from Naver Shopping API"""
    if not NAVER_CLIENT_ID or not NAVER_CLIENT_SECRET:
        return []
    
    url = "https://openapi.naver.com/v1/search/shop.json"
    headers = {
        "X-Naver-Client-Id": NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": NAVER_CLIENT_SECRET
    }
    params = {"query": query, "display": display, "sort": "sim"}
    products = []
    translator = GoogleTranslator(source='ko', target='en')
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=10)
        if response.status_code == 200:
            items = response.json().get('items', [])
            for item in items:
                try:
                    raw_title = item['title']
                    clean_title = re.sub('<[^<]+?>', '', raw_title)
                    price = int(item['lprice'])
                    image_url = item['image']
                    brand = item.get('brand', '') or item.get('mallName', 'NaverStore')
                    
                    try:
                        eng_title = translator.translate(clean_title)
                        eng_brand = translator.translate(brand) if not re.search('[a-zA-Z]', brand) else brand
                    except:
                        eng_title = clean_title
                        eng_brand = brand
                    
                    usd_price = round(price / 1300)
                    if usd_price < 1:
                        usd_price = 1
                    
                    category = classify_product(eng_title)
                    weather_tag = assign_weather_tag(category, eng_title)
                    style_tag = assign_style_tag(eng_title)
                    description = "High-quality K-Pet fashion item sourced directly from Korea."
                    
                    products.append({
                        'name': eng_title,
                        'price': usd_price,
                        'brand': eng_brand,
                        'category': category,
                        'image_url': image_url,
                        'description': description,
                        'weather_tag': weather_tag,
                        'style_tag': style_tag
                    })
                except:
                    continue
    except:
        pass
    
    return products


# =======================
# Recommendation Engine - Score-Based Formula
# =======================
def calculate_fit_score(pet_chest, pet_back, pet_neck, product_chest, product_back, product_neck):
    """
    Calculate fit score based on size matching.
    Smaller difference = higher score.
    Formula: 1 - (total_diff / max_possible_diff)
    """
    chest_diff = abs(float(pet_chest) - float(product_chest))
    back_diff = abs(float(pet_back) - float(product_back))
    
    # Neck is optional
    if pet_neck and product_neck:
        neck_diff = abs(float(pet_neck) - float(product_neck))
        total_diff = chest_diff + back_diff + neck_diff
        max_possible = 30  # Arbitrary max difference
    else:
        total_diff = chest_diff + back_diff
        max_possible = 20
    
    # Normalize to 0-1 scale (1 = perfect fit, 0 = worst fit)
    fit_score = max(0, 1 - (total_diff / max_possible))
    return fit_score


def calculate_weather_score(pet_weather_pref='all-season', product_weather_tag='all-season'):
    """
    Calculate weather score based on pet preference and product weather tag.
    Perfect match = 1.0, all-season = 0.8, no match = 0.5
    """
    if not pet_weather_pref or not product_weather_tag:
        return 0.5
    
    # Perfect match
    if pet_weather_pref == product_weather_tag:
        return 1.0
    
    # All-season products work for everyone
    if product_weather_tag == 'all-season' or pet_weather_pref == 'all-season':
        return 0.8
    
    # No match
    return 0.5


def calculate_style_score(pet_style_pref='any', product_style='classic'):
    """
    Calculate style score based on pet preference and product style.
    Perfect match = 1.0, 'any' preference = 0.7, no match = 0.5
    """
    if not pet_style_pref or not product_style:
        return 0.5
    
    # Pet owner doesn't care about style
    if pet_style_pref == 'any':
        return 0.7
    
    # Perfect match
    if pet_style_pref == product_style:
        return 1.0
    
    # No match
    return 0.5


def calculate_price_score(price_cents):
    """
    Calculate price score.
    Lower price = higher score (budget-friendly)
    Normalized: max price assumed at $100
    """
    max_price = 10000  # $100 in cents
    normalized = min(price_cents, max_price) / max_price
    return 1 - normalized  # Invert: lower price = higher score


def calculate_popularity_score(popularity):
    """
    Return popularity score (already normalized 0-1)
    """
    return float(popularity)


def get_pet_estimated_dimensions(pet_data, breed_data):
    """
    Estimate pet dimensions based on breed and weight.
    
    Formula:
    - If weight provided: estimated_size = avg_breed_size * (dog_weight / avg_breed_weight)
    - If no weight: use average breed size
    """
    if not breed_data or not breed_data.get('avg_chest_cm'):
        # Default dimensions for unknown breed
        return {
            'chest_cm': 40,
            'back_cm': 32,
            'neck_cm': 28
        }
    
    avg_chest = float(breed_data['avg_chest_cm'] or 40)
    avg_back = float(breed_data['avg_back_cm'] or 32)
    avg_neck = float(breed_data['avg_neck_cm'] or 28)
    avg_weight = float(breed_data['avg_weight_kg'] or 5)
    
    if pet_data.get('weight_kg'):
        pet_weight = float(pet_data['weight_kg'])
        weight_ratio = pet_weight / avg_weight
        
        estimated_chest = avg_chest * weight_ratio
        estimated_back = avg_back * weight_ratio
        estimated_neck = avg_neck * weight_ratio
    else:
        estimated_chest = avg_chest
        estimated_back = avg_back
        estimated_neck = avg_neck
    
    return {
        'chest_cm': estimated_chest,
        'back_cm': estimated_back,
        'neck_cm': estimated_neck
    }


def generate_recommendations(pet_id, top_n=3):
    """
    Generate top N product recommendations for a pet using score-based formula.
    
    Formula:
    total_score = 0.55*fit + 0.20*weather + 0.15*style + 0.05*price + 0.05*popularity
    """
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    # Get pet data with breed info
    cur.execute("""
        SELECT p.*, b.name as breed_name, b.avg_weight_kg, b.avg_chest_cm, 
               b.avg_back_cm, b.avg_neck_cm
        FROM pets p
        LEFT JOIN breeds b ON p.breed_id = b.id
        WHERE p.id = %s
    """, (pet_id,))
    pet_data = cur.fetchone()
    
    if not pet_data:
        cur.close()
        conn.close()
        return []
    
    # Get estimated dimensions
    breed_data = {
        'avg_weight_kg': pet_data.get('avg_weight_kg'),
        'avg_chest_cm': pet_data.get('avg_chest_cm'),
        'avg_back_cm': pet_data.get('avg_back_cm'),
        'avg_neck_cm': pet_data.get('avg_neck_cm')
    }
    
    pet_dimensions = get_pet_estimated_dimensions(pet_data, breed_data)
    
    # Get all active products with their sizes
    cur.execute("""
        SELECT p.id as product_id, p.name, p.brand, p.category, p.description,
               p.base_price_cents, p.weather_tag, p.style_tag, p.popularity_score,
               ps.id as size_id, ps.label as size_label, ps.chest_cm, ps.back_cm, ps.neck_cm,
               ps.weight_min_kg, ps.weight_max_kg
        FROM products p
        JOIN product_sizes ps ON p.id = ps.product_id
        WHERE p.active = TRUE
        ORDER BY p.id, ps.label
    """)
    products = cur.fetchall()
    
    # Calculate scores for each product-size combination
    scored_products = []
    
    # Get pet preferences
    pet_weather_pref = pet_data.get('weather_preference') or 'all-season'
    pet_style_pref = pet_data.get('style_preference') or 'any'
    pet_weight = pet_data.get('weight_kg')
    
    for product in products:
        # Calculate individual scores
        fit_score = calculate_fit_score(
            pet_dimensions['chest_cm'],
            pet_dimensions['back_cm'],
            pet_dimensions['neck_cm'],
            product['chest_cm'],
            product['back_cm'],
            product['neck_cm']
        )

        # Weight-based fit boost for better per-pet differentiation
        weight_score = 0.5
        if pet_weight and (product.get('weight_min_kg') or product.get('weight_max_kg')):
            min_w = float(product.get('weight_min_kg') or pet_weight)
            max_w = float(product.get('weight_max_kg') or pet_weight)
            pet_w = float(pet_weight)
            if min_w <= pet_w <= max_w:
                weight_score = 1.0
            else:
                band = max(1.0, max_w - min_w)
                dist = min(abs(pet_w - min_w), abs(pet_w - max_w))
                weight_score = max(0.1, 1 - (dist / band))
        fit_score = (0.7 * fit_score) + (0.3 * weight_score)
        
        weather_score = calculate_weather_score(pet_weather_pref, product['weather_tag'])
        style_score = calculate_style_score(pet_style_pref, product['style_tag'])
        price_score = calculate_price_score(product['base_price_cents'])
        popularity_score = calculate_popularity_score(product['popularity_score'])
        
        # Apply formula: 0.55*fit + 0.20*weather + 0.15*style + 0.05*price + 0.05*popularity
        total_score = (
            0.55 * fit_score +
            0.20 * weather_score +
            0.15 * style_score +
            0.05 * price_score +
            0.05 * popularity_score
        )
        
        scored_products.append({
            'product_id': product['product_id'],
            'size_id': product['size_id'],
            'name': product['name'],
            'brand': product['brand'],
            'category': product['category'],
            'description': product['description'],
            'price': product['base_price_cents'] / 100,  # Convert to dollars
            'size_label': product['size_label'],
            'total_score': total_score,
            'fit_score': fit_score,
            'weather_score': weather_score,
            'style_score': style_score,
            'price_score': price_score,
            'popularity_score': popularity_score,
            'chest_cm': float(product['chest_cm']),
            'back_cm': float(product['back_cm']),
            'neck_cm': float(product['neck_cm']) if product['neck_cm'] else None
        })
    
    # Sort by total score and get top N with unique categories
    scored_products.sort(key=lambda x: x['total_score'], reverse=True)
    top_recommendations = []
    seen_categories = set()
    for rec in scored_products:
        if rec['category'] in seen_categories:
            continue
        top_recommendations.append(rec)
        seen_categories.add(rec['category'])
        if len(top_recommendations) >= top_n:
            break
    
    # Log recommendations
    user_id = pet_data['user_id']
    for rec in top_recommendations:
        cur.execute("""
            INSERT INTO recommendation_logs 
            (user_id, pet_id, product_id, product_size_id, score_total, 
             score_fit, score_weather, score_style, score_price, score_popularity)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (user_id, pet_id, rec['product_id'], rec['size_id'], 
              rec['total_score'], rec['fit_score'], rec['weather_score'],
              rec['style_score'], rec['price_score'], rec['popularity_score']))
    
    conn.commit()
    cur.close()
    conn.close()
    
    return top_recommendations


# =======================
# Routes
# =======================
@app.route('/')
def index():
    """Home page - show products"""
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    category = request.args.get('category')
    sort = request.args.get('sort')
    search_query = request.args.get('q', '').strip()
    
    # Build base query with search
    if search_query:
        search_pattern = f"%{search_query}%"
        if category and category != 'All':
            cur.execute("""
                SELECT DISTINCT ON (p.id) p.*, ps.label as size_label
                FROM products p
                LEFT JOIN product_sizes ps ON p.id = ps.product_id
                WHERE p.active = TRUE 
                    AND p.category = %s
                    AND (p.name ILIKE %s OR p.brand ILIKE %s OR p.description ILIKE %s)
                ORDER BY p.id, p.created_at DESC
                LIMIT 20
            """, (category, search_pattern, search_pattern, search_pattern))
        else:
            cur.execute("""
                SELECT DISTINCT ON (p.id) p.*, ps.label as size_label
                FROM products p
                LEFT JOIN product_sizes ps ON p.id = ps.product_id
                WHERE p.active = TRUE 
                    AND (p.name ILIKE %s OR p.brand ILIKE %s OR p.description ILIKE %s)
                ORDER BY p.id, p.created_at DESC
                LIMIT 20
            """, (search_pattern, search_pattern, search_pattern))
    elif category and category != 'All':
        cur.execute("""
            SELECT DISTINCT ON (p.id) p.*, ps.label as size_label
            FROM products p
            LEFT JOIN product_sizes ps ON p.id = ps.product_id
            WHERE p.active = TRUE AND p.category = %s
            ORDER BY p.id, p.created_at DESC
            LIMIT 20
        """, (category,))
    else:
        if sort == 'best':
            cur.execute("""
                SELECT DISTINCT ON (p.id) p.*, ps.label as size_label
                FROM products p
                LEFT JOIN product_sizes ps ON p.id = ps.product_id
                WHERE p.active = TRUE
                ORDER BY p.id, p.popularity_score DESC NULLS LAST, p.created_at DESC
                LIMIT 20
            """)
        else:
            cur.execute("""
                SELECT DISTINCT ON (p.id) p.*, ps.label as size_label
                FROM products p
                LEFT JOIN product_sizes ps ON p.id = ps.product_id
                WHERE p.active = TRUE
                ORDER BY p.id, p.created_at DESC
                LIMIT 20
            """)
    
    products = cur.fetchall()

    cur.execute("""
        SELECT p.id, p.name, p.brand
        FROM products p
        WHERE p.active = TRUE
        ORDER BY p.created_at DESC
        LIMIT 5
    """)
    featured_products = cur.fetchall()

    cur.close()
    conn.close()
    
    # Convert price to dollars
    for p in products:
        p['price'] = p['base_price_cents'] / 100
    
    return render_template(
        'index.html',
        products=products,
        current_category=category,
        featured_products=featured_products,
        search_query=search_query
    )


@app.route('/register', methods=['GET', 'POST'])
def register():
    """User registration"""
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        
        if not username or not password:
            flash('Username and password are required', 'error')
            return redirect(url_for('register'))
        
        if len(password) < 6:
            flash('Password must be at least 6 characters', 'error')
            return redirect(url_for('register'))
        
        conn = get_db()
        cur = conn.cursor()
        
        try:
            password_hash = generate_password_hash(password)
            cur.execute(
                "INSERT INTO users (username, email, password_hash) VALUES (%s, %s, %s)",
                (username, email, password_hash)
            )
            conn.commit()
            cur.close()
            conn.close()
            flash('Registration successful! Please login.', 'success')
            return redirect(url_for('login'))
        except psycopg2.IntegrityError:
            conn.rollback()
            cur.close()
            conn.close()
            flash('Username or email already exists', 'error')
            return redirect(url_for('register'))
        except Exception as e:
            conn.rollback()
            cur.close()
            conn.close()
            flash(f'Registration failed: {str(e)}', 'error')
            return redirect(url_for('register'))
    
    return render_template('register.html')
    
    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    """User login"""
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        conn = get_db()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        cur.execute("SELECT * FROM users WHERE username = %s", (username,))
        user = cur.fetchone()
        
        cur.close()
        conn.close()
        
        if user and check_password_hash(user['password_hash'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            flash('Login successful!', 'success')
            return redirect(url_for('mypage'))
        else:
            flash('Invalid username or password', 'error')
    
    return render_template('login.html')


@app.route('/logout')
def logout():   
    """User logout"""
    session.clear()
    flash('Logged out successfully', 'success')
    return redirect(url_for('index'))


@app.route('/pet_image/<int:pet_id>')
def pet_image(pet_id):
    """Serve pet image from database"""
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    cur.execute("SELECT image_data, image_mime_type FROM pets WHERE id = %s", (pet_id,))
    result = cur.fetchone()
    
    cur.close()
    conn.close()
    
    if result and result['image_data']:
        from flask import Response
        return Response(bytes(result['image_data']), mimetype=result['image_mime_type'] or 'image/jpeg')
    else:
        # Return a placeholder image
        return redirect('/static/placeholder-pet.png')


@app.route('/product_image/<int:product_id>')
def product_image(product_id):
    """Serve product image from database"""
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    cur.execute("SELECT image_data, image_mime_type FROM products WHERE id = %s", (product_id,))
    result = cur.fetchone()
    
    cur.close()
    conn.close()
    
    if result and result['image_data']:
        from flask import Response
        return Response(bytes(result['image_data']), mimetype=result['image_mime_type'] or 'image/jpeg')
    else:
        # For products without images, try to show from URL if exists
        return redirect('/static/placeholder-product.png')


@app.route('/mypage')
def mypage():
    """User's page showing their pets"""
    if 'user_id' not in session:
        flash('Please login first', 'error')
        return redirect(url_for('login'))
    
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    # Get user info
    cur.execute("SELECT * FROM users WHERE id = %s", (session['user_id'],))
    user = cur.fetchone()
    
    # Get user's pets
    cur.execute("""
        SELECT p.*, b.name as breed_name
        FROM pets p
        LEFT JOIN breeds b ON p.breed_id = b.id
        WHERE p.user_id = %s
        ORDER BY p.created_at DESC
    """, (session['user_id'],))
    pets = cur.fetchall()
    
    # Get all breeds for the dropdown
    cur.execute("SELECT * FROM breeds ORDER BY name")
    breeds = cur.fetchall()
    
    cur.close()
    conn.close()
    
    return render_template('mypage.html', user=user, pets=pets, breeds=breeds)


@app.route('/account/update', methods=['POST'])
def account_update():
    """Update user account details"""
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    # Get current user
    cur.execute("SELECT * FROM users WHERE id = %s", (session['user_id'],))
    user = cur.fetchone()
    
    if not user:
        cur.close()
        conn.close()
        return redirect(url_for('login'))
    
    email = request.form.get('email')
    current_password = request.form.get('current_password')
    new_password = request.form.get('new_password')
    confirm_password = request.form.get('confirm_password')
    
    updates = []
    params = []
    
    # Update email
    if email:
        updates.append('email = %s')
        params.append(email)
    
    # Update password
    if current_password and new_password and new_password == confirm_password:
        if check_password_hash(user['password_hash'], current_password):
            updates.append('password_hash = %s')
            params.append(generate_password_hash(new_password))
            flash('Password updated successfully!', 'success')
        else:
            flash('Current password is incorrect', 'error')
            cur.close()
            conn.close()
            return redirect(url_for('mypage'))
    
    if updates:
        params.append(session['user_id'])
        cur.execute(f"UPDATE users SET {', '.join(updates)} WHERE id = %s", tuple(params))
        conn.commit()
        flash('Account updated successfully!', 'success')
    
    cur.close()
    conn.close()
    return redirect(url_for('mypage'))


@app.route('/pets/add', methods=['GET', 'POST'])
def add_pet():
    """Create a new pet profile"""
    if 'user_id' not in session:
        flash('Please login first', 'error')
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        name = request.form.get('pet_name') or request.form.get('name')
        breed_id = request.form.get('breed_id')
        weight_kg = request.form.get('weight_kg')
        size_label = request.form.get('size_label') or request.form.get('pet_size')
        weather_pref = request.form.get('weather_preference') or 'all-season'
        style_pref = request.form.get('style_preference') or 'any'
        
        # Handle image upload - store in database
        image_data = None
        mime_type = None
        
        if 'pet_image' in request.files:
            file = request.files['pet_image']
            if file and file.filename:
                image_data = file.read()
                mime_type = file.content_type or 'image/jpeg'
        
        conn = get_db()
        cur = conn.cursor()
        
        try:
            cur.execute("""
                INSERT INTO pets (user_id, name, breed_id, weight_kg, size_label, 
                                  weather_preference, style_preference, image_data, image_mime_type)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (session['user_id'], name, breed_id or None, 
                  weight_kg or None, size_label, weather_pref, style_pref,
                  psycopg2.Binary(image_data) if image_data else None, 
                  mime_type))
            
            pet_id = cur.fetchone()[0]
            conn.commit()
            flash('Pet profile created successfully!', 'success')
            return redirect(url_for('mypage'))
        except Exception as e:
            conn.rollback()
            flash(f'Error creating pet: {str(e)}', 'error')
        finally:
            cur.close()
            conn.close()
    
    # GET request - show form with breeds
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM breeds ORDER BY name")
    breeds = cur.fetchall()
    cur.close()
    conn.close()
    
    return render_template('create_pet.html', breeds=breeds)


@app.route('/pets/update/<int:pet_id>', methods=['POST'])
def update_pet(pet_id):
    """Update pet profile"""
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    # Verify ownership
    cur.execute("SELECT * FROM pets WHERE id = %s AND user_id = %s", (pet_id, session['user_id']))
    if not cur.fetchone():
        flash('Pet not found', 'error')
        cur.close()
        conn.close()
        return redirect(url_for('mypage'))
    
    updates = []
    params = []
    
    name = request.form.get('pet_name')
    breed_id = request.form.get('breed_id')
    weight_kg = request.form.get('weight_kg')
    size_label = request.form.get('pet_size')
    weather_pref = request.form.get('weather_preference')
    style_pref = request.form.get('style_preference')
    
    if name:
        updates.append('name = %s')
        params.append(name)
    if breed_id:
        updates.append('breed_id = %s')
        params.append(breed_id)
    if weight_kg:
        updates.append('weight_kg = %s')
        params.append(weight_kg)
    if size_label:
        updates.append('size_label = %s')
        params.append(size_label)
    if weather_pref:
        updates.append('weather_preference = %s')
        params.append(weather_pref)
    if style_pref:
        updates.append('style_preference = %s')
        params.append(style_pref)
    
    # Handle image - store in database
    if 'pet_image' in request.files:
        file = request.files['pet_image']
        if file and file.filename:
            image_data = file.read()
            mime_type = file.content_type or 'image/jpeg'
            updates.append('image_data = %s')
            params.append(psycopg2.Binary(image_data))
            updates.append('image_mime_type = %s')
            params.append(mime_type)
    
    if updates:
        params.append(pet_id)
        cur.execute(f"UPDATE pets SET {', '.join(updates)} WHERE id = %s", tuple(params))
        conn.commit()
        flash('Pet updated successfully!', 'success')
    
    cur.close()
    conn.close()
    return redirect(url_for('mypage'))


@app.route('/pets/delete/<int:pet_id>', methods=['POST'])
def delete_pet(pet_id):
    """Delete pet profile"""
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    conn = get_db()
    cur = conn.cursor()
    cur.execute('DELETE FROM pets WHERE id = %s AND user_id = %s', (pet_id, session['user_id']))
    conn.commit()
    cur.close()
    conn.close()
    
    flash('Pet deleted successfully', 'success')
    return redirect(url_for('mypage'))


@app.route('/recommendations', methods=['GET', 'POST'])
def recommendations():
    """Generate recommendations for a pet"""
    if 'user_id' not in session:
        flash('Please login first', 'error')
        return redirect(url_for('login'))
    
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    # Get user's pets
    cur.execute("""
        SELECT p.*, b.name as breed_name
        FROM pets p
        LEFT JOIN breeds b ON p.breed_id = b.id
        WHERE p.user_id = %s
    """, (session['user_id'],))
    pets = cur.fetchall()
    
    cur.close()
    conn.close()
    
    if not pets:
        flash('Please create a pet profile first!', 'error')
        return redirect(url_for('add_pet'))
    
    selected_pet_id = request.values.get('pet_id')
    selected_pet = None
    recs = []
    
    if selected_pet_id:
        selected_pet = next((p for p in pets if str(p['id']) == str(selected_pet_id)), None)
        if selected_pet:
            recs = generate_recommendations(int(selected_pet_id), top_n=3)
    elif len(pets) == 1:
        selected_pet = pets[0]
        recs = generate_recommendations(pets[0]['id'], top_n=3)
    
    return render_template('recommendations.html', 
                         pets=pets,
                         selected_pet=selected_pet,
                         recommendations=recs)


@app.route('/product/<int:product_id>')
def product_detail(product_id):
    """Product detail page"""
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    cur.execute("SELECT * FROM products WHERE id = %s", (product_id,))
    product = cur.fetchone()
    
    recommended_size = None
    user_pets = []
    selected_pet = None
    
    if product:
        product['price'] = product['base_price_cents'] / 100
        
        # Get sizes with proper ordering
        cur.execute("""
            SELECT * FROM product_sizes 
            WHERE product_id = %s 
            ORDER BY 
                CASE label
                    WHEN 'XXS' THEN 1
                    WHEN 'XS' THEN 2
                    WHEN 'S' THEN 3
                    WHEN 'M' THEN 4
                    WHEN 'L' THEN 5
                    WHEN 'XL' THEN 6
                    WHEN 'XXL' THEN 7
                    ELSE 8
                END
        """, (product_id,))
        sizes = cur.fetchall()
        product['sizes'] = sizes
        
        # Get all user's pets
        if 'user_id' in session:
            cur.execute("""
                SELECT p.*, b.name as breed_name, b.avg_weight_kg, b.avg_chest_cm, b.avg_back_cm, b.avg_neck_cm
                FROM pets p
                LEFT JOIN breeds b ON p.breed_id = b.id
                WHERE p.user_id = %s
                ORDER BY p.created_at DESC
            """, (session['user_id'],))
            user_pets = cur.fetchall()
            
            # Check if pet_id is in query params for recommendation
            pet_id = request.args.get('pet_id')
            
            if pet_id:
                selected_pet = next((p for p in user_pets if p['id'] == int(pet_id)), None)
            elif len(user_pets) == 1:
                # Auto-select if only one pet
                selected_pet = user_pets[0]
            
            # Calculate recommended size if pet selected
            if selected_pet and sizes:
                dimensions = get_pet_estimated_dimensions(selected_pet, selected_pet)
                
                best_size = None
                min_diff = float('inf')
                
                for size in sizes:
                    # Check weight range first
                    if selected_pet.get('weight_kg'):
                        if size.get('weight_min_kg') and size.get('weight_max_kg'):
                            if size['weight_min_kg'] <= selected_pet['weight_kg'] <= size['weight_max_kg']:
                                best_size = size['label']
                                break
                    
                    # Otherwise check dimension match
                    chest_diff = abs(dimensions['chest_cm'] - float(size['chest_cm'])) if dimensions.get('chest_cm') else 999
                    back_diff = abs(dimensions['back_cm'] - float(size['back_cm'])) if dimensions.get('back_cm') else 999
                    total_diff = chest_diff + back_diff
                    
                    if total_diff < min_diff:
                        min_diff = total_diff
                        best_size = size['label']
                
                recommended_size = best_size

        # Quick recommendations for AI loading overlay
        cur.execute("""
            SELECT id, name, brand
            FROM products
            WHERE active = TRUE AND id <> %s
            ORDER BY (category = %s) DESC, created_at DESC
            LIMIT 3
        """, (product_id, product['category']))
        preview_products = cur.fetchall()
    
    cur.close()
    conn.close()
    
    return render_template(
        'detail.html',
        product=product,
        recommended_size=recommended_size,
        user_pets=user_pets,
        selected_pet=selected_pet,
        preview_products=preview_products if product else []
    )


@app.route('/api/fit_clothing', methods=['POST'])
def fit_clothing():
    """Gemini AI virtual try-on"""
    if 'user_id' not in session:
        return jsonify({'error': 'login_required'}), 401
    
    product_name = request.form.get('product_name', 'Stylish Dog Clothes')
    product_image_url = request.form.get('product_image_url')
    pet_id = request.form.get('pet_id')
    background = request.form.get('background', 'studio')
    weather = request.form.get('weather', 'clear')
    tone = request.form.get('tone', 'neutral')
    
    if not pet_id:
        return jsonify({'error': 'Pet ID required'}), 400
    
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    cur.execute("SELECT * FROM pets WHERE id = %s AND user_id = %s", (pet_id, session['user_id']))
    pet = cur.fetchone()
    
    if not pet or not pet.get('image_data'):
        cur.close()
        conn.close()
        return jsonify({'error': 'Pet image required'}), 400
    
    # Get pet image data from database
    pet_image_data = bytes(pet['image_data'])
    
    generated_image_url = None
    
    if gemini_client and product_image_url:
        try:
            # Download product image (make relative URLs absolute)
            if product_image_url.startswith('/'):
                product_image_url = request.host_url.rstrip('/') + product_image_url
            product_response = requests.get(product_image_url, timeout=10)
            product_image_data = product_response.content
            
            background_map = {
                "original": "the original pet photo background and lighting",
                "studio": "a clean studio backdrop with soft lighting",
                "park": "a sunny park with greenery in the background",
                "snowy": "a snowy outdoor scene with soft winter light",
                "rainy": "a cozy rainy-day outdoor scene with muted tones"
            }
            weather_map = {
                "clear": "clear skies and crisp daylight",
                "cloudy": "soft overcast light",
                "drizzle": "light rain with gentle reflections",
                "snowfall": "falling snow with soft winter light"
            }
            tone_map = {
                "neutral": "natural, true-to-life colors",
                "warm": "warm, golden color grading",
                "cool": "cool, clean color grading",
                "vivid": "vibrant, punchy colors"
            }
            background_hint = background_map.get(background, background_map["studio"])
            weather_hint = weather_map.get(weather, weather_map["clear"])
            tone_hint = tone_map.get(tone, tone_map["neutral"])
            if background == "original":
                weather_hint = "match the original lighting conditions"
                tone_hint = "preserve the original colors and tone"
            elif background == "studio":
                weather_hint = "soft, even studio lighting"
            prompt_text = (
                f"Create a realistic photograph of this dog wearing the clothing item shown, "
                f"set in {background_hint}. {weather_hint}. {tone_hint}. "
                "Natural pose, high quality, detailed texture."
            )
            
            contents = [
                prompt_text,
                types.Part.from_bytes(data=pet_image_data, mime_type=pet.get('image_mime_type', 'image/jpeg')),
                types.Part.from_bytes(data=product_image_data, mime_type="image/jpeg")
            ]
            
            response = gemini_client.models.generate_content(
                model=GEMINI_IMAGE_MODEL,
                contents=contents,
                config=types.GenerateContentConfig(
                    response_modalities=["IMAGE"]
                )
            )

            parts = getattr(response, 'parts', None)
            if not parts and response.candidates:
                parts = response.candidates[0].content.parts

            if parts:
                for part in parts:
                    if part.inline_data:
                        image_bytes = part.inline_data.data
                        if isinstance(image_bytes, str):
                            image_bytes = base64.b64decode(image_bytes)

                        unique_filename = f"gemini_{uuid.uuid4().hex[:8]}.jpg"
                        save_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)

                        with open(save_path, "wb") as f:
                            f.write(image_bytes)

                        generated_image_url = f"/static/uploads/{unique_filename}"
                        break
        except Exception as e:
            print(f"Gemini error: {e}")
    
    cur.close()
    conn.close()
    
    if not generated_image_url:
        generated_image_url = "https://images.unsplash.com/photo-1583337130417-3346a1be7dee?w=600"
    
    return jsonify({
        'success': True,
        'result_image': generated_image_url,
        'message': 'AI generated result'
    })


@app.route('/admin/fetch_products', methods=['POST'])
def admin_fetch_products():
    """Admin: Fetch products from Naver API and populate database"""
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    products = fetch_naver_api_products(display=20)
    
    if not products:
        return jsonify({'error': 'No products fetched'}), 400
    
    conn = get_db()
    cur = conn.cursor()
    
    added_count = 0
    for prod in products:
        try:
            # Download image from URL and store as binary
            image_data = None
            mime_type = 'image/jpeg'
            if prod.get('image_url'):
                try:
                    img_response = requests.get(prod['image_url'], timeout=5)
                    if img_response.status_code == 200:
                        image_data = img_response.content
                        mime_type = img_response.headers.get('Content-Type', 'image/jpeg')
                except:
                    pass
            
            # Insert product
            cur.execute("""
                INSERT INTO products 
                (name, brand, category, description, base_price_cents, 
                 weather_tag, style_tag, popularity_score, image_data, image_mime_type)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (prod['name'], prod['brand'], prod['category'], prod['description'],
                  prod['price'] * 100, prod['weather_tag'], prod['style_tag'], 
                  0.5, psycopg2.Binary(image_data) if image_data else None, mime_type))
            
            product_id = cur.fetchone()[0]
            
            # Add default sizes (S, M, L)
            sizes = [
                ('S', 35, 28, 24, 2, 5),
                ('M', 45, 36, 30, 5, 12),
                ('L', 60, 48, 38, 12, 30)
            ]
            
            for size_label, chest, back, neck, min_w, max_w in sizes:
                cur.execute("""
                    INSERT INTO product_sizes 
                    (product_id, label, chest_cm, back_cm, neck_cm, weight_min_kg, weight_max_kg)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (product_id, size_label, chest, back, neck, min_w, max_w))
            
            added_count += 1
        except Exception as e:
            print(f"Error adding product: {e}")
            continue
    
    conn.commit()
    cur.close()
    conn.close()
    
    return jsonify({'success': True, 'added': added_count})


# =======================
# Search API
# =======================
@app.route('/api/search/suggestions')
def search_suggestions():
    """Get search suggestions as user types"""
    query = request.args.get('q', '').strip()
    
    if len(query) < 2:
        return jsonify({'suggestions': []})
    
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    search_pattern = f"%{query}%"
    cur.execute("""
        SELECT DISTINCT ON (p.id) 
            p.id, p.name, p.brand, p.base_price_cents, p.category, p.popularity_score
        FROM products p
        WHERE p.active = TRUE 
            AND (p.name ILIKE %s OR p.brand ILIKE %s)
        ORDER BY p.id, p.popularity_score DESC NULLS LAST
        LIMIT 5
    """, (search_pattern, search_pattern))
    
    products = cur.fetchall()
    cur.close()
    conn.close()
    
    suggestions = [{
        'id': p['id'],
        'name': p['name'],
        'brand': p['brand'],
        'price': p['base_price_cents'] / 100,
        'category': p['category']
    } for p in products]
    
    return jsonify({'suggestions': suggestions})


# =======================
# Cart Routes
# =======================
@app.route('/cart')
def cart():
    """Display shopping cart"""
    if 'user_id' not in session:
        flash('Please log in to view your cart.')
        return redirect(url_for('login'))
    
    # Get cart items from session
    cart_items = session.get('cart', [])
    
    # Fetch available sizes for each product
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    for item in cart_items:
        cur.execute("""
            SELECT label FROM product_sizes 
            WHERE product_id = %s 
            ORDER BY 
                CASE label
                    WHEN 'XXS' THEN 1
                    WHEN 'XS' THEN 2
                    WHEN 'S' THEN 3
                    WHEN 'M' THEN 4
                    WHEN 'L' THEN 5
                    WHEN 'XL' THEN 6
                    WHEN 'XXL' THEN 7
                    ELSE 8
                END
        """, (item['id'],))
        item['available_sizes'] = [s['label'] for s in cur.fetchall()]
    
    cur.close()
    conn.close()
    
    # Calculate total
    total = sum(item.get('price', 0) * item.get('qty', 1) for item in cart_items)
    
    return render_template('cart.html', items=cart_items, total=total)


@app.route('/cart/add/<int:product_id>', methods=['POST'])
def add_to_cart(product_id):
    """Add product to cart"""
    if 'user_id' not in session:
        flash('Please log in to add items to cart.')
        return redirect(url_for('login'))
    
    size = request.form.get('size', 'M')
    qty = int(request.form.get('qty', 1))
    
    # Get product details
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("""
        SELECT id, name, base_price_cents 
        FROM products 
        WHERE id = %s
    """, (product_id,))
    product = cur.fetchone()
    cur.close()
    conn.close()
    
    if not product:
        flash('Product not found.')
        return redirect(url_for('index'))
    
    # Initialize cart if needed
    if 'cart' not in session:
        session['cart'] = []
    
    # Check if item already in cart
    cart = session['cart']
    existing_item = next((item for item in cart if item['id'] == product_id and item['size'] == size), None)
    
    if existing_item:
        existing_item['qty'] += qty
    else:
        cart.append({
            'id': product['id'],
            'name': product['name'],
            'price': product['base_price_cents'] / 100,
            'size': size,
            'qty': qty,
            'image': f'/product_image/{product_id}'
        })
    
    session['cart'] = cart
    session.modified = True
    
    flash(f'Added {product["name"]} to cart.')
    return redirect(url_for('cart'))    


@app.route('/cart/update/<int:product_id>', methods=['POST'])
def update_cart(product_id):
    """Update cart item quantity or size"""
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    size = request.form.get('size', 'M')
    qty = int(request.form.get('qty', 1))
    
    cart = session.get('cart', [])
    for item in cart:
        if item['id'] == product_id:
            item['size'] = size
            item['qty'] = qty
            break
    
    session['cart'] = cart
    session.modified = True
    
    flash('Cart updated.')
    return redirect(url_for('cart'))


@app.route('/cart/remove/<int:product_id>', methods=['POST'])
def remove_from_cart(product_id):
    """Remove item from cart"""
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    cart = session.get('cart', [])
    session['cart'] = [item for item in cart if item['id'] != product_id]
    session.modified = True
    
    flash('Item removed from cart.')
    return redirect(url_for('cart'))


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
