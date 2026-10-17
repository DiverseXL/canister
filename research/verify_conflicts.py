import json
import sys
import zipfile

DRAFT = "research/conflicts_draft.json"
ZIP = "var/benchmark/all_documents.zip"


def load_doc_texts(zf, names):
    texts = []
    for name in names:
        try:
            texts.append((name, zf.read(name).decode("utf-8", "replace")))
        except KeyError:
            pass
    return texts


def matches(span, texts):
    for name, text in texts:
        if span in text:
            return name
    return None


def main():
    draft = json.load(open(DRAFT, encoding="utf-8"))
    zf = zipfile.ZipFile(ZIP)
    members = zf.namelist()

    def members_for(doc_id):
        return [n for n in members if n.rsplit("/", 1)[-1].startswith(doc_id)]

    total = 0
    failures = 0
    for q in draft["questions"]:
        qid = q["question_id"]
        old_names = members_for(q["old_doc_id"])
        new_names = members_for(q["new_doc_id"])
        old_texts = load_doc_texts(zf, old_names)
        new_texts = load_doc_texts(zf, new_names)

        if not old_names:
            print(f"[{qid}] OLD DOC NOT FOUND: {q['old_doc_id']}")
            failures += 1
        if not new_names:
            print(f"[{qid}] NEW DOC NOT FOUND: {q['new_doc_id']}")
            failures += 1

        for field in ("old_span", "new_span"):
            total += 1
            span = q[field]
            pool = old_texts if field == "old_span" else new_texts
            where = matches(span, pool)
            if where:
                print(f"[{qid}] {field:<8} OK  ({where})")
                continue
            failures += 1
            joined = "\n".join(t for _, t in pool)
            matched = 0
            for cut in range(len(span), 0, -1):
                if span[:cut] in joined:
                    matched = cut
                    break
            ctx = span[max(0, matched - 30):matched + 30]
            print(f"[{qid}] {field:<8} FAIL: not found in {[n for n, _ in pool]}")
            print(f"        matched {matched}/{len(span)} chars near: ...{ctx}...")

        ss = q.get("supersession_sentence", "")
        if ss and ss != "UNSURE":
            total += 1
            where = matches(ss, new_texts)
            if where:
                print(f"[{qid}] {'super':<8} OK  ({where})")
            else:
                failures += 1
                print(f"[{qid}] {'super':<8} FAIL: not found in {[n for n, _ in new_texts]}")
        else:
            print(f"[{qid}] {'super':<8} n/a (UNSURE)")

    print("-" * 80)
    print(f"checks: {total}  failures: {failures}")
    zf.close()
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
