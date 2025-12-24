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
    category          TEXT CHECK (category IN ('Top','Outer','Dress','All-in-one','Accessory','Etc')),
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