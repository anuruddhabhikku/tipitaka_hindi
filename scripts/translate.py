#!/usr/bin/python3
import json,os
import time
import requests
import lxml.html as lh
import argparse
import random
from tqdm import tqdm
from lxml import etree
import json
import sys
from pathlib import Path
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

TARGET_TAGS = {"p", "head", "l"}  # extend if needed

API_URL = "https://dharmamitra.org/bff/api/translation"
HEADERS = {
    "accept": "*/*",
    "content-type": "application/json",
    "origin": "https://dharmamitra.org",
    "referer": "https://dharmamitra.org/?target_lang=hindi",
}
COOKIES = {}  # fill if needed
MAX_RETRIES = 5
BACKOFF_BASE = 2

highlight_red='\x1b[40m\x1b[31m\x1b[1m'
highlight_reset='\x1b[49m\x1b[39m\x1b[0m'

class FreeProxyException(Exception):
    '''Exception class with message as a required parameter'''
    def __init__(self, message) -> None:
        self.message = message
        super().__init__(self.message)

class FreeProxy:
    '''
    FreeProxy class scrapes proxies from <https://www.sslproxies.org/>,
    <https://www.us-proxy.org/>, <https://free-proxy-list.net/uk-proxy.html>,
    and <https://free-proxy-list.net> and checks if proxy is working. 
    There is possibility to filter proxies by country and acceptable timeout. 
    You can also randomize list of proxies from where script would get first 
    working proxy.
    '''

    def __init__(self, country_id=None, timeout=0.5, rand=False, anonym=False, elite=False, google=None, https=False, url='https://www.google.com'):
        self.country_id = country_id
        self.timeout = timeout
        self.random = rand
        self.anonym = anonym
        self.elite = elite
        self.google = google
        self.schema = 'https' if https else 'http'
        self.url = url

    def get_proxy_list(self, repeat):
        try:
            page = requests.get(self.__website(repeat))
            doc = lh.fromstring(page.content)
        except requests.exceptions.RequestException as e:
            raise FreeProxyException(
                f'Request to {self.__website(repeat)} failed') from e
        # ~ print('got page in scrape')
        try:
            tr_elements = doc.xpath('//*[@id="list"]//tr')
            # ~ print('tr_elem had elems: '+str(len(tr_elements)))
            return [f'{tr_elements[i][0].text_content()}:{tr_elements[i][1].text_content()}'
                    for i in range(1, len(tr_elements)) if self.__criteria(tr_elements[i])]
        except Exception as e:
            raise FreeProxyException('Failed to get list of proxies') from e

    def __website(self, repeat):
        if repeat:
            return "https://free-proxy-list.net"
        elif self.country_id == ['US']:
            return 'https://www.us-proxy.org'
        elif self.country_id == ['GB']:
            return 'https://free-proxy-list.net/uk-proxy.html'
        else:
            return 'https://www.sslproxies.org'

    def __criteria(self, row_elements):
        country_criteria = True if not self.country_id else row_elements[2].text_content(
        ) in self.country_id
        elite_criteria = True if not self.elite else 'elite' in row_elements[4].text_content(
        )
        anonym_criteria = True if (
            not self.anonym) or self.elite else 'anonymous' == row_elements[4].text_content()
        switch = {'yes': True, 'no': False}
        google_criteria = True if self.google is None else self.google == switch.get(
            row_elements[5].text_content())
        https_criteria = True if self.schema == 'http' else row_elements[6].text_content(
        ).lower() == 'yes'
        return country_criteria and elite_criteria and anonym_criteria and google_criteria and https_criteria

    def get(self, repeat=False,pbar=''):
        '''Returns a working proxy that matches the specified parameters.'''
        if pbar:
          info_msg='trying to scrape proxy list'
          pbar.set_description(info_msg);
          # ~ print(info_msg);
          pbar.refresh()
    
        proxy_list = self.get_proxy_list(repeat)
        # ~ print('pre: ',proxy_list)
        # ~ print('proxy list '+str(len(proxy_list)))
        init_size=len(proxy_list)
        existing=[];bad=[];
        if os.path.exists('.proxies'):
          existing=[i.strip().split('//')[1].strip() for i in open('.proxies').readlines() if i.strip() and ':' in i]      
        if os.path.exists('.bad'):
          bad=[i.strip().split('//')[1].strip() for i in open('.bad').readlines() if i.strip() and ':' in i]      
        # ~ print('bad: ',bad)
        # ~ print('exisint: ',bad)

        # ~ proxy_set=set(proxy_list)-set(bad)
        # ~ proxy_set=proxy_set-set(existing)
        # ~ proxy_list=list(proxy_list);
        # ~ proxy_list.sort();
        proxy_list=[i for i in proxy_list if not ( (i in bad) or (i  in existing)) ]
        
        if pbar:
          info_msg='got %d proxies (init: %d) from list after removeing %d bad and %d exisint' %(len(proxy_list),init_size,len(bad),len(existing))
          pbar.set_description(info_msg);
          # ~ print(info_msg);
          pbar.refresh()
        
        # ~ print('post: ',proxy_list)
        
        if self.random:
            random.shuffle(proxy_list)
        working_proxy = None
        for proxy_address in proxy_list:
            proxies = {self.schema: f'http://{proxy_address}'}
            try:
                working_proxy = self.__check_if_proxy_is_working(proxies)
                if working_proxy:
                    return working_proxy
            except requests.exceptions.RequestException:
                continue
        if not working_proxy and not repeat:
            if self.country_id is not None:
                self.country_id = None
            return self.get(repeat=True)
        raise FreeProxyException(
            'There are no working proxies at this time.')

    def __check_if_proxy_is_working(self, proxies):
        url = f'{self.schema}://{self.url}'
        ip = proxies[self.schema].split(':')[1][2:]
        with requests.get(url, proxies=proxies, timeout=self.timeout, stream=True) as r:
            if r.raw.connection.sock and r.raw.connection.sock.getpeername()[0] == ip:
                return proxies[self.schema]
        return


class ProxyManager:
    def __init__(self, pool_size=8,pbar=''):
        self.pool_size = pool_size
        self.working = []
        self.bad = set()
        self.pbar=pbar
        self.idx=0
        self.load_proxies(silent=True)
        self.working=[i for i in self.working if i not in self.bad]
        self.dump_proxies()

    # -------------------------
    # Get new proxy from FreeProxy
    # -------------------------
    def dump_proxies(self,silent=False):      
      af=open('.proxies','w')
      for pr in self.working:        af.write(str(pr)+'\n')
      af.close()
      
      af=open('.bad','w')
      for pr in self.bad:        af.write(str(pr)+'\n')
      af.close()
      
      if self.pbar:
        if not silent: self.pbar.set_description("dumped "+str(len(self.working))+" proxies to .proxies")
      else:
        print("dumped "+str(len(self.working))+" proxies to .proxies")
      
    def load_proxies(self,silent=False):      
      if os.path.exists('.proxies'):
        self.working=[i.strip() for i in open('.proxies').readlines() if i.strip() and ':' in i]      
        if self.pbar:
          if not silent: self.pbar.set_description("loaded "+str(len(self.working))+" proxies from .proxies")
        else:
          print("loaded "+str(len(self.working))+" proxies from .proxies")
      if os.path.exists('.bad'):
        self.bad=set([i.strip() for i in open('.bad').readlines() if i.strip() and ':' in i]      )
        if self.pbar:
          if not silent: self.pbar.set_description("loaded "+str(len(self.bad))+" bad proxies from .bad")
        else:
          print("loaded "+str(len(self.bad))+" bad proxies from .bad")
    
    
    def fetch_proxy(self):
        while True:
            try:
                # ~ p = FreeProxy(rand=True, timeout=0.5, https=True).get()
                # ~ print('tryinfg to get new https prxoy')
                
                if self.pbar:
                  self.pbar.set_description('tryinfg to get new  prxoy')
                else:
                  print('tryinfg to get new  prxoy')
                # ~ p = FreeProxy(rand=True, https=True).get()
                
                # ~ p = FreeProxy(rand=True).get()
                country_id=random.choice([None,['US'],['GB']])
                p = FreeProxy(country_id=country_id,rand=True,url='https://dharmamitra.org/').get(pbar=self.pbar)
                
                if p and p not in self.bad:
                    if self.pbar:
                      self.pbar.set_description('found new proxy: '+str(p))
                    else:
                      print('found new proxy: '+str(p))

                    return p
            except:
                pass

    # -------------------------
    # Fill pool
    # -------------------------
    def refill_pool(self):
        
        if self.pbar:
          self.pbar.set_description("Refilling proxy pool...")
        else:
          print("Refilling proxy pool...")
        while len(self.working) < self.pool_size:
            p = self.fetch_proxy()
            if p not in self.working:
                self.working.append(p)
                if self.pbar:
                  self.pbar.set_description("Added:"+str(p))
                else:
                  print("Added:", p)
        self.dump_proxies()
    
      
    # -------------------------
    # Get proxy from pool
    # -------------------------
    def get_proxy(self):
        # ~ if not self.working:
        if len(self.working)< self.pool_size:
            self.refill_pool()

        # ~ return random.choice(self.working)
        proxy = self.working[self.idx]
        self.idx = (self.idx + 1) % len(self.working)
        return proxy
        

    # -------------------------
    # Mark proxy bad
    # -------------------------
    def mark_bad(self, proxy):
        if self.pbar:
            self.pbar.set_description("Bad proxy:"+str(proxy))
        else:
            print("Bad proxy:", proxy)
        self.bad.add(proxy)
        self.dump_proxies(silent=True)
        
        if proxy in self.working:
            i = self.working.index(proxy)
    
            # fetch replacement proxy
            newp = None
            while not newp or newp in self.bad or newp in self.working:
                newp = self.fetch_proxy()
    
            # replace IN-PLACE (key change!)
            self.working[i] = newp
            self.idx = i   # ← KEY LINE

              
    
            if self.pbar:
                self.pbar.set_description(f"Replaced {proxy} -> {newp}")
            else:
                print(f"Replaced {proxy} -> {newp}")
    
            self.dump_proxies(silent=True)
        
        # ~ if proxy in self.working:
            # ~ self.working.remove(proxy)
            # ~ self.dump_proxies(silent=True)

    # -------------------------
    # POST with rotation
    # -------------------------
    def post(self, url,info_msg='', **kwargs):
        retries = kwargs.pop("retries", 5)

        for attempt in range(retries):
            proxy = self.get_proxy()
            if self.pbar:
              self.pbar.set_description("Using proxy:"+ str(proxy)+' :: '+info_msg)
            else:
              print("Using proxy:", proxy)

            proxies = {"http": proxy, "https": proxy}

            try:
                r = requests.post(
                    url,
                    proxies=proxies,
                    timeout=15,
                    verify=False,
                    **kwargs
                )

                if r.status_code >= 500:
                    raise requests.RequestException(f"{r.status_code} server error")

                return r

            except Exception as e:
                if self.pbar:
                  self.pbar.set_description(f"Attempt {attempt+1} failed:"+str(e))
                else:
                  print(f"Attempt {attempt+1} failed:", e)
                self.mark_bad(proxy)

                if len(self.working) < 2:
                    self.refill_pool()

                time.sleep(2 ** attempt)

        raise Exception("All proxies failed")


def get_full_text(el):
    """
    Extracts ALL text inside an element including nested tags.
    This prevents silent text loss.
    """
    return "".join(el.itertext()).strip()

def parse_tei(xml_path):
    parser = etree.XMLParser(remove_comments=True, recover=True)
    tree = etree.parse(str(xml_path), parser)
    root = tree.getroot()

    chunks = []
    counter = 1
    prefix = Path(xml_path).stem

    gatha_buffer = []
    gatha_meta = None  # stores tag/n of first gatha line

    for el in root.iter():
        tag = etree.QName(el).localname

        if tag not in TARGET_TAGS:
            continue

        text = get_full_text(el)
        if not text.strip():
            continue

        rend = el.attrib.get("rend", "")

        # ---------------- GATHA HANDLING ----------------
        if rend.startswith("gatha"):
            # start of a gatha block
            if not gatha_buffer:
                gatha_meta = {
                    "tag": tag,
                    "n": el.attrib.get("n"),
                }

            gatha_buffer.append(text)

            # end of gatha block
            if rend == "gathalast":
                chunk = {
                    "id": f"{prefix}_{counter:05d}",
                    "tag": gatha_meta["tag"],
                    "n": gatha_meta["n"],
                    "rend": "gatha",
                    "text": "\n".join(gatha_buffer)
                }
                chunks.append(chunk)
                counter += 1

                gatha_buffer = []
                gatha_meta = None

            continue

        # ---------------- FLUSH STRAY GATHA ----------------
        # if a gatha block was open but TEI is inconsistent
        if gatha_buffer:
            chunk = {
                "id": f"{prefix}_{counter:05d}",
                "tag": gatha_meta["tag"],
                "n": gatha_meta["n"],
                "rend": "gatha",
                "text": "\n".join(gatha_buffer)
            }
            chunks.append(chunk)
            counter += 1

            gatha_buffer = []
            gatha_meta = None

        # ---------------- NORMAL CHUNK ----------------
        chunk = {
            "id": f"{prefix}_{counter:05d}",
            "tag": tag,
            "n": el.attrib.get("n"),
            "rend": rend,
            "text": text
        }

        chunks.append(chunk)
        counter += 1

    # ---------------- FINAL SAFETY FLUSH ----------------
    if gatha_buffer:
        chunk = {
            "id": f"{prefix}_{counter:05d}",
            "tag": gatha_meta["tag"],
            "n": gatha_meta["n"],
            "rend": "gatha",
            "text": "\n".join(gatha_buffer)
        }
        chunks.append(chunk)

    # ---------------- VALIDATION ----------------
    all_xml_text = "".join(root.itertext())
    all_parsed_text = " ".join(c["text"] for c in chunks)

    print("XML chars:", len(all_xml_text))
    print("Parsed chars:", len(all_parsed_text))

    return chunks

def parse_tei_original(xml_path):
    parser = etree.XMLParser(remove_comments=True, recover=True)
    tree = etree.parse(str(xml_path), parser)
    root = tree.getroot()

    chunks = []
    counter = 1
    prefix = Path(xml_path).stem

    for el in root.iter():
        tag = etree.QName(el).localname

        if tag not in TARGET_TAGS:
            continue

        text = get_full_text(el)

        if not text.strip():
            continue

        chunk = {
            "id": f"{prefix}_{counter:05d}",
            "tag": tag,
            "n": el.attrib.get("n"),
            "rend": el.attrib.get("rend"),
            "text": text
        }

        chunks.append(chunk)
        counter += 1

    # ✅ VALIDATION CHECK GOES HERE
    all_xml_text = "".join(root.itertext())
    all_parsed_text = " ".join(c["text"] for c in chunks)

    print("XML chars:", len(all_xml_text))
    print("Parsed chars:", len(all_parsed_text))

    return chunks

import unicodedata

def sanitize_for_translation(s: str) -> str:
    s = unicodedata.normalize("NFC", s)
    for ch in ("\u200c", "\u200d", "\ufeff"):
        s = s.replace(ch, "")
    return s


def parse_sse(resp, debug=False):
    text = ""
    # ~ debug=True
    for raw in resp.iter_lines(decode_unicode=False):  # decode manually
        if debug: print('raw ',raw)
        if not raw:
            continue
        line = raw.decode("utf-8", errors="replace").strip()
        if not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if data == "[DONE]":
            break
        try:
            obj = json.loads(data)
        except Exception as e:
            if debug:
                print("JSON load error:", e, repr(data))
            continue
        if obj.get("type") == "text-delta":
            delta = obj.get("delta", "")
            text += delta
            if debug:
                print("DELTA:", repr(delta))
    return text


def translate_with_proxy(text='एवं मे सुतं' ,proxy=1, cid='s0402a.att_00004', debug=False,pm='',info_msg=''):
    
    # ~ if not proxy:
      # ~ from fp.fp import FreeProxy
      # ~ proxy = FreeProxy(rand=True,https=True).get()
      # ~ if debug: 
        # ~ print('freeproxy gave proxy: ',proxy)
    text = sanitize_for_translation(text)   # ← ADD THIS
    payload = {
        "input_sentence": text,
        "input_encoding": "auto",
        "target_lang": "hindi",
        "do_grammar_explanation": False,
        "model": "default",
        "messages": [{
            "role": "user",
            "id": cid,
            "parts": [{"type": "text", "text": text}]
        }]
    }

    for attempt in range(MAX_RETRIES):
        try:
            result = ''
            if proxy:
              # ~ if debug: 
                # ~ print('using proxy: ',proxy) 
              # ~ proxies = {"http": proxy, "https": proxy}
              r = pm.post(
                API_URL,info_msg=info_msg,headers=HEADERS, cookies=COOKIES,
                json=payload, stream=True
              )
              r.raise_for_status()
              result = parse_sse(r, debug=debug).strip()
            else:
              r = requests.post(
                  API_URL, headers=HEADERS, cookies=COOKIES,
                  json=payload, stream=True, timeout=120
              )
              r.raise_for_status()
              result = parse_sse(r, debug=debug).strip()
            
            
            if debug: 
                print('with proxy: ',proxy,' got translation: ',result) 
            return result
        except Exception as e:
            wait = BACKOFF_BASE ** attempt
            if debug:
                print(f"{cid} retry {attempt+1}: {e} → wait {wait}s")
            time.sleep(wait)
    raise RuntimeError(f"{cid} failed after retries")


def translate(text, cid, debug=False):
    text = sanitize_for_translation(text)   # ← ADD THIS
    payload = {
        "input_sentence": text,
        "input_encoding": "auto",
        "target_lang": "hindi",
        "do_grammar_explanation": False,
        "model": "default",
        "messages": [{
            "role": "user",
            "id": cid,
            "parts": [{"type": "text", "text": text}]
        }]
    }

    for attempt in range(MAX_RETRIES):
        try:
            r = requests.post(
                API_URL, headers=HEADERS, cookies=COOKIES,
                json=payload, stream=True, timeout=120
            )
            r.raise_for_status()
            result = parse_sse(r, debug=debug).strip()
            return result
        except Exception as e:
            wait = BACKOFF_BASE ** attempt
            if debug:
                print(f"{cid} retry {attempt+1}: {e} → wait {wait}s")
            time.sleep(wait)
    raise RuntimeError(f"{cid} failed after retries")

def main(json_file, debug=False,proxies_size=5,use_proxy=False, base_delay=None):
    
    if json_file=='mvl': #loop
      bb=[i.strip() for i in open('mvl').readlines() if os.path.exists(i.strip())]
      for ff in bb:
        print('processing file: ',ff)
        main(ff,debug=debug,proxies_size=proxies_size,use_proxy=use_proxy,base_delay=base_delay)
      return
      
    if json_file.endswith('.xml'):
      if not os.path.exists(Path(json_file).with_suffix(".json")) : #first parse
        xml_file=json_file
        if not os.path.exists(xml_file):
          print('xml_file: %s does not exist in ./' %(xml_file))
          return
        chunks = parse_tei(xml_file)
  
        out_file = Path(xml_file).with_suffix(".json")
    
        with open(out_file, "w", encoding="utf-8") as f:
            # ~ json.dump(chunks, f, ensure_ascii=False, indent=2)
            # ~ json.dump(chunks, f, ensure_ascii=False) #fast
            json.dump(chunks, f, ensure_ascii=False, separators=(",", ":")) #faster

    
        print(f"✅ Extracted {len(chunks)} chunks")
        print(f"✅ Saved to {out_file}")
        json_file=out_file
      else:
        json_file= Path(json_file).with_suffix(".json")

      
    with open(json_file, "r", encoding="utf-8") as f:
        chunks = json.load(f)
    
    
    
    # --- preprocess ---
    worklist = []
    for c in chunks:
        if "hi" in c and c["hi"]:
            continue
        if c.get("rend") in ("hangnum", "subhead"):
            c["hi"] = c["text"]  # copy as-is
            continue
        worklist.append(c)
    
    # tqdm over real work only
    pbarr = tqdm(worklist, desc="Translating chunks")
    
    # ~ pbarr=tqdm(chunks, desc="Translating chunks")
    if use_proxy:
      # ~ print('using proxies')
      pbarr.set_description('using proxies'.upper())
      pm=ProxyManager(pool_size=proxies_size,pbar=pbarr)
    
    if base_delay is not None:
      min_delay = base_delay
    else:
      if use_proxy:
        min_delay = 3
      else:
        min_delay = 5
        if ('GITHUB_REPOSITORY' in os.environ):
          # ~ print('reducing delay to 4s on github')
          min_delay = 5
       
          # ~ if 'lenovo' in os.uname().nodename.lower():
            # ~ min_delay=10
    max_delay = 240
    
    adaptive_delay = min_delay
    
    max_retries = 0
    last_save_time=0
    last_char_len=0
    last_save_loc=0
    err_cnt=0
    
    for c in pbarr:
        pbarr.refresh()
        possible_err=''
        cid = c["id"]
        
        if err_cnt>5:
          print(highlight_red+'got empty response more than 5 times. exiting!'+highlight_reset)
          # final save
          with open(json_file, "w", encoding="utf-8") as f:
              json.dump(chunks, f, ensure_ascii=False, indent=2)

          sys.exit(1)
    
        if "hi" in c and c["hi"]:
            pbarr.refresh()
            pbarr.set_description('already translated! '+cid)
            pbarr.refresh()
            continue
        
        # -------- skip certain rend types --------
        rend = c.get("rend","")
        
        if rend in ("hangnum", "subhead"):
            c["hi"] = c["text"]   # copy as-is
            pbarr.set_description(f"SKIP_COPY {rend}: {cid}")
             # AVOID save progress to save cpu time
            # ~ with open(json_file, "w", encoding="utf-8") as f:
                # ~ json.dump(chunks, f, ensure_ascii=False, indent=2)
            continue
            
        text = c["text"]
        pbarr.refresh()
    
        retries = 0
    
        while True:
            loop_start_time=time.time()
            try:              
              pbarr.refresh();
              
              
              if use_proxy:
                info_msg='POST-ing proxy: '+cid+' (l: '+str(len(text))+') ; last_recv_len: '+str(last_char_len)+' ; last_save_loc: '+str(last_save_loc)
                pbarr.set_description(info_msg)
                pbarr.refresh();
                hi = translate_with_proxy(text, cid, debug=debug,pm=pm,info_msg=info_msg)
                pbarr.refresh()
              else:
                pbarr.set_description('POST-ing: '+cid+' (l: '+str(len(text))+') ; last_recv_len: '+str(last_char_len)+' ; last_save_loc: '+str(last_save_loc))
                pbarr.refresh();
                hi = translate(text, cid, debug=debug)
                pbarr.refresh()
            except Exception as e:
              pbarr.set_description('Exception: '+cid+str(e))
              pbarr.refresh();
              break
    
            # -------- SUCCESS --------
            if hi:
                c["hi"] = hi
                
                
                if len(hi)==last_char_len: possible_err=highlight_red+'; ERR?? '+highlight_reset
    
                if debug:
                    print("TEXT:", text)
                    print("HINDI:", hi)
                    print(f"[OK] sleeping {adaptive_delay:.1f}s")
                pbarr.set_description('delay: %.1fs , -> %d chars, ' %(adaptive_delay,len(hi))+cid+possible_err)                
                pbarr.refresh()
                err_cnt=0
                if (time.time()-last_save_time) > 60: #save every minute only
                  # save progress
                  pbarr.set_description('saving progress afte cid: '+cid+possible_err)
                  pbarr.refresh()
                  with open(json_file, "w", encoding="utf-8") as f:
                      # ~ json.dump(chunks, f, ensure_ascii=False, indent=2)
                      # ~ json.dump(chunks, f, ensure_ascii=False) #fast
                      if ('GITHUB_REPOSITORY' in os.environ) or ('lenovo' in os.uname().nodename.lower()):
                        json.dump(chunks, f, ensure_ascii=False, separators=(",", ":"), indent=2) #faster
                      else:
                        json.dump(chunks, f, ensure_ascii=False, separators=(",", ":")) #faster
                  last_save_time=time.time()
                  last_save_loc=cid
    
                # gently reduce delay (speed up)
                adaptive_delay = max(min_delay, adaptive_delay * 0.85)
                pbarr.refresh()
                time_elapsed=time.time()-loop_start_time
                if time_elapsed < adaptive_delay:
                  time.sleep(adaptive_delay-time_elapsed)
                
                last_char_len=len(hi)
    
                # ~ time.sleep(adaptive_delay)
                break
    
            # -------- FAILURE / 429 --------
            retries += 1
    
            if retries > max_retries:
                if debug:
                    print(f"[WARN] skipping {cid}")
                pbarr.set_description(f"[WARN] skipping {cid} due to 429 err. delay %.1fs" %(adaptive_delay))
                pbarr.refresh()
                c["hi"] = ""
                err_cnt+=1
                break
    
            # increase delay (slow down)
            adaptive_delay = min(max_delay, adaptive_delay * 1.8)
    
            if debug:
                print(f"[BACKOFF] {cid} retry {retries}, sleep {adaptive_delay:.1f}s")
            pbarr.set_description(f"[BACKOFF] {cid} retry {retries}, sleep {adaptive_delay:.1f}s ,  "+cid)
            pbarr.refresh()
            time_elapsed=time.time()-loop_start_time
            if time_elapsed < adaptive_delay:
              pbarr.refresh()
              time.sleep(adaptive_delay-time_elapsed)
              pbarr.refresh()
    
    # final save
    with open(json_file, "w", encoding="utf-8") as f:
        json.dump(chunks, f, ensure_ascii=False, indent=2)
  
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("json_file", help="Input JSON file")
    parser.add_argument("--debug", action="store_true", help="Show debug output")
    parser.add_argument("--proxy", action="store_true", help="use proxy")
    parser.add_argument("--delay",    type=float,    default=None,    help="Override base delay in seconds")
    args = parser.parse_args()
    # ~ print('parser args: ',args)
    main(args.json_file, debug=args.debug,use_proxy=args.proxy,base_delay=args.delay)
