import sys
sys.path.append('D:/chinese')
from bs4 import BeautifulSoup, Tag, NavigableString
from progress.bar import Bar
from pprint import pprint
import asyncio
import aiohttp
import requests
import string
import json
import time
import os
import re
from utils import *

with open('../cedict/cedict.json', 'rb') as f:
    cedict = json.load(f)
with open('../chars/chars.json', 'rb') as f:
    chars = json.load(f)


pinyin_chars = set('āáǎàĀÁǍÀēéěèĒÉĚÈīíǐìĪÍǏÌōóǒòŌÓǑÒūúǔùŪÚǓÙüǖǘǚǜÜǕǗǙǛ' + string.ascii_letters)

def remove_invalid(text):
    chars = []
    for char in text:
        if char in pinyin_chars:
            chars.append(char)
    return ''.join(chars)


def get_pinyin(word, pinyin):
    pinyin = remove_invalid(pinyin)
    if word in cedict:
        for pinyin_cedict in cedict[word]:
            if pinyin == pinyin_cedict.replace(' ', ''):
                return pinyin_cedict
    pinyin_join = []
    for char in word:
        if char.isascii():
            pinyin_join.append(char)
            pinyin = pinyin[1:]
            continue
        found = False
        for pinyin_char in chars[char]:
            if pinyin[:len(pinyin_char)] == pinyin_char:
                pinyin_join.append(pinyin_char)
                pinyin = pinyin[len(pinyin_char):]
                found = True
                break
        if not found:
            return pinyin
    return ' '.join(pinyin_join)



def parse_zdic(word, data, zdic):
    soup = BeautifulSoup(data, 'html.parser')
    # word not found
    if soup.title.text[-2:] != '解释':
        return

    if len(word) == 1:
        
        div = soup.find('div', 'content definitions jnr')
        if not div:
            return
        zdic[word] = {}
        tags = [tag for tag in div.contents if isinstance(tag, Tag)]
        for i in range(len(tags)):
            try:
                if tags[i].contents[0]['class'][0] == 'dicpy':
                    pinyin = tags[i].contents[0].text.split()[0]
                    zdic[word][pinyin] = []
            except:
                continue
            offset = 2 if tags[i + 1].name == 'hr' else 1
            if tags[i + offset].name == 'ol':
                for tag in tags[i + offset].contents:
                    if isinstance(tag, Tag):
                        zdic[word][pinyin].append(full_width(tag.text.replace('◎', '').strip()))
            else:
                zdic[word][pinyin].append(full_width(tags[i + offset].text.replace('◎', '').strip()))
    else:
        div = soup.find('div', 'jnr')
        if not div:
            return
        zdic[word] = {}
        tags = []
        pinyin = ''
        single_pinyin = len(div.find_all('span', class_ = 'dicpy')) <= 1
        if single_pinyin:
            pinyin = soup.find('span', class_ = 'dicpy').text.strip()
            zdic[word][pinyin] = []
        def_count = 0
        definition = ''
        
        for p in div.children:
            if isinstance(p, NavigableString):
                stripped = str(p).strip()
                if stripped:
                    definition += full_width(stripped)
            elif p.name == 'li':
                definition += full_width(p.text.strip())
            else:
                for tag in p.children:
                    if isinstance(tag, NavigableString):
                        stripped = str(tag).strip('◎∶·\n ')
                        if stripped:
                            definition += full_width(stripped)
                    elif not tag.has_attr('class'):
                        continue
                    elif tag['class'][0] == 'dicpy' and not single_pinyin:
                        def_count = 0
                        if definition:
                            zdic[word][pinyin].append(definition)
                            definition = ''
                        pinyin = get_pinyin(word, tag.text)
                        zdic[word][pinyin] = []
                    elif tag['class'][0] == 'cino':
                        # if numeric tag is used to enumerate definitions, append current definition
                        # otherwise it is part of zh definition
                        if int(str(tag.text).strip('()')) == def_count + 1:
                            def_count += 1
                            if definition:
                                zdic[word][pinyin].append(definition)
                                definition = ''
                        else:
                            definition += full_width(tag.text)
                    elif tag['class'][0] == 'encs':
                        # correct spacing around punctuation
                        def_en = re.sub(r';([^\s])', r'; \1', tag.text.strip('\n []'))
                        def_en = re.sub(r'([^\s])\(', r'\1 (', def_en)
                        def_en = re.sub(r'\)([^\s])', r') \1', def_en)
                        if not is_cjk(def_en):
                            definition += def_en + '; '
                    elif tag['class'][0] == 'diczx1' and not (tag.find('span', class_ = 'smcs') or tag.text[-2:] == '——'):
                        # if tag is an example but not a quote, add to `usage`
                        if definition[-1] != '。':
                            definition += '：'
                        definition += f'“{full_width(tag.text.strip(" ；。！"))}”。'
                    else:
                        break
        if definition:
            zdic[word][pinyin].append(definition)

parsing_time = 0


async def download(session, word, chars, bar):
    global parsing_time
    global timeout
    while True:
        try:
            async with session.get(f'https://www.zdic.net/hans/{word}') as response:
                if response.status == 200:
                    data = await response.read()
                    if data:
                        try:
                            start = time.time()
                            parse_zdic(word, data, chars)
                            parsing_time += time.time() - start
                            bar.next()
                            return
                        except Exception as e:
                            print('\nPARSE ERROR', word, e.__class__.__name__, e)
                elif response.status == 514:
                    continue
                else:
                    print(response.status)
        except Exception as e:
            print('\nword download', word, e.__class__.__name__, e)
    

async def main():
    with open('../dicts/words.txt', encoding = 'utf8') as f:
        words = [x.strip() for x in f.readlines()][10000:14000]

    zdic = {}
    bar = Bar(max = len(words))
    
    timeout = aiohttp.ClientTimeout(total = 300)
    async with aiohttp.ClientSession(timeout = timeout) as session:
        await asyncio.gather(*(download(session, word, zdic, bar) for word in words))

    with open('zdic.json', 'w', encoding = 'utf8') as f:
        json.dump(zdic, f, ensure_ascii = False, indent = 4, sort_keys = True)



if __name__ == '__main__':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    

    test = False

    if test:
        zdic = {}
        word = '三折喇叭形反射器天线'
        if False and os.path.isfile(f'{word}.html'):
            with open(f'{word}.html', 'rb') as f:
                data = f.read()
        else:
            while True:
                try:
                    data = requests.get(f'https://www.zdic.net/hans/{word}').content
                    with open(f'{word}.html', 'wb') as f:
                        f.write(data)
                    break
                except:
                    continue

        parse_zdic(word, data, zdic)

        pprint(zdic)

    else:
        start = time.time()
        
        asyncio.run(main())
        print('\n', time.time() - start, parsing_time)
