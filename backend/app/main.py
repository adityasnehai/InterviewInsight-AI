from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

from app.db import init_db
from app.api.auth import router as auth_router
from app.api.analysis import router as analysis_router
from app.api.avatar import router as avatar_router
from app.api.interview import router as interview_router
from app.api.live_interview import router as live_interview_router
from app.api.product import router as product_router
from app.api.reflective import router as reflective_router
from app.api.reports import router as reports_router
from app.api.routes import router as api_router
from app.api.scoring import router as scoring_router
from app.api.users import router as users_router

load_dotenv()
init_db()

app = FastAPI(title="InterviewInsight AI API")

origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(api_router, prefix="/api")
app.include_router(interview_router)
app.include_router(analysis_router)
app.include_router(reports_router)
app.include_router(scoring_router)
app.include_router(users_router)
app.include_router(reflective_router)
app.include_router(auth_router)
app.include_router(product_router)
app.include_router(live_interview_router)
app.include_router(avatar_router)
