import sys
from aiohttp import connector
#sys.path.append('D:/chinese')
from bs4 import BeautifulSoup, SoupStrainer, Tag, NavigableString
from progress.bar import Bar
from pprint import pprint
import asyncio
import aiohttp
import requests
import cchardet
import string
import json
import time
import lxml
import os
import re
from utils import *

with open('cedict.json', 'rb') as f:
#with open('../cedict/cedict.json', 'rb') as f:
    cedict = json.load(f)
with open('chars.json', 'rb') as f:
#with open('../chars/chars.json', 'rb') as f:
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

soup_time = 0

def char_tags(name, attrs):
    return name == 'div' and 'class' in attrs and attrs['class'] == 'content definitions jnr'

def word_tags(name, attrs):
    return 'class' in attrs and \
        (name == 'div' and attrs['class'] == 'jnr' or \
        name == 'span' and attrs['class'] == 'dicpy')

def split_numbered(text):
    defs = []
    start = 0
    end = 0
    count = 1
    while True:
        delim = f'{count}.'
        end = text.find(f'{count}.', start)
        if end != -1:
            if count != 1:
                defs.append(full_width(text[start:end].strip()))
            start = end + len(delim)
        else:
            defs.append(text[start:].strip())
            return defs
        count += 1
        

def parse_zdic(word, data, zdic):
    global soup_time
    start = time.time()

    # finding title
    title = data.find('</title>')
    if data[title - 2 : title] != '解释':
        return
        

    content_start, content_end = -1, -1
    if len(word) == 1:
        content_tag = '<div class="content definitions jnr">'
        content_start = data.find(content_tag, title)
        if content_start != -1:
            content_end = data.find('</div>', content_start) + 6
        if content_start == -1 or content_end == -1:
            return

        soup = BeautifulSoup(data[content_start:content_end], 'lxml')

        soup_time += time.time() - start


        div = soup.find('div')


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

        dicpy_start, dicpy_end = -1, -1
        dicpy_tags = ['<span class = "dicpy"', '<span class="dicpy"']
        for tag in dicpy_tags:
            dicpy_start = data.find(tag)
            if dicpy_start == -1:
                continue
            else:
                dicpy_end = data.find('>', dicpy_start + len(tag) + 1) + 1
                break
        if dicpy_start == -1 or dicpy_end == -1:
            print('dicpy???')
            return
        
        content_tag = '<div class="jnr">'
        content_start = data.find(content_tag, dicpy_end)
        if content_start != -1:
            content_end = data.find('</div>', content_start) + 6
        if content_start == -1 or content_end == -1:
            return
        

        soup = BeautifulSoup(data[dicpy_start:dicpy_end] + data[content_start:content_end], 'lxml')

        soup_time += time.time() - start

        div = soup.find('div', 'jnr')

        zdic[word] = {}
        tags = []
        pinyin = ''
        single_pinyin = len(div.find_all('span', class_ = 'dicpy')) <= 1
        if single_pinyin:
            pinyin = soup.find('span', class_ = 'dicpy').text.strip()
            zdic[word][pinyin] = []

        if len(div.contents) == 1:
            if isinstance(div.contents[0], NavigableString):
                text = str(div.contents[0])
            else:
                text = div.contents[0].text
            for definition in split_numbered(text):
                zdic[word][pinyin].append(definition)
            return
        
        def_count = 0
        definition = ''
        
        for p in div.children:
            if isinstance(p, NavigableString):
                stripped = str(p).strip()
                if stripped:
                    definition += full_width(stripped)
            elif p.name == 'li':
                for definition in split_numbered(p.text):
                    zdic[word][pinyin].append(definition)
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

async def download(session, word, chars, bar, retry):
    global parsing_time
    retry[word] = 0
    while True:
        try:
            if retry[word] >= 5:
                retry[word] = 6
                #print('\nRetry limit:', word)
                return
            async with session.get(f'https://www.zdic.net/hans/{word}') as response:
                if response.status == 200:
                    data = await response.read()
                    start = time.time()
                    try:
                        parse_zdic(word, str(data, response.charset), chars)
                    except Exception as e:
                        print('\nParse exception:', word, e.__class__.__name__, e)

                    parsing_time += time.time() - start
                    bar.next()
                    return
        except Exception as e:
            retry[word] += 1
            continue

    

async def main():
    print('Reading words')
    with open('words.txt', encoding = 'utf8') as f:
    #with open('../dicts/words.txt', encoding = 'utf8') as f:
        words = [x.strip() for x in f.readlines()]

    bar = Bar(max = len(words))


    start = time.time()
    print('Downloading and parsing')
    

    chunk = 10000
    count = 0

    timeout = aiohttp.ClientTimeout(sock_connect = 5)
    connector = aiohttp.TCPConnector(limit = 500)
    retry = {}
    async with aiohttp.ClientSession(timeout = timeout, connector = connector) as session:
        while True:
            zdic = {}
            
            await asyncio.gather(*(download(session, words[i], zdic, bar, retry) for i in range(count, min(len(words), count + chunk))))
            with open('zdic.json', 'a', encoding = 'utf8') as f:
                entries = ',\n'.join(f'{json.dumps(word, ensure_ascii = False)}: {json.dumps(zdic[word], ensure_ascii = False, indent = 4)}' for word in zdic if zdic[word] != {})
                f.write(entries)
                f.write(',\n')
            count += chunk
            if count >= len(words):
                break

    with open('retry.txt', 'w', encoding = 'utf8') as f:
        f.write('\n'.join([word for word in retry if retry[word] == 6]))


    global parsing_time
    global soup_time
    print('\nTotal:', time.time() - start)
    print('Parsing:', parsing_time)
    print('Soup:', soup_time)


        

if __name__ == '__main__':
    #asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    test = False

    if test:
        zdic = {}
        word = '一交'
        if os.path.isfile(f'{word}.html'):
            with open(f'{word}.html', encoding = 'utf8') as f:
                data = f.read()
        else:
            while True:
                try:
                    data = requests.get(f'https://www.zdic.net/hans/{word}').text
                    with open(f'{word}.html', 'wb') as f:
                        f.write(data)
                    break
                except:
                    continue

        parse_zdic(word, data, zdic)

        pprint(zdic)

    else:
        asyncio.run(main())
