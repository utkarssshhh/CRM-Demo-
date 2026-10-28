# AI CRM Demo (Streamlit + SQLite)

Dashboard, drag-free Kanban pipeline, contacts with timeline, and an AI lead inbox
that scores incoming WhatsApp/web-form messages. Runs with no API key
(rule-based fallback); add a Claude key to switch on real AI.

## Run locally
    pip install -r requirements.txt
    streamlit run app.py

## Deploy free (Streamlit Community Cloud)
1. Create a GitHub repo and push these files (app.py, requirements.txt, .streamlit/config.toml, .gitignore).
2. Go to share.streamlit.io, sign in with GitHub, click "Create app", pick the repo, main file `app.py`, Deploy.
3. Optional: App settings -> Secrets -> add `ANTHROPIC_API_KEY = "sk-ant-..."`.
4. You get a public link like https://yourname-crm-demo.streamlit.app to send to clients.

## Notes
- Data resets when the free app restarts (seed data is recreated). Good for demos; use Supabase/Postgres for real use.
- Free apps sleep after inactivity; open the link a few minutes before a client call.
- Use the "Reset demo data" button in the sidebar to clean up after testing.
