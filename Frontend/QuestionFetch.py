from Frontend.forms import QuestionForm
import random
from random import choice
from typing import Any, cast
from Frontend.forms import RadioQuestionForm, CheckboxQuestionForm, ShortAnswerQuestionForm
from parser_engine import generateQuestion
# from flask import session
from dataclasses import dataclass
import supabase_client
import sys

questionIDs = supabase_client.FetchAllQuestions()

def makeSeed() -> int:
    aSeed = random.randrange(sys.maxsize)
    return aSeed


@dataclass
class QuestionContainer:
    prompt: str
    question: str
    correct: list[str]
    feedback: str
    answer: list[str]
    type: str
    language: str
    title: str

    def __init__(self, prompt: str, question: str, correct: list[str], feedback: str, answer: list[str], type: str, language: str, title: str):
        self.prompt = prompt
        self.question = question
        self.correct = correct
        self.feedback = feedback
        self.answer = answer
        self.type = type
        self.language = language
        self.title = title

    def __hash__(self):
        return hash(
            (self.prompt,
            self.question,
            self.feedback,
            self.type)
        )

def getRandomQuestions(seed: int, count: int = 1, tags: list[str] = [], types: list[str] = [], languages: list[str] = []) -> list[QuestionContainer] | None:
    def getDbQuestions() -> list[dict[str, str]] | None:
        #print(f"Fetching question with tags: {tags} and types: {types} and languages: {languages}")
        print(f"Using seed {seed}")
        options = supabase_client.FetchFilteredQuestions(tags=tags, questionTypes=types, languages=languages)
        print(f"Got question ids: {options}")
        if not options:
            return None

        questions = []

        random.seed(seed)
        ids = [choice(options) for _ in range(count)]
        print(f"Using question ids: {ids}")
        qs = supabase_client.FetchQuestionsByIds(ids)
        for c in qs:
            questions.append({
                    "type": c["question_type"],
                    "template": c["prompt_template"],
                    "prompt": c["question_template"],
                    "feedback": c["feedback_template"],
                    "language": c["language"],
                    "title": c["title"],
                })

        return questions

    q = getDbQuestions()
    if q is None:
        return None

    return _buildQuestions(q, seed)


def shuffleAnswers(answers: list[tuple[str, str]], seed: int) -> Any:
    opt = answers
    random.seed(seed)
    random.shuffle(opt)
    return cast(Any, opt)


# Turns raw question rows (type/template/prompt/feedback/language/title) into generated QuestionContainers.
# Shared by the random quiz and the admin hand-picked quiz so both generate questions the same way.
def _buildQuestions(q: list[dict[str, str]], seed: int) -> list[QuestionContainer]:
    questions = []

    random.seed(seed)
    print("Generating questions, seeds:")
    for qu in q:
        randNum = random.randrange(sys.maxsize)
        print(randNum)
        gq = generateQuestion(
            templateText=qu["template"], promptText=qu["prompt"], feedbackText=qu["feedback"], seed=randNum
        )
        gq["answers"] = shuffleAnswers([*gq["incorrect"], *gq["answer"]], seed=randNum)
        gq["type"] = qu["type"]
        questions.append(QuestionContainer(
            prompt=gq["prompt"],
            question=gq["question"],
            correct=gq["answer"],
            feedback=gq["feedback"],
            answer=gq["answers"],
            type=gq["type"],
            language=qu["language"],
            title=qu["title"]
        ))

    return questions


# ADMIN TESTING: builds a quiz from exactly the given question ids, in the given order (no random picking).
def getQuestionsByIds(ids: list[int], seed: int) -> list[QuestionContainer] | None:
    rows = supabase_client.FetchQuestionsByIds(ids)
    if not rows:
        return None

    q = [
        {
            "type": c["question_type"],
            "template": c["prompt_template"],
            "prompt": c["question_template"],
            "feedback": c["feedback_template"],
            "language": c["language"],
            "title": c["title"],
        }
        for c in rows
    ]
    return _buildQuestions(q, seed)

def getQuestionForm(question: QuestionContainer, label: str = "Answers") -> QuestionForm:

    match question.type:
        case "multiple_choice":
            form = RadioQuestionForm(
                prompt=question.prompt,
                question=question.question,
                correct=question.correct,
                feedback=question.feedback,
                answerChoices=question.answer,
                language=question.language,
                prefix = label
            )
        case "multiple_select":
            form = CheckboxQuestionForm(
                prompt=question.prompt,
                question=question.question,
                correct=question.correct,
                feedback=question.feedback,
                answerChoices=question.answer,
                language=question.language,
                prefix=label
            )
        case "true_false":
            form = RadioQuestionForm(
                prompt=question.prompt,
                question=question.question,
                correct=question.correct,
                feedback=question.feedback,
                answerChoices=question.answer,
                language=question.language,
                prefix=label
            )
        case "short_answer":
            form = ShortAnswerQuestionForm(
                prompt=question.prompt,
                question=question.question,
                correct=question.correct,
                feedback=question.feedback,
                language=question.language,
                prefix=label
            )
        case _:
            raise ValueError("Unknown question type.")

    return form
