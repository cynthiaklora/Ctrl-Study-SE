# CTRL+STUDY

Flask app for building and previewing template-based questions.

## Quick Start (macOS)
1. `python3 -m venv .venv`
2. `source .venv/bin/activate`
3. `python3 -m pip install -r requirements.txt`
4. `python3 ctrl.py`
5. Open `http://127.0.0.1:5000`

## Quick Start (Windows)
1. `python3 -m venv .venv`
2. `.venv/Scripts/Activate.ps1` (Ensure running scripts is enabled)
3. `pip install -r requirements.txt`
4. `python3 ctrl.py`
5. Open `http://127.0.0.1:5000`

## Alternate Run (Flask CLI)
1. `python3 -m venv .venv`
2. `source .venv/bin/activate`
3. `python3 -m pip install -r requirements.txt`
4. `flask run`

The `.flaskenv` file sets `FLASK_APP=ctrl.py`. If you don’t use `flask run`, you can ignore it.

## DigitalOcean Documentation

To get on the droplet, an SSH key needs to be setup and configured in account settings. This will not register it with the droplet, but it will be good to have for future use. 

Either through an already authorized user or the DigitalOcean Web Console, the public key must be appended by running either:
1. From root user:      `echo "<ssh key>" >> /home/deploy/.ssh/authorized_keys`
2. From deploy user:    `echo "<ssh key>" >> ~/.ssh/authorized_keys`

Once it's registerd, login via `ssh -i <path-to-private-ssh-key> deploy@<public-droplet-ip>`.

!! Reminder to set up a credentials manager to securely share sudo password and ctrlstudy email account credentials 

Software Engineering Group Members:

Jackson Reed

Cynthia Hawkersmith

Belden Love

Tanner Sloan

Kevin Molina

Dion Ukwuoma