.PHONY: setup test check lint clean login

setup:
	python3 -m venv .venv
	.venv/bin/pip install -q --upgrade pip
	.venv/bin/pip install -q qrcode pillow
	@echo "Ready. Use '.venv/bin/python avy.py ...' or 'make test'."

test:
	python3 -m unittest discover -s tests -v

check: test
	bash scripts/check-secrets.sh

lint:
	python3 -m compileall -q avy.py avy-login.py tests

login:
	python3 avy-login.py

clean:
	rm -rf .venv __pycache__ tests/__pycache__
