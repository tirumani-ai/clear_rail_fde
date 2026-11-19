"""STEP 3a: read cheaply. Plain rules pick the cheapest reader for each file. No model is called.

  payment instruction JSON  already a form: read by code
  text PDF                  the text is in the file
  Excel invoice             each sheet becomes a page of text
  scan or photo             only these need a vision model (step 3b), and only for their picture pages

Run:  ./run.sh ladder/step3/a_read.py                    (four cases that hold every format, then totals for all 32)
      ./run.sh ladder/step3/a_read.py PAY-202611021
"""
import collections

from common import CASES, DEMO, case_dirs, files

from app.ingestion.readers import read_document


def main():
    for case in case_dirs(DEMO):
        print(case.name)
        for path in files(case):
            doc = read_document(path)
            print(f"  {path.name:30} {doc.fmt:12} fingerprint {doc.fingerprint[:8]}   pages for a vision model: {len(doc.pages_needing_vision)}")

    count, vision_pages, vision_files, total = collections.Counter(), 0, 0, 0
    for path in sorted(CASES.glob("PAY-*/*")):
        doc = read_document(path)
        count[doc.fmt] += 1
        vision_pages += len(doc.pages_needing_vision)
        vision_files += bool(doc.pages_needing_vision)
        total += 1
    print(f"\nAll {total} UC1 files: {dict(count)}")
    print(f"Files that need the vision model: {vision_files} ({vision_pages} pages). "
          f"Read by code with no model at all: {count['json']} payment instructions.")


if __name__ == "__main__":
    main()
