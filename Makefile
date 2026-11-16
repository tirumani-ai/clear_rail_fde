.PHONY: setup check
setup:  ## create .env from the template (never overwrites an existing one)
	@test -f .env && echo ".env already exists" || (cp .env.example .env && echo "Created .env: put your Gemini key in it")
check:  ## prove Docker, the sample data and (if set) the key work
	./run.sh check.py
