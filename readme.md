# Road Rakshak

A civic web app for reporting and tracking road damage. Citizens report damage with a photo and a map pin, municipal staff review and repair it, and an AI model gives a preliminary classification of each photo.

## Features

**For citizens**
- Register, log in, and report road damage with a photo, a description and a map location (GPS button included)
- Track a complaint by its ID, with a status timeline and staff remarks
- Download a PDF record of a complaint
- Delete your own complaint while it is still Submitted or Rejected
- Public live map of reported damage (shows no personal details)
- Email when the status of a complaint changes (optional)

**For municipal staff** (separate login at `/municipal/login`)
- Dashboard with search, filters, sorting and CSV export
- Complaint priority (Low, Normal, High, Urgent) and repair teams
- Duplicate detection with one-click "reject as duplicate"
- Staff account management
- Review, correct or confirm the AI classification
- Upload before, progress and after repair photos
- Analytics charts and a PDF summary report

**AI**
- YOLOv8 image classification of each report photo, with a confidence threshold of 35%
- Receipts, documents and screenshots are rejected before classification
- The app works without the model: complaints then go to manual review
- Rule-based severity estimate (Low, Medium, High) with a suggested priority

All times are shown in Indian Standard Time (IST).

## Tech stack

Python, Flask, Flask-SQLAlchemy (SQLite), Bootstrap 5, Leaflet, Chart.js, ReportLab (PDF), OpenCV and Pillow (image checks), Ultralytics YOLOv8 (classification), pytest.

## AI model

The model classifies a photo into one of five classes. It is a classifier, so it says what the damage is, not how big it is.

Evaluation on a held-out test split of 440 images the model never trained on:

| | Result |
|---|---|
| Overall accuracy | **95.9%** (422 of 440 correct) |
| pothole_issues | F1 97.3% (336 images) |
| damaged_road_issues | F1 92.6% (69 images) |
| mixed_issues | F1 78.9% (20 images) |
| illegal_parking_issues | F1 100% (11 images) |
| broken_road_sign_issues | F1 100% (4 images) |

Potholes make up most of the test set, so accuracy alone looks better than the weaker classes. The illegal parking and road sign test sets are too small to trust their 100%.

The severity estimate is rule-based. It uses the damage category, the AI confidence and warning words in the description, and it only suggests a priority. Staff decide the real one.

## Setup (Windows, PowerShell)

1. Clone the project and open the folder:
```powershell
   git clone https://github.com/vaishnaviD1509/RoadRakshak_Smartroad.git
   cd RoadRakshak_Smartroad
```

2. Create and activate a virtual environment, then install the requirements:
```powershell
   python -m venv venv
   .\venv\Scripts\Activate.ps1
   python -m pip install -r requirements.txt
```

3. Optional, to turn the AI on:
```powershell
   python -m pip install -r requirements-ai.txt
```
   The trained model is in `ai_models/road_damage_model.pt`.

4. Create your settings file and add a secret key:
```powershell
   Copy-Item .env.example .env
   python -c "import secrets; print(secrets.token_hex(32))"
```
   Put the printed key in `.env` as `SECRET_KEY=...`. Never share or commit `.env`.

5. Create a staff account. Run `python scripts\create_admin.py --help` to see its options, for example:
```powershell
   python scripts\create_admin.py --email you@example.com --name "Your Name"
```

6. Run the app:
```powershell
   python app.py
```
   Citizens log in at `http://127.0.0.1:5000/login` and staff at `http://127.0.0.1:5000/municipal/login`.

## Settings (`.env`)

| Setting | What it does |
|---|---|
| `SECRET_KEY` | Signs sessions. Required for real use. |
| `FLASK_DEBUG` | `1` for development, `0` when deployed. |
| `MAIL_USERNAME`, `MAIL_PASSWORD` | Turn on status emails. For Gmail, use an App Password. Leave empty for no email. |
| `MAIL_SERVER`, `MAIL_PORT`, `MAIL_FROM` | Optional mail settings (defaults: smtp.gmail.com, 587). |
| `APP_BASE_URL` | Optional, adds a tracking link to emails. |
| `AI_MODEL_PATH`, `AI_CONFIDENCE_THRESHOLD` | Model file and minimum confidence (default 0.35). |

## Training and evaluating the model

```powershell
python scripts\split_dataset.py --source "path\to\Road Issues"
python scripts\train_classifier.py --data dataset
python scripts\evaluate_model.py --data dataset
python scripts\predict_image.py "path\to\photo.jpg"
```

## Running the tests

```powershell
python -m pytest tests
```

## Project structure

```
app.py            app factory and entry point
config.py         settings read from .env
models/           database models
routes/           citizen, staff, tracking, map and auth routes
services/         business logic (complaints, AI, email, PDF, severity, time)
templates/        Jinja pages
static/           CSS and JavaScript
scripts/          admin creation and AI training / evaluation tools
tests/            pytest suite
ai_models/        trained model
```

## Limitations

- The AI is a preliminary aid and does not replace verification by a municipal engineer.
- Severity is an estimate from a category and wording, not a measurement of the damage.
- The "mixed" class is the least reliable one.
- SQLite is fine for a demo; a larger deployment should use a server database.

## Disclaimer

Road Rakshak is a civic technology demonstration project.