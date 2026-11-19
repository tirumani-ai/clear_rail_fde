"""STEP 3b: copy the scans into text, then split each file into its papers. The split is plain code.

A scan or photo has no text, so a vision model copies each picture page into text (saved, so a second run is
free and identical). Then ordinary rules decide what each paper is and where it ends: a page whose first lines
carry a title (COMMERCIAL INVOICE, PROFORMA INVOICE, PURCHASE ORDER, SERVICES AGREEMENT, ... BANK DETAILS) starts
a paper; a page with no title continues the paper before it (app/ingestion/split.py).

Only when a paper has no title code knows is the step 2 classifier asked. That is the fallback, not the rule.

Run:  ./run.sh ladder/step3/b_split.py                 (all 32 cases: 20 picture pages go to the vision model)
      ./run.sh ladder/step3/b_split.py                 (again: nothing is called)
      ./run.sh ladder/step3/b_split.py --hide-titles   (pretend no title can be read: every paper goes to the classifier)
"""
import collections

from common import answer_key, case_dirs, files, flags

from app.cache import cached
from app.ingestion.papers import page_texts
from app.ingestion.readers import read_document
from app.ingestion.split import split_papers
from app.models import classify


def expected_kinds(row: dict, name: str) -> list[str]:
    f = next(f for f in row["files"] if f["file"] == name)
    return [s["doc_type"] for s in f["segments"]] if f.get("bundle") else [f["doc_type"]]


def main():
    hide = "--hide-titles" in flags()
    key, score, by = answer_key(), collections.Counter(), collections.Counter()
    made = saved = 0
    for case in case_dirs():
        for path in files(case):
            doc = read_document(path)
            if doc.fmt == "json":
                continue
            texts, now, before = page_texts(doc)
            made, saved = made + now, saved + before
            kinds = []
            for part in split_papers(texts, use_titles=not hide):
                kind, how = part.kind, "title"
                if kind is None:
                    text = "\n\n".join(texts[part.start - 1: part.end])
                    kind, _ = cached("kind", f"{doc.fingerprint}-p{part.start}", lambda: classify(text))
                    how = "classifier"
                by[how] += 1
                kinds.append(f"{kind} (pages {part.start}-{part.end}, by {how})")
            want = expected_kinds(key[case.name], path.name)
            got = [k.split(" ")[0] for k in kinds]
            score["right" if got == want else "wrong"] += 1
            mark = "" if got == want else f"   <- answer key: {want}"
            source = "vision" if doc.pages_needing_vision else "text"
            print(f"{case.name}/{path.name:28} read by {source:6} {len(texts)} page(s) -> {', '.join(kinds)}{mark}")
    print(f"\nFiles split and named as the answer key says: {score['right']}/{score['right'] + score['wrong']}. "
          f"Papers named by title: {by['title']}, by the classifier: {by['classifier']}.")
    print(f"Vision: {made} page(s) transcribed now, {saved} already saved.")


if __name__ == "__main__":
    main()
