from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from groq import Groq
from pymongo import MongoClient
import os, json
from dotenv import load_dotenv
from datetime import datetime
from typing import List, Dict, Any, Optional
from bson import ObjectId
import re

# ---------------- OOP CLASSES ----------------
class DatabaseManager:
    """Manages MongoDB database operations"""
    
    def __init__(self, connection_string: str, database_name: str):
        self.client = MongoClient(connection_string)
        self.db = self.client[database_name]
        self.users_col = self.db["users"]
        self.history_col = self.db["history"]
        self._test_connection()
        self._create_indexes()
    
    def _test_connection(self):
        """Test MongoDB connection"""
        try:
            self.client.admin.command('ping')
            print("MongoDB connected successfully.")
        except Exception as e:
            print("MongoDB connection error:", e)
            raise
    
    def _create_indexes(self):
        """Create indexes to prevent duplicates"""
        try:
            # Create unique compound index to prevent duplicates
            self.history_col.create_index(
                [("username", 1), ("timestamp", 1), ("topic", 1)], 
                unique=True, 
                name="unique_quiz_attempt"
            )
            print("Database indexes created successfully.")
        except Exception as e:
            print("Note: Index might already exist:", e)
    
    def find_user(self, username: str, password: str = None) -> Optional[Dict]:
        """Find user by username and optionally password"""
        query = {"username": username}
        if password:
            query["password"] = password
        return self.users_col.find_one(query)
    
    def insert_user(self, username: str, password: str) -> bool:
        """Insert new user"""
        try:
            self.users_col.insert_one({"username": username, "password": password})
            return True
        except Exception as e:
            print("Error inserting user:", e)
            return False
    
    def insert_quiz_history(self, quiz_data: Dict) -> bool:
        """Insert quiz history record - ONLY FOR EVALUATED QUIZZES"""
        try:
            # Only save if it's an evaluated quiz (has a score and answers)
            if quiz_data.get("score") is None and not quiz_data.get("answers"):
                print("🔄 Skipping quiz generation record (no score/answers)")
                return False
                
            # Use update with upsert to prevent duplicates
            result = self.history_col.update_one(
                {
                    "username": quiz_data["username"],
                    "timestamp": quiz_data["timestamp"],
                    "topic": quiz_data["topic"]
                },
                {"$set": quiz_data},
                upsert=True
            )
            
            if result.upserted_id:
                print(f"✅ Saved evaluated quiz for {quiz_data['username']} - Score: {quiz_data.get('score')}/{quiz_data.get('total')}")
                return True
            elif result.modified_count > 0:
                print(f"🔄 Updated quiz record for {quiz_data['username']}")
                return True
            else:
                print(f"ℹ️  No changes made for {quiz_data['username']}")
                return True
                
        except Exception as e:
            print("❌ Error inserting quiz history:", e)
            return False
    
    def get_user_history(self, username: str) -> List[Dict]:
        """Get user's quiz history - ONLY EVALUATED QUIZZES"""
        try:
            print(f"📖 Fetching history for user: {username}")
            
            # ONLY get evaluated quizzes (have scores and answers)
            records = list(self.history_col.find(
                {
                    "username": username,
                    "score": {"$ne": None},  # Score is not null
                    "answers": {"$exists": True, "$ne": []}  # Answers exist and not empty
                }, 
                {"_id": 0}
            ).sort("timestamp", -1))
            
            print(f"✅ Found {len(records)} evaluated quiz records for {username}")
            
            if not records:
                return []
            
            # Manual deduplication
            unique_records = []
            seen_combinations = set()
            
            for record in records:
                # Create a unique key
                combo_key = f"{record.get('timestamp', '')}_{record.get('topic', '')}"
                
                if combo_key not in seen_combinations:
                    seen_combinations.add(combo_key)
                    unique_records.append(record)
                else:
                    print(f"🔄 Filtered out duplicate: {combo_key}")
            
            print(f"🎯 After deduplication: {len(unique_records)} unique evaluated quizzes")
            
            return unique_records
            
        except Exception as e:
            print("❌ Error in get_user_history:", e)
            return []
    
    def clear_user_history(self, username: str) -> int:
        """Clear all history for a user"""
        try:
            result = self.history_col.delete_many({"username": username})
            print(f"🗑️ Cleared {result.deleted_count} records for {username}")
            return result.deleted_count
        except Exception as e:
            print("Error clearing history:", e)
            return 0
    
    def delete_quiz(self, username: str, timestamp: str) -> int:
        """Delete a specific quiz by timestamp"""
        try:
            result = self.history_col.delete_one({
                "username": username,
                "timestamp": timestamp
            })
            print(f"🗑️ Deleted {result.deleted_count} quiz for {username} at {timestamp}")
            return result.deleted_count
        except Exception as e:
            print("Error deleting quiz:", e)
            return 0
    
    def cleanup_unevaluated_quizzes(self, username: str) -> int:
        """Remove unevaluated quiz records (without scores/answers)"""
        try:
            result = self.history_col.delete_many({
                "username": username,
                "$or": [
                    {"score": None},
                    {"answers": {"$exists": False}},
                    {"answers": []}
                ]
            })
            print(f"🧹 Cleaned up {result.deleted_count} unevaluated quizzes for {username}")
            return result.deleted_count
        except Exception as e:
            print("Error cleaning up unevaluated quizzes:", e)
            return 0


class QuizGenerator:
    """Handles quiz generation using Groq API"""
    
    def __init__(self, api_key: str):
        self.client = Groq(api_key=api_key)
    
    def is_coding_topic(self, topic: str, subtopic: str) -> bool:
        """Check if the topic/subtopic is programming-related"""
        coding_keywords = [
            "python", "java", "c++", "c#", "javascript", "typescript", "programming", 
            "coding", "algorithm", "data structure", "function", "class", "object", 
            "variable", "loop", "array", "string", "debug", "code", "program",
            "software", "development", "html", "css", "sql", "database", "api",
            "react", "node", "vue", "angular", "django", "flask", "express",
            "oop", "object oriented", "inheritance", "polymorphism", "encapsulation",
            "abstraction", "constructor", "method", "attribute", "interface"
        ]
        combined_text = f"{topic} {subtopic}".lower()
        return any(keyword in combined_text for keyword in coding_keywords)
    
    def generate_subtopics(self, topic: str) -> List[str]:
        """Generate exactly 9 subtopics for a given topic"""
        prompt = f"""
Generate exactly 9 diverse and distinct subtopics related to '{topic}'.
- Return exactly 9 subtopics, no more no less
- Make them comprehensive and cover different aspects
- Format as simple comma-separated values
- No numbering, no bullet points, just plain text
Example: "Subtopic1, Subtopic2, Subtopic3, ..."
"""
        
        try:
            chat = self.client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model="llama-3.3-70b-versatile",
                temperature=0.8
            )
            response_text = chat.choices[0].message.content.strip()
            
            # Parse comma-separated subtopics
            subtopics = [subtopic.strip() for subtopic in response_text.split(",")]
            subtopics = [s for s in subtopics if s and len(s) > 2]
            
            # Ensure we have exactly 9
            if len(subtopics) > 9:
                subtopics = subtopics[:9]
            elif len(subtopics) < 9:
                remaining = 9 - len(subtopics)
                additional_prompt = f"Generate exactly {remaining} more distinct subtopics about {topic} to complete a set of 9. Comma-separated:"
                additional_chat = self.client.chat.completions.create(
                    messages=[{"role": "user", "content": additional_prompt}],
                    model="llama-3.3-70b-versatile"
                )
                additional_text = additional_chat.choices[0].message.content.strip()
                additional_subtopics = [s.strip() for s in additional_text.split(",") if s.strip()]
                subtopics.extend(additional_subtopics[:remaining])
            
            print(f"✅ Generated {len(subtopics)} subtopics for '{topic}'")
            return subtopics[:9]
            
        except Exception as e:
            print("Error generating subtopics:", e)
            fallback_subtopics = [
                "Fundamentals", "Key Concepts", "Advanced Topics", 
                "Historical Context", "Important Figures", "Major Events",
                "Theoretical Framework", "Practical Applications", "Current Developments"
            ]
            return fallback_subtopics[:9]
    
    def _extract_json_from_response(self, response_text: str) -> List[Dict]:
        """Extract JSON from AI response, handling various formats"""
        try:
            # First try direct JSON parsing
            return json.loads(response_text)
        except json.JSONDecodeError:
            # Try to extract JSON from text
            json_match = re.search(r'\[.*\]', response_text, re.DOTALL)
            if json_match:
                try:
                    return json.loads(json_match.group())
                except json.JSONDecodeError:
                    pass
            
            # If no JSON found, create fallback questions
            print("⚠️ Could not parse JSON, creating fallback questions")
            return self._create_fallback_questions()
    
    def _create_fallback_questions(self) -> List[Dict]:
        """Create fallback questions when API fails"""
        return [
            {
                "question": "This is a sample question. The API response could not be parsed.",
                "options": ["A) Option A", "B) Option B", "C) Option C", "D) Option D"],
                "answer": "A",
                "explanation": "This is a fallback question due to API issues."
            }
        ]
    
    def generate_quiz(self, topic: str, subtopics: List[str], num_questions: int, username: str) -> Dict:
        """Generate quiz questions for selected subtopics - DON'T SAVE TO HISTORY"""
        if not subtopics:
            return {"quiz": [], "error": "No subtopics selected"}
        
        print(f"🎯 Requested {num_questions} questions for {len(subtopics)} subtopics: {subtopics}")
        
        # FIXED: Generate ALL questions from the FIRST subtopic only
        # This ensures we get exactly the requested number of questions
        all_questions = []
        
        # Use only the first subtopic to generate all questions
        # This prevents multiplication of questions across multiple subtopics
        first_subtopic = subtopics[0]
        print(f"🔍 Generating ALL {num_questions} questions from first subtopic: {first_subtopic}")
        
        # Generate all questions from the first subtopic
        questions = self._generate_subtopic_quiz(topic, first_subtopic, num_questions)
        
        # Ensure we don't exceed the requested number
        if len(questions) > num_questions:
            questions = questions[:num_questions]
        
        all_questions.extend(questions)
        
        print(f"✅ Generated exactly {len(all_questions)} questions (requested: {num_questions})")
        
        return {"quiz": all_questions}
    
    def _generate_subtopic_quiz(self, topic: str, subtopic: str, num_questions: int) -> List[Dict]:
        """Generate questions for a single subtopic"""
        is_coding = self.is_coding_topic(topic, subtopic)
        
        print(f"🔍 Topic: {topic}, Subtopic: {subtopic}, Is Coding: {is_coding}")
        
        if is_coding:
            # FORCE CODE SNIPPETS FOR PROGRAMMING TOPICS
            prompt = f"""
IMPORTANT: You are generating programming questions about '{subtopic}' in '{topic}'. 
You MUST include ACTUAL CODE SNIPPETS in EVERY question.

CRITICAL REQUIREMENTS:
1. EVERY question MUST contain a REAL CODE SNIPPET with proper syntax highlighting
2. Use triple backticks with language tags: ```cpp, ```python, ```java, etc.
3. Code must be 5-15 lines, well-indented, and demonstrate programming concepts
4. For C++ topics:  proper headers required for code to run like <iostream>, <vector>, etc for respective langauge codes and 'using namespace std;' for C++ 
5. NO THEORY-ONLY QUESTIONS - every question must test code understanding

QUESTION FORMATS (MUST INCLUDE CODE):
- "What does this code output?"
- "What's wrong with this code?"
- "What completes this code?"
- "Which code demonstrates [concept]?"

EXAMPLES OF REQUIRED FORMAT:

C++ OOP Example:
{{
  "question": "What does this C++ OOP code output?\\n```cpp\\n#include <iostream>\\nusing namespace std;\\n\\nclass Animal {{\\npublic:\\n    virtual void sound() {{ cout << \\"Animal sound\\" << endl; }}\\n}};\\n\\nclass Dog : public Animal {{\\npublic:\\n    void sound() override {{ cout << \\"Bark\\" << endl; }}\\n}};\\n\\nint main() {{\\n    Animal* animal = new Dog();\\n    animal->sound();\\n    return 0;\\n}}\\n```",
  "options": ["A) Animal sound", "B) Bark", "C) Compilation error", "D) Runtime error"],
  "answer": "B",
  "explanation": "Polymorphism - Dog's sound() is called due to virtual function"
}}

Java OOP Example:
{{
  "question": "What's the issue with this Java inheritance code?\\n```java\\nclass Vehicle {{\\n    private int speed;\\n    public Vehicle(int s) {{ speed = s; }}\\n}}\\n\\nclass Car extends Vehicle {{\\n    public Car() {{ }}\\n}}\\n```",
  "options": ["A) Missing constructor in Car", "B) Private field access", "C) No main method", "D) Speed should be protected"],
  "answer": "A",
  "explanation": "Car constructor doesn't call super() and Vehicle has no default constructor"
}}

Return EXACTLY {num_questions} questions in this JSON format. EVERY question must have code snippets.
"""
        else:
            # Regular prompt for non-programming topics
            prompt = f"""
Create exactly {num_questions} multiple-choice questions about '{subtopic}' in '{topic}'.

Return ONLY a valid JSON array with this exact structure:
[
  {{
    "question": "Question text here?",
    "options": ["A) First option", "B) Second option", "C) Third option", "D) Fourth option"],
    "answer": "A",
    "explanation": "Brief explanation here"
  }}
]

Requirements:
- {num_questions} questions total
- Each question has exactly 4 options (A, B, C, D)
- Clear correct answer (A/B/C/D)
- Short explanation
- Return ONLY the JSON, no other text
"""
        
        try:
            print(f"🔍 Generating {num_questions} questions for: {subtopic} (coding: {is_coding})")
            
            chat = self.client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model="llama-3.3-70b-versatile",
                temperature=0.7,
                max_tokens=4000
            )
            
            response_text = chat.choices[0].message.content.strip()
            print(f"📄 Raw response preview: {response_text[:300]}...")
            
            questions = self._extract_json_from_response(response_text)
            
            # Validate questions structure
            validated_questions = []
            for q in questions:
                if isinstance(q, dict) and 'question' in q and 'options' in q:
                    # Ensure options is a list with exactly 4 items
                    if not isinstance(q['options'], list):
                        q['options'] = ["A) Option A", "B) Option B", "C) Option C", "D) Option D"]
                    elif len(q['options']) != 4:
                        # Pad or truncate options to exactly 4
                        while len(q['options']) < 4:
                            q['options'].append(f"{chr(68 - (4 - len(q['options'])))} Option")
                        q['options'] = q['options'][:4]
                    
                    # Ensure answer is A/B/C/D
                    if 'answer' not in q or q['answer'] not in ['A', 'B', 'C', 'D']:
                        q['answer'] = 'A'
                    
                    validated_questions.append(q)
            
            print(f"✅ Generated {len(validated_questions)} valid questions for {subtopic}")
            
            # FORCE CODING: If it's a coding topic but no code snippets found, add them
            if is_coding and validated_questions:
                has_code_snippets = any('```' in q.get('question', '') for q in validated_questions)
                if not has_code_snippets:
                    print("⚠️ No code snippets detected in programming questions, forcing code generation...")
                    # Regenerate with stricter prompt
                    return self._generate_subtopic_quiz(topic, subtopic, num_questions)
            
            return validated_questions[:num_questions]  # Ensure we don't exceed requested number
            
        except Exception as e:
            print(f"❌ Error generating quiz for {subtopic}: {e}")
            # Return fallback questions instead of empty list
            return self._create_fallback_questions()


class QuizEvaluator:
    """Handles quiz evaluation and explanation generation"""
    
    def __init__(self, groq_client):
        self.client = groq_client
    
    def evaluate_quiz(self, username: str, topic: str, subtopics: List[str], 
                     user_answers: List[str], questions: List[Dict]) -> Dict:
        """Evaluate user's quiz answers"""
        if not questions:
            return {"score": 0, "total": 0, "explanations": []}
        
        score = 0
        explanations = []
        
        for i, question in enumerate(questions):
            correct_answer = question.get("answer", "").strip().upper()
            given_answer = str(user_answers[i]).strip().upper() if i < len(user_answers) else ""
            
            if given_answer == correct_answer:
                score += 1
                # Use existing explanation for correct answers
                existing_explanation = question.get("explanation", "No explanation provided.")
                explanations.append(f"✅ Correct! {existing_explanation}")
            else:
                # Generate focused explanation for wrong answers
                explanation = self._generate_strict_explanation(question, correct_answer, given_answer)
                explanations.append(f"❌ Your answer: {given_answer}. Correct: {correct_answer}. {explanation}")
        
        # Prepare history record - ONLY THIS GETS SAVED
        history_data = {
            "username": username,
            "topic": topic,
            "subtopics": subtopics,
            "score": score,
            "total": len(questions),
            "answers": user_answers,
            "questions": questions,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        return {
            "score": score,
            "total": len(questions),
            "explanations": explanations,
            "history_data": history_data
        }
    
    def _generate_strict_explanation(self, question: Dict, correct_answer: str, given_answer: str) -> str:
        """Generate strict explanation focusing on why the given answer is wrong and correct answer is right"""
        try:
            prompt = f"""
For this programming question:
Question: {question.get('question', '')}

Options:
{chr(10).join(question.get('options', []))}

The correct answer is: {correct_answer}
The user selected: {given_answer}

Generate a STRICT explanation that:
1. Briefly explains why {correct_answer} is correct (max 2 sentences)
2. Briefly explains why {given_answer} is wrong (max 2 sentences)
3. Focus ONLY on the technical reasoning from the code/question
4. Do NOT introduce new concepts or alternatives
5. Do NOT suggest answers not in the options
6. Keep it under 100 words
7. Base explanation ONLY on the provided code and options

Explanation:
"""
            chat = self.client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model="llama-3.3-70b-versatile",
                max_tokens=150,
                temperature=0.3
            )
            explanation = chat.choices[0].message.content.strip()
            
            # Validate explanation doesn't contain invalid content
            if self._is_valid_explanation(explanation, question.get('options', [])):
                return explanation
            else:
                return question.get("explanation", "The selected answer is incorrect. Review the code logic carefully.")
                
        except Exception as e:
            print(f"Error generating explanation: {e}")
            return question.get("explanation", "The selected answer is incorrect. Review the code logic carefully.")
    
    def _is_valid_explanation(self, explanation: str, options: List[str]) -> bool:
        """Validate that explanation doesn't suggest answers outside the given options"""
        # Check if explanation suggests answers not in options
        option_letters = ['A', 'B', 'C', 'D']
        for letter in option_letters:
            if f" {letter}) " in explanation and f" {letter}) " not in ' '.join(options):
                return False
        return True


# ---------------- FLASK APP SETUP ----------------
load_dotenv()
app = Flask(__name__, static_folder=".", static_url_path="")
CORS(app)

# Initialize components using OOP
try:
    db_manager = DatabaseManager(
        connection_string=os.getenv("MONGO_URI"),
        database_name="quiz"
    )
    quiz_generator = QuizGenerator(api_key=os.getenv("GROQ_API_KEY"))
    quiz_evaluator = QuizEvaluator(groq_client=Groq(api_key=os.getenv("GROQ_API_KEY")))
    print("✅ All components initialized successfully")
except Exception as e:
    print("❌ Initialization error:", e)
    raise

# ---------------- ROUTES ----------------
@app.route("/")
def home():
    try:
        return send_from_directory(".", "index.html")
    except Exception as e:
        print("Error serving index.html:", e)
        return "Index file not found.", 404

# ---------- Authentication ----------
@app.route("/register", methods=["POST"])
def register():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Missing or invalid JSON payload"}), 400

        username = data.get("username")
        password = data.get("password")
        if not username or not password:
            return jsonify({"error": "Username and password are required"}), 400

        if db_manager.find_user(username):
            return jsonify({"message": "User already exists!"}), 400

        if db_manager.insert_user(username, password):
            return jsonify({"message": "Registration successful!"})
        else:
            return jsonify({"error": "Failed to register user"}), 500

    except Exception as e:
        print("Error in /register:", e)
        return jsonify({"error": "Internal server error"}), 500

@app.route("/login", methods=["POST"])
def login():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "Missing or invalid JSON payload"}), 400

        username = data.get("username")
        password = data.get("password")
        if not username or not password:
            return jsonify({"error": "Username and password are required"}), 400

        user = db_manager.find_user(username, password)
        if user:
            return jsonify({"message": "Login successful!"})
        else:
            return jsonify({"message": "Invalid credentials"}), 401

    except Exception as e:
        print("Error in /login:", e)
        return jsonify({"error": "Internal server error"}), 500

# ---------- Subtopics with Selection ----------
@app.route("/get_subtopics", methods=["POST"])
def get_subtopics():
    try:
        data = request.get_json()
        topic = data.get("topic", "")
        
        if not topic:
            return jsonify({"error": "Topic not provided"}), 400

        # Always generate exactly 9 subtopics
        subtopics = quiz_generator.generate_subtopics(topic)
        return jsonify({
            "subtopics": subtopics,
            "count": len(subtopics),
            "message": f"Found {len(subtopics)} subtopics. Select the ones you want to include in your quiz."
        })

    except Exception as e:
        print("Error in /get_subtopics:", e)
        return jsonify({"error": "Failed to generate subtopics"}), 500

# ---------- Quiz Generation with Selected Subtopics ----------
@app.route("/generate_quiz", methods=["POST"])
def generate_quiz():
    try:
        data = request.get_json()
        topic = data.get("topic")
        selected_subtopics = data.get("subtopics", [])
        num = int(data.get("num", 5))
        username = data.get("username", "Guest")

        if not topic or not selected_subtopics:
            return jsonify({"error": "Topic and at least one subtopic are required"}), 400

        print(f"🎯 Generating quiz: {topic}, subtopics: {selected_subtopics}, questions: {num}")

        # Generate quiz using selected subtopics - DON'T SAVE TO HISTORY
        result = quiz_generator.generate_quiz(topic, selected_subtopics, num, username)
        
        return jsonify({"quiz": result["quiz"]})

    except Exception as e:
        print("Error in /generate_quiz:", e)
        return jsonify({"error": f"Failed to generate quiz: {str(e)}"}), 500

# ---------- Quiz Evaluation ----------
@app.route("/evaluate_quiz", methods=["POST"])
def evaluate_quiz():
    try:
        data = request.get_json()
        username = data.get("username")
        topic = data.get("topic")
        subtopics = data.get("subtopics", [])
        user_answers = data.get("answers", [])
        questions = data.get("questions", [])
        time_taken = data.get("time_taken", 0)  # NEW: Total time taken
        time_per_question = data.get("time_per_question", [])  # NEW: Time per question

        if not username or not topic:
            return jsonify({"error": "Missing required fields"}), 400

        # Evaluate quiz
        result = quiz_evaluator.evaluate_quiz(username, topic, subtopics, user_answers, questions)
        
        # Store evaluation results - ONLY THIS GETS SAVED
        if "history_data" in result:
            # Add timing information to history data
            result["history_data"]["time_taken"] = time_taken
            result["history_data"]["time_per_question"] = time_per_question
            result["history_data"]["average_time_per_question"] = round(time_taken / len(questions), 2) if questions else 0
            
            db_manager.insert_quiz_history(result["history_data"])

        return jsonify({
            "score": result["score"],
            "total": result["total"],
            "explanations": result["explanations"],
            "time_taken": time_taken,  # NEW: Return timing info
            "average_time_per_question": round(time_taken / len(questions), 2) if questions else 0
        })

    except Exception as e:
        print("Error in /evaluate_quiz:", e)
        return jsonify({"error": "Failed to evaluate quiz"}), 500

# ---------- History ----------
@app.route("/get_history", methods=["GET"])
def get_history():
    try:
        username = request.args.get("username")
        if not username:
            return jsonify({"success": False, "error": "Username not provided"}), 400

        print(f"📖 API: Fetching EVALUATED history for user: {username}")
        
        records = db_manager.get_user_history(username)
        
        print(f"✅ API: Returning {len(records)} EVALUATED quiz records to frontend")
        
        return jsonify({
            "success": True,
            "history": records,
            "count": len(records)
        })

    except Exception as e:
        print("❌ API Error in /get_history:", e)
        return jsonify({"success": False, "error": f"Failed to fetch history: {str(e)}"}), 500

@app.route("/clear_history", methods=["POST"])
def clear_history():
    try:
        data = request.get_json()
        username = data.get("username")
        
        if not username:
            return jsonify({"success": False, "error": "Username not provided"}), 400

        # Delete all history records for the user
        deleted_count = db_manager.clear_user_history(username)
        
        return jsonify({
            "success": True,
            "message": f"Cleared {deleted_count} history records",
            "deleted_count": deleted_count
        })

    except Exception as e:
        print("Error in /clear_history:", e)
        return jsonify({"success": False, "error": "Failed to clear history"}), 500

@app.route("/delete_quiz", methods=["POST"])
def delete_quiz():
    try:
        data = request.get_json()
        username = data.get("username")
        timestamp = data.get("timestamp")
        
        if not username or not timestamp:
            return jsonify({"success": False, "error": "Username and timestamp are required"}), 400

        # Delete the specific quiz record
        deleted_count = db_manager.delete_quiz(username, timestamp)
        
        if deleted_count > 0:
            return jsonify({
                "success": True,
                "message": "Quiz deleted successfully",
                "deleted_count": deleted_count
            })
        else:
            return jsonify({"success": False, "error": "Quiz not found"}), 404

    except Exception as e:
        print("Error in /delete_quiz:", e)
        return jsonify({"success": False, "error": "Failed to delete quiz"}), 500

# ---------- Cleanup Unevaluated Quizzes ----------
@app.route("/cleanup_unevaluated", methods=["POST"])
def cleanup_unevaluated():
    """Remove all unevaluated quiz records"""
    try:
        data = request.get_json()
        username = data.get("username")
        
        if not username:
            return jsonify({"success": False, "error": "Username not provided"}), 400
        
        deleted_count = db_manager.cleanup_unevaluated_quizzes(username)
        
        return jsonify({
            "success": True,
            "message": f"Removed {deleted_count} unevaluated quiz records",
            "deleted_count": deleted_count
        })
        
    except Exception as e:
        print("Error in cleanup_unevaluated:", e)
        return jsonify({"success": False, "error": str(e)}), 500

# ---------- Serve Static ----------
@app.route("/<path:path>")
def static_proxy(path):
    try:
        return send_from_directory(".", path)
    except Exception as e:
        print("Error serving static file:", e)
        return "File not found.", 404

# ---------- MAIN ----------
if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=5000)