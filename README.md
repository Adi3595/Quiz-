# Quiz Application

A web-based quiz application built with Flask, featuring AI-generated questions, user authentication, and quiz history tracking.

## Features

- **User Authentication**: Register and login functionality
- **AI-Powered Quiz Generation**: Uses Groq API to generate questions on various topics
- **Subtopic Selection**: Choose specific subtopics for customized quizzes
- **Quiz Evaluation**: Automatic scoring with detailed explanations
- **History Tracking**: View past quiz attempts and scores
- **Responsive UI**: HTML-based frontend with multiple pages
- **Database Integration**: MongoDB for user data and quiz history

## Technologies Used

- **Backend**: Python Flask
- **Database**: MongoDB
- **AI API**: Groq (Llama model)
- **Frontend**: HTML, CSS, JavaScript
- **Additional**: C++ evaluator (evaluator.cpp), JSON handling (json.hpp)

## Installation

1. Clone the repository:
   ```
   git clone <repository-url>
   cd final-oop
   ```

2. Install Python dependencies:
   ```
   pip install -r requirements.txt
   ```

3. Set up environment variables:
   Create a `.env` file in the root directory with:
   ```
   MONGO_URI=your_mongodb_connection_string
   GROQ_API_KEY=your_groq_api_key
   ```

4. Ensure MongoDB is running and accessible.

## Running the Application

1. Start the Flask server:
   ```
   python app.py
   ```

2. Open your browser and navigate to `http://localhost:5000`

## Usage

1. **Register/Login**: Create an account or log in
2. **Select Topic**: Choose a quiz topic
3. **Pick Subtopics**: Select specific subtopics (up to 9 generated)
4. **Take Quiz**: Answer questions within the time limit
5. **View Results**: See score and explanations
6. **Check History**: Review past quiz attempts

## API Endpoints

- `POST /register` - User registration
- `POST /login` - User login
- `POST /get_subtopics` - Generate subtopics for a topic
- `POST /generate_quiz` - Create quiz questions
- `POST /evaluate_quiz` - Evaluate quiz answers
- `GET /get_history` - Retrieve user's quiz history
- `POST /clear_history` - Clear user's history
- `POST /delete_quiz` - Delete specific quiz
- `POST /cleanup_unevaluated` - Remove unevaluated quizzes

## Project Structure

- `app.py` - Main Flask application with OOP classes
- `evaluator.cpp` - C++ evaluation logic
- `json.hpp` - JSON handling header
- `*.html` - Frontend pages (index, quiz, history, etc.)
- `data/` - Sample data files
- `requirements.txt` - Python dependencies

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## License

This project is open-source. Please check the license file for details.
