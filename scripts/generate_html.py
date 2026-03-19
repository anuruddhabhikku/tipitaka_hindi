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
            if f.startswith(prefix) and (f.endswith(".mul.json") or f.endswith("m.nrf.json") or f.endswith(".att.json") or f.endswith("m.mul.json")):
                files.append(f)
        else:
            # Match both sutta and vinaya patterns
            if re.match(r"^(s\d+|vin\d+).*\.(mul|nrf|att)\.json$", f):
                files.append(f)
    return sorted(files)

def load_corpus(prefix=None):
    """Group files by prefix, optionally filtered by prefix"""
    corpus = defaultdict(dict)
    
    if prefix=='all':
        files = []
        # Include both sutta and vinaya prefixes
        for prefix0 in ['s01','s02','s03','s04','s05', 'vin01', 'vin02']:
        # ~ for prefix0 in [ 's02','s05',]:
            files0 = get_sutta_files(prefix0)
            files.extend(files0)
    else:
        files = get_sutta_files(prefix)
    
    for f in files:
        base = f.split('.')[0]  # vin01a, vin01m, vin02a1, etc.
        
        # Determine the group based on file pattern
        if base.startswith('vin'):
            # For vinaya files, group by the main number (vin01, vin02)
            match = re.match(r'(vin\d{2})', base)
            if match:
                group = match.group(1)
            else:
                group = base
        else:
            # For sutta files, extract the core sutta identifier
            match = re.match(r'(s\d{2}\d+)', base)
            group = match.group(1) if match else base
        
        # Now group mul and att files together
        if f.endswith("mul.json") or f.endswith("m.nrf.json") or f.endswith("m.mul.json"):
            if "mul" not in corpus[group]:
                corpus[group]["mul"] = []
            corpus[group]["mul"].append(f)
        elif f.endswith("att.json"):
            if "att" not in corpus[group]:
                corpus[group]["att"] = []
            corpus[group]["att"].append(f)
    
    return corpus
# --------------------------------------------------
# Commentary index
# --------------------------------------------------

def index_para(entries):
    """Create index and also return ordered list for sequential matching"""
    idx = defaultdict(list)
    leading_entries = []
    found_first_number = False
    
    # Store original order for sequential processing
    ordered_entries = entries.copy()
    
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
    
    # Return both index and ordered list
    return {
        'index': idx,
        'ordered': ordered_entries,
        'usage_counter': defaultdict(int)  # Track how many times each para number has been used
    }
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
    
        // Keyboard shortcut: Ctrl+H
document.addEventListener('keydown', function(e) {{
    if (e.ctrlKey && e.key === 'h') {{
        e.preventDefault(); // Prevent browser's find bar
        
        // Move commentary icons outside .pali
        document.querySelectorAll('.pali span[onclick*="toggleCommentary"]').forEach(icon => {{
            let paliDiv = icon.closest('.pali');
            if (paliDiv) {{
                let clone = icon.cloneNode(true);
                paliDiv.parentNode.insertBefore(clone, paliDiv.nextSibling);
                icon.remove();
            }}
        }});
        
        // Click all main text Hindi icons
        document.querySelectorAll('.pali > span[onclick*="toggleHindi"]').forEach(icon => icon.click());
        
        // Hide Pali text but keep container
        document.querySelectorAll('.pali').forEach(el => {{
            Array.from(el.childNodes).forEach(node => {{
                if (node.nodeType === Node.TEXT_NODE) {{
                    node.textContent = '';
                }} else if (node.nodeType === Node.ELEMENT_NODE && 
                           !node.classList.contains('hindi') && 
                           !node.tagName.match(/span/i)) {{
                    node.style.display = 'none';
                }}
            }});
        }});
        
        // Also check the toggle checkbox
        const toggle = document.getElementById('hindiOnlyToggle');
        if (toggle) {{
            toggle.checked = true;
            localStorage.setItem('hindiOnlyMode', 'true');
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


// NEW: Middle click on pali text toggles Hindi translation
document.addEventListener('auxclick', function(e) {{
    // Check for middle button (button === 1)
    if (e.button === 1) {{
        // Find the closest pali div
        const paliDiv = e.target.closest('.pali');
        if (paliDiv) {{
            e.preventDefault(); // Prevent default middle-click behavior
            const toggleIcon = paliDiv.querySelector('span[onclick*="toggleHindi"]');
            if (toggleIcon && toggleIcon.onclick) {{
                toggleIcon.onclick(e);
            }}
        }}
    }}
}});

// Prevent default middle-click scrolling
document.addEventListener('mousedown', function(e) {{
    if (e.button === 1) {{
        e.preventDefault();
        return false;
    }}
}});


// Double finger tap on Android/tablets toggles Hindi translation
let touchTimer = null;
let touchCount = 0;

document.addEventListener('touchstart', function(e) {{
    // Check for two-finger touch
    if (e.touches.length === 2) {{
        e.preventDefault(); // Prevent zoom/context menu
        
        // Find the pali div under either touch point
        const touch = e.touches[0];
        const element = document.elementFromPoint(touch.clientX, touch.clientY);
        const paliDiv = element?.closest('.pali');
        
        if (paliDiv) {{
            const toggleIcon = paliDiv.querySelector('span[onclick*="toggleHindi"]');
            if (toggleIcon && toggleIcon.onclick) {{
                toggleIcon.onclick(e);
            }}
        }}
    }}
}}, {{ passive: false }});
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

def merge_gatha_parts(entries):
    """Merge sequences of gatha1, gatha2, ... gathalast into single gatha entries"""
    merged = []
    i = 0
    gatha_counter = 0
    while i < len(entries):
        entry = entries[i]
        rend = entry.get("rend", "")
        
        # Check if this is the start of a gatha sequence
        if rend and rend.startswith("gatha") and rend != "gatha":
            # Start collecting gatha parts
            gatha_parts = []
            gatha_hindi_parts = []
            first_id = entry.get("id", "")
            current_verse_number = entry.get("n")  # Get verse number from first part
            
            # Collect ALL consecutive gatha-prefixed entries
            while i < len(entries):
                current = entries[i]
                current_rend = current.get("rend", "")
                
                if not current_rend or not current_rend.startswith("gatha"):
                    break
                
                if current.get("text"):
                    gatha_parts.append(current.get("text", ""))
                if current.get("hi"):
                    gatha_hindi_parts.append(current.get("hi", ""))
                
                i += 1
            
            # Create merged gatha entry with UNIQUE ID
            if gatha_parts:
                gatha_counter += 1
                # Use verse number if available, otherwise use counter
                if current_verse_number:
                    unique_id = f"{first_id.split('_')[0]}_gatha_v{current_verse_number}"
                else:
                    unique_id = f"{first_id.split('_')[0]}_gatha_{gatha_counter}"
                
                merged_entry = {
                    "id": unique_id,
                    "tag": "p",
                    "n": current_verse_number,
                    "rend": "gatha",
                    "text": "\\n".join(gatha_parts),
                    "hi": " ".join(gatha_hindi_parts) if gatha_hindi_parts else ""
                }
                merged.append(merged_entry)
        else:
            # Keep non-gatha-sequence entries as is
            merged.append(entry)
            i += 1
    
    return merged
def format_gatha_text(text):
    """Convert literal \n to line breaks and format for HTML"""
    if not text:
        return text
    
    # Replace literal '\n' with HTML line breaks
    lines = text.split('\\n')
    wrapped_lines = []
    
    for line in lines:
        if line.strip():
            wrapped_lines.append(wrap_pali_words(line))
    
    return '<br>'.join(wrapped_lines)
# --------------------------------------------------
# Render Sutta Page
# --------------------------------------------------
def render_sutta_page(prefix, block, att_index_data, att):
    html = []
    used_words = set()
    sutta_title = None
    current_verse_number = None  # Add this to track verse numbers

    # Extract components from att_index_data
    att_index = att_index_data['index']
    att_ordered = att_index_data['ordered']
    usage_counter = att_index_data['usage_counter']

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
        content_rends = ["bodytext", "gatha", "subhead", "verse", "prose","hangnum"]
        
        # SPECIAL HANDLING FOR HANGNUM - do this FIRST
        if e.get("rend") == "hangnum":
            verse_text = e.get('text', '')
            html.append(f"""
            <div class="verse-number">{verse_text}</div>
            """)
            # Store the verse number for the next gatha
            if e.get("n"):
                current_verse_number = e.get("n")
            continue  # Skip to next entry
        
        if e.get("rend") in content_rends:
            para_id = e.get("id", "para")
            pali_raw = e.get("text","")
            rend = e.get("rend", "")
            hindi_text = e.get("hi", "")  # Make sure this is captured
            
            # Add a class based on rend type
            extra_class = ""
            if rend == "gatha":
                extra_class = " gatha"
            elif rend == "subhead":
                extra_class = " subhead"
            
            # Extract words for dictionary - handle literal \n properly
            text_for_words = pali_raw.replace('\\n', ' ')
            for w in text_for_words.split():
                used_words.add(normalize_word(w))
            
            # Format display text based on rend type
            if "gatha" in rend:
                pali_text = format_gatha_text(pali_raw)
            else:
                pali_text = wrap_pali_words(pali_raw)
            hindi_text = e.get("hi","")

            html.append(f"""
            <div class="pali{extra_class}">
                
            """)

            # Check if this paragraph has commentary - UPDATED WITH SEQUENTIAL LOGIC
            para_num = None
            has_commentary = False
            commentary_entries = []
            
            # For gathas, use the stored verse number
            if rend == "gatha" and current_verse_number is not None:
                try:
                    para_num = int(current_verse_number)
                    if para_num and para_num in att_index:
                        all_entries_for_num = att_index[para_num]
                        if all_entries_for_num:
                            current_usage = usage_counter[para_num]
                            if current_usage < len(all_entries_for_num):
                                current_entry = all_entries_for_num[current_usage]
                                commentary_entries = [current_entry]
                                has_commentary = True
                                usage_counter[para_num] += 1
                except:
                    pass
            # For regular entries, use their own n value
            elif e.get("n"):
                try:
                    para_num = int(e["n"])
                    if para_num and para_num in att_index:
                        all_entries_for_num = att_index[para_num]
                        if all_entries_for_num:
                            current_usage = usage_counter[para_num]
                            if current_usage < len(all_entries_for_num):
                                current_entry = all_entries_for_num[current_usage]
                                commentary_entries = [current_entry]
                                has_commentary = True
                                usage_counter[para_num] += 1
                except:
                    pass
            
            # Reset current_verse_number after using it? 
            # Only reset if we want one verse number per gatha
            if rend == "gatha":
                current_verse_number = None

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
            </div>  <!-- close pali div -->
            """)
            
            # Hindi translation for Mula (hidden by default)
            if hindi_text:
                html.append(f"""
            <div class="hindi" id="{para_id}_hi">
                {hindi_text}
            </div>
            """)
            
            # Commentary section - UPDATED TO USE att_ordered
            if has_commentary and commentary_entries:
                # Find this specific entry in the ordered list
                target_id = commentary_entries[0].get('id')
                start_idx = -1
                
                for i, att_entry in enumerate(att_ordered):
                    if att_entry.get('id') == target_id:
                        start_idx = i
                        break
                
                if start_idx >= 0:
                    html.append(f"""
            <div class="commentary" id="{para_id}_comm" style="display:none;">
                    """)
                    
                    # Render all commentary entries from start_idx until n changes
                    for j in range(start_idx, len(att_ordered)):
                        att_entry = att_ordered[j]
                        current_n = att_entry.get('n')
                        
                        # Check if this entry matches current paragraph
                        matches_current_para = False
                        if current_n is not None:
                            if '-' in str(current_n):
                                # Handle range entries like "301-302"
                                try:
                                    parts = str(current_n).split('-')
                                    start = int(parts[0])
                                    end = int(parts[1])
                                    if start <= para_num <= end:
                                        matches_current_para = True
                                except:
                                    pass
                            elif str(current_n) == str(para_num):
                                matches_current_para = True
                        
                        # Stop if we hit an entry with a different non-null n that doesn't match
                        if current_n is not None and not matches_current_para:
                            break
                        
                        # Skip leading entries entirely
                        if att_entry in att_index.get('leading', []):
                            continue
                        
                        att_text = att_entry.get("text","")
                        att_hindi = att_entry.get("hi","")
                        # ~ att_id = att_entry.get("id", f"commentary_{prefix}_{para_num}_{j}")
                        
                        # Replace with this:
                        original_id = att_entry.get("id", f"commentary_{prefix}_{para_num}_{j}")
                        # Make ID unique by appending paragraph number if it's a range commentary
                        if '-' in str(att_entry.get("n", "")):
                            unique_att_id = f"{original_id}_p{para_num}"
                        else:
                            unique_att_id = original_id
                        
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
                                  onclick="toggleHindi('{unique_att_id}_hi', event)">📖</span>
                        </div>
                        """)
                        
                        if att_hindi:
                            html.append(f"""
                        <div class="hindi" id="{unique_att_id}_hi">
                            {att_hindi}
                        </div>
                        """)
                    
                    html.append("</div>")  # Close commentary div
            
            html.append("</div>")  # Close the inner pali div
            html.append("</div>")  # Close the outer pali{extra_class} div
            html.append("</div>")  # Close para div

    # Build local dictionary subset - COMPACT, NO REDUNDANT HEADWORD
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
    
    # Structure for both pitakas
    structure = {
        "sutta": {},  # For Sutta Pitaka (nikayas)
        "vinaya": {}  # For Vinaya Pitaka
    }
    
    # Track processed groups to avoid duplicates
    processed_groups = set()
    
    for prefix, files in sorted(corpus.items()):
        if "mul" not in files:
            continue
            
        # Skip if we've already processed this group
        if prefix in processed_groups:
            continue
        processed_groups.add(prefix)
        
        # Handle multiple mul files
        mul_data = []
        if isinstance(files["mul"], list):
            for mul_file in sorted(files["mul"]):  # Sort to ensure consistent order
                with open(mul_file, "r", encoding="utf8") as f:
                    mul_data.extend(json.load(f))
        else:
            with open(files["mul"], "r", encoding="utf8") as f:
                mul_data = json.load(f)
        
        # Determine if this is Vinaya or Sutta
        is_vinaya = prefix.startswith('vin')
        
        if is_vinaya:
            # VINAYA STRUCTURE
            current_pitaka = "विनयपिटके"
            current_division = None
            current_chapter = None
            current_item = None
            
            # Initialize Vinaya structure if needed
            if current_pitaka not in structure["vinaya"]:
                structure["vinaya"][current_pitaka] = {}
            
            for e in mul_data:
                rend = e.get("rend")
                text = e.get("text", "")
                
                if rend == "book" or rend == "vagga":
                    # Major division (like पाराजिकपाळि, पाचित्तियपाळि)
                    current_division = text
                    if current_division not in structure["vinaya"][current_pitaka]:
                        structure["vinaya"][current_pitaka][current_division] = []
                    print(f"Added Vinaya division: {current_division}")
                
                elif rend == "chapter":
                    # Chapter within a division
                    current_chapter = {
                        "title": text,
                        "hi": e.get("hi", ""),
                        "file": os.path.join(prefix, e.get("id", "chapter") + ".html"),
                        "id": e.get("id"),
                        "subsections": []
                    }
                    if current_division:
                        structure["vinaya"][current_pitaka][current_division].append(current_chapter)
                    current_item = current_chapter
                
                elif rend == "subhead" and current_item:
                    # Subsection within a chapter
                    current_item["subsections"].append({
                        "title": text,
                        "hi": e.get("hi", ""),
                        "id": e.get("id")
                    })
        
        else:
            # SUTTA STRUCTURE (existing code, preserved exactly)
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
                    if current_nikaya not in structure["sutta"]:
                        structure["sutta"][current_nikaya] = {}
                
                elif rend in ["book", "vagga", "nipata", "samyutta"]:
                    current_vagga = text
                    if current_nikaya and current_vagga not in structure["sutta"][current_nikaya]:
                        structure["sutta"][current_nikaya][current_vagga] = []
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
                        structure["sutta"][current_nikaya][current_vagga].append(current_sutta)
                
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
    <title>Tipitaka - Index</title>
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
        .pitaka {
            margin-bottom: 30px;
        }
        .pitaka h2 {
            color: #8B4513;
            padding: 10px;
            background: #f0f0f0;
            border-radius: 5px;
            cursor: pointer;
            border-left: 5px solid #8B4513;
        }
        .pitaka h2:before {
            content: "▶ ";
            font-size: 0.9em;
            color: #8B4513;
            display: inline-block;
            transition: transform 0.2s;
        }
        .pitaka h2.expanded:before {
            content: "▼ ";
        }
        .pitaka-content {
            display: none;
            margin-top: 15px;
        }
        .pitaka-content.expanded {
            display: block;
        }
        .nikaya, .vinaya-division {
            background: white;
            padding: 15px;
            margin-bottom: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }
        .nikaya h3, .vinaya-division h3 {
            color: #8B4513;
            margin: 0;
            padding: 12px;
            cursor: pointer;
            border-left: 5px solid #8B4513;
            background: #f9f9f9;
            border-radius: 5px;
            transition: background 0.2s;
            font-size: 1.2em;
        }
        .nikaya h3:hover, .vinaya-division h3:hover {
            background: #f0f0f0;
        }
        .nikaya h3:before, .vinaya-division h3:before {
            content: "▶ ";
            font-size: 0.9em;
            color: #8B4513;
            display: inline-block;
            transition: transform 0.2s;
        }
        .nikaya h3.expanded:before, .vinaya-division h3.expanded:before {
            content: "▼ ";
        }
        .nikaya-content, .division-content {
            display: none;
            margin-top: 15px;
        }
        .nikaya-content.expanded, .division-content.expanded {
            display: block;
        }
        .intro-section {
            margin: 10px 0 15px 20px;
            padding: 10px 15px;
            background: #f5f5f5;
            border-left: 3px solid #8B4513;
            border-radius: 0 5px 5px 0;
        }
        .intro-section a {
            color: #8B4513;
            text-decoration: none;
            font-weight: 500;
            font-size: 1.1em;
        }
        .intro-section a:hover {
            text-decoration: underline;
        }
        .vagga, .chapter-section {
            margin: 15px 0 10px 15px;
        }
        .vagga h4, .chapter-section h4 {
            color: #666;
            margin: 10px 0 8px 0;
            padding: 8px;
            cursor: pointer;
            border-bottom: 1px solid #eee;
            transition: background 0.2s;
            font-size: 1.1em;
        }
        .vagga h4:hover, .chapter-section h4:hover {
            background: #f5f5f5;
        }
        .vagga h4:before, .chapter-section h4:before {
            content: "▶ ";
            font-size: 0.8em;
            color: #999;
            display: inline-block;
            transition: transform 0.2s;
        }
        .vagga h4.expanded:before, .chapter-section h4.expanded:before {
            content: "▼ ";
        }
        .vagga-content, .chapter-content {
            display: none;
            margin-left: 20px;
        }
        .vagga-content.expanded, .chapter-content.expanded {
            display: block;
        }
        .sutta, .chapter-item {
            margin: 8px 0 8px 20px;
        }
        .sutta-header, .chapter-header {
            padding: 5px 10px;
            cursor: pointer;
            border-radius: 4px;
            transition: background 0.2s;
            display: flex;
            align-items: baseline;
            flex-wrap: wrap;
        }
        .sutta-header:hover, .chapter-header:hover {
            background: #f5f5f5;
        }
        .sutta-header:before, .chapter-header:before {
            content: "▶ ";
            font-size: 0.8em;
            color: #999;
            display: inline-block;
            transition: transform 0.2s;
            margin-right: 5px;
        }
        .sutta-header.expanded:before, .chapter-header.expanded:before {
            content: "▼ ";
        }
        .sutta-title, .chapter-title {
            color: #0066cc;
            text-decoration: none;
            font-weight: 500;
        }
        .sutta-title:hover, .chapter-title:hover {
            text-decoration: underline;
        }
        .sutta-hi, .chapter-hi {
            color: #666;
            font-size: 0.9em;
            margin-left: 10px;
        }
        .sutta-content, .chapter-content-inner {
            display: none;
            margin-left: 25px;
            padding-left: 15px;
            border-left: 2px dotted #ddd;
        }
        .sutta-content.expanded, .chapter-content-inner.expanded {
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
    <h1>📚 तिपिटक - Index</h1>
    <p class="note">सुत्त पिटक एवं विनय पिटक</p>
""")
    
    # First, render Vinaya Pitaka if it exists
    if structure["vinaya"]:
        html.append('<div class="pitaka">')
        html.append('<h2>📖 विनय पिटक</h2>')
        html.append('<div class="pitaka-content">')
        
        for pitaka_name, divisions in structure["vinaya"].items():
            for division_name, chapters in divisions.items():
                html.append(f'<div class="vinaya-division">')
                html.append(f'<h3>{division_name}</h3>')
                html.append(f'<div class="division-content">')
                
                for chapter in chapters:
                    html.append('<div class="chapter-section">')
                    html.append(f'<h4>{chapter["title"]}</h4>')
                    html.append('<div class="chapter-content">')
                    
                    html.append('<div class="chapter-item">')
                    html.append(f'<div class="chapter-header">')
                    html.append(f'<a class="chapter-title" href="{chapter["file"]}">{chapter["title"]}</a>')
                    if chapter.get("hi"):
                        html.append(f'<span class="chapter-hi">{chapter["hi"]}</span>')
                    html.append('</div>')
                    
                    if chapter.get("subsections"):
                        html.append('<div class="chapter-content-inner">')
                        html.append('<ul class="subsection-list">')
                        for sub in chapter["subsections"]:
                            html.append('<li class="subsection-item">')
                            subsection_link = f'{chapter["file"]}#{sub["id"]}'
                            html.append(f'<a class="subsection-link" href="{subsection_link}">{sub["title"]}</a>')
                            if sub.get("hi"):
                                html.append(f'<span class="subsection-hi"> – {sub["hi"]}</span>')
                            html.append('</li>')
                        html.append('</ul>')
                        html.append('</div>')
                    
                    html.append('</div>')  # Close chapter-item
                    html.append('</div>')  # Close chapter-content
                    html.append('</div>')  # Close chapter-section
                
                html.append('</div>')  # Close division-content
                html.append('</div>')  # Close vinaya-division
        
        html.append('</div>')  # Close pitaka-content
        html.append('</div>')  # Close pitaka
    
    # Then render Sutta Pitaka (existing code, preserved)
    if structure["sutta"]:
        html.append('<div class="pitaka">')
        html.append('<h2>📖 सुत्त पिटक</h2>')
        html.append('<div class="pitaka-content">')
        
        # Sort nikayas in traditional order
        nikaya_order = ["दीघनिकायो", "मज्झिमनिकायो", "संयुत्तनिकायो", "अङ्गुत्तरनिकायो", "खुद्दकनिकायो"]
        nikaya_display = NIKAYA_MAP
        
        for nikaya in nikaya_order:
            if nikaya not in structure["sutta"]:
                continue
                
            display_name = nikaya_display.get(nikaya, nikaya)
            html.append(f'<div class="nikaya">')
            html.append(f'<h3>{display_name}</h3>')
            html.append(f'<div class="nikaya-content">')
            
            # Add intro link if this nikaya has an intro page
            intro_file = intro_pages.get(nikaya, {}).get("file")
            if intro_file:
                html.append(f"""
            <div class="intro-section">
                <a href="{intro_file}">📖 परिचय (Introduction)</a>
                <span class="intro-hi">{nikaya}</span>
            </div>
                """)
            
            vaggas = structure["sutta"][nikaya]
            for vagga, suttas in vaggas.items():
                html.append(f'<div class="vagga">')
                html.append(f'<h4>{vagga}</h4>')
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
        
        html.append('</div>')  # Close pitaka-content
        html.append('</div>')  # Close pitaka
    
    html.append("""
</body>
<script>
document.addEventListener('DOMContentLoaded', function() {
    // Toggle Pitaka
    document.querySelectorAll('.pitaka h2').forEach(function(header) {
        header.addEventListener('click', function(e) {
            e.stopPropagation();
            this.classList.toggle('expanded');
            var content = this.nextElementSibling;
            while(content && !content.classList.contains('pitaka-content')) {
                content = content.nextElementSibling;
            }
            if(content) {
                content.classList.toggle('expanded');
            }
        });
    });
    
    // Toggle Nikaya/Vinaya Division
    document.querySelectorAll('.nikaya h3, .vinaya-division h3').forEach(function(header) {
        header.addEventListener('click', function(e) {
            e.stopPropagation();
            this.classList.toggle('expanded');
            var content = this.nextElementSibling;
            while(content && !content.classList.contains('nikaya-content') && !content.classList.contains('division-content')) {
                content = content.nextElementSibling;
            }
            if(content) {
                content.classList.toggle('expanded');
            }
        });
    });
    
    // Toggle Vagga/Chapter Section
    document.querySelectorAll('.vagga h4, .chapter-section h4').forEach(function(header) {
        header.addEventListener('click', function(e) {
            e.stopPropagation();
            this.classList.toggle('expanded');
            var content = this.nextElementSibling;
            while(content && !content.classList.contains('vagga-content') && !content.classList.contains('chapter-content')) {
                content = content.nextElementSibling;
            }
            if(content) {
                content.classList.toggle('expanded');
            }
        });
    });
    
    // Toggle Sutta/Chapter Item
    document.querySelectorAll('.sutta-header, .chapter-header').forEach(function(header) {
        header.addEventListener('click', function(e) {
            e.stopPropagation();
            this.classList.toggle('expanded');
            var content = this.nextElementSibling;
            while(content && !content.classList.contains('sutta-content') && !content.classList.contains('chapter-content-inner')) {
                content = content.nextElementSibling;
            }
            if(content) {
                content.classList.toggle('expanded');
            }
        });
    });
    
    // Expand first pitaka by default
    var firstPitaka = document.querySelector('.pitaka h2');
    if(firstPitaka) {
        firstPitaka.classList.add('expanded');
        var firstContent = firstPitaka.nextElementSibling;
        while(firstContent && !firstContent.classList.contains('pitaka-content')) {
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

    # In main() function, find this section:
    for prefix, files in tqdm.tqdm(corpus.items()):
        if "mul" not in files or "att" not in files:
            continue
    
        # Handle multiple mul files
        mul_data = []
        if isinstance(files["mul"], list):
            for mul_file in files["mul"]:
                mul_data.extend(json.load(open(mul_file, encoding="utf8")))
        else:
            mul_data = json.load(open(files["mul"], encoding="utf8"))
        
        # Handle multiple att files
        att_data = []
        if isinstance(files["att"], list):
            for att_file in files["att"]:
                att_data.extend(json.load(open(att_file, encoding="utf8")))
        else:
            att_data = json.load(open(files["att"], encoding="utf8"))
        
        # Merge gatha parts
        mul_data = merge_gatha_parts(mul_data)
        att_data = merge_gatha_parts(att_data)
        
        mul = mul_data
        att = att_data
    
        # REPLACE THIS LINE:
        # att_index = index_para(att)
        
        # WITH THIS:
        att_index_data = index_para(att)  # Returns dict with index, ordered, usage_counter
        att_index = att_index_data['index']  # Keep for backward compatibility if needed elsewhere
    
        blocks = build_blocks(mul)
    
        # Create intro page
        intro_info = render_nikaya_intro(prefix, files["att"], corpus)
        if intro_info:
            nikaya_name = None
            for e in mul:
                if e.get("rend") == "nikaya":
                    nikaya_name = e.get("text")
                    break
            if nikaya_name:
                intro_pages[nikaya_name] = intro_info
    
        # UPDATE THIS FUNCTION CALL to pass att_index_data instead of just att_index
        for block in blocks:
            render_sutta_page(prefix, block, att_index_data, att)  # Pass the full data structure
    
    # Generate hierarchical index after all suttas are rendered
    print("\nGenerating hierarchical index...")
    generate_hierarchical_index(OUTPUT_DIR, corpus, intro_pages)
    
    print("\nDone.") 

if __name__ == "__main__":
    main()
