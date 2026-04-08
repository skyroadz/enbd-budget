"""
FastAPI application factory.
Creates the app, registers CORS middleware, includes all routers, and initialises the DB.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .db import init_db
from .routes import admin, budget, health, loans, monthly, summary, transactions

app = FastAPI(title="Budget Exporter", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)

# Initialise DB schema on startup
init_db()

# Register routers
app.include_router(health.router)
app.include_router(transactions.router)
app.include_router(summary.router)
app.include_router(budget.router)
app.include_router(admin.router)
app.include_router(loans.router)
app.include_router(monthly.router)
