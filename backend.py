from flask import Flask, request, jsonify, session
from flask_cors import CORS
import sqlite3
import hashlib
import secrets
from datetime import datetime, timedelta
import cv2
import numpy as np
from ultralytics import YOLO
import base64
import json
import os
from functools import wraps

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)

# CORS configuration - IMPORTANT: Update this with your frontend URL
CORS(app, 
     supports_credentials=True,
     origins=['http://localhost:3000', 'http://127.0.0.1:3000', 'http://localhost:8000', 'http://127.0.0.1:8000'],
     allow_headers=['Content-Type'],
     methods=['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'])

# Session configuration
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = False  # Set to True in production with HTTPS
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)

# Initialize YOLO model
try:
    model = YOLO('yolov8n.pt')
    print("YOLO model loaded successfully!")
except Exception as e:
    print(f"Warning: YOLO model not loaded - {e}")
    model = None

# Database initialization
def init_db():
    conn = sqlite3.connect('aibsfms.db')
    cursor = conn.cursor()
    
    # Users table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # User profiles table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            age INTEGER,
            weight REAL,
            height REAL,
            dietary_preference TEXT,
            goals TEXT,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    
    # Tracking sessions table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tracking_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            tracking_mode TEXT NOT NULL,
            start_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            end_time TIMESTAMP,
            status TEXT DEFAULT 'active',
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    
    # Food items detected table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS food_detections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            item_name TEXT NOT NULL,
            quantity REAL,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            detection_type TEXT,
            confidence REAL,
            image_path TEXT,
            FOREIGN KEY (session_id) REFERENCES tracking_sessions (id)
        )
    ''')
    
    # Waste tracking table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS waste_tracking (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER NOT NULL,
            waste_type TEXT NOT NULL,
            quantity REAL,
            suggestions TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (session_id) REFERENCES tracking_sessions (id)
        )
    ''')
    
    # AI suggestions table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS ai_suggestions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            session_id INTEGER,
            suggestion_text TEXT NOT NULL,
            category TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id),
            FOREIGN KEY (session_id) REFERENCES tracking_sessions (id)
        )
    ''')
    
    # Dashboard statistics table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_statistics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            total_sessions INTEGER DEFAULT 0,
            total_waste_kg REAL DEFAULT 0,
            total_food_consumed_kg REAL DEFAULT 0,
            avg_waste_percentage REAL DEFAULT 0,
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    
    conn.commit()
    conn.close()
    print("Database initialized successfully!")

# Authentication decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'error': 'Authentication required'}), 401
        return f(*args, **kwargs)
    return decorated_function

# Helper functions
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def get_db():
    conn = sqlite3.connect('aibsfms.db')
    conn.row_factory = sqlite3.Row
    return conn

# Health check endpoint
@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({
        'status': 'healthy',
        'model_loaded': model is not None
    }), 200

# Authentication routes
@app.route('/api/auth/signup', methods=['POST'])
def signup():
    try:
        data = request.json
        name = data.get('name')
        email = data.get('email')
        password = data.get('password')
        
        if not all([name, email, password]):
            return jsonify({'error': 'All fields are required'}), 400
        
        conn = get_db()
        cursor = conn.cursor()
        
        try:
            password_hash = hash_password(password)
            cursor.execute(
                'INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)',
                (name, email, password_hash)
            )
            user_id = cursor.lastrowid
            
            # Initialize user statistics
            cursor.execute(
                'INSERT INTO user_statistics (user_id) VALUES (?)',
                (user_id,)
            )
            
            conn.commit()
            session.permanent = True
            session['user_id'] = user_id
            session['user_name'] = name
            
            return jsonify({
                'success': True,
                'user_id': user_id,
                'name': name
            }), 201
            
        except sqlite3.IntegrityError:
            return jsonify({'error': 'Email already exists'}), 409
        finally:
            conn.close()
    except Exception as e:
        print(f"Signup error: {e}")
        return jsonify({'error': 'Server error during signup'}), 500

@app.route('/api/auth/login', methods=['POST'])
def login():
    try:
        data = request.json
        email = data.get('email')
        password = data.get('password')
        
        if not all([email, password]):
            return jsonify({'error': 'Email and password are required'}), 400
        
        conn = get_db()
        cursor = conn.cursor()
        
        password_hash = hash_password(password)
        cursor.execute(
            'SELECT id, name FROM users WHERE email = ? AND password_hash = ?',
            (email, password_hash)
        )
        user = cursor.fetchone()
        conn.close()
        
        if user:
            session.permanent = True
            session['user_id'] = user['id']
            session['user_name'] = user['name']
            return jsonify({
                'success': True,
                'user_id': user['id'],
                'name': user['name']
            }), 200
        else:
            return jsonify({'error': 'Invalid email or password'}), 401
    except Exception as e:
        print(f"Login error: {e}")
        return jsonify({'error': 'Server error during login'}), 500

@app.route('/api/auth/logout', methods=['POST'])
@login_required
def logout():
    session.clear()
    return jsonify({'success': True}), 200

@app.route('/api/auth/check', methods=['GET'])
def check_auth():
    if 'user_id' in session:
        return jsonify({
            'authenticated': True,
            'user_id': session['user_id'],
            'name': session['user_name']
        }), 200
    return jsonify({'authenticated': False}), 200

# User profile routes
@app.route('/api/profile/save', methods=['POST'])
@login_required
def save_profile():
    try:
        data = request.json
        user_id = session['user_id']
        
        conn = get_db()
        cursor = conn.cursor()
        
        # Check if profile exists
        cursor.execute('SELECT id FROM user_profiles WHERE user_id = ?', (user_id,))
        existing = cursor.fetchone()
        
        if existing:
            cursor.execute('''
                UPDATE user_profiles 
                SET age = ?, weight = ?, height = ?, dietary_preference = ?, goals = ?
                WHERE user_id = ?
            ''', (data['age'], data['weight'], data['height'], 
                  data['dietary'], data['goals'], user_id))
        else:
            cursor.execute('''
                INSERT INTO user_profiles (user_id, age, weight, height, dietary_preference, goals)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (user_id, data['age'], data['weight'], data['height'], 
                  data['dietary'], data['goals']))
        
        conn.commit()
        conn.close()
        
        return jsonify({'success': True}), 200
    except Exception as e:
        print(f"Profile save error: {e}")
        return jsonify({'error': 'Failed to save profile'}), 500

@app.route('/api/profile/get', methods=['GET'])
@login_required
def get_profile():
    user_id = session['user_id']
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM user_profiles WHERE user_id = ?', (user_id,))
    profile = cursor.fetchone()
    conn.close()
    
    if profile:
        return jsonify(dict(profile)), 200
    return jsonify({'error': 'Profile not found'}), 404

# Tracking routes
@app.route('/api/tracking/start', methods=['POST'])
@login_required
def start_tracking():
    try:
        data = request.json
        user_id = session['user_id']
        tracking_mode = data.get('mode')
        
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO tracking_sessions (user_id, tracking_mode)
            VALUES (?, ?)
        ''', (user_id, tracking_mode))
        session_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        session['current_session_id'] = session_id
        
        return jsonify({
            'success': True,
            'session_id': session_id
        }), 201
    except Exception as e:
        print(f"Start tracking error: {e}")
        return jsonify({'error': 'Failed to start tracking'}), 500

@app.route('/api/tracking/process-frame', methods=['POST'])
@login_required
def process_frame():
    try:
        if 'current_session_id' not in session:
            return jsonify({'error': 'No active tracking session'}), 400
        
        session_id = session['current_session_id']
        
        # Get image data
        data = request.json
        image_data = data.get('image')
        
        if not model:
            return jsonify({'error': 'YOLO model not available'}), 503
        
        # Decode base64 image
        image_bytes = base64.b64decode(image_data.split(',')[1])
        nparr = np.frombuffer(image_bytes, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        # Process with YOLO
        results = model(frame, verbose=False)
        
        # Extract detections
        detections = []
        conn = get_db()
        cursor = conn.cursor()
        
        for result in results:
            boxes = result.boxes
            for box in boxes:
                cls = int(box.cls[0])
                conf = float(box.conf[0])
                name = model.names[cls]
                
                # Filter for food-related items (confidence > 0.5)
                if conf > 0.5:
                    # Save detection
                    cursor.execute('''
                        INSERT INTO food_detections 
                        (session_id, item_name, confidence, detection_type, timestamp)
                        VALUES (?, ?, ?, 'yolo', CURRENT_TIMESTAMP)
                    ''', (session_id, name, conf))
                    
                    detections.append({
                        'item': name,
                        'confidence': conf
                    })
        
        conn.commit()
        
        # Generate AI suggestions based on detections
        suggestions = generate_ai_suggestions(session_id, detections)
        
        conn.close()
        
        return jsonify({
            'success': True,
            'detections': detections,
            'suggestions': suggestions
        }), 200
    except Exception as e:
        print(f"Frame processing error: {e}")
        return jsonify({'error': f'Failed to process frame: {str(e)}'}), 500

@app.route('/api/tracking/stop', methods=['POST'])
@login_required
def stop_tracking():
    try:
        if 'current_session_id' not in session:
            return jsonify({'error': 'No active tracking session'}), 400
        
        session_id = session['current_session_id']
        
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE tracking_sessions 
            SET end_time = CURRENT_TIMESTAMP, status = 'completed'
            WHERE id = ?
        ''', (session_id,))
        conn.commit()
        
        # Update user statistics
        update_user_statistics(session['user_id'])
        
        conn.close()
        
        del session['current_session_id']
        
        return jsonify({'success': True}), 200
    except Exception as e:
        print(f"Stop tracking error: {e}")
        return jsonify({'error': 'Failed to stop tracking'}), 500

# Dashboard routes
@app.route('/api/dashboard/stats', methods=['GET'])
@login_required
def get_dashboard_stats():
    try:
        user_id = session['user_id']
        
        conn = get_db()
        cursor = conn.cursor()
        
        # Get user statistics
        cursor.execute('SELECT * FROM user_statistics WHERE user_id = ?', (user_id,))
        stats = cursor.fetchone()
        
        # Get recent sessions
        cursor.execute('''
            SELECT id, tracking_mode, start_time, end_time, status
            FROM tracking_sessions
            WHERE user_id = ?
            ORDER BY start_time DESC
            LIMIT 10
        ''', (user_id,))
        recent_sessions = [dict(row) for row in cursor.fetchall()]
        
        # Get recent detections
        cursor.execute('''
            SELECT fd.item_name, fd.quantity, fd.timestamp, fd.confidence
            FROM food_detections fd
            JOIN tracking_sessions ts ON fd.session_id = ts.id
            WHERE ts.user_id = ?
            ORDER BY fd.timestamp DESC
            LIMIT 20
        ''', (user_id,))
        recent_detections = [dict(row) for row in cursor.fetchall()]
        
        # Get AI suggestions
        cursor.execute('''
            SELECT suggestion_text, category, timestamp
            FROM ai_suggestions
            WHERE user_id = ?
            ORDER BY timestamp DESC
            LIMIT 10
        ''', (user_id,))
        suggestions = [dict(row) for row in cursor.fetchall()]
        
        # Get waste data (create sample data if empty)
        cursor.execute('''
            SELECT wt.waste_type, SUM(wt.quantity) as total_quantity
            FROM waste_tracking wt
            JOIN tracking_sessions ts ON wt.session_id = ts.id
            WHERE ts.user_id = ?
            GROUP BY wt.waste_type
        ''', (user_id,))
        waste_data = [dict(row) for row in cursor.fetchall()]
        
        # If no waste data, create sample
        if not waste_data:
            waste_data = [
                {'waste_type': 'Vegetable Peels', 'total_quantity': 0},
                {'waste_type': 'Leftover Food', 'total_quantity': 0},
                {'waste_type': 'Spillage', 'total_quantity': 0}
            ]
        
        conn.close()
        
        return jsonify({
            'statistics': dict(stats) if stats else {
                'total_sessions': 0,
                'total_waste_kg': 0,
                'total_food_consumed_kg': 0,
                'avg_waste_percentage': 0
            },
            'recent_sessions': recent_sessions,
            'recent_detections': recent_detections,
            'suggestions': suggestions,
            'waste_data': waste_data
        }), 200
    except Exception as e:
        print(f"Dashboard stats error: {e}")
        return jsonify({'error': 'Failed to load dashboard data'}), 500

@app.route('/api/dashboard/session/<int:session_id>', methods=['GET'])
@login_required
def get_session_details(session_id):
    try:
        user_id = session['user_id']
        
        conn = get_db()
        cursor = conn.cursor()
        
        # Verify session belongs to user
        cursor.execute('''
            SELECT * FROM tracking_sessions 
            WHERE id = ? AND user_id = ?
        ''', (session_id, user_id))
        session_data = cursor.fetchone()
        
        if not session_data:
            return jsonify({'error': 'Session not found'}), 404
        
        # Get detections for this session
        cursor.execute('''
            SELECT * FROM food_detections
            WHERE session_id = ?
            ORDER BY timestamp
        ''', (session_id,))
        detections = [dict(row) for row in cursor.fetchall()]
        
        # Get waste data
        cursor.execute('''
            SELECT * FROM waste_tracking
            WHERE session_id = ?
        ''', (session_id,))
        waste = [dict(row) for row in cursor.fetchall()]
        
        conn.close()
        
        return jsonify({
            'session': dict(session_data),
            'detections': detections,
            'waste': waste
        }), 200
    except Exception as e:
        print(f"Session details error: {e}")
        return jsonify({'error': 'Failed to load session details'}), 500

# Helper function for AI suggestions
def generate_ai_suggestions(session_id, detections):
    """Generate AI-powered suggestions based on detections"""
    suggestions = []
    
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        # Get session info
        cursor.execute('''
            SELECT ts.user_id, ts.tracking_mode
            FROM tracking_sessions ts
            WHERE ts.id = ?
        ''', (session_id,))
        session_info = cursor.fetchone()
        
        if not session_info:
            return suggestions
            
        user_id = session_info['user_id']
        mode = session_info['tracking_mode']
        
        # Generate mode-specific suggestions
        if mode == 'cooking':
            suggestion_texts = [
                'Consider saving vegetable peels for making stock or compost',
                'Batch cooking can save time and energy',
                'Store leftovers properly to extend their shelf life'
            ]
            for text in suggestion_texts[:2]:
                cursor.execute('''
                    INSERT INTO ai_suggestions (user_id, session_id, suggestion_text, category)
                    VALUES (?, ?, ?, ?)
                ''', (user_id, session_id, text, 'waste_reduction'))
                suggestions.append({'text': text, 'category': 'waste_reduction'})
                
        elif mode == 'eating':
            suggestion_texts = [
                'Great portion control! This helps minimize waste',
                'Try to finish what\'s on your plate to reduce food waste',
                'Consider sharing larger portions with others'
            ]
            for text in suggestion_texts[:2]:
                cursor.execute('''
                    INSERT INTO ai_suggestions (user_id, session_id, suggestion_text, category)
                    VALUES (?, ?, ?, ?)
                ''', (user_id, session_id, text, 'health'))
                suggestions.append({'text': text, 'category': 'health'})
                
        elif mode == 'summary':
            suggestion_texts = [
                'Your tracking consistency is improving!',
                'Consider meal planning to further reduce waste',
                'You\'re making good progress in waste reduction'
            ]
            for text in suggestion_texts[:2]:
                cursor.execute('''
                    INSERT INTO ai_suggestions (user_id, session_id, suggestion_text, category)
                    VALUES (?, ?, ?, ?)
                ''', (user_id, session_id, text, 'planning'))
                suggestions.append({'text': text, 'category': 'planning'})
        
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Suggestion generation error: {e}")
    
    return suggestions

def update_user_statistics(user_id):
    """Update user statistics after session completion"""
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        # Count total sessions
        cursor.execute('''
            SELECT COUNT(*) as total FROM tracking_sessions WHERE user_id = ? AND status = 'completed'
        ''', (user_id,))
        total_sessions = cursor.fetchone()['total']
        
        # Calculate waste (simulated for now)
        cursor.execute('''
            SELECT COALESCE(SUM(quantity), 0) as total_waste
            FROM waste_tracking wt
            JOIN tracking_sessions ts ON wt.session_id = ts.id
            WHERE ts.user_id = ?
        ''', (user_id,))
        total_waste = cursor.fetchone()['total_waste']
        
        # Estimate consumed food (2x waste as placeholder)
        total_consumed = total_waste * 2.5
        waste_percentage = (total_waste / total_consumed * 100) if total_consumed > 0 else 0
        
        # Update statistics
        cursor.execute('''
            UPDATE user_statistics
            SET total_sessions = ?,
                total_waste_kg = ?,
                total_food_consumed_kg = ?,
                avg_waste_percentage = ?,
                last_updated = CURRENT_TIMESTAMP
            WHERE user_id = ?
        ''', (total_sessions, total_waste, total_consumed, waste_percentage, user_id))
        
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Statistics update error: {e}")

# Initialize database on startup
init_db()

if __name__ == '__main__':
    print("\n" + "="*50)
    print("🚀 AiBSFMS Backend Server Starting...")
    print("="*50)
    print(f"📍 Server: http://localhost:5000")
    print(f"📍 API Base: http://localhost:5000/api")
    print(f"🔐 CORS Enabled for local development")
    print("="*50 + "\n")
    app.run(debug=True, host='0.0.0.0', port=5000)