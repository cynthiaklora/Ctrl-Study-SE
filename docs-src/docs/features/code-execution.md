# Code Execution

This section will cover the code execution element of the application.

## Overview

Arbitrary code execution functionality was implemented to support the addition of programming-style questions that allow users to write code that will be executed on the server. Docker spawns single-use containers responsible for running one chunk of code and preserving the contents of `stdout` and `stderr` among other things for evaluation and grading purposes.

Along with the ability to code within defined programming questions, administrator accounts have access to a code sandbox at the `/code-sandbox` endpoint which can be used to execute any code on the server for testing/debugging purposes.

## Implementation

The main functionality is defined in `code_runner.py`. The public entrypoint that spawns docker containers, `runCode()` is defined here.

To support this function, a few dictionaries are declared:

* `BASE_OPTS`: define the flags that spawn the Docker container which try to prevent users from gaining elevated access. Each flag is explained more in-detail in its declaration.
* `LANGUAGE_ALIASES`: correct misalignment of how different programming langauges are defined across the codebase. This could be solved by defining a global, but would involve changing all references across the whole codebase to use these global references.
* `LANGUAGES` - for each language, define:
    * `image`: the docker image that this language needs to be able to execute the code.
    * `cmd`: the command the container will run to actually run the code.
    * `strip_pattern`: a regular expression that strips away comments and string literals in the code. This is used to support `checkRequirements()`, elaborated below.

A few constants are also declared for load balancing. See the top of the source file to view them, as their names are self explanatory.

To ensure programming questions follow the defined constraints of the problem, a `checkRequirements()` method is defined that will return a dictionary corresponding to unmet requirements defined in the question's template. These requirements are defined using regular expressions and can be used to enforce a specific pattern or to forbid a specific pattern. Before checking for these patterns, the `strip_pattern` is used to strip plaintext code from comments and string literals to ensure that the requirements are actually met within the code that's being run.

## Adding Programming Questions

Implementing a new programming question involves declaring variables, starter code, a correct answer, and applicable requirements. See the attached example:

    variables:
    var1 = UInt("a", 1, 50);
    var2 = UInt("b", 1, 50);

    starterCode:
    #include <iostream>

    using namespace std;

    // TODO: write your add function here

    int main() {
        int {{ var1.name }} = {{ var1 }};
        int {{ var2.name }} = {{ var2 }};

        // TODO: call your function in the allocated space
        cout << // <your function call> << endl;

        return 0;
    }

    answer:
    {{ var1.value + var2.value }}

    requirements:
    !cout\s*<<[^;]*\+ => Don't do the addition inside the cout statement. Put it in your function.
    cout\s*<<\s*[^;]*\([^;]*\)\s*<< => Ensure you call your function within the cout statement.

Note the requirements section. Two regular expressions are defined separated by a newline and, in this case, the first contains a forbidden pattern denoted by the `!` at the beginning, an arrow `=>` followed by a feedback message that corresponds to the requirement. This feedback message will be displayed to users that violate this requirement.

For this question, the requirements forbid users from adding directly within the cout statement and enforces a function call within the cout statement. This forces a specific code format.
