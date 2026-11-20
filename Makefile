.PHONY: setup test check lint clean login

setup:
	python3 -m venv .venv
	.venv/bin/pip install -q -e .
	@echo "Ready. Use '.venv/bin/avy', 'make login', or 'make test'."

test:
	python3 -m unittest discover -s tests -v

check: test
	bash scripts/check-secrets.sh

lint:
	python3 -m compileall -q avy.py avy-login.py avy_login.py tests

login:
	.venv/bin/avy-login

clean:
	rm -rf .venv __pycache__ tests/__pycache__
