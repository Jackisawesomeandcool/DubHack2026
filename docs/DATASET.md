# Shared dataset

`backend/dataset/` is the catalog (products) plus its cutout images, committed to git. A teammate
only needs `git pull` and to start the backend: on start it copies the images and adds any missing
products to their local database (no scraping, takes a second).

## Everyone, once per clone
```
git config core.hooksPath .githooks     # every commit then refreshes backend/dataset automatically
pip install -r backend/requirements-local.txt
```

## Publishing your data
Normal `git add ... && git commit && git push`. The pre-commit hook exports your local catalog into
`backend/dataset/` and stages it. Without the hook: `cd backend && python3 dataset.py export`, then
`git add backend/dataset`.

## Rules
* Export **merges**: it adds/updates your products and never deletes products just because you do not
  have them. Products are only deleted when someone removes them with `view_catalog.py` (the x button),
  which puts the URL on `removed.json`; everyone's backend deletes it on the next start and scrapers skip it.
* Pull before you scrape/review, and run `python3 dataset.py load` (or just start the backend) before you
  commit, so you start from the shared data. The hook does the load for you.
* Images are shrunk to <= 900 px and 256 colors; unchanged images never change, so git history stays small.
* `python3 dataset.py status` shows how your local catalog and the dataset differ.
* Two people editing the same product line in `catalog.json` at once can conflict; resolve by keeping both
  sides' lines (one product per line) and run `python3 dataset.py load`.
* Images are retailer product photos. Fine for a hackathon demo; do not redistribute them.
