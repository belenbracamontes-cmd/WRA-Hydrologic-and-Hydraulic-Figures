# WRA Hydrology Tools

A small Streamlit web app that turns internal Python data tools (originally
ipywidgets/Jupyter GUIs) into a shared, multi-page website the team can open
in a browser.

Repo: https://github.com/belenbracamontes-cmd/WRA-Hydrologic-and-Hydraulic-Figures

## Project structure

```
peak_flow_webapp/
  Home.py                     # entrypoint -- st.set_page_config + the
                               # sectioned st.navigation() router (registers
                               # every page below under a labeled section)
  app_pages/                  # one file per tool. NOT named "pages" --
                               # Streamlit unconditionally falls back to its
                               # legacy auto-discovery (ignoring
                               # st.navigation entirely) whenever a folder
                               # literally named pages/ exists next to the
                               # entrypoint, regardless of what Home.py does
    0_Home.py                  # landing page content
    1_Peak_Flow_Viewer.py
  core/                       # shared logic, kept separate from UI code
    peak_flow.py              # Peak Flow Viewer's data/plotting logic
    branding.py                # logo helper
    view_source.py             # "View source" panel used on every page
  templates/
    new_page_template.py      # copy this to add a new tool (see below)
  assets/
    logo.png                  # drop your logo PNG here -- it gets committed
                               # like any other file so teammates get it too
  requirements.txt
```

## Running it locally

```
cd peak_flow_webapp
pip install -r requirements.txt
streamlit run Home.py
```

This opens a local URL (usually `http://localhost:8501`). For the whole team
to use it without everyone running it locally, deploy it to an internal
server or Streamlit Community Cloud so people get a shared link instead.

## Adding a new tool page

1. Copy the template into `app_pages/`:
   ```
   cp templates/new_page_template.py "app_pages/my_new_tool.py"
   ```

2. If the tool has real logic (data fetching, math, plotting), put it in
   its own module under `core/` (e.g. `core/my_new_tool.py`), mirroring how
   `core/peak_flow.py` holds all of the Peak Flow Viewer's logic. Keep the
   page file itself a thin UI layer -- sidebar inputs, a "Run" button, and
   calls into `core/`. This keeps the logic testable/reusable outside
   Streamlit and keeps `app_pages/` easy to read.

3. Register the page in `Home.py`: add an `st.Page(...)` entry (title,
   icon, unique `url_path`) and add it to a section in the
   `st.navigation({...})` dict.

4. Fill in the `TODO`s in the copied template, then run the app locally
   (`streamlit run Home.py`) and check the new page in the sidebar.

4. Commit and push (see below).

## Viewing the code

Every page has a **"View source code for this page"** expander at the
bottom, so teammates can see exactly how a tool works without leaving the
app. That's on top of -- not instead of -- browsing the full repo (history,
diffs, all files at once) on GitHub at the link above.

## Git / GitHub workflow

The repo is already initialized and pushed. For day-to-day changes:

```
git add -A
git commit -m "Describe what changed"
git push
```

To pull the latest changes (e.g. on another machine, or before starting new
work):

```
git pull
```

If you're new to git: `git status` shows what's changed, `git log --oneline`
shows recent commits. When in doubt before a push, run `git status` and
`git diff` first to see exactly what you're about to send up.
