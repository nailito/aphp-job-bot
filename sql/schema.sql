CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    title TEXT,
    metier TEXT,
    filiere TEXT,
    hopital TEXT,
    location TEXT,
    contrat TEXT,
    teletravail TEXT,
    horaire TEXT,
    temps_travail TEXT,
    date_publication TEXT,
    description TEXT,
    url TEXT,
    score INTEGER,
    priorite TEXT,
    score_raison TEXT,
    score_points_forts TEXT,
    score_points_faibles TEXT,
    mots_cles_matches TEXT,
    raison TEXT,
    rejection_category TEXT,
    rejection_reason TEXT,
    first_seen TEXT,
    last_seen TEXT,
    scored_at TIMESTAMPTZ,
    miss_count INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'active'
);

ALTER TABLE jobs ADD COLUMN IF NOT EXISTS miss_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS scored_at TIMESTAMPTZ;

CREATE TABLE IF NOT EXISTS feedbacks (
    id SERIAL PRIMARY KEY,
    job_id TEXT NOT NULL UNIQUE REFERENCES jobs(id) ON DELETE CASCADE,
    decision TEXT NOT NULL,
    tags TEXT,
    commentaire TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS applications (
    id SERIAL PRIMARY KEY,
    job_id TEXT NOT NULL UNIQUE REFERENCES jobs(id) ON DELETE CASCADE,
    statut TEXT NOT NULL DEFAULT 'En cours',
    date_candidature DATE,
    notes TEXT,
    refus_raison TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS hcl_jobs (
    id INTEGER PRIMARY KEY,
    titre TEXT,
    url TEXT,
    localisation TEXT,
    contrats TEXT,
    filiere TEXT,
    duree TEXT,
    date_debut DATE,
    date_publication DATE,
    date_modification DATE,
    description TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    miss_count INTEGER NOT NULL DEFAULT 0,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ai_filter_decision TEXT,
    ai_filter_reason TEXT,
    score INTEGER,
    score_analysis TEXT,
    scored_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS hcl_feedbacks (
    id SERIAL PRIMARY KEY,
    job_id INTEGER NOT NULL UNIQUE REFERENCES hcl_jobs(id) ON DELETE CASCADE,
    decision TEXT NOT NULL,
    commentaire TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS hcl_applications (
    id SERIAL PRIMARY KEY,
    job_id INTEGER NOT NULL UNIQUE REFERENCES hcl_jobs(id) ON DELETE CASCADE,
    statut TEXT NOT NULL DEFAULT 'En cours',
    date_candidature DATE,
    notes TEXT,
    refus_raison TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS pipeline_runs (
    id SERIAL PRIMARY KEY,
    run_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    source TEXT NOT NULL,
    total_scraped INTEGER NOT NULL DEFAULT 0,
    new_offers INTEGER NOT NULL DEFAULT 0,
    removed_offers INTEGER NOT NULL DEFAULT 0,
    reactivated_offers INTEGER NOT NULL DEFAULT 0,
    ai_filtered INTEGER NOT NULL DEFAULT 0,
    ai_passed INTEGER NOT NULL DEFAULT 0,
    ai_rejected INTEGER NOT NULL DEFAULT 0,
    scored INTEGER NOT NULL DEFAULT 0,
    status TEXT,
    duration_sec INTEGER
);
