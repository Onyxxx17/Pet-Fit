# #!/usr/bin/env python3
# """
# Add HugMe - Lilac Bundle product with image to database
# Run this script to insert the product with its image from static/uploads/image.png
# """

# import os
# import sys
# import psycopg2
# from psycopg2.extras import RealDictCursor
# from dotenv import load_dotenv

# # Load environment variables from .env file
# load_dotenv()

# # Get database URL from environment
# DATABASE_URL = os.environ.get('DATABASE_URL')
# if not DATABASE_URL:
#     print("ERROR: DATABASE_URL environment variable not set")
#     print("Set it with: export DATABASE_URL='your_neon_postgres_url'")
#     print("Or add it to .env file")
#     sys.exit(1)

# # Path to image
# IMAGE_PATH = 'static/uploads/image.png'

# def add_hugme_bundle():
#     """Add HugMe - Lilac Bundle to database with image"""
    
#     # Check if image exists
#     if not os.path.exists(IMAGE_PATH):
#         print(f"ERROR: Image not found at {IMAGE_PATH}")
#         sys.exit(1)
    
#     # Read image file
#     with open(IMAGE_PATH, 'rb') as f:
#         image_data = f.read()
    
#     print(f"✓ Loaded image: {len(image_data)} bytes")
    
#     # Connect to database
#     conn = psycopg2.connect(DATABASE_URL)
#     cur = conn.cursor(cursor_factory=RealDictCursor)
    
#     try:
#         # Insert product
#         cur.execute("""
#             INSERT INTO products (
#                 name, brand, category, description, 
#                 base_price_cents, weather_tag, style_tag, popularity_score,
#                 image_data, image_mime_type
#             ) VALUES (
#                 %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
#             ) RETURNING id
#         """, (
#             'HugMe - Lilac Bundle',
#             'Boss & Olly',
#             'All-in-one',
#             'Complete bundle including HugMe Harness, Collar, Grab Handle, Sailor Bow, and Poo Bag. Premium quality set for your stylish pet.',
#             9800,  # $98.00 in cents
#             'all-season',
#             'classic',
#             0.85,
#             psycopg2.Binary(image_data),
#             'image/png'
#         ))
        
#         product_id = cur.fetchone()['id']
#         print(f"✓ Added product with ID: {product_id}")
        
#         # Add all size variants
#         sizes = [
#             ('XXS', 23, 16, 21, 1.0, 3.0),
#             ('XS', 29, 19, 27, 2.5, 4.5),
#             ('S', 35, 20, 32, 4.0, 7.0),
#             ('M', 42, 25, 40, 6.0, 12.0),
#             ('L', 50, 30, 45, 11.0, 20.0),
#             ('XL', 48, 31.5, 52, 18.0, 35.0)
#         ]
        
#         for label, chest, back, neck, min_weight, max_weight in sizes:
#             cur.execute("""
#                 INSERT INTO product_sizes (
#                     product_id, label, chest_cm, back_cm, neck_cm, 
#                     weight_min_kg, weight_max_kg
#                 ) VALUES (%s, %s, %s, %s, %s, %s, %s)
#             """, (product_id, label, chest, back, neck, min_weight, max_weight))
#             print(f"  ✓ Added size: {label}")
        
#         conn.commit()
#         print("\n✅ Successfully added HugMe - Lilac Bundle with 6 sizes!")
#         print(f"   Product ID: {product_id}")
#         print(f"   Price: $98.00")
#         print(f"   Sizes: XXS, XS, S, M, L, XL")
#         print(f"   Image: ✓ Stored in database ({len(image_data)} bytes)")
        
#     except Exception as e:
#         conn.rollback()
#         print(f"\n❌ Error: {e}")
#         sys.exit(1)
#     finally:
#         cur.close()
#         conn.close()

# if __name__ == '__main__':
#     add_hugme_bundle()
