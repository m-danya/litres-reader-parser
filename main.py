from selenium import webdriver
from selenium.webdriver.common.by import By
from tqdm import tqdm
import math
import time
from datetime import datetime
import pickle
from pathlib import Path
import os
import requests
from bs4 import BeautifulSoup
import traceback
import argparse


def main():
    args = parse_args()
    book_links = (
        read_pickle_object('book_links') if args.cached else get_books_list()
    )
    seconds = ((2 + args.timeout) * len(book_links))
    print('book_links are ready for parsing')
    alarmer(f'started parsing. For parsing (without limits) the time'
            ' estimation is'
            f' {(seconds / 60):.2f}'
            f' mins = {(seconds / 3600):.2f} hours'
    )
    books_db = get_books_db(
        book_links, args.limit, args.start_with, args.timeout
    )
    alarmer(f'RESULT: {len(books_db)} books were parsed')
    print_top_books(books_db)


def parse_args():
    parser = argparse.ArgumentParser(description='Obtain stats about books'
                                                 ' that ЛитРес offers me'
                                                 ' to voice')
    parser.add_argument(
        '--cached',
        action=argparse.BooleanOptionalAction,
        help='Use the cached list of books (guarantees determinism)',
        required=True
    )
    parser.add_argument(
        '--limit',
        type=int,
        help='Limit the amount of parsed books'
    )
    parser.add_argument(
        '--start-with',
        type=int,
        help='Start with the given offset'
    )
    parser.add_argument(
        '--timeout',
        type=int,
        default=10,
        help='Timeout for parsing ЛитРес'
    )
    return parser.parse_args()


def get_books_list():
    driver = webdriver.Chrome()
    book_list_urls = [
        'https://reader.litres.ru/vybor/small',
        'https://reader.litres.ru/vybor/big',
        'https://reader.litres.ru/vybor/modern',
        'https://reader.litres.ru/vybor/samizdat'
    ]

    book_links = []

    with open('SECRET_LINK.txt') as f:
        login_link = f.read()
    driver.get(login_link)

    for i, book_list_url in enumerate(book_list_urls):
        book_list_url += '?sort=name-book' + '&per-page=100&page='
        driver.get(book_list_url)
        books_n = driver.find_element(By.CLASS_NAME, "summary").text
        books_n = books_n[books_n.find('из') + 3:-1].replace(' ', '')
        books_n = int(books_n)
        print(f'{books_n} are need to be parsed ({i+1}/4)')
        for page in tqdm(range(1, math.ceil(books_n / 100) + 1)):
            page_url = book_list_url + str(page)
            driver.get(page_url)
            for book_button in driver.find_elements(By.PARTIAL_LINK_TEXT,
                                                    'ОТКРЫТЬ НА LITRES'):
                book_links.append(book_button.get_attribute("href"))
            time.sleep(0.5)
    driver.close()
    save_pickle_object(book_links, 'book_links')
    return book_links


def get_books_db(book_links, limit, start_with, timeout):
    books_db = []
    if start_with:
        book_links = book_links[start_with:]
    if limit:
        book_links = book_links[:limit]
    try:
        for i, book_link in (pbar := tqdm(enumerate(book_links))):
            pbar.set_description(book_link)
            headers = {
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_1) '
                              'AppleWebKit/537.36 (KHTML, like Gecko) '
                              'Chrome/39.0.2171.95 Safari/537.36'}
            tries = 0
            ok = False
            is_404 = False
            while tries < 5 and not ok:
                r = requests.get(book_link, headers=headers, timeout=60)
                if r.status_code != 200:
                    if r.status_code == 404:
                        print(f'404: {book_link}')
                        is_404 = True
                        ok = True
                        break
                    # smth bad happen, try again in a moment
                    tries += 1
                    print(f'status code is {r.status_code}! Full html:'
                          f'\n{r.text}')
                    time.sleep(5)
                else:
                    ok = True
            if not ok:
                alarmer('STRANGE STATUS CODE for 5 times in a row!')
                continue
            if tries > 0:
                alarmer('reestablished')

            if is_404:
                continue

            soup = BeautifulSoup(r.text, 'html.parser')
            try:
                title = soup.find('div', {
                    'class': 'biblio_book_name biblio-book__title-block'})
                title = title.h1.text
            except Exception as e:
                alarmer(f"Couldn't find a book name! {book_link=}")
                print(e)
                print(traceback.format_exc())
                break  # something is definitely goes wrong
            author = '—'
            try:
                author = soup.find('div', {'class': 'biblio_book_author'})
                author = author.text[len('Автор:'):]
            except Exception as e:
                alarmer(f"Couldn't find the author of the book! {book_link=}")
            mean = 0
            n_votes = 0
            try:
                soup.find(itemprop="aggregateRating")
                rating_div = soup.find(itemprop="aggregateRating")
                mean = rating_div.findChild("div", {'class': "rating-number"}).text
                mean = float(mean.replace(',', '.'))
                n_votes = rating_div.findChild("div", {'class': "votes-count"}).text
                n_votes = int(n_votes.replace(' ', ''))
            except AttributeError as e:
                pass
            pages = 0
            published = 'never'
            try:
                info_block = soup.find('ul',
                                       {'class': 'biblio_book_info_detailed_left'})
                info_lis = info_block.findAll('li')
                for info in info_lis:
                    if 'Дата выхода на ЛитРес' in info.text:
                        published = info.text[len('Дата выхода на ЛитРес: '):]
                    if 'Объем: ' in info.text:
                        pages = info.text
                        pages = pages[len('Объем: '):pages.find('стр.')]
                        pages = int(pages)
            except AttributeError as e:
                pass
            book = {
                'author': author,
                'title': title,
                'pages': pages,
                'mean_rating': mean,
                'n_votes': n_votes,
                'link': book_link,
                'published': published
            }
            books_db.append(book)
            time.sleep(timeout)
        save_pickle_object(books_db, f'books_db_{len(books_db)}')
    except BaseException as e:  # even the KeyboardInterrupt
        save_pickle_object(books_db, f'books_db_{len(books_db)}')
        alarmer('Couldn\'t dump all the books info! (but info'
                f' about {len(books_db)} books was saved)')
        print(e)
        print(traceback.format_exc())
    return books_db


def save_pickle_object(obj, prefix: str):
    filename = prefix + '_' + datetime.now().strftime("%m-%d-%Y_%H-%M") + '.pkl'
    output_folder = Path('output')
    output_folder.mkdir(exist_ok=True)
    with open(output_folder / filename, 'wb') as f:
        pickle.dump(obj, f)


def read_pickle_object(prefix):
    output_folder = Path('output')
    # get the most recent file
    paths = sorted(Path(output_folder).iterdir(), key=os.path.getmtime)
    idx = -1
    # having the wanted prefix
    while prefix not in paths[idx].name:
        idx -= 1
    with open(paths[idx], 'rb') as f:
        print(f'Using {f.name} as a book_links list')
        obj = pickle.load(f)
    return obj


def print_top_books(books_db):
    top_n = 25
    print(f'Top-{top_n} books: ')
    for book in sorted(books_db, key=lambda book: -book['n_votes'])[:top_n]:
        print(book)


# Send a message to Telegram to notify me
def alarmer(msg):
    print(msg)
    try:
        with open('ALARMER_API_KEY.txt') as f:
            api_key = f.read()
        requests.get(
            f'https://alarmerbot.ru/?key={api_key}&message={msg}'
        )
    except Exception as e:
        pass


if __name__ == "__main__":
    main()
