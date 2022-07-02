import argparse
import pickle
from pathlib import Path
from tabulate import tabulate


def main():
    args = parse_args()
    books_db = collect_books_from_files(args)
    books_db = sort_books(books_db, args)
    trim_strings(books_db)
    print(tabulate(books_db, headers="keys"))


def parse_args():
    parser = argparse.ArgumentParser(
        description="Show best books from parsed for a voiceover"
    )
    parser.add_argument(
        "-d",
        "--directory",
        help="directory with books_db_* files",
        type=Path,
        required=True,
    )
    parser.add_argument("--pages-limit", type=int, default=0)
    parser.add_argument(
        "--only-without-audiobooks",
        action="store_true",
    )
    parser.add_argument("--limit-output", type=int, default=500)
    parser.add_argument(
        "--skip-unwanted-authors-txt",
        type=Path,
        help="a list of unwanted authors in txt, separated by a line break",
    )
    return parser.parse_args()


def collect_books_from_files(args):
    directory: Path = args.directory
    assert directory.is_dir()
    books_db = []
    for file in directory.iterdir():
        if "books_db" not in file.name:
            continue
        with open(file, "rb") as f:
            lst = pickle.load(f)
            new_books = [book for book in lst if book not in books_db]
            books_db.extend(new_books)
    return books_db


def sort_books(books_db, args):
    full_length = len(books_db)
    if args.skip_unwanted_authors_txt:
        with open(args.skip_unwanted_authors_txt) as f:
            unwanted_authors = [a.strip() for a in f]
        books_db = [b for b in books_db if b["author"] not in unwanted_authors]
    if args.only_without_audiobooks:
        books_db = [b for b in books_db if not b["has_audiobook"]]
    if args.pages_limit:
        books_db = [b for b in books_db if b["pages"] <= args.pages_limit]
    print(
        f"{len(books_db)} books were chosen from"
        f" {full_length} to meet the criteria."
    )
    print()
    # sort by n_votes
    books_db = sorted(books_db, key=lambda book: -book["n_votes"])
    if args.limit_output:
        books_db = books_db[: args.limit_output]
    return books_db


def trim_strings(books_db):
    for book in books_db:
        n = 20
        if len(book["author"]) > n:
            book["author"] = book["author"][: n - 3] + "..."
        if len(book["title"]) > n:
            book["title"] = book["title"][: n - 3] + "..."


if __name__ == "__main__":
    main()
