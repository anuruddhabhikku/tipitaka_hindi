#!/usr/bin/env python3
"""
Convert Majjhima Nikaya JSON to EPUB with hidden Roman Pali for dictionary lookup.
Produces two versions:
  - KOReader version: Devanagari visible, Roman hidden
  - Kindle version: Roman visible (for DPD dictionary compatibility)
"""

import json,sys
import os
from datetime import datetime
from ebooklib import epub
from indic_transliteration import sanscript
from indic_transliteration.sanscript import transliterate
import html
import unicodedata

# Configuration
JSON_FILE = "s0201m.mul.json"
KOREADER_EPUB = "epubs/majjhima_nikaya_koreader.epub"
KINDLE_EPUB = "epubs/majjhima_nikaya_kindle.epub"
FONT_REGULAR = "TiroDevaSanskrit-Regular.ttf"
FONT_ITALIC = "TiroDevaSanskrit-Italic.ttf"
AUTHOR = "Buddha's Teachings"
LANGUAGE = "pi"

class PaliConverter:
    """Convert Devanagari Pali to Roman Pali with proper conjunct handling."""
    
    @staticmethod
    def devanagari_to_roman(text):
        """Convert Devanagari text to Roman Pali, stripping any ZWJ."""
        if not text or not isinstance(text, str):
            return text
        
        text = unicodedata.normalize('NFC', text.strip())
        
        try:
            # Remove ZWJ before transliteration
            text = text.replace('\u200D', '')
            
            # Devanagari to IAST
            roman = transliterate(text, sanscript.DEVANAGARI, sanscript.IAST)
            
            # Standardize Pali diacritics
            roman = roman.replace('ṃ', 'ṃ')
            roman = roman.replace('ṅ', 'ṅ')
            roman = roman.replace('ñ', 'ñ')
            roman = roman.replace('ṇ', 'ṇ')
            roman = roman.replace('ṭ', 'ṭ')
            roman = roman.replace('ḍ', 'ḍ')
            roman = roman.replace('ḷ', 'ḷ')
            roman = roman.replace('ṁ', 'ṃ')
            
            return roman
        except Exception as e:
            print(f"Transliteration error: {e}")
            return text
    
    @staticmethod
    def process_pali_text_koreader(text):
        """Process for KOReader: Devanagari visible, Roman hidden."""
        if not text:
            return text
        
        text = unicodedata.normalize('NFC', text)
        
        parts = []
        all_roman = []
        
        i = 0
        length = len(text)
        
        while i < length:
            char = text[i]
            code = ord(char)
            
            if 0x0900 <= code <= 0x097F:
                word_chars = [char]
                i += 1
                
                while i < length:
                    next_char = text[i]
                    next_code = ord(next_char)
                    
                    if (0x0900 <= next_code <= 0x097F or
                        next_code == 0x094D or
                        next_code == 0x200D):
                        word_chars.append(next_char)
                        i += 1
                    else:
                        break
                
                word = ''.join(word_chars)
                display_word = word.replace('\u200D', '')
                
                parts.append(('devanagari', display_word))
                roman_word = PaliConverter.devanagari_to_roman(word)
                all_roman.append(roman_word)
                
            else:
                other_chars = [char]
                i += 1
                
                while i < length:
                    next_char = text[i]
                    next_code = ord(next_char)
                    if not (0x0900 <= next_code <= 0x097F):
                        other_chars.append(next_char)
                        i += 1
                    else:
                        break
                
                other_text = ''.join(other_chars)
                parts.append(('other', other_text))
                
                if other_text.strip() == '':
                    all_roman.append(' ')
        
        # Build HTML
        html_parts = []
        for part_type, content in parts:
            if part_type == 'devanagari':
                html_parts.append(f'<span class="visible-devanagari">{html.escape(content)}</span>')
            else:
                html_parts.append(html.escape(content))
        
        continuous_roman = ''.join(all_roman)
        html_parts.append(f'<span class="hidden-roman-global">{html.escape(continuous_roman)}</span>')
        
        return ''.join(html_parts)
    
    @staticmethod
    def process_pali_text_kindle(text):
        """Process for Kindle: Roman visible (for dictionary lookup)."""
        if not text:
            return text
        
        text = unicodedata.normalize('NFC', text)
        
        roman_parts = []
        
        i = 0
        length = len(text)
        
        while i < length:
            char = text[i]
            code = ord(char)
            
            if 0x0900 <= code <= 0x097F:
                word_chars = [char]
                i += 1
                
                while i < length:
                    next_char = text[i]
                    next_code = ord(next_char)
                    
                    if (0x0900 <= next_code <= 0x097F or
                        next_code == 0x094D or
                        next_code == 0x200D):
                        word_chars.append(next_char)
                        i += 1
                    else:
                        break
                
                word = ''.join(word_chars)
                roman_word = PaliConverter.devanagari_to_roman(word)
                roman_parts.append(roman_word)
                
            else:
                roman_parts.append(char)
                i += 1
        
        return ''.join(roman_parts)

def create_css_koreader():
    """CSS for KOReader version with hidden Roman."""
    return '''\
@font-face {
    font-family: "Tiro Devanagari Sanskrit";
    font-weight: normal;
    font-style: normal;
    src: url("fonts/TiroDevaSanskrit-Regular.ttf");
}

@font-face {
    font-family: "Tiro Devanagari Sanskrit";
    font-weight: normal;
    font-style: italic;
    src: url("fonts/TiroDevaSanskrit-Italic.ttf");
}

body {
    font-family: "Tiro Devanagari Sanskrit", serif;
    line-height: 1.8;
    margin: 5%;
    text-align: left;
    direction: ltr;
    font-size: 1.1em;
    background-color: #fafafa;
    color: #000;
}

h1.nikaya { font-size: 2em; text-align: center; margin: 2em 0 1em; page-break-before: always; font-weight: bold; color: #8B4513; }
h2.book { font-size: 1.8em; text-align: center; margin: 1.5em 0; font-style: italic; color: #2c3e50; }
h2.chapter { font-size: 1.6em; text-align: center; margin: 2em 0 1em; background: #f0f0f0; padding: 0.5em; border-radius: 4px; color: #34495e; }
h3.subhead { font-size: 1.4em; font-weight: bold; text-align: center; margin: 1.5em 0 1em; color: #16a085; border-bottom: 1px solid #16a085; padding-bottom: 0.3em; }

.visible-devanagari {
    display: inline;
    color: #000;
    font-weight: normal;
    font-size: 1em;
}

.hidden-roman-global {
    display: inline !important;
    font-size: 0 !important;
    opacity: 0 !important;
    position: absolute !important;
    left: 0 !important;
    top: 0 !important;
    width: 100% !important;
    height: 100% !important;
    overflow: hidden !important;
    pointer-events: none !important;
    z-index: -1 !important;
    color: transparent !important;
    user-select: text !important;
    -webkit-user-select: text !important;
    white-space: pre-wrap !important;
}

.pali-text { font-weight: bold; margin: 1.2em 0 0.8em; position: relative; }
.pali-line { display: block; margin: 0.3em 0; white-space: pre-wrap; position: relative; }

.hindi-text {
    font-weight: normal;
    color: #2c3e50;
    margin: 0.5em 0 1.2em 1.5em;
    padding: 0.5em 0 0.5em 1.2em;
    border-left: 3px solid #95a5a6;
    font-style: regular;
    line-height: 1.8;
    background: #f9f9f9;
    border-radius: 0 4px 4px 0;
    white-space: pre-wrap;
}

.hindi-text br { display: block; margin: 0.3em 0; }

.gatha-entry {
    margin: 1.5em 0;
    page-break-inside: avoid;
    position: relative;
    font-style: italic;
}

.gatha-text {
    margin: 1em 0;
    padding-left: 2em;
}

.gatha-line {
    display: block;
    margin: 0.2em 0;
    white-space: pre-wrap;
    position: relative;
    font-style: italic;
}
/* Footnote markers */
.footnote-ref {
    font-size: 0.8em;
    vertical-align: super;
    line-height: 1;
    text-decoration: none;
    color: #0066cc;
    margin: 0 0.2em;
}

/* Footnotes section at chapter end */
.footnotes-section {
    margin-top: 3em;
    padding-top: 1em;
    border-top: 1px solid #ccc;
    font-size: 0.9em;
}

.footnotes-section h4 {
    text-align: center;
    margin-bottom: 1em;
    color: #666;
}

.footnote {
    margin: 0.5em 0;
    padding: 0.5em;
    background: #f9f9f9;
    border-left: 3px solid #0066cc;
}

/* Hide footnote content when displayed in popup? Actually KOReader handles this */
.bodytext-entry { margin: 1.5em 0; page-break-inside: avoid; position: relative; }
* { -webkit-font-feature-settings: "locl" off; font-feature-settings: "locl" off; }

/* Mark footnote asides as non-linear fragments */
aside[epub|type="footnote"] {
    -cr-hint: non-linear-combining;
}

/* Hide the footnotes section completely */
.footnotes-section {
    display: none;
}
@media print { .hidden-roman-global { display: none !important; } }
'''

def create_css_kindle():
    """Simplified CSS for Kindle version with Roman text."""
    return '''\
body {
    font-family: serif;
    line-height: 1.6;
    margin: 5%;
    text-align: left;
    font-size: 1.1em;
}

h1.nikaya { font-size: 2em; text-align: center; margin: 2em 0 1em; font-weight: bold; color: #8B4513; }
h2.book { font-size: 1.8em; text-align: center; margin: 1.5em 0; font-style: italic; color: #2c3e50; }
h2.chapter { font-size: 1.6em; text-align: center; margin: 2em 0 1em; background: #f0f0f0; padding: 0.5em; border-radius: 4px; color: #34495e; }
h3.subhead { font-size: 1.4em; font-weight: bold; text-align: center; margin: 1.5em 0 1em; color: #16a085; border-bottom: 1px solid #16a085; padding-bottom: 0.3em; }

.pali-text { margin: 1.2em 0 0.8em; }
.pali-line { display: block; margin: 0.3em 0; }

.hindi-text {
    font-weight: normal;
    color: #2c3e50;
    margin: 0.5em 0 1.2em 1.5em;
    padding: 0.5em 0 0.5em 1.2em;
    border-left: 3px solid #95a5a6;
    font-style: italic;
    line-height: 1.6;
    background: #f9f9f9;
    border-radius: 0 4px 4px 0;
}

.hindi-text br { display: block; margin: 0.3em 0; }
.gatha-entry {
    margin: 1.5em 0;
    page-break-inside: avoid;
}

.gatha-text {
    margin: 1em 0;
    padding-left: 2em;
    font-style: italic;
}

.gatha-line {
    display: block;
    margin: 0.2em 0;
    font-style: italic;
}
/* Footnote markers */
.footnote-ref {
    font-size: 0.8em;
    vertical-align: super;
    line-height: 1;
    text-decoration: none;
    color: #0066cc;
    margin: 0 0.2em;
}

/* Footnotes section at chapter end */
.footnotes-section {
    margin-top: 3em;
    padding-top: 1em;
    border-top: 1px solid #ccc;
    font-size: 0.9em;
}

.footnotes-section h4 {
    text-align: center;
    margin-bottom: 1em;
    color: #666;
}

.footnote {
    margin: 0.5em 0;
    padding: 0.5em;
    background: #f9f9f9;
    border-left: 3px solid #0066cc;
}

/* Hide footnote content when displayed in popup? Actually KOReader handles this */
.bodytext-entry { margin: 1.5em 0; page-break-inside: avoid; }
'''

def process_entry_koreader(entry, converter, footnote_counter=None):
    """Process entry for KOReader version."""
    return _process_entry(entry, converter, for_kindle=False, footnote_counter=footnote_counter)

def process_entry_kindle(entry, converter, footnote_counter=None):
    """Process entry for Kindle version."""
    return _process_entry(entry, converter, for_kindle=True, footnote_counter=footnote_counter)

def _process_entry(entry, converter, for_kindle=False, footnote_counter=None):
    """Common entry processing logic."""
    if footnote_counter is None:
        footnote_counter = [1]  # Use list for mutable counter
    
    rend = entry.get('rend', '')
    pali_text = entry.get('text', '')
    hindi_text = entry.get('hi', '')
    entry_id = entry.get('id', '')
    
    html_parts = []
    footnotes = []  # Collect footnotes for this entry
    
    if entry_id:
        html_parts.append(f'<div id="{html.escape(entry_id)}">')
    
    if rend == 'centre':
        html_parts.append(f'<p class="centre">{html.escape(pali_text)}</p>')
        if hindi_text:
            # Add footnote marker for centre text
            footnote_num = footnote_counter[0]
            footnote_id = f"fn_{footnote_num}"
            footnote_ref = f"fnref_{footnote_num}"
            
            html_parts.append(
                f'<a epub:type="noteref" href="#{footnote_id}" id="{footnote_ref}" '
                f'class="footnote-ref">[{footnote_num}]</a>'
            )
            
            footnotes.append({
                'id': footnote_id,
                'ref': footnote_ref,
                'content': hindi_text.replace('\n', '<br/>'),
                'number': footnote_num
            })
            footnote_counter[0] += 1
    
    elif rend == 'nikaya':
        html_parts.append(f'<h1 class="nikaya">{html.escape(pali_text)}</h1>')
        if hindi_text:
            # Add footnote marker for nikaya title
            footnote_num = footnote_counter[0]
            footnote_id = f"fn_{footnote_num}"
            footnote_ref = f"fnref_{footnote_num}"
            
            html_parts.append(
                f'<a epub:type="noteref" href="#{footnote_id}" id="{footnote_ref}" '
                f'class="footnote-ref">[{footnote_num}]</a>'
            )
            
            footnotes.append({
                'id': footnote_id,
                'ref': footnote_ref,
                'content': hindi_text.replace('\n', '<br/>'),
                'number': footnote_num
            })
            footnote_counter[0] += 1
    
    elif rend == 'book':
        html_parts.append(f'<h2 class="book">{html.escape(pali_text)}</h2>')
        if hindi_text:
            # Add footnote marker for book title
            footnote_num = footnote_counter[0]
            footnote_id = f"fn_{footnote_num}"
            footnote_ref = f"fnref_{footnote_num}"
            
            html_parts.append(
                f'<a epub:type="noteref" href="#{footnote_id}" id="{footnote_ref}" '
                f'class="footnote-ref">[{footnote_num}]</a>'
            )
            
            footnotes.append({
                'id': footnote_id,
                'ref': footnote_ref,
                'content': hindi_text.replace('\n', '<br/>'),
                'number': footnote_num
            })
            footnote_counter[0] += 1
    
    elif rend == 'chapter':
        html_parts.append(f'<h2 class="chapter">{html.escape(pali_text)}</h2>')
        if hindi_text:
            # Add footnote marker for chapter title
            footnote_num = footnote_counter[0]
            footnote_id = f"fn_{footnote_num}"
            footnote_ref = f"fnref_{footnote_num}"
            
            html_parts.append(
                f'<a epub:type="noteref" href="#{footnote_id}" id="{footnote_ref}" '
                f'class="footnote-ref">[{footnote_num}]</a>'
            )
            
            footnotes.append({
                'id': footnote_id,
                'ref': footnote_ref,
                'content': hindi_text.replace('\n', '<br/>'),
                'number': footnote_num
            })
            footnote_counter[0] += 1
    
    elif rend == 'subhead':
        html_parts.append(f'<h3 class="subhead">{html.escape(pali_text)}</h3>')
        if hindi_text:
            # Add footnote marker for subhead
            footnote_num = footnote_counter[0]
            footnote_id = f"fn_{footnote_num}"
            footnote_ref = f"fnref_{footnote_num}"
            
            html_parts.append(
                f'<a epub:type="noteref" href="#{footnote_id}" id="{footnote_ref}" '
                f'class="footnote-ref">[{footnote_num}]</a>'
            )
            
            footnotes.append({
                'id': footnote_id,
                'ref': footnote_ref,
                'content': hindi_text.replace('\n', '<br/>'),
                'number': footnote_num
            })
            footnote_counter[0] += 1
    
    elif rend == 'bodytext':
        html_parts.append('<div class="bodytext-entry">')
        
        # Process Pali text
        lines = pali_text.split('\n')
        html_parts.append('<div class="pali-text">')
        
        for line in lines:
            if not line.strip():
                continue
            html_parts.append('<span class="pali-line">')
            if for_kindle:
                html_parts.append(converter.process_pali_text_kindle(line))
            else:
                html_parts.append(converter.process_pali_text_koreader(line))
            html_parts.append('</span>')
        
        html_parts.append('</div>')
        
        # Add footnote marker if Hindi translation exists
        if hindi_text:
            footnote_num = footnote_counter[0]
            footnote_id = f"fn_{footnote_num}"
            footnote_ref = f"fnref_{footnote_num}"
            
            html_parts.append(
                f'<a epub:type="noteref" href="#{footnote_id}" id="{footnote_ref}" '
                f'class="footnote-ref">[{footnote_num}]</a>'
            )
            
            # Process Hindi text - preserve line breaks
            hindi_paragraphs = [p for p in hindi_text.split('\n') if p.strip()]
            combined_hindi = '<br/>'.join(hindi_paragraphs)
            
            footnotes.append({
                'id': footnote_id,
                'ref': footnote_ref,
                'content': combined_hindi,
                'number': footnote_num
            })
            footnote_counter[0] += 1
        
        html_parts.append('</div>')
    
    elif rend == 'gatha':
        html_parts.append('<div class="gatha-entry">')
        
        # Process Pali verse lines
        lines = pali_text.split('\n')
        html_parts.append('<div class="gatha-text">')
        
        for line in lines:
            if not line.strip():
                continue
            html_parts.append('<span class="gatha-line">')
            if for_kindle:
                html_parts.append(converter.process_pali_text_kindle(line))
            else:
                html_parts.append(converter.process_pali_text_koreader(line))
            html_parts.append('</span>')
        
        html_parts.append('</div>')
        
        # Add footnote marker if Hindi translation exists
        if hindi_text:
            footnote_num = footnote_counter[0]
            footnote_id = f"fn_{footnote_num}"
            footnote_ref = f"fnref_{footnote_num}"
            
            html_parts.append(
                f'<a epub:type="noteref" href="#{footnote_id}" id="{footnote_ref}" '
                f'class="footnote-ref">[{footnote_num}]</a>'
            )
            
            # Process Hindi text - preserve line breaks for verses
            hindi_paragraphs = [p for p in hindi_text.split('\n') if p.strip()]
            combined_hindi = '<br/>'.join(hindi_paragraphs)
            
            footnotes.append({
                'id': footnote_id,
                'ref': footnote_ref,
                'content': combined_hindi,
                'number': footnote_num
            })
            footnote_counter[0] += 1
        
        html_parts.append('</div>')
    
    else:
        # Handle any other rend types
        html_parts.append(f'<p class="{html.escape(rend)}">{html.escape(pali_text)}</p>')
        if hindi_text:
            # Add footnote marker for other text types
            footnote_num = footnote_counter[0]
            footnote_id = f"fn_{footnote_num}"
            footnote_ref = f"fnref_{footnote_num}"
            
            html_parts.append(
                f'<a epub:type="noteref" href="#{footnote_id}" id="{footnote_ref}" '
                f'class="footnote-ref">[{footnote_num}]</a>'
            )
            
            footnotes.append({
                'id': footnote_id,
                'ref': footnote_ref,
                'content': hindi_text.replace('\n', '<br/>'),
                'number': footnote_num
            })
            footnote_counter[0] += 1
    
    if entry_id:
        html_parts.append('</div>')
    
    return '\n'.join(html_parts), footnotes
    
def create_epub(data, epub_filename, css_content, process_func, title_suffix):
    """Create an EPUB file with the given parameters."""
    book = epub.EpubBook()
    # ~ book.set_identifier(f'majjhima_nikaya_{datetime.now().timestamp()}')
    # ~ book.set_title(f'Majjhima Nikaya - Mulapannasa {title_suffix}')
    book.set_identifier(os.path.split(os.path.splitext(epub_filename)[0])[1])
    book.set_title(os.path.split(os.path.splitext(epub_filename)[0])[1])
    book.set_language(LANGUAGE)
    book.add_author(AUTHOR)
    
    # Add CSS
    nav_css = epub.EpubItem(
        uid='style',
        file_name='style.css',
        media_type='text/css',
        content=css_content
    )
    book.add_item(nav_css)
    
    # Add fonts (only for KOReader version that needs Devanagari)
    if 'koreader' in epub_filename:
        if os.path.exists(FONT_REGULAR):
            with open(FONT_REGULAR, 'rb') as f:
                font_item = epub.EpubItem(
                    uid='font_regular',
                    file_name=f'fonts/{FONT_REGULAR}',
                    media_type='application/vnd.ms-opentype',
                    content=f.read()
                )
                book.add_item(font_item)
        
        if os.path.exists(FONT_ITALIC):
            with open(FONT_ITALIC, 'rb') as f:
                font_item = epub.EpubItem(
                    uid='font_italic',
                    file_name=f'fonts/{FONT_ITALIC}',
                    media_type='application/vnd.ms-opentype',
                    content=f.read()
                )
                book.add_item(font_item)
    
    # Initialize converter
    converter = PaliConverter()
    
    # Structure tracking
    books = []
    vaggas = []
    current_book = None
    current_vagga = None
    current_vagga_content = []  # Will store tuples of (html_content, footnotes)
    current_vagga_entries = []  # Store entries for this vagga
    current_suttas = []
    chapters = []
    chapter_index = 0
    current_sutta = None
    current_sutta_subsections = []
    
    for entry in data:
        rend = entry.get('rend', '')
        entry_text = entry.get('text', '')
        entry_id = entry.get('id', '')
        sutta_num = entry.get('n', '')
        
        if rend == 'book':
            # Save previous vagga if exists
            if current_vagga and current_vagga_entries:
                # Process all entries in this vagga with a single footnote counter
                footnote_counter = [1]
                chapter_content = []
                all_footnotes = []
                
                for vagga_entry in current_vagga_entries:
                    content, footnotes = process_func(vagga_entry, converter, footnote_counter)
                    chapter_content.append(content)
                    all_footnotes.extend(footnotes)
                
                # Add footnotes section at end of chapter
                if all_footnotes:
                    chapter_content.append('<div class="footnotes-section">')
                    chapter_content.append('<h4>Hindi Translations</h4>')
                    
                    for fn in all_footnotes:
                        chapter_content.append(
                            f'<aside epub:type="footnote" id="{fn["id"]}" class="footnote">'
                            # ~ f'<a href="#{fn["ref"]}">[{fn["number"]}]</a> '
                            f'{fn["content"]}'
                            f'</aside>'
                        )
                    
                    chapter_content.append('</div>')
                
                filename = f'chap_{chapter_index:04d}.xhtml'
                chap = epub.EpubHtml(
                    title=current_vagga,
                    file_name=filename,
                    lang=LANGUAGE
                )
                chap.content = f'''\
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
<head>
    <title>{html.escape(current_vagga)}</title>
    <link rel="stylesheet" type="text/css" href="style.css"/>
</head>
<body>
    {"".join(chapter_content)}
</body>
</html>'''
                chap.add_item(nav_css)
                book.add_item(chap)
                vaggas.append((current_vagga, filename, current_suttas.copy()))
                chapters.append(chap)
                chapter_index += 1
            
            if current_book:
                books.append((current_book, vaggas.copy()))
            
            current_book = entry_text
            vaggas = []
            current_vagga = None
            current_vagga_entries = []
            current_suttas = []
            current_vagga_entries.append(entry)
        
        elif rend == 'chapter':
            # Save previous vagga if exists
            if current_vagga and current_vagga_entries:
                # Process all entries in this vagga with a single footnote counter
                footnote_counter = [1]
                chapter_content = []
                all_footnotes = []
                
                for vagga_entry in current_vagga_entries:
                    content, footnotes = process_func(vagga_entry, converter, footnote_counter)
                    chapter_content.append(content)
                    all_footnotes.extend(footnotes)
                
                # Add footnotes section at end of chapter
                if all_footnotes:
                    chapter_content.append('<div class="footnotes-section">')
                    chapter_content.append('<h4>Hindi Translations</h4>')
                    
                    for fn in all_footnotes:
                        chapter_content.append(
                            f'<aside epub:type="footnote" id="{fn["id"]}" class="footnote">'
                            # ~ f'<a href="#{fn["ref"]}">[{fn["number"]}]</a> '
                            f'{fn["content"]}'
                            f'</aside>'
                        )
                    
                    chapter_content.append('</div>')
                
                filename = f'chap_{chapter_index:04d}.xhtml'
                chap = epub.EpubHtml(
                    title=current_vagga,
                    file_name=filename,
                    lang=LANGUAGE
                )
                chap.content = f'''\
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
<head>
    <title>{html.escape(current_vagga)}</title>
    <link rel="stylesheet" type="text/css" href="style.css"/>
</head>
<body>
    {"".join(chapter_content)}
</body>
</html>'''
                chap.add_item(nav_css)
                book.add_item(chap)
                vaggas.append((current_vagga, filename, current_suttas.copy()))
                chapters.append(chap)
                chapter_index += 1
            
            current_vagga = entry_text
            current_vagga_entries = [entry]
            current_suttas = []
        
        elif rend == 'subhead':
            entry_text = entry.get('text', '')
            
            # Check if this is a numbered sutta (starts with Devanagari numeral and dot)
            import re
            is_numbered_sutta = bool(re.match(r'^[\u0966-\u096F]+\.', entry_text.strip()))
            
            if not entry_id:
                if is_numbered_sutta:
                    # Extract the number for ID
                    num_match = re.match(r'^([\u0966-\u096F]+)', entry_text.strip())
                    if num_match:
                        entry_id = f'sutta_{num_match.group(1)}'
                    else:
                        entry_id = f'sutta_{chapter_index}_{len(current_suttas)}'
                else:
                    entry_id = f'sutta_{chapter_index}_{len(current_suttas)}_{len(current_sutta_subsections)}'
                entry['id'] = entry_id
            
            if is_numbered_sutta:
                # This is a new main sutta
                if entry_text:
                    clean_title = entry_text.strip()
                    if len(clean_title) > 40:
                        clean_title = clean_title[:40] + "..."
                    sutta_title = clean_title
                
                # Add as flat sutta initially (will be updated when subsections appear)
                current_suttas.append({
                    'title': sutta_title,
                    'anchor': f'#{entry_id}',
                    'subsections': []
                })
                current_sutta_subsections = []  # Reset subsections for new sutta
                
            else:
                # This is a subsection within the current sutta
                if entry_text:
                    subsection_title = entry_text.strip()
                    subsection = (subsection_title, f'#{entry_id}')
                    current_sutta_subsections.append(subsection)
                    
                    # Update the last sutta with its subsections immediately
                    if current_suttas and isinstance(current_suttas[-1], dict):
                        current_suttas[-1]['subsections'] = current_sutta_subsections.copy()
            
            current_vagga_entries.append(entry)
        
        else:
            current_vagga_entries.append(entry)
    
    # Save last vagga
    if current_vagga and current_vagga_entries:
        # Process all entries in this vagga with a single footnote counter
        footnote_counter = [1]
        chapter_content = []
        all_footnotes = []
        
        for vagga_entry in current_vagga_entries:
            content, footnotes = process_func(vagga_entry, converter, footnote_counter)
            chapter_content.append(content)
            all_footnotes.extend(footnotes)
        
        # Add footnotes section at end of chapter
        if all_footnotes:
            chapter_content.append('<div class="footnotes-section">')
            chapter_content.append('<h4>Hindi Translations</h4>')
            
            for fn in all_footnotes:
                chapter_content.append(
                    f'<aside epub:type="footnote" id="{fn["id"]}" class="footnote">'
                    # ~ f'<a href="#{fn["ref"]}">[{fn["number"]}]</a> '
                    f'{fn["content"]}'
                    f'</aside>'
                )
            
            chapter_content.append('</div>')
        
        filename = f'chap_{chapter_index:04d}.xhtml'
        chap = epub.EpubHtml(
            title=current_vagga,
            file_name=filename,
            lang=LANGUAGE
        )
        chap.content = f'''\
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
<head>
    <title>{html.escape(current_vagga)}</title>
    <link rel="stylesheet" type="text/css" href="style.css"/>
</head>
<body>
    {"".join(chapter_content)}
</body>
</html>'''
        chap.add_item(nav_css)
        book.add_item(chap)
        vaggas.append((current_vagga, filename, current_suttas.copy()))
        chapters.append(chap)
        chapter_index += 1
    
    # Save last book
    if current_book:
        books.append((current_book, vaggas.copy()))
    
    # Build TOC (unchanged from original)
    toc = []
    for book_title, book_vaggas in books:
        book_section = epub.Section(book_title)
        book_links = []
        
        for vagga_title, vagga_file, suttas in book_vaggas:
            if suttas:
                sutta_links = []
                for idx, sutta_item in enumerate(suttas):
                    if isinstance(sutta_item, dict) and sutta_item.get('subsections'):
                        sutta_title = sutta_item['title']
                        sutta_anchor = sutta_item['anchor']
                        subsections = sutta_item['subsections']
                        
                        subsection_links = []
                        for sub_idx, (sub_title, sub_anchor) in enumerate(subsections):
                            sub_link = epub.Link(
                                f"{vagga_file}{sub_anchor}",
                                sub_title,
                                f"subsection_{idx}_{sub_idx}"
                            )
                            subsection_links.append(sub_link)
                        
                        sutta_section = epub.Section(sutta_title)
                        sutta_links.append((sutta_section, subsection_links))
                    else:
                        if isinstance(sutta_item, dict):
                            sutta_title = sutta_item['title']
                            sutta_anchor = sutta_item['anchor']
                        else:
                            sutta_title, sutta_anchor = sutta_item
                        
                        sutta_link = epub.Link(
                            f"{vagga_file}{sutta_anchor}",
                            sutta_title,
                            f"sutta_{idx}"
                        )
                        sutta_links.append(sutta_link)
                
                vagga_section = epub.Section(vagga_title)
                book_links.append((vagga_section, sutta_links))
            else:
                vagga_link = epub.Link(
                    vagga_file,
                    vagga_title,
                    vagga_title.replace(' ', '_')
                )
                book_links.append(vagga_link)
        toc.append((book_section, book_links))
    
    book.toc = toc
    book.spine = ['nav'] + chapters
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    
    print(f"Generating {epub_filename}...")
    epub.write_epub(epub_filename, book, {})
    print(f"Done! {epub_filename} saved.")
def main():
    """Main function to create both EPUB versions."""
    
    # Load JSON
    if sys.argv[-1].endswith('.json') and os.path.exists(sys.argv[-1]): 
      JSON_FILE=sys.argv[-1]
      # ~ KOREADER_EPUB = os.path.splitext(JSON_FILE)[0]+'_koreader.epub'
      # ~ KOREADER_EPUB = 'epubs/'+os.path.splitext(JSON_FILE)[0]+'_koreader.epub'
      KOREADER_EPUB = 'epubs/'+os.path.splitext(JSON_FILE)[0]+'.epub'
      KINDLE_EPUB = os.path.splitext(JSON_FILE)[0]+'_kindle.epub'
    print(f"Loading JSON file: {JSON_FILE}")
    try:
        with open(JSON_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"Error: {JSON_FILE} not found!")
        return
    except json.JSONDecodeError as e:
        print(f"Error parsing JSON: {e}")
        return
    
    print(f"Loaded {len(data)} entries")
    
    # Create KOReader version (Devanagari visible, Roman hidden)
    create_epub(
        data=data,
        epub_filename=KOREADER_EPUB,
        css_content=create_css_koreader(),
        process_func=process_entry_koreader,
        title_suffix="(KOReader with Dictionary Support)"
    )
    
    # Create Kindle version (Roman visible)
    # ~ create_epub(
        # ~ data=data,
        # ~ epub_filename=KINDLE_EPUB,
        # ~ css_content=create_css_kindle(),
        # ~ process_func=process_entry_kindle,
        # ~ title_suffix="(Kindle Edition with DPD Dictionary Support)"
    # ~ )
    
    print("\n" + "="*50)
    print("Both EPUBs generated successfully!")
    print("="*50)
    print(f"KOReader version: {KOREADER_EPUB}")
    print("  - Devanagari visible, Roman hidden")
    print("  - For use with KOReader")
    print(f"Kindle version: {KINDLE_EPUB}")
    print("  - Roman Pali visible")
    print("  - Compatible with DPD Kindle dictionary")
    print("="*50)

if __name__ == "__main__":
    main()
