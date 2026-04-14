sources = NetBox RPKI Plugin

.PHONY: test test-fast test-contract test-full unittest format lint pre-commit clean

test: test-contract

test-fast:
	./devrun/test.sh fast

test-contract:
	./devrun/test.sh contract

test-full:
	./devrun/test.sh full

unittest: test-full

format:
	isort $(sources) tests
	black $(sources) tests

lint:
	flake8 $(sources) tests

pre-commit:
	pre-commit run --all-files

clean:
	rm -rf *.egg-info
	rm -rf .tox dist site
