# Review Radar — company-driven feedback prioritization

This version implements the clarified flow:

1. A company specifies its product context, problem keywords/phrases and priorities.
2. It uploads a CSV of customer feedback.
3. The backend removes exact same-user duplicates, uses AI to classify feedback by meaning, and ranks configured problems.
4. The output table opens customer names and original comments for each problem.

## 1. Put the files into your existing project

Back up your existing code or make a Git commit first. Extract this package and copy the following into your existing `feedback-intelligence` project:

| Package file | Destination | Purpose |
| --- | --- | --- |
| `backend/main.py` | `feedback-intelligence/backend/main.py` | CSV + company-settings API and frontend hosting |
| `backend/analyzer.py` | `feedback-intelligence/backend/analyzer.py` | AI relevance and topic assignment |
| `backend/analytics.py` | `feedback-intelligence/backend/analytics.py` | CSV cleanup, frequency, ranking and evidence |
| `backend/requirements.txt` | `feedback-intelligence/backend/requirements.txt` | Required dependencies |
| `frontend/index.html` | `feedback-intelligence/frontend/index.html` | Three screens |
| `frontend/style.css` | `feedback-intelligence/frontend/style.css` | Styling and responsive layout |
| `frontend/app.js` | `feedback-intelligence/frontend/app.js` | Forms, upload, results and evidence |
| `frontend/sample-feedback.csv` | `feedback-intelligence/frontend/sample-feedback.csv` | CSV template download |
| `.gitignore` | `feedback-intelligence/.gitignore` | Ignore keys and virtual environments |

If your existing `.gitignore` has other useful entries, merge these entries into it.
Use the exact names `analyzer.py`, `analytics.py`, and `requirements.txt`, WITHOUT `(2)` or `(1)`.
The backend and frontend in this package must be used together; the API response format has changed.
Keep the project's other files unless you know they are obsolete.

Keep your existing `backend/.env` with its real key. Do not replace it with the example.
If you are making a fresh project, copy `backend/.env.example` to `backend/.env`, then edit it:

```dotenv
OPENAI_API_KEY=your_existing_key
OPENAI_MODEL=gpt-4o-mini
```

A real key is deliberately NOT included in this download. No uploaded credentials were copied into it.
`.gitignore` prevents new untracked secrets from being added; it does not remove a file already tracked by Git.

## 2. Run on Windows CMD

Open the project folder in VS Code, then open a CMD terminal. If the terminal is at the project root:

```bat
cd backend
python -m venv venv
venv\Scripts\activate
python -m pip install -r requirements.txt
python -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

If `venv` already exists and works, skip `python -m venv venv` and activate it.
If your existing environment is named `.venv`, activate `.venv\Scripts\activate` instead.
If your terminal already ends in `\backend`, skip `cd backend`.
Keep this terminal open while using the app. Stop the server with Ctrl+C.

## 3. Run on macOS Terminal

For an existing project directly on your Desktop:

```bash
cd ~/Desktop/feedback-intelligence/backend
python3 -m venv venv
source venv/bin/activate
python -m pip install -r requirements.txt
python -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

Adjust the first path if your folder has a different name. If an environment already exists and works, skip creating it and activate that environment.

## 4. Open the website

Visit **http://127.0.0.1:8000** in your browser.

Use the Python server for this version, not VS Code Live Server and not a double-clicked HTML file. FastAPI serves the frontend and API at the same origin, so no separate frontend server or CORS setup is necessary.

- Website: `http://127.0.0.1:8000`
- Health check: `http://127.0.0.1:8000/health`
- API documentation: `http://127.0.0.1:8000/docs`

## 5. Try a complete demonstration

1. Click **Use example settings** on the first screen.
2. Inspect the company description, high-priority payment topic and low-priority UI topic.
3. Click **Save priorities & continue**.
4. Download the example CSV on the upload screen, or select `sample-feedback.csv` from this package.
5. Click **Analyze feedback**. This calls your AI backend and consumes API usage.
6. Inspect the ranked table. Open **Payment problems** to see names, IDs and original comments.
7. Use **Review & filtering log** to inspect duplicates, irrelevant comments, unconfigured problems and praise.
8. Export the full JSON report to keep the results.
9. Change company priorities and reanalyze to see how the ranking changes.

The sample includes an exact duplicate, a differently worded repeat by the same user, multiple customers, a multi-problem comment, spam, praise and an unconfigured feature request.
AI outputs can vary; inspect the classifications before presenting them as correct.

## 6. Your CSV format

Required headers: `user_id,name,feedback`. Optional: `date`.

```csv
user_id,name,feedback,date
u101,Asha,"Payment failed, but the money was deducted.",2026-09-25
u102,Dev,"Please make the settings button easier to find.",2026-09-25
```

- Export Excel/Sheets as **CSV UTF-8**.
- Use the same stable `user_id` for repeat submissions by one customer.
- Use different IDs for different customers, even if their names are identical.
- IDs are case-sensitive after trimming whitespace. Consistent IDs are the source system's responsibility.
- Comments containing commas or newlines must be quoted; spreadsheet CSV export does this automatically.
- Names and user IDs are required on non-empty comments. Empty feedback goes into the filtering log.
- Limit: 5 MB, 3,000 records, 6,000 characters per feedback message.
- The record number in the report refers to its data-record position, excluding the CSV header; a quoted multiline comment is one record.

## 7. What “filtering and clustering” means here

**Exact same-user duplicates:** compare `user_id` plus case-folded comment text with repeated whitespace collapsed. Keep the first and log the others before calling AI. Identical comments from DIFFERENT IDs remain separate reports.

**Same-user paraphrases:** they can remain as original evidence, but one user contributes just one frequency vote to each problem. This prevents repetitive complaints from inflating the ranking without discarding distinct information.

**Company-defined clusters:** each configured problem is a cluster. AI maps wording such as “money taken but order failed” to a configured payment problem. Company-supplied priority is used unchanged. AI does not invent priority levels.

**Multiple problems:** one comment may join several clusters. Its user counts once within each cluster.

**Unconfigured or uncertain problems:** go to Needs review. They receive no invented priority or rank. Add a company topic and reanalyze to rank them.

**Irrelevant and no-action feedback:** excluded from ranking but retained in the audit log. Praise that happens to contain a keyword is not automatically a problem.

Names, IDs and full original comments are attached by the backend, not generated by AI. Names/user IDs are not sent as separate fields to the model. Personal data present inside comment text will still be included in that text.

## 8. Ranking formula

Priority points: High = 3, Medium = 2, Low = 1.

`score = 60 × (priority_points / 3) + 40 × (issue_unique_users / all_matched_unique_users)`

Example: 6 different users have feedback matched to at least one topic:

| Problem | Priority | Unique users | Score |
| --- | --- | --- | --- |
| Payment problems | High (3) | 3 | 80.00 |
| UI improvements | Low (1) | 4 | 46.67 |

Repeated comments do not increase unique-user counts. Denominator excludes irrelevant, unmatched, empty and no-action-only users.
Scores are sorted descending by unrounded score. Ties use company priority, then unique-user count, then problem name. Displayed scores are rounded to two decimals.
This is a weighted priority/frequency ranking, not a strict “all high before all medium” policy. A very frequent medium-priority issue can outrank a rare high-priority issue.
The 60/40 weights are an explicit prototype default; change them in `analytics.py` and update the formula text in the backend and frontend together.
Because users may report multiple problems, frequency percentages across issues do not necessarily total 100%.

## 9. API contract for teammates

`POST /analyze` uses multipart form data:

- `file`: CSV upload
- `config`: JSON string with `company`, `context` and `rules`

```json
{
  "company": "Acme Shop",
  "context": "Online shopping app with payments and order tracking.",
  "rules": [
    {
      "id": "payments",
      "label": "Payment problems",
      "phrases": ["payment failed", "money deducted", "refund delay"],
      "priority": "high"
    }
  ]
}
```

Response fields: `company`, `context`, `rules`, `formula`, `summary`, `issues`, `audit`.
Each issue includes `rank`, `issue`, `priority`, `unique_users`, `messages`, `score`, `frequency_percent`, and full `evidence`.
Evidence includes original `id`, `user_id`, `name`, `feedback`, optional `date`, classification and reason.
The old `/chat` endpoint and global `latest_result` are not in this version; this implementation focuses on your requested three-screen workflow and returns results separately per request.

## 10. What is tested and what remains

Verified offline:
- CSV BOM, quoted commas/newlines, missing columns and malformed records.
- Same-user duplicates vs different users with the same name.
- Company-priority changes affect ranking.
- Unique-user counting, multiple topics per comment, evidence names and record IDs.
- Invalid/duplicate AI IDs and invalid topic assignments are rejected.
- All-irrelevant uploads return an empty ranking without dividing by zero.
- Website, static files, API settings validation and upload-to-results integration.

Run the included backend tests without making API calls:

```bash
python -m pip install httpx
python -m unittest discover -s backend -p "test_*.py" -v
```

Run the command from the project ROOT with the virtual environment activated.
The test classifier is a fixed fixture only used by the tests. The actual app uses the AI API, with no fake success or automatic demo fallback.

No paid live AI request was made while preparing this package. Your first real upload verifies the API key, model access, quota and real classification quality.
This is a local hackathon prototype, not a hosted multi-company account system: no authentication, database, company accounts, durable report history or background-job queue is included. Company settings persist in the browser; results last until reload or settings change unless exported. Large uploads run in batches and may take several minutes.
