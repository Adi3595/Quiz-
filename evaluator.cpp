#include <iostream>
#include <vector>
#include <memory>
#include <stdexcept>
#include "json.hpp"

using json = nlohmann::json;
using namespace std;

// Abstract base class for evaluation strategies
class EvaluationStrategy {
public:
    virtual ~EvaluationStrategy() = default;
    virtual int evaluate(const vector<string>& userAnswers, const vector<string>& correctAnswers) = 0;
};

// Concrete strategy for exact match evaluation
class ExactMatchEvaluator : public EvaluationStrategy {
public:
    int evaluate(const vector<string>& userAnswers, const vector<string>& correctAnswers) override {
        int score = 0;
        size_t minSize = min(userAnswers.size(), correctAnswers.size());
        
        for (size_t i = 0; i < minSize; ++i) {
            if (normalizeAnswer(userAnswers[i]) == normalizeAnswer(correctAnswers[i])) {
                score++;
            }
        }
        return score;
    }

private:
    string normalizeAnswer(const string& answer) {
        string normalized = answer;
        // Convert to uppercase for case-insensitive comparison
        for (char& c : normalized) {
            c = toupper(c);
        }
        // Remove any whitespace
        normalized.erase(remove_if(normalized.begin(), normalized.end(), ::isspace), normalized.end());
        return normalized;
    }
};

// Context class that uses the evaluation strategy
class QuizEvaluationContext {
private:
    unique_ptr<EvaluationStrategy> strategy_;
    
public:
    // Constructor with dependency injection
    explicit QuizEvaluationContext(unique_ptr<EvaluationStrategy> strategy) 
        : strategy_(move(strategy)) {}
    
    // Default constructor uses ExactMatchEvaluator
    QuizEvaluationContext() 
        : strategy_(make_unique<ExactMatchEvaluator>()) {}
    
    // Set strategy at runtime
    void setStrategy(unique_ptr<EvaluationStrategy> strategy) {
        strategy_ = move(strategy);
    }
    
    int calculateScore(const vector<string>& userAnswers, const vector<string>& correctAnswers) {
        if (!strategy_) {
            throw runtime_error("Evaluation strategy not set");
        }
        return strategy_->evaluate(userAnswers, correctAnswers);
    }
};

// Factory class for creating evaluators
class EvaluatorFactory {
public:
    static unique_ptr<EvaluationStrategy> createExactMatchEvaluator() {
        return make_unique<ExactMatchEvaluator>();
    }
};

// Main QuizEvaluator class (facade pattern)
class QuizEvaluator {
private:
    QuizEvaluationContext context_;
    
public:
    QuizEvaluator() : context_(EvaluatorFactory::createExactMatchEvaluator()) {}
    
    // Constructor with custom strategy
    explicit QuizEvaluator(unique_ptr<EvaluationStrategy> strategy) 
        : context_(move(strategy)) {}
    
    int calculateScore(const vector<string>& userAnswers, const vector<string>& correctAnswers) {
        return context_.calculateScore(userAnswers, correctAnswers);
    }
    
    // Utility method to parse JSON arrays
    static vector<string> parseJsonArray(const string& jsonStr) {
        try {
            json j = json::parse(jsonStr);
            return j.get<vector<string>>();
        } catch (const exception& e) {
            cerr << "Error parsing JSON: " << e.what() << endl;
            return {};
        }
    }
};

// Command line argument handler
class ArgumentParser {
private:
    vector<string> args_;
    
public:
    ArgumentParser(int argc, char* argv[]) {
        for (int i = 0; i < argc; ++i) {
            args_.emplace_back(argv[i]);
        }
    }
    
    bool validateArguments() const {
        return args_.size() >= 3;
    }
    
    string getUserAnswersJson() const {
        return args_.size() > 1 ? args_[1] : "[]";
    }
    
    string getCorrectAnswersJson() const {
        return args_.size() > 2 ? args_[2] : "[]";
    }
    
    void showUsage() const {
        cout << "Usage: " << args_[0] << " <user_answers_json> <correct_answers_json>" << endl;
        cout << "Example: " << args_[0] << " '[\"A\",\"B\",\"C\"]' '[\"A\",\"B\",\"D\"]'" << endl;
    }
};

int main(int argc, char* argv[]) {
    try {
        // Parse command line arguments
        ArgumentParser parser(argc, argv);
        
        if (!parser.validateArguments()) {
            parser.showUsage();
            return 1;
        }
        
        // Parse JSON inputs
        vector<string> userAnswers = QuizEvaluator::parseJsonArray(parser.getUserAnswersJson());
        vector<string> correctAnswers = QuizEvaluator::parseJsonArray(parser.getCorrectAnswersJson());
        
        // Create evaluator and calculate score
        QuizEvaluator evaluator;
        int score = evaluator.calculateScore(userAnswers, correctAnswers);
        
        // Output result
        cout << score;
        
    } catch (const exception& e) {
        cerr << "Error: " << e.what() << endl;
        return 1;
    }
    
    return 0;
}