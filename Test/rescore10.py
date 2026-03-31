# rescore_top10.py
import psycopg as psycopg2
import os

DATABASE_URL = os.getenv("DATABASE_URL", "")

def get_connection():
    return psycopg2.connect(DATABASE_URL, sslmode="require")

# 1. Reset les scores des 10 meilleures offres
with get_connection() as conn:
    with conn.cursor() as cur:
        cur.execute("""
            UPDATE jobs
            SET score = NULL,
                priorite = NULL,
                score_raison = NULL,
                score_points_forts = NULL,
                score_points_faibles = NULL,
                rejection_category = 'passed_filter_1'
            WHERE id IN (
                SELECT id FROM jobs
                WHERE score IS NOT NULL
                AND status = 'active'
                ORDER BY score DESC
                LIMIT 10
            )
        """)
    conn.commit()
    print("✅ 10 offres remises à zéro")

# 2. Re-scorer uniquement ces offres
from scorer import run_scorer
run_scorer(limit=10)