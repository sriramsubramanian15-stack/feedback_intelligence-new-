"""Review Radar: company rules + CSV -> ranked, traceable product issues."""
import csv
import json
import logging
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from openai import AuthenticationError, RateLimitError, APIConnectionError, APITimeoutError
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from analyzer import analyze_batch
from analytics import read_feedback, build_result

app = FastAPI(title="Review Radar", version="2.0.0")
FRONTEND = Path(__file__).resolve().parent.parent / "frontend"
MAX_BYTES = 5 * 1024 * 1024


class Rule(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,80}$")
    label: str = Field(min_length=2, max_length=100)
    phrases: list[str] = Field(min_length=1, max_length=20)
    priority: Literal["low", "medium", "high"]

    @field_validator("phrases")
    @classmethod
    def clean_phrases(cls, values):
        values = list(dict.fromkeys(v.strip() for v in values))
        if any(not v or len(v) > 200 for v in values):
            raise ValueError("Each phrase must contain 1–200 characters.")
        return values


class Settings(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    company: str = Field(min_length=2, max_length=120)
    context: str = Field(min_length=10, max_length=2000)
    rules: list[Rule] = Field(min_length=1, max_length=30)

    @model_validator(mode="after")
    def unique_rules(self):
        if len({r.id for r in self.rules}) != len(self.rules):
            raise ValueError("Topic IDs must be unique.")
        if len({r.label.casefold() for r in self.rules}) != len(self.rules):
            raise ValueError("Use a distinct name for each problem topic.")
        return self


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/analyze")
def analyze(file: UploadFile = File(...), config: str = Form(...)):
    # Synchronous handler runs in FastAPI's threadpool; no blocking AI calls on the event loop.
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(400, "Upload a .csv file.")
    if len(config) > 100000:
        raise HTTPException(400, "Company settings are too large.")
    try:
        settings = Settings.model_validate_json(config)
    except (ValidationError, ValueError):
        raise HTTPException(400, "Invalid company settings. Check company, product description, distinct topic names, phrases and priorities.")
    raw = file.file.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise HTTPException(413, "Maximum CSV size is 5 MB.")
    try:
        rows, removed, total = read_feedback(raw)
    except (ValueError, csv.Error) as exc:
        raise HTTPException(400, str(exc))
    rules = [r.model_dump() for r in settings.rules]
    analyses = []
    try:
        for start in range(0, len(rows), 20):
            analyses.extend(analyze_batch(rows[start:start + 20], settings.company, settings.context, rules))
        # Result belongs to this request. No shared latest_result between companies.
        return build_result(rows, analyses, rules, removed, total, settings.company, settings.context)
    except AuthenticationError:
        raise HTTPException(502, "AI authentication failed. Check the backend API key.")
    except RateLimitError:
        raise HTTPException(503, "AI quota or rate limit reached. Check API credits or retry later.")
    except (APIConnectionError, APITimeoutError):
        raise HTTPException(503, "Could not reach the AI service. Check connectivity and retry.")
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(502, str(exc))
    except Exception:
        logging.exception("Feedback analysis failed")
        raise HTTPException(500, "Analysis failed. Check the backend terminal for details.")


@app.get("/", include_in_schema=False)
def homepage():
    return FileResponse(FRONTEND / "index.html")


# UI and API share localhost:8000; no separate frontend server or CORS configuration.
app.mount("/static", StaticFiles(directory=FRONTEND), name="static")
