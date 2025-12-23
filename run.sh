#!/bin/bash

# PetFit - Run Script
# This script starts the Pet-Fit recommendation system

echo "🐕 Starting Pet-Fit Recommendation System..."
echo ""

# Check if .env file exists
if [ ! -f .env ]; then
    echo "⚠️  No .env file found. Creating template..."
    cat > .env << 'EOF'
# PostgreSQL Database (Neon or any PostgreSQL)
DATABASE_URL=postgresql://username:password@hostname/database

# Google Gemini AI (for virtual try-on)
GOOGLE_API_KEY=your_gemini_api_key_here

# Naver Shopping API (optional - for fetching products)
NAVER_CLIENT_ID=your_naver_client_id
NAVER_CLIENT_SECRET=your_naver_client_secret

# Flask Secret Key
SECRET_KEY=change_this_to_a_random_secret_key
EOF
    echo "✅ Created .env template file"
    echo "⚠️  Please edit .env and add your credentials, then run this script again."
    echo ""
    exit 1
fi

# Load environment variables
export $(cat .env | grep -v '^#' | xargs)

# Check if DATABASE_URL is set
if [ -z "$DATABASE_URL" ] || [ "$DATABASE_URL" = "postgresql://username:password@hostname/database" ]; then
    echo "❌ DATABASE_URL not configured in .env"
    echo "   Please set your Neon PostgreSQL connection string"
    echo ""
    echo "   Example: DATABASE_URL=postgresql://user:pass@ep-xyz.us-east-1.aws.neon.tech/petfit"
    echo ""
    exit 1
fi

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "🔧 Activating virtual environment..."
source venv/bin/activate

# Install/update dependencies
echo "📦 Installing dependencies..."
pip install -q -r requirements.txt

# Check database connection
echo "🔍 Checking database connection..."
python3 << EOF
import os
import psycopg2

try:
    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    conn.close()
    print("✅ Database connection successful")
except Exception as e:
    print(f"❌ Database connection failed: {e}")
    exit(1)
EOF

if [ $? -ne 0 ]; then
    exit 1
fi

echo ""
echo "🚀 Starting Flask application..."
echo "   Access the app at: http://localhost:5000"
echo ""
echo "   Press Ctrl+C to stop"
echo ""

# Run the Flask app
python3 app.py
