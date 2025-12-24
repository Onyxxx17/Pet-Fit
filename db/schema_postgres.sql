-- PostgreSQL schema for rule-based pet apparel recommendations
-- Assumes DATABASE_URL provided by Neon (or any Postgres 14+)

-- Users
CREATE TABLE IF NOT EXISTS users (
    id              BIGSERIAL PRIMARY KEY,
    username        TEXT NOT NULL UNIQUE,
    email           TEXT UNIQUE,
    password_hash   TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Reference breeds with average metrics
CREATE TABLE IF NOT EXISTS breeds (
    id               BIGSERIAL PRIMARY KEY,
    name             TEXT NOT NULL UNIQUE,
    avg_weight_kg    NUMERIC(6,2),
    avg_chest_cm     NUMERIC(6,2),
    avg_back_cm      NUMERIC(6,2),
    avg_neck_cm      NUMERIC(6,2),
    size_label       TEXT CHECK (size_label IN ('XS','S','M','L','XL','XXL'))
);

-- Pet profiles (one user -> many pets)
CREATE TABLE IF NOT EXISTS pets (
    id              BIGSERIAL PRIMARY KEY,
    user_id         BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name            TEXT NOT NULL,
    breed_id        BIGINT REFERENCES breeds(id) ON DELETE SET NULL,
    weight_kg       NUMERIC(6,2),
    size_label      TEXT CHECK (size_label IN ('XS','S','M','L','XL','XXL')),
    weather_pref    TEXT CHECK (weather_pref IN ('all-season','cold','rain')),
    style_pref      TEXT CHECK (style_pref IN ('classic','sport','street')),
    price_range     TEXT CHECK (price_range IN ('budget','mid','premium')),
    image_data      BYTEA,
    image_mime_type TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_pets_user_id ON pets(user_id);
CREATE INDEX IF NOT EXISTS idx_pets_breed_id ON pets(breed_id);

-- Products
CREATE TABLE IF NOT EXISTS products (
    id                BIGSERIAL PRIMARY KEY,
    name              TEXT NOT NULL,
    brand             TEXT,
    category          TEXT CHECK (category IN ('Top','Outer','Dress','Harness&Leash','Accessory')),
    description       TEXT,
    base_price_cents  INTEGER NOT NULL,
    weather_tag       TEXT,
    style_tag         TEXT,
    popularity_score  NUMERIC(4,2) DEFAULT 0.50,
    image_data        BYTEA,
    image_mime_type   TEXT,
    active            BOOLEAN NOT NULL DEFAULT TRUE,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_products_category ON products(category);
CREATE INDEX IF NOT EXISTS idx_products_active ON products(active);

-- Product sizes/dimensions (multiple sizes per product)
CREATE TABLE IF NOT EXISTS product_sizes (
    id           BIGSERIAL PRIMARY KEY,
    product_id   BIGINT NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    label        TEXT NOT NULL, -- e.g., S/M/L or numeric
    chest_cm     NUMERIC(6,2) NOT NULL,
    back_cm      NUMERIC(6,2) NOT NULL,
    neck_cm      NUMERIC(6,2),
    weight_min_kg NUMERIC(6,2),
    weight_max_kg NUMERIC(6,2),
    sku          TEXT,
    stock_qty    INTEGER,
    UNIQUE(product_id, label)
);
CREATE INDEX IF NOT EXISTS idx_product_sizes_product_id ON product_sizes(product_id);

-- Optional logging for recommendations
CREATE TABLE IF NOT EXISTS recommendation_logs (
    id               BIGSERIAL PRIMARY KEY,
    user_id          BIGINT REFERENCES users(id) ON DELETE SET NULL,
    pet_id           BIGINT REFERENCES pets(id) ON DELETE SET NULL,
    product_id       BIGINT REFERENCES products(id) ON DELETE SET NULL,
    product_size_id  BIGINT REFERENCES product_sizes(id) ON DELETE SET NULL,
    score_total      NUMERIC(4,2),
    score_fit        NUMERIC(4,2),
    score_weather    NUMERIC(4,2),
    score_style      NUMERIC(4,2),
    score_price      NUMERIC(4,2),
    score_popularity NUMERIC(4,2),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_reco_logs_user_pet ON recommendation_logs(user_id, pet_id);

-- Sample lookup data for breeds (extend as needed)
INSERT INTO breeds (name, avg_weight_kg, avg_chest_cm, avg_back_cm, avg_neck_cm, size_label)
VALUES
    ('Chihuahua', 2.5, 30, 22, 20, 'XS'),
    ('Yorkshire Terrier', 3.0, 32, 24, 22, 'XS'),
    ('Pomeranian', 3.5, 34, 26, 23, 'S'),
    ('Poodle (Toy)', 3.5, 35, 28, 24, 'S'),
    ('Shih Tzu', 5.5, 40, 30, 26, 'S'),
    ('Maltese', 4.0, 36, 28, 24, 'S'),
    ('Poodle (Miniature)', 7.5, 45, 36, 30, 'M'),
    ('Cocker Spaniel', 12.0, 52, 42, 34, 'M'),
    ('Beagle', 12.0, 54, 40, 32, 'M'),
    ('French Bulldog', 11.0, 50, 38, 34, 'M'),
    ('Corgi', 12.5, 56, 44, 36, 'M'),
    ('Labrador Retriever', 30.0, 70, 58, 44, 'L'),
    ('Golden Retriever', 32.0, 72, 60, 46, 'L'),
    ('Poodle (Standard)', 23.0, 65, 55, 42, 'L'),
    ('German Shepherd', 35.0, 75, 62, 48, 'XL'),
    ('Husky', 25.0, 68, 56, 44, 'L'),
    ('Bulldog', 23.0, 62, 48, 40, 'L'),
    ('Mixed Breed (Small)', 5.0, 38, 30, 26, 'S'),
    ('Mixed Breed (Medium)', 12.0, 54, 42, 34, 'M'),
    ('Mixed Breed (Large)', 28.0, 70, 56, 44, 'L')
ON CONFLICT (name) DO NOTHING;
