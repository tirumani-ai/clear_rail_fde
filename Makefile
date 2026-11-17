.PHONY: setup check data spec
setup:  ## create .env from the template (never overwrites an existing one)
	@test -f .env && echo ".env already exists" || (cp .env.example .env && echo "Created .env: put your Gemini key in it")
check:  ## prove Docker, the sample data and (if set) the key work
	./run.sh check.py
data:   ## rebuild data/ from data/datagen/generate.py (same fonts and library versions every time)
	docker run --rm -v "$$PWD/data:/data" -w /data/datagen python:3.12-slim sh -c \
	  "apt-get update -qq >/dev/null && apt-get install -y -qq fonts-dejavu-core >/dev/null && \
	   pip install -q --root-user-action=ignore reportlab==4.4.4 openpyxl==3.1.5 pillow==12.3.0 && python generate.py"
spec:   ## rebuild docs/ClearRail_Use_Cases.pdf from its HTML source (uses the installed Google Chrome)
	uv run -q --with playwright==1.55.0 python docs/build_spec.py
