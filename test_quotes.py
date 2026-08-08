import sys
lines = open('backend/api/main.py', encoding='utf-8').readlines()
quotes = [i+1 for i, l in enumerate(lines) if '\"\"\"' in l]
for q in quotes:
    print(f'{q}: {lines[q-1].strip()}')
