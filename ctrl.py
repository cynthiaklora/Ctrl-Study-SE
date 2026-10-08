# Purpose:
# This file is the Flask entrypoint for the template-based question generator app

# Function:
# - Displays one template input textbox and one question-name textbox
# - Supports Preview, Save, Load, Delete, and New actions
# - Uses parser_engine.generateQuestion to build preview output
# - Persists named question templates in a local JSON file for editing later

from __future__ import annotations

from flask import Flask, render_template, session, request, jsonify                             # Flask imports provide routing, form access, session state, and redirects

from Frontend import QuestionFetch
from Frontend.forms import RadioQuestionForm, SetupQuizForm, QuestionForm, ShortAnswerQuestionForm, LoginForm, RegisterForm

from datetime import timedelta
from flask_session import Session

from flask import redirect, url_for
from flask_login import LoginManager, login_required, login_user, current_user, logout_user, UserMixin

import supabase_client
from supabase_client import ctrlDB
import template_builder

from urllib.parse import urlencode

from Frontend.QuestionFetch import QuestionContainer, makeSeed

import os

import shutil
cache_path = "./flask_session_cache"
try:
    shutil.rmtree(cache_path)
except FileNotFoundError:
    pass

# essential startup component
if os.environ.get("WERKZEUG_RUN_MAIN") != "true":
    print(r"""
    ____ _____ ____  _         ____ _____ _   _ ______   __
   / ___|_   _|  _ \| |       / ___|_   _| | | |  _ \ \ / /
  | |     | | | |_) | |   ____\___ \ | | | | | | | | \ V /
  | |___  | | |  _ <| |__|_____|__) || | | |_| | |_| || |
   \____| |_| |_| \_\_____|   |____/ |_|  \___/|____/ |_|
    """)
# end essential startup component

# app is the Flask application instance
app = Flask(__name__)
app.secret_key = "template-question-builder-secret"

app.config["SESSION_FILE_DIR"] = "./flask_session_cache"

app.config["SESSION_PERMANENT"] = False  # Sessions expire when the browser is closed
app.config["SESSION_TYPE"] = "filesystem"  # Store session data in files
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=6)

Session(app)

login_manager = LoginManager()
login_manager.login_view = "login"
login_manager.init_app(app)

# proper home page
@app.route("/", methods=["GET"])
@app.route("/index", methods=["GET"])
def home():
    userName = getattr(current_user, "username", "")
    return render_template("index.html", title="Ctrl-Study: Home", username=userName)

class User(UserMixin):
    def __init__(self, id, username, role=None):
        self.id = id
        self.username = username
        self.role = role

    def get_id(self):
        return self.id

@login_manager.user_loader
def load_user(user_id):
    result = ctrlDB.table("users").select("id, username, role").eq("id", user_id).execute()
    if not result.data:
        return None
    row = result.data[0]
    return User(id=row["id"], username=row["username"], role=row["role"])

@app.route("/login", methods=["GET", "POST"])
def login():
    form = LoginForm()
    error = None

    if current_user.is_authenticated:
        return redirect(url_for("home"))

    if request.method == "POST" and form.validate_on_submit():
        username = str(form.username.data or "").strip()
        password = str(form.password.data or "")

        account = ctrlDB.table("users").select("id, username, role").eq("username", username).execute()
        
        if not account.data:
            error = "Invalid username."
            return render_template("Login.html", title="Ctrl-Study: Login", form=form, error=error)
        
        supabaseEmail = f"{username}@users.table"

        try:
            user = ctrlDB.auth.sign_in_with_password({
                "email": supabaseEmail,
                "password": password
            }).user
        except Exception:
            user = None

        if user is not None:
            role=account.data[0]["role"]
            login_user(User(id=user.id, username=username, role=role))
            session["userID"] = getattr(current_user, "id", None)
            if (role == "admin"):
                return redirect(url_for("templateIndex"))
            else:
                return redirect(url_for("home"))
        error = "Invalid username or password."

    return render_template("Login.html", title="Ctrl-Study: Login", form=form, error=error)

@app.route("/register", methods=["GET", "POST"])
def register():
    form = RegisterForm()
    error = None

    if request.method == "POST" and form.validate_on_submit():
        username = str(form.username.data or "").strip()
        password = str(form.password.data or "")
        confirmPassword = str(form.confirmPassword.data or "")

        existingUser = ctrlDB.table("users").select("id").eq("username", username).execute()
        if existingUser.data:
                error = "Username already exists."
                return render_template("register.html", title="Register for an Account!", form=form, error=error)

        if password != confirmPassword:
            error = "Passwords do not match."
            return render_template("register.html", title="Register for an Account!", form=form, error=error)

        # Fake email is used because supabase's auth system works on emails, so this is an easy work around to use usernames
        supabaseEmail = f"{username}@users.table"
        try:
            # Makes use of supabases auth system with bcrypt. Password hashes are stored in the auth schema, users table in supabase.
            result = ctrlDB.auth.sign_up({
                "email": supabaseEmail,
                "password": password
            })
            user = result.user
        except Exception:
            user = None
            error = "Registration failed. Please try again."
    
        if user is not None:
            try:
                ctrlDB.table("users").insert({
                    "id": user.id,
                    "username": username
                }).execute()
                return redirect(url_for("login"))
            except:
                error = "Registration failed, please try again."
                return render_template("register.html", title="Register for an Account!", form=form, error=error)
        error = "Invalid registration."

    return render_template("register.html", title="Register for an Account!", form=form, error=error)

@app.route("/logout")
@login_required
def logout():
    logout_user()
    session["userID"] = None
    return redirect(url_for("home"))

@app.route("/account")
def account():
    error = None

    if not session["userID"]:
        return redirect(url_for("home"))

    savedSeeds = ctrlDB.table("quizzes").select("*").eq("user_id", session["userID"]).execute()
    savedSeedsRows = savedSeeds.data
    fullQuizzes = (ctrlDB.table("quizzes").select("*, quiz_questions(*)").eq("user_id", session["userID"]).order("created_at", desc=True).execute())
    allQuizzes = fullQuizzes.data or []
    fullQuizzesRows = [q for q in allQuizzes if q.get("quiz_questions")] # Keeps only quizzes that actually have saved questions

    for q in fullQuizzesRows:
        q["quiz_questions"].sort(key=lambda r: r["position"])

    return render_template("account.html", title="Account", error=error, autoSaved=savedSeedsRows, manualSaved=fullQuizzesRows)
    

@app.route("/template", methods=["GET", "POST"])
@login_required
def templateIndex():
    # template builder access for ONLY ADMINS
    if getattr(current_user, "role", None) != "admin":
        return redirect(url_for("home"))
    return template_builder.templateIndex()

@app.route("/credits", methods=["GET"])
def credits():
    return render_template("credits.html", title="Ctrl-Study: Credits")

def createQuizRow():
    """Inserts the quizzes row for the current quiz once and remembers its id.
    Returns the quiz id, or None if it couldn't be created."""
    if session.get("quizID"):
        return session["quizID"]

    userID = session.get("userID")
    params = session.get("quizParameters")
    questions = session.get("quizQuestions")
    if not (userID and params and questions):
        return None

    try:
        resp = ctrlDB.table("quizzes").insert({
            "user_id": userID,
            "seed": int(params["seed"]),
            "question_count": len(questions),
            "tags": params.get("tags", []),
            "types": params.get("types", []),
            "languages": params.get("languages", []),
        }).execute()
        session["quizID"] = resp.data[0]["id"]
        session.modified = True
        return session["quizID"]
    except Exception as e:
        print(f"createQuizRow failed: {e}")
        return None

@app.route("/quiz-complete", methods=["GET"])
def quizComplete():
    error = None

    if "quizQuestions" not in session or "progress" not in session:
        print("User tried to use quiz results page without questions or progress in session")
        return redirect(url_for("quiz"))
    if session["progress"] < len(session["quizQuestions"]):
        print("too soon to see those results, don'cha think?")
        return redirect(url_for("question"))
    if "quizGivenAnswers" not in session:
        print("tried to use quiz results page without answers in session")
        return redirect(url_for("question"))
    if "correctness" not in session:
        print("no correctness huh")
        return redirect(url_for("quiz"))

    correctPercent = sum(1 for v in session["correctness"].values() if v) / len(session["quizQuestions"])

    forms = list[QuestionForm]()
    for index, question in enumerate(session["quizQuestions"]):
        form = QuestionFetch.getQuestionForm(question, label=f"Answers{index}")
        data: list = session["quizGivenAnswers"].get(index, [])
        if isinstance(form, RadioQuestionForm) or isinstance(form, ShortAnswerQuestionForm):
            form.answer.data = data[0]
        else:
            form.answer.data = data
        forms.append(form)

    url = "/quiz?" + urlencode(session["quizParameters"], doseq=True)

    # Auto saves the quiz seed, question count, tags, types, and languages
    # save-quiz below lets users save the full quiz including questions, answers, feedback, etc
    if session.get("userID"):
        if createQuizRow() is None:
            error = "Could not autosave quiz."

    return render_template (
        "QuizComplete.html",
        title="Ctrl-Study: Quiz Complete",
        questions = session["quizQuestions"],
        givenAnswers = session["quizGivenAnswers"],
        correctness = session["correctness"],
        forms = forms,
        correctPercent = correctPercent,
        retakeQuizURL = url,
        error=error
    )

@app.route("/question", methods=["GET", "POST"])
def question():
    if "quizQuestions" not in session or session["quizQuestions"] is None:
        print("User tried to use quiz question page without questions in session")
        return redirect(url_for("quiz"))
    if "progress" not in session:
        session["progress"] = 0
    if "correctness" not in session:
        session["correctness"] = {}
    if "quizGivenAnswers" not in session:
        session["quizGivenAnswers"] = {}
    if session["progress"] >= len(session["quizQuestions"]):
        return redirect(url_for("quizComplete"))
    if "SingleQuestionState" not in session:
        session["SingleQuestionState"] = "NewQuestion"
    elif session["SingleQuestionState"] == "ToNewQuestion":
        session["SingleQuestionState"] = "NewQuestion"

    # STATE MACHINE
    action = request.form.get("action") if request.method == "POST" else None

    if action == "next" and session["SingleQuestionState"] == "Answered":
        session["progress"] += 1
        session["SingleQuestionState"] = "ToNewQuestion"
        session.modified = True
        return redirect(url_for("question"))

    question = session["quizQuestions"][session["progress"]]
    form = QuestionFetch.getQuestionForm(question)

    if action == "submit" and session["SingleQuestionState"] == "NewQuestion" and form.validate_on_submit():
        correct = form.correct
        answers = form.answer.data
        if not isinstance(answers, list):
            answers = [answers]
        answers = [answer.replace('\r\n', '\n') for answer in answers]
        isCorrect = set(answers) == set(correct)
        session["quizGivenAnswers"][session["progress"]] = answers
        session["correctness"][session["progress"]] = isCorrect
        session["SingleQuestionState"] = "Answered"
        session.modified = True

    if session["SingleQuestionState"] == "Answered":
        isCorrect = session["correctness"].get(session["progress"], False)
        return render_template(
            "individualQuestion.html",
            title="Question",
            form=form,
            status="Correct" if isCorrect else "Incorrect",
            showingAnswer=True,
            currentQuestion=session["progress"] + 1,
            totalQuestions=len(session["quizQuestions"]),
        )
    else:
        return render_template(
            "individualQuestion.html",
            title="Question",
            form=form,
            status="",
            showingAnswer=False,
            currentQuestion=session["progress"] + 1,
            totalQuestions=len(session["quizQuestions"]),
        )

@app.route("/quiz", methods=["GET", "POST"])
def quiz():
    tags = supabase_client.FetchUsedTags()
    types = [
        "multiple_choice",
        "multiple_select",
        #"short_answer", until we have good ones
        "true_false"
    ]
    languages = ["Python", "C++"]
    ts = [(tag["id"], tag["name"]) for tag in tags]
    form = SetupQuizForm(types=types, tags=ts, languages=languages)
    for key in ["quizQuestions", "SingleQuestionState", "progress", "quizGivenAnswers", "correctness",
                "seed", "quizParameters", "quizID", "quizQuestionsSaved"]:
        session.pop(key, None)  # None default avoids KeyError check

    if len(request.args.keys()) > 0:
        newseed = makeSeed()
        tag: list[str] = [name for id, name in ts]

        argTags = request.args.getlist('tags')
        argTypes = request.args.getlist('types')
        argLangs = request.args.getlist('languages')
        argSeed = request.args.get('seed')

        count = int(request.args.get('count', default = 10))
        seed = argSeed if argSeed else newseed
        tags = argTags if argTags else tag
        types = argTypes if argTypes else types
        languages = argLangs if argLangs else languages

        session["quizQuestions"] = QuestionFetch.getRandomQuestions(
            count=count,
            tags=tags,
            types=types,
            languages=languages,
            seed=seed
        )

        session["quizParameters"] = {
            "count": int(request.args.get('count', default = 10)),
            "tags": argTags if argTags else tag,
            "types": types,
            "languages": languages,
            "seed": seed
        }

        session["seed"] = seed

        return redirect(url_for('question'))

    if form.validate_on_submit():
        t = form.tagSelection.data
        types = form.questionTypes.data
        count = form.questionCount.data
        languageSel = form.languageSelection.data
        seed = form.seed.data if form.seed.data else makeSeed()
        session["seed"] = seed
        if t is not None and types is not None and languageSel is not None and count is not None:
            ts_dict = {str(tag_id): name for tag_id, name in ts}
            tag = [ts_dict[id] for id in t]
            session["quizQuestions"] = QuestionFetch.getRandomQuestions(
                count=count,
                tags=tag,
                types=types,
                languages=languageSel,
                seed=seed
            )
            session["quizParameters"] = {
                "count": count,
                "tags": tag,
                "types": types,
                "languages": languageSel,
                "seed": seed
            }
        return redirect(url_for("question"))
    return render_template("QuizSetup.html", tags=tags, form=form)

def sessionLookup(mapping, index, default=None):
    if index in mapping:
        return mapping[index]
    return mapping.get(str(index), default)

@app.route("/save-quiz", methods=['POST'])
def saveQuiz():
    userID = session.get("userID")
    if not userID:
        return jsonify(status="error", message="You need to be logged in to save a quiz."), 401

    if session.get("quizQuestionsSaved"):
        return jsonify(status="success", message="This quiz is already saved.")

    questions = session.get("quizQuestions")
    givenAnswers = session.get("quizGivenAnswers")
    correctness = session.get("correctness")

    if not questions or givenAnswers is None or correctness is None:
        return jsonify(status="error", message="No completed quiz to save."), 400
    if session.get("progress", 0) < len(questions):
        return jsonify(status="error", message="Finish the quiz before saving it."), 400

    # Normally created by the autosave; this is a fallback if that failed
    quizID = createQuizRow()
    if quizID is None:
        return jsonify(status="error", message="Could not find or create this quiz."), 500

    try:
        rows = [
            {
                "position": index,
                "source_question_id": getattr(question, "id", None),
                "question_type": question.type,
                "language": question.language,
                "question_text": "\n\n".join(p for p in (question.prompt, question.question) if p) or question.title,
                "options": (
                    [
                        {"value": str(c[0]), "label": str(c[1])}
                        if isinstance(c, (tuple, list)) and len(c) >= 2
                        else {"value": str(c), "label": str(c)}
                        for c in question.answer
                    ]
                    if question.answer
                    else None
                ),
                "correct_answers": [str(c[0]) if isinstance(c, (tuple, list)) else str(c) for c in (
                    question.correct
                    if isinstance(question.correct, (list, tuple, set))
                    else [question.correct]
                )],
                "given_answers": [str(g) for g in sessionLookup(givenAnswers, index, [])],
                "is_correct": bool(sessionLookup(correctness, index, False)),
                "feedback": question.feedback,
                "quiz_id": quizID,
            }
            for index, question in enumerate(questions)
        ]
    except Exception as e:
        print(f"save-quiz: could not build question rows: {e}")
        return jsonify(status="error", message="Could not read the quiz data."), 500

    try:
        # Upsert on the (quiz_id, position) unique constraint, so a retry
        # after a partial failure can't create duplicates or conflicts
        ctrlDB.table("quiz_questions").upsert(rows, on_conflict="quiz_id,position").execute()
    except Exception as e:
        print(f"save-quiz: question insert failed: {e}")
        return jsonify(status="error", message="Could not save the quiz questions."), 500

    session["quizQuestionsSaved"] = True
    session.modified = True
    return jsonify(status="success", message="Quiz saved to account.")

# Starts local development server when run directly
if __name__ == "__main__":
    app.run(debug=True)
