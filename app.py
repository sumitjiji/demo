import streamlit as st
import requests
from bs4 import BeautifulSoup
import re
import json
import random

st.set_page_config(page_title="Form Auto‑Fill Demo", layout="centered")

st.markdown("""
<h1 style="text-align:center;">📝 Form Auto‑Fill (Education Only)</h1>
<p style="text-align:center;">
Parse a Google Form, set percentage distributions, and auto‑fill fake responses.<br>
<b>Do not use this to cheat or spam real forms.</b>
</p>
""", unsafe_allow_html=True)

# 1. URL input
form_url = st.text_input("1. Paste Google Form URL (viewform link)", placeholder="https://docs.google.com/forms/d/e/.../viewform")
if not form_url:
    st.stop()

# 2. Parse form structure
def parse_form(url):
    with st.spinner("Loading form structure..."):
        try:
            page = requests.get(url, timeout=10)
            page.raise_for_status()
        except Exception as e:
            st.error(f"Cannot load form: {e}")
            return None

        soup = BeautifulSoup(page.content, "html.parser")
        script_tags = soup.find_all("script")
        script_text = None
        for script in script_tags:
            if "FB_PUBLIC_LOAD_DATA_" in script.text:
                script_text = script.text
                break
        if not script_text:
            st.error("Could not find form data in page HTML.")
            return None

        match = re.search(r"FB_PUBLIC_LOAD_DATA_ = (\[.*?\]);", script_text, re.DOTALL)
        if not match:
            st.error("Could not find FB_PUBLIC_LOAD_DATA_.")
            return None

        data_str = match.group(1)
        data = json.loads(data_str)

        questions = []
        if not data or len(data) < 2 or not data[1] or len(data[1]) < 2:
            st.error("Unexpected form data structure.")
            return None

        for q in data[1][1]:
            qdata = q
            text = qdata[1] if len(qdata) > 1 else "Unknown question"
            qtype = qdata[3] if len(qdata) > 3 else None
            options_raw = qdata[4] if len(qdata) > 4 and qdata[4] else []
            options = [opt[0] for opt in options_raw if opt and len(opt) > 0]
            entry_id = None
            if options_raw and options_raw[0] and len(options_raw[0]) > 4 and options_raw[0][4]:
                entry_id = str(options_raw[0][4][0])
            questions.append({
                "id": entry_id,
                "text": text,
                "type": qtype,
                "options": options,
            })

        return questions

if st.button("Parse Form"):
    questions = parse_form(form_url)
    if not questions:
        st.stop()

    st.session_state.questions = questions
    st.success(f"✅ Found {len(questions)} question(s).")
    st.write("Parsed questions:")
    for q in questions:
        st.write(f"**Q:** {q['text']} → options: {q['options']}")

if "questions" not in st.session_state:
    st.stop()

questions = st.session_state.questions

# 3. Prompt input
prompt = st.text_input(
    "2. Enter prompt (percentage per option + number of responses)",
    placeholder="Q1: 70% Yes, 30% No; Q2: 50% A, 30% B; Generate 5 responses"
)
if not prompt:
    st.stop()

# 4. Simple prompt parser
def parse_prompt(prompt, questions):
    import re
    distribution = {}
    qmap = {str(i+1): q["id"] for i, q in enumerate(questions)}

    for match in re.findall(r"Q(\d+):\s*(.+?)(?=(?:;|$))", prompt, re.DOTALL):
        q_idx = match[0]
        rules = match[1]
        qid = qmap.get(q_idx)
        if not qid:
            st.warning(f"Unknown question index {q_idx}, skipped.")
            continue
        dist = {}
        total = 0.0
        for opt_match in re.findall(r"(\d+\.?\d*)% ([^,;]+)", rules):
            perc = float(opt_match[0])
            opt = opt_match[1].strip()
            dist[opt] = perc / 100.0
            total += perc / 100.0
        if total > 1.0:
            st.warning(f"Percentages for Q{q_idx} sum to more than 100%; normalizing.")
        distribution[qid] = dist

    nums = re.search(r"Generate (\d+) response", prompt, re.IGNORECASE)
    num_responses = int(nums.group(1)) if nums else 1
    return distribution, num_responses

dist, num_responses = parse_prompt(prompt, questions)

st.write(f"➡ Using **{num_responses}** response(s) with distribution:")
st.write(dist)

# 5. Sample one response
def sample_response(questions, distribution):
    answers = {}
    for q in questions:
        qid = q["id"]
        opts = q["options"]
        probs = distribution.get(qid, None)
        if probs and opts:
            total = sum(probs.values())
            if abs(total - 1.0) > 1e-6:
                probs = {k: v / total for k, v in probs.items()}
            weighted = list(probs.items())
            weights = [p for _, p in weighted]
            chosen = random.choices([o for o, _ in weighted], weights)[0]
            answers[qid] = chosen
        else:
            answers[qid] = random.choice(opts) if opts else "Unknown"
    return answers

# 6. Submit one response
def submit_response(form_url, answers):
    if "viewform" in form_url:
        response_url = form_url.replace("viewform", "formResponse")
    else:
        response_url = form_url + "/formResponse"

    payload = {}
    for qid, answer in answers.items():
        if qid:
            payload[f"entry.{qid}"] = answer

    try:
        res = requests.post(response_url, data=payload, timeout=10)
        return res.status_code == 200
    except Exception as e:
        st.error(f"Submit error: {e}")
        return False

# 7. Generate & auto‑fill button
if st.button("🚀 Generate & Auto‑Fill Responses"):
    if num_responses <= 0:
        st.error("Number of responses must be greater than 0.")
    else:
        progress = st.empty()
        success = 0  # ✅ FIXED: Initialize success variable
        
        for i in range(num_responses):
            answers = sample_response(questions, dist)
            if submit_response(form_url, answers):
                success += 1
            progress.text(f"📆 Done {i+1}/{num_responses} responses; success {success}")
        
        st.success(f"✅ Simulation finished. {success}/{num_responses} submissions succeeded.")
