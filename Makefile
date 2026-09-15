.PHONY: install install-extraction test run

install:
	pip install -r requirements.txt

install-extraction:
	pip install -r requirements-extraction.txt
	playwright install chromium

test:
	pytest -q

run:
	python3 web_viewer.py
