# Welcome

Welcome to the Ctrl+Study documentation page. Here, you can find information about what the project is, how it runs, known issues/pitfalls, areas of improvement, and feature suggestions to keep the project moving.

This page is dedicated to briefly introducing the various pieces of the project. More information can be found on each of these topics and more under the Features tab.

Happy coding and good luck!

## Overview

Ctrl+Study is a learning platform for introductory level computer science courses, allowing users to take quizzes to reinforce their understanding of various fundamental concepts.

Ctrl+Study offers questions in the formats:

* Multiple Choice
* Fill-in-the-blank
* Programming

Users can make accounts to allow them to keep track of their learning by saving their quizzes and associated answers.

Administrator accounts can be used to create/edit/delete questions, view platform analytics, and collect information for debugging.

## Implementation

This section will give a brief introduction to how different elements of the project are implemented.

### Frontend

Ctrl+Study is built on [Flask](https://flask.palletsprojects.com/en/stable/), a web application framework.

The frontend is composed of Jinja Templates defined at `templates/`. Jinja is responsible for rendering the page based on underlying data passed to it from a Flask-WTF Form object, each defined at `Frontend/forms.py`, which are mainly used to communicate information between the internal server state and the front facing interface.

### Templating

Questions use a templating system, which allow variables to be randomized and persist between question and answer options. Read more [here](./Features/templating.md).

### Code Execution

Arbitrary code execution functionality supports programming style questions that allow users to submit any valid code that will be executed safely on the server side. Read more [here](./Features/code-execution.md).

### Database

User information persists between sessions using an externally hosted Supabase database. Public interfaces to communicate between the application and the database are defined within `supabase_client.py`. Read more [here](./Features/templating.md).

## Running Locally

Follow the steps for your desired method.

### Running via Python commands

**Prerequisites:** Python installed

1. Create a virtual environment so the running environment is consistent across machines:

    `python -m venv .venv`

    This creates a virtual environment called `.venv`.

2. Activate the virtual environment:

    - **Windows (PowerShell):**

        `.venv\Scripts\Activate.ps1`

        If this is your first time running a PowerShell script, see [this Stack Overflow article](https://stackoverflow.com/questions/18713086/virtualenv-wont-activate-on-windows) for help.

    - **Mac/Linux:**

        `source .venv/bin/activate`

3. Install the required packages:

    `pip install -r requirements.txt`

4. Start the app:

    `python ctrl.py`

5. The project will be accessible at <http://127.0.0.1:5000>.

### Running via Docker commands

**Prerequisites:** Docker installed, with the following images pulled:

| Image  | Command                       |
|--------|-------------------------------|
| Python | `docker pull python:3.12-slim`|
| GCC    | `docker pull gcc:13`          |
| Caddy  | `docker pull caddy:2`         |

1. Build and start the containers:

    `docker compose up --build`

2. The project will be accessible at <http://127.0.0.1:5000>.

> **Note:** The terminal will occasionally fill with error messages from Caddy. This is expected, because Caddy can't reach the production domain while running locally.

## Deployment Startup Guide

The application's deployment is meant to be run using Docker which will make a container for the main application spawned from running the `ctrl.py` main file and sibling containers for Caddy, acting as a reverse-proxy to redirect traffic from the domain to the application and allowing connections to be made over HTTPS, and additional Python or C++ containers for programming questions.

**Prerequisites:** A domain name and Docker installed, with the following images pulled:

| Image  | Command                       |
|--------|-------------------------------|
| Python | `docker pull python:3.12-slim`|
| GCC    | `docker pull gcc:13`          |
| Caddy  | `docker pull caddy:2`         |

The application is meant to be deployed using Docker via `docker compose up -d --build`. The `docker-compose.yaml` file defines the Docker project, the relationships between the containers, and forces the containers to restart if they crash for whatever reason.

The project was hosted previously on a DigitalOcean droplet, which provides the host. A free subdomain from [Duck DNS](https://www.duckdns.org) was used. Point the subdomain at the droplet's public IP and all traffic that reaches your subdomain will be directed to the droplet.
