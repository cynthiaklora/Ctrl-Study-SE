from flask_wtf import FlaskForm
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import CppLexer, PythonLexer, MarkdownLexer
from wtforms import Field, RadioField, SubmitField, SelectMultipleField, TextAreaField, FieldList, FormField, validators, widgets, StringField, PasswordField
from wtforms.fields import IntegerField
from wtforms.validators import DataRequired, Optional, InputRequired, Length, StopValidation
from markupsafe import Markup
from html import escape
import re
from typing import TypeVar, Generic
from question_library import BLANK_MARKER

class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=8)])
    submit = SubmitField('Login')

class RegisterForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=8)])
    confirmPassword = PasswordField('Password', validators=[DataRequired(), Length(min=8)])
    submit = SubmitField("Register")

class MultiCheckboxField(SelectMultipleField):
    widget = widgets.ListWidget(prefix_label=False)
    option_widget = widgets.CheckboxInput()

class SetupQuizForm(FlaskForm):
    questionTypes = MultiCheckboxField("Question Types")
    tagSelection = MultiCheckboxField("Tag Selection")
    languageSelection = MultiCheckboxField("Programming Language")
    questionCount = IntegerField("Question Count", validators=[DataRequired(), validators.number_range(min=1)], default=10)
    seed = StringField("Seed", validators=[Optional()])

    submit = SubmitField("Submit")

    def __init__(self, types: list[str], tags: list[tuple[str, str]], languages: list[str], *args, **kwargs):
        super(SetupQuizForm, self).__init__(*args, **kwargs)
        self.questionTypes.choices = [(t, t) for t in types]
        self.tagSelection.choices = [(id, name) for (id,name) in tags]
        self.languageSelection.choices = [(l, l) for l in languages]

# QUESTION TYPES

# generic question form, from which all questions descend
# T is a Field
# this type should never be instantiated directly
T = TypeVar("T", bound=Field)
class QuestionForm(FlaskForm, Generic[T]):
    prompt: str
    question: str
    correct: list[str]
    feedback: str
    language: str
    instructions: str
    answer: T

    def getCorrect(self) -> list[str]:
        return self.correct

    # Set True on forms whose inputs live inside the highlighted code block (fill in the blank)
    inline_blanks: bool = False

    def _highlight(self, text: str) -> str:
        match self.language:
            case "C++":
                lexer = CppLexer()
            case "Python":
                lexer = PythonLexer()
            case _:
                lexer = MarkdownLexer()
        formatter = HtmlFormatter(style="monokai", noclasses=True)
        return highlight(text, lexer, formatter)

    def format_html(self) -> str:
        return self._highlight(self.question)

class RadioQuestionForm(QuestionForm[RadioField]):
    prompt: str
    question: str
    correct: list[str]
    feedback: str
    answer: RadioField = RadioField("Answers", validators=[InputRequired()])
    instructions: str = "Choose one option."
    submit = SubmitField("Submit")

    def getCorrect(self) -> list[str]:
        return [self._choice_map[correct] for correct in self.correct]

    def __init__(
        self,
        prompt: str,
        question: str,
        correct: list[str],
        feedback: str,
        language: str,
        answerChoices: list[str],
        *args,
        **kwargs,
    ):
        super(RadioQuestionForm, self).__init__(*args, **kwargs)
        self.prompt = prompt
        self.question = question
        self.feedback = feedback
        self.language = language

        self._choice_map = {
            f"choice_{i}": text for i, text in enumerate(answerChoices)
        }
        self.answer.choices = list(self._choice_map.items())
        self.correct = [
            key for key, text in self._choice_map.items() if text in correct
        ]

class CheckboxQuestionForm(QuestionForm[MultiCheckboxField]):
    prompt: str
    question: str
    correct: list[str]
    feedback: str
    answer: MultiCheckboxField = MultiCheckboxField("Answers", validators=[InputRequired()])
    instructions: str = "Select all that apply."
    submit = SubmitField("Submit")

    def getCorrect(self) -> list[str]:
        return [self._choice_map[correct] for correct in self.correct]

    def __init__(
        self,
        prompt: str,
        question: str,
        correct: list[str],
        feedback: str,
        language: str,
        answerChoices: list[str],
        *args,
        **kwargs,
    ):
        super(CheckboxQuestionForm, self).__init__(*args, **kwargs)
        self.prompt = prompt
        self.question = question
        self.correct = correct
        self.feedback = feedback
        self.language = language
        self._choice_map = {
            f"choice_{i}": text for i, text in enumerate(answerChoices)
        }
        self.answer.choices = list(self._choice_map.items())
        self.correct = [
            key for key, text in self._choice_map.items() if text in correct
        ]

class ShortAnswerQuestionForm(QuestionForm[TextAreaField]):
    prompt: str
    question: str
    correct: list[str]
    feedback: str
    answer: TextAreaField = TextAreaField("Answers", validators=[DataRequired()], default=None)
    instructions: str = "Type your answer below."
    submit = SubmitField("Submit")

    def __init__(
        self,
        prompt: str,
        question: str,
        correct: list[str],
        language: str,
        feedback: str,
        *args,
        **kwargs,
    ):
        super(ShortAnswerQuestionForm, self).__init__(*args, **kwargs)
        self.prompt = prompt
        self.question = question
        self.correct = correct
        self.feedback = feedback
        self.language = language


# Renders nothing: the blank inputs are drawn inside the code block by FillBlankQuestionForm.format_html
class _NoWidget:
    def __call__(self, field, **kwargs):
        return Markup("")

# Collects every blank input (they all share the field's name, so the browser sends them in page order)
class BlankListField(Field):
    widget = _NoWidget()

    def process_formdata(self, valuelist):
        self.data = [str(v).replace("\r\n", "\n") for v in valuelist]

    def _value(self):
        return ""

    def pre_validate(self, form):
        if not self.data or not any(str(v).strip() for v in self.data):
            raise StopValidation("Fill in at least one blank.")

class FillBlankQuestionForm(QuestionForm[BlankListField]):
    prompt: str
    question: str
    correct: list[str]
    feedback: str
    answer: BlankListField = BlankListField("Answers")
    instructions: str = "Fill in each blank."
    inline_blanks: bool = True
    submit = SubmitField("Submit")

    def __init__(
        self,
        prompt: str,
        question: str,
        correct: list[str],
        feedback: str,
        language: str,
        *args,
        **kwargs,
    ):
        super(FillBlankQuestionForm, self).__init__(*args, **kwargs)
        self.prompt = prompt
        self.question = question
        self.correct = correct
        self.feedback = feedback
        self.language = language

    # Whitespace-insensitive, case-sensitive (code is case-sensitive)
    @staticmethod
    def _normalize(value: str) -> str:
        return " ".join(str(value).split())

    # Every blank must match its own answer, in order
    def grade(self, given: list[str]) -> bool:
        if len(given) != len(self.correct):
            return False
        return all(self._normalize(g) == self._normalize(c) for g, c in zip(given, self.correct))

    def getCorrect(self) -> list[str]:
        if len(self.correct) <= 1:
            return list(self.correct)
        return [f"Blank {i + 1}: {c}" for i, c in enumerate(self.correct)]

    # Highlights the code with placeholder tokens, then swaps each token for a text input
    def format_html(self) -> str:
        parts = self.question.split(BLANK_MARKER)
        tokens = [f"CTRLBLANK{i:02d}Z" for i in range(len(parts) - 1)]
        text = parts[0]
        for token, rest in zip(tokens, parts[1:]):
            text += token + rest

        html = self._highlight(text)
        given = self.answer.data if isinstance(self.answer.data, list) else []
        for i, token in enumerate(tokens):
            value = escape(given[i], quote=True) if i < len(given) else ""
            box = (
                f'<input type="text" name="{escape(self.answer.name, quote=True)}" value="{value}" '
                'autocomplete="off" autocapitalize="off" spellcheck="false" '
                f'aria-label="Blank {i + 1}" '
                'style="width: 12ch; font: inherit; color: #f8f8f2; background: #3e3d32; '
                'border: 1px dashed #a6e22e; border-radius: 3px; padding: 0 4px;">'
            )
            html = html.replace(token, box)
        return html
