# Purpose:
# This file is the Flask entrypoint for the template-based question generator app

# Function:
# - Displays one template input textbox and one question-name textbox
# - Supports Preview, Save, Load, Delete, and New actions
# - Uses parser_engine.generateQuestion to build preview output
# - Persists named question templates in a local JSON file for editing later

from __future__ import annotations

from flask import Flask, render_template, session, request, jsonify                        # Flask imports provide routing, form access, session state, and redirects

from Frontend import QuestionFetch
from Frontend.forms import RadioQuestionForm, SetupQuizForm, QuestionForm, ShortAnswerQuestionForm, FillBlankQuestionForm, LoginForm, RegisterForm, CustomQuizForm

from functools import wraps
from datetime import timedelta, timezone, datetime
from flask_session import Session

from flask import redirect, url_for, abort
from flask_login import LoginManager, login_required, login_user, current_user, logout_user, UserMixin
from flask_wtf import FlaskForm

from collections import Counter

import supabase_client
from supabase_client import ctrlDB, makeOauthClient
import template_builder

from urllib.parse import urlencode

from Frontend.QuestionFetch import QuestionContainer, makeSeed, parseSeed

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
    role = getattr(current_user, "role", "")
    return render_template("index.html", title="Ctrl-Study: Home", username=userName, role=role)

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

# Restricts a route to logged-in admins (non-admins are sent home, anonymous users to the login page)
def adminRequired(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user.is_authenticated:
            return login_manager.unauthorized()
        if getattr(current_user, "role", None) != "admin":
            return redirect(url_for("home"))
        return view(*args, **kwargs)
    return wrapped

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


def uniqueUsername(base):
    """
    This is just for in the very rare case that someone has the same generated username as someone else
    For example, if someone with user_name bob from github signs in, and then someone with 
    full_name bob from google signs in, they would have the same generated username, so
    this checks and corrects that issue.
    """
    base = "".join(c for c in base if c.isalnum() or c in "-_")[:30] or "user"
    candidate, n = base, 0
    while ctrlDB.table("users").select("id").eq("username", candidate).execute().data:
        n += 1
        candidate = f"{base}{n}"
    return candidate

def get_or_create_profile(user):
    existing = ctrlDB.table("users").select("id, username, role").eq("id", user.id).execute()
    if existing.data:
        return existing.data[0]

    meta = user.user_metadata or {}
    base = (
    meta.get("user_name") or meta.get("preferred_username") # Github oath returns
    or meta.get("full_name") or meta.get("name") # Google oath returns
    or (user.email or "").split("@")[0] # Final default
    )
    username = uniqueUsername(base)
    ctrlDB.table("users").insert({"id": user.id, "username": username}).execute()
    return {"id": user.id, "username": username, "role": None}

@app.route("/auth/callback")
def authCallback():
    code = request.args.get("code")
    if not code:  # user cancelled on provider, or Supabase returned an error
        return redirect(url_for("login"))

    callbackClient = makeOauthClient()
    try:
        user = callbackClient.auth.exchange_code_for_session({"auth_code": code}).user
        profile = get_or_create_profile(user)
    except Exception:
        return redirect(url_for("login"))

    login_user(User(id=profile["id"], username=profile["username"], role=profile["role"]))
    session["userID"] = current_user.id

    if profile["role"] == "admin":
        return redirect(url_for("templateIndex"))
    return redirect(url_for("home"))

OAuthProviders = {"github", "google"}

@app.route("/login/<provider>")
def OAuthLogin(provider):
    if provider not in OAuthProviders:
        abort(404)
    if current_user.is_authenticated:
        return redirect(url_for("home"))

    OAuthClient = makeOauthClient()
    result = OAuthClient.auth.sign_in_with_oauth({
        "provider": provider,
        "options": {"redirect_to": url_for("authCallback", _external=True)}
    })
    return redirect(result.url)

@app.route("/logout")
@login_required
def logout():
    ctrlDB.auth.sign_out()
    logout_user()
    session.clear()
    return redirect(url_for("home"))

class CsrfForm(FlaskForm):
    pass  # just provides the CSRF token

@app.route("/account")
@login_required
def account():
    error = None

    savedSeeds = (ctrlDB.table("quizzes").select("*").eq("user_id", session["userID"])
                 .is_("deleted_at", "NULL").order("created_at", desc=True).execute())
    savedSeedsRows = savedSeeds.data
    allQuizzes = (ctrlDB.table("quizzes").select("*, quiz_questions(*)")
                   .eq("user_id", session["userID"]).is_("deleted_at", "NULL").order("created_at", desc=True).execute().data or [])
    
    for q in allQuizzes:
        q["quiz_questions"].sort(key=lambda r: r["position"])

    # Only quizzes the user explicitly saved in full
    fullQuizzesRows = [q for q in allQuizzes if q.get("fully_saved")]

    # Every flagged question, newest quiz first, whether or not the quiz was fully saved
    confusingRows = [
        {"quiz": q, "q": qq}
        for q in allQuizzes
        for qq in q["quiz_questions"]
        if qq.get("is_confusing")
    ]

    return render_template("account.html", title="Account", error=error, autoSaved=savedSeedsRows, 
                           confusing=confusingRows, manualSaved=fullQuizzesRows, csrfForm=CsrfForm())
    

@app.route("/template", methods=["GET", "POST"])
@login_required
def templateIndex():
    # template builder access for ONLY ADMINS
    if getattr(current_user, "role", None) != "admin":
        return redirect(url_for("home"))
    return template_builder.templateIndex()

def fetchAll(table, columns, orderBy="id", pageSize=1000):
    # Supabase returns at most 1000 rows per request, so page through the table where needed
    rows, start = [], 0
    while True:
        batch = (ctrlDB.table(table).select(columns).order(orderBy)
                 .range(start, start + pageSize - 1).execute().data or [])
        rows.extend(batch)
        if len(batch) < pageSize:
            return rows
        start += pageSize

def barRows(counter, limit=None):
    # Turns a counter into rows for the template's bar lists
    items = counter.most_common(limit)
    top = items[0][1] if items else 1
    return [{"label": l, "value": v, "pct": round(v / top * 100), "text": str(v)} for l, v in items]

# As dev and live use the same database, these stats aren't going to be fully accurate
@app.route("/analytics", methods=["GET"])
@login_required
def analytics():
    if getattr(current_user, "role", None) != "admin":
        return redirect(url_for("home"))

    today = datetime.now(timezone.utc).date()
    day7 = (today - timedelta(days=7)).isoformat()
    day30 = (today - timedelta(days=30)).isoformat()
    day = lambda row: (row.get("created_at") or "")[:10]  # "YYYY-MM-DD", so strings compare correctly

    users = fetchAll("users", "id, username, created_at")
    quizzes = fetchAll("quizzes", "id, user_id, seed, question_count, tags, types, languages, created_at, deleted_at")
    savedQs = fetchAll("quiz_questions", "quiz_id, question_type, language, is_correct")
    bank = fetchAll("questions", "id, question_type, language, is_active")
    savedQs = fetchAll("quiz_questions", "quiz_id, question_type, language, is_correct, source_question_id")
    bank = fetchAll("questions", "id, title, question_type, language, is_active")
    quizzes = fetchAll("quizzes", "id, user_id, seed, question_count, tags, types, languages, created_at, deleted_at, fully_saved")
    savedQs = fetchAll("quiz_questions", "quiz_id, question_type, language, is_correct, source_question_id, is_confusing")
    fullIds = {q["id"] for q in quizzes if q.get("fully_saved")}
    fullQs = [r for r in savedQs if r["quiz_id"] in fullIds]   # complete quizzes only

    stats = {
        "totalUsers": len(users),
        "newUsers7": sum(1 for u in users if day(u) >= day7),
        "newUsers30": sum(1 for u in users if day(u) >= day30),
        "totalQuizzes": len(quizzes),
        "quizzes7": sum(1 for q in quizzes if day(q) >= day7),
        "quizzes30": sum(1 for q in quizzes if day(q) >= day30),
        "activeUsers30": len({au["user_id"] for au in quizzes if day(au) >= day30}),
        "avgQuestions": round(sum(aq["question_count"] or 0 for aq in quizzes) / len(quizzes), 1) if quizzes else 0,
        "uniqueSeeds": len({s["seed"] for s in quizzes}),
        "fullySaved": len(fullIds),
        "softDeleted": sum(1 for q in quizzes if q.get("deleted_at")),
        "activeQuestions": sum(1 for b in bank if b["is_active"])
    }

    # Quizzes per day, last 30 days (zero-filled so gaps show)
    perDay = Counter(day(q) for q in quizzes)
    days = [(today - timedelta(days=i)).isoformat() for i in range(29, -1, -1)]
    counts = [perDay[d] for d in days]
    peak = max(counts) or 1
    daily = [{"label": d[5:], "value": c, "pct": round(c / peak * 100)} for d, c in zip(days, counts)]

    # What users choose to study (from the quizzes' saved settings)
    tagCounts = barRows(Counter(t for q in quizzes for t in (q.get("tags") or [])), limit=10)
    typeCounts = barRows(Counter(t for q in quizzes for t in (q.get("types") or [])))
    langCounts = barRows(Counter(t for q in quizzes for t in (q.get("languages") or [])))

    # Site-wide accuracy calculated from fully saved quizzes only
    def accuracyRows(key):
        attempts, correct = Counter(), Counter()
        for sq in fullQs:
            k = sq.get(key) or "Unknown"
            attempts[k] += 1
            correct[k] += 1 if sq["is_correct"] else 0
        rows = []
        for l, n in attempts.most_common():
            pct = round(correct[l] / n * 100)
            rows.append({"label": l, "value": pct, "pct": pct, "text": f"{pct}% ({n} answers)"})
        return rows

    totalAnswers = len(fullQs)
    overallAccuracy = round(sum(1 for sq in fullQs if sq["is_correct"]) / totalAnswers * 100) if totalAnswers else None

    # Most active users
    names = {u["id"]: u["username"] for u in users}
    perUser = Counter(q["user_id"] for q in quizzes)
    topUsers = barRows(Counter({names.get(uid, "unknown"): n for uid, n in perUser.items()}), limit=5)

    # Question bank size
    bankByType = barRows(Counter(b["question_type"] for b in bank if b["is_active"]))

    # Hardest questions
    MIN_ATTEMPTS = 3  # Ignore templates with too few answers to mean anything
    titles = {b["id"]: b["title"] for b in bank}
    tries, right = Counter(), Counter()
    for sq in fullQs:
        qid = sq.get("source_question_id")
        if qid is None:  # Ignore if saved before ids were added to container
            continue
        tries[qid] += 1
        right[qid] += 1 if sq["is_correct"] else 0

    # Highest miss rate first then by most attempts
    ranked = sorted(
        ((qid, n, n - right[qid]) for qid, n in tries.items() if n >= MIN_ATTEMPTS),
        key=lambda t: (-(t[2] / t[1]), -t[1])
    )
    hardest = [
        {"label": titles.get(qid, f"Question #{qid}"), "value": missed,
        "pct": round(missed / n * 100), "text": f"{round(missed / n * 100)}% missed ({n})"}
        for qid, n, missed in ranked[:10]
    ]
    trackedAnswers = sum(tries.values())

    # Most flagged question templates (flags come from both partial and full saves)
    flagCounts = Counter(
        r["source_question_id"] for r in savedQs
        if r.get("is_confusing") and r.get("source_question_id") is not None
    )
    mostConfusing = barRows(Counter({
        titles.get(qid, f"Question #{qid}"): n for qid, n in flagCounts.items()
    }), limit=10)
    for row in mostConfusing:
        row["text"] = f"{row['value']} flag{'s' if row['value'] != 1 else ''}"

    totalFlags = sum(1 for r in savedQs if r.get("is_confusing"))

    return render_template(
        "analytics.html", title="Analytics", stats=stats, daily=daily,
        tagCounts=tagCounts, typeCounts=typeCounts, langCounts=langCounts,
        accuracyByType=accuracyRows("question_type"), accuracyByLang=accuracyRows("language"),
        overallAccuracy=overallAccuracy, totalAnswers=totalAnswers,
        topUsers=topUsers, bankByType=bankByType, hardest=hardest,
        trackedAnswers=trackedAnswers, minAttempts=MIN_ATTEMPTS,
        mostConfusing=mostConfusing, totalFlags=totalFlags
    )

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

def buildQuestionRows(quizID, indexes=None):
    questions = session.get("quizQuestions") or []
    givenAnswers = session.get("quizGivenAnswers") or {}
    correctness = session.get("correctness") or {}
    flagged = {int(i) for i in session.get("confusingQuestions", [])}

    rows = []
    for index, question in enumerate(questions):
        if indexes is not None and index not in indexes:
            continue

        labels = {f"choice_{i}": str(text) for i, text in enumerate(question.answer or [])}

        correctValues = (
            question.correct
            if isinstance(question.correct, (list, tuple, set))
            else [question.correct]
        )
        correctValues = [str(c[0]) if isinstance(c, (tuple, list)) else str(c) for c in correctValues]
        givenValues = [str(g) for g in sessionLookup(givenAnswers, index, [])]

        rows.append({
            "position": index,
            "source_question_id": getattr(question, "id", None),
            "question_type": question.type,
            "language": question.language,
            "question_text": "\n\n".join(p for p in (question.prompt, question.question) if p) or question.title,
            "options": [{"value": v, "label": l} for v, l in labels.items()] if labels else None,
            "correct_answers": correctValues,
            "given_answers": [labels.get(v, v) for v in givenValues],
            "is_correct": bool(sessionLookup(correctness, index, False)),
            "feedback": question.feedback,
            "is_confusing": index in flagged,
            "quiz_id": quizID,
        })
    return rows

def autosaveConfusingQuestions(quizID):
    flagged = session.get("confusingQuestions") or []
    if not flagged or session.get("confusingSaved"):
        return True
    try:
        rows = buildQuestionRows(quizID, indexes={int(i) for i in flagged})
        ctrlDB.table("quiz_questions").upsert(rows, on_conflict="quiz_id,position").execute()
    except Exception as e:
        print(f"autosaveConfusingQuestions failed: {e}")
        return False
    session["confusingSaved"] = True
    session.modified = True
    return True

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
        quizID = createQuizRow()
        if quizID is None:
            error = "Could not autosave quiz."
        elif not autosaveConfusingQuestions(quizID):
            error = "Could not save your confusing questions."

    if session.get("customQuiz"):
        url = url_for("customQuiz") + "?" + urlencode(session["quizParameters"], doseq=True)
    else:
        url = "/quiz?" + urlencode(session["quizParameters"], doseq=True)

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

    if action in ("submit", "confusing") and session["SingleQuestionState"] == "NewQuestion" and form.validate_on_submit():
        correct = form.correct
        answers = form.answer.data
        if not isinstance(answers, list):
            answers = [answers]
        answers = [answer.replace('\r\n', '\n') for answer in answers]
        if isinstance(form, FillBlankQuestionForm):
            isCorrect = form.grade(answers)     # blanks are graded in order, not as a set
        else:
            isCorrect = set(answers) == set(correct)
        session["quizGivenAnswers"][session["progress"]] = answers
        session["correctness"][session["progress"]] = isCorrect
        session["SingleQuestionState"] = "Answered"

        if action == "confusing":
            flagged = session.setdefault("confusingQuestions", [])
            if session["progress"] not in flagged:
                flagged.append(session["progress"])

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
        "true_false",
        "fill_in_the_blank"
    ]
    languages = ["Python", "C++"]
    ts = [(tag["id"], tag["name"]) for tag in tags]
    form = SetupQuizForm(types=types, tags=ts, languages=languages)
    for key in ["quizQuestions", "SingleQuestionState", "progress", "quizGivenAnswers", "correctness",
                "seed", "quizParameters", "quizID", "quizQuestionsSaved", "customQuiz", "confusingQuestions", "confusingSaved"]:
        session.pop(key, None)  # None default avoids KeyError check

    if len(request.args.keys()) > 0:
        tag: list[str] = [name for id, name in ts]

        argTags = request.args.getlist('tags')
        argTypes = request.args.getlist('types')
        argLangs = request.args.getlist('languages')
        argSeed = request.args.get('seed')

        count = int(request.args.get('count', default = 10))
        seed = parseSeed(argSeed)
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
        seed = parseSeed(form.seed.data)
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

    # Normally created by the autosave; this is a fallback if that failed
    quizID = createQuizRow()
    if quizID is None:
        return jsonify(status="error", message="Could not find or create this quiz."), 500

    try:
        rows = buildQuestionRows(quizID)
    except Exception as e:
        print(f"save-quiz: could not build question rows: {e}")
        return jsonify(status="error", message="Could not read the quiz data."), 500

    try:
        # Upsert on (quiz_id, position): rows already autosaved as confusing are updated, not duplicated
        ctrlDB.table("quiz_questions").upsert(rows, on_conflict="quiz_id,position").execute()
        ctrlDB.table("quizzes").update({"fully_saved": True}).eq("id", quizID).execute()
    except Exception as e:
        print(f"save-quiz: question insert failed: {e}")
        return jsonify(status="error", message="Could not save the quiz questions."), 500

    session["quizQuestionsSaved"] = True
    session.modified = True
    return jsonify(status="success", message="Quiz saved to account.")

@app.route("/quiz/<int:quizId>/delete", methods=["POST"])
@login_required
def deleteQuiz(quizId):
    if not CsrfForm().validate_on_submit():
        abort(400)

    (ctrlDB.table("quizzes")
        .update({"deleted_at": datetime.now(timezone.utc).isoformat()})
        .eq("id", quizId)
        .eq("user_id", current_user.id)
        .is_("deleted_at", "null")
        .execute())

    return redirect(url_for("account"))

@app.route("/quesiton/<int:questionID>/unConfuse", methods=["POST"])
@login_required
def removeConfused(questionID):
    if not CsrfForm().validate_on_submit():
        abort(400)

    userQuizzes = (ctrlDB.table("quizzes")
            .select("id")
            .eq("user_id", current_user.id)
            .execute())

    quizIDs = [r["id"] for r in userQuizzes.data]

    (ctrlDB.table("quiz_questions")
    .update({"is_confusing": False})
    .eq("id", questionID)
    .in_("quiz_id", quizIDs)
    .is_("is_confusing", "TRUE")
    .execute())

    return redirect(url_for("account"))

# ADMIN TESTING: hand-pick specific questions from the pool and take them as a quiz.
# Lets admins try out newly added questions before students see them.
QUIZ_SESSION_KEYS = ["quizQuestions", "SingleQuestionState", "progress", "quizGivenAnswers", "correctness", "seed", "quizParameters", "customQuiz"]

def beginCustomQuiz(ids: list[int], seed) -> bool:
    for key in QUIZ_SESSION_KEYS:
        session.pop(key, None)
    questions = QuestionFetch.getQuestionsByIds(ids, seed)
    if not questions:
        return False
    session["quizQuestions"] = questions
    session["quizParameters"] = {"ids": ids, "seed": seed}
    session["customQuiz"] = True
    session["seed"] = seed
    return True

@app.route("/quiz/custom", methods=["GET", "POST"])
@adminRequired
def customQuiz():
    pool = supabase_client.FetchQuestionPool()
    form = CustomQuizForm(questions=[(str(q["id"]), q["title"]) for q in pool])
    error = None

    # Retake / shared link: /quiz/custom?ids=3&ids=7&seed=123 starts straight away
    argIds = []
    for raw in request.args.getlist("ids"):
        try:
            argIds.append(int(raw))
        except ValueError:
            pass
    if argIds:
        seed = request.args.get("seed") or makeSeed()
        if beginCustomQuiz(argIds, seed):
            return redirect(url_for("question"))
        error = "None of those questions exist anymore."

    elif form.validate_on_submit():
        ids = [int(i) for i in form.questionIds.data]
        seed = form.seed.data.strip() if form.seed.data and form.seed.data.strip() else makeSeed()
        if beginCustomQuiz(ids, seed):
            return redirect(url_for("question"))
        error = "Could not load the selected questions."

    return render_template("CustomQuiz.html", title="Ctrl-Study: Test Questions", form=form, pool=pool, error=error)

# Starts local development server when run directly
if __name__ == "__main__":
    app.run(debug=True)
