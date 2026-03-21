import sqlite3
conn = sqlite3.connect('aphp_jobs.db')
conn.execute('''
    UPDATE jobs
    SET rejection_category = NULL, rejection_reason = NULL
    WHERE rejection_category IN ('passed_filter_1', 'diplome_paramedical', 'surqualification', 'profil_inadequat')
''')
conn.commit()
print('✅ Filtre IA réinitialisé :', conn.execute('SELECT COUNT(*) FROM jobs WHERE rejection_category IS NULL AND status = \"active\"').fetchone()[0], 'offres prêtes à être refiltrées')