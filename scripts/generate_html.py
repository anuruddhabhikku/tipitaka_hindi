#!/usr/bin/env python3

import json,sys
import os
import re
import sqlite3
import unicodedata
from collections import defaultdict
import tqdm

from indic_transliteration import sanscript
from indic_transliteration.sanscript import transliterate

# --------------------------------------------------
# Config
# --------------------------------------------------

INPUT_DIR = "."
OUTPUT_DIR = "output"
DPD_DB_PATH = os.path.join("output", "assets", "dpd.db")

# --------------------------------------------------
# Open SQLite
# --------------------------------------------------

print("Opening DPD SQLite...")
conn = sqlite3.connect(DPD_DB_PATH)
conn.row_factory = sqlite3.Row
print("DPD SQLite ready.")

# --------------------------------------------------
# Preload DB into memory (FAST)
# --------------------------------------------------

import json
import unicodedata

# Nikaya mapping for display
NIKAYA_MAP = {
    "दीघनिकायो": "दीघनिकाय",
    "मज्झिमनिकायो": "मज्झिमनिकाय",
    "संयुत्तनिकायो": "संयुत्तनिकाय",
    "अङ्गुत्तरनिकायो": "अङ्गुत्तरनिकाय",
    "खुद्दकनिकायो": "खुद्दकनिकाय",
    "खुद्दकनिकाये": "खुद्दकनिकाय"
}

print("Loading lookup index into memory...")

LOOKUP_MAP = {}

for row in conn.execute("""
    SELECT lookup_key, headwords
    FROM lookup
"""):
    key = row["lookup_key"]

    if not key:
        continue

    key = unicodedata.normalize("NFC", key.lower())

    hw = row["headwords"]

    if not hw:
        continue

    try:
        ids = json.loads(hw)
    except:
        continue

    if not ids:
        continue

    LOOKUP_MAP[key] = ids  # store list of ints

print("Lookup index ready.")

print("Loading headword data into memory...")

HEADWORD_MAP = {}

for row in conn.execute("""
    SELECT id, lemma_1, pos, meaning_1, grammar, derived_from, meaning_lit, meaning_2
    FROM dpd_headwords
"""):
    HEADWORD_MAP[row["id"]] = dict(row)

print(f"Loaded {len(HEADWORD_MAP)} headwords")

conn.close()

# --------------------------------------------------
# Render Nikaya Intro Page
# --------------------------------------------------

def render_nikaya_intro(prefix, att, corpus):
    """Create a separate page for nikaya intro (leading commentary entries)"""
    
    # Load att file(s) to get leading entries
    att_data = []
    if isinstance(att, list):
        for att_file in att:
            with open(att_file, "r", encoding="utf8") as f:
                att_data.extend(json.load(f))
    else:
        with open(att, "r", encoding="utf8") as f:
            att_data = json.load(f)
    
    # Get leading entries (those without 'n' at the beginning)
    leading_entries = []
    for e in att_data:
        if not e.get('n'):  # No paragraph number = leading entry
            leading_entries.append(e)
        else:
            break  # Stop once we hit first numbered entry
    
    if not leading_entries:
        return None
    
    # Find nikaya name from mul file
    nikaya_name = prefix  # Default to prefix
    mul_files = corpus.get(prefix, {}).get("mul")
    mul_data = []
    if mul_files:
        if isinstance(mul_files, list):
            for mul_file in mul_files:
                with open(mul_file, "r", encoding="utf8") as f:
                    mul_data.extend(json.load(f))
        else:
            with open(mul_files, "r", encoding="utf8") as f:
                mul_data = json.load(f)
        
        for e in mul_data:
            if e.get("rend") == "nikaya":
                nikaya_name = e.get("hi") or e.get("text")
                break
    
    html = []
    used_words = set()
    
    for e in leading_entries:
        att_text = e.get("text", "")
        att_hindi = e.get("hi", "")
        att_id = e.get("id", f"intro_{len(html)}")
        att_rend = e.get("rend", "")
        
        for w in att_text.split():
            used_words.add(normalize_word(w))
        wrapped_att = wrap_pali_words(att_text)
        
        extra_class = ""
        if att_rend == "subsubhead":
            extra_class = " subhead"
        elif att_rend == "gatha1":
            extra_class = " gatha"
        
        html.append(f"""
<div class="para">
    <div class="pali{extra_class}">
        {wrapped_att}
        <span style="float:right; cursor:pointer" 
              onclick="toggleHindi('{att_id}_hi', event)">📖</span>
    </div>
""")
        
        if att_hindi:
            html.append(f"""
    <div class="hindi" id="{att_id}_hi">
        {att_hindi}
    </div>
""")
        html.append("</div>")
    
    # Build local dictionary
    local_dict = {}
    for w in used_words:
        ids = LOOKUP_MAP.get(w)
        if not ids:
            continue
        
        entries = []
        seen = set()
        for id_ in ids:
            entry = HEADWORD_MAP.get(id_)
            if not entry:
                continue
            
            pos = entry.get("pos", "")
            meaning = entry.get("meaning_1", "")
            grammar = entry.get("grammar", "")
            
            construction = (
                entry.get("construction", "") or 
                entry.get("compound_construction", "") or 
                entry.get("derived_from", "") or
                entry.get("root_base", "")
            )
            
            root = entry.get("root_key", "")
            suffix = entry.get("suffix", "")
            lit = entry.get("meaning_lit", "")
            
            sig = f"{pos}|{meaning}|{grammar}|{construction}"
            if sig in seen:
                continue
            seen.add(sig)
            
            parts = []
            if pos:
                pos_map = {
                    "masculine": "masc", "feminine": "fem", "neuter": "nt",
                    "adjective": "adj", "verb": "vb", "adverb": "adv",
                    "preposition": "prep", "conjunction": "conj",
                    "indeclinable": "ind", "pronoun": "pron", "numeral": "num"
                }
                pos_short = pos_map.get(pos.lower(), pos[:4])
                parts.append(f"<i>{pos_short}</i>")
            
            if meaning:
                parts.append(meaning)
            
            if grammar and grammar not in meaning:
                grammar_clean = grammar.replace("comp", "").strip()
                if grammar_clean:
                    parts.append(f"[{grammar_clean}]")
            
            if construction:
                construction_parts = construction.split(' + ')
                dev_parts = []
                for part in construction_parts:
                    if is_pali_word(part):
                        dev_parts.append(roman_to_devanagari(part))
                    else:
                        dev_parts.append(part)
                dev_construction = ' + '.join(dev_parts)
                parts.append(f"‹ {dev_construction}")
            elif root:
                root_part = root
                if suffix:
                    root_part += f" + {suffix}"
                dev_root = roman_to_devanagari(root_part)
                parts.append(f"‹ {dev_root}")
            
            if lit and lit != meaning:
                parts.append(f"(lit. {lit})")
            
            entries.append(" ".join(parts))
        
        if entries:
            numbered_entries = []
            for i, entry in enumerate(entries, 1):
                numbered_entries.append(f"{i} {entry}")
            local_dict[w] = "<br>".join(numbered_entries)
    
    local_dict_js = f"const LOCAL_DICT = {json.dumps(local_dict, ensure_ascii=False)};"
    
    # Create output file
    outdir = os.path.join(OUTPUT_DIR, f"{prefix}_intro")
    os.makedirs(outdir, exist_ok=True)
    filename = f"{prefix}_intro.html"
    filepath = os.path.join(outdir, filename)
    
    title = f"{nikaya_name} - परिचय (Introduction)"
    with open(filepath, "w", encoding="utf8") as f:
        f.write(wrap_page(title, "\n".join(html), local_dict_js))
    
    return {
        "nikaya": nikaya_name,
        "file": os.path.join(f"{prefix}_intro", filename),
        "title": "परिचय (Introduction)",
        "hi": nikaya_name
    }
    
# --------------------------------------------------
# Helpers
# --------------------------------------------------
def is_pali_word(text):
    """Check if text contains Pali (IAST) characters"""
    # Pali IAST uses Latin characters with diacritics
    # English meanings won't have characters like ā, ī, ū, ṃ, ṅ, ñ, ṭ, ḍ, ṇ, ḷ
    pali_chars = set('āīūṃṅñṭḍṇḷ')
    return any(c in pali_chars for c in text)

def convert_pali_to_devanagari(text):
    """Convert only the Pali parts of text to Devanagari"""
    if not text:
        return text
    
    # Split into words
    words = text.split()
    converted = []
    
    for w in words:
        if is_pali_word(w):
            # This is a Pali word, convert it
            try:
                dev = transliterate(w, sanscript.IAST, sanscript.DEVANAGARI)
                converted.append(dev)
            except:
                converted.append(w)
        else:
            # This is English or punctuation, leave as is
            converted.append(w)
    
    return " ".join(converted)
def roman_to_devanagari(text):
    """Convert Roman IAST text to Devanagari"""
    try:
        return transliterate(text, sanscript.IAST, sanscript.DEVANAGARI)
    except:
        return text

def normalize_word(w):
    # Remove ALL punctuation including curly quotes
    w = re.sub(r"[.,;:!?।\"'()…‘’“”]", "", w).strip()

    if not w:
        return ""

    # Remove all invisible characters that break transliteration
    invisible_chars = [
        '\u200b',  # ZERO WIDTH SPACE
        '\u200c',  # ZERO WIDTH NON-JOINER (ZWNJ)
        '\u200d',  # ZERO WIDTH JOINER (ZWJ)
        '\u200e',  # LEFT-TO-RIGHT MARK
        '\u200f',  # RIGHT-TO-LEFT MARK
        '\u202a',  # LEFT-TO-RIGHT EMBEDDING
        '\u202b',  # RIGHT-TO-LEFT EMBEDDING
        '\u202c',  # POP DIRECTIONAL FORMATTING
        '\u202d',  # LEFT-TO-RIGHT OVERRIDE
        '\u202e',  # RIGHT-TO-LEFT OVERRIDE
        '\u2060',  # WORD JOINER
        '\ufeff',  # ZERO WIDTH NO-BREAK SPACE (BOM)
    ]
    
    for char in invisible_chars:
        w = w.replace(char, '')
    
    # STEP 2: Now transliterate with clean input
    try:
        # Check if it contains Devanagari characters
        if any('\u0900' <= c <= '\u097F' for c in w):
            w = transliterate(w, sanscript.DEVANAGARI, sanscript.IAST)
    except Exception as e:
        print(f"Transliteration warning for '{w}': {e}")
        # If transliteration fails, return original cleaned word
        pass

    # STEP 3: Final normalization
    return unicodedata.normalize("NFC", w.lower())
def wrap_pali_words(text):

    if not text:
        return ""

    words = text.split()
    wrapped = []

    for w in words:
        clean = normalize_word(w)
        wrapped.append(
            f'<span class="paliword" data-word="{clean}">{w}</span>'
        )

    return " ".join(wrapped)

# --------------------------------------------------
# File selection
# --------------------------------------------------

def get_sutta_files(prefix=None):
    """Get all mul and att files, optionally filtered by prefix"""
    files = []
    for f in os.listdir(INPUT_DIR):
        if prefix:
            if f.startswith(prefix) and (f.endswith(".mul.json") or f.endswith("m.nrf.json") or f.endswith(".att.json")):
                files.append(f)
        else:
            if re.match(r"^[a-z]+\d+[a-z]\d*\.(mul|nrf|att)\.json$", f):
                files.append(f)
    return sorted(files)

def load_corpus(prefix=None):
    """Group files by prefix, optionally filtered by prefix"""
    corpus = defaultdict(dict)
    
    if prefix=='all':
      files=[]
      for prefix0 in ['s01','s02','s03','s04','s05']:
        files0 = get_sutta_files(prefix0)
        files.extend(files0)
    else:
      files = get_sutta_files(prefix)
    
    for f in files:
        # Extract the base prefix (first part before .mul or .att)
        # ~ base = f.split('.')[0]  # s0101m, s0101a, etc.
        # ~ # Remove the trailing m/a to group mul and att together
        # ~ group = base[:-1]  # s0101
        base = f.split('.')[0]  # s0402m1, s0402a, etc.
        # Extract core sutta identifier (e.g., s0402 from s0402m1 or s0402a)
        import re
        match = re.match(r'(s\d{2}\d+)', base)
        group = match.group(1) if match else base
        
        if f.endswith("mul.json") or f.endswith("m.nrf.json"):
            if "mul" not in corpus[group]:
              corpus[group]["mul"] = []
            corpus[group]["mul"].append(f)
        elif f.endswith("att.json"):
            if "att" not in corpus[group]:
                corpus[group]["att"] = []
            corpus[group]["att"].append(f)
        # ~ if f.endswith("mul.json"):
            # ~ corpus[group]["mul"] = f
        # ~ elif f.endswith("att.json"):
            # ~ corpus[group]["att"] = f
    
    return corpus
# --------------------------------------------------
# Commentary index
# --------------------------------------------------

def index_para(entries):
    idx = defaultdict(list)
    leading_entries = []
    found_first_number = False
    
    # Store the full ordered list for sequential rendering
    ordered_entries = entries  # Keep reference to original order
    
    for e in entries:
        para = e.get("n")
        if para:
            found_first_number = True
            try:
                int_para = int(para)
                idx[int_para].append(e)
            except ValueError:
                if '-' in para:
                    try:
                        parts = para.split('-')
                        start = int(parts[0])
                        end = int(parts[1])
                        for num in range(start, end + 1):
                            idx[num].append(e)
                    except Exception:
                        pass
        else:
            if not found_first_number:
                leading_entries.append(e)
    
    if leading_entries:
        idx['leading'] = leading_entries
    
    # Also store the full ordered list
    idx['ordered'] = ordered_entries
    
    return idx
# --------------------------------------------------
# HTML Wrapper
# --------------------------------------------------

def wrap_page(title, body, local_dict_js):

    return f"""
<html>
<head>
<meta charset="utf8"/>

<style>

@font-face {{
    font-family: 'TiroDevaSanskrit';
    src: url('../assets/fonts/TiroDevaSanskrit-Regular.ttf') format('truetype');
    font-weight: normal;
    font-style: normal;
}}

@font-face {{
    font-family: 'TiroDevaSanskrit';
    src: url('../assets/fonts/TiroDevaSanskrit-Italic.ttf') format('truetype');
    font-weight: normal;
    font-style: italic;
}}

@font-face {{
    font-family: 'TiroDevanagari';
    src: url('../assets/fonts/TiroDevanagari-Regular.ttf') format('truetype');
    font-weight: normal;
    font-style: normal;
}}

@font-face {{
    font-family: 'TiroDevanagariHindi';
    src: url('../assets/fonts/TiroDevanagariHindi-Regular.ttf') format('truetype');
    font-weight: normal;
    font-style: normal;
}}

@font-face {{
    font-family: 'TiroDevanagariHindi';
    src: url('../assets/fonts/TiroDevanagariHindi-Italic.ttf') format('truetype');
    font-weight: normal;
    font-style: italic;
}}
body {{
    max-width: 900px;
    margin: auto;
    padding: 20px;
    line-height: 1.7;
    background: #fafafa;
}}

.para {{
    border-bottom: 1px solid #eee;
    padding: 15px 5px;
}}

.pali.gatha {{
    font-style: italic;
    border-left: 2px solid #ccc;
    padding-left: 10px;
    color: #444;
}}

.pali.subhead {{
    font-weight: bold;
    font-size: 1.1em;
    color: #333;
    border-bottom: 1px dotted #999;
    padding-bottom: 3px;
}}

.subsection-link {{
    color: #666;
    text-decoration: none;
    font-size: 0.95em;
}}
.subsection-link:hover {{
    color: #0066cc;
    text-decoration: underline;
}}
.paliword {{
    cursor:pointer;
        transition: background-color 0.2s;

}}

.paliword.no-dict {{
    text-decoration: underline dotted #cccccc;
    text-underline-offset: 3px;
    text-decoration-thickness: 1px;
    opacity: 0.8;
}}

.paliword.has-dict:hover {{
    background: #e6f0ff;
}}
.paliword.no-dict:hover {{
    background: #f5f5f5;
}}

.paliword:hover {{
    background:#f0f0f0;
}}


.pali {{
    font-size: 20px;
    padding: 6px 0;
    font-family: 'TiroDevaSanskrit', serif;  /* Pali uses TiroDevaSanskrit */
}}

.pali span[cursor="pointer"] {{
    opacity: 0.6;
    transition: opacity 0.2s;
}}
.pali span[cursor="pointer"]:hover {{
    opacity: 1;
}}
.hindi {{
    display:none;
    color:#444;
    margin-left:25px;
    font-family: 'TiroDevanagariHindi', 'TiroDevanagari', serif;  /* Hindi uses Hindi font */

}}

.commentary {{
    margin-left:25px;
    border-left:3px solid #eee;
    padding-left:15px;
    color:#666;
    font-family: 'TiroDevanagariHindi', 'TiroDevanagari', serif;  /* Hindi uses Hindi font */
}}

.commentary .pali {{
    font-family: 'TiroDevaSanskrit', serif;  /* Commentary Pali also uses Sanskrit font */
    min-height: 1.5em;  /* Maintain consistent height even when hidden */
}}

.commentary-pali {{
    display: none;  /* Hidden by default */
}}

.commentary-pali.visible {{
    display: inline;  /* Show when toggled on */
}}

/* Optional: Style for the toggle icons */
.commentary .pali span[cursor="pointer"] {{
    opacity: 0.6;
    transition: opacity 0.2s;
    font-size: 1.2em;
    padding: 0 2px;
}}

.commentary .pali span[cursor="pointer"]:hover {{
    opacity: 1;
    background: #f0f0f0;
    border-radius: 3px;
}}

/* Optional: Style for the fullscreen button */
.fullscreen-btn {{
    float: right;
    cursor: pointer;
    font-size: 24px;
    padding: 5px;
    user-select: none; /* Prevents accidental text selection */
}}
.fullscreen-btn:hover {{
    background: #f0f0f0;
    border-radius: 3px;
}}

</style>

<script>
{local_dict_js}

// Highlight words that have dictionary entries
// Mark words that DON'T have dictionary entries
document.addEventListener("DOMContentLoaded", function() {{
    document.querySelectorAll('.paliword').forEach(function(el) {{
        let word = el.dataset.word;
        if (word) {{
            if (LOCAL_DICT[word]) {{
                el.classList.add('has-dict');
            }} else {{
                el.classList.add('no-dict');
            }}
        }}
    }});
}});

function normalizePali(word){{
    if(!word) return "";
    return word.toLowerCase().trim();
}}

function lookupWord(word){{
    word = normalizePali(word);
    return LOCAL_DICT[word] || null;
}}

function showDictionary(word, event){{
    let result = lookupWord(word);
    let popup = document.getElementById("dictPopup");

    if(!popup) return;

    if(!result){{
        popup.style.display = "none";
        return;
    }}

    popup.innerHTML = result;
    popup.style.display = "block";

    let x = event.clientX + window.scrollX;
    let y = event.clientY + window.scrollY;

    popup.style.left = Math.min(x, window.innerWidth - 400) + "px";
    popup.style.top = y + "px";
}}

function toggleCommentary(id, event){{
    if(event) event.stopPropagation();
    let el = document.getElementById(id);
    if(!el) return;
    el.style.display = 
        el.style.display === "block" ? "none" : "block";
}}
function toggleHindi(id, event){{
    if(event) event.stopPropagation();
    let el = document.getElementById(id);
    if(!el) return;
    el.style.display =
        el.style.display === "block" ? "none" : "block";
}}

// ========== NEW FULLSCREEN FUNCTION ==========
function goFullScreen() {{
    var doc = window.document;
    var docEl = doc.documentElement; // Fullscreen the whole page

    var requestFullScreen = docEl.requestFullscreen ||
                            docEl.mozRequestFullScreen ||    // Firefox
                            docEl.webkitRequestFullScreen || // Chrome, Safari, Opera
                            docEl.msRequestFullscreen;       // IE/Edge

    if (requestFullScreen) {{
        requestFullScreen.call(docEl);
    }} else {{
        alert("Sorry, your browser doesn't support fullscreen mode.");
    }}
}}
document.addEventListener("click", function(e){{
    if(e.target.classList.contains("paliword")){{
        showDictionary(e.target.dataset.word, e);
    }}
    else{{
        let popup = document.getElementById("dictPopup");
        if(popup) popup.style.display = "none";
    }}
}});
</script>

</head>
<body>

<h1>{title} <span class="fullscreen-btn" onclick="goFullScreen()" title="Go Fullscreen">⛶</span></h1>

{body}

<div id="dictPopup"
style="
position:absolute;
display:none;
background:white;
border:1px solid #ccc;
padding:12px;
max-width:380px;
z-index:9999;
box-shadow:0 2px 8px rgba(0,0,0,0.2);
border-radius:6px;">
</div>

</body>
</html>
"""

# --------------------------------------------------
# Render Sutta Page
# --------------------------------------------------

def render_sutta_page(prefix, block, att_index, att):
    html = []
    used_words = set()
    sutta_title = None

    for e in block:

        if e.get("rend") == "chapter":
            sutta_title = e.get("hi") or e.get("text")
            
        # ADD THIS BLOCK FOR SUBHEAD
        if e.get("rend") == "subhead":
            para_id = e.get("id")
            pali_raw = e.get("text","")
            hindi_text = e.get("hi","")
            
            for w in pali_raw.split():
                used_words.add(normalize_word(w))
            
            pali_text = wrap_pali_words(pali_raw)
            
            # Add subhead with ID for anchor linking
            if para_id:
                html.append(f"<h3 id='{para_id}'>{pali_text}</h3>")
            else:
                html.append(f"<h3>{pali_text}</h3>")
                
            if hindi_text:
                # Use same ID with _hi suffix for Hindi toggle
                hindi_id = f"{para_id}_hi" if para_id else f"subhead_{len(html)}_hi"
                html.append(f"<div class='hindi' id='{hindi_id}'>{hindi_text}</div>")
            continue  # Skip the rest of the loop for subheads

# Process any rend that contains text content
        content_rends = ["bodytext", "gatha", "subhead", "verse", "prose"]
        if e.get("rend") in content_rends:
        # ~ if e.get("rend") == "bodytext":
          

            para_id = e.get("id", "para")
            pali_raw = e.get("text","")
            rend = e.get("rend", "")
            
              # Add a class based on rend type
            extra_class = ""
            if rend == "gatha":
                extra_class = " gatha"
            elif rend == "subhead":
                extra_class = " subhead"


            for w in pali_raw.split():
                used_words.add(normalize_word(w))

            pali_text = wrap_pali_words(pali_raw)
            hindi_text = e.get("hi","")

            html.append("<div class='para'>")
            # Add the extra_class to the pali div
            # ~ html.append(f"""
            # ~ <div class="pali{extra_class}">
                # ~ <span style="float:right; cursor:pointer" 
                      # ~ onclick="toggleHindi('{para_id}_hi', event)" 
                      # ~ title="Toggle Hindi translation">📖</span>
            # ~ """)

            html.append(f"""
            <div class="pali{extra_class}">
                
            """)

            # Check if this paragraph has commentary
            para_num = None
            has_commentary = False
            commentary_entries = []
            
            if e.get("n"):
                try:
                    para_num = int(e["n"])
                    if para_num and para_num in att_index:
                        has_commentary = True
                        commentary_entries = att_index[para_num]
                except:
                    pass

            # Mula Pali line with both icons (Hindi and Commentary)
            html.append(f"""
            <div class="pali">
                <span style="float:right; cursor:pointer" 
                      onclick="toggleHindi('{para_id}_hi', event)" 
                      title="Toggle Hindi translation">📖</span>
            """)
            
            # Add commentary toggle icon if there's commentary
            if has_commentary:
                html.append(f"""
                <span style="float:right; cursor:pointer; margin-right:10px" 
                      onclick="toggleCommentary('{para_id}_comm', event)" 
                      title="Toggle Pali commentary">📚</span>
                """)
            
            html.append(f"""
                {pali_text}
            </div>
            """)
            
            # Hindi translation for Mula (hidden by default)
            if hindi_text:
                html.append(f"""
            <div class="hindi" id="{para_id}_hi">
                {hindi_text}
            </div>
            """)
            
            

            # Commentary section (completely hidden by default)
            # FIX 1: Use commentary_entries directly instead of trying to find start_idx
                        # Commentary section (completely hidden by default)
            if has_commentary and commentary_entries:
                # Find the start index in the ordered commentary list
                start_idx = -1
                first_entry_id = commentary_entries[0].get('id')
                for i, att_entry in enumerate(att_index['ordered']):
                    if att_entry.get('id') == first_entry_id:
                        start_idx = i
                        break
                
                # Start commentary div
                html.append(f"""
            <div class="commentary" id="{para_id}_comm" style="display:none;">
            """)
                
                # Render all commentary entries from start_idx until n changes
                if start_idx >= 0:
                    ordered = att_index['ordered']
                    for j in range(start_idx, len(ordered)):
                        att_entry = ordered[j]
                        current_n = att_entry.get('n')
                        
                        # FIX: Handle range entries like "301-302"
                        matches_current_para = False
                        if current_n is not None:
                            if '-' in current_n:
                                # This is a range like "301-302"
                                try:
                                    parts = current_n.split('-')
                                    start = int(parts[0])
                                    end = int(parts[1])
                                    if start <= para_num <= end:
                                        matches_current_para = True
                                except:
                                    pass
                            elif current_n == str(para_num):
                                matches_current_para = True
                        
                        # Stop if we hit an entry with a different non-null n that doesn't match
                        if current_n is not None and not matches_current_para:
                            break
                        
                        # Skip leading entries entirely
                        if att_entry in att_index.get('leading', []):
                            continue
                        
                        att_text = att_entry.get("text","")
                        att_hindi = att_entry.get("hi","")
                        att_id = att_entry.get("id", f"commentary_{prefix}_{para_num}_{j}")
                        att_rend = att_entry.get("rend", "")
                        
                        for w in att_text.split():
                            used_words.add(normalize_word(w))
                        wrapped_att = wrap_pali_words(att_text)
                        
                        extra_class = ""
                        if att_rend == "subsubhead":
                            extra_class = " subhead"
                        elif att_rend == "gatha1":
                            extra_class = " gatha"
                        
                        html.append(f"""
                <div class="pali{extra_class}">
                    {wrapped_att}
                    <span style="float:right; cursor:pointer" 
                          onclick="toggleHindi('{att_id}_hi', event)">📖</span>
                </div>
                        """)
                        
                        if att_hindi:
                            html.append(f"""
                <div class="hindi" id="{att_id}_hi">
                    {att_hindi}
                </div>
                            """)
                
                html.append("</div>")  # Close commentary div
            html.append("</div>")  # Close para div


    # Build local dictionary subset - COMPACT, INFO# Build local dictionary subset - COMPACT, NO REDUNDANT HEADWORD
    local_dict = {}
    
    for w in used_words:
        ids = LOOKUP_MAP.get(w)
        if not ids:
            continue
        
        entries = []
        seen = set()
        
        for id_ in ids:
            entry = HEADWORD_MAP.get(id_)
            if not entry:
                continue
            
            lemma = entry.get("lemma_1", "")
            pos = entry.get("pos", "")
            meaning = entry.get("meaning_1", "")
            grammar = entry.get("grammar", "")
            
            # Get construction info
            construction = (
                entry.get("construction", "") or 
                entry.get("compound_construction", "") or 
                entry.get("derived_from", "") or
                entry.get("root_base", "")
            )
            
            root = entry.get("root_key", "")
            suffix = entry.get("suffix", "")
            lit = entry.get("meaning_lit", "")
            
            # Create unique signature
            sig = f"{pos}|{meaning}|{grammar}|{construction}"
            if sig in seen:
                continue
            seen.add(sig)
            
            # Build entry WITHOUT the headword at the beginning
            parts = []
            
            # Just the number and POS (no headword)
            if pos:
                pos_map = {
                    "masculine": "masc",
                    "feminine": "fem",
                    "neuter": "nt",
                    "adjective": "adj",
                    "verb": "vb",
                    "adverb": "adv",
                    "preposition": "prep",
                    "conjunction": "conj",
                    "indeclinable": "ind",
                    "pronoun": "pron",
                    "numeral": "num"
                }
                pos_short = pos_map.get(pos.lower(), pos[:4])
                parts.append(f"<i>{pos_short}</i>")
            
            # Meaning
            if meaning:
                parts.append(meaning)
            
            # Grammar
            if grammar and grammar not in meaning:
                grammar_clean = grammar.replace("comp", "").strip()
                if grammar_clean:
                    parts.append(f"[{grammar_clean}]")
            
            # Construction
            if construction:
                construction_parts = construction.split(' + ')
                dev_parts = []
                for part in construction_parts:
                    if is_pali_word(part):
                        dev_parts.append(roman_to_devanagari(part))
                    else:
                        dev_parts.append(part)
                dev_construction = ' + '.join(dev_parts)
                parts.append(f"‹ {dev_construction}")
            elif root:
                root_part = root
                if suffix:
                    root_part += f" + {suffix}"
                dev_root = roman_to_devanagari(root_part)
                parts.append(f"‹ {dev_root}")
            
            # Literal meaning
            if lit and lit != meaning:
                parts.append(f"(lit. {lit})")
            # ~ print(parts)
            entries.append(" ".join(parts))
        
        if entries:
            # Join with numbers to show distinct meanings
            numbered_entries = []
            for i, entry in enumerate(entries, 1):
                numbered_entries.append(f"{i} {entry}")
            
            local_dict[w] = "<br>".join(numbered_entries)
  
    local_dict_js = f"const LOCAL_DICT = {json.dumps(local_dict, ensure_ascii=False)};"

    outdir = os.path.join(OUTPUT_DIR, prefix)
    os.makedirs(outdir, exist_ok=True)

    filename = block[0].get("id","sutta") + ".html"

    with open(os.path.join(outdir, filename), "w", encoding="utf8") as f:
        f.write(wrap_page(sutta_title or prefix,
                          "\n".join(html),
                          local_dict_js))                        
# --------------------------------------------------
# Build blocks
# --------------------------------------------------

def build_blocks(mul):

    blocks = []
    current = []

    for e in mul:

        if e.get("rend") == "chapter":
            if current:
                blocks.append(current)
                current = []

        current.append(e)

    if current:
        blocks.append(current)

    return blocks

# --------------------------------------------------
# Generate Enhanced Hierarchical Index
# --------------------------------------------------

def generate_hierarchical_index(output_dir, corpus, intro_pages):
    """Generate a single index.html with complete nikaya/vagga/sutta hierarchy including intros"""
    global NIKAYA_MAP
    
    # First, scan all mul files to extract structure
    structure = {}
    
    for prefix, files in corpus.items():
        if "mul" not in files:
            continue
            
        # Handle multiple mul files
        mul_data = []
        if isinstance(files["mul"], list):
            for mul_file in files["mul"]:
                with open(mul_file, "r", encoding="utf8") as f:
                    mul_data.extend(json.load(f))
        else:
            with open(files["mul"], "r", encoding="utf8") as f:
                mul_data = json.load(f)
        
        current_nikaya = None
        current_vagga = None
        current_sutta = None
        
        for e in mul_data:
            rend = e.get("rend")
            text = e.get("text", "")
            
            if rend == "nikaya":
                current_nikaya = text
                # Normalize nikaya name to consistent form
                if current_nikaya == "मज्झिमनिकाये":
                    current_nikaya = "मज्झिमनिकायो"
                elif current_nikaya == "संयुत्तनिकाये":
                    current_nikaya = "संयुत्तनिकायो"
                elif current_nikaya == "खुद्दकनिकाये":
                    current_nikaya = "खुद्दकनिकायो"
                if current_nikaya not in structure:
                    structure[current_nikaya] = {}
            
            elif rend in ["book", "vagga", "nipata", "samyutta"]:
                current_vagga = text
                if current_nikaya and current_vagga not in structure[current_nikaya]:
                    structure[current_nikaya][current_vagga] = []
                    print(f"Added vagga: {current_vagga} to {current_nikaya}")

            
            elif rend in ["chapter", "sutta"]:
                current_sutta = {
                    "title": text,
                    "hi": e.get("hi", ""),
                    "file": os.path.join(prefix, e.get("id", "sutta") + ".html"),
                    "id": e.get("id"),
                    "subsections": []
                }
                if current_nikaya and current_vagga:
                    structure[current_nikaya][current_vagga].append(current_sutta)
            
            elif rend == "subhead" and current_sutta:
                # Add subsection to current sutta
                current_sutta["subsections"].append({
                    "title": text,
                    "hi": e.get("hi", ""),
                    "id": e.get("id")
                })
    
    # Generate HTML with enhanced styling
    html = []
    html.append("""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Tipitaka - Sutta Index</title>
    <style>
        body {
            max-width: 1000px;
            margin: 0 auto;
            padding: 20px;
            font-family: 'TiroDevanagariHindi', sans-serif;
            background: #fafafa;
        }
        h1 {
            color: #333;
            border-bottom: 2px solid #8B4513;
            padding-bottom: 10px;
        }
        .nikaya {
    background: white;
    padding: 15px;
    margin-bottom: 20px;
    border-radius: 8px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.1);
}

/* Nikaya level */
.nikaya h2 {
    color: #8B4513;
    margin: 0;
    padding: 12px;
    cursor: pointer;
    border-left: 5px solid #8B4513;
    background: #f9f9f9;
    border-radius: 5px;
    transition: background 0.2s;
    font-size: 1.4em;
}

.nikaya h2:hover {
    background: #f0f0f0;
}

.nikaya h2:before {
    content: "▶ ";
    font-size: 0.9em;
    color: #8B4513;
    display: inline-block;
    transition: transform 0.2s;
}

.nikaya h2.expanded:before {
    content: "▼ ";
}

.nikaya-content {
    display: none;
    margin-top: 15px;
}

.nikaya-content.expanded {
    display: block;
}

/* Intro section */
.nikaya-intro {
    margin: 10px 0 15px 20px;
    padding: 10px 15px;
    background: #f5f5f5;
    border-left: 3px solid #8B4513;
    border-radius: 0 5px 5px 0;
}

.nikaya-intro a {
    color: #8B4513;
    text-decoration: none;
    font-weight: 500;
    font-size: 1.1em;
}

.nikaya-intro a:hover {
    text-decoration: underline;
}

.nikaya-intro .intro-hi {
    color: #666;
    font-size: 0.9em;
    margin-left: 10px;
}

/* Vagga level */
.vagga {
    margin: 15px 0 10px 15px;
}

.vagga h3 {
    color: #666;
    margin: 10px 0 8px 0;
    padding: 8px;
    cursor: pointer;
    border-bottom: 1px solid #eee;
    transition: background 0.2s;
    font-size: 1.2em;
}

.vagga h3:hover {
    background: #f5f5f5;
}

.vagga h3:before {
    content: "▶ ";
    font-size: 0.8em;
    color: #999;
    display: inline-block;
    transition: transform 0.2s;
}

.vagga h3.expanded:before {
    content: "▼ ";
}

.vagga-content {
    display: none;
    margin-left: 20px;
}

.vagga-content.expanded {
    display: block;
}

/* Sutta level */
.sutta {
    margin: 8px 0 8px 20px;
}

.sutta-header {
    padding: 5px 10px;
    cursor: pointer;
    border-radius: 4px;
    transition: background 0.2s;
    display: flex;
    align-items: baseline;
    flex-wrap: wrap;
}

.sutta-header:hover {
    background: #f5f5f5;
}

.sutta-header:before {
    content: "▶ ";
    font-size: 0.8em;
    color: #999;
    display: inline-block;
    transition: transform 0.2s;
    margin-right: 5px;
}

.sutta-header.expanded:before {
    content: "▼ ";
}

.sutta-title {
    color: #0066cc;
    text-decoration: none;
    font-weight: 500;
}

.sutta-title:hover {
    text-decoration: underline;
}

.sutta-hi {
    color: #666;
    font-size: 0.9em;
    margin-left: 10px;
}

.sutta-content {
    display: none;
    margin-left: 25px;
    padding-left: 15px;
    border-left: 2px dotted #ddd;
}

.sutta-content.expanded {
    display: block;
}

.subsection-list {
    list-style: none;
    padding: 5px 0 5px 5px;
    margin: 5px 0;
}

.subsection-item {
    margin: 3px 0;
    padding: 3px 8px;
}

.subsection-link {
    color: #777;
    text-decoration: none;
    font-size: 0.95em;
}

.subsection-link:hover {
    color: #0066cc;
    text-decoration: underline;
}

.subsection-hi {
    color: #888;
    font-size: 0.9em;
    margin-left: 10px;
}
        .note {
            color: #666;
            font-style: italic;
            margin-bottom: 30px;
        }
    </style>
</head>
<body>
    <h1>📚 तिपिटक - सुत्त पिटक</h1>
    <p class="note">दीघ, मज्झिम, संयुत्त, अङ्गुत्तर, खुद्दक निकाय</p>
""")
    
    # Sort nikayas in traditional order
    nikaya_order = ["दीघनिकायो", "मज्झिमनिकायो", "संयुत्तनिकायो", "अङ्गुत्तरनिकायो", "खुद्दकनिकायो"]
    nikaya_display = NIKAYA_MAP
    
    for nikaya in nikaya_order:
        if nikaya not in structure:
            continue
            
        display_name = nikaya_display.get(nikaya, nikaya)
        html.append(f'<div class="nikaya">')
        html.append(f'<h2>{display_name}</h2>')
        html.append(f'<div class="nikaya-content">')
        
        # Add intro link if this nikaya has an intro page
        intro_file = intro_pages.get(nikaya, {}).get("file")
        if intro_file:
            html.append(f"""
        <div class="nikaya-intro">
            <a href="{intro_file}">📖 परिचय (Introduction)</a>
            <span class="intro-hi">{nikaya}</span>
        </div>
            """)

        vaggas = structure[nikaya]
        for vagga, suttas in vaggas.items():
            html.append(f'<div class="vagga">')
            html.append(f'<h3>{vagga}</h3>')
            html.append(f'<div class="vagga-content">')
            
            for sutta in suttas:
                html.append('<div class="sutta">')
                html.append(f'<div class="sutta-header">')
                html.append(f'<a class="sutta-title" href="{sutta["file"]}">{sutta["title"]}</a>')
                if sutta.get("hi"):
                    html.append(f'<span class="sutta-hi">{sutta["hi"]}</span>')
                html.append('</div>')
                
                if sutta.get("subsections"):
                    html.append('<div class="sutta-content">')
                    html.append('<ul class="subsection-list">')
                    for sub in sutta["subsections"]:
                        html.append('<li class="subsection-item">')
                        subsection_link = f'{sutta["file"]}#{sub["id"]}'
                        html.append(f'<a class="subsection-link" href="{subsection_link}">{sub["title"]}</a>')
                        if sub.get("hi"):
                            html.append(f'<span class="subsection-hi"> – {sub["hi"]}</span>')
                        html.append('</li>')
                    html.append('</ul>')
                    html.append('</div>')
                
                html.append('</div>')
            
            html.append('</div>')
            html.append('</div>')
        
        html.append('</div>')
        html.append('</div>')
    
    html.append("""
</body>
<script>
document.addEventListener('DOMContentLoaded', function() {
    // Toggle Nikaya
    document.querySelectorAll('.nikaya h2').forEach(function(header) {
        header.addEventListener('click', function(e) {
            e.stopPropagation();
            this.classList.toggle('expanded');
            var content = this.nextElementSibling;
            while(content && !content.classList.contains('nikaya-content')) {
                content = content.nextElementSibling;
            }
            if(content) {
                content.classList.toggle('expanded');
            }
        });
    });
    
    // Toggle Vagga
    document.querySelectorAll('.vagga h3').forEach(function(header) {
        header.addEventListener('click', function(e) {
            e.stopPropagation();
            this.classList.toggle('expanded');
            var content = this.nextElementSibling;
            while(content && !content.classList.contains('vagga-content')) {
                content = content.nextElementSibling;
            }
            if(content) {
                content.classList.toggle('expanded');
            }
        });
    });
    
    // Toggle Sutta
    document.querySelectorAll('.sutta-header').forEach(function(header) {
        header.addEventListener('click', function(e) {
            e.stopPropagation();
            this.classList.toggle('expanded');
            var content = this.nextElementSibling;
            while(content && !content.classList.contains('sutta-content')) {
                content = content.nextElementSibling;
            }
            if(content) {
                content.classList.toggle('expanded');
            }
        });
    });
    
    // Expand first nikaya by default
    var firstNikaya = document.querySelector('.nikaya h2');
    if(firstNikaya) {
        firstNikaya.classList.add('expanded');
        var firstContent = firstNikaya.nextElementSibling;
        while(firstContent && !firstContent.classList.contains('nikaya-content')) {
            firstContent = firstContent.nextElementSibling;
        }
        if(firstContent) {
            firstContent.classList.add('expanded');
        }
    }
});
</script>
</html>""")
    
    # Write index file
    index_path = os.path.join(output_dir, "index.html")
    with open(index_path, "w", encoding="utf8") as f:
        f.write("\n".join(html))
    
    print(f"✅ Generated enhanced hierarchical index at {index_path}")  

# --------------------------------------------------
# --------------------------------------------------
# Main
# --------------------------------------------------

def main():
    if len(sys.argv) > 1 and sys.argv[-1].startswith('s0'):
      prefix=sys.argv[-1]
      corpus = load_corpus(prefix=prefix)
    elif len(sys.argv) > 1 and sys.argv[-1].startswith('all'):
      prefix=sys.argv[-1]
      corpus = load_corpus(prefix='all')
    else:
      corpus = load_corpus()
    print(corpus)

    # Track intro pages for each nikaya
    intro_pages = {}

    for prefix, files in tqdm.tqdm(corpus.items()):

        if "mul" not in files or "att" not in files:
            continue

        # ~ mul = json.load(open(files["mul"],encoding="utf8"))
        # ~ att = json.load(open(files["att"],encoding="utf8"))
        # Handle multiple mul files
        mul_data = []
        if isinstance(files["mul"], list):
            for mul_file in files["mul"]:
                mul_data.extend(json.load(open(mul_file, encoding="utf8")))
        else:
            mul_data = json.load(open(files["mul"], encoding="utf8"))
        # Use mul_data instead of mul for all subsequent operations
        mul = mul_data
        
        # Handle multiple att files
        att_data = []
        if isinstance(files["att"], list):
            for att_file in files["att"]:
                att_data.extend(json.load(open(att_file, encoding="utf8")))
        else:
            att_data = json.load(open(files["att"], encoding="utf8"))
        
        att = att_data

        att_index = index_para(att)
        blocks = build_blocks(mul)

        # Create intro page for this nikaya if it has leading entries
        intro_info = render_nikaya_intro(prefix, files["att"], corpus)
        if intro_info:
            # Find nikaya name from mul
            nikaya_name = None
            for e in mul:
                if e.get("rend") == "nikaya":
                    nikaya_name = e.get("text")
                    break
            if nikaya_name:
                intro_pages[nikaya_name] = intro_info

        for block in blocks:
            render_sutta_page(prefix, block, att_index, att)
    
    # Generate hierarchical index after all suttas are rendered
    print("\nGenerating hierarchical index...")
    generate_hierarchical_index(OUTPUT_DIR, corpus, intro_pages)
    
    print("\nDone.") 

if __name__ == "__main__":
    main()
