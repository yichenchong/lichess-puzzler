import time

from rank_bm25 import BM25Okapi
import os

# scan for all files in directory "out" and read them
# then convert to list of strings
# read all files in directory "out"
files = os.listdir("out")
corpus = []
for file in files:
    with open(f"out/{file}", 'r') as f:
        corpus.append(file + " " + f.read())

# tokenize the corpus
search = corpus[-1]
corpus = corpus[:-5]
tokenized_corpus = [doc.split() for doc in corpus]

# create the BM25 object
start = time.process_time()
bm25 = BM25Okapi(tokenized_corpus)
print(time.process_time() - start)
results = bm25.get_top_n(search.split(), corpus, n=3)
print(time.process_time() - start)
print(search.split()[0])
print([result.split()[0] for result in results])