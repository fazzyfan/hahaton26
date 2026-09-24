"""Одноразовый инспектор официальных CSV: заголовки, строки, счётчики."""
import codecs
import os

DIR = "Обезличивание"


def ascii_safe(text: str) -> str:
    return text.encode("ascii", "backslashreplace").decode("ascii")


for name in sorted(os.listdir(DIR)):
    path = os.path.join(DIR, name)

    if not name.endswith("Синтетические данные.csv"):
        continue

    with codecs.open(path, encoding="cp1251") as file:
        lines = file.read().splitlines()

    print(f"FILE: {ascii_safe(name)} | total_lines={len(lines)}")

    if lines:
        print(f"  header: {ascii_safe(repr(lines[0]))}")

    for line in lines[1:3]:
        print(f"  row: {ascii_safe(repr(line))}")

    for line in lines[-2:]:
        print(f"  tail: {ascii_safe(repr(line))}")


print("\n=== VALUE ANALYSIS ===")

from collections import Counter

bk_counter = Counter()
hd_counter = Counter()
gig_counter = Counter()
conn_counter = Counter()
job_counts = {}

for name in sorted(os.listdir(DIR)):
    path = os.path.join(DIR, name)

    if not name.endswith("Синтетические данные.csv"):
        continue

    with codecs.open(path, encoding="cp1251") as file:
        lines = file.read().splitlines()

    headers = lines[0].split(";")
    idx = {h: i for i, h in enumerate(headers)}
    jobs = 0

    for line in lines[1:]:
        cells = [c.strip() for c in line.split(";")]

        if not any(cells):
            continue

        if cells[0].lower().startswith("адрес офиса"):
            continue

        jobs += 1

        bk = cells[idx["Тип заявки BK"]] if "Тип заявки BK" in idx else ""
        hd = cells[idx["Тип заявки HD"]] if "Тип заявки HD" in idx else ""
        gig = cells[idx["Гигабитное подключение"]] if "Гигабитное подключение" in idx else ""
        conn = cells[idx["Подключение"]] if "Подключение" in idx else ""

        bk_counter[bk] += 1
        if hd:
            hd_counter[hd] += 1
        if gig:
            gig_counter[gig] += 1
        if conn:
            conn_counter[conn] += 1

    job_counts[name] = jobs

print("jobs per file:", {ascii_safe(k): v for k, v in job_counts.items()})
print("BK types:", {ascii_safe(k): v for k, v in bk_counter.items()})
print("HD types:", {ascii_safe(k): v for k, v in hd_counter.most_common(10)})
print("gigabit values:", {ascii_safe(k): v for k, v in gig_counter.items()})
print("connection values:", {ascii_safe(k): v for k, v in conn_counter.items()})