"""
Full backend: MySQL connection pooling + templates, JWT (access + refresh),
user signup/login, per-user flashcards, and IntaSend hosted-checkout /pay route.
Enhanced AI Study Buddy Backend with comprehensive features.
"""

import os
import json
import logging
from datetime import datetime, timedelta
from dotenv import load_dotenv

from flask import Flask, request, jsonify, render_template
import requests
from werkzeug.security import generate_password_hash, check_password_hash
from flask_cors import CORS

# JWT
from flask_jwt_extended import (
    JWTManager, create_access_token, create_refresh_token,
    jwt_required, get_jwt_identity, get_jwt, decode_token
)

# MySQL connector + pooling
import mysql.connector
from mysql.connector import pooling

# IntaSend SDK (optional — install intasend-python)
try:
    from intasend import APIService
except ImportError:
    APIService = None

# ---------------------------
# Load environment variables
# ---------------------------
load_dotenv()  # reads .env file

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")  # Update with your password
DB_NAME = os.getenv("DB_NAME", "studybuddy")

JWT_SECRET = os.getenv("JWT_SECRET_KEY", "super-secret-key-change-in-production")

# IntaSend configuration
INTASEND_SECRET = os.getenv("INTASEND_SECRET_KEY", "")
INTASEND_PUBLISHABLE = os.getenv("INTASEND_PUBLIC_KEY", "")
INTASEND_TEST = os.getenv("INTASEND_TEST", "True").lower() in ("1", "true", "yes")


# HuggingFace Configuration
HUGGINGFACE_API_TOKEN = os.getenv("HUGGINGFACE_API_TOKEN", "") # ENTER THE TOKEN HERE
HUGGINGFACE_MODEL = os.getenv("HUGGINGFACE_MODEL", "microsoft/DialoGPT-medium")
# ---------------------------
# Flask + JWT config
# ---------------------------
app = Flask(__name__)
CORS(app, origins=["http://127.0.0.1:5500", "http://localhost:5500", "http://127.0.0.1:8000"])

app.config["JWT_SECRET_KEY"] = JWT_SECRET
app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(hours=1)      # access tokens valid for 1 hour
app.config["JWT_REFRESH_TOKEN_EXPIRES"] = timedelta(days=30)    # refresh tokens valid for 30 days

jwt = JWTManager(app)

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------------------
# MySQL connection pool
# ---------------------------
try:
    POOL = pooling.MySQLConnectionPool(
        pool_name="ai_pool",
        pool_size=10,
        pool_reset_session=True,
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME,
        charset="utf8mb4",
        autocommit=False
    )
    logger.info("MySQL connection pool created successfully")
except Exception as e:
    logger.error(f"Failed to create MySQL connection pool: {e}")
    raise

def get_conn():
    """Get a connection from the pool. Caller must close it."""
    try:
        return POOL.get_connection()
    except Exception as e:
        logger.error(f"Failed to get database connection: {e}")
        raise

# ---------------------------
# Ensure comprehensive tables exist
# ---------------------------
def ensure_tables():
    """Create all necessary tables if they don't exist"""
    conn = get_conn()
    cur = conn.cursor()
    
    try:
        # Users table
        cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INT AUTO_INCREMENT PRIMARY KEY,
            username VARCHAR(80) NOT NULL UNIQUE,
            email VARCHAR(255) NOT NULL UNIQUE,
            password VARCHAR(255) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            INDEX idx_email (email),
            INDEX idx_username (username)
        ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
        """)
        
        # Enhanced flashcards table
        cur.execute("""
        CREATE TABLE IF NOT EXISTS flashcards (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NULL,  -- Allow NULL for guest users
            subject VARCHAR(50) NOT NULL,
            notes TEXT,
            question TEXT NOT NULL,
            answer TEXT NOT NULL,
            difficulty_level ENUM('easy', 'medium', 'hard') DEFAULT 'medium',
            times_reviewed INT DEFAULT 0,
            last_reviewed TIMESTAMP NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL,
            INDEX idx_user_subject (user_id, subject),
            INDEX idx_created_at (created_at),
            INDEX idx_subject (subject)
        ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
        """)
        
        # Refresh tokens table for JWT management
        cur.execute("""
        CREATE TABLE IF NOT EXISTS refresh_tokens (
            id INT AUTO_INCREMENT PRIMARY KEY,
            jti VARCHAR(255) NOT NULL UNIQUE,
            user_id INT NOT NULL,
            revoked BOOLEAN DEFAULT FALSE,
            expires_at DATETIME,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            INDEX idx_jti (jti),
            INDEX idx_user_expires (user_id, expires_at)
        ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
        """)
        
        # Payments table for IntaSend integration
        cur.execute("""
        CREATE TABLE IF NOT EXISTS payments (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT,
            ref VARCHAR(255),
            amount INT,
            currency VARCHAR(10),
            status VARCHAR(50),
            metadata JSON,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL,
            INDEX idx_ref (ref),
            INDEX idx_user_status (user_id, status)
        ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
        """)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS xp_log (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL,
            xp_gained INT NOT NULL,
            reason VARCHAR(255),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            INDEX idx_user_date (user_id, created_at)
        ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
        """) 
        # Study sessions table for analytics
        cur.execute("""
        CREATE TABLE IF NOT EXISTS study_sessions (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NULL,
            subject VARCHAR(50) NOT NULL,
            flashcards_studied INT DEFAULT 0,
            session_duration_minutes INT DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL,
            INDEX idx_user_date (user_id, created_at)
        ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
        """)
        
        conn.commit()
        logger.info("All database tables created/verified successfully")
        
    except Exception as e:
        logger.error(f"Database table creation failed: {e}")
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()

# Initialize tables on startup
ensure_tables()

# ---------------------------
# Refresh token database helpers
# ---------------------------
def store_refresh_token(jti, user_id, expires_at_dt):
    """Store refresh token in database for revocation tracking"""
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO refresh_tokens (jti, user_id, expires_at) VALUES (%s, %s, %s)",
            (jti, user_id, expires_at_dt)
        )
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        logger.error(f"Failed to store refresh token: {e}")
        raise

def is_refresh_token_revoked(jti):
    """Check if refresh token is revoked"""
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT revoked FROM refresh_tokens WHERE jti = %s", (jti,))
        row = cur.fetchone()
        cur.close()
        conn.close()
        if not row:
            # If we can't find it, treat as revoked/invalid for safety
            return True
        return bool(row[0])
    except Exception as e:
        logger.error(f"Error checking token revocation: {e}")

        return True  # Fail safe
    



    # ---------------------------
# HuggingFace Integration
# ---------------------------
def generate_flashcard_with_huggingface(notes, subject, difficulty='medium'):
    """Generate flashcard using HuggingFace API with proper error handling"""
    if not HUGGINGFACE_API_TOKEN:
        logger.warning("HuggingFace API token not configured")
        return None
    
    try:
        # Better prompts for each difficulty level
        prompts = {
            'easy': f"Create a simple question and answer for beginners learning {subject}. Based on these notes: {notes[:600]}.\n\nFormat your response as:\nQuestion: [your question]\nAnswer: [your answer]",
            'medium': f"Create a moderately challenging question about {subject} that tests understanding. Based on these notes: {notes[:600]}.\n\nFormat your response as:\nQuestion: [your question]\nAnswer: [your answer]",
            'hard': f"Create a complex analytical question about {subject} that requires critical thinking. Based on these notes: {notes[:600]}.\n\nFormat your response as:\nQuestion: [your question]\nAnswer: [your answer]"
        }
        
        prompt = prompts.get(difficulty, prompts['medium'])
        
        headers = {
            'Authorization': f'Bearer {HUGGINGFACE_API_TOKEN}',
            'Content-Type': 'application/json'
        }
        
        # Use a better model for text generation
        api_url = "https://api-inference.huggingface.co/models/microsoft/DialoGPT-medium"
        
        payload = {
            "inputs": prompt,
            "parameters": {
                "max_new_tokens": 250,
                "temperature": 0.7,
                "do_sample": True,
                "return_full_text": False
            },
            "options": {
                "wait_for_model": True
            }
        }
        
        # Add timeout and retry logic
        import time
        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = requests.post(api_url, headers=headers, json=payload, timeout=30)
                
                if response.status_code == 200:
                    result = response.json()
                    logger.info(f"HuggingFace response: {result}")
                    
                    if isinstance(result, list) and len(result) > 0:
                        generated_text = result[0].get('generated_text', '')
                        if generated_text:
                            return parse_generated_flashcard(generated_text, subject, difficulty)
                
                elif response.status_code == 503:
                    # Model loading, wait and retry
                    logger.info(f"Model loading, waiting... (attempt {attempt + 1})")
                    time.sleep(20)
                    continue
                    
                else:
                    logger.error(f"HuggingFace API error {response.status_code}: {response.text}")
                    break
                    
            except requests.exceptions.Timeout:
                logger.warning(f"HuggingFace API timeout (attempt {attempt + 1})")
                if attempt < max_retries - 1:
                    time.sleep(5)
                    continue
                    
        return None
        
    except Exception as e:
        logger.error(f"HuggingFace generation error: {e}")
        return None
    
def parse_generated_flashcard(generated_text, subject, difficulty):
    """Enhanced parsing with multiple fallback strategies"""
    try:
        # Clean the text
        text = generated_text.strip()
        
        # Strategy 1: Look for "Question:" and "Answer:" format
        if "Question:" in text and "Answer:" in text:
            parts = text.split("Answer:")
            question = parts[0].replace("Question:", "").strip()
            answer = parts[1].strip()
        
        # Strategy 2: Look for "Q:" and "A:" format
        elif "Q:" in text and "A:" in text:
            parts = text.split("A:")
            question = parts[0].replace("Q:", "").strip()
            answer = parts[1].strip()
        
        # Strategy 3: Split by newlines and assume first is question
        elif "\n" in text:
            lines = [line.strip() for line in text.split('\n') if line.strip()]
            if len(lines) >= 2:
                question = lines[0]
                answer = " ".join(lines[1:])
            else:
                question = f"What can you tell me about {subject}?"
                answer = text
        
        # Strategy 4: Use entire text as answer with generated question
        else:
            question = f"Based on your {subject} knowledge, explain this concept:"
            answer = text
        
        # Clean and validate
        question = question[:500].strip()
        answer = answer[:1000].strip()
        
        if not question or not answer:
            return None
        
        return {
            'question': question,
            'answer': answer,
            'subject': subject,
            'difficulty': difficulty
        }
        
    except Exception as e:
        logger.error(f"Error parsing generated flashcard: {e}")
        return None


def update_user_streak_on_completion(user_id):
    """Update user's study streak when they complete a task"""
    try:
        conn = get_conn()
        cursor = conn.cursor()
        
        today = datetime.now().date()
        yesterday = today - timedelta(days=1)
        
        # Check if user studied today already
        cursor.execute(
            "SELECT id FROM study_streaks WHERE user_id = %s AND study_date = %s",
            (user_id, today)
        )
        
        if not cursor.fetchone():
            # Check if user studied yesterday to continue streak
            cursor.execute(
                "SELECT id FROM study_streaks WHERE user_id = %s AND study_date = %s",
                (user_id, yesterday)
            )
            
            had_yesterday = cursor.fetchone() is not None
            
            if had_yesterday:
                # Continue streak
                cursor.execute(
                    "UPDATE users SET current_streak = current_streak + 1 WHERE id = %s",
                    (user_id,)
                )
            else:
                # Start new streak
                cursor.execute(
                    "UPDATE users SET current_streak = 1 WHERE id = %s",
                    (user_id,)
                )
            
            # Record today's study
            cursor.execute(
                "INSERT INTO study_streaks (user_id, study_date, cards_studied) VALUES (%s, %s, 1)",
                (user_id, today)
            )
            
            conn.commit()
            
            # Get updated streak
            cursor.execute("SELECT current_streak FROM users WHERE id = %s", (user_id,))
            streak = cursor.fetchone()[0]
            
        cursor.close()
        conn.close()
        return streak
        
    except Exception as e:
        logger.error(f"Error updating streak: {e}")
        return 0

@app.route("/complete_task", methods=["POST"])
@jwt_required()
def complete_task():
    """Mark task as completed and update streak"""
    try:
        user_id = get_jwt_identity()
        streak = update_user_streak_on_completion(user_id)
        
        return jsonify({
            "message": "Task completed!",
            "streak": streak
        }), 200
        
    except Exception as e:
        logger.error(f"Complete task error: {e}")
        return jsonify({"error": "Failed to complete task"}), 500


@app.route("/flashcards_by_subject/<subject>", methods=["GET"])
@jwt_required()
def get_flashcards_by_subject(subject):
    """Get flashcards filtered by subject"""
    try:
        user_id = get_jwt_identity()
        
        conn = get_conn()
        cursor = conn.cursor(dictionary=True)
        
        cursor.execute(
            """
            SELECT id, question, answer, subject, difficulty_level, 
                   times_reviewed, created_at
            FROM flashcards 
            WHERE user_id = %s AND subject = %s
            ORDER BY created_at DESC
            """,
            (user_id, subject)
        )
        
        flashcards = cursor.fetchall()
        cursor.close()
        conn.close()
        
        return jsonify({"flashcards": flashcards}), 200
        
    except Exception as e:
        logger.error(f"Get flashcards by subject error: {e}")
        return jsonify({"error": "Failed to retrieve flashcards"}), 500
    
    import requests

def generate_flashcard_with_huggingface(notes, subject, difficulty='medium'):
    """Generate flashcard using HuggingFace API with difficulty-based prompts"""
    if not HUGGINGFACE_API_TOKEN:
        return None
    
    try:
        # Difficulty-based prompts for better question generation
        difficulty_prompts = {
            'easy': f"Create a simple, basic question and answer about {subject} from these notes. Make it suitable for beginners:",
            'medium': f"Create a moderately challenging question about {subject} that requires understanding. Based on these notes:",
            'hard': f"Create a complex, analytical question about {subject} that requires critical thinking. From these notes:"
        }
        
        prompt = f"{difficulty_prompts.get(difficulty, difficulty_prompts['medium'])} {notes[:800]}\n\nQuestion:"
        
        headers = {
            'Authorization': f'Bearer {HUGGINGFACE_API_TOKEN}',
            'Content-Type': 'application/json'
        }
        
        # Use a text generation model suitable for Q&A
        api_url = "https://api-inference.huggingface.co/models/google/flan-t5-large"
        
        payload = {
            "inputs": prompt,
            "parameters": {
                "max_new_tokens": 200,
                "temperature": 0.7,
                "do_sample": True
            }
        }
        
        response = requests.post(api_url, headers=headers, json=payload, timeout=30)
        
        if response.status_code == 200:
            result = response.json()
            if isinstance(result, list) and len(result) > 0:
                generated_text = result[0].get('generated_text', '')
                return parse_generated_flashcard(generated_text, subject, difficulty)
        
        return None
        
    except Exception as e:
        logger.error(f"HuggingFace generation error: {e}")
        return None

def parse_generated_flashcard(generated_text, subject, difficulty):
    """Parse generated text into question and answer with subject context"""
    try:
        # Split by common delimiters
        if "Answer:" in generated_text:
            parts = generated_text.split("Answer:")
            question = parts[0].replace("Question:", "").strip()
            answer = parts[1].strip()
        elif "A:" in generated_text:
            parts = generated_text.split("A:")
            question = parts[0].replace("Q:", "").strip()
            answer = parts[1].strip()
        else:
            # Fallback: use the generated text as an answer and create a question
            question = f"What can you tell me about this {subject} concept?"
            answer = generated_text.strip()
        
        return {
            'question': question[:500],  # Limit length
            'answer': answer[:1000],
            'subject': subject,
            'difficulty': difficulty
        }
        
    except Exception as e:
        logger.error(f"Error parsing generated flashcard: {e}")
        return None
    

def generate_flashcard_with_flan_t5(notes, subject, difficulty='medium'):
    """Alternative HuggingFace implementation using Flan-T5"""
    if not HUGGINGFACE_API_TOKEN:
        return None
    
    try:
        # Flan-T5 works better with instruction-following
        instruction = f"Create a {difficulty}-level question and answer about {subject} based on these study notes. Format: Q: [question] A: [answer]"
        prompt = f"{instruction}\n\nNotes: {notes[:500]}"
        
        headers = {
            'Authorization': f'Bearer {HUGGINGFACE_API_TOKEN}',
            'Content-Type': 'application/json'
        }
        
        api_url = "https://api-inference.huggingface.co/models/google/flan-t5-large"
        
        payload = {
            "inputs": prompt,
            "parameters": {
                "max_new_tokens": 200,
                "temperature": 0.8
            }
        }
        
        response = requests.post(api_url, headers=headers, json=payload, timeout=30)
        
        if response.status_code == 200:
            result = response.json()
            if isinstance(result, list) and len(result) > 0:
                generated_text = result[0].get('generated_text', '')
                return parse_generated_flashcard(generated_text, subject, difficulty)
        
        return None
        
    except Exception as e:
        logger.error(f"Flan-T5 generation error: {e}")
        return None

    
@app.route("/update_xp", methods=["POST"])
@jwt_required()
def update_xp():
    """Update user XP and level"""
    try:
        user_id = get_jwt_identity()
        data = request.get_json() or {}
        xp_gained = int(data.get("xp", 0))
        reason = data.get("reason", "")
        
        if xp_gained <= 0:
            return jsonify({"error": "XP must be positive"}), 400
        
        conn = get_conn()
        cursor = conn.cursor(dictionary=True)
        
        # Get current user data
        cursor.execute("SELECT xp, level FROM users WHERE id = %s", (user_id,))
        user = cursor.fetchone()
        
        if not user:
            return jsonify({"error": "User not found"}), 404
        
        old_xp = user['xp'] or 0
        old_level = user['level'] or 1
        new_xp = old_xp + xp_gained
        
        # Calculate new level (every 100 XP = 1 level)
        new_level = max(1, new_xp // 100 + 1)
        
        # Update user
        cursor.execute(
            "UPDATE users SET xp = %s, level = %s WHERE id = %s",
            (new_xp, new_level, user_id)
        )
        
        # Log XP gain
        cursor.execute(
            """
            INSERT INTO xp_log (user_id, xp_gained, reason, created_at)
            VALUES (%s, %s, %s, NOW())
            """,
            (user_id, xp_gained, reason)
        )
        
        conn.commit()
        cursor.close()
        conn.close()
        
        level_up = new_level > old_level
        
        return jsonify({
            "xp": new_xp,
            "level": new_level,
            "level_up": level_up,
            "xp_gained": xp_gained
        }), 200
        
    except Exception as e:
        logger.error(f"Update XP error: {e}")
        return jsonify({"error": "Failed to update XP"}), 500



def generate_congratulatory_story(subject, card_count):
    """Generate a story when user creates 15+ cards in a subject"""
    if not HUGGINGFACE_API_TOKEN:
        return None
    
    try:
        prompt = f"Write a short, encouraging story (2-3 sentences) congratulating a student who just created {card_count} flashcards about {subject}. Make it motivational and subject-specific."
        
        headers = {
            'Authorization': f'Bearer {HUGGINGFACE_API_TOKEN}',
            'Content-Type': 'application/json'
        }
        
        api_url = "https://api-inference.huggingface.co/models/google/flan-t5-large"
        
        payload = {
            "inputs": prompt,
            "parameters": {
                "max_new_tokens": 150,
                "temperature": 0.8
            }
        }
        
        response = requests.post(api_url, headers=headers, json=payload, timeout=20)
        
        if response.status_code == 200:
            result = response.json()
            if isinstance(result, list) and len(result) > 0:
                return result[0].get('generated_text', '').strip()
        
        return None
        
    except Exception as e:
        logger.error(f"Story generation error: {e}")
        return None

@app.route("/check_milestone", methods=["POST"])
@jwt_required()
def check_milestone():
    """Check if user has reached card creation milestone"""
    try:
        user_id = get_jwt_identity()
        data = request.get_json() or {}
        subject = data.get("subject")
        
        conn = get_conn()
        cursor = conn.cursor()
        
        # Count cards in subject created today
        cursor.execute(
            """
            SELECT COUNT(*) as count
            FROM flashcards 
            WHERE user_id = %s AND subject = %s AND DATE(created_at) = CURDATE()
            """,
            (user_id, subject)
        )
        
        count = cursor.fetchone()[0]
        cursor.close()
        conn.close()
        
        story = None
        if count >= 15:
            story = generate_congratulatory_story(subject, count)
        
        return jsonify({
            "count": count,
            "milestone_reached": count >= 15,
            "story": story
        }), 200
        
    except Exception as e:
        logger.error(f"Check milestone error: {e}")
        return jsonify({"error": "Failed to check milestone"}), 500






# Add these missing endpoints to your Flask backend

# 1. Generate AI flashcards endpoint (called by generateAIFlashcards())
# @app.route("/generate_flashcards", methods=["POST"])
# @jwt_required(optional=True)
# def generate_flashcards():
#     """Generate flashcards using HuggingFace AI"""
#     try:
#         data = request.get_json() or {}
#         notes = data.get("notes", "").strip()
#         subject = data.get("subject", "general")
#         difficulty = data.get("difficulty", "medium")
        
#         if not notes:
#             return jsonify({"error": "Notes are required"}), 400
        
#         # Try to generate with HuggingFace
#         generated_cards = []
#         for i in range(3):  # Generate 3 cards
#             ai_card = generate_flashcard_with_huggingface(notes, subject, difficulty)
#             if ai_card:
#                 generated_cards.append(ai_card)
#             else:
#                 # Fallback to sample data
#                 fallback_card = {
#                     'question': f"What key concept from {subject} can you identify in these notes?",
#                     'answer': f"Based on the notes: {notes[:100]}...",
#                     'subject': subject,
#                     'difficulty': difficulty
#                 }
#                 generated_cards.append(fallback_card)
        
#         return jsonify({"flashcards": generated_cards}), 200
        
#     except Exception as e:
#         logger.error(f"Generate flashcards error: {e}")
#         return jsonify({"error": "Failed to generate flashcards"}), 500

# 2. Todo endpoints (called by todo functions)
@app.route("/todos", methods=["GET"])
@jwt_required()
def get_todos():
    """Get user's todo items"""
    try:
        user_id = get_jwt_identity()
        
        conn = get_conn()
        cursor = conn.cursor(dictionary=True)
        
        cursor.execute(
            """
            SELECT id, title, description, due_date, priority, subject, completed, created_at
            FROM todos 
            WHERE user_id = %s
            ORDER BY due_date ASC, created_at DESC
            """,
            (user_id,)
        )
        
        todos = cursor.fetchall()
        cursor.close()
        conn.close()
        
        return jsonify({"todos": todos}), 200
        
    except Exception as e:
        logger.error(f"Get todos error: {e}")
        return jsonify({"error": "Failed to retrieve todos"}), 500

@app.route("/todos", methods=["POST"])
@jwt_required()
def save_todo():
    """Save new todo item"""
    try:
        user_id = get_jwt_identity()
        data = request.get_json() or {}
        
        title = data.get("title", "").strip()
        description = data.get("description", "").strip()
        due_date = data.get("date")
        priority = data.get("priority", "medium")
        subject = data.get("subject", "other")
        
        if not title or not due_date:
            return jsonify({"error": "Title and due date are required"}), 400
        
        conn = get_conn()
        cursor = conn.cursor()
        
        cursor.execute(
            """
            INSERT INTO todos (user_id, title, description, due_date, priority, subject)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (user_id, title, description, due_date, priority, subject)
        )
        
        conn.commit()
        todo_id = cursor.lastrowid
        cursor.close()
        conn.close()
        
        return jsonify({
            "message": "Todo saved successfully",
            "id": todo_id
        }), 201
        
    except Exception as e:
        logger.error(f"Save todo error: {e}")
        return jsonify({"error": "Failed to save todo"}), 500

@app.route("/todos/<int:todo_id>", methods=["PUT"])
@jwt_required()
def update_todo(todo_id):
    """Update todo completion status"""
    try:
        user_id = get_jwt_identity()
        data = request.get_json() or {}
        completed = data.get("completed", False)
        
        conn = get_conn()
        cursor = conn.cursor()
        
        cursor.execute(
            """
            UPDATE todos 
            SET completed = %s, updated_at = CURRENT_TIMESTAMP
            WHERE id = %s AND user_id = %s
            """,
            (completed, todo_id, user_id)
        )
        
        if cursor.rowcount == 0:
            cursor.close()
            conn.close()
            return jsonify({"error": "Todo not found"}), 404
        
        conn.commit()
        cursor.close()
        conn.close()
        
        # Award XP for completion
        if completed:
            # You can call your existing update_xp endpoint internally
            pass
        
        return jsonify({"message": "Todo updated successfully"}), 200
        
    except Exception as e:
        logger.error(f"Update todo error: {e}")
        return jsonify({"error": "Failed to update todo"}), 500

@app.route("/todos/<int:todo_id>", methods=["DELETE"])
@jwt_required()
def delete_todo(todo_id):
    """Delete todo item"""
    try:
        user_id = get_jwt_identity()
        
        conn = get_conn()
        cursor = conn.cursor()
        
        cursor.execute(
            "DELETE FROM todos WHERE id = %s AND user_id = %s",
            (todo_id, user_id)
        )
        
        if cursor.rowcount == 0:
            cursor.close()
            conn.close()
            return jsonify({"error": "Todo not found"}), 404
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify({"message": "Todo deleted successfully"}), 200
        
    except Exception as e:
        logger.error(f"Delete todo error: {e}")
        return jsonify({"error": "Failed to delete todo"}), 500

# 3. Enhanced user profile endpoint
@app.route("/profile", methods=["GET"])
@jwt_required()
def get_user_profile():
    """Get comprehensive user profile with stats"""
    try:
        user_id = get_jwt_identity()
        
        conn = get_conn()
        cursor = conn.cursor(dictionary=True)
        
        # Get user basic info with stats
        cursor.execute(
            """
            SELECT id, username, email, xp, level, current_streak, 
                   best_streak, total_cards, created_at
            FROM users 
            WHERE id = %s
            """,
            (user_id,)
        )
        
        user = cursor.fetchone()
        if not user:
            return jsonify({"error": "User not found"}), 404
        
        # Get subject breakdown
        cursor.execute(
            """
            SELECT subject, COUNT(*) as count
            FROM flashcards 
            WHERE user_id = %s
            GROUP BY subject
            ORDER BY count DESC
            """,
            (user_id,)
        )
        
        subjects = cursor.fetchall()
        
        # Get recent activity
        cursor.execute(
            """
            SELECT created_at, 'flashcard' as activity_type, subject
            FROM flashcards 
            WHERE user_id = %s
            ORDER BY created_at DESC
            LIMIT 10
            """,
            (user_id,)
        )
        
        activities = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        return jsonify({
            "user": user,
            "subjects": subjects,
            "recent_activities": activities
        }), 200
        
    except Exception as e:
        logger.error(f"Get profile error: {e}")
        return jsonify({"error": "Failed to retrieve profile"}), 500

# 4. Missing database table for todos
def ensure_tables():
    """Create all necessary tables if they don't exist - ADD THIS TO YOUR EXISTING FUNCTION"""
    conn = get_conn()
    cur = conn.cursor()
    
    try:
        # Add this todos table creation to your existing ensure_tables function
        cur.execute("""
        CREATE TABLE IF NOT EXISTS todos (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL,
            title VARCHAR(255) NOT NULL,
            description TEXT,
            due_date DATE NOT NULL,
            priority ENUM('low', 'medium', 'high') DEFAULT 'medium',
            subject VARCHAR(50) DEFAULT 'other',
            completed BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            INDEX idx_user_due (user_id, due_date),
            INDEX idx_completed (completed)
        ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
        """)
        
        # Add this timetable table to your existing ensure_tables function
        cur.execute("""
        CREATE TABLE IF NOT EXISTS timetable_entries (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL,
            subject VARCHAR(50) NOT NULL,
            day_of_week VARCHAR(10) NOT NULL,
            start_time TIME NOT NULL,
            end_time TIME NOT NULL,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            INDEX idx_user_day (user_id, day_of_week)
        ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
        """)
        
        conn.commit()
        logger.info("Additional tables created/verified successfully")
        
    except Exception as e:
        logger.error(f"Additional table creation failed: {e}")
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()










def revoke_refresh_token(jti):
    """Revoke a refresh token"""
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("UPDATE refresh_tokens SET revoked = TRUE WHERE jti = %s", (jti,))
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        logger.error(f"Error revoking token: {e}")

# JWT callback to check token revocation (blocklist)
@jwt.token_in_blocklist_loader
def check_if_token_revoked(jwt_headers, jwt_payload):
    """Check if JWT token is revoked"""
    jti = jwt_payload.get("jti")
    token_type = jwt_payload.get("type")
    if token_type == "refresh":
        return is_refresh_token_revoked(jti)
    return False

# ---------------------------
# IntaSend client setup
# ---------------------------
inta_client = None
if APIService is not None and INTASEND_SECRET:
    try:
        inta_client = APIService(
            token=INTASEND_SECRET, 
            publishable_key=INTASEND_PUBLISHABLE, 
            test=INTASEND_TEST
        )
        logger.info("IntaSend client initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize IntaSend client: {e}")
        inta_client = None

# ---------------------------
# Helper functions
# ---------------------------
def validate_flashcard_data(flashcard):
    """Validate individual flashcard data"""
    required_fields = ['question', 'answer']
    for field in required_fields:
        if not flashcard.get(field) or not str(flashcard[field]).strip():
            return False, f"Missing or empty {field}"
    return True, "Valid"

# ---------------------------
# Authentication Routes
# ---------------------------
@app.route("/")
def index():
    """Main route - serve frontend or status"""
    try:
        return render_template("index.html")
    except Exception:
        return jsonify({
            "status": "AI Study Buddy server running",
            "version": "2.0",
            "endpoints": ["/signup", "/login", "/save_flashcards", "/my_flashcards", "/pay"]
        }), 200

@app.route("/signup", methods=["POST"])
def signup():
    """Register new user with enhanced validation"""
    try:
        data = request.get_json() or {}
        username = (data.get("username") or "").strip()
        email = (data.get("email") or "").strip().lower()
        password = data.get("password") or ""

        # Validation
        if not username or not email or not password:
            return jsonify({"error": "Username, email and password are required"}), 400

        if len(password) < 6:
            return jsonify({"error": "Password must be at least 6 characters long"}), 400

        if len(username) < 3:
            return jsonify({"error": "Username must be at least 3 characters long"}), 400

        # Email basic validation
        if "@" not in email or "." not in email:
            return jsonify({"error": "Invalid email format"}), 400

        hashed = generate_password_hash(password, method="pbkdf2:sha256")
        
        conn = get_conn()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO users (username, email, password) VALUES (%s, %s, %s)",
            (username, email, hashed)
        )
        conn.commit()
        cur.close()
        conn.close()
        
        logger.info(f"New user registered: {email}")
        return jsonify({"message": "User registered successfully"}), 201
        
    except mysql.connector.IntegrityError as e:
        error_msg = str(e)
        if "username" in error_msg:
            return jsonify({"error": "Username already exists"}), 400
        elif "email" in error_msg:
            return jsonify({"error": "Email already exists"}), 400
        return jsonify({"error": "Registration failed"}), 400
    except Exception as e:
        logger.error(f"Signup error: {e}")
        return jsonify({"error": "Internal server error"}), 500

@app.route("/login", methods=["POST"])
def login():
    """Authenticate user with email or username"""
    try:
        data = request.get_json() or {}
        username_or_email = (data.get("username") or data.get("email") or "").strip().lower()
        password = data.get("password") or ""

        if not username_or_email or not password:
            return jsonify({"error": "Username/email and password are required"}), 400

        conn = get_conn()
        cur = conn.cursor(dictionary=True)
        
        # Try both username and email
        cur.execute(
            "SELECT id, username, email, password FROM users WHERE username = %s OR email = %s", 
            (username_or_email, username_or_email)
        )
        user = cur.fetchone()
        cur.close()
        conn.close()

        if not user or not check_password_hash(user["password"], password):
            return jsonify({"error": "Invalid credentials"}), 401

        user_id = user["id"]
        access_token = create_access_token(identity=str(user_id))
        refresh_token = create_refresh_token(identity=str(user_id))

        # Store refresh token JTI and expiry
        decoded = decode_token(refresh_token)
        jti = decoded.get("jti")
        exp_ts = decoded.get("exp")
        expires_at = datetime.utcfromtimestamp(exp_ts)
        store_refresh_token(jti, user_id, expires_at)

        logger.info(f"User logged in: {user['email']}")
        return jsonify({
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_in": int(app.config["JWT_ACCESS_TOKEN_EXPIRES"].total_seconds()),
            "user": {
                "id": user_id,
                "username": user["username"],
                "email": user["email"]
            }
        }), 200
        
    except Exception as e:
        logger.error(f"Login error: {e}")
        return jsonify({"error": "Internal server error"}), 500

@app.route("/refresh", methods=["POST"])
@jwt_required(refresh=True)
def refresh():
    """Exchange valid refresh token for new access token"""
    try:
        current_user_id = get_jwt_identity()
        new_access = create_access_token(identity=current_user_id)
        return jsonify({"access_token": new_access}), 200
    except Exception as e:
        logger.error(f"Token refresh error: {e}")
        return jsonify({"error": "Failed to refresh token"}), 500

@app.route("/logout", methods=["POST"])
@jwt_required(refresh=True)
def logout():
    """Revoke refresh token (logout)"""
    try:
        jti = get_jwt().get("jti")
        revoke_refresh_token(jti)
        return jsonify({"message": "Logged out successfully"}), 200
    except Exception as e:
        logger.error(f"Logout error: {e}")
        return jsonify({"error": "Logout failed"}), 500

# ---------------------------
# Flashcard Routes (Enhanced)
# ---------------------------
# @app.route("/save_flashcards", methods=["POST"])
# def save_flashcards():
#     """Save flashcards (works for both authenticated and guest users)"""
#     try:
#         # Get user ID if authenticated, otherwise None for guest
#         user_id = None
#         try:
#             if request.headers.get('Authorization'):
#                 from flask_jwt_extended import verify_jwt_in_request
#                 verify_jwt_in_request()
#                 user_id = get_jwt_identity()
#         except:
#             # Guest user - continue without authentication
#             pass

#         data = request.get_json()
#         if not data:
#             return jsonify({"error": "No data provided"}), 400

#         subject = data.get("subject")
#         notes = data.get("notes", "")
#         flashcards = data.get("flashcards", [])

#         if not subject:
#             return jsonify({"error": "Subject is required"}), 400
            
#         if not flashcards or not isinstance(flashcards, list):
#             return jsonify({"error": "Flashcards array is required"}), 400

#         # Validate each flashcard
#         for i, fc in enumerate(flashcards):
#             is_valid, error_msg = validate_flashcard_data(fc)
#             if not is_valid:
#                 return jsonify({"error": f"Flashcard {i+1}: {error_msg}"}), 400

#         # Save to database
#         conn = get_conn()
#         cursor = conn.cursor()
        
#         saved_count = 0
#         for fc in flashcards:
#             cursor.execute(
#                 """
#                 INSERT INTO flashcards (user_id, subject, notes, question, answer) 
#                 VALUES (%s, %s, %s, %s, %s)
#                 """,
#                 (user_id, subject, notes, fc["question"], fc["answer"])
#             )
#             saved_count += 1
        
#         conn.commit()
#         cursor.close()
#         conn.close()
        
#         logger.info(f"Saved {saved_count} flashcards for {'user ' + str(user_id) if user_id else 'guest'}")
#         return jsonify({
#             "message": f"Successfully saved {saved_count} flashcards",
#             "count": saved_count
#         }), 201
        
#     except Exception as e:
#         logger.error(f"Save flashcards error: {e}")
#         return jsonify({"error": "Failed to save flashcards"}), 500

@app.route("/my_flashcards", methods=["GET"])
@jwt_required()
def my_flashcards():
    """Get user's flashcards with filtering and pagination"""
    try:
        user_id = get_jwt_identity()
        
        # Get query parameters
        subject = request.args.get('subject')
        limit = request.args.get('limit', 50, type=int)
        offset = request.args.get('offset', 0, type=int)
        
        # Ensure reasonable limits
        limit = min(limit, 100)  # Max 100 per request
        offset = max(offset, 0)   # No negative offset
        
        conn = get_conn()
        cursor = conn.cursor(dictionary=True)
        
        # Build query
        base_query = """
            SELECT id, subject, notes, question, answer, difficulty_level, 
                   times_reviewed, last_reviewed, created_at, updated_at
            FROM flashcards 
            WHERE user_id = %s
        """
        params = [user_id]
        
        if subject and subject != 'all':
            base_query += " AND subject = %s"
            params.append(subject)
            
        base_query += " ORDER BY created_at DESC LIMIT %s OFFSET %s"
        params.extend([limit, offset])
        
        cursor.execute(base_query, params)
        flashcards = cursor.fetchall()
        
        # Get total count
        count_query = "SELECT COUNT(*) as total FROM flashcards WHERE user_id = %s"
        count_params = [user_id]
        if subject and subject != 'all':
            count_query += " AND subject = %s"
            count_params.append(subject)
            
        cursor.execute(count_query, count_params)
        total = cursor.fetchone()['total']
        
        cursor.close()
        conn.close()
        
        return jsonify({
            "flashcards": flashcards,
            "total": total,
            "limit": limit,
            "offset": offset
        }), 200
        
    except Exception as e:
        logger.error(f"Get flashcards error: {e}")
        return jsonify({"error": "Failed to retrieve flashcards"}), 500

@app.route("/flashcards/<int:flashcard_id>", methods=["DELETE"])
@jwt_required()
def delete_flashcard(flashcard_id):
    """Delete specific flashcard"""
    try:
        user_id = get_jwt_identity()
        
        conn = get_conn()
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM flashcards WHERE id = %s AND user_id = %s",
            (flashcard_id, user_id)
        )
        
        if cursor.rowcount == 0:
            cursor.close()
            conn.close()
            return jsonify({"error": "Flashcard not found"}), 404
            
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify({"message": "Flashcard deleted successfully"}), 200
        
    except Exception as e:
        logger.error(f"Delete flashcard error: {e}")
        return jsonify({"error": "Failed to delete flashcard"}), 500

@app.route("/flashcards/<int:flashcard_id>/review", methods=["POST"])
@jwt_required()
def mark_reviewed(flashcard_id):
    """Mark flashcard as reviewed"""
    try:
        user_id = get_jwt_identity()
        
        conn = get_conn()
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE flashcards 
            SET times_reviewed = times_reviewed + 1, 
                last_reviewed = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s AND user_id = %s
            """,
            (flashcard_id, user_id)
        )
        
        if cursor.rowcount == 0:
            cursor.close()
            conn.close()
            return jsonify({"error": "Flashcard not found"}), 404
            
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify({"message": "Flashcard marked as reviewed"}), 200
        
    except Exception as e:
        logger.error(f"Mark reviewed error: {e}")
        return jsonify({"error": "Failed to mark as reviewed"}), 500

# ---------------------------
# Legacy Routes (for compatibility)
# ---------------------------
@app.route("/add_flashcard", methods=["POST"])
@jwt_required()
def add_flashcard():
    """Add single flashcard (legacy route)"""
    try:
        current_user_id = get_jwt_identity()
        data = request.get_json() or {}
        question = (data.get("question") or "").strip()
        answer = (data.get("answer") or "").strip()
        subject = data.get("subject", "general")

        if not question or not answer:
            return jsonify({"error": "Question and answer are required"}), 400

        conn = get_conn()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO flashcards (question, answer, user_id, subject) VALUES (%s, %s, %s, %s)",
            (question, answer, current_user_id, subject)
        )
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({"message": "Flashcard added successfully"}), 201
        
    except Exception as e:
        logger.error(f"Add flashcard error: {e}")
        return jsonify({"error": "Failed to add flashcard"}), 500

@app.route("/flashcards", methods=["GET"])
@jwt_required()
def get_flashcards():
    """Get flashcards (legacy route)"""
    try:
        current_user_id = get_jwt_identity()
        conn = get_conn()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, question, answer, subject, created_at 
            FROM flashcards 
            WHERE user_id = %s 
            ORDER BY created_at DESC
            """,
            (current_user_id,)
        )
        rows = cur.fetchall()
        cur.close()
        conn.close()
        
        result = [{
            "id": r[0], 
            "question": r[1], 
            "answer": r[2], 
            "subject": r[3],
            "created_at": str(r[4])
        } for r in rows]
        
        return jsonify(result), 200
        
    except Exception as e:
        logger.error(f"Get flashcards error: {e}")
        return jsonify({"error": "Failed to retrieve flashcards"}), 500

# ---------------------------
# Payment Routes (IntaSend Integration)
# ---------------------------
@app.route("/pay", methods=["POST"])
@jwt_required()
def pay():
    """Create payment checkout using IntaSend"""
    if inta_client is None:
        return jsonify({
            "error": "IntaSend not configured. Install intasend-python and set INTASEND_SECRET_KEY"
        }), 500

    try:
        user_id = get_jwt_identity()
        data = request.get_json() or {}
        
        try:
            amount = int(data.get("amount", 0))
        except (TypeError, ValueError):
            return jsonify({"error": "Invalid amount"}), 400

        if amount <= 0:
            return jsonify({"error": "Amount must be greater than 0"}), 400

        currency = (data.get("currency") or "KES").upper()
        metadata = data.get("metadata") or {}
        description = data.get("description") or f"AI Study Buddy - Payment by user {user_id}"

        # Add user ID to metadata
        metadata["user_id"] = user_id

        body = {
            "amount": amount,
            "currency": currency,
            "description": description,
            "metadata": metadata
        }

        # Create checkout with IntaSend
        try:
            if hasattr(inta_client, "checkout_create"):
                checkout_resp = inta_client.checkout_create(body)
            elif hasattr(inta_client, "create_checkout"):
                checkout_resp = inta_client.create_checkout(body)
            elif hasattr(inta_client, "create_payment_link"):
                checkout_resp = inta_client.create_payment_link(body)
            else:
                checkout_resp = inta_client.create(body)
        except Exception as e:
            logger.error(f"IntaSend API error: {e}")
            return jsonify({"error": "Failed to create payment checkout"}), 500

        # Extract checkout URL
        checkout_url = None
        if isinstance(checkout_resp, dict):
            # Try different possible URL keys
            for key in ("url", "checkout_url", "payment_url", "redirect_url"):
                if key in checkout_resp and isinstance(checkout_resp[key], str):
                    checkout_url = checkout_resp[key]
                    break
            # Check nested data object
            if not checkout_url and "data" in checkout_resp and isinstance(checkout_resp["data"], dict):
                for key in ("url", "checkout_url", "payment_url", "redirect_url"):
                    if key in checkout_resp["data"]:
                        checkout_url = checkout_resp["data"][key]
                        break
        else:
            # Try object attributes
            for attr in ("url", "checkout_url", "payment_url", "redirect_url"):
                if hasattr(checkout_resp, attr):
                    val = getattr(checkout_resp, attr)
                    if isinstance(val, str):
                        checkout_url = val
                        break

        # Store payment record
        try:
            conn = get_conn()
            cur = conn.cursor()
            ref = None
            if isinstance(checkout_resp, dict):
                ref = checkout_resp.get("ref") or checkout_resp.get("reference") or checkout_resp.get("id")
                if not ref and "data" in checkout_resp:
                    ref = checkout_resp["data"].get("ref") or checkout_resp["data"].get("reference")
            elif hasattr(checkout_resp, "reference"):
                ref = getattr(checkout_resp, "reference")
            elif hasattr(checkout_resp, "ref"):
                ref = getattr(checkout_resp, "ref")
            
            cur.execute(
                """
                INSERT INTO payments (user_id, ref, amount, currency, status, metadata) 
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (user_id, ref, amount, currency, "created", json.dumps(metadata))
            )
            conn.commit()
            cur.close()
            conn.close()
        except Exception as e:
            logger.warning(f"Failed to store payment record: {e}")

        if checkout_url:
            return jsonify({"checkout_url": checkout_url}), 201
        
        # Fallback: return full response for debugging
        return jsonify({"checkout": checkout_resp}), 201

    except Exception as e:
        logger.error(f"Payment creation error: {e}")
        return jsonify({"error": "Failed to create payment"}), 500

@app.route("/payment-callback", methods=["POST"])
def payment_callback():
    """Handle IntaSend payment webhooks"""
    try:
        payload = request.get_json() or {}
        ref = (payload.get("ref") or 
               payload.get("reference") or 
               payload.get("data", {}).get("ref") or
               payload.get("data", {}).get("reference"))
        
        status = (payload.get("status") or 
                 payload.get("state") or 
                 payload.get("data", {}).get("status"))
        
        metadata = (payload.get("metadata") or 
                   payload.get("data", {}).get("metadata") or {})

        if not ref:
            return jsonify({"error": "Missing payment reference"}), 400

        conn = get_conn()
        cur = conn.cursor()
        
        # Check if payment exists
        cur.execute("SELECT id, user_id FROM payments WHERE ref = %s", (ref,))
        row = cur.fetchone()
        
        if row:
            # Update existing payment
            cur.execute(
                "UPDATE payments SET status = %s, metadata = %s, updated_at = CURRENT_TIMESTAMP WHERE ref = %s",
                (status, json.dumps(metadata), ref)
            )
            logger.info(f"Updated payment {ref} with status {status}")
        else:
            # Create new payment record
            user_id = metadata.get("user_id") if isinstance(metadata, dict) else None
            cur.execute(
                """
                INSERT INTO payments (user_id, ref, amount, currency, status, metadata) 
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (user_id, ref, 0, "KES", status, json.dumps(metadata))
            )
            logger.info(f"Created new payment record for {ref} with status {status}")
        
        conn.commit()
        cur.close()
        conn.close()

        return jsonify({"message": "Payment callback processed successfully"}), 200

    except Exception as e:
        logger.error(f"Payment callback error: {e}")
        return jsonify({"error": "Failed to process payment callback"}), 500

@app.route("/payments", methods=["GET"])
@jwt_required()
def get_user_payments():
    """Get user's payment history"""
    try:
        user_id = get_jwt_identity()
        
        conn = get_conn()
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            SELECT id, ref, amount, currency, status, metadata, created_at, updated_at
            FROM payments 
            WHERE user_id = %s 
            ORDER BY created_at DESC
            """,
            (user_id,)
        )
        payments = cur.fetchall()
        cur.close()
        conn.close()
        
        return jsonify({"payments": payments}), 200
        
    except Exception as e:
        logger.error(f"Get payments error: {e}")
        return jsonify({"error": "Failed to retrieve payments"}), 500

# ---------------------------
# Statistics and Analytics Routes
# ---------------------------
@app.route("/stats", methods=["GET"])
@jwt_required()
def get_user_stats():
    """Get comprehensive user statistics"""
    try:
        user_id = get_jwt_identity()
        
        conn = get_conn()
        cursor = conn.cursor(dictionary=True)
        
        # Get flashcard counts by subject
        cursor.execute(
            """
            SELECT subject, COUNT(*) as count 
            FROM flashcards 
            WHERE user_id = %s 
            GROUP BY subject
            ORDER BY count DESC
            """,
            (user_id,)
        )
        subject_counts = cursor.fetchall()
        
        # Get total flashcards
        cursor.execute(
            "SELECT COUNT(*) as total FROM flashcards WHERE user_id = %s",
            (user_id,)
        )
        total_flashcards = cursor.fetchone()['total']
        
        # Get recently reviewed (today)
        cursor.execute(
            """
            SELECT COUNT(*) as reviewed_today 
            FROM flashcards 
            WHERE user_id = %s AND DATE(last_reviewed) = CURDATE()
            """,
            (user_id,)
        )
        reviewed_today = cursor.fetchone()['reviewed_today']
        
        # Get review streak (consecutive days)
        cursor.execute(
            """
            SELECT DISTINCT DATE(last_reviewed) as review_date
            FROM flashcards 
            WHERE user_id = %s AND last_reviewed IS NOT NULL
            ORDER BY review_date DESC
            LIMIT 30
            """,
            (user_id,)
        )
        review_dates = [row['review_date'] for row in cursor.fetchall()]
        
        # Calculate streak
        streak = 0
        if review_dates:
            current_date = datetime.now().date()
            for date in review_dates:
                if date == current_date or (current_date - date).days == streak + 1:
                    streak += 1
                    current_date = date
                else:
                    break
        
        # Most reviewed subject
        cursor.execute(
            """
            SELECT subject, SUM(times_reviewed) as total_reviews
            FROM flashcards 
            WHERE user_id = %s 
            GROUP BY subject
            ORDER BY total_reviews DESC
            LIMIT 1
            """,
            (user_id,)
        )
        most_reviewed_result = cursor.fetchone()
        most_reviewed_subject = most_reviewed_result['subject'] if most_reviewed_result else None
        
        cursor.close()
        conn.close()
        
        return jsonify({
            "total_flashcards": total_flashcards,
            "reviewed_today": reviewed_today,
            "streak_days": streak,
            "most_reviewed_subject": most_reviewed_subject,
            "by_subject": subject_counts
        }), 200
        
    except Exception as e:
        logger.error(f"Get stats error: {e}")
        return jsonify({"error": "Failed to retrieve statistics"}), 500

@app.route("/study-session", methods=["POST"])
@jwt_required()
def log_study_session():
    """Log a study session for analytics"""
    try:
        user_id = get_jwt_identity()
        data = request.get_json() or {}
        
        subject = data.get("subject", "general")
        flashcards_studied = data.get("flashcards_studied", 0)
        session_duration = data.get("session_duration_minutes", 0)
        
        conn = get_conn()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO study_sessions (user_id, subject, flashcards_studied, session_duration_minutes)
            VALUES (%s, %s, %s, %s)
            """,
            (user_id, subject, flashcards_studied, session_duration)
        )
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify({"message": "Study session logged successfully"}), 201
        
    except Exception as e:
        logger.error(f"Log study session error: {e}")
        return jsonify({"error": "Failed to log study session"}), 500

# ---------------------------
# Admin Routes (Optional)
# ---------------------------
@app.route("/admin/stats", methods=["GET"])
@jwt_required()
def admin_stats():
    """Get system-wide statistics (implement admin role check as needed)"""
    try:
        # Note: In production, add admin role verification here
        
        conn = get_conn()
        cursor = conn.cursor(dictionary=True)
        
        # Total users
        cursor.execute("SELECT COUNT(*) as total_users FROM users")
        total_users = cursor.fetchone()['total_users']
        
        # Total flashcards
        cursor.execute("SELECT COUNT(*) as total_flashcards FROM flashcards")
        total_flashcards = cursor.fetchone()['total_flashcards']
        
        # Active users (last 7 days)
        cursor.execute(
            """
            SELECT COUNT(DISTINCT user_id) as active_users 
            FROM flashcards 
            WHERE created_at >= DATE_SUB(NOW(), INTERVAL 7 DAY)
            """
        )
        active_users = cursor.fetchone()['active_users']
        
        # Popular subjects
        cursor.execute(
            """
            SELECT subject, COUNT(*) as count 
            FROM flashcards 
            GROUP BY subject 
            ORDER BY count DESC 
            LIMIT 10
            """
        )
        popular_subjects = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        return jsonify({
            "total_users": total_users,
            "total_flashcards": total_flashcards,
            "active_users_7d": active_users,
            "popular_subjects": popular_subjects
        }), 200
        
    except Exception as e:
        logger.error(f"Admin stats error: {e}")
        return jsonify({"error": "Failed to retrieve admin statistics"}), 500

# ---------------------------
# Health Check and Status Routes
# ---------------------------
@app.route("/health", methods=["GET"])
def health_check():
    """Comprehensive health check endpoint"""
    try:
        # Test database connection
        conn = get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        cursor.fetchone()
        cursor.close()
        conn.close()
        
        # Check IntaSend status
        intasend_status = "configured" if inta_client else "not_configured"
        
        return jsonify({
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
            "database": "connected",
            "intasend": intasend_status,
            "version": "2.0"
        }), 200
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return jsonify({
            "status": "unhealthy",
            "timestamp": datetime.utcnow().isoformat(),
            "database": "disconnected",
            "error": str(e)
        }), 503

@app.route("/status", methods=["GET"])
def status():
    """Simple status endpoint"""
    return jsonify({
        "status": "AI Study Buddy Backend Running",
        "version": "2.0",
        "timestamp": datetime.utcnow().isoformat()
    }), 200

# ---------------------------
# Error Handlers
# ---------------------------
@app.errorhandler(404)
def not_found_error(error):
    return jsonify({
        "error": "Endpoint not found",
        "message": "The requested endpoint does not exist"
    }), 404

@app.errorhandler(500)
def internal_error(error):
    logger.error(f"Internal server error: {error}")
    return jsonify({
        "error": "Internal server error",
        "message": "Something went wrong on our end"
    }), 500

@app.errorhandler(400)
def bad_request_error(error):
    return jsonify({
        "error": "Bad request",
        "message": "The request could not be understood"
    }), 400

# JWT Error Handlers
@jwt.expired_token_loader
def expired_token_callback(jwt_header, jwt_payload):
    return jsonify({
        "error": "Token has expired",
        "message": "Please refresh your token or login again"
    }), 401

@jwt.invalid_token_loader
def invalid_token_callback(error):
    return jsonify({
        "error": "Invalid token",
        "message": "The provided token is not valid"
    }), 401

@jwt.unauthorized_loader
def missing_token_callback(error):
    return jsonify({
        "error": "Authorization token required",
        "message": "Please provide a valid access token"
    }), 401

@jwt.revoked_token_loader
def revoked_token_callback(jwt_header, jwt_payload):
    return jsonify({
        "error": "Token has been revoked",
        "message": "Please login again"
    }), 401

# ---------------------------
# Database Maintenance Routes (Optional)
# ---------------------------
@app.route("/admin/cleanup", methods=["POST"])
@jwt_required()
def cleanup_database():
    """Clean up expired tokens and old data"""
    try:
        # Note: Add admin role check in production
        
        conn = get_conn()
        cursor = conn.cursor()
        
        # Clean up expired refresh tokens
        cursor.execute(
            "DELETE FROM refresh_tokens WHERE expires_at < NOW() OR revoked = TRUE"
        )
        expired_tokens = cursor.rowcount
        
        # Clean up old guest flashcards (optional, older than 30 days)
        cursor.execute(
            """
            DELETE FROM flashcards 
            WHERE user_id IS NULL 
            AND created_at < DATE_SUB(NOW(), INTERVAL 30 DAY)
            """
        )
        old_guest_cards = cursor.rowcount
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify({
            "message": "Database cleanup completed",
            "expired_tokens_removed": expired_tokens,
            "old_guest_flashcards_removed": old_guest_cards
        }), 200
        
    except Exception as e:
        logger.error(f"Database cleanup error: {e}")
        return jsonify({"error": "Database cleanup failed"}), 500

# ---------------------------
# Application Startup
# ---------------------------
def create_app():
    """Application factory pattern"""
    return app@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "message": "Backend running"}), 200

@app.route("/dashboard", methods=["GET"])
@jwt_required()
def dashboard():
    user_id = get_jwt_identity()
    conn = get_conn()
    cur = conn.cursor(dictionary=True)
    cur.execute("SELECT username, email FROM users WHERE id = %s", (user_id,))
    user = cur.fetchone()

    # Count flashcards
    cur.execute("SELECT COUNT(*) as total_cards FROM flashcards WHERE user_id = %s", (user_id,))
    stats = cur.fetchone()
    cur.close()
    conn.close()

    # TODO: Replace with real XP/streak tracking (needs new DB fields)
    return jsonify({
        "user": {
            "id": user_id,
            "username": user["username"],
            "email": user["email"],
            "level": 1,
            "xp": 0,
            "current_streak": 0,
            "total_cards": stats["total_cards"]
        }
    }), 200

# Update your generate_flashcards endpoint to use both models
@app.route("/generate_flashcards", methods=["POST"])
@jwt_required(optional=True)
def generate_flashcards():
    """Enhanced generate flashcards with fallbacks"""
    try:
        data = request.get_json() or {}
        notes = data.get("notes", "").strip()
        subject = data.get("subject", "general")
        difficulty = data.get("difficulty", "medium")
        count = data.get("count", 3)  # Allow customizable count
        
        if not notes:
            return jsonify({"error": "Notes are required"}), 400
        
        generated_cards = []
        
        # Try generating multiple cards
        for i in range(min(count, 5)):  # Max 5 cards per request
            # Try primary method
            ai_card = generate_flashcard_with_huggingface(notes, subject, difficulty)
            
            # Try alternative method if first fails
            if not ai_card:
                ai_card = generate_flashcard_with_flan_t5(notes, subject, difficulty)
            
            # Fallback to rule-based generation
            if not ai_card:
                ai_card = generate_fallback_flashcard(notes, subject, difficulty, i)
            
            if ai_card:
                generated_cards.append(ai_card)
        
        if not generated_cards:
            return jsonify({"error": "Failed to generate flashcards"}), 500
        
        return jsonify({"flashcards": generated_cards}), 200
        
    except Exception as e:
        logger.error(f"Generate flashcards error: {e}")
        return jsonify({"error": "Failed to generate flashcards"}), 500


def generate_fallback_flashcard(notes, subject, difficulty, index=0):
    """Generate fallback flashcard when AI fails"""
    try:
        # Extract key phrases from notes
        words = notes.split()
        key_concepts = [word for word in words if len(word) > 5][:3]
        
        questions = {
            'easy': [
                f"What is the main topic discussed in these {subject} notes?",
                f"Define the key concept mentioned in these {subject} notes.",
                f"What can you learn from these {subject} notes?"
            ],
            'medium': [
                f"How do the concepts in these {subject} notes relate to each other?",
                f"Explain the significance of {key_concepts[0] if key_concepts else 'the main concept'} in {subject}.",
                f"What are the practical applications of these {subject} concepts?"
            ],
            'hard': [
                f"Analyze the implications of the concepts discussed in these {subject} notes.",
                f"How might these {subject} concepts be applied to solve complex problems?",
                f"What are the potential limitations or criticisms of these {subject} ideas?"
            ]
        }
        
        question_list = questions.get(difficulty, questions['medium'])
        question = question_list[index % len(question_list)]
        
        # Create answer based on notes
        answer = f"Based on the provided notes: {notes[:200]}..."
        if len(notes) > 200:
            answer += " [Key concepts to review from your complete notes]"
        
        return {
            'question': question,
            'answer': answer,
            'subject': subject,
            'difficulty': difficulty
        }
        
    except Exception as e:
        logger.error(f"Fallback generation error: {e}")
        return None

@app.route("/study_session", methods=["GET"])
@jwt_required()
def study_session():
    user_id = get_jwt_identity()
    conn = get_conn()
    cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT id, subject, question, answer, difficulty_level as difficulty
        FROM flashcards WHERE user_id = %s ORDER BY RAND() LIMIT 10
    """, (user_id,))
    flashcards = cur.fetchall()
    cur.close()
    conn.close()
    return jsonify({"flashcards": flashcards}), 200

#  @app.route("/update_xp", methods=["POST"])
# @jwt_required()
# def update_xp():
#     user_id = get_jwt_identity()
#     data = request.get_json() or {}
#     xp = data.get("xp", 0)
#     reason = data.get("reason", "")
#     # For now, just log it
#     logger.info(f"User {user_id} gained {xp} XP ({reason})")
#     return jsonify({"message": "XP updated"}), 200

# Fixed save_flashcards route with better authentication and validation
@app.route("/save_flashcards", methods=["POST"])
def save_flashcards():
    """Save flashcards (works for both authenticated and guest users)"""
    try:
        # Get user ID if authenticated, otherwise None for guest
        user_id = None
        authenticated = False
        
        # Check for Authorization header
        auth_header = request.headers.get('Authorization')
        if auth_header and auth_header.startswith('Bearer '):
            try:
                from flask_jwt_extended import verify_jwt_in_request
                verify_jwt_in_request()
                user_id = get_jwt_identity()
                authenticated = True
                logger.info(f"Authenticated request from user: {user_id}")
            except Exception as e:
                logger.warning(f"JWT verification failed: {e}")
                # Continue as guest user

        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400

        subject = data.get("subject")
        notes = data.get("notes", "")
        flashcards = data.get("flashcards", [])

        if not subject:
            return jsonify({"error": "Subject is required"}), 400
            
        if not flashcards or not isinstance(flashcards, list):
            return jsonify({"error": "Flashcards array is required"}), 400

        # Validate each flashcard
        for i, fc in enumerate(flashcards):
            is_valid, error_msg = validate_flashcard_data(fc)
            if not is_valid:
                return jsonify({"error": f"Flashcard {i+1}: {error_msg}"}), 400

        # Save to database
        conn = get_conn()
        cursor = conn.cursor()
        
        saved_count = 0
        try:
            for fc in flashcards:
                # Ensure we have the required fields
                question = fc.get("question", "").strip()
                answer = fc.get("answer", "").strip()
                difficulty = fc.get("difficulty", "medium")
                
                if not question or not answer:
                    continue
                    
                cursor.execute(
                    """
                    INSERT INTO flashcards (user_id, subject, notes, question, answer, difficulty_level) 
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (user_id, subject, notes, question, answer, difficulty)
                )
                saved_count += 1
            
            conn.commit()
            
            # Update user stats if authenticated
            if authenticated and user_id:
                try:
                    # Update user's total card count
                    cursor.execute(
                        "SELECT COUNT(*) FROM flashcards WHERE user_id = %s",
                        (user_id,)
                    )
                    total_cards = cursor.fetchone()[0]
                    
                    # Calculate XP
                    xp_values = {"easy": 3, "medium": 5, "hard": 8}
                    total_xp = sum(xp_values.get(fc.get("difficulty", "medium"), 5) for fc in flashcards)
                    
                    # Update streak (simplified version)
                    cursor.execute(
                        """
                        UPDATE users 
                        SET total_cards = %s, 
                            last_activity = CURRENT_TIMESTAMP,
                            xp = COALESCE(xp, 0) + %s
                        WHERE id = %s
                        """,
                        (total_cards, total_xp, user_id)
                    )
                    conn.commit()
                    
                except Exception as e:
                    logger.warning(f"Failed to update user stats: {e}")
            
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            cursor.close()
            conn.close()
        
        logger.info(f"Saved {saved_count} flashcards for {'user ' + str(user_id) if user_id else 'guest'}")
        
        response_data = {
            "message": f"Successfully saved {saved_count} flashcards",
            "count": saved_count
        }
        
        if authenticated:
            response_data["xp_awarded"] = total_xp
            
        return jsonify(response_data), 201
        
    except Exception as e:
        logger.error(f"Save flashcards error: {e}")
        return jsonify({"error": "Failed to save flashcards"}), 500

# Add a new route to test flashcard saving specifically
@app.route("/test_save", methods=["POST"])
@jwt_required()
def test_save():
    """Test route for debugging flashcard saving"""
    try:
        user_id = get_jwt_identity()
        data = request.get_json() or {}
        
        logger.info(f"Test save request from user {user_id}: {data}")
        
        # Create a simple test flashcard
        conn = get_conn()
        cursor = conn.cursor()
        
        cursor.execute(
            """
            INSERT INTO flashcards (user_id, subject, question, answer, difficulty_level) 
            VALUES (%s, %s, %s, %s, %s)
            """,
            (user_id, "test", "Test question", "Test answer", "medium")
        )
        
        conn.commit()
        flashcard_id = cursor.lastrowid
        
        cursor.close()
        conn.close()
        
        return jsonify({
            "message": "Test flashcard saved successfully",
            "flashcard_id": flashcard_id,
            "user_id": user_id
        }), 201
        
    except Exception as e:
        logger.error(f"Test save error: {e}")
        return jsonify({"error": str(e)}), 500

# Enhanced user table structure to support streaks and stats
def ensure_tables():
    """Create all necessary tables if they don't exist"""
    conn = get_conn()
    cur = conn.cursor()
    
    try:
        # Enhanced users table with streak tracking
        cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INT AUTO_INCREMENT PRIMARY KEY,
            username VARCHAR(80) NOT NULL UNIQUE,
            email VARCHAR(255) NOT NULL UNIQUE,
            password VARCHAR(255) NOT NULL,
            xp INT DEFAULT 0,
            level INT DEFAULT 1,
            current_streak INT DEFAULT 0,
            best_streak INT DEFAULT 0,
            total_cards INT DEFAULT 0,
            last_activity TIMESTAMP NULL,
            last_streak_date DATE NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            INDEX idx_email (email),
            INDEX idx_username (username)
        ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
        """)
        
        # Enhanced flashcards table with better indexing
        cur.execute("""
        CREATE TABLE IF NOT EXISTS flashcards (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NULL,  -- Allow NULL for guest users
            subject VARCHAR(50) NOT NULL,
            notes TEXT,
            question TEXT NOT NULL,
            answer TEXT NOT NULL,
            difficulty_level ENUM('easy', 'medium', 'hard') DEFAULT 'medium',
            times_reviewed INT DEFAULT 0,
            last_reviewed TIMESTAMP NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL,
            INDEX idx_user_subject (user_id, subject),
            INDEX idx_created_at (created_at),
            INDEX idx_subject (subject),
            INDEX idx_user_created (user_id, created_at)
        ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
        """)
        
        # Study streaks tracking table
        cur.execute("""
        CREATE TABLE IF NOT EXISTS study_streaks (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL,
            study_date DATE NOT NULL,
            cards_studied INT DEFAULT 0,
            session_duration INT DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY unique_user_date (user_id, study_date),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            INDEX idx_user_date (user_id, study_date)
        ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
        """)
        
        # Rest of tables remain the same...
        cur.execute("""
        CREATE TABLE IF NOT EXISTS refresh_tokens (
            id INT AUTO_INCREMENT PRIMARY KEY,
            jti VARCHAR(255) NOT NULL UNIQUE,
            user_id INT NOT NULL,
            revoked BOOLEAN DEFAULT FALSE,
            expires_at DATETIME,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            INDEX idx_jti (jti),
            INDEX idx_user_expires (user_id, expires_at)
        ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
        """)
        
        conn.commit()
        logger.info("All database tables created/verified successfully")
        
    except Exception as e:
        logger.error(f"Database table creation failed: {e}")
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()

# Add streak calculation function
def update_user_streak(user_id):
    """Update user's study streak"""
    try:
        conn = get_conn()
        cursor = conn.cursor()
        
        today = datetime.now().date()
        
        # Insert or update today's study record
        cursor.execute(
            """
            INSERT INTO study_streaks (user_id, study_date, cards_studied, session_duration)
            VALUES (%s, %s, 1, 0)
            ON DUPLICATE KEY UPDATE 
            cards_studied = cards_studied + 1,
            session_duration = session_duration
            """,
            (user_id, today)
        )
        
        # Calculate current streak
        cursor.execute(
            """
            SELECT study_date 
            FROM study_streaks 
            WHERE user_id = %s 
            ORDER BY study_date DESC
            """,
            (user_id,)
        )
        
        dates = [row[0] for row in cursor.fetchall()]
        
        # Calculate streak
        current_streak = 0
        if dates:
            current_date = today
            for date in dates:
                if date == current_date or (current_date - date).days == current_streak + 1:
                    current_streak += 1
                    current_date = date
                else:
                    break
        
        # Update user's streak
        cursor.execute(
            """
            UPDATE users 
            SET current_streak = %s,
                best_streak = GREATEST(best_streak, %s),
                last_streak_date = %s,
                last_activity = CURRENT_TIMESTAMP
            WHERE id = %s
            """,
            (current_streak, current_streak, today, user_id)
        )
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return current_streak
        
    except Exception as e:
        logger.error(f"Error updating streak: {e}")
        return 0
    
@app.route("/timetable", methods=["GET"])
@jwt_required()
def get_timetable():
    """Get user's timetable entries"""
    try:
        user_id = get_jwt_identity()
        
        conn = get_conn()
        cursor = conn.cursor(dictionary=True)
        
        cursor.execute(
            """
            SELECT id, subject, day_of_week, start_time, end_time
            FROM timetable_entries 
            WHERE user_id = %s
            ORDER BY FIELD(day_of_week, 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'), start_time
            """,
            (user_id,)
        )
        
        entries = cursor.fetchall()
        cursor.close()
        conn.close()
        
        return jsonify({"timetable": entries}), 200
        
    except Exception as e:
        logger.error(f"Get timetable error: {e}")
        return jsonify({"error": "Failed to retrieve timetable"}), 500

@app.route("/timetable", methods=["POST"])
@jwt_required()
def save_timetable():
    """Save new timetable entry"""
    try:
        user_id = get_jwt_identity()
        data = request.get_json() or {}
        
        subject = data.get("subject")
        day = data.get("day")
        start_time = data.get("startTime")
        end_time = data.get("endTime")
        # notes = data.get("notes", "")
        
        if not all([subject, day, start_time, end_time]):
            return jsonify({"error": "Missing required fields"}), 400
        
        conn = get_conn()
        cursor = conn.cursor()
        
        cursor.execute(
            """
            INSERT INTO timetable_entries (user_id, subject, day_of_week, start_time, end_time, notes)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (user_id, subject, day, start_time, end_time)
        )
        
        conn.commit()
        entry_id = cursor.lastrowid
        cursor.close()
        conn.close()
        
        return jsonify({
            "message": "Timetable entry saved successfully",
            "id": entry_id
        }), 201
        
    except Exception as e:
        logger.error(f"Save timetable error: {e}")
        return jsonify({"error": "Failed to save timetable entry"}), 500

@app.route("/timetable/<int:entry_id>", methods=["DELETE"])
@jwt_required()
def delete_timetable_entry(entry_id):
    """Delete timetable entry"""
    try:
        user_id = get_jwt_identity()
        
        conn = get_conn()
        cursor = conn.cursor()
        
        cursor.execute(
            "DELETE FROM timetable_entries WHERE id = %s AND user_id = %s",
            (entry_id, user_id)
        )
        
        if cursor.rowcount == 0:
            cursor.close()
            conn.close()
            return jsonify({"error": "Timetable entry not found"}), 404
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify({"message": "Timetable entry deleted"}), 200
        
    except Exception as e:
        logger.error(f"Delete timetable error: {e}")
        return jsonify({"error": "Failed to delete timetable entry"}), 500
    

# Add these testing endpoints and improved HuggingFace functions to your backend

import random
import hashlib

# Test endpoint to verify HuggingFace connection
@app.route("/test_huggingface", methods=["POST"])
@jwt_required(optional=True)
def test_huggingface():
    """Test HuggingFace API connection and response quality"""
    try:
        data = request.get_json() or {}
        test_notes = data.get("notes", "Python is a programming language known for its simplicity and readability.")
        
        if not HUGGINGFACE_API_TOKEN:
            return jsonify({
                "error": "HuggingFace token not configured",
                "token_configured": False,
                "instructions": "Add HUGGINGFACE_API_TOKEN to your .env file"
            }), 400
        
        # Test API connection first
        headers = {'Authorization': f'Bearer {HUGGINGFACE_API_TOKEN}'}
        test_url = "https://api-inference.huggingface.co/models/microsoft/DialoGPT-medium"
        
        # Simple test request
        test_payload = {
            "inputs": "Hello, how are you?",
            "parameters": {"max_new_tokens": 10}
        }
        
        response = requests.post(test_url, headers=headers, json=test_payload, timeout=30)
        
        return jsonify({
            "api_status": response.status_code,
            "api_response": response.json() if response.status_code == 200 else response.text,
            "token_configured": True,
            "test_generation": generate_test_flashcard(test_notes)
        }), 200
        
    except Exception as e:
        logger.error(f"HuggingFace test error: {e}")
        return jsonify({
            "error": str(e),
            "token_configured": bool(HUGGINGFACE_API_TOKEN)
        }), 500

def generate_test_flashcard(notes):
    """Test flashcard generation with detailed logging"""
    try:
        result = generate_improved_flashcard(notes, "programming", "medium")
        return {
            "success": result is not None,
            "flashcard": result,
            "notes_hash": hashlib.md5(notes.encode()).hexdigest()[:8]
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

def generate_improved_flashcard(notes, subject, difficulty='medium'):
    """Improved flashcard generation with better uniqueness"""
    if not HUGGINGFACE_API_TOKEN:
        logger.warning("HuggingFace token not configured")
        return None
    
    try:
        # Create more varied prompts based on content analysis
        note_words = notes.lower().split()
        key_terms = [word for word in note_words if len(word) > 4 and word.isalpha()]
        
        # Generate a seed for randomness
        content_seed = abs(hash(notes + subject + difficulty)) % 1000
        random.seed(content_seed)
        
        # Multiple prompt strategies for variety
        prompt_strategies = {
            'definition': f"Based on these {subject} notes, create a definition question:\n{notes[:500]}\n\nQ:",
            'application': f"Create a practical application question about {subject} from these notes:\n{notes[:500]}\n\nQ:",
            'comparison': f"Create a comparison or analysis question about {subject} from these notes:\n{notes[:500]}\n\nQ:",
            'example': f"Create a question asking for an example or case study about {subject} from these notes:\n{notes[:500]}\n\nQ:",
            'explanation': f"Create an explanation question about {subject} concepts from these notes:\n{notes[:500]}\n\nQ:"
        }
        
        # Choose strategy based on difficulty and randomness
        if difficulty == 'easy':
            strategies = ['definition', 'example']
        elif difficulty == 'medium':
            strategies = ['application', 'explanation']
        else:  # hard
            strategies = ['comparison', 'analysis']
        
        chosen_strategy = random.choice(strategies) if strategies else 'explanation'
        prompt = prompt_strategies.get(chosen_strategy, prompt_strategies['explanation'])
        
        headers = {
            'Authorization': f'Bearer {HUGGINGFACE_API_TOKEN}',
            'Content-Type': 'application/json'
        }
        
        # Try different models for variety
        models = [
            "microsoft/DialoGPT-medium",
            "facebook/blenderbot-400M-distill",
            "microsoft/DialoGPT-small"
        ]
        
        model = random.choice(models)
        api_url = f"https://api-inference.huggingface.co/models/{model}"
        
        payload = {
            "inputs": prompt,
            "parameters": {
                "max_new_tokens": 150,
                "temperature": 0.8 + (random.random() * 0.4),  # 0.8-1.2 for variety
                "top_p": 0.9,
                "do_sample": True,
                "repetition_penalty": 1.2
            },
            "options": {
                "wait_for_model": True,
                "use_cache": False  # Important for uniqueness!
            }
        }
        
        logger.info(f"Trying model: {model} with strategy: {chosen_strategy}")
        
        response = requests.post(api_url, headers=headers, json=payload, timeout=45)
        
        if response.status_code == 200:
            result = response.json()
            logger.info(f"HuggingFace raw response: {result}")
            
            if isinstance(result, list) and len(result) > 0:
                generated_text = result[0].get('generated_text', '')
                if generated_text:
                    parsed = parse_improved_flashcard(generated_text, prompt, subject, difficulty, chosen_strategy)
                    if parsed:
                        logger.info(f"Successfully generated with {chosen_strategy} strategy")
                        return parsed
        
        elif response.status_code == 503:
            logger.warning("Model loading, trying fallback...")
            return generate_deterministic_fallback(notes, subject, difficulty, content_seed)
        
        else:
            logger.error(f"API Error {response.status_code}: {response.text}")
            return generate_deterministic_fallback(notes, subject, difficulty, content_seed)
        
        return None
        
    except Exception as e:
        logger.error(f"Improved generation error: {e}")
        return generate_deterministic_fallback(notes, subject, difficulty, content_seed)

def parse_improved_flashcard(generated_text, original_prompt, subject, difficulty, strategy):
    """Enhanced parsing with strategy-aware logic"""
    try:
        # Remove the original prompt
        clean_text = generated_text.replace(original_prompt, '').strip()
        
        # Strategy-specific parsing
        if strategy == 'definition':
            question_starters = ["What is", "Define", "Explain what"]
        elif strategy == 'application':
            question_starters = ["How would you", "In what way", "How can"]
        elif strategy == 'comparison':
            question_starters = ["How does", "What's the difference", "Compare"]
        else:
            question_starters = ["What", "How", "Why", "Explain"]
        
        # Multiple parsing attempts
        question, answer = None, None
        
        # Method 1: Look for Q: A: pattern
        if "Q:" in clean_text and "A:" in clean_text:
            parts = clean_text.split("A:")
            question = parts[0].replace("Q:", "").strip()
            answer = parts[1].strip()
        
        # Method 2: Look for ? delimiter
        elif "?" in clean_text:
            parts = clean_text.split("?", 1)
            question = parts[0].strip() + "?"
            answer = parts[1].strip() if len(parts) > 1 else f"Please refer to your {subject} notes for details."
        
        # Method 3: Split by newlines
        elif "\n" in clean_text:
            lines = [line.strip() for line in clean_text.split('\n') if line.strip()]
            if len(lines) >= 2:
                question = lines[0]
                answer = " ".join(lines[1:])
        
        # Method 4: Generate question from text
        if not question:
            starter = random.choice(question_starters)
            question = f"{starter} {clean_text[:50]}?"
            answer = clean_text
        
        # Clean and validate
        if question and answer:
            question = question[:300].strip()
            answer = answer[:800].strip()
            
            # Add variety suffix based on difficulty
            difficulty_suffixes = {
                'easy': '',
                'medium': ' Provide specific examples.',
                'hard': ' Include analysis of implications and potential limitations.'
            }
            
            if answer and not answer.endswith('.'):
                answer += '.'
            answer += difficulty_suffixes.get(difficulty, '')
            
            return {
                'question': question,
                'answer': answer,
                'subject': subject,
                'difficulty': difficulty,
                'strategy_used': strategy,
                'generated_by': 'huggingface'
            }
        
        return None
        
    except Exception as e:
        logger.error(f"Parsing error: {e}")
        return None

def generate_deterministic_fallback(notes, subject, difficulty, seed):
    """Generate unique fallback questions using deterministic randomness"""
    try:
        random.seed(seed)
        
        # Extract meaningful content
        sentences = [s.strip() for s in notes.replace('!', '.').replace('?', '.').split('.') if len(s.strip()) > 10]
        words = notes.lower().split()
        key_terms = [word for word in words if len(word) > 4 and word.isalpha()]
        
        # Question templates by difficulty
        templates = {
            'easy': [
                f"What is the main concept about {subject} in these notes?",
                f"Define the key term related to {subject} mentioned in the notes.",
                f"List the main points discussed about {subject}."
            ],
            'medium': [
                f"How do the {subject} concepts in these notes relate to practical applications?",
                f"Explain the significance of {random.choice(key_terms) if key_terms else 'the main concept'} in {subject}.",
                f"What are the implications of these {subject} concepts?",
                f"How would you apply these {subject} principles in a real scenario?"
            ],
            'hard': [
                f"Analyze the underlying assumptions in these {subject} concepts.",
                f"What are the potential limitations or criticisms of these {subject} ideas?",
                f"How might these {subject} concepts evolve or be challenged in the future?",
                f"Compare and contrast the different approaches mentioned in these {subject} notes."
            ]
        }
        
        question_list = templates.get(difficulty, templates['medium'])
        question = random.choice(question_list)
        
        # Create contextual answer
        if sentences:
            selected_sentence = random.choice(sentences)
            answer = f"Based on the provided notes: {selected_sentence}"
            if len(sentences) > 1:
                answer += f" Additionally, {random.choice([s for s in sentences if s != selected_sentence])}"
        else:
            answer = f"Key concepts from your {subject} notes: {notes[:150]}..."
        
        return {
            'question': question,
            'answer': answer,
            'subject': subject,
            'difficulty': difficulty,
            'strategy_used': 'deterministic_fallback',
            'generated_by': 'fallback',
            'seed_used': seed
        }
        
    except Exception as e:
        logger.error(f"Fallback generation error: {e}")
        return None

# Enhanced debugging endpoint
@app.route("/debug_generation", methods=["POST"])
@jwt_required(optional=True)
def debug_generation():
    """Detailed debugging of flashcard generation"""
    try:
        data = request.get_json() or {}
        notes = data.get("notes", "")
        subject = data.get("subject", "general")
        difficulty = data.get("difficulty", "medium")
        
        debug_info = {
            "input": {
                "notes_length": len(notes),
                "subject": subject,
                "difficulty": difficulty,
                "notes_preview": notes[:100]
            },
            "config": {
                "token_configured": bool(HUGGINGFACE_API_TOKEN),
                "token_preview": HUGGINGFACE_API_TOKEN[:10] + "..." if HUGGINGFACE_API_TOKEN else None
            }
        }
        
        # Test multiple generation attempts
        attempts = []
        for i in range(3):
            try:
                result = generate_improved_flashcard(notes, subject, difficulty)
                attempts.append({
                    "attempt": i + 1,
                    "success": result is not None,
                    "result": result
                })
            except Exception as e:
                attempts.append({
                    "attempt": i + 1,
                    "success": False,
                    "error": str(e)
                })
        
        debug_info["generation_attempts"] = attempts
        
        return jsonify(debug_info), 200
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500
# ---------------------------
# Main execution
# ---------------------------
if __name__ == "__main__":
    logger.info("Starting AI Study Buddy Flask application...")
    logger.info(f"Database: {DB_NAME} on {DB_HOST}")
    logger.info(f"IntaSend configured: {'Yes' if inta_client else 'No'}")
    logger.info(f"HuggingFace AI: {'Configured' if HUGGINGFACE_API_TOKEN else 'Not configured'}")
    logger.info(f"IntaSend: {'Configured' if INTASEND_SECRET else 'Not configured'}")
    
    
    # Run the application
    app.run(
        host="127.0.0.1", 
        port=5000, 
        debug=True,
        threaded=True
    )

